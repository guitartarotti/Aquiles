"""Ports for the official data providers consumed by Funds Flow."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

Payload = dict[str, Any]
SourceResult = tuple[Payload, Payload]


class CvmSource(Protocol):
    """CVM datasets required to build the local funds-flow series."""

    def load_informe_diario(
        self,
        *,
        start_date: date,
        end_date: date,
        force: bool,
    ) -> tuple[Any, list[Payload]]: ...

    def load_fund_registry(self, *, force: bool) -> tuple[Any, Payload]: ...


class AnbimaSource(Protocol):
    """ANBIMA consolidated fund statistics and rankings."""

    def load_funds(self, *, force: bool) -> SourceResult: ...

    def build_validation(
        self,
        class_latest: Any,
        anbima_payload: Payload,
        *,
        as_of_date: date,
    ) -> Payload: ...


class B3Source(Protocol):
    """B3 participant, open-interest, market and listed-fund datasets."""

    def load_etfs(self, *, force: bool) -> SourceResult: ...

    def load_investor_participation(
        self,
        *,
        target_date: date,
        force: bool,
    ) -> SourceResult: ...

    def load_open_interest(
        self,
        *,
        target_date: date,
        force: bool,
    ) -> SourceResult: ...

    def load_monthly_investor_participation(
        self,
        *,
        target_date: date,
        force: bool,
    ) -> SourceResult: ...

    def load_market_data_report(self, *, force: bool) -> SourceResult: ...


class IciSource(Protocol):
    """ICI global mutual-fund and ETF flow datasets."""

    def load_global_flows(self, *, force: bool) -> SourceResult: ...
