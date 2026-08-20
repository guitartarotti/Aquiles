from __future__ import annotations

from typing import Any

from .macro_participant_context import MacroParticipantContextMixin
from .macro_participant_math import _clamp, _parse_iso, _safe_float, _utc_now
from .macro_thermometer_service import MacroThermometerService


class MacroParticipantSignalMixin(MacroParticipantContextMixin):
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
