"""Shared HTTP and file-cache behavior for official source adapters."""

from __future__ import annotations

import os

import requests


class CachedHttpSource:
    def __init__(self, *, raw_dir: str, timeout_seconds: float) -> None:
        self.raw_dir = raw_dir
        self.timeout_seconds = timeout_seconds

    def _download(self, url: str, target_path: str, *, force: bool) -> None:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        if os.path.exists(target_path) and not force and os.path.getsize(target_path) > 0:
            return
        response = requests.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        temp_path = f"{target_path}.tmp"
        with open(temp_path, "wb") as handle:
            handle.write(response.content)
        os.replace(temp_path, target_path)
