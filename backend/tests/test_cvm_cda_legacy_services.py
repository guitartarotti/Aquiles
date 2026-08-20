from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from app.services.cvm_cda_graph_service import CvmCdaGraphService
from app.services.cvm_cda_service import CvmCdaService

MONTH = "202607"


def _insert(con: sqlite3.Connection, table: str, **values: Any) -> None:
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    con.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def _seed_cda(service: CvmCdaService) -> None:
    service.init_db()
    with service._connect() as con:
        _insert(
            con,
            "cvm_cda_months",
            month=MONTH,
            source_url="https://example.test/cda.zip",
            source_last_modified="2026-08-10T10:00:00Z",
            imported_at="2026-08-10T11:00:00Z",
            status="ready",
            schema_version=1,
            file_count=2,
            total_rows=6,
            latest_dt="2026-07-31",
            total_pl=300_000_000,
            total_position_value=210_000_000,
            total_confidential_value=5_000_000,
            metadata_json=json.dumps({"fixture": True}),
        )
        _insert(
            con,
            "cvm_cda_file_manifest",
            month=MONTH,
            source_file="cda_fi_BLC_4_202607.csv",
            source_block="BLC_4",
            row_count=6,
            column_count=12,
            file_size_bytes=2048,
            loaded_at="2026-08-10T11:00:00Z",
            columns_json="[]",
        )
        _insert(
            con,
            "cvm_cda_ingest_logs",
            month=MONTH,
            event_at="2026-08-10T11:00:00Z",
            level="info",
            message="fixture imported",
            detail_json="{}",
        )

        funds = [
            ("11111111000111", "Fundo Alpha", "FIF / Acoes", 200_000_000),
            ("22222222000122", "Fundo Beta", "FIF / Multimercado", 100_000_000),
        ]
        for cnpj, name, fund_type, pl in funds:
            _insert(
                con,
                "cvm_cda_fund_pl",
                month=MONTH,
                fund_type=fund_type,
                fund_cnpj=cnpj,
                fund_name=name,
                dt_comptc="2026-07-31",
                pl=pl,
            )
            _insert(
                con,
                "cvm_cda_fund_summary",
                month=MONTH,
                fund_cnpj=cnpj,
                fund_name=name,
                fund_type=fund_type,
                dt_comptc="2026-07-31",
                pl=pl,
                holding_count=3,
                issuer_count=3,
                asset_count=3,
                position_value=pl * 0.7,
                abs_position_value=pl * 0.75,
                foreign_value=pl * 0.1,
                public_bond_value=0,
                private_credit_value=pl * 0.15,
                fund_quota_value=pl * 0.2,
                equity_value=pl * 0.35,
                derivative_value=-pl * 0.05,
                confidential_value=0,
                related_issuer_value=0,
                buy_value=pl * 0.03,
                sell_value=pl * 0.02,
                max_position_value=pl * 0.35,
                concentration_pct=35,
                foreign_pct_pl=10,
                private_credit_pct_pl=15,
                confidential_pct_pl=0,
                turnover_pct_pl=5,
            )

        holdings = [
            {
                "fund_cnpj": funds[0][0], "fund_name": funds[0][1], "fund_type": funds[0][2],
                "asset_class": "Acoes", "asset_subclass": "Acoes locais", "asset_code": "PETR4",
                "asset_desc": "PETROBRAS PN", "isin": "BRPETRACNPR6", "issuer_name": "Petrobras",
                "issuer_doc": "33000167000101", "country": "Brasil", "country_code": "BR",
                "value_market": 70_000_000, "qty_final": 500_000, "is_foreign": 0,
                "is_fund_quota": 0, "is_derivative": 0, "tp_aplic": "Acoes",
            },
            {
                "fund_cnpj": funds[0][0], "fund_name": funds[0][1], "fund_type": funds[0][2],
                "asset_class": "Derivativos", "asset_subclass": "Opcoes", "asset_code": "PETRA320",
                "asset_desc": "Opcao de compra PETR4", "issuer_name": "B3", "country": "Brasil",
                "country_code": "BR", "value_market": -10_000_000, "qty_final": -5000,
                "is_foreign": 0, "is_fund_quota": 0, "is_derivative": 1, "tp_aplic": "Lancador",
            },
            {
                "fund_cnpj": funds[0][0], "fund_name": funds[0][1], "fund_type": funds[0][2],
                "asset_class": "Cotas de Fundos", "asset_subclass": "Fundo local",
                "asset_code": "33333333000133", "asset_desc": "Fundo Gamma", "issuer_name": "Fundo Gamma",
                "issuer_doc": "33333333000133", "country": "Brasil", "country_code": "BR",
                "value_market": 40_000_000, "qty_final": 1, "is_foreign": 0,
                "is_fund_quota": 1, "is_derivative": 0, "tp_aplic": "Cota",
            },
            {
                "fund_cnpj": funds[1][0], "fund_name": funds[1][1], "fund_type": funds[1][2],
                "asset_class": "Investimento Exterior", "asset_subclass": "Equity US",
                "asset_code": "AAPL", "asset_desc": "Apple Inc", "issuer_name": "Apple",
                "country": "Estados Unidos", "country_code": "US", "value_market": 20_000_000,
                "qty_final": 10000, "is_foreign": 1, "is_fund_quota": 0,
                "is_derivative": 0, "tp_aplic": "Equity",
            },
            {
                "fund_cnpj": funds[1][0], "fund_name": funds[1][1], "fund_type": funds[1][2],
                "asset_class": "Credito Privado", "asset_subclass": "Debenture",
                "asset_code": "DEB123", "asset_desc": "Debenture Energia", "issuer_name": "Energia SA",
                "issuer_doc": "44444444000144", "country": "Brasil", "country_code": "BR",
                "value_market": 30_000_000, "qty_final": 1000, "is_foreign": 0,
                "is_fund_quota": 0, "is_derivative": 0, "tp_aplic": "Debenture",
            },
        ]
        for row in holdings:
            _insert(
                con,
                "cvm_cda_holdings",
                month=MONTH,
                source_file="fixture.csv",
                source_block="BLC_4",
                dt_comptc="2026-07-31",
                value_cost=row["value_market"],
                value_buy=1_000_000,
                value_sell=500_000,
                is_confidential=0,
                is_related_issuer=0,
                **row,
            )

        targets = [
            (funds[0], "derivatives", "Derivativos", 0, 10_000_000, -10_000_000, 10_000_000),
            (funds[0], "fund_quotas", "Cotas de Fundos", 40_000_000, 0, 40_000_000, 40_000_000),
            (funds[1], "foreign", "Exterior", 20_000_000, 0, 20_000_000, 20_000_000),
            (funds[1], "private_credit", "Credito Privado", 30_000_000, 0, 30_000_000, 30_000_000),
        ]
        for fund, target, label, long_value, short_value, net_value, gross_value in targets:
            cnpj, name, fund_type, pl = fund
            _insert(
                con,
                "cvm_cda_fund_target_exposure",
                month=MONTH, target=target, target_label=label, fund_cnpj=cnpj,
                fund_name=name, fund_type=fund_type, dt_comptc="2026-07-31", pl=pl,
                long_value=long_value, short_value=short_value, net_value=net_value,
                gross_value=gross_value, target_pct_pl=gross_value / pl * 100,
                holdings_count=1, issuers_count=1, assets_count=1, top_issuer=name,
                top_asset_class=label, concentration_pct=100,
            )

        for row in holdings:
            if row["asset_code"] not in {"AAPL", "DEB123"}:
                continue
            target = "foreign" if row["asset_code"] == "AAPL" else "private_credit"
            _insert(
                con,
                "cvm_cda_asset_target_exposure",
                month=MONTH, target=target, target_label=target, security_key=row["asset_code"],
                issuer_name=row["issuer_name"], asset_desc=row["asset_desc"],
                asset_class=row["asset_class"], country=row["country"],
                long_value=row["value_market"], short_value=0, net_value=row["value_market"],
                gross_value=abs(row["value_market"]), fund_count=1, holding_count=1,
            )

        for dimension, key, label, value in (
            ("asset_class", "acoes", "Acoes", 70_000_000),
            ("asset_class", "credito", "Credito Privado", 30_000_000),
            ("fund_type", "fif_acoes", "FIF / Acoes", 140_000_000),
            ("country", "br", "Brasil", 130_000_000),
            ("issuer", "petrobras", "Petrobras", 70_000_000),
            ("security", "petr4", "PETR4", 70_000_000),
            ("maturity_bucket", "sem", "sem vencimento", 100_000_000),
            ("related_issuer", "false", "Nao relacionado", 100_000_000),
            ("asset_subclass", "local", "Local", 100_000_000),
        ):
            _insert(
                con,
                "cvm_cda_summary_group",
                month=MONTH, dimension=dimension, key=key, label=label,
                row_count=1, fund_count=1, value=value, abs_value=abs(value),
                share_value_pct=50, extra_json="{}",
            )


