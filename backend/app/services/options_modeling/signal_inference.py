from __future__ import annotations

from typing import Any

from .math_utils import clamp


def infer_signal(
    row: dict[str, Any],
    sign_convention: str,
    threshold: float,
) -> dict[str, Any]:
    convention = str(sign_convention or "neutral").strip().lower()
    if convention == "neutral":
        return {
            "signal": 1.0,
            "confidence": 0.0,
            "mode": "neutral",
            "reason": "Neutral convention keeps exposures unsigned and deterministic.",
            "raw_score": 0.0,
        }

    if convention == "dealer_short_optionality":
        return {
            "signal": -1.0,
            "confidence": 0.65,
            "mode": "dealer_short_optionality",
            "reason": "Configured hypothesis assumes dealers are structurally short customer optionality.",
            "raw_score": -1.0,
        }

    distance = float(row.get("distance_to_atm_ratio") or 1.0)
    liquidity_weight = float(row.get("liquidity_weight") or 0.0)
    reliability_weight = float(row.get("reliability_weight") or 0.0)
    volume = float(row.get("px_volume") or 0.0)
    spread_pct = float(row.get("spread_pct") or 1.0)
    days = max(int(row.get("days_to_expiry_business") or 0), 0)
    oi_change_pct = row.get("oi_change_pct")
    oi_change_pct = float(oi_change_pct) if oi_change_pct not in (None, "") else 0.0

    atm_score = clamp(1.0 - (distance / 0.08), 0.0, 1.0)
    expiry_score = clamp(1.0 - (days / 120.0), 0.0, 1.0)
    volume_score = clamp(volume / 100000.0, 0.0, 1.0)
    spread_penalty = clamp(spread_pct / 0.15, 0.0, 1.0)
    oi_score = clamp(abs(oi_change_pct) / 0.25, 0.0, 1.0)

    customer_optional_demand = (
        0.26 * atm_score
        + 0.18 * expiry_score
        + 0.18 * volume_score
        + 0.18 * liquidity_weight
        + 0.12 * reliability_weight
        + 0.08 * oi_score
        - 0.15 * spread_penalty
    )
    customer_optional_demand = clamp(customer_optional_demand, 0.0, 1.0)

    if customer_optional_demand < threshold:
        return {
            "signal": 1.0,
            "confidence": customer_optional_demand,
            "mode": "heuristic_fallback_neutral",
            "reason": "Heuristic confidence is too low, so the run falls back to the neutral sign convention.",
            "raw_score": 1.0,
        }

    signal = -(0.20 + 0.80 * customer_optional_demand)
    return {
        "signal": clamp(signal, -1.0, 1.0),
        "confidence": customer_optional_demand,
        "mode": "heuristic",
        "reason": "High liquidity, ATM proximity, front-tenor relevance and fresh activity raise the probability that dealers are short optionality in this bucket.",
        "raw_score": signal,
    }
