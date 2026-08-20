"""HTTP adapter for collectors owned by the collection scheduler process."""

from __future__ import annotations

from typing import Any

import requests
from flask import has_request_context, request

from ..config import Config


class ScheduledCollectorClient:
    """Expose a manager-like interface while execution stays outside the API."""

    def __init__(self, collector: str, base_url: str | None = None) -> None:
        self.collector = collector
        self.base_url = str(base_url or Config.COLLECTION_SCHEDULER_SERVICE_URL).rstrip("/")

    def status(self) -> dict[str, Any]:
        return self._request("GET", "status")

    def start(self, **options: Any) -> dict[str, Any]:
        return self._request("POST", "start", options)

    def stop(self) -> dict[str, Any]:
        return self._request("POST", "stop")

    def collect_once(self, **options: Any) -> dict[str, Any]:
        return self._request("POST", "collect", options)

    def _request(
        self,
        method: str,
        command: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = requests.request(
            method,
            f"{self.base_url}/api/collections/{self.collector}/{command}",
            json=payload or None,
            headers=self._forwarded_headers(),
            timeout=Config.COLLECTION_SCHEDULER_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError("Collection scheduler returned an invalid response")
        return data

    @staticmethod
    def _forwarded_headers() -> dict[str, str]:
        headers: dict[str, str] = {}
        if Config.INTERNAL_SERVICE_TOKEN:
            headers["X-Aquiles-Internal-Token"] = Config.INTERNAL_SERVICE_TOKEN
        if has_request_context():
            for name in ("Authorization", "X-Request-ID"):
                value = request.headers.get(name)
                if value:
                    headers[name] = value
        return headers
