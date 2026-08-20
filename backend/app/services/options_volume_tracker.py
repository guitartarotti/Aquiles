"""
options_volume_tracker.py

Pipeline de rastreamento de volume para TODAS as opcoes e, ao mesmo tempo,
captura a superficie mensal de IV/OI usada pelo Volatility Index.

Fluxo por poll:
  1. Busca a cadeia completa via fetch_option_chain.
  2. Detecta variacao de volume versus o ultimo estado persistido.
  3. Para os vencimentos mensais, busca snapshots com IV/OI e grava um
     historico intraday mensal desacoplado do run do modelo.
  4. Persiste eventos de atividade + estado atualizado.
"""
from __future__ import annotations

import hashlib
import threading
from collections import defaultdict
from datetime import date as date_cls
from datetime import datetime, timezone
from typing import Any, Optional

from ..config import Config
from ..utils.logger import get_logger
from .options_store import OptionsStore
from .vol_index.iv_surface import extract_iv_metrics

logger = get_logger("aquiles.options_volume_tracker")

_MONTHLY_IV_FIELDS = [
    "OPT_EXPIRE_DT",
    "OPT_PUT_CALL",
    "OPT_STRIKE_PX",
    "OPT_UNDL_PX",
    "OPEN_INT",
    "OPT_OPEN_INTEREST",
    "IVOL_MID",
    "MODEL_IV",
    "EFF_IV",
    "OPT_DELTA",
    "MODEL_DELTA",
    "EFF_DELTA",
    "PX_LAST",
    "BID",
    "ASK",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _utc_now().isoformat()


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: Any) -> date_cls | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except Exception:
        return None


