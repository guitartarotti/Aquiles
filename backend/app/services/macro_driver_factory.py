from __future__ import annotations

from typing import Optional

from ..utils.llm_client import LLMClient
from .macro_driver_service import PERSISTED_CROSS_ASSET_VERSION, MacroDriverService
from .macro_live_service import MacroIngestionService
from .macro_live_state_store import MacroStateStore

__all__ = ["PERSISTED_CROSS_ASSET_VERSION", "build_macro_driver_service"]


def build_macro_driver_service(
    *,
    store: Optional[MacroStateStore] = None,
    llm_client: Optional[LLMClient] = None,
) -> MacroDriverService:
    resolved_store = store or MacroStateStore()
    return MacroDriverService(
        store=resolved_store,
        ingestion=MacroIngestionService(store=resolved_store),
        llm_client=llm_client,
    )
