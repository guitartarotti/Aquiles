import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv


def prepare_env():
    root_env = Path(__file__).resolve().parents[1] / ".env"
    if root_env.exists():
        load_dotenv(root_env, override=False)

    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("LLM_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["LLM_API_KEY"]


async def run_e2e_test():
    prepare_env()

    from graphiti_core import Graphiti
    from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
    from graphiti_core.embedder.openai import OpenAIEmbedder
    from graphiti_core.llm_client.openai_client import OpenAIClient
    from graphiti_core.nodes import EpisodeType

    group_id = f"graphiti-e2e-{uuid4().hex[:8]}"
    graphiti = Graphiti(
        uri=os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "password"),
        llm_client=OpenAIClient(),
        embedder=OpenAIEmbedder(),
        cross_encoder=OpenAIRerankerClient(),
    )

    try:
        result = await graphiti.add_episode(
            name="macro-smoke-test",
            episode_body=(
                "Em 10 de abril de 2026, a curva longa de DI abriu, o WINJ26 caiu "
                "e o dolar WDOK26 ganhou forca apos noticias macro mais duras. "
                "Participantes locais reduziram risco no indice e buscaram protecao "
                "em dolar."
            ),
            source_description="local graphiti e2e test",
            reference_time=datetime.now(timezone.utc),
            source=EpisodeType.text,
            group_id=group_id,
        )

        episode_uuid = getattr(result.episode, "uuid", None)
        graph_slice = await graphiti.get_nodes_and_edges_by_episode([episode_uuid]) if episode_uuid else None
        runtime_counts = await graphiti.driver.execute_query(
            """
            MATCH (e:Episodic {group_id: $group_id})
            OPTIONAL MATCH (n:Entity {group_id: $group_id})
            OPTIONAL MATCH ()-[r:RELATES_TO {group_id: $group_id}]->()
            RETURN count(DISTINCT e) AS episodes,
                   count(DISTINCT n) AS entities,
                   count(DISTINCT r) AS relations
            """,
            group_id=group_id,
        )
        counts = runtime_counts.records[0].data() if runtime_counts.records else {}

        return {
            "group_id": group_id,
            "episode_uuid": episode_uuid,
            "episodes_in_db": counts.get("episodes"),
            "entities_in_db": counts.get("entities"),
            "relations_in_db": counts.get("relations"),
            "nodes_in_graph_slice": len(getattr(graph_slice, "nodes", []) or []) if graph_slice else 0,
            "edges_in_graph_slice": len(getattr(graph_slice, "edges", []) or []) if graph_slice else 0,
        }
    finally:
        await graphiti.close()


if __name__ == "__main__":
    report = asyncio.run(run_e2e_test())
    print(json.dumps(report, indent=2, ensure_ascii=False))
