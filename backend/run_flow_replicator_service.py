"""
Dedicated WIN/XB1 participant-flow replicator API.

This service owns the AquantX WebSocket connection, persists participant
summary snapshots into a separate SQLite database, computes per-agent deltas,
and exposes read APIs for Discovery widgets such as the 10P atemporal chart.
"""

from __future__ import annotations

import os
import sys
import time

from flask import Flask, jsonify, request
from flask_cors import CORS

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _load_project_env() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return

    root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if os.path.exists(root_env):
        load_dotenv(root_env, override=True)
    else:
        load_dotenv(override=True)


_load_project_env()

from app.auth import register_auth, require_role
from app.http import error_response, register_error_handlers
from app.server import serve
from app.services.flow_activity_radar_service import FlowActivityRadarService
from app.services.flow_replicator_service import FlowReplicatorService
from app.services.flow_replicator_store import FlowReplicatorStore
from app.utils.logger import get_logger

logger = get_logger("aquiles.flow_replicator_service")

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)

store = FlowReplicatorStore()
replicator = FlowReplicatorService(store=store)
activity_radar = FlowActivityRadarService(store=store)


def _json_error(exc: Exception, status_code: int = 500):
    return error_response(logger, status_code=status_code, exception=exc)


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_epoch(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except Exception:
        return None


@app.route("/health", methods=["GET"])
def health():
    status = replicator.status()
    return {
        "status": "ok",
        "service": "aquiles-flow-replicator-service",
        "running": bool(status.get("running")),
        "connected": bool(status.get("connected")),
        "ticker": status.get("ticker"),
    }


@app.route("/api/flow/replicator/status", methods=["GET"])
def flow_replicator_status():
    try:
        return jsonify({"success": True, "data": replicator.status()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/flow/replicator/start", methods=["POST"])
@require_role("admin")
def flow_replicator_start():
    try:
        return jsonify({"success": True, "data": replicator.start()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/flow/replicator/stop", methods=["POST"])
@require_role("admin")
def flow_replicator_stop():
    try:
        return jsonify({"success": True, "data": replicator.stop()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/flow/summary/latest", methods=["GET"])
def flow_summary_latest():
    try:
        ticker = request.args.get("ticker") or None
        snapshot = store.latest_snapshot(ticker)
        return jsonify({"success": bool(snapshot), "data": snapshot}), 200 if snapshot else 404
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/flow/agents/latest", methods=["GET"])
def flow_agents_latest():
    try:
        ticker = request.args.get("ticker") or None
        limit = int(request.args.get("limit") or 80)
        rows = store.latest_agents(ticker, limit=limit)
        return jsonify({"success": True, "data": {"agents": rows, "count": len(rows)}})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/flow/deltas/aggregate", methods=["GET"])
@app.route("/api/flow/candles/aggregate", methods=["GET"])
def flow_deltas_aggregate():
    try:
        ticker = request.args.get("ticker") or None
        since_epoch = _parse_epoch(request.args.get("since_epoch"))
        until_epoch = _parse_epoch(request.args.get("until_epoch"))
        lookback_seconds = int(request.args.get("lookback_seconds") or 0)
        if since_epoch is None and lookback_seconds > 0:
            since_epoch = time.time() - lookback_seconds
        limit = int(request.args.get("limit") or 80)
        result = store.aggregate_deltas(
            ticker=ticker,
            since_epoch=since_epoch,
            until_epoch=until_epoch,
            limit=limit,
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/flow/deltas/windows", methods=["POST"])
@app.route("/api/flow/candles/windows", methods=["POST"])
def flow_deltas_windows():
    try:
        payload = request.get_json(silent=True) or {}
        raw_windows = payload.get("windows")
        if not isinstance(raw_windows, list):
            return jsonify({"success": False, "error": "windows must be a list"}), 400

        try:
            raw_agent_limit = payload.get("agent_limit")
            agent_limit = 12 if raw_agent_limit is None else int(raw_agent_limit)
        except (TypeError, ValueError):
            agent_limit = 12

        windows = []
        for item in raw_windows:
            if not isinstance(item, dict):
                continue

            start_epoch = _parse_epoch(item.get("start_epoch") or item.get("start"))
            end_epoch = _parse_epoch(item.get("end_epoch") or item.get("end"))
            if start_epoch is None or end_epoch is None or end_epoch <= start_epoch:
                continue

            windows.append({
                "index": item.get("index"),
                "start_epoch": start_epoch,
                "end_epoch": end_epoch,
            })

        result = store.aggregate_delta_windows(
            ticker=payload.get("ticker") or None,
            windows=windows,
            agent_limit=max(0, min(agent_limit, 50)),
        )
        return jsonify({"success": True, "count": len(result), "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/flow/activity-radar", methods=["GET"])
def flow_activity_radar():
    try:
        ticker = request.args.get("ticker") or None
        session_date = request.args.get("session_date") or None
        bucket_minutes = int(request.args.get("bucket_minutes") or 1)
        top_runs = int(request.args.get("top_runs") or 24)
        result = activity_radar.build_dashboard(
            ticker=ticker,
            session_date=session_date,
            bucket_minutes=bucket_minutes,
            top_runs=top_runs,
        )
        return jsonify({"success": bool(result.get("ok")), "data": result})
    except Exception as exc:
        return _json_error(exc)


def main() -> None:
    host = os.environ.get("FLOW_REPLICATOR_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("FLOW_REPLICATOR_SERVICE_PORT", "5020"))
    if _truthy(os.environ.get("FLOW_REPLICATOR_AUTO_START", "false")):
        replicator.start()
    logger.info("Starting aquiles-flow-replicator-service on %s:%s", host, port)
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
