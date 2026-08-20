from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup

from app.config import Config
from app.services.etf_daily_flow_service import (
    EtfDailyFlowService,
    EtfObservation,
    EtfScrapeError,
    GenericHtmlEtfProvider,
    _anchor_snippet,
    _classify_aum_bucket,
    _classify_country_focus,
    _classify_development,
    _classify_segment,
    _classify_type,
    _coalesce,
    _compact_text,
    _finite_float,
    _fund_text_blob,
    _json_dumps,
    _json_loads,
    _meta_float,
    _meta_text,
    _parse_date,
    _provider_label,
    _row_text_for_label,
    _safe_provider,
    _safe_ticker,
    _sha256,
    _slugify,
    _text_by_data_id,
    _value_after_label,
    _walk_json,
)

TZ = ZoneInfo("America/Sao_Paulo")


def test_etf_normalizers_cover_market_formats_and_classification() -> None:
    assert _safe_provider("State Street Global Advisors") == "state_street"
    assert _safe_provider("BlackRock") == "ishares"
    assert _safe_ticker(" brk.b / ") == "BRK.B"
    assert _slugify("S&P 500 & Growth") == "s-and-p-500-and-growth"
    assert _finite_float("US$ 1,25 billion") == 1_250_000_000
    assert _finite_float("2.5M") == 2_500_000
    assert _finite_float("-") is None
    assert _parse_date(date(2026, 8, 19), TZ) == "2026-08-19"
    assert _parse_date(datetime(2026, 8, 18, 12), TZ) == "2026-08-18"
    assert _parse_date("as of August 17, 2026", TZ) == "2026-08-17"
    assert _parse_date("invalid", TZ) is None
    assert _coalesce(None, "", 0, 2) == 0
    assert _json_loads(_json_dumps({"b": 2, "a": 1})) == {"a": 1, "b": 2}
    assert _json_loads("bad", []) == []
    assert len(_sha256("aquiles")) == 64

    metadata = {
        "catalog_asset_class": "Equity",
        "catalog_category": "Sector",
        "catalog_strategy": "Artificial Intelligence growth",
        "catalog_net_expense_ratio": "0.25%",
    }
    name = "Brazil Artificial Intelligence ETF"
    assert "artificial intelligence" in _fund_text_blob(name, metadata)
    assert _meta_float(metadata, "catalog_net_expense_ratio") == 0.25
    assert _meta_text(metadata, "missing", "catalog_category") == "Sector"
    assert _classify_country_focus(name, metadata) == "Brasil"
    assert _classify_development(name, metadata) == "Emergentes"
    assert _classify_segment(name, metadata) == "Equity"
    assert _classify_type(name, metadata, "Equity", "Brasil") == "Single country"
    assert _classify_segment("Bitcoin ETF", {}) == "Digital assets"
    assert _classify_type("Short Treasury ETF", {}, "Renda fixa", "Estados Unidos") == "Inverse"
    assert _provider_label("global_x") == "Global X"
    assert [_classify_aum_bucket(value) for value in (None, 1, 1e9, 3e9, 20e9, 60e9)] == [
        "Sem AUM",
        "< US$ 500 mi",
        "US$ 500 mi-2 bi",
        "US$ 2-10 bi",
        "US$ 10-50 bi",
        "US$ 50 bi+",
    ]


def test_generic_provider_parses_dom_regex_and_structured_json() -> None:
    provider = GenericHtmlEtfProvider(timeout_seconds=1, user_agent="Aquiles tests")
    markup = """
    <html><body>
      <div id="price-nav">$125.50</div>
      <div id="snapshot-netAssets">US$ 2.5 billion</div>
      <div id="price-asOfDate">August 18, 2026</div>
      <div data-id="shares">20,000,000</div>
      <div><span>Shares Outstanding</span><strong>20,000,000 as of 08/18/2026</strong></div>
      <script type="application/json">
        {"fund":{"sharesOutstanding":"20000000","navDate":"2026-08-18"}}
      </script>
    </body></html>
    """
    soup = BeautifulSoup(markup, "html.parser")

    assert _compact_text(" a\n b ") == "a b"
    assert _text_by_data_id(soup, "shares") == "20,000,000"
    assert _row_text_for_label(soup, "Shares Outstanding") == "Shares Outstanding"
    assert _value_after_label("NAV $125.50 as of today", "NAV") == "$125.50"
    assert "nav" in _anchor_snippet(markup, "NAV", radius=20).lower()
    assert ("fund.sharesOutstanding", "20000000") in _walk_json(
        {"fund": {"sharesOutstanding": "20000000"}}
    )

    observation = provider.parse_observation(
        {
            "provider": "globalx",
            "ticker": " qyld ",
            "name": "Global X Nasdaq 100 Covered Call ETF",
            "currency": "usd",
        },
        markup,
        "https://example.test/qyld",
        TZ,
    )
    assert observation.provider == "global_x"
    assert observation.ticker == "QYLD"
    assert observation.nav == 125.5
    assert observation.shares_outstanding == 20_000_000
    assert observation.total_net_assets == 2_500_000_000
    assert observation.as_of_date == "2026-08-18"

    inferred = provider.build_observation_from_fields(
        fund={"provider": "test", "ticker": "TST"},
        fields={"nav": 10, "total_net_assets": 1_000, "as_of_date": "2026-08-18"},
        source_url="https://example.test/tst",
        tz=TZ,
    )
    assert inferred.shares_outstanding == 100
    assert inferred.confidence == 0.75
    with pytest.raises(EtfScrapeError, match="missing nav"):
        provider.build_observation_from_fields(
            fund={"provider": "test", "ticker": "BAD"},
            fields={},
            source_url="https://example.test/bad",
            tz=TZ,
        )


