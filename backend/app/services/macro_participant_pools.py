from __future__ import annotations

from typing import Any

from .macro_participant_context import MacroParticipantContextMixin
from .macro_participant_math import _clamp, _safe_float


class MacroParticipantPoolMixin(MacroParticipantContextMixin):
    def _build_liquidity_pool_model(  # noqa: C901
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
            if asset_key == "win" or primary_asset is None:
                primary_asset = asset_payload

        return {
            "primary_asset_key": (primary_asset or {}).get("asset_key"),
            "primary": (primary_asset or {}).get("primary"),
            "primary_asset": primary_asset,
            "assets": assets_payload,
            "methodology_note": "Synthetic intraday inventory-at-risk model. Uses OFI, depth proxies, clustered value-map regions, and stop-cascade heuristics. It does not observe true exchange open interest intraday.",
        }
