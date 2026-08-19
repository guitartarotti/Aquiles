from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..config import Config
from ..utils.logger import get_logger
from .options_bloomberg_service import OptionsBloombergService
from .options_data_provider import get_options_data_provider
from .options_snapshot_service import OptionsSnapshotService
from .options_store import OptionsStore

logger = get_logger("aquiles.options_history")


def _daily_oi_checkpoint_key(underlying_security: str, trade_date: str) -> str:
    return f"daily_oi_complete::{underlying_security}::{trade_date}"


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


class OptionsHistoryService:
    def __init__(
        self,
        store: OptionsStore | None = None,
        bloomberg: OptionsBloombergService | None = None,
        snapshot_service: OptionsSnapshotService | None = None,
    ):
        self.store = store or OptionsStore()
        self.bloomberg = bloomberg or get_options_data_provider()
        self.snapshot_service = snapshot_service or OptionsSnapshotService(store=self.store, bloomberg=self.bloomberg)

    def is_daily_oi_complete(self, underlying_security: str, trade_date: str | None = None) -> bool:
        """Retorna True se o OI desse dia já foi coletado e persistido com sucesso."""
        target_date = trade_date or datetime.now().date().isoformat()
        key = _daily_oi_checkpoint_key(underlying_security, target_date)
        checkpoint = self.store.load_backfill_checkpoint(key)
        return bool(checkpoint and checkpoint.get("complete") and checkpoint.get("processed_contracts", 0) > 0)

    def _mark_daily_oi_complete(
        self,
        underlying_security: str,
        trade_date: str,
        processed_contracts: int,
        rows_written: int,
    ) -> None:
        """Salva checkpoint indicando que o OI do dia foi coletado com sucesso."""
        key = _daily_oi_checkpoint_key(underlying_security, trade_date)
        self.store.save_backfill_checkpoint(key, {
            "underlying_security": underlying_security,
            "trade_date": trade_date,
            "complete": True,
            "processed_contracts": processed_contracts,
            "rows_written": rows_written,
            "completed_at": datetime.utcnow().isoformat() + "Z",
        })
        logger.info(
            "OI diário marcado como completo: %s %s (%d contratos, %d linhas)",
            underlying_security,
            trade_date,
            processed_contracts,
            rows_written,
        )

    def backfill_open_interest_history(
        self,
        underlying_security: str,
        lookback_days: int | None = None,
        checkpoint_key: str | None = None,
        max_contracts: int | None = None,
    ) -> dict[str, Any]:
        universe_payload = self.snapshot_service.prepare_universe(underlying_security)
        structural_rows = [
            row for row in universe_payload.get("structural", [])
            if row.get("structural_eligible")
        ]
        if max_contracts is not None:
            structural_rows = structural_rows[: max(1, int(max_contracts))]
        lookback_days = int(lookback_days or Config.OPTIONS_OI_BACKFILL_LOOKBACK_DAYS)
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=lookback_days)
        checkpoint_key = checkpoint_key or f"backfill::{underlying_security}"
        checkpoint = self.store.load_backfill_checkpoint(checkpoint_key)
        start_index = int(checkpoint.get("last_completed_index", -1)) + 1 if checkpoint else 0

        total_rows = 0
        processed_contracts = 0
        errors: list[dict[str, Any]] = []
        for index, contract in enumerate(structural_rows[start_index:], start=start_index):
            security = contract.get("bloomberg_ticker")
            option_id = contract.get("option_id")
            if not security or not option_id:
                continue
            try:
                history = self.bloomberg.fetch_option_history(
                    security=security,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    fields=self.bloomberg.DAILY_HISTORY_FIELDS,
                )
                normalized_rows = self._normalize_history_rows(
                    contract=contract,
                    history_rows=history.get("rows", []),
                    load_type="backfill",
                )
                upsert_result = self.store.upsert_oi_daily_rows(normalized_rows)
                self.store.recompute_oi_changes(upsert_result.get("affected_option_ids", []))
                total_rows += int(upsert_result.get("rows_written", 0))
                processed_contracts += 1
                self.store.save_backfill_checkpoint(checkpoint_key, {
                    "underlying_security": underlying_security,
                    "last_completed_index": index,
                    "last_security": security,
                    "last_option_id": option_id,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "rows_written": total_rows,
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                })
            except Exception as exc:
                logger.exception("Options OI backfill failed for %s", security)
                errors.append({
                    "security": security,
                    "error": str(exc),
                })

        return {
            "underlying_security": underlying_security,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "eligible_contracts": len(structural_rows),
            "processed_contracts": processed_contracts,
            "rows_written": total_rows,
            "errors": errors[:50],
            "checkpoint_key": checkpoint_key,
            "max_contracts": max_contracts,
        }

    def update_daily_open_interest(
        self,
        underlying_security: str,
        trade_date: str | None = None,
        max_contracts: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        target_date = trade_date or datetime.now().date().isoformat()

        # Se já coletamos o OI de hoje, não bate no Bloomberg de novo
        if not force and self.is_daily_oi_complete(underlying_security, target_date):
            logger.debug(
                "OI diário já coletado para %s em %s — pulando Bloomberg",
                underlying_security,
                target_date,
            )
            return {
                "underlying_security": underlying_security,
                "trade_date": target_date,
                "eligible_contracts": 0,
                "processed_contracts": 0,
                "rows_written": 0,
                "missing_ranges_filled": 0,
                "errors": [],
                "max_contracts": max_contracts,
                "skipped": True,
                "skip_reason": "daily_oi_already_collected",
            }

        universe_payload = self.snapshot_service.prepare_universe(underlying_security)
        structural_rows = [
            row for row in universe_payload.get("structural", [])
            if row.get("structural_eligible")
        ]
        if max_contracts is not None:
            structural_rows = structural_rows[: max(1, int(max_contracts))]

        processed_contracts = 0
        rows_written = 0
        missing_filled = 0
        errors: list[dict[str, Any]] = []

        for contract in structural_rows:
            security = contract.get("bloomberg_ticker")
            option_id = contract.get("option_id")
            if not security or not option_id:
                continue
            try:
                latest_trade_date = self.store.get_latest_trade_date_for_option(option_id)
                if latest_trade_date and latest_trade_date >= target_date:
                    continue
                start_date = target_date
                if latest_trade_date:
                    start_date_dt = datetime.fromisoformat(latest_trade_date).date() + timedelta(days=1)
                    start_date = start_date_dt.isoformat()
                    if start_date < target_date:
                        missing_filled += 1
                history = self.bloomberg.fetch_option_history(
                    security=security,
                    start_date=start_date,
                    end_date=target_date,
                    fields=self.bloomberg.DAILY_HISTORY_FIELDS,
                )
                normalized_rows = self._normalize_history_rows(
                    contract=contract,
                    history_rows=history.get("rows", []),
                    load_type="incremental",
                )
                upsert_result = self.store.upsert_oi_daily_rows(normalized_rows)
                self.store.recompute_oi_changes(upsert_result.get("affected_option_ids", []))
                rows_written += int(upsert_result.get("rows_written", 0))
                processed_contracts += 1
            except Exception as exc:
                logger.exception("Options OI incremental update failed for %s", security)
                errors.append({
                    "security": security,
                    "error": str(exc),
                })

        # Persiste checkpoint se coletou pelo menos um contrato com sucesso
        if processed_contracts > 0:
            self._mark_daily_oi_complete(
                underlying_security=underlying_security,
                trade_date=target_date,
                processed_contracts=processed_contracts,
                rows_written=rows_written,
            )
        else:
            logger.warning(
                "OI diário para %s em %s: nenhum contrato processado — checkpoint NÃO salvo",
                underlying_security,
                target_date,
            )

        return {
            "underlying_security": underlying_security,
            "trade_date": target_date,
            "eligible_contracts": len(structural_rows),
            "processed_contracts": processed_contracts,
            "rows_written": rows_written,
            "missing_ranges_filled": missing_filled,
            "errors": errors[:50],
            "max_contracts": max_contracts,
            "skipped": False,
        }

    def _normalize_history_rows(
        self,
        contract: dict[str, Any],
        history_rows: list[dict[str, Any]],
        load_type: str,
    ) -> list[dict[str, Any]]:
        normalized_rows: list[dict[str, Any]] = []
        previous_row = self.store.get_latest_oi_row_before(
            option_id=str(contract.get("option_id") or ""),
            trade_date=str(history_rows[0].get("trade_date") or "") if history_rows else "",
        )
        previous_oi = self._extract_oi_value(previous_row) if previous_row else None

        for item in sorted(history_rows, key=lambda row: row.get("trade_date") or ""):
            trade_date = str(item.get("trade_date") or "")[:10]
            if not trade_date:
                continue
            fields = item.get("fields") or {}
            row = {
                "trade_date": trade_date,
                "option_id": contract.get("option_id"),
                "bloomberg_ticker": contract.get("bloomberg_ticker"),
                "underlying_security": contract.get("underlying_security"),
                "underlying_trade_symbol": contract.get("underlying_trade_symbol"),
                "expiry_date": contract.get("expiry_date"),
                "strike": contract.get("strike"),
                "put_call": contract.get("put_call"),
                "open_int": _safe_float(fields.get("OPEN_INT")),
                "opt_open_interest": _safe_float(fields.get("OPT_OPEN_INTEREST")),
                "px_volume": _safe_float(fields.get("PX_VOLUME")),
                "ivol_mid": _safe_float(fields.get("IVOL_MID")),
                "px_last": _safe_float(fields.get("PX_LAST")),
                "bid": _safe_float(fields.get("BID")),
                "ask": _safe_float(fields.get("ASK")),
                "captured_at": datetime.utcnow().isoformat() + "Z",
                "history_load_type": load_type,
            }
            current_oi = self._extract_oi_value(row)
            if current_oi is not None and previous_oi not in (None, 0):
                row["oi_change_abs"] = current_oi - previous_oi
                row["oi_change_pct"] = (current_oi - previous_oi) / previous_oi
            elif current_oi is not None and previous_oi == 0:
                row["oi_change_abs"] = current_oi
                row["oi_change_pct"] = None
            else:
                row["oi_change_abs"] = None
                row["oi_change_pct"] = None
            if current_oi is not None:
                previous_oi = current_oi
            normalized_rows.append(row)
        return normalized_rows

    def _extract_oi_value(self, row: dict[str, Any] | None) -> float | None:
        if not row:
            return None
        for key in ("opt_open_interest", "open_int", "OPT_OPEN_INTEREST", "OPEN_INT"):
            value = row.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except Exception:
                continue
        return None
