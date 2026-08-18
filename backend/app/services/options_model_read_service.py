from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from typing import Any

from .options_query_service import OptionsQueryService
from .options_store import OptionsStore


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_float(value: Any, default=None):
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _compact_curve_point(point: dict | None) -> dict:
    point = point or {}
    if not isinstance(point, dict):
        return {}
    return {
        "spot": point.get("spot"),
        "hp": point.get("hp"),
        "dex": point.get("dex"),
        "gex": point.get("gex"),
        "vex": point.get("vex"),
        "cex": point.get("cex"),
        "by_put_call": point.get("by_put_call") or {},
        "by_expiry": point.get("by_expiry") or {},
    }


def compact_model_run(payload: dict | None) -> dict:
    payload = payload or {}
    if not payload:
        return {}

    summary = payload.get("summary") or {}
    pressure = payload.get("pressure") or {}
    dealer_inference = payload.get("dealer_inference") or {}

    return {
        "run_id": payload.get("run_id"),
        "captured_at": payload.get("captured_at"),
        "session_date": payload.get("session_date"),
        "underlying_security": payload.get("underlying_security"),
        "source": payload.get("source") or {},
        "config": payload.get("config") or {},
        "market_context": payload.get("market_context") or {},
        "diagnostics": payload.get("diagnostics") or {},
        "summary": summary,
        "pressure": {
            "zero_pressure": pressure.get("zero_pressure"),
            "max_acceleration": pressure.get("max_acceleration"),
            "center_of_mass": pressure.get("center_of_mass"),
            "pinning_band": pressure.get("pinning_band"),
            "acceleration_band": pressure.get("acceleration_band"),
            "decompression_band": pressure.get("decompression_band"),
            "dominant_side": pressure.get("dominant_side"),
            "current_point": _compact_curve_point(pressure.get("current_point")),
            "curve": [
                _compact_curve_point(point)
                for point in (pressure.get("curve") or [])
            ],
        },
        "dealer_inference": {
            "enabled": dealer_inference.get("enabled"),
            "config": dealer_inference.get("config") or {},
            "comparison": dealer_inference.get("comparison") or summary.get("dealer_inference_comparison") or {},
            "rows": dealer_inference.get("rows") or [],
        },
        "range_projection": payload.get("range_projection") or {},
        "strike_profiles": payload.get("strike_profiles") or [],
        "gamma_flip_history": payload.get("gamma_flip_history") or {},
        "daily_insights": payload.get("daily_insights") or {},
        "vol_surface_points": [
            {
                "strike": opt.get("strike"),
                "expiry": opt.get("expiry_date"),
                "dte": opt.get("days_to_expiry_business"),
                "put_call": opt.get("put_call"),
                "iv": opt.get("selected_iv"),
                "m": opt.get("moneyness_spot"),
            }
            for opt in (payload.get("prepared_options") or [])
            if opt.get("selected_iv") and opt.get("strike")
        ],
        "gex_surface_points": [
            {
                "strike": (exp.get("option") or {}).get("strike"),
                "expiry": (exp.get("option") or {}).get("expiry_date"),
                "dte": (exp.get("option") or {}).get("days_to_expiry_business"),
                "put_call": (exp.get("option") or {}).get("put_call"),
                "m": (exp.get("option") or {}).get("moneyness_spot"),
                "gex": exp.get("gex"),
                "dex": exp.get("dex"),
                "oi": (exp.get("option") or {}).get("open_int"),
            }
            for exp in (payload.get("option_exposures") or [])
            if exp.get("option") and exp.get("option", {}).get("strike")
        ],
    }


