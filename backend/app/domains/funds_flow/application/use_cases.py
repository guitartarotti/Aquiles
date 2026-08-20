"""Use cases that coordinate Funds Flow gateways without HTTP dependencies."""

from __future__ import annotations

from typing import Any

from ..contracts import (
    CollectFundsFlowCommand,
    FundsFlowCollectorStatus,
    FundsFlowDashboardQuery,
    FundsFlowPayload,
    RefreshFundsFlowSourceCommand,
)
from .ports import FundsFlowCollectorGateway, FundsFlowDashboardGateway


def _validated_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return FundsFlowPayload.model_validate(payload).model_dump(mode="json", exclude_none=True)


def _validated_status(payload: dict[str, Any]) -> dict[str, Any]:
    return FundsFlowCollectorStatus.model_validate(payload).model_dump(
        mode="json", exclude_none=True
    )


class GetFundsFlowDashboard:
    def __init__(
        self,
        dashboard: FundsFlowDashboardGateway,
        collector: FundsFlowCollectorGateway,
    ) -> None:
        self.dashboard = dashboard
        self.collector = collector

    def execute(self, query: FundsFlowDashboardQuery) -> dict[str, Any]:
        payload = self.dashboard.get_dashboard(
            target_date=query.target_date,
            period=query.period,
            history_days=query.history_days,
            refresh=query.refresh,
        )
        return _validated_payload({**payload, "collector": self.collector.status()})


class CollectFundsFlow:
    def __init__(self, collector: FundsFlowCollectorGateway) -> None:
        self.collector = collector

    def execute(self, command: CollectFundsFlowCommand) -> dict[str, Any]:
        payload = self.collector.collect_once(
            force=command.force,
            target_date=command.target_date,
            period=command.period,
            history_days=command.history_days,
        )
        return _validated_payload({**payload, "collector": self.collector.status()})


class RefreshFundsFlowSource:
    def __init__(self, collector: FundsFlowCollectorGateway) -> None:
        self.collector = collector

    def execute(self, command: RefreshFundsFlowSourceCommand) -> dict[str, Any]:
        payload = self.collector.collect_once(
            force=True,
            target_date=command.target_date,
            period=command.period,
            history_days=command.history_days,
        )
        return _validated_payload(
            {
                **payload,
                "requested_source_id": command.source_id,
                "collector": self.collector.status(),
            }
        )


class GetFundsFlowCollectorStatus:
    def __init__(self, collector: FundsFlowCollectorGateway) -> None:
        self.collector = collector

    def execute(self) -> dict[str, Any]:
        return _validated_status(self.collector.status())


class StartFundsFlowCollector:
    def __init__(self, collector: FundsFlowCollectorGateway) -> None:
        self.collector = collector

    def execute(self) -> dict[str, Any]:
        return _validated_status(self.collector.start())


class StopFundsFlowCollector:
    def __init__(self, collector: FundsFlowCollectorGateway) -> None:
        self.collector = collector

    def execute(self) -> dict[str, Any]:
        return _validated_status(self.collector.stop())
