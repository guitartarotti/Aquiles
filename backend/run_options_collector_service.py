"""
Dedicated OptionsCollectorManager worker/API.

This process owns scheduled options snapshots, B3 OI collection, and scheduled
model runs. The main Flask backend can stay API-only and delegate collector
commands here through the existing /api/options endpoints.
"""

from __future__ import annotations

import os
import sys

from flask import Flask, jsonify, request
from flask_cors import CORS

os.environ.pop("AQUILES_DISABLE_OPTIONS_COLLECTOR", None)

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
from app.models.task import TaskManager, TaskStatus
from app.server import serve
from app.services.options_collector_manager import OptionsCollectorManager
from app.utils.logger import get_logger

logger = get_logger("mirofish.options_collector_service")

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)

collector = OptionsCollectorManager.get_instance()


def _json_error(exc: Exception, status_code: int = 500):
    return error_response(logger, status_code=status_code, exception=exc)


def _run_async_task(task_type: str, metadata: dict, message: str, completed_message: str, fn):
    task_manager = TaskManager()
    task_id = task_manager.create_task(task_type, metadata=metadata)

    def runner() -> None:
        try:
            task_manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=10,
                message=message,
            )
            result = fn()
            task_manager.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message=completed_message,
                result=result,
            )
        except Exception:
            logger.exception("Options collector task failed task_id=%s", task_id)
            task_manager.update_task(
                task_id,
                status=TaskStatus.FAILED,
                message=f"{message} failed",
                error="Task execution failed",
            )

    import threading

    threading.Thread(target=runner, daemon=True).start()
    return jsonify({"success": True, "data": {"task_id": task_id, "message": message}})


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "service": "aquiles-options-collector-service",
        "collector": collector.status(),
    }


@app.route("/api/options/collector/status", methods=["GET"])
def options_collector_status():
    try:
        return jsonify({"success": True, "data": collector.status()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/collector/start", methods=["POST"])
@require_role("admin")
def start_options_collector():
    try:
        return jsonify({"success": True, "data": collector.start()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/collector/stop", methods=["POST"])
@require_role("admin")
def stop_options_collector():
    try:
        return jsonify({"success": True, "data": collector.stop()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/collect", methods=["POST"])
def collect_options_once():
    try:
        payload = request.get_json(silent=True) or {}
        include_structural = bool(payload.get("include_structural", True))
        include_liquid = bool(payload.get("include_liquid", True))
        include_critical = bool(payload.get("include_critical", True))
        include_ticks = payload.get("include_ticks")
        run_async = bool(payload.get("async", True))

        def execute():
            return collector.collect_once(
                include_structural=include_structural,
                include_liquid=include_liquid,
                include_critical=include_critical,
                include_ticks=include_ticks,
            )

        if not run_async:
            return jsonify({"success": True, "data": execute()})

        return _run_async_task(
            "options_collect",
            metadata={
                "include_structural": include_structural,
                "include_liquid": include_liquid,
                "include_critical": include_critical,
                "include_ticks": include_ticks,
            },
            message="Collecting options snapshots",
            completed_message="Options collection completed",
            fn=execute,
        )
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/history/update", methods=["POST"])
def update_options_history():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = payload.get("underlying_security") or "IBOVE Index"
        trade_date = payload.get("trade_date")
        max_contracts = payload.get("max_contracts")
        force = bool(payload.get("force", False))
        result = collector.update_daily_history_once(
            underlying,
            trade_date=trade_date,
            max_contracts=max_contracts,
            force=force,
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/jobs/<task_id>", methods=["GET"])
def get_options_task(task_id: str):
    task = TaskManager().get_task(task_id)
    if not task:
        return jsonify({"success": False, "error": f"Task not found: {task_id}"}), 404
    return jsonify({"success": True, "data": task.to_dict()})


def main() -> None:
    status = collector.resume_if_needed()
    logger.info(
        "Starting aquiles-options-collector-service on %s:%s running=%s desired=%s",
        Config.OPTIONS_COLLECTOR_SERVICE_HOST,
        Config.OPTIONS_COLLECTOR_SERVICE_PORT,
        status.get("running"),
        status.get("desired_running"),
    )
    serve(
        app,
        host=Config.OPTIONS_COLLECTOR_SERVICE_HOST,
        port=Config.OPTIONS_COLLECTOR_SERVICE_PORT,
    )


if __name__ == "__main__":
    main()
