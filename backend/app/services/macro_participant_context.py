"""Shared typing contract for macro participant analytics mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ..config import Config
    from .macro_live_service import MacroStateStore


class MacroParticipantContextMixin:
    config: type[Config]
    store: MacroStateStore
    _classify_broker_origin: Callable[[Any], dict[str, Any]]

    def _build_pressure_model(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError
