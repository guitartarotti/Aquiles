"""
Volatility Index service.

This service now keeps two complementary histories:
1. A daily snapshot per underlying.
2. An intraday trail keyed by capture timestamp so the Discovery widget can
   show how vol and skew move during the session.

For realized volatility we anchor the return history to the recent XB1 closes
persisted in `price_history.jsonl`, and we keep replacing today's close with
the latest intraday XB1 price from the market-screen capture. That lets the
realized-vol and GARCH/fallback series breathe during the day instead of
staying frozen until the close.
"""

from __future__ import annotations

import csv
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import numpy as np

from .garch_ged import GarchGedParams, fit_garch_ged, forecast_garch_ged, realized_vol_simple
from .history_store import VolHistoryStore
from .iv_surface import extract_iv_metrics
from .vrp_model import compute_vrp

logger = logging.getLogger(__name__)

_BRT = ZoneInfo("America/Sao_Paulo")
_BASE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "uploads", "vol_history")
)
_MARKET_SCREEN_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "..",
        "uploads",
        "options",
        "market_screen_capture",
    )
)

_REFERENCE_SYMBOL_MAP = {
    "IBOVE INDEX": "XB1",
    "IBOVB3 INDEX": "XB1",
    "WIN INDEX": "WIN",
    "WDO INDEX": "WDO",
}

_DAILY_GARCH_SHORT_WINDOW = 5
_INTRADAY_BAR_SECONDS = 60
_INTRADAY_GARCH_LOOKBACK_BARS = 240
_INTRADAY_GARCH_FORECAST_BARS = 30
_INTRADAY_BARS_PER_DAY = 390
_INTRADAY_PERIODS_PER_YEAR = 252 * _INTRADAY_BARS_PER_DAY


def _today() -> str:
    return datetime.datetime.now(_BRT).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.datetime.now(_BRT).isoformat()


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(parsed):
        return None
    return parsed


def _parse_iso(value: Any) -> datetime.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


