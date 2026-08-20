"""HTTP adapter for the dedicated options-volume tracker service."""

from __future__ import annotations

from typing import Any

import requests
from flask import has_request_context, request

from ..config import Config


class OptionsVolumeTrackerClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = str(base_url or Config.OPTIONS_VOLUME_TRACKER_SERVICE_URL).rstrip("/")

    def status(self) -> dict[str, Any]:
        return self._request("GET", "/api/options/volume/tracker/status")

    def start(self) -> dict[str, Any]:
        return self._request("POST", "/api/options/volume/tracker/start")

    def stop(self) -> dict[str, Any]:
        return self._request("POST", "/api/options/volume/tracker/stop")

    def backfill_today(self) -> dict[str, Any]:
        return self._request("POST", "/api/options/volume/tracker/backfill")

    def poll_once(self, underlying_security: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/options/volume/poll",
            {"underlying_security": underlying_security},
        )

    def poll_all_underlyings(self) -> dict[str, Any]:
        return self._request("POST", "/api/options/volume/poll/all")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if has_request_context():
            for name in ("Authorization", "X-Request-ID"):
                value = request.headers.get(name)
                if value:
                    headers[name] = value
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            json=payload or None,
            headers=headers,
            timeout=Config.OPTIONS_VOLUME_TRACKER_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError("Options volume tracker returned an invalid response")
        return data
