from __future__ import annotations

from typing import Any

from app.config import Config
from app.infrastructure.scheduled_collector_client import ScheduledCollectorClient
from run_collection_scheduler_service import app, execute_collector_command


class RecordingCollector:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _record(self, command: str, **payload: Any) -> dict[str, Any]:
        self.calls.append((command, payload))
        return {"command": command, **payload}

    def status(self) -> dict[str, Any]:
        return self._record("status")

    def start(self, **payload: Any) -> dict[str, Any]:
        return self._record("start", **payload)

    def stop(self) -> dict[str, Any]:
        return self._record("stop")

    def collect_once(self, **payload: Any) -> dict[str, Any]:
        return self._record("collect", **payload)


def test_scheduler_dispatches_domain_specific_collection_arguments() -> None:
    collector = RecordingCollector()

    result = execute_collector_command(
        collector,
        "funds_flow",
        "collect",
        {
            "force": False,
            "target_date": "2026-08-14",
            "period": "63d",
            "history_days": 95,
            "ignored": "value",
        },
    )

    assert result["command"] == "collect"
    assert collector.calls == [
        (
            "collect",
            {
                "force": False,
                "target_date": "2026-08-14",
                "period": "63d",
                "history_days": 95,
            },
        )
    ]


def test_remote_client_forwards_commands_and_request_identity(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    class Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, Any]:
            return {"success": True, "data": {"running": True}}

    def fake_request(method: str, url: str, **kwargs: Any) -> Response:
        captured.update({"method": method, "url": url, **kwargs})
        return Response()

    monkeypatch.setattr(
        "app.infrastructure.scheduled_collector_client.requests.request", fake_request
    )
    monkeypatch.setattr(Config, "INTERNAL_SERVICE_TOKEN", "internal-test-token")
    client = ScheduledCollectorClient("macro", base_url="http://scheduler:5023/")

    assert client.start(interval_seconds=30) == {"running": True}
    assert captured["method"] == "POST"
    assert captured["url"] == "http://scheduler:5023/api/collections/macro/start"
    assert captured["json"] == {"interval_seconds": 30}
    assert captured["headers"]["X-Aquiles-Internal-Token"] == "internal-test-token"


def test_scheduler_control_endpoint_requires_internal_service_token(monkeypatch) -> None:
    collector = RecordingCollector()
    monkeypatch.setattr(Config, "INTERNAL_SERVICE_TOKEN", "internal-test-token")
    monkeypatch.setattr(
        "run_collection_scheduler_service._collector",
        lambda _name: collector,
    )
    client = app.test_client()

    unauthorized = client.get("/api/collections/macro/status")
    authorized = client.get(
        "/api/collections/macro/status",
        headers={"X-Aquiles-Internal-Token": "internal-test-token"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.get_json()["data"]["command"] == "status"
