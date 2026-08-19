"""
Dedicated CVM CDA graph API.

The service reads the structured CDA SQLite store and builds/serves a
deterministic Neo4j graph for Funds Flow Local. It is intentionally separate
from the main Flask backend so graph imports and graph queries do not block
the dashboard API.
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
from app.services.cvm_cda_graph_service import CvmCdaGraphService
from app.utils.logger import get_logger

logger = get_logger("aquiles.cvm_cda_graph_service")

app = Flask(__name__)
if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
    app.json.ensure_ascii = False
CORS(app, resources={r"/api/*": {"origins": "*"}})
register_auth(app)
register_error_handlers(app)

graph_service = CvmCdaGraphService()


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


def _int_value(payload: dict, key: str, default: int) -> int:
    try:
        return int(payload.get(key, request.args.get(key, default)) or default)
    except Exception:
        return default


def _float_value(payload: dict, key: str, default: float) -> float:
    try:
        return float(payload.get(key, request.args.get(key, default)) or default)
    except Exception:
        return default


@app.route("/health", methods=["GET"])
def health():
    try:
        status = graph_service.status()
        return jsonify({
            "status": "ok" if status.get("ok") else "degraded",
            "service": "aquiles-cvm-cda-graph-service",
            "data": status,
        }), 200
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/cda-graph/schema", methods=["GET"])
@app.route("/api/v1/cda-graph/schema", methods=["GET"])
def schema():
    try:
        return jsonify(graph_service.schema())
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/cda-graph/status", methods=["GET"])
@app.route("/api/v1/cda-graph/status", methods=["GET"])
def status():
    try:
        return jsonify(graph_service.status())
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/cda-graph/build", methods=["POST"])
@app.route("/api/v1/cda-graph/build", methods=["POST"])
def build_graph():
    try:
        payload = request.get_json(silent=True) or {}
        result = graph_service.build_graph(
            month=payload.get("month") or request.args.get("month"),
            reset=_bool_arg("reset", False),
            max_funds=_int_value(payload, "max_funds", int(os.environ.get("CVM_CDA_GRAPH_MAX_FUNDS", "350"))),
            max_positions_per_fund=_int_value(
                payload,
                "max_positions_per_fund",
                int(os.environ.get("CVM_CDA_GRAPH_MAX_POSITIONS_PER_FUND", "30")),
            ),
            min_abs_value=_float_value(
                payload,
                "min_abs_value",
                float(os.environ.get("CVM_CDA_GRAPH_MIN_ABS_VALUE", "10000000")),
            ),
            target_funds_per_theme=_int_value(
                payload,
                "target_funds_per_theme",
                int(os.environ.get("CVM_CDA_GRAPH_TARGET_FUNDS_PER_THEME", "60")),
            ),
            dry_run=_bool_arg("dry_run", False),
        )
        return jsonify(result), 200 if result.get("ok") else 400
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/cda-graph/month/<month>", methods=["DELETE"])
@app.route("/api/v1/cda-graph/month/<month>", methods=["DELETE"])
@require_role("admin")
def clear_month(month: str):
    try:
        result = graph_service.clear_month(month)
        return jsonify(result)
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/cda-graph/network", methods=["GET"])
@app.route("/api/v1/cda-graph/network", methods=["GET"])
def network():
    try:
        result = graph_service.network(
            month=request.args.get("month"),
            limit=request.args.get("limit", 180, type=int),
            fund_cnpj=request.args.get("fund_cnpj"),
            issuer=request.args.get("issuer"),
            target=request.args.get("target"),
        )
        return jsonify(result), 200 if result.get("ok") else 404
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/cda-graph/fund/<path:fund_cnpj>/network", methods=["GET"])
@app.route("/api/v1/cda-graph/fund/<path:fund_cnpj>/network", methods=["GET"])
def fund_network(fund_cnpj: str):
    try:
        result = graph_service.fund_network(
            fund_cnpj,
            month=request.args.get("month"),
            limit=request.args.get("limit", 160, type=int),
        )
        return jsonify(result), 200 if result.get("ok") else 404
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/cda-graph/crowding/issuers", methods=["GET"])
@app.route("/api/v1/cda-graph/crowding/issuers", methods=["GET"])
def issuer_crowding():
    try:
        result = graph_service.issuer_crowding(
            month=request.args.get("month"),
            limit=request.args.get("limit", 50, type=int),
        )
        return jsonify(result), 200 if result.get("ok") else 404
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/cda-graph/money-trails", methods=["GET"])
@app.route("/api/v1/cda-graph/money-trails", methods=["GET"])
def money_trails():
    try:
        result = graph_service.money_trails(
            month=request.args.get("month"),
            limit=request.args.get("limit", 20, type=int),
        )
        return jsonify(result), 200 if result.get("ok") else 404
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/cda-graph/bridge-path-detail", methods=["GET"])
@app.route("/api/v1/cda-graph/bridge-path-detail", methods=["GET"])
def bridge_path_detail():
    try:
        result = graph_service.bridge_path_detail(
            month=request.args.get("month"),
            target=request.args.get("target"),
            fund_type=request.args.get("fund_type"),
            limit=request.args.get("limit", 18, type=int),
        )
        return jsonify(result), 200 if result.get("ok") else 400
    except Exception as exc:
        return _json_error(exc)


@app.route("/api/cda-graph/asset-trail-detail", methods=["GET"])
@app.route("/api/v1/cda-graph/asset-trail-detail", methods=["GET"])
def asset_trail_detail():
    try:
        result = graph_service.asset_trail_detail(
            month=request.args.get("month"),
            asset_key=request.args.get("asset_key"),
            asset_class=request.args.get("asset_class"),
            side=request.args.get("side", "coveted"),
            limit=request.args.get("limit", 24, type=int),
        )
        return jsonify(result), 200 if result.get("ok") else 400
    except Exception as exc:
        return _json_error(exc)


def main() -> None:
    host = os.environ.get("CVM_CDA_GRAPH_SERVICE_HOST", "0.0.0.0")
    port = int(os.environ.get("CVM_CDA_GRAPH_SERVICE_PORT", "5017"))
    logger.info("Starting aquiles-cvm-cda-graph-service on %s:%s", host, port)
    logger.info("CDA db: %s | Neo4j: %s | backend=%s", graph_service.cda_db_path, Config.NEO4J_URI, Config.GRAPH_BACKEND)
    serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
