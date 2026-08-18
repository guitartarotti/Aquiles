from __future__ import annotations

import math
from typing import Any

from ...config import Config
from .market_context import infer_carry_from_forward, interpolate_rate_for_days
from .math_utils import clamp, normalize_vol
from .types import MarketContext, ModelRunConfig, PreparedOption


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _pick_first(*values: Any) -> float | None:
    for value in values:
        parsed = _safe_float(value)
        if parsed is not None:
            return parsed
    return None


def _choose_iv(row: dict[str, Any]) -> float:
    # EFF_IV tem prioridade — calculado pelo modelo proprietario a partir do preco mid real.
    # Fallback para IVOL_MID/LAST do historico OpLab, depois bid/ask medio.
    value = _pick_first(row.get("EFF_IV"), row.get("IVOL_MID"), row.get("IVOL_LAST"))
    if value is None:
        bid = _safe_float(row.get("IVOL_BID"))
        ask = _safe_float(row.get("IVOL_ASK"))
        if bid is not None and ask is not None:
            value = (bid + ask) / 2.0
        else:
            value = _pick_first(bid, ask, 0.20)
    return normalize_vol(value)


def _choose_open_interest(row: dict[str, Any], latest_oi_row: dict[str, Any] | None) -> float:
    current = _pick_first(row.get("OPT_OPEN_INTEREST"), row.get("OPEN_INT"))
    if current is not None:
        return max(current, 0.0)
    if latest_oi_row:
        historical = _pick_first(latest_oi_row.get("opt_open_interest"), latest_oi_row.get("open_int"))
        if historical is not None:
            return max(historical, 0.0)
    return 0.0


def _moneyness_bucket(distance_ratio: float) -> str:
    if distance_ratio <= 0.01:
        return "atm"
    if distance_ratio <= 0.03:
        return "near_atm"
    if distance_ratio <= 0.07:
        return "otm_itm"
    return "wing"


def _expiry_bucket(days_to_expiry_business: int) -> str:
    if days_to_expiry_business <= 5:
        return "0_5d"
    if days_to_expiry_business <= 21:
        return "6_21d"
    if days_to_expiry_business <= 63:
        return "22_63d"
    return "64_120d"


def _reliability_weight(row: dict[str, Any], selected_iv: float, selected_delta: float | None, selected_gamma: float | None) -> float:
    score = 0.25
    if not row.get("stale_flag"):
        score += 0.20
    if row.get("MID") is not None:
        score += 0.20
    if selected_iv > 0:
        score += 0.15
    if selected_delta is not None:
        score += 0.10
    if selected_gamma is not None:
        score += 0.10
    spread_pct = _safe_float(row.get("spread_pct"))
    if spread_pct is not None:
        score -= clamp(spread_pct / 0.35, 0.0, 0.20)
    return clamp(score, 0.0, 1.0)


def _liquidity_weight(row: dict[str, Any]) -> float:
    liquidity_score = _safe_float(row.get("liquidity_score"))
    if liquidity_score is not None:
        return clamp(liquidity_score / 100.0, 0.0, 1.0)
    spread_pct = _safe_float(row.get("spread_pct")) or 1.0
    volume = _safe_float(row.get("PX_VOLUME")) or _safe_float(row.get("VOLUME")) or 0.0
    oi = _pick_first(row.get("OPT_OPEN_INTEREST"), row.get("OPEN_INT")) or 0.0
    score = 0.10 + clamp(volume / 100000.0, 0.0, 0.35) + clamp(oi / 300000.0, 0.0, 0.35) - clamp(spread_pct / 0.20, 0.0, 0.20)
    return clamp(score, 0.0, 1.0)


