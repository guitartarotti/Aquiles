"""Provider catalog and classification constants for daily ETF flows."""

from __future__ import annotations

ETF_DAILY_FLOW_SCHEMA_VERSION = 1

DEFAULT_PROVIDER_ORDER = (
    "schwab",
    "state_street",
    "vaneck",
    "ishares",
    "dimensional",
    "vanguard",
    "invesco",
    "proshares",
    "global_x",
)

DEFAULT_ETF_UNIVERSE = (
    {
        "provider": "schwab",
        "ticker": "SCHX",
        "name": "Schwab U.S. Large-Cap ETF",
        "url": "https://www.schwabassetmanagement.com/products/schx",
        "currency": "USD",
    },
    {
        "provider": "state_street",
        "ticker": "SPY",
        "name": "State Street SPDR S&P 500 ETF Trust",
        "url": "https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy",
        "currency": "USD",
    },
    {
        "provider": "vaneck",
        "ticker": "SMH",
        "name": "VanEck Semiconductor ETF",
        "url": "https://www.vaneck.com/us/en/investments/semiconductor-etf-smh/",
        "currency": "USD",
    },
    {
        "provider": "ishares",
        "ticker": "IVV",
        "name": "iShares Core S&P 500 ETF",
        "url": "https://www.blackrock.com/us/individual/products/239726/ishares-core-s-p-500-etf",
        "currency": "USD",
    },
    {
        "provider": "dimensional",
        "ticker": "DFAU",
        "name": "Dimensional US Core Equity Market ETF",
        "url": "https://www.dimensional.com/us-en/funds/dfau/us-core-equity-market-etf",
        "currency": "USD",
    },
    {
        "provider": "vanguard",
        "ticker": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "url": "https://investor.vanguard.com/investment-products/etfs/profile/voo",
        "currency": "USD",
    },
    {
        "provider": "invesco",
        "ticker": "QQQ",
        "name": "Invesco QQQ Trust",
        "url": "https://www.invesco.com/qqq-etf/en/home.html",
        "currency": "USD",
    },
    {
        "provider": "proshares",
        "ticker": "TQQQ",
        "name": "ProShares UltraPro QQQ",
        "url": "https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq",
        "currency": "USD",
    },
    {
        "provider": "global_x",
        "ticker": "QYLD",
        "name": "Global X Nasdaq 100 Covered Call ETF",
        "url": "https://www.globalxetfs.com/funds/qyld",
        "currency": "USD",
    },
)

PROVIDER_LABELS = {
    "schwab": "Schwab",
    "state_street": "State Street",
    "vaneck": "VanEck",
    "ishares": "iShares",
    "dimensional": "Dimensional",
    "vanguard": "Vanguard",
    "invesco": "Invesco",
    "proshares": "ProShares",
    "global_x": "Global X",
}

COUNTRY_KEYWORDS = (
    ("united states", "Estados Unidos"),
    ("u.s.", "Estados Unidos"),
    (" us ", "Estados Unidos"),
    ("china", "China"),
    ("japan", "Japao"),
    ("india", "India"),
    ("brazil", "Brasil"),
    ("mexico", "Mexico"),
    ("canada", "Canada"),
    ("germany", "Alemanha"),
    ("france", "Franca"),
    ("italy", "Italia"),
    ("spain", "Espanha"),
    ("taiwan", "Taiwan"),
    ("korea", "Coreia"),
    ("south korea", "Coreia"),
    ("vietnam", "Vietna"),
    ("argentina", "Argentina"),
    ("saudi", "Arabia Saudita"),
    ("turkey", "Turquia"),
    ("israel", "Israel"),
    ("africa", "Africa"),
)

EMERGING_HINTS = (
    "emerging",
    "latin america",
    "africa",
    "vietnam",
    "india",
    "brazil",
    "mexico",
    "china",
)
DEVELOPED_HINTS = (
    "developed",
    "united states",
    "u.s.",
    "europe",
    "japan",
    "canada",
    "germany",
    "france",
)
FACTOR_HINTS = (
    "value",
    "growth",
    "quality",
    "momentum",
    "size",
    "min vol",
    "minimum volatility",
    "factor",
)
SECTOR_HINTS = (
    "semiconductor",
    "biotech",
    "cyber",
    "technology",
    "health",
    "financial",
    "energy",
    "industrial",
    "infrastructure",
    "robot",
    "ai",
    "artificial intelligence",
    "uranium",
    "cloud",
    "real estate",
)
INCOME_HINTS = (
    "covered call",
    "income",
    "premium",
    "yield",
    "buywrite",
    "option",
    "buffer",
    "collar",
)
