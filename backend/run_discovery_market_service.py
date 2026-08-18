"""
Dedicated Discovery market-data API.

The XB1 Gamma, Fair Value and Curve Discovery widgets call this process. The
service reads the hot latest capture and cold SQLite history written by
run_market_screen_collector.py; it does not capture the screen itself.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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
from app.services.fair_value_legs_chart_service import FairValueLegsChartService
from app.services.macro_curve_discovery_service import MacroCurveDiscoveryService
from app.services.market_screen_capture_service import MarketScreenCaptureService
from app.services.market_screen_chart_service import MarketScreenChartService
from app.utils.logger import get_logger

logger = get_logger("mirofish.discovery_market_service")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)

market_screen_chart_service = MarketScreenChartService()
fair_value_legs_chart_service = FairValueLegsChartService(chart_service=market_screen_chart_service)
macro_curve_discovery_service = MacroCurveDiscoveryService(chart_service=market_screen_chart_service)


def _is_truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_error(exc: Exception, status_code: int = 500):
    return error_response(logger, status_code=status_code, exception=exc)


def _latest_capture_payload() -> dict | None:
    service = MarketScreenCaptureService()
    return service.read_latest_capture()


def _curve_keys_from_request() -> list[str]:
    values = request.args.getlist("curve")
    raw_curves = request.args.get("curves")
    if raw_curves:
        values.extend([item.strip() for item in raw_curves.split(",") if item.strip()])
    return values


@app.route("/health", methods=["GET"])
def health():
    latest = _latest_capture_payload() or {}
    return {
        "status": "ok",
        "service": "aquiles-discovery-service",
        "latest_capture_id": latest.get("capture_id"),
        "latest_captured_at": latest.get("captured_at"),
        "latest_row_count": latest.get("row_count"),
    }


@app.route("/api/macro/screen-capture/w32-basica/latest", methods=["GET"])
@app.route("/api/discovery/xb1/latest-capture", methods=["GET"])
def latest_w32_basica_screen_capture():
    try:
        result = _latest_capture_payload()
        if not result:
            return jsonify({
                "success": False,
                "error": "No market screen capture available yet.",
            }), 404
        return jsonify({
            "success": True,
            "data": result,
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/macro/screen-capture/w32-basica/latest-symbol", methods=["GET"])
@app.route("/api/discovery/xb1/latest-symbol", methods=["GET"])
def latest_w32_basica_symbol():
    try:
        requested_symbol = request.args.get("symbol") or "XB1"
        resolved_symbol = (
            market_screen_chart_service._resolve_symbol(requested_symbol)
            or str(requested_symbol).strip()
        )
        payload = _latest_capture_payload()
        if not payload:
            return jsonify({
                "success": False,
                "error": "No market screen capture available yet.",
            }), 404

        row_match = None
        for row in payload.get("rows") or []:
            row_symbol = market_screen_chart_service._resolve_symbol(
                (row or {}).get("symbol_normalized")
                or (row or {}).get("symbol")
                or (row or {}).get("symbol_raw")
            )
            if row_symbol == resolved_symbol:
                row_match = row
                break

        if not row_match:
            return jsonify({
                "success": False,
                "error": f"Symbol not available in latest capture: {resolved_symbol}",
            }), 404

        return jsonify({
            "success": True,
            "data": {
                "symbol": resolved_symbol,
                "captured_at": payload.get("captured_at"),
                "capture_id": payload.get("capture_id"),
                "price": row_match.get("price"),
                "daily_change_pct": row_match.get("daily_change_pct"),
                "source": "discovery_latest_symbol",
            },
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/macro/screen-capture/w32-basica/benchmark-candles", methods=["GET"])
@app.route("/api/discovery/xb1/benchmark-candles", methods=["GET"])
def w32_basica_benchmark_candles():
    try:
        requested_symbol = request.args.get("symbol") or request.args.get("benchmark_symbol") or "XB1"
        resolved_symbol = (
            market_screen_chart_service._resolve_symbol(requested_symbol)
            or str(requested_symbol).strip()
        )
        bar_minutes = max(int(request.args.get("bar_minutes") or 5), 1)
        lookback_minutes = max(int(request.args.get("lookback_minutes") or 10080), 1)
        max_points = max(int(request.args.get("max_points") or 360), 1)
        cutoff_epoch = time.time() - (lookback_minutes * 60)
        since_bucket_epoch = float(int(cutoff_epoch // (bar_minutes * 60)) * (bar_minutes * 60))

        db_path = market_screen_chart_service.history_store.db_path
        with sqlite3.connect(db_path, timeout=2.0) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA query_only=ON")
            rows = conn.execute(
                """
                SELECT
                    symbol,
                    bar_minutes,
                    bucket_epoch,
                    bucket_at,
                    open,
                    high,
                    low,
                    close,
                    first_capture_at_epoch,
                    last_capture_at_epoch,
                    daily_change_pct,
                    sample_count
                FROM market_screen_candles
                WHERE symbol = ?
                    AND bar_minutes = ?
                    AND bucket_epoch >= ?
                ORDER BY bucket_epoch ASC
                """,
                (resolved_symbol, bar_minutes, since_bucket_epoch),
            ).fetchall()

        candles = []
        latest_capture_epoch = None
        for row in rows:
            bucket_epoch = float(row["bucket_epoch"] or 0)
            local_bucket = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc).astimezone(LOCAL_TZ)
            local_minutes = (local_bucket.hour * 60) + local_bucket.minute
            if local_minutes < 9 * 60 or local_minutes > 18 * 60:
                continue
            last_capture = row["last_capture_at_epoch"]
            if last_capture is not None:
                latest_capture_epoch = max(float(last_capture), latest_capture_epoch or float(last_capture))
            candles.append({
                "timestamp": row["bucket_at"],
                "timestamp_ms": int(bucket_epoch * 1000),
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "price": row["close"],
                "daily_change_pct": row["daily_change_pct"],
                "sample_count": int(row["sample_count"] or 0),
                "bar_minutes": bar_minutes,
            })

        candles = MarketScreenChartService._downsample_points(candles, max_points)
        latest_capture_at = (
            datetime.fromtimestamp(latest_capture_epoch, tz=timezone.utc).isoformat()
            if latest_capture_epoch is not None
            else None
        )
        payload = {
            "ok": bool(candles),
            "status": "ready" if candles else "no_history",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "discovery_sqlite_benchmark_candles",
            "latest_capture_at": latest_capture_at,
            "benchmark_symbol": resolved_symbol,
            "selected_symbol": resolved_symbol,
            "bar_minutes": bar_minutes,
            "lookback_minutes": lookback_minutes,
            "max_points": max_points,
            "series": {
                "price_points": [],
                "pearson_points": [],
                "benchmark_points": [],
                "benchmark_candles": candles,
            },
        }
        return jsonify({
            "success": bool(payload.get("ok")),
            "data": payload,
        }), 200 if payload.get("ok") else 404
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/macro/curves/discovery", methods=["GET"])
@app.route("/api/discovery/curves/discovery", methods=["GET"])
def macro_curves_discovery_payload():
    try:
        result = macro_curve_discovery_service.build_payload(
            curves=_curve_keys_from_request(),
            lookback_minutes=int(request.args.get("lookback_minutes", 720)),
            max_points=int(request.args.get("max_points", 720)),
            include_shape_points=_is_truthy(request.args.get("include_shape_points", "true")),
            session_date=request.args.get("session_date") or None,
        )
        return jsonify({
            "success": True,
            "data": result,
        })
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/macro/curves/discovery/ai", methods=["POST"])
@app.route("/api/discovery/curves/discovery/ai", methods=["POST"])
def macro_curves_discovery_ai():
    try:
        payload = request.get_json(silent=True) or {}
        raw_curves = payload.get("curves")
        if isinstance(raw_curves, str):
            curves = [item.strip() for item in raw_curves.split(",") if item.strip()]
        elif isinstance(raw_curves, list):
            curves = [str(item).strip() for item in raw_curves if str(item).strip()]
        else:
            curves = []

        result = macro_curve_discovery_service.build_ai_view(
            curves=curves,
            lookback_minutes=int(payload.get("lookback_minutes") or 720),
            session_date=payload.get("session_date") or None,
        )
        return jsonify({
            "success": True,
            "data": result,
        })
    except Exception as exc:
        return _json_error(exc)


def _fair_value_build_kwargs(payload: dict) -> dict:
    return {
        "config": payload.get("config") if isinstance(payload.get("config"), dict) else payload,
        "sessions": int(payload.get("sessions") or 3),
        "bar_minutes": int(payload.get("bar_minutes") or 5),
        "session_start": str(payload.get("session_start") or "09:00"),
        "session_end": str(payload.get("session_end") or "18:30"),
        "rolling_window_points": int(payload.get("rolling_window_points") or 60),
        "vol_context": payload.get("vol_context") if isinstance(payload.get("vol_context"), dict) else None,
    }


@app.route("/api/macro/fair-value/legs-chart", methods=["POST"])
@app.route("/api/discovery/fair-value/legs-chart", methods=["POST"])
def macro_fair_value_legs_chart():
    try:
        payload = request.get_json(silent=True) or {}
        build_kwargs = _fair_value_build_kwargs(payload)
        config_payload = build_kwargs.get("config") if isinstance(build_kwargs.get("config"), dict) else {}
        is_default_composition = not bool((config_payload or {}).get("legs"))
        min_history_timestamp = None
        if is_default_composition and not _is_truthy(payload.get("force_refresh")):
            snapshot = fair_value_legs_chart_service._load_payload_snapshot()
            if snapshot is not None:
                snapshot_covers_latest = fair_value_legs_chart_service.payload_covers_latest_available_session(
                    snapshot,
                    sessions=build_kwargs["sessions"],
                )
                snapshot_last_timestamp = fair_value_legs_chart_service.payload_last_timestamp_ms(snapshot)
                latest_probe = fair_value_legs_chart_service.build_latest_payload(**build_kwargs)
                latest_timestamp = fair_value_legs_chart_service.payload_last_timestamp_ms(latest_probe)
                interval_ms = max(int(build_kwargs["bar_minutes"] or 5), 1) * 60_000
                if latest_timestamp is not None:
                    min_history_timestamp = max(int(latest_timestamp) - interval_ms, 0)
                snapshot_covers_latest_timestamp = (
                    min_history_timestamp is None
                    or (
                        snapshot_last_timestamp is not None
                        and snapshot_last_timestamp >= min_history_timestamp
                    )
                )
                if not snapshot_covers_latest:
                    fair_value_legs_chart_service.refresh_snapshot_async(
                        **build_kwargs,
                        min_timestamp_ms=min_history_timestamp,
                    )
                    snapshot["snapshot_refresh_pending"] = True
                    snapshot["snapshot_refresh_reason"] = "session"
                    return jsonify({
                        "success": True,
                        "data": snapshot,
                    }), 200
                if snapshot_covers_latest_timestamp:
                    return jsonify({
                        "success": True,
                        "data": snapshot,
                    }), 200
                fair_value_legs_chart_service.refresh_snapshot_async(
                    **build_kwargs,
                    min_timestamp_ms=min_history_timestamp,
                )
                snapshot["snapshot_refresh_pending"] = True
                snapshot["snapshot_refresh_reason"] = "timestamp"
                return jsonify({
                    "success": True,
                    "data": snapshot,
                }), 200

        result = fair_value_legs_chart_service.build_payload(
            **build_kwargs,
            min_timestamp_ms=min_history_timestamp,
        )
        return jsonify({
            "success": bool(result.get("ok")),
            "data": result,
        }), 200 if result.get("ok") else 404
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/macro/fair-value/legs-chart/latest", methods=["POST"])
@app.route("/api/discovery/fair-value/legs-chart/latest", methods=["POST"])
def macro_fair_value_legs_chart_latest():
    try:
        payload = request.get_json(silent=True) or {}
        result = fair_value_legs_chart_service.build_latest_payload(**_fair_value_build_kwargs(payload))
        return jsonify({
            "success": bool(result.get("ok")),
            "data": result,
        }), 200 if result.get("ok") else 404
    except Exception as exc:
        return _json_error(exc)


def main() -> None:
    os.environ.setdefault("AQUILES_DISABLE_MARKET_SCREEN_COLLECTOR", "1")
    host = os.environ.get("DISCOVERY_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("DISCOVERY_SERVICE_PORT", "5012"))
    logger.info("Starting aquiles-discovery-service on %s:%s", host, port)
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
