from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable

from .macro_participant_context import MacroParticipantContextMixin
from .macro_participant_math import _clamp, _parse_iso, _safe_float


class MacroParticipantLiquidityMixin(MacroParticipantContextMixin):
    def _build_concentration_model(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        raw_windows = getattr(self.config, "MACRO_PARTICIPANT_PRESSURE_WINDOWS", [1, 3, 5, 15]) or [1, 3, 5, 15]
        windows = sorted({max(1, int(value)) for value in raw_windows})
        primary_window = max(1, int(getattr(self.config, "MACRO_PARTICIPANT_PRESSURE_PRIMARY_WINDOW", 5)))
        if primary_window not in windows:
            windows.append(primary_window)
            windows = sorted(set(windows))

        ordered_samples: list[dict[str, Any]] = []
        for sample in samples:
            captured_dt = _parse_iso(sample.get("captured_at"))
            if not captured_dt:
                continue
            ordered_samples.append({
                "captured_dt": captured_dt,
                "participants": sample.get("participants") or [],
            })

        ordered_samples.sort(key=lambda item: item["captured_dt"])
        if not ordered_samples:
            return {
                "primary_window_minutes": primary_window,
                "primary_window_label": f"{primary_window}m",
                "primary": None,
                "windows": [],
            }

        flow_events: list[dict[str, Any]] = []
        broker_baseline: dict[str, dict[str, Any]] = {}

        for sample in ordered_samples:
            captured_dt = sample["captured_dt"]
            for row in sample.get("participants") or []:
                origin_scope = row.get("origin_scope")
                broker_segment = row.get("broker_segment")
                if origin_scope in {None, "", "local_or_unclassified"} or broker_segment in {None, "", "local_or_unclassified"}:
                    origin = self._classify_broker_origin(row.get("broker_name"))
                else:
                    origin = {
                        "origin_scope": row.get("origin_scope"),
                        "is_foreign_broker": row.get("is_foreign_broker"),
                        "is_retail_broker": row.get("is_retail_broker"),
                    }

                broker_key = f"{row.get('broker_id')}::{row.get('broker_name')}"
                quantity = _safe_float(row.get("quantity_float"))
                if quantity is None:
                    quantity = _safe_float(row.get("quantity")) or 0.0
                previous = broker_baseline.get(broker_key)
                broker_baseline[broker_key] = {"quantity": quantity}
                if previous is None:
                    continue

                delta_quantity = quantity - (previous.get("quantity") or 0.0)
                if abs(delta_quantity) < 0.000001:
                    continue

                flow_events.append({
                    "captured_dt": captured_dt,
                    "broker_key": broker_key,
                    "broker_name": row.get("broker_name"),
                    "delta_quantity": delta_quantity,
                    "origin_scope": origin.get("origin_scope") or "local_or_unclassified",
                    "is_foreign_broker": bool(origin.get("is_foreign_broker")),
                    "is_retail_broker": bool(origin.get("is_retail_broker")),
                })

        end_dt = ordered_samples[-1]["captured_dt"]
        windows_payload: list[dict[str, Any]] = []
        primary_payload: dict[str, Any] | None = None

        def _state_label(active_count: int, top_share: float, hhi: float, buy_players: int, sell_players: int) -> str:
            if active_count <= 0:
                return "inactive"
            if active_count == 1 or top_share >= 0.74:
                return "single_name_push"
            if hhi >= 3200 or top_share >= 0.55:
                return "concentrated_drive"
            if buy_players > 0 and sell_players > 0 and top_share <= 0.42:
                return "two_way_participation"
            if active_count >= 4 and top_share <= 0.35 and hhi <= 2200:
                return "broad_participation"
            return "mixed_participation"

        cohort_filters: dict[str, Callable[[dict[str, Any]], bool]] = {
            "net": lambda _event: True,
            "foreign": lambda event: bool(event.get("is_foreign_broker")),
            "retail": lambda event: bool(event.get("is_retail_broker")),
        }

        for minutes in windows:
            window_start = end_dt - timedelta(minutes=minutes)
            window_events = [event for event in flow_events if event["captured_dt"] >= window_start]
            cohorts_payload: dict[str, Any] = {}

            for cohort_name, predicate in cohort_filters.items():
                cohort_events = [event for event in window_events if predicate(event)]
                by_broker: dict[str, dict[str, Any]] = {}
                for event in cohort_events:
                    broker_entry = by_broker.setdefault(event["broker_key"], {
                        "broker_name": event.get("broker_name"),
                        "net_quantity": 0.0,
                        "gross_quantity": 0.0,
                        "buy_quantity": 0.0,
                        "sell_quantity": 0.0,
                        "event_count": 0,
                    })
                    delta_quantity = event["delta_quantity"]
                    broker_entry["net_quantity"] += delta_quantity
                    broker_entry["gross_quantity"] += abs(delta_quantity)
                    broker_entry["buy_quantity"] += max(delta_quantity, 0.0)
                    broker_entry["sell_quantity"] += max(-delta_quantity, 0.0)
                    broker_entry["event_count"] += 1

                players = list(by_broker.values())
                total_gross = sum(item["gross_quantity"] for item in players)
                total_net = sum(item["net_quantity"] for item in players)
                active_count = len(players)
                buy_players = sum(1 for item in players if item["net_quantity"] > 0)
                sell_players = sum(1 for item in players if item["net_quantity"] < 0)
                if total_gross > 0:
                    shares = [item["gross_quantity"] / total_gross for item in players]
                    hhi_raw = sum((share ** 2) for share in shares)
                    hhi = hhi_raw * 10000.0
                    effective_player_count = (1.0 / hhi_raw) if hhi_raw > 0 else 0.0
                    top_player = max(players, key=lambda item: item["gross_quantity"])
                    top_player_share = top_player["gross_quantity"] / total_gross
                else:
                    hhi = 0.0
                    effective_player_count = 0.0
                    top_player = None
                    top_player_share = 0.0

                breadth_score = _clamp(
                    (min(active_count / 6.0, 1.0) * 42.0)
                    + (min(effective_player_count / 4.5, 1.0) * 38.0)
                    + ((1.0 - top_player_share) * 20.0),
                    0.0,
                    100.0,
                ) if active_count > 0 else 0.0
                concentration_score = _clamp(
                    (top_player_share * 55.0)
                    + (min(hhi / 4000.0, 1.0) * 45.0),
                    0.0,
                    100.0,
                ) if active_count > 0 else 0.0
                state = _state_label(active_count, top_player_share, hhi, buy_players, sell_players)
                bias_side = "buy" if total_net > 0 else "sell" if total_net < 0 else "neutral"
                dominant_player_name = top_player.get("broker_name") if top_player else None
                dominant_player_delta = top_player.get("net_quantity") if top_player else None
                rationale_parts = [
                    f"players {active_count}",
                    f"top {round(top_player_share * 100.0, 1)}%",
                    f"hhi {round(hhi, 0)}",
                ]
                if dominant_player_name:
                    rationale_parts.append(f"lead {dominant_player_name}")

                top_players = []
                for player in sorted(players, key=lambda item: item["gross_quantity"], reverse=True)[:3]:
                    share = (player["gross_quantity"] / total_gross) if total_gross > 0 else 0.0
                    top_players.append({
                        "broker_name": player.get("broker_name"),
                        "gross_quantity": round(player["gross_quantity"], 4),
                        "net_quantity": round(player["net_quantity"], 4),
                        "share": round(share, 4),
                        "side": "buy" if player["net_quantity"] > 0 else "sell" if player["net_quantity"] < 0 else "balanced",
                        "event_count": int(player["event_count"]),
                    })

                cohorts_payload[cohort_name] = {
                    "state": state,
                    "bias_side": bias_side,
                    "active_player_count": active_count,
                    "buy_player_count": buy_players,
                    "sell_player_count": sell_players,
                    "effective_player_count": round(effective_player_count, 2),
                    "breadth_score": round(breadth_score, 2),
                    "concentration_score": round(concentration_score, 2),
                    "concentration_hhi": round(hhi, 2),
                    "top_player_share": round(top_player_share, 4),
                    "dominant_player_name": dominant_player_name,
                    "dominant_player_delta": round(dominant_player_delta, 4) if dominant_player_delta is not None else None,
                    "gross_quantity": round(total_gross, 4),
                    "net_quantity": round(total_net, 4),
                    "top_players": top_players,
                    "rationale": " | ".join(rationale_parts),
                }

            dominant_cohort = max(
                ("net", "foreign", "retail"),
                key=lambda name: cohorts_payload.get(name, {}).get("gross_quantity", 0.0),
            )
            dominant_entry = cohorts_payload.get(dominant_cohort, {})
            payload = {
                "minutes": minutes,
                "window_label": f"{minutes}m",
                "state": dominant_entry.get("state") or "inactive",
                "primary_cohort": dominant_cohort,
                "primary_bias_side": dominant_entry.get("bias_side") or "neutral",
                "primary_breadth_score": dominant_entry.get("breadth_score") or 0.0,
                "primary_concentration_score": dominant_entry.get("concentration_score") or 0.0,
                "primary_rationale": dominant_entry.get("rationale") or "--",
                "cohorts": cohorts_payload,
            }
            windows_payload.append(payload)
            if minutes == primary_window:
                primary_payload = payload

        if primary_payload is None and windows_payload:
            primary_payload = windows_payload[-1]

        return {
            "primary_window_minutes": primary_window,
            "primary_window_label": f"{primary_window}m",
            "primary": primary_payload,
            "windows": windows_payload,
        }

    def _build_liquidity_intelligence_model(  # noqa: C901
        self,
        assets: list[dict[str, Any]],
        cross_asset_flow_package: dict[str, Any],
        structural_divergence_model: dict[str, Any],
        continuation_reversal_model: dict[str, Any],
        news_thermometer_context: dict[str, Any],
        win_trade_thermometer: dict[str, Any],
    ) -> dict[str, Any]:
        def _window_map(model: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
            payload: dict[int, dict[str, Any]] = {}
            for window in (model or {}).get("windows") or []:
                try:
                    minutes = int(window.get("minutes") or 0)
                except (TypeError, ValueError):
                    continue
                if minutes > 0:
                    payload[minutes] = window
            return payload

        def _cohort_entry(window: dict[str, Any] | None, cohort: str) -> dict[str, Any]:
            return (((window or {}).get("cohorts") or {}).get(cohort) or {})

        def _score(window: dict[str, Any] | None, cohort: str, field: str) -> float:
            return float(_cohort_entry(window, cohort).get(field) or 0.0)

        def _sign(value: float, threshold: float = 8.0) -> int:
            if value >= threshold:
                return 1
            if value <= -threshold:
                return -1
            return 0

        def _bias(value: float, threshold: float = 8.0) -> str:
            signal = _sign(value, threshold)
            if signal > 0:
                return "buy"
            if signal < 0:
                return "sell"
            return "neutral"

        def _cohort_label(value: str) -> str:
            return "estrangeiro" if value == "foreign" else "varejo" if value == "retail" else "mercado"

        def _region_role(level: dict[str, Any], latest_price: float | None) -> str:
            price = _safe_float(level.get("price"))
            net_quantity = float(level.get("net_quantity") or 0.0)
            current_position = str(level.get("current_position") or "unavailable")
            if bool(level.get("is_poc")):
                return "inventory_poc"
            if net_quantity > 0 and latest_price is not None and price is not None and price <= latest_price:
                return "bid_support_inventory"
            if net_quantity < 0 and latest_price is not None and price is not None and price >= latest_price:
                return "offer_resistance_inventory"
            if current_position == "above_value" and net_quantity < 0:
                return "bull_trap_offer_zone"
            if current_position == "below_value" and net_quantity > 0:
                return "sell_trap_bid_zone"
            return "two_way_inventory"

        def _regions(asset: dict[str, Any]) -> list[dict[str, Any]]:
            value_map = asset.get("cohort_value_map") or {}
            latest_price = _safe_float(value_map.get("latest_price")) or _safe_float(asset.get("latest_price"))
            raw_bin_size = _safe_float(value_map.get("bin_size"))
            bin_size = raw_bin_size if raw_bin_size and raw_bin_size > 0 else 1.0
            rows: list[dict[str, Any]] = []
            for cohort_name, cohort_entry in ((value_map.get("cohorts") or {}).items()):
                current_position = str(cohort_entry.get("current_position") or "unavailable")
                for raw_level in cohort_entry.get("levels") or []:
                    gross_quantity = float(raw_level.get("gross_quantity") or 0.0)
                    price = _safe_float(raw_level.get("price"))
                    if gross_quantity <= 0 or price is None:
                        continue
                    level = {**raw_level, "current_position": current_position}
                    liquidity_score = _clamp(
                        (float(raw_level.get("share") or 0.0) * 100.0 * 0.55)
                        + (abs(float(raw_level.get("net_ratio_score") or 0.0)) * 0.25)
                        + (min(int(raw_level.get("event_count") or 0) / 10.0, 1.0) * 100.0 * 0.20)
                        + (14.0 if raw_level.get("is_poc") else 0.0),
                        0.0,
                        100.0,
                    )
                    rows.append({
                        "cohort": cohort_name,
                        "cohort_label": _cohort_label(cohort_name),
                        "region_role": _region_role(level, latest_price),
                        "price": round(price, 6),
                        "band_low": round(price - (bin_size / 2.0), 6),
                        "band_high": round(price + (bin_size / 2.0), 6),
                        "gross_quantity": round(gross_quantity, 4),
                        "buy_quantity": round(float(raw_level.get("buy_quantity") or 0.0), 4),
                        "sell_quantity": round(float(raw_level.get("sell_quantity") or 0.0), 4),
                        "net_quantity": round(float(raw_level.get("net_quantity") or 0.0), 4),
                        "net_ratio_score": round(float(raw_level.get("net_ratio_score") or 0.0), 2),
                        "share": round(float(raw_level.get("share") or 0.0), 4),
                        "event_count": int(raw_level.get("event_count") or 0),
                        "is_poc": bool(raw_level.get("is_poc")),
                        "in_value_area": bool(raw_level.get("in_value_area")),
                        "current_position": current_position,
                        "liquidity_score": round(liquidity_score, 2),
                    })
            rows.sort(key=lambda item: (item.get("liquidity_score") or 0.0, item.get("gross_quantity") or 0.0), reverse=True)
            return rows[:9]

        assets_payload: dict[str, Any] = {}
        primary_asset: dict[str, Any] | None = None
        asset_map = {str(asset.get("key")): asset for asset in assets if isinstance(asset, dict) and asset.get("key")}
        for asset_key, asset in asset_map.items():
            pressure_model = asset.get("pressure_model") or {}
            divergence_model = asset.get("divergence_model") or {}
            concentration_model = asset.get("concentration_model") or {}
            cohort_value_map = asset.get("cohort_value_map") or {}
            flow_regime_classifier = asset.get("flow_regime_classifier") or {}
            level_defense_model = asset.get("level_defense_model") or {}
            regions = _regions(asset)

            pressure_windows = _window_map(pressure_model)
            divergence_windows = _window_map(divergence_model)
            concentration_windows = _window_map(concentration_model)
            package_windows = _window_map(cross_asset_flow_package if asset_key == "win" else {})
            smt_windows = _window_map(structural_divergence_model if asset_key == "win" else {})
            continuation_windows = _window_map(continuation_reversal_model if asset_key == "win" else {})
            thermometer_windows = _window_map(win_trade_thermometer if asset_key == "win" else {})

            primary_window = int(
                (win_trade_thermometer if asset_key == "win" else pressure_model).get("primary_window_minutes")
                or pressure_model.get("primary_window_minutes")
                or 5
            )
            window_minutes = sorted(set(pressure_windows.keys()) | set(divergence_windows.keys()) | set(concentration_windows.keys()) | {primary_window})
            value_cohorts = cohort_value_map.get("cohorts") or {}
            level_cohorts = level_defense_model.get("cohorts") or {}
            regime_cohorts = flow_regime_classifier.get("cohorts") or {}
            current_price = _safe_float(asset.get("latest_price")) or _safe_float((asset.get("last_candle") or {}).get("close"))
            density_seed = _clamp(
                (sum(float(region.get("share") or 0.0) for region in regions[:4]) * 100.0 * 0.72)
                + (min(sum(int(region.get("event_count") or 0) for region in regions[:4]) / 20.0, 1.0) * 100.0 * 0.28),
                0.0,
                100.0,
            )

            windows_payload: list[dict[str, Any]] = []
            primary_window_payload: dict[str, Any] | None = None
            for minutes in window_minutes:
                pressure_window = pressure_windows.get(minutes) or {}
                divergence_window = divergence_windows.get(minutes) or {}
                concentration_window = concentration_windows.get(minutes) or {}
                package_window = package_windows.get(minutes) or {}
                smt_windows.get(minutes) or {}
                continuation_window = continuation_windows.get(minutes) or {}
                thermometer_window = thermometer_windows.get(minutes) or {}

                net_pressure = _score(pressure_window, "net", "pressure_score")
                foreign_pressure = _score(pressure_window, "foreign", "pressure_score")
                retail_pressure = _score(pressure_window, "retail", "pressure_score")
                gross_quantity = _score(pressure_window, "net", "gross_quantity")
                foreign_gross = _score(pressure_window, "foreign", "gross_quantity")
                retail_gross = _score(pressure_window, "retail", "gross_quantity")
                delta_efficiency = _score(pressure_window, "net", "delta_efficiency_score")
                absorption = _score(pressure_window, "net", "absorption_score")
                fragility = _score(pressure_window, "net", "fragility_score")
                breadth_score = float((_cohort_entry(concentration_window, "net") or {}).get("breadth_score") or 0.0)
                concentration_score = float((_cohort_entry(concentration_window, "net") or {}).get("concentration_score") or 0.0)
                concentration_state = str((_cohort_entry(concentration_window, "net") or {}).get("state") or "inactive")
                divergence_state = str(divergence_window.get("state") or "inactive")
                lead_score = float(divergence_window.get("lead_score") or 0.0)
                package_score = float(package_window.get("local_package_score") or 0.0)
                continuation_state = str(continuation_window.get("state") or "balanced_transition")
                continuation_probability = float(continuation_window.get("continuation_probability") or 0.0)
                reversal_probability = float(continuation_window.get("reversal_probability") or 0.0)
                net_position = str((value_cohorts.get("net") or {}).get("current_position") or "unavailable")
                level_state = str((level_cohorts.get("net") or {}).get("primary_state") or "inactive")
                net_regime = str((regime_cohorts.get("net") or {}).get("regime_state") or "inactive")
                foreign_regime = str((regime_cohorts.get("foreign") or {}).get("regime_state") or "inactive")
                directional_anchor = float(thermometer_window.get("directional_score") or 0.0) if asset_key == "win" else net_pressure
                if abs(directional_anchor) < 8:
                    directional_anchor = net_pressure + (package_score * 0.35)
                bias_side = _bias(directional_anchor, 10.0)
                news_bias = str(news_thermometer_context.get("bias") or "watch") if asset_key == "win" else "watch"
                news_directional_score = float(news_thermometer_context.get("directional_score") or 0.0) if asset_key == "win" else 0.0

                retail_contra_trend_score = 0.0
                if bias_side == "buy" and retail_pressure <= -8:
                    retail_contra_trend_score = _clamp(abs(retail_pressure) * 0.8 + max(lead_score, 0.0) * 0.28, 0.0, 100.0)
                elif bias_side == "sell" and retail_pressure >= 8:
                    retail_contra_trend_score = _clamp(abs(retail_pressure) * 0.8 + max(-lead_score, 0.0) * 0.28, 0.0, 100.0)
                elif divergence_state in {"foreign_buy_vs_retail_sell", "foreign_sell_vs_retail_buy"}:
                    retail_contra_trend_score = _clamp(abs(lead_score) * 0.72 + abs(retail_pressure) * 0.30, 0.0, 100.0)

                retail_microstructure_state = "retail_balanced"
                if retail_contra_trend_score >= 52 and retail_pressure > 0 and bias_side != "buy":
                    retail_microstructure_state = "retail_buying_top"
                elif retail_contra_trend_score >= 52 and retail_pressure < 0 and bias_side != "sell":
                    retail_microstructure_state = "retail_selling_bottom"
                elif retail_contra_trend_score >= 36:
                    retail_microstructure_state = "retail_adding_against_trend"

                bull_trap_score = _clamp(
                    (22.0 if retail_microstructure_state in {"retail_buying_top", "retail_adding_against_trend"} and retail_pressure > 0 else 0.0)
                    + (22.0 if divergence_state == "foreign_sell_vs_retail_buy" else 0.0)
                    + (10.0 if net_position == "above_value" else 0.0)
                    + (16.0 if continuation_state == "reversal_down" else 0.0)
                    + (14.0 if level_state in {"rejection_above_value", "resistance_defense", "responsive_rejection"} else 0.0)
                    + (12.0 if net_regime in {"exhaustion_buy", "divergence_buy", "absorption_buy"} else 0.0)
                    + (8.0 if news_bias == "sell" else 0.0),
                    0.0,
                    100.0,
                )
                sell_trap_score = _clamp(
                    (22.0 if retail_microstructure_state in {"retail_selling_bottom", "retail_adding_against_trend"} and retail_pressure < 0 else 0.0)
                    + (22.0 if divergence_state == "foreign_buy_vs_retail_sell" else 0.0)
                    + (10.0 if net_position == "below_value" else 0.0)
                    + (16.0 if continuation_state == "reversal_up" else 0.0)
                    + (14.0 if level_state in {"rejection_below_value", "support_defense", "responsive_rejection"} else 0.0)
                    + (12.0 if net_regime in {"exhaustion_sell", "divergence_sell", "absorption_sell"} else 0.0)
                    + (8.0 if news_bias == "buy" else 0.0),
                    0.0,
                    100.0,
                )
                trap_state = "balanced_liquidity"
                trap_bias_side = "neutral"
                trap_risk_score = max(bull_trap_score, sell_trap_score) * 0.55
                trapped_cohort = None
                if bull_trap_score >= sell_trap_score + 8 and bull_trap_score >= 22:
                    trap_state, trap_bias_side, trap_risk_score, trapped_cohort = "bull_trap_risk", "sell", bull_trap_score, "retail"
                elif sell_trap_score >= bull_trap_score + 8 and sell_trap_score >= 22:
                    trap_state, trap_bias_side, trap_risk_score, trapped_cohort = "sell_trap_risk", "buy", sell_trap_score, "retail"

                short_squeeze_score = _clamp(
                    (24.0 if divergence_state == "foreign_buy_vs_retail_sell" else 0.0)
                    + (16.0 if continuation_state == "continuation_up" else 0.0)
                    + (14.0 if net_regime == "initiative_break_buy" else 0.0)
                    + (10.0 if foreign_regime in {"initiative_break_buy", "absorption_buy"} else 0.0)
                    + (8.0 if fragility >= 45 else 0.0)
                    + (6.0 if news_bias == "buy" else 0.0),
                    0.0,
                    100.0,
                )
                long_liquidation_score = _clamp(
                    (24.0 if divergence_state == "foreign_sell_vs_retail_buy" else 0.0)
                    + (16.0 if continuation_state == "continuation_down" else 0.0)
                    + (14.0 if net_regime == "initiative_break_sell" else 0.0)
                    + (10.0 if foreign_regime in {"initiative_break_sell", "absorption_sell"} else 0.0)
                    + (8.0 if fragility >= 45 else 0.0)
                    + (6.0 if news_bias == "sell" else 0.0),
                    0.0,
                    100.0,
                )
                squeeze_state = "contained_squeeze"
                squeeze_bias_side = "neutral"
                squeeze_risk_score = max(short_squeeze_score, long_liquidation_score) * 0.55
                if short_squeeze_score >= long_liquidation_score + 8 and short_squeeze_score >= 24:
                    squeeze_state, squeeze_bias_side, squeeze_risk_score = "short_squeeze_risk", "buy", short_squeeze_score
                elif long_liquidation_score >= short_squeeze_score + 8 and long_liquidation_score >= 24:
                    squeeze_state, squeeze_bias_side, squeeze_risk_score = "long_liquidation_risk", "sell", long_liquidation_score

                stop_run_above_score = _clamp((18.0 if level_state in {"rejection_above_value", "resistance_defense"} else 0.0) + (12.0 if fragility >= 40 else 0.0) + (10.0 if concentration_state in {"single_name_push", "concentrated_drive"} else 0.0), 0.0, 100.0)
                stop_run_below_score = _clamp((18.0 if level_state in {"rejection_below_value", "support_defense"} else 0.0) + (12.0 if fragility >= 40 else 0.0) + (10.0 if concentration_state in {"single_name_push", "concentrated_drive"} else 0.0), 0.0, 100.0)
                stop_run_state = "contained_stop_risk"
                stop_run_bias_side = "neutral"
                stop_run_risk_score = max(stop_run_above_score, stop_run_below_score) * 0.55
                if stop_run_above_score >= stop_run_below_score + 6 and stop_run_above_score >= 24:
                    stop_run_state, stop_run_bias_side, stop_run_risk_score = "stop_run_above_risk", "sell", stop_run_above_score
                elif stop_run_below_score >= stop_run_above_score + 6 and stop_run_below_score >= 24:
                    stop_run_state, stop_run_bias_side, stop_run_risk_score = "stop_run_below_risk", "buy", stop_run_below_score

                liquidity_provider_state = "mixed_liquidity"
                providing_cohort = "market"
                if foreign_regime == "absorption_buy":
                    liquidity_provider_state, providing_cohort = "foreign_absorbing_offers", "foreign"
                elif foreign_regime == "absorption_sell":
                    liquidity_provider_state, providing_cohort = "foreign_absorbing_bids", "foreign"
                elif retail_microstructure_state in {"retail_buying_top", "retail_selling_bottom"}:
                    liquidity_provider_state, providing_cohort = "retail_serving_liquidity", "retail"
                elif concentration_state in {"two_way_participation", "broad_participation"} and abs(net_pressure) < 18:
                    liquidity_provider_state = "two_way_liquidity"
                elif fragility >= 52 or breadth_score <= 34:
                    liquidity_provider_state = "thin_liquidity"

                liquidity_density_score = _clamp(density_seed + min(gross_quantity / 2500.0, 1.0) * 10.0, 0.0, 100.0)
                thin_liquidity_score = _clamp((fragility * 0.42) + (max(0.0, 60.0 - breadth_score) * 0.36) + (concentration_score * 0.22), 0.0, 100.0)
                retail_trapped_score = _clamp((retail_contra_trend_score * 0.55) + (trap_risk_score * 0.35) + (max(abs(lead_score) - 12.0, 0.0) * 0.25), 0.0, 100.0)

                comment_bits = ["Fluxo equilibrado."]
                if bias_side == "buy":
                    comment_bits[0] = "Fluxo base favorece compra."
                elif bias_side == "sell":
                    comment_bits[0] = "Fluxo base favorece venda."
                if liquidity_provider_state == "foreign_absorbing_offers":
                    comment_bits.append("Estrangeiro esta absorvendo oferta.")
                elif liquidity_provider_state == "foreign_absorbing_bids":
                    comment_bits.append("Estrangeiro esta absorvendo bids.")
                elif liquidity_provider_state == "retail_serving_liquidity":
                    comment_bits.append("Varejo parece servir liquidez para a ponta dominante.")
                elif liquidity_provider_state == "thin_liquidity":
                    comment_bits.append("A liquidez esta fina e sensivel a deslocamentos.")
                if trap_state == "bull_trap_risk":
                    comment_bits.append("Ha risco de bull trap com compra ruim acima do value.")
                elif trap_state == "sell_trap_risk":
                    comment_bits.append("Ha risco de sell trap com venda ruim abaixo do value.")
                if squeeze_state == "short_squeeze_risk":
                    comment_bits.append("O setup permite squeeze para cima.")
                elif squeeze_state == "long_liquidation_risk":
                    comment_bits.append("O setup permite liquidacao longa para baixo.")
                if retail_microstructure_state == "retail_buying_top":
                    comment_bits.append("O varejo esta comprando topo contra o pano de fundo.")
                elif retail_microstructure_state == "retail_selling_bottom":
                    comment_bits.append("O varejo esta vendendo fundo contra o pano de fundo.")
                if regions:
                    lead_region = regions[0]
                    comment_bits.append(f"Maior bolsao de liquidez estimada em {round(float(lead_region.get('price') or 0.0), 2)}.")

                payload = {
                    "minutes": minutes,
                    "window_label": f"{minutes}m",
                    "state": trap_state if trap_state != "balanced_liquidity" else squeeze_state if squeeze_state != "contained_squeeze" else liquidity_provider_state,
                    "bias_side": bias_side,
                    "liquidity_provider_state": liquidity_provider_state,
                    "liquidity_density_score": round(liquidity_density_score, 2),
                    "thin_liquidity_score": round(thin_liquidity_score, 2),
                    "trap_state": trap_state,
                    "trap_bias_side": trap_bias_side,
                    "trap_risk_score": round(trap_risk_score, 2),
                    "bull_trap_score": round(bull_trap_score, 2),
                    "sell_trap_score": round(sell_trap_score, 2),
                    "squeeze_state": squeeze_state,
                    "squeeze_bias_side": squeeze_bias_side,
                    "squeeze_risk_score": round(squeeze_risk_score, 2),
                    "stop_run_state": stop_run_state,
                    "stop_run_bias_side": stop_run_bias_side,
                    "stop_run_risk_score": round(stop_run_risk_score, 2),
                    "retail_microstructure_state": retail_microstructure_state,
                    "retail_contra_trend_score": round(retail_contra_trend_score, 2),
                    "retail_trapped_score": round(retail_trapped_score, 2),
                    "providing_cohort": providing_cohort,
                    "trapped_cohort": trapped_cohort,
                    "estimated_liquidity_contracts": round(gross_quantity, 4),
                    "estimated_foreign_contracts": round(foreign_gross, 4),
                    "estimated_retail_contracts": round(retail_gross, 4),
                    "net_pressure_score": round(net_pressure, 2),
                    "foreign_pressure_score": round(foreign_pressure, 2),
                    "retail_pressure_score": round(retail_pressure, 2),
                    "delta_efficiency_score": round(delta_efficiency, 2),
                    "absorption_score": round(absorption, 2),
                    "fragility_score": round(fragility, 2),
                    "breadth_score": round(breadth_score, 2),
                    "concentration_score": round(concentration_score, 2),
                    "package_score": round(package_score, 2),
                    "continuation_probability": round(continuation_probability, 2),
                    "reversal_probability": round(reversal_probability, 2),
                    "divergence_state": divergence_state,
                    "lead_score": round(lead_score, 2),
                    "concentration_state": concentration_state,
                    "net_regime_state": net_regime,
                    "level_state": level_state,
                    "net_position": net_position,
                    "news_bias": news_bias,
                    "news_directional_score": round(news_directional_score, 2),
                    "current_price": round(current_price, 2) if current_price is not None else None,
                    "commentary": " ".join(comment_bits),
                    "rationale": " | ".join([
                        f"net {round(net_pressure, 1)}",
                        f"foreign {round(foreign_pressure, 1)}",
                        f"retail {round(retail_pressure, 1)}",
                        f"div {divergence_state or '--'}",
                        f"lvl {level_state or '--'}",
                        f"reg {net_regime or '--'}",
                        f"news {news_bias}/{round(news_directional_score, 1)}" if asset_key == "win" else f"pos {net_position}",
                    ]),
                }
                windows_payload.append(payload)
                if minutes == primary_window:
                    primary_window_payload = payload

            if primary_window_payload is None and windows_payload:
                primary_window_payload = windows_payload[-1]
            asset_payload = {
                "asset_key": asset_key,
                "label": asset.get("label"),
                "ticker": asset.get("ticker"),
                "inventory_mode": "estimated_net_inventory",
                "primary_window_minutes": primary_window,
                "primary_window_label": f"{primary_window}m",
                "current_price": round(current_price, 2) if current_price is not None else None,
                "estimated_regions": regions,
                "primary": primary_window_payload,
                "windows": windows_payload,
            }
            assets_payload[asset_key] = asset_payload
            if asset_key == "win" or primary_asset is None:
                primary_asset = asset_payload

        return {
            "primary_asset_key": (primary_asset or {}).get("asset_key"),
            "primary": (primary_asset or {}).get("primary"),
            "primary_asset": primary_asset,
            "assets": assets_payload,
            "news_context": news_thermometer_context,
        }
