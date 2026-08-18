from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Any

from .greeks_engine import calculate_full_greeks
from .types import ModelRunConfig, PreparedOption


def compute_option_exposures(
    option: PreparedOption,
    run_config: ModelRunConfig,
    use_observed_greeks: bool = True,
) -> dict[str, Any]:
    model = calculate_full_greeks(
        option.put_call,
        option.spot_price,
        option.strike,
        option.time_to_expiry_years,
        option.interpolated_rate,
        option.carry_dividend_proxy,
        option.selected_iv,
        run_config.vol_epsilon,
        run_config.time_epsilon_days,
        run_config.min_time_years,
    )
    delta = option.observed_delta if use_observed_greeks and option.observed_delta is not None else model["delta"]
    gamma = option.observed_gamma if use_observed_greeks and option.observed_gamma is not None else model["gamma"]
    vega = option.observed_vega if use_observed_greeks and option.observed_vega is not None else model["vega"]
    theta = option.observed_theta if use_observed_greeks and option.observed_theta is not None else model["theta"]
    signed_oi = option.signal * option.open_int * option.option_multiplier
    dex = signed_oi * delta
    gex = signed_oi * gamma
    # Vanna e Charm: preferencia pelo modelo proprietario (EFF_VANNA/EFF_CHARM do snapshot);
    # fallback para o motor interno BSM quando nao disponiveis.
    vanna_eff = option.observed_vanna if option.observed_vanna is not None else model["vanna"]
    charm_eff = option.observed_charm if option.observed_charm is not None else model["charm"]
    vex = signed_oi * vanna_eff
    cex = signed_oi * charm_eff
    forward_reference_price = option.forward_price or option.spot_price

    return {
        "option": asdict(option),
        "model_greeks": model,
        "selected_greeks": {
            "delta": delta,
            "gamma": gamma,
            "vega": vega,
            "theta": theta,
            "vanna": vanna_eff,
            "charm": charm_eff,
            "source_delta": "observed" if delta == option.observed_delta and option.observed_delta is not None else "model",
            "source_gamma": "observed" if gamma == option.observed_gamma and option.observed_gamma is not None else "model",
            "source_vanna": "observed" if option.observed_vanna is not None else "model",
            "source_charm": "observed" if option.observed_charm is not None else "model",
        },
        "signed_open_interest": signed_oi,
        "dex": dex,
        "dex_notional": dex * option.spot_price,
        "dex_notional_forward": dex * forward_reference_price,
        "gex": gex,
        "gex_notional": gex * (option.spot_price ** 2),
        "gex_notional_forward": gex * (forward_reference_price ** 2),
        "vex": vex,
        "vex_notional": vex * option.spot_price,
        "vex_notional_forward": vex * forward_reference_price,
        "cex": cex,
        "cex_notional": cex * option.spot_price,
        "cex_notional_forward": cex * forward_reference_price,
    }


def aggregate_exposures(option_exposures: list[dict[str, Any]]) -> dict[str, Any]:
    totals = defaultdict(float)
    by_strike: dict[str, dict[str, Any]] = {}
    by_expiry: dict[str, dict[str, Any]] = {}
    by_put_call: dict[str, dict[str, Any]] = {}
    by_moneyness_bucket: dict[str, dict[str, Any]] = {}

    def touch(group: dict[str, dict[str, Any]], key: str) -> dict[str, Any]:
        if key not in group:
            group[key] = {
                "key": key,
                "contracts": 0,
                "open_interest": 0.0,
                "dex": 0.0,
                "gex": 0.0,
                "vex": 0.0,
                "cex": 0.0,
            }
        return group[key]

    for item in option_exposures:
        option = item["option"]
        totals["contracts"] += 1
        totals["open_interest"] += float(option.get("open_int") or 0.0)
        for field in (
            "dex",
            "gex",
            "vex",
            "cex",
            "dex_notional",
            "dex_notional_forward",
            "gex_notional",
            "gex_notional_forward",
            "vex_notional",
            "vex_notional_forward",
            "cex_notional",
            "cex_notional_forward",
        ):
            totals[field] += float(item.get(field) or 0.0)

        strike_bucket = touch(by_strike, f"{float(option.get('strike') or 0.0):.2f}")
        expiry_bucket = touch(by_expiry, str(option.get("expiry_date") or ""))
        side_bucket = touch(by_put_call, str(option.get("put_call") or ""))
        moneyness_bucket = touch(by_moneyness_bucket, str(option.get("moneyness_bucket") or ""))

        for bucket in (strike_bucket, expiry_bucket, side_bucket, moneyness_bucket):
            bucket["contracts"] += 1
            bucket["open_interest"] += float(option.get("open_int") or 0.0)
            bucket["dex"] += float(item.get("dex") or 0.0)
            bucket["gex"] += float(item.get("gex") or 0.0)
            bucket["vex"] += float(item.get("vex") or 0.0)
            bucket["cex"] += float(item.get("cex") or 0.0)

    return {
        "totals": dict(totals),
        "by_strike": list(by_strike.values()),
        "by_expiry": list(by_expiry.values()),
        "by_put_call": list(by_put_call.values()),
        "by_moneyness_bucket": list(by_moneyness_bucket.values()),
    }
