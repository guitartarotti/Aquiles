from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FairValueFactorDefinition:
    name: str
    label: str
    block: str
    source_kind: str
    source_key: str
    transform: str = "return"
    weight: float = 1.0
    economic_name: str = ""
    asset_class: str = ""
    subclass: str = ""
    model_layer: str = "core"
    expected_direction_to_ibov: str = ""
    purpose: str = ""


@dataclass(frozen=True)
class FairValueRunConfig:
    lookback_hours: int
    max_snapshots: int
    min_points: int
    zscore_window: int
    feature_min_coverage_ratio: float
    feature_min_coverage_floor: int
    factor_run_fill_tolerance_minutes: float
    engine_mode: str
    intraday_anchor_type: str
    rls_forgetting: float
    rls_init_covariance: float
    residual_sigma_halflife: float
    state_space_measurement_noise: float
    state_space_process_noise: float
    breadth_scale_floor: float
    breadth_warmup_minutes: float
    band_sigma_multiplier: float
    band_floor_points: float
    band_vol_weight: float
    options_overlay_weight: float
    global_overlay_weight: float
    residual_overlay_weight: float
    options_max_sigma_mult: float
    global_max_sigma_mult: float
    residual_max_sigma_mult: float
