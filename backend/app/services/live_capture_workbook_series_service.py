from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Iterable

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("aquiles.live_capture_workbook_series")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _parse_iso_epoch(value: Any) -> float | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return float(parsed.astimezone(timezone.utc).timestamp())


class LiveCaptureWorkbookSeriesService:
    """Indexed reader for live-capture workbook archive values.

    The capture process still owns the JSONL append path. This service builds a
    small SQLite read index on demand so Discovery widgets do not parse a full
    archive file for every chart refresh.
    """

    def __init__(self, root_dir: str | None = None, db_path: str | None = None) -> None:
        self.root_dir = os.path.abspath(root_dir or Config.MACRO_DATA_DIR)
        self.state_path = os.path.join(self.root_dir, "options_heatmap_context.json")
        self.live_capture_archive_dir = os.path.join(self.root_dir, "live_capture_archive")
        self.db_path = os.path.abspath(
            db_path or os.path.join(self.root_dir, "live_capture_workbook_series.sqlite3")
        )
        self._lock = threading.RLock()
        self._initialized = False

    @staticmethod
    def archive_underlying_key(underlying_security: str) -> str:
        text = str(underlying_security or "IBOVE Index").strip().replace(" ", "_")
        return "".join(ch for ch in text if ch.isalnum() or ch in {"_", "-" }).upper() or "IBOVE_INDEX"

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
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
                    CREATE TABLE IF NOT EXISTS live_capture_workbook_values (
                        session_date TEXT NOT NULL,
                        underlying_security TEXT NOT NULL,
                        security TEXT NOT NULL COLLATE NOCASE,
                        captured_at TEXT NOT NULL,
                        captured_at_epoch REAL NOT NULL,
                        raw_value REAL NOT NULL,
                        daily_change_pct REAL,
                        source_file TEXT NOT NULL,
                        inserted_at TEXT NOT NULL,
                        PRIMARY KEY (
                            session_date,
                            underlying_security,
                            security,
                            captured_at
                        )
                    );

                    CREATE INDEX IF NOT EXISTS idx_live_capture_workbook_lookup
                        ON live_capture_workbook_values (
                            session_date,
                            underlying_security,
                            security,
                            captured_at_epoch
                        );

                    CREATE TABLE IF NOT EXISTS live_capture_workbook_ingested_files (
                        path TEXT NOT NULL,
                        security TEXT NOT NULL COLLATE NOCASE,
                        session_date TEXT NOT NULL,
                        underlying_security TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL DEFAULT 0,
                        mtime_ns INTEGER NOT NULL DEFAULT 0,
                        offset_bytes INTEGER NOT NULL DEFAULT 0,
                        line_count INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (path, security)
                    );
                    """
                )
            self._initialized = True

    def _archive_path(self, *, session_date: str, underlying_security: str) -> str:
        filename = f"{session_date}_{self.archive_underlying_key(underlying_security)}.jsonl"
        return os.path.join(self.live_capture_archive_dir, filename)

    def list_session_dates(self, *, underlying_security: str) -> list[str]:
        suffix = f"_{self.archive_underlying_key(underlying_security)}.jsonl"
        try:
            return sorted(
                str(entry)[:-len(suffix)]
                for entry in os.listdir(self.live_capture_archive_dir)
                if str(entry).endswith(suffix) and str(entry)[:-len(suffix)]
            )
        except Exception:
            logger.exception("Failed to enumerate live capture workbook archive dates")
            return []

    @staticmethod
    def _normalize_securities(securities: Iterable[Any]) -> list[str]:
        normalized = [
            str(item or "").strip()
            for item in securities
            if str(item or "").strip()
        ]
        return list(dict.fromkeys(normalized))

    @staticmethod
    def _workbook_pair(values: dict[str, Any] | None, security: str) -> tuple[float | None, float | None]:
        target = str(security or "").strip()
        if not target:
            return None, None
        source = values or {}
        direct = source.get(target)
        if direct is None:
            lowered = target.lower()
            for key, raw_dynamic in source.items():
                if str(key or "").strip().lower() == lowered:
                    direct = raw_dynamic
                    break
        if direct is None:
            return None, None
        if isinstance(direct, (list, tuple)):
            raw_value = _finite_float(direct[0] if len(direct) >= 1 else None)
            daily_change_pct = _finite_float(direct[1] if len(direct) >= 2 else None)
            return raw_value, daily_change_pct
        dynamic = dict(direct or {})
        return _finite_float(dynamic.get("raw_value")), _finite_float(dynamic.get("daily_change_pct"))

    @staticmethod
    def _row_from_snapshot(
        payload: dict[str, Any],
        *,
        fallback_session_date: str,
        underlying_security: str,
        security: str,
        source_file: str,
    ) -> tuple[Any, ...] | None:
        raw_value, daily_change_pct = LiveCaptureWorkbookSeriesService._workbook_pair(
            payload.get("workbook_values") or {},
            security,
        )
        if raw_value is None:
            return None
        captured_at = str(payload.get("captured_at") or payload.get("current_price_timestamp") or "").strip()
        captured_epoch = _parse_iso_epoch(captured_at)
        if not captured_at or captured_epoch is None:
            return None
        session_date = str(payload.get("session_date") or fallback_session_date or "").strip()
        if not session_date:
            return None
        return (
            session_date,
            underlying_security,
            security,
            captured_at,
            captured_epoch,
            raw_value,
            daily_change_pct,
            source_file,
            _utc_now_iso(),
        )

    @staticmethod
    def _upsert_rows(conn: sqlite3.Connection, rows: list[tuple[Any, ...]]) -> None:
        if not rows:
            return
        conn.executemany(
            """
            INSERT INTO live_capture_workbook_values (
                session_date,
                underlying_security,
                security,
                captured_at,
                captured_at_epoch,
                raw_value,
                daily_change_pct,
                source_file,
                inserted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                session_date,
                underlying_security,
                security,
                captured_at
            ) DO UPDATE SET
                captured_at_epoch = excluded.captured_at_epoch,
                raw_value = excluded.raw_value,
                daily_change_pct = excluded.daily_change_pct,
                source_file = excluded.source_file,
                inserted_at = excluded.inserted_at
            """,
            rows,
        )

    def _sync_archive(
        self,
        *,
        session_date: str,
        underlying_security: str,
        securities: list[str],
    ) -> dict[str, Any]:
        self._ensure_schema()
        archive_path = self._archive_path(
            session_date=session_date,
            underlying_security=underlying_security,
        )
        if not os.path.exists(archive_path):
            return {"path": archive_path, "exists": False, "inserted": 0, "line_count": 0}

        stat = os.stat(archive_path)
        file_size = int(stat.st_size)
        file_mtime_ns = int(stat.st_mtime_ns)
        source_file = os.path.abspath(archive_path)
        normalized_securities = self._normalize_securities(securities)
        if not normalized_securities:
            return {"path": archive_path, "exists": True, "inserted": 0, "line_count": 0}

        with self._lock:
            with self._connect() as conn:
                placeholders = ", ".join("?" for _ in normalized_securities)
                states = conn.execute(
                    f"""
                    SELECT security, size_bytes, mtime_ns, offset_bytes
                    FROM live_capture_workbook_ingested_files
                    WHERE path = ? AND security IN ({placeholders})
                    """,
                    [source_file, *normalized_securities],
                ).fetchall()
                state_by_security = {str(row["security"]).lower(): row for row in states}
                pending_securities: list[str] = []
                offsets: list[int] = []
                for security in normalized_securities:
                    state = state_by_security.get(security.lower())
                    offset = int(state["offset_bytes"]) if state is not None else 0
                    size_bytes = int(state["size_bytes"]) if state is not None else -1
                    mtime_ns = int(state["mtime_ns"]) if state is not None else -1
                    up_to_date = state is not None and size_bytes == file_size and mtime_ns == file_mtime_ns
                    if up_to_date:
                        continue
                    if offset > file_size:
                        offset = 0
                        conn.execute(
                            """
                            DELETE FROM live_capture_workbook_values
                            WHERE source_file = ? AND lower(security) = lower(?)
                            """,
                            (source_file, security),
                        )
                    pending_securities.append(security)
                    offsets.append(max(offset, 0))

                if not pending_securities:
                    return {
                        "path": archive_path,
                        "exists": True,
                        "inserted": 0,
                        "line_count": 0,
                        "cached": True,
                    }

                start_offset = min(offsets) if offsets else 0
                if start_offset <= 0:
                    for security in pending_securities:
                        conn.execute(
                            """
                            DELETE FROM live_capture_workbook_values
                            WHERE source_file = ? AND lower(security) = lower(?)
                            """,
                            (source_file, security),
                        )

                inserted = 0
                line_count = 0
                batch: list[tuple[Any, ...]] = []
                final_offset = start_offset
                with open(archive_path, "rb") as handle:
                    handle.seek(start_offset)
                    for raw_line in handle:
                        final_offset = handle.tell()
                        line_count += 1
                        raw = raw_line.decode("utf-8", errors="replace").strip()
                        if not raw:
                            continue
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            continue
                        if not isinstance(payload, dict):
                            continue
                        for security in pending_securities:
                            row = self._row_from_snapshot(
                                payload,
                                fallback_session_date=session_date,
                                underlying_security=underlying_security,
                                security=security,
                                source_file=source_file,
                            )
                            if row is None:
                                continue
                            batch.append(row)
                        if len(batch) >= 5000:
                            self._upsert_rows(conn, batch)
                            inserted += len(batch)
                            batch.clear()
                    if batch:
                        self._upsert_rows(conn, batch)
                        inserted += len(batch)
                        batch.clear()

                now_iso = _utc_now_iso()
                for security in pending_securities:
                    conn.execute(
                        """
                        INSERT INTO live_capture_workbook_ingested_files (
                            path,
                            security,
                            session_date,
                            underlying_security,
                            size_bytes,
                            mtime_ns,
                            offset_bytes,
                            line_count,
                            updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(path, security) DO UPDATE SET
                            session_date = excluded.session_date,
                            underlying_security = excluded.underlying_security,
                            size_bytes = excluded.size_bytes,
                            mtime_ns = excluded.mtime_ns,
                            offset_bytes = excluded.offset_bytes,
                            line_count = live_capture_workbook_ingested_files.line_count + excluded.line_count,
                            updated_at = excluded.updated_at
                        """,
                        (
                            source_file,
                            security,
                            session_date,
                            underlying_security,
                            file_size,
                            file_mtime_ns,
                            final_offset,
                            line_count,
                            now_iso,
                        ),
                    )

                return {
                    "path": archive_path,
                    "exists": True,
                    "inserted": inserted,
                    "line_count": line_count,
                    "cached": False,
                }

    def _query_series(
        self,
        *,
        session_dates: list[str],
        underlying_security: str,
        security: str,
    ) -> list[dict[str, Any]]:
        self._ensure_schema()
        if not session_dates:
            return []
        placeholders = ", ".join("?" for _ in session_dates)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    session_date,
                    captured_at,
                    security,
                    raw_value,
                    daily_change_pct,
                    underlying_security
                FROM live_capture_workbook_values
                WHERE session_date IN ({placeholders})
                    AND underlying_security = ?
                    AND lower(security) = lower(?)
                ORDER BY captured_at_epoch ASC, captured_at ASC
                """,
                [*session_dates, underlying_security, security],
            ).fetchall()
        return [
            {
                "date": row["session_date"],
                "session_date": row["session_date"],
                "captured_at": row["captured_at"],
                "security": row["security"],
                "raw_value": row["raw_value"],
                "daily_change_pct": row["daily_change_pct"],
                "underlying_security": row["underlying_security"],
            }
            for row in rows
        ]

    def _query_latest(
        self,
        *,
        session_dates: list[str],
        underlying_security: str,
        security: str,
    ) -> dict[str, Any] | None:
        self._ensure_schema()
        if not session_dates:
            return None
        placeholders = ", ".join("?" for _ in session_dates)
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT
                    session_date,
                    captured_at,
                    security,
                    raw_value,
                    daily_change_pct,
                    underlying_security
                FROM live_capture_workbook_values
                WHERE session_date IN ({placeholders})
                    AND underlying_security = ?
                    AND lower(security) = lower(?)
                ORDER BY captured_at_epoch DESC, captured_at DESC
                LIMIT 1
                """,
                [*session_dates, underlying_security, security],
            ).fetchone()
        if row is None:
            return None
        return {
            "date": row["session_date"],
            "session_date": row["session_date"],
            "captured_at": row["captured_at"],
            "security": row["security"],
            "raw_value": row["raw_value"],
            "daily_change_pct": row["daily_change_pct"],
            "underlying_security": row["underlying_security"],
        }

    def _read_recent_state_rows(
        self,
        *,
        session_dates: list[str],
        underlying_security: str,
        securities: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        if not session_dates or not os.path.exists(self.state_path):
            return {security: [] for security in securities}
        session_set = set(session_dates)
        rows_by_security = {security: [] for security in securities}
        try:
            with open(self.state_path, "r", encoding="utf-8", errors="replace") as handle:
                state = json.load(handle)
            history = (state or {}).get("live_capture_history") or {}
            snapshots = []
            latest_snapshot = history.get("latest_snapshot")
            if isinstance(latest_snapshot, dict):
                snapshots.append(latest_snapshot)
            snapshots.extend(
                dict(item or {})
                for item in (history.get("snapshots") or [])
                if isinstance(item, dict)
            )
            for snapshot in snapshots:
                if str(snapshot.get("underlying_security") or "IBOVE Index") != underlying_security:
                    continue
                snapshot_session = str(snapshot.get("session_date") or "").strip()
                if snapshot_session not in session_set:
                    continue
                for security in securities:
                    row = self._row_from_snapshot(
                        snapshot,
                        fallback_session_date=snapshot_session,
                        underlying_security=underlying_security,
                        security=security,
                        source_file=self.state_path,
                    )
                    if row is None:
                        continue
                    rows_by_security[security].append(
                        {
                            "date": row[0],
                            "session_date": row[0],
                            "captured_at": row[3],
                            "security": row[2],
                            "raw_value": row[5],
                            "daily_change_pct": row[6],
                            "underlying_security": row[1],
                        }
                    )
        except Exception:
            logger.exception("Failed to read recent live-capture workbook state")
        return rows_by_security

    @staticmethod
    def _merge_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for row in rows:
            captured_at = str((row or {}).get("captured_at") or "").strip()
            if captured_at:
                merged[captured_at] = dict(row or {})
        return sorted(merged.values(), key=lambda item: str(item.get("captured_at") or ""))

    def read_series(
        self,
        *,
        underlying_security: str = "IBOVE Index",
        security: str = "VXBR Index",
        session_date: str | None = None,
        session_count: int = 2,
        include_recent_state: bool = False,
    ) -> dict[str, Any]:
        multi = self.read_series_multi(
            underlying_security=underlying_security,
            securities=[security],
            session_date=session_date,
            session_count=session_count,
            include_recent_state=include_recent_state,
        )
        rows = multi["series_by_security"].get(security) or []
        return {
            "underlying_security": underlying_security,
            "security": security,
            "session_dates": multi["session_dates"],
            "series": rows,
            "latest": rows[-1] if rows else None,
            "sync": multi.get("sync"),
        }

    def read_series_multi(
        self,
        *,
        underlying_security: str = "IBOVE Index",
        securities: Iterable[Any],
        session_date: str | None = None,
        session_count: int = 2,
        include_recent_state: bool = False,
    ) -> dict[str, Any]:
        normalized_underlying = str(underlying_security or "IBOVE Index").strip() or "IBOVE Index"
        normalized_securities = self._normalize_securities(securities)
        if not normalized_securities:
            normalized_securities = ["VXBR Index"]

        resolved_session_date = str(session_date or "").strip()
        if resolved_session_date:
            selected_dates = [resolved_session_date]
        else:
            available_dates = self.list_session_dates(underlying_security=normalized_underlying)
            selected_dates = available_dates[-max(1, min(int(session_count or 2), 10)) :]

        sync_results = []
        for item in selected_dates:
            sync_results.append(
                self._sync_archive(
                    session_date=item,
                    underlying_security=normalized_underlying,
                    securities=normalized_securities,
                )
            )

        recent_rows = (
            self._read_recent_state_rows(
                session_dates=selected_dates,
                underlying_security=normalized_underlying,
                securities=normalized_securities,
            )
            if include_recent_state
            else {security: [] for security in normalized_securities}
        )

        series_by_security: dict[str, list[dict[str, Any]]] = {}
        latest_by_security: dict[str, dict[str, Any] | None] = {}
        for security in normalized_securities:
            archive_rows = self._query_series(
                session_dates=selected_dates,
                underlying_security=normalized_underlying,
                security=security,
            )
            rows = self._merge_rows([*archive_rows, *(recent_rows.get(security) or [])])
            series_by_security[security] = rows
            latest_by_security[security] = rows[-1] if rows else None

        return {
            "underlying_security": normalized_underlying,
            "securities": normalized_securities,
            "session_dates": selected_dates,
            "series_by_security": series_by_security,
            "latest_by_security": latest_by_security,
            "sync": sync_results,
        }

    def read_latest_multi(
        self,
        *,
        underlying_security: str = "IBOVE Index",
        securities: Iterable[Any],
        session_date: str | None = None,
        include_recent_state: bool = True,
    ) -> dict[str, Any]:
        normalized_underlying = str(underlying_security or "IBOVE Index").strip() or "IBOVE Index"
        normalized_securities = self._normalize_securities(securities)
        if not normalized_securities:
            normalized_securities = ["VXBR Index"]

        resolved_session_date = str(session_date or "").strip()
        if resolved_session_date:
            selected_dates = [resolved_session_date]
        else:
            available_dates = self.list_session_dates(underlying_security=normalized_underlying)
            selected_dates = available_dates[-1:]

        sync_results = []
        for item in selected_dates:
            sync_results.append(
                self._sync_archive(
                    session_date=item,
                    underlying_security=normalized_underlying,
                    securities=normalized_securities,
                )
            )

        recent_rows = (
            self._read_recent_state_rows(
                session_dates=selected_dates,
                underlying_security=normalized_underlying,
                securities=normalized_securities,
            )
            if include_recent_state
            else {security: [] for security in normalized_securities}
        )

        latest_by_security: dict[str, dict[str, Any] | None] = {}
        for security in normalized_securities:
            candidates = []
            archive_latest = self._query_latest(
                session_dates=selected_dates,
                underlying_security=normalized_underlying,
                security=security,
            )
            if archive_latest:
                candidates.append(archive_latest)
            candidates.extend(recent_rows.get(security) or [])
            merged = self._merge_rows(candidates)
            latest_by_security[security] = merged[-1] if merged else None

        return {
            "underlying_security": normalized_underlying,
            "securities": normalized_securities,
            "session_dates": selected_dates,
            "latest_by_security": latest_by_security,
            "sync": sync_results,
        }
