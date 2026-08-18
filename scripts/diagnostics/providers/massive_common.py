"""Shared configuration and output paths for Massive diagnostics."""

from __future__ import annotations

import os
from pathlib import Path


ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts"


def massive_api_key() -> str:
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MASSIVE_API_KEY is required to run this diagnostic")
    return api_key


def artifact_path(filename: str) -> Path:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS_DIR / filename