def prepare_option_inputs(
    snapshot_rows: list[dict[str, Any]],
    market_context: MarketContext,
    latest_oi_map: dict[str, dict[str, Any]],
    run_config: ModelRunConfig,
    signal_payload_by_option: dict[str, dict[str, Any]],
) -> tuple[list[PreparedOption], dict[str, Any]]:
    prepared: list[PreparedOption] = []
    model_fallback_count = 0

    for row in snapshot_rows:
        option_id = str(row.get("option_id") or "").strip()
        if not option_id:
            continue
        strike = _pick_first(row.get("strike"), row.get("OPT_STRIKE_PX"))
        if strike is None or strike <= 0:
            continue
        spot = _pick_first(row.get("OPT_UNDL_PX"), market_context.spot_price)
        if spot is None or spot <= 0:
            continue
        days_business = int(row.get("days_to_expiry_business") or 0)
        if days_business > Config.OPTIONS_MAX_BUSINESS_DAYS:
            continue
        time_years = max(days_business / 252.0, run_config.min_time_years)
        interpolated_rate = interpolate_rate_for_days(days_business, market_context)
        forward_price = market_context.forward_price or spot
        carry = infer_carry_from_forward(spot, forward_price, interpolated_rate, time_years)
        selected_iv = _choose_iv(row)
        # Prioridade: EFF_* (modelo proprietario) > OPT_*_MID (Bloomberg) > OPT_* (Bloomberg)
        observed_delta = _pick_first(row.get("EFF_DELTA"),    row.get("OPT_DELTA_MID"), row.get("OPT_DELTA"))
        observed_gamma = _pick_first(row.get("EFF_GAMMA_PT"), row.get("OPT_GAMMA_MID"), row.get("OPT_GAMMA"))
        observed_vega  = _pick_first(row.get("EFF_VEGA"),     row.get("OPT_VEGA_MID"),  row.get("OPT_VEGA"))
        observed_theta = _pick_first(row.get("EFF_THETA"),    row.get("OPT_THETA_MID"), row.get("OPT_THETA"))
        # Vanna e Charm — exclusivos do modelo proprietario (OpLab nao fornece)
        observed_vanna = _safe_float(row.get("EFF_VANNA"))
        observed_charm = _safe_float(row.get("EFF_CHARM"))
        if observed_delta is None or observed_gamma is None:
            model_fallback_count += 1

        distance_points = abs(strike - spot)
        distance_ratio = distance_points / spot if spot else 0.0
        moneyness_spot = (strike / spot) - 1.0 if spot else None
        moneyness_forward = (strike / forward_price) - 1.0 if forward_price else None
        log_moneyness = math.log(strike / forward_price) if forward_price and strike > 0 else None
        latest_oi_row = latest_oi_map.get(option_id) or {}
        open_interest = _choose_open_interest(row, latest_oi_row)
        signal_payload = signal_payload_by_option.get(option_id) or {}

        prepared.append(
            PreparedOption(
                option_id=option_id,
                bloomberg_ticker=str(row.get("bloomberg_ticker") or ""),
                underlying_security=str(row.get("underlying_security") or market_context.underlying_security),
                underlying_trade_symbol=row.get("underlying_trade_symbol"),
                put_call=str(row.get("put_call") or row.get("OPT_PUT_CALL") or ""),
                strike=float(strike),
                expiry_date=str(row.get("expiry_date") or row.get("OPT_EXPIRE_DT") or ""),
                days_to_expiry_business=days_business,
                days_to_expiry_calendar=int(row.get("days_to_expiry_calendar") or days_business),
                time_to_expiry_years=time_years,
                snapshot_timestamp=str(row.get("captured_at") or ""),
                snapshot_id=row.get("snapshot_id"),
                batch_id=row.get("batch_id"),
                batch_key=row.get("batch_key"),
                universe_tier=row.get("universe_tier"),
                px_last=_safe_float(row.get("PX_LAST")),
                bid=_safe_float(row.get("BID")),
                ask=_safe_float(row.get("ASK")),
                mid=_safe_float(row.get("MID")),
                open_int=open_interest,
                px_volume=_pick_first(row.get("PX_VOLUME"), row.get("VOLUME")),
                iv_bid=_safe_float(row.get("IVOL_BID")),
                iv_ask=_safe_float(row.get("IVOL_ASK")),
                iv_mid=_safe_float(row.get("IVOL_MID")),
                iv_last=_safe_float(row.get("IVOL_LAST")),
                selected_iv=selected_iv,
                observed_delta=observed_delta,
                observed_gamma=observed_gamma,
                observed_vega=observed_vega,
                observed_theta=observed_theta,
                observed_vanna=observed_vanna,
                observed_charm=observed_charm,
                spot_price=float(spot),
                forward_price=float(forward_price),
                interpolated_rate=float(interpolated_rate),
                carry_dividend_proxy=float(carry),
                moneyness_spot=moneyness_spot,
                moneyness_forward=moneyness_forward,
                log_moneyness=log_moneyness,
                distance_to_atm_points=float(distance_points),
                distance_to_atm_ratio=float(distance_ratio),
                moneyness_bucket=_moneyness_bucket(distance_ratio),
                expiry_bucket=_expiry_bucket(days_business),
                liquidity_score=float(_pick_first(row.get("liquidity_score"), row.get("liquidity_score_initial"), 0.0)),
                liquidity_weight=_liquidity_weight(row),
                reliability_weight=_reliability_weight(row, selected_iv, observed_delta, observed_gamma),
                option_multiplier=float(_pick_first(row.get("contract_multiplier"), run_config.option_multiplier, 1.0)),
                signal=float(signal_payload.get("signal", 1.0)),
                signal_confidence=float(signal_payload.get("confidence", 0.0)),
                signal_mode=str(signal_payload.get("mode", "neutral")),
                signal_reason=str(signal_payload.get("reason", "")),
                diagnostics={
                    "oi_change_abs": latest_oi_row.get("oi_change_abs"),
                    "oi_change_pct": latest_oi_row.get("oi_change_pct"),
                    "history_trade_date": latest_oi_row.get("trade_date"),
                },
            )
        )

    diagnostics = {
        "prepared_count": len(prepared),
        "model_greek_fallback_count": model_fallback_count,
        "spot_price": market_context.spot_price,
        "forward_price": market_context.forward_price,
        "rate_curve_points": market_context.rate_curve_points,
        "sources": market_context.sources,
    }
    return prepared, diagnostics
