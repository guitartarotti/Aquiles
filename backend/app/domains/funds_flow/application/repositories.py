"""Typed persistence ports consumed by Funds Flow use cases and services."""

from __future__ import annotations

from typing import Protocol

from ..contracts import (
    FundFlowCollectorState,
    FundFlowSnapshot,
    FundFlowSnapshotSummary,
)


class FundsFlowSnapshotRepository(Protocol):
    def load_latest(self) -> FundFlowSnapshot | None: ...

    def save_latest(self, payload: FundFlowSnapshot) -> None: ...

    def append_summary(self, summary: FundFlowSnapshotSummary) -> None: ...


class FundsFlowCollectorStateRepository(Protocol):
    def load(self) -> FundFlowCollectorState: ...

    def save(self, state: FundFlowCollectorState) -> None: ...
