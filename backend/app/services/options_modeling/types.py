from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MarketContext:
    underlying_security: str
    snapshot_batch_id: str | None
    snapshot_batch_key: str | None
    spot_price: float
    spot_security: str | None
    forward_price: float | None
    forward_security: str | None
    future_basis_points: float | None
    future_basis_pct: float | None
    dividend_proxy_level: float | None
    dividend_security: str | None
    rate_curve_points: dict[int, float]
    reference_trade_date: str | None
    sources: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PreparedOption:
    option_id: str
    bloomberg_ticker: str
    underlying_security: str
    underlying_trade_symbol: str | None
    put_call: str
    strike: float
    expiry_date: str
    days_to_expiry_business: int
    days_to_expiry_calendar: int | None
    time_to_expiry_years: float
    snapshot_timestamp: str
    snapshot_id: str | None
    batch_id: str | None
    batch_key: str | None
    universe_tier: str | None
    px_last: float | None
    bid: float | None
    ask: float | None
    mid: float | None
    open_int: float
    px_volume: float | None
    iv_bid: float | None
    iv_ask: float | None
    iv_mid: float | None
    iv_last: float | None
    selected_iv: float
    observed_delta: float | None
    observed_gamma: float | None
    observed_vega: float | None
    observed_theta: float | None
    spot_price: float
    forward_price: float
    interpolated_rate: float
    carry_dividend_proxy: float
    moneyness_spot: float | None
    moneyness_forward: float | None
    log_moneyness: float | None
    distance_to_atm_points: float
    distance_to_atm_ratio: float
    moneyness_bucket: str
    expiry_bucket: str
    liquidity_score: float
    liquidity_weight: float
    reliability_weight: float
    option_multiplier: float
    signal: float
    signal_confidence: float
    signal_mode: str
    signal_reason: str
    observed_vanna: float | None = None   # EFF_VANNA — ∂Δ/∂σ do modelo proprietario
    observed_charm: float | None = None   # EFF_CHARM — ∂Δ/∂t por DU-252
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModelRunConfig:
    sign_convention: str
    grid_range_pct: float
    grid_points: int
    gex_weight: float
    vex_weight: float
    cex_weight: float
    option_multiplier: float
    win_point_value: float
    min_time_years: float
    vol_epsilon: float
    time_epsilon_days: float
