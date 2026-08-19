"""
Dedicated OptionsVolumeTracker API.

This process owns the automatic volume polling loop and serves volume activity
read endpoints without tying Discovery widgets to the main Flask backend.
"""

from __future__ import annotations

import os
import sys
import threading
from datetime import date

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
from app.services.options_store import OptionsStore
from app.services.options_volume_tracker import OptionsVolumeTracker
from app.utils.logger import get_logger

logger = get_logger("aquiles.options_volume_tracker_service")

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)

store = OptionsStore()
tracker = OptionsVolumeTracker.get_instance()


def _json_error(exc: Exception, status_code: int = 500):
    return error_response(logger, status_code=status_code, exception=exc)


def _resume_tracker_async() -> None:
    try:
        status = tracker.resume_if_needed()
        logger.info(
            "Options volume tracker service active: interval=%ss underlyings=%s tracked_symbols=%s",
            status.get("poll_interval_seconds"),
            status.get("underlyings"),
            status.get("tracked_symbols"),
        )
    except Exception:
        logger.exception("Failed to resume options volume tracker in dedicated service")


def _request_limit(default: int = 500, maximum: int = 5000) -> int:
    try:
        value = int(request.args.get("limit", default))
    except Exception:
        value = default
    return max(1, min(value, maximum))


@app.route("/health", methods=["GET"])
def health():
    try:
        status = tracker.status()
    except Exception:
        status = {}
    return {
        "status": "ok",
        "service": "aquiles-options-volume-tracker-service",
        "tracker_running": bool(status.get("running")),
        "tracked_symbols": status.get("tracked_symbols"),
        "latest_monthly_iv_at": status.get("latest_monthly_iv_at"),
    }


@app.route("/api/options/volume/activity", methods=["GET"])
def volume_activity():
    try:
        session_date = request.args.get("session_date") or None
        symbol = request.args.get("symbol") or None
        underlying = request.args.get("underlying_security") or None
        try:
            lookback = int(request.args.get("lookback_days", Config.OPTIONS_VOLUME_ACTIVITY_LOOKBACK_DAYS))
        except Exception:
            lookback = Config.OPTIONS_VOLUME_ACTIVITY_LOOKBACK_DAYS

        rows = store.read_volume_activity(
            session_date=session_date,
            symbol=symbol,
            underlying_security=underlying if not symbol else None,
            limit=_request_limit(),
            lookback_days=lookback,
        )
        return jsonify({"success": True, "data": rows, "count": len(rows)})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/volume/summary", methods=["GET"])
def volume_activity_summary():
    try:
        session_date = request.args.get("session_date") or date.today().isoformat()
        underlying = request.args.get("underlying_security") or None
        summary = store.volume_activity_summary(
            session_date=session_date,
            underlying_security=underlying,
        )
        return jsonify({"success": True, "data": summary})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/volume/state", methods=["GET"])
def volume_state():
    try:
        state = store.load_volume_state()
        symbol = request.args.get("symbol")
        if symbol:
            state = {key: value for key, value in state.items() if key == symbol}
        return jsonify({"success": True, "data": state, "count": len(state)})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/volume/poll", methods=["POST"])
def volume_poll():
    try:
        body = request.get_json(silent=True) or {}
        underlying = (
            body.get("underlying_security")
            or request.args.get("underlying_security")
            or (Config.OPTIONS_BLOOMBERG_UNDERLYINGS[0] if Config.OPTIONS_BLOOMBERG_UNDERLYINGS else "IBOVE Index")
        )
        result = tracker.poll_once(underlying)
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/volume/poll/all", methods=["POST"])
def volume_poll_all():
    try:
        return jsonify({"success": True, "data": tracker.poll_all_underlyings()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/volume/tracker/status", methods=["GET"])
def volume_tracker_status():
    try:
        return jsonify({"success": True, "data": tracker.status()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/volume/tracker/start", methods=["POST"])
@require_role("admin")
def volume_tracker_start():
    try:
        return jsonify({"success": True, "data": tracker.start()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/volume/tracker/stop", methods=["POST"])
@require_role("admin")
def volume_tracker_stop():
    try:
        return jsonify({"success": True, "data": tracker.stop()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/volume/tracker/backfill", methods=["POST"])
@require_role("admin")
def volume_tracker_backfill():
    try:
        status = tracker.status()
        if not status.get("running"):
            tracker.start()
        result = tracker.backfill_today()
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


def main() -> None:
    host = os.environ.get("OPTIONS_VOLUME_TRACKER_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("OPTIONS_VOLUME_TRACKER_SERVICE_PORT", "5015"))
    logger.info("Starting aquiles-options-volume-tracker-service on %s:%s", host, port)
    threading.Thread(
        target=_resume_tracker_async,
        daemon=True,
        name="options-volume-tracker-service-resume",
    ).start()
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
