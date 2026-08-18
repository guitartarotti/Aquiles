from __future__ import annotations

import csv
import json
import math
import os
import statistics
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from datetime import time as dt_time
from io import StringIO
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from ..config import Config
from ..utils.atomic_io import atomic_json_dump
from ..utils.logger import get_logger

logger = get_logger("mirofish.report_source_discovery")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utc_now().isoformat()


def _local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(str(value).strip())
    except Exception:
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _round(value: Any, digits: int = 4) -> float | None:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    return round(parsed, digits)


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _business_days(start_date: date, end_date: date) -> int:
    if end_date < start_date:
        return 0
    days = 0
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            days += 1
        cursor += timedelta(days=1)
    return days


@dataclass(frozen=True)
class TimeSeriesDefinition:
    id: str
    label: str
    block: str
    provider: str
    source_kind: str
    feed: str
    symbol: str
    url: str
    unit: str
    method: str
    report_role: str
    confidence: str
    legal_note: str


YAHOO_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


TIME_SERIES_DEFINITIONS: tuple[TimeSeriesDefinition, ...] = (
    TimeSeriesDefinition(
        id="spx",
        label="SPX",
        block="LEV / HSBC",
        provider="Yahoo Finance",
        source_kind="public_proxy",
        feed="yahoo",
        symbol="^GSPC",
        url="https://finance.yahoo.com/quote/%5EGSPC/history/",
        unit="price_index",
        method="Yahoo chart API, daily close",
        report_role="Equities factor and HSBC public proxy",
        confidence="proxy_public",
        legal_note="Operational public proxy; confirm terms before redistribution.",
    ),
    TimeSeriesDefinition(
        id="ibov",
        label="IBOV",
        block="LEV",
        provider="Yahoo Finance / B3 reference",
        source_kind="public_proxy",
        feed="yahoo",
        symbol="^BVSP",
        url="https://finance.yahoo.com/quote/%5EBVSP/history/",
        unit="price_index",
        method="Yahoo chart API, daily close; B3 remains official reference",
        report_role="Brazil equity benchmark factor",
        confidence="proxy_public",
        legal_note="Use B3 licensed feeds for official production redistribution.",
    ),
    TimeSeriesDefinition(
        id="usdbrl",
        label="USD/BRL",
        block="LEV",
        provider="Yahoo Finance",
        source_kind="public_proxy",
        feed="yahoo",
        symbol="USDBRL=X",
        url="https://finance.yahoo.com/quote/USDBRL%3DX/history/",
        unit="fx_rate",
        method="Yahoo chart API, daily close",
        report_role="Dollar factor",
        confidence="proxy_public",
        legal_note="Operational public proxy; validate against an official FX source if needed.",
    ),
    TimeSeriesDefinition(
        id="brent",
        label="Brent",
        block="LEV / HSBC",
        provider="Yahoo Finance / EIA reference",
        source_kind="public_proxy",
        feed="yahoo",
        symbol="BZ=F",
        url="https://finance.yahoo.com/quote/BZ%3DF/history/",
        unit="commodity_price",
        method="Yahoo chart API, daily close; EIA spot Brent remains official public check",
        report_role="Oil factor and HSBC commodities proxy",
        confidence="proxy_public",
        legal_note="Futures proxy; compare with EIA spot series for official checks.",
    ),
    TimeSeriesDefinition(
        id="gold",
        label="Gold",
        block="LEV",
        provider="Yahoo Finance",
        source_kind="public_proxy",
        feed="yahoo",
        symbol="GC=F",
        url="https://finance.yahoo.com/quote/GC%3DF/history/",
        unit="commodity_price",
        method="Yahoo chart API, daily close",
        report_role="Gold factor",
        confidence="proxy_public",
        legal_note="Futures proxy; contract rolls can affect the level series.",
    ),
    TimeSeriesDefinition(
        id="t2y",
        label="T2Y",
        block="LEV / HSBC",
        provider="FRED",
        source_kind="official_public",
        feed="fred",
        symbol="DGS2",
        url="https://fred.stlouisfed.org/series/DGS2",
        unit="yield_pct",
        method="FRED observations API when FRED_API_KEY is configured",
        report_role="US Treasury 2Y yield factor",
        confidence="official_public",
        legal_note="FRED API can require a key and some third-party series carry restrictions.",
    ),
    TimeSeriesDefinition(
        id="t5y",
        label="T5Y",
        block="LEV / HSBC",
        provider="FRED",
        source_kind="official_public",
        feed="fred",
        symbol="DGS5",
        url="https://fred.stlouisfed.org/series/DGS5",
        unit="yield_pct",
        method="FRED observations API when FRED_API_KEY is configured",
        report_role="US Treasury 5Y yield factor / T5Y ambiguity check",
        confidence="official_public",
        legal_note="FRED API can require a key and some third-party series carry restrictions.",
    ),
    TimeSeriesDefinition(
        id="t10y",
        label="T10Y",
        block="LEV / HSBC",
        provider="FRED",
        source_kind="official_public",
        feed="fred",
        symbol="DGS10",
        url="https://fred.stlouisfed.org/series/DGS10",
        unit="yield_pct",
        method="FRED observations API when FRED_API_KEY is configured",
        report_role="US Treasury 10Y yield factor",
        confidence="official_public",
        legal_note="FRED API can require a key and some third-party series carry restrictions.",
    ),
    TimeSeriesDefinition(
        id="b5y",
        label="B5Y",
        block="LEV",
        provider="FRED",
        source_kind="official_public",
        feed="fred",
        symbol="T5YIE",
        url="https://fred.stlouisfed.org/series/T5YIE",
        unit="yield_pct",
        method="FRED observations API when FRED_API_KEY is configured",
        report_role="5Y breakeven candidate for B5Y/BE5Y ambiguity",
        confidence="official_public",
        legal_note="FRED API can require a key and some third-party series carry restrictions.",
    ),
)


