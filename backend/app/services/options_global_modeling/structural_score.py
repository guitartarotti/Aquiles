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


def build_structural_scores(
    asset_states: list[dict[str, Any]],
    dynamic_model: dict[str, Any],
    distortion_band: dict[str, Any],
) -> dict[str, Any]:
    relationship_map = {
        str(item.get("slug")): item
        for item in (dynamic_model.get("relationships") or [])
        if item.get("slug")
    }
    local_state = next((asset for asset in asset_states if asset.get("asset") == "local_index"), None) or {}
    local_return = _safe_float(dynamic_model.get("local_return"), 0.0)
    expected_return = _safe_float(dynamic_model.get("basket_expected_return"), 0.0)
    local_direction = 1 if local_return > 0 else -1 if local_return < 0 else 0

    weighted_absorption = 0.0
    weighted_breakout = 0.0
    weighted_sync = 0.0
    weighted_quality = 0.0
    alignment_weight = 0.0

    per_asset_scores: list[dict[str, Any]] = []
    for asset in asset_states:
        if asset.get("asset") == "local_index":
            rel = None
            direction_match = 1.0
            corr_smoothed = 1.0
            beta = 1.0
        else:
            rel = relationship_map.get(str(asset.get("asset")))
            corr_smoothed = _safe_float((rel or {}).get("corr_smoothed"), 0.0)
            beta = _safe_float((rel or {}).get("beta"), 0.0)
            asset_direction = 1 if _safe_float(asset.get("latest_return"), 0.0) > 0 else -1 if _safe_float(asset.get("latest_return"), 0.0) < 0 else 0
            predicted_local_direction = 1 if (beta * _safe_float(asset.get("latest_return"), 0.0)) > 0 else -1 if (beta * _safe_float(asset.get("latest_return"), 0.0)) < 0 else 0
            direction_match = 1.0 if local_direction == 0 or predicted_local_direction == local_direction or asset_direction == local_direction else 0.0

        support_multiplier = 1.15 if asset.get("support_level") == "A" else 0.90 if asset.get("support_level") == "B" else 0.70
        weight = max(_safe_float(asset.get("state_quality_score"), 0.0), 0.05) * support_multiplier
        absorption = _safe_float(asset.get("local_absorption_score"), 0.0)
        breakout = _safe_float(asset.get("local_breakout_score"), 0.0)
        sync_component = _clamp(max(corr_smoothed, 0.0) * direction_match, 0.0, 1.0)

        weighted_absorption += weight * absorption
        weighted_breakout += weight * breakout
        weighted_sync += weight * sync_component
        weighted_quality += weight
        if asset.get("dealer_regime_state") in {"compression", "absorption", "release", "breakout"}:
            alignment_weight += weight

        per_asset_scores.append(
            {
                "asset": asset.get("asset"),
                "label": asset.get("label"),
                "support_level": asset.get("support_level"),
                "beta_to_local": beta if asset.get("asset") != "local_index" else 1.0,
                "corr_short": _safe_float((rel or {}).get("corr_short"), 1.0 if asset.get("asset") == "local_index" else 0.0),
                "corr_smoothed": corr_smoothed,
                "absorption_score": absorption,
                "breakout_score": breakout,
                "sync_component": sync_component,
            }
        )

    denom = max(weighted_quality, 1e-8)
    global_absorption_score = 100.0 * (weighted_absorption / denom)
    global_breakout_score = 100.0 * (weighted_breakout / denom)
    global_sync_score = 100.0 * (weighted_sync / denom)
    corr_regime_score = 100.0 * _clamp(abs(_safe_float(dynamic_model.get("global_corr_smoothed"), 0.0)), 0.0, 1.0)
    distortion_abs = abs(_safe_float(distortion_band.get("distortion_zscore"), 0.0))
    distortion_penalty = min(distortion_abs / 3.0, 1.0) * 100.0
    structural_gamma_vol_score = _clamp(
        (0.50 * global_breakout_score)
        + (0.30 * global_sync_score)
        + (0.20 * max(0.0, 100.0 - distortion_penalty)),
        0.0,
        100.0,
    )

    if alignment_weight / denom >= 0.66:
        zone_alignment = "sim"
    elif alignment_weight / denom >= 0.38:
        zone_alignment = "parcial"
    else:
        zone_alignment = "nao"

    local_absorption = _safe_float(local_state.get("local_absorption_score"), 0.0)
    local_breakout = _safe_float(local_state.get("local_breakout_score"), 0.0)
    global_absorption_score = _clamp((0.75 * global_absorption_score) + (25.0 * local_absorption), 0.0, 100.0)
    global_breakout_score = _clamp((0.75 * global_breakout_score) + (25.0 * local_breakout), 0.0, 100.0)

    return {
        "global_absorption_score": global_absorption_score,
        "global_breakout_score": global_breakout_score,
        "global_sync_score": global_sync_score,
        "corr_regime_score": corr_regime_score,
        "structural_gamma_vol_score": structural_gamma_vol_score,
        "zone_alignment": zone_alignment,
        "per_asset_scores": per_asset_scores,
        "local_direction": local_direction,
        "expected_direction": 1 if expected_return > 0 else -1 if expected_return < 0 else 0,
    }
