"""Validated input and output models shared by Funds Flow adapters."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


class FundFlowSourceStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    label: str = ""
    provider: str | None = None
    kind: str | None = None
    cadence: str | None = None
    role: str | None = None
    url: str | None = None
    status: str
    ok: bool | None = None
    rows: int | None = Field(default=None, ge=0)
    latest_error: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    latest_data_date: date | None = None
    last_captured_at: datetime | None = None

    @model_validator(mode="after")
    def default_label_to_source_id(self) -> FundFlowSourceStatus:
        if not self.label.strip():
            self.label = self.id
        return self


class FundFlowReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = "Funds Flow Local"
    as_of_date: date | None = None
    requested_date: date | None = None
    period: str = "21d"
    history_days: int = Field(default=30, ge=1)
    schema_version: int = Field(default=1, ge=1)
    currency: str = "BRL"
    sources: list[str] = Field(default_factory=list)
    primary_source: str | None = None
    last_updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    lineage: dict[str, Any] = Field(default_factory=dict)


class FundFlowKpis(BaseModel):
    model_config = ConfigDict(extra="allow")

    industry_aum: Decimal | None = None
    net_flow_1d: Decimal | None = None
    net_flow_5d: Decimal | None = None
    net_flow_21d: Decimal | None = None
    net_flow_63d: Decimal | None = None
    net_flow_ytd: Decimal | None = None
    flow_pct_pl_21d: Decimal | None = None
    total_shareholders: Decimal | None = None
    delta_shareholders_21d: Decimal | None = None
    num_funds: int | None = Field(default=None, ge=0)
    pressure_index: Decimal | None = None
    regime: str | None = None

    @field_serializer(
        "industry_aum",
        "net_flow_1d",
        "net_flow_5d",
        "net_flow_21d",
        "net_flow_63d",
        "net_flow_ytd",
        "flow_pct_pl_21d",
        "total_shareholders",
        "delta_shareholders_21d",
        "pressure_index",
    )
    def serialize_decimal(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class FundFlowSnapshot(BaseModel):
    """Versioned Funds Flow aggregate persisted and returned by the application."""

    model_config = ConfigDict(extra="allow")

    ok: bool = True
    generated_at: datetime
    report: FundFlowReport
    kpis: FundFlowKpis
    source_status: list[FundFlowSourceStatus] = Field(default_factory=list)


class FundFlowSnapshotSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    as_of_date: date | None = None
    period: str
    industry_aum: Decimal | None = None
    net_flow_21d: Decimal | None = None
    pressure_index: Decimal | None = None
    regime: str | None = None

    @field_serializer("industry_aum", "net_flow_21d", "pressure_index")
    def serialize_decimal(self, value: Decimal | None) -> float | None:
        return float(value) if value is not None else None


class FundFlowCollectorState(BaseModel):
    model_config = ConfigDict(extra="allow")

    desired_running: bool = False
    running: bool = False
    run_count: int = Field(default=0, ge=0)
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    stopped_reason: str | None = None


class _FundsFlowWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    target_date: str | date | None = Field(
        default=None,
        validation_alias=AliasChoices("target_date", "date"),
    )
    period: str = "21d"
    history_days: int | None = Field(default=None, ge=30, le=540)

    @field_validator("target_date", mode="before")
    @classmethod
    def validate_target_date(cls, value: Any) -> Any:
        if value is None or isinstance(value, date):
            return value
        normalized = str(value).strip()
        if not normalized:
            return None
        date.fromisoformat(normalized[:10])
        return normalized

    @field_validator("period", mode="before")
    @classmethod
    def normalize_period(cls, value: Any) -> str:
        normalized = str(value or "21d").strip().lower()
        if not normalized:
            return "21d"
        if len(normalized) > 12:
            raise ValueError("period is too long")
        return normalized


class FundsFlowDashboardQuery(_FundsFlowWindow):
    refresh: bool = False


class CollectFundsFlowCommand(_FundsFlowWindow):
    force: bool = True


class RefreshFundsFlowSourceCommand(_FundsFlowWindow):
    source_id: str = Field(min_length=1, max_length=120)
    force: bool = True

    @field_validator("source_id")
    @classmethod
    def normalize_source_id(cls, value: str) -> str:
        return value.strip().lower()


class FundsFlowPayload(BaseModel):
    """Stable response envelope that preserves source-specific extensions."""

    model_config = ConfigDict(extra="allow")

    ok: bool = True
    report: FundFlowReport = Field(default_factory=FundFlowReport)
    kpis: FundFlowKpis = Field(default_factory=FundFlowKpis)
    source_status: list[FundFlowSourceStatus] = Field(default_factory=list)
    collector: FundFlowCollectorState | None = None
    requested_source_id: str | None = None


class FundsFlowCollectorStatus(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool | None = None
    running: bool = False
    desired_running: bool | None = None
    last_error: str | None = None
