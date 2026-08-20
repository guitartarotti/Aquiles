"""Volume activity, hedge, and tracker routes for the options API."""

from __future__ import annotations

import logging
import math
from datetime import date

from flask import jsonify, request

from ..auth import require_role
from ..config import Config
from ..container import get_container
from ..http import error_response
from . import options_bp

logger = logging.getLogger(__name__)


@options_bp.get("/volume/activity")
def volume_activity():
    from ..services.options_store import OptionsStore

    try:
        symbol = request.args.get("symbol") or None
        rows = OptionsStore().read_volume_activity(
            session_date=request.args.get("session_date") or None,
            symbol=symbol,
            underlying_security=(request.args.get("underlying_security") or None)
            if not symbol
            else None,
            limit=min(int(request.args.get("limit", 500)), 5000),
            lookback_days=int(
                request.args.get(
                    "lookback_days",
                    Config.OPTIONS_VOLUME_ACTIVITY_LOOKBACK_DAYS,
                )
            ),
        )
        return jsonify({"success": True, "data": rows, "count": len(rows)})
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.get("/volume/summary")
def volume_activity_summary():
    from ..services.options_store import OptionsStore

    try:
        summary = OptionsStore().volume_activity_summary(
            session_date=request.args.get("session_date") or date.today().isoformat(),
            underlying_security=request.args.get("underlying_security") or None,
        )
        return jsonify({"success": True, "data": summary})
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.get("/volume/iv-history")
def volume_iv_history():
    from ..services.options_store import OptionsStore

    try:
        rows = OptionsStore().read_volume_iv_history(
            session_date=request.args.get("session_date") or None,
            underlying_security=request.args.get("underlying_security") or None,
            limit=min(int(request.args.get("limit", 500)), 5000),
            lookback_days=int(
                request.args.get(
                    "lookback_days",
                    Config.OPTIONS_VOLUME_ACTIVITY_LOOKBACK_DAYS,
                )
            ),
        )
        return jsonify(
            {
                "success": True,
                "data": {"history": rows, "latest": rows[0] if rows else None},
                "count": len(rows),
            }
        )
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.post("/hedge/delta")
def hedge_delta():
    """Calculate delta hedge contracts using SABR and transaction-cost bands."""
    try:
        from ..services.sabr_hedge_model import SABRHedgeModel

        body = request.get_json(force=True) or {}
        spot = float(body.get("spot") or 0)
        events = _hedge_events(body)
        if not events:
            return jsonify(
                {
                    "success": True,
                    "sabr_params": {},
                    "events": [],
                    "summary": {"n_events": 0, "cumul_n_win": 0.0, "cumul_n_ind": 0.0},
                }
            )

        if spot <= 0:
            spot = next(
                (
                    candidate
                    for event in events
                    if (candidate := _native_float(event.get("spot_price"), 8)) > 0
                ),
                0.0,
            )
        if spot <= 0:
            return jsonify(
                {"success": False, "error": "spot não informado e não encontrado nos eventos"}
            ), 400

        model = SABRHedgeModel(
            beta=float(body.get("beta") or 0.5),
            tc_bps=float(body.get("tc_bps") or 10.0),
        )
        params, results = model.hedge_contracts(
            events=events,
            spot=spot,
            market_ctx=body.get("market_ctx") or {},
            vol_surface=body.get("vol_surface") or [],
            fut_type=str(body.get("fut_type") or "WIN").upper(),
            dt_minutes=float(body.get("dt_minutes") or 60.0),
        )
        return jsonify(
            {
                "success": True,
                "sabr_params": params.to_dict(),
                "events": [result.to_dict() for result in results],
                "summary": {
                    "n_events": len(results),
                    "cumul_n_win": _native_float(sum(result.n_win for result in results), 1),
                    "cumul_n_ind": _native_float(sum(result.n_ind for result in results), 1),
                    "avg_delta_sabr": _native_float(
                        sum(result.delta_sabr for result in results) / len(results)
                        if results
                        else 0.0,
                        5,
                    ),
                },
            }
        )
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


def _hedge_events(body: dict) -> list:
    events = body.get("events") or []
    if events or not body.get("session_date"):
        return events

    from ..services.options_store import OptionsStore

    return OptionsStore().read_volume_activity(
        session_date=body["session_date"],
        underlying_security=body.get("underlying_security") or None,
        limit=5000,
    )


def _native_float(value, digits: int) -> float:
    try:
        if hasattr(value, "item"):
            value = value.item()
        parsed = float(value or 0.0)
        return round(parsed, digits) if math.isfinite(parsed) else 0.0
    except (TypeError, ValueError):
        return 0.0


@options_bp.get("/volume/state")
def volume_state():
    from ..services.options_store import OptionsStore

    try:
        state = OptionsStore().load_volume_state()
        symbol = request.args.get("symbol")
        if symbol:
            state = {key: value for key, value in state.items() if key == symbol}
        return jsonify({"success": True, "data": state, "count": len(state)})
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.post("/volume/poll")
def volume_poll():
    try:
        body = request.get_json(silent=True) or {}
        configured = Config.OPTIONS_BLOOMBERG_UNDERLYINGS
        underlying = (
            body.get("underlying_security")
            or request.args.get("underlying_security")
            or (configured[0] if configured else "IBOVE Index")
        )
        result = get_container().options_volume_tracker().poll_once(underlying)
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.post("/volume/poll/all")
def volume_poll_all():
    try:
        result = get_container().options_volume_tracker().poll_all_underlyings()
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.get("/volume/tracker/status")
def volume_tracker_status():
    return _tracker_command("status")


@options_bp.post("/volume/tracker/start")
@require_role("admin")
def volume_tracker_start():
    return _tracker_command("start")


@options_bp.post("/volume/tracker/stop")
@require_role("admin")
def volume_tracker_stop():
    return _tracker_command("stop")


def _tracker_command(command: str):
    try:
        tracker = get_container().options_volume_tracker()
        return jsonify({"success": True, "data": getattr(tracker, command)()})
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.post("/volume/tracker/backfill")
@require_role("admin")
def volume_tracker_backfill():
    try:
        tracker = get_container().options_volume_tracker()
        return jsonify({"success": True, "data": tracker.backfill_today()})
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)
