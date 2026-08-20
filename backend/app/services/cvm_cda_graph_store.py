from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

from neo4j import GraphDatabase

from ..utils.logger import get_logger
from .cvm_cda_contracts import CDA_TARGET_LABELS

logger = get_logger("aquiles.cvm_cda_graph.store")


class CvmCdaGraphStoreMixin:
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
