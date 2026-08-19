from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

FUNDS_FLOW_LOCAL_SCHEMA_VERSION = 6

CVM_INFORME_PACKAGE = "fi-doc-inf_diario"
CVM_CADASTRO_PACKAGE = "fi-cad"
CVM_CKAN_PACKAGE_URL = "https://dados.cvm.gov.br/api/3/action/package_show"
CVM_INFORME_PATTERN = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_{yyyymm}.zip"
CVM_CADASTRO_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/cad_fi.csv"
CVM_REGISTRO_FUNDO_CLASSE_URL = "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip"
B3_BDI_PATTERN = "https://arquivos.b3.com.br/bdi/download/bdi/{iso_date}/BDI_02_{yyyymmdd}.pdf"
B3_BDI_TABLE_EXPORT_URL = "https://arquivos.b3.com.br/bdi/table/export"
B3_BDI_TABLE_EXPORT_CSV_URL = "https://arquivos.b3.com.br/bdi/table/export/csv"
B3_BDI_STRUCTURED_TABLES_START_DATE = date(2025, 12, 15)
B3_MARKET_DATA_REPORT_URL = "https://sistemaswebb3-listados.b3.com.br/marketDataProxy/MarketDataCall/GetDownloadMarketData/RELATORIO_DADOS_DE_MERCADO.csv"
B3_FUNDS_LISTED_SEARCH_URL = "https://sistemaswebb3-listados.b3.com.br/fundsListedProxy/Search"
B3_FUNDS_LISTED_PAGE_URL = "https://sistemaswebb3-listados.b3.com.br/fundsListedPage/ETF"
B3_ETF_FUND_TYPES = (
    ("ETF", "ETF Renda Variavel"),
    ("ETF-RF", "ETF Renda Fixa"),
    ("ETF-FII", "ETF FII"),
    ("ETF-CRIPTO", "ETF Cripto"),
    ("ETF-INT-RF", "ETF Renda Fixa Internacional"),
    ("ETF-MOEDA", "ETF Moeda"),
)
B3_DERIVATIVE_OPEN_INTEREST_TABLE = "OpenPositionsEquities"
B3_INVESTOR_PARTICIPATION_TABLE = "SharesInvesVolum"
B3_INVESTOR_PARTICIPATION_MONTHLY_TABLE = "SharesInvesVolumMonthly"
B3_DEFAULT_OPEN_INTEREST_ASSETS = ("DI1", "DOL", "WDO", "WIN", "IND", "DAP", "DDI")
B3_FUTURES_MONTH_CODES = set("FGHJKMNQUVXZ")
BCB_SGS_BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
BCB_PTAX_PERIOD_URL = (
    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
    "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)
BCB_SGS_SERIES = (
    {
        "key": "usdbrl_sgs",
        "code": 1,
        "label": "Dolar comercial venda",
        "unit": "BRL",
        "frequency": "daily",
        "group": "fx",
    },
    {
        "key": "selic_daily",
        "code": 11,
        "label": "Selic diaria efetiva",
        "unit": "% a.d.",
        "frequency": "daily",
        "group": "rates",
    },
    {
        "key": "selic_target",
        "code": 432,
        "label": "Selic meta",
        "unit": "% a.a.",
        "frequency": "daily",
        "group": "rates",
    },
    {
        "key": "ipca_monthly",
        "code": 433,
        "label": "IPCA mensal",
        "unit": "% m/m",
        "frequency": "monthly",
        "group": "inflation",
        "min_history_days": 540,
    },
)
ANBIMA_STRAPI_BASE_URL = "https://data-strapi.prd.anbima.com.br"
ANBIMA_PUBLICATION_POPULATE = "template,template.connected_documents.file,template.more_content,template.publication_document.file"
ANBIMA_CONSOLIDATED_DAILY_ENDPOINT = "/api/consolidado-diario-de-fundos-de-investimento"
ANBIMA_BOLETIM_HOME_ENDPOINT = "/api/api-home-boletim-de-fundos-de-investimento"
ANBIMA_BOLETIM_LIST_ENDPOINT = "/api/boletim-de-fundos-de-investimentos"
ANBIMA_RANKING_ADMIN_ENDPOINT = "/api/ranking-de-adm-de-fundo"
ANBIMA_RANKING_MANAGER_ENDPOINT = "/api/ranking-de-gestores-de-fundos-de-investimento"
ICI_BASE_URL = "https://www.ici.org"
ICI_WEEKLY_FLOW_URLS = {
    "mutual_fund": "https://www.ici.org/flows_data_{year}.xls",
    "etf": "https://www.ici.org/etf_flows_data_{year}.xls",
    "combined": "https://www.ici.org/combined_flows_data_{year}.xls",
}
ICI_MONTHLY_ETF_PAGE_URL = (
    "https://www.ici.org/research/statistics/exchange-traded-funds/"
    "monthly-exchangetraded-fund-assets"
)
ICI_WORLDWIDE_PAGE_URL = (
    "https://www.ici.org/research/statistics/mutual-funds/"
    "quarterly-worldwide-mutual-fund-market"
)
CFTC_TFF_RESOURCE_URLS = {
    "combined": "https://publicreporting.cftc.gov/resource/yw9f-hn96.json",
    "futures_only": "https://publicreporting.cftc.gov/resource/gpe5-46if.json",
}
CFTC_PRE_STORY_URL = "https://publicreporting.cftc.gov/stories/s/Commitments-of-Traders/r4w3-av2u/"
CFTC_EXTRA_HISTORY_WEEKS = 156
CFTC_COT_EXTRA_DATASETS = {
    "disagg_futures_only": {
        "family": "disaggregated",
        "family_label": "Disaggregated",
        "variant": "futures_only",
        "variant_label": "Futures only",
        "url": "https://publicreporting.cftc.gov/resource/72hh-3qpy.json",
        "role": "Commodity positioning by Producer/Merchant, Swap Dealers and Managed Money",
    },
    "disagg_combined": {
        "family": "disaggregated",
        "family_label": "Disaggregated",
        "variant": "combined",
        "variant_label": "Futures + Options Combined",
        "url": "https://publicreporting.cftc.gov/resource/kh3c-gbw2.json",
        "role": "Commodity positioning including futures and options",
    },
    "legacy_futures_only": {
        "family": "legacy",
        "family_label": "Legacy",
        "variant": "futures_only",
        "variant_label": "Futures only",
        "url": "https://publicreporting.cftc.gov/resource/6dca-aqww.json",
        "role": "Classic Commercial, Non-commercial and Nonreportable split",
    },
    "legacy_combined": {
        "family": "legacy",
        "family_label": "Legacy",
        "variant": "combined",
        "variant_label": "Futures + Options Combined",
        "url": "https://publicreporting.cftc.gov/resource/jun7-fc8e.json",
        "role": "Classic COT split including futures and options",
    },
    "supplemental_cit": {
        "family": "supplemental_cit",
        "family_label": "Supplemental CIT",
        "variant": "supplemental",
        "variant_label": "Commodity Index Trader",
        "url": "https://publicreporting.cftc.gov/resource/4zgm-a668.json",
        "role": "Commodity Index Trader positioning proxy",
    },
}
CFTC_TFF_FIELDS = (
    "report_date_as_yyyy_mm_dd",
    "yyyy_report_week_ww",
    "market_and_exchange_names",
    "contract_market_name",
    "cftc_contract_market_code",
    "cftc_market_code",
    "cftc_region_code",
    "cftc_commodity_code",
    "commodity_name",
    "commodity_group_name",
    "commodity_subgroup_name",
    "open_interest_all",
    "dealer_positions_long_all",
    "dealer_positions_short_all",
    "dealer_positions_spread_all",
    "asset_mgr_positions_long",
    "asset_mgr_positions_short",
    "asset_mgr_positions_spread",
    "lev_money_positions_long",
    "lev_money_positions_short",
    "lev_money_positions_spread",
    "other_rept_positions_long",
    "other_rept_positions_short",
    "other_rept_positions_spread",
    "tot_rept_positions_long_all",
    "tot_rept_positions_short",
    "nonrept_positions_long_all",
    "nonrept_positions_short_all",
    "change_in_open_interest_all",
    "change_in_dealer_long_all",
    "change_in_dealer_short_all",
    "change_in_dealer_spread_all",
    "change_in_asset_mgr_long",
    "change_in_asset_mgr_short",
    "change_in_asset_mgr_spread",
    "change_in_lev_money_long",
    "change_in_lev_money_short",
    "change_in_lev_money_spread",
    "change_in_other_rept_long",
    "change_in_other_rept_short",
    "change_in_other_rept_spread",
    "change_in_tot_rept_long_all",
    "change_in_tot_rept_short",
    "change_in_nonrept_long_all",
    "change_in_nonrept_short_all",
    "pct_of_oi_dealer_long_all",
    "pct_of_oi_dealer_short_all",
    "pct_of_oi_asset_mgr_long",
    "pct_of_oi_asset_mgr_short",
    "pct_of_oi_lev_money_long",
    "pct_of_oi_lev_money_short",
    "pct_of_oi_other_rept_long",
    "pct_of_oi_other_rept_short",
    "pct_of_oi_nonrept_long_all",
    "pct_of_oi_nonrept_short_all",
    "traders_tot_all",
    "traders_dealer_long_all",
    "traders_dealer_short_all",
    "traders_asset_mgr_long_all",
    "traders_asset_mgr_short_all",
    "traders_lev_money_long_all",
    "traders_lev_money_short_all",
    "traders_other_rept_long_all",
    "traders_other_rept_short",
    "traders_tot_rept_long_all",
    "traders_tot_rept_short_all",
    "conc_gross_le_4_tdr_long",
    "conc_gross_le_4_tdr_short",
    "conc_gross_le_8_tdr_long",
    "conc_gross_le_8_tdr_short",
    "conc_net_le_4_tdr_long_all",
    "conc_net_le_4_tdr_short_all",
    "conc_net_le_8_tdr_long_all",
    "conc_net_le_8_tdr_short_all",
    "contract_units",
    "futonly_or_combined",
)
CFTC_TFF_PARTICIPANTS = (
    ("dealer", "Dealer/Intermediary", "dealer_positions_long_all", "dealer_positions_short_all", "dealer_positions_spread_all", "change_in_dealer_long_all", "change_in_dealer_short_all", "pct_of_oi_dealer_long_all", "pct_of_oi_dealer_short_all", "traders_dealer_long_all", "traders_dealer_short_all"),
    ("asset_mgr", "Asset Manager/Institutional", "asset_mgr_positions_long", "asset_mgr_positions_short", "asset_mgr_positions_spread", "change_in_asset_mgr_long", "change_in_asset_mgr_short", "pct_of_oi_asset_mgr_long", "pct_of_oi_asset_mgr_short", "traders_asset_mgr_long_all", "traders_asset_mgr_short_all"),
    ("lev_money", "Leveraged Funds", "lev_money_positions_long", "lev_money_positions_short", "lev_money_positions_spread", "change_in_lev_money_long", "change_in_lev_money_short", "pct_of_oi_lev_money_long", "pct_of_oi_lev_money_short", "traders_lev_money_long_all", "traders_lev_money_short_all"),
    ("other_rept", "Other Reportables", "other_rept_positions_long", "other_rept_positions_short", "other_rept_positions_spread", "change_in_other_rept_long", "change_in_other_rept_short", "pct_of_oi_other_rept_long", "pct_of_oi_other_rept_short", "traders_other_rept_long_all", "traders_other_rept_short"),
    ("nonrept", "Nonreportables", "nonrept_positions_long_all", "nonrept_positions_short_all", None, "change_in_nonrept_long_all", "change_in_nonrept_short_all", "pct_of_oi_nonrept_long_all", "pct_of_oi_nonrept_short_all", None, None),
)
CFTC_EXTRA_PARTICIPANTS = {
    "disaggregated": (
        ("prod_merc", "Producer/Merchant", "prod_merc_positions_long", "prod_merc_positions_short", None, "change_in_prod_merc_long", "change_in_prod_merc_short", "pct_of_oi_prod_merc_long", "pct_of_oi_prod_merc_short", "traders_prod_merc_long_all", "traders_prod_merc_short_all"),
        ("swap", "Swap Dealers", "swap_positions_long_all", "swap__positions_short_all", "swap__positions_spread_all", "change_in_swap_long_all", "change_in_swap_short_all", "pct_of_oi_swap_long_all", "pct_of_oi_swap_short_all", "traders_swap_long_all", "traders_swap_short_all"),
        ("managed_money", "Managed Money", "m_money_positions_long_all", "m_money_positions_short_all", "m_money_positions_spread", "change_in_m_money_long_all", "change_in_m_money_short_all", "pct_of_oi_m_money_long_all", "pct_of_oi_m_money_short_all", "traders_m_money_long_all", "traders_m_money_short_all"),
        ("other_rept", "Other Reportables", "other_rept_positions_long", "other_rept_positions_short", "other_rept_positions_spread", "change_in_other_rept_long", "change_in_other_rept_short", "pct_of_oi_other_rept_long", "pct_of_oi_other_rept_short", "traders_other_rept_long_all", "traders_other_rept_short"),
        ("nonrept", "Nonreportables", "nonrept_positions_long_all", "nonrept_positions_short_all", None, "change_in_nonrept_long_all", "change_in_nonrept_short_all", "pct_of_oi_nonrept_long_all", "pct_of_oi_nonrept_short_all", None, None),
    ),
    "legacy": (
        ("noncomm", "Non-commercial", "noncomm_positions_long_all", "noncomm_positions_short_all", "noncomm_postions_spread_all", "change_in_noncomm_long_all", "change_in_noncomm_short_all", "pct_of_oi_noncomm_long_all", "pct_of_oi_noncomm_short_all", "traders_noncomm_long_all", "traders_noncomm_short_all"),
        ("commercial", "Commercial", "comm_positions_long_all", "comm_positions_short_all", None, "change_in_comm_long_all", "change_in_comm_short_all", "pct_of_oi_comm_long_all", "pct_of_oi_comm_short_all", "traders_comm_long_all", "traders_comm_short_all"),
        ("nonrept", "Nonreportables", "nonrept_positions_long_all", "nonrept_positions_short_all", None, "change_in_nonrept_long_all", "change_in_nonrept_short_all", "pct_of_oi_nonrept_long_all", "pct_of_oi_nonrept_short_all", None, None),
    ),
    "supplemental_cit": (
        ("noncomm_nocit", "Non-commercial ex-CIT", "NComm_Postions_Long_All_NoCIT", "NComm_Postions_Short_All_NoCIT", "NComm_Postions_Spread_All_NoCIT", "change_noncomm_long_all_nocit", "Change_NonComm_Short_All_NoCIT", "pct_oi_noncomm_long_all_nocit", "Pct_OI_NonComm_Short_All_NoCIT", "Traders_NonComm_Long_All_NoCIT", "Traders_NonComm_Short_All_NoCIT"),
        ("commercial_nocit", "Commercial ex-CIT", "comm_positions_long_all_nocit", "Comm_Positions_Short_All_NoCIT", None, "change_comm_long_all_nocit", "change_comm_short_all_nocit", "pct_oi_comm_long_all_nocit", "pct_oi_comm_short_all_nocit", "traders_comm_long_all_nocit", "traders_comm_short_all_nocit"),
        ("cit", "Commodity Index Traders", "cit_positions_long_all", "cit_positions_short_all", None, "change_cit_long_all", "change_cit_short_all", "pct_oi_cit_long_all", "pct_oi_cit_short_all", "traders_cit_long_all", "traders_cit_short_all"),
        ("nonrept", "Nonreportables", "nonrept_positions_long_all", "nonrept_positions_short_all", None, "change_nonrept_long_all", "change_nonrept_short_all", "pct_oi_nonrept_long_all_nocit", "Pct_OI_NonRept_Short_All_NoCIT", None, None),
    ),
}
CFTC_PRIMARY_PARTICIPANT_BY_FAMILY = {
    "tff": "lev_money",
    "disaggregated": "managed_money",
    "legacy": "noncomm",
    "supplemental_cit": "cit",
}
CFTC_FOCUS_MARKET_TOKENS = (
    "U.S. TREASURY",
    "SOFR",
    "FED FUNDS",
    "EURO FX",
    "JAPANESE YEN",
    "BRITISH POUND",
    "CANADIAN DOLLAR",
    "AUSTRALIAN DOLLAR",
    "SWISS FRANC",
    "MEXICAN PESO",
    "BRAZILIAN REAL",
    "S&P 500",
    "NASDAQ",
    "DOW JONES",
    "RUSSELL",
    "VIX",
    "BITCOIN",
    "ETHER",
)
ANBIMA_CATEGORY_TO_MACRO = {
    "RENDA FIXA": "Renda Fixa",
    "ACOES": "Acoes",
    "MULTIMERCADOS": "Multimercado",
    "CAMBIAL": "Cambial",
    "PREVIDENCIA": "Previdencia",
    "ETF": "ETF",
    "FIDC": "FIDC",
    "FIP": "FIP",
    "FIAGRO": "Fiagro",
    "FII": "FII",
}

INFORME_COLUMNS = {
    "TP_FUNDO_CLASSE": "tp_fundo_classe",
    "CNPJ_FUNDO": "cnpj_fundo",
    "CNPJ_FUNDO_CLASSE": "cnpj_fundo",
    "ID_SUBCLASSE": "id_subclasse",
    "DT_COMPTC": "dt",
    "VL_TOTAL": "vl_total",
    "VL_QUOTA": "vl_quota",
    "VL_PATRIM_LIQ": "pl",
    "CAPTC_DIA": "captacao",
    "RESG_DIA": "resgate",
    "NR_COTST": "cotistas",
}

INFORME_SOURCE_PRIORITY = {
    "CLASSES - FIF": 0,
    "FI": 1,
    "FAPI": 2,
    "CLASSE FIF/FAPI": 3,
}

MASTER_RENAME = {
    "CNPJ_FUNDO": "cnpj_fundo",
    "DENOM_SOCIAL": "nome_fundo",
    "CLASSE": "classe_cvm",
    "TP_FUNDO": "tipo_fundo",
    "ADMIN": "administrador",
    "GESTOR": "gestor",
    "SIT": "situacao",
    "DT_REG": "data_registro",
    "DT_INI_ATIV": "data_inicio",
    "CONDOM": "condominio",
    "FUNDO_EXCLUSIVO": "fundo_exclusivo",
    "PUBLICO_ALVO": "publico_alvo",
}

CLASS_REGISTER_RENAME = {
    "ID_Registro_Fundo": "id_registro_fundo",
    "ID_Registro_Classe": "id_registro_classe",
    "CNPJ_Classe": "cnpj_fundo",
    "Data_Registro": "data_registro",
    "Data_Inicio": "data_inicio",
    "Tipo_Classe": "tipo_fundo",
    "Denominacao_Social": "nome_fundo",
    "Situacao": "situacao",
    "Classificacao": "classe_cvm",
    "Classificacao_Anbima": "classe_anbima",
    "Forma_Condominio": "condominio",
    "Exclusivo": "fundo_exclusivo",
    "Publico_Alvo": "publico_alvo",
}

FUND_REGISTER_RENAME = {
    "ID_Registro_Fundo": "id_registro_fundo",
    "Administrador": "administrador",
    "Gestor": "gestor",
}

WINDOWS = (5, 21, 63)

ICI_SIMPLE_WEEKLY_COLUMNS = (
    (1, "total", "Total", "total"),
    (3, "equity", "Equity", "equity"),
    (5, "domestic_equity", "Domestic Equity", "equity"),
    (7, "world_equity", "World Equity", "equity"),
    (9, "hybrid", "Hybrid", "hybrid"),
    (11, "bond", "Bond", "bond"),
    (13, "taxable_bond", "Taxable Bond", "bond"),
    (15, "municipal_bond", "Municipal Bond", "bond"),
    (17, "commodity", "Commodity", "commodity"),
)

ICI_MUTUAL_FUND_WEEKLY_COLUMNS = (
    (1, "total_long_term", "Total Long-Term", "total"),
    (3, "equity", "Equity", "equity"),
    (5, "domestic_equity", "Domestic Equity", "equity"),
    (7, "large_cap", "Large Cap", "equity"),
    (9, "mid_cap", "Mid Cap", "equity"),
    (11, "small_cap", "Small Cap", "equity"),
    (13, "multi_cap", "Multi Cap", "equity"),
    (15, "other_domestic_equity", "Other Domestic Equity", "equity"),
    (17, "world_equity", "World Equity", "equity"),
    (19, "developed_markets", "Developed Markets", "equity"),
    (21, "emerging_markets", "Emerging Markets", "equity"),
    (23, "hybrid", "Hybrid", "hybrid"),
    (25, "bond", "Bond", "bond"),
    (27, "taxable_bond", "Taxable Bond", "bond"),
    (29, "investment_grade", "Investment Grade", "bond"),
    (31, "high_yield", "High Yield", "bond"),
    (33, "government", "Government", "bond"),
    (35, "multisector", "Multisector", "bond"),
    (37, "global_bond", "Global Bond", "bond"),
    (39, "municipal_bond", "Municipal Bond", "bond"),
)

ICI_WORLDWIDE_COLUMNS = (
    (2, "total", "Total"),
    (3, "equity", "Equity"),
    (4, "bond", "Bond"),
    (5, "balanced_mixed", "Balanced/Mixed"),
    (6, "money_market", "Money Market"),
    (7, "guaranteed_protected", "Guaranteed/Protected"),
    (8, "real_estate", "Real Estate"),
    (9, "other_funds", "Other Funds"),
    (10, "etfs", "ETFs"),
    (11, "institutional_funds", "Institutional Funds"),
)


@dataclass(frozen=True)
class SourceInventoryItem:
    id: str
    label: str
    provider: str
    kind: str
    cadence: str
    role: str
    url: str
    status: str = "configured"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "provider": self.provider,
            "kind": self.kind,
            "cadence": self.cadence,
            "role": self.role,
            "url": self.url,
            "status": self.status,
        }


