from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from flask import Flask

from app.container import AquilesContainer, attach_container, get_container
from app.infrastructure.scheduled_collector_client import ScheduledCollectorClient
from app.workers.collection_scheduler import resume_scheduled_collectors


def test_provider_constructs_dependency_once_under_concurrent_access() -> None:
    dependencies = AquilesContainer()
    constructed: list[object] = []

    def factory() -> object:
        instance = object()
        constructed.append(instance)
        return instance

    dependencies.register("test_service", factory)
    with ThreadPoolExecutor(max_workers=8) as executor:
        resolved = list(executor.map(lambda _: dependencies.resolve("test_service"), range(40)))

    assert len(constructed) == 1
    assert all(instance is constructed[0] for instance in resolved)


def test_app_uses_explicitly_attached_dependencies() -> None:
    app = Flask(__name__)
    dependencies = AquilesContainer()
    attach_container(app, dependencies)

    with app.app_context():
        assert get_container() is dependencies


def test_override_replaces_factory_without_constructing_default() -> None:
    dependencies = AquilesContainer()
    replacement = object()
    dependencies.override("macro_collector", replacement)

    assert dependencies.macro_collector() is replacement


def test_managers_share_the_services_owned_by_the_container(tmp_path) -> None:
    class FundsService:
        root_dir = str(tmp_path / "funds")

    class CvmService:
        root_dir = tmp_path / "cvm"

    funds_service = FundsService()
    cvm_service = CvmService()
    dependencies = AquilesContainer.for_collection_scheduler()
    dependencies.override("funds_flow_service", funds_service)
    dependencies.override("cvm_cda_service", cvm_service)

    assert dependencies.funds_flow_manager().service is funds_service
    assert dependencies.cvm_cda_manager().service is cvm_service


def test_api_container_uses_remote_collector_controls() -> None:
    dependencies = AquilesContainer()

    assert isinstance(dependencies.funds_flow_manager(), ScheduledCollectorClient)
    assert isinstance(dependencies.cvm_cda_manager(), ScheduledCollectorClient)
    assert isinstance(dependencies.macro_collector(), ScheduledCollectorClient)
    assert isinstance(dependencies.report_source_collector(), ScheduledCollectorClient)


def test_scheduler_resumes_every_owned_collector() -> None:
    class RecordingCollector:
        def __init__(self) -> None:
            self.resume_calls = 0

        def resume_if_needed(self) -> dict[str, bool]:
            self.resume_calls += 1
            return {"running": True}

    class RecordingLogger:
        def __init__(self) -> None:
            self.exceptions: list[tuple] = []

        def info(self, *_args) -> None:
            pass

        def exception(self, *args, **kwargs) -> None:
            self.exceptions.append((args, kwargs))

    collectors = {
        name: RecordingCollector()
        for name in (
            "cvm_cda_manager",
            "funds_flow_manager",
            "report_source_collector",
            "macro_collector",
        )
    }
    logger = RecordingLogger()
    dependencies = AquilesContainer.for_collection_scheduler()
    for name, collector in collectors.items():
        dependencies.override(name, collector)

    statuses = resume_scheduled_collectors(dependencies, logger)

    assert set(statuses) == {"cvm_cda", "funds_flow", "report_sources", "macro"}
    assert all(collector.resume_calls == 1 for collector in collectors.values())
    assert logger.exceptions == []
