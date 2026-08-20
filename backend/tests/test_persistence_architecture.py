from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.domains.funds_flow.contracts import FundFlowCollectorState, FundFlowSnapshot
from app.domains.funds_flow.infrastructure import (
    JsonFundsFlowSnapshotRepository,
    PostgresFundsFlowCollectorStateRepository,
    PostgresFundsFlowSnapshotRepository,
)
from app.infrastructure.funds_flow_persistence import build_funds_flow_persistence


class FakeCursor:
    def __init__(self, row: tuple[Any, ...] | None = None) -> None:
        self.row = row
        self.executions: list[tuple[str, tuple[Any, ...] | None]] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, statement: str, parameters: tuple[Any, ...] | None = None) -> None:
        self.executions.append((statement, parameters))

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.row


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return self._cursor


def _snapshot() -> FundFlowSnapshot:
    return FundFlowSnapshot.model_validate(
        {
            "generated_at": "2026-08-18T12:00:00Z",
            "report": {
                "as_of_date": "2026-08-18",
                "period": "21d",
                "history_days": 95,
                "schema_version": 6,
            },
            "kpis": {
                "industry_aum": "13427107777493.16",
                "net_flow_21d": "-25795817332.80",
                "pressure_index": "-0.3211",
                "num_funds": 22936,
            },
            "source_status": [
                {
                    "id": "cvm_informe_diario",
                    "label": "CVM Informe Diario FI",
                    "status": "active",
                    "ok": True,
                    "rows": 6605540,
                }
            ],
        }
    )


def test_snapshot_contract_requires_versioned_report_and_kpis() -> None:
    with pytest.raises(ValidationError):
        FundFlowSnapshot.model_validate({"ok": True, "report": {}, "kpis": {}})

    payload = _snapshot().model_dump(mode="json")

    assert isinstance(payload["kpis"]["industry_aum"], float)
    assert payload["report"]["schema_version"] == 6
    assert payload["source_status"][0]["id"] == "cvm_informe_diario"


def test_persistence_factory_defaults_to_filesystem_and_rejects_split_configuration(
    tmp_path: Path,
) -> None:
    class FileConfig:
        PERSISTENCE_BACKEND = "filesystem"

    class MissingDatabaseConfig:
        PERSISTENCE_BACKEND = "postgresql"
        DATABASE_URL = ""

    persistence = build_funds_flow_persistence(str(tmp_path), FileConfig)

    assert isinstance(persistence.snapshots, JsonFundsFlowSnapshotRepository)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        build_funds_flow_persistence(str(tmp_path), MissingDatabaseConfig)


def test_filesystem_repository_upgrades_legacy_snapshot(tmp_path: Path) -> None:
    latest_path = tmp_path / "latest.json"
    latest_path.write_text(
        '{"report":{"last_updated_at":"2026-08-18T12:00:00Z"}}',
        encoding="utf-8",
    )

    snapshot = JsonFundsFlowSnapshotRepository(str(tmp_path)).load_latest()

    assert snapshot is not None
    assert snapshot.generated_at.isoformat() == "2026-08-18T12:00:00+00:00"
    assert snapshot.kpis.net_flow_21d is None


def test_postgres_repositories_use_parameterized_jsonb_operations() -> None:
    snapshot_cursor = FakeCursor()
    snapshot_repository = PostgresFundsFlowSnapshotRepository(
        "postgresql://test",
        connection_factory=lambda: FakeConnection(snapshot_cursor),
    )
    snapshot_repository.save_latest(_snapshot())

    statement, parameters = snapshot_cursor.executions[0]
    assert "INSERT INTO funds_flow_snapshots" in statement
    assert "%s::jsonb" in statement
    assert parameters is not None
    assert "cvm_informe_diario" in parameters[-1]

    state_cursor = FakeCursor()
    state_repository = PostgresFundsFlowCollectorStateRepository(
        "postgresql://test",
        connection_factory=lambda: FakeConnection(state_cursor),
    )
    state_repository.save(FundFlowCollectorState(desired_running=True, run_count=3))

    state_statement, state_parameters = state_cursor.executions[0]
    assert "ON CONFLICT (collector_name)" in state_statement
    assert state_parameters is not None
    assert state_parameters[0] == "funds_flow"


def test_core_migration_assigns_each_persistence_responsibility() -> None:
    migration = (
        Path(__file__).resolve().parents[1] / "migrations" / "001_persistence_core.sql"
    ).read_text(encoding="utf-8")

    for table in (
        "app_users",
        "job_executions",
        "job_results",
        "collector_states",
        "funds_flow_snapshots",
        "market_timeseries",
        "artifacts",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in migration
    assert "PARTITION BY RANGE (observed_at)" in migration
