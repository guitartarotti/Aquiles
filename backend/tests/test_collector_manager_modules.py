from __future__ import annotations

from datetime import datetime

from app.config import Config
from app.services import options_collector_manager as options_collector_module
from app.services.cvm_cda_manager import CvmCdaManager
from app.services.funds_flow_local_manager import FundsFlowLocalManager
from app.services.macro_options_heatmap_context_schedule import options_poll_interval_seconds
from app.services.macro_participant_heatmap_manager import (
    MacroParticipantHeatmapCollectorManager,
)
from app.startup import COLLECTORS


def test_funds_flow_schedule_parsing_and_rollover(monkeypatch) -> None:
    monkeypatch.setattr(Config, "FUNDS_FLOW_LOCAL_UPDATE_TIME", "07:40")
    configured = FundsFlowLocalManager._configured_update_time()
    assert (configured.hour, configured.minute) == (7, 40)

    before_run = datetime.fromisoformat("2026-08-18T06:00:00-03:00")
    after_run = datetime.fromisoformat("2026-08-18T08:00:00-03:00")
    manager = FundsFlowLocalManager.__new__(FundsFlowLocalManager)

    assert manager._next_run_at(before_run).date() == before_run.date()
    assert manager._next_run_at(after_run).date() > after_run.date()


def test_participant_manager_reports_runtime_without_starting_thread(monkeypatch) -> None:
    class FakeService:
        @staticmethod
        def _read_state():
            return {"collector": {"last_error": None}, "assets": [{"samples": [1, 2]}]}

        @staticmethod
        def _count_samples(_state):
            return 2

    monkeypatch.setattr(Config, "MACRO_PARTICIPANT_HEATMAP_ENABLE", True)
    monkeypatch.setattr(Config, "MACRO_PARTICIPANT_HEATMAP_AUTO_START", False)
    monkeypatch.setattr(Config, "MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS", 15)
    monkeypatch.setattr(Config, "MACRO_PARTICIPANT_HEATMAP_SESSION_SAMPLE_LIMIT", 120)

    manager = MacroParticipantHeatmapCollectorManager.__new__(
        MacroParticipantHeatmapCollectorManager
    )
    manager.service = FakeService()
    manager._thread = None

    assert manager.status() == {
        "last_error": None,
        "enabled": True,
        "auto_start": False,
        "interval_seconds": 15,
        "session_sample_limit": 120,
        "running": False,
        "sample_count": 2,
    }


def test_options_collector_construction_and_status_are_inert(monkeypatch) -> None:
    class FakeStore:
        @staticmethod
        def read_state():
            return {"collector": {"desired_running": True}}

    supervisor_starts: list[bool] = []

    monkeypatch.setattr(options_collector_module, "OptionsStore", FakeStore)
    monkeypatch.setattr(
        options_collector_module,
        "OptionsSnapshotService",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        options_collector_module,
        "OptionsHistoryService",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        options_collector_module,
        "B3OIService",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        options_collector_module,
        "OptionsModelingService",
        lambda **_kwargs: object(),
    )
    monkeypatch.setattr(
        options_collector_module.OptionsCollectorManager,
        "_ensure_supervisor_running",
        lambda _self: supervisor_starts.append(True),
    )

    manager = options_collector_module.OptionsCollectorManager()
    status = manager.status()

    assert supervisor_starts == []
    assert status["desired_running"] is True
    assert status["running"] is False
    assert status["supervisor_running"] is False


def test_startup_loads_funds_flow_manager_from_lifecycle_module() -> None:
    funds_flow_spec = next(spec for spec in COLLECTORS if spec.label == "funds-flow collector")
    assert funds_flow_spec.module == ".services.funds_flow_local_manager"
    assert funds_flow_spec.manager_class == "FundsFlowLocalManager"

    cvm_cda_spec = next(spec for spec in COLLECTORS if spec.label == "CVM CDA collector")
    assert cvm_cda_spec.module == ".services.cvm_cda_manager"
    assert cvm_cda_spec.manager_class == "CvmCdaManager"


def test_options_poll_uses_fastest_configured_interval() -> None:
    class TestConfig:
        MACRO_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS = 30
        MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS = 10
        MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS = 15

    assert options_poll_interval_seconds(TestConfig) == 10


def test_cvm_cda_schedule_parsing_falls_back_to_expected_time(monkeypatch) -> None:
    monkeypatch.setattr(Config, "CVM_CDA_UPDATE_TIME", "invalid")
    configured = CvmCdaManager._configured_update_time()
    assert (configured.hour, configured.minute) == (8, 25)
