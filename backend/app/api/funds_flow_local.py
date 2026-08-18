"""
Funds Flow Local API.
"""

from __future__ import annotations

import logging

from flask import jsonify, request

from ..auth import require_role
from ..http import error_response
from ..services.funds_flow_local_manager import FundsFlowLocalManager
from ..services.funds_flow_local_service import FundsFlowLocalService
from . import funds_flow_local_bp

funds_flow_local_service = FundsFlowLocalService()
logger = logging.getLogger(__name__)


def _is_truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _optional_int(value):
    text = str(value or "").strip()
    if not text:
        return None
    return int(text)


@funds_flow_local_bp.route("/dashboard", methods=["GET"])
def funds_flow_local_dashboard():
    try:
        payload = funds_flow_local_service.get_dashboard(
            target_date=request.args.get("date") or None,
            period=request.args.get("period") or "21d",
            history_days=_optional_int(request.args.get("history_days")),
            refresh=_is_truthy(request.args.get("refresh", "false")),
        )
        payload["collector"] = FundsFlowLocalManager.get_instance().status()
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@funds_flow_local_bp.route("/collect", methods=["POST"])
def collect_funds_flow_local():
    try:
        payload = request.get_json(silent=True) or {}
        result = FundsFlowLocalManager.get_instance().collect_once(
            force=_is_truthy(payload.get("force", True)),
            target_date=payload.get("date") or payload.get("target_date") or None,
            period=payload.get("period") or "21d",
            history_days=_optional_int(payload.get("history_days")),
        )
        result["collector"] = FundsFlowLocalManager.get_instance().status()
        return jsonify(result)
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@funds_flow_local_bp.route("/sources/<source_id>/refresh", methods=["POST"])
def refresh_funds_flow_local_source(source_id):
    try:
        payload = request.get_json(silent=True) or {}
        result = FundsFlowLocalManager.get_instance().collect_once(
            force=True,
            target_date=payload.get("date") or payload.get("target_date") or None,
            period=payload.get("period") or "21d",
            history_days=_optional_int(payload.get("history_days")),
        )
        result["requested_source_id"] = source_id
        result["collector"] = FundsFlowLocalManager.get_instance().status()
        return jsonify(result)
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False, 'source_id': source_id})


@funds_flow_local_bp.route("/status", methods=["GET"])
def funds_flow_local_status():
    try:
        return jsonify(FundsFlowLocalManager.get_instance().status())
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@funds_flow_local_bp.route("/collector/start", methods=["POST"])
@require_role("admin")
def start_funds_flow_local_collector():
    try:
        return jsonify(FundsFlowLocalManager.get_instance().start())
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@funds_flow_local_bp.route("/collector/stop", methods=["POST"])
@require_role("admin")
def stop_funds_flow_local_collector():
    try:
        return jsonify(FundsFlowLocalManager.get_instance().stop())
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})
