from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from neo4j import GraphDatabase

from ..config import Config
from ..utils.logger import get_logger
from .cvm_cda_service import CDA_TARGET_LABELS, CDA_TARGET_SQL, CvmCdaService

logger = get_logger("aquiles.cvm_cda_graph")


class CvmCdaGraphService:
    """Deterministic Neo4j graph built from CVM CDA portfolio filings.

    This is intentionally separate from Graphiti text ingestion. CDA is
    structured portfolio data, so the graph is derived directly from audited
    rows, values and classifications instead of asking an LLM to infer facts.
    """

    DEFAULT_GROUP_ID = "funds_flow_local:cvm_cda"

    def __init__(
        self,
        *,
        cda_data_dir: str | os.PathLike[str] | None = None,
        neo4j_uri: str | None = None,
        neo4j_user: str | None = None,
        neo4j_password: str | None = None,
        group_id: str | None = None,
    ):
        self.cda_service = CvmCdaService(data_dir=cda_data_dir)
        self.cda_db_path = Path(self.cda_service.db_path)
        self.neo4j_uri = neo4j_uri or Config.NEO4J_URI
        self.neo4j_user = neo4j_user or Config.NEO4J_USER
        self.neo4j_password = neo4j_password or Config.NEO4J_PASSWORD
        self.group_id = group_id or os.environ.get("CVM_CDA_GRAPH_GROUP_ID") or self.DEFAULT_GROUP_ID

    def schema(self) -> dict[str, Any]:
        return {
            "ok": True,
            "success": True,
            "graph": {
                "name": "Funds Flow Local CDA Graph",
                "group_id": self.group_id,
                "type": "deterministic_neo4j_graph",
                "source": "CVM CDA Carteiras",
                "role": "portfolio_holdings_network",
            },
            "nodes": [
                {"label": "CdaMonth", "key": "id", "description": "Competencia mensal do CDA."},
                {"label": "CdaFund", "key": "id", "description": "Fundo brasileiro identificado por CNPJ."},
                {"label": "CdaFundType", "key": "id", "description": "Tipo cadastral do fundo no CDA."},
                {"label": "CdaAsset", "key": "id", "description": "Ativo, contrato, cota, titulo ou posicao reportada."},
                {"label": "CdaIssuer", "key": "id", "description": "Emissor ou contraparte inferida do ativo."},
                {"label": "CdaAssetClass", "key": "id", "description": "Classe normalizada do ativo."},
                {"label": "CdaCountry", "key": "id", "description": "Pais de exposicao do ativo quando disponivel."},
                {"label": "CdaExposureTarget", "key": "id", "description": "Tema analitico: exterior, credito, derivativos etc."},
            ],
            "relationships": [
                {"type": "REPORTED_IN", "from": "CdaFund", "to": "CdaMonth"},
                {"type": "HAS_FUND_TYPE", "from": "CdaFund", "to": "CdaFundType"},
                {"type": "HOLDS_POSITION", "from": "CdaFund", "to": "CdaAsset"},
                {"type": "ISSUED_BY", "from": "CdaAsset", "to": "CdaIssuer"},
                {"type": "CLASSIFIED_AS", "from": "CdaAsset", "to": "CdaAssetClass"},
                {"type": "LOCATED_IN", "from": "CdaAsset", "to": "CdaCountry"},
                {"type": "HAS_TARGET_EXPOSURE", "from": "CdaFund", "to": "CdaExposureTarget"},
            ],
            "edge_metrics": [
                "value_market",
                "abs_value_market",
                "pct_pl",
                "side",
                "qty_final",
                "value_buy",
                "value_sell",
                "target_pct_pl",
                "gross_value",
                "net_value",
                "concentration_pct",
            ],
        }

    def status(self) -> dict[str, Any]:
        cda_status = self.cda_service.status()
        latest_month = cda_status.get("latest_month")
        neo4j_status: dict[str, Any] = {"ok": False}
        graph_counts: dict[str, Any] = {}
        latest_graph_month = None
        try:
            with self._driver() as driver:
                driver.execute_query("RETURN 1 AS ok")
                latest_records, _, _ = driver.execute_query(
                    """
                    MATCH (m:CdaMonth {group_id: $group_id})
                    RETURN m.month AS month, m.imported_at AS imported_at, m.graph_updated_at AS graph_updated_at
                    ORDER BY m.month DESC
                    LIMIT 1
                    """,
                    group_id=self.group_id,
                )
                latest_graph_month = latest_records[0]["month"] if latest_records else None
                node_records, _, _ = driver.execute_query(
                    """
                    MATCH (n {group_id: $group_id})
                    UNWIND labels(n) AS label
                    WITH label, count(*) AS count
                    RETURN label, count
                    ORDER BY count DESC
                    """,
                    group_id=self.group_id,
                )
                edge_records, _, _ = driver.execute_query(
                    """
                    MATCH ()-[r {group_id: $group_id}]->()
                    RETURN type(r) AS type, count(*) AS count
                    ORDER BY count DESC
                    """,
                    group_id=self.group_id,
                )
                graph_counts = {
                    "nodes_by_label": [record.data() for record in node_records],
                    "edges_by_type": [record.data() for record in edge_records],
                }
                neo4j_status = {"ok": True, "uri": self.neo4j_uri, "user": self.neo4j_user}
        except Exception as exc:
            neo4j_status = {"ok": False, "uri": self.neo4j_uri, "error": str(exc)}

        return {
            "ok": bool(cda_status.get("ok")) and neo4j_status.get("ok", False),
            "success": bool(cda_status.get("ok")) and neo4j_status.get("ok", False),
            "service": "cvm-cda-graph",
            "group_id": self.group_id,
            "cda": {
                "ok": cda_status.get("ok"),
                "latest_month": latest_month,
                "latest_label": cda_status.get("latest_label"),
                "db_path": str(self.cda_db_path),
            },
            "neo4j": neo4j_status,
            "graph": {
                "latest_month": latest_graph_month,
                **graph_counts,
            },
            "schema": self.schema().get("graph"),
        }

    def build_graph(
        self,
        *,
        month: str | None = None,
        reset: bool = False,
        max_funds: int = 350,
        max_positions_per_fund: int = 30,
        min_abs_value: float = 10_000_000.0,
        target_funds_per_theme: int = 60,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        max_funds = max(20, min(int(max_funds or 350), 2000))
        max_positions_per_fund = max(5, min(int(max_positions_per_fund or 30), 150))
        min_abs_value = max(float(min_abs_value or 0), 0.0)
        target_funds_per_theme = max(10, min(int(target_funds_per_theme or 60), 300))
        self.cda_service.init_db()

        with self._connect_cda() as con:
            resolved_month = self._resolve_month(con, month)
            if not resolved_month:
                return {"ok": False, "success": False, "error": "CVM CDA database is empty."}
            month_row = self._fetch_month_row(con, resolved_month)
            fund_cnpjs = self._select_graph_funds(
                con,
                resolved_month,
                max_funds=max_funds,
                target_funds_per_theme=target_funds_per_theme,
            )
            funds = self._fetch_fund_nodes(con, resolved_month, fund_cnpjs)
            target_edges = self._fetch_target_edges(con, resolved_month, fund_cnpjs)
            positions = self._fetch_position_rows(
                con,
                resolved_month,
                fund_cnpjs,
                max_positions_per_fund=max_positions_per_fund,
                min_abs_value=min_abs_value,
            )

        payload = self._prepare_graph_payload(resolved_month, month_row, funds, target_edges, positions)
        if dry_run:
            return {
                "ok": True,
                "success": True,
                "dry_run": True,
                "month": resolved_month,
                "selected_funds": len(fund_cnpjs),
                "counts": payload["counts"],
                "config": {
                    "max_funds": max_funds,
                    "max_positions_per_fund": max_positions_per_fund,
                    "min_abs_value": min_abs_value,
                    "target_funds_per_theme": target_funds_per_theme,
                },
            }

        started = datetime.now(timezone.utc)
        with self._driver() as driver:
            self._ensure_constraints(driver)
            if reset:
                self.clear_month(resolved_month, driver=driver)
            self._write_payload(driver, payload)

        elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        return {
            "ok": True,
            "success": True,
            "month": resolved_month,
            "group_id": self.group_id,
            "elapsed_ms": elapsed_ms,
            "selected_funds": len(fund_cnpjs),
            "counts": payload["counts"],
            "config": {
                "reset": reset,
                "max_funds": max_funds,
                "max_positions_per_fund": max_positions_per_fund,
                "min_abs_value": min_abs_value,
                "target_funds_per_theme": target_funds_per_theme,
            },
        }

    def clear_month(self, month: str, *, driver=None) -> dict[str, Any]:
        close_driver = False
        if driver is None:
            driver = self._driver()
            close_driver = True
        try:
            records, _, _ = driver.execute_query(
                """
                MATCH (n {group_id: $group_id, month: $month})
                RETURN count(n) AS nodes
                """,
                group_id=self.group_id,
                month=month,
            )
            deleted_nodes = records[0]["nodes"] if records else 0
            if deleted_nodes:
                driver.execute_query(
                    """
                    MATCH (n {group_id: $group_id, month: $month})
                    DETACH DELETE n
                    """,
                    group_id=self.group_id,
                    month=month,
                )
            return {"ok": True, "success": True, "month": month, "deleted_nodes": deleted_nodes}
        finally:
            if close_driver:
                driver.close()

    def network(
        self,
        *,
        month: str | None = None,
        limit: int = 180,
        fund_cnpj: str | None = None,
        issuer: str | None = None,
        target: str | None = None,
    ) -> dict[str, Any]:
        resolved_month = self._resolve_graph_month(month)
        if not resolved_month:
            return {"ok": False, "success": False, "error": "CDA graph is empty.", "nodes": [], "edges": []}
        limit = max(10, min(int(limit or 180), 1000))
        params = {
            "group_id": self.group_id,
            "month": resolved_month,
            "limit": limit,
        }
        where_parts = []
        if fund_cnpj:
            params["fund_cnpj"] = self._digits(fund_cnpj)
            where_parts.append("f.cnpj = $fund_cnpj")
        if issuer:
            params["issuer_query"] = str(issuer).strip().lower()
            where_parts.append("toLower(coalesce(i.name, '')) CONTAINS $issuer_query")
        if target:
            params["target"] = target
            where_parts.append(
                "EXISTS { MATCH (f)-[:HAS_TARGET_EXPOSURE {group_id: $group_id, month: $month}]->(:CdaExposureTarget {target: $target}) }"
            )
        where_sql = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""
        query = f"""
        MATCH (f:CdaFund {{group_id: $group_id, month: $month}})-[r:HOLDS_POSITION {{group_id: $group_id, month: $month}}]->(a:CdaAsset {{group_id: $group_id, month: $month}})
        OPTIONAL MATCH (a)-[:ISSUED_BY {{group_id: $group_id, month: $month}}]->(i:CdaIssuer {{group_id: $group_id, month: $month}})
        {where_sql}
        WITH f, r, a, i
        ORDER BY abs(coalesce(r.value_market, 0)) DESC
        LIMIT $limit
        RETURN f AS source, r AS rel, a AS target, i AS issuer
        """
        with self._driver() as driver:
            records, _, _ = driver.execute_query(query, **params)
            graph = self._records_to_graph(records)
            self._append_context_edges(driver, graph, resolved_month)
        return {
            "ok": True,
            "success": True,
            "month": resolved_month,
            "group_id": self.group_id,
            "filters": {"fund_cnpj": fund_cnpj, "issuer": issuer, "target": target, "limit": limit},
            **graph,
        }

    def fund_network(self, fund_cnpj: str, *, month: str | None = None, limit: int = 160) -> dict[str, Any]:
        return self.network(month=month, limit=limit, fund_cnpj=fund_cnpj)

    def issuer_crowding(self, *, month: str | None = None, limit: int = 50) -> dict[str, Any]:
        resolved_month = self._resolve_graph_month(month)
        if not resolved_month:
            return {"ok": False, "success": False, "error": "CDA graph is empty.", "rows": []}
        limit = max(5, min(int(limit or 50), 200))
        with self._driver() as driver:
            records, _, _ = driver.execute_query(
                """
                MATCH (f:CdaFund {group_id: $group_id, month: $month})-[r:HOLDS_POSITION {group_id: $group_id, month: $month}]->(:CdaAsset {group_id: $group_id, month: $month})-[:ISSUED_BY {group_id: $group_id, month: $month}]->(i:CdaIssuer {group_id: $group_id, month: $month})
                WHERE i.name <> 'Emissor nao identificado'
                WITH
                    i,
                    count(DISTINCT f) AS fund_count,
                    count(r) AS position_count,
                    sum(coalesce(r.value_market, 0)) AS net_value,
                    sum(abs(coalesce(r.value_market, 0))) AS gross_value,
                    sum(CASE WHEN coalesce(r.value_market, 0) > 0 THEN coalesce(r.value_market, 0) ELSE 0 END) AS long_value,
                    sum(CASE WHEN coalesce(r.value_market, 0) < 0 THEN abs(coalesce(r.value_market, 0)) ELSE 0 END) AS short_value
                RETURN
                    i.id AS issuer_id,
                    i.name AS issuer_name,
                    i.issuer_doc AS issuer_doc,
                    fund_count,
                    position_count,
                    net_value,
                    gross_value,
                    long_value,
                    short_value
                ORDER BY fund_count DESC, gross_value DESC
                LIMIT $limit
                """,
                group_id=self.group_id,
                month=resolved_month,
                limit=limit,
            )
        rows = [record.data() for record in records]
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
        return {"ok": True, "success": True, "month": resolved_month, "rows": rows}

    def money_trails(self, *, month: str | None = None, limit: int = 20) -> dict[str, Any]:
        resolved_month = self._resolve_graph_month(month)
        if not resolved_month:
            return {
                "ok": False,
                "success": False,
                "error": "CDA graph is empty.",
                "layers": [],
                "countries": [],
                "similar_funds": [],
                "bridge_paths": [],
                "explanatory_connections": [],
            }
        limit = max(5, min(int(limit or 20), 80))
        with self._driver() as driver:
            layer_records, _, _ = driver.execute_query(
                """
                MATCH (f:CdaFund {group_id: $group_id, month: $month})
                  -[r:HAS_TARGET_EXPOSURE {group_id: $group_id, month: $month}]
                  ->(t:CdaExposureTarget {group_id: $group_id, month: $month})
                WITH
                  t,
                  count(DISTINCT f) AS fund_count,
                  sum(coalesce(r.long_value, 0)) AS long_value,
                  sum(coalesce(r.short_value, 0)) AS short_value,
                  sum(coalesce(r.net_value, 0)) AS net_value,
                  sum(coalesce(r.gross_value, 0)) AS gross_value,
                  avg(coalesce(r.target_pct_pl, 0)) AS avg_pct_pl,
                  collect(DISTINCT r.top_issuer)[0..5] AS top_issuers,
                  collect(DISTINCT r.top_asset_class)[0..5] AS top_asset_classes
                RETURN
                  t.target AS target,
                  t.target_label AS target_label,
                  t.name AS name,
                  fund_count,
                  long_value,
                  short_value,
                  net_value,
                  gross_value,
                  avg_pct_pl,
                  top_issuers,
                  top_asset_classes
                ORDER BY gross_value DESC
                """,
                group_id=self.group_id,
                month=resolved_month,
            )
            country_records, _, _ = driver.execute_query(
                """
                MATCH (f:CdaFund {group_id: $group_id, month: $month})
                  -[r:HOLDS_POSITION {group_id: $group_id, month: $month}]
                  ->(:CdaAsset {group_id: $group_id, month: $month})
                  -[:LOCATED_IN {group_id: $group_id, month: $month}]
                  ->(c:CdaCountry {group_id: $group_id, month: $month})
                WHERE c.name <> 'Nao informado'
                WITH
                  c,
                  count(DISTINCT f) AS fund_count,
                  count(r) AS position_count,
                  sum(coalesce(r.value_market, 0)) AS net_value,
                  sum(abs(coalesce(r.value_market, 0))) AS gross_value,
                  sum(CASE WHEN coalesce(r.value_market, 0) > 0 THEN coalesce(r.value_market, 0) ELSE 0 END) AS long_value,
                  sum(CASE WHEN coalesce(r.value_market, 0) < 0 THEN abs(coalesce(r.value_market, 0)) ELSE 0 END) AS short_value
                RETURN
                  c.name AS country,
                  c.country_code AS country_code,
                  fund_count,
                  position_count,
                  net_value,
                  gross_value,
                  long_value,
                  short_value
                ORDER BY gross_value DESC
                LIMIT $limit
                """,
                group_id=self.group_id,
                month=resolved_month,
                limit=limit,
            )
            similarity_records, _, _ = driver.execute_query(
                """
                MATCH (f1:CdaFund {group_id: $group_id, month: $month})
                  -[r1:HOLDS_POSITION {group_id: $group_id, month: $month}]
                  ->(:CdaAsset {group_id: $group_id, month: $month})
                  -[:ISSUED_BY {group_id: $group_id, month: $month}]
                  ->(i:CdaIssuer {group_id: $group_id, month: $month})
                  <-[:ISSUED_BY {group_id: $group_id, month: $month}]
                  -(:CdaAsset {group_id: $group_id, month: $month})
                  <-[r2:HOLDS_POSITION {group_id: $group_id, month: $month}]
                  -(f2:CdaFund {group_id: $group_id, month: $month})
                WHERE f1.id < f2.id
                  AND i.name <> 'Emissor nao identificado'
                WITH
                  f1,
                  f2,
                  i,
                  sum(abs(coalesce(r1.value_market, 0))) AS f1_overlap_value,
                  sum(abs(coalesce(r2.value_market, 0))) AS f2_overlap_value
                WITH
                  f1,
                  f2,
                  count(DISTINCT i) AS shared_issuer_count,
                  collect(DISTINCT i.name)[0..6] AS shared_issuers,
                  sum(f1_overlap_value + f2_overlap_value) AS shared_gross_value
                WHERE shared_issuer_count >= 2
                RETURN
                  f1.name AS fund_a,
                  f1.cnpj AS fund_a_cnpj,
                  f1.fund_type AS fund_a_type,
                  f2.name AS fund_b,
                  f2.cnpj AS fund_b_cnpj,
                  f2.fund_type AS fund_b_type,
                  shared_issuer_count,
                  shared_issuers,
                  shared_gross_value,
                  shared_issuer_count * 1000000000000 + shared_gross_value AS similarity_score
                ORDER BY similarity_score DESC, shared_gross_value DESC
                LIMIT $limit
                """,
                group_id=self.group_id,
                month=resolved_month,
                limit=limit,
            )
            bridge_records, _, _ = driver.execute_query(
                """
                MATCH (f:CdaFund {group_id: $group_id, month: $month})
                  -[:HAS_FUND_TYPE {group_id: $group_id, month: $month}]
                  ->(ft:CdaFundType {group_id: $group_id, month: $month})
                MATCH (f)
                  -[r:HAS_TARGET_EXPOSURE {group_id: $group_id, month: $month}]
                  ->(t:CdaExposureTarget {group_id: $group_id, month: $month})
                WITH
                  ft,
                  t,
                  count(DISTINCT f) AS fund_count,
                  sum(coalesce(r.gross_value, 0)) AS gross_value,
                  sum(coalesce(r.net_value, 0)) AS net_value,
                  avg(coalesce(r.target_pct_pl, 0)) AS avg_pct_pl,
                  collect(DISTINCT r.top_issuer)[0..5] AS top_issuers,
                  collect(DISTINCT r.top_asset_class)[0..5] AS top_asset_classes
                RETURN
                  ft.name AS fund_type,
                  t.target AS target,
                  t.target_label AS target_label,
                  fund_count,
                  gross_value,
                  net_value,
                  avg_pct_pl,
                  top_issuers,
                  top_asset_classes
                ORDER BY gross_value DESC
                LIMIT $limit
                """,
                group_id=self.group_id,
                month=resolved_month,
                limit=limit,
            )

        bridge_paths = [self._rank_row(record.data(), index) for index, record in enumerate(bridge_records, start=1)]

        with self._connect_cda() as con:
            activity_layers = self._fetch_activity_layers(con, resolved_month)
            asset_class_activity = self._fetch_asset_class_activity(con, resolved_month, limit=limit)
            fund_quota_breakdown = self._fetch_fund_quota_breakdown(con, resolved_month, limit=limit)
            target_details = self._fetch_target_flow_details(con, resolved_month, limit=min(limit, 12))
            asset_trails = self._fetch_asset_trails(con, resolved_month, limit=min(limit, 18))
            asset_lenses = self._fetch_asset_lenses(con, resolved_month, limit=min(limit, 24))
            option_triangulation = self._fetch_option_triangulation(
                con,
                resolved_month,
                limit=min(max(limit * 2, 36), 80),
            )
            participant_asset_coherence = self._fetch_participant_asset_coherence(
                con,
                resolved_month,
                limit=min(limit, 16),
            )
            portfolio_similarity = self._fetch_portfolio_similarity(
                con,
                resolved_month,
                limit=min(max(limit * 2, 32), 80),
            )
            explanatory_connections = self._fetch_explanatory_connections(con, resolved_month, limit=limit * 2)

        layers = [self._rank_row(record.data(), index) for index, record in enumerate(layer_records, start=1)]
        countries = [self._rank_row(record.data(), index) for index, record in enumerate(country_records, start=1)]
        similar_funds = [self._rank_row(record.data(), index) for index, record in enumerate(similarity_records, start=1)]
        return {
            "ok": True,
            "success": True,
            "month": resolved_month,
            "group_id": self.group_id,
            "layers": layers,
            "countries": countries,
            "activity_layers": activity_layers,
            "asset_class_activity": asset_class_activity,
            "fund_quota_breakdown": fund_quota_breakdown,
            "target_details": target_details,
            "bridge_path_details": {},
            "asset_trails": asset_trails,
            "asset_lenses": asset_lenses,
            "option_triangulation": option_triangulation,
            "participant_asset_coherence": participant_asset_coherence,
            "portfolio_similarity": portfolio_similarity,
            "similar_funds": similar_funds,
            "bridge_paths": bridge_paths,
            "explanatory_connections": explanatory_connections,
            "map": {
                "source": "CVM CDA structured portfolio holdings",
                "layer_metric": "gross_value",
                "direction_metric": "net_value",
                "interpretation": "Camadas positivas indicam valor liquido comprado; negativas indicam exposicao vendida/short no CDA.",
            },
        }

    def bridge_path_detail(
        self,
        *,
        target: str,
        fund_type: str,
        month: str | None = None,
        limit: int = 18,
    ) -> dict[str, Any]:
        resolved_month = self._resolve_graph_month(month)
        cleaned_target = str(target or "").strip()
        cleaned_fund_type = str(fund_type or "").strip()
        if not resolved_month:
            return {"ok": False, "success": False, "error": "CDA graph is empty.", "detail": None}
        if cleaned_target not in CDA_TARGET_SQL or not cleaned_fund_type:
            return {"ok": False, "success": False, "error": "Invalid bridge path.", "detail": None}
        bridge = {
            "target": cleaned_target,
            "target_label": CDA_TARGET_LABELS.get(cleaned_target, cleaned_target),
            "fund_type": cleaned_fund_type,
        }
        with self._connect_cda() as con:
            details = self._fetch_bridge_path_details(
                con,
                resolved_month,
                [bridge],
                limit=max(5, min(int(limit or 18), 30)),
            )
        key = f"{cleaned_target}|{cleaned_fund_type}"
        return {
            "ok": True,
            "success": True,
            "month": resolved_month,
            "key": key,
            "detail": details.get(key) or {**bridge, "funds": [], "issuers": [], "assets": []},
        }

    def asset_trail_detail(
        self,
        *,
        asset_key: str,
        asset_class: str | None = None,
        side: str = "coveted",
        month: str | None = None,
        limit: int = 24,
    ) -> dict[str, Any]:
        resolved_month = self._resolve_graph_month(month)
        cleaned_asset_key = str(asset_key or "").strip()
        cleaned_asset_class = str(asset_class or "").strip()
        cleaned_side = "shorted" if str(side or "").strip().lower() == "shorted" else "coveted"
        if not resolved_month:
            return {"ok": False, "success": False, "error": "CDA graph is empty.", "detail": None}
        if not cleaned_asset_key:
            return {"ok": False, "success": False, "error": "Invalid asset trail.", "detail": None}
        with self._connect_cda() as con:
            detail = self._fetch_asset_trail_detail(
                con,
                resolved_month,
                asset_key=cleaned_asset_key,
                asset_class=cleaned_asset_class or None,
                side=cleaned_side,
                limit=max(5, min(int(limit or 24), 40)),
            )
        return {
            "ok": True,
            "success": True,
            "month": resolved_month,
            "key": self._asset_trail_key(cleaned_asset_key, cleaned_asset_class, cleaned_side),
            "detail": detail,
        }

    def _fetch_activity_layers(self, con: sqlite3.Connection, month: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for target, condition in CDA_TARGET_SQL.items():
            row = con.execute(
                f"""
                SELECT
                    ? AS target,
                    ? AS target_label,
                    COUNT(*) AS holding_count,
                    COUNT(DISTINCT fund_cnpj) AS fund_count,
                    COUNT(DISTINCT NULLIF(issuer_name, '')) AS issuer_count,
                    SUM(COALESCE(value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                    SUM(COALESCE(value_buy, 0)) AS buy_value,
                    SUM(COALESCE(value_sell, 0)) AS sell_value,
                    SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity,
                    SUM(CASE WHEN COALESCE(value_sell, 0) > 0 THEN COALESCE(value_sell, 0) ELSE 0 END) AS reductions_value,
                    MAX(asset_class) AS top_asset_class,
                    MAX(issuer_name) AS top_issuer
                FROM cvm_cda_holdings
                WHERE month = ? AND ({condition})
                """,
                (target, CDA_TARGET_LABELS[target], month),
            ).fetchone()
            if row:
                item = dict(row)
                item["activity_direction"] = self._activity_direction(item.get("reported_activity"))
                rows.append(item)
        rows.sort(key=lambda item: abs(float(item.get("gross_value") or 0)), reverse=True)
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
        return rows

    def _fetch_asset_class_activity(self, con: sqlite3.Connection, month: str, *, limit: int) -> list[dict[str, Any]]:
        rows = [dict(row) for row in con.execute(
            """
            SELECT
                COALESCE(NULLIF(asset_class, ''), 'Outros') AS asset_class,
                COUNT(*) AS holding_count,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(DISTINCT NULLIF(issuer_name, '')) AS issuer_count,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) AS buy_value,
                SUM(COALESCE(value_sell, 0)) AS sell_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity,
                SUM(CASE WHEN COALESCE(value_sell, 0) > COALESCE(value_buy, 0)
                         THEN COALESCE(value_sell, 0) - COALESCE(value_buy, 0)
                         ELSE 0 END) AS net_reduction_value
            FROM cvm_cda_holdings
            WHERE month = ?
            GROUP BY COALESCE(NULLIF(asset_class, ''), 'Outros')
            ORDER BY ABS(SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0))) DESC,
                     SUM(ABS(COALESCE(value_market, 0))) DESC
            LIMIT ?
            """,
            (month, limit),
        ).fetchall()]
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
            row["activity_direction"] = self._activity_direction(row.get("reported_activity"))
        return rows

    def _fetch_fund_quota_breakdown(self, con: sqlite3.Connection, month: str, *, limit: int) -> list[dict[str, Any]]:
        rows = [dict(row) for row in con.execute(
            """
            SELECT
                COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(asset_class, ''), 'Cotas de Fundos') AS asset_class,
                COUNT(*) AS holding_count,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(DISTINCT NULLIF(issuer_name, '')) AS invested_fund_count,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) AS buy_value,
                SUM(COALESCE(value_sell, 0)) AS sell_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity,
                MAX(issuer_name) AS sample_invested_fund
            FROM cvm_cda_holdings
            WHERE month = ? AND is_fund_quota = 1
            GROUP BY COALESCE(NULLIF(fund_type, ''), 'Outros'), COALESCE(NULLIF(asset_class, ''), 'Cotas de Fundos')
            ORDER BY ABS(SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0))) DESC,
                     SUM(ABS(COALESCE(value_market, 0))) DESC
            LIMIT ?
            """,
            (month, limit),
        ).fetchall()]
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
            row["activity_direction"] = self._activity_direction(row.get("reported_activity"))
        return rows

    def _fetch_target_flow_details(self, con: sqlite3.Connection, month: str, *, limit: int) -> dict[str, Any]:
        details: dict[str, Any] = {}
        for target, condition in CDA_TARGET_SQL.items():
            top_buy_funds = [dict(row) for row in con.execute(
                f"""
                SELECT
                    fund_cnpj,
                    MAX(fund_name) AS fund_name,
                    MAX(fund_type) AS fund_type,
                    COUNT(*) AS holding_count,
                    SUM(COALESCE(value_buy, 0)) AS buy_value,
                    SUM(COALESCE(value_sell, 0)) AS sell_value,
                    SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity,
                    SUM(COALESCE(value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(value_market, 0))) AS gross_value
                FROM cvm_cda_holdings
                WHERE month = ? AND ({condition})
                GROUP BY fund_cnpj
                HAVING buy_value > 0 OR sell_value > 0
                ORDER BY buy_value DESC
                LIMIT ?
                """,
                (month, limit),
            ).fetchall()]
            top_sell_funds = [dict(row) for row in con.execute(
                f"""
                SELECT
                    fund_cnpj,
                    MAX(fund_name) AS fund_name,
                    MAX(fund_type) AS fund_type,
                    COUNT(*) AS holding_count,
                    SUM(COALESCE(value_buy, 0)) AS buy_value,
                    SUM(COALESCE(value_sell, 0)) AS sell_value,
                    SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity,
                    SUM(COALESCE(value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(value_market, 0))) AS gross_value
                FROM cvm_cda_holdings
                WHERE month = ? AND ({condition})
                GROUP BY fund_cnpj
                HAVING buy_value > 0 OR sell_value > 0
                ORDER BY sell_value DESC
                LIMIT ?
                """,
                (month, limit),
            ).fetchall()]
            top_assets = [dict(row) for row in con.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(asset_code, ''), NULLIF(asset_desc, ''), NULLIF(issuer_name, ''), 'UNCLASSIFIED') AS asset_key,
                    MAX(asset_desc) AS asset_desc,
                    MAX(issuer_name) AS issuer_name,
                    MAX(asset_class) AS asset_class,
                    COUNT(DISTINCT fund_cnpj) AS fund_count,
                    SUM(COALESCE(value_buy, 0)) AS buy_value,
                    SUM(COALESCE(value_sell, 0)) AS sell_value,
                    SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity,
                    SUM(COALESCE(value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(value_market, 0))) AS gross_value
                FROM cvm_cda_holdings
                WHERE month = ? AND ({condition})
                GROUP BY COALESCE(NULLIF(asset_code, ''), NULLIF(asset_desc, ''), NULLIF(issuer_name, ''), 'UNCLASSIFIED')
                ORDER BY ABS(SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0))) DESC,
                         SUM(ABS(COALESCE(value_market, 0))) DESC
                LIMIT ?
                """,
                (month, limit),
            ).fetchall()]
            details[target] = {
                "target": target,
                "target_label": CDA_TARGET_LABELS[target],
                "top_buy_funds": self._rank_rows(top_buy_funds),
                "top_sell_funds": self._rank_rows(top_sell_funds),
                "top_assets": self._rank_rows(top_assets),
            }
        return details

    def _fetch_asset_trails(self, con: sqlite3.Connection, month: str, *, limit: int) -> dict[str, Any]:
        item_limit = max(6, min(int(limit or 18), 30))

        def clean_rows(rows: list[sqlite3.Row], side: str) -> list[dict[str, Any]]:
            cleaned: list[dict[str, Any]] = []
            for index, row in enumerate(rows, start=1):
                item = dict(row)
                if self._is_generic_asset_text(item.get("asset_key")) or self._is_generic_asset_text(item.get("asset_class")):
                    continue
                item["rank"] = len(cleaned) + 1
                item["side"] = side
                item["trail_key"] = self._asset_trail_key(item.get("asset_key"), item.get("asset_class"), side)
                item["tone"] = "down" if side == "shorted" else "up"
                cleaned.append(item)
                if len(cleaned) >= item_limit:
                    break
            return cleaned

        coveted_rows = con.execute(
            """
            SELECT
                COALESCE(NULLIF(asset_code, ''), NULLIF(asset_desc, ''), NULLIF(issuer_name, ''), 'UNCLASSIFIED') AS asset_key,
                MAX(asset_desc) AS asset_desc,
                MAX(issuer_name) AS issuer_name,
                COALESCE(NULLIF(MAX(asset_class), ''), 'Outros') AS asset_class,
                MAX(country) AS country,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(*) AS holding_count,
                COUNT(DISTINCT COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_type_count,
                group_concat(DISTINCT COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_types,
                SUM(CASE WHEN COALESCE(value_market, 0) > 0 THEN COALESCE(value_market, 0) ELSE 0 END) AS long_value,
                SUM(CASE WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) AS buy_value,
                SUM(COALESCE(value_sell, 0)) AS sell_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings
            WHERE month = ?
              AND COALESCE(value_market, 0) > 0
            GROUP BY
                COALESCE(NULLIF(asset_code, ''), NULLIF(asset_desc, ''), NULLIF(issuer_name, ''), 'UNCLASSIFIED'),
                COALESCE(NULLIF(asset_class, ''), 'Outros')
            HAVING long_value > 0
            ORDER BY long_value DESC,
                     buy_value DESC,
                     fund_count DESC
            LIMIT ?
            """,
            (month, item_limit * 4),
        ).fetchall()
        shorted_rows = con.execute(
            """
            SELECT
                COALESCE(NULLIF(asset_code, ''), NULLIF(asset_desc, ''), NULLIF(issuer_name, ''), 'UNCLASSIFIED') AS asset_key,
                MAX(asset_desc) AS asset_desc,
                MAX(issuer_name) AS issuer_name,
                COALESCE(NULLIF(MAX(asset_class), ''), 'Outros') AS asset_class,
                MAX(country) AS country,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(*) AS holding_count,
                COUNT(DISTINCT COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_type_count,
                group_concat(DISTINCT COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_types,
                SUM(CASE WHEN COALESCE(value_market, 0) > 0 THEN COALESCE(value_market, 0) ELSE 0 END) AS long_value,
                SUM(CASE WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) AS buy_value,
                SUM(COALESCE(value_sell, 0)) AS sell_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings
            WHERE month = ?
              AND (COALESCE(value_market, 0) < 0 OR COALESCE(is_derivative, 0) = 1)
            GROUP BY
                COALESCE(NULLIF(asset_code, ''), NULLIF(asset_desc, ''), NULLIF(issuer_name, ''), 'UNCLASSIFIED'),
                COALESCE(NULLIF(asset_class, ''), 'Outros')
            HAVING short_value > 0 OR gross_value > 0
            ORDER BY short_value DESC,
                     gross_value DESC,
                     sell_value DESC
            LIMIT ?
            """,
            (month, item_limit * 4),
        ).fetchall()
        coveted = clean_rows(coveted_rows, "coveted")
        shorted = clean_rows(shorted_rows, "shorted")
        return {
            "coveted": coveted,
            "shorted": shorted,
            "summary": {
                "coveted_count": len(coveted),
                "shorted_count": len(shorted),
                "metric": "long_value for coveted, short_value for shorted",
            },
        }

    def _fetch_asset_trail_detail(
        self,
        con: sqlite3.Connection,
        month: str,
        *,
        asset_key: str,
        asset_class: str | None,
        side: str,
        limit: int,
    ) -> dict[str, Any]:
        item_limit = max(5, min(int(limit or 24), 40))
        class_filter = "AND COALESCE(NULLIF(h.asset_class, ''), 'Outros') = ?" if asset_class else ""
        side_filter = (
            "AND (COALESCE(h.value_market, 0) < 0 OR COALESCE(h.is_derivative, 0) = 1)"
            if side == "shorted"
            else "AND COALESCE(h.value_market, 0) > 0"
        )
        params: list[Any] = [month, asset_key]
        if asset_class:
            params.append(asset_class)
        params.append(item_limit)
        fund_links = [dict(row) for row in con.execute(
            f"""
            SELECT
                h.fund_cnpj,
                MAX(h.fund_name) AS fund_name,
                COALESCE(NULLIF(MAX(h.fund_type), ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(MAX(h.asset_code), ''), NULLIF(MAX(h.asset_desc), ''), NULLIF(MAX(h.issuer_name), ''), 'UNCLASSIFIED') AS asset_key,
                MAX(h.asset_desc) AS asset_desc,
                MAX(h.issuer_name) AS issuer_name,
                COALESCE(NULLIF(MAX(h.asset_class), ''), 'Outros') AS asset_class,
                MAX(h.country) AS country,
                SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS long_value,
                SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(h.value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0)) AS reported_activity,
                SUM(COALESCE(h.qty_final, 0)) AS qty_final,
                COUNT(*) AS holding_count,
                MAX(fs.pl) AS pl,
                CASE WHEN MAX(fs.pl) != 0 THEN SUM(COALESCE(h.value_market, 0)) / MAX(fs.pl) * 100.0 ELSE NULL END AS pct_pl
            FROM cvm_cda_holdings h
            LEFT JOIN cvm_cda_fund_summary fs
              ON fs.month = h.month AND fs.fund_cnpj = h.fund_cnpj
            WHERE h.month = ?
              AND COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'UNCLASSIFIED') = ?
              {class_filter}
              {side_filter}
            GROUP BY h.fund_cnpj
            ORDER BY
                CASE WHEN ? = 'shorted' THEN SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END)
                     ELSE SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END)
                END DESC,
                SUM(ABS(COALESCE(h.value_market, 0))) DESC
            LIMIT ?
            """,
            [*params[:-1], side, params[-1]],
        ).fetchall()]
        summary = dict(con.execute(
            f"""
            SELECT
                ? AS asset_key,
                COALESCE(NULLIF(MAX(h.asset_class), ''), 'Outros') AS asset_class,
                MAX(h.asset_desc) AS asset_desc,
                MAX(h.issuer_name) AS issuer_name,
                MAX(h.country) AS country,
                COUNT(DISTINCT h.fund_cnpj) AS fund_count,
                COUNT(*) AS holding_count,
                SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS long_value,
                SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(h.value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings h
            WHERE h.month = ?
              AND COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'UNCLASSIFIED') = ?
              {class_filter}
              {side_filter}
            """,
            ([asset_key, month, asset_key, asset_class] if asset_class else [asset_key, month, asset_key]),
        ).fetchone() or {})
        ranked_links = self._rank_rows(fund_links)
        for row in ranked_links:
            row["link_label"] = (
                f"{row.get('fund_name') or row.get('fund_cnpj')} -> {row.get('asset_key')}"
            )
            row["side"] = "shorted" if self._num(row.get("short_value")) > self._num(row.get("long_value")) else "coveted"
        return {
            "asset_key": asset_key,
            "asset_class": asset_class or summary.get("asset_class"),
            "side": side,
            "summary": summary,
            "fund_links": ranked_links,
        }

    def _fetch_asset_lenses(self, con: sqlite3.Connection, month: str, *, limit: int) -> dict[str, Any]:
        item_limit = max(8, min(int(limit or 24), 40))
        labels = self._asset_lens_labels()
        tagged_cte = self._asset_lens_tagged_cte()
        summary_rows = [dict(row) for row in con.execute(
            f"""
            {tagged_cte}
            SELECT
                asset_bucket AS bucket,
                COUNT(DISTINCT asset_key) AS asset_count,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(*) AS holding_count,
                SUM(CASE
                    WHEN asset_bucket IN ('options_call', 'options_put', 'options_unknown') AND option_position_role = 'written' THEN 0
                    WHEN COALESCE(value_market, 0) > 0 THEN COALESCE(value_market, 0)
                    ELSE 0
                END) AS long_value,
                SUM(CASE
                    WHEN asset_bucket IN ('options_call', 'options_put', 'options_unknown') AND option_position_role = 'written' THEN ABS(COALESCE(value_market, 0))
                    WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0))
                    ELSE 0
                END) AS short_value,
                SUM(CASE
                    WHEN asset_bucket IN ('options_call', 'options_put', 'options_unknown') AND option_position_role = 'written' THEN -ABS(COALESCE(value_market, 0))
                    ELSE COALESCE(value_market, 0)
                END) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) AS buy_value,
                SUM(COALESCE(value_sell, 0)) AS sell_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM tagged
            GROUP BY asset_bucket
            HAVING gross_value > 0
            ORDER BY gross_value DESC
            """,
            (month,),
        ).fetchall()]
        bucket_rows: list[dict[str, Any]] = []
        for row in summary_rows:
            bucket = str(row.get("bucket") or "other")
            row["label"] = labels.get(bucket, bucket)
            row["tone"] = "up" if self._num(row.get("reported_activity")) > 0 else "down" if self._num(row.get("reported_activity")) < 0 else "flat"
            bucket_rows.append(row)
        bucket_rows.insert(0, {
            "bucket": "all",
            "label": "Todos",
            "asset_count": sum(int(row.get("asset_count") or 0) for row in summary_rows),
            "fund_count": max([int(row.get("fund_count") or 0) for row in summary_rows] or [0]),
            "holding_count": sum(int(row.get("holding_count") or 0) for row in summary_rows),
            "long_value": sum(self._num(row.get("long_value")) for row in summary_rows),
            "short_value": sum(self._num(row.get("short_value")) for row in summary_rows),
            "net_value": sum(self._num(row.get("net_value")) for row in summary_rows),
            "gross_value": sum(self._num(row.get("gross_value")) for row in summary_rows),
            "buy_value": sum(self._num(row.get("buy_value")) for row in summary_rows),
            "sell_value": sum(self._num(row.get("sell_value")) for row in summary_rows),
            "reported_activity": sum(self._num(row.get("reported_activity")) for row in summary_rows),
            "tone": "flat",
        })

        asset_rows = [dict(row) for row in con.execute(
            f"""
            {tagged_cte}
            , grouped AS (
            SELECT
                asset_bucket AS bucket,
                MAX(option_side) AS option_side,
                MAX(option_position_role) AS option_position_role,
                asset_key,
                MAX(asset_desc) AS asset_desc,
                MAX(issuer_name) AS issuer_name,
                COALESCE(NULLIF(MAX(asset_class), ''), 'Outros') AS asset_class,
                MAX(tp_ativo) AS tp_ativo,
                MAX(tp_aplic) AS tp_aplic,
                MAX(country) AS country,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(*) AS holding_count,
                COUNT(DISTINCT COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_type_count,
                group_concat(DISTINCT COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_types,
                SUM(CASE
                    WHEN asset_bucket IN ('options_call', 'options_put', 'options_unknown') AND option_position_role = 'written' THEN 0
                    WHEN COALESCE(value_market, 0) > 0 THEN COALESCE(value_market, 0)
                    ELSE 0
                END) AS long_value,
                SUM(CASE
                    WHEN asset_bucket IN ('options_call', 'options_put', 'options_unknown') AND option_position_role = 'written' THEN ABS(COALESCE(value_market, 0))
                    WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0))
                    ELSE 0
                END) AS short_value,
                SUM(CASE
                    WHEN asset_bucket IN ('options_call', 'options_put', 'options_unknown') AND option_position_role = 'written' THEN -ABS(COALESCE(value_market, 0))
                    ELSE COALESCE(value_market, 0)
                END) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) AS buy_value,
                SUM(COALESCE(value_sell, 0)) AS sell_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM tagged
            GROUP BY asset_bucket, asset_key, COALESCE(NULLIF(asset_class, ''), 'Outros')
            HAVING gross_value > 0
            ),
            ranked AS (
                SELECT
                    grouped.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY bucket
                        ORDER BY fund_count DESC,
                                 gross_value DESC,
                                 ABS(reported_activity) DESC
                    ) AS bucket_rank
                FROM grouped
            )
            SELECT *
            FROM ranked
            WHERE bucket_rank <= ?
            ORDER BY
                bucket,
                bucket_rank,
                fund_count DESC,
                gross_value DESC,
                ABS(reported_activity) DESC
            """,
            (month, item_limit * 3),
        ).fetchall()]

        per_bucket_count: dict[str, int] = {}
        cleaned_rows: list[dict[str, Any]] = []
        for row in asset_rows:
            bucket = str(row.get("bucket") or "other")
            if bucket not in {"options_call", "options_put", "options_unknown"} and self._is_generic_asset_text(row.get("asset_key")):
                continue
            current_count = per_bucket_count.get(bucket, 0)
            if current_count >= item_limit:
                continue
            per_bucket_count[bucket] = current_count + 1
            row["rank"] = current_count + 1
            row["bucket_label"] = labels.get(bucket, bucket)
            row["display_name"] = row.get("asset_desc") or row.get("issuer_name") or row.get("asset_key")
            row["side"] = "shorted" if self._num(row.get("short_value")) > self._num(row.get("long_value")) else "coveted"
            row["tone"] = "down" if row["side"] == "shorted" else "up"
            row["trail_key"] = self._asset_trail_key(row.get("asset_key"), row.get("asset_class"), row.get("side"))
            row["correlation_score"] = round(
                self._num(row.get("fund_count")) * (abs(self._num(row.get("gross_value"))) / 1_000_000_000.0 + 1.0),
                4,
            )
            cleaned_rows.append(row)

        return {
            "buckets": bucket_rows,
            "rows": cleaned_rows,
            "default_bucket": "equity" if any(row.get("bucket") == "equity" for row in bucket_rows) else "fund_quotas",
            "methodology": (
                "CDA monthly portfolio holdings grouped by inferred asset lens. "
                "Correlation here means fund/asset overlap and crowding, not statistical time-series correlation."
            ),
        }

    def _fetch_option_triangulation(self, con: sqlite3.Connection, month: str, *, limit: int) -> dict[str, Any]:
        item_limit = max(12, min(int(limit or 36), 80))
        option_rows = [dict(row) for row in con.execute(
            """
            SELECT
                h.fund_cnpj,
                MAX(h.fund_name) AS fund_name,
                COALESCE(NULLIF(MAX(h.fund_type), ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'OPCAO SEM TICKER') AS option_key,
                MAX(h.asset_code) AS asset_code,
                MAX(h.asset_desc) AS asset_desc,
                MAX(h.issuer_name) AS issuer_name,
                COALESCE(NULLIF(MAX(h.asset_class), ''), 'Outros') AS asset_class,
                MAX(h.tp_aplic) AS tp_aplic,
                MAX(h.tp_ativo) AS tp_ativo,
                MAX(h.country) AS country,
                SUM(COALESCE(h.value_market, 0)) AS net_value_raw,
                SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                SUM(COALESCE(h.qty_final, 0)) AS qty_final,
                COUNT(*) AS holding_count
            FROM cvm_cda_holdings h
            WHERE h.month = ?
              AND ABS(COALESCE(h.value_market, 0)) > 0
              AND (
                (h.tp_aplic LIKE 'Op%' AND h.tp_aplic NOT LIKE 'Opera%')
                OR h.tp_ativo LIKE 'Op%'
                OR UPPER(h.asset_desc) LIKE 'OPCAO%'
                OR UPPER(h.asset_desc) LIKE 'OPCOES%'
              )
            GROUP BY
                h.fund_cnpj,
                COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'OPCAO SEM TICKER'),
                COALESCE(NULLIF(h.asset_class, ''), 'Outros'),
                h.tp_aplic,
                h.tp_ativo
            """,
            (month,),
        ).fetchall()]
        equity_rows = [dict(row) for row in con.execute(
            """
            SELECT
                h.fund_cnpj,
                MAX(h.fund_name) AS fund_name,
                COALESCE(NULLIF(MAX(h.fund_type), ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'ACAO SEM TICKER') AS equity_key,
                MAX(h.asset_code) AS asset_code,
                MAX(h.asset_desc) AS asset_desc,
                MAX(h.issuer_name) AS issuer_name,
                COALESCE(NULLIF(MAX(h.asset_class), ''), 'Acoes') AS asset_class,
                MAX(h.tp_aplic) AS tp_aplic,
                MAX(h.tp_ativo) AS tp_ativo,
                SUM(COALESCE(h.value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                COUNT(*) AS holding_count
            FROM cvm_cda_holdings h
            WHERE h.month = ?
              AND ABS(COALESCE(h.value_market, 0)) > 0
              AND (
                h.asset_class = 'Acoes'
                OR h.tp_aplic LIKE 'A%'
                OR h.tp_aplic LIKE 'Brazilian Depository Receipt%'
                OR h.tp_ativo LIKE '%BDR%'
                OR h.tp_ativo LIKE '%Fundos de%'
              )
            GROUP BY
                h.fund_cnpj,
                COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'ACAO SEM TICKER')
            """,
            (month,),
        ).fetchall()]

        option_by_key: dict[str, dict[str, Any]] = {}
        option_entries: list[dict[str, Any]] = []
        for row in option_rows:
            option_key = str(row.get("option_key") or "").strip() or "OPCAO SEM TICKER"
            side = self._option_side_from_row(row)
            role = self._option_position_role_from_row(row)
            underlying = self._infer_option_underlying(row)
            gross = abs(self._num(row.get("gross_value")))
            raw_net = self._num(row.get("net_value_raw"))
            holder_value = gross if role != "written" and raw_net >= 0 else 0.0
            writer_value = gross if role == "written" or raw_net < 0 else 0.0
            signed_value = holder_value - writer_value if (holder_value or writer_value) else raw_net
            display = row.get("asset_desc") or row.get("asset_code") or row.get("issuer_name") or option_key
            entry = {
                "fund_cnpj": row.get("fund_cnpj"),
                "fund_name": row.get("fund_name"),
                "fund_type": row.get("fund_type"),
                "option_key": option_key,
                "display_name": display,
                "asset_key": option_key,
                "asset_desc": row.get("asset_desc"),
                "asset_class": row.get("asset_class") or "Opcoes",
                "tp_aplic": row.get("tp_aplic"),
                "tp_ativo": row.get("tp_ativo"),
                "issuer_name": row.get("issuer_name"),
                "option_side": side,
                "option_position_role": role,
                "underlying_key": underlying,
                "gross_value": gross,
                "holder_value": holder_value,
                "writer_value": writer_value,
                "net_value": signed_value,
                "buy_value": self._num(row.get("buy_value")),
                "sell_value": self._num(row.get("sell_value")),
                "qty_final": self._num(row.get("qty_final")),
                "holding_count": int(row.get("holding_count") or 0),
            }
            option_entries.append(entry)
            aggregate = option_by_key.setdefault(option_key, {
                "option_key": option_key,
                "asset_key": option_key,
                "display_name": display,
                "asset_desc": row.get("asset_desc"),
                "asset_class": row.get("asset_class") or "Opcoes",
                "bucket": "options_put" if side == "put" else "options_call" if side == "call" else "options_unknown",
                "bucket_label": "Opcoes put" if side == "put" else "Opcoes call" if side == "call" else "Opcoes sem ticker",
                "option_side": side,
                "option_position_role": role,
                "underlying_key": underlying,
                "funds": set(),
                "fund_types": set(),
                "holder_value": 0.0,
                "writer_value": 0.0,
                "net_value": 0.0,
                "gross_value": 0.0,
                "buy_value": 0.0,
                "sell_value": 0.0,
                "holding_count": 0,
            })
            aggregate["funds"].add(row.get("fund_cnpj"))
            aggregate["fund_types"].add(row.get("fund_type") or "Outros")
            aggregate["holder_value"] += holder_value
            aggregate["writer_value"] += writer_value
            aggregate["net_value"] += signed_value
            aggregate["gross_value"] += gross
            aggregate["buy_value"] += self._num(row.get("buy_value"))
            aggregate["sell_value"] += self._num(row.get("sell_value"))
            aggregate["holding_count"] += int(row.get("holding_count") or 0)
            if not aggregate.get("underlying_key") and underlying:
                aggregate["underlying_key"] = underlying

        equity_by_fund_underlying: dict[str, dict[str, dict[str, Any]]] = {}
        for row in equity_rows:
            underlying = self._infer_equity_underlying(row)
            if not underlying:
                continue
            fund = str(row.get("fund_cnpj") or "").strip()
            if not fund:
                continue
            by_underlying = equity_by_fund_underlying.setdefault(fund, {})
            equity_key = str(row.get("equity_key") or "").strip() or underlying
            current = by_underlying.setdefault(underlying, {
                "fund_cnpj": fund,
                "fund_name": row.get("fund_name"),
                "fund_type": row.get("fund_type"),
                "underlying_key": underlying,
                "equity_key": equity_key,
                "equity_display": row.get("asset_desc") or row.get("asset_code") or equity_key,
                "asset_class": row.get("asset_class") or "Acoes",
                "gross_value": 0.0,
                "net_value": 0.0,
                "buy_value": 0.0,
                "sell_value": 0.0,
                "holding_count": 0,
                "sample_equities": [],
            })
            gross = abs(self._num(row.get("gross_value")))
            current["gross_value"] += gross
            current["net_value"] += self._num(row.get("net_value"))
            current["buy_value"] += self._num(row.get("buy_value"))
            current["sell_value"] += self._num(row.get("sell_value"))
            current["holding_count"] += int(row.get("holding_count") or 0)
            if len(current["sample_equities"]) < 4 and equity_key not in current["sample_equities"]:
                current["sample_equities"].append(equity_key)
            if gross > abs(self._num(current.get("top_equity_gross"))):
                current["equity_key"] = equity_key
                current["equity_display"] = row.get("asset_desc") or row.get("asset_code") or equity_key
                current["top_equity_gross"] = gross

        fund_links: dict[str, dict[str, Any]] = {}
        pair_rows: dict[str, dict[str, Any]] = {}
        underlying_rows: dict[str, dict[str, Any]] = {}
        for option in option_entries:
            underlying = option.get("underlying_key")
            if not underlying:
                continue
            fund = str(option.get("fund_cnpj") or "").strip()
            equity = equity_by_fund_underlying.get(fund, {}).get(str(underlying))
            base = underlying_rows.setdefault(str(underlying), {
                "underlying_key": underlying,
                "funds": set(),
                "option_count": 0,
                "option_gross_value": 0.0,
                "equity_gross_value": 0.0,
                "triangulated_gross_value": 0.0,
                "call_value": 0.0,
                "put_value": 0.0,
                "written_value": 0.0,
                "holder_value": 0.0,
                "sample_options": [],
                "sample_equities": [],
            })
            base["funds"].add(fund)
            base["option_count"] += 1
            base["option_gross_value"] += self._num(option.get("gross_value"))
            base["call_value"] += self._num(option.get("gross_value")) if option.get("option_side") == "call" else 0.0
            base["put_value"] += self._num(option.get("gross_value")) if option.get("option_side") == "put" else 0.0
            base["written_value"] += self._num(option.get("writer_value"))
            base["holder_value"] += self._num(option.get("holder_value"))
            if len(base["sample_options"]) < 5 and option.get("option_key") not in base["sample_options"]:
                base["sample_options"].append(option.get("option_key"))
            if not equity:
                continue
            base["equity_gross_value"] += self._num(equity.get("gross_value"))
            base["triangulated_gross_value"] += min(self._num(option.get("gross_value")), self._num(equity.get("gross_value")))
            for eq in equity.get("sample_equities") or []:
                if len(base["sample_equities"]) < 5 and eq not in base["sample_equities"]:
                    base["sample_equities"].append(eq)
            link_key = self._hash(fund, option.get("option_key"), equity.get("equity_key"), underlying)
            link = fund_links.setdefault(link_key, {
                "fund_cnpj": fund,
                "fund_name": option.get("fund_name"),
                "fund_type": option.get("fund_type"),
                "underlying_key": underlying,
                "option_key": option.get("option_key"),
                "option_display": option.get("display_name"),
                "option_side": option.get("option_side"),
                "option_position_role": option.get("option_position_role"),
                "equity_key": equity.get("equity_key"),
                "equity_display": equity.get("equity_display"),
                "option_gross_value": 0.0,
                "option_net_value": 0.0,
                "equity_gross_value": self._num(equity.get("gross_value")),
                "equity_net_value": self._num(equity.get("net_value")),
                "link_score": 0.0,
            })
            link["option_gross_value"] += self._num(option.get("gross_value"))
            link["option_net_value"] += self._num(option.get("net_value"))
            link["link_score"] = min(link["option_gross_value"], link["equity_gross_value"]) + max(link["option_gross_value"], link["equity_gross_value"]) * 0.08
            pair_key = self._hash(option.get("option_key"), equity.get("equity_key"), underlying)
            pair = pair_rows.setdefault(pair_key, {
                "underlying_key": underlying,
                "option_key": option.get("option_key"),
                "option_display": option.get("display_name"),
                "option_side": option.get("option_side"),
                "option_position_role": option.get("option_position_role"),
                "equity_key": equity.get("equity_key"),
                "equity_display": equity.get("equity_display"),
                "funds": set(),
                "option_gross_value": 0.0,
                "equity_gross_value": 0.0,
                "pair_score": 0.0,
            })
            pair["funds"].add(fund)
            pair["option_gross_value"] += self._num(option.get("gross_value"))
            pair["equity_gross_value"] += self._num(equity.get("gross_value"))
            pair["pair_score"] = min(pair["option_gross_value"], pair["equity_gross_value"]) + len(pair["funds"]) * 1_000_000_000

        option_ranked = []
        for item in option_by_key.values():
            item["fund_count"] = len([fund for fund in item.pop("funds") if fund])
            item["fund_type_count"] = len([fund_type for fund_type in item.pop("fund_types") if fund_type])
            item["long_value"] = item.get("holder_value", 0.0)
            item["short_value"] = item.get("writer_value", 0.0)
            item["correlation_score"] = item["gross_value"] + item["fund_count"] * 1_500_000_000
            option_ranked.append(item)
        option_ranked.sort(key=lambda row: row.get("correlation_score") or 0, reverse=True)
        for index, row in enumerate(option_ranked[:item_limit], start=1):
            row["rank"] = index
            row["trail_key"] = self._asset_trail_key(row.get("asset_key"), row.get("asset_class"), "shorted" if self._num(row.get("short_value")) > self._num(row.get("long_value")) else "coveted")
            row["side"] = "shorted" if self._num(row.get("short_value")) > self._num(row.get("long_value")) else "coveted"
            row["tone"] = "down" if row["side"] == "shorted" else "up"

        underlyings = []
        for item in underlying_rows.values():
            item["fund_count"] = len([fund for fund in item.pop("funds") if fund])
            item["coverage_ratio"] = (
                item["triangulated_gross_value"] / item["option_gross_value"] * 100.0
                if item["option_gross_value"] else 0.0
            )
            item["score"] = item["triangulated_gross_value"] + item["option_gross_value"] * 0.35 + item["fund_count"] * 1_000_000_000
            underlyings.append(item)
        underlyings.sort(key=lambda row: row.get("score") or 0, reverse=True)
        for index, row in enumerate(underlyings[:item_limit], start=1):
            row["rank"] = index

        links = list(fund_links.values())
        links.sort(key=lambda row: row.get("link_score") or 0, reverse=True)
        for index, row in enumerate(links[:item_limit], start=1):
            row["rank"] = index
            row["tone"] = "down" if row.get("option_position_role") == "written" else "up"

        pairs = []
        for item in pair_rows.values():
            item["shared_fund_count"] = len([fund for fund in item.pop("funds") if fund])
            pairs.append(item)
        pairs.sort(key=lambda row: row.get("pair_score") or 0, reverse=True)
        for index, row in enumerate(pairs[:item_limit], start=1):
            row["rank"] = index
            row["tone"] = "down" if row.get("option_position_role") == "written" else "up"

        return {
            "summary": {
                "option_position_count": len(option_entries),
                "option_asset_count": len(option_ranked),
                "underlying_count": len(underlyings),
                "fund_option_equity_link_count": len(links),
                "pair_count": len(pairs),
            },
            "option_rows": option_ranked[:item_limit],
            "underlying_rows": underlyings[:item_limit],
            "fund_option_equity_links": links[:item_limit],
            "asset_pair_rows": pairs[:item_limit],
            "methodology": (
                "Triangulation links option positions to inferred underlyings from option tickers/descriptions "
                "and then to equity/ETF positions held by the same fund. It is a portfolio-overlap screen, not price correlation."
            ),
        }

    def _fetch_portfolio_similarity(self, con: sqlite3.Connection, month: str, *, limit: int) -> dict[str, Any]:
        labels = self._asset_lens_labels()
        tagged_cte = self._asset_lens_tagged_cte()
        item_limit = max(12, min(int(limit or 40), 80))
        base_candidate_limit = max(110, min(item_limit * 2, 180))
        focus_candidate_limit = max(28, min(item_limit, 72))
        niche_candidate_limit = max(18, min(item_limit // 2, 42))
        rows = [dict(row) for row in con.execute(
            f"""
            {tagged_cte},
            fund_stats AS (
                SELECT
                    fund_cnpj,
                    MAX(COALESCE(NULLIF(fund_name, ''), fund_cnpj)) AS fund_name,
                    MAX(COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_type,
                    COUNT(*) AS holding_count,
                    SUM(ABS(COALESCE(value_market, 0))) AS gross_total,
                    SUM(COALESCE(value_market, 0)) AS net_total,
                    SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS activity_total,
                    SUM(CASE WHEN asset_bucket LIKE 'options_%' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS option_gross,
                    SUM(CASE WHEN asset_bucket = 'equity' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS equity_gross,
                    SUM(CASE WHEN asset_bucket IN ('public_bonds', 'private_credit', 'fund_fixed_income', 'cash_if') THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS fixed_income_gross,
                    SUM(CASE WHEN asset_bucket = 'derivatives' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS derivatives_gross,
                    SUM(CASE WHEN asset_bucket = 'private_credit' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS private_credit_gross,
                    SUM(CASE WHEN asset_bucket = 'public_bonds' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS public_bonds_gross,
                    SUM(CASE WHEN asset_bucket IN ('fund_quotas', 'fund_fixed_income', 'fund_multimarket', 'fund_equity', 'fund_real_estate', 'fund_structured') THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS fund_quota_gross,
                    SUM(CASE WHEN asset_bucket = 'foreign' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS foreign_gross,
                    COUNT(DISTINCT asset_bucket) AS bucket_count,
                    (
                        SUM(ABS(COALESCE(value_market, 0)))
                        + SUM(CASE WHEN asset_bucket LIKE 'options_%' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) * 7.0
                        + SUM(CASE WHEN asset_bucket = 'equity' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) * 2.5
                        + SUM(CASE WHEN asset_bucket IN ('public_bonds', 'private_credit', 'fund_fixed_income', 'cash_if') THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) * 1.1
                        + SUM(CASE WHEN asset_bucket = 'derivatives' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) * 5.0
                        + SUM(CASE WHEN asset_bucket = 'foreign' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) * 2.2
                        + ABS(SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0))) * 2.5
                    ) AS composite_score
                FROM tagged
                WHERE COALESCE(NULLIF(fund_cnpj, ''), '') <> ''
                GROUP BY fund_cnpj
                HAVING gross_total > 0
            ),
            candidate_funds AS (
                SELECT * FROM (
                    SELECT * FROM fund_stats ORDER BY composite_score DESC, gross_total DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE option_gross > 0 ORDER BY option_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE derivatives_gross > 0 ORDER BY derivatives_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE equity_gross > 0 ORDER BY equity_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE private_credit_gross > 0 ORDER BY private_credit_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE public_bonds_gross > 0 ORDER BY public_bonds_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE fund_quota_gross > 0 ORDER BY fund_quota_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE foreign_gross > 0 ORDER BY foreign_gross DESC LIMIT ?
                )
                ORDER BY composite_score DESC, gross_total DESC
                LIMIT ?
            )
            SELECT
                t.*,
                cf.fund_name AS candidate_fund_name,
                cf.fund_type AS candidate_fund_type,
                cf.gross_total,
                cf.net_total,
                cf.activity_total,
                cf.option_gross,
                cf.equity_gross,
                cf.fixed_income_gross,
                cf.derivatives_gross,
                cf.private_credit_gross,
                cf.public_bonds_gross,
                cf.fund_quota_gross,
                cf.foreign_gross,
                cf.bucket_count
            FROM tagged t
            JOIN candidate_funds cf ON cf.fund_cnpj = t.fund_cnpj
            WHERE ABS(COALESCE(t.value_market, 0)) > 0
               OR ABS(COALESCE(t.value_buy, 0)) + ABS(COALESCE(t.value_sell, 0)) > 0
            ORDER BY cf.composite_score DESC, cf.gross_total DESC, ABS(COALESCE(t.value_market, 0)) DESC
            """,
            (
                month,
                base_candidate_limit,
                focus_candidate_limit,
                focus_candidate_limit,
                focus_candidate_limit,
                niche_candidate_limit,
                niche_candidate_limit,
                focus_candidate_limit,
                niche_candidate_limit,
                base_candidate_limit + focus_candidate_limit * 4,
            ),
        ).fetchall()]

        funds: dict[str, dict[str, Any]] = {}
        feature_info: dict[str, dict[str, Any]] = {}

        def clean_key(value: Any) -> str:
            return re.sub(r"\s+", " ", str(value or "").strip())[:120]

        def add_feature(
            fund: dict[str, Any],
            kind: str,
            key: Any,
            label: str,
            weight: float,
            *,
            bucket: str = "",
        ) -> None:
            if weight <= 0:
                return
            clean = clean_key(key)
            if not clean:
                return
            feature_id = f"{kind}:{clean.upper()}"
            fund["features"][feature_id] = fund["features"].get(feature_id, 0.0) + float(weight)
            if feature_id not in feature_info:
                feature_info[feature_id] = {
                    "feature_id": feature_id,
                    "feature_type": kind,
                    "feature_key": clean,
                    "label": label or clean,
                    "bucket": bucket,
                }

        def get_fund(row: dict[str, Any]) -> dict[str, Any]:
            cnpj = str(row.get("fund_cnpj") or "").strip()
            if cnpj not in funds:
                funds[cnpj] = {
                    "fund_cnpj": cnpj,
                    "fund_name": row.get("candidate_fund_name") or row.get("fund_name") or cnpj,
                    "fund_type": row.get("candidate_fund_type") or row.get("fund_type") or "Outros",
                    "gross_total": self._num(row.get("gross_total")),
                    "net_total": self._num(row.get("net_total")),
                    "activity_total": self._num(row.get("activity_total")),
                    "holding_count": 0,
                    "features": {},
                    "bucket_gross": {},
                    "asset_gross": {},
                    "issuer_gross": {},
                    "option_underlyings": {},
                    "equity_underlyings": {},
                    "structures": [],
                }
            return funds[cnpj]

        for row in rows:
            fund = get_fund(row)
            bucket = str(row.get("asset_bucket") or "other")
            bucket_label = labels.get(bucket, bucket)
            value_market = self._num(row.get("value_market"))
            activity = abs(self._num(row.get("value_buy"))) + abs(self._num(row.get("value_sell")))
            gross = abs(value_market) if abs(value_market) > 0 else activity * 0.45
            if gross <= 0:
                continue
            fund["holding_count"] += 1
            fund["bucket_gross"][bucket] = fund["bucket_gross"].get(bucket, 0.0) + gross
            asset_key = clean_key(row.get("asset_key") or row.get("asset_code") or row.get("asset_desc") or row.get("issuer_name"))
            issuer = clean_key(row.get("issuer_name"))
            issuer_doc = clean_key(row.get("issuer_doc") or row.get("risk_issuer"))
            asset_class = clean_key(row.get("asset_class"))
            maturity_bucket = clean_key(row.get("maturity_bucket"))
            country = clean_key(row.get("country") or row.get("country_code"))
            market = clean_key(row.get("market") or row.get("tp_negoc"))
            explanatory_bucket = bucket not in {"confidential", "other"}
            net_activity = self._num(row.get("value_buy")) - self._num(row.get("value_sell"))

            if explanatory_bucket:
                add_feature(fund, "bucket", bucket, bucket_label, gross * 0.55, bucket=bucket)
            if explanatory_bucket and asset_class and not self._is_generic_asset_text(asset_class) and asset_class.lower() not in {"confidencial", "outros"}:
                add_feature(fund, "asset_class", asset_class, asset_class, gross * 0.32, bucket=bucket)
            if explanatory_bucket and issuer and not self._is_generic_asset_text(issuer):
                fund["issuer_gross"][issuer] = fund["issuer_gross"].get(issuer, 0.0) + gross
                add_feature(fund, "issuer", issuer, issuer, gross * 0.9, bucket=bucket)
            if explanatory_bucket and issuer_doc and not self._is_generic_asset_text(issuer_doc):
                add_feature(fund, "issuer_doc", issuer_doc, issuer or issuer_doc, gross * 0.72, bucket=bucket)
            if explanatory_bucket and asset_key and not self._is_generic_asset_text(asset_key):
                fund["asset_gross"][asset_key] = fund["asset_gross"].get(asset_key, 0.0) + gross
                asset_weight = 1.35 if bucket in {"equity", "private_credit", "public_bonds", "fund_quotas"} else 1.15
                if bucket.startswith("options_"):
                    asset_weight = 1.85
                add_feature(fund, "asset", f"{bucket}|{asset_key}", asset_key, gross * asset_weight, bucket=bucket)
            if explanatory_bucket and country and country.lower() not in {"nao informado", "não informado", "brasil", "bra", "br"}:
                add_feature(fund, "country", country, country, gross * 0.46, bucket=bucket)
            if explanatory_bucket and market and market.lower() not in {"nao informado", "não informado", "sem mercado"}:
                add_feature(fund, "market", f"{bucket}|{market}", f"{bucket_label} / {market}", gross * 0.34, bucket=bucket)
            if explanatory_bucket and abs(net_activity) > 0:
                direction = "compra" if net_activity > 0 else "venda"
                add_feature(fund, "activity_direction", f"{bucket}|{direction}", f"{bucket_label} com {direction}", abs(net_activity) * 0.95, bucket=bucket)
            if maturity_bucket and bucket in {"public_bonds", "private_credit", "cash_if"} and maturity_bucket.lower() not in {"sem vencimento", "nao informado", "não informado"}:
                add_feature(
                    fund,
                    "fixed_income_maturity",
                    f"{bucket}|{maturity_bucket}",
                    f"{bucket_label} / {maturity_bucket}",
                    gross * 0.82,
                    bucket=bucket,
                )
            maturity_date = clean_key(row.get("maturity_date"))
            maturity_year = str(maturity_date)[:4] if re.match(r"^\d{4}", str(maturity_date or "")) else ""
            if maturity_year and bucket in {"public_bonds", "private_credit", "cash_if"}:
                add_feature(
                    fund,
                    "fixed_income_year",
                    f"{bucket}|{maturity_year}",
                    f"{bucket_label} venc. {maturity_year}",
                    gross * 0.72,
                    bucket=bucket,
                )

            if bucket.startswith("options_"):
                underlying = self._infer_option_underlying(row)
                if underlying:
                    side = self._option_side_from_row(row)
                    role = self._option_position_role_from_row(row)
                    option_map = fund["option_underlyings"].setdefault(underlying, {})
                    option_map[f"{side}_{role}"] = option_map.get(f"{side}_{role}", 0.0) + gross
                    option_map["gross"] = option_map.get("gross", 0.0) + gross
                    add_feature(fund, "option_underlying", underlying, f"Opcao sobre {underlying}", gross * 2.1, bucket=bucket)
                    add_feature(fund, "option_leg", f"{underlying}|{side}|{role}", f"{underlying} {side}/{role}", gross * 2.5, bucket=bucket)
            elif bucket == "equity":
                underlying = self._infer_equity_underlying(row)
                if underlying:
                    fund["equity_underlyings"][underlying] = fund["equity_underlyings"].get(underlying, 0.0) + gross
                    add_feature(fund, "equity_underlying", underlying, f"Acao/ETF {underlying}", gross * 1.8, bucket=bucket)

        structure_stats: dict[str, dict[str, Any]] = {}

        def add_structure(
            fund: dict[str, Any],
            key: str,
            label: str,
            value: float,
            *,
            score: float,
            underlyings: list[str] | None = None,
            detail: str = "",
        ) -> None:
            if value <= 0:
                return
            structure = {
                "structure_key": key,
                "label": label,
                "value": value,
                "score": score,
                "underlyings": underlyings or [],
                "detail": detail,
            }
            fund["structures"].append(structure)
            add_feature(fund, "structure", key, label, max(value, fund.get("gross_total") or 0) * max(score, 0.08) * 1.7)
            stats = structure_stats.setdefault(key, {
                "structure_key": key,
                "label": label,
                "fund_count": 0,
                "gross_value": 0.0,
                "score_sum": 0.0,
                "sample_funds": [],
                "sample_underlyings": [],
            })
            stats["fund_count"] += 1
            stats["gross_value"] += float(value or 0)
            stats["score_sum"] += float(score or 0)
            if len(stats["sample_funds"]) < 5:
                stats["sample_funds"].append(fund.get("fund_name"))
            for underlying in underlyings or []:
                if underlying and underlying not in stats["sample_underlyings"] and len(stats["sample_underlyings"]) < 8:
                    stats["sample_underlyings"].append(underlying)

        for fund in funds.values():
            gross_total = max(self._num(fund.get("gross_total")), 1.0)
            bucket_gross = fund.get("bucket_gross") or {}
            fixed_income = sum(bucket_gross.get(key, 0.0) for key in ("public_bonds", "private_credit", "fund_fixed_income", "cash_if"))
            fund_quota = sum(bucket_gross.get(key, 0.0) for key in ("fund_quotas", "fund_fixed_income", "fund_multimarket", "fund_equity", "fund_real_estate", "fund_structured"))
            option_total = sum(value.get("gross", 0.0) for value in (fund.get("option_underlyings") or {}).values())
            equity_total = sum((fund.get("equity_underlyings") or {}).values())
            derivative_total = bucket_gross.get("derivatives", 0.0)
            private_credit = bucket_gross.get("private_credit", 0.0)
            public_bonds = bucket_gross.get("public_bonds", 0.0)
            cash_if = bucket_gross.get("cash_if", 0.0)
            foreign_total = bucket_gross.get("foreign", 0.0)
            option_holder_total = 0.0
            option_writer_total = 0.0

            covered: list[str] = []
            protected: list[str] = []
            collar: list[str] = []
            synthetic: list[str] = []
            for underlying, option_map in (fund.get("option_underlyings") or {}).items():
                equity_value = (fund.get("equity_underlyings") or {}).get(underlying, 0.0)
                call_written = option_map.get("call_written", 0.0)
                put_holder = option_map.get("put_holder", 0.0)
                call_holder = option_map.get("call_holder", 0.0)
                put_written = option_map.get("put_written", 0.0)
                option_holder_total += call_holder + put_holder
                option_writer_total += call_written + put_written
                if equity_value > 0 and call_written > 0:
                    covered.append(underlying)
                if equity_value > 0 and put_holder > 0:
                    protected.append(underlying)
                if equity_value > 0 and call_written > 0 and put_holder > 0:
                    collar.append(underlying)
                if call_holder > 0 and put_written > 0:
                    synthetic.append(underlying)

            if collar:
                value = sum((fund["option_underlyings"][u].get("call_written", 0.0) + fund["option_underlyings"][u].get("put_holder", 0.0) + fund["equity_underlyings"].get(u, 0.0)) for u in collar)
                add_structure(fund, "equity_collar", "Collar acao + call lancada + put comprada", value, score=min(value / gross_total, 1.0), underlyings=collar[:6])
            if covered:
                value = sum((fund["option_underlyings"][u].get("call_written", 0.0) + fund["equity_underlyings"].get(u, 0.0)) for u in covered)
                add_structure(fund, "covered_call", "Acao com call lancada", value, score=min(value / gross_total, 1.0), underlyings=covered[:6])
            if protected:
                value = sum((fund["option_underlyings"][u].get("put_holder", 0.0) + fund["equity_underlyings"].get(u, 0.0)) for u in protected)
                add_structure(fund, "protective_put", "Acao com put comprada", value, score=min(value / gross_total, 1.0), underlyings=protected[:6])
            if synthetic:
                value = sum((fund["option_underlyings"][u].get("call_holder", 0.0) + fund["option_underlyings"][u].get("put_written", 0.0)) for u in synthetic)
                add_structure(fund, "synthetic_long_options", "Call comprada + put lancada", value, score=min(value / gross_total, 1.0), underlyings=synthetic[:6])
            if option_total / gross_total >= 0.015 and len(fund.get("option_underlyings") or {}) >= 3:
                add_structure(
                    fund,
                    "options_overlay_basket",
                    "Overlay diversificado de opcoes",
                    option_total,
                    score=min(option_total / gross_total, 1.0),
                    underlyings=list((fund.get("option_underlyings") or {}).keys())[:8],
                    detail="Carteira com opcoes em varios subjacentes.",
                )
            if option_writer_total > option_holder_total * 1.25 and option_writer_total / gross_total >= 0.002:
                add_structure(
                    fund,
                    "short_vol_options_overlay",
                    "Overlay vendedor de volatilidade",
                    option_writer_total,
                    score=min(option_writer_total / gross_total, 1.0),
                    underlyings=list((fund.get("option_underlyings") or {}).keys())[:8],
                )
            if option_holder_total > option_writer_total * 1.25 and option_holder_total / gross_total >= 0.002:
                add_structure(
                    fund,
                    "long_optionality_overlay",
                    "Overlay comprador de opcionalidade",
                    option_holder_total,
                    score=min(option_holder_total / gross_total, 1.0),
                    underlyings=list((fund.get("option_underlyings") or {}).keys())[:8],
                )
            if fixed_income / gross_total >= 0.55 and derivative_total / gross_total >= 0.003:
                add_structure(fund, "rates_hedged_fixed_income", "Renda fixa com overlay de derivativos", fixed_income + derivative_total, score=min((fixed_income + derivative_total) / gross_total, 1.0))
            if fixed_income / gross_total >= 0.65 and private_credit / gross_total >= 0.08:
                add_structure(fund, "credit_carry_core", "Nucleo renda fixa + credito privado", fixed_income, score=min(fixed_income / gross_total, 1.0))
            if public_bonds / gross_total >= 0.35 and private_credit / gross_total >= 0.08:
                add_structure(fund, "public_private_credit_barbell", "Barbell titulo publico + credito privado", public_bonds + private_credit, score=min((public_bonds + private_credit) / gross_total, 1.0))
            if (public_bonds + cash_if) / gross_total >= 0.7:
                add_structure(fund, "cash_duration_core", "Caixa/duration em titulos publicos", public_bonds + cash_if, score=min((public_bonds + cash_if) / gross_total, 1.0))
            if private_credit / gross_total >= 0.12 and cash_if / gross_total >= 0.1:
                add_structure(fund, "credit_liquidity_sleeve", "Credito privado com colchao de liquidez", private_credit + cash_if, score=min((private_credit + cash_if) / gross_total, 1.0))
            if fund_quota / gross_total >= 0.45:
                add_structure(fund, "fund_allocator", "Alocador em cotas de fundos", fund_quota, score=min(fund_quota / gross_total, 1.0))
            if equity_total / gross_total >= 0.15 and option_total / gross_total >= 0.005:
                add_structure(fund, "equity_options_overlay", "Acoes com overlay de opcoes", equity_total + option_total, score=min((equity_total + option_total) / gross_total, 1.0), underlyings=list((fund.get("equity_underlyings") or {}).keys())[:8])
            if equity_total / gross_total >= 0.12 and derivative_total / gross_total >= 0.006:
                add_structure(fund, "equity_derivatives_overlay", "Acoes com overlay de derivativos", equity_total + derivative_total, score=min((equity_total + derivative_total) / gross_total, 1.0), underlyings=list((fund.get("equity_underlyings") or {}).keys())[:8])
            if foreign_total / gross_total >= 0.08 and option_total / gross_total >= 0.003:
                add_structure(fund, "foreign_options_overlay", "Exterior/BDR com overlay de opcoes", foreign_total + option_total, score=min((foreign_total + option_total) / gross_total, 1.0), underlyings=list((fund.get("option_underlyings") or {}).keys())[:8])
            if fund_quota / gross_total >= 0.25 and derivative_total / gross_total >= 0.004:
                add_structure(fund, "fund_allocator_with_derivatives", "Cotas de fundos com overlay de derivativos", fund_quota + derivative_total, score=min((fund_quota + derivative_total) / gross_total, 1.0))

        feature_to_funds: dict[str, dict[str, float]] = {}
        norms: dict[str, float] = {}
        for cnpj, fund in funds.items():
            gross_total = max(self._num(fund.get("gross_total")), 1.0)
            norm_sq = 0.0
            for feature_id, raw_weight in (fund.get("features") or {}).items():
                info = feature_info.get(feature_id, {})
                kind = info.get("feature_type")
                normalized = max(float(raw_weight or 0) / gross_total, 0.0)
                if kind in {"asset", "option_leg", "option_underlying", "equity_underlying", "structure"}:
                    weight = math.sqrt(min(normalized, 4.0))
                elif kind in {"issuer", "issuer_doc", "fixed_income_maturity", "fixed_income_year"}:
                    weight = math.sqrt(min(normalized, 2.2)) * 0.85
                elif kind in {"activity_direction", "country", "market"}:
                    weight = math.sqrt(min(normalized, 1.8)) * 0.7
                else:
                    weight = math.sqrt(min(normalized, 1.3)) * 0.55
                if weight <= 0.00001:
                    continue
                feature_to_funds.setdefault(feature_id, {})[cnpj] = weight
                norm_sq += weight * weight
            norms[cnpj] = math.sqrt(norm_sq) if norm_sq > 0 else 1.0

        pair_stats: dict[tuple[str, str], dict[str, Any]] = {}
        max_feature_funds = max(42, min((base_candidate_limit + focus_candidate_limit * 4) // 4, 78))
        for feature_id, holdings in feature_to_funds.items():
            if len(holdings) < 2:
                continue
            info = feature_info.get(feature_id, {})
            items = sorted(holdings.items(), key=lambda item: item[1], reverse=True)
            if len(items) > max_feature_funds:
                if info.get("feature_type") not in {"structure", "option_leg", "option_underlying", "equity_underlying", "fixed_income_maturity", "fixed_income_year", "activity_direction", "issuer_doc", "country"}:
                    continue
                items = items[:max_feature_funds]
            for left_index in range(len(items)):
                left_cnpj, left_weight = items[left_index]
                for right_cnpj, right_weight in items[left_index + 1:]:
                    key = (left_cnpj, right_cnpj) if left_cnpj < right_cnpj else (right_cnpj, left_cnpj)
                    contribution = left_weight * right_weight
                    if contribution <= 0.000001:
                        continue
                    stat = pair_stats.setdefault(key, {"dot": 0.0, "features": []})
                    stat["dot"] += contribution
                    if len(stat["features"]) < 18:
                        stat["features"].append({
                            "feature_id": feature_id,
                            "label": info.get("label") or feature_id,
                            "feature_type": info.get("feature_type") or "",
                            "bucket": info.get("bucket") or "",
                            "contribution": contribution,
                        })

        pair_rows: list[dict[str, Any]] = []
        for (left_cnpj, right_cnpj), stat in pair_stats.items():
            left = funds.get(left_cnpj)
            right = funds.get(right_cnpj)
            if not left or not right:
                continue
            denominator = norms.get(left_cnpj, 1.0) * norms.get(right_cnpj, 1.0)
            score = stat["dot"] / denominator if denominator else 0.0
            if score < 0.18:
                continue
            features = sorted(stat.get("features") or [], key=lambda item: item.get("contribution") or 0, reverse=True)
            shared_structures = [feature.get("label") for feature in features if feature.get("feature_type") == "structure"][:5]
            shared_options = [feature.get("label") for feature in features if feature.get("feature_type") in {"option_leg", "option_underlying"}][:5]
            shared_fixed_income = [feature.get("label") for feature in features if feature.get("feature_type") in {"fixed_income_maturity", "fixed_income_year"}][:5]
            shared_activity = [feature.get("label") for feature in features if feature.get("feature_type") == "activity_direction"][:5]
            shared_macro = [feature.get("label") for feature in features if feature.get("feature_type") in {"country", "market"}][:5]
            shared_assets = [feature.get("label") for feature in features if feature.get("feature_type") in {"asset", "issuer", "equity_underlying"}][:7]
            specific_feature_count = len([
                feature for feature in features
                if feature.get("feature_type") in {
                    "asset",
                    "issuer",
                    "issuer_doc",
                    "equity_underlying",
                    "option_leg",
                    "option_underlying",
                    "fixed_income_maturity",
                    "fixed_income_year",
                    "activity_direction",
                    "country",
                    "market",
                    "structure",
                }
            ])
            if specific_feature_count < 2:
                continue
            left_structures = sorted(left.get("structures") or [], key=lambda item: item.get("score") or 0, reverse=True)[:4]
            right_structures = sorted(right.get("structures") or [], key=lambda item: item.get("score") or 0, reverse=True)[:4]
            if shared_options:
                profile_label = "opcoes + ativo-base"
            elif shared_fixed_income:
                profile_label = "renda fixa/duration"
            elif shared_activity:
                profile_label = "atividade semelhante"
            elif shared_macro:
                profile_label = "exposicao geografica/mercado"
            elif shared_structures:
                profile_label = "estrutura semelhante"
            else:
                profile_label = "carteira sobreposta"
            pair_rows.append({
                "fund_a": left.get("fund_name"),
                "fund_a_cnpj": left_cnpj,
                "fund_a_type": left.get("fund_type"),
                "fund_b": right.get("fund_name"),
                "fund_b_cnpj": right_cnpj,
                "fund_b_type": right.get("fund_type"),
                "similarity_score": score,
                "similarity_pct": score * 100,
                "profile_label": profile_label,
                "shared_feature_count": len(features),
                "shared_factors": features[:8],
                "shared_structures": shared_structures,
                "shared_options": shared_options,
                "shared_fixed_income": shared_fixed_income,
                "shared_activity": shared_activity,
                "shared_macro": shared_macro,
                "shared_assets": shared_assets,
                "fund_a_structures": left_structures,
                "fund_b_structures": right_structures,
                "fund_a_gross": left.get("gross_total"),
                "fund_b_gross": right.get("gross_total"),
                "explanation": (
                    f"Similaridade de {score * 100:.1f}% por {profile_label}; fatores principais: "
                    f"{', '.join(str(feature.get('label')) for feature in features[:4])}."
                ),
            })
        pair_rows.sort(key=lambda row: (row.get("similarity_score") or 0, row.get("shared_feature_count") or 0), reverse=True)

        structure_rows = []
        for item in structure_stats.values():
            avg_score = item["score_sum"] / item["fund_count"] if item["fund_count"] else 0
            structure_rows.append({
                **item,
                "avg_score": avg_score,
                "avg_score_pct": avg_score * 100,
            })
        structure_rows.sort(key=lambda row: (row.get("fund_count") or 0, row.get("gross_value") or 0), reverse=True)

        factor_rows = []
        for feature_id, holdings in feature_to_funds.items():
            if len(holdings) < 2:
                continue
            info = feature_info.get(feature_id, {})
            gross_proxy = sum(self._num(funds.get(cnpj, {}).get("gross_total")) * min(weight, 1.0) for cnpj, weight in holdings.items())
            factor_rows.append({
                **info,
                "fund_count": len(holdings),
                "gross_proxy": gross_proxy,
                "avg_weight": sum(holdings.values()) / len(holdings),
                "sample_funds": [funds.get(cnpj, {}).get("fund_name") for cnpj, _ in sorted(holdings.items(), key=lambda item: item[1], reverse=True)[:5]],
            })
        factor_rows.sort(key=lambda row: (row.get("fund_count") or 0, row.get("gross_proxy") or 0), reverse=True)

        profile_rows = []
        for fund in funds.values():
            structures = sorted(fund.get("structures") or [], key=lambda item: item.get("score") or 0, reverse=True)
            if not structures:
                continue
            top_buckets = sorted((fund.get("bucket_gross") or {}).items(), key=lambda item: item[1], reverse=True)[:5]
            profile_rows.append({
                "fund_cnpj": fund.get("fund_cnpj"),
                "fund_name": fund.get("fund_name"),
                "fund_type": fund.get("fund_type"),
                "gross_total": fund.get("gross_total"),
                "net_total": fund.get("net_total"),
                "activity_total": fund.get("activity_total"),
                "structure_count": len(structures),
                "structures": structures[:5],
                "top_buckets": [
                    {"bucket": key, "bucket_label": labels.get(key, key), "gross_value": value, "share_pct": value / max(self._num(fund.get("gross_total")), 1.0) * 100}
                    for key, value in top_buckets
                ],
            })
        profile_rows.sort(key=lambda row: (row.get("structure_count") or 0, row.get("gross_total") or 0), reverse=True)

        return {
            "pairs": self._rank_rows(pair_rows[:item_limit]),
            "structures": self._rank_rows(structure_rows[:item_limit]),
            "factors": self._rank_rows(factor_rows[:item_limit]),
            "fund_profiles": self._rank_rows(profile_rows[:item_limit]),
            "summary": {
                "candidate_fund_count": len(funds),
                "pair_count": len(pair_rows),
                "structure_count": len(structure_rows),
                "factor_count": len(factor_rows),
                "feature_count": len(feature_to_funds),
                "month": month,
            },
            "methodology": (
                "Portfolio profile similarity builds sparse vectors from CDA holdings: asset buckets, issuers, "
                "specific assets, option underlyings/legs, fixed-income maturities and detected structures. "
                "Pairs are ranked by cosine similarity over normalized portfolio features; it is a holdings-overlap "
                "screen, not return correlation or causal inference."
            ),
        }

    def _fetch_participant_asset_coherence(self, con: sqlite3.Connection, month: str, *, limit: int) -> dict[str, Any]:
        participants = self._read_b3_participant_trends()
        labels = self._asset_lens_labels()
        tagged_cte = self._asset_lens_tagged_cte()
        bucket_rows = [dict(row) for row in con.execute(
            f"""
            {tagged_cte}
            SELECT
                asset_bucket AS bucket,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(DISTINCT asset_key) AS asset_count,
                SUM(CASE WHEN COALESCE(value_market, 0) > 0 THEN COALESCE(value_market, 0) ELSE 0 END) AS long_value,
                SUM(CASE WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) AS buy_value,
                SUM(COALESCE(value_sell, 0)) AS sell_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity,
                group_concat(DISTINCT asset_key) AS sample_assets
            FROM tagged
            GROUP BY asset_bucket
            HAVING gross_value > 0
            """,
            (month,),
        ).fetchall()]
        focus_buckets = {
            "equity",
            "fund_quotas",
            "fund_equity",
            "fund_multimarket",
            "fund_real_estate",
            "fund_structured",
            "options_call",
            "options_put",
            "options_unknown",
            "derivatives",
            "foreign",
        }
        bucket_rows = [row for row in bucket_rows if row.get("bucket") in focus_buckets]
        rows: list[dict[str, Any]] = []
        for participant in participants:
            participant_flow = self._num(participant.get("rolling_21d_net_flow_brl"))
            if abs(participant_flow) < 1:
                continue
            for bucket in bucket_rows:
                activity = self._num(bucket.get("reported_activity"))
                if abs(activity) < 1:
                    continue
                same_direction = participant_flow * activity > 0
                bucket_key = str(bucket.get("bucket") or "other")
                score = abs(participant_flow) * (abs(activity) + abs(self._num(bucket.get("net_value"))) * 0.15)
                relationship = "coerente" if same_direction else "divergente"
                participant_direction = "entrada" if participant_flow > 0 else "saida"
                bucket_direction = "compra liquida/aumento reportado" if activity > 0 else "venda liquida/reducao reportada"
                bucket_label = labels.get(bucket_key, bucket_key)
                sample_assets = [item for item in str(bucket.get("sample_assets") or "").split(",") if item][:4]
                rows.append({
                    "participant_type": participant.get("participant_type"),
                    "participant_flow_21d_brl": participant_flow,
                    "participant_flow_5d_brl": self._num(participant.get("rolling_5d_net_flow_brl")),
                    "participant_daily_flow_brl": self._num(participant.get("daily_net_flow_brl")),
                    "participant_date": participant.get("date"),
                    "bucket": bucket_key,
                    "bucket_label": bucket_label,
                    "fund_count": bucket.get("fund_count"),
                    "asset_count": bucket.get("asset_count"),
                    "bucket_activity": activity,
                    "bucket_buy_value": bucket.get("buy_value"),
                    "bucket_sell_value": bucket.get("sell_value"),
                    "bucket_net_value": bucket.get("net_value"),
                    "bucket_gross_value": bucket.get("gross_value"),
                    "sample_assets": sample_assets,
                    "relationship": relationship,
                    "participant_direction": participant_direction,
                    "bucket_direction": bucket_direction,
                    "window_note": (
                        f"B3 usa fluxo liquido de participante em 21 dias ate {participant.get('date') or 'a data BDI'}; "
                        f"CDA usa atividade reportada no mes {month}."
                    ),
                    "rule_note": (
                        "Classificacao por sinal: coerente quando fluxo B3 e atividade CDA apontam na mesma direcao; "
                        "divergente quando os sinais sao opostos. A leitura e coincidencia temporal, nao causalidade."
                    ),
                    "ranking_note": (
                        "O ranking prioriza materialidade: abs(fluxo B3 21d) multiplicado por "
                        "(abs(atividade CDA) + 15% de abs(posicao liquida CDA))."
                    ),
                    "explanation": (
                        f"{participant.get('participant_type')} registrou {participant_direction} liquida de "
                        f"{self._fmt_brl(participant_flow)} em 21d na B3. No CDA, {bucket_label} mostrou "
                        f"{bucket_direction} de {self._fmt_brl(activity)} no mes {month}. "
                        f"Por isso a tela marcou a relacao como {relationship}."
                    ),
                    "tone": "up" if same_direction and activity > 0 else "down" if same_direction else "warn",
                    "score": score,
                    "note": (
                        f"{participant.get('participant_type')} {'entrou' if participant_flow > 0 else 'saiu'} "
                        f"{self._fmt_brl(participant_flow)} em 21d na B3 enquanto {bucket_label} "
                        f"teve atividade CDA de {self._fmt_brl(activity)}."
                    ),
                })
        rows.sort(key=lambda row: row.get("score") or 0, reverse=True)
        item_limit = max(6, min(int(limit or 16), 32))
        max_score = max((self._num(row.get("score")) for row in rows), default=0)
        for index, row in enumerate(rows[:item_limit], start=1):
            row["rank"] = index
            row["score_share"] = self._num(row.get("score")) / max_score if max_score else 0
        return {
            "rows": rows[:item_limit],
            "source_note": (
                "B3 participant flow is daily/21d from BDI; CDA activity is monthly portfolio report. "
                "Rows are coincidence/coherence screens, not causal attribution."
            ),
            "participant_source": str(self._b3_trend_csv_path()),
        }

    def _fetch_bridge_path_details(
        self,
        con: sqlite3.Connection,
        month: str,
        bridge_paths: list[dict[str, Any]],
        *,
        limit: int,
    ) -> dict[str, Any]:
        details: dict[str, Any] = {}
        item_limit = max(5, min(int(limit or 12), 24))
        for bridge in bridge_paths:
            target = str(bridge.get("target") or "").strip()
            fund_type = str(bridge.get("fund_type") or "").strip()
            condition = CDA_TARGET_SQL.get(target)
            if not target or not fund_type or not condition:
                continue
            key = f"{target}|{fund_type}"
            params = (month, fund_type, item_limit)
            funds = [dict(row) for row in con.execute(
                f"""
                SELECT
                    h.fund_cnpj,
                    MAX(h.fund_name) AS fund_name,
                    COALESCE(NULLIF(MAX(h.fund_type), ''), 'Outros') AS fund_type,
                    COUNT(*) AS holding_count,
                    COUNT(DISTINCT NULLIF(h.issuer_name, '')) AS issuer_count,
                    COUNT(DISTINCT COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''))) AS asset_count,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS long_value,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(h.value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                    SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                    SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                    SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0)) AS reported_activity,
                    MAX(fs.pl) AS pl,
                    CASE WHEN MAX(fs.pl) != 0 THEN SUM(COALESCE(h.value_market, 0)) / MAX(fs.pl) * 100.0 ELSE NULL END AS target_pct_pl
                FROM cvm_cda_holdings h
                LEFT JOIN cvm_cda_fund_summary fs
                  ON fs.month = h.month AND fs.fund_cnpj = h.fund_cnpj
                WHERE h.month = ?
                  AND COALESCE(NULLIF(h.fund_type, ''), 'Outros') = ?
                  AND ({condition})
                GROUP BY h.fund_cnpj
                ORDER BY SUM(ABS(COALESCE(h.value_market, 0))) DESC,
                         ABS(SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0))) DESC
                LIMIT ?
                """,
                params,
            ).fetchall()]
            issuers = [dict(row) for row in con.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(h.issuer_name, ''), 'Emissor nao identificado') AS issuer_name,
                    COUNT(DISTINCT h.fund_cnpj) AS fund_count,
                    COUNT(*) AS holding_count,
                    COUNT(DISTINCT COALESCE(NULLIF(h.asset_class, ''), 'Outros')) AS asset_class_count,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS long_value,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(h.value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                    SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0)) AS reported_activity,
                    MAX(COALESCE(NULLIF(h.asset_class, ''), 'Outros')) AS sample_asset_class
                FROM cvm_cda_holdings h
                WHERE h.month = ?
                  AND COALESCE(NULLIF(h.fund_type, ''), 'Outros') = ?
                  AND ({condition})
                  AND COALESCE(NULLIF(h.issuer_name, ''), 'Emissor nao identificado') <> 'Emissor nao identificado'
                GROUP BY COALESCE(NULLIF(h.issuer_name, ''), 'Emissor nao identificado')
                ORDER BY SUM(ABS(COALESCE(h.value_market, 0))) DESC
                LIMIT ?
                """,
                params,
            ).fetchall()]
            assets = [dict(row) for row in con.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'UNCLASSIFIED') AS asset_key,
                    MAX(h.asset_desc) AS asset_desc,
                    MAX(h.issuer_name) AS issuer_name,
                    COALESCE(NULLIF(MAX(h.asset_class), ''), 'Outros') AS asset_class,
                    COUNT(DISTINCT h.fund_cnpj) AS fund_count,
                    COUNT(*) AS holding_count,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS long_value,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(h.value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                    SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                    SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                    SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0)) AS reported_activity
                FROM cvm_cda_holdings h
                WHERE h.month = ?
                  AND COALESCE(NULLIF(h.fund_type, ''), 'Outros') = ?
                  AND ({condition})
                GROUP BY COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'UNCLASSIFIED')
                ORDER BY SUM(ABS(COALESCE(h.value_market, 0))) DESC,
                         ABS(SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0))) DESC
                LIMIT ?
                """,
                params,
            ).fetchall()]
            details[key] = {
                "target": target,
                "target_label": bridge.get("target_label") or CDA_TARGET_LABELS.get(target, target),
                "fund_type": fund_type,
                "summary": bridge,
                "funds": self._rank_rows(funds),
                "issuers": self._rank_rows(issuers),
                "assets": self._rank_rows(assets),
            }
        return details

    def _fetch_explanatory_connections(self, con: sqlite3.Connection, month: str, *, limit: int) -> list[dict[str, Any]]:
        per_query_limit = max(6, min(int(limit or 20), 40))
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        generic_terms = (
            "emissor nao identificado",
            "nao informado",
            "valor a pagar",
            "valores a pagar",
            "valor a receber",
            "valores a receber",
            "disponibilidade",
            "caixa",
            "outros",
            "sem ativo lider",
        )

        def is_generic_text(value: Any) -> bool:
            text = str(value or "").strip().lower()
            return not text or any(term in text for term in generic_terms)

        def tone_for(*values: Any) -> str:
            for value in values:
                number = self._num(value)
                if abs(number) > 0.000001:
                    return "up" if number > 0 else "down"
            return "flat"

        def add(
            *,
            connection_type: str,
            name: str,
            fact: str,
            score: float,
            category: str,
            tone: str = "flat",
            metrics: dict[str, Any] | None = None,
        ) -> None:
            key = self._hash(connection_type, name, fact[:180])
            if key in seen:
                return
            seen.add(key)
            rows.append({
                "uuid": f"cda:explanatory:{key}",
                "name": name,
                "fact": fact,
                "fact_type": connection_type,
                "category": category,
                "tone": tone,
                "score": float(score or 0),
                "metrics": metrics or {},
            })

        for target, condition in CDA_TARGET_SQL.items():
            target_rows = [dict(row) for row in con.execute(
                f"""
                SELECT
                    ? AS target,
                    ? AS target_label,
                    COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                    COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado') AS issuer_name,
                    COUNT(DISTINCT fund_cnpj) AS fund_count,
                    COUNT(*) AS holding_count,
                    COUNT(DISTINCT COALESCE(NULLIF(asset_class, ''), 'Outros')) AS asset_class_count,
                    SUM(COALESCE(value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                    SUM(COALESCE(value_buy, 0)) AS buy_value,
                    SUM(COALESCE(value_sell, 0)) AS sell_value,
                    SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity,
                    MAX(COALESCE(NULLIF(asset_class, ''), 'Outros')) AS sample_asset_class
                FROM cvm_cda_holdings
                WHERE month = ?
                  AND ({condition})
                  AND COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado') <> 'Emissor nao identificado'
                GROUP BY
                    COALESCE(NULLIF(fund_type, ''), 'Outros'),
                    COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado')
                HAVING COUNT(DISTINCT fund_cnpj) >= 2
                   AND SUM(ABS(COALESCE(value_market, 0))) > 0
                ORDER BY SUM(ABS(COALESCE(value_market, 0))) DESC,
                         ABS(SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0))) DESC
                LIMIT ?
                """,
                (target, CDA_TARGET_LABELS[target], month, per_query_limit),
            ).fetchall()]
            for item in target_rows:
                if is_generic_text(item.get("issuer_name")):
                    continue
                activity = self._num(item.get("reported_activity"))
                gross = self._num(item.get("gross_value"))
                score = gross + abs(activity) * 0.65 + self._num(item.get("fund_count")) * 10_000_000_000
                add(
                    connection_type="TARGET_ISSUER_CLUSTER",
                    name=f"{item.get('target_label')} -> {item.get('issuer_name')}",
                    category="Tema + emissor",
                    tone=tone_for(activity, item.get("net_value")),
                    score=score,
                    metrics=item,
                    fact=(
                        f"{item.get('fund_count')} fundos {item.get('fund_type')} conectam {item.get('target_label')} "
                        f"a {item.get('issuer_name')}, com gross {self._fmt_brl(item.get('gross_value'))}, "
                        f"liquido {self._fmt_brl(item.get('net_value'))} e atividade declarada "
                        f"{self._fmt_brl(activity)}."
                    ),
                )

        activity_rows = [dict(row) for row in con.execute(
            """
            SELECT
                COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(asset_class, ''), 'Outros') AS asset_class,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(DISTINCT NULLIF(issuer_name, '')) AS issuer_count,
                COUNT(*) AS holding_count,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) AS buy_value,
                SUM(COALESCE(value_sell, 0)) AS sell_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings
            WHERE month = ?
            GROUP BY COALESCE(NULLIF(fund_type, ''), 'Outros'), COALESCE(NULLIF(asset_class, ''), 'Outros')
            HAVING SUM(ABS(COALESCE(value_market, 0))) > 0
            ORDER BY ABS(SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0))) DESC,
                     SUM(ABS(COALESCE(value_market, 0))) DESC
            LIMIT ?
            """,
            (month, per_query_limit),
        ).fetchall()]
        for item in activity_rows:
            if is_generic_text(item.get("asset_class")):
                continue
            activity = self._num(item.get("reported_activity"))
            gross = self._num(item.get("gross_value"))
            if abs(activity) < 1 and gross < 50_000_000:
                continue
            add(
                connection_type="FUND_TYPE_ASSET_ACTIVITY",
                name=f"{item.get('fund_type')} -> {item.get('asset_class')}",
                category="Tipo + classe",
                tone=tone_for(activity, item.get("net_value")),
                score=gross + abs(activity) + self._num(item.get("fund_count")) * 5_000_000_000,
                metrics=item,
                fact=(
                    f"{item.get('fund_type')} reportou atividade liquida de {self._fmt_brl(activity)} "
                    f"em {item.get('asset_class')} (compras {self._fmt_brl(item.get('buy_value'))}, "
                    f"vendas {self._fmt_brl(item.get('sell_value'))}) em {item.get('fund_count')} fundos; "
                    f"estoque liquido {self._fmt_brl(item.get('net_value'))}."
                ),
            )

        country_rows = [dict(row) for row in con.execute(
            """
            SELECT
                COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(country, ''), 'Nao informado') AS country,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(*) AS holding_count,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(CASE WHEN COALESCE(value_market, 0) > 0 THEN COALESCE(value_market, 0) ELSE 0 END) AS long_value,
                SUM(CASE WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings
            WHERE month = ?
              AND COALESCE(NULLIF(country, ''), 'Nao informado') <> 'Nao informado'
            GROUP BY COALESCE(NULLIF(fund_type, ''), 'Outros'), COALESCE(NULLIF(country, ''), 'Nao informado')
            HAVING COUNT(DISTINCT fund_cnpj) >= 2
               AND SUM(ABS(COALESCE(value_market, 0))) > 0
            ORDER BY SUM(ABS(COALESCE(value_market, 0))) DESC,
                     ABS(SUM(COALESCE(value_market, 0))) DESC
            LIMIT ?
            """,
            (month, per_query_limit),
        ).fetchall()]
        for item in country_rows:
            add(
                connection_type="GEOGRAPHIC_EXPOSURE_CLUSTER",
                name=f"{item.get('fund_type')} -> {item.get('country')}",
                category="Pais + tipo",
                tone=tone_for(item.get("net_value"), item.get("reported_activity")),
                score=self._num(item.get("gross_value")) + self._num(item.get("fund_count")) * 4_000_000_000,
                metrics=item,
                fact=(
                    f"No mapa geografico, {item.get('fund_type')} carrega {self._fmt_brl(item.get('gross_value'))} "
                    f"gross em {item.get('country')}, com long {self._fmt_brl(item.get('long_value'))}, "
                    f"short {self._fmt_brl(item.get('short_value'))} e {item.get('fund_count')} fundos conectados."
                ),
            )

        short_rows = [dict(row) for row in con.execute(
            """
            SELECT
                COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(asset_class, ''), 'Outros') AS asset_class,
                COALESCE(NULLIF(asset_code, ''), NULLIF(asset_desc, ''), NULLIF(issuer_name, ''), 'Sem ativo lider') AS sample_asset,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(*) AS holding_count,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(CASE WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings
            WHERE month = ?
              AND (COALESCE(is_derivative, 0) = 1 OR COALESCE(value_market, 0) < 0)
            GROUP BY
                COALESCE(NULLIF(fund_type, ''), 'Outros'),
                COALESCE(NULLIF(asset_class, ''), 'Outros'),
                COALESCE(NULLIF(asset_code, ''), NULLIF(asset_desc, ''), NULLIF(issuer_name, ''), 'Sem ativo lider')
            HAVING SUM(ABS(COALESCE(value_market, 0))) > 0
            ORDER BY SUM(ABS(COALESCE(value_market, 0))) DESC
            LIMIT ?
            """,
            (month, per_query_limit),
        ).fetchall()]
        for item in short_rows:
            if is_generic_text(item.get("sample_asset")) or is_generic_text(item.get("asset_class")):
                continue
            add(
                connection_type="SHORT_DERIVATIVE_POCKET",
                name=f"{item.get('fund_type')} -> {item.get('sample_asset')}",
                category="Short/derivativo",
                tone="down" if self._num(item.get("short_value")) > 0 else tone_for(item.get("net_value")),
                score=self._num(item.get("gross_value")) + self._num(item.get("short_value")) * 0.5,
                metrics=item,
                fact=(
                    f"Bolso vendido/derivativo: {item.get('fund_type')} aparece em {item.get('sample_asset')} "
                    f"({item.get('asset_class')}), com gross {self._fmt_brl(item.get('gross_value'))}, "
                    f"short {self._fmt_brl(item.get('short_value'))} e {item.get('fund_count')} fundos."
                ),
            )

        issuer_rows = [dict(row) for row in con.execute(
            """
            SELECT
                COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado') AS issuer_name,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(DISTINCT COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_type_count,
                group_concat(DISTINCT COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_types,
                COUNT(DISTINCT COALESCE(NULLIF(asset_class, ''), 'Outros')) AS asset_class_count,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings
            WHERE month = ?
              AND COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado') <> 'Emissor nao identificado'
            GROUP BY COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado')
            HAVING COUNT(DISTINCT fund_cnpj) >= 5
            ORDER BY COUNT(DISTINCT fund_cnpj) DESC,
                     SUM(ABS(COALESCE(value_market, 0))) DESC
            LIMIT ?
            """,
            (month, per_query_limit),
        ).fetchall()]
        for item in issuer_rows:
            if is_generic_text(item.get("issuer_name")):
                continue
            fund_types = ", ".join(str(item.get("fund_types") or "").split(",")[:4])
            add(
                connection_type="ISSUER_CROWDING_CLUSTER",
                name=f"Crowding -> {item.get('issuer_name')}",
                category="Crowding",
                tone=tone_for(item.get("reported_activity"), item.get("net_value")),
                score=self._num(item.get("fund_count")) * 12_000_000_000 + self._num(item.get("gross_value")),
                metrics=item,
                fact=(
                    f"{item.get('issuer_name')} e ponto de crowding: {item.get('fund_count')} fundos, "
                    f"{item.get('fund_type_count')} tipos ({fund_types}) e {self._fmt_brl(item.get('gross_value'))} "
                    f"gross; saldo liquido {self._fmt_brl(item.get('net_value'))}."
                ),
            )

        concentration_rows = [dict(row) for row in con.execute(
            """
            SELECT
                fund_name,
                fund_cnpj,
                COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                target,
                target_label,
                target_pct_pl,
                gross_value,
                net_value,
                concentration_pct,
                top_issuer,
                top_asset_class
            FROM cvm_cda_fund_target_exposure
            WHERE month = ?
              AND COALESCE(pl, 0) > 1000000
              AND ABS(COALESCE(target_pct_pl, 0)) <= 500
              AND (ABS(COALESCE(target_pct_pl, 0)) >= 5 OR COALESCE(gross_value, 0) >= 100000000)
            ORDER BY ABS(COALESCE(target_pct_pl, 0)) DESC,
                     COALESCE(gross_value, 0) DESC
            LIMIT ?
            """,
            (month, per_query_limit),
        ).fetchall()]
        for item in concentration_rows:
            add(
                connection_type="FUND_TARGET_CONCENTRATION",
                name=f"{item.get('fund_name')} -> {item.get('target_label')}",
                category="Concentracao",
                tone=tone_for(item.get("net_value")),
                score=abs(self._num(item.get("target_pct_pl"))) * 1_000_000_000 + self._num(item.get("gross_value")),
                metrics=item,
                fact=(
                    f"{item.get('fund_name')} tem {self._fmt_pct(item.get('target_pct_pl'))} do PL em "
                    f"{item.get('target_label')}, gross {self._fmt_brl(item.get('gross_value'))}, "
                    f"top emissor {item.get('top_issuer') or 'nao identificado'} e classe "
                    f"{item.get('top_asset_class') or 'nao informada'}."
                ),
            )

        rows.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        for index, row in enumerate(rows[:limit], start=1):
            row["rank"] = index
        return rows[:limit]

    def _connect_cda(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self.cda_db_path), timeout=30.0)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA temp_store=MEMORY")
        return con

    def _driver(self):
        if not self.neo4j_password:
            raise RuntimeError("NEO4J_PASSWORD is not configured.")
        return GraphDatabase.driver(self.neo4j_uri, auth=(self.neo4j_user, self.neo4j_password))

    def _resolve_month(self, con: sqlite3.Connection, month: str | None) -> str | None:
        if month:
            cleaned = re.sub(r"[^0-9]", "", str(month))
            if len(cleaned) >= 6:
                cleaned = cleaned[:6]
            row = con.execute(
                "SELECT month FROM cvm_cda_months WHERE month = ? AND status = 'ready'",
                (cleaned,),
            ).fetchone()
            if row:
                return row["month"]
        row = con.execute(
            "SELECT month FROM cvm_cda_months WHERE status = 'ready' ORDER BY month DESC LIMIT 1"
        ).fetchone()
        return row["month"] if row else None

    def _resolve_graph_month(self, month: str | None) -> str | None:
        if month:
            cleaned = re.sub(r"[^0-9]", "", str(month))
            if len(cleaned) >= 6:
                return cleaned[:6]
        try:
            with self._driver() as driver:
                records, _, _ = driver.execute_query(
                    """
                    MATCH (m:CdaMonth {group_id: $group_id})
                    RETURN m.month AS month
                    ORDER BY m.month DESC
                    LIMIT 1
                    """,
                    group_id=self.group_id,
                )
                return records[0]["month"] if records else None
        except Exception:
            logger.exception("Failed to resolve latest CDA graph month")
            return None

    def _fetch_month_row(self, con: sqlite3.Connection, month: str) -> dict[str, Any]:
        row = con.execute("SELECT * FROM cvm_cda_months WHERE month = ?", (month,)).fetchone()
        return dict(row) if row else {"month": month}

    def _select_graph_funds(
        self,
        con: sqlite3.Connection,
        month: str,
        *,
        max_funds: int,
        target_funds_per_theme: int,
    ) -> list[str]:
        selected: list[str] = []
        seen: set[str] = set()

        def add_rows(rows: Iterable[sqlite3.Row]):
            for row in rows:
                raw_cnpj = str(row["fund_cnpj"] or "").strip()
                cnpj_key = self._digits(raw_cnpj) or raw_cnpj
                if raw_cnpj and cnpj_key not in seen:
                    selected.append(raw_cnpj)
                    seen.add(cnpj_key)
                if len(selected) >= max_funds:
                    break

        add_rows(con.execute(
            """
            SELECT fund_cnpj
            FROM cvm_cda_fund_summary
            WHERE month = ?
            ORDER BY COALESCE(pl, 0) DESC
            LIMIT ?
            """,
            (month, max(25, max_funds // 4)),
        ).fetchall())

        for target in CDA_TARGET_LABELS:
            if len(selected) >= max_funds:
                break
            add_rows(con.execute(
                """
                SELECT fund_cnpj
                FROM cvm_cda_fund_target_exposure
                WHERE month = ? AND target = ?
                ORDER BY COALESCE(gross_value, 0) DESC
                LIMIT ?
                """,
                (month, target, target_funds_per_theme),
            ).fetchall())

        if len(selected) < max_funds:
            add_rows(con.execute(
                """
                SELECT fund_cnpj
                FROM cvm_cda_fund_summary
                WHERE month = ?
                ORDER BY COALESCE(abs_position_value, 0) DESC
                LIMIT ?
                """,
                (month, max_funds),
            ).fetchall())

        return selected[:max_funds]

    def _fetch_fund_nodes(self, con: sqlite3.Connection, month: str, fund_cnpjs: list[str]) -> list[dict[str, Any]]:
        if not fund_cnpjs:
            return []
        placeholders, values = self._fund_in_clause(fund_cnpjs)
        return [dict(row) for row in con.execute(
            f"""
            SELECT fs.*
            FROM cvm_cda_fund_summary fs
            WHERE fs.month = ?
              AND fs.fund_cnpj IN ({placeholders})
            """,
            [month, *values],
        ).fetchall()]

    def _fetch_target_edges(self, con: sqlite3.Connection, month: str, fund_cnpjs: list[str]) -> list[dict[str, Any]]:
        if not fund_cnpjs:
            return []
        placeholders, values = self._fund_in_clause(fund_cnpjs)
        return [dict(row) for row in con.execute(
            f"""
            SELECT e.*
            FROM cvm_cda_fund_target_exposure e
            WHERE e.month = ?
              AND e.fund_cnpj IN ({placeholders})
            """,
            [month, *values],
        ).fetchall()]

    def _fetch_position_rows(
        self,
        con: sqlite3.Connection,
        month: str,
        fund_cnpjs: list[str],
        *,
        max_positions_per_fund: int,
        min_abs_value: float,
    ) -> list[dict[str, Any]]:
        if not fund_cnpjs:
            return []
        placeholders, values = self._fund_in_clause(fund_cnpjs)
        return [dict(row) for row in con.execute(
            f"""
            WITH ranked AS (
                SELECT
                    h.*,
                    fs.pl,
                    ROW_NUMBER() OVER (
                        PARTITION BY h.fund_cnpj
                        ORDER BY ABS(COALESCE(h.value_market, 0)) DESC
                    ) AS position_rank
                FROM cvm_cda_holdings h
                LEFT JOIN cvm_cda_fund_summary fs
                  ON fs.month = h.month AND fs.fund_cnpj = h.fund_cnpj
                WHERE h.month = ?
                  AND h.fund_cnpj IN ({placeholders})
                  AND ABS(COALESCE(h.value_market, 0)) >= ?
            )
            SELECT *
            FROM ranked
            WHERE position_rank <= ?
            ORDER BY ABS(COALESCE(value_market, 0)) DESC
            """,
            [month, *values, min_abs_value, max_positions_per_fund],
        ).fetchall()]

    def _fund_in_clause(self, fund_cnpjs: list[str]) -> tuple[str, list[str]]:
        values = [str(cnpj or "").strip() for cnpj in fund_cnpjs if str(cnpj or "").strip()]
        if not values:
            return "''", []
        return ",".join("?" for _ in values), values

    def _prepare_graph_payload(
        self,
        month: str,
        month_row: dict[str, Any],
        funds: list[dict[str, Any]],
        target_edges: list[dict[str, Any]],
        positions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        updated_at = datetime.now(timezone.utc).isoformat()
        month_node = {
            "id": self._node_id(month, "month", month),
            "uuid": self._node_id(month, "month", month),
            "name": self._month_label(month),
            "month": month,
            "label": self._month_label(month),
            "group_id": self.group_id,
            "imported_at": month_row.get("imported_at"),
            "latest_dt": month_row.get("latest_dt"),
            "total_pl": month_row.get("total_pl"),
            "total_rows": month_row.get("total_rows"),
            "total_position_value": month_row.get("total_position_value"),
            "total_confidential_value": month_row.get("total_confidential_value"),
            "graph_updated_at": updated_at,
        }

        fund_nodes = []
        fund_type_nodes: dict[str, dict[str, Any]] = {}
        fund_type_edges = []
        month_edges = []
        for fund in funds:
            fund_id = self._fund_id(month, fund.get("fund_cnpj"))
            fund_type = self._clean_label(fund.get("fund_type"), "Outros")
            fund_type_id = self._node_id(month, "fund_type", fund_type)
            fund_nodes.append({
                "id": fund_id,
                "uuid": fund_id,
                "name": fund.get("fund_name") or fund.get("fund_cnpj") or "Fundo sem nome",
                "cnpj": self._digits(fund.get("fund_cnpj")),
                "fund_type": fund_type,
                "month": month,
                "group_id": self.group_id,
                "dt_comptc": fund.get("dt_comptc"),
                "pl": fund.get("pl"),
                "position_value": fund.get("position_value"),
                "abs_position_value": fund.get("abs_position_value"),
                "holding_count": fund.get("holding_count"),
                "issuer_count": fund.get("issuer_count"),
                "asset_count": fund.get("asset_count"),
                "foreign_pct_pl": fund.get("foreign_pct_pl"),
                "private_credit_pct_pl": fund.get("private_credit_pct_pl"),
                "confidential_pct_pl": fund.get("confidential_pct_pl"),
                "turnover_pct_pl": fund.get("turnover_pct_pl"),
                "concentration_pct": fund.get("concentration_pct"),
                "updated_at": updated_at,
            })
            fund_type_nodes[fund_type_id] = {
                "id": fund_type_id,
                "uuid": fund_type_id,
                "name": fund_type,
                "month": month,
                "group_id": self.group_id,
                "updated_at": updated_at,
            }
            fund_type_edges.append({
                "id": self._edge_id("fund_type", fund_id, fund_type_id, month),
                "source_id": fund_id,
                "target_id": fund_type_id,
                "month": month,
                "group_id": self.group_id,
            })
            month_edges.append({
                "id": self._edge_id("reported_in", fund_id, month_node["id"], month),
                "source_id": fund_id,
                "target_id": month_node["id"],
                "month": month,
                "group_id": self.group_id,
            })

        target_nodes = [
            {
                "id": self._target_id(month, key),
                "uuid": self._target_id(month, key),
                "name": label,
                "target": key,
                "target_label": label,
                "month": month,
                "group_id": self.group_id,
                "updated_at": updated_at,
            }
            for key, label in CDA_TARGET_LABELS.items()
        ]
        target_rel_edges = []
        for row in target_edges:
            fund_id = self._fund_id(month, row.get("fund_cnpj"))
            target_id = self._target_id(month, row.get("target"))
            target_rel_edges.append({
                "id": self._edge_id("target", fund_id, target_id, month, row.get("target")),
                "source_id": fund_id,
                "target_id": target_id,
                "month": month,
                "group_id": self.group_id,
                "target": row.get("target"),
                "target_label": row.get("target_label"),
                "long_value": row.get("long_value"),
                "short_value": row.get("short_value"),
                "net_value": row.get("net_value"),
                "gross_value": row.get("gross_value"),
                "target_pct_pl": row.get("target_pct_pl"),
                "holdings_count": row.get("holdings_count"),
                "issuers_count": row.get("issuers_count"),
                "assets_count": row.get("assets_count"),
                "top_issuer": row.get("top_issuer"),
                "top_asset_class": row.get("top_asset_class"),
                "concentration_pct": row.get("concentration_pct"),
            })

        asset_nodes: dict[str, dict[str, Any]] = {}
        issuer_nodes: dict[str, dict[str, Any]] = {}
        asset_class_nodes: dict[str, dict[str, Any]] = {}
        country_nodes: dict[str, dict[str, Any]] = {}
        position_edges = []
        issuer_edges: dict[str, dict[str, Any]] = {}
        class_edges: dict[str, dict[str, Any]] = {}
        country_edges: dict[str, dict[str, Any]] = {}
        for pos in positions:
            fund_id = self._fund_id(month, pos.get("fund_cnpj"))
            asset_key = self._asset_key(pos)
            asset_class = self._clean_label(pos.get("asset_class"), "Outros")
            asset_id = self._asset_id(month, asset_key, asset_class)
            issuer_name = self._clean_label(pos.get("issuer_name") or pos.get("risk_issuer"), "Emissor nao identificado")
            issuer_doc = self._digits(pos.get("issuer_doc"))
            issuer_id = self._issuer_id(month, issuer_name, issuer_doc)
            asset_class_id = self._node_id(month, "asset_class", asset_class)
            country = self._clean_label(pos.get("country"), "Nao informado")
            country_id = self._node_id(month, "country", country)
            value_market = self._num(pos.get("value_market"))
            pl = self._num(pos.get("pl"))

            asset_nodes[asset_id] = {
                "id": asset_id,
                "uuid": asset_id,
                "name": pos.get("asset_desc") or pos.get("asset_code") or asset_key,
                "security_key": asset_key,
                "asset_code": pos.get("asset_code"),
                "asset_desc": pos.get("asset_desc"),
                "isin": pos.get("isin"),
                "asset_class": asset_class,
                "asset_subclass": pos.get("asset_subclass"),
                "country": country,
                "country_code": pos.get("country_code"),
                "market": pos.get("market"),
                "maturity_date": pos.get("maturity_date"),
                "maturity_bucket": pos.get("maturity_bucket"),
                "is_foreign": self._bool(pos.get("is_foreign")),
                "is_derivative": self._bool(pos.get("is_derivative")),
                "is_fund_quota": self._bool(pos.get("is_fund_quota")),
                "is_confidential": self._bool(pos.get("is_confidential")),
                "month": month,
                "group_id": self.group_id,
                "updated_at": updated_at,
            }
            issuer_nodes[issuer_id] = {
                "id": issuer_id,
                "uuid": issuer_id,
                "name": issuer_name,
                "issuer_doc": issuer_doc,
                "month": month,
                "group_id": self.group_id,
                "updated_at": updated_at,
            }
            asset_class_nodes[asset_class_id] = {
                "id": asset_class_id,
                "uuid": asset_class_id,
                "name": asset_class,
                "month": month,
                "group_id": self.group_id,
                "updated_at": updated_at,
            }
            country_nodes[country_id] = {
                "id": country_id,
                "uuid": country_id,
                "name": country,
                "country_code": pos.get("country_code"),
                "month": month,
                "group_id": self.group_id,
                "updated_at": updated_at,
            }
            position_edges.append({
                "id": self._edge_id(
                    "position",
                    fund_id,
                    asset_id,
                    month,
                    pos.get("source_block"),
                    pos.get("asset_code"),
                    pos.get("asset_desc"),
                    pos.get("position_rank"),
                ),
                "source_id": fund_id,
                "target_id": asset_id,
                "month": month,
                "group_id": self.group_id,
                "source_block": pos.get("source_block"),
                "asset_class": asset_class,
                "asset_subclass": pos.get("asset_subclass"),
                "side": "short" if value_market < 0 else "long",
                "value_market": value_market,
                "abs_value_market": abs(value_market),
                "pct_pl": (value_market / pl * 100.0) if pl else None,
                "qty_final": pos.get("qty_final"),
                "value_cost": pos.get("value_cost"),
                "value_buy": pos.get("value_buy"),
                "value_sell": pos.get("value_sell"),
                "is_confidential": self._bool(pos.get("is_confidential")),
                "is_foreign": self._bool(pos.get("is_foreign")),
                "is_related_issuer": self._bool(pos.get("is_related_issuer")),
                "position_rank": pos.get("position_rank"),
            })
            issuer_edges[self._edge_id("issuer", asset_id, issuer_id, month)] = {
                "id": self._edge_id("issuer", asset_id, issuer_id, month),
                "source_id": asset_id,
                "target_id": issuer_id,
                "month": month,
                "group_id": self.group_id,
            }
            class_edges[self._edge_id("class", asset_id, asset_class_id, month)] = {
                "id": self._edge_id("class", asset_id, asset_class_id, month),
                "source_id": asset_id,
                "target_id": asset_class_id,
                "month": month,
                "group_id": self.group_id,
            }
            country_edges[self._edge_id("country", asset_id, country_id, month)] = {
                "id": self._edge_id("country", asset_id, country_id, month),
                "source_id": asset_id,
                "target_id": country_id,
                "month": month,
                "group_id": self.group_id,
            }

        return {
            "month": month,
            "month_node": month_node,
            "fund_nodes": fund_nodes,
            "fund_type_nodes": list(fund_type_nodes.values()),
            "target_nodes": target_nodes,
            "asset_nodes": list(asset_nodes.values()),
            "issuer_nodes": list(issuer_nodes.values()),
            "asset_class_nodes": list(asset_class_nodes.values()),
            "country_nodes": list(country_nodes.values()),
            "month_edges": month_edges,
            "fund_type_edges": fund_type_edges,
            "target_edges": target_rel_edges,
            "position_edges": position_edges,
            "issuer_edges": list(issuer_edges.values()),
            "class_edges": list(class_edges.values()),
            "country_edges": list(country_edges.values()),
            "counts": {
                "months": 1,
                "funds": len(fund_nodes),
                "fund_types": len(fund_type_nodes),
                "targets": len(target_nodes),
                "assets": len(asset_nodes),
                "issuers": len(issuer_nodes),
                "asset_classes": len(asset_class_nodes),
                "countries": len(country_nodes),
                "positions": len(position_edges),
                "target_exposures": len(target_rel_edges),
                "edges": (
                    len(month_edges)
                    + len(fund_type_edges)
                    + len(target_rel_edges)
                    + len(position_edges)
                    + len(issuer_edges)
                    + len(class_edges)
                    + len(country_edges)
                ),
            },
        }

    def _write_payload(self, driver, payload: dict[str, Any]) -> None:
        self._merge_nodes(driver, "CdaMonth", [payload["month_node"]])
        self._merge_nodes(driver, "CdaFund", payload["fund_nodes"])
        self._merge_nodes(driver, "CdaFundType", payload["fund_type_nodes"])
        self._merge_nodes(driver, "CdaExposureTarget", payload["target_nodes"])
        self._merge_nodes(driver, "CdaAsset", payload["asset_nodes"])
        self._merge_nodes(driver, "CdaIssuer", payload["issuer_nodes"])
        self._merge_nodes(driver, "CdaAssetClass", payload["asset_class_nodes"])
        self._merge_nodes(driver, "CdaCountry", payload["country_nodes"])
        self._merge_relationships(driver, "REPORTED_IN", payload["month_edges"])
        self._merge_relationships(driver, "HAS_FUND_TYPE", payload["fund_type_edges"])
        self._merge_relationships(driver, "HAS_TARGET_EXPOSURE", payload["target_edges"])
        self._merge_relationships(driver, "HOLDS_POSITION", payload["position_edges"])
        self._merge_relationships(driver, "ISSUED_BY", payload["issuer_edges"])
        self._merge_relationships(driver, "CLASSIFIED_AS", payload["class_edges"])
        self._merge_relationships(driver, "LOCATED_IN", payload["country_edges"])

    def _ensure_constraints(self, driver) -> None:
        for label in (
            "CdaMonth",
            "CdaFund",
            "CdaFundType",
            "CdaAsset",
            "CdaIssuer",
            "CdaAssetClass",
            "CdaCountry",
            "CdaExposureTarget",
        ):
            driver.execute_query(
                f"CREATE CONSTRAINT cda_{label.lower()}_id IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE"
            )
        for rel_type in (
            "REPORTED_IN",
            "HAS_FUND_TYPE",
            "HAS_TARGET_EXPOSURE",
            "HOLDS_POSITION",
            "ISSUED_BY",
            "CLASSIFIED_AS",
            "LOCATED_IN",
        ):
            driver.execute_query(
                f"CREATE INDEX cda_{rel_type.lower()}_id IF NOT EXISTS FOR ()-[r:{rel_type}]-() ON (r.id)"
            )

    def _merge_nodes(self, driver, label: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        query = f"""
        UNWIND $rows AS row
        MERGE (n:{label} {{id: row.id}})
        SET n += row.props
        """
        for batch in self._chunks(rows, 500):
            driver.execute_query(
                query,
                rows=[{"id": row["id"], "props": self._props(row)} for row in batch],
            )

    def _merge_relationships(self, driver, rel_type: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        query = f"""
        UNWIND $rows AS row
        MATCH (source {{id: row.source_id}})
        MATCH (target {{id: row.target_id}})
        MERGE (source)-[r:{rel_type} {{id: row.id}}]->(target)
        SET r += row.props
        """
        for batch in self._chunks(rows, 500):
            driver.execute_query(
                query,
                rows=[
                    {
                        "id": row["id"],
                        "source_id": row["source_id"],
                        "target_id": row["target_id"],
                        "props": self._props(row),
                    }
                    for row in batch
                ],
            )

    def _records_to_graph(self, records) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: dict[str, dict[str, Any]] = {}
        for record in records:
            source = record.get("source")
            rel = record.get("rel")
            target = record.get("target")
            issuer = record.get("issuer")
            for node in (source, target, issuer):
                if node is not None:
                    node_payload = self._format_node(node)
                    nodes[node_payload["uuid"]] = node_payload
            if rel is not None and source is not None and target is not None:
                edge_payload = self._format_edge(rel, source, target)
                edges[edge_payload["uuid"]] = edge_payload
        return {"nodes": list(nodes.values()), "edges": list(edges.values()), "node_count": len(nodes), "edge_count": len(edges)}

    def _append_context_edges(self, driver, graph: dict[str, Any], month: str) -> None:
        node_ids = [node["uuid"] for node in graph.get("nodes") or []]
        if not node_ids:
            return
        records, _, _ = driver.execute_query(
            """
            MATCH (source {group_id: $group_id, month: $month})-[r {group_id: $group_id, month: $month}]->(target {group_id: $group_id, month: $month})
            WHERE source.id IN $node_ids
              AND type(r) <> 'HOLDS_POSITION'
            RETURN source, r AS rel, target
            LIMIT 2000
            """,
            group_id=self.group_id,
            month=month,
            node_ids=node_ids,
        )
        existing_nodes = {node["uuid"]: node for node in graph.get("nodes") or []}
        existing_edges = {edge["uuid"]: edge for edge in graph.get("edges") or []}
        for record in records:
            source = record["source"]
            target = record["target"]
            rel = record["rel"]
            for node in (source, target):
                node_payload = self._format_node(node)
                existing_nodes[node_payload["uuid"]] = node_payload
            edge_payload = self._format_edge(rel, source, target)
            existing_edges[edge_payload["uuid"]] = edge_payload
        graph["nodes"] = list(existing_nodes.values())
        graph["edges"] = list(existing_edges.values())
        graph["node_count"] = len(graph["nodes"])
        graph["edge_count"] = len(graph["edges"])

    def _format_node(self, node) -> dict[str, Any]:
        props = dict(node)
        labels = list(node.labels)
        uuid = str(props.get("uuid") or props.get("id"))
        reserved = {"id", "uuid", "name", "group_id", "month"}
        attributes = {key: self._json_value(value) for key, value in props.items() if key not in reserved}
        return {
            "uuid": uuid,
            "name": props.get("name") or uuid,
            "labels": labels,
            "summary": self._node_summary(labels, props),
            "attributes": attributes,
            "created_at": props.get("updated_at"),
        }

    def _format_edge(self, rel, source, target) -> dict[str, Any]:
        props = dict(rel)
        uuid = str(props.get("id") or rel.element_id)
        reserved = {"id", "group_id", "month", "source_id", "target_id"}
        attributes = {key: self._json_value(value) for key, value in props.items() if key not in reserved}
        rel_type = rel.type
        fact = self._edge_fact(rel_type, dict(source), dict(target), props)
        return {
            "uuid": uuid,
            "name": rel_type,
            "fact": fact,
            "fact_type": rel_type,
            "source_node_uuid": dict(source).get("id"),
            "target_node_uuid": dict(target).get("id"),
            "source_node_name": dict(source).get("name"),
            "target_node_name": dict(target).get("name"),
            "attributes": attributes,
            "created_at": props.get("updated_at"),
            "valid_at": None,
            "invalid_at": None,
            "expired_at": None,
            "episodes": [],
        }

    def _node_summary(self, labels: list[str], props: dict[str, Any]) -> str:
        if "CdaFund" in labels:
            return f"Fundo CDA {props.get('cnpj')} com PL reportado de {self._fmt_brl(props.get('pl'))}."
        if "CdaAsset" in labels:
            return f"Ativo CDA de classe {props.get('asset_class') or 'nao informada'}."
        if "CdaIssuer" in labels:
            return "Emissor/contraparte presente nas carteiras CVM CDA."
        return "No deterministico do grafo CVM CDA."

    def _edge_fact(self, rel_type: str, source: dict[str, Any], target: dict[str, Any], props: dict[str, Any]) -> str:
        if rel_type == "HOLDS_POSITION":
            return (
                f"{source.get('name')} reportou posicao {props.get('side')} em {target.get('name')} "
                f"no valor de {self._fmt_brl(props.get('value_market'))}; "
                f"classe {props.get('asset_class') or 'nao informada'} e {self._fmt_pct(props.get('pct_pl'))} do PL."
            )
        if rel_type == "HAS_TARGET_EXPOSURE":
            return (
                f"{source.get('name')} tem exposicao ao tema {target.get('name')} "
                f"com valor liquido de {self._fmt_brl(props.get('net_value'))}, "
                f"gross de {self._fmt_brl(props.get('gross_value'))} e {self._fmt_pct(props.get('target_pct_pl'))} do PL."
            )
        if rel_type == "ISSUED_BY":
            return f"{source.get('name')} foi associado ao emissor/contraparte {target.get('name')}."
        if rel_type == "CLASSIFIED_AS":
            return f"{source.get('name')} entra na camada de ativo {target.get('name')}."
        if rel_type == "LOCATED_IN":
            return f"{source.get('name')} foi mapeado para exposicao geografica {target.get('name')}."
        return f"{source.get('name')} -> {rel_type} -> {target.get('name')}."

    @staticmethod
    def _rank_row(row: dict[str, Any], rank: int) -> dict[str, Any]:
        cleaned = dict(row)
        cleaned["rank"] = rank
        return cleaned

    @classmethod
    def _rank_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = []
        for index, row in enumerate(rows, start=1):
            item = cls._rank_row(row, index)
            item["activity_direction"] = cls._activity_direction(item.get("reported_activity"))
            ranked.append(item)
        return ranked

    @staticmethod
    def _activity_direction(value: Any) -> str:
        try:
            number = float(value or 0)
        except Exception:
            number = 0.0
        if number > 0:
            return "inflow"
        if number < 0:
            return "outflow"
        return "neutral"

    @staticmethod
    def _is_generic_asset_text(value: Any) -> bool:
        text = str(value or "").strip().lower()
        generic_terms = (
            "emissor nao identificado",
            "nao informado",
            "valor a pagar",
            "valores a pagar",
            "valor a receber",
            "valores a receber",
            "disponibilidade",
            "caixa",
            "outros",
            "unclassified",
            "sem ativo lider",
        )
        return not text or any(term in text for term in generic_terms)

    def _asset_trail_key(self, asset_key: Any, asset_class: Any, side: Any) -> str:
        return self._hash("asset_trail", asset_key, asset_class, side)

    @classmethod
    def _option_side_from_row(cls, row: dict[str, Any]) -> str:
        text = cls._symbol_text(row.get("tp_ativo"), row.get("asset_desc"), row.get("asset_code"))
        if "VENDA" in text or " PUT " in f" {text} ":
            return "put"
        if "COMPRA" in text or " CALL " in f" {text} ":
            return "call"
        return "unknown"

    @classmethod
    def _option_position_role_from_row(cls, row: dict[str, Any]) -> str:
        text = cls._symbol_text(row.get("tp_aplic"))
        if "LANC" in text or "LAN " in text:
            return "written"
        if "TITULAR" in text:
            return "holder"
        return "unknown"

    @classmethod
    def _infer_option_underlying(cls, row: dict[str, Any]) -> str:
        candidates = [
            row.get("asset_code"),
            row.get("asset_desc"),
            row.get("issuer_name"),
            row.get("option_key"),
        ]
        for raw in candidates:
            symbol = cls._infer_symbol_prefix(raw)
            if symbol:
                return symbol
        return ""

    @classmethod
    def _infer_equity_underlying(cls, row: dict[str, Any]) -> str:
        candidates = [
            row.get("asset_code"),
            row.get("asset_desc"),
            row.get("issuer_name"),
            row.get("equity_key"),
        ]
        for raw in candidates:
            symbol = cls._infer_symbol_prefix(raw, equity=True)
            if symbol:
                return symbol
        return ""

    @classmethod
    def _infer_symbol_prefix(cls, value: Any, *, equity: bool = False) -> str:
        text = cls._symbol_text(value)
        if not text:
            return ""
        if re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", str(value or "")):
            return ""
        compact = re.sub(r"[^A-Z0-9]+", "", text)
        spaced = re.sub(r"[^A-Z0-9]+", " ", text).strip()
        if compact.startswith(("DOLOP", "DOL", "DOV", "WDO")) or "DOLAR" in spaced:
            return "USD/BRL"
        if compact.startswith(("IBOV", "WIN", "IND")):
            return "IBOV"
        if compact.startswith("BOVA"):
            return "BOVA11"
        if compact.startswith("SMAL"):
            return "SMAL11"
        if compact.startswith("IDIV"):
            return "IDIV"
        first = re.match(r"^([A-Z]{4})(?:[A-Z0-9]|\\s|$)", compact)
        if first:
            prefix = first.group(1)
            if prefix in {"OPCA", "OPCO", "OPFC", "OPCAO", "OFCF"}:
                return ""
            return prefix
        if equity:
            spaced_first = re.match(r"^([A-Z]{4})\\s", spaced)
            if spaced_first:
                return spaced_first.group(1)
        return ""

    @staticmethod
    def _symbol_text(*values: Any) -> str:
        raw = " ".join(str(value or "") for value in values if value is not None)
        replacements = {
            "Á": "A",
            "À": "A",
            "Â": "A",
            "Ã": "A",
            "Ä": "A",
            "Ç": "C",
            "É": "E",
            "Ê": "E",
            "Í": "I",
            "Ó": "O",
            "Ô": "O",
            "Õ": "O",
            "Ú": "U",
            "Ü": "U",
        }
        text = raw.upper()
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    @staticmethod
    def _asset_lens_labels() -> dict[str, str]:
        return {
            "all": "Todos",
            "equity": "Acoes/BDR",
            "fund_quotas": "Cotas de fundos",
            "fund_fixed_income": "Fundos RF/DI",
            "fund_multimarket": "Fundos multimercado",
            "fund_equity": "Fundos de acoes",
            "fund_real_estate": "Fundos imobiliarios",
            "fund_structured": "FIDC/FIP/FIAGRO",
            "options_call": "Opcoes call",
            "options_put": "Opcoes put",
            "options_unknown": "Opcoes sem ticker",
            "derivatives": "Derivativos/swaps",
            "foreign": "Exterior/BDR/ETF global",
            "public_bonds": "Titulos publicos",
            "private_credit": "Credito privado",
            "cash_if": "Depositos/IF",
            "confidential": "Confidencial",
            "other": "Outros",
        }

    @staticmethod
    def _asset_lens_tagged_cte() -> str:
        return """
            WITH tagged AS (
                SELECT
                    h.*,
                    COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'UNCLASSIFIED') AS asset_key,
                    CASE
                        WHEN (
                            (h.tp_aplic LIKE 'Op%' AND h.tp_aplic NOT LIKE 'Opera%')
                            OR h.tp_ativo LIKE 'Op%'
                            OR UPPER(h.asset_desc) LIKE 'OPCAO%'
                            OR UPPER(h.asset_desc) LIKE 'OPCOES%'
                          )
                          AND (
                            LOWER(h.tp_ativo) LIKE '%compra%'
                            OR UPPER(h.asset_desc) LIKE '%CALL%'
                            OR UPPER(h.asset_code) LIKE '%CALL%'
                          )
                            THEN 'options_call'
                        WHEN (
                            (h.tp_aplic LIKE 'Op%' AND h.tp_aplic NOT LIKE 'Opera%')
                            OR h.tp_ativo LIKE 'Op%'
                            OR UPPER(h.asset_desc) LIKE 'OPCAO%'
                            OR UPPER(h.asset_desc) LIKE 'OPCOES%'
                          )
                          AND (
                            LOWER(h.tp_ativo) LIKE '%venda%'
                            OR UPPER(h.asset_desc) LIKE '%PUT%'
                            OR UPPER(h.asset_code) LIKE '%PUT%'
                          )
                            THEN 'options_put'
                        WHEN (
                            (h.tp_aplic LIKE 'Op%' AND h.tp_aplic NOT LIKE 'Opera%')
                            OR h.tp_ativo LIKE 'Op%'
                            OR UPPER(h.asset_desc) LIKE 'OPCAO%'
                            OR UPPER(h.asset_desc) LIKE 'OPCOES%'
                          )
                            THEN 'options_unknown'
                        WHEN h.tp_ativo LIKE '%Opção de compra%'
                          OR h.asset_desc LIKE 'OPCAO CALL%'
                          OR (h.tp_aplic LIKE '%Opções%' AND h.tp_ativo LIKE '%compra%')
                            THEN 'options_call'
                        WHEN h.tp_ativo LIKE '%Opção de venda%'
                          OR h.asset_desc LIKE 'OPCAO PUT%'
                          OR (h.tp_aplic LIKE '%Opções%' AND h.tp_ativo LIKE '%venda%')
                            THEN 'options_put'
                        WHEN h.asset_class = 'Acoes'
                          OR h.tp_aplic = 'Ações'
                          OR h.tp_aplic LIKE 'Brazilian Depository Receipt%'
                          OR h.tp_aplic LIKE 'Obrigações por ações%'
                          OR h.tp_ativo LIKE 'Ação%'
                          OR h.tp_ativo LIKE '%BDR%'
                          OR h.tp_ativo LIKE '%Fundos de Índice%'
                            THEN 'equity'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          AND (
                            h.tp_ativo LIKE '%Imobili%'
                            OR h.asset_desc LIKE '%IMOBILI%'
                            OR h.issuer_name LIKE '%IMOBILI%'
                            OR h.asset_desc LIKE '% FII%'
                            OR h.issuer_name LIKE '% FII%'
                          )
                            THEN 'fund_real_estate'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          AND (
                            h.tp_ativo LIKE '%FIDC%'
                            OR h.tp_ativo LIKE '%FIP%'
                            OR h.tp_ativo LIKE '%FIAGRO%'
                            OR h.asset_desc LIKE '%FIDC%'
                            OR h.asset_desc LIKE '%FIP%'
                            OR h.asset_desc LIKE '%FIAGRO%'
                          )
                            THEN 'fund_structured'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          AND (
                            h.asset_desc LIKE '%MULTIMERCADO%'
                            OR h.issuer_name LIKE '%MULTIMERCADO%'
                            OR h.asset_desc LIKE '% FIM%'
                            OR h.issuer_name LIKE '% FIM%'
                          )
                            THEN 'fund_multimarket'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          AND (
                            h.asset_desc LIKE '%AÇÕES%'
                            OR h.issuer_name LIKE '%AÇÕES%'
                            OR h.asset_desc LIKE '%ACOES%'
                            OR h.issuer_name LIKE '%ACOES%'
                            OR h.asset_desc LIKE '%EQUITY%'
                            OR h.issuer_name LIKE '%EQUITY%'
                          )
                            THEN 'fund_equity'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          AND (
                            h.asset_desc LIKE '%RENDA FIXA%'
                            OR h.issuer_name LIKE '%RENDA FIXA%'
                            OR h.asset_desc LIKE '%REFERENCIADO%'
                            OR h.issuer_name LIKE '%REFERENCIADO%'
                            OR h.asset_desc LIKE '% DI %'
                            OR h.issuer_name LIKE '% DI %'
                          )
                            THEN 'fund_fixed_income'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          OR h.asset_class = 'Cotas de Fundos'
                            THEN 'fund_quotas'
                        WHEN COALESCE(h.is_derivative, 0) = 1
                          OR h.asset_class = 'Derivativos'
                          OR h.tp_ativo LIKE '%SWAP%'
                            THEN 'derivatives'
                        WHEN COALESCE(h.is_foreign, 0) = 1
                          OR h.asset_class = 'Investimento Exterior'
                            THEN 'foreign'
                        WHEN h.asset_class = 'Titulos Publicos'
                          OR h.tp_aplic LIKE '%Títulos Públicos%'
                            THEN 'public_bonds'
                        WHEN h.asset_class = 'Credito Privado'
                          OR h.tp_aplic LIKE '%Debêntures%'
                          OR h.tp_ativo LIKE '%Debênture%'
                            THEN 'private_credit'
                        WHEN h.asset_class = 'Depositos e IF'
                          OR h.tp_aplic LIKE '%Depósitos%'
                            THEN 'cash_if'
                        WHEN h.asset_class = 'Confidencial'
                            THEN 'confidential'
                        ELSE 'other'
                    END AS asset_bucket,
                    CASE
                        WHEN LOWER(h.tp_ativo) LIKE '%compra%' OR UPPER(h.asset_desc) LIKE '%CALL%' THEN 'call'
                        WHEN LOWER(h.tp_ativo) LIKE '%venda%' OR UPPER(h.asset_desc) LIKE '%PUT%' THEN 'put'
                        WHEN h.tp_ativo LIKE '%Opção de compra%' OR h.asset_desc LIKE 'OPCAO CALL%' THEN 'call'
                        WHEN h.tp_ativo LIKE '%Opção de venda%' OR h.asset_desc LIKE 'OPCAO PUT%' THEN 'put'
                        ELSE ''
                    END AS option_side,
                    CASE
                        WHEN h.tp_aplic LIKE '%lan%' THEN 'written'
                        WHEN h.tp_aplic LIKE '%titular%' THEN 'holder'
                        ELSE ''
                    END AS option_position_role
                FROM cvm_cda_holdings h
                WHERE h.month = ?
            )
        """

    def _b3_trend_csv_path(self) -> Path:
        return Path(Config.MACRO_DATA_DIR) / "funds_flow_local" / "derived" / "b3_trend_by_participant.csv"

    def _read_b3_participant_trends(self) -> list[dict[str, Any]]:
        path = self._b3_trend_csv_path()
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    rows.append({
                        "participant_type": row.get("participant_type"),
                        "date": row.get("date"),
                        "daily_net_flow_brl": self._num(row.get("daily_net_flow_brl")),
                        "rolling_5d_net_flow_brl": self._num(row.get("rolling_5d_net_flow_brl")),
                        "rolling_21d_net_flow_brl": self._num(row.get("rolling_21d_net_flow_brl")),
                        "buy_participation_pct": self._num(row.get("buy_participation_pct")),
                        "sell_participation_pct": self._num(row.get("sell_participation_pct")),
                    })
        except Exception as exc:
            logger.warning("Failed to read B3 participant trend CSV for CDA graph coherence: %s", exc)
            return []
        return rows

    @staticmethod
    def _chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
        for index in range(0, len(rows), size):
            yield rows[index:index + size]

    def _props(self, row: dict[str, Any]) -> dict[str, Any]:
        props = {}
        for key, value in row.items():
            cleaned = self._clean_value(value)
            if cleaned is not None:
                props[key] = cleaned
        return props

    @staticmethod
    def _clean_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                return None
            return value
        if isinstance(value, (list, tuple)):
            return [CvmCdaGraphService._clean_value(item) for item in value if CvmCdaGraphService._clean_value(item) is not None]
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _digits(value: Any) -> str:
        return re.sub(r"\D+", "", str(value or ""))

    @staticmethod
    def _clean_label(value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        return text if text else fallback

    @staticmethod
    def _num(value: Any) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    @staticmethod
    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        try:
            return int(value or 0) == 1
        except Exception:
            return False

    def _asset_key(self, row: dict[str, Any]) -> str:
        for key in ("asset_code", "isin", "asset_desc", "issuer_name"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        return f"{row.get('source_block') or 'CDA'}:{row.get('fund_cnpj') or ''}:{row.get('position_rank') or ''}"

    def _fund_id(self, month: str, cnpj: Any) -> str:
        return self._node_id(month, "fund", self._digits(cnpj))

    def _asset_id(self, month: str, security_key: str, asset_class: str) -> str:
        return self._node_id(month, "asset", security_key, asset_class)

    def _issuer_id(self, month: str, issuer_name: str, issuer_doc: str | None = None) -> str:
        return self._node_id(month, "issuer", issuer_doc or issuer_name)

    def _target_id(self, month: str, target: Any) -> str:
        return self._node_id(month, "target", target)

    def _node_id(self, month: str, node_type: str, *parts: Any) -> str:
        digest = self._hash(*parts)
        return f"cda:{month}:{node_type}:{digest}"

    def _edge_id(self, edge_type: str, *parts: Any) -> str:
        digest = self._hash(edge_type, *parts)
        return f"cda:edge:{digest}"

    @staticmethod
    def _hash(*parts: Any) -> str:
        raw = "|".join(str(part or "").strip().lower() for part in parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _month_label(month: str) -> str:
        text = re.sub(r"[^0-9]", "", str(month or ""))
        if len(text) == 6:
            return f"{text[:4]}-{text[4:]}"
        return str(month)

    @staticmethod
    def _fmt_brl(value: Any) -> str:
        try:
            number = float(value or 0)
        except Exception:
            number = 0
        abs_number = abs(number)
        sign = "-" if number < 0 else ""
        if abs_number >= 1e12:
            return f"{sign}R$ {abs_number / 1e12:.2f} tri"
        if abs_number >= 1e9:
            return f"{sign}R$ {abs_number / 1e9:.1f} bi"
        if abs_number >= 1e6:
            return f"{sign}R$ {abs_number / 1e6:.1f} mi"
        return f"{sign}R$ {abs_number:,.0f}"

    @staticmethod
    def _fmt_pct(value: Any) -> str:
        try:
            number = float(value or 0)
        except Exception:
            number = 0
        return f"{number:.2f}%"
