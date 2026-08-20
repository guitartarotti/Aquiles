from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from redis import Redis

from app.domains.funds_flow.contracts import FundFlowCollectorState, FundFlowSnapshot
from app.domains.funds_flow.infrastructure import (
    PostgresFundsFlowCollectorStateRepository,
    PostgresFundsFlowSnapshotRepository,
)
from app.services.cvm_cda_graph_service import CvmCdaGraphService

INTEGRATION_ENABLED = os.environ.get("AQUILES_RUN_INTEGRATION_TESTS") == "1"
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not INTEGRATION_ENABLED,
        reason="set AQUILES_RUN_INTEGRATION_TESTS=1 to use real infrastructure",
    ),
]


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(f"{name} is required by the integration test job")
    return value


def _snapshot() -> FundFlowSnapshot:
    return FundFlowSnapshot.model_validate(
        {
            "generated_at": "2026-08-20T18:00:00Z",
            "report": {
                "as_of_date": "2026-08-20",
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
                    "status": "active",
                    "ok": True,
                    "rows": 6605540,
                }
            ],
        }
    )


def test_postgresql_migration_and_funds_flow_repositories_round_trip() -> None:
    dsn = _required_environment("DATABASE_URL")
    migration = (
        Path(__file__).resolve().parents[2] / "migrations" / "001_persistence_core.sql"
    ).read_text(encoding="utf-8")
    with psycopg.connect(dsn) as connection:
        connection.execute(migration)

    snapshots = PostgresFundsFlowSnapshotRepository(dsn)
    states = PostgresFundsFlowCollectorStateRepository(dsn)
    expected_snapshot = _snapshot()
    expected_state = FundFlowCollectorState(
        desired_running=True,
        running=True,
        run_count=7,
        last_success_at="2026-08-20T18:01:00Z",
    )

    snapshots.save_latest(expected_snapshot)
    states.save(expected_state)

    loaded_snapshot = snapshots.load_latest()
    loaded_state = states.load()
    assert loaded_snapshot is not None
    assert loaded_snapshot.generated_at == expected_snapshot.generated_at
    assert loaded_snapshot.kpis.net_flow_21d == expected_snapshot.kpis.net_flow_21d
    assert loaded_state.run_count == 7
    assert loaded_state.last_success_at == expected_state.last_success_at


def test_redis_round_trip_transaction_and_expiration() -> None:
    client = Redis.from_url(_required_environment("REDIS_URL"), decode_responses=True)
    key = f"aquiles:integration:{uuid4()}"
    payload = {"service": "redis", "status": "ready"}
    try:
        assert client.ping() is True
        results = client.pipeline(transaction=True).set(
            key,
            json.dumps(payload),
        ).expire(key, 60).execute()
        assert results == [True, True]
        assert json.loads(client.get(key) or "{}") == payload
        assert 0 < client.ttl(key) <= 60
    finally:
        client.delete(key)
        client.close()


def test_neo4j_graph_round_trip_uses_project_driver(tmp_path: Path) -> None:
    source_id = f"source-{uuid4()}"
    target_id = f"target-{uuid4()}"
    service = CvmCdaGraphService(
        cda_data_dir=tmp_path,
        neo4j_uri=_required_environment("NEO4J_URI"),
        neo4j_user=_required_environment("NEO4J_USER"),
        neo4j_password=_required_environment("NEO4J_PASSWORD"),
        group_id=f"integration:{uuid4()}",
    )

    with service._driver() as driver:
        driver.verify_connectivity()
        try:
            records, _, _ = driver.execute_query(
                """
                MERGE (source:AquilesIntegration {id: $source_id})
                MERGE (target:AquilesIntegration {id: $target_id})
                MERGE (source)-[:VALIDATES]->(target)
                RETURN source.id AS source_id, target.id AS target_id
                """,
                source_id=source_id,
                target_id=target_id,
            )
            assert records[0]["source_id"] == source_id
            assert records[0]["target_id"] == target_id
        finally:
            driver.execute_query(
                "MATCH (node:AquilesIntegration) WHERE node.id IN $ids DETACH DELETE node",
                ids=[source_id, target_id],
            )
