"""Compose Funds Flow persistence adapters from runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from ..domains.funds_flow.application import (
    FundsFlowCollectorStateRepository,
    FundsFlowSnapshotRepository,
)
from ..domains.funds_flow.infrastructure import (
    JsonFundsFlowCollectorStateRepository,
    JsonFundsFlowSnapshotRepository,
    PostgresFundsFlowCollectorStateRepository,
    PostgresFundsFlowSnapshotRepository,
)


@dataclass(frozen=True)
class FundsFlowPersistence:
    snapshots: FundsFlowSnapshotRepository
    collector_state: FundsFlowCollectorStateRepository


def build_funds_flow_persistence(
    root_dir: str,
    config: Any,
) -> FundsFlowPersistence:
    backend = str(getattr(config, "PERSISTENCE_BACKEND", "filesystem") or "filesystem")
    backend = backend.strip().lower()
    if backend == "filesystem":
        return FundsFlowPersistence(
            snapshots=JsonFundsFlowSnapshotRepository(root_dir),
            collector_state=JsonFundsFlowCollectorStateRepository(
                os.path.join(root_dir, "collector_status.json")
            ),
        )
    if backend == "postgresql":
        dsn = str(getattr(config, "DATABASE_URL", "") or "").strip()
        if not dsn:
            raise ValueError("DATABASE_URL is required when AQUILES_PERSISTENCE_BACKEND=postgresql")
        return FundsFlowPersistence(
            snapshots=PostgresFundsFlowSnapshotRepository(dsn),
            collector_state=PostgresFundsFlowCollectorStateRepository(dsn),
        )
    raise ValueError(f"Unsupported persistence backend: {backend}")
