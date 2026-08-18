from __future__ import annotations

from typing import Optional

from ...config import Config
from .base import GraphBackend
from .graphiti_local import GraphitiLocalBackend
from .zep_cloud import ZepCloudGraphBackend


def create_graph_backend(
    backend_name: Optional[str] = None,
    api_key: Optional[str] = None,
) -> GraphBackend:
    """Instantiate the configured graph backend implementation."""

    selected_backend = (backend_name or Config.GRAPH_BACKEND or "zep_cloud").strip().lower()

    if selected_backend == "zep_cloud":
        return ZepCloudGraphBackend(api_key=api_key)

    if selected_backend == "graphiti_local":
        return GraphitiLocalBackend()

    raise ValueError(f"Unsupported graph backend: {selected_backend}")
