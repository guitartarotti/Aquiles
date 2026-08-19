"""
Options module API routes.
"""

import logging
import math
import os
import threading
import time as _time

import requests as http_requests
from flask import jsonify, request

from ..auth import require_role
from ..config import Config
from ..http import error_response
from ..models.task import TaskManager, TaskStatus
from ..services.options_bloomberg_service import OptionsBloombergService
from ..services.options_collector_manager import OptionsCollectorManager
from ..services.options_context_chat_service import OptionsContextChatService
from ..services.options_global_modeling import OptionsGlobalTriangulationService
from ..services.options_history_service import OptionsHistoryService
from ..services.options_modeling import OptionsModelingService
from ..services.options_query_service import OptionsQueryService
from ..services.options_snapshot_service import OptionsSnapshotService
from . import options_bp
from .legacy_heatmap_proxy import legacy_heatmap_proxy_or_disabled

logger = logging.getLogger(__name__)


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _options_collector_delegated() -> bool:
    return _is_truthy(os.environ.get("AQUILES_DISABLE_OPTIONS_COLLECTOR"))


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
        return error_response(logger, status_code=503, exception=exc, extra={'delegated': True})


def _options_collector_status_payload() -> dict:
    if not _options_collector_delegated():
        return OptionsCollectorManager.get_instance().status()
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
        # Slim IV points for vol-surface widget (expiry × strike × iv)
        "vol_surface_points": [
            {
                "strike":   opt.get("strike"),
                "expiry":   opt.get("expiry_date"),
                "dte":      opt.get("days_to_expiry_business"),
                "put_call": opt.get("put_call"),
                "iv":       opt.get("selected_iv"),
                "m":        opt.get("moneyness_spot"),
            }
            for opt in (payload.get("prepared_options") or [])
            if opt.get("selected_iv") and opt.get("strike")
        ],
        # Slim GEX/DEX points for exposure surface widget (expiry × strike × gex/dex)
        "gex_surface_points": [
            {
                "strike":   (exp.get("option") or {}).get("strike"),
                "expiry":   (exp.get("option") or {}).get("expiry_date"),
                "dte":      (exp.get("option") or {}).get("days_to_expiry_business"),
                "put_call": (exp.get("option") or {}).get("put_call"),
                "m":        (exp.get("option") or {}).get("moneyness_spot"),
                "gex":      exp.get("gex"),
                "dex":      exp.get("dex"),
                "oi":       (exp.get("option") or {}).get("open_int"),
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


@options_bp.route('/status', methods=['GET'])
def get_options_status():
    try:
        query = OptionsQueryService()
        bloomberg = OptionsBloombergService()
        data = query.status()
        data["bloomberg"] = bloomberg.status()
        data["collector"] = _options_collector_status_payload()
        return jsonify({"success": True, "data": data})
    except ValueError:
        return error_response(
            logger,
            status_code=422,
            message="Options status is unavailable",
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/bloomberg/diagnose', methods=['GET'])
def diagnose_bloomberg_options():
    """
    Diagnóstico de conectividade Bloomberg para opções.
    Testa: status da sessão → chain do underlying → snapshot de 3 contratos.
    Retorna o que veio de cada etapa para identificar onde a cadeia quebra.
    """
    try:
        underlying = request.args.get('underlying_security') or 'IBOVE Index'
        bloomberg = OptionsBloombergService()

        result: dict = {
            "underlying_security": underlying,
            "steps": {},
        }

        # Passo 1 — status da conexão
        status = bloomberg.status()
        result["steps"]["connection"] = {
            "enabled": status.get("enabled"),
            "blpapi_available": status.get("blpapi_available"),
            "tcp_available": status.get("tcp_available"),
            "host": status.get("host"),
            "port": status.get("port"),
            "ok": bool(status.get("enabled") and status.get("blpapi_available") and status.get("tcp_available")),
        }

        if not result["steps"]["connection"]["ok"]:
            result["diagnosis"] = "Bloomberg não está disponível — verifique se o BBComm está rodando e o blpapi instalado."
            return jsonify({"success": True, "data": result})

        # Passo 2 — busca chain de opções
        chain_result = bloomberg.fetch_option_chain(underlying)
        chain = chain_result.get("chain") or []
        result["steps"]["option_chain"] = {
            "ok": len(chain) > 0,
            "contract_count": len(chain),
            "sample": chain[:5],
            "security_error": chain_result.get("security_error"),
            "field_exceptions": chain_result.get("field_exceptions") or [],
            "status": chain_result.get("status") or {},
        }

        if not chain:
            result["diagnosis"] = "Bloomberg conectado mas cadeia de opções vazia — verifique se o ticker do underlying está correto ou se há opções disponíveis."
            return jsonify({"success": True, "data": result})

        # Passo 3 — snapshot dos primeiros 3 contratos
        sample_tickers = chain[:3]
        snapshot_result = bloomberg.fetch_option_snapshots(
            sample_tickers,
            bloomberg.DISCOVERY_FIELDS,
        )
        snapshot_rows = snapshot_result.get("rows") or []
        rows_ok = [row for row in snapshot_rows if row.get("ok")]
        rows_fail = [row for row in snapshot_rows if not row.get("ok")]

        result["steps"]["snapshot_sample"] = {
            "ok": len(rows_ok) > 0,
            "requested": len(sample_tickers),
            "returned": len(snapshot_rows),
            "success_count": len(rows_ok),
            "fail_count": len(rows_fail),
            "status": snapshot_result.get("status") or {},
            "rows": [
                {
                    "security": row.get("security"),
                    "ok": row.get("ok"),
                    "fields": {
                        k: v for k, v in (row.get("fields") or {}).items()
                        if v not in (None, "")
                    },
                    "security_error": row.get("security_error"),
                    "field_exceptions": [
                        fe.get("field_id") for fe in (row.get("field_exceptions") or [])
                    ],
                }
                for row in snapshot_rows
            ],
        }

        if rows_ok:
            has_strike = any(
                row.get("fields", {}).get("OPT_STRIKE_PX") is not None
                for row in rows_ok
            )
            has_undl = any(
                row.get("fields", {}).get("OPT_UNDL_PX") is not None
                for row in rows_ok
            )
            has_iv = any(
                row.get("fields", {}).get("IVOL_MID") is not None
                for row in rows_ok
            )
            result["diagnosis"] = (
                f"Bloomberg OK — {len(rows_ok)}/{len(snapshot_rows)} contratos retornados. "
                f"Strike: {'✓' if has_strike else '✗'}  "
                f"UnderlyingPx: {'✓' if has_undl else '✗'}  "
                f"IV: {'✓' if has_iv else '✗'}"
            )
            result["fields_present"] = {
                "OPT_STRIKE_PX": has_strike,
                "OPT_UNDL_PX": has_undl,
                "IVOL_MID": has_iv,
            }
        else:
            result["diagnosis"] = "Bloomberg retornou contratos mas todos falharam — verifique permissões de dados ou tickers."

        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/discover', methods=['POST'])
def discover_options_contracts():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = payload.get('underlying_security') or request.args.get('underlying_security') or 'IBOVE Index'
        service = OptionsSnapshotService()
        result = service.discover_underlying(underlying)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/contracts', methods=['GET'])
def list_options_contracts():
    try:
        underlying = request.args.get('underlying_security')
        only_active = str(request.args.get('only_active', 'false')).lower() == 'true'
        limit = request.args.get('limit')
        service = OptionsQueryService()
        result = service.contracts(
            underlying_security=underlying,
            only_active=only_active,
            limit=int(limit) if limit else None,
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/universe', methods=['GET'])
def get_options_universe():
    try:
        underlying = request.args.get('underlying_security')
        query = OptionsQueryService()
        result = query.universe(underlying_security=underlying)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/snapshot/latest', methods=['GET'])
def get_latest_options_snapshot():
    try:
        tier = request.args.get('tier', 'critical')
        underlying = request.args.get('underlying_security')
        limit = max(1, min(int(request.args.get('limit', 200)), 2000))
        query = OptionsQueryService()
        result = query.latest_snapshot(universe_tier=tier, underlying_security=underlying, limit=limit)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/model/latest', methods=['GET'])
def get_latest_options_model_run():
    try:
        underlying = request.args.get('underlying_security') or 'IBOVE Index'
        universe_tier = request.args.get('universe_tier')
        compact = _is_truthy(request.args.get('compact'))
        query = OptionsQueryService()
        result = query.latest_model_run(underlying, universe_tier=universe_tier)
        if compact:
            result = _compact_model_run(result)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/model/run/<run_id>', methods=['GET'])
def get_options_model_run(run_id: str):
    try:
        compact = _is_truthy(request.args.get('compact'))
        query = OptionsQueryService()
        result = query.model_run(run_id)
        if not result:
            return jsonify({"success": False, "error": f"Model run not found: {run_id}"}), 404
        if compact:
            result = _compact_model_run(result)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/global/latest', methods=['GET'])
def get_latest_options_global_run():
    try:
        underlying = request.args.get('underlying_security') or 'IBOVE Index'
        query = OptionsQueryService()
        result = query.latest_global_run(underlying)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/global/run/<run_id>', methods=['GET'])
def get_options_global_run(run_id: str):
    try:
        query = OptionsQueryService()
        result = query.global_run(run_id)
        if not result:
            return jsonify({"success": False, "error": f"Global run not found: {run_id}"}), 404
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/fair-value/latest', methods=['GET'])
def get_latest_options_fair_value_run():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/latest",
        feature="Legacy Options Dashboard fair value",
        timeout=90.0,
    )


@options_bp.route('/fair-value/legs/latest', methods=['GET'])
def get_latest_options_fair_value_legs():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/legs/latest",
        feature="Legacy Options Dashboard fair value legs",
        timeout=90.0,
    )


@options_bp.route('/fair-value/quality/latest', methods=['GET'])
def get_latest_options_fair_value_quality():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/quality/latest",
        feature="Legacy Options Dashboard fair value quality",
        timeout=90.0,
    )


@options_bp.route('/intraday-dependency/latest', methods=['GET'])
def get_latest_intraday_dependency():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/intraday-dependency/latest",
        feature="Legacy intraday dependency",
        timeout=60.0,
    )


