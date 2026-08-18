from __future__ import annotations

import math
from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _row_map(latest_factor_rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("factor") or "").strip(): dict(item)
        for item in (latest_factor_rows or [])
        if str(item.get("factor") or "").strip()
    }


def _z(rows: dict[str, dict[str, Any]], factor: str) -> float:
    return _safe_float((rows.get(factor) or {}).get("feature_zscore"))


def _raw(rows: dict[str, dict[str, Any]], factor: str) -> float:
    return _safe_float((rows.get(factor) or {}).get("raw_value"))


def _daily_change(rows: dict[str, dict[str, Any]], factor: str) -> float:
    return _safe_float((rows.get(factor) or {}).get("daily_change_pct"))


def _factor_score(
    rows: dict[str, dict[str, Any]],
    factor: str,
    *,
    invert: bool = False,
    daily_scale: float = 0.25,
) -> float:
    row = rows.get(factor) or {}
    z_value = row.get("feature_zscore")
    if z_value is not None:
        score = _safe_float(z_value)
    else:
        score = _clamp(_daily_change(rows, factor) / max(daily_scale, 1e-6), -2.5, 2.5)
    return -score if invert else score


def _as_payload(name: str, score: float, raw_value: float, state: str, rationale: str) -> dict[str, Any]:
    return {
        "name": name,
        "score": score,
        "raw_value": raw_value,
        "state": state,
        "confidence": _clamp(0.30 + (0.16 * abs(score)), 0.20, 0.95),
        "rationale": rationale,
    }