REPORT_SOURCE_INVENTORY: tuple[dict[str, Any], ...] = (
    {
        "id": "cvm_inf_diario",
        "label": "CVM Informe Diario FI",
        "provider": "CVM",
        "kind": "official_public",
        "role": "Cotas, PL, captacao, resgate e cotistas dos fundos",
        "url": "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/",
        "access": "ZIP CSV mensal/anual",
        "collection": "configured_source",
    },
    {
        "id": "cvm_fund_registry",
        "label": "CVM Registro Fundo Classe",
        "provider": "CVM",
        "kind": "official_public",
        "role": "Universo e status cadastral de fundos/classes",
        "url": "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip",
        "access": "ZIP CSV",
        "collection": "configured_source",
    },
    {
        "id": "anbima_ima",
        "label": "ANBIMA IRF-M / IMA-B",
        "provider": "ANBIMA",
        "kind": "official_or_authenticated",
        "role": "Indices de renda fixa usados como fatores",
        "url": "https://data.anbima.com.br/indices/consulta/ima/resultados-diarios/irf-m",
        "access": "Pagina publica XLS ou API autenticada",
        "collection": "configured_source",
    },
    {
        "id": "b3_ibov",
        "label": "B3 Ibovespa",
        "provider": "B3",
        "kind": "official_or_licensed",
        "role": "Referencia oficial do IBOV",
        "url": "https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-amplos/indice-ibovespa-ibovespa-estatisticas-historicas.htm",
        "access": "Pagina publica / Datawise+ contratado",
        "collection": "validated_by_proxy",
    },
    {
        "id": "fred_yields",
        "label": "FRED Yields / Breakeven",
        "provider": "FRED",
        "kind": "official_public",
        "role": "Treasuries 2Y/5Y/10Y e breakeven 5Y",
        "url": "https://fred.stlouisfed.org/",
        "access": "API com chave; CSV publico como fallback",
        "collection": "active_time_series",
    },
    {
        "id": "yahoo_market",
        "label": "Yahoo Market History",
        "provider": "Yahoo Finance",
        "kind": "public_proxy",
        "role": "SPX, IBOV proxy, USD/BRL, Brent e Gold",
        "url": "https://finance.yahoo.com/",
        "access": "Chart API publica nao oficial",
        "collection": "active_time_series",
    },
    {
        "id": "eia_brent",
        "label": "EIA Brent Spot",
        "provider": "EIA",
        "kind": "official_public",
        "role": "Validacao publica do Brent spot",
        "url": "https://www.eia.gov/dnav/pet/hist/RBRTED.htm",
        "access": "XLS/CSV publico",
        "collection": "configured_source",
    },
    {
        "id": "hsbc_private",
        "label": "HSBC / Macrobond / Bloomberg / CEIC",
        "provider": "HSBC + vendors",
        "kind": "proprietary",
        "role": "Forecasts, cenarios e series proprietarias do relatorio HSBC",
        "url": "https://www.research.hsbc.com/",
        "access": "Contrato/licenca",
        "collection": "not_reproducible_publicly",
    },
)


