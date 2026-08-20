"""Application-facing gateways implemented by Funds Flow adapters."""

from __future__ import annotations

from typing import Any, Protocol


class FundsFlowDashboardGateway(Protocol):
    def get_dashboard(
        self,
        *,
        target_date: Any = None,
        period: str | None = "21d",
        history_days: int | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]: ...


class FundsFlowCollectorGateway(Protocol):
    def collect_once(
        self,
        *,
        force: bool = True,
        target_date: Any = None,
        period: str | None = "21d",
        history_days: int | None = None,
    ) -> dict[str, Any]: ...

    def status(self) -> dict[str, Any]: ...

    def start(self) -> dict[str, Any]: ...

    def stop(self) -> dict[str, Any]: ...
