from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import pandas as pd

from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .market_screen_chart_service import MarketScreenChartService, _safe_float

logger = get_logger("aquiles.macro_curve_discovery")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")


@dataclass(frozen=True)
class CurveVertex:
    symbol: str
    label: str
    tenor_years: float


@dataclass(frozen=True)
class CurveDefinition:
    key: str
    label: str
    short_label: str
    color: str
    vertices: tuple[CurveVertex, ...]


CURVE_DEFINITIONS: dict[str, CurveDefinition] = {
    "ois": CurveDefinition(
        key="ois",
        label="OIS USD",
        short_label="OIS",
        color="#38bdf8",
        vertices=(
            CurveVertex("USSO1", "1Y", 1.0),
            CurveVertex("USSO2", "2Y", 2.0),
            CurveVertex("USSO5", "5Y", 5.0),
            CurveVertex("USSO10", "10Y", 10.0),
        ),
    ),
    "treasury": CurveDefinition(
        key="treasury",
        label="Treasury USD",
        short_label="UST",
        color="#f59e0b",
        vertices=(
            CurveVertex("USGG2YR", "2Y", 2.0),
            CurveVertex("USGG5YR", "5Y", 5.0),
            CurveVertex("USGG10YR", "10Y", 10.0),
            CurveVertex("USGG30YR", "30Y", 30.0),
        ),
    ),
    "di": CurveDefinition(
        key="di",
        label="DI Brasil",
        short_label="DI",
        color="#22c55e",
        vertices=(
            CurveVertex("ODF27", "Jan27", 1.0),
            CurveVertex("ODF28", "Jan28", 2.0),
            CurveVertex("ODF29", "Jan29", 3.0),
            CurveVertex("ODF30", "Jan30", 4.0),
            CurveVertex("ODF31", "Jan31", 5.0),
            CurveVertex("ODF32", "Jan32", 6.0),
            CurveVertex("ODF33", "Jan33", 7.0),
            CurveVertex("ODF35", "Jan35", 9.0),
        ),
    ),
    "br_inflation": CurveDefinition(
        key="br_inflation",
        label="Inflacao Imp BR",
        short_label="BRII",
        color="#f472b6",
        vertices=(
            CurveVertex(".BRII1Y", "1Y", 1.0),
            CurveVertex(".BRII2Y", "2Y", 2.0),
            CurveVertex(".BRII5Y", "5Y", 5.0),
            CurveVertex(".BRII10Y", "10Y", 10.0),
        ),
    ),
}


ALL_CURVE_SYMBOLS = {
    vertex.symbol
    for definition in CURVE_DEFINITIONS.values()
    for vertex in definition.vertices
}


SHAPE_LABELS: dict[str, dict[str, str]] = {
    "neutral": {
        "label": "Sem shape dominante",
        "tone": "neutral",
        "meaning": "A curva esta sem deslocamento direcional suficiente no nivel ou na inclinacao.",
        "risk_read": "Sinal baixo; melhor esperar confirmacao de preco ou volume.",
    },
    "bull_steepening": {
        "label": "Bull steepening",
        "tone": "constructive",
        "meaning": "O nivel cai enquanto a inclinacao aumenta; a ponta curta alivia mais que a longa.",
        "risk_read": "Costuma sugerir alivio de risco/cortes no curto prazo, com premio longo ainda preservado.",
    },
    "bull_flattening": {
        "label": "Bull flattening",
        "tone": "defensive",
        "meaning": "O nivel cai e a inclinacao diminui; a ponta longa cede mais que a curta.",
        "risk_read": "Pode indicar busca por duration, queda de premio de prazo ou leitura de desaceleracao.",
    },
    "bear_steepening": {
        "label": "Bear steepening",
        "tone": "risk",
        "meaning": "O nivel sobe e a inclinacao aumenta; a ponta longa abre mais que a curta.",
        "risk_read": "Sinal classico de premio de risco/inflacao/term premium pressionando a parte longa.",
    },
    "bear_flattening": {
        "label": "Bear flattening",
        "tone": "tightening",
        "meaning": "O nivel sobe e a inclinacao diminui; a ponta curta abre mais que a longa.",
        "risk_read": "Costuma apontar aperto de politica monetaria ou stress concentrado no curto prazo.",
    },
    "bull_parallel": {
        "label": "Bull parallel",
        "tone": "constructive",
        "meaning": "A curva desloca para baixo com pouca mudanca de inclinacao.",
        "risk_read": "Alivio amplo de juros/premio, mas sem mensagem forte de shape.",
    },
    "bear_parallel": {
        "label": "Bear parallel",
        "tone": "risk",
        "meaning": "A curva desloca para cima com pouca mudanca de inclinacao.",
        "risk_read": "Reprecificacao ampla de juros/premio, sem concentracao clara por prazo.",
    },
    "steepening": {
        "label": "Steepening puro",
        "tone": "watch",
        "meaning": "A inclinacao aumenta sem deslocamento relevante do nivel medio.",
        "risk_read": "Observe se a longa esta puxando premio ou se a curta esta aliviando.",
    },
    "flattening": {
        "label": "Flattening puro",
        "tone": "watch",
        "meaning": "A inclinacao diminui sem deslocamento relevante do nivel medio.",
        "risk_read": "Observe se o movimento vem de duration longa ou pressao de curto prazo.",
    },
}


