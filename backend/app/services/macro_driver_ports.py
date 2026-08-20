from __future__ import annotations

from typing import Any, Protocol

from .macro_live_state_store import MacroStateStore

__all__ = ["MacroIngestionPort", "MacroStateStore"]


class MacroIngestionPort(Protocol):
    """Behavior the driver analysis needs from macro ingestion."""

    def reclassify_news_events(
        self,
        news_events: list[dict[str, Any]],
        market_snapshot: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...

    def _build_contract_signal(
        self,
        ticker: str,
        contract: dict[str, Any],
    ) -> dict[str, Any]: ...
