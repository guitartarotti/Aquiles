from __future__ import annotations

import json
import math
import os
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from ..config import Config
from ..utils.logger import get_logger
from .fair_value_legs_contracts import (
    BENCHMARK_SYMBOL,
    LEG_DEFINITION_VERSION,
    LOCAL_TZ,
    RPC_COMPONENT_VERSION_DEFINITIONS,
)
from .fair_value_legs_contracts import (
    DEFAULT_LEG_DEFINITIONS as DEFAULT_LEG_DEFINITIONS,
)
from .fair_value_legs_contracts import (
    RPC_COMPONENT_DEFINITIONS as RPC_COMPONENT_DEFINITIONS,
)
from .fair_value_legs_math import (
    _mean,
    _minutes_from_hhmm,
    _safe_float,
)
from .fair_value_legs_model import FairValueLegsModelMixin
from .market_screen_chart_service import MarketScreenChartService

logger = get_logger("aquiles.fair_value_legs_chart")

class FairValueLegsChartService(FairValueLegsModelMixin):
    """Builds a compact XB1 fair-value-by-legs payload from saved W32 captures."""

    def __init__(self, chart_service: MarketScreenChartService | None = None) -> None:
        self.chart_service = chart_service or MarketScreenChartService()
        self.history_store = self.chart_service.history_store
        self.root_dir = os.path.abspath(
            os.path.join(Config.OPTIONS_DATA_DIR, "market_screen_capture")
        )
        self.rows_dir = os.path.join(self.root_dir, "rows")
        self.payload_cache_path = os.path.join(self.root_dir, "fair_value_legs_chart_latest.json")
        self._cache_lock = threading.RLock()
        self._base_build_lock = threading.Lock()
        self._snapshot_refresh_lock = threading.Lock()
        self._snapshot_refresh_thread: threading.Thread | None = None
        self._frame_cache: dict[tuple[Any, ...], pd.DataFrame] = {}
        self._base_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._payload_cache: dict[tuple[Any, ...], dict[str, Any]] = {}

    def _normalize_symbol(self, value: Any, cache: dict[str, str] | None = None) -> str:
        if cache is not None:
            return self.chart_service._resolve_symbol_cached(value, cache)
        return self.chart_service._resolve_symbol(value)

    def _load_payload_snapshot(self) -> dict[str, Any] | None:
        try:
            with open(self.payload_cache_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return None
        if not isinstance(payload, dict) or not payload.get("ok"):
            return None
        if payload.get("leg_definition_version") != LEG_DEFINITION_VERSION:
            return None
        payload = deepcopy(payload)
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        payload["cache_stale"] = True
        payload["cache_source"] = "disk_snapshot"
        return payload

    @staticmethod
    def _payload_last_session_date(payload: dict[str, Any] | None) -> str | None:
        if not isinstance(payload, dict):
            return None
        session_dates: list[str] = []
        for item in payload.get("sessions") or []:
            if isinstance(item, dict):
                value = str(item.get("date") or item.get("session_date") or "").strip()
                if value:
                    session_dates.append(value[:10])
        rows = payload.get("chart_rows") or []
        if rows and isinstance(rows[-1], dict):
            value = str(rows[-1].get("session_date") or "").strip()
            if value:
                session_dates.append(value[:10])
        return max(session_dates) if session_dates else None

    @staticmethod
    def payload_last_timestamp_ms(payload: dict[str, Any] | None) -> int | None:
        if not isinstance(payload, dict):
            return None
        candidates: list[float] = []
        rows = payload.get("chart_rows") or []
        if rows and isinstance(rows[-1], dict):
            value = _safe_float(rows[-1].get("timestamp_ms"))
            if value is not None:
                candidates.append(value)
        latest = payload.get("latest")
        if isinstance(latest, dict):
            value = _safe_float(latest.get("timestamp_ms"))
            if value is not None:
                candidates.append(value)
        if not candidates:
            return None
        return int(max(candidates))

    def latest_available_session_date(self, sessions: int = 3) -> str | None:
        dates: list[str] = []
        for path in self._candidate_row_files(max(int(sessions or 3), 1)):
            session_date = self.chart_service._row_file_date(path)
            if session_date is not None:
                dates.append(session_date.isoformat())
        return max(dates) if dates else None

    def payload_covers_latest_available_session(
        self,
        payload: dict[str, Any] | None,
        *,
        sessions: int = 3,
    ) -> bool:
        latest_available = self.latest_available_session_date(sessions)
        payload_last = self._payload_last_session_date(payload)
        if not latest_available:
            return True
        if not payload_last:
            return False
        return payload_last >= latest_available

    def apply_live_overlay(
        self,
        payload: dict[str, Any],
        *,
        sessions: int = 3,
        bar_minutes: int = 5,
        session_start: str = "09:00",
        session_end: str = "18:30",
    ) -> dict[str, Any]:
        if not isinstance(payload, dict) or not payload.get("ok"):
            return payload
        rows = list(payload.get("chart_rows") or [])
        if not rows:
            return payload

        latest_session = self.latest_available_session_date(sessions)
        if not latest_session or self._payload_last_session_date(payload) != latest_session:
            return payload

        paths = [
            path for path in self._candidate_row_files(max(int(sessions or 3), 1))
            if (self.chart_service._row_file_date(path) and self.chart_service._row_file_date(path).isoformat() == latest_session)
        ]
        if not paths:
            return payload

        needed_symbols: set[str] = {BENCHMARK_SYMBOL}
        for leg in payload.get("legs") or []:
            if isinstance(leg, dict) and not bool(leg.get("enabled", True)):
                continue
            for asset in (leg.get("assets") if isinstance(leg, dict) else []) or []:
                if isinstance(asset, dict):
                    if not bool(asset.get("selected", True)):
                        continue
                    symbol = str(asset.get("symbol") or "").strip()
                else:
                    symbol = str(asset or "").strip()
                if symbol:
                    needed_symbols.add(symbol)

        try:
            frame = self._read_recent_rows_from_store(
                paths=paths,
                needed_symbols=needed_symbols,
                session_start_minutes=_minutes_from_hhmm(session_start, 9 * 60),
                session_end_minutes=_minutes_from_hhmm(session_end, (18 * 60) + 30),
                bar_minutes=bar_minutes,
            )
            if frame is None:
                frame = self._read_recent_rows(
                    paths=paths,
                    needed_symbols=needed_symbols,
                    session_start_minutes=_minutes_from_hhmm(session_start, 9 * 60),
                    session_end_minutes=_minutes_from_hhmm(session_end, (18 * 60) + 30),
                )
        except Exception:
            logger.exception("Failed to apply fair-value live overlay")
            return payload

        if frame is None:
            return payload

        if frame.empty:
            return payload
        frame = frame[frame["session_date"].astype(str) == latest_session].copy()
        if frame.empty:
            return payload

        xb1 = frame[frame["symbol"] == BENCHMARK_SYMBOL].copy()
        if xb1.empty:
            return payload

        resolved_bar_minutes = max(int(bar_minutes or 5), 1)
        freq = f"{resolved_bar_minutes}min"
        xb1 = xb1.sort_values("captured_at")
        latest_capture = xb1["captured_at"].max()
        if not isinstance(latest_capture, pd.Timestamp):
            return payload
        latest_bucket = latest_capture.floor(freq)
        bucket_mask = xb1["captured_at"].dt.floor(freq) == latest_bucket
        bucket_xb1 = xb1[bucket_mask].copy()
        if bucket_xb1.empty:
            return payload

        previous_close = None
        for session_info in payload.get("sessions") or []:
            if isinstance(session_info, dict) and str(session_info.get("date") or "") == latest_session:
                previous_close = _safe_float(session_info.get("previous_close"))
                break
        previous_close = previous_close or _safe_float(rows[-1].get("previous_close"))
        if previous_close is None:
            previous_close = self._previous_close_from_session(xb1)
        if previous_close is None:
            return payload

        live_grids = self._build_change_grid(
            frame,
            [{"session_date": latest_session, "timestamp": latest_bucket.isoformat()}],
        )
        live_grid = live_grids.get(latest_session)
        live_row_changes = (
            live_grid.loc[latest_bucket]
            if live_grid is not None and latest_bucket in live_grid.index
            else None
        )
        row_changes: dict[str, float] = {}
        if live_row_changes is not None:
            for symbol, value in live_row_changes.items():
                change_decimal = _safe_float(value)
                if change_decimal is not None:
                    row_changes[str(symbol)] = change_decimal

        stats = payload.get("asset_stats") or {}
        leg_prices: dict[str, float | None] = {}
        leg_pct_moves: dict[str, float | None] = {}
        leg_counts: dict[str, int] = {}
        leg_band_prices: dict[str, tuple[float | None, float | None]] = {}
        leg_band_pct_moves: dict[str, tuple[float | None, float | None]] = {}
        leg_band_pearsons: dict[str, tuple[float | None, float | None]] = {}
        core_leg_keys: set[str] = set()
        shadow_leg_keys: set[str] = set()

        for leg in payload.get("legs") or []:
            if not isinstance(leg, dict):
                continue
            key = str(leg.get("key") or "")
            if not key:
                continue
            enabled = bool(leg.get("enabled", True))
            if leg.get("layer") == "core" and enabled:
                core_leg_keys.add(key)
            if leg.get("layer") == "shadow" and enabled:
                shadow_leg_keys.add(key)
            if not enabled:
                leg_prices[key] = None
                leg_pct_moves[key] = None
                leg_counts[key] = 0
                leg_band_prices[key] = (None, None)
                leg_band_pct_moves[key] = (None, None)
                leg_band_pearsons[key] = (None, None)
                continue

            contributions: list[float] = []
            band_lower_contributions: list[float] = []
            band_upper_contributions: list[float] = []
            pearson_lows: list[float] = []
            pearson_highs: list[float] = []

            for asset in leg.get("assets") or []:
                if isinstance(asset, dict):
                    if not bool(asset.get("selected", True)):
                        continue
                    symbol = str(asset.get("symbol") or "").strip()
                else:
                    symbol = str(asset or "").strip()
                if not symbol:
                    continue
                stat = stats.get(symbol) or {}
                beta = _safe_float(stat.get("effective_beta"))
                change_decimal = _safe_float(row_changes.get(symbol))
                if beta is None or change_decimal is None:
                    continue
                contributions.append(change_decimal * beta)

                pearson_candidates = [
                    value for value in (
                        _safe_float(stat.get("pearson_min")),
                        _safe_float(stat.get("pearson_max")),
                    )
                    if value is not None and math.isfinite(float(value))
                ]
                if pearson_candidates:
                    low_pearson = min(pearson_candidates)
                    high_pearson = max(pearson_candidates)
                    pearson_lows.append(low_pearson)
                    pearson_highs.append(high_pearson)
                    projected_moves = [change_decimal * low_pearson, change_decimal * high_pearson]
                    band_lower_contributions.append(min(projected_moves))
                    band_upper_contributions.append(max(projected_moves))

            leg_move = _mean(contributions)
            leg_pct_moves[key] = leg_move
            leg_counts[key] = len(contributions)
            leg_prices[key] = previous_close * (1.0 + leg_move) if leg_move is not None else None

            band_lower_move = _mean(band_lower_contributions)
            band_upper_move = _mean(band_upper_contributions)
            leg_band_pct_moves[key] = (band_lower_move, band_upper_move)
            leg_band_pearsons[key] = (_mean(pearson_lows), _mean(pearson_highs))
            lower_price = previous_close * (1.0 + band_lower_move) if band_lower_move is not None else None
            upper_price = previous_close * (1.0 + band_upper_move) if band_upper_move is not None else None
            band_candidates = [
                value for value in (lower_price, leg_prices[key], upper_price)
                if value is not None
            ]
            leg_band_prices[key] = (
                min(band_candidates) if band_candidates else None,
                max(band_candidates) if band_candidates else None,
            )

        core_prices = [
            value for key, value in leg_prices.items()
            if key in core_leg_keys and value is not None
        ]
        shadow_prices = [
            value for key, value in leg_prices.items()
            if key in shadow_leg_keys and value is not None
        ]
        core_value = _mean(core_prices)
        shadow_value = _mean(shadow_prices)

        template = deepcopy(rows[-1])
        for index, row in enumerate(rows):
            if str(row.get("session_date") or "") != latest_session:
                continue
            row_ts = pd.to_datetime(row.get("timestamp"), utc=True, errors="coerce")
            if isinstance(row_ts, pd.Timestamp) and row_ts == latest_bucket:
                template = deepcopy(row)
                break

        close_price = _safe_float(bucket_xb1["price"].iloc[-1])
        high_price = _safe_float(bucket_xb1["price"].max())
        low_price = _safe_float(bucket_xb1["price"].min())
        open_price = _safe_float(bucket_xb1["price"].iloc[0])
        latest_change = _safe_float(bucket_xb1["daily_change_pct"].iloc[-1])
        if close_price is None or open_price is None or high_price is None or low_price is None:
            return payload

        chart_row = {
            **template,
            "timestamp": latest_bucket.isoformat(),
            "timestamp_ms": int(latest_bucket.timestamp() * 1000),
            "session_date": latest_session,
            "open": round(open_price, 4),
            "high": round(high_price, 4),
            "low": round(low_price, 4),
            "close": round(close_price, 4),
            "daily_change_pct": round(latest_change, 6) if latest_change is not None else template.get("daily_change_pct"),
            "previous_close": round(previous_close, 4),
            "fair_value_core": round(core_value, 4) if core_value is not None else None,
            "fair_value_shadow": round(shadow_value, 4) if shadow_value is not None else None,
            "live_overlay": True,
            "live_source_timestamp": latest_capture.isoformat(),
            "live_overlay_generated_at": datetime.now(timezone.utc).isoformat(),
        }

        range_points = _safe_float(template.get("fair_value_range_points"))
        if range_points is not None and core_value is not None:
            chart_row["fair_value_core_upper"] = round(core_value + range_points, 4)
            chart_row["fair_value_core_lower"] = round(core_value - range_points, 4)

        for key, value in leg_prices.items():
            chart_row[f"leg_{key}"] = round(value, 4) if value is not None else None
            leg_move_decimal = leg_pct_moves.get(key)
            chart_row[f"leg_{key}_impact_decimal"] = round(leg_move_decimal, 8) if leg_move_decimal is not None else None
            chart_row[f"leg_{key}_impact_points"] = round(previous_close * leg_move_decimal, 4) if leg_move_decimal is not None else None
            chart_row[f"leg_{key}_pct"] = round(leg_move_decimal * 100.0, 6) if leg_move_decimal is not None else None
            chart_row[f"leg_{key}_assets"] = int(leg_counts.get(key) or 0)
            band_lower, band_upper = leg_band_prices.get(key, (None, None))
            band_lower_move, band_upper_move = leg_band_pct_moves.get(key, (None, None))
            pearson_low, pearson_high = leg_band_pearsons.get(key, (None, None))
            chart_row[f"leg_{key}_lower"] = round(band_lower, 4) if band_lower is not None else None
            chart_row[f"leg_{key}_upper"] = round(band_upper, 4) if band_upper is not None else None
            chart_row[f"leg_{key}_band_lower_pct"] = round(band_lower_move * 100.0, 6) if band_lower_move is not None else None
            chart_row[f"leg_{key}_band_upper_pct"] = round(band_upper_move * 100.0, 6) if band_upper_move is not None else None
            chart_row[f"leg_{key}_band_points"] = (
                round((band_upper - band_lower), 4)
                if band_lower is not None and band_upper is not None
                else None
            )
            chart_row[f"leg_{key}_pearson_min_mean"] = round(pearson_low, 6) if pearson_low is not None else None
            chart_row[f"leg_{key}_pearson_max_mean"] = round(pearson_high, 6) if pearson_high is not None else None

        output = deepcopy(payload)
        output_rows = list(output.get("chart_rows") or [])
        replaced = False
        for index, row in enumerate(output_rows):
            if (
                str(row.get("session_date") or "") == latest_session
                and str(row.get("timestamp") or "") == latest_bucket.isoformat()
            ):
                output_rows[index] = chart_row
                replaced = True
                break
        if not replaced:
            output_rows.append(chart_row)
            output_rows.sort(key=lambda row: int(row.get("timestamp_ms") or 0))

        output["chart_rows"] = output_rows
        output["latest"] = chart_row
        output["generated_at"] = datetime.now(timezone.utc).isoformat()
        output["live_overlay"] = True
        output["live_source_timestamp"] = latest_capture.isoformat()
        for session_info in output.get("sessions") or []:
            if isinstance(session_info, dict) and str(session_info.get("date") or "") == latest_session:
                session_info["candle_count"] = sum(
                    1 for item in output_rows if str(item.get("session_date") or "") == latest_session
                )
                break
        return output

    def _legacy_apply_live_overlay(
        self,
        payload: dict[str, Any],
        *,
        sessions: int = 3,
        bar_minutes: int = 5,
        session_start: str = "09:00",
        session_end: str = "18:30",
    ) -> dict[str, Any]:
        if not isinstance(payload, dict) or not payload.get("ok"):
            return payload
        rows = list(payload.get("chart_rows") or [])
        if not rows:
            return payload

        latest_session = self.latest_available_session_date(sessions)
        if not latest_session or self._payload_last_session_date(payload) != latest_session:
            return payload

        paths = [
            path for path in self._candidate_row_files(max(int(sessions or 3), 1))
            if (self.chart_service._row_file_date(path) and self.chart_service._row_file_date(path).isoformat() == latest_session)
        ]
        if not paths:
            return payload

        needed_symbols: set[str] = {BENCHMARK_SYMBOL}
        for leg in payload.get("legs") or []:
            if isinstance(leg, dict) and not bool(leg.get("enabled", True)):
                continue
            for asset in (leg.get("assets") if isinstance(leg, dict) else []) or []:
                if isinstance(asset, dict):
                    if not bool(asset.get("selected", True)):
                        continue
                    symbol = str(asset.get("symbol") or "").strip()
                else:
                    symbol = str(asset or "").strip()
                if symbol:
                    needed_symbols.add(symbol)

        try:
            frame = self._read_recent_rows(
                paths=paths,
                needed_symbols=needed_symbols,
                session_start_minutes=_minutes_from_hhmm(session_start, 9 * 60),
                session_end_minutes=_minutes_from_hhmm(session_end, (18 * 60) + 30),
            )
        except Exception:
            logger.exception("Failed to apply fair-value live overlay")
            return payload

        if frame.empty:
            return payload
        frame = frame[frame["session_date"].astype(str) == latest_session].copy()
        if frame.empty:
            return payload

        xb1 = frame[frame["symbol"] == BENCHMARK_SYMBOL].copy()
        if xb1.empty:
            return payload

        resolved_bar_minutes = max(int(bar_minutes or 5), 1)
        freq = f"{resolved_bar_minutes}min"
        xb1 = xb1.sort_values("captured_at")
        latest_capture = xb1["captured_at"].max()
        if not isinstance(latest_capture, pd.Timestamp):
            return payload
        latest_bucket = latest_capture.floor(freq)
        bucket_mask = xb1["captured_at"].dt.floor(freq) == latest_bucket
        bucket_xb1 = xb1[bucket_mask].copy()
        if bucket_xb1.empty:
            return payload

        previous_close = None
        for session_info in payload.get("sessions") or []:
            if isinstance(session_info, dict) and str(session_info.get("date") or "") == latest_session:
                previous_close = _safe_float(session_info.get("previous_close"))
                break
        previous_close = previous_close or _safe_float(rows[-1].get("previous_close"))
        if previous_close is None:
            previous_close = self._previous_close_from_session(xb1)
        if previous_close is None:
            return payload

        live_grids = self._build_change_grid(
            frame,
            [{"session_date": latest_session, "timestamp": latest_bucket.isoformat()}],
        )
        live_grid = live_grids.get(latest_session)
        live_row_changes = (
            live_grid.loc[latest_bucket]
            if live_grid is not None and latest_bucket in live_grid.index
            else None
        )
        row_changes: dict[str, float] = {}
        if live_row_changes is not None:
            for symbol, value in live_row_changes.items():
                change_decimal = _safe_float(value)
                if change_decimal is not None:
                    row_changes[str(symbol)] = change_decimal

        stats = payload.get("asset_stats") or {}
        leg_prices: dict[str, float | None] = {}
        leg_pct_moves: dict[str, float | None] = {}
        leg_counts: dict[str, int] = {}
        leg_band_prices: dict[str, tuple[float | None, float | None]] = {}
        leg_band_pct_moves: dict[str, tuple[float | None, float | None]] = {}
        leg_band_pearsons: dict[str, tuple[float | None, float | None]] = {}
        core_leg_keys: set[str] = set()
        shadow_leg_keys: set[str] = set()

        for leg in payload.get("legs") or []:
            if not isinstance(leg, dict):
                continue
            key = str(leg.get("key") or "")
            if not key:
                continue
            enabled = bool(leg.get("enabled", True))
            if leg.get("layer") == "core" and enabled:
                core_leg_keys.add(key)
            if leg.get("layer") == "shadow" and enabled:
                shadow_leg_keys.add(key)
            if not enabled:
                leg_prices[key] = None
                leg_pct_moves[key] = None
                leg_counts[key] = 0
                leg_band_prices[key] = (None, None)
                leg_band_pct_moves[key] = (None, None)
                leg_band_pearsons[key] = (None, None)
                continue

            contributions: list[float] = []
            band_lower_contributions: list[float] = []
            band_upper_contributions: list[float] = []
            pearson_lows: list[float] = []
            pearson_highs: list[float] = []

            for asset in leg.get("assets") or []:
                if isinstance(asset, dict):
                    if not bool(asset.get("selected", True)):
                        continue
                    symbol = str(asset.get("symbol") or "").strip()
                else:
                    symbol = str(asset or "").strip()
                if not symbol:
                    continue
                stat = stats.get(symbol) or {}
                beta = _safe_float(stat.get("effective_beta"))
                change_decimal = _safe_float(row_changes.get(symbol))
                if beta is None or change_decimal is None:
                    continue
                contributions.append(change_decimal * beta)

                pearson_candidates = [
                    value for value in (
                        _safe_float(stat.get("pearson_min")),
                        _safe_float(stat.get("pearson_max")),
                    )
                    if value is not None and math.isfinite(float(value))
                ]
                if pearson_candidates:
                    low_pearson = min(pearson_candidates)
                    high_pearson = max(pearson_candidates)
                    pearson_lows.append(low_pearson)
                    pearson_highs.append(high_pearson)
                    projected_moves = [change_decimal * low_pearson, change_decimal * high_pearson]
                    band_lower_contributions.append(min(projected_moves))
                    band_upper_contributions.append(max(projected_moves))

            leg_move = _mean(contributions)
            leg_pct_moves[key] = leg_move
            leg_counts[key] = len(contributions)
            leg_prices[key] = previous_close * (1.0 + leg_move) if leg_move is not None else None

            band_lower_move = _mean(band_lower_contributions)
            band_upper_move = _mean(band_upper_contributions)
            leg_band_pct_moves[key] = (band_lower_move, band_upper_move)
            leg_band_pearsons[key] = (_mean(pearson_lows), _mean(pearson_highs))
            lower_price = previous_close * (1.0 + band_lower_move) if band_lower_move is not None else None
            upper_price = previous_close * (1.0 + band_upper_move) if band_upper_move is not None else None
            band_candidates = [
                value for value in (lower_price, leg_prices[key], upper_price)
                if value is not None
            ]
            leg_band_prices[key] = (
                min(band_candidates) if band_candidates else None,
                max(band_candidates) if band_candidates else None,
            )

        core_prices = [
            value for key, value in leg_prices.items()
            if key in core_leg_keys and value is not None
        ]
        shadow_prices = [
            value for key, value in leg_prices.items()
            if key in shadow_leg_keys and value is not None
        ]
        core_value = _mean(core_prices)
        shadow_value = _mean(shadow_prices)

        template = deepcopy(rows[-1])
        for index, row in enumerate(rows):
            if str(row.get("session_date") or "") != latest_session:
                continue
            row_ts = pd.to_datetime(row.get("timestamp"), utc=True, errors="coerce")
            if isinstance(row_ts, pd.Timestamp) and row_ts == latest_bucket:
                template = deepcopy(row)
                break

        close_price = _safe_float(bucket_xb1["price"].iloc[-1])
        high_price = _safe_float(bucket_xb1["price"].max())
        low_price = _safe_float(bucket_xb1["price"].min())
        open_price = _safe_float(bucket_xb1["price"].iloc[0])
        latest_change = _safe_float(bucket_xb1["daily_change_pct"].iloc[-1])
        if close_price is None or open_price is None or high_price is None or low_price is None:
            return payload

        chart_row = {
            **template,
            "timestamp": latest_bucket.isoformat(),
            "timestamp_ms": int(latest_bucket.timestamp() * 1000),
            "session_date": latest_session,
            "open": round(open_price, 4),
            "high": round(high_price, 4),
            "low": round(low_price, 4),
            "close": round(close_price, 4),
            "daily_change_pct": round(latest_change, 6) if latest_change is not None else template.get("daily_change_pct"),
            "previous_close": round(previous_close, 4),
            "fair_value_core": round(core_value, 4) if core_value is not None else None,
            "fair_value_shadow": round(shadow_value, 4) if shadow_value is not None else None,
            "live_overlay": True,
            "live_source_timestamp": latest_capture.isoformat(),
            "live_overlay_generated_at": datetime.now(timezone.utc).isoformat(),
        }

        range_points = _safe_float(template.get("fair_value_range_points"))
        if range_points is not None and core_value is not None:
            chart_row["fair_value_core_upper"] = round(core_value + range_points, 4)
            chart_row["fair_value_core_lower"] = round(core_value - range_points, 4)

        for key, value in leg_prices.items():
            chart_row[f"leg_{key}"] = round(value, 4) if value is not None else None
            leg_move_decimal = leg_pct_moves.get(key)
            chart_row[f"leg_{key}_impact_decimal"] = round(leg_move_decimal, 8) if leg_move_decimal is not None else None
            chart_row[f"leg_{key}_impact_points"] = round(previous_close * leg_move_decimal, 4) if leg_move_decimal is not None else None
            chart_row[f"leg_{key}_pct"] = round(leg_move_decimal * 100.0, 6) if leg_move_decimal is not None else None
            chart_row[f"leg_{key}_assets"] = int(leg_counts.get(key) or 0)
            band_lower, band_upper = leg_band_prices.get(key, (None, None))
            band_lower_move, band_upper_move = leg_band_pct_moves.get(key, (None, None))
            pearson_low, pearson_high = leg_band_pearsons.get(key, (None, None))
            chart_row[f"leg_{key}_lower"] = round(band_lower, 4) if band_lower is not None else None
            chart_row[f"leg_{key}_upper"] = round(band_upper, 4) if band_upper is not None else None
            chart_row[f"leg_{key}_band_lower_pct"] = round(band_lower_move * 100.0, 6) if band_lower_move is not None else None
            chart_row[f"leg_{key}_band_upper_pct"] = round(band_upper_move * 100.0, 6) if band_upper_move is not None else None
            chart_row[f"leg_{key}_band_points"] = (
                round((band_upper - band_lower), 4)
                if band_lower is not None and band_upper is not None
                else None
            )
            chart_row[f"leg_{key}_pearson_min_mean"] = round(pearson_low, 6) if pearson_low is not None else None
            chart_row[f"leg_{key}_pearson_max_mean"] = round(pearson_high, 6) if pearson_high is not None else None

        output = deepcopy(payload)
        output_rows = list(output.get("chart_rows") or [])
        replaced = False
        for index, row in enumerate(output_rows):
            if (
                str(row.get("session_date") or "") == latest_session
                and str(row.get("timestamp") or "") == latest_bucket.isoformat()
            ):
                output_rows[index] = chart_row
                replaced = True
                break
        if not replaced:
            output_rows.append(chart_row)
            output_rows.sort(key=lambda row: int(row.get("timestamp_ms") or 0))

        output["chart_rows"] = output_rows
        output["latest"] = chart_row
        output["generated_at"] = datetime.now(timezone.utc).isoformat()
        output["live_overlay"] = True
        output["live_source_timestamp"] = latest_capture.isoformat()
        for session_info in output.get("sessions") or []:
            if isinstance(session_info, dict) and str(session_info.get("date") or "") == latest_session:
                session_info["candle_count"] = sum(
                    1 for item in output_rows if str(item.get("session_date") or "") == latest_session
                )
                break
        return output

    def _store_payload_snapshot(self, payload: dict[str, Any]) -> None:
        if not payload.get("ok"):
            return
        try:
            existing = self._load_payload_snapshot()
            existing_last_timestamp = self.payload_last_timestamp_ms(existing)
            next_last_timestamp = self.payload_last_timestamp_ms(payload)
            if (
                existing_last_timestamp is not None
                and next_last_timestamp is not None
                and existing_last_timestamp > next_last_timestamp
            ):
                logger.info(
                    "Skipping stale fair-value legs snapshot overwrite: existing_ts=%s next_ts=%s",
                    existing_last_timestamp,
                    next_last_timestamp,
                )
                return

            existing_last_session = self._payload_last_session_date(existing)
            next_last_session = self._payload_last_session_date(payload)
            latest_available_session = self.latest_available_session_date(
                int(payload.get("requested_sessions") or 3)
            )
            if (
                latest_available_session
                and next_last_session
                and next_last_session < latest_available_session
            ):
                logger.info(
                    "Skipping fair-value legs snapshot that misses latest available session: latest_available=%s next_session=%s",
                    latest_available_session,
                    next_last_session,
                )
                return
            if (
                existing_last_session
                and next_last_session
                and existing_last_session > next_last_session
            ):
                logger.info(
                    "Skipping stale fair-value legs snapshot overwrite: existing_session=%s next_session=%s",
                    existing_last_session,
                    next_last_session,
                )
                return

            os.makedirs(os.path.dirname(self.payload_cache_path), exist_ok=True)
            tmp_path = (
                f"{self.payload_cache_path}."
                f"{os.getpid()}.{threading.get_ident()}.tmp"
            )
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, allow_nan=False, default=str)
            for attempt in range(5):
                try:
                    os.replace(tmp_path, self.payload_cache_path)
                    break
                except PermissionError:
                    if attempt >= 4:
                        raise
                    time.sleep(0.1 * (attempt + 1))
        except Exception:
            logger.exception("Failed to store fair-value legs payload snapshot")

    def payload_snapshot_age_seconds(self) -> float | None:
        try:
            return max(datetime.now(timezone.utc).timestamp() - os.stat(self.payload_cache_path).st_mtime, 0.0)
        except OSError:
            return None

    def refresh_snapshot_async(self, **kwargs: Any) -> bool:
        with self._snapshot_refresh_lock:
            if self._snapshot_refresh_thread is not None and self._snapshot_refresh_thread.is_alive():
                return False

            def _refresh() -> None:
                try:
                    self.build_payload(**kwargs)
                except Exception:
                    logger.exception("Failed to refresh fair-value legs snapshot in background")

            self._snapshot_refresh_thread = threading.Thread(
                target=_refresh,
                name="fair-value-legs-snapshot-refresh",
                daemon=True,
            )
            self._snapshot_refresh_thread.start()
            return True

    @staticmethod
    def _selected_symbols_from_legs(legs: list[dict[str, Any]]) -> set[str]:
        symbols: set[str] = set()
        for leg in legs or []:
            if not isinstance(leg, dict) or not bool(leg.get("enabled", True)):
                continue
            for asset in leg.get("assets") or []:
                if isinstance(asset, dict):
                    if not bool(asset.get("selected", True)):
                        continue
                    symbol = str(asset.get("symbol") or "").strip()
                else:
                    symbol = str(asset or "").strip()
                if symbol:
                    symbols.add(symbol)
        return symbols

    def _asset_stats_for_hot_payload(
        self,
        *,
        symbols: set[str],
        base_payload: dict[str, Any],
        bar_minutes: int,
        rolling_window_points: int,
        session_start_minutes: int,
        session_end_minutes: int,
    ) -> dict[str, dict[str, Any]]:
        stats = {
            str(symbol): dict(payload)
            for symbol, payload in (base_payload.get("asset_stats") or {}).items()
            if isinstance(payload, dict)
        }
        try:
            stored_stats = self.history_store.query_fair_value_asset_stats(
                symbols,
                bar_minutes=bar_minutes,
                rolling_window_points=rolling_window_points,
                session_start_minutes=session_start_minutes,
                session_end_minutes=session_end_minutes,
            )
            for symbol, payload in stored_stats.items():
                stats[str(symbol)] = dict(payload)
        except Exception:
            logger.debug("Failed to read fair-value hot stats from SQLite", exc_info=True)
        return stats

    def _latest_quotes_for_symbols(self, symbols: set[str]) -> dict[str, dict[str, Any]]:
        latest_path = os.path.join(self.root_dir, "latest.json")
        symbol_cache: dict[str, str] = {}
        quotes: dict[str, dict[str, Any]] = {}
        try:
            with open(latest_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            captured_at = str(payload.get("captured_at") or "").strip()
            try:
                captured_epoch = datetime.fromisoformat(
                    captured_at.replace("Z", "+00:00")
                ).astimezone(timezone.utc).timestamp()
            except Exception:
                captured_epoch = datetime.now(timezone.utc).timestamp()
            for row in payload.get("rows") or []:
                if not isinstance(row, dict):
                    continue
                symbol = self._normalize_symbol(
                    row.get("symbol_normalized") or row.get("symbol") or row.get("symbol_raw"),
                    symbol_cache,
                )
                if symbol not in symbols:
                    continue
                price = _safe_float(row.get("price"))
                if price is None:
                    continue
                daily_change_pct = _safe_float(row.get("daily_change_pct"))
                quotes[symbol] = {
                    "symbol": symbol,
                    "captured_at": captured_at,
                    "captured_at_epoch": captured_epoch,
                    "price": price,
                    "daily_change_pct": daily_change_pct,
                    "change_decimal": (
                        daily_change_pct / 100.0
                        if daily_change_pct is not None and abs(daily_change_pct) < 50.0
                        else None
                    ),
                }
            if quotes:
                return quotes
        except Exception:
            logger.debug("Failed to read latest W32 JSON for fair-value hot quotes", exc_info=True)

        query_symbols = self._store_symbol_query_set(symbols)
        rows = self.history_store.query_latest_symbols(query_symbols)
        for row in rows:
            symbol = self._normalize_symbol(row.get("symbol"), symbol_cache)
            if symbol not in symbols:
                continue
            epoch = _safe_float(row.get("captured_at_epoch"), 0.0) or 0.0
            previous_epoch = _safe_float((quotes.get(symbol) or {}).get("captured_at_epoch"), -1.0) or -1.0
            if epoch < previous_epoch:
                continue
            price = _safe_float(row.get("price"))
            daily_change_pct = _safe_float(row.get("daily_change_pct"))
            if price is None:
                continue
            quotes[symbol] = {
                "symbol": symbol,
                "captured_at": row.get("captured_at"),
                "captured_at_epoch": epoch,
                "price": price,
                "daily_change_pct": daily_change_pct,
                "change_decimal": (
                    daily_change_pct / 100.0
                    if daily_change_pct is not None and abs(daily_change_pct) < 50.0
                    else None
                ),
            }
        return quotes

    def _latest_xb1_candle_from_store(
        self,
        *,
        bar_minutes: int,
        latest_quote: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        quote_epoch = _safe_float((latest_quote or {}).get("captured_at_epoch"))
        if quote_epoch is not None:
            quote_dt = datetime.fromtimestamp(quote_epoch, tz=timezone.utc)
        else:
            quote_dt = datetime.now(timezone.utc)
        local_start = datetime.combine(
            quote_dt.astimezone(LOCAL_TZ).date(),
            datetime.min.time(),
            tzinfo=LOCAL_TZ,
        ).astimezone(timezone.utc)
        records = self.history_store.query_symbol_candles(
            BENCHMARK_SYMBOL,
            bar_minutes=bar_minutes,
            since=local_start,
        )
        if records:
            return records[-1]
        price = _safe_float((latest_quote or {}).get("price"))
        if price is None or quote_epoch is None:
            return None
        bucket_epoch = math.floor(quote_epoch / (max(int(bar_minutes or 5), 1) * 60)) * (max(int(bar_minutes or 5), 1) * 60)
        return {
            "bucket_epoch": float(bucket_epoch),
            "bucket_at": datetime.fromtimestamp(bucket_epoch, tz=timezone.utc).isoformat(),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "last_capture_at_epoch": quote_epoch,
            "daily_change_pct": _safe_float((latest_quote or {}).get("daily_change_pct")),
        }

    @staticmethod
    def _quote_change_decimal(
        quote: dict[str, Any],
        stat: dict[str, Any],
    ) -> float | None:
        daily_change_pct = _safe_float(quote.get("daily_change_pct"))
        daily_decimal = (
            daily_change_pct / 100.0
            if daily_change_pct is not None and abs(daily_change_pct) < 50.0
            else None
        )
        previous_asset_close = _safe_float(stat.get("asset_previous_close"))
        price = _safe_float(quote.get("price"))
        if price is None or previous_asset_close in (None, 0.0):
            return daily_decimal

        price_decimal = (price - previous_asset_close) / previous_asset_close
        price_pct = price_decimal * 100.0
        if daily_change_pct is not None and abs(daily_change_pct) < 50.0:
            mismatch_limit = max((abs(daily_change_pct) * 0.75) + 0.25, 1.50)
            if abs(price_pct - daily_change_pct) > mismatch_limit:
                return daily_decimal
        if abs(price_pct) > 25.0:
            return daily_decimal
        return price_decimal

    def _build_latest_row_fast(
        self,
        *,
        base_payload: dict[str, Any],
        legs: list[dict[str, Any]],
        stats: dict[str, dict[str, Any]],
        bar_minutes: int,
    ) -> dict[str, Any] | None:
        selected_symbols = self._selected_symbols_from_legs(legs)
        needed_symbols = {BENCHMARK_SYMBOL, *selected_symbols}
        quotes = self._latest_quotes_for_symbols(needed_symbols)
        xb1_quote = quotes.get(BENCHMARK_SYMBOL)
        if not xb1_quote:
            return None

        quote_epoch = _safe_float(xb1_quote.get("captured_at_epoch"))
        close_price = _safe_float(xb1_quote.get("price"))
        if quote_epoch is None or close_price is None:
            return None
        seconds = max(int(bar_minutes or 5), 1) * 60
        bucket_epoch = float(math.floor(quote_epoch / seconds) * seconds)
        bucket_at = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc).isoformat()
        bucket_dt = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
        latest_session = bucket_dt.astimezone(LOCAL_TZ).date().isoformat()

        rows = list(base_payload.get("chart_rows") or [])
        if not rows:
            return None
        template = deepcopy(rows[-1])
        for row in rows:
            if str(row.get("session_date") or "") != latest_session:
                continue
            if str(row.get("timestamp") or "") == bucket_at:
                template = deepcopy(row)
                break

        previous_close = None
        for session_info in base_payload.get("sessions") or []:
            if isinstance(session_info, dict) and str(session_info.get("date") or "") == latest_session:
                previous_close = _safe_float(session_info.get("previous_close"))
                break
        previous_close = previous_close or _safe_float(template.get("previous_close"))
        if previous_close is None:
            xb1_price = _safe_float(xb1_quote.get("price"))
            xb1_change = _safe_float(xb1_quote.get("daily_change_pct"))
            denominator = 1.0 + ((xb1_change or 0.0) / 100.0)
            if xb1_price is not None and abs(denominator) > 1e-9:
                previous_close = xb1_price / denominator
        if previous_close is None:
            return None

        same_bucket = str(template.get("timestamp") or "") == bucket_at
        template_open = _safe_float(template.get("open"))
        template_high = _safe_float(template.get("high"))
        template_low = _safe_float(template.get("low"))
        template_close = _safe_float(template.get("close"))
        open_price = (
            template_open
            if same_bucket and template_open is not None
            else (template_close if template_close is not None else previous_close)
        )
        high_price = max(
            value for value in (template_high if same_bucket else None, open_price, close_price)
            if value is not None
        )
        low_price = min(
            value for value in (template_low if same_bucket else None, open_price, close_price)
            if value is not None
        )

        row_changes: dict[str, float] = {}
        for symbol, quote in quotes.items():
            stat = stats.get(symbol) or {}
            change_decimal = self._quote_change_decimal(quote, stat)
            if change_decimal is None:
                change_decimal = _safe_float(quote.get("change_decimal"))
            if change_decimal is not None:
                row_changes[symbol] = change_decimal

        leg_prices: dict[str, float | None] = {}
        leg_pct_moves: dict[str, float | None] = {}
        leg_counts: dict[str, int] = {}
        leg_band_prices: dict[str, tuple[float | None, float | None]] = {}
        leg_band_pct_moves: dict[str, tuple[float | None, float | None]] = {}
        leg_band_pearsons: dict[str, tuple[float | None, float | None]] = {}
        core_leg_keys: set[str] = set()
        shadow_leg_keys: set[str] = set()

        for leg in legs:
            key = str(leg.get("key") or "")
            if not key:
                continue
            enabled = bool(leg.get("enabled", True))
            if leg.get("layer") == "core" and enabled:
                core_leg_keys.add(key)
            if leg.get("layer") == "shadow" and enabled:
                shadow_leg_keys.add(key)
            if not enabled:
                leg_prices[key] = None
                leg_pct_moves[key] = None
                leg_counts[key] = 0
                leg_band_prices[key] = (None, None)
                leg_band_pct_moves[key] = (None, None)
                leg_band_pearsons[key] = (None, None)
                continue

            contributions: list[float] = []
            band_lower_contributions: list[float] = []
            band_upper_contributions: list[float] = []
            pearson_lows: list[float] = []
            pearson_highs: list[float] = []
            for asset in leg.get("assets") or []:
                symbol = str(asset.get("symbol") if isinstance(asset, dict) else asset or "").strip()
                if isinstance(asset, dict) and not bool(asset.get("selected", True)):
                    continue
                stat = stats.get(symbol) or {}
                beta = _safe_float(stat.get("effective_beta"))
                change_decimal = _safe_float(row_changes.get(symbol))
                if beta is None or change_decimal is None:
                    continue
                contributions.append(change_decimal * beta)
                pearson_candidates = [
                    value for value in (
                        _safe_float(stat.get("pearson_min")),
                        _safe_float(stat.get("pearson_max")),
                    )
                    if value is not None and math.isfinite(float(value))
                ]
                if pearson_candidates:
                    low_pearson = min(pearson_candidates)
                    high_pearson = max(pearson_candidates)
                    pearson_lows.append(low_pearson)
                    pearson_highs.append(high_pearson)
                    projected_moves = [change_decimal * low_pearson, change_decimal * high_pearson]
                    band_lower_contributions.append(min(projected_moves))
                    band_upper_contributions.append(max(projected_moves))

            leg_move = _mean(contributions)
            leg_pct_moves[key] = leg_move
            leg_counts[key] = len(contributions)
            leg_prices[key] = previous_close * (1.0 + leg_move) if leg_move is not None else None
            band_lower_move = _mean(band_lower_contributions)
            band_upper_move = _mean(band_upper_contributions)
            leg_band_pct_moves[key] = (band_lower_move, band_upper_move)
            leg_band_pearsons[key] = (_mean(pearson_lows), _mean(pearson_highs))
            lower_price = previous_close * (1.0 + band_lower_move) if band_lower_move is not None else None
            upper_price = previous_close * (1.0 + band_upper_move) if band_upper_move is not None else None
            band_candidates = [
                value for value in (lower_price, leg_prices[key], upper_price)
                if value is not None
            ]
            leg_band_prices[key] = (
                min(band_candidates) if band_candidates else None,
                max(band_candidates) if band_candidates else None,
            )

        core_value = _mean([
            value for key, value in leg_prices.items()
            if key in core_leg_keys and value is not None
        ])
        shadow_value = _mean([
            value for key, value in leg_prices.items()
            if key in shadow_leg_keys and value is not None
        ])

        chart_row = {
            **template,
            "timestamp": bucket_at,
            "timestamp_ms": int(bucket_epoch * 1000),
            "session_date": latest_session,
            "open": round(open_price, 4),
            "high": round(high_price, 4),
            "low": round(low_price, 4),
            "close": round(close_price, 4),
            "daily_change_pct": _safe_float(xb1_quote.get("daily_change_pct")),
            "previous_close": round(previous_close, 4),
            "fair_value_core": round(core_value, 4) if core_value is not None else None,
            "fair_value_shadow": round(shadow_value, 4) if shadow_value is not None else None,
            "live_overlay": True,
            "live_source_timestamp": xb1_quote.get("captured_at"),
            "live_overlay_generated_at": datetime.now(timezone.utc).isoformat(),
        }
        range_points = _safe_float(template.get("fair_value_range_points"))
        if range_points is not None and core_value is not None:
            chart_row["fair_value_core_upper"] = round(core_value + range_points, 4)
            chart_row["fair_value_core_lower"] = round(core_value - range_points, 4)

        for key, value in leg_prices.items():
            chart_row[f"leg_{key}"] = round(value, 4) if value is not None else None
            leg_move_decimal = leg_pct_moves.get(key)
            chart_row[f"leg_{key}_impact_decimal"] = round(leg_move_decimal, 8) if leg_move_decimal is not None else None
            chart_row[f"leg_{key}_impact_points"] = round(previous_close * leg_move_decimal, 4) if leg_move_decimal is not None else None
            chart_row[f"leg_{key}_pct"] = round(leg_move_decimal * 100.0, 6) if leg_move_decimal is not None else None
            chart_row[f"leg_{key}_assets"] = int(leg_counts.get(key) or 0)
            band_lower, band_upper = leg_band_prices.get(key, (None, None))
            band_lower_move, band_upper_move = leg_band_pct_moves.get(key, (None, None))
            pearson_low, pearson_high = leg_band_pearsons.get(key, (None, None))
            chart_row[f"leg_{key}_lower"] = round(band_lower, 4) if band_lower is not None else None
            chart_row[f"leg_{key}_upper"] = round(band_upper, 4) if band_upper is not None else None
            chart_row[f"leg_{key}_band_lower_pct"] = round(band_lower_move * 100.0, 6) if band_lower_move is not None else None
            chart_row[f"leg_{key}_band_upper_pct"] = round(band_upper_move * 100.0, 6) if band_upper_move is not None else None
            chart_row[f"leg_{key}_band_points"] = (
                round((band_upper - band_lower), 4)
                if band_lower is not None and band_upper is not None
                else None
            )
            chart_row[f"leg_{key}_pearson_min_mean"] = round(pearson_low, 6) if pearson_low is not None else None
            chart_row[f"leg_{key}_pearson_max_mean"] = round(pearson_high, 6) if pearson_high is not None else None

        return chart_row

    def build_latest_payload(
        self,
        *,
        config: dict[str, Any] | None = None,
        sessions: int = 3,
        bar_minutes: int = 5,
        session_start: str = "09:00",
        session_end: str = "18:30",
        rolling_window_points: int = 60,
        vol_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_sessions = max(int(sessions or 3), 1)
        resolved_bar_minutes = max(int(bar_minutes or 5), 1)
        session_start_minutes = _minutes_from_hhmm(session_start, 9 * 60)
        session_end_minutes = _minutes_from_hhmm(session_end, (18 * 60) + 30)
        config_payload = config if isinstance(config, dict) else {}
        has_custom_composition = bool(config_payload.get("legs"))

        base_payload = self._load_payload_snapshot()
        if base_payload is None:
            base_payload = self.build_payload(
                config=None,
                sessions=resolved_sessions,
                bar_minutes=resolved_bar_minutes,
                session_start=session_start,
                session_end=session_end,
                rolling_window_points=rolling_window_points,
                vol_context=vol_context,
            )

        working_payload = deepcopy(base_payload)
        legs = working_payload.get("legs") or []
        if has_custom_composition:
            legs = self._normalize_leg_config(config_payload)
            selected_symbols = self._selected_symbols_from_legs(legs)
            working_payload["legs"] = legs
            working_payload["asset_stats"] = self._asset_stats_for_hot_payload(
                symbols=selected_symbols,
                base_payload=base_payload,
                bar_minutes=resolved_bar_minutes,
                rolling_window_points=int(rolling_window_points or 60),
                session_start_minutes=session_start_minutes,
                session_end_minutes=session_end_minutes,
            )
        stats = {
            str(symbol): dict(payload)
            for symbol, payload in (working_payload.get("asset_stats") or {}).items()
            if isinstance(payload, dict)
        }
        latest = self._build_latest_row_fast(
            base_payload=working_payload,
            legs=legs,
            stats=stats,
            bar_minutes=resolved_bar_minutes,
        )
        if latest is None:
            live_payload = self.apply_live_overlay(
                working_payload,
                sessions=resolved_sessions,
                bar_minutes=resolved_bar_minutes,
                session_start=session_start,
                session_end=session_end,
            )
            latest = live_payload.get("latest") if isinstance(live_payload, dict) else None
        # Keep the hot endpoint latest-only. History repair/snapshot rebuilds are too heavy
        # for the 2.5s refresh loop and can block OCR writes in SQLite.
        return {
            "ok": bool(latest),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "benchmark_symbol": BENCHMARK_SYMBOL,
            "bar_minutes": resolved_bar_minutes,
            "latest": latest,
            "live_overlay": bool((latest or {}).get("live_overlay")) if isinstance(latest, dict) else False,
            "live_source_timestamp": (latest or {}).get("live_source_timestamp") if isinstance(latest, dict) else None,
            "source": "sqlite_hot_overlay",
        }

    def build_payload(
        self,
        *,
        config: dict[str, Any] | None = None,
        sessions: int = 3,
        bar_minutes: int = 5,
        session_start: str = "09:00",
        session_end: str = "18:30",
        rolling_window_points: int = 60,
        vol_context: dict[str, Any] | None = None,
        min_timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        resolved_sessions = max(int(sessions or 3), 1)
        resolved_bar_minutes = max(int(bar_minutes or 5), 1)
        session_start_minutes = _minutes_from_hhmm(session_start, 9 * 60)
        session_end_minutes = _minutes_from_hhmm(session_end, (18 * 60) + 30)
        legs = self._normalize_leg_config(config)
        needed_symbols = {BENCHMARK_SYMBOL}
        for leg in legs:
            needed_symbols.update(str(asset) for asset in leg.get("available_assets") or [] if str(asset).strip())
        for _, definitions in RPC_COMPONENT_VERSION_DEFINITIONS:
            for definition in definitions:
                needed_symbols.update(self._rpc_definition_symbols(definition))

        paths = self._candidate_row_files(resolved_sessions)
        signature = self._file_signature(paths)
        config_signature = tuple(
            (
                leg.get("key"),
                bool(leg.get("enabled", True)),
                tuple(leg.get("assets") or []),
            )
            for leg in legs
        )
        try:
            vol_signature = json.dumps(vol_context or {}, sort_keys=True, default=str)
        except Exception:
            vol_signature = str(vol_context or {})
        cache_key = (
            resolved_sessions,
            resolved_bar_minutes,
            session_start_minutes,
            session_end_minutes,
            int(rolling_window_points),
            config_signature,
            vol_signature,
            signature,
        )
        with self._cache_lock:
            cached = self._payload_cache.get(cache_key)
            if cached is not None:
                payload = deepcopy(cached)
                if (
                    min_timestamp_ms is None
                    or (self.payload_last_timestamp_ms(payload) or 0) >= int(min_timestamp_ms)
                ):
                    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
                    self._store_payload_snapshot(payload)
                    return payload

        base_cache_key = (
            signature,
            tuple(sorted(needed_symbols)),
            resolved_sessions,
            resolved_bar_minutes,
            session_start_minutes,
            session_end_minutes,
            int(rolling_window_points or 60),
        )
        with self._cache_lock:
            base_payload = self._base_cache.get(base_cache_key)
            if base_payload is not None and min_timestamp_ms is not None:
                candles = list(base_payload.get("candles") or [])
                last_candle_timestamp = _safe_float(
                    (candles[-1] if candles else {}).get("timestamp_ms")
                )
                if last_candle_timestamp is None or last_candle_timestamp < int(min_timestamp_ms):
                    base_payload = None

        if base_payload is None:
            acquired_build_lock = self._base_build_lock.acquire(timeout=8.0)
            if not acquired_build_lock:
                stale_payload = self._load_payload_snapshot()
                stale_covers_target = (
                    min_timestamp_ms is None
                    or (self.payload_last_timestamp_ms(stale_payload) or 0) >= int(min_timestamp_ms)
                )
                if (
                    stale_payload is not None
                    and stale_covers_target
                    and self.payload_covers_latest_available_session(
                        stale_payload,
                        sessions=resolved_sessions,
                    )
                ):
                    return stale_payload
                self._base_build_lock.acquire()
                acquired_build_lock = True
            try:
                with self._cache_lock:
                    base_payload = self._base_cache.get(base_cache_key)
                    if base_payload is not None and min_timestamp_ms is not None:
                        candles = list(base_payload.get("candles") or [])
                        last_candle_timestamp = _safe_float(
                            (candles[-1] if candles else {}).get("timestamp_ms")
                        )
                        if last_candle_timestamp is None or last_candle_timestamp < int(min_timestamp_ms):
                            base_payload = None
                if base_payload is None:
                    frame = self._read_rows_from_store(
                        paths=paths,
                        needed_symbols=needed_symbols,
                        session_start_minutes=session_start_minutes,
                        session_end_minutes=session_end_minutes,
                        bar_minutes=resolved_bar_minutes,
                    )
                    if frame is None or frame.empty:
                        frame = self._read_rows(
                            paths=paths,
                            needed_symbols=needed_symbols,
                            session_start_minutes=session_start_minutes,
                            session_end_minutes=session_end_minutes,
                        )
                    valid_sessions = self._latest_valid_sessions(frame, resolved_sessions)
                    if valid_sessions:
                        frame = frame[frame["session_date"].isin(valid_sessions)].copy()

                    candles, previous_closes = self._build_candles(frame, resolved_bar_minutes)
                    stats = self._pearson_stats(frame, needed_symbols, int(rolling_window_points or 60))
                    try:
                        self.history_store.replace_fair_value_asset_stats(
                            stats,
                            bar_minutes=resolved_bar_minutes,
                            rolling_window_points=int(rolling_window_points or 60),
                            session_start_minutes=session_start_minutes,
                            session_end_minutes=session_end_minutes,
                        )
                    except Exception:
                        logger.exception("Failed to persist fair-value asset stats")
                    change_grids = self._build_change_grid(frame, candles)
                    base_payload = {
                        "valid_sessions": valid_sessions,
                        "candles": candles,
                        "previous_closes": previous_closes,
                        "stats": stats,
                        "change_grids": change_grids,
                    }
                    with self._cache_lock:
                        self._base_cache[base_cache_key] = base_payload
                        while len(self._base_cache) > 4:
                            self._base_cache.pop(next(iter(self._base_cache)), None)
            finally:
                if acquired_build_lock:
                    self._base_build_lock.release()

        valid_sessions = list(base_payload.get("valid_sessions") or [])
        candles = list(base_payload.get("candles") or [])
        previous_closes = dict(base_payload.get("previous_closes") or {})
        stats = dict(base_payload.get("stats") or {})
        change_grids = dict(base_payload.get("change_grids") or {})

        chart_rows, rpc_metadata = self._build_chart_rows(
            candles=candles,
            previous_closes=previous_closes,
            change_grids=change_grids,
            legs=legs,
            stats=stats,
            vol_context=vol_context,
        )

        enriched_legs: list[dict[str, Any]] = []
        for leg in legs:
            enriched_assets = []
            selected_assets = set(str(asset) for asset in leg.get("assets") or [])
            for symbol in leg.get("available_assets") or leg.get("assets") or []:
                stat = stats.get(symbol) or {}
                enriched_assets.append({
                    "symbol": symbol,
                    "selected": symbol in selected_assets,
                    "stats": stat,
                })
            enriched_legs.append({
                **leg,
                "selected_assets": list(leg.get("assets") or []),
                "assets": enriched_assets,
            })

        latest = chart_rows[-1] if chart_rows else None
        payload = {
            "ok": bool(chart_rows),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "leg_definition_version": LEG_DEFINITION_VERSION,
            "benchmark_symbol": BENCHMARK_SYMBOL,
            "session_window": {
                "timezone": "America/Sao_Paulo",
                "start": session_start,
                "end": session_end,
            },
            "bar_minutes": resolved_bar_minutes,
            "requested_sessions": resolved_sessions,
            "sessions": [
                {
                    "date": session_date,
                    "previous_close": round(previous_closes.get(session_date), 4)
                    if previous_closes.get(session_date) is not None
                    else None,
                    "candle_count": sum(1 for item in candles if item.get("session_date") == session_date),
                }
                for session_date in valid_sessions
            ],
            "legs": enriched_legs,
            "asset_stats": stats,
            "risk_pressure_composite": rpc_metadata,
            "chart_rows": chart_rows,
            "latest": latest,
            "methodology": {
                "pearson": "Rolling Pearson on price deltas vs XB1 across the selected sessions.",
                "effective_beta": "Halfway between mean Pearson and the favorable extreme: max for positive mean beta, min for negative mean beta.",
                "leg_price": "Each asset uses its own intraday decimal return versus its own previous close; impact = return * effective beta once; projected points = previous XB1 close * impact.",
                "leg_bands": "Optional per-leg bands use only the selected assets' rolling Pearson min/max: each asset projects the current intraday return with its Pearson min and max, then the leg averages those lower/upper projections.",
                "core_fair_value": "Average of enabled core leg prices.",
                "shadow_fair_value": "Average of enabled shadow leg prices; used as quality/sentiment confirmation.",
                "range": "Blend of selected-asset oscillation, XB1 realized daily vol and optional implied/vol-of-vol context.",
                "edge_bias": "Online 15-minute XB1 edge forecast calibrated only on already-known bars: fair-value dislocation, Core/Shadow lead-lag, cross-leg consensus, price momentum and a noise floor with hysteresis.",
                "risk_pressure_composite": "Synthetic Brazil macro pressure asset. RPC v2 is active; RPC v1 is preserved for comparison. Positive RPC is supportive/risk-on; negative RPC is pressure/risk-off. RPC v2 uses desk-sign adjusted raw moves with fixed per-component scales so the component direction remains monotonic; RPC v1 keeps the rolling robust-z comparison model.",
                "sentiment_score": "Alias of rpc_pressure_score for chart compatibility.",
            },
        }

        with self._cache_lock:
            self._payload_cache[cache_key] = deepcopy(payload)
            while len(self._payload_cache) > 8:
                self._payload_cache.pop(next(iter(self._payload_cache)), None)
        self._store_payload_snapshot(payload)
        return payload
