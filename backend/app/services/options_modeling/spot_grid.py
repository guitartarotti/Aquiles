from __future__ import annotations

from collections import defaultdict
from typing import Any

from .greeks_engine import calculate_full_greeks
from .types import ModelRunConfig, PreparedOption


def build_spot_grid(spot_price: float, range_pct: float, points: int) -> list[float]:
    if points < 3:
        points = 3
    lower = spot_price * (1.0 - abs(range_pct))
    upper = spot_price * (1.0 + abs(range_pct))
    step = (upper - lower) / (points - 1)
    return [lower + step * index for index in range(points)]


def reprice_grid(
    options: list[PreparedOption],
    run_config: ModelRunConfig,
) -> dict[str, Any]:
    if not options:
        return {"grid": [], "curve": []}
    spot_reference = options[0].spot_price
    grid = build_spot_grid(spot_reference, run_config.grid_range_pct, run_config.grid_points)
    curve: list[dict[str, Any]] = []

    for spot in grid:
        by_expiry: defaultdict[str, dict[str, float]] = defaultdict(lambda: {"dex": 0.0, "gex": 0.0, "vex": 0.0, "cex": 0.0})
        by_put_call: defaultdict[str, dict[str, float]] = defaultdict(lambda: {"dex": 0.0, "gex": 0.0, "vex": 0.0, "cex": 0.0})
        by_moneyness_bucket: defaultdict[str, dict[str, float]] = defaultdict(lambda: {"dex": 0.0, "gex": 0.0, "vex": 0.0, "cex": 0.0})
        totals = {"dex": 0.0, "gex": 0.0, "vex": 0.0, "cex": 0.0}

        for option in options:
            greeks = calculate_full_greeks(
                option.put_call,
                spot,
                option.strike,
                option.time_to_expiry_years,
                option.interpolated_rate,
                option.carry_dividend_proxy,
                option.selected_iv,
                run_config.vol_epsilon,
                run_config.time_epsilon_days,
                run_config.min_time_years,
            )
            signed_oi = option.signal * option.open_int * option.option_multiplier
            dex = signed_oi * greeks["delta"]
            gex = signed_oi * greeks["gamma"]
            vex = signed_oi * greeks["vanna"]
            cex = signed_oi * greeks["charm"]

            totals["dex"] += dex
            totals["gex"] += gex
            totals["vex"] += vex
            totals["cex"] += cex

            for bucket in (
                by_expiry[option.expiry_date],
                by_put_call[option.put_call],
                by_moneyness_bucket[option.moneyness_bucket],
            ):
                bucket["dex"] += dex
                bucket["gex"] += gex
                bucket["vex"] += vex
                bucket["cex"] += cex

        curve.append(
            {
                "spot": spot,
                "dex": totals["dex"],
                "gex": totals["gex"],
                "vex": totals["vex"],
                "cex": totals["cex"],
                "by_expiry": dict(by_expiry),
                "by_put_call": dict(by_put_call),
                "by_moneyness_bucket": dict(by_moneyness_bucket),
            }
        )

    return {"grid": grid, "curve": curve}