@options_bp.route('/intraday-neural/latest', methods=['GET'])
def get_latest_intraday_neural():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/intraday-neural/latest",
        feature="Legacy intraday neural",
        timeout=60.0,
    )


@options_bp.route('/intraday-correlation-history/latest', methods=['GET'])
def get_latest_intraday_correlation_history():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/intraday-correlation-history/latest",
        feature="Legacy intraday correlation history",
        timeout=90.0,
    )


@options_bp.route('/fair-value/regime-price-making/latest', methods=['GET'])
def get_latest_regime_price_making():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/regime-price-making/latest",
        feature="Legacy Options Dashboard regime price making",
        timeout=90.0,
    )


@options_bp.route('/fair-value/price-making/latest', methods=['GET'])
def get_latest_price_making():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/price-making/latest",
        feature="Legacy Options Dashboard price making",
        timeout=90.0,
    )


@options_bp.route('/fair-value/nonlinear-dependence/latest', methods=['GET'])
def get_latest_nonlinear_dependence():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/nonlinear-dependence/latest",
        feature="Legacy Options Dashboard nonlinear dependence",
        timeout=90.0,
    )


@options_bp.route('/fair-value/market-state/latest', methods=['GET'])
def get_latest_market_state():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/market-state/latest",
        feature="Legacy Options Dashboard market state",
        timeout=90.0,
    )


@options_bp.route('/fair-value/live-factors', methods=['GET'])
def get_live_options_fair_value_factors():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/live-factors",
        feature="Legacy Options Dashboard live fair value factors",
        timeout=90.0,
    )


@options_bp.route('/heatmap-context/latest', methods=['GET'])
def get_latest_options_heatmap_context():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/heatmap-context/latest",
        feature="Legacy options heatmap context",
        timeout=60.0,
    )


@options_bp.route('/live-capture/workbook-series', methods=['GET'])
def get_live_capture_workbook_series():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/live-capture/workbook-series",
        feature="Legacy live-capture workbook series",
        timeout=60.0,
    )


@options_bp.route('/live-capture/workbook-latest', methods=['GET'])
def get_live_capture_workbook_latest():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/live-capture/workbook-latest",
        feature="Legacy live-capture workbook latest",
        timeout=60.0,
    )


@options_bp.route('/fair-value/run/<run_id>', methods=['GET'])
def get_options_fair_value_run(run_id: str):
    return legacy_heatmap_proxy_or_disabled(
        f"/api/options/fair-value/run/{run_id}",
        feature="Legacy Options Dashboard fair value run",
        timeout=90.0,
    )


