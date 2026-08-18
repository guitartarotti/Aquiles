from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GlobalAssetConfig:
    slug: str
    label: str
    primary_security: str
    region: str
    support_level: str = "C"
    weight: float = 1.0
    alternate_securities: tuple[str, ...] = field(default_factory=tuple)
    model_underlying: str | None = None
    trade_symbol: str | None = None
    use_future_space: bool = False


@dataclass(frozen=True)
class GlobalTriangulationConfig:
    bar_interval_minutes: int
    lookback_hours: int
    min_points: int
    ewma_alpha: float
    corr_short_window: int
    corr_smooth_window: int
    distortion_sigma_multiplier: float
    distortion_weight: float
    structural_weight: float
    corr_weight: float
    local_model_max_age_seconds: int
    level_cluster_points: float
    level_match_points: float
    min_corr_for_mapping: float
    vol_band_sigma: float
    top_mapped_levels: int