def test_cvm_cda_dashboard_queries_and_validation_use_real_sqlite(tmp_path: Path) -> None:
    service = CvmCdaService(data_dir=str(tmp_path))
    assert service.get_dashboard()["ok"] is False
    _seed_cda(service)

    status = service.status()
    assert status["ok"] is True
    assert status["latest_month"] == MONTH
    dashboard = service.get_dashboard("latest")
    assert dashboard["kpis"]["funds"] == 2
    assert dashboard["kpis"]["holdings"] == 5
    assert dashboard["top_funds"][0]["fund_name"] == "Fundo Alpha"
    assert dashboard["ai_readiness"]

    funds = service.list_funds(target="foreign", side="long", month=MONTH)
    assets = service.list_assets(target="foreign", side="net", month=MONTH)
    holdings = service.list_fund_holdings(
        "22222222000122", target="foreign", side="all", month=MONTH
    )
    assert funds["rows"][0]["rank"] == 1
    assert assets["rows"][0]["security_key"] == "AAPL"
    assert holdings["rows"][0]["country"] == "Estados Unidos"
    assert service.get_positioning_lab(MONTH)["concentration"]

    assert service._normalize_target("external") == "foreign"
    assert service._normalize_side("all", allow_all=True) == "all"
    assert service._pagination(-1, 999, max_per_page=100) == (1, 100, 0)
    assert service._resolve_month(service._connect(), "latest") == MONTH
    assert service._estimate_current_pl(100, 120, -10) == 120
    assert service._defensive_floor_pct("FIF / Renda Fixa") > 0
    assert service._scenario_daily_outflow(
        pd.Series({"daily_outflow_base": 1000}), scenario_key="base", multiplier=0.1
    ) == 100
    assert service._radar_coverage_flag(
        pd.Series({"runway_days_stress": 4, "inventory_burn_pct": 0.5})
    ) == "critico"

    with pytest.raises(ValueError, match="fund_cnpj"):
        service.list_fund_holdings("")
    assert service.list_funds(target="unknown")["target"] == "foreign"
    assert service.list_assets(side="unknown")["side"] == "long"


