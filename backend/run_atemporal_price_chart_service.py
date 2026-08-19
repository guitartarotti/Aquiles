"""
Dedicated Atemporal Price Chart API for Discovery widgets.

The service builds movement-based XB1 candles (for example 10 ticks of 5
points) and indicator bands without tying this experimental chart engine to the
main backend or the broader Discovery market service.
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
from app.services.atemporal_price_chart_service import AtemporalPriceChartService
from app.utils.logger import get_logger

logger = get_logger("aquiles.atemporal_price_chart_service")

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)

atemporal_chart_service = AtemporalPriceChartService()


def _json_error(exc: Exception, status_code: int = 500):
    return error_response(logger, status_code=status_code, exception=exc)


def _build_kwargs(payload: dict) -> dict:
    return {
        "symbol": payload.get("symbol") or payload.get("benchmark_symbol") or "XB1",
        "lookback_minutes": int(payload.get("lookback_minutes") or 10080),
        "tick_size_points": float(payload.get("tick_size_points") or 5.0),
        "ticks_per_candle": int(payload.get("ticks_per_candle") or 10),
        "moving_average_points": int(payload.get("moving_average_points") or 271),
        "implied_vol": payload.get("atm_implied_vol") or payload.get("iv_atm") or payload.get("implied_vol"),
        "max_points": int(payload.get("max_points") or 900),
        "include_partial": bool(payload.get("include_partial", True)),
        "force_refresh": bool(payload.get("force_refresh", False)),
    }


def _trim_chart_tail(result: dict, tail_points: int) -> dict:
    rows = result.get("chart_rows")
    if not isinstance(rows, list) or len(rows) <= tail_points:
        return result
    trimmed = dict(result)
    trimmed_rows = rows[-tail_points:]
    trimmed["chart_rows"] = trimmed_rows
    trimmed["latest"] = trimmed_rows[-1] if trimmed_rows else result.get("latest")
    trimmed["hot_tail_points"] = tail_points
    return trimmed


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "service": "aquiles-atemporal-price-chart-service",
    }


@app.route("/api/macro/atemporal/price-chart", methods=["POST"])
@app.route("/api/discovery/atemporal/price-chart", methods=["POST"])
def atemporal_price_chart():
    try:
        payload = request.get_json(silent=True) or {}
        result = atemporal_chart_service.build_payload(**_build_kwargs(payload))
        return jsonify({
            "success": bool(result.get("ok")),
            "data": result,
        }), 200 if result.get("ok") else 404
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/macro/atemporal/price-chart/latest", methods=["POST"])
@app.route("/api/discovery/atemporal/price-chart/latest", methods=["POST"])
def atemporal_price_chart_latest():
    try:
        payload = request.get_json(silent=True) or {}
        kwargs = _build_kwargs(payload)
        tail_points = max(int(payload.get("tail_points") or 160), 1)
        kwargs["max_points"] = max(
            int(kwargs.get("moving_average_points") or 271) + tail_points + 5,
            tail_points,
        )
        result = atemporal_chart_service.build_payload(**kwargs)
        result = _trim_chart_tail(result, tail_points)
        return jsonify({
            "success": bool(result.get("ok")),
            "data": result,
        }), 200 if result.get("ok") else 404
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/macro/atemporal/price-chart/latest-price", methods=["POST"])
@app.route("/api/discovery/atemporal/price-chart/latest-price", methods=["POST"])
def atemporal_price_chart_latest_price():
    try:
        payload = request.get_json(silent=True) or {}
        result = atemporal_chart_service.latest_price_payload(
            symbol=payload.get("symbol") or payload.get("benchmark_symbol") or "XB1",
        )
        return jsonify({
            "success": bool(result.get("ok")),
            "data": result,
        }), 200 if result.get("ok") else 404
    except Exception as exc:
        return _json_error(exc)


def main() -> None:
    os.environ.setdefault("AQUILES_DISABLE_MARKET_SCREEN_COLLECTOR", "1")
    host = os.environ.get("ATEMPORAL_CHART_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("ATEMPORAL_CHART_SERVICE_PORT", "5019"))
    logger.info("Starting aquiles-atemporal-price-chart-service on %s:%s", host, port)
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
