from __future__ import annotations

from typing import Any, Protocol


class IntradayContextReader(Protocol):
    """Read-only context required by intraday modeling services."""

    def read_live_capture_snapshots(
        self,
        *,
        session_date: str | None = None,
        underlying_security: str = "IBOVE Index",
    ) -> list[dict[str, Any]]: ...

    def read_state(self) -> dict[str, Any]: ...