def test_cvm_cda_graph_reads_relational_portfolios_and_builds_dry_run(tmp_path: Path) -> None:
    cda = CvmCdaService(data_dir=str(tmp_path))
    _seed_cda(cda)
    graph = CvmCdaGraphService(cda_data_dir=str(tmp_path), group_id="fixture")

    dry_run = graph.build_graph(
        month=MONTH,
        dry_run=True,
        max_funds=20,
        max_positions_per_fund=20,
        min_abs_value=0,
        target_funds_per_theme=10,
    )
    assert dry_run["ok"] is True
    assert dry_run["counts"]["funds"] == 2
    assert dry_run["counts"]["positions"] == 5

    with graph._connect_cda() as con:
        assert graph._fetch_month_row(con, MONTH)["month"] == MONTH
        assert len(graph._fetch_fund_nodes(con, MONTH, ["11111111000111"])) == 1
        assert graph._fetch_target_edges(con, MONTH, ["11111111000111"])
        assert graph._fetch_position_rows(
            con, MONTH, ["11111111000111"], max_positions_per_fund=20, min_abs_value=0
        )
        assert graph._fetch_option_triangulation(con, MONTH, limit=20)
        assert graph._fetch_portfolio_similarity(con, MONTH, limit=20)
        assert graph._fetch_participant_asset_coherence(con, MONTH, limit=20)
        assert isinstance(graph._fetch_explanatory_connections(con, MONTH, limit=20), list)
        assert isinstance(graph._fetch_activity_layers(con, MONTH), list)
        assert isinstance(graph._fetch_asset_class_activity(con, MONTH, limit=20), list)
        assert isinstance(graph._fetch_fund_quota_breakdown(con, MONTH, limit=20), list)
        assert graph._fetch_target_flow_details(con, MONTH, limit=20)
        trails = graph._fetch_asset_trails(con, MONTH, limit=20)
        assert trails
        assert graph._fetch_asset_trail_detail(
            con, MONTH, asset_key="PETR4", asset_class="Acoes", side="long", limit=20
        )
        assert graph._fetch_asset_lenses(con, MONTH, limit=20)

    assert graph.schema()["graph"]["type"] == "deterministic_neo4j_graph"
    assert graph.fund_network("11111111000111", month="missing")["ok"] is False
    assert graph.issuer_crowding(month="missing")["rows"] == []
    assert graph.money_trails(month="missing")["layers"] == []
