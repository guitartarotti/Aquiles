"""
Participant heatmap panel for WIN / WDO / DI.

This service samples the existing Aquant contract snapshot every few seconds,
persists a short rolling history, and returns a chart-friendly payload for the
macro dashboard.
"""

from __future__ import annotations

import json
import os
import threading
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from ..config import Config
from .macro_live_service import MacroIngestionService, MacroStateStore
from .macro_options_heatmap_context_manager import MacroOptionsHeatmapContextManager
from .macro_participant_analytics import MacroParticipantAnalyticsMixin
from .macro_participant_math import (
    _clamp,
    _normalize_broker_name,
    _parse_iso,
    _safe_float,
    _utc_now,
)
from .macro_participant_registry import (
    DEFAULT_FOREIGN_BROKER_REGISTRY,
    DEFAULT_RETAIL_BROKER_REGISTRY,
)


class MacroParticipantHeatmapService(MacroParticipantAnalyticsMixin):
    _state_lock = threading.RLock()

    def __init__(
        self,
        store: MacroStateStore | None = None,
        config: type[Config] = Config,
        options_heatmap_manager: MacroOptionsHeatmapContextManager | None = None,
    ):
        self.store = store or MacroStateStore()
        self.config = config
        self.options_heatmap_manager = (
            options_heatmap_manager or MacroOptionsHeatmapContextManager()
        )
        self.root_dir = self.store.root_dir
        self.state_path = os.path.join(self.root_dir, "participant_heatmap_state.json")
        self._lock = self.__class__._state_lock
        self._panel_cache: dict[str, Any] | None = None
        self._panel_cache_at: float = 0.0
        self._foreign_registry_cache: dict[str, dict[str, Any]] | None = None
        self._retail_registry_cache: dict[str, dict[str, Any]] | None = None
        os.makedirs(self.root_dir, exist_ok=True)

    def _default_state(self) -> dict[str, Any]:
        return {
            "generated_at": None,
            "sample_interval_seconds": int(self.config.MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS),
            "history_minutes": int(self.config.MACRO_PARTICIPANT_HEATMAP_HISTORY_MINUTES),
            "collector": {
                "enabled": bool(self.config.MACRO_PARTICIPANT_HEATMAP_ENABLE),
                "auto_start": bool(self.config.MACRO_PARTICIPANT_HEATMAP_AUTO_START),
                "interval_seconds": int(self.config.MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS),
                "session_sample_limit": int(
                    self.config.MACRO_PARTICIPANT_HEATMAP_SESSION_SAMPLE_LIMIT
                ),
                "running": False,
                "last_started_at": None,
                "last_completed_at": None,
                "last_error": None,
                "sample_count": 0,
            },
            "assets": {},
        }

    def _read_state(self) -> dict[str, Any]:
        with self._lock:
            if not os.path.exists(self.state_path):
                return self._default_state()

            payload: dict[str, Any] | None = None
            for attempt in range(3):
                try:
                    with open(self.state_path, "r", encoding="utf-8") as handle:
                        payload = json.load(handle) or {}
                    break
                except Exception:
                    if attempt >= 2:
                        return self._default_state()
                    time.sleep(0.05)

        if not isinstance(payload, dict):
            return self._default_state()
        state = self._default_state()
        state.update({k: v for k, v in payload.items() if k not in {"assets", "collector"}})
        state["collector"] = {**state["collector"], **(payload.get("collector") or {})}
        state["assets"] = payload.get("assets", {}) or {}
        return state

    def _build_foreign_registry(self) -> dict[str, dict[str, Any]]:
        if self._foreign_registry_cache is not None:
            return self._foreign_registry_cache

        self._foreign_registry_cache = self._build_registry(DEFAULT_FOREIGN_BROKER_REGISTRY)
        return self._foreign_registry_cache

    def _build_retail_registry(self) -> dict[str, dict[str, Any]]:
        if self._retail_registry_cache is not None:
            return self._retail_registry_cache

        self._retail_registry_cache = self._build_registry(DEFAULT_RETAIL_BROKER_REGISTRY)
        return self._retail_registry_cache

    def _build_registry(self, items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        registry: dict[str, dict[str, Any]] = {}
        for item in items:
            aliases = item.get("aliases") or []
            normalized_aliases = [_normalize_broker_name(alias) for alias in aliases if alias]
            entry = {
                "registry_key": item.get("registry_key"),
                "canonical_name": item.get("canonical_name"),
                "country": item.get("country"),
                "region": item.get("region", "global"),
                "aliases": normalized_aliases,
            }
            for alias in normalized_aliases:
                registry[alias] = entry

        return registry

    def _match_registry_entry(
        self, normalized_broker_name: str, registry: dict[str, dict[str, Any]]
    ) -> dict[str, Any] | None:
        if not normalized_broker_name:
            return None

        exact = registry.get(normalized_broker_name)
        if exact:
            return exact

        best_match: dict[str, Any] | None = None
        best_alias_length = -1
        for alias, entry in registry.items():
            if not alias:
                continue
            if normalized_broker_name.startswith(alias) or alias in normalized_broker_name:
                alias_length = len(alias)
                if alias_length > best_alias_length:
                    best_match = entry
                    best_alias_length = alias_length
        return best_match

    def _classify_broker_origin(self, broker_name: Any) -> dict[str, Any]:
        normalized = _normalize_broker_name(broker_name)
        retail_registry = self._build_retail_registry()
        retail_match = self._match_registry_entry(normalized, retail_registry)
        if retail_match:
            return {
                "is_foreign_broker": False,
                "is_retail_broker": True,
                "broker_segment": "retail",
                "origin_scope": "retail",
                "origin_confidence": "retail_registry_match",
                "origin_registry_key": retail_match.get("registry_key"),
                "origin_label": retail_match.get("canonical_name"),
                "origin_country": retail_match.get("country"),
                "origin_region": retail_match.get("region"),
            }

        foreign_registry = self._build_foreign_registry()
        match = self._match_registry_entry(normalized, foreign_registry)
        if match:
            return {
                "is_foreign_broker": True,
                "is_retail_broker": False,
                "broker_segment": "foreign",
                "origin_scope": "foreign",
                "origin_confidence": "registry_match",
                "origin_registry_key": match.get("registry_key"),
                "origin_label": match.get("canonical_name"),
                "origin_country": match.get("country"),
                "origin_region": match.get("region"),
            }
        return {
            "is_foreign_broker": False,
            "is_retail_broker": False,
            "broker_segment": "local_or_unclassified",
            "origin_scope": "local_or_unclassified",
            "origin_confidence": "unclassified",
            "origin_registry_key": None,
            "origin_label": None,
            "origin_country": None,
            "origin_region": None,
        }

    def _write_state(self, state: dict[str, Any]) -> None:
        with self._lock:
            temp_path = f"{self.state_path}.{os.getpid()}.{threading.get_ident()}.tmp"
            try:
                with open(temp_path, "w", encoding="utf-8") as handle:
                    json.dump(state, handle, ensure_ascii=False, indent=2)
                last_error = None
                for _ in range(12):
                    try:
                        os.replace(temp_path, self.state_path)
                        last_error = None
                        break
                    except PermissionError as exc:
                        last_error = exc
                        time.sleep(0.1)
                if last_error is not None:
                    raise last_error
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass

    def _asset_specs(self) -> list[dict[str, str]]:
        specs: list[dict[str, Any]] = []
        di_tickers: list[str] = []
        seen_di: set[str] = set()
        configured_di = list(
            getattr(self.config, "MACRO_PARTICIPANT_CROSS_ASSET_DI_TICKERS", []) or []
        )
        fallback_di = list(
            dict.fromkeys(
                list(getattr(self.config, "MACRO_CURVE_SHORT_TICKERS", []) or [])
                + list(getattr(self.config, "MACRO_CURVE_LONG_TICKERS", []) or [])
            )
        )
        source_di = configured_di if configured_di else fallback_di
        for ticker in source_di:
            normalized = str(ticker or "").strip()
            if normalized and normalized not in seen_di:
                seen_di.add(normalized)
                di_tickers.append(normalized)

        if self.config.MACRO_INDEX_TICKERS:
            specs.append(
                {
                    "key": "win",
                    "label": "WIN",
                    "ticker": self.config.MACRO_INDEX_TICKERS[0],
                    "visible": True,
                    "role": "win",
                }
            )
        if self.config.MACRO_DOLLAR_TICKERS:
            specs.append(
                {
                    "key": "wdo",
                    "label": "WDO",
                    "ticker": self.config.MACRO_DOLLAR_TICKERS[0],
                    "visible": True,
                    "role": "wdo",
                }
            )
        if di_tickers:
            specs.append(
                {
                    "key": "di",
                    "label": "DI",
                    "ticker": di_tickers[0],
                    "visible": True,
                    "role": "di_anchor",
                    "curve_bucket": "di_curve",
                }
            )
            for ticker in di_tickers[1:]:
                suffix = ticker.split("DI1")[-1].replace(":", "").lower()
                specs.append(
                    {
                        "key": f"di_{suffix}",
                        "label": suffix.upper(),
                        "ticker": ticker,
                        "visible": False,
                        "role": "di_curve",
                        "curve_bucket": "di_curve",
                    }
                )
        return specs

    def _is_price_valid(self, value: float | None) -> bool:
        return value is not None and value > 0 and value < 10_000_000

    def _extract_price(self, snapshot: dict[str, Any]) -> tuple[float | None, str]:
        book = snapshot.get("book", {}) or {}
        summary = book.get("summary", {}) or {}
        bid = _safe_float(summary.get("best_bid_price"))
        ask = _safe_float(summary.get("best_ask_price"))

        if bid is not None and ask is not None and self._is_price_valid(bid) and self._is_price_valid(ask) and ask >= bid:
            midpoint = (bid + ask) / 2.0
            spread_ratio = abs(ask - bid) / max(abs(midpoint), 1.0)
            if spread_ratio <= 0.02:
                return midpoint, "book_mid"

        last_candle = (snapshot.get("ohlcv") or {}).get("last") or {}
        close_price = _safe_float(last_candle.get("close"))
        if self._is_price_valid(close_price):
            return close_price, "ohlcv_close"

        if self._is_price_valid(bid):
            return bid, "book_bid"
        if self._is_price_valid(ask):
            return ask, "book_ask"
        return None, "unavailable"

    def _normalize_participant_row(self, row: dict[str, Any]) -> dict[str, Any]:
        quantity = _safe_float(row.get("quantity_float"))
        if quantity is None:
            quantity = _safe_float(row.get("quantity")) or 0.0
        avg_price = _safe_float(row.get("average_price"))
        percentage = _safe_float(row.get("percentage_float"))
        if percentage is None:
            percentage = _safe_float(row.get("percentage"))
        relative_percentage = _safe_float(row.get("relative_percentage_float"))
        if relative_percentage is None:
            relative_percentage = _safe_float(row.get("relative_percentage"))

        side = "buy" if quantity > 0 else "sell" if quantity < 0 else "flat"
        magnitude = max(abs(quantity), abs(relative_percentage or 0.0), abs(percentage or 0.0))
        origin = self._classify_broker_origin(row.get("broker_name"))

        return {
            "broker_id": row.get("broker_id"),
            "broker_name": row.get("broker_name"),
            "average_price": row.get("average_price"),
            "average_price_float": avg_price,
            "quantity": row.get("quantity"),
            "quantity_float": quantity,
            "percentage": row.get("percentage"),
            "percentage_float": percentage,
            "relative_percentage": row.get("relative_percentage"),
            "relative_percentage_float": relative_percentage,
            "side": side,
            "intensity_raw": magnitude,
            **origin,
        }

    def _build_sample(self, spec: dict[str, str], snapshot: dict[str, Any]) -> dict[str, Any]:
        collected_at = snapshot.get("collected_at")
        participants = ((snapshot.get("participants") or {}).get("all_rows") or [])[
            : self.config.MACRO_PARTICIPANT_HEATMAP_PARTICIPANT_LIMIT
        ]
        normalized_rows = [self._normalize_participant_row(row) for row in participants]
        last_price, price_source = self._extract_price(snapshot)
        last_candle = (snapshot.get("ohlcv") or {}).get("last") or {}
        book_summary = (snapshot.get("book") or {}).get("summary") or {}

        return {
            "captured_at": collected_at,
            "ticker": spec["ticker"],
            "label": spec["label"],
            "price_source": price_source,
            "last_price": last_price,
            "best_bid": _safe_float(book_summary.get("best_bid_price")),
            "best_ask": _safe_float(book_summary.get("best_ask_price")),
            "spread": _safe_float(book_summary.get("spread")),
            "imbalance": _safe_float(book_summary.get("imbalance")),
            "last_candle": {
                "time": last_candle.get("time"),
                "open": _safe_float(last_candle.get("open")),
                "high": _safe_float(last_candle.get("high")),
                "low": _safe_float(last_candle.get("low")),
                "close": _safe_float(last_candle.get("close")),
                "volume": _safe_float(last_candle.get("volume")),
            },
            "participants": normalized_rows,
            "participants_ok": bool((snapshot.get("participants") or {}).get("ok")),
            "book_ok": bool((snapshot.get("book") or {}).get("ok")),
            "ohlcv_ok": bool((snapshot.get("ohlcv") or {}).get("ok")),
        }

    def _trim_samples(self, samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
        session_start_utc, _ = self._session_start_utc(_utc_now())
        session_sample_limit = max(
            120, int(self.config.MACRO_PARTICIPANT_HEATMAP_SESSION_SAMPLE_LIMIT)
        )
        trimmed = []
        for item in samples:
            captured_at = _parse_iso(item.get("captured_at"))
            if captured_at and captured_at >= session_start_utc:
                trimmed.append(item)
        return trimmed[-session_sample_limit:]

    def _sample_is_stale(self, samples: list[dict[str, Any]]) -> bool:
        if not samples:
            return True
        last_dt = _parse_iso(samples[-1].get("captured_at"))
        if not last_dt:
            return True
        age = (_utc_now() - last_dt).total_seconds()
        return age >= max(5, int(self.config.MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS))

    def _market_timezone(self) -> ZoneInfo:
        return ZoneInfo("America/Sao_Paulo")

    def _session_start_utc(self, now_utc: datetime) -> tuple[datetime, str]:
        local_now = now_utc.astimezone(self._market_timezone())
        session_start_local = local_now.replace(
            hour=int(self.config.MACRO_PARTICIPANT_HEATMAP_SESSION_START_HOUR),
            minute=int(self.config.MACRO_PARTICIPANT_HEATMAP_SESSION_START_MINUTE),
            second=0,
            microsecond=0,
        )
        if local_now < session_start_local:
            session_start_local = session_start_local - timedelta(days=1)
        return session_start_local.astimezone(timezone.utc), session_start_local.date().isoformat()

    def _dedupe_candles(
        self, candles: list[dict[str, Any]], limit: int | None = None
    ) -> list[dict[str, Any]]:
        by_time: dict[str, dict[str, Any]] = {}
        for candle in candles:
            if not isinstance(candle, dict):
                continue
            timestamp = candle.get("time")
            if not timestamp:
                continue
            by_time[str(timestamp)] = candle
        ordered = sorted(by_time.values(), key=lambda candle: str(candle.get("time") or ""))
        if limit:
            return ordered[-limit:]
        return ordered

    def _fetch_session_candles(
        self, ingestion: MacroIngestionService, ticker: str, now_utc: datetime
    ) -> tuple[list[dict[str, Any]], str | None, str]:
        session_start_utc, session_date = self._session_start_utc(now_utc)
        response, payload, error = ingestion._fetch_json(
            f"https://sdk.aquant.com.br/trade/{ticker}/ohlcv",
            params={
                "start": session_start_utc.replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z"),
                "end": now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "interval": self.config.MACRO_AQUANT_OHLCV_INTERVAL,
            },
        )
        candles: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            candles = payload.get("candles", []) or []
        if not (response and response.ok) and not error:
            error = f"ohlcv_session_fetch_failed:{ticker}"
        return (
            self._dedupe_candles(
                candles, limit=max(180, int(self.config.MACRO_PARTICIPANT_HEATMAP_DAY_CANDLE_LIMIT))
            ),
            error,
            session_date,
        )

    def _state_has_cached_assets(self, state: dict[str, Any]) -> bool:
        assets = state.get("assets") or {}
        return any(asset_state.get("samples") or [] for asset_state in assets.values())

    def _count_samples(self, state: dict[str, Any]) -> int:
        return sum(
            len((asset_state.get("samples") or []))
            for asset_state in ((state.get("assets") or {}).values())
        )

    def _capture_assets(
        self, specs: list[dict[str, Any]], current_state: dict[str, Any], refresh: bool
    ) -> dict[str, Any]:
        ingestion = MacroIngestionService(store=self.store)
        assets_state = current_state.get("assets", {}) or {}
        now_utc = _utc_now()

        for spec in specs:
            ticker = spec["ticker"]
            asset_state = assets_state.setdefault(
                ticker,
                {
                    "key": spec["key"],
                    "label": spec["label"],
                    "ticker": ticker,
                    "samples": [],
                },
            )
            samples = asset_state.get("samples", []) or []
            if not refresh and not self._sample_is_stale(samples):
                asset_state["samples"] = self._trim_samples(samples)
                continue

            snapshot = ingestion._collect_contract_snapshot(ticker)
            sample = self._build_sample(spec, snapshot)
            samples.append(sample)
            session_candles, session_candles_error, session_date = self._fetch_session_candles(
                ingestion, ticker, now_utc
            )
            existing_session_date = str(asset_state.get("session_date") or "")
            existing_session_candles = asset_state.get("session_candles_1m") or []
            merged_session_candles: list[dict[str, Any]] = []
            if existing_session_date == session_date:
                merged_session_candles = self._dedupe_candles(existing_session_candles)
            merged_session_candles = self._dedupe_candles(
                merged_session_candles
                + ((snapshot.get("ohlcv") or {}).get("candles_1m") or [])
                + session_candles,
                limit=max(180, int(self.config.MACRO_PARTICIPANT_HEATMAP_DAY_CANDLE_LIMIT)),
            )
            asset_state.update(
                {
                    "key": spec["key"],
                    "label": spec["label"],
                    "ticker": ticker,
                    "samples": self._trim_samples(samples),
                    "latest_candles_1m": ((snapshot.get("ohlcv") or {}).get("candles_1m") or [])[
                        -self.config.MACRO_PARTICIPANT_HEATMAP_CANDLE_LIMIT :
                    ],
                    "session_candles_1m": merged_session_candles,
                    "session_date": session_date,
                    "session_candles_error": session_candles_error,
                }
            )

        current_state["generated_at"] = _utc_now().isoformat()
        current_state["sample_interval_seconds"] = int(
            self.config.MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS
        )
        current_state["history_minutes"] = int(
            self.config.MACRO_PARTICIPANT_HEATMAP_HISTORY_MINUTES
        )
        current_state["collector"] = {
            **(current_state.get("collector") or {}),
            "enabled": bool(self.config.MACRO_PARTICIPANT_HEATMAP_ENABLE),
            "auto_start": bool(self.config.MACRO_PARTICIPANT_HEATMAP_AUTO_START),
            "interval_seconds": int(self.config.MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS),
            "session_sample_limit": int(self.config.MACRO_PARTICIPANT_HEATMAP_SESSION_SAMPLE_LIMIT),
            "last_completed_at": current_state["generated_at"],
            "last_error": None,
        }
        current_state["assets"] = assets_state
        return current_state

    def capture_once(self, refresh: bool = True) -> dict[str, Any]:
        with self._lock:
            state = self._read_state()
            specs = self._asset_specs()
            collector_state = {**(state.get("collector") or {})}
            collector_state.update(
                {
                    "enabled": bool(self.config.MACRO_PARTICIPANT_HEATMAP_ENABLE),
                    "auto_start": bool(self.config.MACRO_PARTICIPANT_HEATMAP_AUTO_START),
                    "interval_seconds": int(self.config.MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS),
                    "session_sample_limit": int(
                        self.config.MACRO_PARTICIPANT_HEATMAP_SESSION_SAMPLE_LIMIT
                    ),
                }
            )
            state["collector"] = collector_state
            try:
                state = self._capture_assets(specs, state, refresh=refresh)
                state["collector"] = {
                    **(state.get("collector") or {}),
                    "sample_count": self._count_samples(state),
                    "last_error": None,
                }
            except Exception as exc:
                state["collector"] = {
                    **(state.get("collector") or {}),
                    "last_error": str(exc),
                }
                self._write_state(state)
                raise
            self._write_state(state)
            return state

    def collector_status(self) -> dict[str, Any]:
        state = self._read_state()
        collector = {
            **(state.get("collector") or {}),
            "sample_count": self._count_samples(state),
        }
        return collector

    def _build_asset_panel(self, asset_state: dict[str, Any]) -> dict[str, Any]:
        samples = asset_state.get("samples", []) or []
        latest = samples[-1] if samples else {}
        heat_points: list[dict[str, Any]] = []
        participant_catalog: dict[str, dict[str, Any]] = {}
        negative_seen = False
        positive_seen = False
        configured_render_lookback_minutes = max(
            5, int(self.config.MACRO_PARTICIPANT_HEATMAP_RENDER_LOOKBACK_MINUTES)
        )

        for sample in samples:
            captured_at = sample.get("captured_at")
            captured_dt = _parse_iso(captured_at)
            sample_price = sample.get("last_price")
            sample_candle_time = (sample.get("last_candle") or {}).get("time")
            sample_candle_dt = _parse_iso(sample_candle_time)
            participants = sample.get("participants", []) or []
            for row in participants:
                row_scope = row.get("origin_scope")
                row_segment = row.get("broker_segment")
                if row_scope in {None, "", "local_or_unclassified"} or row_segment in {
                    None,
                    "",
                    "local_or_unclassified",
                }:
                    origin = self._classify_broker_origin(row.get("broker_name"))
                else:
                    origin = {
                        "is_foreign_broker": row.get("is_foreign_broker"),
                        "is_retail_broker": row.get("is_retail_broker"),
                        "broker_segment": row.get("broker_segment"),
                        "origin_scope": row.get("origin_scope"),
                        "origin_confidence": row.get("origin_confidence"),
                        "origin_registry_key": row.get("origin_registry_key"),
                        "origin_label": row.get("origin_label"),
                        "origin_country": row.get("origin_country"),
                        "origin_region": row.get("origin_region"),
                    }
                quantity = row.get("quantity_float") or 0.0
                side = row.get("side") or "flat"
                if quantity < 0:
                    negative_seen = True
                if quantity > 0:
                    positive_seen = True
                broker_key = f"{row.get('broker_id')}::{row.get('broker_name')}"
                catalog_entry = participant_catalog.setdefault(
                    broker_key,
                    {
                        "broker_id": row.get("broker_id"),
                        "broker_name": row.get("broker_name"),
                        "cumulative_quantity": 0.0,
                        "max_relative_percentage": 0.0,
                        "sample_count": 0,
                        "last_average_price": None,
                        "last_side": side,
                        "is_foreign_broker": bool(origin.get("is_foreign_broker")),
                        "is_retail_broker": bool(origin.get("is_retail_broker")),
                        "broker_segment": origin.get("broker_segment"),
                        "origin_scope": origin.get("origin_scope"),
                        "origin_confidence": origin.get("origin_confidence"),
                        "origin_registry_key": origin.get("origin_registry_key"),
                        "origin_label": origin.get("origin_label"),
                        "origin_country": origin.get("origin_country"),
                        "origin_region": origin.get("origin_region"),
                    },
                )
                catalog_entry["cumulative_quantity"] += abs(quantity)
                catalog_entry["max_relative_percentage"] = max(
                    catalog_entry["max_relative_percentage"],
                    abs(row.get("relative_percentage_float") or 0.0),
                )
                catalog_entry["sample_count"] += 1
                catalog_entry["last_average_price"] = row.get("average_price_float")
                catalog_entry["last_side"] = side

                heat_points.append(
                    {
                        "point_id": f"{captured_at}:{row.get('broker_id')}",
                        "captured_at": captured_at,
                        "captured_at_epoch": captured_dt.timestamp() if captured_dt else 0.0,
                        "sample_candle_time": sample_candle_time,
                        "sample_candle_epoch": sample_candle_dt.timestamp()
                        if sample_candle_dt
                        else 0.0,
                        "broker_id": row.get("broker_id"),
                        "broker_name": row.get("broker_name"),
                        "average_price": row.get("average_price"),
                        "average_price_float": row.get("average_price_float"),
                        "quantity": row.get("quantity"),
                        "quantity_float": quantity,
                        "percentage_float": row.get("percentage_float"),
                        "relative_percentage_float": row.get("relative_percentage_float"),
                        "last_price": sample_price,
                        "side": side,
                        "side_confidence": "confirmed" if negative_seen else "provisional",
                        "intensity_raw": row.get("intensity_raw") or 0.0,
                        "is_foreign_broker": bool(origin.get("is_foreign_broker")),
                        "is_retail_broker": bool(origin.get("is_retail_broker")),
                        "broker_segment": origin.get("broker_segment"),
                        "origin_scope": origin.get("origin_scope"),
                        "origin_confidence": origin.get("origin_confidence"),
                        "origin_registry_key": origin.get("origin_registry_key"),
                        "origin_label": origin.get("origin_label"),
                        "origin_country": origin.get("origin_country"),
                        "origin_region": origin.get("origin_region"),
                    }
                )

        max_intensity = (
            max((point.get("intensity_raw") or 0.0) for point in heat_points)
            if heat_points
            else 0.0
        )
        for point in heat_points:
            ratio = (point.get("intensity_raw") or 0.0) / max(max_intensity, 1.0)
            point["intensity_score"] = round(_clamp(ratio, 0.08, 1.0), 4)

        heat_points.sort(
            key=lambda item: (
                float(item.get("sample_candle_epoch") or item.get("captured_at_epoch") or 0.0),
                float(item.get("captured_at_epoch") or 0.0),
                int(item.get("broker_id") or 0),
            )
        )
        max(1, int(self.config.MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS))
        participant_limit = max(1, int(self.config.MACRO_PARTICIPANT_HEATMAP_PARTICIPANT_LIMIT))
        render_sample_frame_limit = max(5, len(samples))
        distinct_timestamps = sorted(
            {str(item.get("captured_at")) for item in heat_points if item.get("captured_at")}
        )
        if len(distinct_timestamps) > render_sample_frame_limit:
            selected_timestamps = set(distinct_timestamps[-render_sample_frame_limit:])
            heat_points = [
                item for item in heat_points if item.get("captured_at") in selected_timestamps
            ]

        # Safety cap should never collapse the time window just because participant rows increased.
        point_limit = max(
            120,
            int(self.config.MACRO_PARTICIPANT_HEATMAP_POINT_LIMIT),
            render_sample_frame_limit * participant_limit,
        )
        if len(heat_points) > point_limit:
            heat_points = heat_points[-point_limit:]

        for point in heat_points:
            point.pop("sample_candle_epoch", None)
            point.pop("captured_at_epoch", None)

        participant_list = sorted(
            participant_catalog.values(),
            key=lambda item: (
                item.get("cumulative_quantity") or 0.0,
                item.get("max_relative_percentage") or 0.0,
            ),
            reverse=True,
        )[: self.config.MACRO_PARTICIPANT_HEATMAP_CATALOG_LIMIT]

        side_note = (
            "Signed participant balance observed in the lookback window."
            if negative_seen
            else "Current SDK window only exposed non-negative balances; cold tones are provisional until a signed sell balance appears."
        )

        latest_participants = (latest.get("participants") or [])[:10]
        latest_candles = asset_state.get("latest_candles_1m") or []
        session_candles = asset_state.get("session_candles_1m") or latest_candles
        oldest_sample_dt = _parse_iso((samples[0] or {}).get("captured_at")) if samples else None
        newest_sample_dt = _parse_iso((samples[-1] or {}).get("captured_at")) if samples else None
        if oldest_sample_dt and newest_sample_dt and newest_sample_dt >= oldest_sample_dt:
            session_span_minutes = max(
                1, int((newest_sample_dt - oldest_sample_dt).total_seconds() / 60) + 1
            )
        else:
            session_span_minutes = configured_render_lookback_minutes
        pressure_model = self._build_pressure_model(samples)
        cohort_value_map = self._build_cohort_value_map(samples)
        flow_regime_classifier = self._build_flow_regime_classifier(
            pressure_model, cohort_value_map
        )
        divergence_model = self._build_divergence_model(pressure_model)
        level_defense_model = self._build_level_defense_model(cohort_value_map)
        concentration_model = self._build_concentration_model(samples)

        return {
            "key": asset_state.get("key"),
            "label": asset_state.get("label"),
            "ticker": asset_state.get("ticker"),
            "sample_count": len(samples),
            "generated_at": latest.get("captured_at"),
            "latest_price": latest.get("last_price"),
            "price_source": latest.get("price_source"),
            "best_bid": latest.get("best_bid"),
            "best_ask": latest.get("best_ask"),
            "spread": latest.get("spread"),
            "imbalance": latest.get("imbalance"),
            "last_candle": latest.get("last_candle") or {},
            "candles_1m": self._dedupe_candles(
                session_candles,
                limit=max(180, int(self.config.MACRO_PARTICIPANT_HEATMAP_DAY_CANDLE_LIMIT)),
            ),
            "latest_candles_1m": latest_candles[
                -self.config.MACRO_PARTICIPANT_HEATMAP_CANDLE_LIMIT :
            ],
            "latest_participants": latest_participants,
            "participant_catalog": participant_list,
            "heat_points": heat_points,
            "samples_with_negative_balance": sum(
                1
                for sample in samples
                if any(
                    (row.get("quantity_float") or 0.0) < 0
                    for row in (sample.get("participants") or [])
                )
            ),
            "render_lookback_minutes": session_span_minutes,
            "render_point_count": len(heat_points),
            "session_date": asset_state.get("session_date"),
            "session_candles_error": asset_state.get("session_candles_error"),
            "pressure_model": pressure_model,
            "cohort_value_map": cohort_value_map,
            "flow_regime_classifier": flow_regime_classifier,
            "divergence_model": divergence_model,
            "level_defense_model": level_defense_model,
            "concentration_model": concentration_model,
            "side_confidence": "confirmed" if negative_seen and positive_seen else "provisional",
            "side_note": side_note,
            "side_available": bool(positive_seen or negative_seen),
            "foreign_broker_count": sum(
                1 for item in participant_list if item.get("origin_scope") == "foreign"
            ),
            "retail_broker_count": sum(
                1 for item in participant_list if item.get("origin_scope") == "retail"
            ),
        }

    def get_panel(self, refresh: bool = False) -> dict[str, Any]:
        if not refresh:
            cached = self._panel_cache
            cache_age = time.time() - self._panel_cache_at
            if cached and cache_age <= 30.0:
                try:
                    raw_cached_assets = cached.get("assets")
                    cached_assets = raw_cached_assets if isinstance(raw_cached_assets, list) else []
                    cached_win: dict[str, Any] = next(
                        (
                            item
                            for item in cached_assets
                            if isinstance(item, dict)
                            and str(item.get("key") or "").lower() == "win"
                        ),
                        {},
                    )
                    cached_win_sample_at = _parse_iso(
                        (
                            (
                                (cached_win.get("fair_value_history") or {}).get("latest_sample")
                                or {}
                            ).get("captured_at")
                        )
                    )
                    options_state = self.options_heatmap_manager.service.read_state()
                    latest_options_sample_at = _parse_iso(
                        (
                            (
                                (options_state.get("fair_value_history") or {}).get("latest_sample")
                                or {}
                            ).get("captured_at")
                        )
                    )
                    if latest_options_sample_at is not None and (
                        cached_win_sample_at is None
                        or latest_options_sample_at > cached_win_sample_at
                    ):
                        cached = None
                    else:
                        return deepcopy(cached)
                except Exception:
                    if cached is not None:
                        return deepcopy(cached)

        with self._lock:
            state = self._read_state()
            specs = self._asset_specs()
            has_cached_assets = self._state_has_cached_assets(state)
            should_capture = refresh or not has_cached_assets
            if should_capture:
                state = self._capture_assets(specs, state, refresh=refresh)
                self._write_state(state)

        visible_specs = [spec for spec in specs if spec.get("visible", True)]
        assets = []
        for spec in visible_specs:
            asset_state = (state.get("assets", {}) or {}).get(spec["ticker"]) or {
                "key": spec["key"],
                "label": spec["label"],
                "ticker": spec["ticker"],
                "samples": [],
            }
            assets.append(self._build_asset_panel(asset_state))

        cross_asset_flow_package = self._build_cross_asset_flow_package(state, specs)
        structural_divergence_model = self._build_structural_divergence_model(
            assets, cross_asset_flow_package
        )
        continuation_reversal_model = self._build_continuation_reversal_model(
            assets,
            cross_asset_flow_package,
            structural_divergence_model,
        )
        news_thermometer_context = self._build_news_thermometer_context()
        win_trade_thermometer = self._build_win_trade_thermometer(
            assets,
            cross_asset_flow_package,
            structural_divergence_model,
            continuation_reversal_model,
            news_thermometer_context,
        )
        options_heatmap_manager = self.options_heatmap_manager
        options_heatmap_manager.resume_if_needed()
        options_heatmap_context = options_heatmap_manager.service.build_payload(refresh=refresh)
        liquidity_intelligence_model = self._build_liquidity_intelligence_model(
            assets,
            cross_asset_flow_package,
            structural_divergence_model,
            continuation_reversal_model,
            news_thermometer_context,
            win_trade_thermometer,
        )
        liquidity_pool_model = self._build_liquidity_pool_model(
            assets,
            cross_asset_flow_package,
            structural_divergence_model,
            continuation_reversal_model,
            news_thermometer_context,
            win_trade_thermometer,
            liquidity_intelligence_model,
        )
        options_flow_alignment_model = self._build_options_flow_alignment_model(
            assets,
            cross_asset_flow_package,
            win_trade_thermometer,
            liquidity_intelligence_model,
            options_heatmap_context,
        )
        liquidity_asset_map = liquidity_intelligence_model.get("assets") or {}
        liquidity_pool_asset_map = liquidity_pool_model.get("assets") or {}
        options_gamma_context = json.loads(
            json.dumps(options_heatmap_context.get("gamma_context") or {})
        )
        options_fair_value_history = json.loads(
            json.dumps(options_heatmap_context.get("fair_value_history") or {})
        )
        options_live_capture_history = json.loads(
            json.dumps(options_heatmap_context.get("live_capture_history") or {})
        )
        for asset in assets:
            asset["liquidity_intelligence"] = liquidity_asset_map.get(asset.get("key"))
            asset["liquidity_pools"] = liquidity_pool_asset_map.get(asset.get("key"))
            if asset.get("key") == "win":
                asset["gamma_context"] = json.loads(json.dumps(options_gamma_context))
                asset["fair_value_history"] = json.loads(json.dumps(options_fair_value_history))
                asset["live_capture_history"] = json.loads(json.dumps(options_live_capture_history))
                asset["options_flow_alignment"] = json.loads(
                    json.dumps(options_flow_alignment_model or {})
                )
            else:
                asset["gamma_context"] = {}
                asset["fair_value_history"] = {}
                asset["live_capture_history"] = {}
                asset["options_flow_alignment"] = {}

        result = {
            "generated_at": state.get("generated_at"),
            "sample_interval_seconds": state.get("sample_interval_seconds"),
            "history_minutes": state.get("history_minutes"),
            "collector": self.collector_status(),
            "foreign_registry": [
                {
                    "registry_key": item.get("registry_key"),
                    "canonical_name": item.get("canonical_name"),
                    "country": item.get("country"),
                    "region": item.get("region"),
                }
                for item in DEFAULT_FOREIGN_BROKER_REGISTRY
            ],
            "retail_registry": [
                {
                    "registry_key": item.get("registry_key"),
                    "canonical_name": item.get("canonical_name"),
                    "country": item.get("country"),
                    "region": item.get("region"),
                }
                for item in DEFAULT_RETAIL_BROKER_REGISTRY
            ],
            "assets": assets,
            "cross_asset_flow_package": cross_asset_flow_package,
            "structural_divergence_model": structural_divergence_model,
            "continuation_reversal_model": continuation_reversal_model,
            "news_thermometer_context": news_thermometer_context,
            "win_trade_thermometer": win_trade_thermometer,
            "options_heatmap_context": {
                "collector": json.loads(json.dumps(options_heatmap_context.get("collector") or {})),
            },
            "options_flow_alignment_model": options_flow_alignment_model,
            "liquidity_intelligence_model": liquidity_intelligence_model,
            "liquidity_pool_model": liquidity_pool_model,
            "notes": [
                "Heatmap points are sampled from the existing participant net feed every 15 seconds by a dedicated background collector.",
                "Cold tones map to positive participant balance and warm tones to negative balance when signed rows are available.",
                "If the current SDK window only exposes non-negative balances, the panel keeps the side as provisional and highlights the limitation.",
            ],
        }
        self._panel_cache = json.loads(json.dumps(result, ensure_ascii=False, default=str))
        self._panel_cache_at = time.time()
        return result