@options_bp.route('/chat', methods=['GET'])
def get_options_chat_thread():
    try:
        underlying = request.args.get('underlying_security') or 'IBOVE Index'
        sign_convention = request.args.get('sign_convention') or 'neutral'
        trade_date = request.args.get('trade_date')
        service = OptionsContextChatService()
        result = service.get_thread(
            underlying_security=underlying,
            sign_convention=sign_convention,
            trade_date=trade_date,
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/chat/message', methods=['POST'])
def send_options_chat_message():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = payload.get('underlying_security') or 'IBOVE Index'
        sign_convention = payload.get('sign_convention') or 'neutral'
        run_id = payload.get('run_id')
        message = payload.get('message')
        service = OptionsContextChatService()
        result = service.send_message(
            underlying_security=underlying,
            sign_convention=sign_convention,
            run_id=run_id,
            message=message,
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/model/run', methods=['POST'])
def run_options_model():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = payload.get('underlying_security') or 'IBOVE Index'
        universe_tier = payload.get('universe_tier')
        sign_convention = payload.get('sign_convention')
        session_date = payload.get('session_date')
        batch_key = payload.get('batch_key')
        persist = bool(payload.get('persist', True))
        run_async = bool(payload.get('async', True))
        compact = _is_truthy(payload.get('compact'))
        refresh_snapshot = bool(payload.get('refresh_snapshot', True))
        service = OptionsModelingService()
        snapshot_service = OptionsSnapshotService()

        def execute() -> dict:
            from ..services.b3_oi_service import B3OIService  # noqa: PLC0415

            b3_oi_service = B3OIService()
            oi_ready = b3_oi_service.ensure_recent_oi(
                trade_date=b3_oi_service.last_published_trade_date(),
            )
            resolved_oi_trade_date = oi_ready.get("resolved_trade_date")
            if not resolved_oi_trade_date:
                raise ValueError(
                    "B3 open interest is not available for the current session or recent business days. "
                    f"Details: {oi_ready.get('error') or 'unknown_error'}"
                )
            if session_date and batch_key and universe_tier:
                result = service.run_for_batch(
                    underlying_security=underlying,
                    universe_tier=universe_tier,
                    session_date=session_date,
                    batch_key=batch_key,
                    sign_convention=sign_convention,
                    persist=persist,
                )
                result.setdefault("diagnostics", {})["b3_oi_trade_date"] = resolved_oi_trade_date
                return result
            if refresh_snapshot:
                tier = str(universe_tier or Config.OPTIONS_MODEL_DEFAULT_TIER or "critical").strip().lower()
                if tier == "full":
                    capture_result = snapshot_service.collect_full_snapshot(underlying)
                elif tier == "structural":
                    capture_result = snapshot_service.collect_structural_snapshot(underlying)
                elif tier == "liquid":
                    capture_result = snapshot_service.collect_liquid_snapshot(underlying)
                else:
                    tier = "critical"
                    capture_result = snapshot_service.collect_critical_snapshot(underlying)
                batch = capture_result.get("batch") or {}
                snapshot_payload = snapshot_service.store.read_snapshot_batch(
                    tier,
                    str(batch.get("session_date") or ""),
                    str(batch.get("batch_key") or ""),
                )
                if snapshot_payload:
                    result = service.run_from_snapshot_payload(
                        snapshot_payload,
                        sign_convention=sign_convention,
                        persist=persist,
                    )
                    result.setdefault("diagnostics", {})["b3_oi_trade_date"] = resolved_oi_trade_date
                    return result
            result = service.run_latest(
                underlying_security=underlying,
                universe_tier=universe_tier,
                sign_convention=sign_convention,
                persist=persist,
            )
            result.setdefault("diagnostics", {})["b3_oi_trade_date"] = resolved_oi_trade_date
            return result

        if not run_async:
            result = execute()
            if compact:
                result = _compact_model_run(result)
            return jsonify({"success": True, "data": result})

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            "options_model_run",
            metadata={
                "underlying_security": underlying,
                "universe_tier": universe_tier,
                "session_date": session_date,
                "batch_key": batch_key,
                "sign_convention": sign_convention,
                "persist": persist,
                "refresh_snapshot": refresh_snapshot,
            },
        )

        def run_model_task() -> None:
            try:
                task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=10, message="Running options quantitative model")
                result = execute()
                task_manager.update_task(task_id, status=TaskStatus.COMPLETED, progress=100, message="Options model completed", result=result)
            except Exception as exc:
                logger.exception("options model task failed", exc_info=exc)
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Options model failed",
                    error="Internal server error",
                )

        threading.Thread(target=run_model_task, daemon=True).start()
        return jsonify({"success": True, "data": {"task_id": task_id, "message": "Options model started"}})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/global/run', methods=['POST'])
def run_options_global_model():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = payload.get('underlying_security') or 'IBOVE Index'
        refresh_local_model = bool(payload.get('refresh_local_model', False))
        persist = bool(payload.get('persist', True))
        run_async = bool(payload.get('async', True))
        service = OptionsGlobalTriangulationService()

        def execute() -> dict:
            return service.run_latest(
                underlying_security=underlying,
                refresh_local_model=refresh_local_model,
                persist=persist,
            )

        if not run_async:
            result = execute()
            return jsonify({"success": True, "data": result})

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            "options_global_run",
            metadata={
                "underlying_security": underlying,
                "refresh_local_model": refresh_local_model,
                "persist": persist,
            },
        )

        def run_global_task() -> None:
            try:
                task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=10, message="Running global triangulation overlay")
                result = execute()
                task_manager.update_task(task_id, status=TaskStatus.COMPLETED, progress=100, message="Global triangulation completed", result=result)
            except Exception as exc:
                logger.exception("global triangulation task failed", exc_info=exc)
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Global triangulation failed",
                    error="Internal server error",
                )

        threading.Thread(target=run_global_task, daemon=True).start()
        return jsonify({"success": True, "data": {"task_id": task_id, "message": "Global triangulation started"}})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/fair-value/run', methods=['POST'])
def run_options_fair_value_model():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/run",
        feature="Legacy Options Dashboard fair value engine",
        timeout=180.0,
    )


@options_bp.route('/hard-refresh', methods=['POST'])
@require_role("admin")
def hard_refresh_options_base():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/hard-refresh",
        feature="Legacy options heatmap hard refresh",
        timeout=180.0,
    )


