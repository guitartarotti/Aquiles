from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..config import Config


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


class OptionsUniverseService:
    def build_structural_universe(
        self,
        contracts: list[dict[str, Any]],
        market_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        market_by_security = {
            str(row.get("security") or ""): row
            for row in market_rows
            if row.get("security")
        }
        structural_rows: list[dict[str, Any]] = []
        strategic_strikes = {str(value) for value in Config.OPTIONS_STRATEGIC_STRIKES}

        for contract in contracts:
            security = str(contract.get("bloomberg_ticker") or "")
            market_row = market_by_security.get(security, {})
            fields = market_row.get("fields") or {}
            underlying_px = _safe_float(fields.get("OPT_UNDL_PX"))
            strike = _safe_float(fields.get("OPT_STRIKE_PX")) or _safe_float(contract.get("strike"))
            bid = _safe_float(fields.get("BID"))
            ask = _safe_float(fields.get("ASK"))
            px_volume = _safe_float(fields.get("PX_VOLUME")) or _safe_float(fields.get("VOLUME")) or 0.0
            open_int = _safe_float(fields.get("OPT_OPEN_INTEREST"))
            if open_int is None:
                open_int = _safe_float(fields.get("OPEN_INT")) or 0.0
            distance_to_atm = None
            moneyness_spot = None
            if underlying_px and underlying_px > 0 and strike is not None:
                moneyness_spot = (strike / underlying_px) - 1.0
                distance_to_atm = abs(moneyness_spot)

            valid_bid_ask = bid is not None and ask is not None and ask >= bid and ask > 0
            near_atm = distance_to_atm is not None and distance_to_atm <= Config.OPTIONS_ATM_PROXIMITY_PCT
            in_band = distance_to_atm is not None and distance_to_atm <= Config.OPTIONS_MONEYNESS_BAND_PCT
            strategic = str(int(strike)) in strategic_strikes if strike is not None and strike.is_integer() else str(strike) in strategic_strikes

            inclusion_reasons: list[str] = []
            if open_int and open_int > 0:
                inclusion_reasons.append("oi_positive")
            if px_volume and px_volume > 0:
                inclusion_reasons.append("volume_positive")
            if valid_bid_ask:
                inclusion_reasons.append("valid_bid_ask")
            if near_atm:
                inclusion_reasons.append("near_atm")
            if strategic:
                inclusion_reasons.append("strategic_strike")

            expiry_days = contract.get("days_to_expiry_business")
            expiry_days = int(expiry_days) if expiry_days is not None else 9999

            eligible = (
                contract.get("status") == "active"
                and expiry_days <= Config.OPTIONS_MAX_BUSINESS_DAYS
                and in_band
                and bool(inclusion_reasons)
            )

            structural_rows.append({
                **contract,
                "underlying_price": underlying_px,
                "strike": strike,
                "moneyness_spot": moneyness_spot,
                "distance_to_atm": distance_to_atm,
                "bid": bid,
                "ask": ask,
                "px_volume": px_volume,
                "open_int": open_int,
                "valid_bid_ask": valid_bid_ask,
                "near_atm": near_atm,
                "in_band": in_band,
                "strategic_strike": strategic,
                "structural_eligible": eligible,
                "selection_reason": inclusion_reasons,
                "market_ok": bool(market_row.get("ok")),
                "market_field_exceptions": market_row.get("field_exceptions") or [],
            })

        structural_rows.sort(
            key=lambda row: (
                row.get("expiry_date") or "",
                row.get("distance_to_atm") if row.get("distance_to_atm") is not None else 999,
                -(row.get("open_int") or 0),
            )
        )
        return structural_rows

    def build_liquid_universe(self, structural_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        eligible_rows = [row for row in structural_rows if row.get("structural_eligible")]
        if not eligible_rows:
            return []

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in eligible_rows:
            grouped[str(row.get("expiry_date") or "")].append(row)

        selected_ids: set[str] = set()
        for expiry, rows in grouped.items():
            rows_by_oi = sorted(rows, key=lambda row: row.get("open_int") or 0, reverse=True)
            rows_by_volume = sorted(rows, key=lambda row: row.get("px_volume") or 0, reverse=True)
            rows_by_atm = sorted(
                rows,
                key=lambda row: row.get("distance_to_atm") if row.get("distance_to_atm") is not None else 999,
            )
            limit = max(1, Config.OPTIONS_LIQUID_TOP_N_PER_EXPIRY)
            for bucket in (rows_by_oi[:limit], rows_by_volume[:limit], rows_by_atm[: limit * 2]):
                for row in bucket:
                    selected_ids.add(str(row.get("option_id")))

        selected_rows = [row for row in eligible_rows if str(row.get("option_id")) in selected_ids]
        scored_rows = [self.score_contract(row) for row in selected_rows]
        scored_rows.sort(key=lambda row: row.get("relevance_score") or 0, reverse=True)
        return scored_rows[: Config.OPTIONS_LIQUID_MAX_CONTRACTS]

    def build_critical_universe(self, liquid_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not liquid_rows:
            return []
        sorted_rows = sorted(
            liquid_rows,
            key=lambda row: (
                row.get("days_to_expiry_business") if row.get("days_to_expiry_business") is not None else 9999,
                -(row.get("relevance_score") or 0),
                row.get("distance_to_atm") if row.get("distance_to_atm") is not None else 999,
            )
        )
        return sorted_rows[: Config.OPTIONS_CRITICAL_MAX_CONTRACTS]

    def score_contract(self, row: dict[str, Any]) -> dict[str, Any]:
        distance_to_atm = row.get("distance_to_atm")
        open_int = row.get("open_int") or 0.0
        day_volume = row.get("px_volume") or 0.0
        spread_pct = self._spread_pct(row.get("bid"), row.get("ask"))
        expiry_days_raw = row.get("days_to_expiry_business")
        expiry_days = int(expiry_days_raw) if expiry_days_raw is not None else 9999

        atm_proximity_score = 0.0
        if distance_to_atm is not None:
            atm_proximity_score = max(0.0, 1.0 - min(distance_to_atm / max(Config.OPTIONS_MONEYNESS_BAND_PCT, 1e-6), 1.0))

        oi_rank_score = min(open_int / 1_000_000.0, 1.0)
        day_volume_rank_score = min(day_volume / 100_000.0, 1.0)
        recent_trade_score = 1.0 if day_volume > 0 else 0.0
        spread_quality_score = 0.0
        if spread_pct is not None:
            spread_quality_score = max(0.0, 1.0 - min(spread_pct / 0.10, 1.0))
        expiry_urgency_score = max(0.0, 1.0 - min(expiry_days / max(Config.OPTIONS_MAX_BUSINESS_DAYS, 1), 1.0))
        greek_importance_proxy = min((open_int * atm_proximity_score) / 1_000_000.0, 1.0)

        relevance_score = round(
            (
                0.30 * atm_proximity_score
                + 0.20 * oi_rank_score
                + 0.15 * day_volume_rank_score
                + 0.10 * recent_trade_score
                + 0.10 * spread_quality_score
                + 0.10 * expiry_urgency_score
                + 0.05 * greek_importance_proxy
            ) * 100,
            4,
        )

        return {
            **row,
            "spread_pct": spread_pct,
            "relevance_score": relevance_score,
            "relevance_components": {
                "atm_proximity_score": atm_proximity_score,
                "oi_rank_score": oi_rank_score,
                "day_volume_rank_score": day_volume_rank_score,
                "recent_trade_score": recent_trade_score,
                "spread_quality_score": spread_quality_score,
                "expiry_urgency_score": expiry_urgency_score,
                "greek_importance_proxy": greek_importance_proxy,
            },
        }

    def summarize_universe(
        self,
        underlying_security: str,
        full_rows: list[dict[str, Any]],
        structural_rows: list[dict[str, Any]],
        liquid_rows: list[dict[str, Any]],
        critical_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        structural_eligible = [row for row in structural_rows if row.get("structural_eligible")]
        return {
            "underlying_security": underlying_security,
            "full_total": len(full_rows),
            "structural_total": len(structural_rows),
            "structural_eligible": len(structural_eligible),
            "liquid_total": len(liquid_rows),
            "critical_total": len(critical_rows),
            "nearest_expiry": min(
                (row.get("expiry_date") for row in structural_eligible if row.get("expiry_date")),
                default=None,
            ),
            "farthest_expiry": max(
                (row.get("expiry_date") for row in structural_eligible if row.get("expiry_date")),
                default=None,
            ),
        }

    def _spread_pct(self, bid: Any, ask: Any) -> float | None:
        bid_value = _safe_float(bid)
        ask_value = _safe_float(ask)
        if bid_value is None or ask_value is None or ask_value <= 0 or ask_value < bid_value:
            return None
        mid = (bid_value + ask_value) / 2.0
        if mid <= 0:
            return None
        return (ask_value - bid_value) / mid
