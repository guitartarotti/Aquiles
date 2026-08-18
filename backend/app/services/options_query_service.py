from __future__ import annotations

from typing import Any

from ..config import Config
from .options_store import OptionsStore


class OptionsQueryService:
    def __init__(self, store: OptionsStore | None = None):
        self.store = store or OptionsStore()

    def status(self) -> dict[str, Any]:
        state = self.store.read_state()
        collector = state.get("collector", {}) or {}
        return {
            "enabled": bool(Config.OPTIONS_ENABLE),
            "ingest_enabled": bool(Config.OPTIONS_INGEST_ENABLE),
            "underlyings": list(Config.OPTIONS_BLOOMBERG_UNDERLYINGS),
            "trade_map": dict(Config.OPTIONS_UNDERLYING_TRADE_MAP),
            "collector": collector,
            "latest_batches": state.get("latest_batches", {}) or {},
        }

    def contracts(
        self,
        underlying_security: str | None = None,
        only_active: bool = False,
        limit: int | None = None,
    ) -> dict[str, Any]:
        rows = self.store.list_contracts(
            underlying_security=underlying_security,
            only_active=only_active,
            limit=limit,
        )
        return {
            "count": len(rows),
            "rows": rows,
        }

    def universe(self, underlying_security: str | None = None) -> dict[str, Any]:
        return self.store.load_universe_state(underlying_security=underlying_security)

    def latest_snapshot(
        self,
        universe_tier: str,
        underlying_security: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        return self.store.read_latest_snapshot(
            universe_tier=universe_tier,
            underlying_security=underlying_security,
            limit=limit,
        )

    def oi_history(
        self,
        underlying_security: str | None = None,
        option_id: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        rows = self.store.list_oi_history(
            underlying_security=underlying_security,
            option_id=option_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        return {
            "count": len(rows),
            "rows": rows,
        }

    def latest_model_run(
        self,
        underlying_security: str,
        universe_tier: str | None = None,
    ) -> dict[str, Any]:
        payload = self.store.read_latest_model_run(underlying_security, universe_tier=universe_tier)
        return payload or {}

    def model_run(self, run_id: str) -> dict[str, Any]:
        payload = self.store.read_model_run(run_id)
        return payload or {}

    def latest_global_run(self, underlying_security: str) -> dict[str, Any]:
        payload = self.store.read_latest_global_run(underlying_security)
        return payload or {}

    def global_run(self, run_id: str) -> dict[str, Any]:
        payload = self.store.read_global_run(run_id)
        return payload or {}

    def latest_fair_value_run(self, underlying_security: str) -> dict[str, Any]:
        payload = self.store.read_latest_fair_value_run(underlying_security)
        return payload or {}

    def fair_value_run(self, run_id: str) -> dict[str, Any]:
        payload = self.store.read_fair_value_run(run_id)
        return payload or {}
