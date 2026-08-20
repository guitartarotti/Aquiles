from pathlib import Path


def test_ci_runs_real_postgres_redis_and_neo4j_integration_services() -> None:
    workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    required_contract = (
        "integration:",
        "postgres:16-alpine",
        "redis:7-alpine",
        "neo4j:5-community",
        "AQUILES_RUN_INTEGRATION_TESTS: \"1\"",
        "tests/integration",
        "--strict-markers",
    )
    assert all(fragment in workflow for fragment in required_contract)
