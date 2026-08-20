"""Thin Flask adapter that validates requests and invokes Funds Flow use cases."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from pydantic import ValidationError

from ....auth import require_role
from ....container import get_container
from ....http import error_response
from ..application import (
    CollectFundsFlow,
    GetFundsFlowCollectorStatus,
    GetFundsFlowDashboard,
    RefreshFundsFlowSource,
    StartFundsFlowCollector,
    StopFundsFlowCollector,
)
from ..contracts import (
    CollectFundsFlowCommand,
    FundsFlowDashboardQuery,
    RefreshFundsFlowSourceCommand,
)

if TYPE_CHECKING:
    from ....services.funds_flow_local_manager import FundsFlowLocalManager

funds_flow_local_bp = Blueprint("funds_flow_local", __name__)
logger = logging.getLogger(__name__)


def _manager() -> FundsFlowLocalManager:
    return get_container().funds_flow_manager()


def _validation_error_response(exc: ValidationError) -> ResponseReturnValue:
    fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
    return cast(
        ResponseReturnValue,
        error_response(
            logger,
            status_code=400,
            message="Invalid Funds Flow request",
            extra={"invalid_fields": sorted(set(fields))},
        ),
    )


def _server_error(exc: Exception, *, extra: dict[str, Any]) -> ResponseReturnValue:
    return cast(
        ResponseReturnValue,
        error_response(logger, status_code=500, exception=exc, extra=extra),
    )


@funds_flow_local_bp.get("/dashboard")
def funds_flow_local_dashboard() -> ResponseReturnValue:
    try:
        query = FundsFlowDashboardQuery.model_validate(request.args.to_dict())
        payload = GetFundsFlowDashboard(
            get_container().funds_flow_service(),
            _manager(),
        ).execute(query)
        response = jsonify(payload)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response
    except ValidationError as exc:
        return _validation_error_response(exc)
    except Exception as exc:
        return _server_error(exc, extra={"ok": False})


@funds_flow_local_bp.post("/collect")
def collect_funds_flow_local() -> ResponseReturnValue:
    try:
        command = CollectFundsFlowCommand.model_validate(request.get_json(silent=True) or {})
        return jsonify(CollectFundsFlow(_manager()).execute(command))
    except ValidationError as exc:
        return _validation_error_response(exc)
    except Exception as exc:
        return _server_error(exc, extra={"ok": False})


@funds_flow_local_bp.post("/sources/<source_id>/refresh")
def refresh_funds_flow_local_source(source_id: str) -> ResponseReturnValue:
    try:
        payload = request.get_json(silent=True) or {}
        command = RefreshFundsFlowSourceCommand.model_validate({**payload, "source_id": source_id})
        return jsonify(RefreshFundsFlowSource(_manager()).execute(command))
    except ValidationError as exc:
        return _validation_error_response(exc)
    except Exception as exc:
        return _server_error(exc, extra={"ok": False, "source_id": source_id})


@funds_flow_local_bp.get("/status")
def funds_flow_local_status() -> ResponseReturnValue:
    try:
        return jsonify(GetFundsFlowCollectorStatus(_manager()).execute())
    except Exception as exc:
        return _server_error(exc, extra={"ok": False})


@funds_flow_local_bp.post("/collector/start")
@require_role("admin")
def start_funds_flow_local_collector() -> ResponseReturnValue:
    try:
        return jsonify(StartFundsFlowCollector(_manager()).execute())
    except Exception as exc:
        return _server_error(exc, extra={"ok": False})


@funds_flow_local_bp.post("/collector/stop")
@require_role("admin")
def stop_funds_flow_local_collector() -> ResponseReturnValue:
    try:
        return jsonify(StopFundsFlowCollector(_manager()).execute())
    except Exception as exc:
        return _server_error(exc, extra={"ok": False})
