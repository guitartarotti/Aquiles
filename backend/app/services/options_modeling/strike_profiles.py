from __future__ import annotations

from typing import Any


def _side_sign(put_call: str | None) -> float:
    side = str(put_call or "").strip().lower()
    return 1.0 if side == "call" else -1.0


def build_strike_profiles(option_exposures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[float, dict[str, Any]] = {}

    def touch(strike: float) -> dict[str, Any]:
        if strike not in grouped:
            grouped[strike] = {
                "strike": strike,
                "open_interest_total": 0.0,
                "open_interest_call": 0.0,
                "open_interest_put": 0.0,
                "open_interest_imbalance": 0.0,
                "delta_call": 0.0,
                "delta_put": 0.0,
                "delta_net": 0.0,
                "dex_call": 0.0,
                "dex_put": 0.0,
                "dex_net": 0.0,
                "dex_notional_future_net": 0.0,
                "gamma_call": 0.0,
                "gamma_put": 0.0,
                "gamma_net": 0.0,
                "gex_call": 0.0,
                "gex_put": 0.0,
                "gex_net": 0.0,
                "gex_notional_future_net": 0.0,
                "vanna_call": 0.0,
                "vanna_put": 0.0,
                "vanna_net": 0.0,
                "vex_call": 0.0,
                "vex_put": 0.0,
                "vex_net": 0.0,
                "charm_call": 0.0,
                "charm_put": 0.0,
                "charm_net": 0.0,
                "cex_call": 0.0,
                "cex_put": 0.0,
                "cex_net": 0.0,
                "contracts": 0,
            }
        return grouped[strike]

    for item in option_exposures:
        option = item.get("option") or {}
        greeks = item.get("selected_greeks") or {}
        strike = float(option.get("strike") or 0.0)
        row = touch(strike)
        put_call = str(option.get("put_call") or "")
        side = put_call.lower()
        oi = float(option.get("open_int") or 0.0)
        if oi <= 0:
            continue
        side_factor = _side_sign(put_call)
        delta_value = float(greeks.get("delta") or 0.0)
        gamma_value = float(greeks.get("gamma") or 0.0)
        vanna_value = float(greeks.get("vanna") or 0.0)
        charm_value = float(greeks.get("charm") or 0.0)
        dex_value = float(item.get("dex") or 0.0)
        gex_value = float(item.get("gex") or 0.0)
        vex_value = float(item.get("vex") or 0.0)
        cex_value = float(item.get("cex") or 0.0)

        row["contracts"] += 1
        row["open_interest_total"] += oi

        if side == "call":
            row["open_interest_call"] += oi
            row["delta_call"] += delta_value
            row["dex_call"] += dex_value
            row["gamma_call"] += gamma_value
            row["gex_call"] += gex_value
            row["vanna_call"] += vanna_value
            row["vex_call"] += vex_value
            row["charm_call"] += charm_value
            row["cex_call"] += cex_value
        else:
            row["open_interest_put"] += oi
            row["delta_put"] += delta_value
            row["dex_put"] += dex_value
            row["gamma_put"] += gamma_value
            row["gex_put"] += gex_value
            row["vanna_put"] += vanna_value
            row["vex_put"] += vex_value
            row["charm_put"] += charm_value
            row["cex_put"] += cex_value

        row["open_interest_imbalance"] += side_factor * oi
        row["delta_net"] += delta_value
        row["dex_net"] += dex_value
        row["dex_notional_future_net"] += float(item.get("dex_notional_forward") or 0.0)
        row["gamma_net"] += side_factor * gamma_value
        row["gex_net"] += side_factor * gex_value
        row["gex_notional_future_net"] += side_factor * float(item.get("gex_notional_forward") or 0.0)
        row["vanna_net"] += side_factor * vanna_value
        row["vex_net"] += side_factor * vex_value
        row["charm_net"] += side_factor * charm_value
        row["cex_net"] += side_factor * cex_value

    return [grouped[key] for key in sorted(grouped.keys())]
