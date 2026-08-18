from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app.services.funds_flow_insights import FundsFlowInsightAgent
from app.services.funds_flow_local_service import FundsFlowLocalService
from app.services.funds_flow_utils import (
    _classify_master_row,
    _clean_json,
    _max_iso_date_value,
    _max_iso_datetime_value,
    _money_brl,
    _money_usd_mn,
    _normalize_cnpj,
    _normalize_text,
    _parse_brazilian_date,
    _parse_date,
    _parse_iso,
    _pct,
    _period_to_window,
    _regime_from_pressure,
    _safe_div,
    _safe_float,
    _yyyymm_months,
)


def test_funds_flow_numeric_and_period_helpers_are_defensive() -> None:
    assert _safe_float("1,25") == 1.25
    assert _safe_float(float("nan")) is None
    assert _safe_div(25, 100) == 0.25
    assert _safe_div(25, 0) is None
    assert _period_to_window("3m") == 63
    assert _period_to_window("400d") == 252
    assert _period_to_window("invalid") == 21
    assert _regime_from_pressure(-2.2) == "stress"


def test_funds_flow_dates_and_json_values_are_normalized() -> None:
    assert _parse_brazilian_date("17/08/2026") == date(2026, 8, 17)
    assert _clean_json(
        {
            "date": pd.Timestamp("2026-08-17"),
            "count": np.int64(3),
            "invalid": np.float64(np.nan),
        }
    ) == {
        "date": "2026-08-17T00:00:00",
        "count": 3,
        "invalid": None,
    }


def test_fund_classification_prioritizes_official_fields() -> None:
    row = pd.Series(
        {
            "classe_cvm": "Fundo de Renda Fixa",
            "classe_anbima": "",
            "tipo_fundo": "Multimercado",
            "nome_fundo": "Exemplo",
        }
    )

    macro, label, strategy, confidence = _classify_master_row(row)

    assert (macro, label, strategy) == ("Renda Fixa", "Renda Fixa", "fixed_income")
    assert confidence == 0.96


def test_insight_agent_builds_a_deterministic_payload() -> None:
    payload = {
        "report": {"as_of_date": "2026-08-17", "sources": ["CVM"]},
        "kpis": {
            "net_flow_21d": -2_500_000,
            "flow_pct_pl_21d": -0.01,
            "pressure_index": -2.1,
            "industry_aum": 100_000_000,
            "total_shareholders": 1200,
        },
        "top_inflows": [{"name": "Fundo A", "net_flow_21d": 1_000_000}],
        "top_outflows": [{"name": "Fundo B", "net_flow_21d": -3_000_000}],
        "stress_panel": {"hhi_redemptions": 0.3},
    }

    result = FundsFlowInsightAgent().generate(payload)

    assert result["agent"] == "FundsFlowInsightAgent"
    assert len(result["quick_read"]) == 3
    assert "Fundo A" in result["top_inflows_comment"]
    assert "concentradas" in result["top_outflows_comment"]


def test_funds_flow_formatting_and_date_helpers_cover_boundaries() -> None:
    assert _parse_date("2026-08-17T12:30:00Z") == date(2026, 8, 17)
    assert _parse_date("not-a-date") is None
    assert _parse_iso("2026-08-17T12:30:00Z") == datetime(
        2026,
        8,
        17,
        12,
        30,
        tzinfo=timezone.utc,
    )
    assert _max_iso_date_value("2026-07-01", "2026-08-17") == "2026-08-17"
    assert _max_iso_datetime_value(
        "2026-08-17T10:00:00+00:00",
        "2026-08-17T12:00:00+00:00",
    ) == "2026-08-17T12:00:00+00:00"
    assert _yyyymm_months(date(2025, 12, 1), date(2026, 2, 1)) == [
        "202512",
        "202601",
        "202602",
    ]
    assert _normalize_cnpj("12.345.678/0001-90") == "12345678000190"
    assert _normalize_text(" Ações  e  Câmbio ") == "ACOES E CAMBIO"
    assert _money_brl(2_500_000_000) == "R$ 2.5 bi"
    assert _money_brl(-2_500_000) == "-R$ 2.5 mi"
    assert _money_usd_mn(1_500) == "US$ 1.5 bi"
    assert _pct(0.1234, 1) == "12.3%"


def _synthetic_funds_flow_frames() -> tuple[pd.DataFrame, pd.DataFrame, date]:
    dates = pd.date_range("2026-05-01", periods=80, freq="D")
    funds = (
        {
            "cnpj_fundo": "00000000000001",
            "nome_fundo": "Fundo Renda Fixa",
            "macro_classe": "Renda Fixa",
            "strategy_tag": "fixed_income",
            "captacao": 200.0,
            "resgate": 100.0,
        },
        {
            "cnpj_fundo": "00000000000002",
            "nome_fundo": "Fundo Acoes",
            "macro_classe": "Acoes",
            "strategy_tag": "equity",
            "captacao": 50.0,
            "resgate": 250.0,
        },
        {
            "cnpj_fundo": "00000000000003",
            "nome_fundo": "Fundo ETF",
            "macro_classe": "ETF",
            "strategy_tag": "listed_fund",
            "captacao": 300.0,
            "resgate": 100.0,
        },
    )

    informe_rows = []
    for day_index, timestamp in enumerate(dates):
        for fund_index, fund in enumerate(funds, start=1):
            informe_rows.append(
                {
                    "cnpj_fundo": fund["cnpj_fundo"],
                    "id_subclasse": "",
                    "dt": timestamp,
                    "vl_total": 100_000_000.0 + day_index * 10_000,
                    "vl_quota": 1.0 + day_index * 0.001 + fund_index * 0.0001,
                    "pl": 100_000_000.0 + day_index * 10_000 + fund_index * 1_000,
                    "captacao": fund["captacao"],
                    "resgate": fund["resgate"],
                    "cotistas": 1_000 + day_index + fund_index,
                }
            )

    master_rows = [
        {
            "cnpj_fundo": fund["cnpj_fundo"],
            "nome_fundo": fund["nome_fundo"],
            "classe_cvm": fund["macro_classe"],
            "macro_classe": fund["macro_classe"],
            "subclasse": fund["macro_classe"],
            "strategy_tag": fund["strategy_tag"],
            "administrador": "Administrador Teste",
            "gestor": f"Gestor {index}",
            "situacao": "EM FUNCIONAMENTO NORMAL",
            "data_registro": pd.Timestamp("2020-01-01"),
            "data_inicio": pd.Timestamp("2020-02-01"),
            "is_active": True,
            "classification_confidence": 0.96,
        }
        for index, fund in enumerate(funds, start=1)
    ]
    return pd.DataFrame(informe_rows), pd.DataFrame(master_rows), dates[-1].date()