SOURCE_INVENTORY: tuple[SourceInventoryItem, ...] = (
    SourceInventoryItem(
        id="cvm_informe_diario",
        label="CVM Informe Diario FI",
        provider="CVM Dados Abertos",
        kind="official_public",
        cadence="daily_monthly_file",
        role="Fonte primaria para captacao, resgate, PL, cotistas e cota por fundo",
        url="https://dados.cvm.gov.br/dataset/fi-doc-inf_diario",
        status="active",
    ),
    SourceInventoryItem(
        id="cvm_cadastro_fi",
        label="CVM Cadastro FI",
        provider="CVM Dados Abertos",
        kind="official_public",
        cadence="daily_file",
        role="Universo, situacao cadastral e classificacao base dos fundos",
        url="https://dados.cvm.gov.br/dataset/fi-cad",
        status="active",
    ),
    SourceInventoryItem(
        id="cvm_cda",
        label="CVM CDA Carteiras",
        provider="CVM Dados Abertos",
        kind="official_public",
        cadence="monthly_daily_publication",
        role="Carteira mensal dos fundos brasileiros: ativos, emissores, paises, PL e posicoes confidenciais",
        url="https://dados.cvm.gov.br/dataset/fi-doc-cda",
        status="configured",
    ),
    SourceInventoryItem(
        id="anbima_fundos",
        label="ANBIMA Estatisticas de Fundos",
        provider="ANBIMA",
        kind="official_public",
        cadence="daily_monthly",
        role="Validacao agregada por tipo de fundo e benchmark de consistencia",
        url="https://data.anbima.com.br/publicacoes/consolidado-diario-de-fundos-de-investimento",
        status="configured",
    ),
    SourceInventoryItem(
        id="bcb_macro",
        label="BCB SGS/OData",
        provider="Banco Central do Brasil",
        kind="official_public",
        cadence="daily_weekly",
        role="Cambio, Selic e variaveis macro locais para cruzamento",
        url="https://dadosabertos.bcb.gov.br/",
        status="configured",
    ),
    SourceInventoryItem(
        id="b3_etfs",
        label="B3 ETFs Listados",
        provider="B3",
        kind="official_public",
        cadence="daily",
        role="Lista oficial de ETFs listados por segmento para compor a aba ETF",
        url=B3_FUNDS_LISTED_PAGE_URL,
        status="configured",
    ),
    SourceInventoryItem(
        id="ici_global_flows",
        label="ICI Global Fund Flows",
        provider="Investment Company Institute",
        kind="official_public",
        cadence="weekly_quarterly",
        role="Fluxos semanais de mutual funds/ETFs e suplemento trimestral por pais/regiao",
        url="https://www.ici.org/research/stats/flows",
        status="configured",
    ),
    SourceInventoryItem(
        id="fred_macro",
        label="FRED Macro Global",
        provider="Federal Reserve Bank of St. Louis",
        kind="official_public",
        cadence="daily",
        role="US yields, breakevens, petroleo e proxies externos",
        url="https://fred.stlouisfed.org/docs/api/fred/",
        status="configured",
    ),
    SourceInventoryItem(
        id="b3_market",
        label="B3 BDI Participacao dos Investidores",
        provider="B3",
        kind="official_public",
        cadence="daily",
        role="Compras, vendas, participacao e saldo derivado por tipo de investidor no volume total da B3",
        url="https://arquivos.b3.com.br/bdi/",
        status="configured",
    ),
    SourceInventoryItem(
        id="b3_investor_participation_monthly",
        label="B3 BDI Participacao dos Investidores Mensal",
        provider="B3",
        kind="official_public",
        cadence="monthly_daily_publication",
        role="Participacao por tipo de investidor e mercado: a vista, termo, opcoes, exercicios, blocos e total",
        url="https://arquivos.b3.com.br/bdi/table/export",
        status="configured",
    ),
    SourceInventoryItem(
        id="b3_market_data_report",
        label="B3 Relatorio Dados de Mercado",
        provider="B3",
        kind="official_public",
        cadence="daily",
        role="CSV oficial com volume, negocios, participacao mensal e movimentacao de estrangeiros",
        url=B3_MARKET_DATA_REPORT_URL,
        status="configured",
    ),
    SourceInventoryItem(
        id="b3_derivatives_open_interest",
        label="B3 BDI Posicoes em Aberto",
        provider="B3",
        kind="official_public",
        cadence="daily",
        role="Contratos em aberto e variacao diaria por ativo/vencimento em derivativos de bolsa",
        url="https://arquivos.b3.com.br/bdi/table/export",
        status="configured",
    ),
    SourceInventoryItem(
        id="cftc_cot",
        label="CFTC COT/PRE",
        provider="CFTC",
        kind="official_public",
        cadence="weekly_tuesday_position_friday_release",
        role="Proxy semanal de posicionamento global em futuros, opcoes e commodities por tipo de participante",
        url=CFTC_PRE_STORY_URL,
        status="configured",
    ),
)
