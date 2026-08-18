from __future__ import annotations

from typing import Any

from .types import MarketContext, ModelRunConfig


def build_operational_output(
    underlying_security: str,
    market_context: MarketContext,
    run_config: ModelRunConfig,
    exposures: dict[str, Any],
    pressure: dict[str, Any],
    option_exposures: list[dict[str, Any]],
    dealer_inference: dict[str, Any] | None = None,
) -> dict[str, Any]:
    totals = exposures.get("totals") or {}
    signal_confidence = 0.0
    if option_exposures:
        signal_confidence = sum(
            float(item.get("option", {}).get("signal_confidence") or 0.0)
            * float(item.get("option", {}).get("reliability_weight") or 0.0)
            for item in option_exposures
        ) / max(len(option_exposures), 1)

    dex_total = float(totals.get("dex") or 0.0)
    payload = {
        "underlying_security": underlying_security,
        "spot_price": market_context.spot_price,
        "forward_price": market_context.forward_price,
        "future_basis_points": market_context.future_basis_points,
        "future_basis_pct": market_context.future_basis_pct,
        "interpolated_rate_curve": market_context.rate_curve_points,
        "carry_dividend_proxy_level": market_context.dividend_proxy_level,
        "dex_total": dex_total,
        "gex_total": float(totals.get("gex") or 0.0),
        "vex_total": float(totals.get("vex") or 0.0),
        "cex_total": float(totals.get("cex") or 0.0),
        "dex_notional_total": float(totals.get("dex_notional") or 0.0),
        "dex_notional_future_total": float(totals.get("dex_notional_forward") or 0.0),
        "gex_notional_total": float(totals.get("gex_notional") or 0.0),
        "gex_notional_future_total": float(totals.get("gex_notional_forward") or 0.0),
        "vex_notional_total": float(totals.get("vex_notional") or 0.0),
        "vex_notional_future_total": float(totals.get("vex_notional_forward") or 0.0),
        "cex_notional_total": float(totals.get("cex_notional") or 0.0),
        "cex_notional_future_total": float(totals.get("cex_notional_forward") or 0.0),
        "zero_pressure": pressure.get("zero_pressure"),
        "max_acceleration": pressure.get("max_acceleration"),
        "center_of_mass": pressure.get("center_of_mass"),
        "pinning_band": pressure.get("pinning_band"),
        "acceleration_band": pressure.get("acceleration_band"),
        "decompression_band": pressure.get("decompression_band"),
        "dominant_side": pressure.get("dominant_side"),
        "signal_confidence": signal_confidence,
        "win_delta_equivalent": dex_total / run_config.win_point_value if run_config.win_point_value else None,
        "weights": {
            "gex": run_config.gex_weight,
            "vex": run_config.vex_weight,
            "cex": run_config.cex_weight,
        },
    }
    if dealer_inference:
        payload["dealer_inference_comparison"] = dealer_inference.get("comparison") or {}
    return payload
