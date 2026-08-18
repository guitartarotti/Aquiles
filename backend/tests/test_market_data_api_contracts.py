from __future__ import annotations

from typing import Any

import pytest
from flask import Flask

from app.api import cvm_cda as cvm_api
from app.api import funds_flow_local as funds_api


class RecordingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _result(self, method: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((method, kwargs))
        return {"ok": True, "method": method, "arguments": kwargs}

    def __getattr__(self, method: str):
        return lambda **kwargs: self._result(method, **kwargs)


class RecordingManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _result(self, method: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append((method, kwargs))
        return {"ok": True, "method": method}

    def status(self) -> dict[str, Any]:
        return self._result("status")

    def start(self) -> dict[str, Any]:
        return self._result("start")

    def stop(self) -> dict[str, Any]:
        return self._result("stop")

    def collect_once(self, **kwargs: Any) -> dict[str, Any]:
        return self._result("collect_once", **kwargs)


@pytest.fixture()
def market_api(monkeypatch):
    application = Flask(__name__)
    application.config.update(TESTING=True)

    funds_service = RecordingService()
    funds_manager = RecordingManager()
    cvm_service = RecordingService()
    cvm_manager = RecordingManager()

    monkeypatch.setattr(funds_api, "funds_flow_local_service", funds_service)
    monkeypatch.setattr(
        funds_api.FundsFlowLocalManager,
        "get_instance",
        classmethod(lambda _cls: funds_manager),
    )
    monkeypatch.setattr(cvm_api, "cvm_cda_service", cvm_service)
    monkeypatch.setattr(
        cvm_api.CvmCdaManager,
        "get_instance",
        classmethod(lambda _cls: cvm_manager),
    )

    application.register_blueprint(
        funds_api.funds_flow_local_bp,
        url_prefix="/api/v1/funds-flow-local",
    )
    application.register_blueprint(cvm_api.cvm_cda_bp, url_prefix="/api/v1/cvm-cda")
    return application, funds_service, funds_manager, cvm_service, cvm_manager


def test_funds_flow_routes_preserve_parameters_and_collector_contract(market_api) -> None:
    application, service, manager, _, _ = market_api
    client = application.test_client()

    dashboard = client.get(
        "/api/v1/funds-flow-local/dashboard",
        query_string={
            "date": "2026-08-14",
            "period": "63d",
            "history_days": "95",
            "refresh": "yes",
        },
    )
    assert dashboard.status_code == 200
    assert dashboard.headers["Cache-Control"] == "no-store, max-age=0"
    assert dashboard.get_json()["collector"]["method"] == "status"
    assert service.calls[-1] == (
        "get_dashboard",
        {
            "target_date": "2026-08-14",
            "period": "63d",
            "history_days": 95,
            "refresh": True,
        },
    )

    collect = client.post(
        "/api/v1/funds-flow-local/collect",
        json={"force": "false", "period": "21d", "history_days": 80},
    )
    assert collect.status_code == 200
    assert manager.calls[-2] == (
        "collect_once",
        {
            "force": False,
            "target_date": None,
            "period": "21d",
            "history_days": 80,
        },
    )

    refresh = client.post(
        "/api/v1/funds-flow-local/sources/cvm/refresh",
        json={"target_date": "2026-08-14"},
    )
    assert refresh.status_code == 200
    assert refresh.get_json()["requested_source_id"] == "cvm"
    assert manager.calls[-2][0] == "collect_once"
    assert manager.calls[-2][1]["force"] is True

    assert client.get("/api/v1/funds-flow-local/status").get_json()["method"] == "status"
    assert client.post("/api/v1/funds-flow-local/collector/start").get_json()["method"] == "start"
    assert client.post("/api/v1/funds-flow-local/collector/stop").get_json()["method"] == "stop"


def test_cvm_cda_read_routes_preserve_query_contract(market_api) -> None:
    application, _, _, service, _ = market_api
    client = application.test_client()

    assert client.get("/api/v1/cvm-cda/dashboard?month=202607").status_code == 200
    assert service.calls[-1] == ("get_dashboard", {"month": "202607"})

    assert client.get(
        "/api/v1/cvm-cda/analytics/funds",
        query_string={"month": "202607", "target": "local", "side": "short", "page": 2, "per_page": 10},
    ).status_code == 200
    assert service.calls[-1] == (
        "list_funds",
        {"month": "202607", "target": "local", "side": "short", "page": 2, "per_page": 10},
    )

    assert client.get("/api/v1/cvm-cda/analytics/assets?page=invalid").status_code == 200
    assert service.calls[-1][0] == "list_assets"
    assert service.calls[-1][1]["page"] == 1

    assert client.get("/api/v1/cvm-cda/analytics/fund-holdings/12.345/0001").status_code == 200
    assert service.calls[-1][0] == "list_fund_holdings"
    assert service.calls[-1][1]["fund_cnpj"] == "12.345/0001"

    assert client.get("/api/v1/cvm-cda/analytics/positioning?month=latest").status_code == 200
    assert service.calls[-1][0] == "get_positioning_lab"
    assert client.get("/api/v1/cvm-cda/analytics/radar?force=on").status_code == 200
    assert service.calls[-1] == ("get_redemption_radar", {"month": "latest", "force": True})
    assert client.get("/api/v1/cvm-cda/status").status_code == 200
    assert service.calls[-1][0] == "status"
    assert client.get("/api/v1/cvm-cda/remote?force=true").status_code == 200
    assert service.calls[-1] == ("discover_remote_months", {"force": True})


def test_cvm_cda_command_routes_choose_explicit_or_latest_ingestion(market_api) -> None:
    application, _, _, service, manager = market_api
    client = application.test_client()

    explicit = client.post(
        "/api/v1/cvm-cda/ingest",
        json={"month": "202607", "force": False},
    )
    assert explicit.status_code == 200
    assert service.calls[-1] == ("ingest_month", {"month": "202607", "force": False})

    latest = client.post(
        "/api/v1/cvm-cda/ingest",
        json={"month": "latest", "lookback_months": "invalid"},
    )
    assert latest.status_code == 200
    assert service.calls[-1] == ("ingest_latest", {"force": True, "lookback_months": 1})

    collect = client.post(
        "/api/v1/cvm-cda/collect",
        json={"force": "yes", "lookback_months": 3},
    )
    assert collect.status_code == 200
    assert manager.calls[-2] == (
        "collect_once",
        {"force": True, "lookback_months": 3},
    )

    assert client.post("/api/v1/cvm-cda/collector/start").get_json()["method"] == "start"
    assert client.post("/api/v1/cvm-cda/collector/stop").get_json()["method"] == "stop"