class ReportSourceDiscoveryService:
    """Collect and summarize public/proxy sources named in the external report."""

    def __init__(self, root_dir: str | None = None, timeout_seconds: float | None = None) -> None:
        self.root_dir = root_dir or os.path.join(Config.MACRO_DATA_DIR, "report_sources")
        self.series_dir = os.path.join(self.root_dir, "series")
        self.latest_path = os.path.join(self.root_dir, "latest.json")
        self.snapshots_path = os.path.join(self.root_dir, "snapshots.jsonl")
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else getattr(Config, "MACRO_REPORT_SOURCES_TIMEOUT_SECONDS", 12)
        )
        self._lock = threading.RLock()
        os.makedirs(self.series_dir, exist_ok=True)

    def get_panel(self, *, refresh: bool = False, lookback_days: int | None = None) -> dict[str, Any]:
        resolved_lookback = self._resolve_lookback_days(lookback_days)
        if refresh:
            return self.collect(lookback_days=resolved_lookback, force=True)

        snapshot = self._read_latest()
        if snapshot and int(snapshot.get("lookback_days") or 0) >= resolved_lookback:
            return snapshot

        return self.collect(lookback_days=resolved_lookback, force=False)

    def collect(self, *, lookback_days: int | None = None, force: bool = False) -> dict[str, Any]:
        resolved_lookback = self._resolve_lookback_days(lookback_days)
        with self._lock:
            if not force:
                cached = self._fresh_cached_snapshot(resolved_lookback)
                if cached is not None:
                    return cached

            started_at = _utc_now()
            end_date = _local_now().date()
            start_date = end_date - timedelta(days=resolved_lookback)

            series_payload: list[dict[str, Any]] = []
            status_payload: list[dict[str, Any]] = []
            for definition in TIME_SERIES_DEFINITIONS:
                fetched_at = _utc_now()
                started = time.monotonic()
                error = None
                points: list[dict[str, Any]] = []
                try:
                    if definition.feed == "yahoo":
                        points = self._fetch_yahoo(definition, start_date=start_date, end_date=end_date)
                    elif definition.feed == "fred":
                        points = self._fetch_fred(definition, start_date=start_date, end_date=end_date)
                    else:
                        error = f"Unsupported feed: {definition.feed}"
                except Exception as exc:
                    logger.warning("Report source collection failed for %s: %s", definition.id, exc)
                    error = str(exc)

                points = self._dedupe_points(points)
                summary = self._summarize_series(definition, points, start_date=start_date, end_date=end_date)
                latency_ms = int((time.monotonic() - started) * 1000)
                source_status = {
                    "id": definition.id,
                    "label": definition.label,
                    "provider": definition.provider,
                    "ok": bool(points),
                    "error": error,
                    "points": len(points),
                    "latency_ms": latency_ms,
                    "fetched_at": fetched_at.isoformat(),
                    "latest_observation_date": summary.get("latest_date"),
                }
                item = {
                    **self._definition_payload(definition),
                    "status": "ok" if points else "error",
                    "error": error,
                    "points": points,
                    "summary": summary,
                    "fetched_at": fetched_at.isoformat(),
                    "latency_ms": latency_ms,
                }
                series_payload.append(item)
                status_payload.append(source_status)
                atomic_json_dump(os.path.join(self.series_dir, f"{definition.id}.json"), item, indent=2)

            ok_count = sum(1 for item in status_payload if item.get("ok"))
            panel = {
                "ok": ok_count > 0,
                "generated_at": _now_iso(),
                "started_at": started_at.isoformat(),
                "completed_at": _now_iso(),
                "lookback_days": resolved_lookback,
                "window": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "business_days": _business_days(start_date, end_date),
                },
                "model": {
                    "id": "report_source_discovery_v1",
                    "label": "LEV/HSBC public source monitor",
                    "notes": [
                        "30d base uses public or operational proxies where official feeds require licensing.",
                        "FRED yield series use the API when FRED_API_KEY is configured.",
                        "CVM/ANBIMA/B3/EIA are tracked in the source inventory for the full LEV pipeline.",
                    ],
                },
                "series": series_payload,
                "sources": list(REPORT_SOURCE_INVENTORY),
                "source_status": status_payload,
                "coverage": {
                    "series_total": len(status_payload),
                    "series_ok": ok_count,
                    "series_error": len(status_payload) - ok_count,
                    "official_public_total": sum(1 for item in REPORT_SOURCE_INVENTORY if item.get("kind") == "official_public"),
                    "active_series_total": len(TIME_SERIES_DEFINITIONS),
                },
            }

            atomic_json_dump(self.latest_path, panel, indent=2)
            self._append_snapshot_summary(panel)
            return panel

    def _resolve_lookback_days(self, value: int | None) -> int:
        default_days = int(getattr(Config, "MACRO_REPORT_SOURCES_LOOKBACK_DAYS", 30))
        try:
            days = int(value if value is not None else default_days)
        except Exception:
            days = default_days
        return max(30, min(days, 180))

    def _fresh_cached_snapshot(self, lookback_days: int) -> dict[str, Any] | None:
        snapshot = self._read_latest()
        if not snapshot:
            return None
        if int(snapshot.get("lookback_days") or 0) < lookback_days:
            return None
        generated_at = _parse_iso(snapshot.get("generated_at"))
        if not generated_at:
            return None
        max_age_seconds = int(getattr(Config, "MACRO_REPORT_SOURCES_CACHE_SECONDS", 900))
        if (_utc_now() - generated_at).total_seconds() > max_age_seconds:
            return None
        return snapshot

    def _read_latest(self) -> dict[str, Any] | None:
        try:
            with open(self.latest_path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except FileNotFoundError:
            return None
        except Exception:
            logger.exception("Failed to read report source latest snapshot")
            return None

    def _fetch_yahoo(
        self,
        definition: TimeSeriesDefinition,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        start_dt = datetime.combine(start_date - timedelta(days=5), dt_time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(end_date + timedelta(days=2), dt_time.min, tzinfo=timezone.utc)
        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{quote(definition.symbol, safe='')}"
            f"?period1={int(start_dt.timestamp())}"
            f"&period2={int(end_dt.timestamp())}"
            "&interval=1d&events=history&includeAdjustedClose=true"
        )
        response = requests.get(
            url,
            timeout=self.timeout_seconds,
            headers={"User-Agent": YAHOO_USER_AGENT, "Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        chart = payload.get("chart") or {}
        if chart.get("error"):
            raise RuntimeError(str(chart.get("error")))
        results = chart.get("result") or []
        if not results:
            return []
        result = results[0]
        timestamps = result.get("timestamp") or []
        quote_payload = (((result.get("indicators") or {}).get("quote") or [{}])[0]) or {}
        adj_payload = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]) or {}
        closes = adj_payload.get("adjclose") or quote_payload.get("close") or []
        opens = quote_payload.get("open") or []
        highs = quote_payload.get("high") or []
        lows = quote_payload.get("low") or []
        volumes = quote_payload.get("volume") or []

        rows: list[dict[str, Any]] = []
        for idx, raw_ts in enumerate(timestamps):
            value = _safe_float(closes[idx] if idx < len(closes) else None)
            if value is None:
                continue
            day = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc).date()
            if day < start_date or day > end_date:
                continue
            rows.append(
                {
                    "date": day.isoformat(),
                    "value": round(value, 8),
                    "open": _round(opens[idx] if idx < len(opens) else None, 8),
                    "high": _round(highs[idx] if idx < len(highs) else None, 8),
                    "low": _round(lows[idx] if idx < len(lows) else None, 8),
                    "volume": _round(volumes[idx] if idx < len(volumes) else None, 0),
                    "source": "yahoo_chart",
                }
            )
        return rows

    def _fetch_fred(
        self,
        definition: TimeSeriesDefinition,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        api_key = (
            os.environ.get("FRED_API_KEY")
            or os.environ.get("STLOUISFED_API_KEY")
            or getattr(Config, "FRED_API_KEY", "")
        )
        if api_key:
            return self._fetch_fred_api(
                definition,
                start_date=start_date,
                end_date=end_date,
                api_key=str(api_key),
            )
        if not bool(getattr(Config, "MACRO_REPORT_SOURCES_FRED_CSV_FALLBACK", False)):
            raise RuntimeError("FRED_API_KEY ausente; configure a chave para coletar yields e breakeven.")
        return self._fetch_fred_csv(definition, start_date=start_date, end_date=end_date)

    def _fetch_fred_api(
        self,
        definition: TimeSeriesDefinition,
        *,
        start_date: date,
        end_date: date,
        api_key: str,
    ) -> list[dict[str, Any]]:
        url = "https://api.stlouisfed.org/fred/series/observations"
        response = requests.get(
            url,
            params={
                "series_id": definition.symbol,
                "api_key": api_key,
                "file_type": "json",
                "observation_start": start_date.isoformat(),
                "observation_end": end_date.isoformat(),
                "sort_order": "asc",
            },
            timeout=self.timeout_seconds,
            headers={"User-Agent": YAHOO_USER_AGENT},
        )
        response.raise_for_status()
        payload = response.json()
        observations = payload.get("observations") or []
        rows: list[dict[str, Any]] = []
        for observation in observations:
            value = _safe_float(observation.get("value"))
            raw_date = str(observation.get("date") or "")[:10]
            if value is None or not raw_date:
                continue
            rows.append({"date": raw_date, "value": round(value, 8), "source": "fred_api"})
        return rows

    def _fetch_fred_csv(
        self,
        definition: TimeSeriesDefinition,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        url = (
            "https://fred.stlouisfed.org/graph/fredgraph.csv"
            f"?id={quote(definition.symbol)}&cosd={start_date.isoformat()}&coed={end_date.isoformat()}"
        )
        response = requests.get(
            url,
            timeout=min(self.timeout_seconds, 10),
            headers={"User-Agent": YAHOO_USER_AGENT, "Accept": "text/csv,*/*"},
        )
        response.raise_for_status()
        reader = csv.DictReader(StringIO(response.text))
        rows: list[dict[str, Any]] = []
        value_column = definition.symbol
        for row in reader:
            raw_date = (row.get("observation_date") or row.get("DATE") or row.get("date") or "")[:10]
            value = _safe_float(row.get(value_column) or row.get(definition.symbol.upper()))
            if value is None or not raw_date:
                continue
            try:
                day = date.fromisoformat(raw_date)
            except Exception:
                continue
            if start_date <= day <= end_date:
                rows.append({"date": day.isoformat(), "value": round(value, 8), "source": "fred_csv"})
        return rows

    @staticmethod
    def _dedupe_points(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_date: dict[str, dict[str, Any]] = {}
        for point in points:
            day = str(point.get("date") or "")[:10]
            value = _safe_float(point.get("value"))
            if not day or value is None:
                continue
            item = dict(point)
            item["date"] = day
            item["value"] = round(value, 8)
            by_date[day] = item
        return [by_date[key] for key in sorted(by_date)]

    def _summarize_series(
        self,
        definition: TimeSeriesDefinition,
        points: list[dict[str, Any]],
        *,
        start_date: date,
        end_date: date,
    ) -> dict[str, Any]:
        clean = [point for point in points if _safe_float(point.get("value")) is not None]
        expected_days = max(_business_days(start_date, end_date), 1)
        if not clean:
            return {
                "latest_date": None,
                "latest_value": None,
                "previous_value": None,
                "change_1d": None,
                "change_1d_pct": None,
                "change_window": None,
                "change_window_pct": None,
                "volatility": None,
                "coverage_ratio": 0,
                "observation_count": 0,
                "expected_business_days": expected_days,
                "sparkline": [],
            }

        values = [_safe_float(point.get("value")) for point in clean]
        values = [value for value in values if value is not None]
        latest = clean[-1]
        first = clean[0]
        previous = clean[-2] if len(clean) > 1 else None
        latest_value = _safe_float(latest.get("value"))
        first_value = _safe_float(first.get("value"))
        previous_value = _safe_float(previous.get("value")) if previous else None

        if definition.unit == "yield_pct":
            change_1d = None if latest_value is None or previous_value is None else (latest_value - previous_value) * 100.0
            change_window = None if latest_value is None or first_value is None else (latest_value - first_value) * 100.0
            daily_moves = [
                (values[idx] - values[idx - 1]) * 100.0
                for idx in range(1, len(values))
                if values[idx] is not None and values[idx - 1] is not None
            ]
            change_1d_pct = None
            change_window_pct = None
        else:
            change_1d = None if latest_value is None or previous_value in (None, 0) else latest_value - previous_value
            change_window = None if latest_value is None or first_value is None else latest_value - first_value
            change_1d_pct = None if latest_value is None or previous_value in (None, 0) else (latest_value / previous_value - 1.0) * 100.0
            change_window_pct = None if latest_value is None or first_value in (None, 0) else (latest_value / first_value - 1.0) * 100.0
            daily_moves = [
                (values[idx] / values[idx - 1] - 1.0) * 100.0
                for idx in range(1, len(values))
                if values[idx] is not None and values[idx - 1] not in (None, 0)
            ]

        volatility = statistics.pstdev(daily_moves) if len(daily_moves) > 1 else None
        coverage_ratio = min(len(clean) / expected_days, 1.0)
        latest_date = str(latest.get("date") or "")[:10]
        stale_days = None
        try:
            stale_days = (end_date - date.fromisoformat(latest_date)).days
        except Exception:
            pass

        return {
            "latest_date": latest_date,
            "latest_value": _round(latest_value, 6),
            "previous_value": _round(previous_value, 6),
            "change_1d": _round(change_1d, 4),
            "change_1d_pct": _round(change_1d_pct, 4),
            "change_window": _round(change_window, 4),
            "change_window_pct": _round(change_window_pct, 4),
            "volatility": _round(volatility, 4),
            "coverage_ratio": _round(coverage_ratio, 4),
            "observation_count": len(clean),
            "expected_business_days": expected_days,
            "stale_days": stale_days,
            "sparkline": [
                {
                    "date": point.get("date"),
                    "value": _round(point.get("value"), 6),
                }
                for point in clean[-45:]
            ],
        }

    @staticmethod
    def _definition_payload(definition: TimeSeriesDefinition) -> dict[str, Any]:
        return {
            "id": definition.id,
            "label": definition.label,
            "block": definition.block,
            "provider": definition.provider,
            "source_kind": definition.source_kind,
            "feed": definition.feed,
            "symbol": definition.symbol,
            "url": definition.url,
            "unit": definition.unit,
            "method": definition.method,
            "report_role": definition.report_role,
            "confidence": definition.confidence,
            "legal_note": definition.legal_note,
        }

    def _append_snapshot_summary(self, panel: dict[str, Any]) -> None:
        summary = {
            "generated_at": panel.get("generated_at"),
            "lookback_days": panel.get("lookback_days"),
            "coverage": panel.get("coverage"),
            "series": [
                {
                    "id": item.get("id"),
                    "latest_date": (item.get("summary") or {}).get("latest_date"),
                    "latest_value": (item.get("summary") or {}).get("latest_value"),
                    "status": item.get("status"),
                }
                for item in panel.get("series") or []
            ],
        }
        os.makedirs(os.path.dirname(self.snapshots_path), exist_ok=True)
        with open(self.snapshots_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(summary, ensure_ascii=False) + "\n")


class ReportSourceDiscoveryManager:
    _instance: "ReportSourceDiscoveryManager | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self.service = ReportSourceDiscoveryService()
        self.root_dir = self.service.root_dir
        self.state_path = os.path.join(self.root_dir, "collector_status.json")
        self._runtime_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        os.makedirs(self.root_dir, exist_ok=True)

    @classmethod
    def get_instance(cls) -> "ReportSourceDiscoveryManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def start(self) -> dict[str, Any]:
        with self._runtime_lock:
            if self._thread and self._thread.is_alive():
                self._save_status(desired_running=True, running=True)
                return self.status()
            self._stop_event = threading.Event()
            self._thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="report-source-discovery-daily",
            )
            self._thread.start()
            self._save_status(
                desired_running=True,
                running=True,
                last_started_at=_now_iso(),
                stopped_reason=None,
                last_error=None,
            )
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._runtime_lock:
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=2)
            if self._thread and not self._thread.is_alive():
                self._thread = None
            self._save_status(
                desired_running=False,
                running=False,
                stopped_reason="manual_stop",
            )
            return self.status()

    def status(self) -> dict[str, Any]:
        state = self._read_status()
        running = bool(self._thread and self._thread.is_alive())
        state.update(
            {
                "enabled": bool(getattr(Config, "MACRO_REPORT_SOURCES_ENABLE", True)),
                "auto_start": bool(getattr(Config, "MACRO_REPORT_SOURCES_AUTO_START", True)),
                "running": running,
                "update_time": str(getattr(Config, "MACRO_REPORT_SOURCES_UPDATE_TIME", "07:30")),
                "lookback_days": int(getattr(Config, "MACRO_REPORT_SOURCES_LOOKBACK_DAYS", 30)),
                "next_run_at": self._next_run_at(_local_now()).astimezone(timezone.utc).isoformat(),
                "latest_snapshot_at": self._latest_snapshot_at(),
            }
        )
        return state

    def resume_if_needed(self) -> dict[str, Any]:
        state = self._read_status()
        should_run = bool(getattr(Config, "MACRO_REPORT_SOURCES_ENABLE", True)) and (
            bool(getattr(Config, "MACRO_REPORT_SOURCES_AUTO_START", True))
            or bool(state.get("desired_running"))
        )
        if should_run:
            return self.start()
        return self.status()

    def collect_once(self, *, force: bool = True, lookback_days: int | None = None) -> dict[str, Any]:
        self._save_status(last_started_at=_now_iso(), last_error=None)
        try:
            panel = self.service.collect(lookback_days=lookback_days, force=force)
            self._save_status(
                last_completed_at=panel.get("completed_at"),
                last_success_at=panel.get("completed_at") if panel.get("ok") else None,
                last_error=None if panel.get("ok") else "No source returned data.",
                run_count=int(self._read_status().get("run_count") or 0) + 1,
            )
            return panel
        except Exception as exc:
            logger.exception("Report source daily collection failed")
            self._save_status(
                last_completed_at=_now_iso(),
                last_error=str(exc),
                run_count=int(self._read_status().get("run_count") or 0) + 1,
            )
            raise

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                if self._due_to_collect():
                    self.collect_once(force=True)
            except Exception:
                logger.exception("Report source collector iteration failed")

            sleep_seconds = self._seconds_until_next_check()
            if self._stop_event.wait(sleep_seconds):
                break

        self._save_status(running=False, stopped_reason="loop_stopped")

    def _due_to_collect(self) -> bool:
        latest_snapshot = self._latest_snapshot_at()
        if latest_snapshot is None:
            return True

        now = _local_now()
        update_time = self._configured_update_time()
        due_today = now.time() >= update_time
        latest_local_date = latest_snapshot.astimezone(LOCAL_TZ).date()
        return due_today and latest_local_date < now.date()

    def _seconds_until_next_check(self) -> float:
        now = _local_now()
        next_run = self._next_run_at(now)
        seconds = max((next_run - now).total_seconds(), 60.0)
        return min(seconds, 3600.0)

    def _next_run_at(self, now: datetime) -> datetime:
        update_time = self._configured_update_time()
        today_run = datetime.combine(now.date(), update_time, tzinfo=LOCAL_TZ)
        if now < today_run:
            return today_run
        return today_run + timedelta(days=1)

    @staticmethod
    def _configured_update_time() -> dt_time:
        raw = str(getattr(Config, "MACRO_REPORT_SOURCES_UPDATE_TIME", "07:30") or "07:30")
        try:
            hour_text, minute_text = raw.split(":", 1)
            return dt_time(hour=max(0, min(int(hour_text), 23)), minute=max(0, min(int(minute_text[:2]), 59)))
        except Exception:
            return dt_time(hour=7, minute=30)

    def _latest_snapshot_at(self) -> datetime | None:
        snapshot = self.service._read_latest()
        return _parse_iso(snapshot.get("generated_at")) if snapshot else None

    def _read_status(self) -> dict[str, Any]:
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                state = json.load(handle)
        except FileNotFoundError:
            state = {}
        except Exception:
            logger.exception("Failed to read report source collector status")
            state = {}
        return {
            "desired_running": False,
            "running": False,
            "run_count": 0,
            "last_started_at": None,
            "last_completed_at": None,
            "last_success_at": None,
            "last_error": None,
            "stopped_reason": None,
            **(state or {}),
        }

    def _save_status(self, **fields: Any) -> None:
        state = self._read_status()
        for key, value in fields.items():
            if value is not None or key in {"last_error", "stopped_reason"}:
                state[key] = value
        state["updated_at"] = _now_iso()
        atomic_json_dump(self.state_path, state, indent=2)
