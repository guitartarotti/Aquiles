from __future__ import annotations

from typing import Any

from .types import FairValueRunConfig


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _normalize_score(value: float) -> float:
    if abs(value) <= 1.0:
        return value
    return max(-1.0, min(1.0, value / 100.0))


def build_global_distortion_overlay(
    current_future_price: float,
    current_sigma_points: float,
    global_run: dict[str, Any] | None,
    run_config: FairValueRunConfig,
) -> dict[str, Any]:
    payload = global_run or {}
    if not payload:
        return {
            "enabled": False,
            "state": "no_global_context",
            "confidence": 0.0,
            "fair_value_global_adjustment": 0.0,
        }

    summary = payload.get("summary") or {}
    desk = summary.get("desk_summary") or {}
    distortion_z = _safe_float(summary.get("distortion_zscore"), 0.0)
    absorption = _normalize_score(_safe_float(summary.get("global_absorption_score"), 0.0))
    breakout = _normalize_score(_safe_float(summary.get("global_breakout_score"), 0.0))
    sync = _normalize_score(_safe_float(summary.get("global_sync_score"), 0.0))
    regime_confidence = _safe_float(summary.get("global_regime_confidence"), 0.0)

    if abs(distortion_z) < 0.75:
        state = "synced_global"
    elif distortion_z > 0 and absorption >= breakout:
        state = "local_ahead_mean_reversion"
    elif distortion_z < 0 and absorption >= breakout:
        state = "local_lagging_catchup"
    elif distortion_z > 0:
        state = "global_breakout_confirmed_up"
    else:
        state = "global_breakout_confirmed_down"

    distortion_strength = min(abs(distortion_z) / 3.0, 1.0)
    mean_reversion_bias = absorption - breakout
    raw_adjustment = (
        -1.0
        * (1.0 if distortion_z >= 0 else -1.0)
        * distortion_strength
        * mean_reversion_bias
        * current_sigma_points
        * run_config.global_overlay_weight
    )
    cap_points = max(current_sigma_points * run_config.global_max_sigma_mult, 150.0)
    adjustment_points = max(-cap_points, min(cap_points, raw_adjustment))
    confidence = max(0.1, min(0.95, (0.55 * distortion_strength) + (0.30 * regime_confidence) + (0.15 * abs(sync))))

    return {
        "enabled": True,
        "state": state,
        "confidence": confidence,
        "distortion_zscore": distortion_z,
        "distortion_band_low": _safe_float(summary.get("distortion_band_low"), 0.0),
        "distortion_band_high": _safe_float(summary.get("distortion_band_high"), 0.0),
        "desk_view": desk.get("indice_local_vs_global"),
        "fair_value_global_adjustment": adjustment_points,
        "raw_adjustment_points": raw_adjustment,
        "cap_points": cap_points,
        "absorption_score": absorption,
        "breakout_score": breakout,
        "sync_score": sync,
        "top_explaining_assets": summary.get("top_explaining_assets") or desk.get("ativos_que_mais_explicam") or [],
    }