class MacroCurveDiscoveryService:
    """Build the Discovery curve widget payload from W32 screen-capture rows."""

    def __init__(
        self,
        chart_service: Optional[MarketScreenChartService] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.chart_service = chart_service or MarketScreenChartService()
        self._llm_client = llm_client
        self._cache_lock = threading.RLock()
        self._curve_frame_cache: dict[tuple[Any, ...], pd.DataFrame] = {}

    @property
    def llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def build_payload(
        self,
        *,
        curves: Optional[list[str]] = None,
        lookback_minutes: int = 720,
        max_points: int = 720,
        include_shape_points: bool = True,
        session_date: str | None = None,
    ) -> dict[str, Any]:
        selected_keys = self._normalize_curve_keys(curves)
        resolved_lookback = max(60, min(int(lookback_minutes or 720), 1440))
        resolved_max_points = max(60, min(int(max_points or 720), 1440))

        frame = self._load_curve_history_frame(
            selected_keys=selected_keys,
            lookback_minutes=resolved_lookback,
            session_date=session_date,
        )
        if frame.empty:
            return self._empty_payload(
                selected_keys=selected_keys,
                reason="Nenhum historico W32 encontrado para a janela solicitada.",
            )

        frame = self._clean_history_frame(frame)
        session_frame, resolved_session_date = self._session_frame(frame, session_date=session_date)
        if session_frame.empty:
            return self._empty_payload(
                selected_keys=selected_keys,
                reason="Nenhum dado encontrado para a sessao selecionada.",
            )

        assets = self._latest_assets_payload()

        curve_payloads = [
            self._build_curve_payload(
                definition=CURVE_DEFINITIONS[key],
                frame=session_frame,
                max_points=resolved_max_points,
                include_shape_points=include_shape_points,
            )
            for key in selected_keys
        ]

        latest_capture_at = session_frame["captured_at"].max()
        return {
            "ok": True,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latest_capture_at": latest_capture_at.isoformat()
            if isinstance(latest_capture_at, datetime)
            else None,
            "session_date": resolved_session_date,
            "sample_interval_minutes": 1,
            "selected_curves": selected_keys,
            "available_curves": self._curve_options(),
            "model": {
                "id": "log_tenor_wls",
                "label": "Regressao geometrica de prazo",
                "description": (
                    "Inclination is the beta of yield versus ln(tenor_years), in bp per log-year. "
                    "This keeps 1Y-2Y, 2Y-5Y and 5Y-10Y comparable on a geometric maturity scale."
                ),
                "shape_threshold_bp": 1.5,
                "level_threshold_bp": 1.5,
            },
            "curves": curve_payloads,
            "assets": assets,
        }

    def build_ai_view(
        self,
        *,
        curves: Optional[list[str]] = None,
        lookback_minutes: int = 720,
        session_date: str | None = None,
    ) -> dict[str, Any]:
        payload = self.build_payload(
            curves=curves,
            lookback_minutes=lookback_minutes,
            max_points=360,
            include_shape_points=True,
            session_date=session_date,
        )
        analysis = self._build_ai_commentary(payload)
        return {
            "ok": bool(payload.get("ok")),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "panel_generated_at": payload.get("generated_at"),
            "session_date": payload.get("session_date"),
            "analysis": analysis,
        }

    def _empty_payload(self, *, selected_keys: list[str], reason: str) -> dict[str, Any]:
        return {
            "ok": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "session_date": None,
            "sample_interval_minutes": 1,
            "selected_curves": selected_keys,
            "available_curves": self._curve_options(),
            "model": {
                "id": "log_tenor_wls",
                "label": "Regressao geometrica de prazo",
                "description": "Inclination is the beta of yield versus ln(tenor_years).",
                "shape_threshold_bp": 1.5,
                "level_threshold_bp": 1.5,
            },
            "curves": [],
            "assets": [],
        }

    def _normalize_curve_keys(self, curves: Optional[list[str]]) -> list[str]:
        if not curves:
            return ["ois", "treasury", "di", "br_inflation"]
        selected: list[str] = []
        aliases = {
            "inflacao": "br_inflation",
            "inflation": "br_inflation",
            "inflacao_imp_br": "br_inflation",
            "brii": "br_inflation",
            "ust": "treasury",
        }
        for raw_key in curves:
            key = str(raw_key or "").strip().lower()
            key = aliases.get(key, key)
            if key in CURVE_DEFINITIONS and key not in selected:
                selected.append(key)
        return selected or ["ois", "treasury", "di", "br_inflation"]

    def _curve_options(self) -> list[dict[str, Any]]:
        return [
            {
                "key": definition.key,
                "label": definition.label,
                "short_label": definition.short_label,
                "color": definition.color,
                "vertices": [
                    {
                        "symbol": vertex.symbol,
                        "label": vertex.label,
                        "tenor_years": vertex.tenor_years,
                    }
                    for vertex in definition.vertices
                ],
            }
            for definition in CURVE_DEFINITIONS.values()
        ]

    def _load_curve_history_frame(
        self,
        *,
        selected_keys: list[str],
        lookback_minutes: int,
        session_date: str | None,
    ) -> pd.DataFrame:
        target_date = self._target_session_date(session_date)
        symbols = {
            vertex.symbol
            for key in selected_keys
            for vertex in CURVE_DEFINITIONS[key].vertices
        }
        variant_map = self._symbol_variant_map(symbols)
        explicit_session_date = bool(str(session_date or "").strip())
        if explicit_session_date:
            session_start = datetime.combine(target_date, datetime.min.time(), tzinfo=LOCAL_TZ)
            session_end = session_start + timedelta(days=1)
            cutoff = session_start.astimezone(timezone.utc)
            upper_cutoff = session_end.astimezone(timezone.utc)
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=max(lookback_minutes, 60))
            upper_cutoff = None

        store_frame = self._load_curve_history_frame_from_store(
            symbols=symbols,
            variant_map=variant_map,
            cutoff=cutoff,
            upper_cutoff=upper_cutoff,
            lookback_minutes=lookback_minutes,
            target_date=target_date,
            explicit_session_date=explicit_session_date,
        )
        if store_frame is not None:
            return store_frame

        files = self._curve_candidate_files(target_date)
        if not files:
            return pd.DataFrame(columns=["capture_id", "captured_at", "symbol", "price", "daily_change_pct"])

        cache_key = self._curve_frame_cache_key(
            files=files,
            symbols=symbols,
            lookback_minutes=lookback_minutes,
            target_date=target_date,
            explicit_session_date=explicit_session_date,
        )
        with self._cache_lock:
            cached = self._curve_frame_cache.get(cache_key)
            if cached is not None:
                return cached.copy()

        records: list[dict[str, Any]] = []
        cutoff_iso = cutoff.isoformat()
        upper_cutoff_iso = upper_cutoff.isoformat() if upper_cutoff else None

        for path in files:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    next(handle, None)
                    for raw_line in handle:
                        parts = raw_line.rstrip("\n").split(",", 11)
                        if len(parts) < 8:
                            continue

                        raw_symbol = parts[3].strip().upper()
                        normalized_symbol = parts[5].strip().upper()
                        canonical = variant_map.get(raw_symbol) or variant_map.get(normalized_symbol)
                        if not canonical:
                            continue

                        captured_raw = parts[1].strip()
                        if captured_raw and captured_raw < cutoff_iso:
                            continue
                        if upper_cutoff_iso and captured_raw and captured_raw >= upper_cutoff_iso:
                            continue

                        price = _safe_float(parts[6])
                        if price is None:
                            continue

                        records.append(
                            {
                                "capture_id": parts[0].strip(),
                                "captured_at": captured_raw,
                                "symbol": canonical,
                                "price": price,
                                "daily_change_pct": _safe_float(parts[7]),
                            }
                        )
            except FileNotFoundError:
                continue
            except Exception:
                logger.exception("Failed to read curve history file: %s", path)

        if not records:
            return pd.DataFrame(columns=["capture_id", "captured_at", "symbol", "price", "daily_change_pct"])

        frame = pd.DataFrame.from_records(records)
        frame["captured_at"] = pd.to_datetime(frame["captured_at"], utc=True, errors="coerce")
        frame = frame[frame["captured_at"].notna()]
        frame = frame[frame["captured_at"] >= cutoff]
        if upper_cutoff is not None:
            frame = frame[frame["captured_at"] < upper_cutoff]
        frame = frame.sort_values(["captured_at", "symbol", "capture_id"]).drop_duplicates(
            subset=["captured_at", "symbol"],
            keep="last",
        )
        frame = frame.reset_index(drop=True)
        with self._cache_lock:
            self._curve_frame_cache[cache_key] = frame
            while len(self._curve_frame_cache) > 8:
                self._curve_frame_cache.pop(next(iter(self._curve_frame_cache)), None)
        return frame.copy()

    def _load_curve_history_frame_from_store(
        self,
        *,
        symbols: set[str],
        variant_map: dict[str, str],
        cutoff: datetime,
        upper_cutoff: datetime | None,
        lookback_minutes: int,
        target_date: date,
        explicit_session_date: bool,
    ) -> pd.DataFrame | None:
        history_store = getattr(self.chart_service, "history_store", None)
        db_path = str(getattr(history_store, "db_path", "") or "").strip()
        if history_store is None or not db_path or not os.path.exists(db_path):
            return None

        cache_key = self._curve_store_cache_key(
            db_path=db_path,
            symbols=symbols,
            lookback_minutes=lookback_minutes,
            target_date=target_date,
            explicit_session_date=explicit_session_date,
        )
        with self._cache_lock:
            cached = self._curve_frame_cache.get(cache_key)
            if cached is not None:
                return cached.copy()

        try:
            query_symbols = set(variant_map.keys())
            records = history_store.query_symbols_history(
                query_symbols,
                since=cutoff,
                until=upper_cutoff,
            )
        except Exception:
            logger.exception("Failed to read curve history from SQLite; falling back to CSV")
            return None

        columns = ["capture_id", "captured_at", "symbol", "price", "daily_change_pct"]
        if not records:
            frame = pd.DataFrame(columns=columns)
        else:
            frame = pd.DataFrame.from_records(records)
            frame["captured_at"] = pd.to_datetime(frame["captured_at"], utc=True, errors="coerce")
            frame = frame[frame["captured_at"].notna()]
            frame["symbol"] = frame["symbol"].map(
                lambda value: variant_map.get(str(value or "").strip().upper())
            )
            frame = frame[frame["symbol"].isin(symbols)]
            frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
            frame["daily_change_pct"] = pd.to_numeric(frame["daily_change_pct"], errors="coerce")
            frame = frame[frame["price"].notna()]
            frame = frame.sort_values(["captured_at", "symbol", "capture_id"]).drop_duplicates(
                subset=["captured_at", "symbol"],
                keep="last",
            )
            frame = frame.reset_index(drop=True)
            frame = frame.reindex(columns=columns)

        with self._cache_lock:
            self._curve_frame_cache[cache_key] = frame
            while len(self._curve_frame_cache) > 8:
                self._curve_frame_cache.pop(next(iter(self._curve_frame_cache)), None)
        return frame.copy()

    @staticmethod
    def _curve_store_cache_key(
        *,
        db_path: str,
        symbols: set[str],
        lookback_minutes: int,
        target_date: date,
        explicit_session_date: bool,
    ) -> tuple[Any, ...]:
        try:
            stat = os.stat(db_path)
            db_signature = (
                os.path.abspath(db_path),
                int(stat.st_mtime_ns) // (30 * 10 ** 9),
            )
        except OSError:
            db_signature = (os.path.abspath(db_path), 0)
        return (
            "sqlite",
            tuple(sorted(symbols)),
            int(lookback_minutes),
            target_date.isoformat(),
            bool(explicit_session_date),
            db_signature,
        )

    @staticmethod
    def _curve_frame_cache_key(
        *,
        files: list[str],
        symbols: set[str],
        lookback_minutes: int,
        target_date: date,
        explicit_session_date: bool,
    ) -> tuple[Any, ...]:
        signature: list[Any] = [
            tuple(sorted(symbols)),
            int(lookback_minutes),
            target_date.isoformat(),
            bool(explicit_session_date),
        ]
        granularity = 30 * 10 ** 9
        for path in files:
            try:
                stat = os.stat(path)
            except OSError:
                continue
            signature.append((path, int(stat.st_size), int(stat.st_mtime_ns) // granularity))
        return tuple(signature)

    def _target_session_date(self, session_date: str | None) -> date:
        if session_date:
            try:
                return date.fromisoformat(str(session_date)[:10])
            except Exception:
                pass

        latest_path = os.path.join(self.chart_service.root_dir, "latest.json")
        try:
            with open(latest_path, "r", encoding="utf-8", errors="replace") as handle:
                payload = json.load(handle)
            captured_at = pd.to_datetime(payload.get("captured_at"), utc=True, errors="coerce")
            if pd.notna(captured_at):
                return captured_at.tz_convert(LOCAL_TZ).date()
        except Exception:
            pass

        today = datetime.now(LOCAL_TZ).date()
        return today

    def _curve_candidate_files(self, target_date: date) -> list[str]:
        candidates: list[str] = []
        # A Brazil local session can cross UTC midnight, so inspect D and D+1 files.
        for item in (target_date, target_date + timedelta(days=1)):
            path = os.path.join(self.chart_service.rows_dir, f"{item.isoformat()}.csv")
            if os.path.exists(path):
                candidates.append(path)
        if candidates:
            return candidates

        row_paths = self.chart_service._row_file_paths()
        return row_paths[-2:]

    @staticmethod
    def _symbol_variant_map(symbols: set[str]) -> dict[str, str]:
        variants: dict[str, str] = {}

        def add(symbol: str, *items: str) -> None:
            for item in (symbol, *items):
                token = str(item or "").strip().upper()
                if token:
                    variants[token] = symbol

        for symbol in symbols:
            add(symbol)

        add("USSO1", "USS01", "USS1", "USSO01")
        add("USSO2", "USS02", "USS2", "USSO02")
        add("USSO5", "USS05", "USS5", "USSO05")
        add("USSO10", "USS010", "USS10", "USSO010")
        return variants

    def _latest_assets_payload(self) -> list[dict[str, Any]]:
        latest_path = os.path.join(self.chart_service.root_dir, "latest.json")
        try:
            with open(latest_path, "r", encoding="utf-8", errors="replace") as handle:
                payload = json.load(handle)
        except Exception:
            return []

        captured_at = payload.get("captured_at")
        assets: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in payload.get("rows") or []:
            symbol = self.chart_service._resolve_symbol(row.get("symbol"))
            price = self._clean_price(symbol, row.get("price"))
            if not symbol or symbol in seen or price is None or price <= 0:
                continue
            seen.add(symbol)
            assets.append(
                {
                    "symbol": symbol,
                    "is_benchmark": symbol == "XB1",
                    "selected": False,
                    "latest_price": self._round(price, 6),
                    "latest_daily_change_pct": self._round(row.get("daily_change_pct"), 4),
                    "latest_timestamp": captured_at,
                    "sample_count": None,
                    "latest_pearson_vs_xb1": None,
                }
            )
        return assets

    def _clean_history_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        working = frame.copy()
        working["captured_at"] = pd.to_datetime(working["captured_at"], utc=True, errors="coerce")
        working = working[working["captured_at"].notna()]
        working["symbol"] = working["symbol"].astype(str).str.strip()
        working["price"] = working.apply(
            lambda row: self._clean_price(row.get("symbol"), row.get("price")),
            axis=1,
        )
        working = working[working["price"].notna()]
        return working.reset_index(drop=True)

    @staticmethod
    def _clean_price(symbol: Any, value: Any) -> float | None:
        price = _safe_float(value)
        if price is None:
            return None

        resolved_symbol = str(symbol or "").strip().upper()

        # OCR sometimes reads the leading "s" in DI rates as 5 (513.836 -> 13.836).
        if resolved_symbol.startswith("ODF") and 100.0 <= price <= 600.0:
            price = price - 500.0

        if resolved_symbol in ALL_CURVE_SYMBOLS and not (0.0 < price < 80.0):
            return None
        return price

    def _session_frame(
        self,
        frame: pd.DataFrame,
        *,
        session_date: str | None = None,
    ) -> tuple[pd.DataFrame, str | None]:
        if frame.empty:
            return frame, None

        working = frame.copy()
        local_dates = working["captured_at"].dt.tz_convert(LOCAL_TZ).dt.date
        if session_date:
            try:
                target_date = date.fromisoformat(str(session_date)[:10])
            except Exception:
                target_date = local_dates.max()
        else:
            target_date = local_dates.max()

        scoped = working[local_dates == target_date].reset_index(drop=True)
        return scoped, target_date.isoformat() if target_date else None

    def _build_curve_payload(
        self,
        *,
        definition: CurveDefinition,
        frame: pd.DataFrame,
        max_points: int,
        include_shape_points: bool,
    ) -> dict[str, Any]:
        symbols = [vertex.symbol for vertex in definition.vertices]
        curve_frame = frame[frame["symbol"].isin(symbols)].copy()

        empty_shape = self._shape_state(0.0, 0.0)
        if curve_frame.empty:
            return {
                "key": definition.key,
                "label": definition.label,
                "short_label": definition.short_label,
                "color": definition.color,
                "available": False,
                "vertices": self._empty_vertices(definition),
                "history": [],
                "shape_points": [],
                "current_shape": empty_shape,
                "summary": {
                    "available_vertices": 0,
                    "current_slope_bp_per_log_year": None,
                    "current_slope_change_bp": None,
                    "current_level_change_bp": None,
                    "current_curvature_bp": None,
                },
            }

        curve_frame = curve_frame.sort_values("captured_at")
        curve_frame["minute"] = curve_frame["captured_at"].dt.floor("min")
        minute_frame = curve_frame.groupby(["minute", "symbol"], as_index=False).tail(1)
        pivot = (
            minute_frame.pivot_table(index="minute", columns="symbol", values="price", aggfunc="last")
            .sort_index()
            .ffill(limit=5)
        )
        daily_change_pivot = (
            minute_frame.pivot_table(index="minute", columns="symbol", values="daily_change_pct", aggfunc="last")
            .sort_index()
            .ffill(limit=5)
        )
        pivot = pivot.dropna(how="all")

        vertices = self._build_vertices(definition, curve_frame, pivot, daily_change_pivot)
        slope_history = self._build_slope_history(
            definition,
            pivot,
            daily_change_pivot=daily_change_pivot,
            max_points=max_points,
        )
        current_shape = empty_shape
        shape_points: list[dict[str, Any]] = []
        if slope_history:
            latest = slope_history[-1]
            current_shape = self._shape_state(
                latest.get("level_change_bp"),
                latest.get("slope_change_bp"),
            )
            if include_shape_points:
                shape_points = self._build_shape_points(slope_history)

        available_vertices = sum(1 for vertex in vertices if vertex.get("available"))
        latest_history = slope_history[-1] if slope_history else {}
        return {
            "key": definition.key,
            "label": definition.label,
            "short_label": definition.short_label,
            "color": definition.color,
            "change_basis": self._change_basis(definition),
            "available": available_vertices >= 2 and bool(slope_history),
            "vertices": vertices,
            "history": slope_history,
            "shape_points": shape_points,
            "current_shape": current_shape,
            "summary": {
                "available_vertices": available_vertices,
                "current_slope_bp_per_log_year": latest_history.get("slope_bp_per_log_year"),
                "current_slope_change_bp": latest_history.get("slope_change_bp"),
                "current_level_change_bp": latest_history.get("level_change_bp"),
                "current_curvature_bp": latest_history.get("curvature_bp"),
                "latest_timestamp": latest_history.get("timestamp"),
                "change_basis": latest_history.get("change_basis") or self._change_basis(definition),
            },
        }

    @staticmethod
    def _empty_vertices(definition: CurveDefinition) -> list[dict[str, Any]]:
        return [
            {
                "symbol": vertex.symbol,
                "label": vertex.label,
                "tenor_years": vertex.tenor_years,
                "available": False,
                "latest_price": None,
                "change_bp": None,
                "min_change_bp": None,
                "max_change_bp": None,
                "daily_change_pct": None,
                "timestamp": None,
            }
            for vertex in definition.vertices
        ]

    def _build_vertices(
        self,
        definition: CurveDefinition,
        curve_frame: pd.DataFrame,
        pivot: pd.DataFrame,
        daily_change_pivot: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        latest_rows = (
            curve_frame.sort_values("captured_at")
            .groupby("symbol", as_index=False)
            .tail(1)
            .set_index("symbol", drop=False)
        )

        vertices: list[dict[str, Any]] = []
        for vertex in definition.vertices:
            if vertex.symbol not in pivot.columns:
                vertices.append(self._empty_vertex(vertex))
                continue

            series = pivot[vertex.symbol].dropna()
            if series.empty:
                vertices.append(self._empty_vertex(vertex))
                continue

            first_price = _safe_float(series.iloc[0])
            latest_price = _safe_float(series.iloc[-1])
            if first_price is None or latest_price is None:
                vertices.append(self._empty_vertex(vertex))
                continue

            session_changes_bp = (series - first_price) * 100.0
            daily_change_pct_series = (
                daily_change_pivot[vertex.symbol]
                if vertex.symbol in daily_change_pivot.columns
                else pd.Series(dtype="float64")
            )
            daily_changes_bp = self._daily_change_bp_series(
                prices=series,
                daily_change_pcts=daily_change_pct_series,
            )
            latest_row = latest_rows.loc[vertex.symbol] if vertex.symbol in latest_rows.index else {}
            latest_timestamp = series.index[-1]
            aligned_daily_change_pct = pd.to_numeric(
                daily_change_pct_series.reindex(series.index).ffill(limit=5),
                errors="coerce",
            )
            daily_change_pct = (
                _safe_float(aligned_daily_change_pct.dropna().iloc[-1])
                if not aligned_daily_change_pct.dropna().empty
                else _safe_float(getattr(latest_row, "daily_change_pct", None))
            )
            latest_daily_change_bp = (
                _safe_float(daily_changes_bp.dropna().iloc[-1])
                if not daily_changes_bp.dropna().empty
                else None
            )
            session_change_bp = _safe_float((latest_price - first_price) * 100.0)
            use_daily_basis = self._uses_daily_change_basis(definition) and latest_daily_change_bp is not None
            display_changes_bp = daily_changes_bp.dropna() if use_daily_basis else session_changes_bp.dropna()
            display_change_bp = latest_daily_change_bp if use_daily_basis else session_change_bp
            vertices.append(
                {
                    "symbol": vertex.symbol,
                    "label": vertex.label,
                    "tenor_years": vertex.tenor_years,
                    "available": True,
                    "latest_price": self._round(latest_price, 6),
                    "change_bp": self._round(display_change_bp, 4),
                    "min_change_bp": self._round(display_changes_bp.min(), 4),
                    "max_change_bp": self._round(display_changes_bp.max(), 4),
                    "session_change_bp": self._round(session_change_bp, 4),
                    "session_min_change_bp": self._round(session_changes_bp.min(), 4),
                    "session_max_change_bp": self._round(session_changes_bp.max(), 4),
                    "daily_change_bp": self._round(latest_daily_change_bp, 4),
                    "daily_min_change_bp": self._round(daily_changes_bp.min(), 4),
                    "daily_max_change_bp": self._round(daily_changes_bp.max(), 4),
                    "daily_change_pct": self._round(daily_change_pct, 4),
                    "change_basis": "daily_w32_pct" if use_daily_basis else "session_first",
                    "timestamp": latest_timestamp.isoformat()
                    if isinstance(latest_timestamp, datetime)
                    else None,
                }
            )
        return vertices

    @staticmethod
    def _empty_vertex(vertex: CurveVertex) -> dict[str, Any]:
        return {
            "symbol": vertex.symbol,
            "label": vertex.label,
            "tenor_years": vertex.tenor_years,
            "available": False,
            "latest_price": None,
            "change_bp": None,
            "min_change_bp": None,
            "max_change_bp": None,
            "daily_change_pct": None,
            "timestamp": None,
        }

    def _build_slope_history(
        self,
        definition: CurveDefinition,
        pivot: pd.DataFrame,
        *,
        daily_change_pivot: pd.DataFrame | None = None,
        max_points: int,
    ) -> list[dict[str, Any]]:
        raw_points: list[dict[str, Any]] = []
        use_daily_basis = self._uses_daily_change_basis(definition)
        for timestamp, row in pivot.iterrows():
            observations: list[tuple[float, float]] = []
            daily_change_observations: list[tuple[float, float]] = []
            used_vertices: list[str] = []
            daily_row = (
                daily_change_pivot.loc[timestamp]
                if daily_change_pivot is not None and timestamp in daily_change_pivot.index
                else None
            )
            for vertex in definition.vertices:
                value = _safe_float(row.get(vertex.symbol))
                if value is None:
                    continue
                observations.append((vertex.tenor_years, value))
                used_vertices.append(vertex.symbol)
                if use_daily_basis and daily_row is not None:
                    daily_change_pct = _safe_float(daily_row.get(vertex.symbol))
                    daily_change_bp = self._daily_change_bp(value, daily_change_pct)
                    if daily_change_bp is not None:
                        daily_change_observations.append((vertex.tenor_years, daily_change_bp / 100.0))

            fit = self._geometric_slope_fit(observations)
            if fit is None:
                continue
            daily_change_fit = (
                self._geometric_slope_fit(daily_change_observations)
                if use_daily_basis and len(daily_change_observations) >= 2
                else None
            )

            raw_points.append(
                {
                    "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else None,
                    "timestamp_ms": int(timestamp.timestamp() * 1000) if isinstance(timestamp, datetime) else None,
                    "slope": fit["slope"],
                    "level": fit["level"],
                    "curvature_bp": fit["curvature_bp"],
                    "daily_change_fit": daily_change_fit,
                    "vertex_count": len(observations),
                    "used_vertices": used_vertices,
                }
            )

        if not raw_points:
            return []

        base = raw_points[0]
        enriched: list[dict[str, Any]] = []
        for point in raw_points:
            slope_change_bp = (point["slope"] - base["slope"]) * 100.0
            level_change_bp = (point["level"] - base["level"]) * 100.0
            daily_change_fit = point.get("daily_change_fit")
            if use_daily_basis and isinstance(daily_change_fit, dict):
                display_slope_change_bp = daily_change_fit["slope"] * 100.0
                display_level_change_bp = daily_change_fit["level"] * 100.0
                display_curvature_bp = daily_change_fit["curvature_bp"]
                change_basis = "daily_w32_pct"
            else:
                display_slope_change_bp = slope_change_bp
                display_level_change_bp = level_change_bp
                display_curvature_bp = point["curvature_bp"]
                change_basis = "session_first"
            enriched.append(
                {
                    "timestamp": point["timestamp"],
                    "timestamp_ms": point["timestamp_ms"],
                    "slope_bp_per_log_year": self._round(point["slope"] * 100.0, 4),
                    "slope_change_bp": self._round(display_slope_change_bp, 4),
                    "session_slope_change_bp": self._round(slope_change_bp, 4),
                    "level_yield_pct": self._round(point["level"], 6),
                    "level_change_bp": self._round(display_level_change_bp, 4),
                    "session_level_change_bp": self._round(level_change_bp, 4),
                    "curvature_bp": self._round(display_curvature_bp, 4),
                    "session_curvature_bp": self._round(point["curvature_bp"], 4),
                    "change_basis": change_basis,
                    "vertex_count": point["vertex_count"],
                    "used_vertices": point["used_vertices"],
                }
            )

        return MarketScreenChartService._downsample_points(enriched, max_points)

    @staticmethod
    def _uses_daily_change_basis(definition: CurveDefinition) -> bool:
        return definition.key == "di"

    @classmethod
    def _change_basis(cls, definition: CurveDefinition) -> str:
        return "daily_w32_pct" if cls._uses_daily_change_basis(definition) else "session_first"

    @staticmethod
    def _daily_change_bp(price: Any, daily_change_pct: Any) -> float | None:
        resolved_price = _safe_float(price)
        resolved_change_pct = _safe_float(daily_change_pct)
        if resolved_price is None or resolved_change_pct is None:
            return None
        return resolved_price * resolved_change_pct

    def _daily_change_bp_series(
        self,
        *,
        prices: pd.Series,
        daily_change_pcts: pd.Series,
    ) -> pd.Series:
        if daily_change_pcts.empty:
            return pd.Series(index=prices.index, dtype="float64")
        aligned_change = pd.to_numeric(
            daily_change_pcts.reindex(prices.index).ffill(limit=5),
            errors="coerce",
        )
        aligned_prices = pd.to_numeric(prices, errors="coerce")
        return aligned_prices * aligned_change

    @staticmethod
    def _geometric_slope_fit(observations: list[tuple[float, float]]) -> dict[str, float] | None:
        clean = [
            (math.log(float(tenor)), float(rate))
            for tenor, rate in observations
            if tenor and tenor > 0 and _safe_float(rate) is not None
        ]
        if len(clean) < 2:
            return None

        weights = [1.0 for _ in clean]
        weight_sum = sum(weights)
        x_bar = sum(weight * item[0] for weight, item in zip(weights, clean)) / weight_sum
        y_bar = sum(weight * item[1] for weight, item in zip(weights, clean)) / weight_sum

        variance = sum(weight * (item[0] - x_bar) ** 2 for weight, item in zip(weights, clean))
        if variance <= 1e-12:
            return None

        covariance = sum(
            weight * (item[0] - x_bar) * (item[1] - y_bar)
            for weight, item in zip(weights, clean)
        )
        slope = covariance / variance
        intercept = y_bar - slope * x_bar

        residuals = [
            item[1] - (intercept + slope * item[0])
            for item in clean
        ]
        curvature_bp = math.sqrt(sum(residual * residual for residual in residuals) / len(residuals)) * 100.0
        return {
            "slope": slope,
            "level": y_bar,
            "curvature_bp": curvature_bp,
        }

    def _build_shape_points(self, slope_history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        points: list[dict[str, Any]] = []
        previous_id: str | None = None
        for point in slope_history:
            shape = self._shape_state(point.get("level_change_bp"), point.get("slope_change_bp"))
            shape_id = shape.get("id")
            if previous_id is None:
                previous_id = shape_id
                continue
            if shape_id == previous_id:
                continue
            points.append(
                {
                    "timestamp": point.get("timestamp"),
                    "timestamp_ms": point.get("timestamp_ms"),
                    "shape": shape,
                    "slope_change_bp": point.get("slope_change_bp"),
                    "level_change_bp": point.get("level_change_bp"),
                }
            )
            previous_id = shape_id
        return points[-80:]

    def _shape_state(self, level_change_bp: Any, slope_change_bp: Any) -> dict[str, Any]:
        level = _safe_float(level_change_bp) or 0.0
        slope = _safe_float(slope_change_bp) or 0.0
        level_threshold = 1.5
        slope_threshold = 1.5

        if abs(level) < level_threshold and abs(slope) < slope_threshold:
            shape_id = "neutral"
        else:
            level_side = "bull" if level <= -level_threshold else "bear" if level >= level_threshold else ""
            slope_side = "steepening" if slope >= slope_threshold else "flattening" if slope <= -slope_threshold else ""

            if level_side and slope_side:
                shape_id = f"{level_side}_{slope_side}"
            elif level_side:
                shape_id = f"{level_side}_parallel"
            elif slope_side:
                shape_id = slope_side
            else:
                shape_id = "neutral"

        base = SHAPE_LABELS.get(shape_id) or SHAPE_LABELS["neutral"]
        return {
            "id": shape_id,
            "label": base["label"],
            "tone": base["tone"],
            "meaning": base["meaning"],
            "risk_read": base["risk_read"],
        }

    def _build_ai_commentary(self, payload: dict[str, Any]) -> dict[str, Any]:
        fallback = self._fallback_ai_commentary(payload)
        if not payload.get("ok"):
            return fallback

        try:
            response = self.llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Voce e um trader macro brasileiro senior. Analise curvas intraday de juros "
                            "com foco em risco, premio de prazo, inclinacao e mudanca de shape. Seja direto, "
                            "nao invente dados, e trate o modelo de inclinacao como beta de yield contra ln(tenor)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Dados do widget de curvas:\n"
                            f"{json.dumps(self._ai_input_bundle(payload), ensure_ascii=False, default=str)}\n\n"
                            "Retorne JSON puro com: headline, overall_view, curve_views "
                            "(lista com curve_key, label, read, shape, what_it_means), "
                            "key_points, risks, monitor, bias (risk_on|risk_off|mixed|watch), confidence."
                        ),
                    },
                ],
                temperature=0.25,
                max_tokens=1800,
            )
            return {
                "headline": str(response.get("headline") or fallback["headline"]),
                "overall_view": str(response.get("overall_view") or fallback["overall_view"]),
                "curve_views": response.get("curve_views") or fallback["curve_views"],
                "key_points": self._string_list(response.get("key_points")) or fallback["key_points"],
                "risks": self._string_list(response.get("risks")) or fallback["risks"],
                "monitor": self._string_list(response.get("monitor")) or fallback["monitor"],
                "bias": self._normalize_bias(response.get("bias"), fallback=fallback["bias"]),
                "confidence": self._normalize_confidence(response.get("confidence"), fallback=fallback["confidence"]),
                "source": "llm",
            }
        except Exception as exc:
            logger.warning("Curve discovery LLM generation failed, using fallback: %s", exc)
            return fallback

    def _ai_input_bundle(self, payload: dict[str, Any]) -> dict[str, Any]:
        curves: list[dict[str, Any]] = []
        for curve in payload.get("curves") or []:
            curves.append(
                {
                    "key": curve.get("key"),
                    "label": curve.get("label"),
                    "current_shape": curve.get("current_shape"),
                    "summary": curve.get("summary"),
                    "vertices": [
                        {
                            "symbol": vertex.get("symbol"),
                            "label": vertex.get("label"),
                            "latest_price": vertex.get("latest_price"),
                            "change_bp": vertex.get("change_bp"),
                            "min_change_bp": vertex.get("min_change_bp"),
                            "max_change_bp": vertex.get("max_change_bp"),
                            "daily_change_pct": vertex.get("daily_change_pct"),
                        }
                        for vertex in curve.get("vertices") or []
                        if vertex.get("available")
                    ],
                    "slope_history_tail": (curve.get("history") or [])[-90:],
                    "shape_points": (curve.get("shape_points") or [])[-25:],
                }
            )

        assets = [
            {
                "symbol": asset.get("symbol"),
                "latest_price": asset.get("latest_price"),
                "latest_daily_change_pct": asset.get("latest_daily_change_pct"),
                "sample_count": asset.get("sample_count"),
            }
            for asset in payload.get("assets") or []
        ]

        return {
            "session_date": payload.get("session_date"),
            "latest_capture_at": payload.get("latest_capture_at"),
            "model": payload.get("model"),
            "curves": curves,
            "all_registered_assets_current_variation": assets,
        }

    def _fallback_ai_commentary(self, payload: dict[str, Any]) -> dict[str, Any]:
        curves = [curve for curve in payload.get("curves") or [] if curve.get("available")]
        if not curves:
            return {
                "headline": "Sem dados suficientes para formar leitura de curvas.",
                "overall_view": payload.get("reason") or "A captura W32 ainda nao entregou vertices suficientes.",
                "curve_views": [],
                "key_points": [],
                "risks": ["Sem pelo menos dois vertices por curva, a inclinacao geometrica nao e estavel."],
                "monitor": ["Aguardar novas capturas de tela W32."],
                "bias": "watch",
                "confidence": 35,
                "source": "fallback",
            }

        leader = max(
            curves,
            key=lambda curve: abs(_safe_float((curve.get("summary") or {}).get("current_slope_change_bp")) or 0.0),
        )
        leader_summary = leader.get("summary") or {}
        leader_shape = (leader.get("current_shape") or {}).get("label") or "shape indefinido"
        curve_views = []
        for curve in curves:
            summary = curve.get("summary") or {}
            shape = curve.get("current_shape") or {}
            curve_views.append(
                {
                    "curve_key": curve.get("key"),
                    "label": curve.get("label"),
                    "shape": shape.get("label"),
                    "read": (
                        f"Slope mudou {self._fmt_bp(summary.get('current_slope_change_bp'))}; "
                        f"nivel mudou {self._fmt_bp(summary.get('current_level_change_bp'))}."
                    ),
                    "what_it_means": shape.get("risk_read") or shape.get("meaning"),
                }
            )

        return {
            "headline": f"Shape dominante: {leader.get('label')} em {leader_shape}.",
            "overall_view": (
                f"A leitura quantitativa aponta maior mudanca de inclinacao em {leader.get('label')}: "
                f"{self._fmt_bp(leader_summary.get('current_slope_change_bp'))}. "
                "Use a leitura como triagem intraday; confirme com liquidez e ativos correlatos."
            ),
            "curve_views": curve_views,
            "key_points": [
                "Modelo: slope de yield contra ln(prazo), amostrado a cada 1 minuto.",
                f"Curva com maior mudanca de inclinacao: {leader.get('label')}.",
            ],
            "risks": [
                "OCR da captura pode gerar ruido em vertices isolados; o modelo reduz, mas nao elimina, esse risco.",
                "Mudancas pequenas abaixo de 1.5 bp sao tratadas como neutras para evitar overfitting intraday.",
            ],
            "monitor": [
                "Persistencia do shape por mais de alguns minutos.",
                "Confirmacao nos ativos registrados da W32 e no movimento de nivel medio.",
            ],
            "bias": "watch",
            "confidence": 55,
            "source": "fallback",
        }

    @staticmethod
    def _sanitize_asset(asset: dict[str, Any]) -> dict[str, Any]:
        item = dict(asset)
        item["latest_price"] = MacroCurveDiscoveryService._clean_price(
            item.get("symbol"),
            item.get("latest_price"),
        )
        return item

    @staticmethod
    def _round(value: Any, digits: int = 4) -> float | None:
        parsed = _safe_float(value)
        if parsed is None:
            return None
        return round(parsed, digits)

    @staticmethod
    def _fmt_bp(value: Any) -> str:
        parsed = _safe_float(value)
        if parsed is None:
            return "n/a"
        return f"{parsed:+.1f} bp"

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item or "").strip()][:8]

    @staticmethod
    def _normalize_bias(value: Any, *, fallback: str) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"risk_on", "risk_off", "mixed", "watch"}:
            return raw
        return fallback

    @staticmethod
    def _normalize_confidence(value: Any, *, fallback: int) -> int:
        parsed = _safe_float(value)
        if parsed is None:
            return fallback
        return max(0, min(100, int(round(parsed))))
