from __future__ import annotations

import csv
import io
import json
import math
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Iterable

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("aquiles.market_screen_history_store")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _parse_iso_utc(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _datetime_to_epoch(value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return float(value.astimezone(timezone.utc).timestamp())


class MarketScreenHistoryStore:
    """SQLite index for OCR market-screen history rows.

    CSV remains the compatibility artifact. This store gives the chart layer an
    indexed time-series path without introducing external infrastructure.
    """

    def __init__(self, root_dir: str | None = None, db_path: str | None = None) -> None:
        self.root_dir = os.path.abspath(
            root_dir or os.path.join(Config.OPTIONS_DATA_DIR, "market_screen_capture")
        )
        configured_db_path = str(
            db_path or getattr(Config, "MARKET_SCREEN_W32_HISTORY_DB_PATH", "") or ""
        ).strip()
        self.db_path = os.path.abspath(
            configured_db_path or os.path.join(self.root_dir, "market_screen_history.sqlite3")
        )
        self._lock = threading.RLock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    def _ensure_schema(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS market_screen_rows (
                        capture_id TEXT NOT NULL,
                        captured_at TEXT NOT NULL,
                        captured_at_epoch REAL NOT NULL,
                        symbol TEXT NOT NULL,
                        symbol_raw TEXT,
                        symbol_normalized TEXT,
                        price REAL NOT NULL,
                        daily_change_pct REAL,
                        direction TEXT,
                        price_raw TEXT,
                        daily_change_raw TEXT,
                        window_title TEXT,
                        image_path TEXT,
                        source_file TEXT,
                        inserted_at TEXT NOT NULL,
                        PRIMARY KEY (capture_id, symbol)
                    );

                    CREATE INDEX IF NOT EXISTS idx_market_screen_rows_symbol_time
                        ON market_screen_rows(symbol, captured_at_epoch);

                    CREATE INDEX IF NOT EXISTS idx_market_screen_rows_time
                        ON market_screen_rows(captured_at_epoch);

                    CREATE TABLE IF NOT EXISTS market_screen_candles (
                        symbol TEXT NOT NULL,
                        bar_minutes INTEGER NOT NULL,
                        bucket_epoch REAL NOT NULL,
                        bucket_at TEXT NOT NULL,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        first_capture_at_epoch REAL NOT NULL,
                        last_capture_at_epoch REAL NOT NULL,
                        daily_change_pct REAL,
                        sample_count INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (symbol, bar_minutes, bucket_epoch)
                    );

                    CREATE INDEX IF NOT EXISTS idx_market_screen_candles_symbol_time
                        ON market_screen_candles(symbol, bar_minutes, bucket_epoch);

                    CREATE TABLE IF NOT EXISTS atemporal_price_candles (
                        symbol TEXT NOT NULL,
                        tick_size_points REAL NOT NULL,
                        ticks_per_candle INTEGER NOT NULL,
                        session_date TEXT NOT NULL,
                        sequence INTEGER NOT NULL,
                        timestamp TEXT NOT NULL,
                        timestamp_ms INTEGER NOT NULL,
                        start_timestamp TEXT,
                        open REAL NOT NULL,
                        high REAL NOT NULL,
                        low REAL NOT NULL,
                        close REAL NOT NULL,
                        price REAL NOT NULL,
                        direction TEXT,
                        complete INTEGER NOT NULL DEFAULT 1,
                        movement_points REAL,
                        target_points REAL,
                        sample_count INTEGER NOT NULL DEFAULT 0,
                        source_last_capture_at_epoch REAL NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (
                            symbol,
                            tick_size_points,
                            ticks_per_candle,
                            session_date,
                            sequence
                        )
                    );

                    CREATE INDEX IF NOT EXISTS idx_atemporal_price_candles_symbol_time
                        ON atemporal_price_candles(
                            symbol,
                            tick_size_points,
                            ticks_per_candle,
                            timestamp_ms
                        );

                    CREATE INDEX IF NOT EXISTS idx_atemporal_price_candles_symbol_source
                        ON atemporal_price_candles(
                            symbol,
                            tick_size_points,
                            ticks_per_candle,
                            source_last_capture_at_epoch
                        );

                    CREATE TABLE IF NOT EXISTS market_screen_ingested_files (
                        path TEXT PRIMARY KEY,
                        size_bytes INTEGER NOT NULL DEFAULT 0,
                        mtime_ns INTEGER NOT NULL DEFAULT 0,
                        offset_bytes INTEGER NOT NULL DEFAULT 0,
                        fieldnames_json TEXT,
                        row_count INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS fair_value_asset_stats (
                        symbol TEXT NOT NULL,
                        bar_minutes INTEGER NOT NULL,
                        rolling_window_points INTEGER NOT NULL,
                        session_start_minutes INTEGER NOT NULL,
                        session_end_minutes INTEGER NOT NULL,
                        samples INTEGER,
                        pearson_samples INTEGER,
                        pearson_mean REAL,
                        pearson_min REAL,
                        pearson_max REAL,
                        pearson_median REAL,
                        pearson_std REAL,
                        effective_beta REAL,
                        daily_change_min REAL,
                        daily_change_max REAL,
                        daily_change_mean REAL,
                        daily_change_median REAL,
                        daily_change_std REAL,
                        oscillation_component_pct REAL,
                        latest_price REAL,
                        asset_previous_close REAL,
                        latest_intraday_return_pct REAL,
                        latest_daily_change_pct REAL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (
                            symbol,
                            bar_minutes,
                            rolling_window_points,
                            session_start_minutes,
                            session_end_minutes
                        )
                    );
                    """
                )
            self._initialized = True

    @staticmethod
    def _row_symbol(row: dict[str, Any]) -> str:
        return str(
            row.get("symbol")
            or row.get("symbol_normalized")
            or row.get("symbol_raw")
            or ""
        ).strip()

    @staticmethod
    def _normalized_record(
        row: dict[str, Any],
        *,
        source_file: str | None,
    ) -> tuple[Any, ...] | None:
        captured_at = _parse_iso_utc(row.get("captured_at"))
        captured_epoch = _datetime_to_epoch(captured_at)
        symbol = MarketScreenHistoryStore._row_symbol(row)
        price = _safe_float(row.get("price"))
        if captured_at is None or captured_epoch is None or not symbol or price is None:
            return None

        capture_id = str(row.get("capture_id") or "").strip()
        if not capture_id:
            capture_id = f"{captured_at.isoformat()}:{symbol}"

        return (
            capture_id,
            captured_at.isoformat(),
            captured_epoch,
            symbol,
            str(row.get("symbol_raw") or "").strip() or None,
            str(row.get("symbol_normalized") or "").strip() or None,
            price,
            _safe_float(row.get("daily_change_pct")),
            str(row.get("direction") or "").strip() or None,
            str(row.get("price_raw") or "").strip() or None,
            str(row.get("daily_change_raw") or "").strip() or None,
            str(row.get("window_title") or "").strip() or None,
            str(row.get("image_path") or "").strip() or None,
            source_file,
            _utc_now_iso(),
        )

    @staticmethod
    def _bucket_epoch(captured_at_epoch: float, bar_minutes: int) -> float:
        seconds = max(int(bar_minutes), 1) * 60
        return float(math.floor(float(captured_at_epoch) / seconds) * seconds)

    @staticmethod
    def _epoch_iso(epoch_seconds: float) -> str:
        return datetime.fromtimestamp(float(epoch_seconds), tz=timezone.utc).isoformat()

    def _upsert_candle_records(
        self,
        conn: sqlite3.Connection,
        records: Iterable[tuple[Any, ...]],
        *,
        bar_minutes: int,
    ) -> int:
        resolved_bar_minutes = max(int(bar_minutes or 5), 1)
        candle_records: list[tuple[Any, ...]] = []
        for record in records:
            symbol = str(record[3] or "").strip()
            captured_at_epoch = _safe_float(record[2])
            price = _safe_float(record[6])
            if captured_at_epoch is None or price is None:
                continue
            bucket_epoch = self._bucket_epoch(captured_at_epoch, resolved_bar_minutes)
            candle_records.append(
                (
                    symbol,
                    resolved_bar_minutes,
                    bucket_epoch,
                    self._epoch_iso(bucket_epoch),
                    price,
                    price,
                    price,
                    price,
                    captured_at_epoch,
                    captured_at_epoch,
                    _safe_float(record[7]),
                    1,
                    _utc_now_iso(),
                )
            )

        if not candle_records:
            return 0

        conn.executemany(
            """
            INSERT INTO market_screen_candles (
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
                sample_count,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, bar_minutes, bucket_epoch) DO UPDATE SET
                open = CASE
                    WHEN excluded.first_capture_at_epoch < market_screen_candles.first_capture_at_epoch
                    THEN excluded.open
                    ELSE market_screen_candles.open
                END,
                high = MAX(market_screen_candles.high, excluded.high),
                low = MIN(market_screen_candles.low, excluded.low),
                close = CASE
                    WHEN excluded.last_capture_at_epoch >= market_screen_candles.last_capture_at_epoch
                    THEN excluded.close
                    ELSE market_screen_candles.close
                END,
                first_capture_at_epoch = MIN(
                    market_screen_candles.first_capture_at_epoch,
                    excluded.first_capture_at_epoch
                ),
                last_capture_at_epoch = MAX(
                    market_screen_candles.last_capture_at_epoch,
                    excluded.last_capture_at_epoch
                ),
                daily_change_pct = CASE
                    WHEN excluded.last_capture_at_epoch >= market_screen_candles.last_capture_at_epoch
                    THEN excluded.daily_change_pct
                    ELSE market_screen_candles.daily_change_pct
                END,
                sample_count = market_screen_candles.sample_count + excluded.sample_count,
                updated_at = excluded.updated_at
            """,
            candle_records,
        )
        return len(candle_records)

    def append_rows(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        source_file: str | None = None,
    ) -> int:
        self._ensure_schema()
        records = [
            record
            for row in rows
            if isinstance(row, dict)
            for record in [self._normalized_record(row, source_file=source_file)]
            if record is not None
        ]
        if not records:
            return 0

        with self._lock:
            with self._connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO market_screen_rows (
                        capture_id,
                        captured_at,
                        captured_at_epoch,
                        symbol,
                        symbol_raw,
                        symbol_normalized,
                        price,
                        daily_change_pct,
                        direction,
                        price_raw,
                        daily_change_raw,
                        window_title,
                        image_path,
                        source_file,
                        inserted_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(capture_id, symbol) DO UPDATE SET
                        captured_at = excluded.captured_at,
                        captured_at_epoch = excluded.captured_at_epoch,
                        symbol_raw = excluded.symbol_raw,
                        symbol_normalized = excluded.symbol_normalized,
                        price = excluded.price,
                        daily_change_pct = excluded.daily_change_pct,
                        direction = excluded.direction,
                        price_raw = excluded.price_raw,
                        daily_change_raw = excluded.daily_change_raw,
                        window_title = excluded.window_title,
                        image_path = excluded.image_path,
                        source_file = COALESCE(excluded.source_file, market_screen_rows.source_file),
                        inserted_at = excluded.inserted_at
                    """,
                    records,
                )
                candle_minutes = int(getattr(Config, "MARKET_SCREEN_W32_HISTORY_CANDLE_MINUTES", 5) or 5)
                if candle_minutes > 0:
                    self._upsert_candle_records(
                        conn,
                        records,
                        bar_minutes=candle_minutes,
                    )
        return len(records)

    def query_symbol_history(
        self,
        symbol: str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        return self.query_symbols_history(
            {symbol},
            since=since,
            until=until,
        )

    def query_symbols_history(
        self,
        symbols: Iterable[str],
        *,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        resolved_symbols = [
            str(symbol or "").strip()
            for symbol in symbols
            if str(symbol or "").strip()
        ]
        resolved_symbols = list(dict.fromkeys(resolved_symbols))
        if not resolved_symbols:
            return []

        placeholders = ", ".join("?" for _ in resolved_symbols)
        clauses = [f"symbol IN ({placeholders})"]
        params: list[Any] = list(resolved_symbols)
        since_epoch = _datetime_to_epoch(since)
        until_epoch = _datetime_to_epoch(until)
        if since_epoch is not None:
            clauses.append("captured_at_epoch >= ?")
            params.append(since_epoch)
        if until_epoch is not None:
            clauses.append("captured_at_epoch <= ?")
            params.append(until_epoch)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    capture_id,
                    captured_at,
                    symbol,
                    price,
                    daily_change_pct
                FROM market_screen_rows
                WHERE {' AND '.join(clauses)}
                ORDER BY captured_at_epoch ASC, capture_id ASC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def ensure_candles_for_symbols(
        self,
        symbols: Iterable[str],
        *,
        bar_minutes: int,
        since: datetime | None = None,
    ) -> int:
        self._ensure_schema()
        resolved_symbols = [
            str(symbol or "").strip()
            for symbol in symbols
            if str(symbol or "").strip()
        ]
        resolved_symbols = list(dict.fromkeys(resolved_symbols))
        if not resolved_symbols:
            return 0

        resolved_bar_minutes = max(int(bar_minutes or 5), 1)
        since_epoch = _datetime_to_epoch(since)
        placeholders = ", ".join("?" for _ in resolved_symbols)
        candle_clauses = [f"symbol IN ({placeholders})", "bar_minutes = ?"]
        candle_params: list[Any] = [*resolved_symbols, resolved_bar_minutes]
        if since_epoch is not None:
            candle_clauses.append("bucket_epoch >= ?")
            candle_params.append(self._bucket_epoch(since_epoch, resolved_bar_minutes))

        with self._lock:
            with self._connect() as conn:
                existing_rows = conn.execute(
                    f"""
                    SELECT symbol, COUNT(*) AS count, MIN(bucket_epoch) AS first_bucket_epoch
                    FROM market_screen_candles
                    WHERE {' AND '.join(candle_clauses)}
                    GROUP BY symbol
                    """,
                    candle_params,
                ).fetchall()
                since_bucket = (
                    self._bucket_epoch(since_epoch, resolved_bar_minutes)
                    if since_epoch is not None
                    else None
                )
                existing_by_symbol = {
                    str(row["symbol"]): row
                    for row in existing_rows
                }
                symbols_to_build: list[str] = []
                for symbol in resolved_symbols:
                    existing = existing_by_symbol.get(symbol)
                    existing_count = int(existing["count"] if existing is not None else 0)
                    existing_first = _safe_float(existing["first_bucket_epoch"] if existing is not None else None)
                    has_sufficient_history = existing_count > 0 and (
                        since_bucket is None
                        or (existing_first is not None and existing_first <= since_bucket + (resolved_bar_minutes * 60))
                    )
                    if not has_sufficient_history:
                        symbols_to_build.append(symbol)

                if not symbols_to_build:
                    return 0

                build_placeholders = ", ".join("?" for _ in symbols_to_build)
                if any(symbol in existing_by_symbol for symbol in symbols_to_build):
                    delete_clauses = [f"symbol IN ({build_placeholders})", "bar_minutes = ?"]
                    delete_params: list[Any] = [*symbols_to_build, resolved_bar_minutes]
                    if since_bucket is not None:
                        delete_clauses.append("bucket_epoch >= ?")
                        delete_params.append(since_bucket)
                    conn.execute(
                        f"""
                        DELETE FROM market_screen_candles
                        WHERE {' AND '.join(delete_clauses)}
                        """,
                        delete_params,
                    )

                row_clauses = [f"symbol IN ({build_placeholders})"]
                row_params: list[Any] = list(symbols_to_build)
                if since_epoch is not None:
                    row_clauses.append("captured_at_epoch >= ?")
                    row_params.append(since_epoch)

                rows = conn.execute(
                    f"""
                    SELECT
                        capture_id,
                        captured_at,
                        captured_at_epoch,
                        symbol,
                        symbol_raw,
                        symbol_normalized,
                        price,
                        daily_change_pct,
                        direction,
                        price_raw,
                        daily_change_raw,
                        window_title,
                        image_path,
                        source_file,
                        inserted_at
                    FROM market_screen_rows
                    WHERE {' AND '.join(row_clauses)}
                    ORDER BY captured_at_epoch ASC, capture_id ASC
                    """,
                    row_params,
                ).fetchall()
                if not rows:
                    return 0
                records = [tuple(row) for row in rows]
                return self._upsert_candle_records(
                    conn,
                    records,
                    bar_minutes=resolved_bar_minutes,
                )

    def query_symbol_candles(
        self,
        symbol: str,
        *,
        bar_minutes: int,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        resolved_symbol = str(symbol or "").strip()
        if not resolved_symbol:
            return []

        resolved_bar_minutes = max(int(bar_minutes or 5), 1)
        clauses = ["symbol = ?", "bar_minutes = ?"]
        params: list[Any] = [resolved_symbol, resolved_bar_minutes]
        since_epoch = _datetime_to_epoch(since)
        until_epoch = _datetime_to_epoch(until)
        if since_epoch is not None:
            clauses.append("bucket_epoch >= ?")
            params.append(self._bucket_epoch(since_epoch, resolved_bar_minutes))
        if until_epoch is not None:
            clauses.append("bucket_epoch <= ?")
            params.append(until_epoch)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
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
                WHERE {' AND '.join(clauses)}
                ORDER BY bucket_epoch ASC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def query_symbols_candles(
        self,
        symbols: Iterable[str],
        *,
        bar_minutes: int,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        resolved_symbols = [
            str(symbol or "").strip()
            for symbol in symbols
            if str(symbol or "").strip()
        ]
        resolved_symbols = list(dict.fromkeys(resolved_symbols))
        if not resolved_symbols:
            return []

        resolved_bar_minutes = max(int(bar_minutes or 5), 1)
        placeholders = ", ".join("?" for _ in resolved_symbols)
        clauses = [f"symbol IN ({placeholders})", "bar_minutes = ?"]
        params: list[Any] = [*resolved_symbols, resolved_bar_minutes]
        since_epoch = _datetime_to_epoch(since)
        until_epoch = _datetime_to_epoch(until)
        if since_epoch is not None:
            clauses.append("bucket_epoch >= ?")
            params.append(self._bucket_epoch(since_epoch, resolved_bar_minutes))
        if until_epoch is not None:
            clauses.append("bucket_epoch <= ?")
            params.append(until_epoch)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
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
                WHERE {' AND '.join(clauses)}
                ORDER BY bucket_epoch ASC, symbol ASC
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def query_latest_symbols(
        self,
        symbols: Iterable[str],
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        resolved_symbols = [
            str(symbol or "").strip()
            for symbol in symbols
            if str(symbol or "").strip()
        ]
        resolved_symbols = list(dict.fromkeys(resolved_symbols))
        if not resolved_symbols:
            return []

        output: list[dict[str, Any]] = []
        with self._connect() as conn:
            for symbol in resolved_symbols:
                row = conn.execute(
                    """
                    SELECT
                        capture_id,
                        captured_at,
                        captured_at_epoch,
                        symbol,
                        price,
                        daily_change_pct
                    FROM market_screen_rows
                    WHERE symbol = ?
                    ORDER BY captured_at_epoch DESC, capture_id DESC
                    LIMIT 1
                    """,
                    (symbol,),
                ).fetchone()
                if row is not None:
                    output.append(dict(row))
        return output

    def query_atemporal_cache_summary(
        self,
        symbol: str,
        *,
        tick_size_points: float,
        ticks_per_candle: int,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        self._ensure_schema()
        resolved_symbol = str(symbol or "").strip()
        if not resolved_symbol:
            return {"count": 0}

        clauses = [
            "symbol = ?",
            "tick_size_points = ?",
            "ticks_per_candle = ?",
        ]
        params: list[Any] = [
            resolved_symbol,
            float(tick_size_points),
            max(int(ticks_per_candle or 1), 1),
        ]
        since_epoch = _datetime_to_epoch(since)
        if since_epoch is not None:
            clauses.append("timestamp_ms >= ?")
            params.append(int(since_epoch * 1000))

        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS count,
                    MIN(timestamp_ms) AS min_timestamp_ms,
                    MAX(timestamp_ms) AS max_timestamp_ms,
                    MAX(source_last_capture_at_epoch) AS max_source_last_capture_at_epoch
                FROM atemporal_price_candles
                WHERE {' AND '.join(clauses)}
                """,
                params,
            ).fetchone()

        payload = dict(row) if row is not None else {"count": 0}
        payload["count"] = int(payload.get("count") or 0)
        min_timestamp_ms = _safe_float(payload.get("min_timestamp_ms"))
        max_timestamp_ms = _safe_float(payload.get("max_timestamp_ms"))
        payload["min_end_capture_at_epoch"] = (
            min_timestamp_ms / 1000.0 if min_timestamp_ms is not None else None
        )
        payload["max_end_capture_at_epoch"] = (
            max_timestamp_ms / 1000.0 if max_timestamp_ms is not None else None
        )
        return payload

    def query_atemporal_candles(
        self,
        symbol: str,
        *,
        tick_size_points: float,
        ticks_per_candle: int,
        since: datetime | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        resolved_symbol = str(symbol or "").strip()
        if not resolved_symbol:
            return []

        clauses = [
            "symbol = ?",
            "tick_size_points = ?",
            "ticks_per_candle = ?",
        ]
        params: list[Any] = [
            resolved_symbol,
            float(tick_size_points),
            max(int(ticks_per_candle or 1), 1),
        ]
        since_epoch = _datetime_to_epoch(since)
        if since_epoch is not None:
            clauses.append("timestamp_ms >= ?")
            params.append(int(since_epoch * 1000))

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    timestamp,
                    timestamp_ms,
                    start_timestamp,
                    session_date,
                    sequence AS bar_index,
                    open,
                    high,
                    low,
                    close,
                    price,
                    direction,
                    complete,
                    movement_points,
                    target_points,
                    sample_count,
                    source_last_capture_at_epoch
                FROM atemporal_price_candles
                WHERE {' AND '.join(clauses)}
                ORDER BY timestamp_ms ASC, session_date ASC, sequence ASC
                """,
                params,
            ).fetchall()

        output = [dict(row) for row in rows]
        resolved_limit = int(limit or 0)
        if resolved_limit > 0 and len(output) > resolved_limit:
            output = output[-resolved_limit:]
        for index, row in enumerate(output, start=1):
            row["bar_index"] = index
            row["complete"] = bool(row.get("complete"))
        return output

    def replace_atemporal_candles_for_sessions(
        self,
        symbol: str,
        *,
        tick_size_points: float,
        ticks_per_candle: int,
        session_dates: Iterable[str],
        rows: Iterable[dict[str, Any]],
    ) -> int:
        self._ensure_schema()
        resolved_symbol = str(symbol or "").strip()
        if not resolved_symbol:
            return 0

        resolved_tick_size = float(tick_size_points)
        resolved_ticks = max(int(ticks_per_candle or 1), 1)
        sessions = [
            str(session or "").strip()
            for session in session_dates
            if str(session or "").strip()
        ]
        sessions = list(dict.fromkeys(sessions))
        if not sessions:
            return 0

        now_iso = _utc_now_iso()
        sequence_by_session: dict[str, int] = {}
        records: list[tuple[Any, ...]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            session_date = str(row.get("session_date") or "").strip()
            if session_date not in sessions:
                continue

            timestamp_ms = _safe_float(row.get("timestamp_ms"))
            timestamp_dt = _parse_iso_utc(row.get("timestamp"))
            if timestamp_ms is None and timestamp_dt is not None:
                timestamp_ms = _datetime_to_epoch(timestamp_dt)
                timestamp_ms = timestamp_ms * 1000 if timestamp_ms is not None else None
            if timestamp_ms is None:
                continue

            sequence = sequence_by_session.get(session_date, 0) + 1
            sequence_by_session[session_date] = sequence
            timestamp_epoch = float(timestamp_ms) / 1000.0
            records.append(
                (
                    resolved_symbol,
                    resolved_tick_size,
                    resolved_ticks,
                    session_date,
                    sequence,
                    str(row.get("timestamp") or self._epoch_iso(timestamp_epoch)),
                    int(timestamp_ms),
                    str(row.get("start_timestamp") or "").strip() or None,
                    _safe_float(row.get("open")),
                    _safe_float(row.get("high")),
                    _safe_float(row.get("low")),
                    _safe_float(row.get("close")),
                    _safe_float(row.get("price")),
                    str(row.get("direction") or "").strip() or None,
                    1 if bool(row.get("complete")) else 0,
                    _safe_float(row.get("movement_points")),
                    _safe_float(row.get("target_points")),
                    int(row.get("sample_count") or 0),
                    _safe_float(row.get("source_last_capture_at_epoch")) or timestamp_epoch,
                    now_iso,
                )
            )

        records = [
            record
            for record in records
            if record[8] is not None
            and record[9] is not None
            and record[10] is not None
            and record[11] is not None
            and record[12] is not None
            and record[18] is not None
        ]

        placeholders = ", ".join("?" for _ in sessions)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    f"""
                    DELETE FROM atemporal_price_candles
                    WHERE symbol = ?
                        AND tick_size_points = ?
                        AND ticks_per_candle = ?
                        AND session_date IN ({placeholders})
                    """,
                    [resolved_symbol, resolved_tick_size, resolved_ticks, *sessions],
                )
                if records:
                    conn.executemany(
                        """
                        INSERT INTO atemporal_price_candles (
                            symbol,
                            tick_size_points,
                            ticks_per_candle,
                            session_date,
                            sequence,
                            timestamp,
                            timestamp_ms,
                            start_timestamp,
                            open,
                            high,
                            low,
                            close,
                            price,
                            direction,
                            complete,
                            movement_points,
                            target_points,
                            sample_count,
                            source_last_capture_at_epoch,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        records,
                    )
        return len(records)

    def replace_fair_value_asset_stats(
        self,
        stats: dict[str, dict[str, Any]],
        *,
        bar_minutes: int,
        rolling_window_points: int,
        session_start_minutes: int,
        session_end_minutes: int,
    ) -> int:
        self._ensure_schema()
        resolved_bar_minutes = max(int(bar_minutes or 5), 1)
        resolved_window = max(int(rolling_window_points or 60), 1)
        start_minutes = int(session_start_minutes)
        end_minutes = int(session_end_minutes)
        records: list[tuple[Any, ...]] = []
        for symbol, payload in (stats or {}).items():
            if not isinstance(payload, dict):
                continue
            resolved_symbol = str(symbol or payload.get("symbol") or "").strip()
            if not resolved_symbol:
                continue
            records.append(
                (
                    resolved_symbol,
                    resolved_bar_minutes,
                    resolved_window,
                    start_minutes,
                    end_minutes,
                    int(payload.get("samples") or 0),
                    int(payload.get("pearson_samples") or 0),
                    _safe_float(payload.get("pearson_mean")),
                    _safe_float(payload.get("pearson_min")),
                    _safe_float(payload.get("pearson_max")),
                    _safe_float(payload.get("pearson_median")),
                    _safe_float(payload.get("pearson_std")),
                    _safe_float(payload.get("effective_beta")),
                    _safe_float(payload.get("daily_change_min")),
                    _safe_float(payload.get("daily_change_max")),
                    _safe_float(payload.get("daily_change_mean")),
                    _safe_float(payload.get("daily_change_median")),
                    _safe_float(payload.get("daily_change_std")),
                    _safe_float(payload.get("oscillation_component_pct")),
                    _safe_float(payload.get("latest_price")),
                    _safe_float(payload.get("asset_previous_close")),
                    _safe_float(payload.get("latest_intraday_return_pct")),
                    _safe_float(payload.get("latest_daily_change_pct")),
                    _utc_now_iso(),
                )
            )
        if not records:
            return 0

        with self._lock:
            with self._connect() as conn:
                conn.executemany(
                    """
                    INSERT INTO fair_value_asset_stats (
                        symbol,
                        bar_minutes,
                        rolling_window_points,
                        session_start_minutes,
                        session_end_minutes,
                        samples,
                        pearson_samples,
                        pearson_mean,
                        pearson_min,
                        pearson_max,
                        pearson_median,
                        pearson_std,
                        effective_beta,
                        daily_change_min,
                        daily_change_max,
                        daily_change_mean,
                        daily_change_median,
                        daily_change_std,
                        oscillation_component_pct,
                        latest_price,
                        asset_previous_close,
                        latest_intraday_return_pct,
                        latest_daily_change_pct,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(
                        symbol,
                        bar_minutes,
                        rolling_window_points,
                        session_start_minutes,
                        session_end_minutes
                    ) DO UPDATE SET
                        samples = excluded.samples,
                        pearson_samples = excluded.pearson_samples,
                        pearson_mean = excluded.pearson_mean,
                        pearson_min = excluded.pearson_min,
                        pearson_max = excluded.pearson_max,
                        pearson_median = excluded.pearson_median,
                        pearson_std = excluded.pearson_std,
                        effective_beta = excluded.effective_beta,
                        daily_change_min = excluded.daily_change_min,
                        daily_change_max = excluded.daily_change_max,
                        daily_change_mean = excluded.daily_change_mean,
                        daily_change_median = excluded.daily_change_median,
                        daily_change_std = excluded.daily_change_std,
                        oscillation_component_pct = excluded.oscillation_component_pct,
                        latest_price = excluded.latest_price,
                        asset_previous_close = excluded.asset_previous_close,
                        latest_intraday_return_pct = excluded.latest_intraday_return_pct,
                        latest_daily_change_pct = excluded.latest_daily_change_pct,
                        updated_at = excluded.updated_at
                    """,
                    records,
                )
        return len(records)

    def query_fair_value_asset_stats(
        self,
        symbols: Iterable[str],
        *,
        bar_minutes: int,
        rolling_window_points: int,
        session_start_minutes: int,
        session_end_minutes: int,
    ) -> dict[str, dict[str, Any]]:
        self._ensure_schema()
        resolved_symbols = [
            str(symbol or "").strip()
            for symbol in symbols
            if str(symbol or "").strip()
        ]
        resolved_symbols = list(dict.fromkeys(resolved_symbols))
        if not resolved_symbols:
            return {}

        placeholders = ", ".join("?" for _ in resolved_symbols)
        params: list[Any] = [
            *resolved_symbols,
            max(int(bar_minutes or 5), 1),
            max(int(rolling_window_points or 60), 1),
            int(session_start_minutes),
            int(session_end_minutes),
        ]
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM fair_value_asset_stats
                WHERE symbol IN ({placeholders})
                    AND bar_minutes = ?
                    AND rolling_window_points = ?
                    AND session_start_minutes = ?
                    AND session_end_minutes = ?
                """,
                params,
            ).fetchall()

        output: dict[str, dict[str, Any]] = {}
        for row in rows:
            payload = dict(row)
            symbol = str(payload.get("symbol") or "").strip()
            if symbol:
                output[symbol] = payload
        return output

    def _load_file_state(self, path: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT path, size_bytes, mtime_ns, offset_bytes, fieldnames_json, row_count
                FROM market_screen_ingested_files
                WHERE path = ?
                """,
                (path,),
            ).fetchone()
        return dict(row) if row is not None else None

    def _store_file_state(
        self,
        *,
        path: str,
        size_bytes: int,
        mtime_ns: int,
        offset_bytes: int,
        fieldnames: list[str] | None,
        row_count_delta: int,
    ) -> None:
        fieldnames_json = json.dumps(fieldnames or [], ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO market_screen_ingested_files (
                    path,
                    size_bytes,
                    mtime_ns,
                    offset_bytes,
                    fieldnames_json,
                    row_count,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    size_bytes = excluded.size_bytes,
                    mtime_ns = excluded.mtime_ns,
                    offset_bytes = excluded.offset_bytes,
                    fieldnames_json = excluded.fieldnames_json,
                    row_count = market_screen_ingested_files.row_count + excluded.row_count,
                    updated_at = excluded.updated_at
                """,
                (
                    path,
                    int(size_bytes),
                    int(mtime_ns),
                    int(offset_bytes),
                    fieldnames_json,
                    int(row_count_delta),
                    _utc_now_iso(),
                ),
            )

    @staticmethod
    def _row_matches_needed_symbols(
        row: dict[str, Any],
        needed_symbols: set[str] | None,
    ) -> bool:
        if not needed_symbols:
            return True
        candidates = {
            str(row.get("symbol") or "").strip(),
            str(row.get("symbol_raw") or "").strip(),
            str(row.get("symbol_normalized") or "").strip(),
        }
        return bool(candidates & needed_symbols)

    @staticmethod
    def _row_matches_time_window(
        row: dict[str, Any],
        *,
        since_epoch: float | None,
        until_epoch: float | None,
    ) -> bool:
        if since_epoch is None and until_epoch is None:
            return True
        captured_at = _parse_iso_utc(row.get("captured_at"))
        captured_epoch = _datetime_to_epoch(captured_at)
        if captured_epoch is None:
            return False
        if since_epoch is not None and captured_epoch < since_epoch:
            return False
        return not (until_epoch is not None and captured_epoch > until_epoch)

    def _append_csv_reader_rows(
        self,
        reader: Iterable[dict[str, Any]],
        *,
        source_file: str,
        needed_symbols: set[str] | None,
        since_epoch: float | None,
        until_epoch: float | None,
        batch_size: int,
    ) -> int:
        batch: list[dict[str, Any]] = []
        row_count = 0
        for row in reader:
            if not isinstance(row, dict):
                continue
            if not self._row_matches_time_window(
                row,
                since_epoch=since_epoch,
                until_epoch=until_epoch,
            ):
                continue
            if not self._row_matches_needed_symbols(row, needed_symbols):
                continue
            batch.append(row)
            if len(batch) >= batch_size:
                row_count += self.append_rows(batch, source_file=source_file)
                batch.clear()
        if batch:
            row_count += self.append_rows(batch, source_file=source_file)
        return row_count

    def _sync_full_csv(
        self,
        path: str,
        *,
        needed_symbols: set[str] | None,
        since_epoch: float | None,
        until_epoch: float | None,
        batch_size: int,
    ) -> tuple[int, list[str] | None, int]:
        with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            row_count = self._append_csv_reader_rows(
                reader,
                source_file=path,
                needed_symbols=needed_symbols,
                since_epoch=since_epoch,
                until_epoch=until_epoch,
                batch_size=batch_size,
            )
        return os.path.getsize(path), fieldnames, row_count

    def _sync_tail_csv(
        self,
        path: str,
        *,
        offset_bytes: int,
        fieldnames: list[str],
        needed_symbols: set[str] | None,
        since_epoch: float | None,
        until_epoch: float | None,
        batch_size: int,
    ) -> tuple[int, int]:
        size = os.path.getsize(path)
        if offset_bytes >= size:
            return size, 0
        with open(path, "rb") as handle:
            handle.seek(max(int(offset_bytes), 0))
            data = handle.read()
        if not data:
            return offset_bytes, 0

        newline_index = data.rfind(b"\n")
        if newline_index < 0:
            return offset_bytes, 0

        complete = data[: newline_index + 1]
        next_offset = int(offset_bytes) + newline_index + 1
        if not complete.strip():
            return next_offset, 0

        text = complete.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text), fieldnames=fieldnames)
        row_count = self._append_csv_reader_rows(
            reader,
            source_file=path,
            needed_symbols=needed_symbols,
            since_epoch=since_epoch,
            until_epoch=until_epoch,
            batch_size=batch_size,
        )
        return next_offset, row_count

    def sync_csv_files(
        self,
        paths: Iterable[str],
        *,
        needed_symbols: set[str] | None = None,
        batch_size: int = 5000,
        force_full: bool = False,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        self._ensure_schema()
        normalized_needed = {
            str(symbol).strip()
            for symbol in (needed_symbols or set())
            if str(symbol or "").strip()
        }
        since_epoch = _datetime_to_epoch(since)
        until_epoch = _datetime_to_epoch(until)
        result = {
            "files_checked": 0,
            "files_ingested": 0,
            "rows_indexed": 0,
        }

        with self._lock:
            for raw_path in paths:
                path = os.path.abspath(str(raw_path or ""))
                if not path.lower().endswith(".csv") or not os.path.exists(path):
                    continue
                result["files_checked"] += 1
                try:
                    stat = os.stat(path)
                    state = self._load_file_state(path)
                    previous_offset = int((state or {}).get("offset_bytes") or 0)
                    previous_fieldnames_json = str((state or {}).get("fieldnames_json") or "")
                    try:
                        previous_fieldnames = json.loads(previous_fieldnames_json) if previous_fieldnames_json else []
                    except Exception:
                        previous_fieldnames = []

                    if not force_full and state and previous_offset == int(stat.st_size):
                        continue

                    if (
                        force_full
                        or not state
                        or previous_offset <= 0
                        or previous_offset > int(stat.st_size)
                        or not previous_fieldnames
                    ):
                        offset, fieldnames, row_count = self._sync_full_csv(
                            path,
                            needed_symbols=normalized_needed or None,
                            since_epoch=since_epoch,
                            until_epoch=until_epoch,
                            batch_size=batch_size,
                        )
                    else:
                        offset, row_count = self._sync_tail_csv(
                            path,
                            offset_bytes=previous_offset,
                            fieldnames=list(previous_fieldnames),
                            needed_symbols=normalized_needed or None,
                            since_epoch=since_epoch,
                            until_epoch=until_epoch,
                            batch_size=batch_size,
                        )
                        fieldnames = list(previous_fieldnames)

                    stat_after = os.stat(path)
                    self._store_file_state(
                        path=path,
                        size_bytes=int(stat_after.st_size),
                        mtime_ns=int(stat_after.st_mtime_ns),
                        offset_bytes=int(offset),
                        fieldnames=fieldnames,
                        row_count_delta=int(row_count),
                    )
                    result["files_ingested"] += 1
                    result["rows_indexed"] += int(row_count)
                except Exception:
                    logger.exception("Failed to sync market screen CSV into SQLite: %s", path)

        return result
