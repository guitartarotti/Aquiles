from __future__ import annotations

import logging

from flask import jsonify, request

from ..auth import require_role
from ..container import get_container
from ..http import error_response
from . import cvm_cda_bp

logger = logging.getLogger(__name__)


def _service():
    return get_container().cvm_cda_service()


def _manager():
    return get_container().cvm_cda_manager()


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


def _optional_int(value, default: int | None = None) -> int | None:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


@cvm_cda_bp.route("/dashboard", methods=["GET"])
def cvm_cda_dashboard():
    try:
        payload = _service().get_dashboard(month=request.args.get("month") or "latest")
        payload["collector"] = _manager().status()
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/analytics/funds", methods=["GET"])
def cvm_cda_funds():
    try:
        return jsonify(
            _service().list_funds(
                month=request.args.get("month") or "latest",
                target=request.args.get("target") or "foreign",
                side=request.args.get("side") or "long",
                page=_int_arg("page", 1),
                per_page=_int_arg("per_page", 25),
            )
        )
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/analytics/assets", methods=["GET"])
def cvm_cda_assets():
    try:
        return jsonify(
            _service().list_assets(
                month=request.args.get("month") or "latest",
                target=request.args.get("target") or "foreign",
                side=request.args.get("side") or "long",
                page=_int_arg("page", 1),
                per_page=_int_arg("per_page", 25),
            )
        )
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/analytics/fund-holdings/<path:fund_cnpj>", methods=["GET"])
def cvm_cda_fund_holdings(fund_cnpj):
    try:
        return jsonify(
            _service().list_fund_holdings(
                fund_cnpj=fund_cnpj,
                month=request.args.get("month") or "latest",
                target=request.args.get("target") or "foreign",
                side=request.args.get("side") or "all",
                page=_int_arg("page", 1),
                per_page=_int_arg("per_page", 40),
            )
        )
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/analytics/positioning", methods=["GET"])
def cvm_cda_positioning():
    try:
        return jsonify(
            _service().get_positioning_lab(
                month=request.args.get("month") or "latest",
            )
        )
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/analytics/radar", methods=["GET"])
def cvm_cda_radar():
    try:
        return jsonify(
            _service().get_redemption_radar(
                month=request.args.get("month") or "latest",
                force=_truthy(request.args.get("force", False)),
            )
        )
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/status", methods=["GET"])
def cvm_cda_status():
    try:
        return jsonify(_service().status())
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/remote", methods=["GET"])
def cvm_cda_remote():
    try:
        return jsonify(
            _service().discover_remote_months(force=_truthy(request.args.get("force", False)))
        )
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/ingest", methods=["POST"])
def cvm_cda_ingest():
    try:
        payload = request.get_json(silent=True) or {}
        lookback = payload.get("lookback_months")
        try:
            lookback_months = int(lookback) if lookback is not None else 1
        except (TypeError, ValueError):
            lookback_months = 1
        month = payload.get("month")
        if month and str(month).lower() != "latest":
            result = _service().ingest_month(
                month=str(month),
                force=_truthy(payload.get("force", True)),
            )
        else:
            result = _service().ingest_latest(
                force=_truthy(payload.get("force", True)),
                lookback_months=lookback_months,
            )
        result["collector"] = _manager().status()
        return jsonify(result)
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/collect", methods=["POST"])
def cvm_cda_collect():
    try:
        payload = request.get_json(silent=True) or {}
        result = _manager().collect_once(
            force=_truthy(payload.get("force", False)),
            lookback_months=_optional_int(payload.get("lookback_months")),
        )
        result["collector"] = _manager().status()
        return jsonify(result)
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/collector/start", methods=["POST"])
@require_role("admin")
def cvm_cda_collector_start():
    try:
        return jsonify(_manager().start())
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})


@cvm_cda_bp.route("/collector/stop", methods=["POST"])
@require_role("admin")
def cvm_cda_collector_stop():
    try:
        return jsonify(_manager().stop())
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={"ok": False})
