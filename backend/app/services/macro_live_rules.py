"""Classification rules and keyword catalogs for macro live events."""

from __future__ import annotations

import re
from typing import Any

from ..config import Config


def _build_market_groups() -> dict[str, list[str]]:
    return {
        "index": list(Config.MACRO_INDEX_TICKERS),
        "dollar": list(Config.MACRO_DOLLAR_TICKERS),
        "curve_short": list(Config.MACRO_CURVE_SHORT_TICKERS),
        "curve_long": list(Config.MACRO_CURVE_LONG_TICKERS),
    }


def _resolve_market_bucket(ticker: str) -> str:
    for bucket, tickers in _build_market_groups().items():
        if ticker in tickers:
            return bucket
    return "other"


MACRO_NEWS_KEYWORDS = {
    "curve_short": ["copom", "selic", "inflacao", "ipca", "juros", "curva curta"],
    "curve_long": ["fiscal", "arcabouco", "tesouro", "premio", "curva longa", "divida"],
    "index": ["ibov", "ibovespa", "indice", "bolsa", "acoes", "equities"],
    "dollar": ["dolar", "fx", "real", "brl", "usd", "cambio"],
    "VALE3": ["vale", "minerio", "mining", "iron ore"],
    "PETR4": ["petrobras", "petr4", "petroleo", "oil", "brent"],
    "ITUB4": ["itau", "itub4", "bancos", "bank"],
    "BPAC11": ["btg", "bpac11", "investment bank"],
    "BBDC4": ["bradesco", "bbdc4"],
}

MACRO_THEME_RULES: dict[str, dict[str, Any]] = {
    "ormuz_blockade": {
        "keyword_groups": [
            ["iran", "irÃ£", "ormuz", "hormuz", "estreito de ormuz", "strait of hormuz"],
            [
                "bloqueio",
                "blockade",
                "naval",
                "navio",
                "navios",
                "shipping",
                "ship",
                "ships",
                "tanker",
                "tankers",
                "petroleo",
                "oil",
                "brent",
                "gasolina",
                "portos",
                "minas",
            ],
        ],
        "buckets": ["dollar", "index", "curve_long"],
        "securities": ["PETR4"],
    },
    "iran_negotiation": {
        "keyword_groups": [
            ["iran", "irÃ£", "irÃƒÂ£", "eua", "usa", "us"],
            [
                "negotiation",
                "negotiations",
                "negociacao",
                "negociação",
                "negociacoes",
                "negociações",
                "dialog",
                "talks",
                "progresso",
                "rodada de negociacoes",
                "rodada de negociações",
                "apetite por risco",
                "risk-on",
                "risk on",
                "chegar a um acordo",
                "disposto a mais uma rodada",
            ],
        ],
        "buckets": ["index", "dollar", "curve_long"],
    },
    "iran_negotiation_setback": {
        "keyword_groups": [
            ["iran", "irÃ£", "irÃƒÂ£", "eua", "usa", "us"],
            [
                "negotiation",
                "negotiations",
                "negociacao",
                "negociação",
                "negociacoes",
                "negociações",
                "dialog",
                "talks",
                "diplomacy",
                "diplomacia",
            ],
            [
                "renuncia",
                "renunciou",
                "resign",
                "resigned",
                "resignation",
                "linha dura",
                "hardliner",
                "hard line",
                "pressure",
                "pressao",
                "pressão",
                "impasse",
                "deadlock",
                "setback",
                "retrocesso",
                "sem sucessor",
                "unknown successor",
            ],
        ],
        "buckets": ["index", "dollar", "curve_long"],
    },
}

MACRO_THEME_RULES["ormuz_blockade"]["keyword_groups"][1].extend(
    [
        "estreito",
        "strait",
        "interdicao",
        "apreensao",
        "exportacoes",
        "marinha",
        "pirataria",
        "energia",
        "energy",
        "combate",
        "combat",
        "forcas",
    ]
)
MACRO_THEME_RULES["iran_negotiation"]["keyword_groups"][0].extend(["libano", "abraham", "abraao"])
MACRO_THEME_RULES["iran_negotiation"]["keyword_groups"][1].extend(
    [
        "acordo nuclear",
        "nuclear deal",
        "ceasefire",
        "cessar-fogo",
        "cessar fogo",
        "desescalada",
        "de-escalation",
        "risk relief",
        "alivio",
        "alívio",
        "sanctions relief",
        "alivio de sancoes",
    ]
)
MACRO_THEME_RULES["iran_negotiation_setback"]["keyword_groups"][1].extend(
    [
        "saida do negociador",
        "saída do negociador",
        "negociador moderado",
        "moderate negotiator",
        "ponta moderada",
        "ghalibaf",
        "substituto incerto",
        "replacement unclear",
        "leadership uncertainty",
        "diplomatic setback",
        "talks setback",
        "colapso das negociacoes",
        "colapso das negociações",
    ]
)

