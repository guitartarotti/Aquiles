from __future__ import annotations

import math
from datetime import timedelta
from typing import Any, Callable

from .macro_participant_context import MacroParticipantContextMixin
from .macro_participant_math import _clamp, _parse_iso, _safe_float


class MacroParticipantPressureMixin(MacroParticipantContextMixin):
    def _pressure_label(self, score: float) -> str:
        if score >= 55:
            return "strong_buy_pressure"
        if score >= 20:
            return "buy_pressure"
        if score <= -55:
            return "strong_sell_pressure"
        if score <= -20:
            return "sell_pressure"
        return "balanced"

    def _response_state(self, net_ratio: float, price_ratio: float, alignment: float) -> str:
        if abs(net_ratio) < 0.08:
            return "inactive"
        if abs(net_ratio) >= 0.35 and abs(price_ratio) <= 0.18:
            return "absorption"
        if alignment < 0 and abs(net_ratio) >= 0.22:
            return "divergence"
        if alignment > 0 and abs(net_ratio) >= 0.2 and abs(price_ratio) >= 0.35:
            return "initiative"
        return "balanced"

    def _efficiency_state(
        self,
        net_quantity: float,
        efficiency_score: float,
        absorption_score: float,
        fragility_score: float,
        alignment: float,
        price_move_points: float,
    ) -> str:
        if abs(net_quantity) < 0.000001:
            return "inactive"
        if absorption_score >= 55:
            return "absorbed_buy" if net_quantity > 0 else "absorbed_sell"
        if fragility_score >= 55 and abs(price_move_points) > 0:
            return "fragile_up" if price_move_points > 0 else "fragile_down"
        if efficiency_score >= 30:
            return "efficient_buy" if net_quantity > 0 else "efficient_sell"
        if alignment < 0 and abs(net_quantity) > 0:
            return "non_confirming"
        return "mixed"

    def _median_value(self, values: list[float]) -> float | None:
        cleaned = sorted(value for value in values if value is not None and math.isfinite(value))
        if not cleaned:
            return None
        middle = len(cleaned) // 2
        if len(cleaned) % 2 == 1:
            return cleaned[middle]
        return (cleaned[middle - 1] + cleaned[middle]) / 2.0

    def _nice_price_step(self, raw_step: float) -> float:
        safe_step = abs(raw_step) if raw_step and math.isfinite(raw_step) else 0.0
        if safe_step <= 0:
            return 1.0
        exponent = math.floor(math.log10(safe_step))
        normalized = safe_step / (10 ** exponent)
        if normalized <= 1.0:
            base = 1.0
        elif normalized <= 2.0:
            base = 2.0
        elif normalized <= 5.0:
            base = 5.0
        else:
            base = 10.0
        return float(base * (10**exponent))

    def _resolve_backend_anchor_price(
        self,
        average_price: float | None,
        delta_quantity: float,
        last_candle: dict[str, Any] | None,
    ) -> float | None:
        candle = last_candle or {}
        high = _safe_float(candle.get("high"))
        low = _safe_float(candle.get("low"))
        close = _safe_float(candle.get("close"))
        open_price = _safe_float(candle.get("open"))
        body_mid = (open_price + close) / 2.0 if open_price is not None and close is not None else None

        if high is not None and low is not None:
            candle_low = min(low, high)
            candle_high = max(low, high)
            candle_mid = body_mid if body_mid is not None else ((candle_low + candle_high) / 2.0)
            candle_range = max(
                candle_high - candle_low,
                abs(candle_mid) * 0.00035,
                0.01,
            )
            tolerance = max(candle_range * 0.35, abs(candle_mid) * 0.00045, 0.01)
            if average_price is not None and (candle_low - tolerance) <= average_price <= (candle_high + tolerance):
                return _clamp(average_price, candle_low, candle_high)
            if delta_quantity > 0:
                return _clamp(candle_mid + (candle_range * 0.18), candle_low, candle_high)
            if delta_quantity < 0:
                return _clamp(candle_mid - (candle_range * 0.18), candle_low, candle_high)
            return _clamp(candle_mid, candle_low, candle_high)

        if close is not None:
            return close
        if body_mid is not None:
            return body_mid
        if high is not None and low is not None:
            return (high + low) / 2.0
        return average_price

    def _build_cohort_value_map(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        value_area_ratio = _clamp(
            float(getattr(self.config, "MACRO_PARTICIPANT_VALUE_AREA_RATIO", 0.70) or 0.70),
            0.5,
            0.95,
        )
        max_levels = max(3, int(getattr(self.config, "MACRO_PARTICIPANT_VALUE_MAX_LEVELS", 8) or 8))

        ordered_samples: list[dict[str, Any]] = []
        for sample in samples:
            captured_dt = _parse_iso(sample.get("captured_at"))
            if not captured_dt:
                continue
            last_price = _safe_float(sample.get("last_price"))
            if last_price is None:
                last_price = _safe_float(((sample.get("last_candle") or {}).get("close")))
            ordered_samples.append({
                "captured_at": sample.get("captured_at"),
                "captured_dt": captured_dt,
                "last_price": last_price,
                "last_candle": sample.get("last_candle") or {},
                "participants": (sample.get("participants") or []),
            })

        ordered_samples.sort(key=lambda item: item["captured_dt"])
        if not ordered_samples:
            return {
                "value_area_ratio": round(value_area_ratio, 4),
                "max_levels": max_levels,
                "bin_size": None,
                "latest_price": None,
                "cohorts": {},
            }

        latest_price = next(
            (sample.get("last_price") for sample in reversed(ordered_samples) if sample.get("last_price") is not None),
            None,
        )
        if latest_price is None:
            latest_price = _safe_float(((ordered_samples[-1].get("last_candle") or {}).get("close")))

        flow_events: list[dict[str, Any]] = []
        broker_baseline: dict[str, dict[str, Any]] = {}
        candle_ranges: list[float] = []

        for sample in ordered_samples:
            last_candle = sample.get("last_candle") or {}
            high = _safe_float(last_candle.get("high"))
            low = _safe_float(last_candle.get("low"))
            if high is not None and low is not None:
                candle_ranges.append(abs(high - low))

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
                broker_baseline[broker_key] = {
                    "quantity": quantity,
                }
                if previous is None:
                    continue

                delta_quantity = quantity - (previous.get("quantity") or 0.0)
                if abs(delta_quantity) < 0.000001:
                    continue

                average_price = _safe_float(row.get("average_price_float"))
                if average_price is None:
                    average_price = _safe_float(row.get("average_price"))
                anchor_price = self._resolve_backend_anchor_price(average_price, delta_quantity, last_candle)
                if anchor_price is None:
                    anchor_price = sample.get("last_price")
                if anchor_price is None or not math.isfinite(anchor_price):
                    continue

                flow_events.append({
                    "captured_dt": sample["captured_dt"],
                    "delta_quantity": delta_quantity,
                    "origin_scope": origin.get("origin_scope") or "local_or_unclassified",
                    "is_foreign_broker": bool(origin.get("is_foreign_broker")),
                    "is_retail_broker": bool(origin.get("is_retail_broker")),
                    "anchor_price": float(anchor_price),
                })

        if latest_price is None and flow_events:
            latest_price = flow_events[-1]["anchor_price"]

        median_range = self._median_value([value for value in candle_ranges if value > 0]) or 0.0
        latest_scale = abs(latest_price) if latest_price is not None else 1.0
        raw_step = max(median_range * 0.35, latest_scale * 0.00012, 0.01)
        bin_size = self._nice_price_step(raw_step)
        if latest_scale >= 50_000:
            bin_size = max(bin_size, 5.0)

        def _bucket_price(price: float) -> float:
            return round(round(price / bin_size) * bin_size, 6)

        cohort_filters: dict[str, Callable[[dict[str, Any]], bool]] = {
            "net": lambda _event: True,
            "foreign": lambda event: bool(event.get("is_foreign_broker")),
            "retail": lambda event: bool(event.get("is_retail_broker")),
        }
        cohorts_payload: dict[str, Any] = {}

        for cohort_name, predicate in cohort_filters.items():
            cohort_events = [event for event in flow_events if predicate(event)]
            level_map: dict[float, dict[str, Any]] = {}
            buy_total = 0.0
            sell_total = 0.0
            for event in cohort_events:
                delta_quantity = float(event["delta_quantity"])
                price_level = _bucket_price(float(event["anchor_price"]))
                level = level_map.setdefault(price_level, {
                    "price": price_level,
                    "gross_quantity": 0.0,
                    "buy_quantity": 0.0,
                    "sell_quantity": 0.0,
                    "net_quantity": 0.0,
                    "event_count": 0,
                })
                abs_delta = abs(delta_quantity)
                level["gross_quantity"] += abs_delta
                level["net_quantity"] += delta_quantity
                level["event_count"] += 1
                if delta_quantity > 0:
                    level["buy_quantity"] += delta_quantity
                    buy_total += delta_quantity
                else:
                    sell_total += abs_delta
                    level["sell_quantity"] += abs_delta

            ordered_levels = sorted(level_map.values(), key=lambda item: item["price"])
            total_gross = sum(item["gross_quantity"] for item in ordered_levels)
            total_net = sum(item["net_quantity"] for item in ordered_levels)
            if not ordered_levels or total_gross <= 0:
                cohorts_payload[cohort_name] = {
                    "level_count": 0,
                    "buy_quantity": round(buy_total, 4),
                    "sell_quantity": round(sell_total, 4),
                    "gross_quantity": round(total_gross, 4),
                    "net_quantity": round(total_net, 4),
                    "net_ratio": 0.0,
                    "net_ratio_score": 0.0,
                    "poc_price": None,
                    "value_area_low": None,
                    "value_area_high": None,
                    "current_position": "unavailable",
                    "dominant_side": "balanced",
                    "distance_to_poc_points": None,
                    "levels": [],
                }
                continue

            poc_index = max(
                range(len(ordered_levels)),
                key=lambda idx: (
                    ordered_levels[idx]["gross_quantity"],
                    -(abs((latest_price or ordered_levels[idx]["price"]) - ordered_levels[idx]["price"])),
                ),
            )
            included_indices = {poc_index}
            cumulative_gross = ordered_levels[poc_index]["gross_quantity"]
            target_gross = total_gross * value_area_ratio
            left = poc_index - 1
            right = poc_index + 1
            while cumulative_gross < target_gross and (left >= 0 or right < len(ordered_levels)):
                left_gross = ordered_levels[left]["gross_quantity"] if left >= 0 else -1.0
                right_gross = ordered_levels[right]["gross_quantity"] if right < len(ordered_levels) else -1.0
                if right_gross > left_gross:
                    included_indices.add(right)
                    cumulative_gross += ordered_levels[right]["gross_quantity"]
                    right += 1
                else:
                    included_indices.add(left)
                    cumulative_gross += ordered_levels[left]["gross_quantity"]
                    left -= 1

            va_low = ordered_levels[min(included_indices)]["price"]
            va_high = ordered_levels[max(included_indices)]["price"]
            current_price = latest_price
            if current_price is None:
                current_position = "unavailable"
            elif current_price < va_low:
                current_position = "below_value"
            elif current_price > va_high:
                current_position = "above_value"
            else:
                current_position = "inside_value"

            net_ratio = _clamp(total_net / total_gross, -1.0, 1.0) if total_gross > 0 else 0.0
            top_levels = sorted(
                ordered_levels,
                key=lambda item: (item["gross_quantity"], abs(item["net_quantity"])),
                reverse=True,
            )[:max_levels]
            cohorts_payload[cohort_name] = {
                "level_count": len(ordered_levels),
                "buy_quantity": round(buy_total, 4),
                "sell_quantity": round(sell_total, 4),
                "gross_quantity": round(total_gross, 4),
                "net_quantity": round(total_net, 4),
                "net_ratio": round(net_ratio, 4),
                "net_ratio_score": round(net_ratio * 100.0, 2),
                "poc_price": round(ordered_levels[poc_index]["price"], 6),
                "poc_gross_quantity": round(ordered_levels[poc_index]["gross_quantity"], 4),
                "poc_net_quantity": round(ordered_levels[poc_index]["net_quantity"], 4),
                "value_area_low": round(va_low, 6),
                "value_area_high": round(va_high, 6),
                "value_area_width_points": round(max(va_high - va_low, 0.0), 6),
                "current_position": current_position,
                "dominant_side": "buy" if total_net > 0 else "sell" if total_net < 0 else "balanced",
                "distance_to_poc_points": round((current_price - ordered_levels[poc_index]["price"]), 6) if current_price is not None else None,
                "distance_to_value_low_points": round((current_price - va_low), 6) if current_price is not None else None,
                "distance_to_value_high_points": round((current_price - va_high), 6) if current_price is not None else None,
                "levels": [
                    {
                        "price": round(level["price"], 6),
                        "gross_quantity": round(level["gross_quantity"], 4),
                        "buy_quantity": round(level["buy_quantity"], 4),
                        "sell_quantity": round(level["sell_quantity"], 4),
                        "net_quantity": round(level["net_quantity"], 4),
                        "net_ratio": round(
                            _clamp(level["net_quantity"] / level["gross_quantity"], -1.0, 1.0),
                            4,
                        ) if level["gross_quantity"] > 0 else 0.0,
                        "net_ratio_score": round(
                            _clamp(level["net_quantity"] / level["gross_quantity"], -1.0, 1.0) * 100.0,
                            2,
                        ) if level["gross_quantity"] > 0 else 0.0,
                        "share": round(level["gross_quantity"] / total_gross, 4) if total_gross > 0 else 0.0,
                        "event_count": int(level["event_count"]),
                        "is_poc": abs(level["price"] - ordered_levels[poc_index]["price"]) < 0.000001,
                        "in_value_area": level["price"] >= va_low and level["price"] <= va_high,
                    }
                    for level in top_levels
                ],
            }

        return {
            "value_area_ratio": round(value_area_ratio, 4),
            "max_levels": max_levels,
            "bin_size": round(bin_size, 6) if bin_size is not None else None,
            "latest_price": round(latest_price, 6) if latest_price is not None else None,
            "session_start_at": ordered_samples[0]["captured_at"],
            "session_end_at": ordered_samples[-1]["captured_at"],
            "event_count": len(flow_events),
            "cohorts": cohorts_payload,
        }

    def _build_pressure_model(self, samples: list[dict[str, Any]]) -> dict[str, Any]:
        raw_windows = getattr(self.config, "MACRO_PARTICIPANT_PRESSURE_WINDOWS", [1, 3, 5, 15]) or [1, 3, 5, 15]
        pressure_windows = sorted({max(1, int(value)) for value in raw_windows})
        primary_window = max(1, int(getattr(self.config, "MACRO_PARTICIPANT_PRESSURE_PRIMARY_WINDOW", 5)))
        if primary_window not in pressure_windows:
            pressure_windows.append(primary_window)
            pressure_windows = sorted(set(pressure_windows))

        ordered_samples: list[dict[str, Any]] = []
        for sample in samples:
            captured_dt = _parse_iso(sample.get("captured_at"))
            if not captured_dt:
                continue
            last_price = _safe_float(sample.get("last_price"))
            if last_price is None:
                last_price = _safe_float(((sample.get("last_candle") or {}).get("close")))
            ordered_samples.append({
                "captured_at": sample.get("captured_at"),
                "captured_dt": captured_dt,
                "last_price": last_price,
                "participants": (sample.get("participants") or []),
            })

        ordered_samples.sort(key=lambda item: item["captured_dt"])
        if not ordered_samples:
            return {
                "primary_window_minutes": primary_window,
                "primary_window_label": f"{primary_window}m",
                "windows": [],
            }

        flow_events: list[dict[str, Any]] = []
        price_points: list[dict[str, Any]] = []
        broker_baseline: dict[str, dict[str, Any]] = {}

        for sample in ordered_samples:
            captured_dt = sample["captured_dt"]
            if sample.get("last_price") is not None:
                price_points.append({
                    "captured_dt": captured_dt,
                    "price": sample.get("last_price"),
                })

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
                broker_baseline[broker_key] = {
                    "quantity": quantity,
                }
                if previous is None:
                    continue

                delta_quantity = quantity - (previous.get("quantity") or 0.0)
                if abs(delta_quantity) < 0.000001:
                    continue

                flow_events.append({
                    "captured_dt": captured_dt,
                    "delta_quantity": delta_quantity,
                    "origin_scope": origin.get("origin_scope") or "local_or_unclassified",
                    "is_foreign_broker": bool(origin.get("is_foreign_broker")),
                    "is_retail_broker": bool(origin.get("is_retail_broker")),
                })

        end_dt = ordered_samples[-1]["captured_dt"]
        end_price = price_points[-1]["price"] if price_points else None
        total_event_count = len(flow_events)

        windows_payload: list[dict[str, Any]] = []
        primary_payload: dict[str, Any] | None = None

        for minutes in pressure_windows:
            window_start = end_dt - timedelta(minutes=minutes)
            window_events = [event for event in flow_events if event["captured_dt"] >= window_start]

            start_price_point = None
            for point in reversed(price_points):
                if point["captured_dt"] <= window_start:
                    start_price_point = point
                    break

            in_window_prices = [point for point in price_points if point["captured_dt"] >= window_start]
            if start_price_point is None:
                start_price_point = in_window_prices[0] if in_window_prices else (price_points[0] if price_points else None)

            observed_prices = []
            if start_price_point and start_price_point.get("price") is not None:
                observed_prices.append(float(start_price_point["price"]))
            observed_prices.extend(
                float(point["price"])
                for point in in_window_prices
                if point.get("price") is not None
            )

            start_price = start_price_point.get("price") if start_price_point else end_price
            price_move_points = (end_price - start_price) if (end_price is not None and start_price is not None) else 0.0
            price_range_points = (max(observed_prices) - min(observed_prices)) if observed_prices else 0.0
            price_move_bps = ((price_move_points / start_price) * 10000.0) if start_price not in {None, 0} else 0.0
            effective_price_span = max(price_range_points, abs(price_move_points), 1.0)
            price_ratio = _clamp(price_move_points / effective_price_span, -1.0, 1.0)
            total_gross = sum(abs(event["delta_quantity"]) for event in window_events)

            cohorts: dict[str, Any] = {}
            cohort_filters: dict[str, Callable[[dict[str, Any]], bool]] = {
                "net": lambda _event: True,
                "foreign": lambda event: bool(event.get("is_foreign_broker")),
                "retail": lambda event: bool(event.get("is_retail_broker")),
            }

            for cohort_name, predicate in cohort_filters.items():
                cohort_events = [event for event in window_events if predicate(event)]
                buy_quantity = sum(max(event["delta_quantity"], 0.0) for event in cohort_events)
                sell_quantity = sum(max(-event["delta_quantity"], 0.0) for event in cohort_events)
                gross_quantity = buy_quantity + sell_quantity
                net_quantity = buy_quantity - sell_quantity
                net_abs = abs(net_quantity)
                net_ratio = _clamp(net_quantity / gross_quantity, -1.0, 1.0) if gross_quantity > 0 else 0.0
                gross_share = _clamp(gross_quantity / total_gross, 0.0, 1.0) if total_gross > 0 else 0.0
                flow_direction = 1.0 if net_quantity > 0 else -1.0 if net_quantity < 0 else 0.0
                price_direction = 1.0 if price_move_points > 0 else -1.0 if price_move_points < 0 else 0.0
                alignment = 1.0 if flow_direction and flow_direction == price_direction else -1.0 if flow_direction and price_direction and flow_direction != price_direction else 0.0
                signed_share = gross_share * flow_direction
                flow_commitment = _clamp(net_abs / gross_quantity, 0.0, 1.0) if gross_quantity > 0 else 0.0
                range_capture = abs(price_ratio)
                points_per_1k_net = abs(price_move_points) / max(net_abs / 1000.0, 0.001) if net_abs > 0 else 0.0
                pressure_score = 100.0 * _clamp(
                    (0.68 * net_ratio) + (0.22 * signed_share) + (0.10 * alignment * abs(price_ratio)),
                    -1.0,
                    1.0,
                )
                efficiency_score = 100.0 * alignment * _clamp(range_capture * flow_commitment, 0.0, 1.0)
                absorption_score = 100.0 * _clamp(flow_commitment * (1.0 - range_capture), 0.0, 1.0)
                fragility_score = 100.0 * _clamp(range_capture * (1.0 - flow_commitment), 0.0, 1.0)
                confidence_score = 100.0 * _clamp(
                    (0.6 * gross_share) + (0.4 * min(len(cohort_events) / max(total_event_count, 1), 1.0)),
                    0.0,
                    1.0,
                )
                efficiency_state = self._efficiency_state(
                    net_quantity=net_quantity,
                    efficiency_score=efficiency_score,
                    absorption_score=absorption_score,
                    fragility_score=fragility_score,
                    alignment=alignment,
                    price_move_points=price_move_points,
                )

                cohorts[cohort_name] = {
                    "buy_quantity": round(buy_quantity, 4),
                    "sell_quantity": round(sell_quantity, 4),
                    "gross_quantity": round(gross_quantity, 4),
                    "net_quantity": round(net_quantity, 4),
                    "net_ratio": round(net_ratio, 4),
                    "gross_share": round(gross_share, 4),
                    "flow_commitment": round(flow_commitment, 4),
                    "pressure_score": round(pressure_score, 2),
                    "confidence_score": round(confidence_score, 2),
                    "pressure_label": self._pressure_label(pressure_score),
                    "response_state": self._response_state(net_ratio, price_ratio, alignment),
                    "delta_efficiency_score": round(efficiency_score, 2),
                    "absorption_score": round(absorption_score, 2),
                    "fragility_score": round(fragility_score, 2),
                    "points_per_1k_net": round(points_per_1k_net, 4),
                    "efficiency_state": efficiency_state,
                    "event_count": len(cohort_events),
                }

            dominant_flow_cohort = max(
                ("foreign", "retail"),
                key=lambda cohort_name: cohorts.get(cohort_name, {}).get("gross_quantity", 0.0),
            )
            window_payload = {
                "minutes": minutes,
                "window_label": f"{minutes}m",
                "start_at": window_start.isoformat(),
                "end_at": end_dt.isoformat(),
                "sample_count": sum(1 for sample in ordered_samples if sample["captured_dt"] >= window_start),
                "event_count": len(window_events),
                "start_price": round(start_price, 4) if start_price is not None else None,
                "end_price": round(end_price, 4) if end_price is not None else None,
                "price_move_points": round(price_move_points, 4),
                "price_move_bps": round(price_move_bps, 2),
                "price_range_points": round(price_range_points, 4),
                "price_response_ratio": round(price_ratio, 4),
                "total_gross_quantity": round(total_gross, 4),
                "dominant_flow_cohort": dominant_flow_cohort,
                "dominant_efficiency_state": cohorts.get(dominant_flow_cohort, {}).get("efficiency_state"),
                "net_efficiency_state": cohorts.get("net", {}).get("efficiency_state"),
                "cohorts": cohorts,
            }
            windows_payload.append(window_payload)
            if minutes == primary_window:
                primary_payload = window_payload

        if primary_payload is None and windows_payload:
            primary_payload = windows_payload[-1]

        return {
            "primary_window_minutes": primary_window,
            "primary_window_label": f"{primary_window}m",
            "windows": windows_payload,
            "primary": primary_payload,
        }
