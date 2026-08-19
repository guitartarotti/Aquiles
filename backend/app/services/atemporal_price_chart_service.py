from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..utils.logger import get_logger
from .market_screen_chart_service import MarketScreenChartService

logger = get_logger("aquiles.atemporal_price_chart")
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
DEFAULT_SYMBOL = "XB1"
XB1_CACHE_SYMBOL = "XB1"
CACHE_SPAN_TOLERANCE_SECONDS = 72 * 60 * 60


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


class AtemporalPriceChartService:
    """Build price-movement candles for atemporal Discovery charts."""

    def __init__(self, chart_service: MarketScreenChartService | None = None) -> None:
        self.chart_service = chart_service or MarketScreenChartService()

    @staticmethod
    def _is_session_time(timestamp: pd.Timestamp) -> bool:
        local_ts = timestamp.to_pydatetime().astimezone(LOCAL_TZ)
        minutes = local_ts.hour * 60 + local_ts.minute
        return (9 * 60) <= minutes <= (18 * 60 + 30)

    @staticmethod
    def _session_date(timestamp: pd.Timestamp) -> str:
        return timestamp.to_pydatetime().astimezone(LOCAL_TZ).date().isoformat()

    @staticmethod
    def _normalize_implied_vol(value: Any) -> float | None:
        parsed = _safe_float(value)
        if parsed is None or parsed <= 0:
            return None
        if parsed > 3.0:
            parsed = parsed / 100.0
        return max(min(parsed, 3.0), 0.0001)

    @staticmethod
    def _append_indicator_bands(
        rows: list[dict[str, Any]],
        *,
        moving_average_points: int,
        implied_vol: float | None,
    ) -> None:
        window = max(int(moving_average_points or 271), 2)
        closes: list[float] = []
        daily_iv = (implied_vol / math.sqrt(252.0)) if implied_vol else None
        for row in rows:
            close = _safe_float(row.get("close"))
            if close is None:
                row["ma_271"] = None
                row["iv_band_upper"] = None
                row["iv_band_lower"] = None
                continue
            closes.append(close)
            scoped = closes[-window:]
            if len(scoped) < window:
                row["ma_271"] = None
                row["iv_band_upper"] = None
                row["iv_band_lower"] = None
                continue
            ma_value = sum(scoped) / len(scoped)
            width = ma_value * daily_iv if daily_iv else None
            row["ma_271"] = round(ma_value, 4)
            row["iv_band_upper"] = round(ma_value + width, 4) if width is not None else None
            row["iv_band_lower"] = round(ma_value - width, 4) if width is not None else None

    @staticmethod
    def _latest_capture_from_frame(frame: pd.DataFrame) -> datetime | None:
        if frame.empty or "captured_at" not in frame.columns or not frame["captured_at"].notna().any():
            return None
        latest_value = frame["captured_at"].max()
        if hasattr(latest_value, "to_pydatetime"):
            return latest_value.to_pydatetime()
        return latest_value

    @staticmethod
    def _parse_capture_datetime(value: Any) -> datetime | None:
        try:
            parsed = pd.to_datetime(value, utc=True, errors="coerce")
        except Exception:
            return None
        if pd.isna(parsed):
            return None
        if hasattr(parsed, "to_pydatetime"):
            return parsed.to_pydatetime()
        return parsed

    @staticmethod
    def _local_day_start_for_epoch(epoch_seconds: float) -> datetime:
        local_ts = datetime.fromtimestamp(float(epoch_seconds), tz=timezone.utc).astimezone(LOCAL_TZ)
        local_start = datetime(local_ts.year, local_ts.month, local_ts.day, tzinfo=LOCAL_TZ)
        return local_start.astimezone(timezone.utc)

    @staticmethod
    def _cache_supported(symbol: str, include_partial: bool) -> bool:
        return bool(include_partial) and str(symbol or "").strip().upper() == XB1_CACHE_SYMBOL

    def _prepare_history_frame(
        self,
        frame: pd.DataFrame,
        *,
        target_points: float,
        apply_outlier_guard: bool,
    ) -> pd.DataFrame:
        if frame.empty:
            return frame

        prepared = frame.copy()
        if "capture_id" not in prepared.columns:
            prepared["capture_id"] = ""
        prepared["capture_id"] = prepared["capture_id"].fillna("").astype(str)
        prepared["captured_at"] = pd.to_datetime(prepared["captured_at"], utc=True, errors="coerce")
        prepared["price"] = pd.to_numeric(prepared["price"], errors="coerce")
        prepared = prepared[prepared["captured_at"].notna() & prepared["price"].notna()]
        prepared = prepared[prepared["captured_at"].map(self._is_session_time)]
        if prepared.empty:
            return prepared

        prepared["session_date"] = prepared["captured_at"].map(self._session_date)
        if apply_outlier_guard:
            prepared = self._drop_xb1_price_outliers(prepared, target_points=target_points)
        return prepared

    def _drop_xb1_price_outliers(
        self,
        frame: pd.DataFrame,
        *,
        target_points: float,
    ) -> pd.DataFrame:
        if frame.empty:
            return frame

        groups: list[pd.DataFrame] = []
        rejected = 0
        floor_points = max(float(target_points or 50.0) * 20.0, 2000.0)

        for _, group in frame.groupby("session_date", sort=True):
            ordered = group.sort_values(["captured_at", "capture_id"]).copy()
            deltas = ordered["price"].diff().abs()
            finite_deltas = deltas[deltas.notna() & (deltas > 0)]
            median_delta = float(finite_deltas.median()) if not finite_deltas.empty else 0.0
            jump_limit = max(floor_points, median_delta * 40.0)

            keep_mask: list[bool] = []
            previous_valid: float | None = None
            for item in ordered.itertuples(index=False):
                price = _safe_float(getattr(item, "price", None))
                if price is None:
                    keep_mask.append(False)
                    continue
                if previous_valid is None:
                    keep_mask.append(True)
                    previous_valid = price
                    continue
                if abs(price - previous_valid) > jump_limit:
                    keep_mask.append(False)
                    rejected += 1
                    continue
                keep_mask.append(True)
                previous_valid = price

            groups.append(ordered.loc[keep_mask])

        if rejected:
            logger.warning("Filtered %s XB1 atemporal OCR outlier row(s)", rejected)
        if not groups:
            return frame.iloc[0:0]
        return pd.concat(groups, ignore_index=True)

    def _build_rows_from_frame(
        self,
        frame: pd.DataFrame,
        *,
        tick_size_points: float,
        ticks_per_candle: int,
        include_partial: bool,
        apply_outlier_guard: bool,
    ) -> tuple[list[dict[str, Any]], datetime | None]:
        target_points = max(float(tick_size_points), 0.01) * max(int(ticks_per_candle), 1)
        prepared = self._prepare_history_frame(
            frame,
            target_points=target_points,
            apply_outlier_guard=apply_outlier_guard,
        )
        if prepared.empty:
            return [], None

        latest_capture_at = self._latest_capture_from_frame(prepared)
        rows = self._build_movement_rows(
            prepared,
            tick_size_points=tick_size_points,
            ticks_per_candle=ticks_per_candle,
            include_partial=include_partial,
        )
        source_epoch = _safe_float(
            latest_capture_at.timestamp() if latest_capture_at is not None else None
        )
        if source_epoch is not None:
            for row in rows:
                row["source_last_capture_at_epoch"] = source_epoch
        return rows, latest_capture_at

    def _build_or_load_xb1_cached_rows(
        self,
        *,
        resolved_symbol: str,
        since: datetime,
        tick_size_points: float,
        ticks_per_candle: int,
        max_points: int,
        include_partial: bool,
        force_refresh: bool = False,
    ) -> tuple[list[dict[str, Any]], datetime | None, str]:
        store = self.chart_service.history_store
        latest_records = store.query_latest_symbols({resolved_symbol})
        latest_record = latest_records[0] if latest_records else {}
        latest_raw_epoch = _safe_float(latest_record.get("captured_at_epoch"))
        latest_capture_at = self._parse_capture_datetime(latest_record.get("captured_at"))

        summary_all = store.query_atemporal_cache_summary(
            resolved_symbol,
            tick_size_points=tick_size_points,
            ticks_per_candle=ticks_per_candle,
        )
        summary_since = store.query_atemporal_cache_summary(
            resolved_symbol,
            tick_size_points=tick_size_points,
            ticks_per_candle=ticks_per_candle,
            since=since,
        )
        since_epoch = since.timestamp()
        min_cached_epoch = _safe_float(summary_since.get("min_end_capture_at_epoch"))
        max_source_epoch = _safe_float(summary_all.get("max_source_last_capture_at_epoch"))
        has_requested_span = int(summary_since.get("count") or 0) > 0 and (
            min_cached_epoch is not None
            and min_cached_epoch <= since_epoch + CACHE_SPAN_TOLERANCE_SECONDS
        )
        cache_is_current = (
            has_requested_span
            and latest_raw_epoch is not None
            and max_source_epoch is not None
            and max_source_epoch >= latest_raw_epoch - 0.5
        )

        if cache_is_current and not force_refresh:
            rows = store.query_atemporal_candles(
                resolved_symbol,
                tick_size_points=tick_size_points,
                ticks_per_candle=ticks_per_candle,
                since=since,
                limit=max_points,
            )
            return rows, latest_capture_at, "sqlite_incremental_xb1"

        raw_since = since
        if (
            not force_refresh
            and int(summary_all.get("count") or 0) > 0
            and has_requested_span
            and latest_raw_epoch is not None
        ):
            raw_since = self._local_day_start_for_epoch(latest_raw_epoch)

        records = store.query_symbols_history({resolved_symbol}, since=raw_since)
        frame = pd.DataFrame.from_records(records)
        rows_to_store, built_latest_capture_at = self._build_rows_from_frame(
            frame,
            tick_size_points=tick_size_points,
            ticks_per_candle=ticks_per_candle,
            include_partial=include_partial,
            apply_outlier_guard=True,
        )
        if built_latest_capture_at is not None:
            latest_capture_at = built_latest_capture_at

        if rows_to_store:
            prepared = self._prepare_history_frame(
                frame,
                target_points=max(float(tick_size_points), 0.01) * max(int(ticks_per_candle), 1),
                apply_outlier_guard=True,
            )
            sessions = sorted(str(value) for value in prepared["session_date"].dropna().unique())
            store.replace_atemporal_candles_for_sessions(
                resolved_symbol,
                tick_size_points=tick_size_points,
                ticks_per_candle=ticks_per_candle,
                session_dates=sessions,
                rows=rows_to_store,
            )

        rows = store.query_atemporal_candles(
            resolved_symbol,
            tick_size_points=tick_size_points,
            ticks_per_candle=ticks_per_candle,
            since=since,
            limit=max_points,
        )
        return rows, latest_capture_at, "sqlite_incremental_xb1"

    def _build_movement_rows(
        self,
        frame: pd.DataFrame,
        *,
        tick_size_points: float,
        ticks_per_candle: int,
        include_partial: bool,
    ) -> list[dict[str, Any]]:
        bar_size = max(float(tick_size_points), 0.01) * max(int(ticks_per_candle), 1)
        rows: list[dict[str, Any]] = []

        for session_date, group in frame.groupby("session_date", sort=True):
            ordered = group.sort_values(["captured_at", "capture_id"]).reset_index(drop=True)
            if ordered.empty:
                continue

            open_price: float | None = None
            high_price: float | None = None
            low_price: float | None = None
            start_ts: pd.Timestamp | None = None
            last_ts: pd.Timestamp | None = None
            sample_count = 0

            def emit(close_price: float, end_ts: pd.Timestamp, complete: bool) -> None:
                nonlocal open_price, high_price, low_price, start_ts, sample_count
                if open_price is None or start_ts is None:
                    return
                direction = 1 if close_price >= open_price else -1
                if direction >= 0:
                    low = open_price
                    high = max(open_price, close_price, high_price if high_price is not None else close_price)
                else:
                    high = open_price
                    low = min(open_price, close_price, low_price if low_price is not None else close_price)
                rows.append({
                    "timestamp": end_ts.isoformat(),
                    "timestamp_ms": int(end_ts.timestamp() * 1000),
                    "start_timestamp": start_ts.isoformat(),
                    "session_date": str(session_date),
                    "bar_index": len(rows) + 1,
                    "open": round(open_price, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "close": round(close_price, 4),
                    "price": round(close_price, 4),
                    "direction": "up" if direction >= 0 else "down",
                    "complete": bool(complete),
                    "movement_points": round(close_price - open_price, 4),
                    "target_points": round(bar_size, 4),
                    "sample_count": int(sample_count),
                })

            for item in ordered.itertuples(index=False):
                ts = getattr(item, "captured_at", None)
                price = _safe_float(getattr(item, "price", None))
                if not isinstance(ts, pd.Timestamp) or price is None:
                    continue
                if open_price is None:
                    open_price = price
                    high_price = price
                    low_price = price
                    start_ts = ts
                    last_ts = ts
                    sample_count = 1
                    continue

                last_ts = ts
                while open_price is not None and abs(price - open_price) >= bar_size:
                    direction = 1 if price >= open_price else -1
                    close_price = open_price + (direction * bar_size)
                    high_price = max(high_price if high_price is not None else close_price, close_price)
                    low_price = min(low_price if low_price is not None else close_price, close_price)
                    emit(close_price, ts, True)
                    open_price = close_price
                    high_price = open_price
                    low_price = open_price
                    start_ts = ts
                    sample_count = 1

                if open_price is not None:
                    sample_count += 1
                    high_price = max(high_price if high_price is not None else price, price)
                    low_price = min(low_price if low_price is not None else price, price)

            if include_partial and open_price is not None and last_ts is not None:
                latest_close = _safe_float(ordered.iloc[-1].get("price"))
                if latest_close is not None:
                    emit(latest_close, last_ts, False)

        return rows

    def latest_price_payload(self, *, symbol: str = DEFAULT_SYMBOL) -> dict[str, Any]:
        resolved_symbol = (
            self.chart_service._resolve_symbol(symbol)
            or str(symbol or DEFAULT_SYMBOL).strip()
            or DEFAULT_SYMBOL
        )
        records = self.chart_service.history_store.query_latest_symbols({resolved_symbol})
        latest = records[0] if records else None
        if not latest:
            return {
                "ok": False,
                "status": "no_latest_price",
                "symbol": resolved_symbol,
                "latest": None,
            }

        captured_at = self._parse_capture_datetime(latest.get("captured_at"))
        price = _safe_float(latest.get("price"))
        if captured_at is None or price is None:
            return {
                "ok": False,
                "status": "invalid_latest_price",
                "symbol": resolved_symbol,
                "latest": None,
            }

        return {
            "ok": True,
            "status": "ready",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "atemporal_latest_price",
            "symbol": resolved_symbol,
            "latest": {
                "capture_id": latest.get("capture_id"),
                "timestamp": captured_at.isoformat(),
                "timestamp_ms": int(captured_at.timestamp() * 1000),
                "price": round(price, 4),
                "daily_change_pct": _safe_float(latest.get("daily_change_pct")),
            },
        }

    def build_payload(
        self,
        *,
        symbol: str = DEFAULT_SYMBOL,
        lookback_minutes: int = 10080,
        tick_size_points: float = 5.0,
        ticks_per_candle: int = 10,
        moving_average_points: int = 271,
        implied_vol: float | None = None,
        max_points: int = 900,
        include_partial: bool = True,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        resolved_symbol = (
            self.chart_service._resolve_symbol(symbol)
            or str(symbol or DEFAULT_SYMBOL).strip()
            or DEFAULT_SYMBOL
        )
        resolved_lookback = max(int(lookback_minutes or 1), 1)
        since = datetime.now(timezone.utc) - timedelta(minutes=resolved_lookback)
        resolved_max_points = max(int(max_points or 900), 1)
        storage_mode = "raw_history_rebuild"
        latest_capture_at: datetime | None = None
        rows: list[dict[str, Any]] = []

        if self._cache_supported(resolved_symbol, include_partial):
            rows, latest_capture_at, storage_mode = self._build_or_load_xb1_cached_rows(
                resolved_symbol=resolved_symbol,
                since=since,
                tick_size_points=tick_size_points,
                ticks_per_candle=ticks_per_candle,
                max_points=resolved_max_points,
                include_partial=include_partial,
                force_refresh=force_refresh,
            )

        if not rows:
            records = self.chart_service.history_store.query_symbols_history(
                {resolved_symbol},
                since=since,
            )
            frame = pd.DataFrame.from_records(records)
            if frame.empty:
                frame, latest_capture_at = self.chart_service._load_benchmark_history_frame(
                    lookback_minutes=resolved_lookback,
                    benchmark_symbol=resolved_symbol,
                )
                storage_mode = "csv_fallback"
            if frame.empty:
                return {
                    "ok": False,
                    "status": "no_history",
                    "symbol": resolved_symbol,
                    "chart_rows": [],
                    "latest": None,
                }

            prepared = self._prepare_history_frame(
                frame,
                target_points=max(float(tick_size_points), 0.01) * max(int(ticks_per_candle), 1),
                apply_outlier_guard=str(resolved_symbol or "").strip().upper() == XB1_CACHE_SYMBOL,
            )
            if prepared.empty:
                return {
                    "ok": False,
                    "status": "no_session_history",
                    "symbol": resolved_symbol,
                    "chart_rows": [],
                    "latest": None,
                }

            latest_capture_at = self._latest_capture_from_frame(prepared)
            rows = self._build_movement_rows(
                prepared,
                tick_size_points=tick_size_points,
                ticks_per_candle=ticks_per_candle,
                include_partial=include_partial,
            )
            source_epoch = _safe_float(
                latest_capture_at.timestamp() if latest_capture_at is not None else None
            )
            if source_epoch is not None:
                for row in rows:
                    row["source_last_capture_at_epoch"] = source_epoch

        normalized_iv = self._normalize_implied_vol(implied_vol)
        rows = rows[-resolved_max_points:]
        for index, row in enumerate(rows, start=1):
            row["bar_index"] = index
        self._append_indicator_bands(
            rows,
            moving_average_points=moving_average_points,
            implied_vol=normalized_iv,
        )
        latest = rows[-1] if rows else None
        return {
            "ok": bool(rows),
            "status": "ready" if rows else "insufficient_movement",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "atemporal_price_chart_service",
            "symbol": resolved_symbol,
            "lookback_minutes": max(int(lookback_minutes or 1), 1),
            "latest_capture_at": latest_capture_at.isoformat() if latest_capture_at else None,
            "tick_size_points": float(tick_size_points),
            "ticks_per_candle": int(ticks_per_candle),
            "target_points": float(tick_size_points) * int(ticks_per_candle),
            "moving_average_points": int(moving_average_points),
            "implied_vol": normalized_iv,
            "band_formula": "MA271 +/- MA271 * IV_ATM / sqrt(252)",
            "storage_mode": storage_mode,
            "chart_rows": rows,
            "latest": latest,
        }
