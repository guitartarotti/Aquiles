from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("mirofish.fair_value_markov_regime_store")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _safe_int(value: Any, default: int | None = None) -> int | None:
    parsed = _safe_float(value)
    if parsed is None:
        return default
    return int(parsed)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, default=str)


def _median(values: list[float]) -> float | None:
    clean = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2.0


def _percentile(values: list[float], percentile: float) -> float | None:
    clean = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * max(min(float(percentile), 100.0), 0.0) / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return clean[lower]
    weight = position - lower
    return clean[lower] * (1.0 - weight) + clean[upper] * weight


def _round_float(value: Any, digits: int = 6) -> float | None:
    parsed = _safe_float(value)
    if parsed is None:
        return None
    return round(parsed, digits)


def _session_date(value: Any) -> str:
    raw = str(value or "").strip()
    return raw[:10] if raw else ""


class FairValueMarkovRegimeStore:
    """SQLite memory for Markov regime runs, rows and derived metrics.

    The JSON snapshot remains the low-latency cache used by the widget. This
    store is the durable model memory: closed sessions become immutable here,
    while the current session can still be recalculated as new candles arrive.
    """

    def __init__(self, root_dir: str | None = None, db_path: str | None = None) -> None:
        self.root_dir = os.path.abspath(
            root_dir or os.path.join(Config.OPTIONS_DATA_DIR, "market_screen_capture")
        )
        self.db_path = os.path.abspath(
            db_path or os.path.join(self.root_dir, "fair_value_markov_regime.sqlite3")
        )
        self._lock = threading.RLock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=15000")
        conn.execute("PRAGMA journal_mode=WAL")
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
                    CREATE TABLE IF NOT EXISTS fair_value_markov_runs (
                        run_id TEXT PRIMARY KEY,
                        request_signature TEXT NOT NULL,
                        model_version INTEGER NOT NULL,
                        generated_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        current_session_date TEXT,
                        source_latest_timestamp_ms INTEGER,
                        source_latest_session_date TEXT,
                        requested_sessions INTEGER,
                        bar_minutes INTEGER,
                        row_count INTEGER NOT NULL DEFAULT 0,
                        session_count INTEGER NOT NULL DEFAULT 0,
                        frozen_row_count INTEGER NOT NULL DEFAULT 0,
                        frozen_session_count INTEGER NOT NULL DEFAULT 0,
                        latest_timestamp_ms INTEGER,
                        latest_session_date TEXT,
                        latest_state_key TEXT,
                        latest_tape_state_key TEXT,
                        latest_risk_label TEXT,
                        latest_risk_score REAL,
                        metrics_json TEXT NOT NULL,
                        payload_digest TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_fv_markov_runs_request_updated
                        ON fair_value_markov_runs(request_signature, model_version, updated_at);

                    CREATE TABLE IF NOT EXISTS fair_value_markov_rows (
                        request_signature TEXT NOT NULL,
                        model_version INTEGER NOT NULL,
                        session_date TEXT NOT NULL,
                        timestamp_ms INTEGER NOT NULL,
                        run_id TEXT NOT NULL,
                        is_final INTEGER NOT NULL DEFAULT 0,
                        dominant_state_key TEXT,
                        tape_regime_key TEXT,
                        risk_label TEXT,
                        risk_score REAL,
                        outlier_score REAL,
                        dislocation_score REAL,
                        row_json TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (
                            request_signature,
                            model_version,
                            session_date,
                            timestamp_ms
                        )
                    );

                    CREATE INDEX IF NOT EXISTS idx_fv_markov_rows_session_final
                        ON fair_value_markov_rows(
                            request_signature,
                            model_version,
                            session_date,
                            is_final,
                            timestamp_ms
                        );

                    CREATE INDEX IF NOT EXISTS idx_fv_markov_rows_run
                        ON fair_value_markov_rows(run_id);

                    CREATE TABLE IF NOT EXISTS fair_value_markov_metrics (
                        run_id TEXT NOT NULL,
                        metric_key TEXT NOT NULL,
                        metric_value REAL,
                        metric_text TEXT,
                        metric_json TEXT,
                        created_at TEXT NOT NULL,
                        PRIMARY KEY (run_id, metric_key)
                    );

                    CREATE INDEX IF NOT EXISTS idx_fv_markov_metrics_key
                        ON fair_value_markov_metrics(metric_key);
                    """
                )
            self._initialized = True

    @staticmethod
    def current_session_date_from_rows(rows: list[dict[str, Any]]) -> str | None:
        sessions = [
            _session_date(row.get("session_date"))
            for row in rows
            if isinstance(row, dict) and _session_date(row.get("session_date"))
        ]
        return max(sessions) if sessions else None

    @staticmethod
    def current_live_timestamp_from_rows(
        rows: list[dict[str, Any]],
        current_session_date: str | None,
    ) -> int | None:
        if not current_session_date:
            return None
        timestamps = [
            int(timestamp_ms)
            for row in rows
            if isinstance(row, dict)
            and _session_date(row.get("session_date")) == current_session_date
            for timestamp_ms in [_safe_int(row.get("timestamp_ms"))]
            if timestamp_ms is not None
        ]
        return max(timestamps) if timestamps else None

    @staticmethod
    def _is_final_row(
        *,
        session_date: str,
        timestamp_ms: int | None,
        current_session_date: str | None,
        current_live_timestamp_ms: int | None,
    ) -> bool:
        if not session_date or not current_session_date or timestamp_ms is None:
            return False
        if session_date != current_session_date:
            return True
        if current_live_timestamp_ms is None:
            return False
        return int(timestamp_ms) < int(current_live_timestamp_ms)

    def merge_frozen_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        request_signature: str,
        model_version: int,
        current_session_date: str | None,
        current_live_timestamp_ms: int | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not rows or not request_signature or not current_session_date:
            return rows, {
                "frozen_row_count": 0,
                "frozen_sessions": [],
                "current_session_date": current_session_date,
                "current_live_timestamp_ms": current_live_timestamp_ms,
                "frozen_current_session_row_count": 0,
            }

        sessions = sorted(
            {
                _session_date(row.get("session_date"))
                for row in rows
                if isinstance(row, dict)
                and _session_date(row.get("session_date"))
                and self._is_final_row(
                    session_date=_session_date(row.get("session_date")),
                    timestamp_ms=_safe_int(row.get("timestamp_ms")),
                    current_session_date=current_session_date,
                    current_live_timestamp_ms=current_live_timestamp_ms,
                )
            }
        )
        if not sessions:
            return rows, {
                "frozen_row_count": 0,
                "frozen_sessions": [],
                "current_session_date": current_session_date,
                "current_live_timestamp_ms": current_live_timestamp_ms,
                "frozen_current_session_row_count": 0,
            }

        self._ensure_schema()
        placeholders = ",".join("?" for _ in sessions)
        query = f"""
            SELECT session_date, timestamp_ms, row_json
              FROM fair_value_markov_rows
             WHERE request_signature = ?
               AND model_version = ?
               AND is_final = 1
               AND session_date IN ({placeholders})
        """
        frozen_rows: dict[tuple[str, int], dict[str, Any]] = {}
        with self._lock:
            try:
                with self._connect() as conn:
                    for record in conn.execute(query, [request_signature, model_version, *sessions]):
                        try:
                            row = json.loads(str(record["row_json"]))
                        except Exception:
                            continue
                        if isinstance(row, dict):
                            frozen_rows[(str(record["session_date"]), int(record["timestamp_ms"]))] = row
            except Exception:
                logger.exception("Failed to read frozen fair-value Markov rows")
                return rows, {
                    "frozen_row_count": 0,
                    "frozen_sessions": [],
                    "current_session_date": current_session_date,
                    "current_live_timestamp_ms": current_live_timestamp_ms,
                    "frozen_current_session_row_count": 0,
                }

        if not frozen_rows:
            return rows, {
                "frozen_row_count": 0,
                "frozen_sessions": [],
                "current_session_date": current_session_date,
                "current_live_timestamp_ms": current_live_timestamp_ms,
                "frozen_current_session_row_count": 0,
            }

        replaced_count = 0
        replaced_current_session_count = 0
        replaced_sessions: set[str] = set()
        merged_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            session_date = _session_date(row.get("session_date"))
            timestamp_ms = _safe_int(row.get("timestamp_ms"))
            frozen = frozen_rows.get((session_date, int(timestamp_ms or 0)))
            should_freeze = self._is_final_row(
                session_date=session_date,
                timestamp_ms=timestamp_ms,
                current_session_date=current_session_date,
                current_live_timestamp_ms=current_live_timestamp_ms,
            )
            if should_freeze and frozen:
                merged_rows.append(deepcopy(frozen))
                replaced_count += 1
                if session_date == current_session_date:
                    replaced_current_session_count += 1
                replaced_sessions.add(session_date)
            else:
                merged_rows.append(row)

        return merged_rows, {
            "frozen_row_count": replaced_count,
            "frozen_sessions": sorted(replaced_sessions),
            "current_session_date": current_session_date,
            "current_live_timestamp_ms": current_live_timestamp_ms,
            "frozen_current_session_row_count": replaced_current_session_count,
        }

    def build_run_id(
        self,
        *,
        payload: dict[str, Any],
        request_signature: str,
        model_version: int,
    ) -> str:
        latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else {}
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        seed = {
            "request_signature": request_signature,
            "model_version": int(model_version),
            "source_latest_timestamp_ms": payload.get("source_latest_timestamp_ms"),
            "latest_timestamp_ms": latest.get("timestamp_ms"),
            "latest_session_date": latest.get("session_date"),
            "latest_state_key": latest.get("dominant_state_key"),
            "latest_tape_state_key": latest.get("tape_regime_key"),
            "row_count": len(rows),
        }
        return hashlib.sha1(_json_dumps(seed).encode("utf-8")).hexdigest()[:20]

    def build_metrics(
        self,
        *,
        payload: dict[str, Any],
        current_session_date: str | None,
        merge_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rows = [
            row for row in (payload.get("rows") or [])
            if isinstance(row, dict)
        ]
        sessions = sorted(
            {
                _session_date(row.get("session_date"))
                for row in rows
                if _session_date(row.get("session_date"))
            }
        )
        latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else (rows[-1] if rows else {})
        risk_latest = latest.get("risk_thermometer") if isinstance(latest.get("risk_thermometer"), dict) else {}
        meta_latest = payload.get("meta_regime") if isinstance(payload.get("meta_regime"), dict) else {}
        meta_latest_row = meta_latest.get("latest") if isinstance(meta_latest.get("latest"), dict) else {}
        state_counts: dict[str, int] = {}
        tape_counts: dict[str, int] = {}
        meta_counts: dict[str, int] = {}
        risk_scores: list[float] = []
        outliers: list[float] = []
        dislocations: list[float] = []
        residual_z_values: list[float] = []
        for row in rows:
            state_key = str(row.get("dominant_state_key") or "").strip()
            if state_key:
                state_counts[state_key] = state_counts.get(state_key, 0) + 1
            tape_key = str(row.get("tape_regime_key") or "").strip()
            if tape_key:
                tape_counts[tape_key] = tape_counts.get(tape_key, 0) + 1
            meta_key = str(row.get("meta_regime_key") or "").strip()
            if meta_key:
                meta_counts[meta_key] = meta_counts.get(meta_key, 0) + 1
            risk_score = _safe_float(
                (row.get("risk_thermometer") or {}).get("score")
                if isinstance(row.get("risk_thermometer"), dict)
                else None
            )
            if risk_score is not None:
                risk_scores.append(risk_score)
            outlier = _safe_float(row.get("outlier_score"))
            if outlier is not None:
                outliers.append(outlier)
            dislocation = _safe_float(row.get("dislocation_score"))
            if dislocation is not None:
                dislocations.append(dislocation)
            residual_z = _safe_float(row.get("residual_z"))
            if residual_z is not None:
                residual_z_values.append(residual_z)

        transition_diagonal: list[float] = []
        transition_matrix = payload.get("transition_matrix")
        if isinstance(transition_matrix, list):
            for index, row in enumerate(transition_matrix):
                if isinstance(row, list) and index < len(row):
                    value = _safe_float(row[index])
                    if value is not None:
                        transition_diagonal.append(value)

        closed_sessions = [
            session
            for session in sessions
            if current_session_date and session != current_session_date
        ]
        merge_metadata = merge_metadata or {}
        current_live_timestamp_ms = _safe_int(merge_metadata.get("current_live_timestamp_ms"))
        current_session_closed_candles = 0
        current_session_live_candles = 0
        if current_session_date and current_live_timestamp_ms is not None:
            for row in rows:
                session_date = _session_date(row.get("session_date"))
                timestamp_ms = _safe_int(row.get("timestamp_ms"))
                if session_date != current_session_date or timestamp_ms is None:
                    continue
                if timestamp_ms < current_live_timestamp_ms:
                    current_session_closed_candles += 1
                elif timestamp_ms == current_live_timestamp_ms:
                    current_session_live_candles += 1
        metrics = {
            "row_count": len(rows),
            "session_count": len(sessions),
            "session_dates": sessions,
            "current_session_date": current_session_date,
            "current_live_timestamp_ms": current_live_timestamp_ms,
            "current_session_closed_candle_count": current_session_closed_candles,
            "current_session_live_candle_count": current_session_live_candles,
            "closed_session_count": len(closed_sessions),
            "closed_sessions": closed_sessions,
            "frozen_row_count": int(merge_metadata.get("frozen_row_count") or 0),
            "frozen_current_session_row_count": int(
                merge_metadata.get("frozen_current_session_row_count") or 0
            ),
            "frozen_sessions": list(merge_metadata.get("frozen_sessions") or []),
            "latest": {
                "timestamp_ms": _safe_int(latest.get("timestamp_ms")) if latest else None,
                "session_date": _session_date(latest.get("session_date")) if latest else None,
                "state_key": latest.get("dominant_state_key") if latest else None,
                "tape_state_key": latest.get("tape_regime_key") if latest else None,
                "meta_regime_key": latest.get("meta_regime_key") if latest else None,
                "risk_label": risk_latest.get("label") if risk_latest else None,
                "risk_score": _round_float(risk_latest.get("score") if risk_latest else None, 4),
            },
            "state_counts": state_counts,
            "tape_state_counts": tape_counts,
            "meta_regime_counts": meta_counts,
            "risk_score": {
                "mean": _round_float(sum(risk_scores) / len(risk_scores), 4) if risk_scores else None,
                "median": _round_float(_median(risk_scores), 4),
                "min": _round_float(min(risk_scores), 4) if risk_scores else None,
                "max": _round_float(max(risk_scores), 4) if risk_scores else None,
                "latest": _round_float(risk_latest.get("score") if risk_latest else None, 4),
            },
            "outlier_score": {
                "mean": _round_float(sum(outliers) / len(outliers), 4) if outliers else None,
                "median": _round_float(_median(outliers), 4),
                "p95": _round_float(_percentile(outliers, 95), 4),
                "max": _round_float(max(outliers), 4) if outliers else None,
            },
            "dislocation_score": {
                "mean": _round_float(sum(dislocations) / len(dislocations), 4) if dislocations else None,
                "median": _round_float(_median(dislocations), 4),
                "p95": _round_float(_percentile(dislocations, 95), 4),
                "max": _round_float(max(dislocations), 4) if dislocations else None,
            },
            "residual_z": {
                "mean_abs": (
                    _round_float(
                        sum(abs(value) for value in residual_z_values) / len(residual_z_values),
                        4,
                    )
                    if residual_z_values
                    else None
                ),
                "max_abs": (
                    _round_float(max(abs(value) for value in residual_z_values), 4)
                    if residual_z_values
                    else None
                ),
            },
            "transition": {
                "diagonal_mean": (
                    _round_float(sum(transition_diagonal) / len(transition_diagonal), 6)
                    if transition_diagonal
                    else None
                ),
                "diagonal_min": _round_float(min(transition_diagonal), 6) if transition_diagonal else None,
            },
            "risk_components_latest": (
                deepcopy(risk_latest.get("components"))
                if isinstance(risk_latest.get("components"), dict)
                else {}
            ),
            "meta_regime_latest": deepcopy(meta_latest_row),
        }
        return metrics

    def persist_payload(
        self,
        *,
        payload: dict[str, Any],
        request_signature: str,
        model_version: int,
        current_session_date: str | None,
        current_live_timestamp_ms: int | None,
        run_id: str,
        metrics: dict[str, Any],
        merge_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rows = [
            row for row in (payload.get("rows") or [])
            if isinstance(row, dict)
        ]
        latest = payload.get("latest") if isinstance(payload.get("latest"), dict) else (rows[-1] if rows else {})
        risk_latest = latest.get("risk_thermometer") if isinstance(latest.get("risk_thermometer"), dict) else {}
        now = _utc_now_iso()
        payload_json = _json_dumps(payload)
        payload_digest = hashlib.sha1(payload_json.encode("utf-8")).hexdigest()
        merge_metadata = merge_metadata or {}
        final_count = 0
        live_count = 0

        self._ensure_schema()
        with self._lock:
            try:
                with self._connect() as conn:
                    conn.execute(
                        """
                        INSERT INTO fair_value_markov_runs (
                            run_id,
                            request_signature,
                            model_version,
                            generated_at,
                            created_at,
                            updated_at,
                            current_session_date,
                            source_latest_timestamp_ms,
                            source_latest_session_date,
                            requested_sessions,
                            bar_minutes,
                            row_count,
                            session_count,
                            frozen_row_count,
                            frozen_session_count,
                            latest_timestamp_ms,
                            latest_session_date,
                            latest_state_key,
                            latest_tape_state_key,
                            latest_risk_label,
                            latest_risk_score,
                            metrics_json,
                            payload_digest,
                            payload_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(run_id) DO UPDATE SET
                            updated_at = excluded.updated_at,
                            generated_at = excluded.generated_at,
                            current_session_date = excluded.current_session_date,
                            source_latest_timestamp_ms = excluded.source_latest_timestamp_ms,
                            source_latest_session_date = excluded.source_latest_session_date,
                            requested_sessions = excluded.requested_sessions,
                            bar_minutes = excluded.bar_minutes,
                            row_count = excluded.row_count,
                            session_count = excluded.session_count,
                            frozen_row_count = excluded.frozen_row_count,
                            frozen_session_count = excluded.frozen_session_count,
                            latest_timestamp_ms = excluded.latest_timestamp_ms,
                            latest_session_date = excluded.latest_session_date,
                            latest_state_key = excluded.latest_state_key,
                            latest_tape_state_key = excluded.latest_tape_state_key,
                            latest_risk_label = excluded.latest_risk_label,
                            latest_risk_score = excluded.latest_risk_score,
                            metrics_json = excluded.metrics_json,
                            payload_digest = excluded.payload_digest,
                            payload_json = excluded.payload_json
                        """,
                        (
                            run_id,
                            request_signature,
                            int(model_version),
                            payload.get("generated_at"),
                            now,
                            now,
                            current_session_date,
                            _safe_int(payload.get("source_latest_timestamp_ms")),
                            current_session_date,
                            _safe_int(payload.get("requested_sessions")),
                            _safe_int(payload.get("bar_minutes")),
                            len(rows),
                            len(metrics.get("session_dates") or []),
                            int(merge_metadata.get("frozen_row_count") or 0),
                            len(merge_metadata.get("frozen_sessions") or []),
                            _safe_int(latest.get("timestamp_ms")) if latest else None,
                            _session_date(latest.get("session_date")) if latest else None,
                            latest.get("dominant_state_key") if latest else None,
                            latest.get("tape_regime_key") if latest else None,
                            risk_latest.get("label") if risk_latest else None,
                            _safe_float(risk_latest.get("score") if risk_latest else None),
                            _json_dumps(metrics),
                            payload_digest,
                            payload_json,
                        ),
                    )

                    for row in rows:
                        session_date = _session_date(row.get("session_date"))
                        timestamp_ms = _safe_int(row.get("timestamp_ms"))
                        if not session_date or timestamp_ms is None:
                            continue
                        is_final = 1 if self._is_final_row(
                            session_date=session_date,
                            timestamp_ms=timestamp_ms,
                            current_session_date=current_session_date,
                            current_live_timestamp_ms=current_live_timestamp_ms,
                        ) else 0
                        final_count += int(is_final == 1)
                        live_count += int(is_final == 0)
                        row_risk = (
                            row.get("risk_thermometer")
                            if isinstance(row.get("risk_thermometer"), dict)
                            else {}
                        )
                        conn.execute(
                            """
                            INSERT INTO fair_value_markov_rows (
                                request_signature,
                                model_version,
                                session_date,
                                timestamp_ms,
                                run_id,
                                is_final,
                                dominant_state_key,
                                tape_regime_key,
                                risk_label,
                                risk_score,
                                outlier_score,
                                dislocation_score,
                                row_json,
                                created_at,
                                updated_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(
                                request_signature,
                                model_version,
                                session_date,
                                timestamp_ms
                            ) DO UPDATE SET
                                run_id = CASE
                                    WHEN fair_value_markov_rows.is_final = 1
                                    THEN fair_value_markov_rows.run_id
                                    ELSE excluded.run_id
                                END,
                                is_final = CASE
                                    WHEN fair_value_markov_rows.is_final = 1
                                    THEN 1
                                    ELSE excluded.is_final
                                END,
                                dominant_state_key = CASE
                                    WHEN fair_value_markov_rows.is_final = 1
                                    THEN fair_value_markov_rows.dominant_state_key
                                    ELSE excluded.dominant_state_key
                                END,
                                tape_regime_key = CASE
                                    WHEN fair_value_markov_rows.is_final = 1
                                    THEN fair_value_markov_rows.tape_regime_key
                                    ELSE excluded.tape_regime_key
                                END,
                                risk_label = CASE
                                    WHEN fair_value_markov_rows.is_final = 1
                                    THEN fair_value_markov_rows.risk_label
                                    ELSE excluded.risk_label
                                END,
                                risk_score = CASE
                                    WHEN fair_value_markov_rows.is_final = 1
                                    THEN fair_value_markov_rows.risk_score
                                    ELSE excluded.risk_score
                                END,
                                outlier_score = CASE
                                    WHEN fair_value_markov_rows.is_final = 1
                                    THEN fair_value_markov_rows.outlier_score
                                    ELSE excluded.outlier_score
                                END,
                                dislocation_score = CASE
                                    WHEN fair_value_markov_rows.is_final = 1
                                    THEN fair_value_markov_rows.dislocation_score
                                    ELSE excluded.dislocation_score
                                END,
                                row_json = CASE
                                    WHEN fair_value_markov_rows.is_final = 1
                                    THEN fair_value_markov_rows.row_json
                                    ELSE excluded.row_json
                                END,
                                updated_at = excluded.updated_at
                            """,
                            (
                                request_signature,
                                int(model_version),
                                session_date,
                                int(timestamp_ms),
                                run_id,
                                is_final,
                                row.get("dominant_state_key"),
                                row.get("tape_regime_key"),
                                row_risk.get("label"),
                                _safe_float(row_risk.get("score")),
                                _safe_float(row.get("outlier_score")),
                                _safe_float(row.get("dislocation_score")),
                                _json_dumps(row),
                                now,
                                now,
                            ),
                        )

                    conn.execute(
                        "DELETE FROM fair_value_markov_metrics WHERE run_id = ?",
                        (run_id,),
                    )
                    for key, value in self._flatten_metrics(metrics).items():
                        metric_value = _safe_float(value)
                        metric_text = None
                        metric_json = None
                        if metric_value is None:
                            if isinstance(value, (dict, list)):
                                metric_json = _json_dumps(value)
                            elif value is not None:
                                metric_text = str(value)
                        conn.execute(
                            """
                            INSERT INTO fair_value_markov_metrics (
                                run_id,
                                metric_key,
                                metric_value,
                                metric_text,
                                metric_json,
                                created_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                run_id,
                                key,
                                metric_value,
                                metric_text,
                                metric_json,
                                now,
                            ),
                        )
            except Exception:
                logger.exception("Failed to persist fair-value Markov regime run")
                return {
                    "enabled": True,
                    "ok": False,
                    "run_id": run_id,
                    "db_path": self.db_path,
                    "error": "failed_to_persist_markov_regime",
                    "current_session_date": current_session_date,
                    "current_live_timestamp_ms": current_live_timestamp_ms,
                    "metrics": metrics,
                }

        return {
            "enabled": True,
            "ok": True,
            "run_id": run_id,
            "db_path": self.db_path,
            "current_session_date": current_session_date,
            "current_live_timestamp_ms": current_live_timestamp_ms,
            "stored_row_count": len(rows),
            "final_row_count": final_count,
            "live_row_count": live_count,
            "frozen_row_count": int(merge_metadata.get("frozen_row_count") or 0),
            "frozen_current_session_row_count": int(
                merge_metadata.get("frozen_current_session_row_count") or 0
            ),
            "frozen_sessions": list(merge_metadata.get("frozen_sessions") or []),
            "payload_digest": payload_digest,
            "metrics": metrics,
        }

    @staticmethod
    def _flatten_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
        output: dict[str, Any] = {}

        def walk(prefix: str, value: Any) -> None:
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    walk(f"{prefix}.{child_key}" if prefix else str(child_key), child_value)
                return
            if isinstance(value, list):
                output[prefix] = value
                return
            output[prefix] = value

        walk("", metrics)
        return output
