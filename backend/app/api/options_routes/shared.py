import logging
import math

import requests as http_requests
from flask import jsonify

from ...config import Config
from ...http import error_response

logger = logging.getLogger(__name__)


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _options_collector_service_request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_payload: dict | None = None,
    timeout: float = 10.0,
):
    url = f"{Config.OPTIONS_COLLECTOR_SERVICE_URL}{path}"
    try:
        response = http_requests.request(
            method,
            url,
            params=params,
            json=json_payload,
            timeout=timeout,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {
                "success": response.ok,
                "data": response.text,
            }
        if isinstance(payload, dict):
            payload["delegated"] = True
            if isinstance(payload.get("data"), dict):
                payload["data"]["delegated"] = True
        return jsonify(payload), response.status_code
    except Exception as exc:
        return error_response(logger, status_code=503, exception=exc, extra={"delegated": True})


def _options_collector_status_payload() -> dict:
    try:
        response = http_requests.get(
            f"{Config.OPTIONS_COLLECTOR_SERVICE_URL}/api/options/collector/status",
            timeout=2.0,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict):
            data["delegated"] = True
            data["service_available"] = True
            return data
    except Exception as exc:
        logger.exception("options collector service status failed", exc_info=exc)
        return {
            "running": False,
            "supervisor_running": False,
            "delegated": True,
            "service_available": False,
            "last_error": "Service unavailable",
            "stopped_reason": "options_collector_service_unavailable",
        }
    return {
        "running": False,
        "supervisor_running": False,
        "delegated": True,
        "service_available": False,
        "last_error": "Service unavailable",
    }


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


def _compact_model_run(payload: dict | None) -> dict:
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
            "curve": [_compact_curve_point(point) for point in (pressure.get("curve") or [])],
        },
        "dealer_inference": {
            "enabled": dealer_inference.get("enabled"),
            "config": dealer_inference.get("config") or {},
            "comparison": dealer_inference.get("comparison")
            or summary.get("dealer_inference_comparison")
            or {},
            "rows": dealer_inference.get("rows") or [],
        },
        "range_projection": payload.get("range_projection") or {},
        "strike_profiles": payload.get("strike_profiles") or [],
        "gamma_flip_history": payload.get("gamma_flip_history") or {},
        "daily_insights": payload.get("daily_insights") or {},
        # Slim IV points for vol-surface widget (expiry × strike × iv)
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
        # Slim GEX/DEX points for exposure surface widget (expiry × strike × gex/dex)
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


def _safe_float(value, default=None):
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _workbook_dynamic_for_security(workbook_values, security: str):
    values = workbook_values or {}
    target = str(security or "").strip()
    if not target:
        return None
    direct = values.get(target)
    if isinstance(direct, dict):
        return direct
    lowered = target.lower()
    for key, dynamic in values.items():
        if str(key or "").strip().lower() == lowered and isinstance(dynamic, dict):
            return dynamic
    return None


def _normalize_cached_factor_rows(rows):
    normalized = []
    for row in rows or []:
        item = dict(row or {})
        original_source = str(item.get("live_source") or "").strip()
        item["is_live"] = False
        item["live_source"] = "persisted_cache"
        if original_source:
            item["cache_source"] = original_source
        normalized.append(item)
    return normalized
