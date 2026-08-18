"""
B3OIService
===========
Orquestra a coleta diaria de Open Interest (OI) da B3 para opcoes de indices.

Fluxo:
  1. Verifica se o OI do dia ja foi coletado (checkpoint)
  2. Se nao, chama B3OpenInterestScraper.fetch(date)
  3. Salva os dados no OptionsStore (oi_daily/{date}/b3_oi.jsonl)
  4. Marca o checkpoint para nao repetir

API publica:
  service.collect_daily_oi(trade_date=None, force=False) -> dict
  service.is_collected(trade_date=None) -> bool
  service.get_oi(symbol, trade_date=None) -> dict | None
  service.backfill(date_from, date_to, force=False) -> dict
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..utils.logger import get_logger
from .b3_open_interest_scraper import B3OpenInterestScraper
from .options_store import OptionsStore

logger = get_logger("mirofish.b3_oi_service")

_CHECKPOINT_PREFIX = "b3_oi_complete"


def _checkpoint_key(trade_date: str) -> str:
    return f"{_CHECKPOINT_PREFIX}::{trade_date}"


class B3OIService:
    """
    Servico de Open Interest da B3 com checkpoint diario.
    Thread-safe via OptionsStore._lock.
    """

    def __init__(
        self,
        store: OptionsStore | None = None,
        scraper: B3OpenInterestScraper | None = None,
    ):
        self.store = store or OptionsStore()
        self.scraper = scraper or B3OpenInterestScraper()

    # ─── API publica ─────────────────────────────────────────────────────

    def is_collected(self, trade_date: str | None = None) -> bool:
        """Retorna True se o OI desta data ja foi coletado e salvo."""
        date = trade_date or _today()
        key = _checkpoint_key(date)
        cp = self.store.load_backfill_checkpoint(key)
        return bool(cp and cp.get("complete") and cp.get("rows_saved", 0) > 0)

    def collect_daily_oi(
        self,
        trade_date: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """
        Coleta e persiste o OI da B3 para a data informada.

        Parametros
        ----------
        trade_date : str, opcional
            Formato 'YYYY-MM-DD'. Padrao: hoje.
        force : bool
            Se True, re-coleta mesmo que ja exista checkpoint.

        Retorna
        -------
        dict com:
          skipped      bool
          skip_reason  str (se skipped)
          trade_date   str
          rows_saved   int
          rows         list[dict] (os registros de OI)
          error        str | None
        """
        date = trade_date or _today()

        if not force and self.is_collected(date):
            logger.info("B3 OI: ja coletado para %s (use force=True para re-coletar)", date)
            return {
                "skipped": True,
                "skip_reason": "b3_oi_already_collected",
                "trade_date": date,
                "rows_saved": 0,
                "rows": [],
                "error": None,
            }

        logger.info("B3 OI: iniciando coleta para %s", date)
        try:
            rows = self.scraper.fetch(date=date)
        except Exception as exc:
            logger.error("B3 OI: erro no scraper para %s — %s", date, exc)
            return {
                "skipped": False,
                "trade_date": date,
                "rows_saved": 0,
                "rows": [],
                "error": str(exc),
            }

        if not rows:
            logger.warning(
                "B3 OI: nenhum dado retornado para %s "
                "(feriado, fim de semana ou mercado sem negociacoes?)",
                date,
            )
            return {
                "skipped": False,
                "trade_date": date,
                "rows_saved": 0,
                "rows": [],
                "error": "no_data_from_b3",
            }

        # Persiste no store
        save_result = self.store.save_b3_oi_rows(trade_date=date, rows=rows)
        rows_saved = save_result.get("rows_written", 0)

        # Salva checkpoint
        self.store.save_backfill_checkpoint(
            _checkpoint_key(date),
            {
                "trade_date": date,
                "complete": True,
                "rows_saved": rows_saved,
                "completed_at": datetime.utcnow().isoformat() + "Z",
                "source": "b3_scraper",
            },
        )

        logger.info("B3 OI: %d contratos salvos para %s", rows_saved, date)
        return {
            "skipped": False,
            "trade_date": date,
            "rows_saved": rows_saved,
            "rows": rows,
            "error": None,
        }

    def get_oi(
        self,
        symbol: str,
        trade_date: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Retorna o registro de OI de um contrato especifico.

        Parametros
        ----------
        symbol : str
            Ticker B3, ex: 'IBOVF178', 'IBOVQ180E2'
        trade_date : str, opcional
            Formato 'YYYY-MM-DD'. Padrao: hoje.

        Retorna None se nao houver dado.
        """
        date = trade_date or _today()
        return self.store.get_b3_oi_for_symbol(symbol=symbol, trade_date=date)

    def get_oi_map(self, trade_date: str | None = None) -> dict[str, dict[str, Any]]:
        """
        Retorna dict {symbol -> row} para rapida lookup.
        Util no pipeline do Wyrm para enriquecer contratos com OI.
        """
        date = trade_date or _today()
        rows = self.store.load_b3_oi_rows(trade_date=date)
        return {row["symbol"]: row for row in rows if row.get("symbol")}

    def last_published_trade_date(self, trade_date: str | None = None) -> str:
        return _last_business_day(trade_date)

    def recent_trade_dates(
        self,
        trade_date: str | None = None,
        lookback_business_days: int = 5,
    ) -> list[str]:
        target = datetime.fromisoformat(trade_date or self.last_published_trade_date()).date()
        dates: list[str] = []
        current = target
        while len(dates) < max(lookback_business_days, 1):
            if current.weekday() < 5:
                dates.append(current.isoformat())
            current -= timedelta(days=1)
        return dates

    def resolve_recent_trade_date(
        self,
        trade_date: str | None = None,
        lookback_business_days: int = 5,
    ) -> str | None:
        for candidate in self.recent_trade_dates(
            trade_date=trade_date,
            lookback_business_days=lookback_business_days,
        ):
            rows = self.store.load_b3_oi_rows(candidate)
            if rows:
                return candidate
        return None

    def ensure_recent_oi(
        self,
        trade_date: str | None = None,
        lookback_business_days: int = 5,
    ) -> dict[str, Any]:
        tried_dates: list[str] = []
        for candidate in self.recent_trade_dates(
            trade_date=trade_date,
            lookback_business_days=lookback_business_days,
        ):
            tried_dates.append(candidate)
            if self.is_collected(candidate):
                rows = self.store.load_b3_oi_rows(candidate)
                if rows:
                    return {
                        "skipped": True,
                        "skip_reason": "b3_oi_already_collected",
                        "trade_date": candidate,
                        "resolved_trade_date": candidate,
                        "rows_saved": len(rows),
                        "rows": [],
                        "error": None,
                    }
            result = self.collect_daily_oi(trade_date=candidate, force=False)
            if not result.get("error"):
                return {
                    **result,
                    "resolved_trade_date": candidate,
                }
        return {
            "skipped": False,
            "trade_date": trade_date or _today(),
            "resolved_trade_date": None,
            "rows_saved": 0,
            "rows": [],
            "error": "no_recent_b3_oi_available",
            "tried_dates": tried_dates,
        }

    def get_recent_oi_map(
        self,
        trade_date: str | None = None,
        lookback_business_days: int = 5,
        ensure: bool = False,
    ) -> dict[str, Any]:
        resolved_trade_date = self.resolve_recent_trade_date(
            trade_date=trade_date,
            lookback_business_days=lookback_business_days,
        )
        ensure_result: dict[str, Any] | None = None
        if resolved_trade_date is None and ensure:
            ensure_result = self.ensure_recent_oi(
                trade_date=trade_date,
                lookback_business_days=lookback_business_days,
            )
            resolved_trade_date = ensure_result.get("resolved_trade_date")
        oi_map = self.get_oi_map(resolved_trade_date) if resolved_trade_date else {}
        if resolved_trade_date and oi_map:
            oi_map = {
                **oi_map,
                **{str(symbol).upper(): row for symbol, row in oi_map.items()},
            }
        return {
            "trade_date": resolved_trade_date,
            "map": oi_map,
            "rows_count": len({str(symbol).upper(): row for symbol, row in oi_map.items()}),
            "ensure_result": ensure_result,
        }

    def list_collected_dates(self) -> list[str]:
        """Lista datas que tem dados de OI salvos."""
        return self.store.list_b3_oi_dates()

    def backfill(
        self,
        date_from: str,
        date_to: str,
        force: bool = False,
        sleep_between_s: float = 3.0,
    ) -> dict[str, Any]:
        """
        Coleta OI para um intervalo de datas (backfill historico).
        Pula datas ja coletadas (a menos que force=True).

        Retorna resumo: {collected, skipped, errors, dates_collected}
        """
        from datetime import timedelta

        start = datetime.fromisoformat(date_from).date()
        end   = datetime.fromisoformat(date_to).date()

        collected: list[str] = []
        skipped:   list[str] = []
        errors:    list[str] = []

        import time

        current = start
        while current <= end:
            if current.weekday() >= 5:   # pula fim de semana
                current += timedelta(days=1)
                continue

            iso = current.isoformat()
            result = self.collect_daily_oi(trade_date=iso, force=force)

            if result.get("skipped"):
                skipped.append(iso)
            elif result.get("error"):
                errors.append(f"{iso}: {result['error']}")
            elif result.get("rows_saved", 0) > 0:
                collected.append(iso)
            else:
                errors.append(f"{iso}: sem dados")

            time.sleep(sleep_between_s)
            current += timedelta(days=1)

        return {
            "date_from": date_from,
            "date_to": date_to,
            "collected": len(collected),
            "skipped": len(skipped),
            "errors": len(errors),
            "dates_collected": collected,
            "error_details": errors,
        }


# ─── Utilidades ─────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now().date().isoformat()


def _last_business_day(ref_date: str | None = None) -> str:
    base = datetime.fromisoformat(ref_date or _today()).date()
    current = base - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current.isoformat()
