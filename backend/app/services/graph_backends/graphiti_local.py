from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from neo4j import GraphDatabase

from ...config import Config
from ...utils.locale import t
from ...utils.logger import get_logger
from .base import GraphBackend, GraphInfo, ProgressCallback

logger = get_logger("aquiles.graphiti_local")


class GraphitiLocalBackend(GraphBackend):
    """Graph backend powered by a local Graphiti + Neo4j runtime."""

    backend_name = "graphiti_local"

    _NODE_RESERVED_FIELDS = {
        "uuid",
        "name",
        "group_id",
        "created_at",
        "summary",
        "name_embedding",
        "summary_embedding",
        "labels",
    }
    _EDGE_RESERVED_FIELDS = {
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
        "fact_embedding",
        "episodes",
    }

    def __init__(self):
        self.neo4j_uri = Config.NEO4J_URI
        self.neo4j_user = Config.NEO4J_USER
        self.neo4j_password = Config.NEO4J_PASSWORD

        self.repo_root = Path(__file__).resolve().parents[4]
        self.graphiti_root = self.repo_root / "graphiti-local"
        self.graphiti_bridge_script = self.graphiti_root / "backend_bridge.py"
        self.graphiti_python = self._resolve_graphiti_python()
        self.graphs_dir = Path(Config.UPLOAD_FOLDER) / "graphiti_graphs"
        self.runtime_dir = self.repo_root / ".codex-run"
        self.graphs_dir.mkdir(parents=True, exist_ok=True)

        if not self.graphiti_bridge_script.exists():
            raise ValueError(
                "Graphiti bridge script not found. Expected "
                f"{self.graphiti_bridge_script}"
            )

        self._check_neo4j_connection()

    def create_graph(self, name: str, description: Optional[str] = None) -> str:
        graph_id = f"graphiti_{uuid.uuid4().hex[:16]}"
        metadata = {
            "graph_id": graph_id,
            "name": name,
            "description": description or "Aquiles Graphiti Local Graph",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "ontology": None,
            "episode_ids": [],
            "backend": self.backend_name,
        }
        self._save_metadata(graph_id, metadata)
        return graph_id

    def set_ontology(self, graph_id: str, ontology: Dict[str, Any]):
        metadata = self._load_metadata(graph_id)
        metadata["ontology"] = ontology
        metadata["updated_at"] = datetime.now().isoformat()
        self._save_metadata(graph_id, metadata)

    def add_text_batches(
        self,
        graph_id: str,
        chunks: List[str],
        batch_size: int = 3,
        progress_callback: ProgressCallback = None,
    ) -> List[str]:
        if not chunks:
            return []

        metadata = self._load_metadata(graph_id)
        ontology = metadata.get("ontology") or {}

        episode_ids: List[str] = []
        total_chunks = len(chunks)
        total_batches = (total_chunks + batch_size - 1) // batch_size

        for index in range(0, total_chunks, batch_size):
            batch_chunks = chunks[index:index + batch_size]
            batch_num = index // batch_size + 1

            if progress_callback:
                progress_callback(
                    t(
                        "progress.sendingBatch",
                        current=batch_num,
                        total=total_batches,
                        chunks=len(batch_chunks),
                    ),
                    (index + len(batch_chunks)) / total_chunks,
                )

            payload = {
                "graph_id": graph_id,
                "graph_name": metadata.get("name") or graph_id,
                "chunks": batch_chunks,
                "ontology": ontology,
                "source_description": metadata.get("description") or "Aquiles Graphiti Local Graph",
            }
            result = self._run_bridge("add_text_batch", payload, timeout=900)
            batch_episode_ids = [str(item) for item in result.get("episode_ids", []) if item]
            episode_ids.extend(batch_episode_ids)

        metadata["episode_ids"] = self._dedupe_list(metadata.get("episode_ids", []) + episode_ids)
        metadata["updated_at"] = datetime.now().isoformat()
        self._save_metadata(graph_id, metadata)

        return episode_ids

    def wait_for_ingestion(
        self,
        graph_id: str,
        episode_ids: List[str],
        progress_callback: ProgressCallback = None,
        timeout: int = 600,
    ):
        del graph_id, episode_ids, timeout
        if progress_callback:
            progress_callback(t("progress.processingComplete", completed=1, total=1), 1.0)

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        data = self.get_graph_data(graph_id)
        entity_types = set()
        for node in data["nodes"]:
            for label in node.get("labels", []):
                if label not in {"Entity", "Node"}:
                    entity_types.add(label)

        return GraphInfo(
            graph_id=graph_id,
            node_count=len(data["nodes"]),
            edge_count=len(data["edges"]),
            entity_types=sorted(entity_types),
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        self._load_metadata(graph_id)

        node_query = """
        MATCH (n:Entity {group_id: $graph_id})
        RETURN
            n.uuid AS uuid,
            n.name AS name,
            labels(n) AS labels,
            coalesce(n.summary, '') AS summary,
            properties(n) AS attributes,
            n.created_at AS created_at
        ORDER BY n.name
        """
        edge_query = """
        MATCH (source:Entity {group_id: $graph_id})-[e:RELATES_TO {group_id: $graph_id}]->(target:Entity {group_id: $graph_id})
        RETURN
            e.uuid AS uuid,
            coalesce(e.name, '') AS name,
            coalesce(e.fact, '') AS fact,
            source.uuid AS source_node_uuid,
            target.uuid AS target_node_uuid,
            source.name AS source_node_name,
            target.name AS target_node_name,
            properties(e) AS attributes,
            e.created_at AS created_at,
            e.valid_at AS valid_at,
            e.invalid_at AS invalid_at,
            e.expired_at AS expired_at
        ORDER BY e.created_at
        """

        with self._driver() as driver:
            node_records, _, _ = driver.execute_query(node_query, graph_id=graph_id)
            edge_records, _, _ = driver.execute_query(edge_query, graph_id=graph_id)

        nodes = []
        for record in node_records:
            data = record.data()
            attributes = self._strip_reserved_attributes(
                data.get("attributes") or {},
                self._NODE_RESERVED_FIELDS,
            )
            nodes.append(
                {
                    "uuid": data.get("uuid", ""),
                    "name": data.get("name", ""),
                    "labels": data.get("labels") or [],
                    "summary": data.get("summary") or "",
                    "attributes": attributes,
                    "created_at": self._stringify_temporal(data.get("created_at")),
                }
            )

        edges = []
        for record in edge_records:
            data = record.data()
            attributes = self._strip_reserved_attributes(
                data.get("attributes") or {},
                self._EDGE_RESERVED_FIELDS,
            )
            raw_episodes = attributes.pop("episodes", None)
            if raw_episodes is None:
                episodes = []
            elif isinstance(raw_episodes, list):
                episodes = [str(item) for item in raw_episodes]
            else:
                episodes = [str(raw_episodes)]

            edges.append(
                {
                    "uuid": data.get("uuid", ""),
                    "name": data.get("name", ""),
                    "fact": data.get("fact", ""),
                    "fact_type": data.get("name", ""),
                    "source_node_uuid": data.get("source_node_uuid", ""),
                    "target_node_uuid": data.get("target_node_uuid", ""),
                    "source_node_name": data.get("source_node_name", ""),
                    "target_node_name": data.get("target_node_name", ""),
                    "attributes": attributes,
                    "created_at": self._stringify_temporal(data.get("created_at")),
                    "valid_at": self._stringify_temporal(data.get("valid_at")),
                    "invalid_at": self._stringify_temporal(data.get("invalid_at")),
                    "expired_at": self._stringify_temporal(data.get("expired_at")),
                    "episodes": episodes,
                }
            )

        return {
            "graph_id": graph_id,
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    def delete_graph(self, graph_id: str):
        delete_query = """
        MATCH (n {group_id: $graph_id})
        WHERE n:Entity OR n:Episodic OR n:Community OR n:Saga
        DETACH DELETE n
        """
        with self._driver() as driver:
            driver.execute_query(delete_query, graph_id=graph_id)

        metadata_path = self._metadata_path(graph_id)
        if metadata_path.exists():
            metadata_path.unlink()

    def _resolve_graphiti_python(self) -> Path:
        configured = os.environ.get("GRAPHITI_PYTHON_BIN")
        if configured:
            candidate = Path(configured)
            if candidate.exists():
                return candidate

        candidates = [
            self.graphiti_root / ".venv" / "Scripts" / "python.exe",
            self.graphiti_root / ".venv" / "bin" / "python",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

        raise ValueError(
            "Graphiti local Python runtime not found. "
            "Expected graphiti-local/.venv to be available."
        )

    def _run_bridge(self, action: str, payload: Dict[str, Any], timeout: int = 600) -> Dict[str, Any]:
        process = subprocess.run(
            [str(self.graphiti_python), str(self.graphiti_bridge_script), action],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            cwd=str(self.repo_root),
        )
        if process.returncode != 0:
            stderr = (process.stderr or process.stdout or "").strip()
            raise RuntimeError(f"Graphiti bridge failed for {action}: {stderr}")

        stdout = process.stdout.strip()
        if not stdout:
            return {}

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Graphiti bridge returned invalid JSON for {action}: {stdout}") from exc

    def _check_neo4j_connection(self):
        try:
            with self._driver() as driver:
                driver.execute_query("RETURN 1 AS ok")
        except Exception as exc:
            logger.warning("Neo4j connection failed on first attempt: %s", exc)
            if self._try_auto_start_neo4j():
                try:
                    with self._driver() as driver:
                        driver.execute_query("RETURN 1 AS ok")
                    logger.info("Neo4j local runtime auto-started successfully for Graphiti")
                    return
                except Exception as restart_exc:
                    logger.error("Neo4j auto-start attempted but the connection still failed: %s", restart_exc)
                    raise ValueError(f"Neo4j connection failed after auto-start attempt: {restart_exc}") from restart_exc
            raise ValueError(f"Neo4j connection failed: {exc}") from exc

    def _driver(self):
        return GraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_user, self.neo4j_password),
        )

    def _try_auto_start_neo4j(self) -> bool:
        auto_start_enabled = os.environ.get("GRAPHITI_AUTO_START_NEO4J", "true").strip().lower() == "true"
        if not auto_start_enabled:
            return False

        host, port = self._parse_bolt_endpoint()
        if host not in {"127.0.0.1", "localhost"}:
            return False
        if self._is_port_open(host, port):
            return True

        neo4j_home = self._resolve_local_neo4j_home()
        if neo4j_home is None:
            logger.warning("Bundled Neo4j runtime was not found; skipping auto-start")
            return False

        neo4j_command = neo4j_home / "bin" / ("neo4j.bat" if os.name == "nt" else "neo4j")
        if not neo4j_command.exists():
            logger.warning("Neo4j startup command not found at %s", neo4j_command)
            return False

        env = os.environ.copy()
        java_home = env.get("JAVA_HOME") or self._discover_java_home()
        if java_home:
            env["JAVA_HOME"] = java_home
            env["PATH"] = f"{java_home}{os.sep}bin{os.pathsep}{env.get('PATH', '')}"

        stdout_path = self.runtime_dir / "neo4j-auto.out.log"
        stderr_path = self.runtime_dir / "neo4j-auto.err.log"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            with open(stdout_path, "a", encoding="utf-8") as stdout_handle, open(stderr_path, "a", encoding="utf-8") as stderr_handle:
                subprocess.Popen(
                    [str(neo4j_command), "console"],
                    cwd=str(neo4j_home),
                    env=env,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    creationflags=creationflags,
                )
        except Exception:
            logger.exception("Failed to auto-start Neo4j local runtime")
            return False

        deadline = time.time() + 45
        while time.time() < deadline:
            if self._is_port_open(host, port):
                return True
            time.sleep(1.5)

        logger.warning("Neo4j auto-start did not expose bolt on %s:%s before timeout", host, port)
        return False

    def _resolve_local_neo4j_home(self) -> Path | None:
        configured_home = os.environ.get("GRAPHITI_NEO4J_HOME")
        if configured_home:
            candidate = Path(configured_home)
            if candidate.exists():
                return candidate

        bundled = self.runtime_dir / "neo4j-community-5.26.24"
        if bundled.exists():
            return bundled
        return None

    def _discover_java_home(self) -> str | None:
        candidates = [
            self.runtime_dir / "jdk-21",
            Path("C:/Program Files/Eclipse Adoptium/jdk-21.0.10.7-hotspot"),
            Path("C:/Program Files/Eclipse Adoptium/jdk-21"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return None

    def _parse_bolt_endpoint(self) -> tuple[str, int]:
        uri = str(self.neo4j_uri or "").strip()
        if uri.startswith("bolt://"):
            uri = uri[len("bolt://") :]
        if ":" not in uri:
            return uri or "127.0.0.1", 7687
        host, port_text = uri.rsplit(":", 1)
        try:
            return host or "127.0.0.1", int(port_text)
        except ValueError:
            return host or "127.0.0.1", 7687

    @staticmethod
    def _is_port_open(host: str, port: int) -> bool:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            return False

    def _metadata_path(self, graph_id: str) -> Path:
        return self.graphs_dir / f"{graph_id}.json"

    def _load_metadata(self, graph_id: str) -> Dict[str, Any]:
        metadata_path = self._metadata_path(graph_id)
        if not metadata_path.exists():
            raise ValueError(f"Graph metadata not found for {graph_id}")

        with open(metadata_path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _save_metadata(self, graph_id: str, metadata: Dict[str, Any]):
        metadata_path = self._metadata_path(graph_id)
        with open(metadata_path, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False, indent=2)

    @staticmethod
    def _dedupe_list(values: List[str]) -> List[str]:
        seen = set()
        result = []
        for value in values:
            if value and value not in seen:
                result.append(value)
                seen.add(value)
        return result

    @staticmethod
    def _strip_reserved_attributes(attributes: Dict[str, Any], reserved_fields: set[str]) -> Dict[str, Any]:
        cleaned = {}
        for key, value in attributes.items():
            if key in reserved_fields:
                continue
            if key.endswith("_embedding"):
                continue
            cleaned[key] = value
        return cleaned

    @staticmethod
    def _stringify_temporal(value: Any) -> Optional[str]:
        if value is None:
            return None
        return str(value)
