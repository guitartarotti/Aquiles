from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.services.macro_driver_service import (
    DRIVER_STATE_VERSION,
    MacroDriverService,
)


class _Ingestion:
    @staticmethod
    def _build_contract_signal(ticker: str, _contract: dict) -> dict:
        if ticker.startswith("BVMF:DI1"):
            return {"direction_5m": "up", "net_change_pct_5m": 0.08, "top_5_share_pct": 32}
        if "DOL" in ticker or "WDO" in ticker:
            return {"direction_5m": "up", "net_change_pct_5m": 0.25, "top_5_share_pct": 38}
        return {"direction_5m": "down", "net_change_pct_5m": -0.4, "top_5_share_pct": 45}


def _service(tmp_path) -> MacroDriverService:
    service = MacroDriverService.__new__(MacroDriverService)
    service.store = SimpleNamespace(root_dir=str(tmp_path))
    service.ingestion = _Ingestion()
    service._llm_client = None
    service.drivers_path = str(tmp_path / "drivers.json")
    return service


def _event(event_id: str, event_time: str, headline: str) -> dict:
    return {
        "event_id": event_id,
        "event_time": event_time,
        "headline": headline,
        "posted_by": "fixture",
        "macro_scope": "macro",
        "market_relevance": True,
        "scenario_classification": "regime_shift",
        "scenario_reason": "cross-asset shock",
        "signal_strength": "high",
        "impact_score": 82,
        "macro_transmission_score": 9.0,
        "linked_contracts": ["BVMF:WINQ26", "BVMF:WDOQ26", "BVMF:DI1F29"],
        "linked_securities": ["CL1 Comdty"],
        "linked_buckets": ["equity", "fx", "curve_long"],
        "themes": ["ormuz_blockade"],
        "high_conviction_macro_terms": ["oil", "ormuz"],
        "technical_operation": False,
        "directional_bias": "sell",
    }


def _contract(candles: list[dict]) -> dict:
    return {
        "ohlcv": {"candles_1m": candles},
        "participants": {
            "all_rows": [
                {"broker_name": "Banco Alpha", "percentage_float": 18},
                {"broker_name": "Banco Beta", "percentage": 12},
            ]
        },
    }


def test_macro_driver_filters_groups_and_identifies_directional_events(tmp_path) -> None:
    service = _service(tmp_path)
    first = _event("evt-1", "2026-08-19T13:00:00-03:00", "Ormuz blockade lifts oil")
    second = _event("evt-2", "2026-08-19T13:20:00-03:00", "Oil shock extends after Ormuz blockade")
    ignored = first | {
        "event_id": "ignored",
        "macro_scope": "idiosyncratic",
        "headline": "Company-specific update",
    }

    assert service._event_is_directional_macro_driver(first)
    assert not service._event_is_directional_macro_driver(
        {"headline": "routine filing", "linked_contracts": []}
    )
    candidates = service._candidate_events([second, ignored, first])
    assert [row["event_id"] for row in candidates] == ["evt-1", "evt-2"]
    groups = service._group_events(candidates)
    assert len(groups) == 1
    assert len(groups[0]["events"]) == 2
    assert groups[0]["focus_buckets"] == {"equity", "fx", "curve_long"}

    signature = service._current_source_signature(
        snapshot={"generated_at": "2026-08-19T13:21:00-03:00"},
        candidate_events=candidates,
    )
    assert signature["candidate_event_count"] == 2
    assert len(signature["event_signature"]) == 40
    assert service._canonical_theme(["other", "ormuz_blockade"]) == "ormuz_blockade"
    assert service._group_window_seconds(["ormuz_blockade"]) == 43_200


