from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_macro_data_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "macro"))


class FlowReplicatorStore:
    def __init__(self, data_dir: str | None = None, db_path: str | None = None) -> None:
        resolved_data_dir = data_dir or os.environ.get("FLOW_REPLICATOR_DATA_DIR")
        if not resolved_data_dir:
            resolved_data_dir = os.path.join(_default_macro_data_dir(), "flow_replicator")
        self.data_dir = os.path.abspath(resolved_data_dir)
        self.db_path = os.path.abspath(db_path or os.path.join(self.data_dir, "flow_replicator.sqlite3"))
        self._lock = threading.RLock()
        self._initialized = False
        self.broker_codes = self._load_broker_codes()

    def _load_broker_codes(self) -> dict[str, str]:
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "b3_broker_codes.json"))
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            return {str(key).strip(): str(value).strip() for key, value in payload.items()}
        except Exception:
            return {}

    def _connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=FILE")
        conn.execute("PRAGMA cache_size=-4096")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def resolve_broker_name(self, agent_code: Any, broker_name: Any) -> str | None:
        resolved_code = str(agent_code or "").strip()
        resolved_name = str(broker_name or "").strip()
        if resolved_name:
            return resolved_name
        if not resolved_code:
            return None
        return self.broker_codes.get(resolved_code)

    def ensure_schema(self) -> None:
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS flow_raw_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        contract TEXT NOT NULL,
                        received_at TEXT NOT NULL,
                        received_at_epoch REAL NOT NULL,
                        kind TEXT,
                        payload_hash TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        inserted_at TEXT NOT NULL,
                        UNIQUE(ticker, received_at_epoch, payload_hash)
                    );

                    CREATE INDEX IF NOT EXISTS idx_flow_raw_ticker_time
                        ON flow_raw_messages(ticker, received_at_epoch);

                    CREATE TABLE IF NOT EXISTS flow_summary_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        contract TEXT NOT NULL,
                        received_at TEXT NOT NULL,
                        received_at_epoch REAL NOT NULL,
                        kind TEXT,
                        vwap REAL,
                        rlp_vwap REAL,
                        agent_count INTEGER NOT NULL DEFAULT 0,
                        payload_hash TEXT NOT NULL,
                        inserted_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_flow_snapshots_ticker_time
                        ON flow_summary_snapshots(ticker, received_at_epoch);

                    CREATE INDEX IF NOT EXISTS idx_flow_snapshots_time
                        ON flow_summary_snapshots(received_at_epoch);

                    CREATE TABLE IF NOT EXISTS flow_summary_agents (
                        snapshot_id INTEGER NOT NULL,
                        ticker TEXT NOT NULL,
                        contract TEXT NOT NULL,
                        received_at TEXT NOT NULL,
                        received_at_epoch REAL NOT NULL,
                        agent_code TEXT NOT NULL,
                        broker_name TEXT,
                        qty REAL,
                        buy_quantity REAL,
                        sell_quantity REAL,
                        buy_agression REAL,
                        sell_agression REAL,
                        agression_balance REAL,
                        maker_balance REAL,
                        buy_rlp REAL,
                        sell_rlp REAL,
                        rlp_balance REAL,
                        vwap REAL,
                        rlp_vwap REAL,
                        inserted_at TEXT NOT NULL,
                        PRIMARY KEY(snapshot_id, agent_code)
                    );

                    CREATE INDEX IF NOT EXISTS idx_flow_agents_ticker_agent_time
                        ON flow_summary_agents(ticker, agent_code, received_at_epoch);

                    CREATE TABLE IF NOT EXISTS flow_agent_deltas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticker TEXT NOT NULL,
                        contract TEXT NOT NULL,
                        received_at TEXT NOT NULL,
                        received_at_epoch REAL NOT NULL,
                        agent_code TEXT NOT NULL,
                        broker_name TEXT,
                        snapshot_id INTEGER NOT NULL,
                        previous_snapshot_id INTEGER,
                        delta_qty REAL,
                        delta_buy_quantity REAL,
                        delta_sell_quantity REAL,
                        delta_buy_agression REAL,
                        delta_sell_agression REAL,
                        delta_agression_balance REAL,
                        delta_maker_balance REAL,
                        delta_buy_rlp REAL,
                        delta_sell_rlp REAL,
                        delta_rlp_balance REAL,
                        inserted_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_flow_deltas_ticker_time
                        ON flow_agent_deltas(ticker, received_at_epoch);

                    CREATE INDEX IF NOT EXISTS idx_flow_deltas_time
                        ON flow_agent_deltas(received_at_epoch);

                    CREATE INDEX IF NOT EXISTS idx_flow_deltas_ticker_agent_time
                        ON flow_agent_deltas(ticker, agent_code, received_at_epoch);
                    """
                )
            self._initialized = True

    @staticmethod
    def _payload_hash(raw_payload: str) -> str:
        return hashlib.sha256(raw_payload.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _epoch_from_iso(value: str) -> float:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return float(parsed.astimezone(timezone.utc).timestamp())

    @staticmethod
    def _agent_numeric(row: dict[str, Any], key: str) -> float | None:
        return _safe_float(row.get(key))

    @staticmethod
    def _weighted_summary_vwap(
        summary: list[dict[str, Any]],
        *,
        value_key: str,
        weight_keys: tuple[str, ...],
    ) -> float | None:
        weighted_sum = 0.0
        weight_sum = 0.0
        fallback = None
        for row in summary or []:
            value = _safe_float(row.get(value_key))
            if value is None or value <= 0:
                continue
            if fallback is None:
                fallback = value
            weight = 0.0
            for key in weight_keys:
                parsed = _safe_float(row.get(key))
                if parsed is not None and parsed > 0:
                    weight += parsed
            if weight <= 0:
                continue
            weighted_sum += value * weight
            weight_sum += weight
        if weight_sum > 0:
            return weighted_sum / weight_sum
        return fallback

    def _previous_agent_row(
        self,
        conn: sqlite3.Connection,
        *,
        ticker: str,
        agent_code: str,
        before_epoch: float,
    ) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT *
            FROM flow_summary_agents
            WHERE ticker = ?
              AND agent_code = ?
              AND received_at_epoch < ?
            ORDER BY received_at_epoch DESC
            LIMIT 1
            """,
            (ticker, agent_code, before_epoch),
        ).fetchone()

    def persist_summary_message(
        self,
        *,
        ticker: str,
        contract: str,
        received_at: str,
        payload: dict[str, Any],
        raw_payload: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_schema()
        normalized_ticker = str(ticker or payload.get("data", {}).get("ticker") or "").strip()
        normalized_contract = str(contract or normalized_ticker).strip()
        kind = str(payload.get("kind") or "").strip()
        summary = payload.get("data", {}).get("summary") or []
        if not isinstance(summary, list):
            summary = []

        raw = raw_payload if raw_payload is not None else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        payload_hash = self._payload_hash(raw)
        received_epoch = self._epoch_from_iso(received_at)
        inserted_at = _utc_now_iso()
        snapshot_vwap = self._weighted_summary_vwap(
            summary,
            value_key="vwap",
            weight_keys=("buy_quantity", "sell_quantity"),
        )
        snapshot_rlp_vwap = self._weighted_summary_vwap(
            summary,
            value_key="rlp_vwap",
            weight_keys=("buy_rlp", "sell_rlp"),
        )

        numeric_keys = [
            "qty",
            "buy_quantity",
            "sell_quantity",
            "buy_agression",
            "sell_agression",
            "agression_balance",
            "maker_balance",
            "buy_rlp",
            "sell_rlp",
            "rlp_balance",
            "vwap",
            "rlp_vwap",
        ]
        delta_keys = [
            "qty",
            "buy_quantity",
            "sell_quantity",
            "buy_agression",
            "sell_agression",
            "agression_balance",
            "maker_balance",
            "buy_rlp",
            "sell_rlp",
            "rlp_balance",
        ]
        cumulative_delta_keys = {
            "buy_quantity",
            "sell_quantity",
            "buy_agression",
            "sell_agression",
            "buy_rlp",
            "sell_rlp",
        }

        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN")
                conn.execute(
                    """
                    INSERT OR IGNORE INTO flow_raw_messages (
                        ticker, contract, received_at, received_at_epoch, kind,
                        payload_hash, payload_json, inserted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_ticker,
                        normalized_contract,
                        received_at,
                        received_epoch,
                        kind,
                        payload_hash,
                        raw,
                        inserted_at,
                    ),
                )
                cursor = conn.execute(
                    """
                    INSERT INTO flow_summary_snapshots (
                        ticker, contract, received_at, received_at_epoch, kind,
                        vwap, rlp_vwap, agent_count, payload_hash, inserted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_ticker,
                        normalized_contract,
                        received_at,
                        received_epoch,
                        kind,
                        snapshot_vwap,
                        snapshot_rlp_vwap,
                        len(summary),
                        payload_hash,
                        inserted_at,
                    ),
                )
                snapshot_id = int(cursor.lastrowid)

                agent_records: list[tuple[Any, ...]] = []
                delta_records: list[tuple[Any, ...]] = []
                for item in summary:
                    if not isinstance(item, dict):
                        continue
                    agent_code = str(item.get("agent") or "").strip()
                    if not agent_code:
                        continue
                    broker_name = self.broker_codes.get(agent_code)
                    values = {key: self._agent_numeric(item, key) for key in numeric_keys}
                    agent_records.append((
                        snapshot_id,
                        normalized_ticker,
                        normalized_contract,
                        received_at,
                        received_epoch,
                        agent_code,
                        broker_name,
                        *(values.get(key) for key in numeric_keys),
                        inserted_at,
                    ))

                    previous = self._previous_agent_row(
                        conn,
                        ticker=normalized_ticker,
                        agent_code=agent_code,
                        before_epoch=received_epoch,
                    )
                    if previous is None:
                        continue
                    previous_received_at = str(previous["received_at"] or "")
                    if previous_received_at[:10] != received_at[:10]:
                        continue
                    counters_reset = False
                    for key in cumulative_delta_keys:
                        current_value = values.get(key)
                        previous_value = _safe_float(previous[key])
                        if current_value is not None and previous_value is not None and current_value < previous_value:
                            counters_reset = True
                            break
                    if counters_reset:
                        continue
                    deltas: list[float | None] = []
                    has_delta = False
                    for key in delta_keys:
                        current_value = values.get(key)
                        previous_value = _safe_float(previous[key])
                        delta_value = (
                            current_value - previous_value
                            if current_value is not None and previous_value is not None
                            else None
                        )
                        if delta_value is not None and abs(delta_value) > 1e-12:
                            has_delta = True
                        deltas.append(delta_value)
                    if not has_delta:
                        continue
                    delta_records.append((
                        normalized_ticker,
                        normalized_contract,
                        received_at,
                        received_epoch,
                        agent_code,
                        broker_name,
                        snapshot_id,
                        int(previous["snapshot_id"]),
                        *deltas,
                        inserted_at,
                    ))

                if agent_records:
                    conn.executemany(
                        """
                        INSERT INTO flow_summary_agents (
                            snapshot_id, ticker, contract, received_at, received_at_epoch,
                            agent_code, broker_name,
                            qty, buy_quantity, sell_quantity, buy_agression,
                            sell_agression, agression_balance, maker_balance,
                            buy_rlp, sell_rlp, rlp_balance, vwap, rlp_vwap, inserted_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        agent_records,
                    )
                if delta_records:
                    conn.executemany(
                        """
                        INSERT INTO flow_agent_deltas (
                            ticker, contract, received_at, received_at_epoch,
                            agent_code, broker_name, snapshot_id, previous_snapshot_id,
                            delta_qty, delta_buy_quantity, delta_sell_quantity,
                            delta_buy_agression, delta_sell_agression,
                            delta_agression_balance, delta_maker_balance,
                            delta_buy_rlp, delta_sell_rlp, delta_rlp_balance, inserted_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        delta_records,
                    )
                conn.commit()

        return {
            "snapshot_id": snapshot_id,
            "ticker": normalized_ticker,
            "received_at": received_at,
            "agent_count": len(agent_records),
            "delta_count": len(delta_records),
            "payload_hash": payload_hash,
        }

    def latest_snapshot(self, ticker: str | None = None) -> dict[str, Any] | None:
        self.ensure_schema()
        clauses: list[str] = []
        params: list[Any] = []
        if ticker:
            clauses.append("ticker = ?")
            params.append(str(ticker).strip())
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            row = conn.execute(
                f"""
                SELECT *
                FROM flow_summary_snapshots
                {where}
                ORDER BY received_at_epoch DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return dict(row) if row else None

    def latest_agents(self, ticker: str | None = None, limit: int = 80) -> list[dict[str, Any]]:
        snapshot = self.latest_snapshot(ticker)
        if not snapshot:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM flow_summary_agents
                WHERE snapshot_id = ?
                ORDER BY ABS(COALESCE(qty, 0)) DESC
                LIMIT ?
                """,
                (snapshot["id"], max(int(limit or 80), 1)),
            ).fetchall()
        resolved_rows: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["broker_name"] = self.resolve_broker_name(item.get("agent_code"), item.get("broker_name"))
            resolved_rows.append(item)
        return resolved_rows

    def aggregate_deltas(
        self,
        *,
        ticker: str | None = None,
        since_epoch: float | None = None,
        until_epoch: float | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        self.ensure_schema()
        clauses: list[str] = []
        params: list[Any] = []
        if ticker:
            clauses.append("ticker = ?")
            params.append(str(ticker).strip())
        if since_epoch is not None:
            clauses.append("received_at_epoch >= ?")
            params.append(float(since_epoch))
        if until_epoch is not None:
            clauses.append("received_at_epoch <= ?")
            params.append(float(until_epoch))
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    agent_code,
                    broker_name,
                    SUM(COALESCE(delta_qty, 0)) AS delta_qty,
                    SUM(COALESCE(delta_buy_quantity, 0)) AS delta_buy_quantity,
                    SUM(COALESCE(delta_sell_quantity, 0)) AS delta_sell_quantity,
                    SUM(COALESCE(delta_buy_agression, 0)) AS delta_buy_agression,
                    SUM(COALESCE(delta_sell_agression, 0)) AS delta_sell_agression,
                    SUM(COALESCE(delta_agression_balance, 0)) AS delta_agression_balance,
                    SUM(COALESCE(delta_maker_balance, 0)) AS delta_maker_balance,
                    SUM(COALESCE(delta_buy_rlp, 0)) AS delta_buy_rlp,
                    SUM(COALESCE(delta_sell_rlp, 0)) AS delta_sell_rlp,
                    SUM(COALESCE(delta_rlp_balance, 0)) AS delta_rlp_balance,
                    COUNT(*) AS sample_count
                FROM flow_agent_deltas
                {where}
                GROUP BY agent_code, broker_name
                ORDER BY ABS(SUM(COALESCE(delta_agression_balance, 0))) DESC
                LIMIT ?
                """,
                (*params, max(int(limit or 80), 1)),
            ).fetchall()
            totals = conn.execute(
                f"""
                SELECT
                    SUM(COALESCE(delta_qty, 0)) AS delta_qty,
                    SUM(COALESCE(delta_buy_quantity, 0)) AS delta_buy_quantity,
                    SUM(COALESCE(delta_sell_quantity, 0)) AS delta_sell_quantity,
                    SUM(COALESCE(delta_buy_agression, 0)) AS delta_buy_agression,
                    SUM(COALESCE(delta_sell_agression, 0)) AS delta_sell_agression,
                    SUM(COALESCE(delta_agression_balance, 0)) AS delta_agression_balance,
                    SUM(COALESCE(delta_maker_balance, 0)) AS delta_maker_balance,
                    SUM(COALESCE(delta_buy_rlp, 0)) AS delta_buy_rlp,
                    SUM(COALESCE(delta_sell_rlp, 0)) AS delta_sell_rlp,
                    SUM(COALESCE(delta_rlp_balance, 0)) AS delta_rlp_balance,
                    COUNT(*) AS sample_count
                FROM flow_agent_deltas
                {where}
                """,
                params,
            ).fetchone()
        return {
            "totals": dict(totals) if totals else {},
            "agents": [
                {
                    **dict(row),
                    "broker_name": self.resolve_broker_name(row["agent_code"], row["broker_name"]),
                }
                for row in rows
            ],
        }

    def aggregate_delta_windows(
        self,
        *,
        ticker: str | None,
        windows: list[dict[str, Any]],
        agent_limit: int = 12,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        normalized_ticker = str(ticker or "").strip() or None
        resolved_agent_limit = 12 if agent_limit is None else max(int(agent_limit), 0)
        prepared_windows: list[dict[str, Any]] = []
        for position, window in enumerate(windows or []):
            if not isinstance(window, dict):
                continue
            start_epoch = _safe_float(window.get("start_epoch"))
            end_epoch = _safe_float(window.get("end_epoch"))
            if start_epoch is None or end_epoch is None or end_epoch <= start_epoch:
                continue
            prepared_windows.append({
                "position": len(prepared_windows),
                "index": window.get("index", position),
                "start_epoch": start_epoch,
                "end_epoch": end_epoch,
                "snapshot_day": datetime.fromtimestamp(end_epoch, timezone.utc).date().isoformat(),
            })

        output: list[dict[str, Any]] = [
            {
                "index": item["index"],
                "start_epoch": item["start_epoch"],
                "end_epoch": item["end_epoch"],
                "totals": {},
                "snapshot": None,
                "agents": [],
            }
            for item in prepared_windows
        ]
        if not prepared_windows:
            return output

        delta_join = (
            "d.received_at_epoch >= w.start_epoch AND d.received_at_epoch <= w.end_epoch"
        )
        snapshot_lookup_where = (
            "candidate.received_at_epoch <= w.end_epoch "
            "AND substr(candidate.received_at, 1, 10) = w.snapshot_day"
        )
        if normalized_ticker:
            delta_join = f"d.ticker = ? AND {delta_join}"
            snapshot_lookup_where = f"candidate.ticker = ? AND {snapshot_lookup_where}"

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TEMP TABLE IF NOT EXISTS temp_flow_windows (
                    position INTEGER PRIMARY KEY,
                    window_index,
                    start_epoch REAL NOT NULL,
                    end_epoch REAL NOT NULL,
                    snapshot_day TEXT NOT NULL
                )
                """
            )
            conn.execute("DELETE FROM temp_flow_windows")
            conn.executemany(
                """
                INSERT INTO temp_flow_windows (
                    position, window_index, start_epoch, end_epoch, snapshot_day
                ) VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["position"],
                        item["index"],
                        item["start_epoch"],
                        item["end_epoch"],
                        item["snapshot_day"],
                    )
                    for item in prepared_windows
                ],
            )

            total_params = [normalized_ticker] if normalized_ticker else []
            total_rows = conn.execute(
                f"""
                SELECT
                    w.position,
                    COALESCE(SUM(COALESCE(d.delta_qty, 0)), 0) AS delta_qty,
                    COALESCE(SUM(COALESCE(d.delta_buy_quantity, 0)), 0) AS delta_buy_quantity,
                    COALESCE(SUM(COALESCE(d.delta_sell_quantity, 0)), 0) AS delta_sell_quantity,
                    COALESCE(SUM(COALESCE(d.delta_buy_agression, 0)), 0) AS delta_buy_agression,
                    COALESCE(SUM(COALESCE(d.delta_sell_agression, 0)), 0) AS delta_sell_agression,
                    COALESCE(SUM(COALESCE(d.delta_agression_balance, 0)), 0) AS delta_agression_balance,
                    COALESCE(SUM(COALESCE(d.delta_maker_balance, 0)), 0) AS delta_maker_balance,
                    COALESCE(SUM(COALESCE(d.delta_buy_rlp, 0)), 0) AS delta_buy_rlp,
                    COALESCE(SUM(COALESCE(d.delta_sell_rlp, 0)), 0) AS delta_sell_rlp,
                    COALESCE(SUM(COALESCE(d.delta_rlp_balance, 0)), 0) AS delta_rlp_balance,
                    COUNT(d.id) AS sample_count,
                    MIN(d.received_at) AS first_received_at,
                    MAX(d.received_at) AS last_received_at
                FROM temp_flow_windows w
                LEFT JOIN flow_agent_deltas d
                  ON {delta_join}
                GROUP BY w.position
                ORDER BY w.position
                """,
                total_params,
            ).fetchall()
            for row in total_rows:
                position = int(row["position"])
                if 0 <= position < len(output):
                    data = dict(row)
                    data.pop("position", None)
                    output[position]["totals"] = data

            if resolved_agent_limit > 0:
                agent_params = [normalized_ticker] if normalized_ticker else []
                agent_params.append(resolved_agent_limit)
                agent_rows = conn.execute(
                    f"""
                    WITH agent_sums AS (
                        SELECT
                            w.position,
                            d.agent_code,
                            d.broker_name,
                            SUM(COALESCE(d.delta_qty, 0)) AS delta_qty,
                            SUM(COALESCE(d.delta_buy_quantity, 0)) AS delta_buy_quantity,
                            SUM(COALESCE(d.delta_sell_quantity, 0)) AS delta_sell_quantity,
                            SUM(COALESCE(d.delta_buy_agression, 0)) AS delta_buy_agression,
                            SUM(COALESCE(d.delta_sell_agression, 0)) AS delta_sell_agression,
                            SUM(COALESCE(d.delta_agression_balance, 0)) AS delta_agression_balance,
                            SUM(COALESCE(d.delta_maker_balance, 0)) AS delta_maker_balance,
                            SUM(COALESCE(d.delta_buy_rlp, 0)) AS delta_buy_rlp,
                            SUM(COALESCE(d.delta_sell_rlp, 0)) AS delta_sell_rlp,
                            SUM(COALESCE(d.delta_rlp_balance, 0)) AS delta_rlp_balance,
                            COUNT(*) AS sample_count
                        FROM temp_flow_windows w
                        JOIN flow_agent_deltas d
                          ON {delta_join}
                        GROUP BY w.position, d.agent_code, d.broker_name
                    ),
                    ranked_agents AS (
                        SELECT
                            *,
                            ROW_NUMBER() OVER (
                                PARTITION BY position
                                ORDER BY ABS(COALESCE(delta_agression_balance, 0)) DESC
                            ) AS rank
                        FROM agent_sums
                    )
                    SELECT *
                    FROM ranked_agents
                    WHERE rank <= ?
                    ORDER BY position, rank
                    """,
                    agent_params,
                ).fetchall()
                for row in agent_rows:
                    position = int(row["position"])
                    if 0 <= position < len(output):
                        data = dict(row)
                        data.pop("position", None)
                        data.pop("rank", None)
                        output[position]["agents"].append(data)

            snapshot_params = [normalized_ticker] if normalized_ticker else []
            snapshot_rows = conn.execute(
                f"""
                SELECT
                    w.position,
                    s.ticker,
                    s.contract,
                    s.received_at,
                    s.received_at_epoch,
                    s.vwap,
                    s.rlp_vwap
                FROM temp_flow_windows w
                JOIN flow_summary_snapshots s
                  ON s.id = (
                      SELECT candidate.id
                      FROM flow_summary_snapshots candidate
                      WHERE {snapshot_lookup_where}
                      ORDER BY candidate.received_at_epoch DESC
                      LIMIT 1
                  )
                ORDER BY position
                """,
                snapshot_params,
            ).fetchall()
            for row in snapshot_rows:
                position = int(row["position"])
                if 0 <= position < len(output):
                    data = dict(row)
                    data.pop("position", None)
                    output[position]["snapshot"] = data

        return output
