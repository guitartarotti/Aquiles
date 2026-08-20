from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from app.services.macro_live_projection import MacroProjectionService
from app.services.macro_live_service import (
    EVENT_CLASSIFICATION_VERSION,
    MacroIngestionService,
)
from app.services.macro_live_state_store import MacroStateStore
from app.services.macro_live_utils import LOCAL_TZ


def _event(event_id: str, headline: str, minute: int = 0) -> dict[str, object]:
    return {
        "event_id": event_id,
        "source": "bleu_news",
        "event_type": "macro_news",
        "headline": headline,
        "posted_by": "Macro Desk",
        "relevance": "breaking",
        "event_time": f"2026-08-19T13:{minute:02d}:00-03:00",
    }


def _market_snapshot() -> dict[str, object]:
    return {
        "contracts": {
            "WINQ26": {
                "bucket": "equity",
                "ohlcv": {
                    "ok": True,
                    "candle_count": 2,
                    "last": {"close": 138000, "volume": 500, "time": "2026-08-19T13:05:00-03:00"},
                    "latest_window": {
                        "window_start": "2026-08-19T13:00:00-03:00",
                        "window_end": "2026-08-19T13:05:00-03:00",
                        "direction": "down",
                        "net_change": -800,
                        "net_change_pct": -0.58,
                        "volume": 1200,
                    },
                    "windows_5m": [
                        {
                            "window_start": "2026-08-19T13:00:00-03:00",
                            "direction": "down",
                            "net_change_pct": -0.58,
                            "volume": 1200,
                        }
                    ],
                },
                "participants": {
                    "ok": True,
                    "rows": 2,
                    "summary": {"top_5_share_percentage": 72},
                    "all_rows": [
                        {
                            "broker_name": "Banco Alpha",
                            "quantity": 900,
                            "percentage": 48,
                            "relative_percentage": 55,
                            "average_price": 138200,
                        }
                    ],
                },
                "book": {
                    "ok": True,
                    "bid_levels": 2,
                    "ask_levels": 2,
                    "best_bid": {"price": 137990},
                    "best_ask": {"price": 138010},
                    "summary": {"spread": 20, "imbalance": -0.35},
                },
            },
            "WDOQ26": {
                "bucket": "fx",
                "ohlcv": {
                    "ok": True,
                    "latest_window": {
                        "direction": "up",
                        "net_change_pct": 0.75,
                        "volume": 900,
                    },
                },
                "participants": {"summary": {"top_5_share_percentage": 60}, "all_rows": []},
                "book": {"summary": {"imbalance": 0.4}},
            },
        },
        "securities": {
            "CL1 Comdty": {"price": 82.5, "change_percent": 2.4, "updated_at": "2026-08-19T13:05:00Z"},
            "USDBRL Curncy": {"price": 5.48, "change_percent": 0.8, "updated_at": "2026-08-19T13:05:00Z"},
        },
        "groups": {"equity": ["WINQ26"], "fx": ["WDOQ26"]},
        "reference_assets": {
            "CL1 Comdty": {"label": "Oil", "bucket": "commodities", "price": 82.5, "change_percent": 2.4, "ok": True}
        },
        "reference_groups": {"commodities": ["CL1 Comdty"]},
    }