def _normalize_put_call(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if raw.startswith("C"):
        return "C"
    if raw.startswith("P"):
        return "P"
    return raw


class OptionsVolumeTracker:
    """
    Singleton que rastreia variacao de volume em toda a cadeia de opcoes.
    """

    _instance: Optional["OptionsVolumeTracker"] = None
    _instance_lock = threading.Lock()

    def __init__(
        self,
        store: OptionsStore | None = None,
        provider: Any | None = None,
    ) -> None:
        self.store = store or OptionsStore()
        if provider is None:
            from .options_data_provider import get_options_data_provider  # noqa: PLC0415
            provider = get_options_data_provider()
        self.provider = provider
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._runtime_lock = threading.RLock()

    @classmethod
    def get_instance(cls) -> "OptionsVolumeTracker":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def poll_once(self, underlying_security: str) -> dict[str, Any]:
        captured_at = _now_iso()
        session_date = captured_at[:10]

        try:
            chain_result = self.provider.fetch_option_chain(underlying_security)
        except Exception as exc:
            logger.error(
                "Volume tracker: erro ao buscar chain para %s: %s",
                underlying_security,
                exc,
            )
            return {
                "underlying_security": underlying_security,
                "captured_at": captured_at,
                "session_date": session_date,
                "error": str(exc),
                "events_created": 0,
                "chain_size": 0,
            }

        chain_rows: list[dict[str, Any]] = chain_result.get("chain_rows") or []
        if not chain_rows:
            logger.debug("Volume tracker: chain vazia para %s", underlying_security)
            return {
                "underlying_security": underlying_security,
                "captured_at": captured_at,
                "session_date": session_date,
                "events_created": 0,
                "chain_size": 0,
            }

        monthly_iv_snapshot, monthly_symbol_metrics, monthly_expiry_dates = self._build_monthly_iv_snapshot(
            underlying_security=underlying_security,
            chain_rows=chain_rows,
            captured_at=captured_at,
            session_date=session_date,
        )

        state: dict[str, float] = self.store.load_volume_state()
        new_state: dict[str, float] = dict(state)
        min_delta = Config.OPTIONS_VOLUME_MIN_DELTA
        events: list[dict[str, Any]] = []
        first_seen_count = 0
        unchanged_count = 0

        for row in chain_rows:
            symbol = str(row.get("symbol") or row.get("option_id") or "").strip()
            if not symbol:
                continue

            current_volume = _safe_float(
                row.get("volume") or row.get("PX_VOLUME") or row.get("VOLUME"),
                default=0.0,
            )
            last_volume = state.get(symbol, -1.0)

            if last_volume < 0:
                new_state[symbol] = current_volume
                first_seen_count += 1
                continue

            delta = current_volume - last_volume
            new_state[symbol] = current_volume

            if delta < min_delta:
                unchanged_count += 1
                continue

            event_key = f"{symbol}|{captured_at}|{current_volume}"
            event_id = hashlib.sha1(event_key.encode()).hexdigest()[:16]

            expiry_date = str(
                row.get("due_date") or row.get("expiry_date") or row.get("OPT_EXPIRE_DT") or ""
            )[:10]
            event = {
                "event_id": event_id,
                "captured_at": captured_at,
                "session_date": session_date,
                "underlying_security": underlying_security,
                "symbol": symbol,
                "put_call": _normalize_put_call(
                    row.get("type") or row.get("put_call") or row.get("OPT_PUT_CALL")
                ),
                "strike": _safe_float(row.get("strike") or row.get("OPT_STRIKE_PX")),
                "expiry_date": expiry_date,
                "days_to_maturity": _safe_int(
                    row.get("days_to_maturity") or row.get("days_to_expiry_business"),
                    default=0,
                ),
                "volume_before": last_volume,
                "volume_after": current_volume,
                "volume_delta": round(delta, 0),
                "spot_price": _safe_float(row.get("spot_price") or row.get("OPT_UNDL_PX")),
                "close": row.get("close") or row.get("PX_LAST"),
                "bid": row.get("bid") or row.get("BID"),
                "ask": row.get("ask") or row.get("ASK"),
                "is_monthly_expiry": expiry_date in monthly_expiry_dates,
            }

            monthly_metrics = monthly_symbol_metrics.get(symbol) or {}
            if monthly_metrics:
                event["selected_iv"] = monthly_metrics.get("selected_iv")
                event["effective_iv"] = monthly_metrics.get("effective_iv")
                event["model_iv"] = monthly_metrics.get("model_iv")
                event["observed_delta"] = monthly_metrics.get("observed_delta")
                event["open_interest"] = monthly_metrics.get("open_interest")
                event["monthly_selected_expiry"] = bool(monthly_metrics.get("monthly_selected_expiry"))

            events.append(event)

        written = self.store.append_volume_activity(events) if events else 0
        self.store.save_volume_state(new_state)
        if monthly_iv_snapshot:
            self.store.append_volume_iv_snapshot(monthly_iv_snapshot)
            try:
                from .vol_index import VolIndexService  # noqa: PLC0415

                spot_value = _safe_float(
                    monthly_iv_snapshot.get("spot_price")
                    or monthly_iv_snapshot.get("reference_price"),
                    default=0.0,
                )
                market_context = {
                    "spot_price": float(spot_value or 0.0),
                    "forward_price": float(spot_value or 0.0),
                }
                VolIndexService(underlying_security).record_snapshot(
                    prepared_options=[],
                    market_context=market_context,
                    date=session_date,
                    iv_payload=monthly_iv_snapshot,
                    option_count_override=monthly_iv_snapshot.get("chain_size") or len(chain_rows),
                    captured_at_override=monthly_iv_snapshot.get("captured_at"),
                )
            except Exception as exc:
                logger.warning(
                    "Volume tracker mensal: falha ao sincronizar vol-index para %s: %s",
                    underlying_security,
                    exc,
                )

        logger.info(
            "Volume tracker [%s]: %d contratos | %d com atividade | %d novos | %d sem mudanca | mensal=%s",
            underlying_security,
            len(chain_rows),
            len(events),
            first_seen_count,
            unchanged_count,
            bool(monthly_iv_snapshot),
        )

        return {
            "underlying_security": underlying_security,
            "captured_at": captured_at,
            "session_date": session_date,
            "chain_size": len(chain_rows),
            "first_seen": first_seen_count,
            "unchanged": unchanged_count,
            "events_created": len(events),
            "events_written": written,
            "events": events,
            "monthly_iv_snapshot": monthly_iv_snapshot,
        }

    def _build_monthly_iv_snapshot(
        self,
        *,
        underlying_security: str,
        chain_rows: list[dict[str, Any]],
        captured_at: str,
        session_date: str,
    ) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]], set[str]]:
        chain_by_symbol = {
            str(row.get("symbol") or "").strip(): row
            for row in chain_rows
            if row.get("symbol")
        }
        expiry_to_symbols: dict[str, list[str]] = defaultdict(list)
        expiry_to_stats: dict[str, dict[str, Any]] = {}
        month_candidates: dict[str, list[str]] = defaultdict(list)
        all_expiries_by_month: dict[str, list[str]] = defaultdict(list)

        for row in chain_rows:
            symbol = str(row.get("symbol") or "").strip()
            expiry_date = str(row.get("due_date") or "").strip()[:10]
            if not symbol or not expiry_date:
                continue
            expiry_to_symbols[expiry_date].append(symbol)
            all_expiries_by_month[expiry_date[:7]].append(expiry_date)
            parsed_expiry = _parse_date(expiry_date)
            if parsed_expiry and parsed_expiry.weekday() == 2:
                month_candidates[expiry_date[:7]].append(expiry_date)
            expiry_to_stats.setdefault(expiry_date, {
                "expiry_date": expiry_date,
                "days_to_expiry_business": _safe_int(row.get("days_to_maturity"), default=0),
                "option_count": 0,
                "total_open_interest": 0.0,
            })
            expiry_to_stats[expiry_date]["option_count"] += 1

        candidate_expiry_dates: list[str] = []
        for month_key, expiries in all_expiries_by_month.items():
            unique_candidates = sorted(set(month_candidates.get(month_key) or expiries))
            candidate_expiry_dates.extend(unique_candidates)
        candidate_expiry_dates = sorted(set(candidate_expiry_dates))
        candidate_symbols = [
            symbol
            for expiry_date in candidate_expiry_dates
            for symbol in expiry_to_symbols.get(expiry_date, [])
        ]
        if not candidate_symbols:
            return None, {}, set()

        try:
            snapshots = self.provider.fetch_option_snapshots(candidate_symbols, fields=_MONTHLY_IV_FIELDS)
        except Exception as exc:
            logger.warning("Volume tracker mensal: falha ao buscar snapshots para %s: %s", underlying_security, exc)
            return None, {}, set()

        snapshot_rows = snapshots.get("rows") or []
        normalized_rows: list[dict[str, Any]] = []
        monthly_symbol_metrics: dict[str, dict[str, Any]] = {}
        latest_spot = None

        for item in snapshot_rows:
            symbol = str(item.get("security") or "").strip()
            fields = item.get("fields") or {}
            chain_row = chain_by_symbol.get(symbol) or {}
            expiry_date = str(fields.get("OPT_EXPIRE_DT") or chain_row.get("due_date") or "")[:10]
            if not expiry_date:
                continue

            open_interest = _safe_optional_float(fields.get("OPEN_INT"))
            if open_interest is None:
                open_interest = _safe_optional_float(fields.get("OPT_OPEN_INTEREST"))
            expiry_to_stats.setdefault(expiry_date, {
                "expiry_date": expiry_date,
                "days_to_expiry_business": _safe_int(chain_row.get("days_to_maturity"), default=0),
                "option_count": 0,
                "total_open_interest": 0.0,
            })
            expiry_to_stats[expiry_date]["total_open_interest"] += max(open_interest or 0.0, 0.0)

            strike = _safe_optional_float(fields.get("OPT_STRIKE_PX"))
            put_call = _normalize_put_call(fields.get("OPT_PUT_CALL") or chain_row.get("type"))
            selected_iv = (
                _safe_optional_float(fields.get("EFF_IV"))
                or _safe_optional_float(fields.get("MODEL_IV"))
                or _safe_optional_float(fields.get("IVOL_MID"))
            )
            observed_delta = (
                _safe_optional_float(fields.get("EFF_DELTA"))
                or _safe_optional_float(fields.get("MODEL_DELTA"))
                or _safe_optional_float(fields.get("OPT_DELTA"))
            )
            days_to_expiry_business = _safe_int(chain_row.get("days_to_maturity"), default=0)
            spot_price = _safe_optional_float(fields.get("OPT_UNDL_PX")) or _safe_optional_float(chain_row.get("spot_price"))
            latest_spot = spot_price or latest_spot

            monthly_symbol_metrics[symbol] = {
                "selected_iv": selected_iv,
                "effective_iv": _safe_optional_float(fields.get("EFF_IV")),
                "model_iv": _safe_optional_float(fields.get("MODEL_IV")),
                "observed_delta": observed_delta,
                "open_interest": open_interest,
                "expiry_date": expiry_date,
            }

            if strike is None or not put_call:
                continue
            normalized_rows.append({
                "symbol": symbol,
                "expiry_date": expiry_date,
                "days_to_expiry_business": days_to_expiry_business,
                "days_to_expiry_calendar": max(days_to_expiry_business, 0),
                "selected_iv": selected_iv,
                "observed_delta": observed_delta,
                "strike": strike,
                "put_call": put_call,
                "open_interest": open_interest,
            })

        if not expiry_to_stats:
            return None, monthly_symbol_metrics, set()

        monthly_expiries: list[dict[str, Any]] = []
        monthly_expiry_dates: set[str] = set()
        for month_key, expiries in all_expiries_by_month.items():
            candidates = sorted(set(month_candidates.get(month_key) or expiries))
            if not candidates:
                continue

            def _rank(expiry_date: str) -> tuple[float, int, int, int]:
                summary = expiry_to_stats.get(expiry_date) or {}
                parsed_expiry = _parse_date(expiry_date)
                closeness = -abs((parsed_expiry.day if parsed_expiry else 15) - 15)
                return (
                    float(summary.get("total_open_interest") or 0.0),
                    int(summary.get("option_count") or 0),
                    closeness,
                    -int(str(expiry_date).replace("-", "")),
                )

            selected_expiry = max(candidates, key=_rank)
            summary = dict(expiry_to_stats.get(selected_expiry) or {})
            summary["month"] = month_key
            monthly_expiries.append(summary)
            monthly_expiry_dates.add(selected_expiry)

        if not monthly_expiries:
            return None, monthly_symbol_metrics, set()

        positive_monthlies = [
            item for item in monthly_expiries
            if _safe_int(item.get("days_to_expiry_business"), default=0) > 0
        ]
        fallback_monthlies = [
            item for item in monthly_expiries
            if _safe_int(item.get("days_to_expiry_business"), default=0) >= 0
        ]
        selection_pool = positive_monthlies or fallback_monthlies or monthly_expiries
        selected_monthly = min(
            selection_pool,
            key=lambda item: (
                _safe_int(item.get("days_to_expiry_business"), default=9_999),
                -float(item.get("total_open_interest") or 0.0),
            ),
        )
        selected_expiry_date = str(selected_monthly.get("expiry_date") or "")

        for _symbol, metrics in monthly_symbol_metrics.items():
            expiry_date = str(metrics.get("expiry_date") or "")
            metrics["is_monthly_expiry"] = expiry_date in monthly_expiry_dates
            metrics["monthly_selected_expiry"] = expiry_date == selected_expiry_date

        spot_context = {
            "spot_price": latest_spot,
            "forward_price": latest_spot,
        }
        monthly_metric_rows = [
            row for row in normalized_rows
            if row.get("expiry_date") in monthly_expiry_dates
        ]
        selected_metric_rows = [
            row for row in monthly_metric_rows
            if row.get("expiry_date") == selected_expiry_date
        ]
        monthly_metrics = extract_iv_metrics(monthly_metric_rows, spot_context, target_dte_days=30) if monthly_metric_rows else {}
        selected_metrics = extract_iv_metrics(
            selected_metric_rows,
            spot_context,
            target_dte_days=max(_safe_int(selected_monthly.get("days_to_expiry_business"), default=21), 1),
        ) if selected_metric_rows else {}

        chosen = selected_metrics or monthly_metrics
        payload = {
            "captured_at": captured_at,
            "session_date": session_date,
            "underlying_security": underlying_security,
            "source": "volume_tracker_monthly",
            "selection_basis": "monthly_expiry_max_oi",
            "spot_price": latest_spot,
            "chain_size": len(chain_rows),
            "candidate_symbol_count": len(candidate_symbols),
            "selected_expiry_date": selected_expiry_date or None,
            "selected_days_to_expiry": _safe_int(selected_monthly.get("days_to_expiry_business"), default=0),
            "selected_total_open_interest": float(selected_monthly.get("total_open_interest") or 0.0),
            "selected_option_count": int(selected_monthly.get("option_count") or 0),
            "monthly_expiries": sorted(
                monthly_expiries,
                key=lambda item: (
                    _safe_int(item.get("days_to_expiry_business"), default=9_999),
                    str(item.get("expiry_date") or ""),
                ),
            ),
            "monthly_term_30d_iv": monthly_metrics.get("iv_interpolated"),
            "iv_interpolated": chosen.get("iv_interpolated") or monthly_metrics.get("iv_interpolated"),
            "iv_atm": chosen.get("iv_atm") or monthly_metrics.get("iv_atm"),
            "iv_25d_put": chosen.get("iv_25d_put"),
            "iv_25d_call": chosen.get("iv_25d_call"),
            "iv_15d_put": chosen.get("iv_15d_put"),
            "iv_15d_call": chosen.get("iv_15d_call"),
            "iv_10d_put": chosen.get("iv_10d_put"),
            "iv_10d_call": chosen.get("iv_10d_call"),
            "skew_25d": chosen.get("skew_25d"),
            "skew_15d": chosen.get("skew_15d"),
            "skew_10d": chosen.get("skew_10d"),
            "term_structure": monthly_metrics.get("term_structure") or [],
            "near_expiry_dte": chosen.get("near_expiry_dte") or _safe_int(selected_monthly.get("days_to_expiry_business"), default=0),
        }
        return payload, monthly_symbol_metrics, monthly_expiry_dates

    def poll_all_underlyings(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        total_events = 0
        for underlying in Config.OPTIONS_BLOOMBERG_UNDERLYINGS:
            result = self.poll_once(underlying)
            results[underlying] = result
            total_events += result.get("events_created", 0)
        return {
            "underlyings": results,
            "total_events_created": total_events,
            "captured_at": _now_iso(),
        }

    def _run_loop(self) -> None:
        interval = max(10, int(Config.OPTIONS_VOLUME_POLL_SECONDS))
        logger.info(
            "Options volume tracker loop iniciado (intervalo=%ds, underlyings=%s)",
            interval,
            Config.OPTIONS_BLOOMBERG_UNDERLYINGS,
        )
        while not self._stop_event.is_set():
            try:
                self.poll_all_underlyings()
            except Exception:
                logger.exception("Volume tracker: erro na iteracao de polling")
            if self._stop_event.wait(interval):
                break
        logger.info("Options volume tracker loop encerrado")

    def start(self) -> dict[str, Any]:
        with self._runtime_lock:
            if self._loop_thread and self._loop_thread.is_alive():
                return self.status()
            self._stop_event = threading.Event()
            self._loop_thread = threading.Thread(
                target=self._run_loop,
                daemon=True,
                name="options-volume-tracker",
            )
            self._loop_thread.start()
            logger.info("Options volume tracker iniciado")
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._runtime_lock:
            self._stop_event.set()
            if self._loop_thread and self._loop_thread.is_alive():
                self._loop_thread.join(timeout=6)
            logger.info("Options volume tracker parado")
            return self.status()

    def status(self) -> dict[str, Any]:
        running = bool(self._loop_thread and self._loop_thread.is_alive())
        vol_state = self.store.load_volume_state()
        latest_iv = self.store.read_latest_volume_iv_snapshot(lookback_days=5)
        return {
            "running": running,
            "poll_interval_seconds": Config.OPTIONS_VOLUME_POLL_SECONDS,
            "min_delta": Config.OPTIONS_VOLUME_MIN_DELTA,
            "underlyings": Config.OPTIONS_BLOOMBERG_UNDERLYINGS,
            "tracked_symbols": len(vol_state),
            "latest_monthly_iv_at": (latest_iv or {}).get("captured_at"),
            "latest_monthly_expiry": (latest_iv or {}).get("selected_expiry_date"),
        }

    def backfill_today(self) -> dict[str, Any]:
        logger.info("Iniciando backfill de atividade de volume para o dia atual")
        result = self.poll_all_underlyings()
        total = result.get("total_events_created", 0)
        logger.info("Backfill concluido: %d eventos criados", total)
        return result

    def resume_if_needed(self) -> dict[str, Any]:
        with self._runtime_lock:
            if self._loop_thread and self._loop_thread.is_alive():
                logger.debug("Options volume tracker ja esta rodando - resume_if_needed ignorado")
                return self.status()
        logger.info("Options volume tracker nao estava rodando - iniciando via resume_if_needed")
        return self.start()
