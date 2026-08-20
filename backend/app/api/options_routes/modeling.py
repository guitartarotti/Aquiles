import threading

from flask import jsonify, request

from ...auth import require_role
from ...config import Config
from ...http import error_response
from ...models.task import TaskManager, TaskStatus
from ...services.options_context_chat_service import OptionsContextChatService
from ...services.options_global_modeling import OptionsGlobalTriangulationService
from ...services.options_modeling import OptionsModelingService
from ...services.options_query_service import OptionsQueryService
from ...services.options_snapshot_service import OptionsSnapshotService
from .. import options_bp
from ..legacy_heatmap_proxy import legacy_heatmap_proxy_or_disabled
from .shared import _compact_model_run, _is_truthy, logger


@options_bp.route("/model/latest", methods=["GET"])
def get_latest_options_model_run():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        universe_tier = request.args.get("universe_tier")
        compact = _is_truthy(request.args.get("compact"))
        query = OptionsQueryService()
        result = query.latest_model_run(underlying, universe_tier=universe_tier)
        if compact:
            result = _compact_model_run(result)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/model/run/<run_id>", methods=["GET"])
def get_options_model_run(run_id: str):
    try:
        compact = _is_truthy(request.args.get("compact"))
        query = OptionsQueryService()
        result = query.model_run(run_id)
        if not result:
            return jsonify({"success": False, "error": f"Model run not found: {run_id}"}), 404
        if compact:
            result = _compact_model_run(result)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/global/latest", methods=["GET"])
def get_latest_options_global_run():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        query = OptionsQueryService()
        result = query.latest_global_run(underlying)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/global/run/<run_id>", methods=["GET"])
def get_options_global_run(run_id: str):
    try:
        query = OptionsQueryService()
        result = query.global_run(run_id)
        if not result:
            return jsonify({"success": False, "error": f"Global run not found: {run_id}"}), 404
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/fair-value/latest", methods=["GET"])
def get_latest_options_fair_value_run():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/latest",
        feature="Legacy Options Dashboard fair value",
        timeout=90.0,
    )


@options_bp.route("/fair-value/legs/latest", methods=["GET"])
def get_latest_options_fair_value_legs():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/legs/latest",
        feature="Legacy Options Dashboard fair value legs",
        timeout=90.0,
    )


@options_bp.route("/fair-value/quality/latest", methods=["GET"])
def get_latest_options_fair_value_quality():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/quality/latest",
        feature="Legacy Options Dashboard fair value quality",
        timeout=90.0,
    )


@options_bp.route("/intraday-dependency/latest", methods=["GET"])
def get_latest_intraday_dependency():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/intraday-dependency/latest",
        feature="Legacy intraday dependency",
        timeout=60.0,
    )


@options_bp.route("/intraday-neural/latest", methods=["GET"])
def get_latest_intraday_neural():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/intraday-neural/latest",
        feature="Legacy intraday neural",
        timeout=60.0,
    )


@options_bp.route("/intraday-correlation-history/latest", methods=["GET"])
def get_latest_intraday_correlation_history():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/intraday-correlation-history/latest",
        feature="Legacy intraday correlation history",
        timeout=90.0,
    )


@options_bp.route("/fair-value/regime-price-making/latest", methods=["GET"])
def get_latest_regime_price_making():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/regime-price-making/latest",
        feature="Legacy Options Dashboard regime price making",
        timeout=90.0,
    )


@options_bp.route("/fair-value/price-making/latest", methods=["GET"])
def get_latest_price_making():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/price-making/latest",
        feature="Legacy Options Dashboard price making",
        timeout=90.0,
    )


@options_bp.route("/fair-value/nonlinear-dependence/latest", methods=["GET"])
def get_latest_nonlinear_dependence():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/nonlinear-dependence/latest",
        feature="Legacy Options Dashboard nonlinear dependence",
        timeout=90.0,
    )


@options_bp.route("/fair-value/market-state/latest", methods=["GET"])
def get_latest_market_state():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/market-state/latest",
        feature="Legacy Options Dashboard market state",
        timeout=90.0,
    )


@options_bp.route("/fair-value/live-factors", methods=["GET"])
def get_live_options_fair_value_factors():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/live-factors",
        feature="Legacy Options Dashboard live fair value factors",
        timeout=90.0,
    )