def test_macro_state_store_round_trips_events_collections_and_filters(tmp_path: Path) -> None:
    store = MacroStateStore(root_dir=str(tmp_path))
    assert store.read_state()["event_count"] == 0
    assert store.update_collector_status(running=True, run_count=1)["running"] is True

    first = _event("evt-1", "Fed cuts rates after inflation cools", 0)
    second = _event("evt-2", "Iran attack threatens oil supply", 5)
    state = store.record_news_events([first, second], {"ok": True, "timeout_windows": 1})
    assert state["event_count"] == 2
    assert state["snapshot"]["news"]["new_count"] == 2
    assert store.record_news_events([first])["event_count"] == 2
    assert store.list_recent_events(limit=1)[0]["event_id"] == "evt-1"
    assert len(store.list_recent_events(source="bleu_news")) == 2

    target_day = date(2026, 8, 19)
    assert len(store.list_events_for_local_day(target_day, limit=10)) == 2
    assert store.list_events_for_local_day(target_day, source="other") == []
    start = datetime(2026, 8, 19, 12, 59, tzinfo=LOCAL_TZ)
    end = start + timedelta(minutes=10)
    assert len(store.list_events_in_local_window(start, end)) == 2

    snapshot = {
        "generated_at": "2026-08-19T13:10:00-03:00",
        "news": {"items": [first, second]},
        "market": _market_snapshot(),
        "sources": {"bleu_ws": {"ok": True}},
    }
    saved = store.record_collection({"snapshot": snapshot, "news_events": [second]})
    assert saved["snapshot"]["generated_at"] == snapshot["generated_at"]
    assert store.list_snapshot_history(limit=5)[0]["snapshot"]["generated_at"] == snapshot["generated_at"]
    replaced = store.replace_recent_events([second])
    assert replaced["snapshot"]["news"]["count"] == 1

    with open(store.events_path, "a", encoding="utf-8") as handle:
        handle.write("not-json\n")
        handle.write(json.dumps([]) + "\n")
    with open(store.snapshots_path, "a", encoding="utf-8") as handle:
        handle.write("not-json\n")
        handle.write(json.dumps([]) + "\n")
    assert store.list_events_for_local_day(target_day)
    assert store.list_snapshot_history(limit=10)
    assert store.list_snapshot_history(limit=0) == []

    Path(store.state_path).write_text("not-json", encoding="utf-8")
    assert store.read_state()["event_count"] == 0


