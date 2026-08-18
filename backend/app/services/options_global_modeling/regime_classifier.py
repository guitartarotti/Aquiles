from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def classify_global_regime(
    *,
    dynamic_model: dict[str, Any],
    distortion_band: dict[str, Any],
    structural_scores: dict[str, Any],
    asset_states: list[dict[str, Any]],
) -> dict[str, Any]:
    absorption = _safe_float(structural_scores.get("global_absorption_score"), 0.0)
    breakout = _safe_float(structural_scores.get("global_breakout_score"), 0.0)
    sync_score = _safe_float(structural_scores.get("global_sync_score"), 0.0)
    corr_score = _safe_float(structural_scores.get("corr_regime_score"), 0.0)
    distortion_z = _safe_float(distortion_band.get("distortion_zscore"), 0.0)
    distortion_abs = abs(distortion_z)
    expected_return = _safe_float(dynamic_model.get("basket_expected_return"), 0.0)
    local_state = next((asset for asset in asset_states if asset.get("asset") == "local_index"), {}) or {}
    local_regime = str(local_state.get("dealer_regime_state") or "")
    local_breakout = _safe_float(local_state.get("local_breakout_score"), 0.0) * 100.0
    local_absorption = _safe_float(local_state.get("local_absorption_score"), 0.0) * 100.0

    regime = "FRAGMENTED_REGIME"
    confidence = 0.45
    breakout_score = _clamp((0.55 * breakout) + (0.25 * sync_score) + (0.20 * corr_score) - (12.0 * max(distortion_abs - 1.0, 0.0)), 0.0, 100.0)
    absorption_score = _clamp((0.60 * absorption) + (0.20 * sync_score) + (0.20 * max(0.0, 100.0 - (distortion_abs * 22.0))), 0.0, 100.0)

    if breakout_score >= 72.0 and sync_score >= 60.0 and distortion_abs < 2.0:
        regime = "GLOBAL_BREAKOUT_CONFIRMED"
        confidence = _clamp((breakout_score + sync_score) / 200.0, 0.0, 1.0)
    elif absorption_score >= 70.0 and local_regime in {"compression", "absorption"}:
        regime = "GLOBAL_ABSORPTION"
        confidence = _clamp((absorption_score + max(0.0, 100.0 - distortion_abs * 15.0)) / 200.0, 0.0, 1.0)
    elif distortion_abs >= 2.2 and sync_score < 52.0 and breakout < 58.0:
        regime = "LOCAL_FALSE_BREAKOUT" if local_breakout >= local_absorption else "LOCAL_MEAN_REVERSION_SETUP"
        confidence = _clamp((min(distortion_abs / 3.5, 1.0) + (1.0 - (sync_score / 100.0))) / 2.0, 0.0, 1.0)
    elif local_regime == "compression" and absorption_score >= 62.0:
        regime = "GAMMA_COMPRESSION"
        confidence = _clamp((absorption_score + local_absorption) / 200.0, 0.0, 1.0)
    elif local_regime == "release" and breakout_score >= 58.0:
        regime = "GAMMA_RELEASE"
        confidence = _clamp((breakout_score + local_breakout) / 200.0, 0.0, 1.0)
    elif sync_score >= 60.0:
        regime = "SYNCED_RISK_ON" if expected_return >= 0 else "SYNCED_RISK_OFF"
        confidence = _clamp((sync_score + corr_score) / 200.0, 0.0, 1.0)

    return {
        "global_regime": regime,
        "global_regime_confidence": confidence,
        "global_breakout_score": breakout_score,
        "global_absorption_score": absorption_score,
    }
