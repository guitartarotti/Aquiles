from __future__ import annotations

from datetime import datetime, timezone

import pytest
from flask import Flask

from app.api import options_bp
from app.api import options_vol_index as vol_index_api


@pytest.fixture(autouse=True)
def clear_vol_index_state():
    vol_index_api._invalidate_cache()
    vol_index_api._collect_states.clear()
    yield
    vol_index_api._invalidate_cache()
    vol_index_api._collect_states.clear()


@pytest.fixture()
def app() -> Flask:
    application = Flask(__name__)
    application.config.update(TESTING=True)
    application.register_blueprint(options_bp, url_prefix="/api/options")
    return application


def test_vol_index_routes_remain_registered(app: Flask) -> None:
    rules = {rule.rule: sorted(rule.methods) for rule in app.url_map.iter_rules()}

    assert "/api/options/vol-index/history" in rules
    assert "/api/options/vol-index/latest" in rules
    assert "/api/options/vol-index/collect" in rules
    assert "/api/options/vol-index/price" in rules
    assert "GET" in rules["/api/options/vol-index/history"]
    assert "POST" in rules["/api/options/vol-index/collect"]


def test_compact_history_preserves_contract_and_uses_cache(
    app: Flask,
    monkeypatch,
) -> None:
    class FakeVolIndexService:
        history_calls = 0

        def __init__(self, underlying: str) -> None:
            self.underlying = underlying

        def get_intraday_history(self, _days: int) -> list[dict]:
            type(self).history_calls += 1
            return [
                {
                    "date": "2026-08-17",
                    "captured_at": "2026-08-17T15:00:00Z",
                    "iv_atm": 0.22,
                    "iv_interpolated": 0.215,
                    "internal_field": "must-not-leak-in-compact-mode",
                }
            ]

        def get_history(self, _days: int) -> list[dict]:
            raise AssertionError("daily history is not read in compact mode")

    monkeypatch.setattr(vol_index_api, "_sync_from_tracker", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.services.vol_index.VolIndexService",
        FakeVolIndexService,
    )

    client = app.test_client()
    first = client.get(
        "/api/options/vol-index/history",
        query_string={"underlying": "IBOVE Index", "compact": "true"},
    )
    second = client.get(
        "/api/options/vol-index/history",
        query_string={"underlying": "IBOVE Index", "compact": "true"},
    )

    assert first.status_code == 200
    assert first.get_json()["data"]["intraday_history"] == [
        {
            "date": "2026-08-17",
            "captured_at": "2026-08-17T15:00:00Z",
            "iv_atm": 0.22,
            "iv_interpolated": 0.215,
        }
    ]
    assert second.status_code == 200
    assert second.get_json()["cached"] is True
    assert FakeVolIndexService.history_calls == 1


def test_price_endpoint_validates_required_fields(app: Flask) -> None:
    response = app.test_client().post(
        "/api/options/vol-index/price",
        json={"underlying": "IBOVE Index"},
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "success": False,
        "error": "date and close are required",
    }


def test_iso_datetime_parser_normalizes_to_utc() -> None:
    parsed = vol_index_api._parse_iso_datetime("2026-08-17T12:30:00-03:00")

    assert parsed == datetime(2026, 8, 17, 15, 30, tzinfo=timezone.utc)
    assert vol_index_api._parse_iso_datetime("") is None
    assert vol_index_api._parse_iso_datetime("invalid") is None


def test_snapshot_tier_merge_deduplicates_contracts() -> None:
    class FakeQuery:
        def latest_snapshot(self, *, universe_tier: str, **_kwargs) -> dict:
            rows = {
                "structural": [{"option_id": "A"}, {"option_id": "B"}],
                "liquid": [{"option_id": "B"}, {"option_id": "C"}],
                "critical": [{"option_id": "A"}],
            }
            return {"rows": rows[universe_tier], "batch": {"tier": universe_tier}}

    rows, batch = vol_index_api._merge_snapshot_tiers(FakeQuery(), "IBOVE Index")

    assert [row["option_id"] for row in rows] == ["A", "B", "C"]
    assert batch == {"tier": "structural"}
