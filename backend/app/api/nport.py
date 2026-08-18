from __future__ import annotations

import logging

from flask import jsonify, request

from ..auth import require_role
from ..http import error_response
from ..services.nport_service import NportService
from . import nport_bp

nport_service = NportService()
logger = logging.getLogger(__name__)


def _truthy(value) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _int_arg(name: str, default: int) -> int:
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


@nport_bp.route("/dashboard", methods=["GET"])
def nport_dashboard():
    try:
        payload = nport_service.get_dashboard(quarter=request.args.get("quarter") or "latest")
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@nport_bp.route("/analytics/rebuild", methods=["POST"])
@require_role("admin")
def nport_rebuild_analytics():
    try:
        payload = request.get_json(silent=True) or {}
        return jsonify(nport_service.rebuild_extended_analytics(quarter=payload.get("quarter") or request.args.get("quarter") or "latest"))
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@nport_bp.route("/analytics/performance", methods=["GET"])
def nport_performance():
    try:
        return jsonify(nport_service.list_fund_performance(
            quarter=request.args.get("quarter") or "latest",
            page=_int_arg("page", 1),
            per_page=_int_arg("per_page", 25),
            weighted=_truthy(request.args.get("weighted", False)),
        ))
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@nport_bp.route("/analytics/funds", methods=["GET"])
def nport_region_funds():
    try:
        return jsonify(nport_service.list_region_funds(
            quarter=request.args.get("quarter") or "latest",
            target=request.args.get("target") or "brazil",
            side=request.args.get("side") or "long",
            page=_int_arg("page", 1),
            per_page=_int_arg("per_page", 25),
        ))
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@nport_bp.route("/analytics/assets", methods=["GET"])
def nport_region_assets():
    try:
        return jsonify(nport_service.list_region_assets(
            quarter=request.args.get("quarter") or "latest",
            target=request.args.get("target") or "emerging",
            side=request.args.get("side") or "long",
            page=_int_arg("page", 1),
            per_page=_int_arg("per_page", 25),
        ))
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@nport_bp.route("/analytics/fund-holdings/<accession_number>", methods=["GET"])
def nport_fund_holdings(accession_number):
    try:
        return jsonify(nport_service.list_fund_holdings(
            accession_number=accession_number,
            quarter=request.args.get("quarter") or "latest",
            target=request.args.get("target") or "emerging",
            side=request.args.get("side") or "all",
            page=_int_arg("page", 1),
            per_page=_int_arg("per_page", 30),
        ))
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@nport_bp.route("/analytics/positioning", methods=["GET"])
def nport_positioning():
    try:
        return jsonify(nport_service.get_positioning_lab(
            quarter=request.args.get("quarter") or "latest",
        ))
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@nport_bp.route("/status", methods=["GET"])
def nport_status():
    try:
        return jsonify(nport_service.status())
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@nport_bp.route("/ingest-local", methods=["POST"])
def nport_ingest_local():
    try:
        payload = request.get_json(silent=True) or {}
        source_dir = payload.get("source_dir") or payload.get("path")
        if not source_dir:
            source_dir = r"C:\Users\Windows\Downloads\2026q1_nport"
        result = nport_service.ingest_local_directory(
            source_dir=source_dir,
            quarter=payload.get("quarter") or None,
            force=_truthy(payload.get("force", False)),
        )
        return jsonify(result)
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@nport_bp.route("/remote", methods=["GET"])
def nport_remote():
    try:
        return jsonify(nport_service.discover_remote_quarters())
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})


@nport_bp.route("/download", methods=["POST"])
def nport_download():
    try:
        payload = request.get_json(silent=True) or {}
        quarter = payload.get("quarter")
        if not quarter:
            remote = nport_service.discover_remote_quarters()
            quarter = remote.get("latest_remote_quarter")
        result = nport_service.download_quarter(
            quarter=quarter,
            force=_truthy(payload.get("force", False)),
            ingest=_truthy(payload.get("ingest", True)),
        )
        return jsonify(result)
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc, extra={'ok': False})
