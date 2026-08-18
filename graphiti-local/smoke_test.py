import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv


def prepare_env():
    root_env = Path(__file__).resolve().parents[1] / ".env"
    if root_env.exists():
        load_dotenv(root_env, override=False)

    if not os.environ.get("OPENAI_API_KEY") and os.environ.get("LLM_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["LLM_API_KEY"]


async def run_smoke_test():
    prepare_env()

    results = {
        "environment": {
            "openai_api_key_present": bool(os.environ.get("OPENAI_API_KEY")),
            "neo4j_uri": os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
        },
        "tests": [],
    }

    def add_test(name, ok, details):
        results["tests"].append(
            {
                "name": name,
                "ok": ok,
                "details": details,
            }
        )

    try:
        import graphiti_core
        import neo4j
        import openai

        add_test(
            "package_imports",
            True,
            {
                "graphiti_core_version": getattr(graphiti_core, "__version__", "unknown"),
                "neo4j_version": getattr(neo4j, "__version__", "unknown"),
                "openai_version": getattr(openai, "__version__", "unknown"),
            },
        )
    except Exception as exc:
        add_test("package_imports", False, {"error": repr(exc)})
        return results

    try:
        from graphiti_core import Graphiti
        from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient
        from graphiti_core.driver.neo4j_driver import Neo4jDriver
        from graphiti_core.embedder.openai import OpenAIEmbedder
        from graphiti_core.llm_client.openai_client import OpenAIClient

        add_test(
            "public_api_imports",
            True,
            {
                "Graphiti": str(Graphiti),
                "Neo4jDriver": str(Neo4jDriver),
            },
        )
    except Exception as exc:
        add_test("public_api_imports", False, {"error": repr(exc)})
        return results

    try:
        llm_client = OpenAIClient()
        embedder = OpenAIEmbedder()
        cross_encoder = OpenAIRerankerClient()
        add_test(
            "openai_clients_init",
            True,
            {
                "llm_client": llm_client.__class__.__name__,
                "embedder": embedder.__class__.__name__,
                "cross_encoder": cross_encoder.__class__.__name__,
            },
        )
    except Exception as exc:
        add_test("openai_clients_init", False, {"error": repr(exc)})
        return results

    graphiti = None
    try:
        graphiti = Graphiti(
            uri=os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"),
            user=os.environ.get("NEO4J_USER", "neo4j"),
            password=os.environ.get("NEO4J_PASSWORD", "password"),
            llm_client=llm_client,
            embedder=embedder,
            cross_encoder=cross_encoder,
        )
        add_test(
            "graphiti_init",
            True,
            {
                "driver_class": graphiti.driver.__class__.__name__,
                "llm_class": graphiti.llm_client.__class__.__name__,
                "embedder_class": graphiti.embedder.__class__.__name__,
                "cross_encoder_class": graphiti.cross_encoder.__class__.__name__,
            },
        )
    except Exception as exc:
        add_test("graphiti_init", False, {"error": repr(exc)})
        return results

    try:
        runtime_result = await graphiti.driver.execute_query("RETURN 1 AS ok")
        first_record = runtime_result.records[0].data() if runtime_result.records else None
        add_test(
            "neo4j_runtime_connection",
            True,
            {
                "message": "Neo4j responded to a Graphiti driver query.",
                "record": first_record,
            },
        )
    except Exception as exc:
        add_test(
            "neo4j_runtime_connection",
            False,
            {
                "error_type": exc.__class__.__name__,
                "error": str(exc),
                "expected": "A failure here is expected when Neo4j is not running locally.",
            },
        )
    finally:
        if graphiti is not None:
            try:
                await graphiti.close()
            except Exception:
                pass

    return results


if __name__ == "__main__":
    report = asyncio.run(run_smoke_test())
    print(json.dumps(report, indent=2, ensure_ascii=False))