@options_bp.route('/history/oi', methods=['GET'])
def get_options_oi_history():
    try:
        query = OptionsQueryService()
        result = query.oi_history(
            underlying_security=request.args.get('underlying_security'),
            option_id=request.args.get('option_id'),
            start_date=request.args.get('start_date'),
            end_date=request.args.get('end_date'),
            limit=max(1, min(int(request.args.get('limit', 1000)), 5000)),
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/collector/status', methods=['GET'])
def options_collector_status():
    try:
        if _options_collector_delegated():
            return _options_collector_service_request("GET", "/api/options/collector/status", timeout=5.0)
        return jsonify({"success": True, "data": OptionsCollectorManager.get_instance().status()})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/collector/start', methods=['POST'])
@require_role("admin")
def start_options_collector():
    try:
        if _options_collector_delegated():
            return _options_collector_service_request("POST", "/api/options/collector/start", timeout=10.0)
        status = OptionsCollectorManager.get_instance().start()
        return jsonify({"success": True, "data": status})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/collector/stop', methods=['POST'])
@require_role("admin")
def stop_options_collector():
    try:
        if _options_collector_delegated():
            return _options_collector_service_request("POST", "/api/options/collector/stop", timeout=10.0)
        status = OptionsCollectorManager.get_instance().stop()
        return jsonify({"success": True, "data": status})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/collect', methods=['POST'])
def collect_options_once():
    try:
        payload = request.get_json(silent=True) or {}
        if _options_collector_delegated():
            return _options_collector_service_request(
                "POST",
                "/api/options/collect",
                json_payload=payload,
                timeout=300.0,
            )
        include_structural = bool(payload.get('include_structural', True))
        include_liquid = bool(payload.get('include_liquid', True))
        include_critical = bool(payload.get('include_critical', True))
        include_ticks = payload.get('include_ticks')
        run_async = bool(payload.get('async', True))

        collector = OptionsCollectorManager.get_instance()
        if not run_async:
            result = collector.collect_once(
                include_structural=include_structural,
                include_liquid=include_liquid,
                include_critical=include_critical,
                include_ticks=include_ticks,
            )
            return jsonify({"success": True, "data": result})

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            "options_collect",
            metadata={
                "include_structural": include_structural,
                "include_liquid": include_liquid,
                "include_critical": include_critical,
                "include_ticks": include_ticks,
            },
        )

        def run_collect() -> None:
            try:
                task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=10, message="Collecting options snapshots")
                result = collector.collect_once(
                    include_structural=include_structural,
                    include_liquid=include_liquid,
                    include_critical=include_critical,
                    include_ticks=include_ticks,
                )
                task_manager.update_task(task_id, status=TaskStatus.COMPLETED, progress=100, message="Options collection completed", result=result)
            except Exception as exc:
                logger.exception("options collection task failed", exc_info=exc)
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Options collection failed",
                    error="Internal server error",
                )

        threading.Thread(target=run_collect, daemon=True).start()
        return jsonify({"success": True, "data": {"task_id": task_id, "message": "Options collection started"}})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/history/backfill', methods=['POST'])
@require_role("admin")
def backfill_options_history():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = payload.get('underlying_security') or 'IBOVE Index'
        lookback_days = payload.get('lookback_days')
        max_contracts = payload.get('max_contracts')
        run_async = bool(payload.get('async', True))
        service = OptionsHistoryService()

        if not run_async:
            result = service.backfill_open_interest_history(
                underlying,
                lookback_days=lookback_days,
                max_contracts=max_contracts,
            )
            return jsonify({"success": True, "data": result})

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            "options_oi_backfill",
            metadata={"underlying_security": underlying, "lookback_days": lookback_days, "max_contracts": max_contracts},
        )

        def run_backfill() -> None:
            try:
                task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=10, message="Backfilling options OI history")
                result = service.backfill_open_interest_history(
                    underlying,
                    lookback_days=lookback_days,
                    max_contracts=max_contracts,
                )
                task_manager.update_task(task_id, status=TaskStatus.COMPLETED, progress=100, message="Options OI backfill completed", result=result)
            except Exception as exc:
                logger.exception("options OI backfill task failed", exc_info=exc)
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Options OI backfill failed",
                    error="Internal server error",
                )

        threading.Thread(target=run_backfill, daemon=True).start()
        return jsonify({"success": True, "data": {"task_id": task_id, "message": "Options OI backfill started"}})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/history/update', methods=['POST'])
def update_options_history():
    try:
        payload = request.get_json(silent=True) or {}
        if _options_collector_delegated():
            return _options_collector_service_request(
                "POST",
                "/api/options/history/update",
                json_payload=payload,
                timeout=300.0,
            )
        underlying = payload.get('underlying_security') or 'IBOVE Index'
        trade_date = payload.get('trade_date')
        max_contracts = payload.get('max_contracts')
        force = bool(payload.get('force', False))
        collector = OptionsCollectorManager.get_instance()
        result = collector.update_daily_history_once(underlying, trade_date=trade_date, max_contracts=max_contracts, force=force)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/history/oi-status', methods=['GET'])
def get_oi_daily_status():
    """Retorna se o OI diário já foi coletado para o underlying/data informados."""
    try:
        underlying = request.args.get('underlying_security') or 'IBOVE Index'
        trade_date = request.args.get('trade_date') or None
        history_service = OptionsHistoryService()
        complete = history_service.is_daily_oi_complete(underlying, trade_date)
        from datetime import datetime as _dt
        target_date = trade_date or _dt.now().date().isoformat()
        return jsonify({
            "success": True,
            "data": {
                "underlying_security": underlying,
                "trade_date": target_date,
                "daily_oi_complete": complete,
            }
        })
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/b3/oi/collect', methods=['POST'])
def collect_b3_open_interest():
    """
    Dispara a coleta de Posicoes em Aberto (OI) da B3 para uma data.

    Body JSON (opcional):
      trade_date  string   YYYY-MM-DD (padrao: hoje)
      force       bool     Re-coleta mesmo se ja coletado (padrao: false)

    Retorna: rows_saved, trade_date, skipped, error
    """
    try:
        from ..services.b3_oi_service import B3OIService
        body = request.get_json(force=True, silent=True) or {}
        trade_date = body.get("trade_date") or request.args.get("trade_date") or None
        force      = _is_truthy(body.get("force", False))

        service = B3OIService()
        result  = service.collect_daily_oi(trade_date=trade_date, force=force)
        return jsonify({"success": True, "data": {
            k: v for k, v in result.items() if k != "rows"  # exclui lista completa do response
        }})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/b3/oi/status', methods=['GET'])
