"""
Dedicated ETF daily flow inference API.

The service captures public ETF issuer pages, stores daily NAV/share snapshots,
and infers fund flow from changes in shares outstanding. It is intentionally
separate from the Funds Flow Local dashboard so scraper failures and retries do
not block Discovery.
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

from app.auth import register_auth, require_role
from app.config import Config
from app.http import error_response, register_error_handlers
from app.server import serve
from app.services.etf_daily_flow_service import EtfDailyFlowManager, EtfDailyFlowService
from app.utils.logger import get_logger

logger = get_logger("mirofish.etf_daily_flow_service")

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)

etf_flow_service = EtfDailyFlowService()
etf_flow_manager = EtfDailyFlowManager(etf_flow_service)


def _json_error(exc: Exception, status_code: int = 500):
    return error_response(
        logger,
        status_code=status_code,
        exception=exc,
        extra={"ok": False},
    )


def _bool_arg(name: str, default: bool = False) -> bool:
    value = request.args.get(name)
    if value is None:
        payload = request.get_json(silent=True) or {}
        value = payload.get(name, default)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default) or default)
    except Exception:
        return default


@app.route("/health", methods=["GET"])
def health():
    try:
        data = etf_flow_service.health(manager_status=etf_flow_manager.status())
        return jsonify(
            {
                "status": data.get("status", "degraded"),
                "service": "aquiles-etf-daily-flow-service",
                "data": data,
            }
        ), 200
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/etf-daily-flow/status", methods=["GET"])
@app.route("/api/v1/etf-daily-flow/status", methods=["GET"])
def status():
    try:
        return jsonify(etf_flow_service.health(manager_status=etf_flow_manager.status()))
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/etf-daily-flow/universe", methods=["GET", "POST"])
@app.route("/api/v1/etf-daily-flow/universe", methods=["GET", "POST"])
def universe():
    try:
        if request.method == "GET":
            active = request.args.get("active")
            active_bool = None if active is None else str(active).strip().lower() in {"1", "true", "yes", "on"}
            return jsonify(
                etf_flow_service.list_universe(
                    active=active_bool,
                    provider=request.args.get("provider"),
                    limit=_int_arg("limit", 0) or None,
                )
            )
        payload = request.get_json(silent=True) or {}
        if isinstance(payload.get("funds"), list):
            results = [etf_flow_service.upsert_fund(item) for item in payload["funds"] if isinstance(item, dict)]
            return jsonify({"ok": True, "count": len(results), "results": results})
        return jsonify(etf_flow_service.upsert_fund(payload))
    except Exception as exc:
        return _json_error(exc, status_code=400)


@app.route("/api/etf-daily-flow/collect", methods=["POST"])
@app.route("/api/v1/etf-daily-flow/collect", methods=["POST"])
def collect():
    try:
        payload = request.get_json(silent=True) or {}
        tickers = payload.get("tickers")
        if isinstance(tickers, str):
            tickers = [item.strip() for item in tickers.split(",") if item.strip()]
        elif not isinstance(tickers, list):
            tickers = None
        result = etf_flow_service.collect(
            provider=payload.get("provider") or request.args.get("provider"),
            tickers=tickers,
            force=_bool_arg("force", False),
            limit=int(payload.get("limit") or request.args.get("limit") or 0) or None,
            refresh_universe=_bool_arg("refresh_universe", Config.ETF_DAILY_FLOW_REFRESH_CATALOG_BEFORE_COLLECT),
        )
        return jsonify(result), 200 if result.get("ok") else 400
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/etf-daily-flow/discover", methods=["POST"])
@app.route("/api/v1/etf-daily-flow/discover", methods=["POST"])
def discover():
    try:
        payload = request.get_json(silent=True) or {}
        result = etf_flow_service.discover_provider(
            provider=payload.get("provider") or request.args.get("provider"),
            source_url=payload.get("source_url") or request.args.get("source_url"),
            seed_universe=_bool_arg("seed_universe", True),
            reset_provider=_bool_arg("reset_provider", False),
            max_funds=int(payload.get("max_funds") or request.args.get("max_funds") or 0) or None,
        )
        return jsonify(result), 200 if result.get("ok") else 400
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/etf-daily-flow/observations", methods=["GET"])
@app.route("/api/v1/etf-daily-flow/observations", methods=["GET"])
def observations():
    try:
        return jsonify(
            etf_flow_service.list_observations(
                provider=request.args.get("provider"),
                ticker=request.args.get("ticker"),
                limit=_int_arg("limit", 200),
            )
        )
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/etf-daily-flow/flows", methods=["GET"])
@app.route("/api/v1/etf-daily-flow/flows", methods=["GET"])
def flows():
    try:
        return jsonify(
            etf_flow_service.list_flows(
                provider=request.args.get("provider"),
                ticker=request.args.get("ticker"),
                limit=_int_arg("limit", 200),
            )
        )
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/etf-daily-flow/dashboard", methods=["GET"])
@app.route("/api/v1/etf-daily-flow/dashboard", methods=["GET"])
def dashboard():
    try:
        return jsonify(etf_flow_service.dashboard(top_n=_int_arg("top_n", 20)))
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/etf-daily-flow/runs", methods=["GET"])
@app.route("/api/v1/etf-daily-flow/runs", methods=["GET"])
def runs():
    try:
        return jsonify(etf_flow_service.list_runs(limit=_int_arg("limit", 20)))
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/etf-daily-flow/errors", methods=["GET"])
@app.route("/api/v1/etf-daily-flow/errors", methods=["GET"])
def errors():
    try:
        return jsonify(etf_flow_service.list_errors(limit=_int_arg("limit", 50)))
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/etf-daily-flow/collector/start", methods=["POST"])
@app.route("/api/v1/etf-daily-flow/collector/start", methods=["POST"])
@require_role("admin")
def collector_start():
    try:
        return jsonify(etf_flow_manager.start())
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/etf-daily-flow/collector/stop", methods=["POST"])
@app.route("/api/v1/etf-daily-flow/collector/stop", methods=["POST"])
@require_role("admin")
def collector_stop():
    try:
        return jsonify(etf_flow_manager.stop())
    except Exception as exc:
        return _json_error(exc)


def main() -> None:
    host = os.environ.get("ETF_DAILY_FLOW_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("ETF_DAILY_FLOW_SERVICE_PORT", "5018"))
    logger.info("Starting aquiles-etf-daily-flow-service on %s:%s", host, port)
    logger.info("ETF daily flow db: %s", etf_flow_service.db_path)
    if Config.ETF_DAILY_FLOW_AUTO_START:
        etf_flow_manager.start()
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
