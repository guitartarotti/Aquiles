from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.domains.funds_flow.application import (
    CollectFundsFlow,
    GetFundsFlowDashboard,
    RefreshFundsFlowSource,
)
from app.domains.funds_flow.contracts import (
    CollectFundsFlowCommand,
    FundFlowCollectorState,
    FundFlowSnapshot,
    FundFlowSnapshotSummary,
    FundsFlowDashboardQuery,
    RefreshFundsFlowSourceCommand,
)
from app.domains.funds_flow.domain.rules import period_to_window, pressure_regime, safe_divide
from app.domains.funds_flow.infrastructure import (
    JsonFundsFlowCollectorStateRepository,
    JsonFundsFlowSnapshotRepository,
)
from app.services.funds_flow_local_manager import FundsFlowLocalManager


class RecordingDashboard:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get_dashboard(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ok": True, "report": {"as_of_date": "2026-08-18"}, "kpis": {}}


class RecordingCollector:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def collect_once(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"ok": True, "report": {"completed_at": "2026-08-18T12:00:00Z"}}

    def status(self) -> dict[str, Any]:
        return {"enabled": True, "running": False, "run_count": len(self.calls)}

    def start(self) -> dict[str, Any]:
        return {"enabled": True, "running": True}

    def stop(self) -> dict[str, Any]:
        return {"enabled": True, "running": False}


class SnapshotServiceStub:
    def __init__(self, root_dir: Path, snapshot: dict[str, Any] | None = None) -> None:
        self.root_dir = str(root_dir)
        self.snapshot = snapshot

    def read_latest_snapshot(self) -> dict[str, Any] | None:
        return self.snapshot


def test_domain_rules_are_pure_and_cover_financial_boundaries() -> None:
    assert safe_divide("25", "100") == 0.25
    assert safe_divide(25, 0) is None
    assert safe_divide(float("nan"), 1) is None
    assert period_to_window("3m") == 63
    assert period_to_window("999d") == 252
    assert period_to_window("invalid") == 21
    assert pressure_regime(2.1) == "entrada_forte"
    assert pressure_regime(-2.1) == "stress"
    assert pressure_regime(None) == "neutral"


def test_funds_flow_contracts_normalize_aliases_and_boolean_values() -> None:
    query = FundsFlowDashboardQuery.model_validate(
        {
            "date": "2026-08-18",
            "period": " 63D ",
            "history_days": "95",
            "refresh": "yes",
        }
    )
    command = CollectFundsFlowCommand.model_validate({"force": "false"})
    refresh = RefreshFundsFlowSourceCommand.model_validate(
        {"source_id": " CVM ", "target_date": date(2026, 8, 18)}
    )

    assert query.target_date == "2026-08-18"
    assert query.period == "63d"
    assert query.history_days == 95
    assert query.refresh is True
    assert command.force is False
    assert refresh.source_id == "cvm"


@pytest.mark.parametrize(
    "payload",
    [
        {"date": "not-a-date"},
        {"history_days": 10},
        {"unexpected": "field"},
    ],
)
def test_funds_flow_contracts_reject_invalid_requests(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        FundsFlowDashboardQuery.model_validate(payload)


def test_funds_flow_use_cases_coordinate_gateways_without_http_dependencies() -> None:
    dashboard = RecordingDashboard()
    collector = RecordingCollector()

    dashboard_result = GetFundsFlowDashboard(dashboard, collector).execute(
        FundsFlowDashboardQuery(
            target_date="2026-08-18",
            period="21d",
            history_days=80,
            refresh=True,
        )
    )
    collect_result = CollectFundsFlow(collector).execute(
        CollectFundsFlowCommand(force=False, period="63d", history_days=95)
    )
    refresh_result = RefreshFundsFlowSource(collector).execute(
        RefreshFundsFlowSourceCommand(source_id="anbima", period="21d")
    )

    assert dashboard.calls == [
        {
            "target_date": "2026-08-18",
            "period": "21d",
            "history_days": 80,
            "refresh": True,
        }
    ]
    assert dashboard_result["collector"]["run_count"] == 0
    assert collect_result["collector"]["run_count"] == 1
    assert collector.calls[0]["force"] is False
    assert refresh_result["requested_source_id"] == "anbima"
    assert collector.calls[1]["force"] is True


def test_json_repositories_round_trip_snapshots_summaries_and_state(tmp_path: Path) -> None:
    snapshots = JsonFundsFlowSnapshotRepository(str(tmp_path))
    state = JsonFundsFlowCollectorStateRepository(str(tmp_path / "collector_status.json"))

    snapshot = FundFlowSnapshot.model_validate(
        {
            "ok": True,
            "generated_at": "2026-08-18T12:00:00Z",
            "report": {"as_of_date": "2026-08-18", "schema_version": 6},
            "kpis": {"net_flow_21d": 125.0},
        }
    )
    summary = FundFlowSnapshotSummary(
        generated_at=datetime(2026, 8, 18, 12, tzinfo=timezone.utc),
        as_of_date=date(2026, 8, 18),
        period="21d",
        net_flow_21d=Decimal("125.0"),
    )
    snapshots.save_latest(snapshot)
    snapshots.append_summary(summary)
    state.save(FundFlowCollectorState(desired_running=True, run_count=4))

    loaded = snapshots.load_latest()
    assert loaded is not None
    assert loaded.report.as_of_date == date(2026, 8, 18)
    assert loaded.kpis.net_flow_21d == Decimal("125.0")
    assert '"net_flow_21d": 125.0' in (tmp_path / "snapshots.jsonl").read_text(encoding="utf-8")
    assert state.load().desired_running is True
    assert state.load().run_count == 4


def test_collector_manager_uses_injected_state_repository(tmp_path: Path) -> None:
    state = JsonFundsFlowCollectorStateRepository(str(tmp_path / "state.json"))
    service = SnapshotServiceStub(
        tmp_path,
        {"report": {"last_updated_at": "2026-08-18T12:00:00+00:00"}},
    )
    manager = FundsFlowLocalManager(service=service, state_repository=state)  # type: ignore[arg-type]

    manager._save_status(desired_running=True, run_count=3)

    assert manager._read_status()["desired_running"] is True
    assert manager._read_status()["run_count"] == 3
    assert manager._latest_snapshot_at() is not None