def get_b3_oi_status():
    """
    Retorna status do OI B3: se foi coletado, datas disponiveis, e
    contagem de contratos para a data informada.

    Query params:
      trade_date  string   YYYY-MM-DD (padrao: hoje)
    """
    try:
        from ..services.b3_oi_service import B3OIService
        from ..services.options_store import OptionsStore
        trade_date = request.args.get("trade_date") or None

        service = B3OIService()
        store   = OptionsStore()

        from datetime import datetime as _dt
        target_date = trade_date or _dt.now().date().isoformat()

        collected = service.is_collected(target_date)
        dates     = service.list_collected_dates()
        rows      = store.load_b3_oi_rows(target_date) if collected else []

        return jsonify({"success": True, "data": {
            "trade_date":        target_date,
            "collected":         collected,
            "contracts_count":   len(rows),
            "dates_available":   dates,
            "sample":            rows[:3] if rows else [],
        }})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/b3/oi/backfill', methods=['POST'])
@require_role("admin")
def backfill_b3_open_interest():
    """
    Dispara backfill de OI da B3 para um intervalo de datas.
    Roda em background (thread separada).

    Body JSON:
      date_from   string   YYYY-MM-DD (obrigatorio)
      date_to     string   YYYY-MM-DD (obrigatorio)
      force       bool     Re-coleta mesmo se ja coletado (padrao: false)
    """
    try:
        from ..services.b3_oi_service import B3OIService
        body = request.get_json(force=True, silent=True) or {}
        date_from = body.get("date_from")
        date_to   = body.get("date_to")
        force     = _is_truthy(body.get("force", False))

        if not date_from or not date_to:
            return jsonify({"success": False, "error": "date_from e date_to sao obrigatorios"}), 400

        import threading as _th
        service = B3OIService()

        def _run():
            try:
                service.backfill(date_from=date_from, date_to=date_to, force=force)
            except Exception as exc:
                import logging
                logging.getLogger("aquiles.b3_oi_service").error("Backfill erro: %s", exc)

        t = _th.Thread(target=_run, daemon=True, name="b3-oi-backfill")
        t.start()

        return jsonify({"success": True, "data": {
            "message":   "Backfill iniciado em background",
            "date_from": date_from,
            "date_to":   date_to,
            "force":     force,
        }})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/jobs/<task_id>', methods=['GET'])
def get_options_task(task_id: str):
    task = TaskManager().get_task(task_id)
    if not task:
        if _options_collector_delegated():
            return _options_collector_service_request(
                "GET",
                f"/api/options/jobs/{task_id}",
                timeout=5.0,
            )
        return jsonify({"success": False, "error": f"Task not found: {task_id}"}), 404
    return jsonify({"success": True, "data": task.to_dict()})



# ─── Live spot price ─────────────────────────────────────────────────────────
# Cache simples em memória: {symbol: (spot_float, timestamp)}
_SPOT_CACHE: dict[str, tuple[float, float]] = {}
_SPOT_CACHE_TTL = 5 * 60  # 5 minutos


@options_bp.route('/market/spot', methods=['GET'])
def market_spot():
    """
    Retorna o preço spot atual do subjacente via OpLab.

    Query params:
      underlying  — símbolo OpLab (default: 'IBOV')

    Resposta:
      { spot: float, underlying: str, ts: float, cached: bool }
    """
    underlying = (request.args.get('underlying') or 'IBOV').strip().upper()
    now = _time.time()

    cached_entry = _SPOT_CACHE.get(underlying)
    if cached_entry and (now - cached_entry[1]) < _SPOT_CACHE_TTL:
        spot, ts = cached_entry
        return jsonify({
            'spot': spot,
            'underlying': underlying,
            'ts': ts,
            'cached': True,
            'age_seconds': round(now - ts),
        })

    try:
        from ..services.oplab_options_service import OpLabOptionsService
        svc = OpLabOptionsService.get_instance()
        spot = svc.fetch_live_spot(underlying)

        if spot is None:
            # Fallback: tenta extrair do modelo mais recente em cache
            from ..services.options_modeling import OptionsModelingService
            model_svc = OptionsModelingService.get_instance()
            latest = model_svc.get_latest_result()
            if latest:
                ctx = getattr(latest, 'market_context', None) or {}
                if isinstance(ctx, dict):
                    spot = ctx.get('spot_price')
                else:
                    spot = getattr(ctx, 'spot_price', None)

        if spot is None:
            return error_response(logger, status_code=503, message='Spot price indisponível', extra={'underlying': underlying})

        _SPOT_CACHE[underlying] = (float(spot), now)
        return jsonify({
            'spot': float(spot),
            'underlying': underlying,
            'ts': now,
            'cached': False,
            'age_seconds': 0,
        })

    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


# ─── B3 Open Interest ────────────────────────────────────────────────────────

@options_bp.route('/b3-oi/latest', methods=['GET'])
def b3_oi_latest():
    """
    Retorna o OI da B3 mais recente, agregado por strike (call + put).

    Query params:
      date  (str)  YYYY-MM-DD — data específica (padrão: data mais recente disponível)
      raw   (bool) se 'true', devolve as linhas brutas sem agregar

    Response (agregado):
      {
        "date": "2026-05-14",
        "total_rows": 762,
        "by_strike": [
          {
            "strike": 175000.0,
            "call_oi": 5000, "put_oi": 3000, "total_oi": 8000,
            "call_coberto": 0, "call_trava": 5000, "call_descoberto": 0,
            "put_coberto": 0,  "put_trava": 3000, "put_descoberto": 0
          }, ...
        ]
      }
    """
    try:
        from ..services.options_store import OptionsStore
        store = OptionsStore()

        requested_date = request.args.get('date') or None
        raw_mode = request.args.get('raw', 'false').lower() == 'true'

        # Descobrir a data mais recente disponível
        if requested_date:
            trade_date = requested_date
        else:
            dates = store.list_b3_oi_dates()
            if not dates:
                return jsonify({"success": True, "data": {"date": None, "by_strike": [], "total_rows": 0}})
            trade_date = sorted(dates)[-1]  # mais recente

        rows = store.load_b3_oi_rows(trade_date)

        if raw_mode:
            return jsonify({"success": True, "data": rows, "date": trade_date, "count": len(rows)})

        # Agregar por strike
        strike_map: dict[float, dict] = {}
        for r in rows:
            s = float(r.get("strike") or 0)
            if s <= 0:
                continue
            if s not in strike_map:
                strike_map[s] = {
                    "strike": s,
                    "call_oi": 0, "put_oi": 0, "total_oi": 0,
                    "call_coberto": 0, "call_trava": 0, "call_descoberto": 0,
                    "put_coberto": 0,  "put_trava": 0,  "put_descoberto": 0,
                    "call_n_titular": 0, "call_n_lancador": 0,
                    "put_n_titular": 0,  "put_n_lancador": 0,
                }
            entry = strike_map[s]
            t = str(r.get("type") or "").upper()
            oi = int(r.get("oi_total") or 0)
            if t == "CALL":
                entry["call_oi"]        += oi
                entry["call_coberto"]   += int(r.get("oi_coberto") or 0)
                entry["call_trava"]     += int(r.get("oi_trava")   or 0)
                entry["call_descoberto"]+= int(r.get("oi_descoberto") or 0)
                entry["call_n_titular"] += int(r.get("n_titular") or 0)
                entry["call_n_lancador"]+= int(r.get("n_lancador") or 0)
            elif t == "PUT":
                entry["put_oi"]         += oi
                entry["put_coberto"]    += int(r.get("oi_coberto") or 0)
                entry["put_trava"]      += int(r.get("oi_trava")   or 0)
                entry["put_descoberto"] += int(r.get("oi_descoberto") or 0)
                entry["put_n_titular"]  += int(r.get("n_titular") or 0)
                entry["put_n_lancador"] += int(r.get("n_lancador") or 0)
            entry["total_oi"] = entry["call_oi"] + entry["put_oi"]

        by_strike = sorted(strike_map.values(), key=lambda x: x["strike"])

        return jsonify({
            "success": True,
            "data": {
                "date": trade_date,
                "total_rows": len(rows),
                "by_strike": by_strike,
            }
        })
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/b3-oi/dates', methods=['GET'])
def b3_oi_dates():
    """Lista todas as datas com dados de OI B3 disponíveis."""
    try:
        from ..services.options_store import OptionsStore
        store = OptionsStore()
        dates = store.list_b3_oi_dates()
        return jsonify({"success": True, "data": sorted(dates)})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/snapshot/by-strike', methods=['GET'])
