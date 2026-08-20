"""Dedicated scheduler for CVM, Funds Flow, macro/news, and report collectors."""

from __future__ import annotations

import os
import sys
from functools import wraps
from hmac import compare_digest
from typing import Any, Callable, ParamSpec

from flask import Flask, jsonify, request

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import Config
from app.container import AquilesContainer
from app.http import error_response, register_error_handlers
from app.server import serve
from app.utils.logger import get_logger
from app.workers.collection_scheduler import (
    SCHEDULED_COLLECTORS,
    resume_scheduled_collectors,
)

logger = get_logger("aquiles.collection_scheduler")
dependencies = AquilesContainer.for_collection_scheduler()

app = Flask(__name__)
setattr(app.json, "ensure_ascii", False)
register_error_handlers(app)

P = ParamSpec("P")


def require_internal_service(view: Callable[P, Any]) -> Callable[P, Any]:
    @wraps(view)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> Any:
        expected = str(Config.INTERNAL_SERVICE_TOKEN or "")
        provided = str(request.headers.get("X-Aquiles-Internal-Token") or "")
        if not expected:
            return jsonify({"success": False, "error": "Internal service token is not configured"}), 503
        if not compare_digest(expected, provided):
            return jsonify({"success": False, "error": "Unauthorized internal service"}), 401
        return view(*args, **kwargs)

    return wrapped


def _collector(name: str) -> Any:
    spec = next((item for item in SCHEDULED_COLLECTORS if item.name == name), None)
    if spec is None:
        raise KeyError(name)
    return dependencies.resolve(spec.dependency)


def _command_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TypeError("Collector command must return a mapping")
    return value


def execute_collector_command(
    collector: Any,
    name: str,
    command: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if command == "status":
        return _command_result(collector.status())
    if command == "start":
        if name == "macro":
            return _command_result(
                collector.start(interval_seconds=payload.get("interval_seconds"))
            )
        return _command_result(collector.start())
    if command == "stop":
        return _command_result(collector.stop())
    if command != "collect":
        raise KeyError(command)

    if name == "cvm_cda":
        return _command_result(
            collector.collect_once(
                force=bool(payload.get("force", False)),
                lookback_months=payload.get("lookback_months"),
            )
        )
    if name == "funds_flow":
        return _command_result(
            collector.collect_once(
                force=bool(payload.get("force", True)),
                target_date=payload.get("target_date"),
                period=payload.get("period", "21d"),
                history_days=payload.get("history_days"),
            )
        )
    if name == "report_sources":
        return _command_result(
            collector.collect_once(
                force=bool(payload.get("force", True)),
                lookback_days=payload.get("lookback_days"),
            )
        )
    if name == "macro":
        return _command_result(
            collector.collect_once(
                include_news=bool(payload.get("include_news", True)),
                include_market=bool(payload.get("include_market", True)),
            )
        )
    raise KeyError(name)


@app.get("/health")
def health() -> dict[str, Any]:
    statuses: dict[str, Any] = {}
    for spec in SCHEDULED_COLLECTORS:
        try:
            statuses[spec.name] = _collector(spec.name).status()
        except Exception as exc:
            statuses[spec.name] = {"running": False, "error": type(exc).__name__}
    return {
        "status": "ok",
        "service": "aquiles-collection-scheduler",
        "collectors": statuses,
    }


@app.get("/api/collections/<name>/status")
@require_internal_service
def collector_status(name: str) -> Any:
    try:
        return jsonify({"success": True, "data": _collector(name).status()})
    except KeyError:
        return jsonify({"success": False, "error": "Unknown collector"}), 404
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@app.post("/api/collections/<name>/<command>")
@require_internal_service
def collector_command(name: str, command: str) -> Any:
    try:
        raw_payload = request.get_json(silent=True)
        payload = raw_payload if isinstance(raw_payload, dict) else {}
        result = execute_collector_command(
            _collector(name),
            name,
            command,
            payload,
        )
        return jsonify({"success": True, "data": result})
    except KeyError:
        return jsonify({"success": False, "error": "Unknown collector command"}), 404
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


def main() -> None:
    statuses = resume_scheduled_collectors(dependencies, logger)
    logger.info("Collection scheduler initialized collectors=%s", sorted(statuses))
    serve(
        app,
        host=Config.COLLECTION_SCHEDULER_SERVICE_HOST,
        port=Config.COLLECTION_SCHEDULER_SERVICE_PORT,
    )


if __name__ == "__main__":
    main()
