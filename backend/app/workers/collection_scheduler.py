"""Lifecycle orchestration for collectors owned by the scheduler process."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..container import AquilesContainer


@dataclass(frozen=True)
class ScheduledCollectorSpec:
    name: str
    label: str
    dependency: str


SCHEDULED_COLLECTORS = (
    ScheduledCollectorSpec("cvm_cda", "CVM CDA collector", "cvm_cda_manager"),
    ScheduledCollectorSpec("funds_flow", "Funds Flow collector", "funds_flow_manager"),
    ScheduledCollectorSpec("report_sources", "report-source collector", "report_source_collector"),
    ScheduledCollectorSpec("macro", "macro and news collector", "macro_collector"),
)


def collector_managers(dependencies: AquilesContainer) -> dict[str, Any]:
    return {spec.name: dependencies.resolve(spec.dependency) for spec in SCHEDULED_COLLECTORS}


def resume_scheduled_collectors(
    dependencies: AquilesContainer,
    logger: Any,
) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    for spec in SCHEDULED_COLLECTORS:
        try:
            status = dependencies.resolve(spec.dependency).resume_if_needed()
            statuses[spec.name] = status
            logger.info("%s resumed status=%s", spec.label, status)
        except Exception as exc:
            logger.exception("Failed to resume %s", spec.label)
            statuses[spec.name] = {
                "running": False,
                "error": type(exc).__name__,
            }
    return statuses
