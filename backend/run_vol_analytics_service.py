"""
Dedicated volatility analytics API for Discovery widgets.

This process serves read-heavy Volatility Index and Vol of Vol endpoints without
blocking the main Flask backend. Expensive synchronization from the volume IV
tracker runs in the background; requests return the persisted history first.
"""

from __future__ import annotations

import math
import os
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, request
from flask_cors import CORS

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.auth import register_auth
from app.config import Config
from app.http import error_response, register_error_handlers
from app.server import serve
from app.services.live_capture_workbook_series_service import LiveCaptureWorkbookSeriesService
from app.services.options_store import OptionsStore
from app.services.vol_index import VolIndexService
from app.utils.logger import get_logger

logger = get_logger("aquiles.vol_analytics_service")

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)


_VOL_INDEX_HISTORY_CACHE_TTL_SEC = 10.0
_VOL_INDEX_LATEST_CACHE_TTL_SEC = 3.0
_vol_index_history_cache: dict[tuple, dict] = {}
_vol_index_latest_cache: dict[str, dict] = {}
_cache_lock = threading.Lock()
_sync_states: dict[str, dict[str, Any]] = {}
_sync_state_lock = threading.Lock()
live_capture_workbook_service = LiveCaptureWorkbookSeriesService()


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_float(value, default=None):
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _parse_iso_datetime(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _compact_vol_intraday_record(record):
    payload = dict(record or {})
    return {
        "date": payload.get("date"),
        "captured_at": payload.get("captured_at"),
        "iv_atm": payload.get("iv_atm"),
        "iv_interpolated": payload.get("iv_interpolated"),
    }


def _read_ttl_cache(cache: dict, key):
    now = time.time()
    with _cache_lock:
        entry = cache.get(key)
        if not entry:
            return None
        if float(entry.get("expires_at", 0.0)) <= now:
            cache.pop(key, None)
            return None
        return entry.get("value")


def _write_ttl_cache(cache: dict, key, value, ttl_seconds: float):
    with _cache_lock:
        cache[key] = {
            "value": value,
            "expires_at": time.time() + max(float(ttl_seconds), 0.0),
        }


def _invalidate_vol_index_cache(underlying: str | None = None):
    normalized = str(underlying or "").strip()
    with _cache_lock:
        if normalized:
            for key in list(_vol_index_history_cache.keys()):
                if key and key[0] == normalized:
                    _vol_index_history_cache.pop(key, None)
            _vol_index_latest_cache.pop(normalized, None)
            return
        _vol_index_history_cache.clear()
        _vol_index_latest_cache.clear()


def _sync_state(underlying: str) -> dict[str, Any]:
    normalized = str(underlying or "IBOVE Index").strip() or "IBOVE Index"
    with _sync_state_lock:
        state = _sync_states.get(normalized)
        if state is None:
            state = {
                "lock": threading.Lock(),
                "running": False,
                "last_started_at": None,
                "last_completed_at": None,
                "last_error": None,
            }
            _sync_states[normalized] = state
        return state


def _sync_status(underlying: str) -> dict[str, Any]:
    state = _sync_state(underlying)
    return {
        "running": bool(state.get("running")),
        "last_started_at": state.get("last_started_at"),
        "last_completed_at": state.get("last_completed_at"),
        "last_error": state.get("last_error"),
    }


def _record_vol_index_from_iv_payload(
    svc: VolIndexService,
    iv_payload: dict | None,
    *,
    date_override: str | None = None,
    option_count_override=None,
):
    payload = dict(iv_payload or {})
    if not payload:
        return None
    spot_value = _safe_float(
        payload.get("spot_price") or payload.get("reference_price"),
        0.0,
    ) or 0.0
    market_context = {
        "spot_price": float(spot_value),
        "forward_price": float(spot_value),
    }
    return svc.record_snapshot(
        prepared_options=[],
        market_context=market_context,
        date=date_override,
        iv_payload=payload,
        option_count_override=option_count_override or payload.get("chain_size"),
        captured_at_override=payload.get("captured_at"),
    )


def _sync_vol_index_from_store(
    underlying: str,
    *,
    backfill_limit: int = 1,
    lookback_days: int = 2,
) -> dict | None:
    normalized = str(underlying or "IBOVE Index").strip() or "IBOVE Index"
    svc = VolIndexService(normalized)
    state = _sync_state(normalized)
    sync_lock = state["lock"]
    if not sync_lock.acquire(blocking=False):
        return svc.get_latest()

    state["running"] = True
    state["last_started_at"] = datetime.now(timezone.utc).isoformat()
    state["last_error"] = None
    try:
        store = OptionsStore()
        latest_persisted = svc.get_latest()
        last_source_dt = _parse_iso_datetime(
            (latest_persisted or {}).get("iv_captured_at")
            or (latest_persisted or {}).get("captured_at")
        )

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
            if row_dt is None:
                continue
            if last_source_dt is None or row_dt > last_source_dt:
                pending_rows.append(row)

        if not pending_rows:
            return latest_persisted

        limit = max(1, int(backfill_limit or 1))
        pending_rows = pending_rows[-limit:]

        latest_record = latest_persisted
        for row in pending_rows:
            latest_record = _record_vol_index_from_iv_payload(
                svc,
                row,
                date_override=str((row or {}).get("session_date") or "")[:10] or None,
                option_count_override=(row or {}).get("chain_size"),
            ) or latest_record

        _invalidate_vol_index_cache(normalized)
        return latest_record
    except Exception as exc:
        state["last_error"] = str(exc)
        logger.warning("Failed to sync vol-index from IV history for %s", normalized, exc_info=True)
        return svc.get_latest()
    finally:
        state["running"] = False
        state["last_completed_at"] = datetime.now(timezone.utc).isoformat()
        sync_lock.release()


def _sync_vol_index_async(underlying: str, *, backfill_limit: int, lookback_days: int) -> bool:
    normalized = str(underlying or "IBOVE Index").strip() or "IBOVE Index"
    state = _sync_state(normalized)
    if state["lock"].locked():
        return False

    thread = threading.Thread(
        target=_sync_vol_index_from_store,
        kwargs={
            "underlying": normalized,
            "backfill_limit": backfill_limit,
            "lookback_days": lookback_days,
        },
        daemon=True,
        name=f"vol-index-sync-{normalized}",
    )
    thread.start()
    return True


def _json_error(exc: Exception, status_code: int = 500):
    return error_response(logger, status_code=status_code, exception=exc)


def _workbook_securities_from_request() -> list[str]:
    values = request.args.getlist("security")
    raw_securities = request.args.get("securities")
    if raw_securities:
        values.extend([item.strip() for item in raw_securities.split(",") if item.strip()])
    return list(dict.fromkeys(str(item or "").strip() for item in values if str(item or "").strip()))


@app.route("/health", methods=["GET"])
def health():
    underlying = request.args.get("underlying") or "IBOVE Index"
    latest = VolIndexService(underlying).get_latest() or {}
    return {
        "status": "ok",
        "service": "aquiles-vol-analytics-service",
        "underlying": underlying,
        "latest_captured_at": latest.get("captured_at"),
        "sync": _sync_status(underlying),
    }


@app.route("/api/options/volume/iv-history", methods=["GET"])
def volume_iv_history():
    try:
        store = OptionsStore()
        session_date = request.args.get("session_date") or None
        underlying = request.args.get("underlying_security") or None
        limit = min(int(request.args.get("limit", 500)), 5000)
        lookback = int(request.args.get("lookback_days", Config.OPTIONS_VOLUME_ACTIVITY_LOOKBACK_DAYS))

        rows = store.read_volume_iv_history(
            session_date=session_date,
            underlying_security=underlying,
            limit=limit,
            lookback_days=lookback,
        )
        latest = rows[0] if rows else None
        return jsonify({
            "success": True,
            "data": {"history": rows, "latest": latest},
            "count": len(rows),
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/live-capture/workbook-series", methods=["GET"])
def live_capture_workbook_series():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        securities = _workbook_securities_from_request()
        if not securities:
            securities = ["VXBR Index"]
        session_date = (request.args.get("session_date") or "").strip() or None
        session_count = max(1, min(int(request.args.get("session_count", 2)), 10))
        include_recent_state = _is_truthy(request.args.get("include_recent_state"))

        multi = live_capture_workbook_service.read_series_multi(
            underlying_security=underlying,
            securities=securities,
            session_date=session_date,
            session_count=session_count,
            include_recent_state=include_recent_state,
        )
        first_security = securities[0]
        first_series = multi["series_by_security"].get(first_security) or []
        return jsonify({
            "success": True,
            "data": {
                "underlying_security": multi["underlying_security"],
                "security": first_security,
                "securities": multi["securities"],
                "session_dates": multi["session_dates"],
                "series": first_series,
                "latest": first_series[-1] if first_series else None,
                "series_by_security": multi["series_by_security"],
                "latest_by_security": multi["latest_by_security"],
                "sync": multi["sync"],
            },
            "count": len(first_series),
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/live-capture/workbook-latest", methods=["GET"])
def live_capture_workbook_latest():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        securities = _workbook_securities_from_request()
        if not securities:
            securities = ["VXBR Index"]
        session_date = (request.args.get("session_date") or "").strip() or None
        include_recent_state = not _is_truthy(request.args.get("exclude_recent_state"))
        result = live_capture_workbook_service.read_latest_multi(
            underlying_security=underlying,
            securities=securities,
            session_date=session_date,
            include_recent_state=include_recent_state,
        )
        first_security = securities[0]
        return jsonify({
            "success": True,
            "data": {
                "underlying_security": result["underlying_security"],
                "security": first_security,
                "securities": result["securities"],
                "latest": result["latest_by_security"].get(first_security),
                "latest_by_security": result["latest_by_security"],
                "session_dates": result.get("session_dates") or [],
                "sync": result.get("sync") or [],
            },
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/vol-index/history", methods=["GET"])
def vol_index_history():
    try:
        underlying = request.args.get("underlying") or "IBOVE Index"
        days = max(1, min(int(request.args.get("days", 252)), 1260))
        intraday_days = max(1, min(int(request.args.get("intraday_days", 5)), 20))
        compact = _is_truthy(request.args.get("compact"))
        force_refresh = _is_truthy(request.args.get("refresh"))
        cache_key = (underlying, days, intraday_days, compact)

        if not force_refresh:
            cached = _read_ttl_cache(_vol_index_history_cache, cache_key)
            if cached is not None:
                return jsonify({"success": True, "data": cached, "cached": True})

        svc = VolIndexService(underlying)
        intraday_history = svc.get_intraday_history(intraday_days)
        if compact:
            compact_intraday_history = [_compact_vol_intraday_record(item) for item in intraday_history]
            latest = compact_intraday_history[-1] if compact_intraday_history else None
            data = {
                "underlying": underlying,
                "days_requested": days,
                "intraday_days_requested": intraday_days,
                "count": len(compact_intraday_history),
                "history": [],
                "daily_history": [],
                "intraday_history": compact_intraday_history,
                "latest": latest,
                "sync": _sync_status(underlying),
            }
        else:
            history = svc.get_history(days)
            latest = intraday_history[-1] if intraday_history else (history[-1] if history else None)
            data = {
                "underlying": underlying,
                "days_requested": days,
                "intraday_days_requested": intraday_days,
                "count": len(history),
                "history": history,
                "daily_history": history,
                "intraday_history": intraday_history,
                "latest": latest,
                "sync": _sync_status(underlying),
            }

        _write_ttl_cache(_vol_index_history_cache, cache_key, data, _VOL_INDEX_HISTORY_CACHE_TTL_SEC)

        if not _is_truthy(request.args.get("no_sync")):
            started = _sync_vol_index_async(
                underlying,
                backfill_limit=360,
                lookback_days=min(max(intraday_days, 1), 5),
            )
            data["sync"] = {
                **_sync_status(underlying),
                "started": started,
            }

        return jsonify({"success": True, "data": data})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/vol-index/latest", methods=["GET"])
def vol_index_latest():
    try:
        underlying = request.args.get("underlying") or "IBOVE Index"
        force_refresh = _is_truthy(request.args.get("refresh"))
        if not force_refresh:
            cached = _read_ttl_cache(_vol_index_latest_cache, underlying)
            if cached is not None:
                return jsonify({"success": True, "data": cached, "cached": True})

        svc = VolIndexService(underlying)
        payload = svc.get_latest() or {}
        if not _is_truthy(request.args.get("no_sync")):
            _sync_vol_index_async(underlying, backfill_limit=1, lookback_days=2)
        payload = {
            **payload,
            "sync": _sync_status(underlying),
        }
        _write_ttl_cache(_vol_index_latest_cache, underlying, payload, _VOL_INDEX_LATEST_CACHE_TTL_SEC)
        return jsonify({"success": True, "data": payload})
    except Exception as exc:
        return _json_error(exc)


def main() -> None:
    host = os.environ.get("VOL_ANALYTICS_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("VOL_ANALYTICS_SERVICE_PORT", "5013"))
    logger.info("Starting aquiles-vol-analytics-service on %s:%s", host, port)
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