@options_bp.route("/heatmap-context/latest", methods=["GET"])
def get_latest_options_heatmap_context():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/heatmap-context/latest",
        feature="Legacy options heatmap context",
        timeout=60.0,
    )


@options_bp.route("/live-capture/workbook-series", methods=["GET"])
def get_live_capture_workbook_series():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/live-capture/workbook-series",
        feature="Legacy live-capture workbook series",
        timeout=60.0,
    )


@options_bp.route("/live-capture/workbook-latest", methods=["GET"])
def get_live_capture_workbook_latest():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/live-capture/workbook-latest",
        feature="Legacy live-capture workbook latest",
        timeout=60.0,
    )


@options_bp.route("/fair-value/run/<run_id>", methods=["GET"])
def get_options_fair_value_run(run_id: str):
    return legacy_heatmap_proxy_or_disabled(
        f"/api/options/fair-value/run/{run_id}",
        feature="Legacy Options Dashboard fair value run",
        timeout=90.0,
    )


@options_bp.route("/chat", methods=["GET"])
def get_options_chat_thread():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        sign_convention = request.args.get("sign_convention") or "neutral"
        trade_date = request.args.get("trade_date")
        service = OptionsContextChatService()
        result = service.get_thread(
            underlying_security=underlying,
            sign_convention=sign_convention,
            trade_date=trade_date,
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/chat/message", methods=["POST"])
def send_options_chat_message():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = payload.get("underlying_security") or "IBOVE Index"
        sign_convention = payload.get("sign_convention") or "neutral"
        run_id = payload.get("run_id")
        message = payload.get("message")
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


@options_bp.route("/model/run", methods=["POST"])
def run_options_model():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = payload.get("underlying_security") or "IBOVE Index"
        universe_tier = payload.get("universe_tier")
        sign_convention = payload.get("sign_convention")
        session_date = payload.get("session_date")
        batch_key = payload.get("batch_key")
        persist = bool(payload.get("persist", True))
        run_async = bool(payload.get("async", True))
        compact = _is_truthy(payload.get("compact"))
        refresh_snapshot = bool(payload.get("refresh_snapshot", True))
        service = OptionsModelingService()
        snapshot_service = OptionsSnapshotService()

        def execute() -> dict:
            from ...services.b3_oi_service import B3OIService  # noqa: PLC0415

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
                tier = (
                    str(universe_tier or Config.OPTIONS_MODEL_DEFAULT_TIER or "critical")
                    .strip()
                    .lower()
                )
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
                    result.setdefault("diagnostics", {})["b3_oi_trade_date"] = (
                        resolved_oi_trade_date
                    )
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
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=10,
                    message="Running options quantitative model",
                )
                result = execute()
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    message="Options model completed",
                    result=result,
                )
            except Exception as exc:
                logger.exception("options model task failed", exc_info=exc)
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Options model failed",
                    error="Internal server error",
                )

        threading.Thread(target=run_model_task, daemon=True).start()
        return jsonify(
            {"success": True, "data": {"task_id": task_id, "message": "Options model started"}}
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/global/run", methods=["POST"])
def run_options_global_model():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = payload.get("underlying_security") or "IBOVE Index"
        refresh_local_model = bool(payload.get("refresh_local_model", False))
        persist = bool(payload.get("persist", True))
        run_async = bool(payload.get("async", True))
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
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=10,
                    message="Running global triangulation overlay",
                )
                result = execute()
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    message="Global triangulation completed",
                    result=result,
                )
            except Exception as exc:
                logger.exception("global triangulation task failed", exc_info=exc)
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Global triangulation failed",
                    error="Internal server error",
                )

        threading.Thread(target=run_global_task, daemon=True).start()
        return jsonify(
            {
                "success": True,
                "data": {"task_id": task_id, "message": "Global triangulation started"},
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/fair-value/run", methods=["POST"])
def run_options_fair_value_model():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/fair-value/run",
        feature="Legacy Options Dashboard fair value engine",
        timeout=180.0,
    )


@options_bp.route("/hard-refresh", methods=["POST"])
@require_role("admin")
def hard_refresh_options_base():
    return legacy_heatmap_proxy_or_disabled(
        "/api/options/hard-refresh",
        feature="Legacy options heatmap hard refresh",
        timeout=180.0,
    )
