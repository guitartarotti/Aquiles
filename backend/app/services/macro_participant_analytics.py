from __future__ import annotations

from typing import Any

from .macro_participant_cross_asset import MacroParticipantCrossAssetMixin
from .macro_participant_liquidity import MacroParticipantLiquidityMixin
from .macro_participant_math import _clamp, _safe_float
from .macro_participant_pools import MacroParticipantPoolMixin
from .macro_participant_pressure import MacroParticipantPressureMixin
from .macro_participant_regime import MacroParticipantRegimeMixin
from .macro_participant_signals import MacroParticipantSignalMixin


class MacroParticipantAnalyticsMixin(
    MacroParticipantPressureMixin,
    MacroParticipantRegimeMixin,
    MacroParticipantLiquidityMixin,
    MacroParticipantPoolMixin,
    MacroParticipantCrossAssetMixin,
    MacroParticipantSignalMixin,
):
    def _build_win_trade_thermometer(  # noqa: C901
        self,
        assets: list[dict[str, Any]],
        cross_asset_flow_package: dict[str, Any],
        structural_divergence_model: dict[str, Any],
        continuation_reversal_model: dict[str, Any],
        news_thermometer_context: dict[str, Any],
    ) -> dict[str, Any]:
        asset_map = {asset.get("key"): asset for asset in assets if isinstance(asset, dict)}
        win_asset = asset_map.get("win") or {}
        if not win_asset:
            return {
                "primary_window_minutes": int(cross_asset_flow_package.get("primary_window_minutes") or 5),
                "primary_window_label": f"{int(cross_asset_flow_package.get('primary_window_minutes') or 5)}m",
                "primary": None,
                "windows": [],
            }

        def _window_map(model: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
            windows = {}
            for window in (model or {}).get("windows") or []:
                try:
                    minutes = int(window.get("minutes") or 0)
                except (TypeError, ValueError):
                    continue
                windows[minutes] = window
            return windows

        def _cohort_score(window: dict[str, Any] | None, cohort: str, field: str) -> float:
            return float((((window or {}).get("cohorts") or {}).get(cohort) or {}).get(field) or 0.0)

        def _side_multiplier(side: str | None) -> float:
            if side == "buy":
                return 1.0
            if side == "sell":
                return -1.0
            return 0.0

        def _signal_from_smt(window: dict[str, Any] | None) -> float:
            if not isinstance(window, dict):
                return 0.0
            state = str(window.get("state") or "")
            confirmation = float(window.get("confirmation_score") or 0.0)
            non_confirmation = float(window.get("non_confirmation_score") or 0.0)
            if state == "confirmed_bullish":
                return confirmation
            if state == "confirmed_bearish":
                return -confirmation
            if state == "bullish_non_confirmation":
                return confirmation - non_confirmation
            if state == "bearish_non_confirmation":
                return -(confirmation - non_confirmation)
            if state == "cross_asset_dissonance":
                return 0.0
            return _side_multiplier(str(window.get("bias_side") or "")) * confirmation * 0.45

        def _pick_price(level: dict[str, Any] | None, fallback: float | None = None) -> float | None:
            if isinstance(level, dict):
                price = _safe_float(level.get("price"))
                if price is not None:
                    return price
            return fallback

        def _build_reference(
            level: dict[str, Any] | None,
            fallback_price: float | None,
            fallback_label: str,
        ) -> dict[str, Any] | None:
            price = _pick_price(level, fallback_price)
            if price is None:
                return None
            if isinstance(level, dict):
                label = str(level.get("state") or fallback_label or "reference")
                side = str(level.get("side") or "")
                score = float(level.get("score") or 0.0)
                return {
                    "price": round(price, 2),
                    "label": label,
                    "side": side or None,
                    "score": round(score, 2),
                }
            return {
                "price": round(price, 2),
                "label": fallback_label,
                "side": None,
                "score": 0.0,
            }

        pressure_windows = _window_map(win_asset.get("pressure_model") or {})
        divergence_windows = _window_map(win_asset.get("divergence_model") or {})
        concentration_windows = _window_map(win_asset.get("concentration_model") or {})
        package_windows = _window_map(cross_asset_flow_package)
        smt_windows = _window_map(structural_divergence_model)
        continuation_windows = _window_map(continuation_reversal_model)

        level_defense = ((win_asset.get("level_defense_model") or {}).get("cohorts") or {}).get("net") or {}
        flow_regime = ((win_asset.get("flow_regime_classifier") or {}).get("cohorts") or {}).get("net") or {}
        value_map = ((win_asset.get("cohort_value_map") or {}).get("cohorts") or {}).get("net") or {}

        current_price = _safe_float(win_asset.get("latest_price"))
        poc_price = _safe_float(value_map.get("poc_price"))
        value_low = _safe_float(value_map.get("value_area_low"))
        value_high = _safe_float(value_map.get("value_area_high"))
        bin_size = _safe_float((win_asset.get("cohort_value_map") or {}).get("bin_size")) or 50.0

        support_reference = _build_reference(level_defense.get("support_level"), value_low, "value_area_low")
        resistance_reference = _build_reference(level_defense.get("resistance_level"), value_high, "value_area_high")
        poc_reference = _build_reference({"price": poc_price, "state": "poc_value", "side": None, "score": 0.0}, poc_price, "poc_value")
        news_directional_score = float(news_thermometer_context.get("directional_score") or 0.0)
        news_confidence_score = float(news_thermometer_context.get("confidence_score") or 0.0)
        news_freshness_score = float(news_thermometer_context.get("freshness_score") or 0.0)
        news_bias = str(news_thermometer_context.get("bias") or "watch")
        news_strength_label = str(news_thermometer_context.get("strength_label") or "background")

        primary_window = int(cross_asset_flow_package.get("primary_window_minutes") or 5)
        configured_windows = sorted(
            set(package_windows.keys())
            | set(pressure_windows.keys())
            | set(divergence_windows.keys())
            | set(continuation_windows.keys())
            | {primary_window}
        )

        windows_payload: list[dict[str, Any]] = []
        primary_payload: dict[str, Any] | None = None

        level_state = str(level_defense.get("primary_state") or "")
        regime_state = str(flow_regime.get("regime_state") or "")
        current_position = str(value_map.get("current_position") or "")

        for minutes in configured_windows:
            pressure_window = pressure_windows.get(minutes) or {}
            divergence_window = divergence_windows.get(minutes) or {}
            concentration_window = concentration_windows.get(minutes) or {}
            package_window = package_windows.get(minutes) or {}
            smt_window = smt_windows.get(minutes) or {}
            continuation_window = continuation_windows.get(minutes) or {}

            win_net = _cohort_score(pressure_window, "net", "pressure_score")
            foreign_pressure = _cohort_score(pressure_window, "foreign", "pressure_score")
            net_confidence = _cohort_score(pressure_window, "net", "confidence_score")
            foreign_confidence = _cohort_score(pressure_window, "foreign", "confidence_score")
            delta_efficiency = _cohort_score(pressure_window, "net", "delta_efficiency_score")
            absorption = _cohort_score(pressure_window, "net", "absorption_score")
            fragility = _cohort_score(pressure_window, "net", "fragility_score")
            flow_commitment = _cohort_score(pressure_window, "net", "flow_commitment")

            package_score = float(package_window.get("local_package_score") or 0.0)
            foreign_package_score = float(package_window.get("foreign_package_score") or 0.0)
            curve_breadth_score = float(package_window.get("curve_breadth_score") or 0.0)
            lead_score = float(divergence_window.get("lead_score") or 0.0)
            alignment_score = float(divergence_window.get("alignment_score") or 0.0)
            divergence_score = float(divergence_window.get("divergence_score") or 0.0)

            concentration_net = ((concentration_window.get("cohorts") or {}).get("net")) or {}
            breadth_score = float(concentration_net.get("breadth_score") or 0.0)
            concentration_score = float(concentration_net.get("concentration_score") or 0.0)
            concentration_state = str(concentration_net.get("state") or "inactive")

            continuation_state = str(continuation_window.get("state") or "")
            continuation_bias = str(continuation_window.get("bias_side") or "")
            continuation_probability = float(continuation_window.get("continuation_probability") or 0.0)
            reversal_probability = float(continuation_window.get("reversal_probability") or 0.0)
            smt_state = str(smt_window.get("state") or "")
            divergence_state = str(divergence_window.get("state") or "")

            directional_score = 0.0
            directional_score += win_net * 0.30
            directional_score += foreign_pressure * 0.14
            directional_score += package_score * 0.18
            directional_score += foreign_package_score * 0.10
            directional_score += lead_score * 0.10
            directional_score += alignment_score * 0.06
            directional_score += _signal_from_smt(smt_window) * 0.18
            directional_score += news_directional_score * 0.16

            continuation_edge = continuation_probability - reversal_probability
            if continuation_state.startswith("continuation_"):
                directional_score += _side_multiplier(continuation_bias) * max(continuation_edge, 0.0) * 0.20
            elif continuation_state.startswith("reversal_"):
                directional_score += _side_multiplier(continuation_bias) * max(-continuation_edge, 0.0) * 0.16

            if regime_state == "initiative_break_buy":
                directional_score += 10.0
            elif regime_state == "initiative_break_sell":
                directional_score -= 10.0
            elif regime_state == "responsive_rejection_buy":
                directional_score += 6.0
            elif regime_state == "responsive_rejection_sell":
                directional_score -= 6.0
            elif regime_state == "divergence_buy":
                directional_score += 4.0
            elif regime_state == "divergence_sell":
                directional_score -= 4.0

            if level_state == "support_defense":
                directional_score += 6.0
            elif level_state == "resistance_defense":
                directional_score -= 6.0
            elif level_state == "rejection_below_value":
                directional_score += 4.0
            elif level_state == "rejection_above_value":
                directional_score -= 4.0

            directional_score = _clamp(directional_score, -100.0, 100.0)

            if directional_score >= 12.0:
                bias_side = "buy"
            elif directional_score <= -12.0:
                bias_side = "sell"
            else:
                bias_side = "neutral"

            news_alignment_state = "neutral"
            if bias_side == "neutral" or news_bias == "watch":
                news_alignment_state = "neutral"
            elif (bias_side == "buy" and news_bias == "buy") or (bias_side == "sell" and news_bias == "sell"):
                news_alignment_state = "aligned"
            else:
                news_alignment_state = "conflicted"

            conviction_score = 0.0
            conviction_score += abs(directional_score) * 0.44
            conviction_score += max(net_confidence, foreign_confidence) * 0.18
            conviction_score += max(continuation_probability, reversal_probability) * 0.18
            conviction_score += abs(package_score) * 0.08
            conviction_score += abs(lead_score) * 0.06
            conviction_score += max(0.0, breadth_score - concentration_score) * 0.06
            conviction_score += news_confidence_score * 0.08
            if smt_state in {"confirmed_bullish", "confirmed_bearish"}:
                conviction_score += 8.0
            if concentration_state == "single_name_push":
                conviction_score -= 10.0
            if news_alignment_state == "aligned":
                conviction_score += 6.0 + (news_freshness_score * 0.02)
            elif news_alignment_state == "conflicted":
                conviction_score -= 10.0 + (news_freshness_score * 0.03)
            conviction_score = _clamp(conviction_score, 0.0, 100.0)

            timing_score = 32.0
            if bias_side == "buy" and regime_state == "initiative_break_buy" or bias_side == "sell" and regime_state == "initiative_break_sell":
                timing_score += 18.0
            elif bias_side == "buy" and regime_state in {"responsive_rejection_buy", "divergence_buy"} or bias_side == "sell" and regime_state in {"responsive_rejection_sell", "divergence_sell"}:
                timing_score += 10.0

            if bias_side != "neutral" and continuation_state.startswith("continuation_") and continuation_bias == bias_side:
                timing_score += 14.0
            if bias_side != "neutral" and continuation_state.startswith("reversal_") and continuation_bias == bias_side:
                timing_score += 12.0

            if bias_side == "buy" and level_state in {"support_defense", "rejection_below_value", "responsive_rejection"} or bias_side == "sell" and level_state in {"resistance_defense", "rejection_above_value", "responsive_rejection"}:
                timing_score += 14.0
            elif level_state == "accepted_value":
                timing_score += 8.0

            if bias_side == "buy" and current_position == "below_value" or bias_side == "sell" and current_position == "above_value":
                timing_score += 8.0
            elif bias_side == "buy" and current_position == "above_value" and continuation_state == "continuation_up" or bias_side == "sell" and current_position == "below_value" and continuation_state == "continuation_down":
                timing_score += 6.0

            if bias_side == "neutral":
                timing_score -= 14.0
            if news_alignment_state == "aligned":
                timing_score += 8.0 + (news_freshness_score * 0.04)
            elif news_alignment_state == "conflicted":
                timing_score -= 14.0 + (news_freshness_score * 0.05)
            elif news_strength_label == "background":
                timing_score -= 2.0
            timing_score = _clamp(timing_score, 0.0, 100.0)

            risk_score = 26.0
            risk_score += fragility * 0.26
            risk_score += concentration_score * 0.18
            risk_score += max(0.0, 55.0 - breadth_score) * 0.16
            risk_score += max(reversal_probability - continuation_probability, 0.0) * 0.10
            risk_score += abs(divergence_score) * 0.05
            risk_score += max(0.0, 18.0 - abs(package_score)) * 0.12
            if concentration_state == "single_name_push":
                risk_score += 10.0
            if bias_side == "buy" and divergence_state == "foreign_sell_vs_retail_buy":
                risk_score += 8.0
            if bias_side == "sell" and divergence_state == "foreign_buy_vs_retail_sell":
                risk_score += 8.0
            if bias_side == "buy" and smt_state == "bearish_non_confirmation":
                risk_score += 12.0
            if bias_side == "sell" and smt_state == "bullish_non_confirmation":
                risk_score += 12.0
            if bias_side != "neutral" and _side_multiplier(bias_side) * package_score > 0:
                risk_score -= 6.0
            if news_alignment_state == "conflicted":
                risk_score += 12.0 + (news_freshness_score * 0.06)
            elif news_alignment_state == "aligned":
                risk_score -= 6.0 + (news_freshness_score * 0.03)
            risk_score = _clamp(risk_score, 0.0, 100.0)

            if bias_side == "buy":
                if continuation_state == "continuation_up" and regime_state == "initiative_break_buy":
                    entry_style = "breakout"
                elif continuation_state == "continuation_up":
                    entry_style = "continuation"
                elif continuation_state == "reversal_up":
                    entry_style = "reversal"
                elif level_state in {"support_defense", "rejection_below_value", "responsive_rejection"}:
                    entry_style = "fade"
                else:
                    entry_style = "continuation"
            elif bias_side == "sell":
                if continuation_state == "continuation_down" and regime_state == "initiative_break_sell":
                    entry_style = "breakout"
                elif continuation_state == "continuation_down":
                    entry_style = "continuation"
                elif continuation_state == "reversal_down":
                    entry_style = "reversal"
                elif level_state in {"resistance_defense", "rejection_above_value", "responsive_rejection"}:
                    entry_style = "fade"
                else:
                    entry_style = "continuation"
            else:
                entry_style = "no_trade"

            signal = "neutral"
            action = "stand_aside"
            if directional_score >= 58.0 and conviction_score >= 62.0 and timing_score >= 56.0 and risk_score <= 58.0:
                signal = "strong_buy"
                action = "buy"
            elif directional_score >= 34.0 and conviction_score >= 50.0 and timing_score >= 44.0 and risk_score <= 70.0:
                signal = "buy"
                action = "buy"
            elif directional_score >= 18.0 and conviction_score >= 42.0 and risk_score <= 76.0:
                signal = "cautious_buy"
                action = "buy"
            elif directional_score <= -58.0 and conviction_score >= 62.0 and timing_score >= 56.0 and risk_score <= 58.0:
                signal = "strong_sell"
                action = "sell"
            elif directional_score <= -34.0 and conviction_score >= 50.0 and timing_score >= 44.0 and risk_score <= 70.0:
                signal = "sell"
                action = "sell"
            elif directional_score <= -18.0 and conviction_score >= 42.0 and risk_score <= 76.0:
                signal = "cautious_sell"
                action = "sell"
            elif abs(directional_score) >= 20.0 and risk_score >= 74.0:
                signal = "watch_only"
                action = "stand_aside"

            if action == "stand_aside":
                entry_style = "no_trade"
                bias_side = "neutral" if signal == "neutral" else bias_side

            invalidation_reference: dict[str, Any] | None = None
            target_reference: dict[str, Any] | None = None
            if action == "buy":
                invalidation_reference = support_reference or poc_reference
                target_reference = resistance_reference or poc_reference
                if current_price is not None and target_reference and target_reference.get("price") is not None and target_reference["price"] <= current_price:
                    target_reference = resistance_reference or {"price": round(current_price + (bin_size * 4), 2), "label": "range_extension", "side": "sell", "score": 0.0}
            elif action == "sell":
                invalidation_reference = resistance_reference or poc_reference
                target_reference = support_reference or poc_reference
                if current_price is not None and target_reference and target_reference.get("price") is not None and target_reference["price"] >= current_price:
                    target_reference = support_reference or {"price": round(current_price - (bin_size * 4), 2), "label": "range_extension", "side": "buy", "score": 0.0}

            invalidation_price = _pick_price(invalidation_reference, None)
            target_price = _pick_price(target_reference, None)

            if current_price is not None and action == "buy":
                if invalidation_price is None or invalidation_price >= current_price:
                    fallback_buy_invalidation = current_price - max(bin_size, abs(current_price - (value_low or current_price)))
                    invalidation_price = round(fallback_buy_invalidation, 2)
                    invalidation_reference = {
                        "price": invalidation_price,
                        "label": "risk_floor",
                        "side": "buy",
                        "score": 0.0,
                    }
                if target_price is None or target_price <= current_price:
                    target_price = round(current_price + (bin_size * 4), 2)
                    target_reference = {
                        "price": target_price,
                        "label": "range_extension",
                        "side": "sell",
                        "score": 0.0,
                    }
            elif current_price is not None and action == "sell":
                if invalidation_price is None or invalidation_price <= current_price:
                    fallback_sell_invalidation = current_price + max(bin_size, abs((value_high or current_price) - current_price))
                    invalidation_price = round(fallback_sell_invalidation, 2)
                    invalidation_reference = {
                        "price": invalidation_price,
                        "label": "risk_ceiling",
                        "side": "sell",
                        "score": 0.0,
                    }
                if target_price is None or target_price >= current_price:
                    target_price = round(current_price - (bin_size * 4), 2)
                    target_reference = {
                        "price": target_price,
                        "label": "range_extension",
                        "side": "buy",
                        "score": 0.0,
                    }

            price_to_target_points = None
            price_to_invalidation_points = None
            risk_reward_ratio = None
            if current_price is not None and target_price is not None and action == "buy":
                price_to_target_points = round(target_price - current_price, 2)
            elif current_price is not None and target_price is not None and action == "sell":
                price_to_target_points = round(current_price - target_price, 2)

            if current_price is not None and invalidation_price is not None and action == "buy":
                price_to_invalidation_points = round(current_price - invalidation_price, 2)
            elif current_price is not None and invalidation_price is not None and action == "sell":
                price_to_invalidation_points = round(invalidation_price - current_price, 2)

            if (
                price_to_target_points is not None
                and price_to_invalidation_points is not None
                and price_to_invalidation_points > 0
            ):
                risk_reward_ratio = round(price_to_target_points / price_to_invalidation_points, 2)

            rationale_parts = [
                f"dir {round(directional_score, 1)}",
                f"conv {round(conviction_score, 1)}",
                f"time {round(timing_score, 1)}",
                f"risk {round(risk_score, 1)}",
                f"news {news_bias}/{round(news_directional_score, 1)}",
                f"smt {smt_state or '--'}",
                f"reg {regime_state or '--'}",
                f"lvl {level_state or '--'}",
            ]

            payload = {
                "minutes": minutes,
                "window_label": f"{minutes}m",
                "signal": signal,
                "action": action,
                "bias_side": bias_side,
                "entry_style": entry_style,
                "directional_score": round(directional_score, 2),
                "conviction_score": round(conviction_score, 2),
                "timing_score": round(timing_score, 2),
                "risk_score": round(risk_score, 2),
                "continuation_probability": round(continuation_probability, 2),
                "reversal_probability": round(reversal_probability, 2),
                "win_net_score": round(win_net, 2),
                "foreign_pressure_score": round(foreign_pressure, 2),
                "package_score": round(package_score, 2),
                "foreign_package_score": round(foreign_package_score, 2),
                "curve_breadth_score": round(curve_breadth_score, 2),
                "lead_score": round(lead_score, 2),
                "alignment_score": round(alignment_score, 2),
                "divergence_score": round(divergence_score, 2),
                "delta_efficiency_score": round(delta_efficiency, 2),
                "absorption_score": round(absorption, 2),
                "fragility_score": round(fragility, 2),
                "flow_commitment": round(flow_commitment, 4),
                "smt_state": smt_state,
                "continuation_state": continuation_state,
                "divergence_state": divergence_state,
                "level_state": level_state,
                "regime_state": regime_state,
                "concentration_state": concentration_state,
                "current_position": current_position or None,
                "current_price": round(current_price, 2) if current_price is not None else None,
                "news_alignment_state": news_alignment_state,
                "news_bias": news_bias,
                "news_marker": news_thermometer_context.get("marker"),
                "news_strength_label": news_strength_label,
                "news_directional_score": round(news_directional_score, 2),
                "news_confidence_score": round(news_confidence_score, 2),
                "news_freshness_score": round(news_freshness_score, 2),
                "news_context": news_thermometer_context,
                "support_reference": support_reference,
                "resistance_reference": resistance_reference,
                "poc_reference": poc_reference,
                "invalidation_reference": invalidation_reference,
                "target_reference": target_reference,
                "invalidation_price": round(invalidation_price, 2) if invalidation_price is not None else None,
                "target_price": round(target_price, 2) if target_price is not None else None,
                "price_to_target_points": price_to_target_points,
                "price_to_invalidation_points": price_to_invalidation_points,
                "risk_reward_ratio": risk_reward_ratio,
                "rationale": " | ".join(rationale_parts),
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
