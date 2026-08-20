"""Read-side portfolio queries for CVM CDA data."""

from __future__ import annotations

from typing import Any

from .cvm_cda_contracts import CDA_TARGET_LABELS, CDA_TARGET_SQL


class CvmCdaQueriesMixin:
    def list_funds(
        self,
        *,
        target: str = "foreign",
        side: str = "long",
        month: str | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        target = self._normalize_target(target)
        side = self._normalize_side(side)
        page, per_page, offset = self._pagination(page, per_page, max_per_page=100)
        order_col = {"long": "long_value", "short": "short_value", "net": "net_value"}[side]
        filter_sql = {
            "long": "AND COALESCE(long_value, 0) > 0",
            "short": "AND COALESCE(short_value, 0) > 0",
            "net": "AND ABS(COALESCE(net_value, 0)) > 0",
        }[side]
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_month(con, month)
            if not resolved:
                return {
                    "ok": False,
                    "success": False,
                    "error": "CVM CDA database is empty.",
                    "rows": [],
                }
            total = con.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM cvm_cda_fund_target_exposure
                WHERE month = ? AND target = ?
                {filter_sql}
                """,
                (resolved, target),
            ).fetchone()["total"]
            rows = [
                dict(row)
                for row in con.execute(
                    f"""
                SELECT
                    fund_cnpj, target, target_label, fund_name, fund_type, dt_comptc, pl,
                    long_value, short_value, net_value, gross_value, target_pct_pl,
                    holdings_count, issuers_count, assets_count, top_issuer, top_asset_class,
                    concentration_pct, {order_col} AS selected_value
                FROM cvm_cda_fund_target_exposure
                WHERE month = ? AND target = ?
                {filter_sql}
                ORDER BY {order_col} DESC
                LIMIT ? OFFSET ?
                """,
                    (resolved, target, per_page, offset),
                ).fetchall()
            ]
            for index, row in enumerate(rows, start=offset + 1):
                row["rank"] = index
            return {
                "ok": True,
                "success": True,
                "month": resolved,
                "target": target,
                "target_label": CDA_TARGET_LABELS[target],
                "side": side,
                "page": page,
                "per_page": per_page,
                "total": total,
                "rows": rows,
            }

    def list_assets(
        self,
        *,
        target: str = "foreign",
        side: str = "long",
        month: str | None = None,
        page: int = 1,
        per_page: int = 25,
    ) -> dict[str, Any]:
        target = self._normalize_target(target)
        side = self._normalize_side(side)
        page, per_page, offset = self._pagination(page, per_page, max_per_page=100)
        order_col = {"long": "long_value", "short": "short_value", "net": "net_value"}[side]
        filter_sql = {
            "long": "AND COALESCE(long_value, 0) > 0",
            "short": "AND COALESCE(short_value, 0) > 0",
            "net": "AND ABS(COALESCE(net_value, 0)) > 0",
        }[side]
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_month(con, month)
            if not resolved:
                return {
                    "ok": False,
                    "success": False,
                    "error": "CVM CDA database is empty.",
                    "rows": [],
                }
            total = con.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM cvm_cda_asset_target_exposure
                WHERE month = ? AND target = ?
                {filter_sql}
                """,
                (resolved, target),
            ).fetchone()["total"]
            rows = [
                dict(row)
                for row in con.execute(
                    f"""
                SELECT
                    security_key, issuer_name, asset_desc, asset_class, country,
                    long_value, short_value, net_value, gross_value, fund_count, holding_count,
                    {order_col} AS selected_value
                FROM cvm_cda_asset_target_exposure
                WHERE month = ? AND target = ?
                {filter_sql}
                ORDER BY {order_col} DESC
                LIMIT ? OFFSET ?
                """,
                    (resolved, target, per_page, offset),
                ).fetchall()
            ]
            for index, row in enumerate(rows, start=offset + 1):
                row["rank"] = index
            return {
                "ok": True,
                "success": True,
                "month": resolved,
                "target": target,
                "target_label": CDA_TARGET_LABELS[target],
                "side": side,
                "page": page,
                "per_page": per_page,
                "total": total,
                "rows": rows,
            }

    def list_fund_holdings(
        self,
        fund_cnpj: str,
        *,
        target: str = "foreign",
        side: str = "all",
        month: str | None = None,
        page: int = 1,
        per_page: int = 40,
    ) -> dict[str, Any]:
        fund_cnpj = str(fund_cnpj or "").strip()
        if not fund_cnpj:
            raise ValueError("fund_cnpj is required")
        target = self._normalize_target(target)
        side = self._normalize_side(side, allow_all=True)
        page, per_page, offset = self._pagination(page, per_page, max_per_page=120)
        condition = CDA_TARGET_SQL[target]
        side_filter = ""
        if side == "long":
            side_filter = "AND COALESCE(value_market, 0) > 0"
        elif side == "short":
            side_filter = "AND COALESCE(value_market, 0) < 0"
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_month(con, month)
            if not resolved:
                return {
                    "ok": False,
                    "success": False,
                    "error": "CVM CDA database is empty.",
                    "rows": [],
                }
            total = con.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM cvm_cda_holdings
                WHERE month = ? AND fund_cnpj = ? AND ({condition}) {side_filter}
                """,
                (resolved, fund_cnpj),
            ).fetchone()["total"]
            fund = con.execute(
                "SELECT * FROM cvm_cda_fund_summary WHERE month = ? AND fund_cnpj = ?",
                (resolved, fund_cnpj),
            ).fetchone()
            rows = [
                dict(row)
                for row in con.execute(
                    f"""
                SELECT
                    source_block, fund_cnpj, fund_name, dt_comptc, tp_aplic, tp_ativo,
                    asset_class, asset_subclass, asset_code, asset_desc, isin,
                    issuer_name, issuer_doc, country, maturity_date, maturity_bucket,
                    qty_final, value_market, value_cost, value_buy, value_sell,
                    is_confidential, is_foreign, is_related_issuer,
                    CASE WHEN COALESCE(value_market, 0) < 0 THEN 'short' ELSE 'long' END AS position_side
                FROM cvm_cda_holdings
                WHERE month = ? AND fund_cnpj = ? AND ({condition}) {side_filter}
                ORDER BY ABS(COALESCE(value_market, 0)) DESC
                LIMIT ? OFFSET ?
                """,
                    (resolved, fund_cnpj, per_page, offset),
                ).fetchall()
            ]
            for index, row in enumerate(rows, start=offset + 1):
                row["rank"] = index
            return {
                "ok": True,
                "success": True,
                "month": resolved,
                "target": target,
                "target_label": CDA_TARGET_LABELS[target],
                "side": side,
                "page": page,
                "per_page": per_page,
                "total": total,
                "fund": dict(fund) if fund else {"fund_cnpj": fund_cnpj},
                "rows": rows,
            }

    def get_positioning_lab(self, month: str | None = None) -> dict[str, Any]:
        self.init_db()
        with self._connect() as con:
            resolved = self._resolve_month(con, month)
            if not resolved:
                return {"ok": False, "success": False, "error": "CVM CDA database is empty."}
            heatmap = self._build_heatmap(con, resolved)
            class_mix = self._summary_rows(con, resolved, "asset_class", 18)
            fund_type_mix = self._summary_rows(con, resolved, "fund_type", 18)
            concentration = [
                dict(row)
                for row in con.execute(
                    """
                SELECT fund_cnpj, fund_name, fund_type, pl, max_position_value, concentration_pct,
                       foreign_pct_pl, private_credit_pct_pl, confidential_pct_pl, turnover_pct_pl
                FROM cvm_cda_fund_summary
                WHERE month = ?
                ORDER BY concentration_pct DESC
                LIMIT 80
                """,
                    (resolved,),
                ).fetchall()
            ]
            issuer_crowding = self._summary_rows(con, resolved, "issuer", 40)
            edge_funds = [
                dict(row)
                for row in con.execute(
                    """
                SELECT fund_cnpj, fund_name, fund_type, pl, foreign_pct_pl, private_credit_pct_pl,
                       confidential_pct_pl, concentration_pct,
                       (COALESCE(foreign_pct_pl, 0) * 0.35
                        + COALESCE(private_credit_pct_pl, 0) * 0.25
                        + COALESCE(confidential_pct_pl, 0) * 0.25
                        + COALESCE(concentration_pct, 0) * 0.15) AS edge_score
                FROM cvm_cda_fund_summary
                WHERE month = ?
                ORDER BY edge_score DESC
                LIMIT 40
                """,
                    (resolved,),
                ).fetchall()
            ]
            return {
                "ok": True,
                "success": True,
                "month": resolved,
                "heatmap": heatmap,
                "class_mix": class_mix,
                "fund_type_mix": fund_type_mix,
                "concentration": concentration,
                "issuer_crowding": issuer_crowding,
                "edge_funds": edge_funds,
            }
