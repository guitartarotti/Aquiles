"""
配置管理
统一从项目根目录的 .env 文件加载配置
"""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


DEFAULT_MACRO_BLOOMBERG_REFERENCE_ASSETS = [
    {"security": "SCOA Comdty", "label": "Coal", "category": "commodity", "bucket": "commodity"},
    {"security": "CLA Comdty", "label": "Crude Oil", "category": "commodity", "bucket": "commodity"},
    {"security": "XB1 Index", "label": "Bovespa Index Future", "category": "equity", "bucket": "equity"},
    {"security": "ESA Index", "label": "S&P 500 Future Proxy", "category": "equity", "bucket": "equity"},
    {"security": "MES1 Index", "label": "Emerging Markets Future", "category": "equity", "bucket": "equity"},
    {"security": "DMA Index", "label": "Developed Markets Basket", "category": "equity", "bucket": "equity"},
    {"security": "RTYA Index", "label": "Russell 2000", "category": "equity", "bucket": "equity"},
    {"security": "EMHY CDSI S44 5Y PRC Corp", "label": "EM HY CDSI S44 5Y", "category": "credit", "bucket": "credit"},
    {"security": "EMBIV Index", "label": "EMBI Volatility", "category": "credit", "bucket": "credit"},
    {"security": "CDX HY CDSI GEN 5Y SPRD Corp", "label": "CDX HY CDSI", "category": "credit", "bucket": "credit"},
    {"security": "BRAZIL CDS USD SR 3Y D14 Curncy", "label": "Brazil CDS USD", "category": "sovereign", "bucket": "credit"},
    {"security": ".JPYB U Index", "label": "JPY Basket", "category": "fx", "bucket": "fx"},
    {"security": "CDX EM CDSI S44 5Y PRC Corp", "label": "CDX EM CDSI S44", "category": "credit", "bucket": "credit"},
]

DEFAULT_MACRO_BLOOMBERG_REFERENCE_MAP = {
    item["security"]: item for item in DEFAULT_MACRO_BLOOMBERG_REFERENCE_ASSETS
}


