"""
Dedicated options-model read API for Discovery widgets.

This process serves read-heavy model/snapshot/vol-surface endpoints without
blocking the main Flask backend. It keeps the same response contracts as the
legacy /api/options routes and adds small in-process TTL caches.
"""

from __future__ import annotations

import os
import sys

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
from app.http import error_response, register_error_handlers
from app.server import serve
from app.services.options_model_read_service import OptionsModelReadService, _is_truthy
from app.utils.logger import get_logger

logger = get_logger("mirofish.options_model_service")

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)

read_service = OptionsModelReadService()


def _json_error(exc: Exception, status_code: int = 500):
    return error_response(logger, status_code=status_code, exception=exc)


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "service": "aquiles-options-model-service",
    }


@app.route("/api/options/model/latest", methods=["GET"])
def latest_options_model():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        universe_tier = request.args.get("universe_tier")
        compact = _is_truthy(request.args.get("compact", "true"))
        refresh = _is_truthy(request.args.get("refresh"))
        ttl_seconds = 0.0 if refresh else 5.0
        result = read_service.latest_model_run(
            underlying_security=underlying,
            universe_tier=universe_tier,
            compact=compact,
            ttl_seconds=ttl_seconds,
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/snapshot/by-strike", methods=["GET"])
def snapshot_by_strike():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        tier = request.args.get("tier") or "critical"
        refresh = _is_truthy(request.args.get("refresh"))
        result = read_service.snapshot_by_strike(
            underlying_security=underlying,
            tier=tier,
            ttl_seconds=0.0 if refresh else 10.0,
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/b3-oi/latest", methods=["GET"])
def b3_oi_latest():
    try:
        raw_mode = _is_truthy(request.args.get("raw"))
        result = read_service.b3_oi_latest(
            date=request.args.get("date") or None,
            raw=raw_mode,
            ttl_seconds=0.0 if _is_truthy(request.args.get("refresh")) else 60.0,
        )
        if raw_mode:
            return jsonify({
                "success": True,
                "data": result.get("rows", []),
                "date": result.get("date"),
                "count": result.get("count", 0),
            })
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/b3-oi/dates", methods=["GET"])
def b3_oi_dates():
    try:
        return jsonify({"success": True, "data": read_service.b3_oi_dates()})
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/options/vol-surface", methods=["GET"])
def vol_surface():
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        tier = request.args.get("tier") or "all"
        min_dte = int(request.args.get("min_dte") or 1)
        max_dte = int(request.args.get("max_dte") or 120)
        refresh = _is_truthy(request.args.get("refresh"))
        result = read_service.vol_surface(
            underlying_security=underlying,
            tier=tier,
            min_dte=min_dte,
            max_dte=max_dte,
            ttl_seconds=0.0 if refresh else 10.0,
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _json_error(exc)


def main() -> None:
    host = os.environ.get("OPTIONS_MODEL_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("OPTIONS_MODEL_SERVICE_PORT", "5014"))
    logger.info("Starting aquiles-options-model-service on %s:%s", host, port)
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
