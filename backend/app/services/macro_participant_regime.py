from __future__ import annotations

from typing import Any

from .macro_participant_context import MacroParticipantContextMixin
from .macro_participant_math import _clamp, _safe_float


class MacroParticipantRegimeMixin(MacroParticipantContextMixin):
    def _build_flow_regime_classifier(
        self,
        pressure_model: dict[str, Any],
        cohort_value_map: dict[str, Any],
    ) -> dict[str, Any]:
        primary_window = pressure_model.get("primary") or {}
        primary_window_label = pressure_model.get("primary_window_label") or primary_window.get("window_label") or "--"
        pressure_cohorts = (primary_window.get("cohorts") or {}) if isinstance(primary_window, dict) else {}
        value_cohorts = (cohort_value_map.get("cohorts") or {}) if isinstance(cohort_value_map, dict) else {}

        def _infer_bias_side(entry: dict[str, Any]) -> str:
            pressure_score = _safe_float(entry.get("pressure_score")) or 0.0
            net_quantity = _safe_float(entry.get("net_quantity")) or 0.0
            if pressure_score >= 6 or net_quantity > 0:
                return "buy"
            if pressure_score <= -6 or net_quantity < 0:
                return "sell"
            return "neutral"

        def _build_rationale(parts: list[str]) -> str:
            cleaned = [str(part).strip() for part in parts if str(part or "").strip()]
            return "; ".join(cleaned)

        def _classify_cohort(cohort_name: str) -> dict[str, Any]:
            pressure_entry = pressure_cohorts.get(cohort_name) or {}
            value_entry = value_cohorts.get(cohort_name) or {}

            gross_quantity = _safe_float(pressure_entry.get("gross_quantity")) or 0.0
            net_quantity = _safe_float(pressure_entry.get("net_quantity")) or 0.0
            pressure_score = _safe_float(pressure_entry.get("pressure_score")) or 0.0
            efficiency_score = _safe_float(pressure_entry.get("delta_efficiency_score")) or 0.0
            absorption_score = _safe_float(pressure_entry.get("absorption_score")) or 0.0
            fragility_score = _safe_float(pressure_entry.get("fragility_score")) or 0.0
            confidence_score = _safe_float(pressure_entry.get("confidence_score")) or 0.0
            flow_commitment = _safe_float(pressure_entry.get("flow_commitment")) or 0.0
            gross_share = _safe_float(pressure_entry.get("gross_share")) or 0.0
            response_state = str(pressure_entry.get("response_state") or "inactive")
            efficiency_state = str(pressure_entry.get("efficiency_state") or "inactive")
            current_position = str(value_entry.get("current_position") or "unavailable")
            net_ratio_score = _safe_float(value_entry.get("net_ratio_score")) or 0.0
            distance_to_poc_points = _safe_float(value_entry.get("distance_to_poc_points"))
            distance_to_value_low_points = _safe_float(value_entry.get("distance_to_value_low_points"))
            distance_to_value_high_points = _safe_float(value_entry.get("distance_to_value_high_points"))
            event_count = int(pressure_entry.get("event_count") or 0)
            bias_side = _infer_bias_side(pressure_entry)

            base_signal_strength = (
                (abs(pressure_score) * 0.34)
                + (abs(efficiency_score) * 0.24)
                + (max(absorption_score, fragility_score) * 0.16)
                + (confidence_score * 0.14)
                + (_clamp(gross_share, 0.0, 1.0) * 100.0 * 0.12)
            )
            classification_confidence = _clamp(base_signal_strength, 0.0, 100.0)

            if gross_quantity <= 0 or event_count <= 0:
                regime_state = "inactive"
                classification_confidence = 0.0
            elif abs(pressure_score) < 12 and abs(efficiency_score) < 10 and max(absorption_score, fragility_score) < 20:
                regime_state = "inactive"
                classification_confidence = min(classification_confidence, 24.0)
            elif response_state == "absorption" or absorption_score >= 55:
                regime_state = f"absorption_{bias_side}" if bias_side != "neutral" else "absorption"
                classification_confidence = _clamp(classification_confidence + 8.0, 0.0, 100.0)
            elif (
                bias_side == "buy"
                and abs(pressure_score) >= 30
                and abs(efficiency_score) >= 22
                and current_position == "above_value"
            ) or (
                bias_side == "sell"
                and abs(pressure_score) >= 30
                and abs(efficiency_score) >= 22
                and current_position == "below_value"
            ) or (
                response_state == "initiative" and abs(efficiency_score) >= 24 and bias_side != "neutral"
            ):
                regime_state = f"initiative_break_{bias_side}" if bias_side != "neutral" else "initiative_break"
                classification_confidence = _clamp(classification_confidence + 10.0, 0.0, 100.0)
            elif (
                bias_side == "buy"
                and current_position == "below_value"
                and abs(pressure_score) >= 18
            ) or (
                bias_side == "sell"
                and current_position == "above_value"
                and abs(pressure_score) >= 18
            ):
                regime_state = f"responsive_rejection_{bias_side}" if bias_side != "neutral" else "responsive_rejection"
                classification_confidence = _clamp(classification_confidence + 6.0, 0.0, 100.0)
            elif response_state == "divergence" or efficiency_state == "non_confirming":
                regime_state = f"divergence_{bias_side}" if bias_side != "neutral" else "divergence"
                classification_confidence = _clamp(classification_confidence + 4.0, 0.0, 100.0)
            elif fragility_score >= 55 or efficiency_state.startswith("fragile"):
                regime_state = f"exhaustion_{bias_side}" if bias_side != "neutral" else "exhaustion"
                classification_confidence = _clamp(classification_confidence + 5.0, 0.0, 100.0)
            else:
                regime_state = "balanced_transition"
                classification_confidence = min(classification_confidence, 52.0)

            rationale = _build_rationale([
                f"pressure {round(pressure_score, 1)} / eff {round(efficiency_score, 1)}",
                f"response {response_state}",
                f"value {current_position}",
                (
                    f"absorcao {round(absorption_score, 1)}"
                    if regime_state.startswith("absorption")
                    else f"fragilidade {round(fragility_score, 1)}"
                    if regime_state.startswith("exhaustion")
                    else f"skew {round(net_ratio_score, 1)}"
                ),
            ])

            return {
                "cohort": cohort_name,
                "regime_state": regime_state,
                "bias_side": bias_side,
                "confidence_score": round(classification_confidence, 2),
                "rationale": rationale,
                "pressure_score": round(pressure_score, 2),
                "delta_efficiency_score": round(efficiency_score, 2),
                "absorption_score": round(absorption_score, 2),
                "fragility_score": round(fragility_score, 2),
                "flow_commitment": round(flow_commitment, 4),
                "gross_share": round(gross_share, 4),
                "gross_quantity": round(gross_quantity, 4),
                "net_quantity": round(net_quantity, 4),
                "response_state": response_state,
                "efficiency_state": efficiency_state,
                "current_position": current_position,
                "distance_to_poc_points": round(distance_to_poc_points, 6) if distance_to_poc_points is not None else None,
                "distance_to_value_low_points": round(distance_to_value_low_points, 6) if distance_to_value_low_points is not None else None,
                "distance_to_value_high_points": round(distance_to_value_high_points, 6) if distance_to_value_high_points is not None else None,
                "event_count": event_count,
            }

        cohorts_payload = {
            cohort_name: _classify_cohort(cohort_name)
            for cohort_name in ("net", "foreign", "retail")
        }

        priority_order = {
            "initiative_break_buy": 6,
            "initiative_break_sell": 6,
            "responsive_rejection_buy": 5,
            "responsive_rejection_sell": 5,
            "absorption_buy": 4,
            "absorption_sell": 4,
            "divergence_buy": 3,
            "divergence_sell": 3,
            "exhaustion_buy": 3,
            "exhaustion_sell": 3,
            "balanced_transition": 2,
            "inactive": 1,
        }
        cohort_priority = {
            "foreign": 3,
            "net": 2,
            "retail": 1,
        }
        primary_cohort = max(
            cohorts_payload.values(),
            key=lambda entry: (
                priority_order.get(str(entry.get("regime_state") or ""), 0),
                entry.get("confidence_score", 0.0),
                abs(entry.get("pressure_score", 0.0)),
                cohort_priority.get(str(entry.get("cohort") or ""), 0),
            ),
        ) if cohorts_payload else None

        return {
            "window_label": primary_window_label,
            "primary_regime_state": primary_cohort.get("regime_state") if primary_cohort else "inactive",
            "primary_bias_side": primary_cohort.get("bias_side") if primary_cohort else "neutral",
            "primary_confidence_score": primary_cohort.get("confidence_score") if primary_cohort else 0.0,
            "primary_cohort": primary_cohort.get("cohort") if primary_cohort else None,
            "primary_rationale": primary_cohort.get("rationale") if primary_cohort else "",
            "cohorts": cohorts_payload,
        }

    def _build_divergence_model(self, pressure_model: dict[str, Any]) -> dict[str, Any]:
        def _direction(entry: dict[str, Any]) -> int:
            pressure_score = _safe_float(entry.get("pressure_score")) or 0.0
            net_quantity = _safe_float(entry.get("net_quantity")) or 0.0
            if pressure_score >= 8 or net_quantity > 0:
                return 1
            if pressure_score <= -8 or net_quantity < 0:
                return -1
            return 0

        def _strength(entry: dict[str, Any]) -> float:
            pressure_score = abs(_safe_float(entry.get("pressure_score")) or 0.0)
            efficiency_score = abs(_safe_float(entry.get("delta_efficiency_score")) or 0.0)
            confidence_score = _safe_float(entry.get("confidence_score")) or 0.0
            gross_share = _safe_float(entry.get("gross_share")) or 0.0
            return _clamp(
                (0.48 * pressure_score)
                + (0.24 * efficiency_score)
                + (0.16 * confidence_score)
                + (0.12 * gross_share * 100.0),
                0.0,
                100.0,
            )

        def _signed_strength(entry: dict[str, Any]) -> float:
            return _strength(entry) * _direction(entry)

        def _state_label(
            foreign_direction: int,
            retail_direction: int,
            foreign_strength: float,
            retail_strength: float,
        ) -> str:
            if foreign_strength < 10 and retail_strength < 10:
                return "inactive"
            if foreign_direction != 0 and foreign_direction == retail_direction:
                return "aligned_buy" if foreign_direction > 0 else "aligned_sell"
            if foreign_direction == 1 and retail_direction == -1:
                return "foreign_buy_vs_retail_sell"
            if foreign_direction == -1 and retail_direction == 1:
                return "foreign_sell_vs_retail_buy"
            if foreign_strength >= retail_strength + 14:
                if foreign_direction > 0:
                    return "foreign_dominant_buy"
                if foreign_direction < 0:
                    return "foreign_dominant_sell"
            if retail_strength >= foreign_strength + 14:
                if retail_direction > 0:
                    return "retail_dominant_buy"
                if retail_direction < 0:
                    return "retail_dominant_sell"
            return "mixed_transition"

        windows_payload: list[dict[str, Any]] = []
        primary_window = pressure_model.get("primary_window_minutes")
        primary_window_label = pressure_model.get("primary_window_label") or (
            f"{primary_window}m" if primary_window else "--"
        )
        primary_payload: dict[str, Any] | None = None

        for window in pressure_model.get("windows") or []:
            foreign_entry = (window.get("cohorts") or {}).get("foreign") or {}
            retail_entry = (window.get("cohorts") or {}).get("retail") or {}

            foreign_direction = _direction(foreign_entry)
            retail_direction = _direction(retail_entry)
            foreign_strength = _strength(foreign_entry)
            retail_strength = _strength(retail_entry)
            foreign_signed_strength = _signed_strength(foreign_entry)
            retail_signed_strength = _signed_strength(retail_entry)
            shared_strength = min(foreign_strength, retail_strength)
            pressure_gap = abs(
                (_safe_float(foreign_entry.get("pressure_score")) or 0.0)
                - (_safe_float(retail_entry.get("pressure_score")) or 0.0)
            )

            if foreign_direction != 0 and foreign_direction == retail_direction:
                alignment_score = foreign_direction * _clamp(
                    (0.72 * shared_strength) + (0.28 * pressure_gap),
                    0.0,
                    100.0,
                )
                divergence_score = 0.0
            elif foreign_direction != 0 and retail_direction != 0 and foreign_direction != retail_direction:
                alignment_score = 0.0
                divergence_score = foreign_direction * _clamp(
                    (0.72 * shared_strength) + (0.28 * pressure_gap),
                    0.0,
                    100.0,
                )
            else:
                signed_bias = foreign_signed_strength - retail_signed_strength
                alignment_score = _clamp(signed_bias, -100.0, 100.0)
                divergence_score = 0.0

            state = _state_label(
                foreign_direction=foreign_direction,
                retail_direction=retail_direction,
                foreign_strength=foreign_strength,
                retail_strength=retail_strength,
            )
            lead_score = _clamp(foreign_signed_strength - retail_signed_strength, -100.0, 100.0)
            confidence_score = _clamp(
                (0.45 * max(foreign_strength, retail_strength))
                + (0.35 * shared_strength)
                + (0.20 * pressure_gap),
                0.0,
                100.0,
            )
            primary_bias_side = (
                "buy" if lead_score >= 8
                else "sell" if lead_score <= -8
                else "neutral"
            )
            rationale = "; ".join([
                f"foreign {round(_safe_float(foreign_entry.get('pressure_score')) or 0.0, 1)} / retail {round(_safe_float(retail_entry.get('pressure_score')) or 0.0, 1)}",
                f"align {round(alignment_score, 1)}",
                f"div {round(divergence_score, 1)}",
                f"lead {round(lead_score, 1)}",
            ])

            payload = {
                "minutes": window.get("minutes"),
                "window_label": window.get("window_label"),
                "state": state,
                "bias_side": primary_bias_side,
                "alignment_score": round(alignment_score, 2),
                "divergence_score": round(divergence_score, 2),
                "lead_score": round(lead_score, 2),
                "confidence_score": round(confidence_score, 2),
                "foreign_direction": foreign_direction,
                "retail_direction": retail_direction,
                "foreign_strength": round(foreign_strength, 2),
                "retail_strength": round(retail_strength, 2),
                "foreign_pressure_score": round(_safe_float(foreign_entry.get("pressure_score")) or 0.0, 2),
                "retail_pressure_score": round(_safe_float(retail_entry.get("pressure_score")) or 0.0, 2),
                "foreign_net_quantity": round(_safe_float(foreign_entry.get("net_quantity")) or 0.0, 4),
                "retail_net_quantity": round(_safe_float(retail_entry.get("net_quantity")) or 0.0, 4),
                "rationale": rationale,
            }
            windows_payload.append(payload)
            if window.get("minutes") == primary_window:
                primary_payload = payload

        if primary_payload is None and windows_payload:
            primary_payload = windows_payload[-1]

        return {
            "primary_window_minutes": primary_window,
            "primary_window_label": primary_window_label,
            "primary": primary_payload,
            "windows": windows_payload,
        }
    def _build_level_defense_model(self, cohort_value_map: dict[str, Any]) -> dict[str, Any]:
        latest_price = _safe_float(cohort_value_map.get("latest_price"))
        raw_bin_size = _safe_float(cohort_value_map.get("bin_size"))
        bin_size = raw_bin_size if raw_bin_size and raw_bin_size > 0 else 1.0

        def _default_payload() -> dict[str, Any]:
            return {
                "primary_state": "inactive",
                "bias_side": "neutral",
                "defense_score": 0.0,
                "acceptance_score": 0.0,
                "rejection_score": 0.0,
                "support_level": None,
                "resistance_level": None,
                "active_level": None,
                "top_levels": [],
                "rationale": "--",
            }

        def _serialize_level(level: dict[str, Any], score: float | None = None) -> dict[str, Any]:
            payload = {
                "price": round(_safe_float(level.get("price")) or 0.0, 6),
                "state": level.get("state") or "inactive",
                "side": level.get("side") or "balanced",
                "share": round(_safe_float(level.get("share")) or 0.0, 4),
                "event_count": int(level.get("event_count") or 0),
                "net_quantity": round(_safe_float(level.get("net_quantity")) or 0.0, 4),
                "net_ratio_score": round(_safe_float(level.get("net_ratio_score")) or 0.0, 2),
                "distance_to_price_points": round(_safe_float(level.get("distance_to_price_points")) or 0.0, 6),
            }
            if score is not None:
                payload["score"] = round(score, 2)
            return payload

        cohorts_payload: dict[str, Any] = {}
        primary_cohort = None
        primary_state = "inactive"
        primary_score = 0.0
        primary_rationale = "--"

        for cohort_name, cohort_entry in (cohort_value_map.get("cohorts") or {}).items():
            levels = list(cohort_entry.get("levels") or [])
            if latest_price is None or not levels:
                cohorts_payload[cohort_name] = _default_payload()
                continue

            max_event_count = max(int(level.get("event_count") or 0) for level in levels) if levels else 0
            support_candidates: list[tuple[float, dict[str, Any]]] = []
            resistance_candidates: list[tuple[float, dict[str, Any]]] = []
            scored_levels: list[tuple[float, dict[str, Any]]] = []
            value_scores: list[float] = []

            for raw_level in levels:
                price = _safe_float(raw_level.get("price"))
                gross_quantity = _safe_float(raw_level.get("gross_quantity")) or 0.0
                net_quantity = _safe_float(raw_level.get("net_quantity")) or 0.0
                share = _safe_float(raw_level.get("share")) or 0.0
                event_count = int(raw_level.get("event_count") or 0)
                if price is None or gross_quantity <= 0:
                    continue

                net_ratio = _safe_float(raw_level.get("net_ratio"))
                if net_ratio is None:
                    net_ratio = _clamp(net_quantity / gross_quantity, -1.0, 1.0) if gross_quantity > 0 else 0.0
                net_ratio_score = _safe_float(raw_level.get("net_ratio_score"))
                if net_ratio_score is None:
                    net_ratio_score = net_ratio * 100.0

                distance_points = latest_price - price
                abs_distance = abs(distance_points)
                event_share = (event_count / max_event_count) if max_event_count > 0 else 0.0
                density_score = _clamp(
                    (share * 100.0 * 0.56)
                    + (event_share * 100.0 * 0.24)
                    + (abs(net_ratio) * 100.0 * 0.20)
                    + (10.0 if raw_level.get("is_poc") else 0.0)
                    + (6.0 if raw_level.get("in_value_area") else 0.0),
                    0.0,
                    100.0,
                )
                distance_penalty = min((abs_distance / max(bin_size, 0.0001)) * 12.0, 42.0)
                base_score = _clamp(density_score - distance_penalty, 0.0, 100.0)
                side = "buy" if net_quantity > 0 else "sell" if net_quantity < 0 else "balanced"

                if abs_distance <= (bin_size * 0.75):
                    if side == "buy":
                        level_state = "active_bid_defense"
                    elif side == "sell":
                        level_state = "active_offer_defense"
                    else:
                        level_state = "active_rotation"
                elif raw_level.get("in_value_area"):
                    level_state = "accepted_value"
                elif side == "buy" and price <= latest_price:
                    level_state = "memory_support"
                elif side == "sell" and price >= latest_price:
                    level_state = "memory_resistance"
                elif latest_price > price:
                    level_state = "rejected_below_value"
                else:
                    level_state = "rejected_above_value"

                scored_level = {
                    **raw_level,
                    "state": level_state,
                    "side": side,
                    "distance_to_price_points": distance_points,
                    "score": base_score,
                }
                scored_levels.append((base_score, scored_level))
                if raw_level.get("in_value_area"):
                    value_scores.append(base_score)

                if net_ratio >= 0.08 and price <= latest_price + (bin_size * 0.35):
                    support_score = _clamp(
                        base_score
                        + (14.0 if abs_distance <= (bin_size * 0.75) else 0.0)
                        + (8.0 if raw_level.get("in_value_area") else 0.0),
                        0.0,
                        100.0,
                    )
                    support_candidates.append((support_score, scored_level))

                if net_ratio <= -0.08 and price >= latest_price - (bin_size * 0.35):
                    resistance_score = _clamp(
                        base_score
                        + (14.0 if abs_distance <= (bin_size * 0.75) else 0.0)
                        + (8.0 if raw_level.get("in_value_area") else 0.0),
                        0.0,
                        100.0,
                    )
                    resistance_candidates.append((resistance_score, scored_level))

            support_level = max(support_candidates, key=lambda item: item[0]) if support_candidates else None
            resistance_level = max(resistance_candidates, key=lambda item: item[0]) if resistance_candidates else None
            defense_score = max(
                support_level[0] if support_level else 0.0,
                resistance_level[0] if resistance_level else 0.0,
            )
            top_value_scores = sorted(value_scores, reverse=True)[:2]
            base_acceptance = (sum(top_value_scores) / len(top_value_scores)) * 0.7 if top_value_scores else 0.0
            current_position = cohort_entry.get("current_position")
            acceptance_score = _clamp(
                base_acceptance + (22.0 if current_position == "inside_value" else 0.0),
                0.0,
                100.0,
            )
            if current_position == "above_value":
                rejection_base = resistance_level[0] if resistance_level else 0.0
                rejection_score = _clamp(rejection_base + 16.0, 0.0, 100.0)
            elif current_position == "below_value":
                rejection_base = support_level[0] if support_level else 0.0
                rejection_score = _clamp(rejection_base + 16.0, 0.0, 100.0)
            else:
                rejection_score = _clamp(max(
                    (resistance_level[0] if resistance_level else 0.0),
                    (support_level[0] if support_level else 0.0),
                ) * 0.55, 0.0, 100.0)

            if defense_score < 8 and acceptance_score < 8 and rejection_score < 8:
                primary_state_local = "inactive"
            elif support_level and support_level[0] >= (resistance_level[0] if resistance_level else 0.0) + 6 and support_level[0] >= max(acceptance_score, rejection_score):
                primary_state_local = "support_defense"
            elif resistance_level and resistance_level[0] >= (support_level[0] if support_level else 0.0) + 6 and resistance_level[0] >= max(acceptance_score, rejection_score):
                primary_state_local = "resistance_defense"
            elif rejection_score >= max(defense_score, acceptance_score) + 4:
                if current_position == "above_value":
                    primary_state_local = "rejection_above_value"
                elif current_position == "below_value":
                    primary_state_local = "rejection_below_value"
                else:
                    primary_state_local = "responsive_rejection"
            elif acceptance_score >= max(defense_score, rejection_score) + 4:
                primary_state_local = "accepted_value"
            elif support_level and resistance_level and abs(support_level[0] - resistance_level[0]) <= 10:
                primary_state_local = "two_sided_balance"
            else:
                primary_state_local = "mixed_level_map"

            dominant_net_ratio = _safe_float(cohort_entry.get("net_ratio_score")) or 0.0
            if (support_level and support_level[0] > (resistance_level[0] if resistance_level else 0.0) + 6) or dominant_net_ratio >= 8:
                bias_side = "buy"
            elif (resistance_level and resistance_level[0] > (support_level[0] if support_level else 0.0) + 6) or dominant_net_ratio <= -8:
                bias_side = "sell"
            else:
                bias_side = "neutral"

            active_candidates: list[tuple[float, dict[str, Any]]] = []
            if support_level:
                active_candidates.append(support_level)
            if resistance_level:
                active_candidates.append(resistance_level)
            active_level = max(active_candidates, key=lambda item: item[0]) if active_candidates else None
            top_levels = [
                _serialize_level(level, score)
                for score, level in sorted(scored_levels, key=lambda item: item[0], reverse=True)[:3]
            ]
            rationale_parts = []
            if support_level:
                rationale_parts.append(
                    f"sup {round(support_level[0], 1)} @ {round(_safe_float(support_level[1].get('price')) or 0.0, 2)}"
                )
            if resistance_level:
                rationale_parts.append(
                    f"res {round(resistance_level[0], 1)} @ {round(_safe_float(resistance_level[1].get('price')) or 0.0, 2)}"
                )
            rationale_parts.append(f"acc {round(acceptance_score, 1)}")
            rationale_parts.append(f"rej {round(rejection_score, 1)}")

            cohort_payload = {
                "primary_state": primary_state_local,
                "bias_side": bias_side,
                "defense_score": round(defense_score, 2),
                "acceptance_score": round(acceptance_score, 2),
                "rejection_score": round(rejection_score, 2),
                "support_level": _serialize_level(support_level[1], support_level[0]) if support_level else None,
                "resistance_level": _serialize_level(resistance_level[1], resistance_level[0]) if resistance_level else None,
                "active_level": _serialize_level(active_level[1], active_level[0]) if active_level else None,
                "top_levels": top_levels,
                "rationale": " | ".join(rationale_parts) if rationale_parts else "--",
            }
            cohorts_payload[cohort_name] = cohort_payload

            cohort_primary_score = max(defense_score, acceptance_score, rejection_score)
            if cohort_primary_score > primary_score:
                primary_score = cohort_primary_score
                primary_cohort = cohort_name
                primary_state = primary_state_local
                primary_rationale = str(cohort_payload["rationale"])

        return {
            "bin_size": round(bin_size, 6) if raw_bin_size is not None else None,
            "latest_price": round(latest_price, 6) if latest_price is not None else None,
            "primary_cohort": primary_cohort,
            "primary_state": primary_state,
            "primary_score": round(primary_score, 2),
            "primary_rationale": primary_rationale,
            "cohorts": cohorts_payload,
        }
