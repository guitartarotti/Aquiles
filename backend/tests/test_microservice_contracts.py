from __future__ import annotations

import importlib
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

RUNNER_CONTRACTS = (
    ("run_atemporal_price_chart_service", "aquiles-atemporal-price-chart-service"),
    ("run_cvm_cda_graph_service", "aquiles-cvm-cda-graph-service"),
    ("run_discovery_market_service", "aquiles-discovery-service"),
    ("run_etf_daily_flow_service", "aquiles-etf-daily-flow-service"),
    ("run_fair_value_markov_regime_service", "aquiles-fair-value-markov-regime-service"),
    ("run_flow_replicator_service", "aquiles-flow-replicator-service"),
    ("run_legacy_heatmap_service", "aquiles-legacy-heatmap-service"),
    ("run_options_collector_service", "aquiles-options-collector-service"),
    ("run_options_model_service", "aquiles-options-model-service"),
    ("run_options_volume_tracker_service", "aquiles-options-volume-tracker-service"),
    ("run_vol_analytics_service", "aquiles-vol-analytics-service"),
)


class RecordingStub:
    def __init__(self, **responses: Any) -> None:
        self.responses = responses
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str):
        if name not in self.responses:
            raise AttributeError(name)

        def method(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            response = self.responses[name]
            return response(*args, **kwargs) if callable(response) else response

        return method


def _load_runner(monkeypatch, module_name: str):
    monkeypatch.setenv("AQUILES_AUTH_ENABLED", "false")
    module = importlib.import_module(module_name)
    module.app.config.update(TESTING=True)
    auth_manager = module.app.extensions.get("aquiles_auth")
    if auth_manager is not None and auth_manager.settings.enabled:
        auth_manager.settings = replace(auth_manager.settings, enabled=False)
    return module


def _stub_health_dependencies(monkeypatch, module_name: str, module) -> None:
    if module_name == "run_cvm_cda_graph_service":
        monkeypatch.setattr(module, "graph_service", RecordingStub(status={"ok": True}))
    elif module_name == "run_discovery_market_service":
        monkeypatch.setattr(
            module,
            "_latest_capture_payload",
            lambda: {"capture_id": "capture-1", "captured_at": "2026-08-18T12:00:00Z", "row_count": 8},
        )
    elif module_name == "run_etf_daily_flow_service":
        monkeypatch.setattr(module, "etf_flow_manager", RecordingStub(status={"running": False}))
        monkeypatch.setattr(module, "etf_flow_service", RecordingStub(health={"status": "ok"}))
    elif module_name == "run_flow_replicator_service":
        monkeypatch.setattr(
            module,
            "replicator",
            RecordingStub(status={"running": False, "connected": False, "ticker": "WINQ26"}),
        )
    elif module_name == "run_options_collector_service":
        monkeypatch.setattr(module, "collector", RecordingStub(status={"running": False}))
    elif module_name == "run_options_volume_tracker_service":
        monkeypatch.setattr(
            module,
            "tracker",
            RecordingStub(status={"running": False, "tracked_symbols": 0, "latest_monthly_iv_at": None}),
        )
    elif module_name == "run_vol_analytics_service":
        monkeypatch.setattr(module, "VolIndexService", lambda _underlying: RecordingStub(get_latest={}))
        monkeypatch.setattr(module, "_sync_status", lambda _underlying: {"running": False})


@pytest.mark.parametrize(("module_name", "service_name"), RUNNER_CONTRACTS)
def test_every_http_microservice_exposes_health_contract(
    monkeypatch,
    module_name: str,
    service_name: str,
) -> None:
    module = _load_runner(monkeypatch, module_name)
    _stub_health_dependencies(monkeypatch, module_name, module)

    response = module.app.test_client().get("/health")
    payload = response.get_json()

    assert response.status_code == 200
    assert response.is_json
    assert payload["service"] == service_name
    assert payload["status"] in {"ok", "degraded"}
    assert "error" not in payload
    assert "traceback" not in payload


def test_contract_inventory_covers_every_http_runner(monkeypatch) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    runner_modules = {path.stem for path in backend_root.glob("run*_service.py")}
    contracted_modules = {module_name for module_name, _service_name in RUNNER_CONTRACTS}

    assert contracted_modules == runner_modules
    for module_name in sorted(contracted_modules):
        module = _load_runner(monkeypatch, module_name)
        assert any(rule.rule == "/health" for rule in module.app.url_map.iter_rules())


def test_atemporal_chart_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_atemporal_price_chart_service")
    service = RecordingStub(build_payload={"ok": True, "chart_rows": [], "latest": None})
    monkeypatch.setattr(module, "atemporal_chart_service", service)

    response = module.app.test_client().post(
        "/api/discovery/atemporal/price-chart",
        json={"symbol": "XB1", "ticks_per_candle": 12, "tick_size_points": 5},
    )

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "data": {"ok": True, "chart_rows": [], "latest": None},
    }
    assert service.calls[0][2]["symbol"] == "XB1"
    assert service.calls[0][2]["ticks_per_candle"] == 12


def test_cda_graph_schema_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_cvm_cda_graph_service")
    expected = {"ok": True, "schema_version": 2, "node_types": ["Fund", "Asset"]}
    monkeypatch.setattr(module, "graph_service", RecordingStub(schema=expected))

    response = module.app.test_client().get("/api/v1/cda-graph/schema")

    assert response.status_code == 200
    assert response.get_json() == expected


