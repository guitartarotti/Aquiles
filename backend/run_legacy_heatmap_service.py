"""
Legacy Macro Heatmap / Options Context API.

This service keeps the old Heatmap experiments available for manual review
without loading or running them inside the main Flask backend. It is intended
to stay stopped by default under PM2.
"""

from __future__ import annotations

import os
import sys
import threading

from flask import Flask, jsonify, request
from flask_cors import CORS

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.auth import register_auth, require_role
from app.config import Config
from app.http import error_response, register_error_handlers
from app.server import serve
from app.utils.logger import get_logger

logger = get_logger("aquiles.legacy_heatmap_service")


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default_value: int) -> int:
    try:
        return int(str(os.environ.get(name, default_value)).strip())
    except Exception:
        return default_value


def _apply_legacy_defaults() -> None:
    """Keep legacy loops disabled unless explicitly started in this process."""
    Config.MACRO_PARTICIPANT_HEATMAP_AUTO_START = _is_truthy(
        os.environ.get("LEGACY_PARTICIPANT_HEATMAP_AUTO_START", "false")
    )
    Config.MACRO_OPTIONS_HEATMAP_CONTEXT_AUTO_START = _is_truthy(
        os.environ.get("LEGACY_OPTIONS_HEATMAP_CONTEXT_AUTO_START", "false")
    )
    Config.OPTIONS_INTRADAY_CORRELATION_CONTINUOUS_ENABLE = _is_truthy(
        os.environ.get("LEGACY_INTRADAY_CORRELATION_CONTINUOUS_ENABLE", "false")
    )
    Config.MACRO_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS = _int_env(
        "LEGACY_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS",
        300,
    )
    Config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS = _int_env(
        "LEGACY_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS",
        60,
    )
    Config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS = _int_env(
        "LEGACY_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS",
        60,
    )


_apply_legacy_defaults()

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)


def _json_error(exc: Exception, status_code: int = 500):
    return error_response(logger, status_code=status_code, exception=exc)


def _workbook_securities_from_request(default_security: str = "VXBR Index") -> list[str]:
    values = request.args.getlist("security")
    raw_securities = request.args.get("securities")
    if raw_securities:
        values.extend([item.strip() for item in raw_securities.split(",") if item.strip()])
    securities = list(dict.fromkeys(str(item or "").strip() for item in values if str(item or "").strip()))
    return securities or [default_security]


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "service": "aquiles-legacy-heatmap-service",
        "auto_start": {
            "participant_heatmap": bool(Config.MACRO_PARTICIPANT_HEATMAP_AUTO_START),
            "options_heatmap_context": bool(Config.MACRO_OPTIONS_HEATMAP_CONTEXT_AUTO_START),
            "intraday_correlation_continuous": bool(Config.OPTIONS_INTRADAY_CORRELATION_CONTINUOUS_ENABLE),
        },
    }


