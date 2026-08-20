"""PostgreSQL implementations of the Funds Flow persistence ports."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from ..contracts import FundFlowCollectorState, FundFlowSnapshot, FundFlowSnapshotSummary

ConnectionFactory = Callable[[], Any]


class _PostgresRepository:
    def __init__(
        self,
        dsn: str,
        *,
        connection_factory: ConnectionFactory | None = None,
    ) -> None:
        if not str(dsn or "").strip():
            raise ValueError("A PostgreSQL DSN is required")
        self.dsn = dsn
        self._connection_factory = connection_factory

    def _connect(self) -> Any:
        if self._connection_factory is not None:
            return self._connection_factory()
        import psycopg

        return psycopg.connect(self.dsn)


class PostgresFundsFlowSnapshotRepository(_PostgresRepository):
    def load_latest(self) -> FundFlowSnapshot | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload
                FROM funds_flow_snapshots
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = row[0]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return FundFlowSnapshot.model_validate(payload)

    def save_latest(self, payload: FundFlowSnapshot) -> None:
        report = payload.report
        serialized = json.dumps(payload.model_dump(mode="json"), ensure_ascii=False)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO funds_flow_snapshots (
                    as_of_date,
                    generated_at,
                    schema_version,
                    payload
                ) VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (generated_at)
                DO UPDATE SET
                    as_of_date = EXCLUDED.as_of_date,
                    schema_version = EXCLUDED.schema_version,
                    payload = EXCLUDED.payload
                """,
                (
                    report.as_of_date,
                    payload.generated_at,
                    report.schema_version,
                    serialized,
                ),
            )

    def append_summary(self, summary: FundFlowSnapshotSummary) -> None:
        serialized = json.dumps(summary.model_dump(mode="json"), ensure_ascii=False)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO funds_flow_snapshot_summaries (
                    generated_at,
                    as_of_date,
                    period,
                    summary
                ) VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (generated_at)
                DO UPDATE SET
                    as_of_date = EXCLUDED.as_of_date,
                    period = EXCLUDED.period,
                    summary = EXCLUDED.summary
                """,
                (
                    summary.generated_at,
                    summary.as_of_date,
                    summary.period,
                    serialized,
                ),
            )


class PostgresFundsFlowCollectorStateRepository(_PostgresRepository):
    COLLECTOR_NAME = "funds_flow"

    def load(self) -> FundFlowCollectorState:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT state FROM collector_states WHERE collector_name = %s",
                (self.COLLECTOR_NAME,),
            )
            row = cursor.fetchone()
        if row is None:
            return FundFlowCollectorState()
        state = row[0]
        if isinstance(state, str):
            state = json.loads(state)
        return FundFlowCollectorState.model_validate(state)

    def save(self, state: FundFlowCollectorState) -> None:
        serialized = json.dumps(state.model_dump(mode="json"), ensure_ascii=False)
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO collector_states (collector_name, state, updated_at)
                VALUES (%s, %s::jsonb, now())
                ON CONFLICT (collector_name)
                DO UPDATE SET state = EXCLUDED.state, updated_at = now()
                """,
                (self.COLLECTOR_NAME, serialized),
            )
