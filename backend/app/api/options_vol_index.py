"""Volatility-index routes and synchronization for the options API."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from flask import jsonify, request

from ..config import Config
from ..container import get_container
from ..http import error_response
from . import options_bp

logger = logging.getLogger(__name__)

_HISTORY_CACHE_TTL_SECONDS = 15.0
_LATEST_CACHE_TTL_SECONDS = 5.0
_COLLECT_COOLDOWN_SECONDS = 45.0
_history_cache: dict[tuple, dict] = {}
_latest_cache: dict[str, dict] = {}
_collect_states: dict[str, dict] = {}
_cache_lock = threading.Lock()


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _read_cache(cache: dict, key):
    now = time.time()
    with _cache_lock:
        entry = cache.get(key)
        if not entry:
            return None
        if float(entry.get("expires_at", 0.0)) <= now:
            cache.pop(key, None)
            return None
        return entry.get("value")


def _write_cache(cache: dict, key, value, ttl_seconds: float) -> None:
    with _cache_lock:
        cache[key] = {
            "value": value,
            "expires_at": time.time() + max(float(ttl_seconds), 0.0),
        }


def _invalidate_cache(underlying: str | None = None) -> None:
    normalized = str(underlying or "").strip()
    with _cache_lock:
        if normalized:
            for key in list(_history_cache):
                if key and key[0] == normalized:
                    _history_cache.pop(key, None)
            _latest_cache.pop(normalized, None)
            return
        _history_cache.clear()
        _latest_cache.clear()


def _collect_state(underlying: str) -> dict:
    normalized = str(underlying or "IBOVE Index").strip() or "IBOVE Index"
    with _cache_lock:
        state = _collect_states.get(normalized)
        if state is None:
            state = {"lock": threading.Lock(), "last_completed_at": 0.0}
            _collect_states[normalized] = state
        return state


def _parse_iso_datetime(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _record_from_iv_payload(
    service,
    iv_payload: dict | None,
    *,
    date_override: str | None = None,
    force: bool = False,
    option_count_override=None,
):
    payload = dict(iv_payload or {})
    if not payload:
        return None
    spot_value = (
        _safe_float(
            payload.get("spot_price") or payload.get("reference_price"),
            0.0,
        )
        or 0.0
    )
    return service.record_snapshot(
        prepared_options=[],
        market_context={"spot_price": float(spot_value), "forward_price": float(spot_value)},
        date=date_override,
        force=force,
        iv_payload=payload,
        option_count_override=option_count_override or payload.get("chain_size"),
        captured_at_override=payload.get("captured_at"),
    )


def _safe_float(value, default=None):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _compact_intraday_record(record) -> dict:
    payload = dict(record or {})
    return {
        "date": payload.get("date"),
        "captured_at": payload.get("captured_at"),
        "iv_atm": payload.get("iv_atm"),
        "iv_interpolated": payload.get("iv_interpolated"),
    }


def _sync_from_tracker(
    underlying: str,
    *,
    backfill_limit: int = 1,
    lookback_days: int = 2,
):
    from ..services.options_store import OptionsStore
    from ..services.vol_index import VolIndexService

    normalized = str(underlying or "IBOVE Index").strip() or "IBOVE Index"
    service = VolIndexService(normalized)
    state = _collect_state(normalized)
    sync_lock = state["lock"]
    if not sync_lock.acquire(blocking=False):
        return service.get_latest()

    try:
        latest_persisted = service.get_latest()
        last_source_dt = _parse_iso_datetime(
            (latest_persisted or {}).get("iv_captured_at")
            or (latest_persisted or {}).get("captured_at")
        )

        store = OptionsStore()
        if int(backfill_limit or 0) <= 1:
            latest_iv = store.read_latest_volume_iv_snapshot(
                underlying_security=normalized,
                lookback_days=max(1, int(lookback_days or 1)),
            )
            tracker_rows = [latest_iv] if latest_iv else []
        else:
            tracker_rows = store.read_volume_iv_history(
                underlying_security=normalized,
                limit=max(int(backfill_limit) * 4, 240),
                lookback_days=max(1, int(lookback_days or 1)),
            )
            tracker_rows.sort(key=lambda row: row.get("captured_at") or "")

        pending_rows = []
        for row in tracker_rows:
            row_dt = _parse_iso_datetime((row or {}).get("captured_at"))
            if row_dt is not None and (last_source_dt is None or row_dt > last_source_dt):
                pending_rows.append(row)

        limit = max(1, int(backfill_limit or 1))
        latest_record = latest_persisted
        for row in pending_rows[-limit:]:
            latest_record = (
                _record_from_iv_payload(
                    service,
                    row,
                    date_override=str((row or {}).get("session_date") or "")[:10] or None,
                    option_count_override=(row or {}).get("chain_size"),
                )
                or latest_record
            )

        if pending_rows and latest_record:
            state["last_completed_at"] = time.time()
            _invalidate_cache(normalized)
        return latest_record
    except Exception:
        logger.warning(
            "Failed to synchronize vol-index from volume tracker for %s",
            normalized,
            exc_info=True,
        )
        return service.get_latest()
    finally:
        sync_lock.release()


@options_bp.get("/vol-index/history")
def vol_index_history():
    """Return daily and intraday volatility-index history."""
    try:
        from ..services.vol_index import VolIndexService

        underlying = request.args.get("underlying") or "IBOVE Index"
        days = max(1, min(int(request.args.get("days", 252)), 1260))
        intraday_days = max(1, min(int(request.args.get("intraday_days", 5)), 20))
        compact = _is_truthy(request.args.get("compact"))
        cache_key = (underlying, days, intraday_days, compact)
        cached = _read_cache(_history_cache, cache_key)
        if cached is not None:
            return jsonify({"success": True, "data": cached, "cached": True})

        _sync_from_tracker(
            underlying,
            backfill_limit=360,
            lookback_days=min(max(intraday_days, 1), 5),
        )
        service = VolIndexService(underlying)
        intraday_history = service.get_intraday_history(intraday_days)
        if compact:
            compact_history = [_compact_intraday_record(item) for item in intraday_history]
            data = {
                "underlying": underlying,
                "days_requested": days,
                "intraday_days_requested": intraday_days,
                "count": len(compact_history),
                "history": [],
                "daily_history": [],
                "intraday_history": compact_history,
                "latest": compact_history[-1] if compact_history else None,
            }
        else:
            history = service.get_history(days)
            data = {
                "underlying": underlying,
                "days_requested": days,
                "intraday_days_requested": intraday_days,
                "count": len(history),
                "history": history,
                "daily_history": history,
                "intraday_history": intraday_history,
                "latest": intraday_history[-1]
                if intraday_history
                else (history[-1] if history else None),
            }

        _write_cache(_history_cache, cache_key, data, _HISTORY_CACHE_TTL_SECONDS)
        return jsonify({"success": True, "data": data})
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.get("/vol-index/latest")
def vol_index_latest():
    """Return the latest volatility-index snapshot."""
    try:
        from ..services.vol_index import VolIndexService

        underlying = request.args.get("underlying") or "IBOVE Index"
        cached = _read_cache(_latest_cache, underlying)
        if cached is not None:
            return jsonify({"success": True, "data": cached, "cached": True})
        latest_synced = _sync_from_tracker(underlying, backfill_limit=1, lookback_days=2)
        payload = latest_synced or VolIndexService(underlying).get_latest() or {}
        _write_cache(_latest_cache, underlying, payload, _LATEST_CACHE_TTL_SECONDS)
        return jsonify({"success": True, "data": payload})
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.post("/vol-index/collect")
def vol_index_collect():
    """Collect a volatility-index snapshot from tracker or model data."""
    try:
        from ..services.options_modeling import OptionsModelingService
        from ..services.options_modeling.input_preparation import prepare_option_inputs
        from ..services.options_modeling.market_context import build_market_context
        from ..services.options_query_service import OptionsQueryService
        from ..services.options_store import OptionsStore
        from ..services.vol_index import VolIndexService

        payload = request.get_json(silent=True) or {}
        underlying = payload.get("underlying") or "IBOVE Index"
        force = bool(payload.get("force", False))
        date_override = payload.get("date")
        service = VolIndexService(underlying)
        state = _collect_state(underlying)
        if not force:
            last_completed_at = float(state.get("last_completed_at") or 0.0)
            if last_completed_at and time.time() - last_completed_at < _COLLECT_COOLDOWN_SECONDS:
                return jsonify(
                    {
                        "success": True,
                        "data": service.get_latest() or {},
                        "skipped_collect": True,
                        "reason": "cooldown",
                    }
                )

        latest_iv = OptionsStore().read_latest_volume_iv_snapshot(
            underlying_security=underlying,
            lookback_days=5,
        )
        latest_dt = _parse_iso_datetime((latest_iv or {}).get("captured_at"))
        latest_age_seconds = (
            max(0.0, (datetime.now(timezone.utc) - latest_dt).total_seconds())
            if latest_dt is not None
            else None
        )
        tracker_stale_after = max(45, int(Config.OPTIONS_VOLUME_POLL_SECONDS) * 2)
        needs_tracker_refresh = (
            force
            or not latest_iv
            or (
                date_override
                and str((latest_iv or {}).get("session_date") or "")[:10] != date_override
            )
            or str((latest_iv or {}).get("underlying_security") or "") != underlying
            or (
                not date_override
                and latest_age_seconds is not None
                and latest_age_seconds > tracker_stale_after
            )
        )

        tracker_result = (
            get_container().options_volume_tracker().poll_once(underlying)
            if needs_tracker_refresh
            else {}
        )
        latest_iv = tracker_result.get("monthly_iv_snapshot") or latest_iv
        if latest_iv:
            record = _record_from_iv_payload(
                service,
                latest_iv,
                date_override=date_override,
                force=force,
                option_count_override=tracker_result.get("chain_size")
                or latest_iv.get("chain_size"),
            )
            if record is None:
                raise RuntimeError("Failed to generate vol-index snapshot from monthly tracker")
            state["last_completed_at"] = time.time()
            _invalidate_cache(underlying)
            return jsonify({"success": True, "data": record})

        query = OptionsQueryService()
        source = query.latest_snapshot(
            universe_tier="full",
            underlying_security=underlying,
            limit=5000,
        )
        rows = source.get("rows", []) if isinstance(source, dict) else []
        batch = source.get("batch") or {} if isinstance(source, dict) else {}
        if not rows:
            rows, batch = _merge_snapshot_tiers(query, underlying)
        if not rows:
            return jsonify(
                {"success": False, "error": f"No snapshot available for {underlying}"}
            ), 404

        modeling = OptionsModelingService()
        try:
            market_context = build_market_context(
                underlying_security=underlying,
                snapshot_rows=rows,
                snapshot_batch=batch,
                bloomberg_service=modeling.bloomberg,
            )
        except Exception:
            spot_values = [
                row.get("spot_price")
                or row.get("OPT_UNDL_PX")
                or row.get("LAST_PRICE")
                or row.get("PX_LAST")
                for row in rows
                if row.get("spot_price")
                or row.get("OPT_UNDL_PX")
                or row.get("LAST_PRICE")
                or row.get("PX_LAST")
            ]
            spot = float(spot_values[0]) if spot_values else 0.0
            market_context = {"spot_price": spot, "forward_price": spot}

        try:
            prepared, _ = prepare_option_inputs(
                snapshot_rows=rows,
                market_context=market_context,
                latest_oi_map={},
                run_config=modeling.build_run_config(),
                signal_payload_by_option={},
            )
        except Exception:
            prepared = rows

        record = service.record_snapshot(
            prepared_options=prepared,
            market_context=market_context,
            date=date_override,
            force=force,
        )
        state["last_completed_at"] = time.time()
        _invalidate_cache(underlying)
        return jsonify({"success": True, "data": record})
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


def _merge_snapshot_tiers(query, underlying: str) -> tuple[list, dict]:
    rows: list = []
    seen_ids: set = set()
    batch: dict = {}
    for tier in ("structural", "liquid", "critical"):
        try:
            result = query.latest_snapshot(
                universe_tier=tier,
                underlying_security=underlying,
                limit=5000,
            )
            tier_rows = result.get("rows", []) if isinstance(result, dict) else []
            if not batch and isinstance(result, dict):
                batch = result.get("batch") or {}
        except Exception:
            tier_rows = []
        for row in tier_rows:
            identifier = (
                row.get("bloomberg_ticker")
                or row.get("option_id")
                or f"{row.get('strike')}_{row.get('put_call') or row.get('OPT_PUT_CALL')}"
            )
            if identifier and identifier not in seen_ids:
                seen_ids.add(identifier)
                rows.append(row)
    return rows, batch


@options_bp.post("/vol-index/price")
def vol_index_append_price():
    """Append a closing price used by the volatility model."""
    try:
        from ..services.vol_index import VolIndexService

        payload = request.get_json(silent=True) or {}
        underlying = payload.get("underlying") or "IBOVE Index"
        date = payload.get("date")
        close = payload.get("close")
        if not date or close is None:
            return jsonify({"success": False, "error": "date and close are required"}), 400
        service = VolIndexService(underlying)
        service._store.append_price(date, float(close))
        return jsonify(
            {
                "success": True,
                "data": {
                    "underlying": underlying,
                    "date": date,
                    "close": close,
                    "n_price_obs": service._store.n_price_obs(),
                },
            }
        )
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)
