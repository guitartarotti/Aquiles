from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.macro_cross_asset_service import MacroCrossAssetService


class _Ingestion:
    def _build_contract_signal(
        self, ticker: str, contract: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "ticker": ticker,
            "top_5_share_percentage": 72,
            "volume_ratio_5m": 2.4,
            "book_imbalance": (contract.get("book") or {}).get("imbalance", 0.35),
        }


def _market(multiplier: float = 1.0) -> dict[str, Any]:
    def contract(bucket: str, price: float) -> dict[str, Any]:
        return {
            "bucket": bucket,
            "ohlcv": {"latest_window": {"close": price * multiplier}},
            "book": {"imbalance": 0.35},
        }

    return {
        "contracts": {
            "WINQ26": contract("index", 138000),
            "WDOQ26": contract("dollar", 5.45),
            "DI1F29": contract("curve_long", 14.8),
        },
        "reference_assets": {
            "BRAZIL CDS USD SR 5Y D14 Curncy": {
                "label": "Brazil CDS",
                "bucket": "credit",
                "price": 145 * multiplier,
            },
            "SPX Index": {"label": "S&P 500", "bucket": "equity", "price": 6500 * multiplier},
            "CL1 Comdty": {"label": "Oil", "bucket": "commodity", "price": 82 * multiplier},
            "DXY Curncy": {"label": "Dollar Index", "bucket": "fx", "price": 99 * multiplier},
        },
        "securities": {
            "IBOV Index": {"price": 137000 * multiplier},
        },
    }


def test_macro_cross_asset_scores_driver_and_builds_analysis_views() -> None:
    service = MacroCrossAssetService.__new__(MacroCrossAssetService)
    service.ingestion = _Ingestion()
    market = _market(1.012)
    specs = service._build_asset_specs(market)
    assert {spec.bucket for spec in specs.values()} >= {"credit", "equity", "commodity", "fx", "rates"}

    start = datetime(2026, 8, 19, 13, tzinfo=timezone.utc)
    history = [
        {"generated_at": (start + timedelta(minutes=index * 5)).isoformat(), "dt": start + timedelta(minutes=index * 5), "market": _market(1 + index * 0.004)}
        for index in range(4)
    ]
    history_stats = service._build_asset_history_stats(history, specs)
    assert history_stats["WINQ26"]["samples"] == 3

    driver = {
        "driver_id": "driver-1",
        "title": "Oil shock and risk-off repricing",
        "first_event_time": "2026-08-19T13:04:00Z",
        "last_event_time": "2026-08-19T13:06:00Z",
        "headline_count": 3,
        "importance_score": 86,
        "importance_label": "high",
        "recommended_action": "sell",
        "themes": ["geopolitics", "oil_shock", "risk_off"],
        "focus_contracts": ["WINQ26", "WDOQ26", "DI1F29"],
        "focus_securities": ["PETR4"],
        "headline_updates": [
            {"headline": "Iran attack threatens oil supply", "relevance": "breaking", "impact_score": 9},
            {"headline": "Dollar and rates confirm risk-off", "relevance": "important", "impact_score": 8},
        ],
        "participant_reactions": [
            {"broker_name": "Alpha", "market_bias": "sell", "activity_score": 45},
            {"broker_name": "Beta", "market_bias": "sell", "activity_score": 38},
            {"broker_name": "Gamma", "market_bias": "sell", "activity_score": 30},
        ],
        "price_evolution": {
            "series": [
                {
                    "ticker": "WINQ26",
                    "pre_event": {"close": 138000, "time": "2026-08-19T13:00:00Z"},
                    "impact_5m": {"price_delta_pct": -0.8, "volume_delta": 1500},
                    "impact_5m_point": {"close": 136896, "time": "2026-08-19T13:05:00Z"},
                },
                {
                    "ticker": "WDOQ26",
                    "pre_event": {"close": 5.4, "time": "2026-08-19T13:00:00Z"},
                    "impact_5m": {"price_delta_pct": 0.9, "volume_delta": 900},
                    "impact_5m_point": {"close": 5.4486, "time": "2026-08-19T13:05:00Z"},
                },
            ]
        },
    }
    profile = service._build_driver_profile(driver)
    assert abs(sum(profile["bucket_weights"].values()) - 1) < 0.001
    assert {"fx", "equity", "rates"} <= service._focus_buckets_from_driver(driver)

    analyzed = service._analyze_driver(driver, market, history, specs, history_stats)
    assert analyzed is not None
    assert analyzed["asset_reactions"]
    assert analyzed["bucket_reactions"]["equity"]["coverage"] >= 1
    assert analyzed["cross_signals"]["regime"]
    assert analyzed["insights"]
    assert analyzed["confidence"] > 50

    timeline = service._build_timeline([analyzed])
    insights = service._flatten_insights([analyzed])
    entities = service._build_entity_views([analyzed], timeline)
    latest_scores = timeline[-1]["scores"]
    summary = service._build_summary(latest_scores, [analyzed], timeline)
    panorama = service._build_ai_panorama(latest_scores, [analyzed], timeline, entities, insights)
    assert timeline[0]["driver_id"] == "driver-1"
    assert insights[0]["driver_title"] == driver["title"]
    assert entities
    assert summary["overall"]["bias"]
    assert panorama["market_commentary"]
    assert service._build_asset_interaction_graph(analyzed)["nodes"]
    assert service._build_driver_cross_asset_commentary(analyzed)
    thermometer = service._build_headline_thermometer(driver)
    assert thermometer["timeline"]


def test_macro_cross_asset_defensive_helpers_cover_missing_and_extreme_inputs() -> None:
    service = MacroCrossAssetService.__new__(MacroCrossAssetService)
    service.ingestion = _Ingestion()
    assert service._normalize_bucket_weights({})
    assert service._participant_context([])["alignment"] == "light"
    assert service._bias_from_score(10) == "buy"
    assert service._bias_from_score(-10) == "sell"
    assert service._bias_from_score(0) == "watch"
    assert service._probability_from_score(100) <= 95
    assert service._risk_label(80)
    assert service._sentiment_label(-20)
    assert service._strength_label(0) == "missing"
    assert service._bucket_status("equity", 12)["bias"] == "buy"
    assert service._pair_bucket_relation(10, 8) == "confirms"
    assert service._pair_bucket_relation(-10, 8) == "diverges"
    assert service._pair_bucket_relation(1, 1) is None
    assert service._parse_datetime("bad") is None
    assert service._to_float("bad") is None
    assert service._clamp(12, 0, 10) == 10
    assert service._analyze_driver({}, {}, [], {}, {}) is None
