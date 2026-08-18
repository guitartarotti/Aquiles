from __future__ import annotations

from typing import Any


def build_regime_price_making_response(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    summary = dict(payload.get("summary") or {})
    return {
        "timestamp": payload.get("captured_at") or summary.get("timestamp"),
        "underlying_security": payload.get("underlying_security"),
        "global_regime": payload.get("global_regime") or summary.get("global_regime"),
        "global_regime_score": payload.get("global_regime_score") or summary.get("global_regime_score"),
        "global_regime_confidence": payload.get("global_regime_confidence") or summary.get("global_regime_confidence"),
        "second_best_regime": payload.get("second_best_regime"),
        "second_best_score": payload.get("second_best_score"),
        "price_making_summary": payload.get("price_making_summary") or {},
        "market_state": payload.get("market_state") or {},
        "legs": payload.get("legs") or {},
        "warnings": payload.get("warnings") or [],
        "explanation": payload.get("explanation") or {},
        "regime_multipliers": payload.get("regime_multipliers") or {},
    }


def build_price_making_response(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    legs = dict(payload.get("legs") or {})
    return {
        "timestamp": payload.get("captured_at"),
        "underlying_security": payload.get("underlying_security"),
        "legs": legs,
        "ranking": sorted(
            [
                {
                    "name": key,
                    "label": value.get("label") or key,
                    "type": value.get("type"),
                    "price_making_score": value.get("price_making_score"),
                    "status": value.get("status"),
                    "state": value.get("state"),
                    "contribution_points": value.get("contribution_points"),
                    "implied_fair_value_xb1": value.get("implied_fair_value_xb1"),
                }
                for key, value in legs.items()
            ],
            key=lambda item: float(item.get("price_making_score") or 0.0),
            reverse=True,
        ),
    }


def build_nonlinear_dependence_response(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    legs = dict(payload.get("legs") or {})
    return {
        "timestamp": payload.get("captured_at"),
        "underlying_security": payload.get("underlying_security"),
        "legs": {
            key: {
                "label": value.get("label") or key,
                "type": value.get("type"),
                "pearson_corr": value.get("linear_corr"),
                "spearman_corr": value.get("spearman_corr"),
                "distance_corr": value.get("distance_corr"),
                "tail_dependence": value.get("tail_dependence"),
                "quantile_beta": value.get("rolling_beta"),
                "best_lag_minutes": value.get("lead_lag_minutes"),
                "dependence_windows": value.get("dependence_windows") or {},
                "confidence": value.get("confidence"),
            }
            for key, value in legs.items()
        },
    }


def build_market_state_response(payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = dict(payload or {})
    snapshot = dict(payload.get("market_state_snapshot") or {})
    return {
        "timestamp": payload.get("captured_at"),
        "underlying_security": payload.get("underlying_security"),
        "acceleration_score": snapshot.get("acceleration_score"),
        "exhaustion_score": snapshot.get("exhaustion_score"),
        "absorption_score": snapshot.get("absorption_score"),
        "consolidation_score": snapshot.get("consolidation_score"),
        "reversal_score": snapshot.get("reversal_score"),
        "divergence_score": snapshot.get("divergence_score"),
        "latent_stress_score": snapshot.get("latent_stress_score"),
        "selected_state": snapshot.get("selected_state"),
        "confidence": snapshot.get("confidence"),
        "direction": snapshot.get("direction"),
        "explanation": snapshot.get("reason"),
    }