SESSION_RISK_THEMES = {"ormuz_blockade", "iran_negotiation", "iran_negotiation_setback"}

MARKET_RELEVANCE_TERMS = [
    "macro",
    "mercado",
    "market",
    "juros",
    "rates",
    "yield",
    "treasury",
    "copom",
    "selic",
    "inflacao",
    "inflation",
    "ipca",
    "fiscal",
    "arcabouco",
    "dolar",
    "fx",
    "real",
    "brl",
    "usd",
    "ibov",
    "ibovespa",
    "indice",
    "equities",
    "petroleo",
    "oil",
    "brent",
    "minerio",
    "iron ore",
    "bancos",
    "bank",
    "payroll",
    "fed",
    "bcb",
    "bc",
    "tariff",
    "china",
    "growth",
    "iran",
    "irÃ£",
    "ormuz",
    "hormuz",
    "estreito de ormuz",
    "blockade",
    "bloqueio",
    "naval",
    "navio",
    "navios",
    "shipping",
    "tanker",
    "tankers",
    "energia",
    "energy",
    "negotiation",
    "negotiations",
    "negociacao",
    "negociação",
    "negociacoes",
    "negociações",
    "dialog",
    "talks",
    "progresso",
    "apetite por risco",
    "risk-on",
    "risk on",
    "hardliner",
    "linha dura",
    "renuncia",
    "resign",
    "resigned",
    "resignation",
    "deadlock",
    "impasse",
]

NEWS_RELEVANCE_WEIGHTS = {
    "breaking": 3,
    "important": 2,
    "relevant": 1,
}

HIGH_CONFIDENCE_MACRO_TERMS = [
    "juros",
    "rates",
    "yield",
    "treasury",
    "copom",
    "selic",
    "inflacao",
    "inflation",
    "ipca",
    "fiscal",
    "arcabouco",
    "dolar",
    "fx",
    "real",
    "brl",
    "usd",
    "ibov",
    "ibovespa",
    "s&p",
    "nasdaq",
    "dow",
    "russell",
    "petroleo",
    "oil",
    "brent",
    "minerio",
    "iron ore",
    "payroll",
    "fed",
    "bcb",
    "bc",
    "tariff",
    "china",
    "ormuz",
    "hormuz",
    "estreito de ormuz",
    "blockade",
    "bloqueio",
    "naval",
    "navio",
    "navios",
    "shipping",
    "tanker",
    "tankers",
    "energia",
    "energy",
    "negotiation",
    "negotiations",
    "negociacao",
    "negociação",
    "negociacoes",
    "negociações",
    "dialog",
    "talks",
    "progresso",
    "apetite por risco",
    "risk-on",
    "risk on",
    "hardliner",
    "linha dura",
    "renuncia",
    "resign",
    "resigned",
    "resignation",
    "deadlock",
    "impasse",
]

GENERIC_EQUITY_TERMS = ["acoes", "aÃ§Ãµes", "equities", "shares", "stock", "stocks"]

IDIOSYNCRATIC_NEWS_TERMS = [
    "fda",
    "terapia",
    "therapy",
    "cancer",
    "oncology",
    "drug",
    "trial",
    "ensaio",
    "phase 2",
    "phase 3",
    "fase 2",
    "fase 3",
    "guidance",
    "earnings",
    "lucro",
    "results",
    "resultado",
    "ceo",
    "cfo",
    "layoff",
    "layoffs",
    "demiss",
    "dividend",
    "buyback",
    "merger",
    "acquisition",
    "m&a",
    "record low",
    "all-time low",
    "mÃ­nima histÃ³rica",
    "minima historica",
    "ipo",
    "initial public offering",
    "abre capital",
    "oferta publica inicial",
    "oferta pública inicial",
]
CORPORATE_DEAL_TERMS = [
    "artificial intelligence",
    "inteligencia artificial",
    "inteligência artificial",
    "ai ",
    "deal",
    "deal for",
    "agreement with",
    "acordo comercial",
    "parceria",
    "partnership",
    "contrato",
    "contract",
    "record close",
    "record high",
    "fechamento recorde",
    "shares",
    "ações",
    "acoes",
    "barrons.com",
    "vendor",
    "cliente",
    "customer",
    "ipo",
    "initial public offering",
    "abre capital",
    "oferta publica inicial",
    "oferta pública inicial",
]