def _parse_key_value_mapping(raw_value: str, item_separator: str = ",", kv_separator: str = "=") -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in str(raw_value or "").split(item_separator):
        text = item.strip()
        if not text or kv_separator not in text:
            continue
        key, value = text.split(kv_separator, 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            mapping[key] = value
    return mapping


def _parse_int_list(raw_value: str, default: list[int]) -> list[int]:
    values: list[int] = []
    for item in str(raw_value or "").split(","):
        text = item.strip()
        if not text:
            continue
        try:
            values.append(int(text))
        except ValueError:
            continue
    return values or list(default)


def _parse_float(value: str | None, default: float) -> float:
    try:
        if value is None:
            return default
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


DEFAULT_OPTIONS_MODEL_FALLBACK_RATE = _parse_float(os.environ.get('OPTIONS_MODEL_FALLBACK_RATE'), 0.135)

class Config:
    """Runtime configuration loaded from environment variables."""
    
    # Flask配置
    APP_VERSION = os.environ.get('AQUILES_VERSION', '0.1.0')
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    START_BACKGROUND_SERVICES = os.environ.get(
        'AQUILES_START_BACKGROUND_SERVICES',
        'True',
    ).lower() == 'true'
    CORS_ORIGINS = [
        origin.strip()
        for origin in os.environ.get(
            'CORS_ORIGINS',
            'http://localhost:3000,http://127.0.0.1:3000',
        ).split(',')
        if origin.strip()
    ]

    # Authentication and role-based access control
    AUTH_ENABLED = os.environ.get('AQUILES_AUTH_ENABLED', 'True').lower() == 'true'
    AUTH_TOKEN_SECRET = os.environ.get('AQUILES_AUTH_TOKEN_SECRET', '')
    AUTH_USERS_JSON = os.environ.get('AQUILES_AUTH_USERS_JSON', '')
    AUTH_TOKEN_TTL_SECONDS = int(os.environ.get('AQUILES_AUTH_TOKEN_TTL_SECONDS', '28800'))
    AUTH_LOGIN_MAX_ATTEMPTS = int(os.environ.get('AQUILES_AUTH_LOGIN_MAX_ATTEMPTS', '5'))
    AUTH_LOGIN_WINDOW_SECONDS = int(os.environ.get('AQUILES_AUTH_LOGIN_WINDOW_SECONDS', '300'))
    
    # JSON配置 - 禁用ASCII转义，让中文直接显示（而不是 \uXXXX 格式）
    JSON_AS_ASCII = False
    
    # LLM配置（统一使用OpenAI格式）
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')

    # Graph backend configuration
    GRAPH_BACKEND = os.environ.get('GRAPH_BACKEND', 'zep_cloud').strip().lower()

    # Zep配置
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')

    # Graphiti local configuration
    GRAPHITI_DATABASE = os.environ.get('GRAPHITI_DATABASE', 'neo4j').strip().lower()
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD')
    
    # 文件上传配置
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}
    
    # 文本处理配置
    DEFAULT_CHUNK_SIZE = 500  # 默认切块大小
    DEFAULT_CHUNK_OVERLAP = 50  # 默认重叠大小
    
    # OASIS模拟配置
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    # Macro live feed configuration
    MACRO_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/macro')
    NPORT_DATA_DIR = os.environ.get('NPORT_DATA_DIR', os.path.join(MACRO_DATA_DIR, 'nport'))
    CVM_CDA_DATA_DIR = os.environ.get('CVM_CDA_DATA_DIR', os.path.join(MACRO_DATA_DIR, 'cvm_cda'))
    CVM_CDA_ENABLE = os.environ.get('CVM_CDA_ENABLE', 'True').lower() == 'true'
    CVM_CDA_AUTO_START = os.environ.get('CVM_CDA_AUTO_START', 'False').lower() == 'true'
    CVM_CDA_UPDATE_TIME = os.environ.get('CVM_CDA_UPDATE_TIME', '08:25')
    CVM_CDA_RECENT_MONTH_LOOKBACK = int(os.environ.get('CVM_CDA_RECENT_MONTH_LOOKBACK', '3'))
    CVM_CDA_GRAPH_SERVICE_HOST = os.environ.get('CVM_CDA_GRAPH_SERVICE_HOST', '0.0.0.0')
    CVM_CDA_GRAPH_SERVICE_PORT = int(os.environ.get('CVM_CDA_GRAPH_SERVICE_PORT', '5017'))
    CVM_CDA_GRAPH_GROUP_ID = os.environ.get('CVM_CDA_GRAPH_GROUP_ID', 'funds_flow_local:cvm_cda')
    CVM_CDA_GRAPH_MAX_FUNDS = int(os.environ.get('CVM_CDA_GRAPH_MAX_FUNDS', '350'))
    CVM_CDA_GRAPH_MAX_POSITIONS_PER_FUND = int(os.environ.get('CVM_CDA_GRAPH_MAX_POSITIONS_PER_FUND', '30'))
    CVM_CDA_GRAPH_MIN_ABS_VALUE = float(os.environ.get('CVM_CDA_GRAPH_MIN_ABS_VALUE', '10000000'))
    CVM_CDA_GRAPH_TARGET_FUNDS_PER_THEME = int(os.environ.get('CVM_CDA_GRAPH_TARGET_FUNDS_PER_THEME', '60'))
    NPORT_SEC_USER_AGENT = os.environ.get(
        'NPORT_SEC_USER_AGENT',
        'Aquiles market research contato@example.com',
    )
    MACRO_INGEST_ENABLE = os.environ.get('MACRO_INGEST_ENABLE', 'False').lower() == 'true'
    MACRO_INGEST_INTERVAL_SECONDS = int(os.environ.get('MACRO_INGEST_INTERVAL_SECONDS', '300'))
    MACRO_INGEST_AUTO_RESTART = os.environ.get('MACRO_INGEST_AUTO_RESTART', 'True').lower() == 'true'
    MACRO_INGEST_SUPERVISOR_INTERVAL_SECONDS = int(
        os.environ.get('MACRO_INGEST_SUPERVISOR_INTERVAL_SECONDS', '15')
    )
    MACRO_BLEU_WS_URL = os.environ.get(
        'MACRO_BLEU_WS_URL',
        'wss://news-ws.bleu.com.br/ws?topics=breaking,important,relevant',
    )
    MACRO_BLEU_WS_AUTH = os.environ.get('MACRO_BLEU_WS_AUTH') or os.environ.get('BLEU_WS_AUTH')
    MACRO_BLEU_TOPICS = [
        topic.strip()
        for topic in os.environ.get('MACRO_BLEU_TOPICS', 'breaking,important,relevant').split(',')
        if topic.strip()
    ]
    MACRO_BLEU_READ_WINDOWS = int(os.environ.get('MACRO_BLEU_READ_WINDOWS', '6'))
    MACRO_BLEU_WAIT_SECONDS = int(os.environ.get('MACRO_BLEU_WAIT_SECONDS', '10'))
    MACRO_BLEU_IDLE_TIMEOUT_SECONDS = int(os.environ.get('MACRO_BLEU_IDLE_TIMEOUT_SECONDS', '10'))
    MACRO_BLEU_RECONNECT_DELAY_SECONDS = int(os.environ.get('MACRO_BLEU_RECONNECT_DELAY_SECONDS', '2'))
    MACRO_INDEX_TICKERS = [
        ticker.strip()
        for ticker in os.environ.get('MACRO_INDEX_TICKERS', 'BVMF:WINM26').split(',')
        if ticker.strip()
    ]
    MACRO_DOLLAR_TICKERS = [
        ticker.strip()
        for ticker in os.environ.get('MACRO_DOLLAR_TICKERS', 'BVMF:WDOK26').split(',')
        if ticker.strip()
    ]
    MACRO_CURVE_SHORT_TICKERS = [
        ticker.strip()
        for ticker in os.environ.get('MACRO_CURVE_SHORT_TICKERS', 'BVMF:DI1F27,BVMF:DI1F28').split(',')
        if ticker.strip()
    ]
    MACRO_CURVE_LONG_TICKERS = [
        ticker.strip()
        for ticker in os.environ.get('MACRO_CURVE_LONG_TICKERS', 'BVMF:DI1F29,BVMF:DI1F30,BVMF:DI1F31,BVMF:DI1F35').split(',')
        if ticker.strip()
    ]
    MACRO_PARTICIPANT_CROSS_ASSET_DI_TICKERS = [
        ticker.strip()
        for ticker in os.environ.get(
            'MACRO_PARTICIPANT_CROSS_ASSET_DI_TICKERS',
            'BVMF:DI1F28,BVMF:DI1F29,BVMF:DI1F30,BVMF:DI1F31,BVMF:DI1F35',
        ).split(',')
        if ticker.strip()
    ]
    MACRO_AQUANT_TICKERS = [
        ticker.strip()
        for ticker in os.environ.get(
            'MACRO_AQUANT_TICKERS',
            ','.join(
                dict.fromkeys(
                    MACRO_INDEX_TICKERS
                    + MACRO_DOLLAR_TICKERS
                    + MACRO_CURVE_SHORT_TICKERS
                    + MACRO_CURVE_LONG_TICKERS
                )
            )
        ).split(',')
        if ticker.strip()
    ]
    MACRO_AQUANT_SECURITY_SYMBOLS = [
        symbol.strip()
        for symbol in os.environ.get('MACRO_AQUANT_SECURITY_SYMBOLS', 'VALE3,PETR4,ITUB4,BPAC11,BBDC4').split(',')
        if symbol.strip()
    ]
    MACRO_AQUANT_OHLCV_INTERVAL = os.environ.get('MACRO_AQUANT_OHLCV_INTERVAL', '1 min')
    MACRO_AQUANT_OHLCV_WINDOW_MINUTES = int(os.environ.get('MACRO_AQUANT_OHLCV_WINDOW_MINUTES', '30'))
    MACRO_AQUANT_TIMEOUT_SECONDS = int(os.environ.get('MACRO_AQUANT_TIMEOUT_SECONDS', '20'))
    MACRO_ANALYSIS_WINDOW_MINUTES = int(os.environ.get('MACRO_ANALYSIS_WINDOW_MINUTES', '5'))
    MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_INTERVAL_SECONDS', '15'))
    MACRO_PARTICIPANT_HEATMAP_HISTORY_MINUTES = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_HISTORY_MINUTES', '45'))
    MACRO_PARTICIPANT_HEATMAP_PARTICIPANT_LIMIT = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_PARTICIPANT_LIMIT', '14'))
    MACRO_PARTICIPANT_HEATMAP_CATALOG_LIMIT = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_CATALOG_LIMIT', '10'))
    MACRO_PARTICIPANT_HEATMAP_CANDLE_LIMIT = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_CANDLE_LIMIT', '45'))
    MACRO_PARTICIPANT_HEATMAP_DAY_CANDLE_LIMIT = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_DAY_CANDLE_LIMIT', '720'))
    MACRO_PARTICIPANT_HEATMAP_SESSION_START_HOUR = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_SESSION_START_HOUR', '9'))
    MACRO_PARTICIPANT_HEATMAP_SESSION_START_MINUTE = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_SESSION_START_MINUTE', '0'))
    MACRO_PARTICIPANT_HEATMAP_ENABLE = os.environ.get('MACRO_PARTICIPANT_HEATMAP_ENABLE', 'True').lower() == 'true'
    MACRO_PARTICIPANT_HEATMAP_AUTO_START = os.environ.get('MACRO_PARTICIPANT_HEATMAP_AUTO_START', 'True').lower() == 'true'
    MACRO_PARTICIPANT_HEATMAP_SESSION_SAMPLE_LIMIT = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_SESSION_SAMPLE_LIMIT', '2600'))
    MACRO_PARTICIPANT_HEATMAP_RENDER_LOOKBACK_MINUTES = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_RENDER_LOOKBACK_MINUTES', '20'))
    MACRO_PARTICIPANT_HEATMAP_POINT_LIMIT = int(os.environ.get('MACRO_PARTICIPANT_HEATMAP_POINT_LIMIT', '420'))
    MACRO_PARTICIPANT_PRESSURE_WINDOWS = _parse_int_list(
        os.environ.get('MACRO_PARTICIPANT_PRESSURE_WINDOWS', '1,3,5,15'),
        [1, 3, 5, 15],
    )
    MACRO_PARTICIPANT_PRESSURE_PRIMARY_WINDOW = int(os.environ.get('MACRO_PARTICIPANT_PRESSURE_PRIMARY_WINDOW', '5'))
    MACRO_PARTICIPANT_VALUE_AREA_RATIO = float(os.environ.get('MACRO_PARTICIPANT_VALUE_AREA_RATIO', '0.70'))
    MACRO_PARTICIPANT_VALUE_MAX_LEVELS = int(os.environ.get('MACRO_PARTICIPANT_VALUE_MAX_LEVELS', '8'))
    MACRO_NEWS_LINK_LOOKBACK_MINUTES = int(os.environ.get('MACRO_NEWS_LINK_LOOKBACK_MINUTES', '180'))
    MACRO_OPTIONS_HEATMAP_CONTEXT_ENABLE = os.environ.get(
        'MACRO_OPTIONS_HEATMAP_CONTEXT_ENABLE',
        'True',
    ).lower() == 'true'
    MACRO_OPTIONS_HEATMAP_CONTEXT_AUTO_START = os.environ.get(
        'MACRO_OPTIONS_HEATMAP_CONTEXT_AUTO_START',
        'True',
    ).lower() == 'true'
    MACRO_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS = int(
        os.environ.get('MACRO_OPTIONS_HEATMAP_CONTEXT_LOOP_SECONDS', '300')
    )
    MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS = int(
        os.environ.get('MACRO_OPTIONS_LIVE_CAPTURE_INTERVAL_SECONDS', '60')
    )
    MACRO_OPTIONS_LIVE_CAPTURE_STATE_LIMIT = int(
        os.environ.get('MACRO_OPTIONS_LIVE_CAPTURE_STATE_LIMIT', '20')
    )
    MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS = int(
        os.environ.get('MACRO_OPTIONS_FAIR_VALUE_SAMPLE_INTERVAL_SECONDS', '300')
    )
    MACRO_OPTIONS_FAIR_VALUE_SAMPLE_LIMIT = int(
        os.environ.get('MACRO_OPTIONS_FAIR_VALUE_SAMPLE_LIMIT', '960')
    )
    MACRO_OPTIONS_GAMMA_REGION_LIMIT = int(
        os.environ.get('MACRO_OPTIONS_GAMMA_REGION_LIMIT', '14')
    )
    MACRO_BLOOMBERG_ENABLE = os.environ.get('MACRO_BLOOMBERG_ENABLE', 'True').lower() == 'true'
    BLOOMBERG_REALTIME_REFERENCE_ENABLE = os.environ.get('BLOOMBERG_REALTIME_REFERENCE_ENABLE', 'False').lower() == 'true'
    BLOOMBERG_EXCEL_FALLBACK_ENABLE = os.environ.get('BLOOMBERG_EXCEL_FALLBACK_ENABLE', 'False').lower() == 'true'
    MACRO_BLOOMBERG_HOST = os.environ.get('MACRO_BLOOMBERG_HOST', '127.0.0.1')
    MACRO_BLOOMBERG_PORT = int(os.environ.get('MACRO_BLOOMBERG_PORT', '8194'))
    MACRO_BLOOMBERG_TIMEOUT_SECONDS = int(os.environ.get('MACRO_BLOOMBERG_TIMEOUT_SECONDS', '15'))
    MACRO_BLOOMBERG_FIELDS = [
        field.strip()
        for field in os.environ.get(
            'MACRO_BLOOMBERG_FIELDS',
            'PX_LAST,CHG_NET_1D,CHG_PCT_1D,PX_OPEN,PX_HIGH,PX_LOW,PX_VOLUME,BID,ASK'
        ).split(',')
        if field.strip()
    ]
    MACRO_BLOOMBERG_REFERENCE_SECURITIES = [
        security.strip()
        for security in os.environ.get(
            'MACRO_BLOOMBERG_REFERENCE_SECURITIES',
            ','.join(item["security"] for item in DEFAULT_MACRO_BLOOMBERG_REFERENCE_ASSETS)
        ).split(',')
        if security.strip()
    ]
    MACRO_BLOOMBERG_REFERENCE_ASSETS = [
        {
            **DEFAULT_MACRO_BLOOMBERG_REFERENCE_MAP.get(
                security,
                {
                    "security": security,
                    "label": security,
                    "category": "reference",
                    "bucket": "reference",
                },
            )
        }
        for security in MACRO_BLOOMBERG_REFERENCE_SECURITIES
    ]
    MACRO_THERMOMETER_ENABLE_LLM = os.environ.get('MACRO_THERMOMETER_ENABLE_LLM', 'False').lower() == 'true'
    MACRO_REPORT_SOURCES_ENABLE = os.environ.get('MACRO_REPORT_SOURCES_ENABLE', 'True').lower() == 'true'
    MACRO_REPORT_SOURCES_AUTO_START = os.environ.get('MACRO_REPORT_SOURCES_AUTO_START', 'True').lower() == 'true'
    MACRO_REPORT_SOURCES_UPDATE_TIME = os.environ.get('MACRO_REPORT_SOURCES_UPDATE_TIME', '07:30').strip()
    MACRO_REPORT_SOURCES_LOOKBACK_DAYS = int(os.environ.get('MACRO_REPORT_SOURCES_LOOKBACK_DAYS', '30'))
    MACRO_REPORT_SOURCES_TIMEOUT_SECONDS = float(os.environ.get('MACRO_REPORT_SOURCES_TIMEOUT_SECONDS', '12'))
    MACRO_REPORT_SOURCES_CACHE_SECONDS = int(os.environ.get('MACRO_REPORT_SOURCES_CACHE_SECONDS', '900'))
    MACRO_REPORT_SOURCES_FRED_CSV_FALLBACK = os.environ.get(
        'MACRO_REPORT_SOURCES_FRED_CSV_FALLBACK',
        'False',
    ).lower() == 'true'
    FRED_API_KEY = os.environ.get('FRED_API_KEY', '')

    # Funds Flow Local configuration
    FUNDS_FLOW_LOCAL_DATA_DIR = os.environ.get(
        'FUNDS_FLOW_LOCAL_DATA_DIR',
        os.path.join(MACRO_DATA_DIR, 'funds_flow_local'),
    )
    FUNDS_FLOW_LOCAL_ENABLE = os.environ.get('FUNDS_FLOW_LOCAL_ENABLE', 'True').lower() == 'true'
    FUNDS_FLOW_LOCAL_AUTO_START = os.environ.get('FUNDS_FLOW_LOCAL_AUTO_START', 'False').lower() == 'true'
    FUNDS_FLOW_LOCAL_UPDATE_TIME = os.environ.get('FUNDS_FLOW_LOCAL_UPDATE_TIME', '07:40').strip()
    FUNDS_FLOW_LOCAL_HISTORY_DAYS = int(os.environ.get('FUNDS_FLOW_LOCAL_HISTORY_DAYS', '95'))
    FUNDS_FLOW_LOCAL_B3_HISTORY_DAYS = int(os.environ.get('FUNDS_FLOW_LOCAL_B3_HISTORY_DAYS', '21'))
    FUNDS_FLOW_LOCAL_B3_OPEN_INTEREST_ASSETS = os.environ.get(
        'FUNDS_FLOW_LOCAL_B3_OPEN_INTEREST_ASSETS',
        'DI1,DOL,WDO,WIN,IND,DAP,DDI',
    )
    FUNDS_FLOW_LOCAL_TIMEOUT_SECONDS = float(os.environ.get('FUNDS_FLOW_LOCAL_TIMEOUT_SECONDS', '45'))
    FUNDS_FLOW_LOCAL_CACHE_SECONDS = int(os.environ.get('FUNDS_FLOW_LOCAL_CACHE_SECONDS', '900'))
    ETF_DAILY_FLOW_DATA_DIR = os.environ.get(
        'ETF_DAILY_FLOW_DATA_DIR',
        os.path.join(MACRO_DATA_DIR, 'etf_daily_flow'),
    )
    ETF_DAILY_FLOW_ENABLE = os.environ.get('ETF_DAILY_FLOW_ENABLE', 'True').lower() == 'true'
    ETF_DAILY_FLOW_AUTO_START = os.environ.get('ETF_DAILY_FLOW_AUTO_START', 'True').lower() == 'true'
    ETF_DAILY_FLOW_SERVICE_HOST = os.environ.get('ETF_DAILY_FLOW_SERVICE_HOST', '0.0.0.0')
    ETF_DAILY_FLOW_SERVICE_PORT = int(os.environ.get('ETF_DAILY_FLOW_SERVICE_PORT', '5018'))
    ETF_DAILY_FLOW_TIMEZONE = os.environ.get('ETF_DAILY_FLOW_TIMEZONE', 'America/Sao_Paulo')
    ETF_DAILY_FLOW_CAPTURE_TIMES = os.environ.get('ETF_DAILY_FLOW_CAPTURE_TIMES', '20:15,22:15,00:30')
    ETF_DAILY_FLOW_REFRESH_CATALOG_BEFORE_COLLECT = os.environ.get(
        'ETF_DAILY_FLOW_REFRESH_CATALOG_BEFORE_COLLECT',
        'True',
    ).lower() == 'true'
    ETF_DAILY_FLOW_CATALOG_PROVIDERS = os.environ.get(
        'ETF_DAILY_FLOW_CATALOG_PROVIDERS',
        'schwab,state_street,vaneck,ishares,dimensional,vanguard,invesco,proshares,global_x',
    )
    ETF_DAILY_FLOW_SCHEDULER_POLL_SECONDS = int(os.environ.get('ETF_DAILY_FLOW_SCHEDULER_POLL_SECONDS', '60'))
    ETF_DAILY_FLOW_REQUEST_TIMEOUT_SECONDS = float(os.environ.get('ETF_DAILY_FLOW_REQUEST_TIMEOUT_SECONDS', '25'))
    ETF_DAILY_FLOW_REQUEST_MAX_ATTEMPTS = int(os.environ.get('ETF_DAILY_FLOW_REQUEST_MAX_ATTEMPTS', '3'))
    ETF_DAILY_FLOW_RETRY_BACKOFF_SECONDS = float(os.environ.get('ETF_DAILY_FLOW_RETRY_BACKOFF_SECONDS', '3'))
    ETF_DAILY_FLOW_MAX_STALE_HOURS = float(os.environ.get('ETF_DAILY_FLOW_MAX_STALE_HOURS', '48'))
    ETF_DAILY_FLOW_CONTRACT_FAILURE_THRESHOLD = int(os.environ.get('ETF_DAILY_FLOW_CONTRACT_FAILURE_THRESHOLD', '2'))
    ETF_DAILY_FLOW_SEED_DEFAULT_UNIVERSE = os.environ.get(
        'ETF_DAILY_FLOW_SEED_DEFAULT_UNIVERSE',
        'True',
    ).lower() == 'true'
    ETF_DAILY_FLOW_USER_AGENT = os.environ.get(
        'ETF_DAILY_FLOW_USER_AGENT',
        'Aquiles ETF daily flow research collector/1.0 (+https://localhost)',
    )
    ETF_DAILY_FLOW_UNIVERSE_JSON = os.environ.get('ETF_DAILY_FLOW_UNIVERSE_JSON', '')

    # ─── OpLab ────────────────────────────────────────────────────────────────
    OPLAB_ENABLE = os.environ.get('OPLAB_ENABLE', 'False').lower() == 'true'
    OPLAB_BASE_URL = os.environ.get('OPLAB_BASE_URL', 'https://api.oplab.com.br/v3')
    OPLAB_ACCESS_TOKEN = os.environ.get('OPLAB_ACCESS_TOKEN', '')
    OPLAB_EMAIL = os.environ.get('OPLAB_EMAIL', '')
    OPLAB_PASSWORD = os.environ.get('OPLAB_PASSWORD', '')
    OPLAB_RATE_LIMIT_PER_MINUTE = int(os.environ.get('OPLAB_RATE_LIMIT_PER_MINUTE', '88'))
    OPLAB_REQUEST_TIMEOUT = int(os.environ.get('OPLAB_REQUEST_TIMEOUT', '30'))
    OPLAB_IV_CACHE_TTL_SECONDS = int(os.environ.get('OPLAB_IV_CACHE_TTL_SECONDS', '300'))
    OPLAB_MAX_DTM = int(os.environ.get('OPLAB_MAX_DTM', '90'))  # max dias ate vencimento no chain
    OPLAB_CHAIN_STABILITY_POLL_SECONDS = float(os.environ.get('OPLAB_CHAIN_STABILITY_POLL_SECONDS', '0.5'))
    OPLAB_CHAIN_STABILITY_MAX_POLLS = int(os.environ.get('OPLAB_CHAIN_STABILITY_MAX_POLLS', '6'))
    OPLAB_CHAIN_STABLE_ROUNDS = int(os.environ.get('OPLAB_CHAIN_STABLE_ROUNDS', '2'))
    # Mapeamento de underlying Bloomberg → OpLab. Ex: "IBOVE Index=IBOV,SPX Index="
    OPLAB_UNDERLYING_MAP = {
        k.strip(): v.strip()
        for item in os.environ.get('OPLAB_UNDERLYING_MAP', 'IBOVE Index=IBOV,BOVA11 Index=BOVA11').split(',')
        for k, _, v in [item.partition('=')]
        if k.strip() and v.strip()
    }

    # Options module configuration
    OPTIONS_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/options')
    OPTIONS_ENABLE = os.environ.get('OPTIONS_ENABLE', 'True').lower() == 'true'
    OPTIONS_INGEST_ENABLE = os.environ.get('OPTIONS_INGEST_ENABLE', 'False').lower() == 'true'
    OPTIONS_INGEST_AUTO_RESTART = os.environ.get('OPTIONS_INGEST_AUTO_RESTART', 'True').lower() == 'true'
    OPTIONS_COLLECTOR_SERVICE_HOST = os.environ.get('OPTIONS_COLLECTOR_SERVICE_HOST', '0.0.0.0')
    OPTIONS_COLLECTOR_SERVICE_PORT = int(os.environ.get('OPTIONS_COLLECTOR_SERVICE_PORT', '5021'))
    OPTIONS_COLLECTOR_SERVICE_URL = os.environ.get(
        'OPTIONS_COLLECTOR_SERVICE_URL',
        f"http://127.0.0.1:{OPTIONS_COLLECTOR_SERVICE_PORT}",
    ).rstrip('/')
    OPTIONS_INGEST_SUPERVISOR_INTERVAL_SECONDS = int(
        os.environ.get('OPTIONS_INGEST_SUPERVISOR_INTERVAL_SECONDS', '15')
    )
    OPTIONS_LOOP_POLL_SECONDS = int(os.environ.get('OPTIONS_LOOP_POLL_SECONDS', '5'))
    OPTIONS_BLOOMBERG_UNDERLYINGS = [
        security.strip()
        for security in os.environ.get('OPTIONS_BLOOMBERG_UNDERLYINGS', 'IBOVE Index,SPX Index').split(',')
        if security.strip()
    ]
    OPTIONS_UNDERLYING_TRADE_MAP = _parse_key_value_mapping(
        os.environ.get('OPTIONS_UNDERLYING_TRADE_MAP', 'IBOVE Index=BVMF:WINM26,SPX Index=ESA Index')
    )
    OPTIONS_MAX_BUSINESS_DAYS = int(os.environ.get('OPTIONS_MAX_BUSINESS_DAYS', '90'))
    OPTIONS_MONEYNESS_BAND_PCT = float(os.environ.get('OPTIONS_MONEYNESS_BAND_PCT', '0.12'))
    OPTIONS_ATM_PROXIMITY_PCT = float(os.environ.get('OPTIONS_ATM_PROXIMITY_PCT', '0.02'))
    OPTIONS_STRATEGIC_STRIKES = [
        strike.strip()
        for strike in os.environ.get('OPTIONS_STRATEGIC_STRIKES', '').split(',')
        if strike.strip()
    ]
    OPTIONS_STRUCTURAL_SNAPSHOT_INTERVAL_SECONDS = int(
        os.environ.get('OPTIONS_STRUCTURAL_SNAPSHOT_INTERVAL_SECONDS', '300')
    )
    OPTIONS_LIQUID_SNAPSHOT_INTERVAL_SECONDS = int(
        os.environ.get('OPTIONS_LIQUID_SNAPSHOT_INTERVAL_SECONDS', '60')
    )
    OPTIONS_CRITICAL_SNAPSHOT_INTERVAL_SECONDS = int(
        os.environ.get('OPTIONS_CRITICAL_SNAPSHOT_INTERVAL_SECONDS', '30')
    )
    OPTIONS_TICK_CAPTURE_ENABLE = os.environ.get('OPTIONS_TICK_CAPTURE_ENABLE', 'False').lower() == 'true'
    OPTIONS_TICK_CAPTURE_MAX_CONTRACTS = int(os.environ.get('OPTIONS_TICK_CAPTURE_MAX_CONTRACTS', '40'))

    # ─── Volume Activity Tracker ──────────────────────────────────────────────
    # Monitora variação de volume em TODAS as opções da cadeia (incluindo sem OI).
    OPTIONS_VOLUME_TRACK_ENABLE = os.environ.get('OPTIONS_VOLUME_TRACK_ENABLE', 'False').lower() == 'true'
    # Intervalo de polling em segundos (default 60 s — 1 chamada/min por underlying)
    OPTIONS_VOLUME_POLL_SECONDS = int(os.environ.get('OPTIONS_VOLUME_POLL_SECONDS', '60'))
    # Delta mínimo de volume para gerar um evento (filtra ruído de arredondamento)
    OPTIONS_VOLUME_MIN_DELTA = float(os.environ.get('OPTIONS_VOLUME_MIN_DELTA', '1.0'))
    # Quantos dias de histórico de atividade manter em consultas sem filtro de data
    OPTIONS_VOLUME_ACTIVITY_LOOKBACK_DAYS = int(os.environ.get('OPTIONS_VOLUME_ACTIVITY_LOOKBACK_DAYS', '2'))
    OPTIONS_LIQUID_TOP_N_PER_EXPIRY = int(os.environ.get('OPTIONS_LIQUID_TOP_N_PER_EXPIRY', '12'))
    OPTIONS_LIQUID_MAX_CONTRACTS = int(os.environ.get('OPTIONS_LIQUID_MAX_CONTRACTS', '150'))
    OPTIONS_CRITICAL_MAX_CONTRACTS = int(os.environ.get('OPTIONS_CRITICAL_MAX_CONTRACTS', '40'))
    OPTIONS_OI_BACKFILL_LOOKBACK_DAYS = int(os.environ.get('OPTIONS_OI_BACKFILL_LOOKBACK_DAYS', '180'))
    OPTIONS_BACKFILL_BATCH_SIZE = int(os.environ.get('OPTIONS_BACKFILL_BATCH_SIZE', '25'))
    OPTIONS_HOT_RETENTION_DAYS = int(os.environ.get('OPTIONS_HOT_RETENTION_DAYS', '2'))
    OPTIONS_WARM_RETENTION_DAYS = int(os.environ.get('OPTIONS_WARM_RETENTION_DAYS', '60'))
    OPTIONS_DAILY_HISTORY_UPDATE_HOUR = int(os.environ.get('OPTIONS_DAILY_HISTORY_UPDATE_HOUR', '18'))
    OPTIONS_B3_DAILY_SNAPSHOT_ENABLE = os.environ.get('OPTIONS_B3_DAILY_SNAPSHOT_ENABLE', 'True').lower() == 'true'
    OPTIONS_B3_DAILY_SNAPSHOT_TIME = os.environ.get('OPTIONS_B3_DAILY_SNAPSHOT_TIME', '09:00').strip()
    OPTIONS_MODEL_SCHEDULE_ENABLE = os.environ.get('OPTIONS_MODEL_SCHEDULE_ENABLE', 'True').lower() == 'true'
    OPTIONS_MODEL_SCHEDULE_TIMES = [
        item.strip()
        for item in os.environ.get('OPTIONS_MODEL_SCHEDULE_TIMES', '10:03,16:30,16:55').split(',')
        if item.strip()
    ]
    OPTIONS_MODEL_SCHEDULE_UNDERLYINGS = [
        security.strip()
        for security in os.environ.get('OPTIONS_MODEL_SCHEDULE_UNDERLYINGS', 'IBOVE Index').split(',')
        if security.strip()
    ]
    OPTIONS_SCHEDULE_RETRY_COOLDOWN_SECONDS = int(
        os.environ.get('OPTIONS_SCHEDULE_RETRY_COOLDOWN_SECONDS', '900')
    )
    OPTIONS_SCHEDULE_LOCK_LEASE_SECONDS = int(
        os.environ.get('OPTIONS_SCHEDULE_LOCK_LEASE_SECONDS', '7200')
    )
    OPTIONS_WYRM_AUTORUN_ENABLE = os.environ.get('OPTIONS_WYRM_AUTORUN_ENABLE', 'True').lower() == 'true'
    OPTIONS_WYRM_AUTORUN_HOUR = int(os.environ.get('OPTIONS_WYRM_AUTORUN_HOUR', '8'))
    OPTIONS_WYRM_AUTORUN_MINUTE = int(os.environ.get('OPTIONS_WYRM_AUTORUN_MINUTE', '30'))
    # Cooldown em segundos entre tentativas falhas do Wyrm (default 20 min).
    # Evita loop infinito quando Bloomberg nao retorna opcoes.
    OPTIONS_WYRM_RETRY_COOLDOWN_SECONDS = int(os.environ.get('OPTIONS_WYRM_RETRY_COOLDOWN_SECONDS', '1200'))
    OPTIONS_WYRM_AUTORUN_UNDERLYINGS = [
        security.strip()
        for security in os.environ.get('OPTIONS_WYRM_AUTORUN_UNDERLYINGS', 'IBOVE Index').split(',')
        if security.strip()
    ]

    # Options quantitative modeling
    OPTIONS_MODEL_DATA_DIR = os.path.join(OPTIONS_DATA_DIR, 'analytics')
    OPTIONS_MODEL_ENABLE = os.environ.get('OPTIONS_MODEL_ENABLE', 'True').lower() == 'true'
    OPTIONS_MODEL_DEFAULT_TIER = os.environ.get('OPTIONS_MODEL_DEFAULT_TIER', 'full').strip().lower()
    OPTIONS_MODEL_SIGN_CONVENTION = os.environ.get('OPTIONS_MODEL_SIGN_CONVENTION', 'neutral').strip().lower()
    OPTIONS_MODEL_SIGNAL_THRESHOLD = float(os.environ.get('OPTIONS_MODEL_SIGNAL_THRESHOLD', '0.20'))
    OPTIONS_MODEL_CONTRACT_POINT_VALUE = float(os.environ.get('OPTIONS_MODEL_CONTRACT_POINT_VALUE', '1.0'))
    OPTIONS_MODEL_WIN_POINT_VALUE = float(os.environ.get('OPTIONS_MODEL_WIN_POINT_VALUE', '0.2'))
    OPTIONS_MODEL_GRID_RANGE_PCT = float(os.environ.get('OPTIONS_MODEL_GRID_RANGE_PCT', '0.10'))
    OPTIONS_MODEL_GRID_POINTS = int(os.environ.get('OPTIONS_MODEL_GRID_POINTS', '81'))
    OPTIONS_MODEL_GEX_WEIGHT = float(os.environ.get('OPTIONS_MODEL_GEX_WEIGHT', '1.0'))
    OPTIONS_MODEL_VEX_WEIGHT = float(os.environ.get('OPTIONS_MODEL_VEX_WEIGHT', '0.35'))
    OPTIONS_MODEL_CEX_WEIGHT = float(os.environ.get('OPTIONS_MODEL_CEX_WEIGHT', '0.25'))
    OPTIONS_MODEL_MIN_TIME_YEARS = float(os.environ.get('OPTIONS_MODEL_MIN_TIME_YEARS', str(1 / 2520)))
    OPTIONS_MODEL_VOL_EPS = float(os.environ.get('OPTIONS_MODEL_VOL_EPS', '0.005'))
    OPTIONS_MODEL_TIME_EPS_DAYS = float(os.environ.get('OPTIONS_MODEL_TIME_EPS_DAYS', '1.0'))
    OPTIONS_MODEL_FALLBACK_RATE = DEFAULT_OPTIONS_MODEL_FALLBACK_RATE
    OPTIONS_MODEL_SPOT_SECURITY_MAP = _parse_key_value_mapping(
        os.environ.get('OPTIONS_MODEL_SPOT_SECURITY_MAP', 'IBOVE Index=IBOV Index,SPX Index=SPX Index')
    )
    OPTIONS_MODEL_FORWARD_SECURITY_MAP = _parse_key_value_mapping(
        os.environ.get('OPTIONS_MODEL_FORWARD_SECURITY_MAP', 'IBOVE Index=XB1 Index,SPX Index=ESA Index|ES1 Index')
    )
    OPTIONS_MODEL_DIVIDEND_SECURITY_MAP = _parse_key_value_mapping(
        os.environ.get('OPTIONS_MODEL_DIVIDEND_SECURITY_MAP', 'IBOVE Index=IDIV Index')
    )
    OPTIONS_MODEL_RATE_CURVE_POINTS = {
        key.strip(): value.strip()
        for key, value in _parse_key_value_mapping(
            os.environ.get(
                'OPTIONS_MODEL_RATE_CURVE_POINTS',
                '21=0.135,42=0.136,63=0.137,84=0.138,126=0.139'
            )
        ).items()
    }
    OPTIONS_MODEL_RATE_CURVE_DAY_POINTS = {
        int(key): _parse_float(value, DEFAULT_OPTIONS_MODEL_FALLBACK_RATE)
        for key, value in OPTIONS_MODEL_RATE_CURVE_POINTS.items()
        if key.isdigit() and value.replace('.', '', 1).replace('-', '', 1).isdigit()
    }
    OPTIONS_MODEL_DEALER_INFERENCE_ENABLE = os.environ.get('OPTIONS_MODEL_DEALER_INFERENCE_ENABLE', 'True').lower() == 'true'
    OPTIONS_MODEL_DEALER_INFERENCE_RANGE_POINTS = float(
        os.environ.get('OPTIONS_MODEL_DEALER_INFERENCE_RANGE_POINTS', '300')
    )
    OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_IV = float(
        os.environ.get('OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_IV', '0.45')
    )
    OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_OI = float(
        os.environ.get('OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_OI', '0.25')
    )
    OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_GEX = float(
        os.environ.get('OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_GEX', '0.20')
    )
    OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_GAMMA = float(
        os.environ.get('OPTIONS_MODEL_DEALER_INFERENCE_WEIGHT_GAMMA', '0.10')
    )
    OPTIONS_MODEL_DEALER_INFERENCE_LAMBDA_IV = float(
        os.environ.get('OPTIONS_MODEL_DEALER_INFERENCE_LAMBDA_IV', '3.0')
    )
    OPTIONS_MODEL_DEALER_INFERENCE_LAMBDA_OI = float(
        os.environ.get('OPTIONS_MODEL_DEALER_INFERENCE_LAMBDA_OI', '2.5')
    )
    OPTIONS_MODEL_DEALER_INFERENCE_EPS = float(
        os.environ.get('OPTIONS_MODEL_DEALER_INFERENCE_EPS', '0.000001')
    )
    OPTIONS_MODEL_GAMMA_FLIP_LOOKBACK_DAYS = int(
        os.environ.get('OPTIONS_MODEL_GAMMA_FLIP_LOOKBACK_DAYS', '10')
    )
    OPTIONS_MODEL_GAMMA_FLIP_MAX_DATES = int(
        os.environ.get('OPTIONS_MODEL_GAMMA_FLIP_MAX_DATES', '10')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_ENABLE = os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_ENABLE', 'True').lower() == 'true'
    OPTIONS_MODEL_RANGE_PROJECTION_EXPIRY_WEIGHT_OI_POWER = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_EXPIRY_WEIGHT_OI_POWER', '0.55')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_EXPIRY_WEIGHT_GAMMA_POWER = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_EXPIRY_WEIGHT_GAMMA_POWER', '0.45')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_EXPIRY_DECAY_KAPPA = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_EXPIRY_DECAY_KAPPA', '4.0')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_CENTER_WEIGHT_FORWARD = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_CENTER_WEIGHT_FORWARD', '0.45')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_CENTER_WEIGHT_DEALER = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_CENTER_WEIGHT_DEALER', '0.30')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_CENTER_WEIGHT_RND = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_CENTER_WEIGHT_RND', '0.25')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_GEX_DEFORM = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_GEX_DEFORM', '0.22')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_VEX_DEFORM = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_VEX_DEFORM', '0.10')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_CEX_DEFORM = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_CEX_DEFORM', '0.08')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_MIN_STRIKES_PER_EXPIRY = int(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_MIN_STRIKES_PER_EXPIRY', '5')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_MAX_EXPIRIES = int(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_MAX_EXPIRIES', '8')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_TACTICAL_HORIZON_DAYS = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_TACTICAL_HORIZON_DAYS', '1.0')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_STRIKE_HORIZON_POINTS = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_STRIKE_HORIZON_POINTS', '20000')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_DOWNSIDE_RATIO_CAP_BASE = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_DOWNSIDE_RATIO_CAP_BASE', '1.55')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_DOWNSIDE_RATIO_CAP_STEP = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_DOWNSIDE_RATIO_CAP_STEP', '0.10')
    )
    OPTIONS_MODEL_RANGE_PROJECTION_DOWNSIDE_FLOOR_MULTIPLIER = float(
        os.environ.get('OPTIONS_MODEL_RANGE_PROJECTION_DOWNSIDE_FLOOR_MULTIPLIER', '0.95')
    )
    OPTIONS_GLOBAL_TRIANGULATION_ENABLE = os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_ENABLE', 'True').lower() == 'true'
    OPTIONS_GLOBAL_TRIANGULATION_ASSETS_JSON = os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_ASSETS_JSON', '')
    OPTIONS_GLOBAL_TRIANGULATION_BAR_INTERVAL_MINUTES = int(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_BAR_INTERVAL_MINUTES', '5')
    )
    OPTIONS_GLOBAL_TRIANGULATION_LOOKBACK_HOURS = int(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_LOOKBACK_HOURS', '12')
    )
    OPTIONS_GLOBAL_TRIANGULATION_MIN_POINTS = int(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_MIN_POINTS', '24')
    )
    OPTIONS_GLOBAL_TRIANGULATION_EWMA_ALPHA = float(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_EWMA_ALPHA', '0.16')
    )
    OPTIONS_GLOBAL_TRIANGULATION_CORR_SHORT_WINDOW = int(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_CORR_SHORT_WINDOW', '12')
    )
    OPTIONS_GLOBAL_TRIANGULATION_CORR_SMOOTH_WINDOW = int(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_CORR_SMOOTH_WINDOW', '36')
    )
    OPTIONS_GLOBAL_TRIANGULATION_DISTORTION_SIGMA_MULTIPLIER = float(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_DISTORTION_SIGMA_MULTIPLIER', '1.5')
    )
    OPTIONS_GLOBAL_TRIANGULATION_DISTORTION_WEIGHT = float(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_DISTORTION_WEIGHT', '0.40')
    )
    OPTIONS_GLOBAL_TRIANGULATION_STRUCTURAL_WEIGHT = float(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_STRUCTURAL_WEIGHT', '0.35')
    )
    OPTIONS_GLOBAL_TRIANGULATION_CORR_WEIGHT = float(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_CORR_WEIGHT', '0.25')
    )
    OPTIONS_GLOBAL_TRIANGULATION_LOCAL_MODEL_MAX_AGE_SECONDS = int(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_LOCAL_MODEL_MAX_AGE_SECONDS', '300')
    )
    OPTIONS_GLOBAL_TRIANGULATION_LEVEL_CLUSTER_POINTS = float(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_LEVEL_CLUSTER_POINTS', '450')
    )
    OPTIONS_GLOBAL_TRIANGULATION_LEVEL_MATCH_POINTS = float(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_LEVEL_MATCH_POINTS', '350')
    )
    OPTIONS_GLOBAL_TRIANGULATION_MIN_CORR_FOR_MAPPING = float(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_MIN_CORR_FOR_MAPPING', '0.35')
    )
    OPTIONS_GLOBAL_TRIANGULATION_VOL_BAND_SIGMA = float(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_VOL_BAND_SIGMA', '1.25')
    )
    OPTIONS_GLOBAL_TRIANGULATION_TOP_MAPPED_LEVELS = int(
        os.environ.get('OPTIONS_GLOBAL_TRIANGULATION_TOP_MAPPED_LEVELS', '24')
    )
    OPTIONS_FAIR_VALUE_ENABLE = os.environ.get('OPTIONS_FAIR_VALUE_ENABLE', 'True').lower() == 'true'
    OPTIONS_FAIR_VALUE_LOOKBACK_HOURS = int(os.environ.get('OPTIONS_FAIR_VALUE_LOOKBACK_HOURS', '120'))
    OPTIONS_FAIR_VALUE_MAX_SNAPSHOTS = int(os.environ.get('OPTIONS_FAIR_VALUE_MAX_SNAPSHOTS', '1600'))
    OPTIONS_FAIR_VALUE_MIN_POINTS = int(os.environ.get('OPTIONS_FAIR_VALUE_MIN_POINTS', '80'))
    OPTIONS_FAIR_VALUE_ZSCORE_WINDOW = int(os.environ.get('OPTIONS_FAIR_VALUE_ZSCORE_WINDOW', '36'))
    OPTIONS_FAIR_VALUE_FEATURE_MIN_COVERAGE_RATIO = float(
        os.environ.get('OPTIONS_FAIR_VALUE_FEATURE_MIN_COVERAGE_RATIO', '0.20')
    )
    OPTIONS_FAIR_VALUE_FEATURE_MIN_COVERAGE_FLOOR = int(
        os.environ.get('OPTIONS_FAIR_VALUE_FEATURE_MIN_COVERAGE_FLOOR', '12')
    )
    OPTIONS_FAIR_VALUE_FACTOR_RUN_FILL_TOLERANCE_MINUTES = float(
        os.environ.get('OPTIONS_FAIR_VALUE_FACTOR_RUN_FILL_TOLERANCE_MINUTES', '180')
    )
    OPTIONS_FAIR_VALUE_ENGINE_MODE = os.environ.get(
        'OPTIONS_FAIR_VALUE_ENGINE_MODE',
        'intraday_anchor',
    ).strip().lower()
    OPTIONS_FAIR_VALUE_INTRADAY_ANCHOR_TYPE = os.environ.get(
        'OPTIONS_FAIR_VALUE_INTRADAY_ANCHOR_TYPE',
        'previous_close',
    ).strip().lower()
    OPTIONS_FAIR_VALUE_RLS_FORGETTING = float(os.environ.get('OPTIONS_FAIR_VALUE_RLS_FORGETTING', '0.985'))
    OPTIONS_FAIR_VALUE_RLS_INIT_COVARIANCE = float(
        os.environ.get('OPTIONS_FAIR_VALUE_RLS_INIT_COVARIANCE', '250.0')
    )
    OPTIONS_FAIR_VALUE_RESIDUAL_SIGMA_HALFLIFE = float(
        os.environ.get('OPTIONS_FAIR_VALUE_RESIDUAL_SIGMA_HALFLIFE', '18.0')
    )
    OPTIONS_FAIR_VALUE_STATE_SPACE_MEASUREMENT_NOISE = float(
        os.environ.get('OPTIONS_FAIR_VALUE_STATE_SPACE_MEASUREMENT_NOISE', '18.0')
    )
    OPTIONS_FAIR_VALUE_STATE_SPACE_PROCESS_NOISE = float(
        os.environ.get('OPTIONS_FAIR_VALUE_STATE_SPACE_PROCESS_NOISE', '0.000004')
    )
    OPTIONS_FAIR_VALUE_BREADTH_SCALE_FLOOR = float(
        os.environ.get('OPTIONS_FAIR_VALUE_BREADTH_SCALE_FLOOR', '0.32')
    )
    OPTIONS_FAIR_VALUE_BREADTH_WARMUP_MINUTES = float(
        os.environ.get('OPTIONS_FAIR_VALUE_BREADTH_WARMUP_MINUTES', '45')
    )
    OPTIONS_FAIR_VALUE_BAND_SIGMA_MULTIPLIER = float(
        os.environ.get('OPTIONS_FAIR_VALUE_BAND_SIGMA_MULTIPLIER', '1.65')
    )
    OPTIONS_FAIR_VALUE_BAND_FLOOR_POINTS = float(
        os.environ.get('OPTIONS_FAIR_VALUE_BAND_FLOOR_POINTS', '350.0')
    )
    OPTIONS_FAIR_VALUE_BAND_VOL_WEIGHT = float(
        os.environ.get('OPTIONS_FAIR_VALUE_BAND_VOL_WEIGHT', '0.35')
    )
    OPTIONS_FAIR_VALUE_OPTIONS_OVERLAY_WEIGHT = float(
        os.environ.get('OPTIONS_FAIR_VALUE_OPTIONS_OVERLAY_WEIGHT', '0.30')
    )
    OPTIONS_FAIR_VALUE_GLOBAL_OVERLAY_WEIGHT = float(
        os.environ.get('OPTIONS_FAIR_VALUE_GLOBAL_OVERLAY_WEIGHT', '0.28')
    )
    OPTIONS_FAIR_VALUE_RESIDUAL_OVERLAY_WEIGHT = float(
        os.environ.get('OPTIONS_FAIR_VALUE_RESIDUAL_OVERLAY_WEIGHT', '0.22')
    )
    OPTIONS_FAIR_VALUE_OPTIONS_MAX_SIGMA_MULT = float(
        os.environ.get('OPTIONS_FAIR_VALUE_OPTIONS_MAX_SIGMA_MULT', '0.75')
    )
    OPTIONS_FAIR_VALUE_GLOBAL_MAX_SIGMA_MULT = float(
        os.environ.get('OPTIONS_FAIR_VALUE_GLOBAL_MAX_SIGMA_MULT', '0.90')
    )
    OPTIONS_FAIR_VALUE_RESIDUAL_MAX_SIGMA_MULT = float(
        os.environ.get('OPTIONS_FAIR_VALUE_RESIDUAL_MAX_SIGMA_MULT', '0.65')
    )
    OPTIONS_FAIR_VALUE_STRUCTURAL_FACTORS_JSON = os.environ.get(
        'OPTIONS_FAIR_VALUE_STRUCTURAL_FACTORS_JSON',
        '',
    )
    OPTIONS_FAIR_VALUE_QUALITY_ENABLE = os.environ.get(
        'OPTIONS_FAIR_VALUE_QUALITY_ENABLE',
        'True',
    ).lower() == 'true'
    OPTIONS_REGIME_PRICE_MAKING_ENABLE = os.environ.get(
        'OPTIONS_REGIME_PRICE_MAKING_ENABLE',
        'True',
    ).lower() == 'true'
    OPTIONS_ASSET_REGIME_ENGINE_ENABLE = os.environ.get(
        'OPTIONS_ASSET_REGIME_ENGINE_ENABLE',
        'True',
    ).lower() == 'true'
    OPTIONS_NONLINEAR_DEPENDENCE_ENGINE_ENABLE = os.environ.get(
        'OPTIONS_NONLINEAR_DEPENDENCE_ENGINE_ENABLE',
        'True',
    ).lower() == 'true'
    OPTIONS_PRICE_MAKING_ENGINE_ENABLE = os.environ.get(
        'OPTIONS_PRICE_MAKING_ENGINE_ENABLE',
        'True',
    ).lower() == 'true'
    OPTIONS_MARKET_STATE_ENGINE_ENABLE = os.environ.get(
        'OPTIONS_MARKET_STATE_ENGINE_ENABLE',
        'True',
    ).lower() == 'true'
    OPTIONS_GLOBAL_REGIME_ENGINE_ENABLE = os.environ.get(
        'OPTIONS_GLOBAL_REGIME_ENGINE_ENABLE',
        'True',
    ).lower() == 'true'
    OPTIONS_FAIR_VALUE_LIVE_ENABLE = os.environ.get('OPTIONS_FAIR_VALUE_LIVE_ENABLE', 'False').lower() == 'true'
    OPTIONS_FAIR_VALUE_EXCEL_BASKET_ENABLE = os.environ.get(
        'OPTIONS_FAIR_VALUE_EXCEL_BASKET_ENABLE',
        'False',
    ).lower() == 'true'
    MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE = os.environ.get(
        'MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE',
        'False',
    ).lower() == 'true'
    MARKET_SCREEN_W32_RESIDENT_ENABLE = os.environ.get(
        'MARKET_SCREEN_W32_RESIDENT_ENABLE',
        'False',
    ).lower() == 'true'
    MARKET_SCREEN_W32_AUTO_START = os.environ.get(
        'MARKET_SCREEN_W32_AUTO_START',
        'False',
    ).lower() == 'true'
    MARKET_SCREEN_W32_SAVE_IMAGE = os.environ.get(
        'MARKET_SCREEN_W32_SAVE_IMAGE',
        'False',
    ).lower() == 'true'
    MARKET_SCREEN_W32_KEEP_LAST_IMAGE_ONLY = os.environ.get(
        'MARKET_SCREEN_W32_KEEP_LAST_IMAGE_ONLY',
        'True',
    ).lower() == 'true'
    MARKET_SCREEN_W32_MAX_AGE_SECONDS = float(
        os.environ.get('MARKET_SCREEN_W32_MAX_AGE_SECONDS', '15')
    )
    MARKET_SCREEN_W32_CANONICAL_SYMBOLS_EXTRA = [
        symbol.strip()
        for symbol in os.environ.get(
            'MARKET_SCREEN_W32_CANONICAL_SYMBOLS_EXTRA',
            '',
        ).split(',')
        if symbol.strip()
    ]
    OPTIONS_FAIR_VALUE_EXCEL_BASKET_WORKBOOK_HINT = os.environ.get(
        'OPTIONS_FAIR_VALUE_EXCEL_BASKET_WORKBOOK_HINT',
        'Basket_FairValue_WIN',
    )
    OPTIONS_FAIR_VALUE_EXCEL_BASKET_SHEET_HINT = os.environ.get(
        'OPTIONS_FAIR_VALUE_EXCEL_BASKET_SHEET_HINT',
        'DATA',
    )
    OPTIONS_FAIR_VALUE_EXCEL_BASKET_ROW_START = int(
        os.environ.get('OPTIONS_FAIR_VALUE_EXCEL_BASKET_ROW_START', '85')
    )
    OPTIONS_FAIR_VALUE_EXCEL_BASKET_ROW_END = int(
        os.environ.get('OPTIONS_FAIR_VALUE_EXCEL_BASKET_ROW_END', '188')
    )
    OPTIONS_FAIR_VALUE_EXCEL_BASKET_NAME_COLUMN = os.environ.get(
        'OPTIONS_FAIR_VALUE_EXCEL_BASKET_NAME_COLUMN',
        'H',
    )
    OPTIONS_FAIR_VALUE_EXCEL_BASKET_PRICE_COLUMN = os.environ.get(
        'OPTIONS_FAIR_VALUE_EXCEL_BASKET_PRICE_COLUMN',
        'I',
    )
    OPTIONS_FAIR_VALUE_EXCEL_BASKET_DAILY_CHANGE_COLUMN = os.environ.get(
        'OPTIONS_FAIR_VALUE_EXCEL_BASKET_DAILY_CHANGE_COLUMN',
        'L',
    )
    MARKET_SCREEN_W32_WINDOW_TITLE = os.environ.get(
        'MARKET_SCREEN_W32_WINDOW_TITLE',
        'W 32: Basica',
    )
    MARKET_SCREEN_W32_FALLBACK_MONITOR_INDEX = int(
        os.environ.get('MARKET_SCREEN_W32_FALLBACK_MONITOR_INDEX', '2')
    )
    MARKET_SCREEN_W32_FALLBACK_LEFT_RATIO = float(
        os.environ.get('MARKET_SCREEN_W32_FALLBACK_LEFT_RATIO', '0.0')
    )
    MARKET_SCREEN_W32_FALLBACK_TOP_RATIO = float(
        os.environ.get('MARKET_SCREEN_W32_FALLBACK_TOP_RATIO', '0.0')
    )
    MARKET_SCREEN_W32_FALLBACK_WIDTH_RATIO = float(
        os.environ.get('MARKET_SCREEN_W32_FALLBACK_WIDTH_RATIO', '0.18')
    )
    MARKET_SCREEN_W32_FALLBACK_HEIGHT_RATIO = float(
        os.environ.get('MARKET_SCREEN_W32_FALLBACK_HEIGHT_RATIO', '0.98')
    )
    MARKET_SCREEN_W32_MIN_CONFIDENCE = float(
        os.environ.get('MARKET_SCREEN_W32_MIN_CONFIDENCE', '0.55')
    )
    MARKET_SCREEN_W32_OCR_USE_CLS = os.environ.get(
        'MARKET_SCREEN_W32_OCR_USE_CLS',
        'False',
    ).lower() == 'true'
    MARKET_SCREEN_W32_OCR_DET_LIMIT_SIDE_LEN = int(
        os.environ.get('MARKET_SCREEN_W32_OCR_DET_LIMIT_SIDE_LEN', '640')
    )
    MARKET_SCREEN_W32_OCR_REC_BATCH_NUM = int(
        os.environ.get('MARKET_SCREEN_W32_OCR_REC_BATCH_NUM', '6')
    )
    MARKET_SCREEN_W32_OCR_LANGUAGE = os.environ.get(
        'MARKET_SCREEN_W32_OCR_LANGUAGE',
        'en-US',
    )
    MARKET_SCREEN_W32_OCR_SCALE = float(
        os.environ.get('MARKET_SCREEN_W32_OCR_SCALE', '2.0')
    )
    MARKET_SCREEN_W32_POLL_INTERVAL_SECONDS = float(
        os.environ.get('MARKET_SCREEN_W32_POLL_INTERVAL_SECONDS', '0.1')
    )
    MARKET_SCREEN_W32_HISTORY_INTERVAL_SECONDS = float(
        os.environ.get('MARKET_SCREEN_W32_HISTORY_INTERVAL_SECONDS', '5')
    )
    MARKET_SCREEN_W32_HISTORY_DB_ENABLE = os.environ.get(
        'MARKET_SCREEN_W32_HISTORY_DB_ENABLE',
        'True',
    ).lower() == 'true'
    MARKET_SCREEN_W32_HISTORY_DB_PATH = os.environ.get(
        'MARKET_SCREEN_W32_HISTORY_DB_PATH',
        '',
    )
    MARKET_SCREEN_W32_HISTORY_CANDLE_MINUTES = int(
        os.environ.get('MARKET_SCREEN_W32_HISTORY_CANDLE_MINUTES', '5')
    )
    FAIR_VALUE_LEGS_LIVE_TAIL_BYTES = int(
        os.environ.get('FAIR_VALUE_LEGS_LIVE_TAIL_BYTES', str(8 * 1024 * 1024))
    )
    FAIR_VALUE_LEGS_LIVE_HEAD_BYTES = int(
        os.environ.get('FAIR_VALUE_LEGS_LIVE_HEAD_BYTES', '0')
    )
    OPTIONS_INTRADAY_DEPENDENCY_HORIZONS = _parse_int_list(
        os.environ.get('OPTIONS_INTRADAY_DEPENDENCY_HORIZONS', '1,5,15'),
        [1, 5, 15],
    )
    OPTIONS_INTRADAY_DEPENDENCY_ROLLING_WINDOW_MINUTES = int(
        os.environ.get('OPTIONS_INTRADAY_DEPENDENCY_ROLLING_WINDOW_MINUTES', '120')
    )
    OPTIONS_INTRADAY_DEPENDENCY_MIN_POINTS = int(
        os.environ.get('OPTIONS_INTRADAY_DEPENDENCY_MIN_POINTS', '4')
    )
    OPTIONS_INTRADAY_DEPENDENCY_MAX_HISTORY_POINTS = int(
        os.environ.get('OPTIONS_INTRADAY_DEPENDENCY_MAX_HISTORY_POINTS', '360')
    )
    OPTIONS_INTRADAY_CORRELATION_CONTINUOUS_ENABLE = os.environ.get(
        'OPTIONS_INTRADAY_CORRELATION_CONTINUOUS_ENABLE',
        'True',
    ).lower() == 'true'
    OPTIONS_INTRADAY_CORRELATION_CONTINUOUS_LOOKBACK_DAYS = int(
        os.environ.get('OPTIONS_INTRADAY_CORRELATION_CONTINUOUS_LOOKBACK_DAYS', '1')
    )
    OPTIONS_INTRADAY_NEURAL_LOOKBACK_SESSIONS = int(
        os.environ.get('OPTIONS_INTRADAY_NEURAL_LOOKBACK_SESSIONS', '8')
    )
    OPTIONS_INTRADAY_NEURAL_MAX_RUNS = int(
        os.environ.get('OPTIONS_INTRADAY_NEURAL_MAX_RUNS', '1200')
    )
    OPTIONS_INTRADAY_NEURAL_MIN_ROWS = int(
        os.environ.get('OPTIONS_INTRADAY_NEURAL_MIN_ROWS', '80')
    )
    OPTIONS_INTRADAY_NEURAL_HIDDEN_WIDTH = int(
        os.environ.get('OPTIONS_INTRADAY_NEURAL_HIDDEN_WIDTH', '10')
    )
    OPTIONS_INTRADAY_NEURAL_EPOCHS = int(
        os.environ.get('OPTIONS_INTRADAY_NEURAL_EPOCHS', '180')
    )
    OPTIONS_INTRADAY_NEURAL_PATIENCE = int(
        os.environ.get('OPTIONS_INTRADAY_NEURAL_PATIENCE', '24')
    )
    OPTIONS_INTRADAY_NEURAL_BATCH_SIZE = int(
        os.environ.get('OPTIONS_INTRADAY_NEURAL_BATCH_SIZE', '64')
    )
    OPTIONS_INTRADAY_NEURAL_LEARNING_RATE = float(
        os.environ.get('OPTIONS_INTRADAY_NEURAL_LEARNING_RATE', '0.008')
    )
    OPTIONS_INTRADAY_NEURAL_WEIGHT_DECAY = float(
        os.environ.get('OPTIONS_INTRADAY_NEURAL_WEIGHT_DECAY', '0.0005')
    )
    OPTIONS_MODEL_DAILY_INSIGHTS_ENABLE = os.environ.get('OPTIONS_MODEL_DAILY_INSIGHTS_ENABLE', 'True').lower() == 'true'
    OPTIONS_CHAT_MAX_MESSAGES = int(os.environ.get('OPTIONS_CHAT_MAX_MESSAGES', '30'))
    
    # OASIS平台可用动作配置
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]
    
    # Report Agent配置
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))
    
    @classmethod
    def validate(cls):
        """验证必要配置"""
        errors = []
        if cls.AUTH_ENABLED:
            if not cls.AUTH_TOKEN_SECRET:
                errors.append("AQUILES_AUTH_TOKEN_SECRET is required when authentication is enabled")
            if not cls.AUTH_USERS_JSON:
                errors.append("AQUILES_AUTH_USERS_JSON is required when authentication is enabled")
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 未配置")

        if cls.GRAPH_BACKEND == 'zep_cloud':
            if not cls.ZEP_API_KEY:
                errors.append("ZEP_API_KEY 未配置")
        elif cls.GRAPH_BACKEND == 'graphiti_local':
            if not cls.NEO4J_URI:
                errors.append("NEO4J_URI 未配置")
            if not cls.NEO4J_USER:
                errors.append("NEO4J_USER 未配置")
            if not cls.NEO4J_PASSWORD:
                errors.append("NEO4J_PASSWORD 未配置")
        else:
            errors.append(f"GRAPH_BACKEND 配置不支持: {cls.GRAPH_BACKEND}")

        if cls.OPTIONS_ENABLE:
            if not cls.OPLAB_ENABLE and not cls.MACRO_BLOOMBERG_ENABLE:
                errors.append(
                    "OPTIONS_ENABLE requer MACRO_BLOOMBERG_ENABLE=True ou OPLAB_ENABLE=True"
                )
            if not cls.OPLAB_ENABLE and not cls.OPTIONS_BLOOMBERG_UNDERLYINGS:
                errors.append("OPTIONS_BLOOMBERG_UNDERLYINGS is required")
            if cls.OPTIONS_MODEL_ENABLE:
                if cls.OPTIONS_MODEL_DEFAULT_TIER not in {'full', 'structural', 'liquid', 'critical'}:
                    errors.append("OPTIONS_MODEL_DEFAULT_TIER must be full, structural, liquid or critical")
                if cls.OPTIONS_MODEL_SIGN_CONVENTION not in {'neutral', 'dealer_short_optionality', 'heuristic'}:
                    errors.append("OPTIONS_MODEL_SIGN_CONVENTION must be neutral, dealer_short_optionality or heuristic")

        return errors