class VolIndexService:
    """Volatility Index orchestration for one underlying."""

    def __init__(self, underlying: str):
        self.underlying = underlying
        self._store = VolHistoryStore(base_dir=_BASE, underlying=underlying)
        self._market_screen_rows_dir = os.path.join(_MARKET_SCREEN_ROOT, "rows")
        self._market_screen_latest_path = os.path.join(_MARKET_SCREEN_ROOT, "latest.json")

    def record_snapshot(
        self,
        prepared_options: list | None,
        market_context,
        date: Optional[str] = None,
        force: bool = False,
        iv_payload: Optional[dict[str, Any]] = None,
        option_count_override: Optional[int] = None,
        captured_at_override: Optional[str] = None,
    ) -> dict:
        """
        Compute and persist a fresh snapshot.

        `force` is kept for API compatibility. Daily storage is still upserted by
        date, but we always append/update the intraday trail because the user now
        wants to track the evolution during the session.
        """
        del force
        date = date or _today()
        prepared_options = prepared_options or []
        market_context = market_context or {}

        reference_symbol = self._reference_symbol()
        recent_closes, live_tick = self._sync_recent_reference_prices(
            reference_symbol=reference_symbol,
            target_date=date,
            lookback_days=5,
        )

        spot = self._get_spot(market_context)
        iv = dict(iv_payload or {})
        if not iv:
            iv = extract_iv_metrics(prepared_options, market_context)

        live_price = None
        if live_tick and str(live_tick.get("session_date") or "") == date:
            live_price = _safe_float(live_tick.get("price"))

        garch = self._run_garch(live_date=date, live_price=live_price)

        history = [item for item in self._store.load_history(252) if str(item.get("date") or "") != date]
        iv_ref = iv.get("iv_interpolated") or iv.get("iv_atm")
        vrp = compute_vrp(
            iv_30d=iv_ref,
            rv_garch_30d=garch.get("rv_garch_30d"),
            history=history,
        )

        normalized_captured_at = _now_iso()
        if captured_at_override:
            parsed_override = _parse_iso(captured_at_override)
            if parsed_override is not None:
                normalized_captured_at = parsed_override.astimezone(_BRT).isoformat()

        record: dict[str, Any] = {
            "date": date,
            "captured_at": normalized_captured_at,
            "underlying": self.underlying,
            "spot": round(float(spot), 4) if spot is not None else None,
            "reference_symbol": reference_symbol,
            "reference_price": round(float(live_price), 4) if live_price is not None else None,
            "reference_price_at": live_tick.get("captured_at") if live_tick else None,
            "reference_price_source": live_tick.get("source") if live_tick else None,
            "recent_closes": recent_closes[-5:],
            "iv_source": iv.get("source") or ("prepared_options" if prepared_options else "unavailable"),
            "iv_captured_at": iv.get("captured_at"),
            "iv_session_date": iv.get("session_date"),
            "iv_underlying_security": iv.get("underlying_security"),
            "iv_selection_basis": iv.get("selection_basis"),
            "selected_expiry_date": iv.get("selected_expiry_date"),
            "selected_days_to_expiry": iv.get("selected_days_to_expiry"),
            "selected_total_open_interest": iv.get("selected_total_open_interest"),
            "selected_option_count": iv.get("selected_option_count"),
            "monthly_expiries": iv.get("monthly_expiries") or [],
            "monthly_term_30d_iv": iv.get("monthly_term_30d_iv"),
            "iv_interpolated": iv.get("iv_interpolated"),
            "iv_atm": iv.get("iv_atm"),
            "iv_25d_put": iv.get("iv_25d_put"),
            "iv_25d_call": iv.get("iv_25d_call"),
            "iv_15d_put": iv.get("iv_15d_put"),
            "iv_15d_call": iv.get("iv_15d_call"),
            "iv_10d_put": iv.get("iv_10d_put"),
            "iv_10d_call": iv.get("iv_10d_call"),
            "skew_25d": iv.get("skew_25d"),
            "skew_15d": iv.get("skew_15d"),
            "skew_10d": iv.get("skew_10d"),
            "term_structure": iv.get("term_structure", []),
            "near_expiry_dte": iv.get("near_expiry_dte"),
            "rv_garch_5d": garch.get("rv_garch_5d"),
            "rv_garch_30d": garch.get("rv_garch_30d"),
            "rv_garch_intraday": garch.get("rv_garch_intraday"),
            "rv_simple_21d": garch.get("rv_simple_21d"),
            "rv_live_5d": garch.get("rv_live_5d"),
            "rv_live_3d": garch.get("rv_live_3d"),
            "garch_alpha": garch.get("alpha"),
            "garch_beta": garch.get("beta"),
            "garch_nu": garch.get("nu"),
            "garch_persistence": garch.get("persistence"),
            "garch_converged": garch.get("converged"),
            "garch_mode": garch.get("mode"),
            "garch_error": garch.get("garch_error"),
            "garch_intraday_mode": garch.get("intraday_mode"),
            "garch_intraday_obs": garch.get("intraday_obs"),
            "garch_intraday_window_bars": garch.get("intraday_window_bars"),
            "vrp_raw": vrp.get("vrp_raw"),
            "vrp_z_score": vrp.get("vrp_z_score"),
            "vrp_percentile": vrp.get("vrp_percentile"),
            "vrp_rolling_20d": vrp.get("vrp_rolling_20d"),
            "vrp_rolling_60d": vrp.get("vrp_rolling_60d"),
            "vrp_is_outlier": vrp.get("vrp_is_outlier"),
            "n_options": int(option_count_override) if option_count_override is not None else len(prepared_options),
            "n_price_obs": garch.get("n_obs"),
            "price_dates": garch.get("price_dates"),
        }

        self._store.append_snapshot(record)
        self._store.append_intraday_snapshot(record)
        logger.info(
            "[VolIndex:%s] recorded %s - IV_ATM=%s G5=%s G30=%s Gmicro=%s RV5=%s ref=%s",
            self.underlying,
            date,
            iv.get("iv_atm"),
            garch.get("rv_garch_5d"),
            garch.get("rv_garch_30d"),
            garch.get("rv_garch_intraday"),
            garch.get("rv_live_5d"),
            live_price,
        )
        return record

    def get_history(self, days: int = 252) -> list[dict]:
        return self._store.load_history(days)

    def get_intraday_history(self, days: int = 5) -> list[dict]:
        return self._store.load_intraday_history(days)

    def get_latest(self) -> Optional[dict]:
        intraday = self._store.load_latest_intraday()
        if intraday:
            return intraday
        return self._store.get_latest()

    def _get_spot(self, ctx) -> Optional[float]:
        value = ctx.get("spot_price") if isinstance(ctx, dict) else getattr(ctx, "spot_price", None)
        return _safe_float(value)

    def _reference_symbol(self) -> str:
        normalized = " ".join(str(self.underlying or "").upper().split()).strip()
        if normalized in _REFERENCE_SYMBOL_MAP:
            return _REFERENCE_SYMBOL_MAP[normalized]
        first_token = normalized.split(" ", 1)[0].strip()
        return first_token or "XB1"

    def _recent_row_csv_paths(self, lookback_days: int) -> list[Path]:
        rows_dir = Path(self._market_screen_rows_dir)
        if not rows_dir.exists():
            return []
        csv_paths = sorted(rows_dir.glob("*.csv"))
        if not csv_paths:
            return []
        return csv_paths[-max(int(lookback_days), 1):]

    @staticmethod
    def _row_file_date(path: Path) -> str | None:
        try:
            return path.stem[:10]
        except Exception:
            return None

    def _last_session_price(self, path: Path, reference_symbol: str) -> dict[str, Any] | None:
        reference = reference_symbol.upper().strip()
        if not reference or not path.exists():
            return None

        last_match: dict[str, Any] | None = None
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                symbol = str(row.get("symbol_normalized") or row.get("symbol") or "").strip().upper()
                price = _safe_float(row.get("price"))
                if symbol != reference or price is None or price <= 0:
                    continue
                last_match = {
                    "session_date": self._row_file_date(path),
                    "captured_at": str(row.get("captured_at") or "").strip() or None,
                    "price": price,
                    "source": "market_screen_rows",
                }
        return last_match

    def _read_latest_live_tick(self, reference_symbol: str) -> dict[str, Any] | None:
        latest_path = Path(self._market_screen_latest_path)
        reference = reference_symbol.upper().strip()
        if latest_path.exists():
            try:
                payload = json.loads(latest_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}
            captured_at = str(payload.get("captured_at") or "").strip() or None
            for row in payload.get("rows") or []:
                symbol = str(row.get("symbol") or "").strip().upper()
                price = _safe_float(row.get("price"))
                if symbol == reference and price is not None and price > 0:
                    session_date = None
                    parsed = _parse_iso(captured_at)
                    if parsed is not None:
                        session_date = parsed.astimezone(_BRT).strftime("%Y-%m-%d")
                    return {
                        "session_date": session_date or _today(),
                        "captured_at": captured_at,
                        "price": price,
                        "source": "market_screen_latest",
                    }

        today_path = Path(self._market_screen_rows_dir) / f"{_today()}.csv"
        return self._last_session_price(today_path, reference_symbol)

    def _sync_recent_reference_prices(
        self,
        *,
        reference_symbol: str,
        target_date: str,
        lookback_days: int,
    ) -> tuple[list[dict], dict[str, Any] | None]:
        latest_by_date: dict[str, dict[str, Any]] = {}

        for path in self._recent_row_csv_paths(lookback_days):
            record = self._last_session_price(path, reference_symbol)
            session_date = str((record or {}).get("session_date") or "").strip()
            if record and session_date:
                latest_by_date[session_date] = record

        live_tick = self._read_latest_live_tick(reference_symbol)
        live_date = str((live_tick or {}).get("session_date") or "").strip()
        if live_tick and live_date:
            latest_by_date[live_date] = live_tick

        upserts = [
            {
                "date": session_date,
                "close": round(float(record["price"]), 6),
            }
            for session_date, record in sorted(latest_by_date.items())
            if record.get("price") is not None
        ]
        if upserts:
            self._store.upsert_prices(upserts)

        stored_window = self._store.load_prices(max(lookback_days + 2, 10))
        recent_closes = [
            {
                "date": str(item.get("date") or ""),
                "close": round(float(item.get("close")), 6),
            }
            for item in stored_window[-lookback_days:]
            if item.get("date") and item.get("close") is not None
        ]

        if not live_tick and target_date:
            today_record = next((item for item in recent_closes if item.get("date") == target_date), None)
            if today_record:
                live_tick = {
                    "session_date": target_date,
                    "captured_at": None,
                    "price": today_record.get("close"),
                    "source": "price_history",
                }

        return recent_closes, live_tick

    def _price_records_with_live_override(
        self,
        *,
        live_date: str | None,
        live_price: float | None,
        days: int = 756,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for item in self._store.load_prices(days):
            date = str(item.get("date") or "").strip()
            close = _safe_float(item.get("close"))
            if not date or close is None or close <= 0:
                continue
            records.append({"date": date, "close": close})

        if live_date and live_price is not None and live_price > 0:
            replaced = False
            for record in records:
                if record["date"] == live_date:
                    record["close"] = live_price
                    replaced = True
                    break
            if not replaced:
                records.append({"date": live_date, "close": live_price})

        records.sort(key=lambda item: item.get("date", ""))
        return records

    @staticmethod
    def _log_returns_from_prices(price_records: list[dict[str, Any]]) -> tuple[list[str], list[float]]:
        dates: list[str] = []
        returns: list[float] = []
        for index in range(1, len(price_records)):
            previous = _safe_float(price_records[index - 1].get("close"))
            current = _safe_float(price_records[index].get("close"))
            if previous is None or current is None or previous <= 0 or current <= 0:
                continue
            dates.append(str(price_records[index].get("date") or ""))
            returns.append(float(np.log(current / previous)))
        return dates, returns

    @staticmethod
    def _annualized_ewma_vol(
        returns: np.ndarray,
        *,
        periods_per_year: int,
        lam: float,
        seed_window: int,
    ) -> float | None:
        clean = np.asarray(returns, dtype=np.float64)
        clean = clean[np.isfinite(clean)]
        if clean.size < 2:
            return None

        window = min(int(seed_window), clean.size)
        variance = float(np.var(clean[-window:], ddof=1))
        variance = max(variance, 1e-12)
        for value in clean[-window:]:
            variance = lam * variance + (1.0 - lam) * float(value) ** 2
        return float(np.sqrt(max(variance, 1e-12) * periods_per_year))

    def _load_intraday_reference_prices(
        self,
        *,
        reference_symbol: str,
        session_date: str | None,
    ) -> list[dict[str, Any]]:
        target_date = str(session_date or _today()).strip() or _today()
        path = Path(self._market_screen_rows_dir) / f"{target_date}.csv"
        if not path.exists():
            return []

        reference = reference_symbol.upper().strip()
        last_by_bucket: dict[str, dict[str, Any]] = {}
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                symbol = str(row.get("symbol_normalized") or row.get("symbol") or "").strip().upper()
                price = _safe_float(row.get("price"))
                captured_at = _parse_iso(row.get("captured_at"))
                if symbol != reference or price is None or price <= 0 or captured_at is None:
                    continue
                bucket = captured_at.astimezone(_BRT).replace(second=0, microsecond=0)
                last_by_bucket[bucket.isoformat()] = {
                    "captured_at": captured_at.astimezone(_BRT).isoformat(),
                    "close": price,
                }

        rows = list(last_by_bucket.values())
        rows.sort(key=lambda item: item.get("captured_at") or "")
        return rows

    def _run_intraday_garch(self, *, reference_symbol: str, session_date: str | None) -> dict[str, Any]:
        intraday_records = self._load_intraday_reference_prices(
            reference_symbol=reference_symbol,
            session_date=session_date,
        )
        intraday_dates, intraday_returns = self._log_returns_from_prices(intraday_records)
        if not intraday_returns:
            return {
                "rv_garch_intraday": None,
                "intraday_mode": "no_microstructure_data",
                "intraday_obs": len(intraday_records),
                "intraday_window_bars": 0,
            }

        ret = np.array(intraday_returns[-_INTRADAY_GARCH_LOOKBACK_BARS:], dtype=np.float64)
        n = len(ret)
        ewma_sigma = self._annualized_ewma_vol(
            ret,
            periods_per_year=_INTRADAY_PERIODS_PER_YEAR,
            lam=0.97,
            seed_window=min(60, max(n, 2)),
        )
        if n < 30:
            return {
                "rv_garch_intraday": round(ewma_sigma, 6) if ewma_sigma is not None else None,
                "intraday_mode": "ewma_micro_short",
                "intraday_obs": len(intraday_records),
                "intraday_window_bars": n,
                "intraday_dates": intraday_dates[-min(n, 5):],
            }

        try:
            params: GarchGedParams = fit_garch_ged(ret)
            eps = ret - params.mu
            history_len = len(ret)
            unconditional = params.omega / max(1 - params.alpha - params.beta, 1e-8)
            variance = np.full(history_len, unconditional)
            for index in range(1, history_len):
                variance[index] = (
                    params.omega
                    + params.alpha * eps[index - 1] ** 2
                    + params.beta * variance[index - 1]
                )

            forecast = forecast_garch_ged(
                params=params,
                last_epsilon=float(eps[-1]),
                last_variance=float(variance[-1]),
                horizon=_INTRADAY_GARCH_FORECAST_BARS,
                tdays_year=_INTRADAY_PERIODS_PER_YEAR,
            )
            return {
                "rv_garch_intraday": round(forecast.sigma_N, 6),
                "intraday_mode": "garch_ged_micro",
                "intraday_obs": len(intraday_records),
                "intraday_window_bars": n,
                "intraday_dates": intraday_dates[-min(n, 5):],
            }
        except Exception as exc:
            logger.warning("[VolIndex:%s] intraday GARCH fit error: %s", self.underlying, exc)
            return {
                "rv_garch_intraday": round(ewma_sigma, 6) if ewma_sigma is not None else None,
                "intraday_mode": "ewma_micro_fallback",
                "intraday_obs": len(intraday_records),
                "intraday_window_bars": n,
                "intraday_dates": intraday_dates[-min(n, 5):],
                "intraday_error": str(exc),
            }

    def _run_daily_garch(self, returns: np.ndarray) -> dict[str, Any]:
        ret = np.asarray(returns, dtype=np.float64)
        ret = ret[np.isfinite(ret)]
        n = len(ret)

        rv_simple_21d = None
        rv_live_5d = None
        rv_live_3d = None
        if n >= 2:
            rv_simple_21d = round(realized_vol_simple(ret, window=21), 6)
            rv_live_5d = round(realized_vol_simple(ret, window=min(5, n)), 6)
            rv_live_3d = round(realized_vol_simple(ret, window=min(3, n)), 6)

        ewma_sigma = self._annualized_ewma_vol(
            ret,
            periods_per_year=252,
            lam=0.94,
            seed_window=min(_DAILY_GARCH_SHORT_WINDOW, max(n, 2)),
        )
        fallback_value = round(ewma_sigma, 6) if ewma_sigma is not None else (rv_live_5d or rv_simple_21d or rv_live_3d)

        if n < 30:
            return {
                "rv_garch_5d": fallback_value,
                "rv_garch_30d": fallback_value,
                "rv_simple_21d": rv_simple_21d,
                "rv_live_5d": rv_live_5d,
                "rv_live_3d": rv_live_3d,
                "mode": "ewma_short_daily",
            }

        try:
            params: GarchGedParams = fit_garch_ged(ret)

            eps = ret - params.mu
            history_len = len(ret)
            unconditional = params.omega / max(1 - params.alpha - params.beta, 1e-8)
            variance = np.full(history_len, unconditional)
            for index in range(1, history_len):
                variance[index] = (
                    params.omega
                    + params.alpha * eps[index - 1] ** 2
                    + params.beta * variance[index - 1]
                )

            forecast_5d = forecast_garch_ged(
                params=params,
                last_epsilon=float(eps[-1]),
                last_variance=float(variance[-1]),
                horizon=5,
            )
            forecast_30d = forecast_garch_ged(
                params=params,
                last_epsilon=float(eps[-1]),
                last_variance=float(variance[-1]),
                horizon=30,
            )

            return {
                "rv_garch_5d": round(forecast_5d.sigma_N, 6),
                "rv_garch_30d": round(forecast_30d.sigma_30d, 6),
                "rv_simple_21d": rv_simple_21d,
                "rv_live_5d": rv_live_5d,
                "rv_live_3d": rv_live_3d,
                "alpha": round(params.alpha, 6),
                "beta": round(params.beta, 6),
                "nu": round(params.nu, 4),
                "persistence": round(params.persistence, 6),
                "converged": params.converged,
                "mode": "garch_ged_daily",
            }
        except Exception as exc:
            logger.warning("[VolIndex:%s] GARCH fit error: %s", self.underlying, exc)
            return {
                "rv_garch_5d": fallback_value,
                "rv_garch_30d": fallback_value,
                "rv_simple_21d": rv_simple_21d,
                "rv_live_5d": rv_live_5d,
                "rv_live_3d": rv_live_3d,
                "mode": "ewma_daily_fallback",
                "garch_error": str(exc),
            }

    def _run_garch(self, *, live_date: str | None, live_price: float | None) -> dict[str, Any]:
        price_records = self._price_records_with_live_override(live_date=live_date, live_price=live_price)
        price_dates, returns = self._log_returns_from_prices(price_records)
        ret = np.array(returns, dtype=np.float64)
        daily_metrics = self._run_daily_garch(ret)
        intraday_metrics = self._run_intraday_garch(
            reference_symbol=self._reference_symbol(),
            session_date=live_date,
        )

        merged = {
            **daily_metrics,
            **intraday_metrics,
            "n_obs": len(price_records),
            "price_dates": price_dates[-5:],
        }
        return merged
