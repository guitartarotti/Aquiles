"""
Macro live feed API routes.
"""

import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from flask import jsonify, request
from flask.typing import ResponseReturnValue

from ..auth import require_role
from ..container import get_container
from ..http import error_response
from ..models.task import TaskManager, TaskStatus
from ..services.bloomberg_desktop_service import BloombergDesktopService
from ..services.fair_value_legs_chart_service import FairValueLegsChartService
from ..services.macro_cross_asset_service import MacroCrossAssetService
from ..services.macro_curve_discovery_service import MacroCurveDiscoveryService
from ..services.macro_driver_factory import build_macro_driver_service
from ..services.macro_live_service import (
    MacroCollectorManager,
    MacroIngestionService,
    MacroProjectionService,
    MacroStateStore,
)
from ..services.macro_market_overview_service import MacroMarketOverviewService
from ..services.macro_thermometer_service import MacroThermometerService
from ..services.macro_trend_service import MacroTrendService
from ..services.market_screen_capture_service import MarketScreenCaptureService
from ..services.market_screen_chart_service import MarketScreenChartService
from ..services.report_source_discovery_service import (
    ReportSourceDiscoveryManager,
    ReportSourceDiscoveryService,
)
from . import macro_bp
from .legacy_heatmap_proxy import legacy_heatmap_proxy_or_disabled

market_screen_chart_service = MarketScreenChartService()
macro_curve_discovery_service = MacroCurveDiscoveryService(
    chart_service=market_screen_chart_service
)
fair_value_legs_chart_service = FairValueLegsChartService(chart_service=market_screen_chart_service)
report_source_discovery_service = ReportSourceDiscoveryService()
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
logger = logging.getLogger(__name__)


def _macro_collector() -> MacroCollectorManager:
    return get_container().macro_collector()


def _report_source_collector() -> ReportSourceDiscoveryManager:
    return get_container().report_source_collector()


def _is_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _curve_keys_from_request() -> list[str]:
    values = request.args.getlist("curve")
    raw_curves = request.args.get("curves")
    if raw_curves:
        values.extend([item.strip() for item in raw_curves.split(",") if item.strip()])
    return values