class OptionsModelReadService:
    """Read-only, cached payload builder for Discovery options-model widgets."""

    def __init__(self, store: OptionsStore | None = None) -> None:
        self.store = store or OptionsStore()
        self.query = OptionsQueryService(store=self.store)
        self._cache_lock = threading.RLock()
        self._cache: dict[tuple[Any, ...], dict[str, Any]] = {}

    def _get_cached(self, key: tuple[Any, ...]) -> Any | None:
        now = time.time()
        with self._cache_lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if float(entry.get("expires_at", 0.0)) <= now:
                self._cache.pop(key, None)
                return None
            return entry.get("value")

    def _set_cached(self, key: tuple[Any, ...], value: Any, ttl_seconds: float) -> Any:
        with self._cache_lock:
            self._cache[key] = {
                "value": value,
                "expires_at": time.time() + max(float(ttl_seconds), 0.0),
            }
            while len(self._cache) > 64:
                self._cache.pop(next(iter(self._cache)), None)
        return value

    @staticmethod
    def _row_uid(row: dict[str, Any]) -> str:
        return str(
            row.get("bloomberg_ticker")
            or row.get("option_id")
            or f"{row.get('strike')}_{row.get('put_call') or row.get('OPT_PUT_CALL')}"
        )

    def latest_model_run(
        self,
        *,
        underlying_security: str = "IBOVE Index",
        universe_tier: str | None = None,
        compact: bool = True,
        ttl_seconds: float = 5.0,
    ) -> dict[str, Any]:
        underlying = str(underlying_security or "IBOVE Index").strip() or "IBOVE Index"
        tier = str(universe_tier or "").strip().lower() or None
        key = ("model_latest", underlying, tier, bool(compact))
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        result = self.query.latest_model_run(underlying, universe_tier=tier)
        if compact:
            result = compact_model_run(result)
        return self._set_cached(key, result, ttl_seconds)

    def _snapshot_rows_for_tier(
        self,
        *,
        underlying_security: str,
        tier: str,
        limit: int = 5000,
        ttl_seconds: float = 10.0,
    ) -> list[dict[str, Any]]:
        normalized_tier = str(tier or "critical").strip().lower() or "critical"
        normalized_limit = max(1, min(int(limit or 5000), 10000))
        key = ("snapshot_rows", underlying_security, normalized_tier, normalized_limit)
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        result = self.query.latest_snapshot(
            universe_tier=normalized_tier,
            underlying_security=underlying_security,
            limit=normalized_limit,
        )
        rows = result.get("rows", []) if isinstance(result, dict) else []
        return self._set_cached(key, rows, ttl_seconds)

    def _snapshot_rows(
        self,
        *,
        underlying_security: str,
        tier: str,
        limit: int = 5000,
        ttl_seconds: float = 10.0,
    ) -> list[dict[str, Any]]:
        normalized_tier = str(tier or "critical").strip().lower() or "critical"
        if normalized_tier == "all":
            key = ("snapshot_rows_all", underlying_security, int(limit or 5000))
            cached = self._get_cached(key)
            if cached is not None:
                return cached
            merged: list[dict[str, Any]] = []
            seen: set[str] = set()
            for tier_name in ("structural", "liquid", "critical"):
                rows = self._snapshot_rows_for_tier(
                    underlying_security=underlying_security,
                    tier=tier_name,
                    limit=limit,
                    ttl_seconds=ttl_seconds,
                )
                for row in rows:
                    uid = self._row_uid(row)
                    if uid and uid not in seen:
                        seen.add(uid)
                        merged.append(row)
            return self._set_cached(key, merged, ttl_seconds)

        return self._snapshot_rows_for_tier(
            underlying_security=underlying_security,
            tier=normalized_tier,
            limit=limit,
            ttl_seconds=ttl_seconds,
        )

    def snapshot_by_strike(
        self,
        *,
        underlying_security: str = "IBOVE Index",
        tier: str = "critical",
        ttl_seconds: float = 10.0,
    ) -> dict[str, Any]:
        underlying = str(underlying_security or "IBOVE Index").strip() or "IBOVE Index"
        normalized_tier = str(tier or "critical").strip().lower() or "critical"
        key = ("snapshot_by_strike", underlying, normalized_tier)
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        rows = self._snapshot_rows(
            underlying_security=underlying,
            tier=normalized_tier,
            limit=5000 if normalized_tier == "all" else 2000,
            ttl_seconds=ttl_seconds,
        )
        if not rows:
            return self._set_cached(key, {"by_strike": [], "options": []}, ttl_seconds)

        options_list = []
        for row in rows:
            put_call = str(row.get("put_call") or row.get("OPT_PUT_CALL") or "").capitalize()
            options_list.append({
                "symbol": row.get("bloomberg_ticker") or row.get("option_id"),
                "put_call": put_call,
                "strike": row.get("strike") or row.get("OPT_STRIKE_PX"),
                "expiry_date": row.get("expiry_date") or row.get("OPT_EXPIRE_DT"),
                "days_to_expiry": row.get("days_to_expiry_business") or row.get("days_to_expiry_calendar"),
                "iv": row.get("MODEL_IV") or row.get("EFF_IV") or row.get("IVOL_MID"),
                "iv_bid": row.get("IVOL_BID"),
                "iv_ask": row.get("IVOL_ASK"),
                "open_int": row.get("OPEN_INT") or row.get("OPT_OPEN_INTEREST"),
                "bid": row.get("BID"),
                "ask": row.get("ASK"),
                "mid": row.get("MID") or row.get("bid_ask_mid"),
                "last": row.get("PX_LAST"),
                "delta": row.get("MODEL_DELTA") or row.get("OPT_DELTA"),
                "gamma": row.get("MODEL_GAMMA_POINT") or row.get("OPT_GAMMA"),
                "vega": row.get("MODEL_VEGA_1PCTVOL") or row.get("OPT_VEGA"),
                "theta": row.get("MODEL_THETA_BD252") or row.get("OPT_THETA"),
                "vanna": row.get("MODEL_VANNA"),
                "charm": row.get("MODEL_CHARM_BD252"),
                "moneyness": row.get("moneyness_spot"),
                "market_ok": row.get("market_ok"),
                "spot_price": row.get("OPT_UNDL_PX"),
            })

        strike_map: dict[float, dict[str, Any]] = {}
        for option in options_list:
            strike = _safe_float(option.get("strike"))
            if strike is None or strike <= 0:
                continue
            if strike not in strike_map:
                strike_map[strike] = {"strike": strike, "calls": [], "puts": []}
            if option["put_call"] == "Call":
                strike_map[strike]["calls"].append(option)
            else:
                strike_map[strike]["puts"].append(option)

        by_strike = []
        for strike, value in sorted(strike_map.items()):
            calls = value["calls"]
            puts = value["puts"]
            best_call = max(calls, key=lambda item: item.get("market_ok") or 0) if calls else {}
            best_put = max(puts, key=lambda item: item.get("market_ok") or 0) if puts else {}
            by_strike.append({
                "strike": strike,
                "iv_call": best_call.get("iv"),
                "iv_put": best_put.get("iv"),
                "gamma_call": best_call.get("gamma"),
                "gamma_put": best_put.get("gamma"),
                "delta_call": best_call.get("delta"),
                "delta_put": best_put.get("delta"),
                "vega_call": best_call.get("vega"),
                "vega_put": best_put.get("vega"),
                "open_int_call": best_call.get("open_int"),
                "open_int_put": best_put.get("open_int"),
            })

        return self._set_cached(
            key,
            {"by_strike": by_strike, "options": options_list},
            ttl_seconds,
        )

    def b3_oi_latest(
        self,
        *,
        date: str | None = None,
        raw: bool = False,
        ttl_seconds: float = 60.0,
    ) -> Any:
        requested_date = str(date or "").strip() or None
        key = ("b3_oi_latest", requested_date, bool(raw))
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        if requested_date:
            trade_date = requested_date
        else:
            dates = self.store.list_b3_oi_dates()
            if not dates:
                return self._set_cached(key, {"date": None, "by_strike": [], "total_rows": 0}, ttl_seconds)
            trade_date = sorted(dates)[-1]

        rows = self.store.load_b3_oi_rows(trade_date)
        if raw:
            return self._set_cached(key, {"rows": rows, "date": trade_date, "count": len(rows)}, ttl_seconds)

        strike_map: dict[float, dict[str, Any]] = {}
        for row in rows:
            strike = _safe_float(row.get("strike"))
            if strike is None or strike <= 0:
                continue
            if strike not in strike_map:
                strike_map[strike] = {
                    "strike": strike,
                    "call_oi": 0,
                    "put_oi": 0,
                    "total_oi": 0,
                    "call_coberto": 0,
                    "call_trava": 0,
                    "call_descoberto": 0,
                    "put_coberto": 0,
                    "put_trava": 0,
                    "put_descoberto": 0,
                    "call_n_titular": 0,
                    "call_n_lancador": 0,
                    "put_n_titular": 0,
                    "put_n_lancador": 0,
                }
            entry = strike_map[strike]
            row_type = str(row.get("type") or "").upper()
            oi = int(row.get("oi_total") or 0)
            if row_type == "CALL":
                entry["call_oi"] += oi
                entry["call_coberto"] += int(row.get("oi_coberto") or 0)
                entry["call_trava"] += int(row.get("oi_trava") or 0)
                entry["call_descoberto"] += int(row.get("oi_descoberto") or 0)
                entry["call_n_titular"] += int(row.get("n_titular") or 0)
                entry["call_n_lancador"] += int(row.get("n_lancador") or 0)
            elif row_type == "PUT":
                entry["put_oi"] += oi
                entry["put_coberto"] += int(row.get("oi_coberto") or 0)
                entry["put_trava"] += int(row.get("oi_trava") or 0)
                entry["put_descoberto"] += int(row.get("oi_descoberto") or 0)
                entry["put_n_titular"] += int(row.get("n_titular") or 0)
                entry["put_n_lancador"] += int(row.get("n_lancador") or 0)
            entry["total_oi"] = entry["call_oi"] + entry["put_oi"]

        return self._set_cached(
            key,
            {
                "date": trade_date,
                "total_rows": len(rows),
                "by_strike": sorted(strike_map.values(), key=lambda item: item["strike"]),
            },
            ttl_seconds,
        )

    def b3_oi_dates(self) -> list[str]:
        key = ("b3_oi_dates",)
        cached = self._get_cached(key)
        if cached is not None:
            return cached
        return self._set_cached(key, sorted(self.store.list_b3_oi_dates()), 60.0)

    @staticmethod
    def _spot_price_from_rows(rows: list[dict[str, Any]]) -> float | None:
        for row in rows:
            value = row.get("OPT_UNDL_PX") or row.get("underlying_px") or row.get("spot_price")
            spot = _safe_float(value)
            if spot is not None:
                return spot
        return None

    def vol_surface(
        self,
        *,
        underlying_security: str = "IBOVE Index",
        tier: str = "all",
        min_dte: int = 1,
        max_dte: int = 120,
        ttl_seconds: float = 10.0,
    ) -> dict[str, Any]:
        underlying = str(underlying_security or "IBOVE Index").strip() or "IBOVE Index"
        normalized_tier = str(tier or "all").strip().lower() or "all"
        min_dte_value = int(min_dte or 1)
        max_dte_value = int(max_dte or 120)
        key = ("vol_surface", underlying, normalized_tier, min_dte_value, max_dte_value)
        cached = self._get_cached(key)
        if cached is not None:
            return cached

        rows = self._snapshot_rows(
            underlying_security=underlying,
            tier=normalized_tier,
            limit=5000,
            ttl_seconds=ttl_seconds,
        )
        if not rows:
            return self._set_cached(
                key,
                {"slices": [], "spot": None, "forward": None},
                ttl_seconds,
            )

        spot_price = self._spot_price_from_rows(rows)
        if not spot_price:
            latest_run = self.latest_model_run(
                underlying_security=underlying,
                compact=False,
                ttl_seconds=ttl_seconds,
            )
            spot_price = _safe_float((latest_run.get("market_context") or {}).get("spot_price"))

        points = []
        for row in rows:
            dte = row.get("days_to_expiry_business") or row.get("days_to_expiry_calendar") or 0
            try:
                dte = int(dte)
            except Exception:
                continue
            if dte < min_dte_value or dte > max_dte_value:
                continue

            strike = _safe_float(row.get("strike") or row.get("OPT_STRIKE_PX"))
            if strike is None or strike <= 0:
                continue

            iv = _safe_float(row.get("MODEL_IV") or row.get("EFF_IV") or row.get("IVOL_MID"))
            if iv is None or iv < 0.005 or iv > 5.0:
                continue

            put_call = str(row.get("put_call") or row.get("OPT_PUT_CALL") or "").strip().capitalize()
            expiry = row.get("expiry_date") or row.get("OPT_EXPIRE_DT") or ""
            moneyness = (strike / spot_price - 1.0) if spot_price else None
            points.append({
                "ticker": row.get("bloomberg_ticker") or row.get("option_id"),
                "strike": strike,
                "expiry": expiry,
                "dte": dte,
                "put_call": put_call,
                "iv": round(iv, 6),
                "iv_observed": round(iv, 6),
                "moneyness": round(moneyness, 6) if moneyness is not None else None,
                "log_m": round(float(math.log(strike / spot_price)), 6) if spot_price and strike > 0 else None,
                "delta": _safe_float(row.get("MODEL_DELTA") or row.get("EFF_DELTA") or row.get("OPT_DELTA")),
                "bid": _safe_float(row.get("BID")),
                "ask": _safe_float(row.get("ASK")),
                "volume": _safe_float(row.get("VOLUME") or row.get("OPT_VOLUME") or row.get("volume") or row.get("volume_delta")),
                "open_int": _safe_float(row.get("OPEN_INT") or row.get("OPT_OPEN_INTEREST") or row.get("open_int")),
                "market_ok": bool(row.get("market_ok")),
                "spread_pct": _safe_float(row.get("spread_pct")),
            })

        by_expiry: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for point in points:
            by_expiry[point["expiry"]].append(point)

        slices = []
        for expiry, expiry_points in sorted(
            by_expiry.items(),
            key=lambda item: (next(iter(item[1]), {}).get("dte") or 999),
        ):
            dtes = [point["dte"] for point in expiry_points]
            dte_value = round(sum(dtes) / len(dtes)) if dtes else 0
            calls = sorted([point for point in expiry_points if point["put_call"] == "Call"], key=lambda item: item["strike"])
            puts = sorted([point for point in expiry_points if point["put_call"] == "Put"], key=lambda item: item["strike"])
            all_sorted = sorted(expiry_points, key=lambda item: item["strike"])
            slices.append({
                "expiry": expiry,
                "dte": dte_value,
                "point_count": len(expiry_points),
                "calls": calls,
                "puts": puts,
                "all": all_sorted,
            })

        return self._set_cached(
            key,
            {
                "spot": spot_price,
                "forward": spot_price,
                "slices": slices,
                "total_points": len(points),
            },
            ttl_seconds,
        )