def test_funds_flow_collection_pipeline_aggregates_and_caches_without_network(
    tmp_path: Path,
    monkeypatch,
) -> None:
    service = FundsFlowLocalService(root_dir=str(tmp_path), timeout_seconds=1)
    informe, master, target_date = _synthetic_funds_flow_frames()
    status = lambda source_id: {  # noqa: E731 - compact fixture factory
        "id": source_id,
        "ok": True,
        "rows": len(informe),
        "latest_data_date": target_date.isoformat(),
        "last_captured_at": "2026-08-17T12:00:00+00:00",
        "latency_ms": 1,
    }

    monkeypatch.setattr(
        service,
        "_load_informe_diario",
        lambda **_kwargs: (informe, [status("cvm_informe_diario_202607")]),
    )
    monkeypatch.setattr(service, "_select_complete_as_of_date", lambda *_args: target_date)
    monkeypatch.setattr(
        service,
        "_load_cadastro",
        lambda **_kwargs: (master, status("cvm_cadastro_fi")),
    )
    monkeypatch.setattr(
        service,
        "_load_anbima_funds",
        lambda **_kwargs: (
            {
                "status": "ok",
                "consolidated_daily": {
                    "reference_date": target_date.isoformat(),
                    "categories": [
                        {
                            "macro_classe": "Renda Fixa",
                            "name": "Renda Fixa",
                            "aum_brl": 100_000_000.0,
                            "net_flow_day_brl": 100.0,
                        }
                    ],
                },
            },
            status("anbima_funds"),
        ),
    )
    monkeypatch.setattr(
        service,
        "_load_ici_global_flows",
        lambda **_kwargs: (
            {
                "status": "ok",
                "weekly": {
                    "weekly_series": [
                        {
                            "date": target_date.isoformat(),
                            "category": "Equity",
                            "category_key": "equity",
                            "category_group": "equity",
                            "vehicle": "etf",
                            "vehicle_label": "ETF",
                            "flow_usd_mn": 25.0,
                            "frequency": "W",
                            "data_kind": "flow",
                        }
                    ],
                    "latest_by_vehicle": {"etf": {"categories": []}},
                },
            },
            status("ici_global_flows"),
        ),
    )

    empty_sources = {
        "_load_cftc_tff_positioning": ("cftc_tff", {"status": "not_loaded"}),
        "_load_b3_investor_participation": ("b3_investor_participation", {"status": "not_loaded"}),
        "_load_b3_open_interest": ("b3_open_interest", {"status": "not_loaded"}),
        "_load_b3_investor_participation_monthly": (
            "b3_investor_participation_monthly",
            {"status": "not_loaded"},
        ),
        "_load_b3_market_data_report": ("b3_market_data_report", {"status": "not_loaded"}),
        "_load_b3_etfs": ("b3_etfs", {"status": "not_loaded"}),
        "_load_bcb_macro": ("bcb_macro", {"status": "not_loaded"}),
    }
    for method_name, (source_id, source_payload) in empty_sources.items():
        monkeypatch.setattr(
            service,
            method_name,
            lambda _source_id=source_id, _payload=source_payload, **_kwargs: (
                _payload,
                status(_source_id),
            ),
        )

    payload = service.collect(
        target_date=target_date,
        period="21d",
        history_days=80,
        force=True,
    )

    assert payload["ok"] is True
    assert payload["report"]["as_of_date"] == target_date.isoformat()
    assert payload["kpis"]["net_flow_1d"] == 100.0
    assert payload["kpis"]["net_flow_21d"] == 2_100.0
    assert payload["stress_panel"]["funds_with_negative_flow"] == 1
    assert payload["top_inflows"][0]["name"] == "ETF"
    assert payload["top_outflows"][0]["name"] == "Acoes"
    assert payload["heatmap"]["x"]
    assert payload["heatmap"]["y"] == ["Acoes", "ETF", "Renda Fixa"]
    assert payload["etf_panel"]["local"]["summary"]["status"] == "ok"
    assert payload["anbima_funds"]["validation"]["status"] == "available"
    assert payload["ai_insights"]["agent"] == "FundsFlowInsightAgent"
    assert Path(service.latest_path).exists()
    assert (Path(service.derived_dir) / "industry_flow.csv").exists()

    cached = service.get_dashboard(
        target_date=target_date,
        period="21d",
        history_days=80,
    )
    assert cached["report"]["cache_status"] == "fresh"
    assert cached["kpis"] == payload["kpis"]
