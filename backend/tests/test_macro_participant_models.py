from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.services.macro_live_service import MacroStateStore
from app.services.macro_participant_heatmap_service import MacroParticipantHeatmapService


def _samples(
    service: MacroParticipantHeatmapService,
    *,
    ticker: str,
    base_price: float,
    direction: float,
) -> list[dict]:
    start = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)
    rows = []
    for index in range(36):
        captured_at = start + timedelta(minutes=index)
        price = base_price + (direction * index * 2.5) + ((index % 4) - 1.5)
        participant_rows = [
            service._normalize_participant_row(
                {
                    "broker_id": 1,
                    "broker_name": "Morgan Stanley",
                    "quantity_float": direction * (2_000 + index * 180),
                    "average_price": price - direction * 3,
                    "percentage_float": 25 + index / 5,
                    "relative_percentage_float": 30 + index / 4,
                }
            ),
            service._normalize_participant_row(
                {
                    "broker_id": 2,
                    "broker_name": "XP Investimentos",
                    "quantity_float": -direction * (1_500 + index * 130),
                    "average_price": price + direction * 4,
                    "percentage_float": 20 + index / 6,
                    "relative_percentage_float": 24 + index / 5,
                }
            ),
            service._normalize_participant_row(
                {
                    "broker_id": 3,
                    "broker_name": "Corretora Local",
                    "quantity_float": direction * (400 + index * 35),
                    "average_price": price - direction,
                    "percentage_float": 8,
                    "relative_percentage_float": 10,
                }
            ),
        ]
        rows.append(
            {
                "captured_at": captured_at.isoformat(),
                "ticker": ticker,
                "label": ticker[:3],
                "price_source": "book_mid",
                "last_price": price,
                "best_bid": price - 0.5,
                "best_ask": price + 0.5,
                "spread": 1.0,
                "imbalance": 0.2 * direction,
                "last_candle": {
                    "time": captured_at.isoformat(),
                    "open": price - direction,
                    "high": price + 4,
                    "low": price - 4,
                    "close": price,
                    "volume": 10_000 + index * 250,
                },
                "participants": participant_rows,
                "participants_ok": True,
                "book_ok": True,
                "ohlcv_ok": True,
            }
        )
    return rows


def test_participant_models_cover_cross_asset_regimes_and_liquidity(tmp_path: Path) -> None:
    service = MacroParticipantHeatmapService(store=MacroStateStore(root_dir=str(tmp_path)))
    specs = [
        {"key": "win", "label": "WIN", "ticker": "WINQ26", "visible": True, "role": "win"},
        {"key": "wdo", "label": "WDO", "ticker": "WDOQ26", "visible": True, "role": "wdo"},
        {"key": "di", "label": "DI", "ticker": "DI1F27", "visible": True, "role": "di_anchor"},
        {"key": "di_long", "label": "DI LONG", "ticker": "DI1F31", "visible": False, "role": "di_curve"},
    ]
    assets_state = {
        "WINQ26": {
            **specs[0],
            "session_date": "2026-08-18",
            "samples": _samples(service, ticker="WINQ26", base_price=135_000, direction=1),
        },
        "WDOQ26": {
            **specs[1],
            "session_date": "2026-08-18",
            "samples": _samples(service, ticker="WDOQ26", base_price=5_450, direction=-1),
        },
        "DI1F27": {
            **specs[2],
            "session_date": "2026-08-18",
            "samples": _samples(service, ticker="DI1F27", base_price=13.5, direction=0.01),
        },
        "DI1F31": {
            **specs[3],
            "session_date": "2026-08-18",
            "samples": _samples(service, ticker="DI1F31", base_price=14.2, direction=-0.01),
        },
    }
    state = {
        "generated_at": "2026-08-18T13:35:00+00:00",
        "assets": assets_state,
    }

    panels = [service._build_asset_panel(assets_state[spec["ticker"]]) for spec in specs[:3]]
    cross_asset = service._build_cross_asset_flow_package(state, specs)
    divergence = service._build_structural_divergence_model(panels, cross_asset)
    continuation = service._build_continuation_reversal_model(panels, cross_asset, divergence)
    news = {
        "available": True,
        "score": 18,
        "regime": "risk_on",
        "confidence_score": 70,
        "drivers": [{"label": "Fiscal", "score": 18}],
    }
    trade = service._build_win_trade_thermometer(
        panels,
        cross_asset,
        divergence,
        continuation,
        news,
    )
    liquidity = service._build_liquidity_intelligence_model(
        panels,
        cross_asset,
        divergence,
        continuation,
        news,
        trade,
    )
    pools = service._build_liquidity_pool_model(
        panels,
        cross_asset,
        divergence,
        continuation,
        news,
        trade,
        liquidity,
    )
    options_alignment = service._build_options_flow_alignment_model(
        panels,
        cross_asset,
        trade,
        liquidity,
        {
            "gamma_context": {
                "available": True,
                "underlying_price": panels[0]["latest_price"],
                "gamma_flip": panels[0]["latest_price"] - 100,
                "max_call_gamma_strike": panels[0]["latest_price"] + 500,
                "max_put_gamma_strike": panels[0]["latest_price"] - 500,
                "net_gamma": 2_000_000,
            },
            "fair_value_history": {"latest_sample": {"captured_at": "2026-08-18T13:35:00+00:00"}},
        },
    )

    assert panels[0]["sample_count"] == 36
    assert panels[0]["side_confidence"] == "confirmed"
    assert panels[0]["pressure_model"]["primary"]
    assert panels[0]["cohort_value_map"]["cohorts"]
    assert panels[0]["flow_regime_classifier"]["cohorts"]
    assert panels[0]["concentration_model"]["primary"]
    assert cross_asset["windows"]
    assert divergence["windows"]
    assert continuation["windows"]
    assert trade["windows"]
    assert liquidity["assets"]["win"]
    assert pools["assets"]["win"]
    assert options_alignment["available"] is True
