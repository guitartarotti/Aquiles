"""
Dedicated Fair Value Markov-regime API for Discovery widgets.

This service consumes the Fair Value Legs chart payload and exposes a robust
sticky Student-t Markov-regime model without blocking the main Flask backend or
the Discovery market-data service.
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
from app.services.fair_value_markov_regime_service import FairValueMarkovRegimeService
from app.utils.logger import get_logger

logger = get_logger("mirofish.fair_value_markov_regime_service")

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)

markov_regime_service = FairValueMarkovRegimeService()


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_error(exc: Exception, status_code: int = 500):
    return error_response(logger, status_code=status_code, exception=exc)


def _build_kwargs(payload: dict) -> dict:
    config = payload.get("config") if isinstance(payload.get("config"), dict) else {}
    regime_mode = str(payload.get("regime_mode") or "smart").strip().lower()
    return {
        "config": config if isinstance(config, dict) else {},
        "sessions": int(payload.get("sessions") or 5),
        "bar_minutes": int(payload.get("bar_minutes") or 5),
        "session_start": str(payload.get("session_start") or "09:00"),
        "session_end": str(payload.get("session_end") or "18:30"),
        "rolling_window_points": int(payload.get("rolling_window_points") or 60),
        "vol_context": payload.get("vol_context") if isinstance(payload.get("vol_context"), dict) else None,
        "regime_mode": regime_mode,
        "target_session_date": str(payload.get("target_session_date") or "").strip() or None,
    }


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "service": "aquiles-fair-value-markov-regime-service",
    }


@app.route("/api/macro/fair-value/markov-regime", methods=["POST"])
@app.route("/api/discovery/fair-value/markov-regime", methods=["POST"])
def fair_value_markov_regime():
    try:
        payload = request.get_json(silent=True) or {}
        result = markov_regime_service.build_payload(
            **_build_kwargs(payload),
            force_refresh=_is_truthy(payload.get("force_refresh")),
        )
        return jsonify({
            "success": bool(result.get("ok")),
            "data": result,
        }), 200
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/macro/fair-value/markov-regime/latest", methods=["POST"])
@app.route("/api/discovery/fair-value/markov-regime/latest", methods=["POST"])
def fair_value_markov_regime_latest():
    try:
        payload = request.get_json(silent=True) or {}
        result = markov_regime_service.build_latest_payload(**_build_kwargs(payload))
        return jsonify({
            "success": bool(result.get("ok")),
            "data": result,
        }), 200
    except Exception as exc:
        return _json_error(exc)


def main() -> None:
    os.environ.setdefault("AQUILES_DISABLE_MARKET_SCREEN_COLLECTOR", "1")
    host = os.environ.get("FAIR_VALUE_MARKOV_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("FAIR_VALUE_MARKOV_SERVICE_PORT", "5016"))
    logger.info("Starting aquiles-fair-value-markov-regime-service on %s:%s", host, port)
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
