"""Shared scheduling rules for the options heatmap collector."""

from __future__ import annotations

from typing import Any

from ..config import Config


def options_poll_interval_seconds(config: Any = Config) -> int:
    return max(
        2,
        min(
            int(config.MACRO_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS),
            int(config.MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS),
            int(config.MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS),
        ),
    )
