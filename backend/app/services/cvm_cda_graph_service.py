from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Config
from ..utils.logger import get_logger
from .cvm_cda_contracts import CDA_TARGET_LABELS, CDA_TARGET_SQL
from .cvm_cda_graph_connections import CvmCdaGraphConnectionsMixin
from .cvm_cda_graph_formatting import CvmCdaGraphFormattingMixin
from .cvm_cda_graph_options import CvmCdaGraphOptionsMixin
from .cvm_cda_graph_portfolios import CvmCdaGraphPortfoliosMixin
from .cvm_cda_graph_store import CvmCdaGraphStoreMixin
from .cvm_cda_service import CvmCdaService

logger = get_logger("aquiles.cvm_cda_graph")


class CvmCdaGraphService(
    CvmCdaGraphOptionsMixin,
    CvmCdaGraphPortfoliosMixin,
    CvmCdaGraphConnectionsMixin,
    CvmCdaGraphStoreMixin,
    CvmCdaGraphFormattingMixin,
):
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
            for _index, row in enumerate(rows, start=1):
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
