"""Concrete adapters for Funds Flow external systems and persistence."""

from .anbima_source import AnbimaFundsFlowAdapter
from .b3_source import B3FundsFlowAdapter
from .cvm_source import CvmFundsFlowAdapter
from .ici_source import IciFundsFlowAdapter
from .json_repositories import (
    JsonFundsFlowCollectorStateRepository,
    JsonFundsFlowSnapshotRepository,
)
from .postgres_repositories import (
    PostgresFundsFlowCollectorStateRepository,
    PostgresFundsFlowSnapshotRepository,
)

__all__ = [
    "JsonFundsFlowCollectorStateRepository",
    "JsonFundsFlowSnapshotRepository",
    "PostgresFundsFlowCollectorStateRepository",
    "PostgresFundsFlowSnapshotRepository",
    "AnbimaFundsFlowAdapter",
    "B3FundsFlowAdapter",
    "CvmFundsFlowAdapter",
    "IciFundsFlowAdapter",
]
