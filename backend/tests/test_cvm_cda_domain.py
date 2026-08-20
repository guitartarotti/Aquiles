from __future__ import annotations

from datetime import date, timedelta, timezone

import pytest

from app.domains.market_data.domain.cvm_cda import (
    CdaRemoteMonth,
    asset_class_for,
    clamp,
    first_nonempty,
    maturity_bucket,
    month_from_text,
    month_label,
    normalize_key,
    normalize_text,
    parse_date_text,
    parse_iso_datetime,
    previous_months,
    safe_div,
    safe_float,
    source_block,
)


def test_month_helpers_cover_discovery_labels_and_year_boundaries() -> None:
    assert month_from_text("cda_fi_202512.zip") == "202512"
    assert month_from_text("cda_fi_202513.zip") is None
    assert month_label("202601") == "2026-01"
    assert month_label(None) == "-"
    assert previous_months("202601", 3) == ["202601", "202512", "202511"]
    assert previous_months("invalid", 3) == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1,234.50", 1234.5), (None, 0.0), ("nan", 0.0), ("invalid", 0.0)],
)
def test_safe_float_normalizes_external_numeric_values(value: object, expected: float) -> None:
    assert safe_float(value) == expected


def test_numeric_rules_handle_zero_denominators_and_bounds() -> None:
    assert safe_div("12", "3") == 4.0
    assert safe_div(12, 0, default=999.0) == 999.0
    assert clamp("1.5", 0.0, 1.0) == 1.0
    assert clamp("-1", 0.0, 1.0) == 0.0


def test_date_parsers_are_tolerant_and_make_naive_datetimes_explicitly_utc() -> None:
    assert parse_date_text("2026-08-20T12:30:00") == date(2026, 8, 20)
    assert parse_date_text("not-a-date") is None

    parsed_utc = parse_iso_datetime("2026-08-20T12:30:00Z")
    parsed_naive = parse_iso_datetime("2026-08-20T12:30:00")
    assert parsed_utc is not None and parsed_utc.utcoffset() == timedelta(0)
    assert parsed_naive is not None and parsed_naive.tzinfo == timezone.utc
    assert parse_iso_datetime("not-a-date") is None


def test_text_rules_normalize_source_values_without_provider_dependencies() -> None:
    assert normalize_text("  Fundo\xa0  XP  ") == "Fundo XP"
    assert normalize_key("Acoes / BDR") == "ACOES BDR"
    assert first_nonempty([None, "  ", " Fundo A "]) == "Fundo A"
    assert first_nonempty([], default="Unclassified") == "Unclassified"


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("cda_fie_confid_202601.csv", "FIE_CONFID"),
        ("cda_confid_202601.csv", "CONFID"),
        ("cda_fi_BLC_3_202601.csv", "BLC_3"),
        ("cda_fie_202601.csv", "FIE"),
        ("other.csv", "CDA"),
    ],
)
def test_source_block_classifies_cvm_files(file_name: str, expected: str) -> None:
    assert source_block(file_name) == expected


@pytest.mark.parametrize(
    ("block", "application", "asset_type", "description", "expected"),
    [
        ("BLC_1", "", "", "", "Titulos Publicos"),
        ("CDA", "", "", "Cota de fundo", "Cotas de Fundos"),
        ("CDA", "", "", "Contrato futuro", "Derivativos"),
        ("CDA", "", "", "Acoes BDR", "Acoes"),
        ("CDA", "CDB", "", "", "Depositos e IF"),
        ("CDA", "", "CRA", "", "Agronegocio/Credito"),
        ("CDA", "", "", "Ativo offshore", "Investimento Exterior"),
        ("CDA", "Debenture", "", "", "Credito Privado"),
        ("CDA", "", "", "Desconhecido", "Outros"),
    ],
)
def test_asset_classification_is_a_pure_domain_rule(
    block: str,
    application: str,
    asset_type: str,
    description: str,
    expected: str,
) -> None:
    assert asset_class_for(block, application, asset_type, description) == expected


@pytest.mark.parametrize(
    ("maturity", "expected"),
    [
        ("2025-12-31", "vencido/indefinido"),
        ("2026-12-31", "0-1y"),
        ("2028-12-01", "1-3y"),
        ("2031-01-01", "3-5y"),
        ("2032-12-01", "5-7y"),
        ("2036-01-01", "7-10y"),
        ("2050-01-01", "10-30y"),
        ("2060-01-01", "30y+"),
        ("invalid", "sem vencimento"),
    ],
)
def test_maturity_bucket_preserves_cda_horizon_rules(maturity: str, expected: str) -> None:
    assert maturity_bucket(maturity, "2026-01-01") == expected


def test_remote_month_contract_has_a_stable_serialized_shape() -> None:
    remote = CdaRemoteMonth(
        month="202601",
        url="https://example.test/cda.zip",
        name="cda.zip",
        last_modified="2026-02-10T12:00:00Z",
    )

    assert remote.as_dict() == {
        "month": "202601",
        "label": "2026-01",
        "url": "https://example.test/cda.zip",
        "name": "cda.zip",
        "last_modified": "2026-02-10T12:00:00Z",
    }