def test_macro_ingestion_builds_market_microstructure_and_news_links(tmp_path: Path) -> None:
    service = MacroIngestionService(store=MacroStateStore(root_dir=str(tmp_path)))
    rows = service._normalize_participant_rows(
        [
            {"broker_id": 1, "broker_name": "Alpha", "quantity": 1200, "percentage": "40"},
            {"broker_id": 2, "broker_name": "Beta", "quantity": 800, "percentage": 30},
        ]
    )
    summary = service._build_participant_summary(rows)
    assert summary["participant_count"] == 2
    assert summary["top_share_percentage"] == 40
    assert service._build_participant_summary([])["participant_count"] == 0

    candles = [
        {"time": "2026-08-19T13:00:00-03:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 10},
        {"time": "2026-08-19T13:04:00-03:00", "open": 101, "high": 104, "low": 100, "close": 103, "volume": 20},
        {"time": "bad", "open": 1},
    ]
    windows = service._build_ohlcv_windows(candles)
    assert windows[0]["direction"] == "up"
    assert windows[0]["volume"] == 30
    book = service._build_book_summary(
        [{"price": "100", "amount": 20}, {"price": "99", "amount": 10}],
        [{"price": "101", "amount": 5}, {"price": "102", "amount": 5}],
    )
    assert book["spread"] == 1
    assert book["imbalance"] == 0.5
    assert service._build_book_summary([], [])["spread"] is None

    events = [
        _event("evt-1", "Breaking Iran attack threatens oil supply and drives risk-off dollar rally"),
        _event("evt-2", "Company announces routine dividend", 2),
    ]
    market = _market_snapshot()
    enriched, links, overview = service._build_news_market_links(events, market)
    assert enriched[0]["classification_version"] == EVENT_CLASSIFICATION_VERSION
    assert enriched[0]["impact_score"] >= enriched[1]["impact_score"]
    assert enriched[0]["market_relevance"] is True
    assert links
    assert overview["top_movers_5m"]
    assert overview["security_moves"]

    frozen = service.freeze_news_events(enriched + [_event("evt-3", "Fed rate shock hits markets", 3)], market)
    assert len(frozen) == 3
    assert service._event_has_frozen_classification(frozen[0])
    assert not service._event_has_frozen_classification({})
    assert service._build_bleu_event({"headline": "Fed decision", "timestamp": 1, "postedBy": "Desk"})
    assert service._build_bleu_event({}) is None
    assert service._macro_transmission_score(
        buckets=["fx", "equity"],
        contracts=["WIN", "WDO"],
        securities=["CL1"],
        themes=["rates"],
        high_conviction_macro_terms=["fed"],
        idiosyncratic_terms=[],
        corporate_deal_terms=[],
        generic_equity_terms=[],
        technical_operation=False,
    ) > 10


def test_macro_ingestion_collect_once_merges_sources_and_persists(tmp_path: Path, monkeypatch) -> None:
    store = MacroStateStore(root_dir=str(tmp_path))
    service = MacroIngestionService(store=store)
    event = _event("evt-1", "Iran attack pushes oil and dollar higher")
    market = _market_snapshot()
    monkeypatch.setattr(
        service,
        "collect_bleu_news",
        lambda: {"events": [event], "source_status": {"ok": True, "messages_received": 1}},
    )
    monkeypatch.setattr(
        service,
        "collect_market_snapshot",
        lambda: {"market": market, "source_status": {"contracts": {"ok": True}}},
    )
    result = service.collect_all_once(include_news=True, include_market=True, persist=True)
    assert result["snapshot"]["generated_at"]
    assert result["snapshot"]["news"]["count"] == 1
    assert result["snapshot"]["market"]["news_links"]
    assert store.read_state()["snapshot"]["generated_at"]

    empty = service.collect_all_once(include_news=False, include_market=False, persist=False)
    assert empty["snapshot"]["news"]["count"] == 0
    assert service.get_snapshot(limit_events=1)["snapshot"]["news"]["items"]


def test_macro_projection_generates_ontology_and_recruiter_readable_markdown(tmp_path: Path) -> None:
    store = MacroStateStore(root_dir=str(tmp_path))
    projection = MacroProjectionService(store=store)
    event = _event("evt-1", "Iran attack threatens oil supply") | {
        "impact_score": 9,
        "market_relevance": True,
        "linked_contracts": ["WINQ26", "WDOQ26"],
        "linked_securities": ["CL1 Comdty"],
        "linked_buckets": ["equity", "fx"],
        "themes": ["geopolitics", "oil"],
        "link_reasons": ["oil shock", "risk off"],
    }
    market = _market_snapshot()
    market["overview"] = {
        "top_movers_5m": [{"ticker": "WINQ26", "direction_5m": "down", "net_change_pct_5m": -0.58, "volume_5m": 1200, "book_imbalance": -0.35}],
        "impactful_news": [event],
    }
    market["news_links"] = [
        {"headline": event["headline"], "ticker": "WINQ26", "bucket": "equity", "direction_5m": "down", "net_change_pct_5m": -0.58, "themes": ["oil"], "link_reasons": ["risk off"]}
    ]
    snapshot = {
        "generated_at": "2026-08-19T13:10:00-03:00",
        "market": market,
        "sources": {"bleu_ws": {"ok": True}, "aquant": {"ok": True}},
    }
    ontology = projection.build_macro_ontology(snapshot)
    assert ontology["entity_types"]
    assert ontology["edge_types"]
    assert "WINQ26" in ontology["analysis_summary"]

    markdown = projection.render_snapshot_markdown(
        snapshot,
        [event],
        "Evaluate transmission from oil into Brazilian assets.",
    )
    assert "# Macro Live Snapshot" in markdown
    assert "## News Impact Links" in markdown
    assert "### WINQ26" in markdown
    assert "Banco Alpha" in markdown
    assert "Feed Health" in markdown

    sparse = projection.render_snapshot_markdown(
        {"generated_at": "now", "market": {}, "sources": {}},
        [],
        "Sparse scenario",
    )
    assert "No impactful macro news" in sparse
    assert "No contract market data" in sparse
