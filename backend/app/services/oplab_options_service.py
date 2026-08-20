"""
OpLabOptionsService
===================
Implementa a mesma interface do OptionsBloombergService usando a API REST da OpLab
(https://api.oplab.com.br/v3) como fonte de dados de opcoes.

Endpoints utilizados:
  GET /market/options/{underlying}                        → chain completo com precos
  GET /market/historical/options/{underlying}/{from}/{to} → historico com gregas
  GET /market/quote?tickers=T1,T2,...                     → cotacoes rapidas multi-ticker
  GET /market/options/bs                                  → Black-Scholes (IV implicita)
  GET /market/interest_rates                              → taxa CDI/SELIC
  GET /market/status                                      → status do mercado

Mapeamento Bloomberg → OpLab:
  PX_LAST        → close (chain) / premium (hist)
  BID            → bid
  ASK            → ask
  PX_VOLUME      → volume
  VOLUME         → volume
  OPEN_INT       → oi_total (via B3OIService)
  OPT_OPEN_INTEREST → oi_total (via B3OIService)
  IVOL_MID       → volatility (hist) / BS computation
  IVOL_BID       → volatility (aprox)
  IVOL_ASK       → volatility (aprox)
  IVOL_LAST      → volatility (aprox)
  OPT_UNDL_PX    → spot_price (chain) / spot.price (hist)
  OPT_STRIKE_PX  → strike
  OPT_EXPIRE_DT  → due_date
  OPT_PUT_CALL   → type
  OPT_DELTA      → delta (hist)
  OPT_GAMMA      → gamma (hist)
  OPT_VEGA       → vega (hist)
  OPT_THETA      → theta (hist)
  OPT_RHO        → rho (hist)
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import requests

from ..config import Config
from ..utils.logger import get_logger
from .options_greeks_model import apply_priority_greeks, compute_greeks_from_snapshot

logger = get_logger("aquiles.oplab_options")


# ─── Rate Limiter ────────────────────────────────────────────────────────────

class _RateLimiter:
    """Limita chamadas a N requisicoes por minuto usando janela deslizante."""

    def __init__(self, max_per_minute: int = 88) -> None:
        self._max = max_per_minute
        self._calls: list[float] = []
        self._lock = Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.time()
            # Remove chamadas fora da janela de 60 segundos
            self._calls = [t for t in self._calls if now - t < 60]
            if len(self._calls) >= self._max:
                sleep_time = 60 - (now - self._calls[0]) + 0.1
                if sleep_time > 0:
                    logger.debug(
                        "Rate limit atingido (%d req/min); aguardando %.2fs",
                        self._max,
                        sleep_time,
                    )
                    time.sleep(sleep_time)
                self._calls = []
            self._calls.append(time.time())


# ─── Servico principal ───────────────────────────────────────────────────────

class OpLabOptionsService:
    """
    Provedor de dados de opcoes via API OpLab.

    Implementa a mesma interface publica do OptionsBloombergService:
      - status() -> dict
      - fetch_option_chain(underlying_security) -> dict
      - fetch_option_snapshots(securities, fields) -> dict
      - fetch_option_history(security, start_date, end_date, fields) -> dict

    Tambem expoe os mesmos atributos de classe de campos:
      DISCOVERY_FIELDS, SNAPSHOT_FIELDS, DAILY_HISTORY_FIELDS
    """

    # Campos expostos para compatibilidade com a interface Bloomberg
    DISCOVERY_FIELDS: list[str] = [
        "PX_LAST",
        "BID",
        "ASK",
        "PX_VOLUME",
        "VOLUME",
        "OPEN_INT",
        "OPT_OPEN_INTEREST",
        "IVOL_MID",
        "OPT_UNDL_PX",
        "OPT_STRIKE_PX",
        "OPT_EXPIRE_DT",
        "OPT_PUT_CALL",
    ]

    SNAPSHOT_FIELDS: list[str] = [
        "PX_LAST",
        "BID",
        "ASK",
        "PX_VOLUME",
        "VOLUME",
        "OPEN_INT",
        "OPT_OPEN_INTEREST",
        "IVOL_BID",
        "IVOL_ASK",
        "IVOL_MID",
        "IVOL_LAST",
        "OPT_DELTA",
        "OPT_GAMMA",
        "OPT_VEGA",
        "OPT_THETA",
        "OPT_UNDL_PX",
        "OPT_STRIKE_PX",
        "OPT_EXPIRE_DT",
        "OPT_PUT_CALL",
    ]

    DAILY_HISTORY_FIELDS: list[str] = [
        "OPEN_INT",
        "OPT_OPEN_INTEREST",
        "PX_VOLUME",
        "IVOL_MID",
        "PX_LAST",
        "BID",
        "ASK",
    ]

    AUXILIARY_REFERENCE_FIELDS: list[str] = [
        "PX_LAST",
        "BID",
        "ASK",
        "PX_VOLUME",
        "CHG_NET_1D",
        "CHG_PCT_1D",
    ]

    def __init__(self, config: Any = None) -> None:
        self.config = config or Config
        self._rate_limiter = _RateLimiter(
            max_per_minute=getattr(self.config, "OPLAB_RATE_LIMIT_PER_MINUTE", 88)
        )
        self._session = requests.Session()
        self._session.headers.update({
            "access-token": getattr(self.config, "OPLAB_ACCESS_TOKEN", ""),
            "Content-Type": "application/json",
        })
        self._timeout: int = getattr(self.config, "OPLAB_REQUEST_TIMEOUT", 30)
        self._base_url: str = getattr(
            self.config, "OPLAB_BASE_URL", "https://api.oplab.com.br/v3"
        ).rstrip("/")

        # Cache de taxa CDI — invalida apos 1 hora
        self._cdi_rate: float | None = None
        self._cdi_fetched_at: float = 0.0
        self._CDI_TTL: int = 3600

        # Cache de gregas historicas por (underlying, date) → list[dict]
        self._greeks_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}

        # Cache de chain (precos atuais) por underlying — TTL curto para nao repetir na mesma chamada de universe
        self._chain_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._CHAIN_TTL: int = 90  # segundos

        # Mapeamento de underlying Bloomberg → OpLab
        self._underlying_map: dict[str, str] = getattr(
            self.config,
            "OPLAB_UNDERLYING_MAP",
            {"IBOVE Index": "IBOV", "BOVA11 Index": "BOVA11"},
        )

    # ─── Interface publica ────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """
        Retorna o status do provedor OpLab.

        Retorno
        -------
        dict com chaves:
          enabled     bool
          session_ok  bool
          error       str | None
          provider    str
          market_status str | None
        """
        enabled = getattr(self.config, "OPLAB_ENABLE", False)
        result: dict[str, Any] = {
            "enabled": enabled,
            "session_ok": False,
            "error": None,
            "provider": "oplab",
            "base_url": self._base_url,
            "market_status": None,
        }
        if not enabled:
            result["error"] = "OpLab desabilitado (OPLAB_ENABLE=False)."
            return result

        token = getattr(self.config, "OPLAB_ACCESS_TOKEN", "")
        if not token:
            result["error"] = "OPLAB_ACCESS_TOKEN nao configurado."
            return result

        try:
            resp = self._make_request("GET", "/market/status")
            if resp is not None:
                result["session_ok"] = True
                result["market_status"] = resp.get("market_status")
                result["server_time"] = resp.get("server_time")
        except Exception as exc:
            result["error"] = f"Falha ao verificar status OpLab: {exc}"
        return result

    def fetch_option_chain(self, underlying_security: str) -> dict[str, Any]:
        """
        Busca a chain de opcoes de um ativo subjacente.

        Parametros
        ----------
        underlying_security : str
            Identificador Bloomberg do subjacente (ex.: 'IBOVE Index').

        Retorno
        -------
        dict com:
          underlying_security  str
          chain                list[str]  — tickers no formato B3 (ex.: 'IBOVF178')
          count                int
          status               dict
        """
        status = self.status()
        if not status.get("session_ok") and not status.get("enabled"):
            return {"underlying_security": underlying_security, "chain": [], "count": 0, "status": status}

        underlying = self._get_underlying_symbol(underlying_security)
        if not underlying:
            status["error"] = f"Subjacente nao mapeado para OpLab: '{underlying_security}'"
            return {"underlying_security": underlying_security, "chain": [], "count": 0, "status": status}
        return self._build_stable_chain_result(underlying_security, underlying, status)

        try:
            data = self._make_request("GET", f"/market/options/{underlying}")
        except Exception as exc:
            status["error"] = f"Erro ao buscar chain OpLab para {underlying}: {exc}"
            logger.error("Chain OpLab — erro para %s: %s", underlying, exc)
            return {"underlying_security": underlying_security, "chain": [], "count": 0, "status": status}

        if data is None:
            status["error"] = f"API OpLab retornou resposta vazia para chain de {underlying}."
            return {"underlying_security": underlying_security, "chain": [], "count": 0, "status": status}

        # A resposta pode ser uma lista direta ou um dict com chave de dados
        rows: list[dict[str, Any]] = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            # Tenta chaves comuns
            for key in ("options", "data", "result", "items"):
                if isinstance(data.get(key), list):
                    rows = data[key]
                    break
            if not rows:
                # Assume que o proprio dict e uma entrada unica
                rows = [data] if data else []

        max_dtm = getattr(self.config, "OPLAB_MAX_DTM", 180)
        chain: list[str] = []
        for row in rows:
            symbol = row.get("symbol") or ""
            if not symbol:
                continue
            dtm = row.get("days_to_maturity")
            if dtm is not None:
                try:
                    if int(dtm) > max_dtm:
                        continue
                except (TypeError, ValueError):
                    pass
            chain.append(symbol)

        chain = sorted(set(chain))

        # Mantém também os rows completos indexados por símbolo,
        # para que OptionsContractService possa normalizar sem parsear o ticker.
        chain_rows_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            sym = row.get("symbol") or ""
            if sym in chain:
                chain_rows_map[sym] = row

        status["session_ok"] = True
        return {
            "underlying_security": underlying_security,
            "chain": chain,
            "chain_rows": list(chain_rows_map.values()),  # metadados completos por contrato
            "count": len(chain),
            "status": status,
        }

    def fetch_option_snapshots(
        self,
        securities: list[str],
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Busca snapshots de opcoes para uma lista de tickers.

        Para cada ticker busca:
          1. Precos atuais via GET /market/options/{underlying}
          2. Gregas do cache historico se disponivel
          3. OI do B3OIService (import lazy para evitar circular)

        Parametros
        ----------
        securities : list[str]
            Lista de tickers B3 (ex.: ['IBOVF178', 'IBOVF180']).
        fields : list[str] | None
            Subset de SNAPSHOT_FIELDS desejado. None = todos.

        Retorno
        -------
        dict com:
          rows    list[dict]  — cada item: {security, ok, fields: {BLOOMBERG_FIELD: value}}
          status  dict
        """
        status = self.status()
        if not status.get("enabled"):
            return {"rows": [], "status": status}

        requested_fields = set(fields or self.SNAPSHOT_FIELDS)
        rows: list[dict[str, Any]] = []

        if not securities:
            status["session_ok"] = True
            return {"rows": rows, "status": status}

        # Determina o subjacente a partir do primeiro ticker (heuristica B3)
        # e busca a chain completa usando cache para evitar chamadas repetidas
        # em lotes de universe (o snapshot service chama em chunks de 100).
        underlying_symbol = self._infer_underlying_from_tickers(securities)
        chain_rows_by_symbol: dict[str, dict[str, Any]] = {}

        if underlying_symbol:
            # Tenta cache primeiro (TTL: 90 segundos)
            cached = self._chain_cache.get(underlying_symbol)
            if cached and (time.time() - cached[0]) < self._CHAIN_TTL:
                raw_list = cached[1]
                logger.debug(
                    "Snapshots OpLab — chain %s carregada do cache (%d entradas)",
                    underlying_symbol, len(raw_list),
                )
            else:
                raw_list = []
                try:
                    data = self._make_request("GET", f"/market/options/{underlying_symbol}")
                    if isinstance(data, list):
                        raw_list = data
                    elif isinstance(data, dict):
                        for key in ("options", "data", "result", "items"):
                            if isinstance(data.get(key), list):
                                raw_list = data[key]
                                break
                    # Armazena no cache
                    self._chain_cache[underlying_symbol] = (time.time(), raw_list)
                    logger.debug(
                        "Snapshots OpLab — chain %s atualizada no cache (%d entradas)",
                        underlying_symbol, len(raw_list),
                    )
                except Exception as exc:
                    logger.warning(
                        "Snapshots OpLab — erro ao buscar chain para %s: %s",
                        underlying_symbol,
                        exc,
                    )

            for entry in raw_list:
                sym = entry.get("symbol") or ""
                if sym:
                    chain_rows_by_symbol[sym] = entry

        # Cache de gregas — tenta hoje; se vazio (mercado ainda aberto) usa ontem
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        greeks_by_symbol: dict[str, dict[str, Any]] = {}
        if underlying_symbol:
            greeks_list = self._get_greeks_cache(underlying_symbol, today)
            if not greeks_list:
                # Historico de hoje nao disponivel (sessao ainda aberta) — usa D-1
                yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
                greeks_list = self._get_greeks_cache(underlying_symbol, yesterday)
                if greeks_list:
                    logger.debug(
                        "Snapshots OpLab — usando gregas de %s (hoje sem dados)", yesterday
                    )
            for g in greeks_list:
                sym = g.get("symbol") or ""
                if sym:
                    greeks_by_symbol[sym] = g

        # OI do B3OIService — carrega um mapa unico da data mais recente disponivel
        # para evitar lookup arquivo-a-arquivo quando o universo cresce.
        oi_by_symbol: dict[str, int | None] = {}
        try:
            from .b3_oi_service import B3OIService  # noqa: PLC0415
            b3_oi = B3OIService()
            oi_payload = b3_oi.get_recent_oi_map(
                trade_date=_last_business_day(today),
                lookback_business_days=5,
                ensure=False,
            )
            oi_trade_date = oi_payload.get("trade_date")
            oi_map = oi_payload.get("map") or {}
            if oi_trade_date:
                status["oi_trade_date"] = oi_trade_date
            for sec in securities:
                oi_record = oi_map.get(sec) or oi_map.get(str(sec).upper())
                if oi_record is not None:
                    oi_by_symbol[sec] = oi_record.get("oi_total")
        except Exception as exc:
            logger.debug("Snapshots OpLab — B3OIService nao disponivel: %s", exc)

        # Taxa CDI única por chamada (cache interno de 1 hora)
        cdi_rate = self._get_cdi_rate()

        # Monta rows no formato Bloomberg
        for sec in securities:
            chain_entry = chain_rows_by_symbol.get(sec) or {}
            greeks_entry = greeks_by_symbol.get(sec) or {}
            oi_val = oi_by_symbol.get(sec)

            field_values: dict[str, Any] = {}

            # Preco / bid / ask
            if "PX_LAST" in requested_fields:
                px = _safe_float(chain_entry.get("close")) or _safe_float(greeks_entry.get("premium"))
                field_values["PX_LAST"] = px
            if "BID" in requested_fields:
                field_values["BID"] = _safe_float(chain_entry.get("bid"))
            if "ASK" in requested_fields:
                field_values["ASK"] = _safe_float(chain_entry.get("ask"))
            if "PX_VOLUME" in requested_fields:
                field_values["PX_VOLUME"] = _safe_float(chain_entry.get("volume"))
            if "VOLUME" in requested_fields:
                field_values["VOLUME"] = _safe_float(chain_entry.get("volume"))

            # Open interest — B3OI e a fonte principal; se nao disponivel,
            # tenta usar o campo open_interest/oi retornado pela chain OpLab
            # como fallback (evita GEX/DEX = 0 quando B3OI ainda nao coletado).
            chain_oi = _safe_float(
                chain_entry.get("open_interest")
                or chain_entry.get("oi")
                or chain_entry.get("oi_total")
            )
            resolved_oi = oi_val if oi_val is not None else chain_oi
            if "OPEN_INT" in requested_fields:
                field_values["OPEN_INT"] = resolved_oi
            if "OPT_OPEN_INTEREST" in requested_fields:
                field_values["OPT_OPEN_INTEREST"] = resolved_oi

            # Volatilidade implicita — usa apenas o cache historico (nao faz chamada BS por contrato
            # para evitar explosao de requisicoes no bulk-fetch do universe service).
            # Para calcular IV individual via BS, use compute_single_iv() diretamente.
            iv_val = _safe_float(greeks_entry.get("volatility"))
            for iv_field in ("IVOL_MID", "IVOL_BID", "IVOL_ASK", "IVOL_LAST"):
                if iv_field in requested_fields:
                    field_values[iv_field] = iv_val

            # Gregas
            for bloomberg_field, oplab_field in (
                ("OPT_DELTA", "delta"),
                ("OPT_GAMMA", "gamma"),
                ("OPT_VEGA", "vega"),
                ("OPT_THETA", "theta"),
                ("OPT_RHO", "rho"),
            ):
                if bloomberg_field in requested_fields:
                    field_values[bloomberg_field] = _safe_float(greeks_entry.get(oplab_field))

            # Campos de referencia do contrato
            if "OPT_UNDL_PX" in requested_fields:
                spot = _safe_float(chain_entry.get("spot_price"))
                if spot is None:
                    spot_obj = greeks_entry.get("spot") or {}
                    if isinstance(spot_obj, dict):
                        spot = _safe_float(spot_obj.get("price"))
                field_values["OPT_UNDL_PX"] = spot
            if "OPT_STRIKE_PX" in requested_fields:
                field_values["OPT_STRIKE_PX"] = _safe_float(
                    chain_entry.get("strike") or greeks_entry.get("strike")
                )
            if "OPT_EXPIRE_DT" in requested_fields:
                field_values["OPT_EXPIRE_DT"] = _format_date(
                    chain_entry.get("due_date") or greeks_entry.get("due_date")
                )
            if "OPT_PUT_CALL" in requested_fields:
                raw_type = chain_entry.get("type") or greeks_entry.get("type") or ""
                field_values["OPT_PUT_CALL"] = _normalize_option_type(raw_type)

            # ── Modelo proprietário de Greeks ──────────────────────────────
            _spot    = field_values.get("OPT_UNDL_PX")
            _strike  = field_values.get("OPT_STRIKE_PX")
            _t_du    = chain_entry.get("days_to_maturity")
            # Fallback: calcula DU a partir da data de vencimento quando
            # o campo days_to_maturity nao esta disponivel na chain OpLab
            if _t_du is None:
                _due = chain_entry.get("due_date") or greeks_entry.get("due_date")
                _t_du = _business_days_to_expiry(_due)
            _bid     = field_values.get("BID")
            _ask     = field_values.get("ASK")
            _px_last = field_values.get("PX_LAST")
            _pc      = field_values.get("OPT_PUT_CALL") or ""
            _opt_code = "P" if str(_pc).upper().startswith("P") else "C"

            # Preço mid preferido; fallback para PX_LAST
            # bid=0 ou ask=0 indicam ausência de cotação (mercado fechado) — ignora
            _price_mid: float | None = None
            if _bid is not None and _ask is not None and _bid > 0 and _ask > 0 and _ask >= _bid:
                _price_mid = (_bid + _ask) / 2.0
            if _price_mid is None or _price_mid <= 0:
                _price_mid = _px_last

            model_result = compute_greeks_from_snapshot(
                S=_spot,
                K=_strike,
                T_du=_t_du,
                price_mid=_price_mid,
                r_cont=cdi_rate,
                opt=_opt_code,
            )

            # Campos MODEL_*
            if model_result:
                field_values["MODEL_IV"]           = model_result["iv"]
                field_values["MODEL_DELTA"]        = model_result["delta"]
                field_values["MODEL_GAMMA_POINT"]  = model_result["gamma_point"]
                field_values["MODEL_GAMMA_1PCT"]   = model_result["gamma_1pct"]
                field_values["MODEL_VEGA_1PCTVOL"] = model_result["vega_1pctvol"]
                field_values["MODEL_THETA_BD252"]  = model_result["theta_bd252"]
                field_values["MODEL_VANNA"]        = model_result["vanna"]
                field_values["MODEL_CHARM_BD252"]  = model_result["charm_bd252"]
            else:
                for _k in (
                    "MODEL_IV", "MODEL_DELTA", "MODEL_GAMMA_POINT", "MODEL_GAMMA_1PCT",
                    "MODEL_VEGA_1PCTVOL", "MODEL_THETA_BD252", "MODEL_VANNA", "MODEL_CHARM_BD252",
                ):
                    field_values[_k] = None

            # Campos EFF_* — prioridade: proprietário > OpLab > insufficient_data
            _eff = apply_priority_greeks(
                model_result=model_result,
                oplab_delta=field_values.get("OPT_DELTA"),
                oplab_gamma=field_values.get("OPT_GAMMA"),
                oplab_iv=field_values.get("IVOL_MID"),
                oplab_vega=field_values.get("OPT_VEGA"),
                oplab_theta=field_values.get("OPT_THETA"),
            )
            field_values.update(_eff)

            ok = bool(chain_entry or greeks_entry)
            rows.append({
                "security": sec,
                "ok": ok,
                "fields": field_values,
            })

        status["session_ok"] = True
        status["captured_count"] = sum(1 for r in rows if r.get("ok"))
        status["failed_count"] = sum(1 for r in rows if not r.get("ok"))
        return {"rows": rows, "status": status}

    def fetch_option_history(
        self,
        security: str,
        start_date: str,
        end_date: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Busca historico diario de um contrato de opcao.

        Parametros
        ----------
        security : str
            Ticker B3 do contrato (ex.: 'IBOVF178').
        start_date : str
            Formato 'YYYY-MM-DD'.
        end_date : str
            Formato 'YYYY-MM-DD'.
        fields : list[str] | None
            Subset de DAILY_HISTORY_FIELDS. None = todos.

        Retorno
        -------
        dict com:
          rows    list[dict]  — cada item: {security, trade_date, fields: {BLOOMBERG_FIELD: value}}
          status  dict
        """
        status = self.status()
        if not status.get("enabled"):
            return {"rows": [], "status": status}

        requested_fields = set(fields or self.DAILY_HISTORY_FIELDS)
        rows: list[dict[str, Any]] = []

        # Determina subjacente a partir do ticker (heuristica B3)
        underlying_symbol = self._infer_underlying_from_tickers([security])
        if not underlying_symbol:
            status["error"] = f"Nao foi possivel inferir o subjacente OpLab para '{security}'."
            return {"rows": rows, "status": status}

        try:
            data = self._make_request(
                "GET",
                f"/market/historical/options/{underlying_symbol}/{start_date}/{end_date}",
            )
        except Exception as exc:
            status["error"] = f"Erro ao buscar historico OpLab para {security}: {exc}"
            logger.error("Historico OpLab — erro para %s: %s", security, exc)
            return {"rows": rows, "status": status}

        if data is None:
            status["error"] = "API OpLab retornou resposta vazia para historico."
            return {"rows": rows, "status": status}

        raw_list: list[dict[str, Any]] = []
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            for key in ("data", "result", "items", "options"):
                if isinstance(data.get(key), list):
                    raw_list = data[key]
                    break

        # Filtra pelo ticker pedido
        relevant = [r for r in raw_list if (r.get("symbol") or "") == security]

        # Carrega OI do B3OIService (import lazy)
        try:
            from .b3_oi_service import B3OIService  # noqa: PLC0415
            b3_oi = B3OIService()
        except Exception:
            b3_oi = None

        for entry in relevant:
            # Data de negociacao: campo "time" (ISO) ou "date"
            raw_time = entry.get("time") or entry.get("date") or ""
            trade_date = str(raw_time)[:10] if raw_time else None
            if not trade_date:
                continue

            field_values: dict[str, Any] = {}

            # Preco / volume
            if "PX_LAST" in requested_fields:
                field_values["PX_LAST"] = _safe_float(entry.get("premium"))
            if "BID" in requested_fields:
                field_values["BID"] = _safe_float(entry.get("bid"))
            if "ASK" in requested_fields:
                field_values["ASK"] = _safe_float(entry.get("ask"))
            if "PX_VOLUME" in requested_fields:
                field_values["PX_VOLUME"] = _safe_float(entry.get("volume"))
            if "VOLUME" in requested_fields:
                field_values["VOLUME"] = _safe_float(entry.get("volume"))

            # Open interest via B3OI
            oi_val: int | None = None
            if b3_oi is not None and (
                "OPEN_INT" in requested_fields or "OPT_OPEN_INTEREST" in requested_fields
            ):
                try:
                    oi_record = b3_oi.get_oi(security, trade_date=trade_date)
                    if oi_record is not None:
                        oi_val = oi_record.get("oi_total")
                except Exception:
                    pass
            if "OPEN_INT" in requested_fields:
                field_values["OPEN_INT"] = oi_val
            if "OPT_OPEN_INTEREST" in requested_fields:
                field_values["OPT_OPEN_INTEREST"] = oi_val

            # Volatilidade implicita
            iv_val = _safe_float(entry.get("volatility"))
            if "IVOL_MID" in requested_fields:
                field_values["IVOL_MID"] = iv_val

            # Gregas
            for bloomberg_field, oplab_field in (
                ("OPT_DELTA", "delta"),
                ("OPT_GAMMA", "gamma"),
                ("OPT_VEGA", "vega"),
                ("OPT_THETA", "theta"),
                ("OPT_RHO", "rho"),
            ):
                if bloomberg_field in requested_fields:
                    field_values[bloomberg_field] = _safe_float(entry.get(oplab_field))

            rows.append({
                "security": security,
                "trade_date": trade_date,
                "fields": field_values,
            })

        # Ordena por data
        rows.sort(key=lambda r: r.get("trade_date") or "")

        status["session_ok"] = True
        return {"rows": rows, "status": status}

    # ─── Metodos internos ─────────────────────────────────────────────────

    def _build_stable_chain_result(
        self,
        underlying_security: str,
        underlying_symbol: str,
        status: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            rows, chain_polling = self._fetch_chain_rows_stable(underlying_symbol, use_cache=True)
        except Exception as exc:
            status["error"] = f"Erro ao buscar chain OpLab para {underlying_symbol}: {exc}"
            logger.error("Chain OpLab â€” erro para %s: %s", underlying_symbol, exc)
            return {"underlying_security": underlying_security, "chain": [], "count": 0, "status": status}

        status["chain_polling"] = chain_polling
        if not rows:
            status["error"] = f"API OpLab retornou resposta vazia para chain de {underlying_symbol}."
            return {"underlying_security": underlying_security, "chain": [], "count": 0, "status": status}

        max_dtm = getattr(self.config, "OPLAB_MAX_DTM", 90)
        chain: list[str] = []
        chain_rows_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "").strip()
            if not symbol:
                continue
            dtm = row.get("days_to_maturity")
            if dtm is not None:
                try:
                    if int(dtm) > max_dtm:
                        continue
                except (TypeError, ValueError):
                    pass
            chain.append(symbol)
            chain_rows_map[symbol] = row

        status["session_ok"] = True
        return {
            "underlying_security": underlying_security,
            "chain": sorted(set(chain)),
            "chain_rows": list(chain_rows_map.values()),
            "count": len(chain_rows_map),
            "status": status,
        }

    def _extract_chain_rows(self, data: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        if isinstance(data, list):
            rows = [row for row in data if isinstance(row, dict)]
        elif isinstance(data, dict):
            for key in ("options", "data", "result", "items"):
                if isinstance(data.get(key), list):
                    rows = [row for row in data[key] if isinstance(row, dict)]
                    break
            if not rows and data:
                rows = [data]

        chain_rows_map: dict[str, dict[str, Any]] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "").strip().upper()
            if symbol:
                chain_rows_map[symbol] = row
        return list(chain_rows_map.values())

    def _fetch_chain_rows_stable(
        self,
        underlying_symbol: str,
        *,
        use_cache: bool = True,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        cached = self._chain_cache.get(underlying_symbol)
        if use_cache and cached and (time.time() - cached[0]) < self._CHAIN_TTL:
            cached_rows = cached[1]
            return cached_rows, {
                "source": "cache",
                "selected_count": len(cached_rows),
                "selected_unique": len(cached_rows),
                "stable": True,
                "completed_reason": "cache_hit",
                "max_polls": 1,
                "stable_rounds_required": 0,
                "poll_interval_seconds": 0.0,
                "attempts": [],
            }

        max_polls = max(int(getattr(self.config, "OPLAB_CHAIN_STABILITY_MAX_POLLS", 6)), 1)
        stable_rounds_required = max(int(getattr(self.config, "OPLAB_CHAIN_STABLE_ROUNDS", 2)), 0)
        poll_interval_seconds = max(float(getattr(self.config, "OPLAB_CHAIN_STABILITY_POLL_SECONDS", 0.5)), 0.0)
        last_symbols: set[str] | None = None
        stable_rounds = 0
        best_rows: list[dict[str, Any]] = []
        best_symbols: set[str] = set()
        attempts: list[dict[str, Any]] = []
        completed_reason = "max_polls_reached"

        for attempt in range(1, max_polls + 1):
            data = self._make_request("GET", f"/market/options/{underlying_symbol}")
            rows = self._extract_chain_rows(data)
            current_symbols = {
                str(row.get("symbol") or "").strip().upper()
                for row in rows
                if row.get("symbol")
            }
            diff_vs_prev = None if last_symbols is None else len(current_symbols.symmetric_difference(last_symbols))
            attempts.append({
                "attempt": attempt,
                "count": len(rows),
                "unique": len(current_symbols),
                "diff_vs_prev": diff_vs_prev,
            })

            if len(current_symbols) >= len(best_symbols):
                best_rows = rows
                best_symbols = current_symbols

            if last_symbols is not None and current_symbols == last_symbols:
                stable_rounds += 1
            else:
                stable_rounds = 0
            last_symbols = current_symbols

            if stable_rounds_required == 0 or stable_rounds >= stable_rounds_required:
                completed_reason = "stable"
                best_rows = rows
                best_symbols = current_symbols
                break

            if attempt < max_polls and poll_interval_seconds > 0:
                time.sleep(poll_interval_seconds)

        selected_rows = best_rows
        self._chain_cache[underlying_symbol] = (time.time(), selected_rows)
        logger.debug(
            "Chain OpLab %s estabilizada=%s entradas=%d tentativas=%d",
            underlying_symbol,
            completed_reason == "stable",
            len(selected_rows),
            len(attempts),
        )
        return selected_rows, {
            "source": "live",
            "selected_count": len(selected_rows),
            "selected_unique": len(best_symbols),
            "stable": completed_reason == "stable",
            "completed_reason": completed_reason,
            "max_polls": max_polls,
            "stable_rounds_required": stable_rounds_required,
            "poll_interval_seconds": poll_interval_seconds,
            "attempts": attempts,
        }

    def _make_request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> Any:
        """
        Faz uma requisicao HTTP para a API OpLab com retry e rate limiting.

        Parametros
        ----------
        method : str
            Metodo HTTP ('GET', 'POST', ...).
        path : str
            Caminho relativo ao base URL (ex.: '/market/status').
        params : dict | None
            Query parameters opcionais.
        retries : int
            Numero de tentativas em caso de erro transitorio.

        Retorno
        -------
        dict | list | None
            Corpo JSON parseado, ou None em caso de falha.
        """
        self._rate_limiter.acquire()
        url = f"{self._base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    timeout=self._timeout,
                )
                if resp.status_code == 429:
                    # Rate limit atingido — aguarda e tenta novamente
                    retry_after = int(resp.headers.get("Retry-After", 60))
                    logger.warning(
                        "OpLab rate limit (429) para %s — aguardando %ds (tentativa %d/%d)",
                        path,
                        retry_after,
                        attempt,
                        retries,
                    )
                    time.sleep(retry_after)
                    continue
                if resp.status_code >= 400:
                    logger.warning(
                        "OpLab HTTP %d para %s (tentativa %d/%d): %s",
                        resp.status_code,
                        path,
                        attempt,
                        retries,
                        resp.text[:200],
                    )
                    if resp.status_code < 500:
                        # Erro de cliente — nao retenta
                        return None
                    # Erro de servidor — retenta
                    last_exc = RuntimeError(f"HTTP {resp.status_code}")
                    time.sleep(2 ** attempt)
                    continue
                return resp.json()
            except requests.exceptions.Timeout as exc:
                logger.warning(
                    "OpLab timeout para %s (tentativa %d/%d)", path, attempt, retries
                )
                last_exc = exc
                time.sleep(2 ** attempt)
            except requests.exceptions.ConnectionError as exc:
                logger.warning(
                    "OpLab conexao recusada para %s (tentativa %d/%d)", path, attempt, retries
                )
                last_exc = exc
                time.sleep(2 ** attempt)
            except Exception as exc:
                logger.error("OpLab erro inesperado para %s: %s", path, exc, exc_info=True)
                last_exc = exc
                break

        logger.error("OpLab — falha apos %d tentativas para %s: %s", retries, path, last_exc)
        return None

    def fetch_live_spot(self, underlying_symbol: str = "IBOV") -> float | None:
        """
        Retorna o preco spot atual do subjacente via OpLab.

        Tenta primeiro o endpoint leve /market/quote?tickers={symbol}.
        Se nao disponivel, busca o primeiro item da chain e extrai spot_price.

        Parametros
        ----------
        underlying_symbol : str
            Simbolo OpLab do subjacente (ex.: 'IBOV', 'BOVA11').

        Retorno
        -------
        float | None — preco spot, ou None em caso de falha.
        """
        # Tentativa 1: endpoint leve de cotacoes
        try:
            data = self._make_request(
                "GET", "/market/quote", params={"tickers": underlying_symbol}, retries=2
            )
            if data is not None:
                # Pode retornar lista ou dict
                rows: list = data if isinstance(data, list) else (
                    data.get("data") or data.get("items") or [data]
                )
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    # Campos candidatos: close, last, price, PX_LAST
                    for field in ("close", "last", "price", "px_last", "PX_LAST"):
                        v = _safe_float(row.get(field))
                        if v and v > 0:
                            logger.debug("OpLab quote spot %s = %.2f (campo=%s)", underlying_symbol, v, field)
                            return v
        except Exception:
            logger.debug("OpLab /market/quote falhou para %s — tentando chain", underlying_symbol, exc_info=True)

        # Tentativa 2: chain de opcoes (extrai spot_price do primeiro contrato)
        try:
            data = self._make_request(
                "GET", f"/market/options/{underlying_symbol}", retries=2
            )
            if data is not None:
                rows = data if isinstance(data, list) else (
                    data.get("options") or data.get("data") or [data]
                )
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    v = _safe_float(row.get("spot_price"))
                    if v and v > 0:
                        logger.debug("OpLab chain spot %s = %.2f", underlying_symbol, v)
                        return v
        except Exception:
            logger.warning("OpLab fetch_live_spot falhou para %s", underlying_symbol, exc_info=True)

        return None

    def _get_underlying_symbol(self, bloomberg_underlying: str) -> str | None:
        """
        Mapeia um identificador Bloomberg de subjacente para o simbolo OpLab.

        Exemplos:
          'IBOVE Index' → 'IBOV'
          'BOVA11 Index' → 'BOVA11'

        Retorna None se nao houver mapeamento configurado.
        """
        return self._underlying_map.get(bloomberg_underlying)

    def _infer_underlying_from_tickers(self, tickers: list[str]) -> str | None:
        """
        Infere o subjacente OpLab a partir de uma lista de tickers B3.

        Estrategia:
          1. Procura correspondencia direta nos valores do _underlying_map.
          2. Usa heuristica: prefixo do ticker (ex.: 'IBOV' de 'IBOVF178').
        """
        if not tickers:
            return None

        # Verifica correspondencia direta (ex.: 'IBOV' como ticker do proprio subjacente)
        for ticker in tickers:
            t = ticker.strip().upper()
            if t in self._underlying_map.values():
                return t

        # Heuristica: prefixo numerico
        sample = tickers[0].strip().upper()
        # Remove sufixo numerico e letras de vencimento para obter o root
        for _bloomberg_key, oplab_val in self._underlying_map.items():
            if sample.startswith(oplab_val):
                return oplab_val

        # Fallback: tenta o primeiro mapeamento configurado
        if self._underlying_map:
            return next(iter(self._underlying_map.values()))
        return None

    def _get_cdi_rate(self) -> float:
        """
        Retorna a taxa CDI/SELIC atual da API OpLab, com cache de 1 hora.

        Retorno
        -------
        float
            Taxa anual como decimal (ex.: 0.144 para 14.4%).
        """
        now = time.time()
        if self._cdi_rate is not None and (now - self._cdi_fetched_at) < self._CDI_TTL:
            return self._cdi_rate

        fallback = getattr(self.config, "OPTIONS_MODEL_FALLBACK_RATE", 0.135)
        try:
            data = self._make_request("GET", "/market/interest_rates")
            if isinstance(data, dict):
                rates_list = data.get("value") or []
                for rate_entry in rates_list:
                    uid = (rate_entry.get("uid") or "").upper()
                    if uid in ("CETIP", "CDI", "SELIC"):
                        val = rate_entry.get("value")
                        if val is not None:
                            pct = float(val)
                            # OpLab entrega em percentual (ex.: 14.4 = 14.4%)
                            self._cdi_rate = pct / 100.0
                            self._cdi_fetched_at = now
                            return self._cdi_rate
        except Exception as exc:
            logger.warning("OpLab — erro ao buscar taxa CDI: %s", exc)

        logger.debug("OpLab — usando taxa CDI de fallback: %.4f", fallback)
        self._cdi_rate = float(fallback)
        self._cdi_fetched_at = now
        return self._cdi_rate

    def _get_greeks_cache(
        self, underlying_symbol: str, date: str
    ) -> list[dict[str, Any]]:
        """
        Retorna gregas historicas para um subjacente e data, com cache de sessao.

        Faz GET /market/historical/options/{underlying}/{date}/{date} na primeira
        chamada e armazena o resultado em memoria.

        Parametros
        ----------
        underlying_symbol : str
            Simbolo OpLab do subjacente (ex.: 'IBOV').
        date : str
            Data no formato 'YYYY-MM-DD'.

        Retorno
        -------
        list[dict]
            Lista de entradas de gregas para todos os contratos nessa data.
        """
        cache_key = (underlying_symbol, date)
        if cache_key in self._greeks_cache:
            return self._greeks_cache[cache_key]

        result: list[dict[str, Any]] = []
        try:
            data = self._make_request(
                "GET",
                f"/market/historical/options/{underlying_symbol}/{date}/{date}",
            )
            if isinstance(data, list):
                result = data
            elif isinstance(data, dict):
                for key in ("data", "result", "items", "options"):
                    if isinstance(data.get(key), list):
                        result = data[key]
                        break
        except Exception as exc:
            logger.debug(
                "OpLab — erro ao buscar cache de gregas para %s em %s: %s",
                underlying_symbol,
                date,
                exc,
            )

        self._greeks_cache[cache_key] = result
        return result

    def _compute_bs_greeks(
        self,
        symbol: str,
        spot: float | None,
        strike: float | None,
        option_type: str,
        premium: float | None,
        dtm: int | None,
        due_date: str | None,
    ) -> dict[str, Any]:
        """
        Calcula gregas via Black-Scholes usando o endpoint da OpLab.

        Parametros
        ----------
        symbol : str
            Ticker B3 do contrato.
        spot : float | None
            Preco spot do subjacente.
        strike : float | None
            Strike do contrato.
        option_type : str
            'CALL' ou 'PUT'.
        premium : float | None
            Premio (preco) do contrato.
        dtm : int | None
            Dias ate o vencimento.
        due_date : str | None
            Data de vencimento 'YYYY-MM-DD'.

        Retorno
        -------
        dict com delta, gamma, vega, theta, rho, volatility ou vazio em caso de erro.
        """
        if None in (spot, strike, premium, dtm) or spot == 0 or strike == 0 or premium == 0:
            return {}

        irate = self._get_cdi_rate() * 100  # BS endpoint espera percentual
        try:
            params = {
                "symbol": symbol,
                "irate": round(irate, 4),
                "type": option_type.upper(),
                "spotprice": spot,
                "strike": strike,
                "premium": premium,
                "dtm": dtm,
            }
            if due_date:
                params["duedate"] = due_date
            data = self._make_request("GET", "/market/options/bs", params=params)
            if isinstance(data, dict):
                return {
                    "delta": _safe_float(data.get("delta")),
                    "gamma": _safe_float(data.get("gamma")),
                    "vega": _safe_float(data.get("vega")),
                    "theta": _safe_float(data.get("theta")),
                    "rho": _safe_float(data.get("rho")),
                    "volatility": _safe_float(data.get("volatility")),
                }
        except Exception as exc:
            logger.debug("OpLab BS para %s — erro: %s", symbol, exc)
        return {}

    # ─── Stubs de compatibilidade Bloomberg ───────────────────────────────

    def fetch_option_ticks(
        self,
        security: str,
        start_dt: Any,
        end_dt: Any,
        event_types: Any = None,
        include_condition_codes: bool = True,
    ) -> dict[str, Any]:
        """
        Stub de compatibilidade com OptionsBloombergService.

        A OpLab nao fornece tick-by-tick por contrato via REST.
        Retorna lista vazia mantendo a interface intacta para o modulo de snapshots.
        """
        logger.debug(
            "fetch_option_ticks chamado para %s — OpLab nao suporta tick data; retornando vazio.",
            security,
        )
        return {
            "rows": [],
            "status": {
                "enabled": True,
                "session_ok": True,
                "provider": "oplab",
                "error": "OpLab nao fornece tick data por contrato.",
                "captured_count": 0,
            },
        }

    def fetch_intraday_bars(
        self,
        security: str,
        start_dt: Any,
        end_dt: Any,
        interval_minutes: int = 5,
        event_type: str = "TRADE",
    ) -> dict[str, Any]:
        """
        Stub de compatibilidade com OptionsBloombergService.

        A OpLab nao fornece barras intraday por contrato de opcao via REST.
        """
        logger.debug(
            "fetch_intraday_bars chamado para %s — OpLab nao suporta intraday bars; retornando vazio.",
            security,
        )
        return {
            "rows": [],
            "status": {
                "enabled": True,
                "session_ok": True,
                "provider": "oplab",
                "error": "OpLab nao fornece barras intraday por contrato.",
                "captured_count": 0,
            },
        }

    def _try_compute_iv(
        self,
        security: str,
        chain_entry: dict[str, Any],
        greeks_entry: dict[str, Any],
    ) -> float | None:
        """
        Tenta calcular IV implicita via endpoint BS quando nao disponivel no cache.

        Retorna None em caso de dados insuficientes ou erro.
        """
        spot = _safe_float(chain_entry.get("spot_price"))
        if spot is None:
            spot_obj = greeks_entry.get("spot") or {}
            if isinstance(spot_obj, dict):
                spot = _safe_float(spot_obj.get("price"))
        strike = _safe_float(
            chain_entry.get("strike") or greeks_entry.get("strike")
        )
        premium = _safe_float(
            chain_entry.get("close") or greeks_entry.get("premium")
        )
        dtm = chain_entry.get("days_to_maturity") or greeks_entry.get("days_to_maturity")
        due_date = chain_entry.get("due_date") or greeks_entry.get("due_date")
        raw_type = chain_entry.get("type") or greeks_entry.get("type") or "CALL"
        option_type = _normalize_option_type(raw_type) or "CALL"

        try:
            dtm_int = int(dtm) if dtm is not None else None
        except (TypeError, ValueError):
            dtm_int = None

        if None in (spot, strike, premium, dtm_int):
            return None

        bs_result = self._compute_bs_greeks(
            security, spot, strike, option_type, premium, dtm_int, _format_date(due_date)
        )
        return bs_result.get("volatility")


# ─── Funcoes auxiliares ───────────────────────────────────────────────────────

def _business_days_to_expiry(due_date_str: str | None) -> int | None:
    """
    Conta dias úteis (seg–sex) entre hoje e a data de vencimento.

    Não considera feriados brasileiros, mas é suficiente para o modelo de IV
    (erro de ±1 DU em feriados tem impacto desprezível no BSM).

    Retorna 0 se a data já passou, None se due_date_str inválido.
    """
    if not due_date_str:
        return None
    try:
        expiry = datetime.fromisoformat(str(due_date_str)[:10]).date()
        today = datetime.now(timezone.utc).date()
        if expiry <= today:
            return 0
        count = 0
        d = today
        while d < expiry:
            d += timedelta(days=1)
            if d.weekday() < 5:   # seg=0 … sex=4
                count += 1
        return count
    except Exception:
        return None


def _last_business_day(ref_date: str | None = None) -> str:
    """
    Retorna a data do ultimo dia util (D-1 util) a partir de ref_date.
    Pula fins de semana. Nao considera feriados.

    Parametros
    ----------
    ref_date : str | None
        Data de referencia no formato 'YYYY-MM-DD'. Padrao: hoje (UTC).

    Retorno
    -------
    str
        Data no formato 'YYYY-MM-DD'.
    """
    if ref_date:
        d = datetime.fromisoformat(ref_date).date()
    else:
        d = datetime.now(timezone.utc).date()

    d -= timedelta(days=1)
    # Pula fins de semana (weekday: 5=sabado, 6=domingo)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


def _safe_float(value: Any) -> float | None:
    """Converte um valor para float de forma segura; retorna None em caso de falha."""
    if value in (None, "", "N/A", "null"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_option_type(raw: str) -> str | None:
    """Normaliza o tipo de opcao para 'CALL' ou 'PUT'."""
    if not raw:
        return None
    upper = str(raw).strip().upper()
    if upper in ("CALL", "C"):
        return "CALL"
    if upper in ("PUT", "P"):
        return "PUT"
    return upper or None


def _format_date(raw: Any) -> str | None:
    """
    Formata uma data para 'YYYY-MM-DD'.

    Aceita strings ISO (com ou sem hora) e objetos datetime.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.strftime("%Y-%m-%d")
    s = str(raw).strip()
    if not s:
        return None
    # ISO com hora: '2025-06-20T00:00:00'
    return s[:10]
