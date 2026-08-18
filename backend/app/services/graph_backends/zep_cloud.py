from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from zep_cloud import EntityEdgeSourceTarget, EpisodeData
from zep_cloud.client import Zep

from ...config import Config
from ...utils.locale import t
from ...utils.zep_paging import fetch_all_edges, fetch_all_nodes
from .base import GraphBackend, GraphInfo, ProgressCallback


class ZepCloudGraphBackend(GraphBackend):
    """Current production graph backend backed by Zep Cloud."""

    backend_name = "zep_cloud"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.ZEP_API_KEY
        if not self.api_key:
            raise ValueError("ZEP_API_KEY 未配置")

        self.client = Zep(api_key=self.api_key)

    def create_graph(self, name: str, description: Optional[str] = None) -> str:
        graph_id = f"mirofish_{uuid.uuid4().hex[:16]}"
        self.client.graph.create(
            graph_id=graph_id,
            name=name,
            description=description or "MiroFish Social Simulation Graph",
        )
        return graph_id

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        import warnings
        from typing import Optional

        from pydantic import Field
        from zep_cloud.external_clients.ontology import EdgeModel, EntityModel, EntityText

        warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

        reserved_names = {"uuid", "name", "group_id", "name_embedding", "summary", "created_at"}

        def safe_attr_name(attr_name: str) -> str:
            if attr_name.lower() in reserved_names:
                return f"entity_{attr_name}"
            return attr_name

        entity_types = {}
        for entity_def in ontology.get("entity_types", []):
            name = entity_def["name"]
            description = entity_def.get("description", f"A {name} entity.")
            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in entity_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])
                attr_desc = attr_def.get("description", attr_name)
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[EntityText]

            attrs["__annotations__"] = annotations
            entity_class = type(name, (EntityModel,), attrs)
            entity_class.__doc__ = description
            entity_types[name] = entity_class

        edge_definitions = {}
        for edge_def in ontology.get("edge_types", []):
            name = edge_def["name"]
            description = edge_def.get("description", f"A {name} relationship.")
            attrs = {"__doc__": description}
            annotations = {}

            for attr_def in edge_def.get("attributes", []):
                attr_name = safe_attr_name(attr_def["name"])
                attr_desc = attr_def.get("description", attr_name)
                attrs[attr_name] = Field(description=attr_desc, default=None)
                annotations[attr_name] = Optional[str]

            attrs["__annotations__"] = annotations
            class_name = "".join(word.capitalize() for word in name.split("_"))
            edge_class = type(class_name, (EdgeModel,), attrs)
            edge_class.__doc__ = description

            source_targets = []
            for source_target in edge_def.get("source_targets", []):
                source_targets.append(
                    EntityEdgeSourceTarget(
                        source=source_target.get("source", "Entity"),
                        target=source_target.get("target", "Entity"),
                    )
                )

            if source_targets:
                edge_definitions[name] = (edge_class, source_targets)

        if entity_types or edge_definitions:
            self.client.graph.set_ontology(
                graph_ids=[graph_id],
                entities=entity_types if entity_types else None,
                edges=edge_definitions if edge_definitions else None,
            )

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: ProgressCallback = None,
    ) -> List[str]:
        episode_uuids: List[str] = []
        total_chunks = len(chunks)

        for i in range(0, total_chunks, batch_size):
            batch_chunks = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total_chunks + batch_size - 1) // batch_size

            if progress_callback:
                progress = (i + len(batch_chunks)) / total_chunks
                progress_callback(
                    t("progress.sendingBatch", current=batch_num, total=total_batches, chunks=len(batch_chunks)),
                    progress,
                )

            episodes = [EpisodeData(data=chunk, type="text") for chunk in batch_chunks]

            try:
                batch_result = self.client.graph.add_batch(graph_id=graph_id, episodes=episodes)
                if batch_result and isinstance(batch_result, list):
                    for episode in batch_result:
                        ep_uuid = getattr(episode, "uuid_", None) or getattr(episode, "uuid", None)
                        if ep_uuid:
                            episode_uuids.append(ep_uuid)
                time.sleep(1)
            except Exception as exc:
                if progress_callback:
                    progress_callback(t("progress.batchFailed", batch=batch_num, error=str(exc)), 0)
                raise

        return episode_uuids

    def wait_for_ingestion(
        self,
        graph_id: str,
        episode_ids: List[str],
        progress_callback: ProgressCallback = None,
        timeout: int = 600,
    ):
        del graph_id

        if not episode_ids:
            if progress_callback:
                progress_callback(t("progress.noEpisodesWait"), 1.0)
            return

        start_time = time.time()
        pending_episodes = set(episode_ids)
        completed_count = 0
        total_episodes = len(episode_ids)

        if progress_callback:
            progress_callback(t("progress.waitingEpisodes", count=total_episodes), 0)

        while pending_episodes:
            if time.time() - start_time > timeout:
                if progress_callback:
                    progress_callback(
                        t("progress.episodesTimeout", completed=completed_count, total=total_episodes),
                        completed_count / total_episodes,
                    )
                break

            for episode_uuid in list(pending_episodes):
                try:
                    episode = self.client.graph.episode.get(uuid_=episode_uuid)
                    if getattr(episode, "processed", False):
                        pending_episodes.remove(episode_uuid)
                        completed_count += 1
                except Exception:
                    pass

            elapsed = int(time.time() - start_time)
            if progress_callback:
                progress_callback(
                    t(
                        "progress.zepProcessing",
                        completed=completed_count,
                        total=total_episodes,
                        pending=len(pending_episodes),
                        elapsed=elapsed,
                    ),
                    completed_count / total_episodes if total_episodes > 0 else 0,
                )

            if pending_episodes:
                time.sleep(3)

        if progress_callback:
            progress_callback(t("progress.processingComplete", completed=completed_count, total=total_episodes), 1.0)

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        entity_types = set()
        for node in nodes:
            if node.labels:
                for label in node.labels:
                    if label not in ["Entity", "Node"]:
                        entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(nodes),
            edge_count=len(edges),
            entity_types=list(entity_types),
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        nodes = fetch_all_nodes(self.client, graph_id)
        edges = fetch_all_edges(self.client, graph_id)

        node_map = {}
        for node in nodes:
            node_map[node.uuid_] = node.name or ""

        nodes_data = []
        for node in nodes:
            created_at = getattr(node, "created_at", None)
            if created_at:
                created_at = str(created_at)

            nodes_data.append(
                {
                    "uuid": node.uuid_,
                    "name": node.name,
                    "labels": node.labels or [],
                    "summary": node.summary or "",
                    "attributes": node.attributes or {},
                    "created_at": created_at,
                }
            )

        edges_data = []
        for edge in edges:
            created_at = getattr(edge, "created_at", None)
            valid_at = getattr(edge, "valid_at", None)
            invalid_at = getattr(edge, "invalid_at", None)
            expired_at = getattr(edge, "expired_at", None)

            episodes = getattr(edge, "episodes", None) or getattr(edge, "episode_ids", None)
            if episodes and not isinstance(episodes, list):
                episodes = [str(episodes)]
            elif episodes:
                episodes = [str(episode) for episode in episodes]

            fact_type = getattr(edge, "fact_type", None) or edge.name or ""

            edges_data.append(
                {
                    "uuid": edge.uuid_,
                    "name": edge.name or "",
                    "fact": edge.fact or "",
                    "fact_type": fact_type,
                    "source_node_uuid": edge.source_node_uuid,
                    "target_node_uuid": edge.target_node_uuid,
                    "source_node_name": node_map.get(edge.source_node_uuid, ""),
                    "target_node_name": node_map.get(edge.target_node_uuid, ""),
                    "attributes": edge.attributes or {},
                    "created_at": str(created_at) if created_at else None,
                    "valid_at": str(valid_at) if valid_at else None,
                    "invalid_at": str(invalid_at) if invalid_at else None,
                    "expired_at": str(expired_at) if expired_at else None,
                    "episodes": episodes or [],
                }
            )

        return {
            "graph_id": graph_id,
            "nodes": nodes_data,
            "edges": edges_data,
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
        }

    def delete_graph(self, graph_id: str):
        self.client.graph.delete(graph_id=graph_id)
