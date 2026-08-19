from __future__ import annotations

import math
from datetime import timedelta
from typing import Any

from .macro_participant_math import _clamp, _parse_iso, _safe_float, _utc_now
from .macro_thermometer_service import MacroThermometerService


class MacroParticipantAnalyticsMixin:
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
        return base * (10 ** exponent)

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

        cohort_filters = {
            "net": lambda event: True,
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
            cohort_filters = {
                "net": lambda event: True,
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
                priority_order.get(entry.get("regime_state"), 0),
                entry.get("confidence_score", 0.0),
                abs(entry.get("pressure_score", 0.0)),
                cohort_priority.get(entry.get("cohort"), 0),
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
                primary_rationale = cohort_payload["rationale"]

        return {
            "bin_size": round(bin_size, 6) if raw_bin_size is not None else None,
            "latest_price": round(latest_price, 6) if latest_price is not None else None,
            "primary_cohort": primary_cohort,
            "primary_state": primary_state,
            "primary_score": round(primary_score, 2),
            "primary_rationale": primary_rationale,
            "cohorts": cohorts_payload,
        }

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

        cohort_filters = {
            "net": lambda event: True,
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

    def _build_liquidity_intelligence_model(
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
            if asset_key == "win":
                primary_asset = asset_payload
            elif primary_asset is None:
                primary_asset = asset_payload

        return {
            "primary_asset_key": (primary_asset or {}).get("asset_key"),
            "primary": (primary_asset or {}).get("primary"),
            "primary_asset": primary_asset,
            "assets": assets_payload,
            "news_context": news_thermometer_context,
        }

    def _build_liquidity_pool_model(
        self,
        assets: list[dict[str, Any]],
        cross_asset_flow_package: dict[str, Any],
        structural_divergence_model: dict[str, Any],
        continuation_reversal_model: dict[str, Any],
        news_thermometer_context: dict[str, Any],
        win_trade_thermometer: dict[str, Any],
        liquidity_intelligence_model: dict[str, Any],
    ) -> dict[str, Any]:
        # Synthetic intraday liquidity-pool model.
        #
        # Methodology anchors:
        # - Cont / Kukanov / Stoikov: short-horizon impact is explained more by
        #   order-flow imbalance than by raw traded volume, with impact growing
        #   as visible depth gets thinner.
        # - Osler: stop-loss orders cluster around salient price levels and can
        #   propagate self-reinforcing cascades once triggered.
        # - CME: true futures open interest is an end-of-day exchange metric, so
        #   intraday broker-level open interest is not directly observable here.
        #
        # Because our feed is participant net inventory, not clearing OI, this
        # layer estimates *inventory-at-risk* and *forced-closure potential* from
        # persistent balance changes, value-map clustering, fragility, breadth,
        # and macro alignment. It is intentionally labeled synthetic.
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

        def _pool_type(
            *,
            cohort: str,
            relative_location: str,
            net_quantity: float,
            is_poc: bool,
            current_position: str,
        ) -> tuple[str, str]:
            if cohort == "net":
                if relative_location == "above" and net_quantity < 0:
                    return "short_cover_above", "buy"
                if relative_location == "below" and net_quantity > 0:
                    return "long_flush_below", "sell"
                if relative_location == "near" and net_quantity < 0:
                    return "offer_wall_near_price", "buy"
                if relative_location == "near" and net_quantity > 0:
                    return "bid_wall_near_price", "sell"
                if is_poc:
                    return "inventory_balance_poc", "neutral"
            if current_position == "above_value" and net_quantity < 0:
                return "bull_trap_offer", "sell"
            if current_position == "below_value" and net_quantity > 0:
                return "sell_trap_bid", "buy"
            return "two_way_inventory", "neutral"

        def _pool_label(value: str) -> str:
            if value == "short_cover_above":
                return "short cover acima"
            if value == "long_flush_below":
                return "long flush abaixo"
            if value == "offer_wall_near_price":
                return "parede de oferta"
            if value == "bid_wall_near_price":
                return "parede de bid"
            if value == "inventory_balance_poc":
                return "POC de inventario"
            if value == "bull_trap_offer":
                return "oferta de bull trap"
            if value == "sell_trap_bid":
                return "bid de sell trap"
            return "inventario bilateral"

        def _location_label(value: str) -> str:
            if value == "above":
                return "acima"
            if value == "below":
                return "abaixo"
            if value == "near":
                return "prox"
            return "misto"

        assets_payload: dict[str, Any] = {}
        primary_asset: dict[str, Any] | None = None
        asset_map = {str(asset.get("key")): asset for asset in assets if isinstance(asset, dict) and asset.get("key")}
        liquidity_asset_map = (liquidity_intelligence_model.get("assets") or {})

        for asset_key, asset in asset_map.items():
            pressure_model = asset.get("pressure_model") or {}
            divergence_model = asset.get("divergence_model") or {}
            concentration_model = asset.get("concentration_model") or {}
            cohort_value_map = asset.get("cohort_value_map") or {}
            flow_regime_classifier = asset.get("flow_regime_classifier") or {}
            level_defense_model = asset.get("level_defense_model") or {}
            liquidity_asset = liquidity_asset_map.get(asset_key) or {}

            pressure_windows = _window_map(pressure_model)
            divergence_windows = _window_map(divergence_model)
            concentration_windows = _window_map(concentration_model)
            package_windows = _window_map(cross_asset_flow_package if asset_key == "win" else {})
            smt_windows = _window_map(structural_divergence_model if asset_key == "win" else {})
            continuation_windows = _window_map(continuation_reversal_model if asset_key == "win" else {})
            thermometer_windows = _window_map(win_trade_thermometer if asset_key == "win" else {})
            liquidity_windows = _window_map(liquidity_asset)

            primary_window = int(
                liquidity_asset.get("primary_window_minutes")
                or (win_trade_thermometer if asset_key == "win" else pressure_model).get("primary_window_minutes")
                or pressure_model.get("primary_window_minutes")
                or 5
            )
            window_minutes = sorted(
                set(pressure_windows.keys())
                | set(divergence_windows.keys())
                | set(concentration_windows.keys())
                | set(package_windows.keys())
                | set(continuation_windows.keys())
                | set(liquidity_windows.keys())
                | {primary_window}
            )

            current_price = _safe_float(cohort_value_map.get("latest_price")) or _safe_float(asset.get("latest_price")) or _safe_float((asset.get("last_candle") or {}).get("close"))
            raw_bin_size = _safe_float(cohort_value_map.get("bin_size"))
            bin_size = raw_bin_size if raw_bin_size and raw_bin_size > 0 else max((current_price or 1.0) * 0.0008, 1.0)
            value_cohorts = cohort_value_map.get("cohorts") or {}
            level_cohorts = (level_defense_model.get("cohorts") or {})
            regime_cohorts = (flow_regime_classifier.get("cohorts") or {})
            news_bias = str(news_thermometer_context.get("bias") or "watch") if asset_key == "win" else "watch"
            news_directional_score = float(news_thermometer_context.get("directional_score") or 0.0) if asset_key == "win" else 0.0

            regions_catalog: list[dict[str, Any]] = []
            for cohort_name in ("net", "foreign", "retail"):
                cohort_entry = (value_cohorts.get(cohort_name) or {})
                current_position = str(cohort_entry.get("current_position") or "unavailable")
                for raw_level in cohort_entry.get("levels") or []:
                    price = _safe_float(raw_level.get("price"))
                    gross_quantity = float(raw_level.get("gross_quantity") or 0.0)
                    net_quantity = float(raw_level.get("net_quantity") or 0.0)
                    if price is None or gross_quantity <= 0:
                        continue
                    price_distance = (price - current_price) if current_price is not None else 0.0
                    distance_bps = ((price_distance / current_price) * 10_000.0) if current_price not in (None, 0) else 0.0
                    relative_location = "mixed"
                    if current_price is not None:
                        if price >= current_price + (bin_size * 0.45):
                            relative_location = "above"
                        elif price <= current_price - (bin_size * 0.45):
                            relative_location = "below"
                        else:
                            relative_location = "near"
                    pool_type, trigger_side = _pool_type(
                        cohort=cohort_name,
                        relative_location=relative_location,
                        net_quantity=net_quantity,
                        is_poc=bool(raw_level.get("is_poc")),
                        current_position=current_position,
                    )
                    proximity_score = _clamp(
                        100.0 - min(abs(price_distance) / max(bin_size * 0.85, 1.0), 4.0) * 25.0,
                        5.0,
                        100.0,
                    )
                    persistence_score = _clamp(
                        (float(raw_level.get("share") or 0.0) * 100.0 * 0.36)
                        + (min(int(raw_level.get("event_count") or 0) / 12.0, 1.0) * 100.0 * 0.24)
                        + (abs(float(raw_level.get("net_ratio_score") or 0.0)) * 0.26)
                        + (12.0 if raw_level.get("is_poc") else 0.0)
                        + (8.0 if raw_level.get("in_value_area") else 0.0),
                        0.0,
                        100.0,
                    )
                    synthetic_open_inventory = gross_quantity * (
                        0.82
                        + (persistence_score / 155.0)
                        + (abs(net_quantity) / max(gross_quantity, 1.0)) * 0.24
                    )
                    regions_catalog.append({
                        "cohort": cohort_name,
                        "cohort_label": _cohort_label(cohort_name),
                        "price": float(price),
                        "band_low": float(price - (bin_size / 2.0)),
                        "band_high": float(price + (bin_size / 2.0)),
                        "gross_quantity": gross_quantity,
                        "net_quantity": net_quantity,
                        "buy_quantity": float(raw_level.get("buy_quantity") or 0.0),
                        "sell_quantity": float(raw_level.get("sell_quantity") or 0.0),
                        "share": float(raw_level.get("share") or 0.0),
                        "event_count": int(raw_level.get("event_count") or 0),
                        "is_poc": bool(raw_level.get("is_poc")),
                        "in_value_area": bool(raw_level.get("in_value_area")),
                        "current_position": current_position,
                        "relative_location": relative_location,
                        "price_distance": float(price_distance),
                        "distance_bps": float(distance_bps),
                        "pool_type": pool_type,
                        "pool_label": _pool_label(pool_type),
                        "trigger_side": trigger_side,
                        "proximity_score": round(proximity_score, 2),
                        "persistence_score": round(persistence_score, 2),
                        "synthetic_open_inventory": round(synthetic_open_inventory, 4),
                        "aggregation_scope": "market_total" if cohort_name == "net" else "cohort_context",
                    })

            windows_payload: list[dict[str, Any]] = []
            primary_window_payload: dict[str, Any] | None = None

            for minutes in window_minutes:
                pressure_window = pressure_windows.get(minutes) or {}
                divergence_window = divergence_windows.get(minutes) or {}
                concentration_window = concentration_windows.get(minutes) or {}
                package_window = package_windows.get(minutes) or {}
                smt_window = smt_windows.get(minutes) or {}
                continuation_window = continuation_windows.get(minutes) or {}
                thermometer_window = thermometer_windows.get(minutes) or {}
                liquidity_window = liquidity_windows.get(minutes) or {}

                net_pressure = _score(pressure_window, "net", "pressure_score")
                foreign_pressure = _score(pressure_window, "foreign", "pressure_score")
                retail_pressure = _score(pressure_window, "retail", "pressure_score")
                market_gross = _score(pressure_window, "net", "gross_quantity")
                _score(pressure_window, "foreign", "gross_quantity")
                _score(pressure_window, "retail", "gross_quantity")
                delta_efficiency = _score(pressure_window, "net", "delta_efficiency_score")
                absorption = _score(pressure_window, "net", "absorption_score")
                fragility = _score(pressure_window, "net", "fragility_score")
                breadth_score = float((_cohort_entry(concentration_window, "net") or {}).get("breadth_score") or 0.0)
                concentration_score = float((_cohort_entry(concentration_window, "net") or {}).get("concentration_score") or 0.0)
                package_score = float(package_window.get("local_package_score") or 0.0)
                continuation_probability = float(continuation_window.get("continuation_probability") or 0.0)
                reversal_probability = float(continuation_window.get("reversal_probability") or 0.0)
                continuation_state = str(continuation_window.get("state") or "balanced_transition")
                divergence_state = str(divergence_window.get("state") or "inactive")
                lead_score = float(divergence_window.get("lead_score") or 0.0)
                structural_state = str(smt_window.get("state") or "neutral_balance")
                thermometer_directional = float(thermometer_window.get("directional_score") or 0.0) if asset_key == "win" else 0.0
                net_level_state = str((level_cohorts.get("net") or {}).get("primary_state") or "inactive")
                net_regime_state = str((regime_cohorts.get("net") or {}).get("regime_state") or "inactive")
                thin_liquidity_score = float(liquidity_window.get("thin_liquidity_score") or 0.0)
                stop_run_state = str(liquidity_window.get("stop_run_state") or "contained_stop_risk")
                squeeze_state = str(liquidity_window.get("squeeze_state") or "contained_squeeze")
                trap_state = str(liquidity_window.get("trap_state") or "balanced_liquidity")
                bias_anchor = thermometer_directional if abs(thermometer_directional) >= 8 else (net_pressure + (package_score * 0.35))
                bias_side = _bias(bias_anchor, 10.0)

                region_payload: list[dict[str, Any]] = []
                market_inventory_contracts = 0.0
                foreign_inventory_contracts = 0.0
                retail_inventory_contracts = 0.0
                short_cover_inventory_above = 0.0
                long_flush_inventory_below = 0.0
                short_cover_closure_contracts = 0.0
                long_flush_closure_contracts = 0.0

                for region in regions_catalog:
                    trigger_side = str(region.get("trigger_side") or "neutral")
                    pool_type = str(region.get("pool_type") or "two_way_inventory")
                    cohort_name = str(region.get("cohort") or "net")
                    synthetic_open_inventory = float(region.get("synthetic_open_inventory") or 0.0)
                    persistence_score = float(region.get("persistence_score") or 0.0)
                    proximity_score = float(region.get("proximity_score") or 0.0)
                    gross_quantity = float(region.get("gross_quantity") or 0.0)

                    unwind_intensity = _clamp(
                        (persistence_score * 0.24)
                        + (proximity_score * 0.18)
                        + (abs(net_pressure) * 0.12)
                        + (abs(package_score) * 0.09)
                        + (fragility * 0.14)
                        + (thin_liquidity_score * 0.10)
                        + (12.0 if continuation_state.startswith("continuation_") and trigger_side == bias_side else 0.0)
                        + (10.0 if divergence_state in {"foreign_buy_vs_retail_sell", "foreign_sell_vs_retail_buy"} else 0.0)
                        + (8.0 if structural_state in {"confirmed_bullish", "confirmed_bearish"} else 0.0)
                        + (7.0 if stop_run_state in {"stop_run_above_risk", "stop_run_below_risk"} else 0.0)
                        + (7.0 if squeeze_state in {"short_squeeze_risk", "long_liquidation_risk"} else 0.0)
                        + (5.0 if trap_state in {"bull_trap_risk", "sell_trap_risk"} else 0.0),
                        0.0,
                        100.0,
                    )

                    closure_ratio = 0.14
                    if pool_type == "short_cover_above":
                        closure_ratio = 0.22 + (unwind_intensity / 220.0) + (0.14 if squeeze_state == "short_squeeze_risk" else 0.0)
                    elif pool_type == "long_flush_below":
                        closure_ratio = 0.22 + (unwind_intensity / 220.0) + (0.14 if squeeze_state == "long_liquidation_risk" else 0.0)
                    elif pool_type in {"bull_trap_offer", "sell_trap_bid"}:
                        closure_ratio = 0.26 + (unwind_intensity / 240.0) + (0.08 if trap_state in {"bull_trap_risk", "sell_trap_risk"} else 0.0)
                    elif pool_type in {"offer_wall_near_price", "bid_wall_near_price"}:
                        closure_ratio = 0.18 + (unwind_intensity / 260.0)
                    elif pool_type == "inventory_balance_poc":
                        closure_ratio = 0.15 + (unwind_intensity / 300.0)
                    else:
                        closure_ratio = 0.12 + (unwind_intensity / 320.0)
                    closure_ratio = _clamp(closure_ratio, 0.10, 0.92)

                    contracts_to_clear_band = min(
                        synthetic_open_inventory,
                        gross_quantity * (
                            0.48
                            + (unwind_intensity / 250.0)
                            + (0.08 if region.get("is_poc") else 0.0)
                            + (0.06 if region.get("in_value_area") else 0.0)
                        ),
                    )
                    closure_contracts = synthetic_open_inventory * closure_ratio
                    cascade_probability = _clamp(
                        unwind_intensity * 0.72
                        + (continuation_probability * 0.10 if trigger_side == bias_side else reversal_probability * 0.10)
                        + (8.0 if news_bias == trigger_side else 0.0)
                        - (6.0 if news_bias not in {"watch", trigger_side, "neutral"} else 0.0),
                        0.0,
                        100.0,
                    )

                    if cohort_name == "net":
                        market_inventory_contracts += synthetic_open_inventory
                        if trigger_side == "buy" and region.get("relative_location") == "above":
                            short_cover_inventory_above += synthetic_open_inventory
                            short_cover_closure_contracts += closure_contracts
                        if trigger_side == "sell" and region.get("relative_location") == "below":
                            long_flush_inventory_below += synthetic_open_inventory
                            long_flush_closure_contracts += closure_contracts
                    elif cohort_name == "foreign":
                        foreign_inventory_contracts += synthetic_open_inventory
                    elif cohort_name == "retail":
                        retail_inventory_contracts += synthetic_open_inventory

                    region_payload.append({
                        "cohort": cohort_name,
                        "cohort_label": region.get("cohort_label"),
                        "pool_type": pool_type,
                        "pool_label": region.get("pool_label"),
                        "trigger_side": trigger_side,
                        "relative_location": region.get("relative_location"),
                        "relative_location_label": _location_label(str(region.get("relative_location") or "mixed")),
                        "price": round(float(region.get("price") or 0.0), 6),
                        "band_low": round(float(region.get("band_low") or 0.0), 6),
                        "band_high": round(float(region.get("band_high") or 0.0), 6),
                        "price_distance": round(float(region.get("price_distance") or 0.0), 6),
                        "distance_bps": round(float(region.get("distance_bps") or 0.0), 2),
                        "gross_quantity": round(gross_quantity, 4),
                        "net_quantity": round(float(region.get("net_quantity") or 0.0), 4),
                        "synthetic_open_inventory_contracts": round(synthetic_open_inventory, 4),
                        "estimated_contracts_to_clear_band": round(contracts_to_clear_band, 4),
                        "estimated_stop_closure_contracts": round(closure_contracts, 4),
                        "stop_closure_ratio": round(closure_ratio, 4),
                        "cascade_probability": round(cascade_probability, 2),
                        "unwind_intensity_score": round(unwind_intensity, 2),
                        "persistence_score": round(persistence_score, 2),
                        "proximity_score": round(proximity_score, 2),
                        "aggregation_scope": region.get("aggregation_scope"),
                        "is_poc": bool(region.get("is_poc")),
                        "in_value_area": bool(region.get("in_value_area")),
                        "rationale": " | ".join([
                            f"{region.get('cohort_label')} {_location_label(str(region.get('relative_location') or 'mixed'))}",
                            f"inv {round(synthetic_open_inventory, 0)}",
                            f"close {round(closure_contracts, 0)}",
                            f"frag {round(fragility, 0)}",
                            f"thin {round(thin_liquidity_score, 0)}",
                        ]),
                    })

                region_payload.sort(
                    key=lambda item: (
                        item.get("estimated_stop_closure_contracts") or 0.0,
                        item.get("cascade_probability") or 0.0,
                        item.get("synthetic_open_inventory_contracts") or 0.0,
                    ),
                    reverse=True,
                )
                displayed_pools = region_payload[:10]

                dominant_pool = displayed_pools[0] if displayed_pools else None
                support_pool = next(
                    (
                        pool for pool in displayed_pools
                        if pool.get("trigger_side") == "sell" and pool.get("relative_location") == "below"
                    ),
                    None,
                )
                resistance_pool = next(
                    (
                        pool for pool in displayed_pools
                        if pool.get("trigger_side") == "buy" and pool.get("relative_location") == "above"
                    ),
                    None,
                )

                state = "distributed_inventory"
                dominant_trigger_side = "neutral"
                if short_cover_closure_contracts >= long_flush_closure_contracts + max(250.0, market_gross * 0.12):
                    state = "short_cover_pool_dominant"
                    dominant_trigger_side = "buy"
                elif long_flush_closure_contracts >= short_cover_closure_contracts + max(250.0, market_gross * 0.12):
                    state = "long_flush_pool_dominant"
                    dominant_trigger_side = "sell"
                elif short_cover_closure_contracts >= max(220.0, market_gross * 0.08) and long_flush_closure_contracts >= max(220.0, market_gross * 0.08):
                    state = "two_sided_stop_coil"
                    dominant_trigger_side = "neutral"
                elif dominant_pool and dominant_pool.get("pool_type") == "inventory_balance_poc":
                    state = "inventory_balance_near_price"

                short_cover_risk_score = _clamp(
                    (short_cover_closure_contracts / max(market_gross, 1.0)) * 85.0
                    + max(foreign_pressure, 0.0) * 0.24
                    + (12.0 if divergence_state == "foreign_buy_vs_retail_sell" else 0.0),
                    0.0,
                    100.0,
                )
                long_flush_risk_score = _clamp(
                    (long_flush_closure_contracts / max(market_gross, 1.0)) * 85.0
                    + max(-foreign_pressure, 0.0) * 0.24
                    + (12.0 if divergence_state == "foreign_sell_vs_retail_buy" else 0.0),
                    0.0,
                    100.0,
                )
                two_sided_stop_coil_score = _clamp(
                    min(short_cover_risk_score, long_flush_risk_score) * 0.70
                    + abs(net_pressure) * 0.18
                    + abs(delta_efficiency) * 0.12,
                    0.0,
                    100.0,
                )

                commentary_bits = [
                    f"Inventario sintetico em risco: {round(market_inventory_contracts, 0)} contratos estimados.",
                ]
                if state == "short_cover_pool_dominant":
                    commentary_bits.append("A bolsao dominante esta acima do preco e favorece cobertura de shorts se rompido.")
                elif state == "long_flush_pool_dominant":
                    commentary_bits.append("A bolsao dominante esta abaixo do preco e favorece flush de longs se perdido.")
                elif state == "two_sided_stop_coil":
                    commentary_bits.append("Existe coil bilateral de stops, com risco de deslocamento rapido em qualquer rompimento.")
                elif state == "inventory_balance_near_price":
                    commentary_bits.append("O inventario dominante esta muito perto do preco e pode atuar como ima de liquidez.")
                if dominant_pool:
                    commentary_bits.append(
                        f"Regiao lider em {round(float(dominant_pool.get('price') or 0.0), 2)} com ~{round(float(dominant_pool.get('estimated_stop_closure_contracts') or 0.0), 0)} contratos de fechamento forcado."
                    )
                if news_bias not in {"watch", "neutral"} and asset_key == "win":
                    commentary_bits.append(f"Macro news esta em {news_bias} e entra no gatilho desse lado.")

                payload = {
                    "minutes": minutes,
                    "window_label": f"{minutes}m",
                    "state": state,
                    "bias_side": dominant_trigger_side if dominant_trigger_side != "neutral" else bias_side,
                    "inventory_mode": "synthetic_intraday_open_inventory",
                    "market_inventory_contracts": round(market_inventory_contracts, 4),
                    "foreign_inventory_contracts": round(foreign_inventory_contracts, 4),
                    "retail_inventory_contracts": round(retail_inventory_contracts, 4),
                    "short_cover_inventory_above": round(short_cover_inventory_above, 4),
                    "long_flush_inventory_below": round(long_flush_inventory_below, 4),
                    "short_cover_closure_contracts": round(short_cover_closure_contracts, 4),
                    "long_flush_closure_contracts": round(long_flush_closure_contracts, 4),
                    "contracts_at_risk_total": round(short_cover_closure_contracts + long_flush_closure_contracts, 4),
                    "short_cover_risk_score": round(short_cover_risk_score, 2),
                    "long_flush_risk_score": round(long_flush_risk_score, 2),
                    "two_sided_stop_coil_score": round(two_sided_stop_coil_score, 2),
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
                    "structural_state": structural_state,
                    "news_bias": news_bias,
                    "news_directional_score": round(news_directional_score, 2),
                    "net_level_state": net_level_state,
                    "net_regime_state": net_regime_state,
                    "dominant_pool": dominant_pool,
                    "support_pool": support_pool,
                    "resistance_pool": resistance_pool,
                    "pools": displayed_pools,
                    "commentary": " ".join(commentary_bits),
                    "rationale": " | ".join([
                        f"mkt {round(market_inventory_contracts, 0)}",
                        f"short {round(short_cover_closure_contracts, 0)}",
                        f"long {round(long_flush_closure_contracts, 0)}",
                        f"frag {round(fragility, 0)}",
                        f"pkg {round(package_score, 0)}",
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
                "inventory_mode": "synthetic_intraday_open_inventory",
                "methodology_note": "Estimate based on persistent participant balance changes, value clustering, OFI fragility, and stop-cascade heuristics; not exchange open interest.",
                "primary_window_minutes": primary_window,
                "primary_window_label": f"{primary_window}m",
                "current_price": round(current_price, 2) if current_price is not None else None,
                "primary": primary_window_payload,
                "windows": windows_payload,
            }
            assets_payload[asset_key] = asset_payload
            if asset_key == "win":
                primary_asset = asset_payload
            elif primary_asset is None:
                primary_asset = asset_payload

        return {
            "primary_asset_key": (primary_asset or {}).get("asset_key"),
            "primary": (primary_asset or {}).get("primary"),
            "primary_asset": primary_asset,
            "assets": assets_payload,
            "methodology_note": "Synthetic intraday inventory-at-risk model. Uses OFI, depth proxies, clustered value-map regions, and stop-cascade heuristics. It does not observe true exchange open interest intraday.",
        }

    def _build_cross_asset_flow_package(self, state: dict[str, Any], specs: list[dict[str, Any]]) -> dict[str, Any]:
        assets_state = state.get("assets", {}) or {}
        primary_window = max(1, int(getattr(self.config, "MACRO_PARTICIPANT_PRESSURE_PRIMARY_WINDOW", 5)))
        configured_windows = sorted({
            max(1, int(value))
            for value in (getattr(self.config, "MACRO_PARTICIPANT_PRESSURE_WINDOWS", [1, 3, 5, 15]) or [1, 3, 5, 15])
        })
        if primary_window not in configured_windows:
            configured_windows.append(primary_window)
            configured_windows = sorted(set(configured_windows))

        win_spec = next((spec for spec in specs if spec.get("role") == "win"), None)
        wdo_spec = next((spec for spec in specs if spec.get("role") == "wdo"), None)
        di_specs = [spec for spec in specs if spec.get("curve_bucket") == "di_curve"]

        def _contract_label(ticker: str | None) -> str:
            text = str(ticker or "")
            if "DI1" in text:
                return text.split("DI1")[-1]
            return text.split(":")[-1] if ":" in text else text

        def _asset_pressure_model(spec: dict[str, Any] | None) -> dict[str, Any]:
            if not spec:
                return {}
            asset_state = assets_state.get(spec.get("ticker")) or {}
            return self._build_pressure_model(asset_state.get("samples", []) or [])

        def _window_entry(model: dict[str, Any], minutes: int) -> dict[str, Any]:
            for window in model.get("windows") or []:
                if int(window.get("minutes") or 0) == minutes:
                    return window
            return {}

        def _score(entry: dict[str, Any] | None, cohort: str) -> float:
            return float((((entry or {}).get("cohorts") or {}).get(cohort) or {}).get("pressure_score") or 0.0)

        def _state_sign(value: float, threshold: float = 10.0) -> int:
            if value >= threshold:
                return 1
            if value <= -threshold:
                return -1
            return 0

        win_model = _asset_pressure_model(win_spec)
        wdo_model = _asset_pressure_model(wdo_spec)
        di_models = {spec["ticker"]: _asset_pressure_model(spec) for spec in di_specs}

        windows_payload: list[dict[str, Any]] = []
        primary_payload: dict[str, Any] | None = None

        for minutes in configured_windows:
            win_window = _window_entry(win_model, minutes)
            wdo_window = _window_entry(wdo_model, minutes)
            di_window_entries = []
            for spec in di_specs:
                window = _window_entry(di_models.get(spec["ticker"]) or {}, minutes)
                if window:
                    di_window_entries.append((spec, window))

            win_net = _score(win_window, "net")
            win_foreign = _score(win_window, "foreign")
            wdo_net = _score(wdo_window, "net")
            wdo_foreign = _score(wdo_window, "foreign")

            di_net_scores = [_score(window, "net") for _, window in di_window_entries]
            di_foreign_scores = [_score(window, "foreign") for _, window in di_window_entries]
            di_supportive_score = (sum(di_net_scores) / len(di_net_scores)) if di_net_scores else 0.0
            di_foreign_supportive_score = (sum(di_foreign_scores) / len(di_foreign_scores)) if di_foreign_scores else 0.0

            short_di_scores = [_score(window, "net") for spec, window in di_window_entries if _contract_label(spec.get("ticker")) in {"F28", "F29"}]
            long_di_scores = [_score(window, "net") for spec, window in di_window_entries if _contract_label(spec.get("ticker")) in {"F30", "F31", "F35"}]
            short_di_avg = (sum(short_di_scores) / len(short_di_scores)) if short_di_scores else 0.0
            long_di_avg = (sum(long_di_scores) / len(long_di_scores)) if long_di_scores else 0.0

            win_component = win_net
            fx_component = -wdo_net
            rates_component = di_supportive_score
            foreign_win_component = win_foreign
            foreign_fx_component = -wdo_foreign
            foreign_rates_component = di_foreign_supportive_score

            local_package_score = _clamp(
                (0.50 * win_component) + (0.30 * fx_component) + (0.20 * rates_component),
                -100.0,
                100.0,
            )
            foreign_package_score = _clamp(
                (0.50 * foreign_win_component) + (0.30 * foreign_fx_component) + (0.20 * foreign_rates_component),
                -100.0,
                100.0,
            )

            component_signs = [
                _state_sign(win_component),
                _state_sign(fx_component),
                _state_sign(rates_component),
            ]
            on_confirmations = sum(1 for sign in component_signs if sign > 0)
            off_confirmations = sum(1 for sign in component_signs if sign < 0)

            if di_net_scores:
                di_direction = _state_sign(di_supportive_score, threshold=6.0)
                if di_direction == 0:
                    curve_breadth_score = 0.0
                else:
                    curve_breadth_score = 100.0 * (
                        sum(1 for score in di_net_scores if _state_sign(score, threshold=6.0) == di_direction) / len(di_net_scores)
                    )
            else:
                curve_breadth_score = 0.0

            if local_package_score >= 16 and on_confirmations >= 2 and curve_breadth_score >= 40:
                state_label = "risk_on_package"
            elif local_package_score <= -16 and off_confirmations >= 2 and curve_breadth_score >= 40:
                state_label = "risk_off_package"
            elif abs(local_package_score) < 8 and abs(foreign_package_score) < 8:
                state_label = "neutral_transition"
            elif on_confirmations == 2 and off_confirmations == 1:
                state_label = "partial_risk_on"
            elif off_confirmations == 2 and on_confirmations == 1:
                state_label = "partial_risk_off"
            else:
                state_label = "mixed_local_package"

            driver_map = {
                "win": abs(win_component),
                "wdo": abs(fx_component),
                "di_curve": abs(rates_component),
            }
            dominant_driver = max(driver_map, key=driver_map.get) if driver_map else "win"

            di_legs = []
            for spec, window in di_window_entries:
                di_legs.append({
                    "label": _contract_label(spec.get("ticker")),
                    "ticker": spec.get("ticker"),
                    "net_pressure_score": round(_score(window, "net"), 2),
                    "foreign_pressure_score": round(_score(window, "foreign"), 2),
                })

            rationale = " | ".join([
                f"win {round(win_component, 1)}",
                f"wdo {round(fx_component, 1)}",
                f"di {round(rates_component, 1)}",
                f"breadth {round(curve_breadth_score, 1)}%",
            ])

            payload = {
                "minutes": minutes,
                "window_label": f"{minutes}m",
                "state": state_label,
                "bias_side": "buy" if local_package_score > 0 else "sell" if local_package_score < 0 else "neutral",
                "dominant_driver": dominant_driver,
                "local_package_score": round(local_package_score, 2),
                "foreign_package_score": round(foreign_package_score, 2),
                "curve_breadth_score": round(curve_breadth_score, 2),
                "on_confirmations": on_confirmations,
                "off_confirmations": off_confirmations,
                "win_component_score": round(win_component, 2),
                "wdo_component_score": round(fx_component, 2),
                "di_curve_component_score": round(rates_component, 2),
                "short_di_average_score": round(short_di_avg, 2),
                "long_di_average_score": round(long_di_avg, 2),
                "curve_slope_score": round(long_di_avg - short_di_avg, 2),
                "di_legs": di_legs,
                "rationale": rationale,
            }
            windows_payload.append(payload)
            if minutes == primary_window:
                primary_payload = payload

        if primary_payload is None and windows_payload:
            primary_payload = windows_payload[-1]

        return {
            "primary_window_minutes": primary_window,
            "primary_window_label": f"{primary_window}m",
            "di_curve_tickers": [spec.get("ticker") for spec in di_specs],
            "primary": primary_payload,
            "windows": windows_payload,
        }

    def _build_structural_divergence_model(
        self,
        assets: list[dict[str, Any]],
        cross_asset_flow_package: dict[str, Any],
    ) -> dict[str, Any]:
        asset_map = {asset.get("key"): asset for asset in assets if isinstance(asset, dict)}
        win_asset = asset_map.get("win") or {}

        def _window_map(model: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
            windows = {}
            for window in (model or {}).get("windows") or []:
                try:
                    minutes = int(window.get("minutes") or 0)
                except (TypeError, ValueError):
                    continue
                windows[minutes] = window
            return windows

        def _cohort_score(window: dict[str, Any] | None, cohort: str, field: str = "pressure_score") -> float:
            return float((((window or {}).get("cohorts") or {}).get(cohort) or {}).get(field) or 0.0)

        def _sign(value: float, threshold: float = 8.0) -> int:
            if value >= threshold:
                return 1
            if value <= -threshold:
                return -1
            return 0

        pressure_windows = _window_map((win_asset.get("pressure_model") or {}))
        divergence_windows = _window_map((win_asset.get("divergence_model") or {}))
        concentration_windows = _window_map((win_asset.get("concentration_model") or {}))
        package_windows = _window_map(cross_asset_flow_package)

        primary_window = int(cross_asset_flow_package.get("primary_window_minutes") or 5)
        configured_windows = sorted(set(package_windows.keys()) | set(pressure_windows.keys()) | {primary_window})

        windows_payload: list[dict[str, Any]] = []
        primary_payload: dict[str, Any] | None = None

        for minutes in configured_windows:
            pressure_window = pressure_windows.get(minutes) or {}
            divergence_window = divergence_windows.get(minutes) or {}
            concentration_window = concentration_windows.get(minutes) or {}
            package_window = package_windows.get(minutes) or {}

            win_net = _cohort_score(pressure_window, "net")
            win_foreign = _cohort_score(pressure_window, "foreign")
            package_score = float(package_window.get("local_package_score") or 0.0)
            foreign_package_score = float(package_window.get("foreign_package_score") or 0.0)
            lead_score = float(divergence_window.get("lead_score") or 0.0)
            divergence_score = float(divergence_window.get("divergence_score") or 0.0)
            concentration_state = ((((concentration_window.get("cohorts") or {}).get("net")) or {}).get("state")) or "inactive"

            sign_win = _sign(win_net, 8.0)
            sign_package = _sign(package_score, 8.0)
            sign_foreign_package = _sign(foreign_package_score, 8.0)
            sign_lead = _sign(lead_score, 10.0)

            confirmation_score = 0.0
            non_confirmation_score = 0.0

            if sign_win != 0 and sign_package != 0:
                if sign_win == sign_package:
                    confirmation_score += 28.0 + (min(abs(win_net), abs(package_score)) * 0.22)
                else:
                    non_confirmation_score += 32.0 + (max(abs(win_net), abs(package_score)) * 0.24)

            if sign_win != 0 and sign_foreign_package != 0:
                if sign_win == sign_foreign_package:
                    confirmation_score += 18.0 + (min(abs(win_foreign), abs(foreign_package_score)) * 0.16)
                else:
                    non_confirmation_score += 18.0 + (max(abs(win_foreign), abs(foreign_package_score)) * 0.14)

            if sign_win != 0 and sign_lead != 0:
                if sign_win == sign_lead:
                    confirmation_score += 12.0 + (abs(lead_score) * 0.12)
                else:
                    non_confirmation_score += 12.0 + (abs(lead_score) * 0.12)

            divergence_state = str(divergence_window.get("state") or "")
            if divergence_state == "foreign_sell_vs_retail_buy" and sign_win > 0:
                non_confirmation_score += 10.0 + (abs(divergence_score) * 0.10)
            if divergence_state == "foreign_buy_vs_retail_sell" and sign_win < 0:
                non_confirmation_score += 10.0 + (abs(divergence_score) * 0.10)

            if concentration_state in {"single_name_push", "concentrated_drive"}:
                if sign_win != 0 and sign_package != 0 and sign_win != sign_package:
                    non_confirmation_score += 12.0
                else:
                    non_confirmation_score += 5.0

            confirmation_score = _clamp(confirmation_score, 0.0, 100.0)
            non_confirmation_score = _clamp(non_confirmation_score, 0.0, 100.0)

            if confirmation_score >= non_confirmation_score + 12.0:
                if (sign_win if sign_win != 0 else sign_package) > 0:
                    state = "confirmed_bullish"
                    bias_side = "buy"
                elif (sign_win if sign_win != 0 else sign_package) < 0:
                    state = "confirmed_bearish"
                    bias_side = "sell"
                else:
                    state = "neutral_balance"
                    bias_side = "neutral"
            elif non_confirmation_score >= confirmation_score + 12.0:
                if sign_win > 0:
                    state = "bearish_non_confirmation"
                    bias_side = "sell"
                elif sign_win < 0:
                    state = "bullish_non_confirmation"
                    bias_side = "buy"
                else:
                    state = "cross_asset_dissonance"
                    bias_side = "neutral"
            elif abs(package_score) < 8.0 and abs(win_net) < 8.0:
                state = "neutral_balance"
                bias_side = "neutral"
            else:
                state = "mixed_confirmation"
                bias_side = "buy" if package_score > 0 else "sell" if package_score < 0 else "neutral"

            rationale = " | ".join([
                f"win {round(win_net, 1)}",
                f"pkg {round(package_score, 1)}",
                f"foreign {round(foreign_package_score, 1)}",
                f"lead {round(lead_score, 1)}",
            ])

            payload = {
                "minutes": minutes,
                "window_label": f"{minutes}m",
                "state": state,
                "bias_side": bias_side,
                "confirmation_score": round(confirmation_score, 2),
                "non_confirmation_score": round(non_confirmation_score, 2),
                "win_net_score": round(win_net, 2),
                "package_score": round(package_score, 2),
                "foreign_package_score": round(foreign_package_score, 2),
                "lead_score": round(lead_score, 2),
                "divergence_score": round(divergence_score, 2),
                "concentration_state": concentration_state,
                "rationale": rationale,
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

    def _build_continuation_reversal_model(
        self,
        assets: list[dict[str, Any]],
        cross_asset_flow_package: dict[str, Any],
        structural_divergence_model: dict[str, Any],
    ) -> dict[str, Any]:
        asset_map = {asset.get("key"): asset for asset in assets if isinstance(asset, dict)}
        win_asset = asset_map.get("win") or {}

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

        def _sign(value: float, threshold: float = 8.0) -> int:
            if value >= threshold:
                return 1
            if value <= -threshold:
                return -1
            return 0

        pressure_windows = _window_map((win_asset.get("pressure_model") or {}))
        divergence_windows = _window_map((win_asset.get("divergence_model") or {}))
        concentration_windows = _window_map((win_asset.get("concentration_model") or {}))
        package_windows = _window_map(cross_asset_flow_package)
        smt_windows = _window_map(structural_divergence_model)

        level_defense = ((win_asset.get("level_defense_model") or {}).get("cohorts") or {}).get("net") or {}
        flow_regime = ((win_asset.get("flow_regime_classifier") or {}).get("cohorts") or {}).get("net") or {}

        primary_window = int(cross_asset_flow_package.get("primary_window_minutes") or 5)
        configured_windows = sorted(set(package_windows.keys()) | set(pressure_windows.keys()) | {primary_window})

        windows_payload: list[dict[str, Any]] = []
        primary_payload: dict[str, Any] | None = None

        for minutes in configured_windows:
            pressure_window = pressure_windows.get(minutes) or {}
            divergence_window = divergence_windows.get(minutes) or {}
            concentration_window = concentration_windows.get(minutes) or {}
            package_window = package_windows.get(minutes) or {}
            smt_window = smt_windows.get(minutes) or {}

            win_net = _cohort_score(pressure_window, "net", "pressure_score")
            efficiency = _cohort_score(pressure_window, "net", "delta_efficiency_score")
            absorption = _cohort_score(pressure_window, "net", "absorption_score")
            fragility = _cohort_score(pressure_window, "net", "fragility_score")
            package_score = float(package_window.get("local_package_score") or 0.0)
            divergence_state = str(divergence_window.get("state") or "")
            concentration_state = ((((concentration_window.get("cohorts") or {}).get("net")) or {}).get("state")) or "inactive"
            smt_state = str(smt_window.get("state") or "")

            direction = _sign(win_net, 8.0)
            if direction == 0:
                direction = _sign(package_score, 8.0)

            continuation_score = 0.0
            reversal_score = 0.0

            continuation_score += abs(win_net) * 0.34
            continuation_score += max(efficiency, 0.0) * 0.18
            if direction != 0 and _sign(package_score, 8.0) == direction:
                continuation_score += abs(package_score) * 0.18
            if smt_state in {"confirmed_bullish", "confirmed_bearish"}:
                if (smt_state == "confirmed_bullish" and direction > 0) or (smt_state == "confirmed_bearish" and direction < 0):
                    continuation_score += 16.0
            if concentration_state == "broad_participation":
                continuation_score += 10.0
            elif concentration_state == "two_way_participation":
                continuation_score += 6.0

            level_state = str(level_defense.get("primary_state") or "")
            if direction > 0 and level_state in {"support_defense", "accepted_value"}:
                continuation_score += 10.0
            if direction < 0 and level_state in {"resistance_defense", "accepted_value"}:
                continuation_score += 10.0

            regime_state = str(flow_regime.get("regime_state") or "")
            if direction > 0 and regime_state == "initiative_break_buy":
                continuation_score += 12.0
            if direction < 0 and regime_state == "initiative_break_sell":
                continuation_score += 12.0

            reversal_score += max(absorption, 0.0) * 0.18
            reversal_score += max(fragility, 0.0) * 0.16
            if direction > 0 and smt_state == "bearish_non_confirmation":
                reversal_score += 18.0
            if direction < 0 and smt_state == "bullish_non_confirmation":
                reversal_score += 18.0
            if concentration_state in {"single_name_push", "concentrated_drive"}:
                reversal_score += 10.0
            if direction > 0 and level_state in {"rejection_above_value", "resistance_defense", "responsive_rejection"}:
                reversal_score += 12.0
            if direction < 0 and level_state in {"rejection_below_value", "support_defense", "responsive_rejection"}:
                reversal_score += 12.0
            if direction > 0 and divergence_state == "foreign_sell_vs_retail_buy":
                reversal_score += 10.0
            if direction < 0 and divergence_state == "foreign_buy_vs_retail_sell":
                reversal_score += 10.0
            if direction != 0 and _sign(package_score, 8.0) == -direction:
                reversal_score += 14.0

            continuation_score = _clamp(continuation_score, 0.0, 100.0)
            reversal_score = _clamp(reversal_score, 0.0, 100.0)
            total = continuation_score + reversal_score + 20.0
            continuation_probability = ((continuation_score + 10.0) / total) * 100.0
            reversal_probability = ((reversal_score + 10.0) / total) * 100.0

            if continuation_probability >= 60.0 and continuation_score >= reversal_score + 10.0:
                if direction > 0:
                    state = "continuation_up"
                    bias_side = "buy"
                elif direction < 0:
                    state = "continuation_down"
                    bias_side = "sell"
                else:
                    state = "balanced_transition"
                    bias_side = "neutral"
            elif reversal_probability >= 60.0 and reversal_score >= continuation_score + 10.0:
                if direction > 0:
                    state = "reversal_down"
                    bias_side = "sell"
                elif direction < 0:
                    state = "reversal_up"
                    bias_side = "buy"
                else:
                    state = "balanced_transition"
                    bias_side = "neutral"
            else:
                state = "balanced_transition"
                bias_side = "neutral"

            rationale = " | ".join([
                f"cont {round(continuation_score, 1)}",
                f"rev {round(reversal_score, 1)}",
                f"smt {smt_state or '--'}",
                f"lvl {level_state or '--'}",
            ])

            payload = {
                "minutes": minutes,
                "window_label": f"{minutes}m",
                "state": state,
                "bias_side": bias_side,
                "continuation_score": round(continuation_score, 2),
                "reversal_score": round(reversal_score, 2),
                "continuation_probability": round(continuation_probability, 2),
                "reversal_probability": round(reversal_probability, 2),
                "win_net_score": round(win_net, 2),
                "package_score": round(package_score, 2),
                "efficiency_score": round(efficiency, 2),
                "absorption_score": round(absorption, 2),
                "fragility_score": round(fragility, 2),
                "smt_state": smt_state,
                "concentration_state": concentration_state,
                "level_state": level_state,
                "rationale": rationale,
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

    def _build_news_thermometer_context(self) -> dict[str, Any]:
        try:
            result = MacroThermometerService(store=self.store).get_thermometer(refresh=False)
        except Exception as exc:
            return {
                "available": False,
                "error": str(exc),
                "bias": "watch",
                "marker": "unknown",
                "directional_score": 0.0,
                "confidence_score": 0.0,
                "freshness_score": 0.0,
            }

        thermometer = (result.get("thermometer") or {})
        overall = thermometer.get("overall") or {}
        equity = thermometer.get("equity") or {}
        credit = thermometer.get("credit") or {}
        fx = thermometer.get("fx") or {}
        ai_summary = result.get("ai_summary") or {}
        timeline = thermometer.get("timeline") or []
        latest_event = timeline[-1] if timeline else {}
        timeline_payload = []
        for item in timeline[-160:]:
            timeline_payload.append({
                "time": item.get("time"),
                "headline": item.get("headline"),
                "driver_title": item.get("driver_title"),
                "impact_score": int(item.get("impact_score") or 0),
                "expected_impact_score": int(item.get("expected_impact_score") or 0),
                "recommended_action": item.get("recommended_action"),
                "market_regime": item.get("market_regime"),
                "event_bias": item.get("event_bias"),
                "marker": item.get("marker"),
                "summary": item.get("summary"),
            })

        generated_at = _parse_iso(result.get("generated_at"))
        latest_event_at = _parse_iso(latest_event.get("time"))
        age_minutes: float | None = None
        if latest_event_at is not None:
            age_minutes = max(0.0, (_utc_now() - latest_event_at).total_seconds() / 60.0)

        freshness_score = 0.0
        if age_minutes is None:
            freshness_score = 0.0
        elif age_minutes <= 10:
            freshness_score = 100.0
        elif age_minutes <= 20:
            freshness_score = 92.0
        elif age_minutes <= 40:
            freshness_score = 78.0
        elif age_minutes <= 60:
            freshness_score = 64.0
        elif age_minutes <= 120:
            freshness_score = 42.0
        else:
            freshness_score = 20.0

        overall_score = float(overall.get("score") or 0.0)
        equity_score = float(equity.get("score") or 0.0)
        credit_score = float(credit.get("score") or 0.0)
        fx_score = float(fx.get("score") or 0.0)
        composite_score = ((equity_score * 0.6) + (overall_score * 0.4))
        directional_score = _clamp(composite_score * (freshness_score / 100.0), -100.0, 100.0)

        confidence_score = _clamp(
            ((float(overall.get("probability") or 0.0) * 0.45)
             + (float(equity.get("probability") or 0.0) * 0.55))
            * (0.45 + (freshness_score / 100.0) * 0.55),
            0.0,
            100.0,
        )

        bias = str(ai_summary.get("action_bias") or overall.get("bias") or "watch")
        marker = str(overall.get("marker") or "neutral")
        if bias not in {"buy", "sell", "watch"}:
            bias = "watch"

        if abs(directional_score) >= 45.0 and freshness_score >= 70.0:
            strength_label = "strong"
        elif abs(directional_score) >= 20.0 and freshness_score >= 40.0:
            strength_label = "moderate"
        elif abs(directional_score) >= 8.0:
            strength_label = "light"
        else:
            strength_label = "background"

        return {
            "available": True,
            "generated_at": generated_at.isoformat() if generated_at else result.get("generated_at"),
            "latest_event_at": latest_event_at.isoformat() if latest_event_at else None,
            "age_minutes": round(age_minutes, 2) if age_minutes is not None else None,
            "freshness_score": round(freshness_score, 2),
            "strength_label": strength_label,
            "bias": bias,
            "marker": marker,
            "directional_score": round(directional_score, 2),
            "confidence_score": round(confidence_score, 2),
            "overall_score": round(overall_score, 2),
            "equity_score": round(equity_score, 2),
            "credit_score": round(credit_score, 2),
            "fx_score": round(fx_score, 2),
            "overall_probability": float(overall.get("probability") or 0.0),
            "equity_probability": float(equity.get("probability") or 0.0),
            "drivers_count": int(thermometer.get("drivers_count") or 0),
            "news_count": int(thermometer.get("news_count") or 0),
            "headline": latest_event.get("headline"),
            "driver_title": latest_event.get("driver_title"),
            "recommended_action": latest_event.get("recommended_action"),
            "market_regime": latest_event.get("market_regime"),
            "summary": ai_summary.get("market_commentary") or ai_summary.get("why") or (result.get("overview_bridge") or {}).get("summary"),
            "why": ai_summary.get("why"),
            "execution_commentary": ai_summary.get("execution_commentary"),
            "timeline_count": len(timeline),
            "timeline": timeline_payload,
        }

    def _build_options_flow_alignment_model(
        self,
        assets: list[dict[str, Any]],
        cross_asset_flow_package: dict[str, Any],
        win_trade_thermometer: dict[str, Any],
        liquidity_intelligence_model: dict[str, Any],
        options_heatmap_context: dict[str, Any],
    ) -> dict[str, Any]:
        gamma_context = (options_heatmap_context or {}).get("gamma_context") or {}
        fair_value_history = (options_heatmap_context or {}).get("fair_value_history") or {}
        latest_sample = fair_value_history.get("latest_sample") or {}
        if not gamma_context:
            return {
                "available": False,
                "commentary": "Sem contexto de opcoes/gamma no momento.",
            }

        win_asset = next((asset for asset in assets if asset.get("key") == "win"), None) or {}
        trade_primary = (win_trade_thermometer or {}).get("primary") or {}
        liquidity_primary = ((liquidity_intelligence_model or {}).get("primary_asset") or {}).get("primary") or {}
        current_price = (
            _safe_float(win_asset.get("latest_price"))
            or _safe_float(trade_primary.get("current_price"))
            or _safe_float(gamma_context.get("current_future_price"))
            or 0.0
        )
        fair_value_price = (
            _safe_float(latest_sample.get("fair_value_final_future"))
            or _safe_float(gamma_context.get("fair_value_price"))
            or 0.0
        )
        basis_points = _safe_float(gamma_context.get("basis_points")) or 0.0
        mispricing_value = current_price - fair_value_price if current_price and fair_value_price else 0.0
        mispricing_zscore = _safe_float(latest_sample.get("mispricing_zscore"))
        if mispricing_zscore is None and fair_value_price:
            fair_low = _safe_float(latest_sample.get("fair_value_band_low"))
            fair_high = _safe_float(latest_sample.get("fair_value_band_high"))
            band_width = max(abs((fair_high or fair_value_price) - (fair_low or fair_value_price)), 80.0)
            mispricing_zscore = mispricing_value / band_width

        all_regions = [dict(item or {}) for item in (gamma_context.get("regions") or [])] + [
            dict(item or {}) for item in (gamma_context.get("special_regions") or [])
        ]
        for region in all_regions:
            band_low = _safe_float(region.get("band_low"))
            band_high = _safe_float(region.get("band_high"))
            price = _safe_float(region.get("price"))
            if price is None:
                continue
            if band_low is None:
                band_low = price
            if band_high is None:
                band_high = price
            if current_price < min(band_low, band_high):
                distance = current_price - min(band_low, band_high)
            elif current_price > max(band_low, band_high):
                distance = current_price - max(band_low, band_high)
            else:
                distance = 0.0
            band_span = max(abs(band_high - band_low), 10.0)
            region["distance_to_price_points"] = round(distance, 2)
            region["near_price"] = abs(distance) <= max(band_span * 1.2, 220.0)
        all_regions.sort(key=lambda item: abs(_safe_float(item.get("distance_to_price_points")) or 0.0))
        nearest_region = all_regions[0] if all_regions else None

        block_tones = [dict(item or {}) for item in (latest_sample.get("block_tones") or [])]
        total_block_contribution = sum(abs(_safe_float(item.get("contribution_points")) or 0.0) for item in block_tones[:3])
        block_bias_score = 0.0
        if total_block_contribution > 0:
            signed = sum(_safe_float(item.get("contribution_points")) or 0.0 for item in block_tones[:3])
            block_bias_score = _clamp((signed / total_block_contribution) * 100.0, -100.0, 100.0)

        flow_score = _safe_float(trade_primary.get("directional_score")) or 0.0
        gamma_score = 0.0
        gamma_state = "neutral_gamma"
        if nearest_region:
            role = str(nearest_region.get("role") or nearest_region.get("region_type") or "")
            near_price = bool(nearest_region.get("near_price"))
            if "negative_gamma" in role or "acceleration" in role:
                gamma_state = "negative_gamma_near" if near_price else "negative_gamma_far"
                gamma_score = flow_score * (0.28 if near_price else 0.12)
            elif "positive_gamma" in role or "pinning" in role:
                gamma_state = "positive_gamma_near" if near_price else "positive_gamma_far"
                if mispricing_value > 0:
                    gamma_score = -25.0 if near_price else -10.0
                elif mispricing_value < 0:
                    gamma_score = 25.0 if near_price else 10.0
            elif "balance" in role or "inventory" in role:
                gamma_state = "balance_region_near" if near_price else "balance_region_far"
                gamma_score = -8.0 if near_price else 0.0

        fair_value_bias_score = 0.0
        fair_value_state = "fair_value_balanced"
        if fair_value_price > 0 and mispricing_zscore is not None:
            if mispricing_zscore >= 0.75:
                fair_value_state = "overpriced_vs_fair_value"
                fair_value_bias_score = -min(abs(mispricing_zscore) * 24.0, 32.0)
            elif mispricing_zscore <= -0.75:
                fair_value_state = "underpriced_vs_fair_value"
                fair_value_bias_score = min(abs(mispricing_zscore) * 24.0, 32.0)

        continuation_score = _safe_float((((cross_asset_flow_package or {}).get("primary") or {}).get("local_score"))) or 0.0
        combined_directional = _clamp(
            (flow_score * 0.42)
            + (fair_value_bias_score * 0.22)
            + (gamma_score * 0.20)
            + (block_bias_score * 0.10)
            + (continuation_score * 0.06),
            -100.0,
            100.0,
        )
        confidence_score = _clamp(
            (abs(flow_score) * 0.35)
            + (abs(fair_value_bias_score) * 0.20)
            + (abs(gamma_score) * 0.18)
            + (abs(block_bias_score) * 0.12)
            + ((_safe_float(nearest_region.get("relevance_score")) or 0.0) * 0.15 if nearest_region else 0.0),
            0.0,
            100.0,
        )
        action_bias = "buy" if combined_directional >= 18 else "sell" if combined_directional <= -18 else "stand_aside"

        def _fmt_price(value: Any) -> str:
            parsed = _safe_float(value)
            if parsed is None:
                return "--"
            return f"{parsed:,.1f}"

        commentary_parts: list[str] = []
        if nearest_region:
            commentary_parts.append(
                f"Preco perto de {nearest_region.get('display_label') or nearest_region.get('short_label')} "
                f"em {_fmt_price(nearest_region.get('price'))} ({nearest_region.get('role') or nearest_region.get('region_type')})."
            )
        if fair_value_price:
            if mispricing_zscore is not None:
                commentary_parts.append(
                    f"Fair value {_fmt_price(fair_value_price)} com desvio {mispricing_value:+.1f} pts e z {mispricing_zscore:+.2f}."
                )
            else:
                commentary_parts.append(
                    f"Fair value {_fmt_price(fair_value_price)} com desvio {mispricing_value:+.1f} pts."
                )
        if block_tones:
            dominant_block = block_tones[0]
            dominant_contribution = _safe_float(dominant_block.get("contribution_points")) or 0.0
            commentary_parts.append(
                f"Perna dominante {dominant_block.get('block')} em {dominant_block.get('tone')} ({dominant_contribution:+.1f} pts)."
            )
        if liquidity_primary.get("commentary"):
            commentary_parts.append(str(liquidity_primary.get("commentary")).strip())

        region_focus = []
        for region in all_regions[:4]:
            region_focus.append({
                "display_label": region.get("display_label") or region.get("short_label"),
                "price": _safe_float(region.get("price")),
                "band_low": _safe_float(region.get("band_low")),
                "band_high": _safe_float(region.get("band_high")),
                "role": region.get("role") or region.get("region_type"),
                "distance_to_price_points": _safe_float(region.get("distance_to_price_points")),
                "relevance_score": _safe_float(region.get("relevance_score")),
                "open_interest_total": _safe_float(region.get("open_interest_total")),
                "gex_notional_future_net": _safe_float(region.get("gex_notional_future_net")),
                "description": region.get("description"),
            })

        return {
            "available": True,
            "current_price": current_price or None,
            "basis_points": basis_points,
            "fair_value_price": fair_value_price or None,
            "mispricing_value": round(mispricing_value, 2) if fair_value_price else None,
            "mispricing_zscore": round(mispricing_zscore, 2) if mispricing_zscore is not None else None,
            "fair_value_state": fair_value_state,
            "gamma_state": gamma_state,
            "action_bias": action_bias,
            "directional_score": round(combined_directional, 2),
            "confidence_score": round(confidence_score, 2),
            "block_bias_score": round(block_bias_score, 2),
            "gamma_score": round(gamma_score, 2),
            "fair_value_bias_score": round(fair_value_bias_score, 2),
            "flow_score": round(flow_score, 2),
            "liquidity_score": round(_safe_float(liquidity_primary.get("thin_liquidity_score")) or 0.0, 2),
            "nearest_region": nearest_region,
            "region_focus": region_focus,
            "leg_tones": block_tones[:4],
            "commentary": " ".join(part for part in commentary_parts if part).strip(),
        }

    def _build_win_trade_thermometer(
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
            if bias_side == "buy" and regime_state == "initiative_break_buy":
                timing_score += 18.0
            elif bias_side == "sell" and regime_state == "initiative_break_sell":
                timing_score += 18.0
            elif bias_side == "buy" and regime_state in {"responsive_rejection_buy", "divergence_buy"}:
                timing_score += 10.0
            elif bias_side == "sell" and regime_state in {"responsive_rejection_sell", "divergence_sell"}:
                timing_score += 10.0

            if bias_side != "neutral" and continuation_state.startswith("continuation_") and continuation_bias == bias_side:
                timing_score += 14.0
            if bias_side != "neutral" and continuation_state.startswith("reversal_") and continuation_bias == bias_side:
                timing_score += 12.0

            if bias_side == "buy" and level_state in {"support_defense", "rejection_below_value", "responsive_rejection"}:
                timing_score += 14.0
            elif bias_side == "sell" and level_state in {"resistance_defense", "rejection_above_value", "responsive_rejection"}:
                timing_score += 14.0
            elif level_state == "accepted_value":
                timing_score += 8.0

            if bias_side == "buy" and current_position == "below_value":
                timing_score += 8.0
            elif bias_side == "sell" and current_position == "above_value":
                timing_score += 8.0
            elif bias_side == "buy" and current_position == "above_value" and continuation_state == "continuation_up":
                timing_score += 6.0
            elif bias_side == "sell" and current_position == "below_value" and continuation_state == "continuation_down":
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

