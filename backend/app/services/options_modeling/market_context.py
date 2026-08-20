from __future__ import annotations

import json
import math
import os
from statistics import median
from typing import Any

from ...config import Config
from ...utils.logger import get_logger
from ..excel_live_workbook_service import ExcelLiveWorkbookService
from .math_utils import linear_interpolate, normalize_rate
from .types import MarketContext

logger = get_logger("aquiles.options_modeling.market_context")
_excel_live_workbook = ExcelLiveWorkbookService()


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _split_security_candidates(raw_value: str | None) -> list[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    for separator in ("|", ";"):
        text = text.replace(separator, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _normalize_security_key(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _macro_state_path() -> str:
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "../../../uploads/macro/state.json"))


def _macro_snapshots_path() -> str:
    return os.path.normpath(os.path.join(os.path.dirname(__file__), "../../../uploads/macro/snapshots.jsonl"))


def _load_latest_macro_market_snapshot() -> dict[str, Any]:
    state_path = _macro_state_path()
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            snapshot = payload.get("snapshot", {}) or {}
            market = snapshot.get("market", {}) or {}
            if market.get("contracts") or market.get("reference_assets"):
                return market
        except Exception:
            logger.exception("Failed to load macro state snapshot for options modeling")

    snapshots_path = _macro_snapshots_path()
    if not os.path.exists(snapshots_path):
        return {}
    try:
        with open(snapshots_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
        for line in reversed(lines):
            payload = json.loads(line)
            snapshot = payload.get("snapshot", {}) or {}
            market = snapshot.get("market", {}) or {}
            if market.get("contracts") or market.get("reference_assets"):
                return market
    except Exception:
        logger.exception("Failed to load macro snapshots history for options modeling")
    return {}


def _load_macro_reference_assets() -> dict[str, Any]:
    market = _load_latest_macro_market_snapshot()
    return market.get("reference_assets", {}) or {}


def _load_macro_contracts() -> dict[str, Any]:
    market = _load_latest_macro_market_snapshot()
    return market.get("contracts", {}) or {}


def _extract_snapshot_spot(snapshot_rows: list[dict[str, Any]]) -> float | None:
    values = [_safe_float(row.get("OPT_UNDL_PX")) for row in snapshot_rows]
    valid_values = [value for value in values if value is not None and value > 0]
    if not valid_values:
        return None
    return float(median(valid_values))


def _load_excel_reference_assets() -> dict[str, Any]:
    if not (
        Config.OPTIONS_FAIR_VALUE_EXCEL_BASKET_ENABLE
        or getattr(Config, "MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE", False)
    ):
        return {}
    payload = _excel_live_workbook.read_fair_value_basket()
    if not isinstance(payload, dict) or not payload.get("ok"):
        return {}
    rows = payload.get("rows") or []
    return {
        _normalize_security_key((row or {}).get("security")): dict(row or {})
        for row in rows
        if str((row or {}).get("security") or "").strip()
    }


def _select_first_price(
    candidates: list[str],
    excel_assets: dict[str, Any],
    persisted_assets: dict[str, Any],
    bloomberg_service: Any | None,
) -> tuple[float | None, str | None, dict[str, Any]]:
    diagnostics: dict[str, Any] = {"attempted": list(candidates), "source": None}
    for security in candidates:
        workbook_row = excel_assets.get(_normalize_security_key(security)) or {}
        fields = workbook_row.get("fields") or {}
        price = _safe_float(fields.get("PX_LAST"))
        if price is None:
            price = _safe_float(workbook_row.get("price"))
        if price is not None:
            diagnostics["source"] = "excel_live_workbook"
            diagnostics["security"] = security
            diagnostics["timestamp"] = workbook_row.get("timestamp")
            diagnostics["worksheet_name"] = workbook_row.get("worksheet_name")
            diagnostics["row_number"] = workbook_row.get("row_number")
            return price, security, diagnostics

    for security in candidates:
        persisted = persisted_assets.get(security) or {}
        fields = persisted.get("fields") or {}
        price = _safe_float(persisted.get("price"))
        if price is None:
            price = _safe_float(fields.get("PX_LAST"))
        if price is not None:
            diagnostics["source"] = "macro_state"
            diagnostics["security"] = security
            return price, security, diagnostics

    if bloomberg_service and candidates and Config.BLOOMBERG_REALTIME_REFERENCE_ENABLE:
        try:
            response = bloomberg_service.fetch_reference_securities(candidates)
            for row in response.get("rows", []):
                security = str(row.get("security") or "")
                fields = row.get("fields") or {}
                price = _safe_float(fields.get("PX_LAST"))
                if price is not None:
                    diagnostics["source"] = "live_bloomberg"
                    diagnostics["security"] = security
                    diagnostics["status"] = response.get("status", {})
                    return price, security, diagnostics
            diagnostics["status"] = response.get("status", {})
        except Exception:
            logger.exception("Failed to fetch reference securities during options modeling")
            diagnostics["source"] = "error"

    diagnostics["live_disabled"] = not Config.BLOOMBERG_REALTIME_REFERENCE_ENABLE
    diagnostics["excel_disabled"] = not Config.BLOOMBERG_EXCEL_FALLBACK_ENABLE
    return None, None, diagnostics


def _extract_macro_contract_price(contract: dict[str, Any]) -> float | None:
    if not isinstance(contract, dict):
        return None

    book = contract.get("book") or {}
    book_summary = book.get("summary") or {}
    best_bid = _safe_float(book_summary.get("best_bid_price"))
    best_ask = _safe_float(book_summary.get("best_ask_price"))
    if best_bid is not None and best_ask is not None and best_bid > 0 and best_ask > 0 and best_ask >= best_bid:
        return (best_bid + best_ask) / 2.0
    if best_ask is not None and best_ask > 0:
        return best_ask
    if best_bid is not None and best_bid > 0:
        return best_bid

    ohlcv = contract.get("ohlcv") or {}
    last_bar = ohlcv.get("last") or {}
    for key in ("close", "open", "high", "low"):
        price = _safe_float(last_bar.get(key))
        if price is not None and price > 0:
            return price

    latest_window = ohlcv.get("latest_window") or {}
    for key in ("close", "open", "high", "low"):
        price = _safe_float(latest_window.get(key))
        if price is not None and price > 0:
            return price

    return None


def _select_macro_contract_price(
    candidates: list[str],
    persisted_contracts: dict[str, Any],
) -> tuple[float | None, str | None, dict[str, Any]]:
    diagnostics: dict[str, Any] = {"attempted": list(candidates), "source": None}
    for security in candidates:
        contract = persisted_contracts.get(security) or {}
        price = _extract_macro_contract_price(contract)
        if price is not None:
            diagnostics["source"] = "macro_contract"
            diagnostics["security"] = security
            return float(price), security, diagnostics
    return None, None, diagnostics


def build_market_context(
    underlying_security: str,
    snapshot_rows: list[dict[str, Any]],
    snapshot_batch: dict[str, Any],
    bloomberg_service: Any | None = None,
) -> MarketContext:
    excel_assets = _load_excel_reference_assets()
    persisted_assets = _load_macro_reference_assets()
    persisted_contracts = _load_macro_contracts()
    observed_snapshot_spot = _extract_snapshot_spot(snapshot_rows)

    spot_candidates = _split_security_candidates(Config.OPTIONS_MODEL_SPOT_SECURITY_MAP.get(underlying_security))
    forward_candidates = _split_security_candidates(Config.OPTIONS_MODEL_FORWARD_SECURITY_MAP.get(underlying_security))
    dividend_candidates = _split_security_candidates(Config.OPTIONS_MODEL_DIVIDEND_SECURITY_MAP.get(underlying_security))

    spot_price, spot_security, spot_diag = _select_first_price(
        spot_candidates,
        excel_assets,
        persisted_assets,
        bloomberg_service,
    )
    if spot_price is None:
        spot_price = observed_snapshot_spot
        spot_diag = {
            "attempted": list(spot_candidates),
            "source": "option_snapshot",
            "security": None,
        }

    if spot_price is None or spot_price <= 0:
        raise ValueError(f"Unable to determine spot price for {underlying_security}")

    forward_price, forward_security, forward_diag = _select_first_price(
        forward_candidates,
        excel_assets,
        persisted_assets,
        bloomberg_service,
    )
    if forward_price is None:
        trade_symbol = str(Config.OPTIONS_UNDERLYING_TRADE_MAP.get(underlying_security) or "").strip()
        if trade_symbol:
            forward_price, forward_security, forward_diag = _select_macro_contract_price([trade_symbol], persisted_contracts)
    dividend_level, dividend_security, dividend_diag = _select_first_price(
        dividend_candidates,
        excel_assets,
        persisted_assets,
        bloomberg_service,
    )
    future_basis_points = None
    future_basis_pct = None
    if forward_price is not None and spot_price and spot_price > 0:
        future_basis_points = float(forward_price) - float(spot_price)
        future_basis_pct = future_basis_points / float(spot_price)

    return MarketContext(
        underlying_security=underlying_security,
        snapshot_batch_id=snapshot_batch.get("batch_id"),
        snapshot_batch_key=snapshot_batch.get("batch_key"),
        spot_price=float(spot_price),
        spot_security=spot_security,
        forward_price=float(forward_price) if forward_price is not None else None,
        forward_security=forward_security,
        future_basis_points=future_basis_points,
        future_basis_pct=future_basis_pct,
        dividend_proxy_level=float(dividend_level) if dividend_level is not None else None,
        dividend_security=dividend_security,
        rate_curve_points=dict(Config.OPTIONS_MODEL_RATE_CURVE_DAY_POINTS),
        reference_trade_date=str(snapshot_batch.get("session_date") or "")[:10] or None,
        sources={
            "spot": spot_diag,
            "forward": forward_diag,
            "dividend": dividend_diag,
            "spot_from_snapshot": observed_snapshot_spot,
            "rate_curve_source": "config_curve_points",
        },
    )


def interpolate_rate_for_days(days_to_expiry_business: int, context: MarketContext) -> float:
    curve_points = {int(day): normalize_rate(rate) for day, rate in (context.rate_curve_points or {}).items()}
    if not curve_points:
        return normalize_rate(Config.OPTIONS_MODEL_FALLBACK_RATE)
    points = sorted(curve_points.items())
    x = max(int(days_to_expiry_business), 0)
    if x <= points[0][0]:
        return points[0][1]
    if x >= points[-1][0]:
        return points[-1][1]
    for index in range(len(points) - 1):
        x0, y0 = points[index]
        x1, y1 = points[index + 1]
        if x0 <= x <= x1:
            return linear_interpolate(float(x), [(float(x0), float(y0)), (float(x1), float(y1))])
    return normalize_rate(Config.OPTIONS_MODEL_FALLBACK_RATE)


def infer_carry_from_forward(spot_price: float, forward_price: float | None, rate: float, time_years: float) -> float:
    if not forward_price or forward_price <= 0 or spot_price <= 0 or time_years <= 0:
        return normalize_rate(rate)
    try:
        return normalize_rate(rate) - (math.log(forward_price / spot_price) / time_years)
    except Exception:
        return normalize_rate(rate)
