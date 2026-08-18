from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from typing import Any

from ..config import Config
from ..utils.logger import get_logger
from .options_store import OptionsStore

logger = get_logger("mirofish.options_contracts")

OPTION_TICKER_PATTERN = re.compile(
    r"^(?P<root>.+?)\s+(?P<expiry>\d{2}/\d{2}/\d{2})\s+(?P<put_call>[CP])(?P<strike>\d+(?:\.\d+)?)\s+(?P<suffix>.+)$"
)


class OptionsContractService:
    def __init__(
        self,
        store: OptionsStore | None = None,
        bloomberg: Any | None = None,
    ):
        self.store = store or OptionsStore()
        if bloomberg is None:
            from .options_data_provider import get_options_data_provider  # noqa: PLC0415
            bloomberg = get_options_data_provider()
        self.bloomberg = bloomberg

    def discover_underlying_contracts(self, underlying_security: str) -> dict[str, Any]:
        chain_result = self.bloomberg.fetch_option_chain(underlying_security)
        chain = chain_result.get("chain", []) or []
        discovered_at = datetime.utcnow().isoformat() + "Z"

        # chain_rows contem metadados completos quando o provider e OpLab (ticker B3 nativo).
        chain_rows: list[dict[str, Any]] = chain_result.get("chain_rows") or []
        chain_rows_by_symbol: dict[str, dict[str, Any]] = {
            (r.get("symbol") or ""): r for r in chain_rows if r.get("symbol")
        }

        normalized_contracts: list[dict[str, Any]] = []
        invalid_contracts: list[dict[str, Any]] = []
        for security in chain:
            chain_row = chain_rows_by_symbol.get(security)
            contract = self.normalize_contract(
                security, underlying_security,
                discovered_at=discovered_at,
                chain_row=chain_row,
            )
            valid, errors = self.validate_contract(contract)
            if not valid:
                invalid_contracts.append({
                    "security": security,
                    "errors": errors,
                })
                continue
            normalized_contracts.append(contract)

        save_result = self.store.upsert_contracts(normalized_contracts)
        return {
            "underlying_security": underlying_security,
            "chain_count": len(chain),
            "valid_contract_count": len(normalized_contracts),
            "invalid_contract_count": len(invalid_contracts),
            "invalid_contracts": invalid_contracts[:50],
            "contracts": normalized_contracts,
            "save_result": save_result,
            "status": chain_result.get("status", {}),
        }

    def normalize_contract(
        self,
        bloomberg_ticker: str,
        underlying_security: str,
        discovered_at: str | None = None,
        chain_row: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Normaliza um contrato de opcao para o formato interno.

        Parametros
        ----------
        bloomberg_ticker : str
            Ticker Bloomberg (ex: 'IBOV 05/15/26 C180000 Index')
            ou B3 nativo (ex: 'IBOVF180') quando provider = OpLab.
        underlying_security : str
            Identificador Bloomberg do subjacente (ex: 'IBOVE Index').
        discovered_at : str | None
            ISO timestamp de descoberta.
        chain_row : dict | None
            Linha completa da chain OpLab (contem strike, due_date, type, etc.).
            Quando fornecido, dispensa o parse do ticker via regex — util para
            tickers B3 nativos que nao seguem o padrao Bloomberg.
        """
        discovered_at = discovered_at or (datetime.utcnow().isoformat() + "Z")
        text = str(bloomberg_ticker or "").strip()

        # ── Caminho 1: metadados fornecidos via chain_row (provider OpLab) ──────
        if chain_row:
            try:
                expiry_raw = chain_row.get("due_date") or ""
                expiry_date = date.fromisoformat(str(expiry_raw)[:10])

                raw_strike = chain_row.get("strike")
                strike = float(raw_strike) if raw_strike is not None else None

                raw_type = str(chain_row.get("type") or chain_row.get("category") or "").upper()
                put_call_flag = "C" if raw_type == "CALL" else ("P" if raw_type == "PUT" else None)
                put_call = "Call" if put_call_flag == "C" else ("Put" if put_call_flag == "P" else None)

                # days_to_maturity ja vem da API (dias uteis B3)
                dtm_api = chain_row.get("days_to_maturity")
                business_days = int(dtm_api) if dtm_api is not None else self._business_days_between(date.today(), expiry_date)
                calendar_days = (expiry_date - date.today()).days
                status = "expired" if expiry_date < date.today() else "active"

                if strike is None or put_call_flag is None:
                    raise ValueError(f"strike ou put_call invalido: strike={raw_strike}, type={raw_type}")

                option_id = hashlib.sha1(
                    f"{underlying_security}|{expiry_date.isoformat()}|{put_call_flag}|{strike}|{text}".encode("utf-8")
                ).hexdigest()

                # root_symbol = prefixo alfabetico do ticker B3 (ex: 'IBOV' de 'IBOVF180')
                root_match = re.match(r"^([A-Z]+)", text)
                root_symbol = root_match.group(1) if root_match else text[:4]

                return {
                    "option_id": option_id,
                    "bloomberg_ticker": text,
                    "root_symbol": root_symbol,
                    "underlying_security": underlying_security,
                    "underlying_trade_symbol": Config.OPTIONS_UNDERLYING_TRADE_MAP.get(underlying_security),
                    "put_call": put_call,
                    "put_call_flag": put_call_flag,
                    "strike": strike,
                    "expiry_date": expiry_date.isoformat(),
                    "days_to_expiry_calendar": calendar_days,
                    "days_to_expiry_business": business_days,
                    "status": status,
                    "mvp_eligible": business_days <= Config.OPTIONS_MAX_BUSINESS_DAYS and status == "active",
                    "discovered_at": discovered_at,
                    "last_seen_at": discovered_at,
                    "expired_at": expiry_date.isoformat() if status == "expired" else None,
                    "contract_multiplier": chain_row.get("contract_size"),
                    "spot_price": chain_row.get("spot_price"),
                    "source": "oplab",
                }
            except Exception as exc:
                logger.debug(
                    "normalize_contract: falha ao usar chain_row para '%s': %s — tentando regex",
                    text, exc,
                )

        # ── Caminho 2: parse via regex Bloomberg (comportamento legado) ──────────
        match = OPTION_TICKER_PATTERN.match(text)
        if not match:
            return {
                "option_id": None,
                "bloomberg_ticker": text,
                "underlying_security": underlying_security,
                "underlying_trade_symbol": Config.OPTIONS_UNDERLYING_TRADE_MAP.get(underlying_security),
                "status": "invalid",
                "parse_error": "Ticker format not recognized",
                "discovered_at": discovered_at,
                "last_seen_at": discovered_at,
                "source": "bloomberg",
            }

        expiry_date = datetime.strptime(match.group("expiry"), "%m/%d/%y").date()
        strike = float(match.group("strike"))
        put_call_flag = match.group("put_call")
        put_call = "Call" if put_call_flag == "C" else "Put"
        today = date.today()
        business_days = self._business_days_between(today, expiry_date)
        calendar_days = (expiry_date - today).days
        status = "expired" if expiry_date < today else "active"

        option_id = hashlib.sha1(
            f"{underlying_security}|{expiry_date.isoformat()}|{put_call_flag}|{strike}|{text}".encode("utf-8")
        ).hexdigest()

        return {
            "option_id": option_id,
            "bloomberg_ticker": text,
            "root_symbol": match.group("root"),
            "underlying_security": underlying_security,
            "underlying_trade_symbol": Config.OPTIONS_UNDERLYING_TRADE_MAP.get(underlying_security),
            "put_call": put_call,
            "put_call_flag": put_call_flag,
            "strike": strike,
            "expiry_date": expiry_date.isoformat(),
            "days_to_expiry_calendar": calendar_days,
            "days_to_expiry_business": business_days,
            "status": status,
            "mvp_eligible": business_days <= Config.OPTIONS_MAX_BUSINESS_DAYS and status == "active",
            "discovered_at": discovered_at,
            "last_seen_at": discovered_at,
            "expired_at": expiry_date.isoformat() if status == "expired" else None,
            "contract_multiplier": None,
            "source": "bloomberg",
        }

    def validate_contract(self, contract: dict[str, Any]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not contract.get("option_id"):
            errors.append("missing option_id")
        if not contract.get("bloomberg_ticker"):
            errors.append("missing bloomberg_ticker")
        if not contract.get("underlying_security"):
            errors.append("missing underlying_security")
        if contract.get("put_call") not in {"Call", "Put"}:
            errors.append("missing or invalid put_call")
        if contract.get("strike") in (None, ""):
            errors.append("missing strike")
        if not contract.get("expiry_date"):
            errors.append("missing expiry_date")
        return not errors, errors

    def list_contracts(
        self,
        underlying_security: str | None = None,
        only_active: bool = False,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return self.store.list_contracts(
            underlying_security=underlying_security,
            only_active=only_active,
            limit=limit,
        )

    def _business_days_between(self, start_date: date, end_date: date) -> int:
        if end_date <= start_date:
            return 0
        count = 0
        current = start_date
        while current < end_date:
            current += timedelta(days=1)
            if current.weekday() < 5:
                count += 1
        return count