@app.route("/api/legacy/heatmap/status", methods=["GET"])
def legacy_heatmap_status():
    try:
        from app.services.macro_options_heatmap_context_manager import (
            MacroOptionsHeatmapContextManager,
        )
        from app.services.macro_participant_heatmap_manager import (
            MacroParticipantHeatmapCollectorManager,
        )

        participant = MacroParticipantHeatmapCollectorManager.get_instance().status()
        options_context = MacroOptionsHeatmapContextManager.get_instance().status()
        return jsonify({
            "success": True,
            "data": {
                "participant_heatmap": participant,
                "options_heatmap_context": options_context,
            },
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/legacy/heatmap/participant/start", methods=["POST"])
@require_role("admin")
def start_participant_heatmap():
    try:
        from app.services.macro_participant_heatmap_manager import (
            MacroParticipantHeatmapCollectorManager,
        )

        return jsonify({
            "success": True,
            "data": MacroParticipantHeatmapCollectorManager.get_instance().start(),
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/legacy/heatmap/participant/stop", methods=["POST"])
@require_role("admin")
def stop_participant_heatmap():
    try:
        from app.services.macro_participant_heatmap_manager import (
            MacroParticipantHeatmapCollectorManager,
        )

        return jsonify({
            "success": True,
            "data": MacroParticipantHeatmapCollectorManager.get_instance().stop(),
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/legacy/heatmap/options-context/start", methods=["POST"])
@require_role("admin")
def start_options_heatmap_context():
    try:
        from app.services.macro_options_heatmap_context_manager import (
            MacroOptionsHeatmapContextManager,
        )

        return jsonify({
            "success": True,
            "data": MacroOptionsHeatmapContextManager.get_instance().start(),
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/legacy/heatmap/options-context/stop", methods=["POST"])
@require_role("admin")
def stop_options_heatmap_context():
    try:
        from app.services.macro_options_heatmap_context_manager import (
            MacroOptionsHeatmapContextManager,
        )

        return jsonify({
            "success": True,
            "data": MacroOptionsHeatmapContextManager.get_instance().stop(),
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/macro/participant-heatmap", methods=["GET"])
def participant_heatmap():
    try:
        from app.services.macro_participant_heatmap_manager import (
            MacroParticipantHeatmapCollectorManager,
        )

        refresh = _is_truthy(request.args.get("refresh"))
        manager = MacroParticipantHeatmapCollectorManager.get_instance()
        result = manager.service.get_panel(refresh=refresh)
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/heatmap-context/latest", methods=["GET"])
def options_heatmap_context_latest():
    try:
        from app.services.macro_options_heatmap_context_manager import (
            MacroOptionsHeatmapContextManager,
        )

        refresh = _is_truthy(request.args.get("refresh"))
        manager = MacroOptionsHeatmapContextManager.get_instance()
        result = manager.service.build_payload(refresh=refresh)
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/intraday-dependency/latest", methods=["GET"])
def intraday_dependency_latest():
    try:
        from app.services.macro_options_heatmap_context_manager import (
            MacroOptionsHeatmapContextManager,
        )
        from app.services.options_fair_value_modeling.intraday_dependency_service import (
            IntradayDependencyService,
        )

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        session_date = request.args.get("session_date")
        factor = request.args.get("factor")
        include_history = _is_truthy(request.args.get("include_history")) or bool(factor)
        refresh = _is_truthy(request.args.get("refresh"))

        if refresh:
            MacroOptionsHeatmapContextManager.get_instance().service.capture_once(
                force_fair_value=False,
                force_wyrm=False,
                allow_scheduled_wyrm=False,
            )

        result = IntradayDependencyService().build_payload(
            underlying_security=underlying,
            session_date=session_date,
            factor=factor,
            include_history=include_history,
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/intraday-neural/latest", methods=["GET"])
def intraday_neural_latest():
    try:
        from app.services.macro_options_heatmap_context_manager import (
            MacroOptionsHeatmapContextManager,
        )
        from app.services.options_fair_value_modeling.intraday_neural_model_service import (
            IntradayNeuralModelService,
        )

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        refresh = _is_truthy(request.args.get("refresh"))
        include_history = _is_truthy(request.args.get("include_history"))
        horizon_minutes = request.args.get("horizon_minutes")
        horizon_value = int(horizon_minutes) if str(horizon_minutes or "").strip() else None

        if refresh:
            MacroOptionsHeatmapContextManager.get_instance().service.capture_once(
                force_fair_value=False,
                force_wyrm=False,
                allow_scheduled_wyrm=False,
            )

        result = IntradayNeuralModelService().build_payload(
            underlying_security=underlying,
            horizon_minutes=horizon_value,
            include_history=include_history,
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/intraday-correlation-history/latest", methods=["GET"])
def intraday_correlation_history_latest():
    try:
        from app.services.macro_options_heatmap_context_manager import (
            MacroOptionsHeatmapContextManager,
        )
        from app.services.options_fair_value_modeling.intraday_correlation_history_service import (
            IntradayCorrelationHistoryService,
        )

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        refresh = _is_truthy(request.args.get("refresh"))
        lookback_days = int(request.args.get("lookback_days") or 1)
        horizon_minutes = int(request.args.get("horizon_minutes") or 5)
        factor_list = [
            item.strip()
            for item in str(request.args.get("factors") or "").split(",")
            if item.strip()
        ]
        mode_list = [
            item.strip()
            for item in str(request.args.get("modes") or "pure,neural").split(",")
            if item.strip()
        ]

        if refresh:
            MacroOptionsHeatmapContextManager.get_instance().service.capture_once(
                force_fair_value=False,
                force_wyrm=False,
                allow_scheduled_wyrm=False,
            )

        result = IntradayCorrelationHistoryService().build_payload(
            underlying_security=underlying,
            lookback_days=lookback_days,
            horizon_minutes=horizon_minutes,
            factors=factor_list,
            modes=mode_list,
            bypass_cache=refresh,
            prefer_persisted=not refresh,
            persist=True,
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/live-capture/workbook-series", methods=["GET"])
def live_capture_workbook_series():
    try:
        from app.services.live_capture_workbook_series_service import (
            LiveCaptureWorkbookSeriesService,
        )
        from app.services.macro_options_heatmap_context_manager import (
            MacroOptionsHeatmapContextManager,
        )

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        securities = _workbook_securities_from_request()
        session_date = (request.args.get("session_date") or "").strip() or None
        session_count = max(1, min(int(request.args.get("session_count", 2)), 10))
        refresh = _is_truthy(request.args.get("refresh"))
        include_recent_state = _is_truthy(request.args.get("include_recent_state"))

        if refresh:
            MacroOptionsHeatmapContextManager.get_instance().service.capture_once(
                force_fair_value=False,
                force_wyrm=False,
                allow_scheduled_wyrm=False,
            )

        multi = LiveCaptureWorkbookSeriesService().read_series_multi(
            underlying_security=underlying,
            securities=securities,
            session_date=session_date,
            session_count=session_count,
            include_recent_state=include_recent_state,
        )
        first_security = securities[0]
        series = multi["series_by_security"].get(first_security) or []
        return jsonify({
            "success": True,
            "data": {
                "underlying_security": multi["underlying_security"],
                "security": first_security,
                "securities": multi["securities"],
                "session_dates": multi["session_dates"],
                "series": series,
                "latest": series[-1] if series else None,
                "series_by_security": multi["series_by_security"],
                "latest_by_security": multi["latest_by_security"],
                "sync": multi["sync"],
            },
            "count": len(series),
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/live-capture/workbook-latest", methods=["GET"])
def live_capture_workbook_latest():
    try:
        from app.services.live_capture_workbook_series_service import (
            LiveCaptureWorkbookSeriesService,
        )
        from app.services.macro_options_heatmap_context_manager import (
            MacroOptionsHeatmapContextManager,
        )

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        securities = _workbook_securities_from_request()
        session_date = (request.args.get("session_date") or "").strip() or None
        refresh = _is_truthy(request.args.get("refresh"))

        if refresh:
            MacroOptionsHeatmapContextManager.get_instance().service.capture_once(
                force_fair_value=False,
                force_wyrm=False,
                allow_scheduled_wyrm=False,
            )

        result = LiveCaptureWorkbookSeriesService().read_latest_multi(
            underlying_security=underlying,
            securities=securities,
            session_date=session_date,
            include_recent_state=True,
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


def _load_legacy_fair_value_payload(underlying: str) -> dict:
    from app.services.options_fair_value_modeling import OptionsFairValueService

    service = OptionsFairValueService()
    result = service.read_latest_run(underlying) or {}
    if not result:
        return {}
    live_overlay_enabled = bool(
        Config.OPTIONS_FAIR_VALUE_LIVE_ENABLE
        or Config.OPTIONS_FAIR_VALUE_EXCEL_BASKET_ENABLE
        or getattr(Config, "MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE", False)
    )
    if live_overlay_enabled:
        try:
            result = dict(result)
            result["live_factor_snapshot"] = service.live_factor_snapshot(underlying, workbook_only=True)
        except Exception:
            logger.exception("Failed to attach legacy fair value live factor snapshot")
    return result


def _fair_value_legs_response(result: dict | None) -> dict:
    summary = dict((result or {}).get("summary") or {})
    core_legs = dict(summary.get("core_legs") or {})
    shadow_legs = dict(summary.get("shadow_legs") or {})
    legs = []
    for leg_type, mapping in (("core", core_legs), ("shadow", shadow_legs)):
        for key, payload in mapping.items():
            leg = dict(payload or {})
            leg["name"] = leg.get("name") or key
            leg["type"] = leg.get("type") or leg_type
            legs.append(leg)
    return {
        "timestamp": summary.get("timestamp") or (result or {}).get("captured_at"),
        "underlying_security": (result or {}).get("underlying_security"),
        "core_legs": core_legs,
        "shadow_legs": shadow_legs,
        "legs": legs,
    }


def _fair_value_quality_response(result: dict | None) -> dict:
    summary = dict((result or {}).get("summary") or {})
    return {
        "timestamp": summary.get("timestamp") or (result or {}).get("captured_at"),
        "underlying_security": (result or {}).get("underlying_security"),
        "core_fair_value_xb1": summary.get("core_fair_value_xb1"),
        "quality_adjusted_fair_value_xb1": summary.get("quality_adjusted_fair_value_xb1"),
        "risk_quality_score": summary.get("risk_quality_score"),
        "implicit_sentiment": summary.get("implicit_sentiment"),
        "sentiment_confidence": summary.get("sentiment_confidence"),
        "confidence": summary.get("confidence"),
        "core_shadow_alignment": summary.get("core_shadow_alignment"),
        "divergence_score": summary.get("divergence_score"),
        "coherence_score": summary.get("coherence_score"),
        "convergence_probability": summary.get("convergence_probability"),
        "regime_break_probability": summary.get("regime_break_probability"),
        "quality_gauge": summary.get("quality_gauge"),
        "quality_ribbon": summary.get("quality_ribbon") or {},
        "explanation": summary.get("explanation") or {},
    }


@app.route("/api/options/fair-value/latest", methods=["GET"])
def fair_value_latest():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        return jsonify({"success": True, "data": _load_legacy_fair_value_payload(underlying)})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/fair-value/legs/latest", methods=["GET"])
def fair_value_legs_latest():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        result = _load_legacy_fair_value_payload(underlying)
        return jsonify({"success": True, "data": _fair_value_legs_response(result)})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/fair-value/quality/latest", methods=["GET"])
def fair_value_quality_latest():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        result = _load_legacy_fair_value_payload(underlying)
        return jsonify({"success": True, "data": _fair_value_quality_response(result)})
    except Exception as exc:
        return _json_error(exc)


def _legacy_regime_payload(underlying: str, refresh: bool = False) -> dict:
    from app.services.options_fair_value_modeling.regime_price_making_service import (
        RegimePriceMakingService,
    )

    service = RegimePriceMakingService()
    if refresh:
        return service.build_latest(underlying, persist=True)
    latest = service.store.read_latest_regime_price_making_run(underlying)
    return latest or service.build_latest(underlying, persist=True)


@app.route("/api/options/fair-value/regime-price-making/latest", methods=["GET"])
def fair_value_regime_price_making_latest():
    try:
        from app.api.regime_price_making_api import build_regime_price_making_response

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        result = _legacy_regime_payload(underlying, refresh=_is_truthy(request.args.get("refresh")))
        return jsonify({"success": True, "data": build_regime_price_making_response(result)})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/fair-value/price-making/latest", methods=["GET"])
def fair_value_price_making_latest():
    try:
        from app.api.regime_price_making_api import build_price_making_response

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        result = _legacy_regime_payload(underlying, refresh=_is_truthy(request.args.get("refresh")))
        return jsonify({"success": True, "data": build_price_making_response(result)})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/fair-value/nonlinear-dependence/latest", methods=["GET"])
def fair_value_nonlinear_dependence_latest():
    try:
        from app.api.regime_price_making_api import build_nonlinear_dependence_response

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        result = _legacy_regime_payload(underlying, refresh=_is_truthy(request.args.get("refresh")))
        return jsonify({"success": True, "data": build_nonlinear_dependence_response(result)})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/fair-value/market-state/latest", methods=["GET"])
def fair_value_market_state_latest():
    try:
        from app.api.regime_price_making_api import build_market_state_response

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        result = _legacy_regime_payload(underlying, refresh=_is_truthy(request.args.get("refresh")))
        return jsonify({"success": True, "data": build_market_state_response(result)})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/fair-value/live-factors", methods=["GET"])
def fair_value_live_factors():
    try:
        from app.services.options_fair_value_modeling import OptionsFairValueService

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        service = OptionsFairValueService()
        return jsonify({"success": True, "data": service.live_factor_snapshot(underlying, workbook_only=True)})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/fair-value/run/<run_id>", methods=["GET"])
def fair_value_run_by_id(run_id: str):
    try:
        from app.services.options_query_service import OptionsQueryService

        result = OptionsQueryService().fair_value_run(run_id)
        if not result:
            return jsonify({"success": False, "error": f"Fair value run not found: {run_id}"}), 404
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/fair-value/run", methods=["POST"])
def fair_value_run():
    try:
        from app.models.task import TaskManager, TaskStatus
        from app.services.options_fair_value_modeling import OptionsFairValueService

        payload = request.get_json(silent=True) or {}
        underlying = payload.get("underlying_security") or "IBOVE Index"
        refresh_options_model = bool(payload.get("refresh_options_model", False))
        refresh_global_overlay = bool(payload.get("refresh_global_overlay", False))
        persist = bool(payload.get("persist", True))
        run_async = bool(payload.get("async", True))
        service = OptionsFairValueService()

        def execute() -> dict:
            return service.run_latest(
                underlying_security=underlying,
                refresh_options_model=refresh_options_model,
                refresh_global_overlay=refresh_global_overlay,
                persist=persist,
            )

        if not run_async:
            return jsonify({"success": True, "data": execute()})

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            "legacy_options_fair_value_run",
            metadata={
                "underlying_security": underlying,
                "refresh_options_model": refresh_options_model,
                "refresh_global_overlay": refresh_global_overlay,
                "persist": persist,
            },
        )

        def run_task() -> None:
            try:
                task_manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=10, message="Running legacy fair value engine")
                result = execute()
                task_manager.update_task(task_id, status=TaskStatus.COMPLETED, progress=100, message="Legacy fair value engine completed", result=result)
            except Exception:
                logger.exception("Legacy fair-value task failed task_id=%s", task_id)
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Legacy fair value engine failed",
                    error="Task execution failed",
                )

        threading.Thread(target=run_task, daemon=True).start()
        return jsonify({"success": True, "data": {"task_id": task_id, "message": "Legacy fair value engine started"}})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/hard-refresh", methods=["POST"])
@require_role("admin")
def hard_refresh_options_base():
    try:
        from app.services.macro_options_heatmap_context_manager import (
            MacroOptionsHeatmapContextManager,
        )

        payload = request.get_json(silent=True) or {}
        underlying = payload.get("underlying_security") or "IBOVE Index"
        state = MacroOptionsHeatmapContextManager.get_instance().service.capture_once(
            force_wyrm=True,
            force_fair_value=True,
            allow_scheduled_wyrm=False,
        )
        collector = dict((state.get("collector") or {}))
        return jsonify({
            "success": True,
            "data": {
                "underlying_security": underlying,
                "collector": collector,
                "context_generated_at": state.get("generated_at"),
                "last_wyrm_run_at": collector.get("last_wyrm_run_at"),
                "last_wyrm_trade_date": collector.get("last_wyrm_trade_date"),
                "last_wyrm_model_run_id": collector.get("last_wyrm_model_run_id"),
                "last_wyrm_global_run_id": collector.get("last_wyrm_global_run_id"),
                "last_wyrm_fair_value_run_id": collector.get("last_wyrm_fair_value_run_id"),
            },
        })
    except Exception as exc:
        return _json_error(exc)


def main() -> None:
    host = os.environ.get("LEGACY_HEATMAP_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("LEGACY_HEATMAP_SERVICE_PORT", "5022"))
    logger.info("Starting aquiles-legacy-heatmap-service on %s:%s", host, port)
    logger.info("Legacy heatmap auto-start disabled by default.")
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
