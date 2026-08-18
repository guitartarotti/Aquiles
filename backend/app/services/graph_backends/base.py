from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

ProgressCallback = Optional[Callable[[str, float], None]]


@dataclass
class GraphInfo:
    """Backend-agnostic graph summary returned after ingestion."""

    graph_id: str
    node_count: int
    edge_count: int
    entity_types: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "entity_types": self.entity_types,
        }


class GraphBackend(ABC):
    """Contract implemented by each graph provider backend."""

    backend_name = "unknown"

    @abstractmethod
    def create_graph(self, name: str, description: Optional[str] = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        raise NotImplementedError

    @abstractmethod
    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: ProgressCallback = None,
    ) -> List[str]:
        raise NotImplementedError

    @abstractmethod
    def wait_for_ingestion(
        self,
        graph_id: str,
        episode_ids: List[str],
        progress_callback: ProgressCallback = None,
        timeout: int = 600,
    ):
        raise NotImplementedError

    @abstractmethod
    def get_graph_info(self, graph_id: str) -> GraphInfo:
        raise NotImplementedError

    @abstractmethod
    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def delete_graph(self, graph_id: str):
        raise NotImplementedError