@macro_bp.route("/snapshot", methods=["GET"])
def get_snapshot() -> ResponseReturnValue:
    try:
        limit_events = max(1, min(int(request.args.get("limit_events", 20)), 100))
        service = MacroIngestionService(store=MacroStateStore())
        state = service.get_snapshot(limit_events=limit_events)
        state["collector"] = _macro_collector().status()

        return jsonify(
            {
                "success": True,
                "data": state,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/events", methods=["GET"])
def list_events() -> ResponseReturnValue:
    """Legacy endpoint – retorna até 100 eventos do recent_events (estado em memória)."""
    try:
        limit = max(1, min(int(request.args.get("limit", 20)), 100))
        source = request.args.get("source") or None
        store = MacroStateStore()
        state = store.read_state()
        events = state.get("recent_events", []) or []
        if source:
            events = [e for e in events if e.get("source") == source]
        ingestion = MacroIngestionService(store=store)
        snapshot = state.get("snapshot", {}) or {}
        events = ingestion.reclassify_news_events(
            events, market_snapshot=(snapshot.get("market") or {})
        )
        events.sort(key=lambda e: e.get("event_time") or "", reverse=True)
        events = events[:limit]
        return jsonify({"success": True, "data": {"events": events, "count": len(events)}})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


# ── Cache para /events/today ──────────────────────────────────────────────────
import json as _json
import os as _os

_today_cache_lock = threading.Lock()  # protege o dict de cache
_today_refresh_lock = threading.Lock()  # garante apenas 1 refresh por vez
_today_cache: dict[str, Any] = {"date": None, "events": [], "ts": 0.0}
_TODAY_CACHE_TTL = 300  # 5 minutos — JSONL tem 38 MB, releitura é cara


def _today_str() -> str:
    import datetime

    try:
        from zoneinfo import ZoneInfo

        tz: datetime.tzinfo = ZoneInfo("America/Sao_Paulo")
    except Exception:
        tz = datetime.timezone(datetime.timedelta(hours=-3))
    return datetime.datetime.now(tz).date().isoformat()


def _read_today_fast(today: str) -> list[dict[str, Any]]:
    """
    Lê o JSONL filtrando por pré-verificação de string antes de parsear JSON.
    Evita parsear 27k entradas históricas — só parseia linhas que contêm
    a data de hoje, reduzindo o tempo de ~10s para < 1s.
    """
    store = MacroStateStore()
    by_id: dict[str, dict[str, Any]] = {}

    # ── 1. JSONL (leitura rápida com pré-filtro) ────────────────────────────
    events_path = store.events_path
    if _os.path.exists(events_path):
        try:
            with open(events_path, "r", encoding="utf-8") as f:
                for raw in f:
                    if today not in raw:  # pré-filtro: string check antes de JSON parse
                        continue
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        ev = _json.loads(raw)
                    except Exception:
                        continue
                    et = ev.get("event_time") or ""
                    if not et.startswith(today):  # confirma a data após parse
                        continue
                    eid = ev.get("event_id") or (et + (ev.get("headline") or "")[:30])
                    by_id[eid] = ev
        except Exception:
            pass

    # ── 2. Estado em memória (recent_events) ────────────────────────────────
    try:
        state = store.read_state()
        for ev in state.get("recent_events", []) or []:
            et = ev.get("event_time") or ""
            if not et.startswith(today):
                continue
            eid = ev.get("event_id") or (et + (ev.get("headline") or "")[:30])
            by_id[eid] = ev
    except Exception:
        pass

    events = list(by_id.values())
    events.sort(key=lambda e: e.get("event_time") or "", reverse=True)
    return events


def _get_today_events() -> list[dict[str, Any]]:
    """
    Retorna todos os eventos de hoje.
    Cache de 5 min; apenas 1 thread refaz a leitura — as demais recebem
    o cache atual (stale-while-revalidate) e não bloqueiam.
    """
    today = _today_str()
    now = time.monotonic()

    # Verificação rápida — cache fresco
    with _today_cache_lock:
        c = _today_cache
        if c["date"] == today and (now - c["ts"]) < _TODAY_CACHE_TTL:
            return list(c["events"])
        stale = list(c["events"]) if c["date"] == today else None

    # Tenta se tornar o único refresher (não bloqueia)
    got = _today_refresh_lock.acquire(blocking=False)
    if not got:
        # Outro thread já está atualizando — devolve stale ou aguarda
        if stale is not None:
            return stale
        with _today_refresh_lock:  # aguarda o refresh terminar
            pass
        with _today_cache_lock:
            return list(_today_cache["events"])

    try:
        events = _read_today_fast(today)
        with _today_cache_lock:
            _today_cache["date"] = today
            _today_cache["events"] = events
            _today_cache["ts"] = time.monotonic()
        return events
    finally:
        _today_refresh_lock.release()


@macro_bp.route("/events/today", methods=["GET"])
def list_events_today() -> ResponseReturnValue:
    """
    Retorna TODOS os eventos de hoje paginados (100 por página).

    Query params:
        offset  int  posição inicial  (default 0)
        limit   int  itens por página (default 100, máx 100)
        source  str  filtra por fonte (opcional)
        relevance str  filtra por relevância: breaking|important|relevant (opcional)

    Response:
        {
          "success": true,
          "data": {
            "events":      [...],   // itens desta página
            "total":       1146,   // total do dia inteiro
            "total_pages": 12,
            "page":        1,
            "offset":      0,
            "limit":       100
          }
        }
    """
    try:
        limit = max(1, min(int(request.args.get("limit", 100)), 100))
        offset = max(0, int(request.args.get("offset", 0)))
        source = request.args.get("source") or None
        relevance = request.args.get("relevance") or None

        all_events = _get_today_events()

        # Filtros opcionais
        if source:
            all_events = [e for e in all_events if e.get("source") == source]
        if relevance:
            all_events = [e for e in all_events if e.get("relevance") == relevance]

        total = len(all_events)
        total_pages = max(1, -(-total // limit))  # ceiling division
        page = offset // limit + 1
        page_events = all_events[offset : offset + limit]

        return jsonify(
            {
                "success": True,
                "data": {
                    "events": page_events,
                    "count": len(page_events),
                    "total": total,
                    "total_pages": total_pages,
                    "page": page,
                    "offset": offset,
                    "limit": limit,
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/overview", methods=["GET"])
def get_macro_overview() -> ResponseReturnValue:
    try:
        participant_limit = max(1, min(int(request.args.get("participant_limit", 12)), 40))
        news_limit = max(1, min(int(request.args.get("news_limit", 5)), 20))
        service = MacroMarketOverviewService(store=MacroStateStore())
        result = service.get_overview(
            participant_limit=participant_limit,
            news_limit=news_limit,
        )
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/bloomberg/status", methods=["GET"])
def get_bloomberg_status() -> ResponseReturnValue:
    try:
        service = BloombergDesktopService()
        return jsonify(
            {
                "success": True,
                "data": service.status(),
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/bloomberg/capture", methods=["POST"])
def capture_bloomberg_reference_assets() -> ResponseReturnValue:
    try:
        service = BloombergDesktopService()
        assets, status = service.capture_reference_assets()
        return jsonify(
            {
                "success": True,
                "data": {
                    "status": status,
                    "assets": assets,
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/thermometer", methods=["GET"])
def get_macro_thermometer() -> ResponseReturnValue:
    try:
        refresh = str(request.args.get("refresh", "false")).lower() == "true"
        service = MacroThermometerService(store=MacroStateStore())
        result = service.get_thermometer(refresh=refresh)
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/cross-asset", methods=["GET"])
def get_macro_cross_asset() -> ResponseReturnValue:
    try:
        limit = max(1, min(int(request.args.get("limit", 80)), 120))
        refresh = str(request.args.get("refresh", "false")).lower() == "true"
        service = MacroCrossAssetService(store=MacroStateStore())
        result = service.get_engine(limit=limit, refresh=refresh)
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/participant-heatmap", methods=["GET"])
def get_macro_participant_heatmap() -> ResponseReturnValue:
    return legacy_heatmap_proxy_or_disabled(
        "/api/macro/participant-heatmap",
        feature="Participant heatmap",
        timeout=45.0,
    )


@macro_bp.route("/drivers", methods=["GET"])
def list_macro_drivers() -> ResponseReturnValue:
    try:
        limit = max(1, min(int(request.args.get("limit", 12)), 100))
        refresh = str(request.args.get("refresh", "false")).lower() == "true"
        service = build_macro_driver_service()
        result = service.list_drivers(limit=limit, refresh=refresh)
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/drivers/focus", methods=["POST"])
def focus_macro_driver() -> ResponseReturnValue:
    try:
        data = request.get_json(silent=True) or {}
        store = MacroStateStore()
        service = build_macro_driver_service(store=store)
        result = service.focus_driver(
            driver_id=data.get("driver_id", ""),
            refresh=bool(data.get("refresh", False)),
        )
        cross_service = MacroCrossAssetService(store=store)
        result["driver_cross_asset"] = cross_service.focus_driver(
            driver_id=data.get("driver_id", ""),
            refresh=bool(data.get("refresh", False)),
        )
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/collector/status", methods=["GET"])
def collector_status() -> ResponseReturnValue:
    try:
        return jsonify(
            {
                "success": True,
                "data": _macro_collector().status(),
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/collector/start", methods=["POST"])
@require_role("admin")
def start_collector() -> ResponseReturnValue:
    try:
        data = request.get_json(silent=True) or {}
        interval_seconds = data.get("interval_seconds")
        if interval_seconds is not None:
            interval_seconds = int(interval_seconds)

        status = _macro_collector().start(interval_seconds=interval_seconds)
        return jsonify(
            {
                "success": True,
                "data": status,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/collector/stop", methods=["POST"])
@require_role("admin")
def stop_collector() -> ResponseReturnValue:
    try:
        status = _macro_collector().stop()
        return jsonify(
            {
                "success": True,
                "data": status,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/collect", methods=["POST"])
def collect_once() -> ResponseReturnValue:
    try:
        data = request.get_json(silent=True) or {}
        include_news = data.get("include_news", True)
        include_market = data.get("include_market", True)
        run_async = data.get("async", True)

        collector = _macro_collector()

        if not run_async:
            result = collector.collect_once(
                include_news=include_news,
                include_market=include_market,
            )
            return jsonify(
                {
                    "success": True,
                    "data": result,
                }
            )

        task_manager = TaskManager()
        task_id = task_manager.create_task(
            "macro_collect",
            metadata={
                "include_news": include_news,
                "include_market": include_market,
            },
        )

        def run_collect() -> None:
            try:
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    progress=10,
                    message="Collecting macro feeds",
                )
                result = collector.collect_once(
                    include_news=include_news,
                    include_market=include_market,
                )
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    progress=100,
                    message="Macro collection completed",
                    result=result,
                )
            except Exception as exc:
                logger.exception("macro collection task failed", exc_info=exc)
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message="Macro collection failed",
                    error="Internal server error",
                )

        thread = threading.Thread(target=run_collect, daemon=True)
        thread.start()

        return jsonify(
            {
                "success": True,
                "data": {
                    "task_id": task_id,
                    "message": "Macro collection started",
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/task/<task_id>", methods=["GET"])
def get_macro_task(task_id: str) -> ResponseReturnValue:
    task = TaskManager().get_task(task_id)

    if not task:
        return jsonify(
            {
                "success": False,
                "error": f"Task not found: {task_id}",
            }
        ), 404

    return jsonify(
        {
            "success": True,
            "data": task.to_dict(),
        }
    )


@macro_bp.route("/project/sync", methods=["POST"])
def sync_snapshot_to_project() -> ResponseReturnValue:
    try:
        data = request.get_json(silent=True) or {}
        projection = MacroProjectionService()
        result = projection.sync_snapshot_to_project(
            project_id=data.get("project_id"),
            project_name=data.get("project_name"),
            simulation_requirement=data.get("simulation_requirement"),
            include_recent_events=int(data.get("include_recent_events", 20)),
        )
        project = result["project"]

        return jsonify(
            {
                "success": True,
                "data": {
                    "project_id": project.project_id,
                    "project": project.to_dict(),
                    "snapshot_generated_at": result["snapshot_generated_at"],
                    "artifact_path": result["artifact_path"],
                    "markdown_preview": result["markdown_preview"],
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/trends", methods=["GET"])
def list_macro_trends() -> ResponseReturnValue:
    try:
        limit = max(1, min(int(request.args.get("limit", 8)), 20))
        service = MacroTrendService(store=MacroStateStore())
        result = service.list_trends(
            limit=limit,
            project_id=request.args.get("project_id"),
            graph_id=request.args.get("graph_id"),
        )
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/trends/focus", methods=["POST"])
def focus_macro_trend() -> ResponseReturnValue:
    try:
        data = request.get_json(silent=True) or {}
        service = MacroTrendService(store=MacroStateStore())
        result = service.focus_trend(
            trend_id=data.get("trend_id", ""),
            project_id=data.get("project_id"),
            graph_id=data.get("graph_id"),
            comment_count=int(data.get("comment_count", 6)),
        )
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/screen-capture/w32-basica/capture", methods=["POST"])
def capture_w32_basica_screen() -> ResponseReturnValue:
    try:
        return jsonify(
            {
                "success": False,
                "error": "Market screen capture is owned by aquiles-market-capture.",
            }
        ), 409
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/screen-capture/w32-basica/latest", methods=["GET"])
def latest_w32_basica_screen_capture() -> ResponseReturnValue:
    try:
        service = MarketScreenCaptureService()
        result = service.read_latest_capture()
        if not result:
            return jsonify(
                {
                    "success": False,
                    "error": "No market screen capture available yet.",
                }
            ), 404
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/screen-capture/w32-basica/latest-symbol", methods=["GET"])
def latest_w32_basica_symbol() -> ResponseReturnValue:
    try:
        requested_symbol = request.args.get("symbol") or "XB1"
        resolved_symbol = (
            market_screen_chart_service._resolve_symbol(requested_symbol)
            or str(requested_symbol).strip()
        )
        service = MarketScreenCaptureService()
        payload = service.read_latest_capture()
        if not payload:
            return jsonify(
                {
                    "success": False,
                    "error": "No market screen capture available yet.",
                }
            ), 404

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
            return jsonify(
                {
                    "success": False,
                    "error": f"Symbol not available in latest capture: {resolved_symbol}",
                }
            ), 404

        return jsonify(
            {
                "success": True,
                "data": {
                    "symbol": resolved_symbol,
                    "captured_at": payload.get("captured_at"),
                    "capture_id": payload.get("capture_id"),
                    "price": row_match.get("price"),
                    "daily_change_pct": row_match.get("daily_change_pct"),
                    "source": "w32_latest_symbol",
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/screen-capture/w32-basica/collector/status", methods=["GET"])
def w32_basica_collector_status() -> ResponseReturnValue:
    try:
        status = MarketScreenCaptureService().status()
        status.update({"owner": "aquiles-market-capture", "external": True})
        return jsonify(
            {
                "success": True,
                "data": status,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/screen-capture/w32-basica/collector/start", methods=["POST"])
@require_role("admin")
def start_w32_basica_collector() -> ResponseReturnValue:
    try:
        return jsonify(
            {
                "success": False,
                "error": "Market screen collector is managed by PM2 as aquiles-market-capture.",
            }
        ), 409
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/screen-capture/w32-basica/collector/stop", methods=["POST"])
@require_role("admin")
def stop_w32_basica_collector() -> ResponseReturnValue:
    try:
        return jsonify(
            {
                "success": False,
                "error": "Market screen collector is managed by PM2 as aquiles-market-capture.",
            }
        ), 409
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/screen-capture/w32-basica/excel-basket/latest", methods=["GET"])
def latest_w32_basica_excel_basket() -> ResponseReturnValue:
    try:
        if _is_truthy(request.args.get("refresh")):
            return jsonify(
                {
                    "success": False,
                    "error": "On-demand capture is owned by aquiles-market-capture.",
                }
            ), 409
        service = MarketScreenCaptureService()
        latest = service.read_latest_capture()
        result = (
            service.build_excel_compatible_payload(latest)
            if latest
            else {"ok": False, "error": "market_screen_capture_unavailable"}
        )
        status_code = 200 if result.get("ok") else 422
        return jsonify(
            {
                "success": bool(result.get("ok")),
                "data": result,
            }
        ), status_code
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/screen-capture/w32-basica/chart", methods=["GET"])
def w32_basica_chart_payload() -> ResponseReturnValue:
    try:
        include_assets = _is_truthy(request.args.get("include_assets", "true"))
        include_collector = _is_truthy(request.args.get("include_collector", "true"))
        benchmark_only = _is_truthy(request.args.get("benchmark_only", "false"))
        result = market_screen_chart_service.build_payload(
            symbol=request.args.get("symbol"),
            benchmark_symbol=request.args.get("benchmark_symbol") or "XB1",
            lookback_minutes=int(request.args.get("lookback_minutes", 360)),
            rolling_window_points=int(request.args.get("rolling_window_points", 60)),
            max_points=int(request.args.get("max_points", 1200)),
            bar_minutes=int(request.args.get("bar_minutes") or 0),
            include_assets=include_assets,
            benchmark_only=benchmark_only,
        )
        if include_collector:
            result["collector"] = {
                **MarketScreenCaptureService().status(),
                "owner": "aquiles-market-capture",
                "external": True,
            }
        status_code = 200 if result.get("ok") else 404
        response = jsonify(
            {
                "success": bool(result.get("ok")),
                "data": result,
            }
        )
        return response, status_code
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/screen-capture/w32-basica/benchmark-candles", methods=["GET"])
def w32_basica_benchmark_candles() -> ResponseReturnValue:
    try:
        requested_symbol = (
            request.args.get("symbol") or request.args.get("benchmark_symbol") or "XB1"
        )
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
            local_bucket = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc).astimezone(
                LOCAL_TZ
            )
            local_minutes = (local_bucket.hour * 60) + local_bucket.minute
            if local_minutes < 9 * 60 or local_minutes > 18 * 60:
                continue
            last_capture = row["last_capture_at_epoch"]
            if last_capture is not None:
                latest_capture_epoch = max(
                    float(last_capture), latest_capture_epoch or float(last_capture)
                )
            candles.append(
                {
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
                }
            )

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
            "source": "sqlite_benchmark_candles",
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
        return jsonify(
            {
                "success": bool(payload.get("ok")),
                "data": payload,
            }
        ), 200 if payload.get("ok") else 404
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


# ─── Admin: compactar CSVs do market screen ───────────────────────────────────


@macro_bp.route("/curves/discovery", methods=["GET"])
def macro_curves_discovery_payload() -> ResponseReturnValue:
    try:
        result = macro_curve_discovery_service.build_payload(
            curves=_curve_keys_from_request(),
            lookback_minutes=int(request.args.get("lookback_minutes", 720)),
            max_points=int(request.args.get("max_points", 720)),
            include_shape_points=_is_truthy(request.args.get("include_shape_points", "true")),
            session_date=request.args.get("session_date") or None,
        )
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/report-sources/panel", methods=["GET"])
def report_source_discovery_panel() -> ResponseReturnValue:
    try:
        refresh = _is_truthy(request.args.get("refresh", "false"))
        lookback_days = request.args.get("lookback_days")
        result = report_source_discovery_service.get_panel(
            refresh=refresh,
            lookback_days=int(str(lookback_days)) if str(lookback_days or "").strip() else None,
        )
        result["collector"] = _report_source_collector().status()
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/report-sources/collect", methods=["POST"])
def collect_report_source_discovery() -> ResponseReturnValue:
    try:
        payload = request.get_json(silent=True) or {}
        lookback_days = payload.get("lookback_days")
        result = _report_source_collector().collect_once(
            force=_is_truthy(payload.get("force", True)),
            lookback_days=int(str(lookback_days)) if str(lookback_days or "").strip() else None,
        )
        result["collector"] = _report_source_collector().status()
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/report-sources/status", methods=["GET"])
def report_source_discovery_status() -> ResponseReturnValue:
    try:
        return jsonify(
            {
                "success": True,
                "data": _report_source_collector().status(),
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/report-sources/collector/start", methods=["POST"])
@require_role("admin")
def start_report_source_discovery_collector() -> ResponseReturnValue:
    try:
        return jsonify(
            {
                "success": True,
                "data": _report_source_collector().start(),
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/report-sources/collector/stop", methods=["POST"])
@require_role("admin")
def stop_report_source_discovery_collector() -> ResponseReturnValue:
    try:
        return jsonify(
            {
                "success": True,
                "data": _report_source_collector().stop(),
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/curves/discovery/ai", methods=["POST"])
def macro_curves_discovery_ai() -> ResponseReturnValue:
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
        return jsonify(
            {
                "success": True,
                "data": result,
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/fair-value/legs-chart", methods=["POST"])
def macro_fair_value_legs_chart() -> ResponseReturnValue:
    try:
        payload = request.get_json(silent=True) or {}
        build_kwargs: dict[str, Any] = dict(
            config=payload.get("config") if isinstance(payload.get("config"), dict) else payload,
            sessions=int(payload.get("sessions") or 3),
            bar_minutes=int(payload.get("bar_minutes") or 5),
            session_start=str(payload.get("session_start") or "09:00"),
            session_end=str(payload.get("session_end") or "18:30"),
            rolling_window_points=int(payload.get("rolling_window_points") or 60),
            vol_context=payload.get("vol_context")
            if isinstance(payload.get("vol_context"), dict)
            else None,
        )
        raw_config_payload = build_kwargs.get("config")
        config_payload: dict[str, Any] = (
            dict(raw_config_payload) if isinstance(raw_config_payload, dict) else {}
        )
        is_default_composition = not bool((config_payload or {}).get("legs"))
        min_history_timestamp = None
        try:
            latest_probe = fair_value_legs_chart_service.build_latest_payload(**build_kwargs)
            latest_timestamp = fair_value_legs_chart_service.payload_last_timestamp_ms(latest_probe)
            interval_ms = max(int(build_kwargs["bar_minutes"] or 5), 1) * 60_000
            if latest_timestamp is not None:
                min_history_timestamp = max(int(latest_timestamp) - interval_ms, 0)
        except Exception:
            latest_probe = None
        if is_default_composition and not bool(payload.get("force_refresh")):
            snapshot = fair_value_legs_chart_service._load_payload_snapshot()
            if snapshot is not None:
                snapshot_covers_latest = (
                    fair_value_legs_chart_service.payload_covers_latest_available_session(
                        snapshot,
                        sessions=build_kwargs["sessions"],
                    )
                )
                snapshot_last_timestamp = fair_value_legs_chart_service.payload_last_timestamp_ms(
                    snapshot
                )
                snapshot_covers_latest_timestamp = min_history_timestamp is None or (
                    snapshot_last_timestamp is not None
                    and snapshot_last_timestamp >= min_history_timestamp
                )
                if not snapshot_covers_latest:
                    fair_value_legs_chart_service.refresh_snapshot_async(
                        **build_kwargs,
                        min_timestamp_ms=min_history_timestamp,
                    )
                    snapshot["snapshot_refresh_pending"] = True
                    snapshot["snapshot_refresh_reason"] = "session"
                    return jsonify(
                        {
                            "success": True,
                            "data": snapshot,
                        }
                    ), 200
                if snapshot_covers_latest_timestamp:
                    return jsonify(
                        {
                            "success": True,
                            "data": snapshot,
                        }
                    ), 200
                fair_value_legs_chart_service.refresh_snapshot_async(
                    **build_kwargs,
                    min_timestamp_ms=min_history_timestamp,
                )
                snapshot["snapshot_refresh_pending"] = True
                snapshot["snapshot_refresh_reason"] = "timestamp"
                return jsonify(
                    {
                        "success": True,
                        "data": snapshot,
                    }
                ), 200

        result = fair_value_legs_chart_service.build_payload(
            **build_kwargs,
            min_timestamp_ms=min_history_timestamp,
        )
        return jsonify(
            {
                "success": bool(result.get("ok")),
                "data": result,
            }
        ), 200 if result.get("ok") else 404
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/fair-value/legs-chart/latest", methods=["POST"])
def macro_fair_value_legs_chart_latest() -> ResponseReturnValue:
    try:
        payload = request.get_json(silent=True) or {}
        result = fair_value_legs_chart_service.build_latest_payload(
            config=payload.get("config") if isinstance(payload.get("config"), dict) else payload,
            sessions=int(payload.get("sessions") or 3),
            bar_minutes=int(payload.get("bar_minutes") or 5),
            session_start=str(payload.get("session_start") or "09:00"),
            session_end=str(payload.get("session_end") or "18:30"),
            rolling_window_points=int(payload.get("rolling_window_points") or 60),
            vol_context=payload.get("vol_context")
            if isinstance(payload.get("vol_context"), dict)
            else None,
        )
        return jsonify(
            {
                "success": bool(result.get("ok")),
                "data": result,
            }
        ), 200 if result.get("ok") else 404
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@macro_bp.route("/screen-capture/compact-csv", methods=["POST"])
def compact_screen_capture_csv() -> ResponseReturnValue:
    """
    Reescreve os CSVs de market screen capture mantendo apenas linhas com
    symbol_normalized e price válidos.  Roda dentro do processo Python para
    evitar conflito de lock do Windows.

    Query params:
      days  (int)  número de arquivos mais recentes a compactar (padrão: 7)
    """
    try:
        import csv as _csv
        import os as _os

        from ..config import Config

        rows_dir = _os.path.join(Config.OPTIONS_DATA_DIR, "market_screen_capture", "rows")
        if not _os.path.isdir(rows_dir):
            return jsonify({"success": False, "error": "rows_dir nao encontrado"}), 404

        days = min(int(request.args.get("days", 7)), 60)

        csv_files = sorted(
            [
                f
                for f in _os.listdir(rows_dir)
                if f.endswith(".csv") and not f.endswith(".tmp") and not f.endswith(".compacting")
            ]
        )[-days:]

        results = []
        for fname in csv_files:
            path = _os.path.join(rows_dir, fname)
            tmp = path + ".compacting"
            try:
                original_bytes = _os.path.getsize(path)
                kept = dropped = 0

                with (
                    open(path, newline="", encoding="utf-8", errors="replace") as fin,
                    open(tmp, "w", newline="", encoding="utf-8", errors="replace") as fout,
                ):
                    reader = _csv.DictReader(fin)
                    if not reader.fieldnames:
                        results.append(
                            {
                                "file": fname,
                                "ok": True,
                                "kept": 0,
                                "dropped": 0,
                                "note": "arquivo vazio",
                            }
                        )
                        continue
                    writer = _csv.DictWriter(fout, fieldnames=reader.fieldnames)
                    writer.writeheader()
                    for row in reader:
                        sym_ok = bool(
                            (row.get("symbol") or row.get("symbol_normalized") or "").strip()
                        )
                        price_ok = bool((row.get("price") or "").strip())
                        if sym_ok and price_ok:
                            writer.writerow(row)
                            kept += 1
                        else:
                            dropped += 1

                compact_bytes = _os.path.getsize(tmp)
                _os.replace(tmp, path)
                results.append(
                    {
                        "file": fname,
                        "original_mb": round(original_bytes / 1024 / 1024, 2),
                        "compact_mb": round(compact_bytes / 1024 / 1024, 2),
                        "kept": kept,
                        "dropped": dropped,
                        "ok": True,
                    }
                )
            except Exception as exc:
                if _os.path.exists(tmp):
                    try:
                        _os.remove(tmp)
                    except Exception:
                        pass
                logger.exception("compact CSV processing failed for %s", fname, exc_info=exc)
                results.append({"file": fname, "ok": False, "error": "Processing failed"})

        # Invalida caches em memória do chart service para forçar releitura
        market_screen_chart_service._frame_cache.clear()
        market_screen_chart_service._analysis_cache.clear()
        market_screen_chart_service._payload_cache.clear()

        return jsonify({"success": True, "data": {"files": results}})

    except Exception as e:
        return error_response(logger, status_code=500, exception=e)
