from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    return parsed if parsed == parsed else default


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _sigmoid(value: float) -> float:
    import math

    return 1.0 / (1.0 + math.exp(-value))


def build_global_regime(
    *,
    core_scores: dict[str, float],
    shadow_scores: dict[str, float],
    price_making_scores: dict[str, float],
    market_state: dict[str, Any],
    risk_quality_score: float,
    dislocation_zscore: float,
    price_vs_core_fv: float,
    price_vs_quality_fv: float,
    core_shadow_alignment: float,
    divergence_score: float,
) -> dict[str, Any]:
    equity = core_scores.get("equity", 0.0)
    fx = core_scores.get("fx", 0.0)
    credit = core_scores.get("credit", 0.0)
    rates = core_scores.get("rates", 0.0)
    commodities = core_scores.get("commodities", 0.0)
    us_rates = core_scores.get("us_rates", 0.0)
    funding = shadow_scores.get("funding", 0.0)
    volatility = shadow_scores.get("volatility", 0.0)
    em_stress = shadow_scores.get("em_stress", 0.0)
    credit_shadow = shadow_scores.get("credit_shadow", 0.0)
    sovereign = shadow_scores.get("sovereign_credit", 0.0)
    brazil_relative = shadow_scores.get("brazil_relative", 0.0)

    bullish_pm = max(price_making_scores.values()) if price_making_scores else 0.0
    bearish_pm = min(price_making_scores.values()) if price_making_scores else 0.0
    market_state_name = str(market_state.get("selected_state") or "neutral")
    market_state_conf = _safe_float(market_state.get("confidence"), 0.0)

    scores = {
        "risk_on_confirmed": _sigmoid(
            equity + fx + credit + commodities + us_rates + bullish_pm - volatility - funding - divergence_score
        ),
        "risk_on_fragile": _sigmoid(
            equity + fx + credit + 0.5 * commodities + abs(price_vs_core_fv) + divergence_score + market_state_conf
            - volatility - funding - core_shadow_alignment
        ),
        "risk_off_confirmed": _sigmoid(
            (-equity) + (-fx) + (-credit) + (-rates) + volatility + funding + em_stress + abs(bearish_pm)
        ),
        "risk_off_fragile": _sigmoid(
            (-equity) + (-fx) + volatility + funding + divergence_score + abs(price_vs_quality_fv)
        ),
        "brazil_idiosyncratic_stress": _sigmoid(max(-rates, 0.0) + max(-fx, 0.0) + sovereign - em_stress + abs(brazil_relative)),
        "em_stress": _sigmoid(em_stress + credit_shadow + funding + volatility),
        "global_funding_stress": _sigmoid(funding + volatility + abs(us_rates) + em_stress),
        "commodities_support": _sigmoid(commodities + max(equity, 0.0) + max(credit, 0.0)),
        "rates_pressure": _sigmoid(abs(rates) + abs(us_rates) + funding),
        "credit_warning": _sigmoid(credit_shadow + sovereign + em_stress + volatility),
        "divergent": _sigmoid(divergence_score + (1.0 - core_shadow_alignment) + abs(price_vs_quality_fv - price_vs_core_fv)),
        "latent_stress": _sigmoid(
            shadow_scores.get("volatility", 0.0)
            + shadow_scores.get("funding", 0.0)
            + market_state.get("latent_stress_score", 0.0)
            - abs(price_vs_core_fv)
        ),
        "recovery_candidate": _sigmoid(max(equity, 0.0) + max(fx, 0.0) + max(credit, 0.0) + max(price_vs_core_fv, 0.0)),
        "overextended_fragile": _sigmoid(max(-price_vs_core_fv, 0.0) + volatility + funding + divergence_score),
        "neutral": _sigmoid(risk_quality_score - abs(dislocation_zscore)),
    }
    scaled_scores = {name: round(_clamp(value * 100.0, 0.0, 100.0), 4) for name, value in scores.items()}
    ordered = sorted(scaled_scores.items(), key=lambda item: item[1], reverse=True)
    dominant_regime, dominant_score = ordered[0]
    second_regime, second_score = ordered[1]
    if abs(dominant_score - second_score) <= 4.5:
        dominant_regime = "divergent"
        dominant_score = max(dominant_score, scaled_scores.get("divergent", dominant_score))
    summary = {
        "global_regime": dominant_regime,
        "global_regime_score": dominant_score,
        "global_regime_confidence": round(_clamp((0.45 * risk_quality_score) + (0.35 * market_state_conf) + (0.20 * (dominant_score / 100.0)), 0.05, 0.98), 6),
        "second_best_regime": second_regime,
        "second_best_score": second_score,
        "regime_scores": scaled_scores,
        "market_state_context": market_state_name,
    }
    return summary
