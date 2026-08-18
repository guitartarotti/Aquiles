from __future__ import annotations

import math
from typing import Any


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-value))


def build_fair_value_output(
    *,
    underlying_security: str,
    current_future_price: float,
    basis_points: float,
    current_price_source: str | None,
    current_price_timestamp: str | None,
    structural_snapshot_timestamp: str | None,
    structural_model: dict[str, Any],
    residual_ml: dict[str, Any],
    options_overlay: dict[str, Any],
    global_overlay: dict[str, Any],
    regime: dict[str, Any],
    band: dict[str, Any],
    us_rates_context: dict[str, Any] | None,
) -> dict[str, Any]:
    fair_value_structural_future = float(structural_model["fair_value_structural"])
    fair_value_tactical_future = (
        fair_value_structural_future
        + float(options_overlay.get("fair_value_options_adjustment") or 0.0)
        + float(global_overlay.get("fair_value_global_adjustment") or 0.0)
    )
    fair_value_final_future = fair_value_tactical_future + float(
        residual_ml.get("fair_value_residual_adjustment") or 0.0
    )
    fair_value_structural_spot = fair_value_structural_future - basis_points
    fair_value_tactical_spot = fair_value_tactical_future - basis_points
    fair_value_final_spot = fair_value_final_future - basis_points

    mispricing_value = current_future_price - fair_value_final_future
    mispricing_pct = (mispricing_value / fair_value_final_future) if fair_value_final_future else 0.0
    residual_sigma_points = max(float(structural_model.get("residual_sigma_points") or 1.0), 1.0)
    mispricing_zscore = mispricing_value / residual_sigma_points

    block_contributions = {
        "macro_structural": structural_model.get("block_contributions_points") or {},
        "options_overlay": float(options_overlay.get("fair_value_options_adjustment") or 0.0),
        "global_overlay": float(global_overlay.get("fair_value_global_adjustment") or 0.0),
        "residual_ml": float(residual_ml.get("fair_value_residual_adjustment") or 0.0),
    }

    ranking = structural_model.get("ranking") or []
    top_factors = ranking[:6]

    compression_probability = min(
        0.98,
        max(
            0.02,
            (0.65 * float(options_overlay.get("confidence") or 0.0))
            if options_overlay.get("state") == "gamma_compression"
            else 0.12,
        ),
    )
    release_probability = min(
        0.98,
        max(
            0.02,
            (0.65 * float(options_overlay.get("confidence") or 0.0))
            if str(options_overlay.get("state") or "").startswith("gamma_release")
            else 0.12,
        ),
    )
    reversion_probability = min(
        0.98,
        max(
            0.02,
            _sigmoid(abs(mispricing_zscore) - 0.8)
            * (0.55 + 0.45 * float(global_overlay.get("confidence") or 0.0))
            * (0.8 if str(global_overlay.get("state") or "").startswith("global_breakout") else 1.0),
        ),
    )
    breakout_probability = min(
        0.98,
        max(
            0.02,
            _sigmoid(abs(mispricing_zscore) - 0.9)
            * max(float(global_overlay.get("confidence") or 0.0), float(options_overlay.get("confidence") or 0.0))
            * (1.2 if str(global_overlay.get("state") or "").startswith("global_breakout") else 0.75),
        ),
    )
    us_rates_context = us_rates_context or {}
    convergence_probability = min(
        0.98,
        max(
            0.02,
            reversion_probability * max(float(us_rates_context.get("convergence_probability_multiplier") or 1.0), 0.5),
        ),
    )
    confidence = min(
        0.98,
        max(
            0.08,
            float(structural_model.get("confidence") or 0.35)
            * max(float(us_rates_context.get("confidence_multiplier") or 1.0), 0.5)
            * (0.88 + (0.12 * float(regime.get("market_regime_confidence") or 0.35))),
        ),
    )
    risk_quality_score = min(
        0.98,
        max(
            0.05,
            (0.42 * confidence)
            + (0.33 * float(us_rates_context.get("risk_quality_score") or 0.5))
            + (0.25 * float(regime.get("market_regime_confidence") or 0.35)),
        ),
    )

    desk_summary = {
        "current_future_price": current_future_price,
        "current_price_source": current_price_source,
        "current_price_timestamp": current_price_timestamp,
        "structural_snapshot_timestamp": structural_snapshot_timestamp,
        "fair_value_final_future": fair_value_final_future,
        "mispricing_points": mispricing_value,
        "mispricing_zscore": mispricing_zscore,
        "fair_value_band_low": band.get("fair_value_band_low"),
        "fair_value_band_high": band.get("fair_value_band_high"),
        "market_regime": regime.get("market_regime"),
        "top_factors": [item.get("label") for item in top_factors[:3]],
        "confidence": confidence,
        "risk_quality_score": risk_quality_score,
    }
    us_explanation = us_rates_context.get("explanation") or {}
    top_bullish = [
        item.get("label")
        for item in top_factors
        if float(item.get("contribution_points") or 0.0) > 0
    ][:3]
    top_bearish = [
        item.get("label")
        for item in top_factors
        if float(item.get("contribution_points") or 0.0) < 0
    ][:3]
    regime_rationale = list(regime.get("rationale") or [])
    explanation = {
        "summary": str(us_explanation.get("summary") or (regime_rationale[0] if regime_rationale else "Structural fair value active.")),
        "bullish_forces": list(us_explanation.get("bullish_forces") or []) + top_bullish,
        "bearish_forces": list(us_explanation.get("bearish_forces") or []) + top_bearish,
        "warnings": list(us_explanation.get("warnings") or []),
    }

    return {
        "underlying_security": underlying_security,
        "model_mode": structural_model.get("engine_mode") or "intraday_anchor",
        "anchor_xb1": structural_model.get("anchor_xb1"),
        "session_anchor_xb1": structural_model.get("session_anchor_xb1") or structural_model.get("anchor_xb1"),
        "anchor_type": structural_model.get("anchor_type"),
        "intraday_anchor_type": structural_model.get("intraday_anchor_type"),
        "current_future_price": current_future_price,
        "current_price_source": current_price_source,
        "current_price_timestamp": current_price_timestamp,
        "structural_snapshot_timestamp": structural_snapshot_timestamp,
        "current_spot_equivalent": current_future_price - basis_points,
        "basis_points": basis_points,
        "fair_value_structural_future": fair_value_structural_future,
        "fair_value_tactical_future": fair_value_tactical_future,
        "fair_value_final_future": fair_value_final_future,
        "fair_value_structural_spot": fair_value_structural_spot,
        "fair_value_tactical_spot": fair_value_tactical_spot,
        "fair_value_final_spot": fair_value_final_spot,
        "mispricing_value": mispricing_value,
        "mispricing": mispricing_value,
        "mispricing_pct": mispricing_pct,
        "mispricing_zscore": mispricing_zscore,
        "dislocation_points": mispricing_value,
        "dislocation_pct": mispricing_pct,
        "zscore_dislocation": mispricing_zscore,
        "is_price_above_fv": bool(current_future_price > fair_value_final_future),
        "fair_value_band_low": band.get("fair_value_band_low"),
        "fair_value_band_high": band.get("fair_value_band_high"),
        "fair_value_band_regime": band.get("fair_value_band_regime"),
        "market_regime": regime.get("market_regime"),
        "market_regime_confidence": regime.get("market_regime_confidence"),
        "dealer_pressure_state": options_overlay.get("state"),
        "dealer_pressure_confidence": options_overlay.get("confidence"),
        "global_distortion_state": global_overlay.get("state"),
        "global_distortion_confidence": global_overlay.get("confidence"),
        "reversion_probability": reversion_probability,
        "convergence_probability": convergence_probability,
        "breakout_probability": breakout_probability,
        "compression_probability": compression_probability,
        "release_probability": release_probability,
        "confidence": confidence,
        "model_confidence": confidence,
        "risk_quality_score": risk_quality_score,
        "factor_ranking": ranking,
        "top_factors": top_factors,
        "factor_expected_returns": structural_model.get("factor_expected_returns") or {},
        "factor_cumulative_contributions_from_anchor": structural_model.get("factor_cumulative_contributions_from_anchor") or {},
        "block_contributions": block_contributions,
        "us_rates_context": us_rates_context,
        "us_ois_short_factor": us_rates_context.get("us_ois_short_factor"),
        "us_ois_long_factor": us_rates_context.get("us_ois_long_factor"),
        "us_monetary_policy_factor": us_rates_context.get("us_monetary_policy_factor"),
        "us_term_premium_factor": us_rates_context.get("us_term_premium_factor"),
        "us_rates_liquidity_factor": us_rates_context.get("us_rates_liquidity_factor"),
        "treasury_vs_ois_divergence": us_rates_context.get("treasury_vs_ois_divergence"),
        "funding_stress_factor": us_rates_context.get("funding_stress_factor"),
        "residual_sigma_points": residual_sigma_points,
        "fair_value_intraday_anchor_future": structural_model.get("fair_value_intraday_anchor"),
        "fair_value_state_space_future": structural_model.get("fair_value_state_space"),
        "state_space": structural_model.get("state_space") or {},
        "explanation": explanation,
        "desk_summary": desk_summary,
    }
