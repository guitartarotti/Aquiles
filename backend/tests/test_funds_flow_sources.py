from __future__ import annotations

import json
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from app.domains.funds_flow.contracts.source_catalog import CFTC_COT_EXTRA_DATASETS
from app.services.funds_flow_local_service import FundsFlowLocalService


def _service(tmp_path: Path) -> FundsFlowLocalService:
    return FundsFlowLocalService(root_dir=str(tmp_path), timeout_seconds=1)


def test_anbima_rows_totals_and_validation_are_normalized(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = service.anbima_source
    frame = pd.DataFrame(
        [
            ["Data de Referencia: 17/08/2026"],
            ["Renda Fixa", 90, 100, 50, None, None, None, None, 1, 2, 3, 4],
            ["Renda Fixa", 90, 100, 50, None, None, None, None, 1, 2, 3, 4],
            ["Total Geral", 180, 200, 100, None, None, None, None, 2, 4, 6, 8],
        ]
    )

    rows = source._parse_anbima_consolidated_rows(
        frame,
        kind="category",
        first_block_only=False,
    )
    total = source._find_anbima_total(frame)
    validation = source.build_validation(
        pd.DataFrame(
            [
                {
                    "macro_classe": "Renda Fixa",
                    "pl_total": 110_000_000,
                    "captacao_liquida_total": 1_500_000,
                }
            ]
        ),
        {
            "consolidated_daily": {
                "reference_date": "2026-08-17",
                "categories": rows,
            }
        },
        as_of_date=date(2026, 8, 18),
    )

    assert len(rows) == 1
    assert rows[0]["aum_brl"] == 100_000_000
    assert rows[0]["macro_classe"] == "Renda Fixa"
    assert total["net_flow_month_brl"] == 4_000_000
    assert validation["status"] == "available"
    assert validation["rows"][0]["aum_diff_brl"] == 10_000_000
    assert source._extract_anbima_date(frame, "Data de Referencia") == date(2026, 8, 17)
    assert source._extract_anbima_period_label(pd.DataFrame([["Agosto/2026"]])) == "Agosto/2026"
    assert (
        source._find_anbima_sheet(["Resumo", "Tipo ANBIMA"], required_tokens=["TIPO ANBIMA"])
        == "Tipo ANBIMA"
    )
    assert source._html_to_text("Fluxo<br>liquido") == "Fluxo liquido"


def test_ici_weekly_worldwide_and_html_parsers(tmp_path: Path, monkeypatch) -> None:
    service = _service(tmp_path)
    source = service.ici_source
    weekly = pd.DataFrame(
        [
            ["Actual monthly"],
            [pd.Timestamp("2026-07-31"), 10, None, 4],
            ["Estimated weekly"],
            [pd.Timestamp("2026-08-07"), 12, None, 5],
        ]
    )
    monkeypatch.setattr(pd, "read_excel", lambda *_args, **_kwargs: weekly)

    records = source._parse_ici_weekly_file(
        "ici_etf.xls",
        vehicle="etf",
        source_url="https://example.test/ici.xls",
    )

    assert {row["frequency"] for row in records} == {"M", "W"}
    assert any(row["category_key"] == "total" and row["flow_usd_mn"] == 12 for row in records)
    assert source._ici_vehicle_label("combined") == "MF + ETF"
    assert source._slug_key("Equity / International") == "equity_international"
    assert source._usd_bn_to_mn("1.25") == 1_250
    assert source._safe_ici_number("US$ 2,345.50") == 2_345.5
    assert source._html_tables(
        "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
    ) == [[["A", "B"], ["1", "2"]]]

    worldwide = pd.DataFrame(
        [[None] * 8 for _ in range(7)] + [["Europe1", None, 100, 40], [None, "Brazil2", 20, 8]]
    )
    monkeypatch.setattr(pd, "read_excel", lambda *_args, **_kwargs: worldwide)
    rows = source._parse_ici_worldwide_sheet("worldwide.xlsx", sheet_name="Assets", prefix="assets")
    merged = source._merge_ici_worldwide_rows(
        [
            rows,
            [
                {
                    "key": "Europe1",
                    "level": "region",
                    "region": "Europe",
                    "fund_count_total_count": 5,
                }
            ],
        ]
    )

    assert rows[0]["region"] == "Europe"
    assert rows[1]["country"] == "Brazil"
    assert merged[0]["fund_count_total_count"] == 5
    assert source._extract_ici_worldwide_quarter("ww_q2_26_sample.xlsx") == "2026:Q2"


def _cftc_row() -> dict[str, str]:
    return {
        "report_date_as_yyyy_mm_dd": "2026-08-11",
        "contract_market_name": "BRAZILIAN REAL - CME",
        "cftc_contract_market_code": "102741",
        "commodity_group_name": "CURRENCY",
        "open_interest_all": "1000",
        "change_in_open_interest_all": "50",
        "tot_rept_positions_long_all": "800",
        "tot_rept_positions_short": "700",
        "lev_money_positions_long": "300",
        "lev_money_positions_short": "220",
        "change_in_lev_money_long": "20",
        "change_in_lev_money_short": "5",
        "pct_of_oi_lev_money_long": "30.0",
        "pct_of_oi_lev_money_short": "22.0",
        "traders_lev_money_long_all": "12",
        "traders_lev_money_short_all": "10",
    }


def test_cftc_tff_normalization_and_payload_summaries(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = _cftc_row()
    invalid = {"report_date_as_yyyy_mm_dd": "not-a-date"}
    combined = service._normalize_cftc_tff_rows([source, invalid], variant="combined")
    futures = service._normalize_cftc_tff_rows([source], variant="futures_only")
    payload = service._build_cftc_tff_payload(
        combined + futures,
        errors=[],
        latest_report_date=None,
    )

    assert len(combined) == 1
    assert combined[0]["asset_bucket"] == "FX"
    assert combined[0]["lev_money_net"] == 80
    assert combined[0]["lev_money_change_net"] == 15
    assert payload["status"] == "ok"
    assert payload["report_date"] == "2026-08-11"
    assert payload["publication_date"] == "2026-08-14"
    assert payload["participant_summary"]
    assert payload["position_matrix"]
    assert (
        service._build_cftc_tff_payload([], errors=["offline"], latest_report_date=None)["status"]
        == "error"
    )


def test_cftc_extra_families_build_extended_views(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = _cftc_row() | {
        "contract_market_name": "GOLD - COMEX",
        "commodity_group_name": "METALS",
        "m_money_positions_long_all": "400",
        "m_money_positions_short_all": "250",
        "change_in_m_money_long_all": "30",
        "change_in_m_money_short_all": "10",
        "pct_of_oi_m_money_long_all": "40",
        "pct_of_oi_m_money_short_all": "25",
    }
    config = CFTC_COT_EXTRA_DATASETS["disagg_combined"]
    rows = service._normalize_cftc_extra_rows(
        [source, {"report_date_as_yyyy_mm_dd": "bad"}],
        dataset_key="disagg_combined",
        config=config,
    )
    payload = service._build_cftc_extra_payload(
        rows,
        datasets=[{"key": "disagg_combined", "status": "ok"}],
        errors=[],
    )

    assert rows[0]["asset_bucket"] == "Metals"
    assert rows[0]["managed_money_net"] == 150
    assert payload["family_summaries"][0]["family"] == "disaggregated"
    assert payload["extended_contracts"]
    assert payload["position_matrix"]
    assert service._build_cftc_extra_payload([], datasets=[], errors=[])["family_summaries"] == []


def test_b3_monthly_market_report_and_numbers(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = service.b3_source
    raw = {
        "values": [["Investidor Estrangeiro", 100, 10, 20, 2, 30, 3, 5, 0.5, 10, 1, 165, 16.5]],
        "texts": [{"textPt": "Dados do mes anterior (Julho/2026)"}],
    }
    json_rows = source._normalize_b3_investor_participation_monthly(raw)
    csv_text = (
        "Tipos de investidores;A;B;C;D;E;F;G;H;I;J;K;L\n"
        "Investidores Individuais;100;10;20;2;30;3;5;0,5;10;1;165;16,5\n"
    )
    csv_rows = source._normalize_b3_investor_participation_monthly_csv(csv_text)

    lines = [
        "Relatorio Ate dia 17/08/2026 - previa",
        "Volume Total",
        "cabecalho",
        "Jul/2026;1.000,5;20;30;40;1.090,5",
        "fim",
        "Volume M",
        "cabecalho",
        "Jul/2026;50;1,5;10;2,0",
        "fim",
        "N\u00ba de Negocios Total",
        "cabecalho",
        "Jul/2026;100;20;30;5;155",
        "fim",
        "Movimenta\u00e7\u00e3o dos Investidores Estrangeiros Mensal",
        "cabecalho",
        "Jul/2026;100;80;0;20",
    ]
    market = source._parse_b3_market_data_report("\n".join(lines))

    assert json_rows[0]["participant_type"] == "Investidor Estrangeiro"
    assert csv_rows[0]["participant_type"] == "Investidores Individuais"
    assert source._extract_b3_monthly_period_label(raw) == "Julho/2026"
    assert (
        source._extract_b3_monthly_period_label_from_text("Previous month (July/2026).")
        == "July/2026"
    )
    assert market["summary"]["total_volume_brl_million"] == 1_090.5
    assert market["summary"]["foreign_balance_brl_million"] == 20
    assert source._parse_b3_csv_number("1.234,56%") == 1_234.56
    assert source._parse_b3_csv_number("-") is None


def test_b3_open_interest_json_csv_and_history(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = service.b3_source
    columns = [
        {"name": name}
        for name in [
            "TckrSymb",
            "ISIN",
            "Asst",
            "XprtnCd",
            "SgmtNm",
            "OpnIntrst",
            "VartnOpnIntrst",
            "LockedQty",
            "UnlockedQty",
        ]
    ]
    raw = {
        "columns": columns,
        "values": [
            ["WINQ26", "BRWIN", "WIN", "Q26", "Equity", 1000, 100, 10, 5],
            ["PETR4", "BRPETR", "PETR", "", "Cash", 500, 1, 0, 0],
        ],
    }
    rows = source._normalize_b3_open_interest_table(
        raw,
        request_date=date(2026, 8, 17),
        tracked_assets=["WIN"],
    )
    csv_text = (
        "Ticker symbol;ISIN code;Asset;Expiration code;Segment;Open interest;Variation open interest;Commodities locked qty;Unlocked qty by transfer\n"
        "WINQ26;BRWIN;WIN;Q26;Equity;1.200;150;10;5\n"
    )
    csv_rows = source._normalize_b3_open_interest_csv(
        csv_text,
        request_date=date(2026, 8, 18),
        tracked_assets=["WIN"],
    )
    history, products, contracts, futures = source._build_b3_open_interest_history(
        [
            {"date": "2026-08-17", "rows": rows},
            {"date": "2026-08-18", "rows": csv_rows},
        ],
        tracked_assets=["WIN"],
        min_points=21,
    )

    assert len(rows) == 1
    assert csv_rows[0]["open_interest"] == 1_200
    assert len(history) == 2
    assert products[0]["leader_contract"] == "WINQ26"
    assert contracts[0]["ticker"] == "WINQ26"
    assert futures[0]["asset"] == "WIN"
    assert (
        source._normalize_b3_open_interest_csv(
            "No results found", request_date=date.today(), tracked_assets=[]
        )
        == []
    )
    assert source._is_b3_future_contract("WINQ26", "WIN") is True
    assert source._is_b3_future_contract("PETR4", "PETR") is False


def test_b3_participant_history_dedupes_and_computes_daily_flow(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = service.b3_source
    records = [
        {
            "publication_date": "2026-08-17",
            "data_until": "2026-08-14",
            "participants": [
                {
                    "participant_type": "Investidor Estrangeiro",
                    "buy_brl": 100,
                    "sell_brl": 80,
                    "net_flow_brl": 20,
                    "turnover_brl": 180,
                    "buy_participation_pct": 10,
                    "sell_participation_pct": 8,
                }
            ],
        },
        {
            "publication_date": "2026-08-18",
            "data_until": "2026-08-17",
            "participants": [
                {
                    "participant_type": "Investidor Estrangeiro",
                    "buy_brl": 160,
                    "sell_brl": 100,
                    "net_flow_brl": 60,
                    "turnover_brl": 260,
                    "buy_participation_pct": 12,
                    "sell_participation_pct": 9,
                }
            ],
        },
    ]
    duplicate = records[1] | {"publication_date": "2026-08-19"}
    deduped = source._dedupe_b3_records(records + [duplicate, {}])
    history, trends = source._build_b3_investor_history(deduped, min_points=21)

    assert len(deduped) == 2
    assert history[-1]["daily_net_flow_brl"] == 40
    assert trends[0]["rolling_5d_net_flow_brl"] == 40
    assert source._same_month("2026-08-01", "2026-08-31") is True
    assert source._same_month("2026-07-31", "2026-08-01") is False
    assert source._candidate_bdi_dates(date(2026, 8, 17), limit=3) == [
        date(2026, 8, 17),
        date(2026, 8, 14),
        date(2026, 8, 13),
    ]
    assert (
        source._normalize_b3_participant_label("Instituicoes Financeiras")
        == "Instituicoes Financeiras"
    )
    assert source._parse_b3_number("1.234,50") == 1_234.5
    assert (
        source._build_b3_bdi_opportunities({"economic_indicators": []})[3]["status"] == "candidate"
    )


def test_cvm_informe_and_master_normalization_resolve_duplicates(tmp_path: Path) -> None:
    service = _service(tmp_path)
    source = service.cvm_source
    informe = source._normalize_informe(
        pd.DataFrame(
            [
                {
                    "TP_FUNDO_CLASSE": "FI",
                    "CNPJ_FUNDO": "12.345.678/0001-90",
                    "ID_SUBCLASSE": None,
                    "DT_COMPTC": "2026-08-17",
                    "VL_PATRIM_LIQ": "100,5",
                    "CAPTC_DIA": "10,5",
                    "RESG_DIA": None,
                    "NR_COTST": "20",
                },
                {
                    "TP_FUNDO_CLASSE": "CLASSES - FIF",
                    "CNPJ_FUNDO_CLASSE": "12.345.678/0001-90",
                    "ID_SUBCLASSE": None,
                    "DT_COMPTC": "2026-08-17",
                    "VL_PATRIM_LIQ": "120,5",
                    "CAPTC_DIA": "12,5",
                    "RESG_DIA": "2,5",
                    "NR_COTST": "21",
                },
                {"CNPJ_FUNDO": "", "DT_COMPTC": "invalid"},
            ]
        )
    )
    master = source._normalize_master(
        pd.DataFrame(
            [
                {
                    "CNPJ_FUNDO": "12.345.678/0001-90",
                    "DENOM_SOCIAL": "Fundo Encerrado",
                    "CLASSE": "Acoes",
                    "SIT": "CANCELADO",
                },
                {
                    "CNPJ_FUNDO": "12.345.678/0001-90",
                    "DENOM_SOCIAL": "Fundo Atual",
                    "CLASSE": "Renda Fixa",
                    "SIT": "EM FUNCIONAMENTO NORMAL",
                },
            ]
        )
    )

    assert len(informe) == 1
    assert informe.iloc[0]["pl"] == 120.5
    assert informe.iloc[0]["resgate"] == 2.5
    assert informe.iloc[0]["series_id"] == "12345678000190"
    assert len(master) == 1
    assert master.iloc[0]["nome_fundo"] == "Fundo Atual"
    assert bool(master.iloc[0]["is_active"]) is True


def test_cvm_month_reader_and_range_loader_use_local_archives(tmp_path: Path, monkeypatch) -> None:
    service = _service(tmp_path)
    source = service.cvm_source
    archive_path = Path(source.raw_dir) / "cvm_informe" / "inf_diario_fi_202608.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    csv_data = (
        "CNPJ_FUNDO;DT_COMPTC;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST\n"
        "12.345.678/0001-90;2026-08-17;100,5;10;2;20\n"
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("inf_diario.csv", csv_data.encode("latin1"))

    monkeypatch.setattr(source, "_download", lambda *_args, **_kwargs: None)
    frame, status = source._read_informe_month(
        yyyymm="202608",
        url="https://example.test/informe.zip",
        force=False,
    )
    monkeypatch.setattr(
        source,
        "_discover_cvm_informe_resources",
        lambda: {"202608": "https://example.test/informe.zip"},
    )
    monkeypatch.setattr(source, "_read_informe_month", lambda **_kwargs: (frame, status))
    ranged, statuses = source.load_informe_diario(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 18),
        force=False,
    )

    assert status["ok"] is True
    assert status["latest_data_date"] == "2026-08-17"
    assert len(ranged) == 1
    assert statuses[0]["id"] == "cvm_informe_diario_202608"


def test_cache_history_and_cadastro_selection_rules(tmp_path: Path, monkeypatch) -> None:
    service = _service(tmp_path)
    snapshot = {
        "report": {
            "schema_version": 6,
            "period": "21d",
            "history_days": 95,
            "requested_date": "2026-08-17",
            "last_updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "etf_panel": {},
        "b3_etfs": {},
        "bcb_macro": {},
        "brazil_vs_global": {"ici_global_flows": {}, "cftc_positioning": {}},
    }
    Path(service.latest_path).parent.mkdir(parents=True, exist_ok=True)
    Path(service.latest_path).write_text(json.dumps(snapshot), encoding="utf-8")

    cached = service._fresh_cached_dashboard(
        target_date="2026-08-17",
        period="21d",
        history_days=90,
    )
    assert cached is not None
    assert cached["report"]["cache_status"] == "fresh"
    assert (
        service._fresh_cached_dashboard(target_date=None, period="63d", history_days=None) is None
    )
    assert service._resolve_history_days("invalid", period="63d") >= 78

    dates = pd.to_datetime(["2026-08-14"] * 120 + ["2026-08-17"] * 20)
    selection = pd.DataFrame(
        {
            "dt": dates,
            "cnpj_fundo": [f"{index:014d}" for index in range(len(dates))],
        }
    )
    assert service._select_complete_as_of_date(selection, date(2026, 8, 17)) == date(2026, 8, 14)

    legacy = pd.DataFrame([{"cnpj_fundo": "1", "nome_fundo": "Legacy", "macro_classe": "Acoes"}])
    modern = pd.DataFrame([{"cnpj_fundo": "1", "nome_fundo": "Modern", "macro_classe": "Acoes"}])
    source = service.cvm_source
    monkeypatch.setattr(
        source, "_load_legacy_registry", lambda **_kwargs: (legacy, {"ok": True, "latency_ms": 2})
    )
    monkeypatch.setattr(
        source, "_load_rcvm175_registry", lambda **_kwargs: (modern, {"ok": True, "latency_ms": 3})
    )
    master, status = source.load_fund_registry(force=False)

    assert master.iloc[0]["nome_fundo"] == "Modern"
    assert status["ok"] is True
    assert status["latency_ms"] == 5