def build_us_rates_factor_context(latest_factor_rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = _row_map(latest_factor_rows)
    if not rows:
        return {
            "available": False,
            "confidence_multiplier": 1.0,
            "band_width_multiplier": 1.0,
            "convergence_probability_multiplier": 1.0,
            "risk_quality_score": 0.50,
            "explanation": {
                "summary": "US rates context unavailable.",
                "bullish_forces": [],
                "bearish_forces": [],
                "warnings": ["No US rates factor rows available."],
            },
        }

    treasury_short_support = _factor_score(rows, "usgg2_treasury", invert=True)
    treasury_long_support = _factor_score(rows, "usgg10_treasury", invert=True)
    dovish_short = _factor_score(rows, "us_ois_short_factor", invert=True)
    dovish_long = _factor_score(rows, "us_ois_long_factor", invert=True)
    dxy = _factor_score(rows, "dxy_index")
    move = _factor_score(rows, "move_index")
    jpy = _factor_score(rows, "jpy_basket")

    treasury_support = (treasury_short_support + treasury_long_support) / 2.0
    ois_support = (dovish_short + dovish_long) / 2.0
    policy_support = _z(rows, "us_monetary_policy_factor")
    if not policy_support:
        policy_support = dovish_short - dovish_long
    policy_support = -policy_support
    term_premium_pressure = _z(rows, "us_term_premium_factor")
    if not term_premium_pressure:
        term_premium_pressure = max((-treasury_support) - ois_support, 0.0) + max(dovish_short - dovish_long, 0.0) * 0.5
    liquidity_pressure = _z(rows, "us_rates_liquidity_factor")
    if not liquidity_pressure:
        liquidity_pressure = max(term_premium_pressure, 0.0) + max(move, 0.0) * 0.35
    divergence_pressure = _z(rows, "treasury_vs_ois_divergence")
    if not divergence_pressure:
        divergence_pressure = abs(treasury_support - ois_support) * (1.0 if ois_support < 0 or treasury_support < 0 else -0.35)
    funding = _z(rows, "funding_stress_factor")
    funding_pressure = max(funding, (max(move, 0.0) + max(dxy, 0.0) + max(jpy, 0.0)) / 3.0, max(liquidity_pressure, 0.0))

    policy_state = "dovish_supportive" if policy_support > 0.35 else "hawkish_tightening" if policy_support < -0.35 else "neutral_policy"
    divergence_state = "widening_stress" if divergence_pressure > 0.35 else "narrowing_relief" if divergence_pressure < -0.35 else "stable_spread"
    funding_state = "tightening" if funding_pressure > 0.45 else "relaxing" if funding_pressure < -0.45 else "balanced"

    risk_quality_score = _clamp(
        0.58
        + (0.12 * treasury_support)
        + (0.12 * ois_support)
        + (0.10 * policy_support)
        - (0.12 * funding_pressure)
        - (0.10 * term_premium_pressure)
        - (0.06 * divergence_pressure),
        0.05,
        0.95,
    )

    confidence_multiplier = _clamp(
        1.0
        - (0.10 * max(funding_pressure, 0.0))
        - (0.08 * max(divergence_pressure, 0.0))
        + (0.04 * max(ois_support, 0.0)),
        0.72,
        1.08,
    )
    band_width_multiplier = _clamp(
        1.0
        + (0.14 * max(funding_pressure, 0.0))
        + (0.10 * max(divergence_pressure, 0.0))
        + (0.08 * max(move, 0.0))
        - (0.06 * max(ois_support, 0.0)),
        0.86,
        1.45,
    )
    convergence_probability_multiplier = _clamp(
        1.0
        + (0.10 * max(ois_support, 0.0))
        + (0.06 * max(treasury_support, 0.0))
        - (0.14 * max(funding_pressure, 0.0))
        - (0.08 * max(divergence_pressure, 0.0)),
        0.70,
        1.18,
    )

    bullish_forces: list[str] = []
    bearish_forces: list[str] = []
    warnings: list[str] = []

    if ois_support > 0.45:
        bullish_forces.append("SOFR OIS caiu de forma consistente, sugerindo Fed mais dovish e funding mais benigno.")
    elif ois_support < -0.45:
        bearish_forces.append("SOFR OIS abriu, sugerindo aperto implícito de política monetária e piora de funding.")

    if treasury_support > 0.35 and ois_support > 0.25:
        bullish_forces.append("Treasuries e OIS caem juntos, configurando cenário dovish / risk-on mais saudável.")
    elif treasury_support > 0.35 and ois_support < -0.20:
        warnings.append("Treasuries aliviam, mas OIS sobe: leitura mais próxima de flight-to-quality com funding piorando.")
    elif funding_pressure > 0.55 and dxy > 0.30:
        bearish_forces.append("OIS, MOVE e DXY apontam aperto financeiro global e pior qualidade para convergência.")

    if divergence_pressure > 0.40:
        warnings.append("Treasury vs OIS abriu, sugerindo aumento de prêmio de prazo ou stress de liquidez.")
    elif divergence_pressure < -0.35:
        bullish_forces.append("Treasury vs OIS estreitou, favorecendo leitura de melhora de liquidez.")

    summary = (
        "US rates/OIS em regime neutro."
        if not bullish_forces and not bearish_forces and not warnings
        else " | ".join((bullish_forces + bearish_forces + warnings)[:3])
    )

    return {
        "available": True,
        "us_ois_short_factor": _as_payload(
            "us_ois_short_factor",
            dovish_short,
            _raw(rows, "us_ois_short_factor"),
            "dovish_supportive" if dovish_short > 0.35 else "tightening" if dovish_short < -0.35 else "balanced",
            "Queda do SOFR OIS 2Y tende a ajudar equities/EM; alta tende a sinalizar aperto.",
        ),
        "us_ois_long_factor": _as_payload(
            "us_ois_long_factor",
            dovish_long,
            _raw(rows, "us_ois_long_factor"),
            "long_end_relief" if dovish_long > 0.35 else "long_end_stress" if dovish_long < -0.35 else "balanced",
            "Queda do SOFR OIS 10Y melhora a leitura estrutural de funding; alta piora.",
        ),
        "us_monetary_policy_factor": _as_payload(
            "us_monetary_policy_factor",
            policy_support,
            _raw(rows, "us_monetary_policy_factor"),
            policy_state,
            "Captura inclinação da curva OIS e velocidade de repricing implícito de Fed.",
        ),
        "us_term_premium_factor": _as_payload(
            "us_term_premium_factor",
            -term_premium_pressure,
            _raw(rows, "us_term_premium_factor"),
            "premium_relief" if term_premium_pressure < -0.35 else "premium_stress" if term_premium_pressure > 0.35 else "stable",
            "Abertura de Treasury vs OIS sugere prêmio de prazo / stress; fechamento sugere alívio.",
        ),
        "us_rates_liquidity_factor": _as_payload(
            "us_rates_liquidity_factor",
            -liquidity_pressure,
            _raw(rows, "us_rates_liquidity_factor"),
            "liquidity_relief" if liquidity_pressure < -0.35 else "liquidity_stress" if liquidity_pressure > 0.35 else "balanced",
            "Proxy de liquidez em rates via prêmio de prazo e divergência Treasury/OIS.",
        ),
        "treasury_vs_ois_divergence": _as_payload(
            "treasury_vs_ois_divergence",
            -divergence_pressure,
            _raw(rows, "treasury_vs_ois_divergence"),
            divergence_state,
            "Widening do spread sugere stress fiscal/liquidez; narrowing sugere melhora.",
        ),
        "funding_stress_factor": _as_payload(
            "funding_stress_factor",
            -funding_pressure,
            _raw(rows, "funding_stress_factor"),
            funding_state,
            "Combina OIS, Treasury vs OIS, MOVE, DXY e JPY para medir aperto financeiro global.",
        ),
        "treasury_support_score": treasury_support,
        "ois_support_score": ois_support,
        "funding_pressure_score": funding_pressure,
        "confidence_multiplier": confidence_multiplier,
        "band_width_multiplier": band_width_multiplier,
        "convergence_probability_multiplier": convergence_probability_multiplier,
        "risk_quality_score": risk_quality_score,
        "summary_state": (
            "dovish_risk_on"
            if ois_support > 0.45 and treasury_support > 0.25 and funding_pressure < 0.15
            else "funding_deterioration"
            if funding_pressure > 0.55
            else "flight_to_quality"
            if treasury_support > 0.35 and ois_support < -0.20
            else "mixed_us_rates"
        ),
        "explanation": {
            "summary": summary,
            "bullish_forces": bullish_forces,
            "bearish_forces": bearish_forces,
            "warnings": warnings,
        },
    }