def test_discovery_capture_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_discovery_market_service")
    capture = {
        "capture_id": "capture-42",
        "captured_at": "2026-08-18T12:00:00Z",
        "row_count": 12,
        "rows": [],
    }
    monkeypatch.setattr(module, "_latest_capture_payload", lambda: capture)

    response = module.app.test_client().get("/api/discovery/xb1/latest-capture")

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": capture}


def test_etf_daily_flow_dashboard_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_etf_daily_flow_service")
    dashboard = {"ok": True, "kpis": {"net_flow": 1250000}, "funds": []}
    service = RecordingStub(dashboard=dashboard)
    monkeypatch.setattr(module, "etf_flow_service", service)

    response = module.app.test_client().get("/api/v1/etf-daily-flow/dashboard?top_n=7")

    assert response.status_code == 200
    assert response.get_json() == dashboard
    assert service.calls == [("dashboard", (), {"top_n": 7})]


def test_markov_latest_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_fair_value_markov_regime_service")
    result = {"ok": True, "regime": {"key": "balanced"}, "probabilities": {"balanced": 0.7}}
    service = RecordingStub(build_latest_payload=result)
    monkeypatch.setattr(module, "markov_regime_service", service)

    response = module.app.test_client().post(
        "/api/discovery/fair-value/markov-regime/latest",
        json={"sessions": 3, "bar_minutes": 15, "regime_mode": "smart"},
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": result}
    assert service.calls[0][2]["sessions"] == 3
    assert service.calls[0][2]["bar_minutes"] == 15


def test_flow_agents_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_flow_replicator_service")
    rows = [{"agent": "broker-1", "buy": 120, "sell": 80, "net": 40}]
    store = RecordingStub(latest_agents=rows)
    monkeypatch.setattr(module, "store", store)

    response = module.app.test_client().get("/api/flow/agents/latest?ticker=WINQ26&limit=12")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "data": {"agents": rows, "count": 1},
    }
    assert store.calls == [("latest_agents", ("WINQ26",), {"limit": 12})]


def test_legacy_heatmap_status_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_legacy_heatmap_service")
    participant_module = importlib.import_module("app.services.macro_participant_heatmap_manager")
    options_module = importlib.import_module("app.services.macro_options_heatmap_context_manager")
    participant = RecordingStub(status={"running": False, "sample_count": 10})
    options = RecordingStub(status={"running": False, "sample_count": 4})
    monkeypatch.setattr(
        participant_module.MacroParticipantHeatmapCollectorManager,
        "get_instance",
        classmethod(lambda _cls: participant),
    )
    monkeypatch.setattr(
        options_module.MacroOptionsHeatmapContextManager,
        "get_instance",
        classmethod(lambda _cls: options),
    )

    response = module.app.test_client().get("/api/legacy/heatmap/status")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "data": {
            "participant_heatmap": {"running": False, "sample_count": 10},
            "options_heatmap_context": {"running": False, "sample_count": 4},
        },
    }


def test_options_collector_status_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_options_collector_service")
    collector = RecordingStub(status={"running": False, "last_success_at": None})
    monkeypatch.setattr(module, "collector", collector)

    response = module.app.test_client().get("/api/options/collector/status")

    assert response.status_code == 200
    assert response.get_json() == {
        "success": True,
        "data": {"running": False, "last_success_at": None},
    }


def test_options_model_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_options_model_service")
    model = {"run_id": "run-1", "underlying_security": "IBOVE Index", "contracts": []}
    service = RecordingStub(latest_model_run=model)
    monkeypatch.setattr(module, "read_service", service)

    response = module.app.test_client().get(
        "/api/options/model/latest?underlying_security=IBOVE+Index&universe_tier=liquid&compact=true"
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": model}
    assert service.calls[0][2] == {
        "underlying_security": "IBOVE Index",
        "universe_tier": "liquid",
        "compact": True,
        "ttl_seconds": 5.0,
    }


def test_options_volume_activity_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_options_volume_tracker_service")
    rows = [{"symbol": "PETRK100", "volume": 2500}]
    store = RecordingStub(read_volume_activity=rows)
    monkeypatch.setattr(module, "store", store)

    response = module.app.test_client().get(
        "/api/options/volume/activity?symbol=PETRK100&lookback_days=3&limit=20"
    )

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "data": rows, "count": 1}
    assert store.calls[0][2] == {
        "session_date": None,
        "symbol": "PETRK100",
        "underlying_security": None,
        "limit": 20,
        "lookback_days": 3,
    }


def test_vol_index_latest_payload_contract(monkeypatch) -> None:
    module = _load_runner(monkeypatch, "run_vol_analytics_service")
    latest = {"captured_at": "2026-08-18T12:00:00Z", "value": 18.4}
    service = RecordingStub(get_latest=latest)
    monkeypatch.setattr(module, "VolIndexService", lambda _underlying: service)
    monkeypatch.setattr(module, "_sync_status", lambda _underlying: {"running": False})

    response = module.app.test_client().get(
        "/api/options/vol-index/latest?underlying=IBOVE+Index&refresh=true&no_sync=true"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"] == {**latest, "sync": {"running": False}}
    assert service.calls == [("get_latest", (), {})]
