from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.domains.funds_flow.infrastructure import (
    AnbimaFundsFlowAdapter,
    B3FundsFlowAdapter,
    CvmFundsFlowAdapter,
    IciFundsFlowAdapter,
    source_http,
)
from app.services.funds_flow_local_service import FundsFlowLocalService


def _source_options(tmp_path: Path) -> dict[str, Any]:
    return {"raw_dir": str(tmp_path / "raw"), "timeout_seconds": 12.5}


def test_official_source_adapters_are_concrete_provider_implementations(
    tmp_path: Path,
) -> None:
    options = _source_options(tmp_path)
    cvm = CvmFundsFlowAdapter(**options)
    anbima = AnbimaFundsFlowAdapter(**options)
    b3 = B3FundsFlowAdapter(**options)
    ici = IciFundsFlowAdapter(**options)

    assert [source.provider for source in (cvm, anbima, b3, ici)] == [
        "cvm",
        "anbima",
        "b3",
        "ici",
    ]
    assert all(not hasattr(source, "_backend") for source in (cvm, anbima, b3, ici))
    assert callable(cvm.load_informe_diario)
    assert callable(cvm.load_fund_registry)
    assert callable(anbima.load_funds)
    assert callable(b3.load_etfs)
    assert callable(b3.load_investor_participation)
    assert callable(b3.load_open_interest)
    assert callable(b3.load_monthly_investor_participation)
    assert callable(b3.load_market_data_report)
    assert callable(ici.load_global_flows)


def test_cvm_adapter_owns_informe_normalization(tmp_path: Path) -> None:
    adapter = CvmFundsFlowAdapter(raw_dir=str(tmp_path / "raw"), timeout_seconds=10.0)
    raw = pd.DataFrame(
        {
            "CNPJ_FUNDO": ["12.345.678/0001-90"],
            "DT_COMPTC": ["2026-08-18"],
            "VL_PATRIM_LIQ": ["1000,50"],
            "CAPTC_DIA": ["20,00"],
            "RESG_DIA": ["5,00"],
            "NR_COTST": [10],
        }
    )

    normalized = adapter._normalize_informe(raw)

    assert normalized.loc[0, "cnpj_fundo"] == "12345678000190"
    assert normalized.loc[0, "pl"] == 1000.5
    assert normalized.loc[0, "captacao"] == 20.0
    assert normalized.loc[0, "resgate"] == 5.0


def test_b3_and_ici_adapters_own_their_parsers(tmp_path: Path) -> None:
    options = _source_options(tmp_path)
    b3 = B3FundsFlowAdapter(**options)
    ici = IciFundsFlowAdapter(**options)

    assert b3._parse_b3_csv_number("1.234,56") == 1234.56
    assert ici._html_tables(
        "<table><tr><th>Segment</th><th>Value</th></tr><tr><td>ETF</td><td>10</td></tr></table>"
    ) == [[["Segment", "Value"], ["ETF", "10"]]]


def test_source_adapter_download_cache_is_local_and_force_aware(
    tmp_path: Path, monkeypatch: Any
) -> None:
    calls: list[str] = []

    class Response:
        content = b"official-source-data"

        @staticmethod
        def raise_for_status() -> None:
            return None

    def fake_get(url: str, *, timeout: float) -> Response:
        calls.append(f"{url}|{timeout}")
        return Response()

    monkeypatch.setattr(source_http.requests, "get", fake_get)
    adapter = CvmFundsFlowAdapter(raw_dir=str(tmp_path / "raw"), timeout_seconds=7.5)
    target = tmp_path / "raw" / "cvm" / "sample.zip"

    adapter._download("https://example.test/sample.zip", str(target), force=False)
    adapter._download("https://example.test/sample.zip", str(target), force=False)
    adapter._download("https://example.test/sample.zip", str(target), force=True)

    assert target.read_bytes() == b"official-source-data"
    assert calls == [
        "https://example.test/sample.zip|7.5",
        "https://example.test/sample.zip|7.5",
    ]


def test_funds_flow_service_accepts_replaceable_source_adapters(tmp_path: Path) -> None:
    cvm = object()
    anbima = object()
    b3 = object()
    ici = object()

    service = FundsFlowLocalService(
        root_dir=str(tmp_path),
        cvm_source=cvm,  # type: ignore[arg-type]
        anbima_source=anbima,  # type: ignore[arg-type]
        b3_source=b3,  # type: ignore[arg-type]
        ici_source=ici,  # type: ignore[arg-type]
    )

    assert service.cvm_source is cvm
    assert service.anbima_source is anbima
    assert service.b3_source is b3
    assert service.ici_source is ici
