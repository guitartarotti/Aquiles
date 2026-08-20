"""Constants and policy tables shared by CVM CDA services."""

from __future__ import annotations

import os
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
CVM_CDA_SCHEMA_VERSION = 2
CVM_CDA_PACKAGE = "fi-doc-cda"
CVM_CKAN_PACKAGE_URL = "https://dados.cvm.gov.br/api/3/action/package_show"
CVM_CDA_PATTERN = "https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_{yyyymm}.zip"
CVM_CDA_DATASET_URL = "https://dados.cvm.gov.br/dataset/fi-doc-cda"

CDA_TARGET_LABELS = {
    "foreign": "Exterior",
    "public_bonds": "Titulos publicos",
    "private_credit": "Credito privado",
    "fund_quotas": "Cotas de fundos",
    "equity": "Acoes",
    "derivatives": "Derivativos",
    "confidential": "Confidencial",
}

CDA_TARGET_SQL = {
    "foreign": "is_foreign = 1",
    "public_bonds": "asset_class = 'Titulos Publicos'",
    "private_credit": "asset_class IN ('Credito Privado', 'Depositos e IF', 'Agronegocio/Credito')",
    "fund_quotas": "is_fund_quota = 1",
    "equity": "asset_class = 'Acoes'",
    "derivatives": "is_derivative = 1",
    "confidential": "is_confidential = 1",
}

HOLDING_NUMERIC_COLUMNS = (
    "qty_final",
    "value_market",
    "value_cost",
    "value_buy",
    "value_sell",
)

HOLDING_CORE_COLUMNS = (
    "month",
    "source_file",
    "source_block",
    "fund_type",
    "fund_cnpj",
    "fund_name",
    "dt_comptc",
    "tp_aplic",
    "tp_ativo",
    "tp_negoc",
    "asset_class",
    "asset_subclass",
    "asset_code",
    "asset_desc",
    "isin",
    "issuer_name",
    "issuer_doc",
    "risk_issuer",
    "country_code",
    "country",
    "market",
    "maturity_date",
    "maturity_bucket",
    "qty_final",
    "value_market",
    "value_cost",
    "value_buy",
    "value_sell",
    "is_confidential",
    "is_foreign",
    "is_fund_quota",
    "is_derivative",
    "is_related_issuer",
)

RADAR_BUCKET_META = {
    "Titulos Publicos": {
        "bucket": "sovereign_liquidity",
        "label": "Juros soberanos",
        "rank": 1,
        "saleability_share": 0.96,
    },
    "Depositos e IF": {
        "bucket": "cash_liquidity",
        "label": "Caixa e IF",
        "rank": 2,
        "saleability_share": 0.92,
    },
    "Acoes": {
        "bucket": "listed_equity",
        "label": "Bolsa local",
        "rank": 3,
        "saleability_share": 0.68,
    },
    "Investimento Exterior": {
        "bucket": "global_liquid",
        "label": "Exterior liquido",
        "rank": 4,
        "saleability_share": 0.58,
    },
    "Derivativos": {
        "bucket": "derivatives_overlay",
        "label": "Derivativos/margem",
        "rank": 5,
        "saleability_share": 0.32,
    },
    "Cotas de Fundos": {
        "bucket": "fund_quotas",
        "label": "Cotas de fundos",
        "rank": 6,
        "saleability_share": 0.38,
    },
    "Credito Privado": {
        "bucket": "private_credit",
        "label": "Credito privado",
        "rank": 7,
        "saleability_share": 0.24,
    },
    "Agronegocio/Credito": {
        "bucket": "structured_credit",
        "label": "Credito estruturado",
        "rank": 8,
        "saleability_share": 0.18,
    },
    "Fundos Estruturados": {
        "bucket": "structured_funds",
        "label": "Fundos estruturados",
        "rank": 9,
        "saleability_share": 0.14,
    },
    "Confidencial": {
        "bucket": "confidential",
        "label": "Confidencial",
        "rank": 10,
        "saleability_share": 0.05,
    },
    "Outros": {
        "bucket": "other_assets",
        "label": "Outros",
        "rank": 11,
        "saleability_share": 0.22,
    },
}

RADAR_DEFAULT_BUCKET = {
    "bucket": "other_assets",
    "label": "Outros",
    "rank": 11,
    "saleability_share": 0.20,
}

RADAR_DEFENSIVE_FLOOR = {
    "RENDA FIXA": 0.18,
    "MULTIMERCADO": 0.12,
    "ACOES": 0.38,
    "CAMBIAL": 0.32,
    "PREVIDENCIA": 0.18,
    "ETF": 0.48,
    "FII": 0.35,
    "FIDC": 0.45,
    "FIP": 0.62,
    "FIAGRO": 0.40,
    "OUTROS": 0.25,
    "UNCLASSIFIED": 0.25,
}

RADAR_SCENARIOS = (
    {
        "key": "base",
        "label": "Base",
        "description": "Usa a media de resgate bruto recente de 21 dias uteis.",
        "multiplier": 1.0,
    },
    {
        "key": "stress",
        "label": "Stress",
        "description": "Usa o pior ritmo bruto recente entre 5d e 21d, com margem adicional.",
        "multiplier": 1.2,
    },
    {
        "key": "extreme",
        "label": "Extremo",
        "description": "Amplifica o stress com ancora no dia mais forte de resgate bruto recente.",
        "multiplier": 1.55,
    },
)

RADAR_CONFIDENTIAL_SALEABILITY_DISCOUNT = 0.50
RADAR_PLAUSIBLE_HORIZON_DAYS = 30
RADAR_MIN_DAYS_SINCE_CDA = int(os.environ.get("CVM_CDA_RADAR_MIN_DAYS_SINCE_CDA", "29"))
RADAR_MIN_MONTH_ROWS = int(os.environ.get("CVM_CDA_RADAR_MIN_MONTH_ROWS", "100000"))
RADAR_PLAUSIBLE_BUCKET_SHARE = {
    "sovereign_liquidity": 0.18,
    "cash_liquidity": 0.70,
    "listed_equity": 0.14,
    "global_liquid": 0.12,
    "derivatives_overlay": 0.10,
    "fund_quotas": 0.06,
    "private_credit": 0.04,
    "structured_credit": 0.025,
    "structured_funds": 0.02,
    "confidential": 0.02,
    "other_assets": 0.05,
}

RADAR_CACHE_TTL_SECONDS = 1800
