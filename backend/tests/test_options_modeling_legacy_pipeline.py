from __future__ import annotations

from typing import Any

import pytest

from app.services.options_modeling import OptionsModelingService
from app.services.options_modeling import market_context as market_context_module


class _OptionsStore:
    def load_latest_oi_map(
        self, option_ids: list[str], trade_date: str | None = None
    ) -> dict[str, dict[str, Any]]:
        return {
            option_id: {
                "trade_date": trade_date,
                "opt_open_interest": 1200,
                "oi_change_abs": 100 if index % 2 == 0 else -80,
                "oi_change_pct": 0.1 if index % 2 == 0 else -0.08,
            }
            for index, option_id in enumerate(option_ids)
        }

    def list_oi_history(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def load_b3_oi_rows(self, _trade_date: str) -> list[dict[str, Any]]:
        return []

    def write_model_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"run_id": payload["run_id"]}


def _option_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for expiry_days in (5, 18, 45, 90):
        for strike in (92.0, 98.0, 100.0, 102.0, 108.0):
            for put_call in ("CALL", "PUT"):
                option_id = f"IBOV-{put_call[0]}-{int(strike)}-{expiry_days}"
                intrinsic_bias = (100.0 - strike) / 100.0
                delta = (
                    max(0.08, min(0.92, 0.5 + intrinsic_bias * 4))
                    if put_call == "CALL"
                    else min(-0.08, max(-0.92, -0.5 + intrinsic_bias * 4))
                )
                rows.append(
                    {
                        "option_id": option_id,
                        "bloomberg_ticker": f"{option_id} BZ Equity",
                        "underlying_security": "IBOVE Index",
                        "underlying_trade_symbol": "WINQ26",
                        "put_call": put_call,
                        "strike": strike,
                        "expiry_date": "2026-12-18",
                        "days_to_expiry_business": expiry_days,
                        "days_to_expiry_calendar": expiry_days + 3,
                        "captured_at": "2026-08-19T13:00:00Z",
                        "snapshot_id": f"snapshot-{option_id}",
                        "batch_id": "batch-1",
                        "batch_key": "2026-08-19-1300",
                        "universe_tier": "structural",
                        "OPT_UNDL_PX": 100.0,
                        "PX_LAST": 2.5,
                        "BID": 2.4,
                        "ASK": 2.6,
                        "MID": 2.5,
                        "OPEN_INT": 1000 + int(strike) * 10,
                        "PX_VOLUME": 500 + expiry_days,
                        "IVOL_BID": 0.20 + abs(strike - 100) / 1000,
                        "IVOL_ASK": 0.22 + abs(strike - 100) / 1000,
                        "IVOL_MID": 0.21 + abs(strike - 100) / 1000,
                        "EFF_IV": 0.21 + abs(strike - 100) / 1000,
                        "EFF_DELTA": delta,
                        "EFF_GAMMA_PT": 0.012 * (1 - min(abs(strike - 100) / 20, 0.8)),
                        "EFF_VEGA": 0.18 + expiry_days / 1000,
                        "EFF_THETA": -0.03,
                        "EFF_VANNA": intrinsic_bias * 0.05,
                        "EFF_CHARM": -delta * 0.01,
                        "distance_to_atm": abs(strike - 100) / 100,
                        "spread_pct": 0.04,
                        "liquidity_score": 82,
                        "contract_multiplier": 1,
                        "stale_flag": False,
                    }
                )
    return rows


def test_options_modeling_runs_full_chain_on_deterministic_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(market_context_module, "_load_excel_reference_assets", lambda: {})
    monkeypatch.setattr(market_context_module, "_load_macro_reference_assets", lambda: {})
    monkeypatch.setattr(market_context_module, "_load_macro_contracts", lambda: {})
    store = _OptionsStore()
    service = OptionsModelingService(store=store, bloomberg=object())
    service.daily_insights.get_or_create = lambda **kwargs: {
        "trade_date": kwargs["trade_date"],
        "summary": "fixture",
    }
    source = {
        "batch": {
            "batch_id": "batch-1",
            "batch_key": "2026-08-19-1300",
            "captured_at": "2026-08-19T13:00:00Z",
            "session_date": "2026-08-19",
            "underlying_security": "IBOVE Index",
            "universe_tier": "structural",
        },
        "rows": _option_rows(),
    }

    payload = service.run_from_snapshot_payload(source, persist=True)
    assert payload["underlying_security"] == "IBOVE Index"
    assert payload["diagnostics"]["prepared_count"] == len(source["rows"])
    assert payload["summary"]["spot_price"] == 100
    assert payload["aggregates"]["totals"]["contracts"] == len(source["rows"])
    assert payload["strike_profiles"]
    assert payload["grid"]["curve"]
    assert payload["pressure"]["zero_pressure"]
    assert payload["dealer_inference"]["comparison"]
    assert payload["range_projection"]
    assert payload["daily_insights"]["summary"] == "fixture"
    assert payload["persisted"]["run_id"] == payload["run_id"]


def test_options_modeling_rejects_invalid_or_empty_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(market_context_module, "_load_excel_reference_assets", lambda: {})
    monkeypatch.setattr(market_context_module, "_load_macro_reference_assets", lambda: {})
    monkeypatch.setattr(market_context_module, "_load_macro_contracts", lambda: {})
    service = OptionsModelingService(store=_OptionsStore(), bloomberg=object())
    with pytest.raises(ValueError, match="underlying_security"):
        service.run_from_snapshot_payload({"batch": {}, "rows": []}, persist=False)

    invalid = {
        "batch": {"underlying_security": "IBOVE Index", "session_date": "2026-08-19"},
        "rows": [
            {
                "option_id": "invalid",
                "underlying_security": "IBOVE Index",
                "OPT_UNDL_PX": 100,
                "strike": 0,
            }
        ],
    }
    with pytest.raises(ValueError, match="No eligible options"):
        service.run_from_snapshot_payload(invalid, persist=False)
