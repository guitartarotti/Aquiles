"""Application-scoped dependency composition for Aquiles."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from flask import Flask, current_app

if TYPE_CHECKING:
    from .services.cvm_cda_manager import CvmCdaManager
    from .services.cvm_cda_service import CvmCdaService
    from .services.funds_flow_local_manager import FundsFlowLocalManager
    from .services.funds_flow_local_service import FundsFlowLocalService
    from .services.macro_live_service import MacroCollectorManager
    from .services.oplab_options_service import OpLabOptionsService
    from .services.options_modeling import OptionsModelingService
    from .services.options_volume_tracker import OptionsVolumeTracker
    from .services.report_source_discovery_service import ReportSourceDiscoveryManager


EXTENSION_KEY = "aquiles_dependencies"


class LazyProvider:
    """Create one dependency on first access, including under concurrent access."""

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._instance: Any = None
        self._initialized = False
        self._lock = threading.Lock()

    def get(self) -> Any:
        if not self._initialized:
            with self._lock:
                if not self._initialized:
                    self._instance = self._factory()
                    self._initialized = True
        return self._instance


class AquilesContainer:
    """Own the dependency graph for one Flask application instance."""

    def __init__(self, *, collector_owner: bool = False) -> None:
        self.collector_owner = collector_owner
        self._providers: dict[str, LazyProvider] = {}
        self._register_defaults()

    @classmethod
    def for_collection_scheduler(cls) -> AquilesContainer:
        return cls(collector_owner=True)

    def register(self, name: str, factory: Callable[[], Any]) -> None:
        self._providers[name] = LazyProvider(factory)

    def override(self, name: str, value: Any) -> None:
        """Replace a dependency explicitly, primarily for tests and local adapters."""
        self.register(name, lambda: value)

    def resolve(self, name: str) -> Any:
        try:
            provider = self._providers[name]
        except KeyError as exc:
            raise KeyError(f"Unknown Aquiles dependency: {name}") from exc
        return provider.get()

    def funds_flow_service(self) -> FundsFlowLocalService:
        return cast("FundsFlowLocalService", self.resolve("funds_flow_service"))

    def funds_flow_manager(self) -> FundsFlowLocalManager:
        return cast("FundsFlowLocalManager", self.resolve("funds_flow_manager"))

    def cvm_cda_service(self) -> CvmCdaService:
        return cast("CvmCdaService", self.resolve("cvm_cda_service"))

    def cvm_cda_manager(self) -> CvmCdaManager:
        return cast("CvmCdaManager", self.resolve("cvm_cda_manager"))

    def macro_collector(self) -> MacroCollectorManager:
        return cast("MacroCollectorManager", self.resolve("macro_collector"))

    def report_source_collector(self) -> ReportSourceDiscoveryManager:
        return cast(
            "ReportSourceDiscoveryManager",
            self.resolve("report_source_collector"),
        )

    def options_volume_tracker(self) -> OptionsVolumeTracker:
        return cast("OptionsVolumeTracker", self.resolve("options_volume_tracker"))

    def oplab_options_service(self) -> OpLabOptionsService:
        return cast("OpLabOptionsService", self.resolve("oplab_options_service"))

    def options_modeling_service(self) -> OptionsModelingService:
        return cast("OptionsModelingService", self.resolve("options_modeling_service"))

    def _register_defaults(self) -> None:
        self.register("funds_flow_persistence", self._create_funds_flow_persistence)
        self.register("funds_flow_service", self._create_funds_flow_service)
        self.register("funds_flow_manager", self._create_funds_flow_manager)
        self.register("cvm_cda_service", self._create_cvm_cda_service)
        self.register("cvm_cda_manager", self._create_cvm_cda_manager)
        self.register(
            "macro_collector",
            self._create_local_macro_collector
            if self.collector_owner
            else self._create_macro_collector,
        )
        self.register(
            "report_source_collector",
            self._create_local_report_source_collector
            if self.collector_owner
            else self._create_report_source_collector,
        )
        self.register("options_volume_tracker", self._create_options_volume_tracker)
        self.register("oplab_options_service", self._create_oplab_options_service)
        self.register("options_modeling_service", self._create_options_modeling_service)

    @staticmethod
    def _create_funds_flow_persistence() -> Any:
        from .config import Config
        from .infrastructure.funds_flow_persistence import build_funds_flow_persistence

        return build_funds_flow_persistence(Config.FUNDS_FLOW_LOCAL_DATA_DIR, Config)

    def _create_funds_flow_service(self) -> FundsFlowLocalService:
        from .services.funds_flow_local_service import FundsFlowLocalService

        persistence = self.resolve("funds_flow_persistence")
        return FundsFlowLocalService(snapshot_repository=persistence.snapshots)

    def _create_funds_flow_manager(self) -> FundsFlowLocalManager:
        if not self.collector_owner:
            return cast(
                "FundsFlowLocalManager",
                self._create_scheduled_collector_client("funds_flow"),
            )
        from .services.funds_flow_local_manager import FundsFlowLocalManager

        persistence = self.resolve("funds_flow_persistence")
        return FundsFlowLocalManager(
            service=self.funds_flow_service(),
            state_repository=persistence.collector_state,
        )

    @staticmethod
    def _create_cvm_cda_service() -> CvmCdaService:
        from .services.cvm_cda_service import CvmCdaService

        return CvmCdaService()

    def _create_cvm_cda_manager(self) -> CvmCdaManager:
        if not self.collector_owner:
            return cast(
                "CvmCdaManager",
                self._create_scheduled_collector_client("cvm_cda"),
            )
        from .services.cvm_cda_manager import CvmCdaManager

        return CvmCdaManager(service=self.cvm_cda_service())

    @staticmethod
    def _create_macro_collector() -> MacroCollectorManager:
        from .infrastructure.scheduled_collector_client import ScheduledCollectorClient

        return cast("MacroCollectorManager", ScheduledCollectorClient("macro"))

    @staticmethod
    def _create_local_macro_collector() -> MacroCollectorManager:
        from .services.macro_live_service import MacroCollectorManager

        return MacroCollectorManager()

    @staticmethod
    def _create_report_source_collector() -> ReportSourceDiscoveryManager:
        from .infrastructure.scheduled_collector_client import ScheduledCollectorClient

        return cast(
            "ReportSourceDiscoveryManager",
            ScheduledCollectorClient("report_sources"),
        )

    @staticmethod
    def _create_local_report_source_collector() -> ReportSourceDiscoveryManager:
        from .services.report_source_discovery_service import ReportSourceDiscoveryManager

        return ReportSourceDiscoveryManager()

    @staticmethod
    def _create_options_volume_tracker() -> OptionsVolumeTracker:
        from .infrastructure.options_volume_tracker_client import OptionsVolumeTrackerClient

        return cast("OptionsVolumeTracker", OptionsVolumeTrackerClient())

    @staticmethod
    def _create_oplab_options_service() -> OpLabOptionsService:
        from .services.oplab_options_service import OpLabOptionsService

        return OpLabOptionsService()

    @staticmethod
    def _create_options_modeling_service() -> OptionsModelingService:
        from .services.options_modeling import OptionsModelingService

        return OptionsModelingService()

    @staticmethod
    def _create_scheduled_collector_client(name: str) -> Any:
        from .infrastructure.scheduled_collector_client import ScheduledCollectorClient

        return ScheduledCollectorClient(name)


def attach_container(app: Flask, container: AquilesContainer | None = None) -> AquilesContainer:
    dependencies = container or AquilesContainer()
    app.extensions[EXTENSION_KEY] = dependencies
    return dependencies


def get_container() -> AquilesContainer:
    """Return dependencies for the active app, with a fallback for small test apps."""
    dependencies = current_app.extensions.get(EXTENSION_KEY)
    if dependencies is None:
        dependencies = attach_container(current_app)
    return cast(AquilesContainer, dependencies)