class _QueuedProvider:
    def __init__(self, observations: list[EtfObservation | Exception]):
        self.observations = observations

    def fetch_observation(self, _fund: dict, _tz: ZoneInfo) -> EtfObservation:
        result = self.observations.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _observation(as_of_date: str, *, shares: float, nav: float, field_hash: str) -> EtfObservation:
    return EtfObservation(
        provider="test",
        ticker="TST",
        as_of_date=as_of_date,
        captured_at=f"{as_of_date}T20:00:00+00:00",
        source_url="https://example.test/tst",
        nav=nav,
        shares_outstanding=shares,
        total_net_assets=nav * shares,
        currency="USD",
        confidence=0.9,
        field_hash=field_hash,
        extraction_method="fixture",
        raw_payload={"nav": nav, "shares": shares},
        warnings=[],
    )


def test_etf_sqlite_pipeline_calculates_flows_health_and_dashboard(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(Config, "ETF_DAILY_FLOW_SEED_DEFAULT_UNIVERSE", False)
    monkeypatch.setattr(Config, "ETF_DAILY_FLOW_UNIVERSE_JSON", "")
    monkeypatch.setattr(Config, "ETF_DAILY_FLOW_REFRESH_CATALOG_BEFORE_COLLECT", False)
    monkeypatch.setattr(Config, "ETF_DAILY_FLOW_CAPTURE_TIMES", "09:30,16:30,bad")
    service = EtfDailyFlowService(tmp_path)

    with pytest.raises(ValueError, match="provider, ticker and url"):
        service.upsert_fund({"provider": "test"})
    assert service.upsert_fund(
        {
            "provider": "test",
            "ticker": "TST",
            "name": "US Technology ETF",
            "url": "https://example.test/tst",
            "metadata": {"catalog_asset_class": "Equity", "catalog_net_expense_ratio": 0.2},
        }
    )["created"]
    assert not service.upsert_fund(
        {
            "provider": "test",
            "ticker": "TST",
            "url": "https://example.test/tst-v2",
        }
    )["created"]

    service._providers["test"] = _QueuedProvider(
        [
            _observation("2026-08-17", shares=100, nav=10, field_hash="v1"),
            _observation("2026-08-18", shares=115, nav=11, field_hash="v2"),
        ]
    )
    first = service.collect(provider="test")
    second = service.collect(provider="test")

    assert first["observations_count"] == 1
    assert first["flows_count"] == 0
    assert second["flows_count"] == 1
    assert service.list_universe(active=True, provider="test")["count"] == 1
    assert service.list_runs()["count"] == 2
    assert service.list_observations(ticker="tst")["count"] == 2
    flows = service.list_flows(provider="test")
    assert flows["count"] == 1
    assert flows["flows"][0]["flow_usd"] == 165

    dashboard = service.dashboard(top_n=5)
    assert dashboard["summary"]["flow_funds"] == 1
    assert dashboard["summary"]["net_flow_usd"] == 165
    assert dashboard["top_inflows"][0]["ticker"] == "TST"
    assert dashboard["tables"]["by_issuer"][0]["label"] == "Test"
    assert dashboard["heatmap"]["cells"]

    health = service.health(manager_status={"running": True})
    assert health["active_funds"] == 1
    assert health["contract_summary"]["total"] == 1
    assert health["contracts"][0]["status"] == "contract_changed"

    now = datetime(2026, 8, 19, 17, 0, tzinfo=TZ)
    slot = service.due_slot(now)
    assert slot and "2026-08-19T16:30" in slot
    service.mark_slot_started(slot)
    assert service.due_slot(now) is None
    assert "2026-08-20T09:30" in (service.next_run_at(now) or "")
    assert len(service._capture_times()) == 2


def test_etf_pipeline_records_failures_and_split_guard(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Config, "ETF_DAILY_FLOW_SEED_DEFAULT_UNIVERSE", False)
    monkeypatch.setattr(Config, "ETF_DAILY_FLOW_UNIVERSE_JSON", "")
    monkeypatch.setattr(Config, "ETF_DAILY_FLOW_REFRESH_CATALOG_BEFORE_COLLECT", False)
    monkeypatch.setattr(Config, "ETF_DAILY_FLOW_REQUEST_MAX_ATTEMPTS", 1)
    service = EtfDailyFlowService(tmp_path)
    service.upsert_fund(
        {"provider": "test", "ticker": "ERR", "url": "https://example.test/err"}
    )
    service._providers["test"] = _QueuedProvider([EtfScrapeError("fixture failure")])

    failed = service.collect(provider="test")
    assert failed["status"] == "failed"
    assert failed["failure_count"] == 1
    assert service.list_errors()["count"] == 1
    assert service.health()["contract_summary"]["degraded"] == 1
    assert service._looks_like_split(100, 200, 10, 5)
    assert not service._looks_like_split(100, 110, 10, 11)
    assert not service._looks_like_split(0, 100, 10, 10)
