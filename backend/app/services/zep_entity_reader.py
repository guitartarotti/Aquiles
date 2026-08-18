"""
Graph entity reading and filtering service.

The historical name is kept because the rest of the app already imports
`ZepEntityReader`, but the implementation now reads from whichever graph
backend is active.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..utils.logger import get_logger
from .graph_builder import GraphBuilderService

logger = get_logger("mirofish.zep_entity_reader")


@dataclass
class EntityNode:
    """Filtered entity node plus related context."""

    uuid: str
    name: str
    labels: List[str]
    summary: str
    attributes: Dict[str, Any]
    related_edges: List[Dict[str, Any]] = field(default_factory=list)
    related_nodes: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "labels": self.labels,
            "summary": self.summary,
            "attributes": self.attributes,
            "related_edges": self.related_edges,
            "related_nodes": self.related_nodes,
        }

    def get_entity_type(self) -> Optional[str]:
        for label in self.labels:
            if label not in ["Entity", "Node"]:
                return label
        return None


@dataclass
class FilteredEntities:
    """Container returned by entity filtering APIs."""

    entities: List[EntityNode]
    entity_types: Set[str]
    total_count: int
    filtered_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [entity.to_dict() for entity in self.entities],
            "entity_types": list(self.entity_types),
            "total_count": self.total_count,
            "filtered_count": self.filtered_count,
        }


class ZepEntityReader:
    """
    Backend-agnostic entity reader.

    The class name is preserved to avoid changing the rest of the codebase,
    but it now reads from `GraphBuilderService.get_graph_data()` so it works
    for both Zep Cloud and Graphiti local.
    """

    def __init__(self, api_key: Optional[str] = None):
        del api_key
        self.builder = GraphBuilderService()

    def get_all_nodes(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"获取图谱 {graph_id} 的所有节点...")
        graph_data = self.builder.get_graph_data(graph_id)
        nodes = graph_data.get("nodes", [])
        logger.info(f"共获取 {len(nodes)} 个节点")
        return [
            {
                "uuid": node.get("uuid", ""),
                "name": node.get("name", ""),
                "labels": node.get("labels", []),
                "summary": node.get("summary", ""),
                "attributes": node.get("attributes", {}),
            }
            for node in nodes
        ]

    def get_all_edges(self, graph_id: str) -> List[Dict[str, Any]]:
        logger.info(f"获取图谱 {graph_id} 的所有边...")
        graph_data = self.builder.get_graph_data(graph_id)
        edges = graph_data.get("edges", [])
        logger.info(f"共获取 {len(edges)} 条边")
        return [
            {
                "uuid": edge.get("uuid", ""),
                "name": edge.get("name", ""),
                "fact": edge.get("fact", ""),
                "source_node_uuid": edge.get("source_node_uuid", ""),
                "target_node_uuid": edge.get("target_node_uuid", ""),
                "attributes": edge.get("attributes", {}),
            }
            for edge in edges
        ]

    def get_node_edges(self, graph_id: str, node_uuid: str) -> List[Dict[str, Any]]:
        try:
            return [
                edge
                for edge in self.get_all_edges(graph_id)
                if edge["source_node_uuid"] == node_uuid or edge["target_node_uuid"] == node_uuid
            ]
        except Exception as exc:
            logger.warning(f"获取节点 {node_uuid} 的边失败: {exc}")
            return []

    def filter_defined_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        logger.info(f"开始筛选图谱 {graph_id} 的实体...")

        all_nodes = self.get_all_nodes(graph_id)
        total_count = len(all_nodes)
        all_edges = self.get_all_edges(graph_id) if enrich_with_edges else []
        node_map = {node["uuid"]: node for node in all_nodes}

        filtered_entities: List[EntityNode] = []
        entity_types_found: Set[str] = set()

        for node in all_nodes:
            labels = node.get("labels", [])
            custom_labels = [label for label in labels if label not in ["Entity", "Node"]]

            if not custom_labels:
                continue

            matching_labels = (
                [label for label in custom_labels if label in defined_entity_types]
                if defined_entity_types
                else custom_labels
            )
            if not matching_labels:
                continue

            entity_type = matching_labels[0]
            entity_types_found.add(entity_type)

            related_edges: List[Dict[str, Any]] = []
            related_nodes: List[Dict[str, Any]] = []

            if enrich_with_edges:
                related_node_uuids = set()
                for edge in all_edges:
                    if edge["source_node_uuid"] == node["uuid"]:
                        related_edges.append(
                            {
                                "direction": "outgoing",
                                "edge_name": edge["name"],
                                "fact": edge["fact"],
                                "target_node_uuid": edge["target_node_uuid"],
                            }
                        )
                        related_node_uuids.add(edge["target_node_uuid"])
                    elif edge["target_node_uuid"] == node["uuid"]:
                        related_edges.append(
                            {
                                "direction": "incoming",
                                "edge_name": edge["name"],
                                "fact": edge["fact"],
                                "source_node_uuid": edge["source_node_uuid"],
                            }
                        )
                        related_node_uuids.add(edge["source_node_uuid"])

                for related_uuid in related_node_uuids:
                    related_node = node_map.get(related_uuid)
                    if not related_node:
                        continue
                    related_nodes.append(
                        {
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        }
                    )

            filtered_entities.append(
                EntityNode(
                    uuid=node["uuid"],
                    name=node["name"],
                    labels=node["labels"],
                    summary=node.get("summary", ""),
                    attributes=node.get("attributes", {}),
                    related_edges=related_edges,
                    related_nodes=related_nodes,
                )
            )

        logger.info(
            f"筛选完成: 总节点 {total_count}, 符合条件 {len(filtered_entities)}, 实体类型: {entity_types_found}"
        )

        return FilteredEntities(
            entities=filtered_entities,
            entity_types=entity_types_found,
            total_count=total_count,
            filtered_count=len(filtered_entities),
        )

    def get_entity_with_context(self, graph_id: str, entity_uuid: str) -> Optional[EntityNode]:
        try:
            all_nodes = self.get_all_nodes(graph_id)
            node_map = {node["uuid"]: node for node in all_nodes}
            node = node_map.get(entity_uuid)
            if not node:
                return None

            edges = self.get_node_edges(graph_id, entity_uuid)
            related_edges: List[Dict[str, Any]] = []
            related_node_uuids = set()

            for edge in edges:
                if edge["source_node_uuid"] == entity_uuid:
                    related_edges.append(
                        {
                            "direction": "outgoing",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "target_node_uuid": edge["target_node_uuid"],
                        }
                    )
                    related_node_uuids.add(edge["target_node_uuid"])
                else:
                    related_edges.append(
                        {
                            "direction": "incoming",
                            "edge_name": edge["name"],
                            "fact": edge["fact"],
                            "source_node_uuid": edge["source_node_uuid"],
                        }
                    )
                    related_node_uuids.add(edge["source_node_uuid"])

            related_nodes = []
            for related_uuid in related_node_uuids:
                related_node = node_map.get(related_uuid)
                if related_node:
                    related_nodes.append(
                        {
                            "uuid": related_node["uuid"],
                            "name": related_node["name"],
                            "labels": related_node["labels"],
                            "summary": related_node.get("summary", ""),
                        }
                    )

            return EntityNode(
                uuid=node["uuid"],
                name=node["name"],
                labels=node["labels"],
                summary=node.get("summary", ""),
                attributes=node.get("attributes", {}),
                related_edges=related_edges,
                related_nodes=related_nodes,
            )
        except Exception as exc:
            logger.error(f"获取实体 {entity_uuid} 失败: {exc}")
            return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ) -> List[EntityNode]:
        result = self.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        )
        return result.entities
