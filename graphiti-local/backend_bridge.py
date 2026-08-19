import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[1]


def prepare_env():
    root_env = ROOT_DIR / ".env"
    if root_env.exists():
        load_dotenv(root_env, override=False)

    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("LLM_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["LLM_API_KEY"]


def safe_attr_name(name: str, reserved: set[str], prefix: str) -> str:
    normalized = (name or "").strip()
    if not normalized:
        normalized = "value"
    normalized = normalized.replace(" ", "_").replace("-", "_")
    if normalized in reserved:
        normalized = f"{prefix}_{normalized}"
    return normalized


def build_entity_types(ontology: Dict[str, Any]) -> Dict[str, type[BaseModel]]:
    from graphiti_core.nodes import EntityNode

    reserved = set(EntityNode.model_fields.keys())
    entity_types: Dict[str, type[BaseModel]] = {}

    for entity_def in ontology.get("entity_types", []):
        name = entity_def.get("name")
        if not name:
            continue

        attrs: Dict[str, Any] = {"__doc__": entity_def.get("description", f"{name} entity")}
        annotations: Dict[str, Any] = {}

        for attr_def in entity_def.get("attributes", []):
            attr_name = safe_attr_name(attr_def.get("name", "value"), reserved, "entity")
            annotations[attr_name] = str | None
            attrs[attr_name] = Field(default=None, description=attr_def.get("description", attr_name))

        attrs["__annotations__"] = annotations
        entity_types[name] = type(name, (BaseModel,), attrs)

    return entity_types


def build_edge_types(ontology: Dict[str, Any]) -> tuple[Dict[str, type[BaseModel]], Dict[tuple[str, str], list[str]]]:
    reserved = {
        "uuid",
        "name",
        "fact",
        "group_id",
        "source_node_uuid",
        "target_node_uuid",
        "created_at",
        "valid_at",
        "invalid_at",
        "expired_at",
        "episodes",
    }
    edge_types: Dict[str, type[BaseModel]] = {}
    edge_type_map: Dict[tuple[str, str], list[str]] = {}

    for edge_def in ontology.get("edge_types", []):
        edge_name = edge_def.get("name")
        if not edge_name:
            continue

        class_name = "".join(part.capitalize() for part in edge_name.split("_")) or "EdgeType"
        attrs: Dict[str, Any] = {"__doc__": edge_def.get("description", f"{edge_name} relationship")}
        annotations: Dict[str, Any] = {}

        for attr_def in edge_def.get("attributes", []):
            attr_name = safe_attr_name(attr_def.get("name", "value"), reserved, "edge")
            annotations[attr_name] = str | None
            attrs[attr_name] = Field(default=None, description=attr_def.get("description", attr_name))

        attrs["__annotations__"] = annotations
        edge_types[edge_name] = type(class_name, (BaseModel,), attrs)

        for source_target in edge_def.get("source_targets", []):
            source = source_target.get("source", "Entity")
            target = source_target.get("target", "Entity")
            key = (source, target)
            edge_type_map.setdefault(key, [])
            if edge_name not in edge_type_map[key]:
                edge_type_map[key].append(edge_name)

    return edge_types, edge_type_map


def build_custom_extraction_instructions(ontology: Dict[str, Any]) -> str:
    entity_parts = []
    for entity_def in ontology.get("entity_types", []):
        entity_name = entity_def.get("name")
        if not entity_name:
            continue
        description = entity_def.get("description", "")
        attrs = ", ".join(attr.get("name", "") for attr in entity_def.get("attributes", []) if attr.get("name"))
        suffix = f" Attributes: {attrs}." if attrs else ""
        entity_parts.append(f"- {entity_name}: {description}{suffix}")

    edge_parts = []
    for edge_def in ontology.get("edge_types", []):
        edge_name = edge_def.get("name")
        if not edge_name:
            continue
        description = edge_def.get("description", "")
        pairs = []
        for source_target in edge_def.get("source_targets", []):
            source = source_target.get("source", "Entity")
            target = source_target.get("target", "Entity")
            pairs.append(f"{source}->{target}")
        pair_text = f" Allowed pairs: {', '.join(pairs)}." if pairs else ""
        edge_parts.append(f"- {edge_name}: {description}{pair_text}")

    instructions = []
    if entity_parts:
        instructions.append("Use only these entity types when classifying extracted entities:\n" + "\n".join(entity_parts))
    if edge_parts:
        instructions.append("Prefer these relationship types when extracting facts:\n" + "\n".join(edge_parts))
    return "\n\n".join(instructions)


async def add_text_batch(payload: Dict[str, Any]) -> Dict[str, Any]:
    prepare_env()

    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
    from graphiti_core.embedder.openai import OpenAIEmbedder
    from graphiti_core.llm_client.openai_client import OpenAIClient
    from graphiti_core.nodes import EpisodeType

    graph_id = payload["graph_id"]
    ontology = payload.get("ontology") or {}
    chunks = payload.get("chunks") or []
    source_description = payload.get("source_description", "Aquiles Graphiti Local Graph")
    graph_name = payload.get("graph_name", graph_id)

    entity_types = build_entity_types(ontology)
    edge_types, edge_type_map = build_edge_types(ontology)
    custom_instructions = build_custom_extraction_instructions(ontology)

    graphiti = Graphiti(
        uri=os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "password"),
        llm_client=OpenAIClient(),
        embedder=OpenAIEmbedder(),
        cross_encoder=OpenAIRerankerClient(),
    )

    episode_ids = []
    try:
        for index, chunk in enumerate(chunks):
            result = await graphiti.add_episode(
                name=f"{graph_name}-chunk-{index + 1}",
                episode_body=chunk,
                source_description=source_description,
                reference_time=datetime.now(timezone.utc),
                source=EpisodeType.text,
                group_id=graph_id,
                entity_types=entity_types or None,
                edge_types=edge_types or None,
                edge_type_map=edge_type_map or None,
                custom_extraction_instructions=custom_instructions or None,
            )
            episode_ids.append(getattr(result.episode, "uuid", None))
    finally:
        await graphiti.close()

    return {
        "graph_id": graph_id,
        "episode_ids": [episode_id for episode_id in episode_ids if episode_id],
        "chunk_count": len(chunks),
    }


async def main():
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:
        raise SystemExit("Usage: backend_bridge.py <action>")

    action = sys.argv[1]
    payload = json.loads(sys.stdin.read() or "{}")

    if action == "add_text_batch":
        result = await add_text_batch(payload)
    else:
        raise SystemExit(f"Unsupported action: {action}")

    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