def snapshot_by_strike():
    """
    Retorna dados do snapshot mais recente agregados por strike.
    Útil para IV smile (MODEL_IV por strike/put_call) e GEX calculation
    quando combinado com B3 OI.

    Query params:
      underlying_security  (str)  ex: 'IBOVE Index'
      tier                 (str)  'critical' | 'liquid' | 'structural' | 'all' (padrão: critical)
                                  'all' = mescla todos os tiers para máxima cobertura de strikes
    """
    try:
        from ..services.options_query_service import OptionsQueryService
        from ..services.options_store import OptionsStore
        underlying = request.args.get('underlying_security') or 'IBOVE Index'
        tier       = request.args.get('tier') or 'critical'

        store = OptionsStore()
        query = OptionsQueryService(store=store)

        if tier == 'all':
            # Mescla todos os tiers para obter cobertura máxima de strikes
            all_rows: list = []
            seen_ids: set  = set()
            for t_name in ('structural', 'liquid', 'critical'):
                try:
                    res_t  = query.latest_snapshot(universe_tier=t_name, underlying_security=underlying, limit=5000)
                    rows_t = res_t.get("rows", []) if isinstance(res_t, dict) else []
                except Exception:
                    rows_t = []
                for r in rows_t:
                    uid = (r.get("bloomberg_ticker") or r.get("option_id") or
                           f"{r.get('strike')}_{r.get('put_call') or r.get('OPT_PUT_CALL')}")
                    if uid and uid not in seen_ids:
                        seen_ids.add(uid)
                        all_rows.append(r)
            rows = all_rows
        else:
            # latest_snapshot retorna {"batch": {...}, "rows": [...dicts...]}
            result = query.latest_snapshot(
                universe_tier=tier,
                underlying_security=underlying,
                limit=2000,
            )
            rows = result.get("rows", []) if isinstance(result, dict) else []

        if not rows:
            return jsonify({"success": True, "data": {"by_strike": [], "options": []}})

        # Monta lista limpa por opção (para IV smile)
        options_list = []
        for r in rows:
            pc = str(r.get("put_call") or r.get("OPT_PUT_CALL") or "").capitalize()
            options_list.append({
                "symbol":      r.get("bloomberg_ticker") or r.get("option_id"),
                "put_call":    pc,                                   # 'Call' | 'Put'
                "strike":      r.get("strike") or r.get("OPT_STRIKE_PX"),
                "expiry_date": r.get("expiry_date") or r.get("OPT_EXPIRE_DT"),
                "days_to_expiry": r.get("days_to_expiry_business") or r.get("days_to_expiry_calendar"),
                # IV — MODEL_IV é calculado do mid real (bid/ask), mais confiável que IVOL_MID histórico
                "iv":    r.get("MODEL_IV") or r.get("EFF_IV") or r.get("IVOL_MID"),
                "iv_bid": r.get("IVOL_BID"),
                "iv_ask": r.get("IVOL_ASK"),
                # OI (geralmente null para IBOV — usar B3)
                "open_int": r.get("OPEN_INT") or r.get("OPT_OPEN_INTEREST"),
                # Preços
                "bid":  r.get("BID"),
                "ask":  r.get("ASK"),
                "mid":  r.get("MID") or r.get("bid_ask_mid"),
                "last": r.get("PX_LAST"),
                # Greeks (modelo interno)
                "delta":  r.get("MODEL_DELTA") or r.get("OPT_DELTA"),
                "gamma":  r.get("MODEL_GAMMA_POINT") or r.get("OPT_GAMMA"),
                "vega":   r.get("MODEL_VEGA_1PCTVOL") or r.get("OPT_VEGA"),
                "theta":  r.get("MODEL_THETA_BD252") or r.get("OPT_THETA"),
                "vanna":  r.get("MODEL_VANNA"),
                "charm":  r.get("MODEL_CHARM_BD252"),
                # Score
                "moneyness":   r.get("moneyness_spot"),
                "market_ok":   r.get("market_ok"),
                "spot_price":  r.get("OPT_UNDL_PX"),
            })

        # Agrega por strike para facilitar charts
        strike_map: dict[float, dict] = {}
        for o in options_list:
            s = float(o["strike"] or 0)
            if s <= 0:
                continue
            if s not in strike_map:
                strike_map[s] = {"strike": s, "calls": [], "puts": []}
            if o["put_call"] == "Call":
                strike_map[s]["calls"].append(o)
            else:
                strike_map[s]["puts"].append(o)

        by_strike = []
        for s, v in sorted(strike_map.items()):
            calls = v["calls"]
            puts  = v["puts"]
            best_call = max(calls, key=lambda x: x.get("market_ok") or 0) if calls else {}
            best_put  = max(puts,  key=lambda x: x.get("market_ok") or 0) if puts  else {}
            by_strike.append({
                "strike":   s,
                "iv_call":  best_call.get("iv"),
                "iv_put":   best_put.get("iv"),
                "gamma_call": best_call.get("gamma"),
                "gamma_put":  best_put.get("gamma"),
                "delta_call": best_call.get("delta"),
                "delta_put":  best_put.get("delta"),
                "vega_call":  best_call.get("vega"),
                "vega_put":   best_put.get("vega"),
                "open_int_call": best_call.get("open_int"),
                "open_int_put":  best_put.get("open_int"),
            })

        return jsonify({
            "success": True,
            "data": {
                "by_strike": by_strike,
                "options":   options_list,
            }
        })
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route('/diagnostics', methods=['GET'])
def options_diagnostics():
    """
    Retorna estatísticas de cobertura de dados de opções para debugging de pipeline.

    Query params:
      underlying_security  (str)  ex: 'IBOVE Index'
    """
    try:
        from ..services.options_query_service import OptionsQueryService
        from ..services.options_store import OptionsStore

        underlying = request.args.get('underlying_security') or 'IBOVE Index'
        store = OptionsStore()
        query = OptionsQueryService(store=store)

        # ── Contratos ─────────────────────────────────────────────────────────
        contracts = store.list_contracts(underlying_security=underlying)
        active    = [c for c in contracts if c.get('status') == 'active']
        eligible  = [c for c in active if c.get('mvp_eligible')]

        # ── Snapshot por tier ─────────────────────────────────────────────────
        tier_stats: dict[str, dict] = {}
        all_rows_merged: list[dict] = []
        seen_ids: set = set()

        for tier_name in ('full', 'structural', 'liquid', 'critical'):
            try:
                res  = query.latest_snapshot(universe_tier=tier_name, underlying_security=underlying, limit=5000)
                rows = res.get('rows', []) if isinstance(res, dict) else []
            except Exception:
                rows = []

            iv_count     = sum(1 for r in rows if r.get('MODEL_IV') or r.get('EFF_IV') or r.get('IVOL_MID'))
            oi_count     = sum(1 for r in rows if r.get('OPEN_INT') or r.get('OPT_OPEN_INTEREST'))
            greek_count  = sum(1 for r in rows if r.get('MODEL_DELTA') or r.get('EFF_DELTA') or r.get('OPT_DELTA'))
            stale_count  = sum(1 for r in rows if r.get('stale_flag'))
            market_ok    = sum(1 for r in rows if r.get('market_ok'))

            tier_stats[tier_name] = {
                'rows':           len(rows),
                'iv_coverage':    iv_count,
                'oi_coverage':    oi_count,
                'greek_coverage': greek_count,
                'stale_count':    stale_count,
                'market_ok':      market_ok,
                'iv_pct':    round(100 * iv_count    / max(len(rows), 1)),
                'oi_pct':    round(100 * oi_count    / max(len(rows), 1)),
                'greek_pct': round(100 * greek_count / max(len(rows), 1)),
                'ok_pct':    round(100 * market_ok   / max(len(rows), 1)),
            }

            for r in rows:
                uid = r.get('bloomberg_ticker') or r.get('option_id')
                if uid and uid not in seen_ids:
                    seen_ids.add(uid)
                    all_rows_merged.append(r)

        # ── Cobertura global (todos os tiers) ─────────────────────────────────
        n_total    = len(all_rows_merged)
        n_iv       = sum(1 for r in all_rows_merged if r.get('MODEL_IV') or r.get('EFF_IV') or r.get('IVOL_MID'))
        n_oi       = sum(1 for r in all_rows_merged if r.get('OPEN_INT') or r.get('OPT_OPEN_INTEREST'))
        n_greeks   = sum(1 for r in all_rows_merged if r.get('MODEL_DELTA') or r.get('EFF_DELTA') or r.get('OPT_DELTA'))
        n_model_iv = sum(1 for r in all_rows_merged if r.get('MODEL_IV'))
        n_eff_iv   = sum(1 for r in all_rows_merged if r.get('EFF_IV') and not r.get('MODEL_IV'))
        n_oplab_iv = sum(1 for r in all_rows_merged if r.get('IVOL_MID') and not r.get('MODEL_IV') and not r.get('EFF_IV'))

        expiries = sorted({r.get('expiry_date') for r in all_rows_merged if r.get('expiry_date')})

        # ── B3 OI ──────────────────────────────────────────────────────────────
        try:
            b3_dates = store.list_b3_oi_dates()
            latest_b3_date = b3_dates[-1] if b3_dates else None
            b3_rows   = store.load_b3_oi_rows(latest_b3_date) if latest_b3_date else []
            b3_symbols = [r.get('symbol') for r in b3_rows if r.get('symbol')]
        except Exception:
            b3_dates, latest_b3_date, b3_symbols = [], None, []

        # ── Model run ──────────────────────────────────────────────────────────
        try:
            latest_run = query.latest_model_run(underlying)
        except Exception:
            latest_run = None

        model_diag: dict = {}
        if latest_run:
            diag = latest_run.get('diagnostics') or {}
            model_diag = {
                'available':        True,
                'captured_at':      latest_run.get('captured_at'),
                'prepared_count':   diag.get('prepared_count'),
                'strike_profiles':  len(latest_run.get('strike_profiles') or []),
                'has_nonzero_gex':  any(
                    abs(sp.get('gex_net') or 0) > 0
                    for sp in (latest_run.get('strike_profiles') or [])
                ),
                'has_nonzero_oi': any(
                    (sp.get('open_interest_total') or 0) > 0
                    for sp in (latest_run.get('strike_profiles') or [])
                ),
                'sign_convention': (latest_run.get('config') or {}).get('sign_convention'),
            }
        else:
            model_diag = {'available': False}

        return jsonify({
            'success': True,
            'data': {
                'underlying':  underlying,
                'contracts': {
                    'total':    len(contracts),
                    'active':   len(active),
                    'eligible': len(eligible),
                },
                'snapshot': {
                    'total_unique_options': n_total,
                    'expiries':        expiries,
                    'expiry_count':    len(expiries),
                    'iv_coverage':     n_iv,
                    'iv_pct':          round(100 * n_iv    / max(n_total, 1)),
                    'model_iv_count':  n_model_iv,
                    'eff_iv_count':    n_eff_iv,
                    'oplab_iv_count':  n_oplab_iv,
                    'oi_coverage':     n_oi,
                    'oi_pct':          round(100 * n_oi    / max(n_total, 1)),
                    'greek_coverage':  n_greeks,
                    'greek_pct':       round(100 * n_greeks / max(n_total, 1)),
                },
                'tiers':   tier_stats,
                'b3_oi': {
                    'dates_available': len(b3_dates),
                    'latest_date':     latest_b3_date,
                    'symbol_count':    len(b3_symbols),
                },
                'model_run': model_diag,
            }
        })
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.route('/vol-surface', methods=['GET'])
def options_vol_surface():
    """
    Retorna superfície de volatilidade implícita organizada por (expiry × strike).
    Usa MODEL_IV como fonte primária — mais confiável que IVOL_MID durante pregão.

    Query params:
      underlying_security  (str)   ex: 'IBOVE Index'
      tier                 (str)   'all' | 'structural' | 'liquid' | 'critical'
      min_dte              (int)   DTE mínimo em dias úteis (padrão: 1)
      max_dte              (int)   DTE máximo (padrão: 120)
    """
    try:
        from ..services.options_query_service import OptionsQueryService
        from ..services.options_store import OptionsStore

        underlying = request.args.get('underlying_security') or 'IBOVE Index'
        tier       = request.args.get('tier') or 'all'
        min_dte    = int(request.args.get('min_dte') or 1)
        max_dte    = int(request.args.get('max_dte') or 120)

        store = OptionsStore()
        query = OptionsQueryService(store=store)

        # Coleta rows (mesma lógica do snapshot_by_strike)
        if tier == 'all':
            all_rows: list = []
            seen_ids: set  = set()
            for t_name in ('structural', 'liquid', 'critical'):
                try:
                    res_t  = query.latest_snapshot(universe_tier=t_name, underlying_security=underlying, limit=5000)
                    rows_t = res_t.get('rows', []) if isinstance(res_t, dict) else []
                except Exception:
                    rows_t = []
                for r in rows_t:
                    uid = r.get('bloomberg_ticker') or r.get('option_id')
                    if uid and uid not in seen_ids:
                        seen_ids.add(uid)
                        all_rows.append(r)
            rows = all_rows
        else:
            result = query.latest_snapshot(universe_tier=tier, underlying_security=underlying, limit=5000)
            rows   = result.get('rows', []) if isinstance(result, dict) else []

        if not rows:
            return jsonify({'success': True, 'data': {'slices': [], 'spot': None, 'forward': None}})

        # Spot price — tenta OPT_UNDL_PX nas rows, depois latest model run
        spot_price = None
        for r in rows:
            v = r.get('OPT_UNDL_PX') or r.get('underlying_px') or r.get('spot_price')
            if v:
                try:
                    spot_price = float(v)
                    break
                except Exception:
                    pass
        if not spot_price:
            try:
                _store2 = OptionsStore()
                _run = _store2.read_latest_model_run(underlying)
                if _run:
                    spot_price = (_run.get('market_context') or {}).get('spot_price')
            except Exception:
                pass

        # ── Monta pontos individuais ───────────────────────────────────────────
        points = []
        for r in rows:
            dte = r.get('days_to_expiry_business') or r.get('days_to_expiry_calendar') or 0
            try:
                dte = int(dte)
            except Exception:
                continue
            if dte < min_dte or dte > max_dte:
                continue

            strike = r.get('strike') or r.get('OPT_STRIKE_PX')
            try:
                strike = float(strike)
            except Exception:
                continue
            if strike <= 0:
                continue

            # IV — MODEL_IV é mais preciso (calculado do mid real)
            iv = r.get('MODEL_IV') or r.get('EFF_IV') or r.get('IVOL_MID')
            try:
                iv = float(iv) if iv is not None else None
            except Exception:
                iv = None

            if iv is None or iv < 0.005 or iv > 5.0:
                continue

            pc = str(r.get('put_call') or r.get('OPT_PUT_CALL') or '').strip().capitalize()
            expiry = r.get('expiry_date') or r.get('OPT_EXPIRE_DT') or ''
            moneyness = (strike / spot_price - 1.0) if spot_price else None

            points.append({
                'ticker':     r.get('bloomberg_ticker') or r.get('option_id'),
                'strike':     strike,
                'expiry':     expiry,
                'dte':        dte,
                'put_call':   pc,
                'iv':         round(iv, 6),
                'iv_observed': round(iv, 6),
                'moneyness':  round(moneyness, 6) if moneyness is not None else None,
                'log_m':      round(float(__import__('math').log(strike / spot_price)), 6) if spot_price and strike > 0 else None,
                'delta':      _safe_float(r.get('MODEL_DELTA') or r.get('EFF_DELTA') or r.get('OPT_DELTA')),
                'bid':        _safe_float(r.get('BID')),
                'ask':        _safe_float(r.get('ASK')),
                'volume':     _safe_float(r.get('VOLUME') or r.get('OPT_VOLUME') or r.get('volume') or r.get('volume_delta')),
                'open_int':   _safe_float(r.get('OPEN_INT') or r.get('OPT_OPEN_INTEREST') or r.get('open_int')),
                'market_ok':  bool(r.get('market_ok')),
                'spread_pct': _safe_float(r.get('spread_pct')),
            })

        # ── Agrupa por expiry ─────────────────────────────────────────────────
        from collections import defaultdict
        by_expiry: dict[str, list] = defaultdict(list)
        for p in points:
            by_expiry[p['expiry']].append(p)

        slices = []
        for expiry, pts in sorted(by_expiry.items(), key=lambda x: (next(iter(x[1]), {}).get('dte') or 999)):
            dtes = [p['dte'] for p in pts]
            dte_val = round(sum(dtes) / len(dtes)) if dtes else 0

            # Separa calls e puts, ordena por strike
            calls = sorted([p for p in pts if p['put_call'] == 'Call'], key=lambda x: x['strike'])
            puts  = sorted([p for p in pts if p['put_call'] == 'Put'],  key=lambda x: x['strike'])
            all_sorted = sorted(pts, key=lambda x: x['strike'])

            slices.append({
                'expiry':     expiry,
                'dte':        dte_val,
                'point_count': len(pts),
                'calls':      calls,
                'puts':       puts,
                'all':        all_sorted,
            })

        return jsonify({
            'success': True,
            'data': {
                'spot':    spot_price,
                'forward': spot_price,  # pode ser substituído pelo forward real se disponível
                'slices':  slices,
                'total_points': len(points),
            }
        })

    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