def test_macro_driver_builds_cross_asset_payload_with_market_evolution(
    tmp_path, monkeypatch
) -> None:
    service = _service(tmp_path)
    events = [
        _event("evt-1", "2026-08-19T13:00:00-03:00", "Ormuz blockade lifts oil"),
        _event("evt-2", "2026-08-19T13:02:00-03:00", "Oil shock pressures risk assets"),
    ]
    group = service._group_events(events)[0]
    candles = [
        {"time": "2026-08-19T12:59:00-03:00", "close": 138_000, "volume": 100},
        {"time": "2026-08-19T13:00:00-03:00", "close": 137_900, "volume": 120},
        {"time": "2026-08-19T13:05:00-03:00", "close": 137_200, "volume": 420},
    ]
    contracts = {
        "BVMF:WINQ26": _contract(candles),
        "BVMF:WDOQ26": _contract(candles),
        "BVMF:DI1F29": _contract(candles),
    }
    snapshot = {
        "generated_at": "2026-08-19T13:06:00-03:00",
        "market": {
            "contracts": contracts,
            "securities": {"CL1 Comdty": {"change_percent": 2.5}},
        },
    }
    history = [
        {
            "generated_at": "2026-08-19T12:59:00-03:00",
            "snapshot": {"market": {"contracts": contracts}},
        }
    ]
    monkeypatch.setattr(
        service,
        "_generate_driver_analysis",
        lambda **_kwargs: {
            "title": "Oil shock",
            "macro_explanation": "Energy shock transmits to FX, equity and rates.",
            "driver_summary": "Risk assets reprice after the headline.",
            "probable_playbook": "Protect equity and monitor FX.",
            "importance_reason": "Broad cross-asset confirmation.",
            "recommended_action": "sell",
            "directional_consensus_bias": "sell",
            "directional_consensus_confidence": 88,
            "market_regime": "risk-off oil shock",
            "agent_context_packet": {
                "semantic": {"aggregate_bias": "sell", "aggregate_confidence": 80},
                "narrative_memory": {"contextual_verdict": "confirmed"},
            },
        },
    )

    driver = service._build_driver(group, snapshot, history)
    assert driver is not None
    assert driver["title"] == "Ormuz Blockade / Oil Shock"
    assert driver["headline_count"] == 2
    assert driver["importance_score"] >= 50
    assert driver["expected_impact_band"] in {"tradable_catalyst", "regime_shift"}
    assert len(driver["asset_asymmetry"]) == 4
    assert driver["participant_reactions"][0]["broker_name"] == "Banco Alpha"
    assert driver["price_evolution"]["series"][0]["impact_5m"]["price_delta"] == -700
    assert driver["market_elasticity"]["rows"]
    assert driver["driver_graph"]["nodes"]
    assert driver["agent_audit_report"]["directional_consensus"]["bias"] == "sell"

    news = service._build_news_feed(events, [driver])
    assert news[0]["driver_id"] == driver["driver_id"]
    service._attach_related_drivers([driver])
    assert driver["related_driver_ids"] == []

    reused = service._build_driver(
        group,
        snapshot,
        history,
        previous_driver={driver["driver_id"]: driver},
    )
    assert reused and reused["driver_id"] == driver["driver_id"]


def test_macro_driver_fallbacks_persistence_and_bias_contracts(tmp_path) -> None:
    service = _service(tmp_path)
    events = [_event("evt-1", "2026-08-19T13:00:00-03:00", "Iran talks fail")]
    assets = [
        {"asset": "WIN", "bias": "sell", "asymmetry_score": 30},
        {"asset": "WDO", "bias": "buy", "asymmetry_score": 12},
    ]
    participants = [{"market_bias": "sell", "activity_score": 20}]

    consensus = service._directional_consensus(events, assets, participants)
    assert consensus["bias"] == "sell"
    assert consensus["confirmed"]
    assert service._expected_impact_band(80) == "regime_shift"
    assert service._importance_label(55) == "medium"
    assert service._direction_to_bias("up") == "buy"
    assert service._direction_to_bias_for_asset("BVMF:DI1F29", "up") == "sell"
    assert service._market_direction_sign_for_contract("BVMF:DI1F29", "down") == 1
    assert service._normalize_bias({"recommended_action": "SELL"}) == "sell"
    assert service._regime_implied_action("dovish relief") == "buy"
    assert service._regime_implied_action("hawkish stress") == "sell"
    assert service._fallback_driver_title(events, "WIN") == "WIN impact driver"
    assert "Watch" not in service._fallback_playbook(assets)
    assert "Simulate" in service._build_simulation_seed("WIN", events, assets)
    assert service._parse_iso_datetime("bad") is None
    assert service._to_float("bad") is None

    graph = service._build_driver_graph("driver-1", "Driver", events, assets, participants)
    assert len(graph["nodes"]) == 1 + len(events) + len(assets) + len(participants)
    assert service._build_driver({}, {}, []) is None

    state = {
        "driver_engine_version": DRIVER_STATE_VERSION,
        "generated_at": "2026-08-19T13:00:00-03:00",
        "source_signature": {"event_signature": "fixture"},
        "news_feed": [],
        "drivers": [{"driver_id": "driver-1", "related_driver_ids": []}],
    }
    service._save_state(state)
    assert json.loads((tmp_path / "drivers.json").read_text(encoding="utf-8"))["drivers"]
    assert service.list_drivers(refresh=False)["driver_count"] == 1
    assert service.focus_driver("driver-1")["driver"]["driver_id"] == "driver-1"
    with pytest.raises(ValueError, match="required"):
        service.focus_driver("")
    with pytest.raises(ValueError, match="not found"):
        service.focus_driver("missing")
