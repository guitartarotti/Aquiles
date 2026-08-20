from __future__ import annotations

from typing import Any

from .macro_participant_context import MacroParticipantContextMixin
from .macro_participant_math import _clamp


class MacroParticipantCrossAssetMixin(MacroParticipantContextMixin):
    def _build_cross_asset_flow_package(self, state: dict[str, Any], specs: list[dict[str, Any]]) -> dict[str, Any]:
        assets_state: dict[str, Any] = state.get("assets", {}) or {}
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
            ticker = str(spec.get("ticker") or "")
            asset_state = assets_state.get(ticker) or {}
            samples = asset_state.get("samples")
            return self._build_pressure_model(samples if isinstance(samples, list) else [])

        def _window_entry(model: dict[str, Any], minutes: int) -> dict[str, Any]:
            for window in model.get("windows") or []:
                if isinstance(window, dict) and int(window.get("minutes") or 0) == minutes:
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
            dominant_driver = max(driver_map, key=lambda driver: driver_map[driver]) if driver_map else "win"

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