HARD_MACRO_ANCHOR_TERMS = {
    "juros",
    "rates",
    "yield",
    "treasury",
    "copom",
    "selic",
    "inflacao",
    "inflation",
    "ipca",
    "fiscal",
    "arcabouco",
    "dolar",
    "fx",
    "real",
    "brl",
    "usd",
    "ibov",
    "ibovespa",
    "indice",
    "index",
    "s&p",
    "nasdaq",
    "dow",
    "russell",
    "petroleo",
    "oil",
    "brent",
    "minerio",
    "iron ore",
    "payroll",
    "fed",
    "bcb",
    "bc",
    "tariff",
    "china",
    "ormuz",
    "hormuz",
    "estreito de ormuz",
    "blockade",
    "bloqueio",
    "naval",
    "navio",
    "navios",
    "shipping",
    "tanker",
    "tankers",
    "negotiation",
    "negotiations",
    "negociacao",
    "negociação",
    "negociacoes",
    "negociações",
    "dialog",
    "talks",
    "progresso",
    "risk-on",
    "risk on",
    "hardliner",
    "linha dura",
    "renuncia",
    "resign",
    "resigned",
    "resignation",
    "deadlock",
    "impasse",
}


TECHNICAL_LIQUIDITY_RULES = [
    {
        "keyword_groups": [
            ["fed de nova york", "new york fed", "ny fed", "federal reserve bank of new york"],
            [
                "reinvest",
                "reinvestment",
                "compras de reinvestimento",
                "reserve management",
                "gestao de reservas",
                "compras de gestao de reservas",
            ],
        ],
    },
    {
        "keyword_groups": [
            ["fed", "federal reserve"],
            [
                "repo",
                "reverse repo",
                "term repo",
                "overnight repo",
                "standing repo",
                "operacao de liquidez",
                "operacao de recompra",
            ],
        ],
    },
]

TECHNICAL_BALANCE_SHEET_RULES = [
    {
        "keyword_groups": [
            ["fed de nova york", "new york fed", "ny fed", "federal reserve bank of new york"],
            [
                "unrealized loss",
                "unrealized losses",
                "prejuizo nao realizado",
                "prejuÃ­zo nÃ£o realizado",
                "prejuÃ­zo nÃ£o realizado",
                "nao realizado",
                "nÃ£o realizado",
                "losses on assets",
                "loss on assets",
                "annual report",
                "relatorio anual",
                "relatÃ³rio anual",
                "annual financial statements",
                "fair value",
            ],
        ],
    },
    {
        "keyword_groups": [
            ["federal reserve", "fed", "reserve bank"],
            [
                "balance sheet",
                "balanco",
                "balanÃ§o",
                "soma",
                "system open market account",
                "held outright",
                "portfolio",
                "mark-to-market",
                "mark to market",
                "mtm",
            ],
        ],
    },
]

LOW_SIGNAL_MACRO_TERMS = {
    "fed",
}

HIGH_CONVICTION_CENTRAL_BANK_TERMS = [
    "surprise",
    "unexpected",
    "emergency",
    "intermeeting",
    "unscheduled",
    "rate cut",
    "rate hike",
    "corte de juros",
    "alta de juros",
    "guidance",
    "dot plot",
    "fomc",
    "fed funds",
    "qe",
    "qt",
]
REGIME_SHIFT_SCENARIO_TERMS = [
    "emergency",
    "intermeeting",
    "unscheduled",
    "ceasefire",
    "blockade",
    "bloqueio",
    "strait",
    "ormuz",
    "hormuz",
    "tariff",
    "default",
    "calamity",
    "sanction",
    "sanctions",
    "war",
    "ataque",
    "ataques",
    "invasion",
    "invasao",
    "breakthrough",
    "deal reached",
    "acordo",
    "agreement",
    "guidance change",
]
SECONDARY_ECHO_SCENARIO_TERMS = [
    "reports",
    "reporta",
    "reported",
    "estima",
    "estimates",
    "planeja",
    "plans",
    "says",
    "afirma",
    "comentou",
    "commented",
    "according to",
    "segundo",
    "expected to",
    "should",
    "could",
    "may",
    "might",
]


def _match_all_keyword_groups(text: str, keyword_groups: list[list[str]]) -> bool:
    if not keyword_groups:
        return False
    return all(
        any(_keyword_in_text(text, keyword) for keyword in group) for group in keyword_groups
    )


def _match_any_keyword_rule(text: str, rules: list[dict[str, Any]]) -> bool:
    return any(_match_all_keyword_groups(text, rule.get("keyword_groups") or []) for rule in rules)


def _keyword_in_text(text: str, keyword: str) -> bool:
    raw = str(keyword or "").strip().lower()
    if not raw:
        return False
    if " " in raw:
        pattern = (
            r"(?<![0-9A-Za-zÀ-ÿ])" + re.escape(raw).replace(r"\ ", r"\s+") + r"(?![0-9A-Za-zÀ-ÿ])"
        )
        return re.search(pattern, text) is not None

    compact = re.sub(r"[^0-9A-Za-zÀ-ÿ]", "", raw)
    if compact and len(compact) <= 4 and compact.isalpha():
        pattern = r"(?<![0-9A-Za-zÀ-ÿ])" + re.escape(raw) + r"(?![0-9A-Za-zÀ-ÿ])"
        return re.search(pattern, text) is not None
    return raw in text
