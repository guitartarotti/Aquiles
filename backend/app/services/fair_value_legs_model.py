from __future__ import annotations

import io
import math
import os
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from ..config import Config
from ..utils.logger import get_logger
from .fair_value_legs_contracts import (
    BENCHMARK_SYMBOL,
    DEFAULT_LEG_DEFINITIONS,
    LOCAL_TZ,
    RPC_COMPONENT_DEFINITIONS_V1,
    RPC_COMPONENT_DEFINITIONS_V2,
    RPC_COMPONENT_VERSION_DEFINITIONS,
)
from .fair_value_legs_math import (
    _bias_label,
    _clamp,
    _mean,
    _median,
    _pearson_corr,
    _rpc_regime,
    _safe_float,
    _sentiment_regime,
    _sign,
)
from .market_screen_chart_service import _security_match_variants

logger = get_logger("aquiles.fair_value_legs.model")


class FairValueLegsModelMixin:
    def _normalize_leg_config(self, config: dict[str, Any] | None) -> list[dict[str, Any]]:
        raw_legs = (config or {}).get("legs") or {}
        symbol_cache: dict[str, str] = {}
        ewz_symbols = {"EWZ", "EWZ US"}
        migrate_ewz_to_local = False
        legs: list[dict[str, Any]] = []
        for definition in DEFAULT_LEG_DEFINITIONS:
            leg = deepcopy(definition)
            requested = raw_legs.get(leg["key"]) if isinstance(raw_legs, dict) else None
            default_assets = [
                self._normalize_symbol(asset, symbol_cache)
                for asset in leg.get("assets") or []
            ]
            default_assets = [asset for asset in dict.fromkeys(default_assets) if asset]
            assets = default_assets
            available_assets = list(default_assets)
            if isinstance(requested, dict) and isinstance(requested.get("assets"), list):
                resolved = [
                    self._normalize_symbol(asset, symbol_cache)
                    for asset in requested.get("assets") or []
                ]
                resolved = [asset for asset in dict.fromkeys(resolved) if asset]
                if leg.get("key") == "equity_foreign":
                    migrate_ewz_to_local = any(asset in ewz_symbols for asset in resolved)
                    resolved = [asset for asset in resolved if asset not in ewz_symbols]
                if leg.get("key") == "equity_local" and migrate_ewz_to_local and "EWZ US" not in resolved:
                    resolved = ["EWZ US", *resolved]
                assets = resolved
                available_assets = list(dict.fromkeys([*default_assets, *resolved]))
            leg["assets"] = assets
            leg["available_assets"] = available_assets
            leg["enabled"] = bool(requested.get("enabled")) if isinstance(requested, dict) and "enabled" in requested else True
            leg["visible"] = bool(requested.get("visible")) if isinstance(requested, dict) and "visible" in requested else bool(leg.get("default_visible", True))
            leg["band_visible"] = (
                bool(requested.get("band_visible"))
                if isinstance(requested, dict) and "band_visible" in requested
                else bool(leg.get("default_band_visible", False))
            )
            legs.append(leg)
        return legs

    def _candidate_row_files(self, sessions: int) -> list[str]:
        paths = self.chart_service._row_file_paths()
        candidates: list[str] = []
        for path in sorted(paths, reverse=True):
            session_date = self.chart_service._row_file_date(path)
            if session_date is None:
                continue
            if session_date.weekday() >= 5:
                continue
            candidates.append(path)
            if len(candidates) >= max(int(sessions) + 2, int(sessions)):
                break
        return sorted(candidates)

    def _file_signature(self, paths: list[str]) -> tuple[Any, ...]:
        signature: list[Any] = []
        for path in paths:
            try:
                stat = os.stat(path)
            except OSError:
                continue
            signature.append((path, int(stat.st_mtime_ns // (30 * 10**9)), int(stat.st_size)))
        return tuple(signature)

    def _store_symbol_query_set(self, symbols: set[str]) -> set[str]:
        query_symbols: set[str] = set()
        for symbol in symbols:
            raw = str(symbol or "").strip()
            if not raw:
                continue
            query_symbols.add(raw)
            query_symbols.update(_security_match_variants(raw))
        return {symbol for symbol in query_symbols if symbol}

    def _frame_from_store_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        needed_symbols: set[str],
        session_start_minutes: int,
        session_end_minutes: int,
    ) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame(
                columns=[
                    "capture_id",
                    "captured_at",
                    "local_dt",
                    "symbol",
                    "price",
                    "daily_change_pct",
                    "asset_previous_close",
                    "intraday_return_decimal",
                    "intraday_return_pct",
                    "session_date",
                    "bucket",
                ]
            )

        raw = pd.DataFrame(rows)
        if raw.empty:
            return raw
        raw["captured_at"] = pd.to_datetime(raw["captured_at"], utc=True, errors="coerce")
        raw = raw[raw["captured_at"].notna()].copy()
        if raw.empty:
            return raw

        local_dt = raw["captured_at"].dt.tz_convert(LOCAL_TZ)
        minutes = (local_dt.dt.hour * 60) + local_dt.dt.minute
        raw = raw[(minutes >= session_start_minutes) & (minutes <= session_end_minutes)].copy()
        if raw.empty:
            return raw

        local_dt = raw["captured_at"].dt.tz_convert(LOCAL_TZ)
        symbol_cache: dict[str, str] = {}
        normalized = pd.DataFrame(
            {
                "capture_id": raw["capture_id"].astype(str).str.strip(),
                "captured_at": raw["captured_at"],
                "local_dt": local_dt,
                "symbol": raw["symbol"].map(
                    lambda value: self._normalize_symbol(value, symbol_cache)
                ),
                "price": pd.to_numeric(raw["price"], errors="coerce"),
                "daily_change_pct": pd.to_numeric(raw["daily_change_pct"], errors="coerce"),
            }
        )
        normalized = normalized[
            normalized["symbol"].astype(str).str.strip().ne("")
            & normalized["price"].notna()
        ]
        if needed_symbols:
            normalized = normalized[normalized["symbol"].isin(needed_symbols)]
        if normalized.empty:
            return normalized

        normalized["session_date"] = normalized["local_dt"].dt.date.astype(str)
        normalized["bucket"] = normalized["captured_at"].dt.floor("5min")
        normalized = normalized.sort_values(["captured_at", "symbol", "capture_id"]).drop_duplicates(
            subset=["captured_at", "symbol"],
            keep="last",
        )
        return self._attach_intraday_returns(normalized.reset_index(drop=True))

    def _frame_from_store_candles(
        self,
        rows: list[dict[str, Any]],
        *,
        needed_symbols: set[str],
        session_start_minutes: int,
        session_end_minutes: int,
        bar_minutes: int,
    ) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()

        raw = pd.DataFrame(rows)
        raw["captured_at"] = pd.to_datetime(raw["bucket_at"], utc=True, errors="coerce")
        raw = raw[raw["captured_at"].notna()].copy()
        if raw.empty:
            return raw

        local_dt = raw["captured_at"].dt.tz_convert(LOCAL_TZ)
        minutes = (local_dt.dt.hour * 60) + local_dt.dt.minute
        raw = raw[(minutes >= session_start_minutes) & (minutes <= session_end_minutes)].copy()
        if raw.empty:
            return raw

        local_dt = raw["captured_at"].dt.tz_convert(LOCAL_TZ)
        symbol_cache: dict[str, str] = {}
        normalized = pd.DataFrame(
            {
                "capture_id": raw.apply(
                    lambda row: f"{row.get('bucket_at')}:{row.get('symbol')}",
                    axis=1,
                ),
                "captured_at": raw["captured_at"],
                "local_dt": local_dt,
                "symbol": raw["symbol"].map(
                    lambda value: self._normalize_symbol(value, symbol_cache)
                ),
                "open": pd.to_numeric(raw["open"], errors="coerce"),
                "high": pd.to_numeric(raw["high"], errors="coerce"),
                "low": pd.to_numeric(raw["low"], errors="coerce"),
                "close": pd.to_numeric(raw["close"], errors="coerce"),
                "price": pd.to_numeric(raw["close"], errors="coerce"),
                "daily_change_pct": pd.to_numeric(raw["daily_change_pct"], errors="coerce"),
            }
        )
        normalized = normalized[
            normalized["symbol"].astype(str).str.strip().ne("")
            & normalized["price"].notna()
        ]
        if needed_symbols:
            normalized = normalized[normalized["symbol"].isin(needed_symbols)]
        if normalized.empty:
            return normalized

        resolved_bar_minutes = max(int(bar_minutes or 5), 1)
        normalized["session_date"] = normalized["local_dt"].dt.date.astype(str)
        normalized["bucket"] = normalized["captured_at"].dt.floor(f"{resolved_bar_minutes}min")
        normalized = normalized.sort_values(["captured_at", "symbol", "capture_id"]).drop_duplicates(
            subset=["captured_at", "symbol"],
            keep="last",
        )
        return self._attach_intraday_returns(normalized.reset_index(drop=True))

    def _store_since_from_paths(self, paths: list[str]) -> datetime | None:
        dates = [
            self.chart_service._row_file_date(path)
            for path in paths
        ]
        valid_dates = [item for item in dates if item is not None]
        if not valid_dates:
            return None
        local_start = datetime.combine(min(valid_dates), datetime.min.time(), tzinfo=LOCAL_TZ)
        return local_start.astimezone(timezone.utc)

    @staticmethod
    def _store_frame_missing_leg_prefix_ranges(
        frame: pd.DataFrame | None,
        *,
        bar_minutes: int,
    ) -> list[tuple[str, datetime, datetime]]:
        if frame is None or frame.empty:
            return []
        required_columns = {"session_date", "symbol", "bucket"}
        if any(column not in frame.columns for column in required_columns):
            return []
        interval = pd.Timedelta(minutes=max(int(bar_minutes or 5), 1))
        ranges: list[tuple[str, datetime, datetime]] = []
        for _, group in frame.groupby("session_date", sort=False):
            xb1 = group[group["symbol"] == BENCHMARK_SYMBOL]
            other = group[group["symbol"] != BENCHMARK_SYMBOL]
            if xb1.empty:
                continue
            first_benchmark_bucket = pd.to_datetime(xb1["bucket"], utc=True, errors="coerce").min()
            if pd.isna(first_benchmark_bucket):
                continue
            if other.empty:
                last_benchmark_bucket = pd.to_datetime(xb1["bucket"], utc=True, errors="coerce").max()
                if pd.isna(last_benchmark_bucket):
                    continue
                ranges.append((
                    str(group["session_date"].iloc[0]),
                    first_benchmark_bucket.to_pydatetime(),
                    last_benchmark_bucket.to_pydatetime(),
                ))
                continue
            first_leg_bucket = pd.to_datetime(other["bucket"], utc=True, errors="coerce").min()
            if pd.isna(first_leg_bucket):
                continue
            if first_leg_bucket - first_benchmark_bucket > interval:
                ranges.append((
                    str(group["session_date"].iloc[0]),
                    first_benchmark_bucket.to_pydatetime(),
                    first_leg_bucket.to_pydatetime(),
                ))
        return ranges

    @classmethod
    def _store_frame_has_missing_leg_prefix(
        cls,
        frame: pd.DataFrame | None,
        *,
        bar_minutes: int,
    ) -> bool:
        return bool(cls._store_frame_missing_leg_prefix_ranges(frame, bar_minutes=bar_minutes))

    def _read_rows_from_store(
        self,
        *,
        paths: list[str],
        needed_symbols: set[str],
        session_start_minutes: int,
        session_end_minutes: int,
        bar_minutes: int = 5,
    ) -> pd.DataFrame | None:
        if not bool(getattr(Config, "MARKET_SCREEN_W32_HISTORY_DB_ENABLE", True)):
            return None
        try:
            query_symbols = self._store_symbol_query_set(needed_symbols)
            since = self._store_since_from_paths(paths)
            rows = self.history_store.query_symbols_candles(
                query_symbols,
                bar_minutes=bar_minutes,
                since=since,
            )
            if not rows:
                return None
            frame = self._frame_from_store_candles(
                rows,
                needed_symbols=needed_symbols,
                session_start_minutes=session_start_minutes,
                session_end_minutes=session_end_minutes,
                bar_minutes=bar_minutes,
            )
            missing_ranges = self._store_frame_missing_leg_prefix_ranges(
                frame,
                bar_minutes=bar_minutes,
            )
            if missing_ranges:
                logger.info("Fair-value SQLite coverage is missing early leg candles; backfilling CSV rows")
                affected_sessions = {session_date for session_date, _, _ in missing_ranges}
                affected_paths = [
                    path for path in paths
                    if (
                        self.chart_service._row_file_date(path) is not None
                        and self.chart_service._row_file_date(path).isoformat() in affected_sessions
                    )
                ]
                backfill_since = min(start for _, start, _ in missing_ranges)
                backfill_until = max(end for _, _, end in missing_ranges)
                self.history_store.sync_csv_files(
                    affected_paths or paths,
                    needed_symbols=query_symbols,
                    since=backfill_since,
                    until=backfill_until,
                    force_full=True,
                )
                self.history_store.ensure_candles_for_symbols(
                    query_symbols,
                    bar_minutes=bar_minutes,
                    since=backfill_since,
                )
                rows = self.history_store.query_symbols_candles(
                    query_symbols,
                    bar_minutes=bar_minutes,
                    since=since,
                )
                if not rows:
                    return frame
                frame = self._frame_from_store_candles(
                    rows,
                    needed_symbols=needed_symbols,
                    session_start_minutes=session_start_minutes,
                    session_end_minutes=session_end_minutes,
                    bar_minutes=bar_minutes,
                )
            return frame
        except Exception:
            logger.exception("Failed to read fair-value rows from SQLite")
            return None

    def _read_recent_rows_from_store(
        self,
        *,
        paths: list[str],
        needed_symbols: set[str],
        session_start_minutes: int,
        session_end_minutes: int,
        bar_minutes: int = 5,
    ) -> pd.DataFrame | None:
        if not bool(getattr(Config, "MARKET_SCREEN_W32_HISTORY_DB_ENABLE", True)):
            return None
        try:
            query_symbols = self._store_symbol_query_set(needed_symbols)
            since = self._store_since_from_paths(paths)
            rows = self.history_store.query_symbols_candles(
                query_symbols,
                bar_minutes=bar_minutes,
                since=since,
            )
            if not rows:
                return None
            return self._frame_from_store_candles(
                rows,
                needed_symbols=needed_symbols,
                session_start_minutes=session_start_minutes,
                session_end_minutes=session_end_minutes,
                bar_minutes=bar_minutes,
            )
        except Exception:
            logger.exception("Failed to read recent fair-value rows from SQLite")
            return None

    def _read_rows(
        self,
        *,
        paths: list[str],
        needed_symbols: set[str],
        session_start_minutes: int,
        session_end_minutes: int,
    ) -> pd.DataFrame:
        cache_key = (
            self._file_signature(paths),
            tuple(sorted(needed_symbols)),
            int(session_start_minutes),
            int(session_end_minutes),
        )
        with self._cache_lock:
            cached = self._frame_cache.get(cache_key)
            if cached is not None:
                return cached.copy()

        frames: list[pd.DataFrame] = []
        symbol_cache: dict[str, str] = {}
        usecols = [
            "capture_id",
            "captured_at",
            "symbol",
            "symbol_normalized",
            "price",
            "daily_change_pct",
        ]

        for path in paths:
            try:
                raw = pd.read_csv(path, usecols=usecols)
            except Exception:
                logger.exception("Failed to read W32 row file for fair-value legs: %s", path)
                continue
            if raw.empty:
                continue

            raw["captured_at"] = pd.to_datetime(raw["captured_at"], utc=True, errors="coerce")
            raw = raw[raw["captured_at"].notna()]
            if raw.empty:
                continue

            local_dt = raw["captured_at"].dt.tz_convert(LOCAL_TZ)
            minutes = (local_dt.dt.hour * 60) + local_dt.dt.minute
            raw = raw[(minutes >= session_start_minutes) & (minutes <= session_end_minutes)].copy()
            if raw.empty:
                continue

            symbol_normalized = raw.get("symbol_normalized")
            symbol_source = symbol_normalized.fillna("").astype(str).str.strip() if symbol_normalized is not None else ""
            if isinstance(symbol_source, str):
                symbol_source = raw["symbol"].fillna("").astype(str).str.strip()
            else:
                fallback_symbol = raw["symbol"].fillna("").astype(str).str.strip()
                symbol_source = symbol_source.where(symbol_source != "", fallback_symbol)
            unique_symbols = symbol_source.dropna().astype(str).str.strip().unique().tolist()
            normalized_symbol_map = {
                value: self._normalize_symbol(value, symbol_cache)
                for value in unique_symbols
                if value
            }

            normalized = pd.DataFrame(
                {
                    "capture_id": raw["capture_id"].astype(str).str.strip(),
                    "captured_at": raw["captured_at"],
                    "local_dt": local_dt.loc[raw.index],
                    "symbol": symbol_source.map(normalized_symbol_map),
                    "price": pd.to_numeric(raw["price"], errors="coerce"),
                    "daily_change_pct": pd.to_numeric(raw["daily_change_pct"], errors="coerce"),
                }
            )
            normalized = normalized[
                normalized["symbol"].astype(str).str.strip().ne("")
                & normalized["price"].notna()
            ]
            if needed_symbols:
                normalized = normalized[normalized["symbol"].isin(needed_symbols)]
            if normalized.empty:
                continue
            normalized["session_date"] = normalized["local_dt"].dt.date.astype(str)
            normalized["bucket"] = normalized["captured_at"].dt.floor("5min")
            frames.append(normalized)

        if not frames:
            return pd.DataFrame(
                columns=[
                    "capture_id",
                    "captured_at",
                    "local_dt",
                    "symbol",
                    "price",
                    "daily_change_pct",
                    "asset_previous_close",
                    "intraday_return_decimal",
                    "intraday_return_pct",
                    "session_date",
                    "bucket",
                ]
            )

        frame = pd.concat(frames, ignore_index=True)
        frame = frame.sort_values(["captured_at", "symbol", "capture_id"]).drop_duplicates(
            subset=["captured_at", "symbol"],
            keep="last",
        )
        normalized = self._attach_intraday_returns(frame.reset_index(drop=True))
        with self._cache_lock:
            self._frame_cache[cache_key] = normalized
            while len(self._frame_cache) > 4:
                self._frame_cache.pop(next(iter(self._frame_cache)), None)
        return normalized.copy()

    @staticmethod
    def _read_csv_head_tail(
        path: str,
        *,
        usecols: list[str],
        head_bytes: int,
        tail_bytes: int,
    ) -> pd.DataFrame:
        size = os.path.getsize(path)
        if size <= 0:
            return pd.DataFrame(columns=usecols)
        head_size = max(int(head_bytes or 0), 0)
        tail_size = max(int(tail_bytes or 0), 256_000)
        with open(path, "rb") as handle:
            header = handle.readline()
            header_size = handle.tell()
            if size <= header_size + head_size + tail_size:
                handle.seek(0)
                data = handle.read()
            else:
                head = b""
                if head_size > 0:
                    head = handle.read(head_size)
                    newline_index = head.rfind(b"\n")
                    if newline_index >= 0:
                        head = head[: newline_index + 1]
                    else:
                        head = b""
                handle.seek(max(size - tail_size, header_size))
                tail = handle.read()
                newline_index = tail.find(b"\n")
                if newline_index >= 0:
                    tail = tail[newline_index + 1 :]
                data = header + head + tail
        if not data.strip():
            return pd.DataFrame(columns=usecols)
        return pd.read_csv(io.StringIO(data.decode("utf-8", errors="replace")), usecols=usecols)

    def _read_recent_rows(
        self,
        *,
        paths: list[str],
        needed_symbols: set[str],
        session_start_minutes: int,
        session_end_minutes: int,
    ) -> pd.DataFrame:
        head_bytes = int(getattr(Config, "FAIR_VALUE_LEGS_LIVE_HEAD_BYTES", 0))
        tail_bytes = int(getattr(Config, "FAIR_VALUE_LEGS_LIVE_TAIL_BYTES", 8 * 1024 * 1024))
        cache_key = (
            "recent_tail",
            self._file_signature(paths),
            tuple(sorted(needed_symbols)),
            int(session_start_minutes),
            int(session_end_minutes),
            int(head_bytes),
            int(tail_bytes),
        )
        with self._cache_lock:
            cached = self._frame_cache.get(cache_key)
            if cached is not None:
                return cached.copy()

        frames: list[pd.DataFrame] = []
        symbol_cache: dict[str, str] = {}
        usecols = [
            "capture_id",
            "captured_at",
            "symbol",
            "symbol_normalized",
            "price",
            "daily_change_pct",
        ]

        for path in paths:
            try:
                raw = self._read_csv_head_tail(
                    path,
                    usecols=usecols,
                    head_bytes=head_bytes,
                    tail_bytes=tail_bytes,
                )
            except Exception:
                logger.exception("Failed to read recent W32 rows for fair-value live overlay: %s", path)
                continue
            if raw.empty:
                continue

            raw["captured_at"] = pd.to_datetime(raw["captured_at"], utc=True, errors="coerce")
            raw = raw[raw["captured_at"].notna()]
            if raw.empty:
                continue

            local_dt = raw["captured_at"].dt.tz_convert(LOCAL_TZ)
            minutes = (local_dt.dt.hour * 60) + local_dt.dt.minute
            raw = raw[(minutes >= session_start_minutes) & (minutes <= session_end_minutes)].copy()
            if raw.empty:
                continue

            symbol_normalized = raw.get("symbol_normalized")
            symbol_source = symbol_normalized.fillna("").astype(str).str.strip() if symbol_normalized is not None else ""
            if isinstance(symbol_source, str):
                symbol_source = raw["symbol"].fillna("").astype(str).str.strip()
            else:
                fallback_symbol = raw["symbol"].fillna("").astype(str).str.strip()
                symbol_source = symbol_source.where(symbol_source != "", fallback_symbol)
            unique_symbols = symbol_source.dropna().astype(str).str.strip().unique().tolist()
            normalized_symbol_map = {
                value: self._normalize_symbol(value, symbol_cache)
                for value in unique_symbols
                if value
            }

            normalized = pd.DataFrame(
                {
                    "capture_id": raw["capture_id"].astype(str).str.strip(),
                    "captured_at": raw["captured_at"],
                    "local_dt": local_dt.loc[raw.index],
                    "symbol": symbol_source.map(normalized_symbol_map),
                    "price": pd.to_numeric(raw["price"], errors="coerce"),
                    "daily_change_pct": pd.to_numeric(raw["daily_change_pct"], errors="coerce"),
                }
            )
            normalized = normalized[
                normalized["symbol"].astype(str).str.strip().ne("")
                & normalized["price"].notna()
            ]
            if needed_symbols:
                normalized = normalized[normalized["symbol"].isin(needed_symbols)]
            if normalized.empty:
                continue
            normalized["session_date"] = normalized["local_dt"].dt.date.astype(str)
            normalized["bucket"] = normalized["captured_at"].dt.floor("5min")
            frames.append(normalized)

        if not frames:
            return pd.DataFrame(
                columns=[
                    "capture_id",
                    "captured_at",
                    "local_dt",
                    "symbol",
                    "price",
                    "daily_change_pct",
                    "asset_previous_close",
                    "intraday_return_decimal",
                    "intraday_return_pct",
                    "session_date",
                    "bucket",
                ]
            )

        frame = pd.concat(frames, ignore_index=True)
        frame = frame.sort_values(["captured_at", "symbol", "capture_id"]).drop_duplicates(
            subset=["captured_at", "symbol"],
            keep="last",
        )
        normalized = self._attach_intraday_returns(frame.reset_index(drop=True))
        with self._cache_lock:
            self._frame_cache[cache_key] = normalized
            while len(self._frame_cache) > 6:
                self._frame_cache.pop(next(iter(self._frame_cache)), None)
        return normalized.copy()

    def _attach_intraday_returns(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        enriched = frame.copy()
        enriched["asset_previous_close"] = pd.NA
        enriched["intraday_return_decimal"] = pd.NA
        enriched["intraday_return_pct"] = pd.NA
        for (_, _), group in enriched.groupby(["session_date", "symbol"], sort=False):
            previous_close = self._previous_close_from_session(group)
            if previous_close is None or abs(previous_close) <= 1e-12:
                continue
            index = group.index
            prices = pd.to_numeric(enriched.loc[index, "price"], errors="coerce")
            returns = (prices - float(previous_close)) / float(previous_close)
            raw_change_pct = pd.to_numeric(enriched.loc[index, "daily_change_pct"], errors="coerce")
            return_pct = returns * 100.0
            sane_raw_change = raw_change_pct.notna() & raw_change_pct.abs().lt(50.0)
            mismatch_limit = raw_change_pct.abs().mul(0.75).add(0.25).clip(lower=1.50)
            inconsistent_price = sane_raw_change & (return_pct - raw_change_pct).abs().gt(mismatch_limit)
            returns = returns.mask(inconsistent_price)
            clean_pct = (returns * 100.0).dropna()
            if len(clean_pct) >= 8:
                group_median = float(clean_pct.median())
                group_mad = float((clean_pct - group_median).abs().median())
                group_limit = max(12.0 * 1.4826 * group_mad, 8.0)
                robust_outlier = ((returns * 100.0) - group_median).abs().gt(group_limit)
                hard_outlier = (returns * 100.0).abs().gt(25.0)
                returns = returns.mask(robust_outlier | hard_outlier)
            enriched.loc[index, "asset_previous_close"] = float(previous_close)
            enriched.loc[index, "intraday_return_decimal"] = returns
            enriched.loc[index, "intraday_return_pct"] = returns * 100.0
        enriched["asset_previous_close"] = pd.to_numeric(enriched["asset_previous_close"], errors="coerce")
        enriched["intraday_return_decimal"] = pd.to_numeric(enriched["intraday_return_decimal"], errors="coerce")
        enriched["intraday_return_pct"] = pd.to_numeric(enriched["intraday_return_pct"], errors="coerce")
        return enriched

    @staticmethod
    def _latest_valid_sessions(frame: pd.DataFrame, requested_sessions: int) -> list[str]:
        if frame.empty:
            return []
        xb1 = frame[frame["symbol"] == BENCHMARK_SYMBOL].copy()
        if xb1.empty:
            return []
        latest_session = str(max(xb1["session_date"].astype(str)))
        sessions: list[tuple[str, int, float]] = []
        for session_date, group in xb1.groupby("session_date", sort=True):
            captures = int(group["captured_at"].nunique())
            span_minutes = (
                group["captured_at"].max() - group["captured_at"].min()
            ).total_seconds() / 60.0
            is_full_session = captures >= 12 and span_minutes >= 30
            # During the first minutes of the current session we still want the
            # chart to include today's partial history. Otherwise the hot latest
            # endpoint appends a single live candle on top of yesterday's snapshot.
            is_latest_partial_session = str(session_date) == latest_session and captures >= 1
            if not is_full_session and not is_latest_partial_session:
                continue
            sessions.append((str(session_date), captures, span_minutes))
        return [item[0] for item in sessions[-max(int(requested_sessions), 1):]]

    @staticmethod
    def _previous_close_from_session(session_frame: pd.DataFrame) -> float | None:
        if session_frame.empty:
            return None
        prices = pd.to_numeric(session_frame["price"], errors="coerce")
        changes = pd.to_numeric(session_frame["daily_change_pct"], errors="coerce")
        denominators = 1.0 + (changes / 100.0)
        valid = prices.notna() & changes.notna() & denominators.abs().gt(1e-9)
        if valid.any():
            first_index = valid[valid].index[0]
            return float(prices.loc[first_index] / denominators.loc[first_index])
        first_valid_price = prices.dropna()
        if first_valid_price.empty:
            return None
        first_price = _safe_float(first_valid_price.iloc[0])
        return first_price

    def _build_candles(self, frame: pd.DataFrame, bar_minutes: int) -> tuple[list[dict[str, Any]], dict[str, float]]:
        candles: list[dict[str, Any]] = []
        previous_closes: dict[str, float] = {}
        xb1 = frame[frame["symbol"] == BENCHMARK_SYMBOL].copy()
        if xb1.empty:
            return candles, previous_closes

        freq = f"{max(int(bar_minutes), 1)}min"
        for session_date, group in xb1.groupby("session_date", sort=True):
            previous_close = self._previous_close_from_session(group)
            if previous_close is not None:
                previous_closes[str(session_date)] = float(previous_close)

            has_ohlc_columns = {"open", "high", "low", "close"}.issubset(set(group.columns))
            agg_spec = (
                {
                    "open": ("open", "first"),
                    "high": ("high", "max"),
                    "low": ("low", "min"),
                    "close": ("close", "last"),
                    "daily_change_pct": ("daily_change_pct", "last"),
                }
                if has_ohlc_columns
                else {
                    "open": ("price", "first"),
                    "high": ("price", "max"),
                    "low": ("price", "min"),
                    "close": ("price", "last"),
                    "daily_change_pct": ("daily_change_pct", "last"),
                }
            )
            grouped = (
                group.sort_values("captured_at")
                .assign(bucket=lambda item: item["captured_at"].dt.floor(freq))
                .groupby("bucket", as_index=False)
                .agg(**agg_spec)
            )
            for row in grouped.itertuples(index=False):
                bucket = row.bucket
                if not isinstance(bucket, pd.Timestamp):
                    continue
                candles.append(
                    {
                        "timestamp": bucket.isoformat(),
                        "timestamp_ms": int(bucket.timestamp() * 1000),
                        "session_date": str(session_date),
                        "open": _safe_float(row.open),
                        "high": _safe_float(row.high),
                        "low": _safe_float(row.low),
                        "close": _safe_float(row.close),
                        "volume": 0,
                        "turnover": 0,
                        "daily_change_pct": _safe_float(row.daily_change_pct),
                    }
                )

        candles.sort(key=lambda item: int(item.get("timestamp_ms") or 0))
        return candles, previous_closes

    def _pearson_stats(self, frame: pd.DataFrame, symbols: set[str], window_points: int) -> dict[str, dict[str, Any]]:
        stats: dict[str, dict[str, Any]] = {}
        if frame.empty:
            return stats

        price_pivot = frame.pivot_table(
            index="captured_at",
            columns="symbol",
            values="price",
            aggfunc="last",
        ).sort_index()
        if BENCHMARK_SYMBOL not in price_pivot.columns:
            return stats

        change_column = "intraday_return_pct" if "intraday_return_pct" in frame.columns else "daily_change_pct"
        change_ranges = (
            frame.groupby("symbol")[change_column]
            .agg(["count", "min", "max", "mean", "median", "std"])
            .to_dict("index")
        )
        latest_rows = (
            frame.sort_values("captured_at")
            .groupby("symbol", as_index=False)
            .tail(1)
            .set_index("symbol", drop=False)
        )

        benchmark_series = price_pivot[BENCHMARK_SYMBOL]
        resolved_window = max(int(window_points), 4)
        min_points = max(6, min(resolved_window, 12))

        for symbol in sorted(symbols):
            if symbol == BENCHMARK_SYMBOL or symbol not in price_pivot.columns:
                continue
            scoped = pd.concat([price_pivot[symbol], benchmark_series], axis=1).dropna()
            scoped.columns = ["asset", "benchmark"]
            delta = scoped.diff().dropna()
            corr_values: list[float] = []
            if not delta.empty:
                corr = delta["asset"].rolling(
                    resolved_window,
                    min_periods=min_points,
                ).corr(delta["benchmark"])
                corr_values = [
                    float(value)
                    for value in corr.dropna().tolist()
                    if _safe_float(value) is not None
                ]

            ranges = change_ranges.get(symbol) or {}
            latest = latest_rows.loc[symbol] if symbol in latest_rows.index else {}
            mean_pearson = _mean(corr_values)
            min_pearson = min(corr_values) if corr_values else None
            max_pearson = max(corr_values) if corr_values else None
            median_pearson = _median(corr_values)
            std_pearson = pd.Series(corr_values).std(ddof=0) if corr_values else None
            edge = max_pearson if (mean_pearson or 0.0) >= 0 else min_pearson
            if edge is None:
                edge = mean_pearson
            effective_beta = ((mean_pearson or 0.0) + (edge or 0.0)) / 2.0
            min_change = _safe_float(ranges.get("min"))
            max_change = _safe_float(ranges.get("max"))
            oscillation_pct = 0.0
            if min_change is not None:
                oscillation_pct = max(oscillation_pct, abs(min_change * effective_beta))
            if max_change is not None:
                oscillation_pct = max(oscillation_pct, abs(max_change * effective_beta))

            stats[symbol] = {
                "symbol": symbol,
                "samples": int(ranges.get("count") or 0),
                "pearson_samples": len(corr_values),
                "pearson_mean": round(mean_pearson, 6) if mean_pearson is not None else None,
                "pearson_min": round(min_pearson, 6) if min_pearson is not None else None,
                "pearson_max": round(max_pearson, 6) if max_pearson is not None else None,
                "pearson_median": round(median_pearson, 6) if median_pearson is not None else None,
                "pearson_std": round(float(std_pearson), 6) if std_pearson is not None and math.isfinite(float(std_pearson)) else None,
                "effective_beta": round(effective_beta, 6),
                "daily_change_min": round(min_change, 6) if min_change is not None else None,
                "daily_change_max": round(max_change, 6) if max_change is not None else None,
                "daily_change_mean": round(_safe_float(ranges.get("mean"), 0.0) or 0.0, 6),
                "daily_change_median": round(_safe_float(ranges.get("median"), 0.0) or 0.0, 6),
                "daily_change_std": round(_safe_float(ranges.get("std"), 0.0) or 0.0, 6),
                "oscillation_component_pct": round(oscillation_pct, 6),
                "latest_price": _safe_float(latest.get("price") if isinstance(latest, pd.Series) else None),
                "asset_previous_close": _safe_float(latest.get("asset_previous_close") if isinstance(latest, pd.Series) else None),
                "latest_intraday_return_pct": _safe_float(latest.get("intraday_return_pct") if isinstance(latest, pd.Series) else None),
                "latest_daily_change_pct": _safe_float(latest.get("daily_change_pct") if isinstance(latest, pd.Series) else None),
            }

        return stats

    @staticmethod
    def _implied_daily_vol_pct(vol_context: dict[str, Any] | None) -> float:
        context = vol_context or {}
        raw = (
            context.get("implied_vol")
            or context.get("atm_implied_vol")
            or context.get("iv")
            or context.get("iv_atm")
        )
        value = _safe_float(raw)
        if value is None or value <= 0:
            return 0.0
        annual_pct = value * 100.0 if value <= 2.0 else value
        return annual_pct / math.sqrt(252.0)

    @staticmethod
    def _realized_daily_vol_by_timestamp(candles: list[dict[str, Any]]) -> dict[int, float]:
        if not candles:
            return {}
        closes = pd.Series(
            [
                _safe_float(item.get("close"))
                for item in candles
            ],
            index=[int(item.get("timestamp_ms") or 0) for item in candles],
            dtype="float64",
        ).dropna()
        if closes.empty:
            return {}
        returns = closes.pct_change()
        bars_per_day = 114.0
        rolling = returns.rolling(36, min_periods=8).std(ddof=0) * math.sqrt(bars_per_day) * 100.0
        fallback = returns.std(ddof=0) * math.sqrt(bars_per_day) * 100.0
        result: dict[int, float] = {}
        last_value = _safe_float(fallback, 0.0) or 0.0
        for timestamp, value in rolling.items():
            parsed = _safe_float(value)
            if parsed is not None:
                last_value = parsed
            result[int(timestamp)] = float(last_value)
        return result

    @staticmethod
    def _edge_feature_vector(
        rows: list[dict[str, Any]],
        index: int,
        leg_keys: list[str],
    ) -> dict[str, Any] | None:
        row = rows[index]
        close_price = _safe_float(row.get("close"))
        core_value = _safe_float(row.get("fair_value_core"))
        if close_price is None or core_value is None:
            return None

        range_points = max(_safe_float(row.get("fair_value_range_points"), 0.0) or 0.0, 10.0)
        session_date = str(row.get("session_date") or "")
        shadow_value = _safe_float(row.get("fair_value_shadow"))
        gap_z = (core_value - close_price) / range_points
        shadow_z = ((shadow_value - close_price) / range_points) if shadow_value is not None else 0.0

        def lag_row(periods: int) -> dict[str, Any] | None:
            lag_index = index - periods
            if lag_index < 0:
                return None
            candidate = rows[lag_index]
            if str(candidate.get("session_date") or "") != session_date:
                return None
            return candidate

        previous_1 = lag_row(1)
        previous_3 = lag_row(3)

        def row_gap_z(candidate: dict[str, Any] | None) -> float:
            if not candidate:
                return gap_z
            candidate_close = _safe_float(candidate.get("close"))
            candidate_core = _safe_float(candidate.get("fair_value_core"))
            candidate_range = max(_safe_float(candidate.get("fair_value_range_points"), range_points) or range_points, 10.0)
            if candidate_close is None or candidate_core is None:
                return gap_z
            return (candidate_core - candidate_close) / candidate_range

        def momentum(candidate: dict[str, Any] | None, key: str, current_value: float | None) -> float:
            previous_value = _safe_float((candidate or {}).get(key))
            if candidate is None or current_value is None or previous_value is None:
                return 0.0
            return (current_value - previous_value) / range_points

        momentum(previous_1, "close", close_price)
        price_mom_3 = momentum(previous_3, "close", close_price)
        momentum(previous_1, "fair_value_core", core_value)
        core_mom_3 = momentum(previous_3, "fair_value_core", core_value)
        shadow_mom_3 = momentum(previous_3, "fair_value_shadow", shadow_value)
        spread_mom_3 = gap_z - row_gap_z(previous_3)
        lead_3 = core_mom_3 - price_mom_3
        shadow_lead_3 = shadow_mom_3 - price_mom_3

        leg_gap_values: list[float] = []
        weighted_sign_sum = 0.0
        total_weight = 0.0
        for key in leg_keys:
            leg_price = _safe_float(row.get(f"leg_{key}"))
            if leg_price is None:
                continue
            count = max(int(_safe_float(row.get(f"leg_{key}_assets"), 1.0) or 1), 1)
            weight = math.sqrt(count)
            leg_gap = (leg_price - close_price) / range_points
            leg_gap_values.append(leg_gap)
            weighted_sign_sum += _sign(leg_gap, 0.05) * weight
            total_weight += weight

        signed_consensus = weighted_sign_sum / total_weight if total_weight > 0 else 0.0
        agreement = abs(signed_consensus)
        leg_gap_mean = _mean(leg_gap_values) or 0.0
        leg_gap_dispersion = 0.0
        if len(leg_gap_values) > 1:
            leg_gap_dispersion = math.sqrt(
                sum((value - leg_gap_mean) ** 2 for value in leg_gap_values) / len(leg_gap_values)
            )
        core_shadow_spread = ((core_value - shadow_value) / range_points) if shadow_value is not None else 0.0

        features = [
            1.0,
            math.tanh(gap_z),
            math.tanh(shadow_z),
            math.tanh(spread_mom_3),
            math.tanh(lead_3),
            math.tanh(shadow_lead_3),
            math.tanh(-price_mom_3),
            signed_consensus,
            math.tanh(gap_z) * agreement,
            math.tanh(core_mom_3),
            math.tanh(gap_z * price_mom_3),
            math.tanh(core_shadow_spread),
        ]
        prior_forecast = (
            (0.26 * math.tanh(gap_z))
            + (0.22 * math.tanh(lead_3))
            + (0.14 * math.tanh(spread_mom_3))
            + (0.14 * signed_consensus)
            + (0.12 * math.tanh(shadow_z))
            + (0.08 * math.tanh(-price_mom_3))
            - (0.06 * math.tanh(leg_gap_dispersion))
        )
        quality = _clamp(
            0.25
            + (0.35 * agreement)
            + (0.25 * min(abs(gap_z) / 1.25, 1.0))
            + (0.15 * min(abs(lead_3) / 0.75, 1.0)),
            0.0,
            1.0,
        )
        return {
            "x": features,
            "scale": range_points,
            "close": close_price,
            "session_date": session_date,
            "gap_z": gap_z,
            "shadow_z": shadow_z,
            "spread_momentum": spread_mom_3,
            "lead_lag": lead_3,
            "shadow_lead_lag": shadow_lead_3,
            "price_momentum": price_mom_3,
            "core_momentum": core_mom_3,
            "signed_consensus": signed_consensus,
            "agreement": agreement,
            "leg_dispersion": leg_gap_dispersion,
            "core_shadow_spread": core_shadow_spread,
            "prior_forecast": prior_forecast,
            "quality": quality,
        }

    @staticmethod
    def _dot(left: list[float], right: list[float]) -> float:
        return sum(a * b for a, b in zip(left, right, strict=False))

    @classmethod
    def _rls_update(
        cls,
        beta: list[float],
        covariance: list[list[float]],
        x_values: list[float],
        target: float,
        forgetting: float = 0.985,
    ) -> tuple[list[float], list[list[float]], float]:
        size = len(beta)
        px = [
            sum(covariance[row][column] * x_values[column] for column in range(size))
            for row in range(size)
        ]
        denominator = max(forgetting + sum(x_values[i] * px[i] for i in range(size)), 1e-9)
        gain = [value / denominator for value in px]
        fitted = cls._dot(beta, x_values)
        error = target - fitted
        next_beta = [beta[i] + gain[i] * error for i in range(size)]
        xp = [
            sum(x_values[row] * covariance[row][column] for row in range(size))
            for column in range(size)
        ]
        next_covariance = [
            [
                _clamp((covariance[row][column] - gain[row] * xp[column]) / forgetting, -1e6, 1e6)
                for column in range(size)
            ]
            for row in range(size)
        ]
        return next_beta, next_covariance, error

    def _apply_edge_bias_model(self, rows: list[dict[str, Any]], leg_keys: list[str]) -> None:
        """Overlays a trade-oriented edge/bias forecast on the chart rows.

        The score is an online 15-minute forecast, not a market mood gauge. It only uses
        outcomes already known at each bar to recalibrate the adaptive lead-lag model.
        """
        if not rows:
            return

        features = [self._edge_feature_vector(rows, index, leg_keys) for index in range(len(rows))]
        feature_size = len((next((item for item in features if item), None) or {}).get("x") or [])
        if not feature_size:
            return

        beta = [0.0 for _ in range(feature_size)]
        covariance = [
            [35.0 if row == column else 0.0 for column in range(feature_size)]
            for row in range(feature_size)
        ]
        horizon_bars = 3
        trained_samples = 0
        residual_abs_ewm = 0.45
        direction_hit_ewm = 0.50
        forecast_history: list[float | None] = [None for _ in rows]
        active_bias = 0
        previous_session: str | None = None
        previous_score: float | None = None

        for index, row in enumerate(rows):
            feature = features[index]
            session_date = str(row.get("session_date") or "")
            if previous_session != session_date:
                active_bias = 0
                previous_score = None
                previous_session = session_date

            mature_index = index - horizon_bars
            if mature_index >= 0:
                mature_feature = features[mature_index]
                mature_row = rows[mature_index]
                if mature_feature and str(mature_row.get("session_date") or "") == session_date:
                    current_close = _safe_float(row.get("close"))
                    mature_close = _safe_float(mature_row.get("close"))
                    if current_close is not None and mature_close is not None:
                        target = _clamp(
                            (current_close - mature_close) / max(_safe_float(mature_feature.get("scale"), 10.0) or 10.0, 10.0),
                            -3.0,
                            3.0,
                        )
                        mature_forecast = forecast_history[mature_index]
                        if mature_forecast is not None and abs(mature_forecast) > 1e-6 and abs(target) > 1e-6:
                            direction_hit_ewm = (
                                (0.94 * direction_hit_ewm)
                                + (0.06 * (1.0 if mature_forecast * target > 0 else 0.0))
                            )
                        beta, covariance, error = self._rls_update(
                            beta,
                            covariance,
                            list(mature_feature.get("x") or []),
                            target,
                        )
                        trained_samples += 1
                        residual_abs_ewm = (0.94 * residual_abs_ewm) + (0.06 * abs(error))

            if not feature:
                continue

            model_forecast = self._dot(beta, list(feature.get("x") or []))
            sample_confidence = 1.0 - math.exp(-trained_samples / 38.0)
            residual_confidence = 1.0 / (1.0 + (1.65 * residual_abs_ewm))
            direction_confidence = _clamp((direction_hit_ewm - 0.49) / 0.16, 0.0, 1.0)
            confidence = _clamp(
                sample_confidence
                * residual_confidence
                * (0.45 + (0.55 * float(feature.get("quality") or 0.0)))
                * (0.35 + (0.65 * direction_confidence)),
                0.0,
                1.0,
            )
            prior_forecast = _safe_float(feature.get("prior_forecast"), 0.0) or 0.0
            expected_z = (
                ((0.18 + (0.42 * confidence)) * model_forecast)
                + ((0.82 - (0.42 * confidence)) * prior_forecast)
            )
            expected_z = _clamp(expected_z, -2.5, 2.5)
            forecast_history[index] = expected_z

            noise_floor_z = 0.05 + (0.08 * (1.0 - confidence))
            edge_excess = max(abs(expected_z) - noise_floor_z, 0.0)
            raw_score = _sign(expected_z) * math.tanh(edge_excess / 0.34) * 100.0
            score = raw_score * (0.62 + (0.38 * confidence))

            desired_bias = _sign(score, 34.0)
            bias_change = "hold"
            if active_bias == 0:
                if desired_bias:
                    active_bias = desired_bias
                    bias_change = "enter_long" if active_bias > 0 else "enter_short"
            elif active_bias > 0:
                if score <= -34.0:
                    active_bias = -1
                    bias_change = "flip_short"
                elif score < 9.0:
                    active_bias = 0
                    bias_change = "exit_long"
            else:
                if score >= 34.0:
                    active_bias = 1
                    bias_change = "flip_long"
                elif score > -9.0:
                    active_bias = 0
                    bias_change = "exit_short"

            score_change = score - previous_score if previous_score is not None else 0.0
            previous_score = score
            expected_move_points = expected_z * float(feature.get("scale") or 0.0)
            noise_floor_points = noise_floor_z * float(feature.get("scale") or 0.0)

            row["edge_score"] = round(score, 4)
            row["edge_bias_score"] = round(score, 4)
            row["edge_expected_move_points"] = round(expected_move_points, 4)
            row["edge_noise_floor_points"] = round(noise_floor_points, 4)
            row["edge_confidence"] = round(confidence, 4)
            row["edge_model_samples"] = int(trained_samples)
            row["edge_horizon_bars"] = horizon_bars
            row["bias_state"] = _bias_label(score, active_bias)
            row["bias_change"] = bias_change
            row["sentiment_score"] = round(score, 4)
            row["sentiment_score_change"] = round(score_change, 4)
            row["sentiment_regime"] = row["bias_state"]
            row["sentiment_components"] = {
                "model_forecast_z": round(model_forecast, 4),
                "prior_forecast_z": round(prior_forecast, 4),
                "expected_forecast_z": round(expected_z, 4),
                "expected_move_points": round(expected_move_points, 4),
                "noise_floor_points": round(noise_floor_points, 4),
                "confidence": round(confidence, 4),
                "direction_hit_ewm": round(direction_hit_ewm, 4),
                "trained_samples": int(trained_samples),
                "residual_abs_ewm": round(residual_abs_ewm, 4),
                "gap_z": round(float(feature.get("gap_z") or 0.0), 4),
                "shadow_z": round(float(feature.get("shadow_z") or 0.0), 4),
                "lead_lag": round(float(feature.get("lead_lag") or 0.0), 4),
                "spread_momentum": round(float(feature.get("spread_momentum") or 0.0), 4),
                "price_momentum": round(float(feature.get("price_momentum") or 0.0), 4),
                "leg_consensus": round(float(feature.get("signed_consensus") or 0.0), 4),
                "leg_agreement": round(float(feature.get("agreement") or 0.0), 4),
                "leg_dispersion": round(float(feature.get("leg_dispersion") or 0.0), 4),
            }

    @staticmethod
    def _rolling_robust_z(values: list[float | None], window: int = 36, min_points: int = 8) -> list[float | None]:
        scores: list[float | None] = []
        for index, value in enumerate(values):
            parsed = _safe_float(value)
            if parsed is None:
                scores.append(None)
                continue
            history = [
                _safe_float(item)
                for item in values[max(0, index - window + 1): index + 1]
            ]
            clean = [float(item) for item in history if item is not None]
            if len(clean) < min_points:
                scores.append(0.0)
                continue
            median = _median(clean) or 0.0
            deviations = [abs(item - median) for item in clean]
            mad = _median(deviations) or 0.0
            robust_sigma = max(1.4826 * mad, 1e-6)
            scores.append(_clamp((parsed - median) / robust_sigma, -5.0, 5.0))
        return scores

    @staticmethod
    def _signed_raw_normalized(values: list[float | None], scale: float | None) -> list[float | None]:
        resolved_scale = max(abs(_safe_float(scale, 0.01) or 0.01), 1e-6)
        scores: list[float | None] = []
        for value in values:
            parsed = _safe_float(value)
            if parsed is None:
                scores.append(None)
                continue
            scores.append(_clamp(parsed / resolved_scale, -5.0, 5.0))
        return scores

    def _rpc_component_scores(
        self,
        values: list[float | None],
        definition: dict[str, Any],
    ) -> list[float | None]:
        mode = str(definition.get("score_mode") or "rolling_robust_z")
        if mode == "signed_raw":
            return self._signed_raw_normalized(values, _safe_float(definition.get("score_scale")))
        return self._rolling_robust_z(values)

    @staticmethod
    def _rpc_symbol_variants(definition: dict[str, Any], symbol: str) -> list[str]:
        aliases = definition.get("symbol_aliases") if isinstance(definition.get("symbol_aliases"), dict) else {}
        values = [str(symbol)]
        for alias in aliases.get(str(symbol), []) or []:
            values.append(str(alias))
        return [item for item in dict.fromkeys(values) if item]

    @classmethod
    def _rpc_definition_symbols(cls, definition: dict[str, Any]) -> list[str]:
        symbols: list[str] = []
        for key in ("symbols", "short_symbols", "long_symbols"):
            for symbol in definition.get(key) or []:
                symbols.extend(cls._rpc_symbol_variants(definition, str(symbol)))
        return [item for item in dict.fromkeys(symbols) if item]

    @staticmethod
    def _component_raw_from_returns(
        row_changes: pd.Series | None,
        definition: dict[str, Any],
    ) -> tuple[float | None, int]:
        if row_changes is None or str(definition.get("kind") or "") == "unavailable":
            return None, 0

        def read_symbols(symbols: list[str]) -> list[float]:
            values: list[float] = []
            for symbol in symbols:
                for candidate in FairValueLegsModelMixin._rpc_symbol_variants(
                    definition, str(symbol)
                ):
                    if candidate not in row_changes.index:
                        continue
                    value = _safe_float(row_changes.get(candidate))
                    if value is not None:
                        values.append(value)
                        break
            return values

        kind = str(definition.get("kind") or "")
        if kind == "slope":
            short_values = read_symbols([str(symbol) for symbol in definition.get("short_symbols") or []])
            long_values = read_symbols([str(symbol) for symbol in definition.get("long_symbols") or []])
            if not short_values or not long_values:
                return None, len(short_values) + len(long_values)
            sign = _safe_float(definition.get("sign"), 1.0) or 1.0
            # The sign lives in the component definition so the desk convention stays explicit.
            return sign * ((_mean(long_values) or 0.0) - (_mean(short_values) or 0.0)), len(short_values) + len(long_values)

        values = read_symbols([str(symbol) for symbol in definition.get("symbols") or []])
        if not values:
            return None, 0
        sign = _safe_float(definition.get("sign"), 1.0) or 1.0
        scale = _safe_float(definition.get("scale"), 1.0) or 1.0
        return sign * scale * (_mean(values) or 0.0), len(values)

    def _apply_risk_pressure_composite(
        self,
        rows: list[dict[str, Any]],
        component_raw: dict[str, list[float | None]],
        component_counts: dict[str, list[int]],
        *,
        definitions: list[dict[str, Any]],
        version: str,
        field_prefix: str,
        write_primary: bool,
    ) -> dict[str, Any]:
        if not rows:
            return {"version": version, "components": [], "missing_components": []}

        active_definitions = [
            definition
            for definition in definitions
            if str(definition.get("kind") or "") != "unavailable"
        ]
        component_scores: dict[str, list[float | None]] = {
            str(definition.get("key")): self._rpc_component_scores(
                component_raw.get(str(definition.get("key"))) or [],
                definition,
            )
            for definition in active_definitions
        }

        xb1_returns: list[float] = []
        previous_close_by_session: dict[str, float] = {}
        for row in rows:
            session_date = str(row.get("session_date") or "")
            close_price = _safe_float(row.get("close"))
            previous_close = previous_close_by_session.get(session_date)
            if close_price is None or previous_close is None or abs(previous_close) <= 1e-12:
                xb1_returns.append(0.0)
            else:
                xb1_returns.append((close_price - previous_close) / previous_close)
            if close_price is not None:
                previous_close_by_session[session_date] = close_price

        pressure_target = [-value for value in xb1_returns]
        rpc_scores: list[float] = []
        rpc_slopes: list[float] = []
        rpc_index_values: list[float] = []
        component_payload: dict[str, dict[str, Any]] = {
            str(definition.get("key")): {
                "key": str(definition.get("key")),
                "label": str(definition.get("label") or definition.get("key")),
                "description": str(definition.get("description") or ""),
                "base_weight": _safe_float(definition.get("base_weight"), 0.0) or 0.0,
                "target_weight": _safe_float(definition.get("target_weight")),
                "score_mode": str(definition.get("score_mode") or "rolling_robust_z"),
                "score_scale": _safe_float(definition.get("score_scale")),
                "available": False,
                "latest_raw": None,
                "latest_z": None,
                "latest_score": None,
                "latest_weight": 0.0,
                "latest_ic": None,
                "samples": 0,
            }
            for definition in active_definitions
        }

        for index, row in enumerate(rows):
            raw_weights: dict[str, float] = {}
            signed_scores: dict[str, float] = {}
            component_ics: dict[str, float | None] = {}
            for definition in active_definitions:
                key = str(definition.get("key"))
                z_value = _safe_float((component_scores.get(key) or [None])[index])
                if z_value is None:
                    continue
                component_score = math.tanh(z_value / 2.25)
                history_scores = [
                    _safe_float(value)
                    for value in (component_scores.get(key) or [])[max(0, index - 35): index + 1]
                ]
                history_target = pressure_target[max(0, index - 35): index + 1]
                ic = _pearson_corr(
                    [float(value) for value in history_scores if value is not None],
                    history_target[-len([value for value in history_scores if value is not None]):],
                )
                component_ics[key] = ic
                ic_quality = max(ic or 0.0, 0.0)
                availability = max(int((component_counts.get(key) or [0])[index] or 0), 0)
                if availability <= 0:
                    continue
                base_weight = _safe_float(definition.get("base_weight"), 0.0) or 0.0
                target_weight = _safe_float(definition.get("target_weight"))
                raw_weights[key] = (
                    max(target_weight, 0.0)
                    if target_weight is not None
                    else base_weight * (0.35 + (0.65 * ic_quality))
                )
                signed_scores[key] = component_score

            total_weight = sum(raw_weights.values())
            weighted_pressure = 0.0
            if total_weight > 0:
                for key, weight in raw_weights.items():
                    normalized_weight = weight / total_weight
                    weighted_pressure += normalized_weight * signed_scores.get(key, 0.0)
                    payload = component_payload.get(key)
                    if payload is not None:
                        payload["available"] = True
                        payload["latest_weight"] = round(normalized_weight, 4)
                        payload["latest_ic"] = round(component_ics[key], 4) if component_ics.get(key) is not None else None

            rpc_score = _clamp(math.tanh(weighted_pressure * 1.65) * 100.0, -100.0, 100.0)
            previous_score = rpc_scores[-1] if rpc_scores else rpc_score
            slope = rpc_score - (rpc_scores[-3] if len(rpc_scores) >= 3 else previous_score)
            previous_slope = rpc_slopes[-1] if rpc_slopes else 0.0
            acceleration = slope - previous_slope
            momentum = rpc_score - (rpc_scores[-12] if len(rpc_scores) >= 12 else previous_score)
            rpc_index = 100.0 + rpc_score
            rpc_scores.append(rpc_score)
            rpc_slopes.append(slope)
            rpc_index_values.append(rpc_index)

            versioned_regime = _rpc_regime(rpc_score, slope, acceleration)
            row[f"{field_prefix}_pressure_score"] = round(rpc_score, 4)
            row[f"{field_prefix}_pressure_index"] = round(rpc_index, 4)
            row[f"{field_prefix}_slope"] = round(slope, 4)
            row[f"{field_prefix}_acceleration"] = round(acceleration, 4)
            row[f"{field_prefix}_momentum"] = round(momentum, 4)
            row[f"{field_prefix}_regime"] = versioned_regime
            row[f"{field_prefix}_score_change"] = round(rpc_score - previous_score, 4)
            row[f"{field_prefix}_components"] = {
                "rpc_pressure_score": round(rpc_score, 4),
                "rpc_pressure_index": round(rpc_index, 4),
                "slope": round(slope, 4),
                "acceleration": round(acceleration, 4),
                "momentum": round(momentum, 4),
                "weighted_pressure": round(weighted_pressure, 4),
            }
            if write_primary:
                row["rpc_pressure_score"] = round(rpc_score, 4)
                row["rpc_pressure_index"] = round(rpc_index, 4)
                row["rpc_slope"] = round(slope, 4)
                row["rpc_acceleration"] = round(acceleration, 4)
                row["rpc_momentum"] = round(momentum, 4)
                row["rpc_regime"] = versioned_regime
                row["sentiment_score"] = round(rpc_score, 4)
                row["sentiment_score_change"] = round(rpc_score - previous_score, 4)
                row["sentiment_regime"] = versioned_regime
                row["sentiment_components"] = deepcopy(row[f"{field_prefix}_components"])
            for definition in active_definitions:
                key = str(definition.get("key"))
                raw_value = _safe_float((component_raw.get(key) or [None])[index])
                z_value = _safe_float((component_scores.get(key) or [None])[index])
                score_value = math.tanh((z_value or 0.0) / 2.25) * 100.0 if z_value is not None else None
                row[f"{field_prefix}_{key}_raw"] = round(raw_value, 8) if raw_value is not None else None
                row[f"{field_prefix}_{key}_z"] = round(z_value, 4) if z_value is not None else None
                row[f"{field_prefix}_{key}_score"] = round(score_value, 4) if score_value is not None else None
                if write_primary:
                    row[f"rpc_{key}_raw"] = round(raw_value, 8) if raw_value is not None else None
                    row[f"rpc_{key}_z"] = round(z_value, 4) if z_value is not None else None
                    row[f"rpc_{key}_score"] = round(score_value, 4) if score_value is not None else None
                payload = component_payload.get(key)
                if payload is not None and raw_value is not None:
                    payload["latest_raw"] = round(raw_value, 8)
                    payload["latest_z"] = round(z_value, 4) if z_value is not None else None
                    payload["latest_score"] = round(score_value, 4) if score_value is not None else None
                    payload["samples"] = int(payload.get("samples") or 0) + 1

        missing_components = [
            {
                "key": str(definition.get("key")),
                "label": str(definition.get("label") or definition.get("key")),
                "description": str(definition.get("description") or ""),
                "reason": "not_available_in_w32_rows",
            }
            for definition in definitions
            if str(definition.get("kind") or "") == "unavailable"
        ]
        for payload in component_payload.values():
            if not payload.get("available"):
                missing_components.append({
                    "key": str(payload.get("key")),
                    "label": str(payload.get("label")),
                    "description": str(payload.get("description") or ""),
                    "reason": "no_valid_symbol_for_selected_sessions",
                })

        return {
            "version": version,
            "components": list(component_payload.values()),
            "missing_components": missing_components,
            "latest_score": rpc_scores[-1] if rpc_scores else None,
            "latest_index": rpc_index_values[-1] if rpc_index_values else None,
        }

    @staticmethod
    def _build_change_grid(frame: pd.DataFrame, candles: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
        if frame.empty or not candles:
            return {}
        working = frame.copy()
        fallback_pivot = None
        if "intraday_return_decimal" in working.columns:
            working["_daily_change_grid_value"] = pd.to_numeric(working["intraday_return_decimal"], errors="coerce")
            if "daily_change_pct" in working.columns:
                daily_change = pd.to_numeric(working["daily_change_pct"], errors="coerce") / 100.0
                working["_fallback_change_grid_value"] = daily_change.where(daily_change.abs().lt(0.50))
        elif "daily_change_pct" in working.columns:
            daily_change = pd.to_numeric(working["daily_change_pct"], errors="coerce") / 100.0
            working["_daily_change_grid_value"] = daily_change.where(daily_change.abs().lt(0.50))
        else:
            return {}

        pivot = working.pivot_table(
            index=["session_date", "bucket"],
            columns="symbol",
            values="_daily_change_grid_value",
            aggfunc="last",
        ).sort_index()
        if "_fallback_change_grid_value" in working.columns:
            fallback_pivot = working.pivot_table(
                index=["session_date", "bucket"],
                columns="symbol",
                values="_fallback_change_grid_value",
                aggfunc="last",
            ).sort_index()
            pivot = pivot.combine_first(fallback_pivot)
        grids: dict[str, pd.DataFrame] = {}
        candle_frame = pd.DataFrame(candles)
        for session_date, group in candle_frame.groupby("session_date", sort=True):
            buckets = pd.to_datetime(group["timestamp"], utc=True, errors="coerce")
            buckets = pd.DatetimeIndex([bucket for bucket in buckets if isinstance(bucket, pd.Timestamp)])
            if not len(buckets):
                continue
            try:
                scoped = pivot.xs(str(session_date), level="session_date")
            except KeyError:
                scoped = pd.DataFrame(index=buckets)
            combined_index = scoped.index.union(buckets).sort_values()
            scoped = scoped.reindex(combined_index).sort_index().ffill().bfill(limit=1)
            grids[str(session_date)] = scoped.reindex(buckets)
        return grids

    def _build_chart_rows(
        self,
        *,
        candles: list[dict[str, Any]],
        previous_closes: dict[str, float],
        change_grids: dict[str, pd.DataFrame],
        legs: list[dict[str, Any]],
        stats: dict[str, dict[str, Any]],
        vol_context: dict[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        realized_vol = self._realized_daily_vol_by_timestamp(candles)
        implied_daily_vol = self._implied_daily_vol_pct(vol_context)
        vol_of_vol_context = _safe_float((vol_context or {}).get("vol_of_vol_daily_pct"), 0.0) or 0.0
        vol_stress_assets = ["VIX", "VIX3M", "VXBR", "WVIX"]
        vol_stress = _mean([
            abs(_safe_float((stats.get(symbol) or {}).get("daily_change_std"), 0.0) or 0.0)
            for symbol in vol_stress_assets
        ]) or 0.0
        vol_multiplier = 1.0 + _clamp((vol_of_vol_context + vol_stress) / 30.0, 0.0, 0.45)

        rows: list[dict[str, Any]] = []
        rpc_component_raw: dict[str, dict[str, list[float | None]]] = {
            version: {
                str(definition.get("key")): []
                for definition in definitions
            }
            for version, definitions in RPC_COMPONENT_VERSION_DEFINITIONS
        }
        rpc_component_counts: dict[str, dict[str, list[int]]] = {
            version: {
                str(definition.get("key")): []
                for definition in definitions
            }
            for version, definitions in RPC_COMPONENT_VERSION_DEFINITIONS
        }
        core_leg_keys = {str(leg.get("key")) for leg in legs if leg.get("layer") == "core" and leg.get("enabled", True)}
        shadow_leg_keys = {str(leg.get("key")) for leg in legs if leg.get("layer") == "shadow" and leg.get("enabled", True)}
        sentiment_state: dict[str, Any] = {
            "session_date": None,
            "gap_fast": None,
            "gap_slow": None,
            "gap_surprise_abs": 0.22,
            "prev_gap_z": None,
            "prev_breadth": 0.0,
            "prev_core": None,
            "prev_shadow": None,
            "prev_close": None,
            "prev_score": None,
            "jump_cusum": 0.0,
        }

        for candle in candles:
            session_date = str(candle.get("session_date") or "")
            previous_close = previous_closes.get(session_date)
            close_price = _safe_float(candle.get("close"))
            timestamp_ms = int(candle.get("timestamp_ms") or 0)
            grid = change_grids.get(session_date)
            bucket = pd.to_datetime(candle.get("timestamp"), utc=True, errors="coerce")
            if previous_close is None or close_price is None or grid is None or not isinstance(bucket, pd.Timestamp):
                continue

            leg_prices: dict[str, float | None] = {}
            leg_pct_moves: dict[str, float | None] = {}
            leg_counts: dict[str, int] = {}
            leg_oscillation_components: dict[str, float] = {}
            leg_band_prices: dict[str, tuple[float | None, float | None]] = {}
            leg_band_pct_moves: dict[str, tuple[float | None, float | None]] = {}
            leg_band_pearsons: dict[str, tuple[float | None, float | None]] = {}
            row_changes = grid.loc[bucket] if bucket in grid.index else None
            rpc_values_by_version: dict[str, dict[str, float | None]] = {}
            rpc_counts_by_version: dict[str, dict[str, int]] = {}
            for version, definitions in RPC_COMPONENT_VERSION_DEFINITIONS:
                rpc_values: dict[str, float | None] = {}
                rpc_counts: dict[str, int] = {}
                for definition in definitions:
                    rpc_key = str(definition.get("key") or "")
                    raw_value, count = self._component_raw_from_returns(row_changes, definition)
                    rpc_values[rpc_key] = raw_value
                    rpc_counts[rpc_key] = count
                rpc_values_by_version[version] = rpc_values
                rpc_counts_by_version[version] = rpc_counts

            for leg in legs:
                key = str(leg.get("key") or "")
                if not key or not leg.get("enabled", True):
                    leg_prices[key] = None
                    leg_pct_moves[key] = None
                    leg_counts[key] = 0
                    leg_band_prices[key] = (None, None)
                    leg_band_pct_moves[key] = (None, None)
                    leg_band_pearsons[key] = (None, None)
                    continue
                contributions: list[float] = []
                oscillations: list[float] = []
                band_lower_contributions: list[float] = []
                band_upper_contributions: list[float] = []
                pearson_lows: list[float] = []
                pearson_highs: list[float] = []
                for symbol in leg.get("assets") or []:
                    stat = stats.get(symbol) or {}
                    beta = _safe_float(stat.get("effective_beta"))
                    if beta is None:
                        continue
                    if row_changes is None or symbol not in row_changes.index:
                        continue
                    change_decimal = _safe_float(row_changes.get(symbol))
                    if change_decimal is None:
                        continue
                    # Preserve economic direction: negative beta/Pearson inverts the asset move on XB1.
                    contributions.append(change_decimal * beta)
                    pearson_min = _safe_float(stat.get("pearson_min"))
                    pearson_max = _safe_float(stat.get("pearson_max"))
                    pearson_candidates = [
                        value for value in (pearson_min, pearson_max)
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
                    oscillation = _safe_float(stat.get("oscillation_component_pct"))
                    if oscillation is not None:
                        oscillations.append(abs(oscillation))
                leg_move = _mean(contributions)
                leg_pct_moves[key] = leg_move
                leg_counts[key] = len(contributions)
                leg_oscillation_components[key] = _mean(oscillations) or 0.0
                leg_prices[key] = (
                    previous_close * (1.0 + leg_move)
                    if leg_move is not None
                    else None
                )
                band_lower_move = _mean(band_lower_contributions)
                band_upper_move = _mean(band_upper_contributions)
                leg_band_pct_moves[key] = (band_lower_move, band_upper_move)
                leg_band_pearsons[key] = (_mean(pearson_lows), _mean(pearson_highs))
                lower_price = (
                    previous_close * (1.0 + band_lower_move)
                    if band_lower_move is not None
                    else None
                )
                upper_price = (
                    previous_close * (1.0 + band_upper_move)
                    if band_upper_move is not None
                    else None
                )
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

            core_oscillation_pct = _mean([
                leg_oscillation_components.get(key, 0.0)
                for key in core_leg_keys
                if leg_oscillation_components.get(key, 0.0) > 0
            ]) or 0.0
            realized_daily_vol = realized_vol.get(timestamp_ms, 0.0)
            range_pct = (
                (0.55 * core_oscillation_pct)
                + (0.30 * realized_daily_vol)
                + (0.15 * implied_daily_vol)
            ) * vol_multiplier
            range_pct = max(range_pct, 0.08)
            range_points = max(previous_close * range_pct / 100.0, 8.0)
            core_upper = (core_value + range_points) if core_value is not None else None
            core_lower = (core_value - range_points) if core_value is not None else None

            if sentiment_state.get("session_date") != session_date:
                sentiment_state = {
                    "session_date": session_date,
                    "gap_fast": None,
                    "gap_slow": None,
                    "gap_surprise_abs": 0.22,
                    "prev_gap_z": None,
                    "prev_breadth": 0.0,
                    "prev_core": None,
                    "prev_shadow": None,
                    "prev_close": None,
                    "prev_score": None,
                    "jump_cusum": 0.0,
                }

            leg_signal_values: list[tuple[float, float]] = []
            for key, price in leg_prices.items():
                if price is None:
                    continue
                weight = math.sqrt(max(int(leg_counts.get(key) or 0), 1))
                relative_gap = (price - close_price) / max(range_points, 1.0)
                leg_signal_values.append((math.tanh(relative_gap), weight))

            total_weight = sum(weight for _, weight in leg_signal_values)
            if total_weight > 0:
                breadth_signal = sum(value * weight for value, weight in leg_signal_values) / total_weight
                agreement_signal = abs(
                    sum(_sign(value, 0.05) * weight for value, weight in leg_signal_values)
                    / total_weight
                )
            else:
                breadth_signal = 0.0
                agreement_signal = 0.0
            prev_breadth = _safe_float(sentiment_state.get("prev_breadth"), 0.0) or 0.0
            breadth_impulse = breadth_signal - prev_breadth

            gap_z = 0.0
            shadow_gap_z = 0.0
            if core_value is not None:
                gap_z = (core_value - close_price) / max(range_points * 0.58, 10.0)
            if shadow_value is not None:
                shadow_gap_z = (shadow_value - close_price) / max(range_points * 0.72, 10.0)

            gap_fast = _safe_float(sentiment_state.get("gap_fast"))
            gap_slow = _safe_float(sentiment_state.get("gap_slow"))
            if gap_fast is None or gap_slow is None:
                gap_fast = gap_z
                gap_slow = gap_z
                gap_surprise = 0.0
            else:
                gap_fast += 0.38 * (gap_z - gap_fast)
                gap_slow += 0.07 * (gap_z - gap_slow)
                gap_surprise = gap_fast - gap_slow
            surprise_scale = max(
                (0.89 * (_safe_float(sentiment_state.get("gap_surprise_abs"), 0.22) or 0.22))
                + (0.11 * abs(gap_surprise)),
                0.12,
            )
            gap_surprise_z = gap_surprise / surprise_scale

            prev_core = _safe_float(sentiment_state.get("prev_core"))
            prev_shadow = _safe_float(sentiment_state.get("prev_shadow"))
            prev_close = _safe_float(sentiment_state.get("prev_close"))
            impulse_denominator = max(range_points * 0.26, 10.0)
            core_impulse = (
                (core_value - prev_core) / impulse_denominator
                if core_value is not None and prev_core is not None
                else 0.0
            )
            shadow_impulse = (
                (shadow_value - prev_shadow) / max(range_points * 0.32, 10.0)
                if shadow_value is not None and prev_shadow is not None
                else 0.0
            )
            price_impulse = (
                (close_price - prev_close) / impulse_denominator
                if prev_close is not None
                else 0.0
            )
            fair_value_impulse = (0.64 * core_impulse) + (0.36 * shadow_impulse)

            prev_gap_z = _safe_float(sentiment_state.get("prev_gap_z"), 0.0) or 0.0
            gap_delta = gap_z - prev_gap_z
            shock_input = (0.60 * gap_surprise_z) + (0.30 * fair_value_impulse) + (0.10 * gap_delta)
            jump_cusum = (0.72 * (_safe_float(sentiment_state.get("jump_cusum"), 0.0) or 0.0)) + shock_input

            fv_direction = _sign(fair_value_impulse, 0.04) or _sign(gap_surprise_z, 0.25) or _sign(gap_z, 0.20)
            price_follow = fv_direction * price_impulse if fv_direction else 0.0
            price_lag = fair_value_impulse - price_impulse
            core_shadow_divergence = (
                abs(core_value - shadow_value) / max(range_points, 1.0)
                if core_value is not None and shadow_value is not None
                else 0.0
            )

            level_component = math.tanh(gap_z * 0.82) * 18.0
            shadow_component = math.tanh(shadow_gap_z * 0.82) * 13.0
            surprise_component = math.tanh(gap_surprise_z * 1.05) * 28.0
            impulse_component = math.tanh(fair_value_impulse * 1.35) * 24.0
            breadth_score = breadth_signal * (14.0 + (8.0 * agreement_signal))
            breadth_shock_component = math.tanh(breadth_impulse / 0.18) * 9.0
            confirmation_component = (
                float(fv_direction) * math.tanh(max(price_follow, 0.0) * 1.05) * 8.0
                if fv_direction
                else 0.0
            )
            lag_component = math.tanh(price_lag * 0.95) * 8.0
            jump_component = math.tanh(jump_cusum * 0.72) * 10.0

            consensus_gate = 0.72 + (0.28 * agreement_signal)
            if core_value is not None and shadow_value is not None:
                core_side = _sign(core_value - close_price, range_points * 0.08)
                shadow_side = _sign(shadow_value - close_price, range_points * 0.08)
                if core_side and shadow_side and core_side != shadow_side:
                    consensus_gate *= max(0.58, 1.0 - min(core_shadow_divergence * 0.18, 0.34))

            raw_sentiment_score = (
                level_component
                + shadow_component
                + surprise_component
                + impulse_component
                + breadth_score
                + breadth_shock_component
                + confirmation_component
                + lag_component
                + jump_component
            ) * consensus_gate
            sentiment_score = _clamp(raw_sentiment_score, -100.0, 100.0)
            previous_score = _safe_float(sentiment_state.get("prev_score"))
            sentiment_score_change = sentiment_score - previous_score if previous_score is not None else 0.0

            sentiment_state.update({
                "gap_fast": gap_fast,
                "gap_slow": gap_slow,
                "gap_surprise_abs": surprise_scale,
                "prev_gap_z": gap_z,
                "prev_breadth": breadth_signal,
                "prev_core": core_value,
                "prev_shadow": shadow_value,
                "prev_close": close_price,
                "prev_score": sentiment_score,
                "jump_cusum": jump_cusum,
            })

            chart_row = {
                **candle,
                "previous_close": round(previous_close, 4),
                "fair_value_core": round(core_value, 4) if core_value is not None else None,
                "fair_value_shadow": round(shadow_value, 4) if shadow_value is not None else None,
                "fair_value_core_upper": round(core_upper, 4) if core_upper is not None else None,
                "fair_value_core_lower": round(core_lower, 4) if core_lower is not None else None,
                "fair_value_range_points": round(range_points, 4),
                "fair_value_range_pct": round(range_pct, 6),
                "sentiment_score": round(sentiment_score, 4),
                "sentiment_score_change": round(sentiment_score_change, 4),
                "sentiment_regime": _sentiment_regime(sentiment_score),
                "sentiment_components": {
                    "level": round(level_component, 4),
                    "shadow": round(shadow_component, 4),
                    "surprise": round(surprise_component, 4),
                    "impulse": round(impulse_component, 4),
                    "breadth": round(breadth_score, 4),
                    "breadth_shock": round(breadth_shock_component, 4),
                    "price_confirmation": round(confirmation_component, 4),
                    "price_lag": round(lag_component, 4),
                    "jump": round(jump_component, 4),
                    "consensus_gate": round(consensus_gate, 4),
                    "gap_z": round(gap_z, 4),
                    "surprise_z": round(gap_surprise_z, 4),
                    "fair_value_impulse": round(fair_value_impulse, 4),
                    "breadth_signal": round(breadth_signal, 4),
                    "agreement_signal": round(agreement_signal, 4),
                    "core_shadow_divergence": round(core_shadow_divergence, 4),
                },
            }
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
            rows.append(chart_row)
            for version, definitions in RPC_COMPONENT_VERSION_DEFINITIONS:
                rpc_values = rpc_values_by_version.get(version) or {}
                rpc_counts = rpc_counts_by_version.get(version) or {}
                for definition in definitions:
                    rpc_key = str(definition.get("key") or "")
                    rpc_component_raw.setdefault(version, {}).setdefault(rpc_key, []).append(rpc_values.get(rpc_key))
                    rpc_component_counts.setdefault(version, {}).setdefault(rpc_key, []).append(int(rpc_counts.get(rpc_key) or 0))

        self._apply_edge_bias_model(
            rows,
            [str(leg.get("key") or "") for leg in legs if str(leg.get("key") or "")],
        )
        rpc_v1_metadata = self._apply_risk_pressure_composite(
            rows,
            rpc_component_raw.get("v1") or {},
            rpc_component_counts.get("v1") or {},
            definitions=RPC_COMPONENT_DEFINITIONS_V1,
            version="v1",
            field_prefix="rpc_v1",
            write_primary=False,
        )
        rpc_v2_metadata = self._apply_risk_pressure_composite(
            rows,
            rpc_component_raw.get("v2") or {},
            rpc_component_counts.get("v2") or {},
            definitions=RPC_COMPONENT_DEFINITIONS_V2,
            version="v2",
            field_prefix="rpc_v2",
            write_primary=True,
        )
        rpc_metadata = {
            **rpc_v2_metadata,
            "active_version": "v2",
            "comparison_versions": {
                "v1": rpc_v1_metadata,
                "v2": rpc_v2_metadata,
            },
        }
        return rows, rpc_metadata
