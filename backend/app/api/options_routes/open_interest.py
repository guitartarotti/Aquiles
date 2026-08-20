import threading

from flask import jsonify, request

from ...auth import require_role
from ...http import error_response
from ...models.task import TaskManager, TaskStatus
from ...services.options_history_service import OptionsHistoryService
from ...services.options_query_service import OptionsQueryService
from .. import options_bp
from .shared import _is_truthy, _options_collector_service_request, logger


@options_bp.route("/history/oi", methods=["GET"])
def get_options_oi_history():
    try:
        query = OptionsQueryService()
        result = query.oi_history(
            underlying_security=request.args.get("underlying_security"),
            option_id=request.args.get("option_id"),
            start_date=request.args.get("start_date"),
            end_date=request.args.get("end_date"),
            limit=max(1, min(int(request.args.get("limit", 1000)), 5000)),
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/collector/status", methods=["GET"])
def options_collector_status():
    try:
        return _options_collector_service_request(
            "GET", "/api/options/collector/status", timeout=5.0
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/collector/start", methods=["POST"])
@require_role("admin")
def start_options_collector():
    try:
        return _options_collector_service_request(
            "POST", "/api/options/collector/start", timeout=10.0
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/collector/stop", methods=["POST"])
@require_role("admin")
def stop_options_collector():
    try:
        return _options_collector_service_request(
            "POST", "/api/options/collector/stop", timeout=10.0
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/collect", methods=["POST"])
def collect_options_once():
    try:
        payload = request.get_json(silent=True) or {}
        return _options_collector_service_request(
            "POST",
            "/api/options/collect",
            json_payload=payload,
            timeout=300.0,
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/history/backfill", methods=["POST"])
@require_role("admin")
def backfill_options_history():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = payload.get("underlying_security") or "IBOVE Index"
        lookback_days = payload.get("lookback_days")
        max_contracts = payload.get("max_contracts")
        run_async = bool(payload.get("async", True))
        service = OptionsHistoryService()

        if not run_async:
            result = service.backfill_open_interest_history(
                underlying,
                lookback_days=lookback_days,
                max_contracts=max_contracts,
            )
            return jsonify({"success": True, "data": result})

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            "options_oi_backfill",
            metadata={
                "underlying_security": underlying,
                "lookback_days": lookback_days,
                "max_contracts": max_contracts,
            },
        )

        def run_backfill() -> None:
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=10,
                    message="Backfilling options OI history",
                )
                result = service.backfill_open_interest_history(
                    underlying,
                    lookback_days=lookback_days,
                    max_contracts=max_contracts,
                )
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    message="Options OI backfill completed",
                    result=result,
                )
            except Exception as exc:
                logger.exception("options OI backfill task failed", exc_info=exc)
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Options OI backfill failed",
                    error="Internal server error",
                )

        threading.Thread(target=run_backfill, daemon=True).start()
        return jsonify(
            {
                "success": True,
                "data": {"task_id": task_id, "message": "Options OI backfill started"},
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/history/update", methods=["POST"])
def update_options_history():
    try:
        payload = request.get_json(silent=True) or {}
        return _options_collector_service_request(
            "POST",
            "/api/options/history/update",
            json_payload=payload,
            timeout=300.0,
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/history/oi-status", methods=["GET"])
def get_oi_daily_status():
    """Retorna se o OI diário já foi coletado para o underlying/data informados."""
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        trade_date = request.args.get("trade_date") or None
        history_service = OptionsHistoryService()
        complete = history_service.is_daily_oi_complete(underlying, trade_date)
        from datetime import datetime as _dt

        target_date = trade_date or _dt.now().date().isoformat()
        return jsonify(
            {
                "success": True,
                "data": {
                    "underlying_security": underlying,
                    "trade_date": target_date,
                    "daily_oi_complete": complete,
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/b3/oi/collect", methods=["POST"])
def collect_b3_open_interest():
    """
    Dispara a coleta de Posicoes em Aberto (OI) da B3 para uma data.

    Body JSON (opcional):
      trade_date  string   YYYY-MM-DD (padrao: hoje)
      force       bool     Re-coleta mesmo se ja coletado (padrao: false)

    Retorna: rows_saved, trade_date, skipped, error
    """
    try:
        from ...services.b3_oi_service import B3OIService

        body = request.get_json(force=True, silent=True) or {}
        trade_date = body.get("trade_date") or request.args.get("trade_date") or None
        force = _is_truthy(body.get("force", False))

        service = B3OIService()
        result = service.collect_daily_oi(trade_date=trade_date, force=force)
        return jsonify(
            {
                "success": True,
                "data": {
                    k: v
                    for k, v in result.items()
                    if k != "rows"  # exclui lista completa do response
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/b3/oi/status", methods=["GET"])
def get_b3_oi_status():
    """
    Retorna status do OI B3: se foi coletado, datas disponiveis, e
    contagem de contratos para a data informada.

    Query params:
      trade_date  string   YYYY-MM-DD (padrao: hoje)
    """
    try:
        from ...services.b3_oi_service import B3OIService
        from ...services.options_store import OptionsStore

        trade_date = request.args.get("trade_date") or None

        service = B3OIService()
        store = OptionsStore()

        from datetime import datetime as _dt

        target_date = trade_date or _dt.now().date().isoformat()

        collected = service.is_collected(target_date)
        dates = service.list_collected_dates()
        rows = store.load_b3_oi_rows(target_date) if collected else []

        return jsonify(
            {
                "success": True,
                "data": {
                    "trade_date": target_date,
                    "collected": collected,
                    "contracts_count": len(rows),
                    "dates_available": dates,
                    "sample": rows[:3] if rows else [],
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/b3/oi/backfill", methods=["POST"])
@require_role("admin")
def backfill_b3_open_interest():
    """
    Dispara backfill de OI da B3 para um intervalo de datas.
    Roda em background (thread separada).

    Body JSON:
      date_from   string   YYYY-MM-DD (obrigatorio)
      date_to     string   YYYY-MM-DD (obrigatorio)
      force       bool     Re-coleta mesmo se ja coletado (padrao: false)
    """
    try:
        from ...services.b3_oi_service import B3OIService

        body = request.get_json(force=True, silent=True) or {}
        date_from = body.get("date_from")
        date_to = body.get("date_to")
        force = _is_truthy(body.get("force", False))

        if not date_from or not date_to:
            return jsonify({"success": False, "error": "date_from e date_to sao obrigatorios"}), 400

        import threading as _th

        service = B3OIService()

        def _run():
            try:
                service.backfill(date_from=date_from, date_to=date_to, force=force)
            except Exception as exc:
                import logging

                logging.getLogger("aquiles.b3_oi_service").error("Backfill erro: %s", exc)

        t = _th.Thread(target=_run, daemon=True, name="b3-oi-backfill")
        t.start()

        return jsonify(
            {
                "success": True,
                "data": {
                    "message": "Backfill iniciado em background",
                    "date_from": date_from,
                    "date_to": date_to,
                    "force": force,
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/jobs/<task_id>", methods=["GET"])
def get_options_task(task_id: str):
    task = TaskManager().get_task(task_id)
    if not task:
        return _options_collector_service_request(
            "GET",
            f"/api/options/jobs/{task_id}",
            timeout=5.0,
        )
    return jsonify({"success": True, "data": task.to_dict()})


@options_bp.route("/b3-oi/latest", methods=["GET"])
def b3_oi_latest():
    """
    Retorna o OI da B3 mais recente, agregado por strike (call + put).

    Query params:
      date  (str)  YYYY-MM-DD — data específica (padrão: data mais recente disponível)
      raw   (bool) se 'true', devolve as linhas brutas sem agregar

    Response (agregado):
      {
        "date": "2026-05-14",
        "total_rows": 762,
        "by_strike": [
          {
            "strike": 175000.0,
            "call_oi": 5000, "put_oi": 3000, "total_oi": 8000,
            "call_coberto": 0, "call_trava": 5000, "call_descoberto": 0,
            "put_coberto": 0,  "put_trava": 3000, "put_descoberto": 0
          }, ...
        ]
      }
    """
    try:
        from ...services.options_store import OptionsStore

        store = OptionsStore()

        requested_date = request.args.get("date") or None
        raw_mode = request.args.get("raw", "false").lower() == "true"

        # Descobrir a data mais recente disponível
        if requested_date:
            trade_date = requested_date
        else:
            dates = store.list_b3_oi_dates()
            if not dates:
                return jsonify(
                    {"success": True, "data": {"date": None, "by_strike": [], "total_rows": 0}}
                )
            trade_date = sorted(dates)[-1]  # mais recente

        rows = store.load_b3_oi_rows(trade_date)

        if raw_mode:
            return jsonify({"success": True, "data": rows, "date": trade_date, "count": len(rows)})

        # Agregar por strike
        strike_map: dict[float, dict] = {}
        for r in rows:
            s = float(r.get("strike") or 0)
            if s <= 0:
                continue
            if s not in strike_map:
                strike_map[s] = {
                    "strike": s,
                    "call_oi": 0,
                    "put_oi": 0,
                    "total_oi": 0,
                    "call_coberto": 0,
                    "call_trava": 0,
                    "call_descoberto": 0,
                    "put_coberto": 0,
                    "put_trava": 0,
                    "put_descoberto": 0,
                    "call_n_titular": 0,
                    "call_n_lancador": 0,
                    "put_n_titular": 0,
                    "put_n_lancador": 0,
                }
            entry = strike_map[s]
            t = str(r.get("type") or "").upper()
            oi = int(r.get("oi_total") or 0)
            if t == "CALL":
                entry["call_oi"] += oi
                entry["call_coberto"] += int(r.get("oi_coberto") or 0)
                entry["call_trava"] += int(r.get("oi_trava") or 0)
                entry["call_descoberto"] += int(r.get("oi_descoberto") or 0)
                entry["call_n_titular"] += int(r.get("n_titular") or 0)
                entry["call_n_lancador"] += int(r.get("n_lancador") or 0)
            elif t == "PUT":
                entry["put_oi"] += oi
                entry["put_coberto"] += int(r.get("oi_coberto") or 0)
                entry["put_trava"] += int(r.get("oi_trava") or 0)
                entry["put_descoberto"] += int(r.get("oi_descoberto") or 0)
                entry["put_n_titular"] += int(r.get("n_titular") or 0)
                entry["put_n_lancador"] += int(r.get("n_lancador") or 0)
            entry["total_oi"] = entry["call_oi"] + entry["put_oi"]

        by_strike = sorted(strike_map.values(), key=lambda x: x["strike"])

        return jsonify(
            {
                "success": True,
                "data": {
                    "date": trade_date,
                    "total_rows": len(rows),
                    "by_strike": by_strike,
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/b3-oi/dates", methods=["GET"])
def b3_oi_dates():
    """Lista todas as datas com dados de OI B3 disponíveis."""
    try:
        from ...services.options_store import OptionsStore

        store = OptionsStore()
        dates = store.list_b3_oi_dates()
        return jsonify({"success": True, "data": sorted(dates)})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)
