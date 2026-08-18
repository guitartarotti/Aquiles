from __future__ import annotations

from collections import defaultdict
from typing import Any


def _side_sign(put_call: str | None) -> float:
    return 1.0 if str(put_call or "").strip().lower() == "call" else -1.0


def _oi_value(row: dict[str, Any]) -> float:
    for key in ("opt_open_interest", "open_int", "OPT_OPEN_INTEREST", "OPEN_INT"):
        value = row.get(key)
        if value in (None, ""):
            continue
        try:
            return max(float(value), 0.0)
        except Exception:
            continue
    return 0.0


def _smoothed_gex_values(strike_rows: list[dict[str, Any]]) -> list[float]:
    values = [float(row.get("gex_net_estimated") or 0.0) for row in strike_rows]
    if len(values) <= 2:
        return values
    smoothed: list[float] = []
    for index, value in enumerate(values):
        previous_value = values[index - 1] if index > 0 else value
        next_value = values[index + 1] if index < len(values) - 1 else value
        smoothed.append((0.25 * previous_value) + (0.5 * value) + (0.25 * next_value))
    return smoothed


def _sign_label(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def _flip_events(strike_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if not strike_rows:
        return events
    smoothed = _smoothed_gex_values(strike_rows)
    max_abs = max(abs(value) for value in smoothed) if smoothed else 0.0
    threshold = max_abs * 0.08
    for index in range(1, len(strike_rows)):
        previous_row = strike_rows[index - 1]
        current_row = strike_rows[index]
        previous_value = smoothed[index - 1]
        current_value = smoothed[index]
        if max(abs(previous_value), abs(current_value)) < threshold:
            continue
        previous_sign = _sign_label(previous_value)
        current_sign_label = _sign_label(current_value)
        if previous_sign == current_sign_label:
            continue
        if previous_sign == "neutral" and current_sign_label == "neutral":
            continue
        flip_strike = (float(previous_row.get("strike") or 0.0) + float(current_row.get("strike") or 0.0)) / 2.0
        from_sign = previous_sign if previous_sign != "neutral" else current_sign_label
        to_sign = current_sign_label if current_sign_label != "neutral" else previous_sign
        events.append(
            {
                "flip_strike": flip_strike,
                "left_strike": float(previous_row.get("strike") or 0.0),
                "right_strike": float(current_row.get("strike") or 0.0),
                "from_sign": from_sign,
                "to_sign": to_sign,
                "direction": f"{from_sign}_to_{to_sign}",
            }
        )
    if not events:
        return events
    clustered: list[list[dict[str, Any]]] = [[events[0]]]
    for event in events[1:]:
        if event["flip_strike"] - clustered[-1][-1]["flip_strike"] <= 2000.0:
            clustered[-1].append(event)
        else:
            clustered.append([event])
    merged: list[dict[str, Any]] = []
    for cluster in clustered:
        merged.append(
            {
                "flip_strike": sum(item["flip_strike"] for item in cluster) / len(cluster),
                "left_strike": cluster[0]["left_strike"],
                "right_strike": cluster[-1]["right_strike"],
                "from_sign": cluster[0]["from_sign"],
                "to_sign": cluster[-1]["to_sign"],
                "direction": f"{cluster[0]['from_sign']}_to_{cluster[-1]['to_sign']}",
            }
        )
    return merged


def _regime_from_value(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def build_gamma_flip_history(
    option_exposures: list[dict[str, Any]],
    oi_history_rows: list[dict[str, Any]],
    max_dates: int = 10,
) -> dict[str, Any]:
    exposure_lookup: dict[str, dict[str, Any]] = {}
    for item in option_exposures:
        option = item.get("option") or {}
        greeks = item.get("selected_greeks") or {}
        option_id = str(option.get("option_id") or "").strip()
        if not option_id:
            continue
        option_multiplier = float(option.get("option_multiplier") or 1.0)
        put_call = str(option.get("put_call") or "")
        side = _side_sign(put_call)
        exposure_lookup[option_id] = {
            "strike": float(option.get("strike") or 0.0),
            "put_call": put_call,
            "gamma_unit": float(greeks.get("gamma") or 0.0) * option_multiplier,
            "delta_unit": float(greeks.get("delta") or 0.0) * option_multiplier,
            "side": side,
        }

    grouped_by_date: dict[str, dict[float, dict[str, Any]]] = defaultdict(dict)
    snapshot_trade_date = None
    for row in oi_history_rows:
        option_id = str(row.get("option_id") or "").strip()
        exposure = exposure_lookup.get(option_id)
        if not exposure:
            continue
        trade_date = str(row.get("trade_date") or "").strip()
        if not trade_date:
            continue
        strike = float(exposure["strike"])
        strike_row = grouped_by_date[trade_date].setdefault(
            strike,
            {
                "strike": strike,
                "open_interest_total": 0.0,
                "gex_net_estimated": 0.0,
                "dex_net_estimated": 0.0,
            },
        )
        open_interest = _oi_value(row)
        strike_row["open_interest_total"] += open_interest
        strike_row["gex_net_estimated"] += exposure["side"] * open_interest * float(exposure["gamma_unit"] or 0.0)
        strike_row["dex_net_estimated"] += open_interest * float(exposure["delta_unit"] or 0.0)

    for item in option_exposures:
        option = item.get("option") or {}
        snapshot_timestamp = str(option.get("snapshot_timestamp") or "").strip()
        if snapshot_timestamp and len(snapshot_timestamp) >= 10:
            snapshot_trade_date = snapshot_timestamp[:10]
            break

    provisional_dates: set[str] = set()
    if snapshot_trade_date:
        provisional_rows: dict[float, dict[str, Any]] = {}
        for item in option_exposures:
            option = item.get("option") or {}
            greeks = item.get("selected_greeks") or {}
            strike = float(option.get("strike") or 0.0)
            side = _side_sign(option.get("put_call"))
            option_row = provisional_rows.setdefault(
                strike,
                {
                    "strike": strike,
                    "open_interest_total": 0.0,
                    "gex_net_estimated": 0.0,
                    "dex_net_estimated": 0.0,
                },
            )
            open_interest = max(float(option.get("open_int") or 0.0), 0.0)
            option_row["open_interest_total"] += open_interest
            option_row["gex_net_estimated"] += side * open_interest * float(greeks.get("gamma") or 0.0)
            option_row["dex_net_estimated"] += open_interest * float(greeks.get("delta") or 0.0)

        existing_today = grouped_by_date.get(snapshot_trade_date) or {}
        existing_total_oi = sum(float(row.get("open_interest_total") or 0.0) for row in existing_today.values())
        if provisional_rows and existing_total_oi <= 0:
            grouped_by_date[snapshot_trade_date] = provisional_rows
            provisional_dates.add(snapshot_trade_date)

    dates = sorted(grouped_by_date.keys())
    payload_dates: list[dict[str, Any]] = []
    for trade_date in dates[-max_dates:]:
        strike_rows = [grouped_by_date[trade_date][key] for key in sorted(grouped_by_date[trade_date].keys())]
        total_open_interest = sum(float(item.get("open_interest_total") or 0.0) for item in strike_rows)
        estimated_gex_total = sum(float(item.get("gex_net_estimated") or 0.0) for item in strike_rows)
        flip_events = _flip_events(strike_rows)
        data_status = "provisional_snapshot_oi" if trade_date in provisional_dates else "daily_oi_history"
        payload_dates.append(
            {
                "trade_date": trade_date,
                "total_open_interest": total_open_interest,
                "estimated_gex_total": estimated_gex_total,
                "estimated_dex_total": sum(float(item.get("dex_net_estimated") or 0.0) for item in strike_rows),
                "estimated_gamma_regime": _regime_from_value(estimated_gex_total),
                "flip_events": flip_events,
                "flip_points": [float(item.get("flip_strike") or 0.0) for item in flip_events],
                "strike_rows": strike_rows,
                "data_status": data_status,
            }
        )

    historical_regime_flips: list[dict[str, Any]] = []
    previous_day = None
    for current_day in payload_dates:
        current_regime = str(current_day.get("estimated_gamma_regime") or "neutral")
        if previous_day is not None:
            previous_regime = str(previous_day.get("estimated_gamma_regime") or "neutral")
            if previous_regime != current_regime and previous_regime != "neutral" and current_regime != "neutral":
                historical_regime_flips.append(
                    {
                        "previous_trade_date": previous_day.get("trade_date"),
                        "trade_date": current_day.get("trade_date"),
                        "from_regime": previous_regime,
                        "to_regime": current_regime,
                        "direction": f"{previous_regime}_to_{current_regime}",
                    }
                )
        previous_day = current_day

    latest = payload_dates[-1] if payload_dates else {}
    return {
        "methodology": "Estimated from daily open interest history using the latest option gamma and delta snapshot, with gamma flips defined as sign changes in estimated net gamma by strike.",
        "dates": payload_dates,
        "latest_trade_date": latest.get("trade_date"),
        "latest_flip_points": latest.get("flip_points") or [],
        "latest_data_status": latest.get("data_status"),
        "latest_flip_events": latest.get("flip_events") or [],
        "historical_regime_flips": historical_regime_flips,
    }
