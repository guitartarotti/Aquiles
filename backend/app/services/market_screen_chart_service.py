from __future__ import annotations

import csv
import json
import math
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from ..config import DEFAULT_MACRO_BLOOMBERG_REFERENCE_ASSETS, Config
from ..utils.logger import get_logger
from .market_screen_history_store import MarketScreenHistoryStore

logger = get_logger("mirofish.market_screen_chart")

DEFAULT_BENCHMARK_SYMBOL = "XB1"
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
DEFAULT_LOOKBACK_MINUTES = 360
DEFAULT_ROLLING_WINDOW_POINTS = 60
DEFAULT_MAX_POINTS = 1200
DEFAULT_PREFERRED_SYMBOLS = (
    "IBOV",
    "SCOA",
    "CLA",
    "DXY",
    "VIX",
    "MOVE",
    "WD01",
    "USGG2YR",
    "USGG10YR",
    "USSO2",
    "USSO10",
    "ODF27",
    "ODF28",
    "ODF29",
    "ODF30",
)
ASSET_SUFFIX_TOKENS = {"INDEX", "COMDTY", "EQUITY", "CURNCY", "CORP"}
OCR_TRAILING_NOISE_TOKENS = {"D"}
DEFAULT_W32_EXTRA_CANONICAL_SYMBOLS = (
    "ODF27",
    "ODF28",
    "ODF29",
    "ODF30",
    "ODF31",
    "ODF32",
    "ODF33",
    "ODF35",
    "USSO1",
    "USSO2",
    "USSO5",
    "USSO10",
)


def _safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _parse_iso_utc(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _split_security_candidates(raw_value: Any) -> list[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    for separator in ("|", ";"):
        text = text.replace(separator, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _normalize_symbol_token(token: Any) -> str:
    text = " ".join(str(token or "").upper().split()).strip()
    text = re.sub(r"[^A-Z0-9. ]+", " ", text)
    parts = [part for part in text.split() if part]
    while parts and parts[-1] in ASSET_SUFFIX_TOKENS.union(OCR_TRAILING_NOISE_TOKENS):
        parts.pop()
    return " ".join(parts).strip()


def _display_symbol_from_security(value: Any) -> str:
    return _normalize_symbol_token(value)


def _contextual_ocr_token_fix(token: Any) -> str:
    text = str(token or "").strip().upper()
    if not text:
        return ""

    core = text[1:] if text.startswith(".") else text
    if core.startswith("0") and len(core) >= 2 and core[1].isalpha():
        core = f"O{core[1:]}"

    chars = list(core)
    for index, char in enumerate(chars):
        if char != "0":
            continue
        previous_char = chars[index - 1] if index > 0 else ""
        next_char = chars[index + 1] if index + 1 < len(chars) else ""
        if previous_char.isalpha() and next_char.isalpha():
            chars[index] = "O"

    core = "".join(chars)
    if len(core) >= 3 and core.endswith("0") and core[-2].isalpha():
        core = f"{core[:-1]}O"

    if text.startswith("."):
        return f".{core}"
    return core


def _contextual_ocr_symbol_fix(value: Any) -> str:
    parts = [part for part in " ".join(str(value or "").upper().split()).split() if part]
    if not parts:
        return ""
    if len(parts) > 1 and parts[-1] in OCR_TRAILING_NOISE_TOKENS:
        parts = parts[:-1]
    fixed_parts = [_contextual_ocr_token_fix(part) for part in parts]
    return " ".join(part for part in fixed_parts if part).strip()


def _ocr_symbol_variant(value: str) -> str:
    return str(value or "").translate(str.maketrans({
        "0": "O",
        "1": "I",
        "5": "S",
    }))


def _security_match_variants(value: Any) -> set[str]:
    base = _normalize_symbol_token(value)
    if not base:
        return set()

    variants: set[str] = set()
    queue_values = [base]

    for item in queue_values:
        cleaned = " ".join(str(item or "").split()).strip()
        if not cleaned:
            continue
        variants.add(cleaned)
        compact = re.sub(r"[^A-Z0-9]", "", cleaned)
        if compact:
            variants.add(compact)
            variants.add(_ocr_symbol_variant(compact))
        translated = _ocr_symbol_variant(cleaned)
        if translated:
            variants.add(translated)

    return {item for item in variants if item}


class MarketScreenChartService:
    def __init__(self, root_dir: str | None = None) -> None:
        self.root_dir = os.path.abspath(
            root_dir or os.path.join(Config.OPTIONS_DATA_DIR, "market_screen_capture")
        )
        self.rows_dir = os.path.join(self.root_dir, "rows")
        self.history_store = MarketScreenHistoryStore(root_dir=self.root_dir)
        self._canonical_lookup = self._build_canonical_lookup()
        self._cache_lock = threading.RLock()
        self._frame_cache: dict[tuple[Any, ...], pd.DataFrame] = {}
        self._analysis_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._payload_cache: dict[tuple[Any, ...], dict[str, Any]] = {}

    def _row_file_paths(self) -> list[str]:
        if not os.path.isdir(self.rows_dir):
            return []
        csv_paths = [
            os.path.join(self.rows_dir, name)
            for name in os.listdir(self.rows_dir)
            if name.lower().endswith(".csv")
        ]
        if csv_paths:
            return sorted(csv_paths)
        paths = [
            os.path.join(self.rows_dir, name)
            for name in os.listdir(self.rows_dir)
            if name.lower().endswith(".jsonl")
        ]
        return sorted(paths)

    @staticmethod
    def _row_file_date(path: str) -> datetime.date | None:
        base_name = os.path.basename(path)
        raw_date = os.path.splitext(base_name)[0][:10]
        try:
            return datetime.strptime(raw_date, "%Y-%m-%d").date()
        except Exception:
            return None

    @staticmethod
    def _normalize_symbol(value: Any) -> str:
        return " ".join(str(value or "").upper().split()).strip()

    def _expected_reference_securities(self) -> list[str]:
        expected: list[str] = []
        seen: set[str] = set()

        def add_security(value: Any) -> None:
            for candidate in _split_security_candidates(value):
                normalized = self._normalize_symbol(candidate)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    expected.append(candidate)

        for item in DEFAULT_MACRO_BLOOMBERG_REFERENCE_ASSETS:
            add_security(item.get("security"))
        for security in getattr(Config, "MACRO_BLOOMBERG_REFERENCE_SECURITIES", []) or []:
            add_security(security)
        for mapping_name in (
            "OPTIONS_MODEL_SPOT_SECURITY_MAP",
            "OPTIONS_MODEL_FORWARD_SECURITY_MAP",
            "OPTIONS_MODEL_DIVIDEND_SECURITY_MAP",
        ):
            for mapped_value in (getattr(Config, mapping_name, {}) or {}).values():
                add_security(mapped_value)

        try:
            from .options_fair_value_modeling.factor_definitions import DEFAULT_FACTOR_DEFINITIONS

            for definition in DEFAULT_FACTOR_DEFINITIONS:
                if str(definition.get("source_kind") or "").strip().lower() != "reference_asset":
                    continue
                add_security(definition.get("source_key"))
        except Exception:
            logger.debug("Failed to load factor definitions for chart symbol matching", exc_info=True)

        return expected

    def _canonical_display_symbols(self) -> list[str]:
        symbols: list[str] = []
        seen: set[str] = set()

        def add_symbol(value: Any) -> None:
            symbol = _display_symbol_from_security(value)
            normalized = self._normalize_symbol(symbol)
            if normalized and normalized not in seen:
                seen.add(normalized)
                symbols.append(symbol)

        for security in self._expected_reference_securities():
            add_symbol(security)
        for symbol in DEFAULT_W32_EXTRA_CANONICAL_SYMBOLS:
            add_symbol(symbol)
        for symbol in getattr(Config, "MARKET_SCREEN_W32_CANONICAL_SYMBOLS_EXTRA", []) or []:
            add_symbol(symbol)
        return symbols

    def _build_canonical_lookup(self) -> dict[str, list[str]]:
        lookup: dict[str, list[str]] = {}
        for symbol in self._canonical_display_symbols():
            for variant in _security_match_variants(symbol):
                lookup.setdefault(variant, [])
                if symbol not in lookup[variant]:
                    lookup[variant].append(symbol)
        return lookup

    def _resolve_symbol(self, value: Any) -> str:
        raw_symbol = self._normalize_symbol(value)
        if not raw_symbol:
            return ""

        contextual_symbol = _contextual_ocr_symbol_fix(raw_symbol) or raw_symbol
        variants = _security_match_variants(contextual_symbol)
        for variant in variants:
            matches = self._canonical_lookup.get(variant) or []
            if len(matches) == 1:
                return matches[0]
            if matches:
                return sorted(matches, key=len)[0]
        return contextual_symbol

    @staticmethod
    def _downsample_points(points: list[dict[str, Any]], max_points: int) -> list[dict[str, Any]]:
        if max_points <= 0 or len(points) <= max_points:
            return points
        if max_points == 1:
            return [points[-1]]

        last_index = len(points) - 1
        sampled_indexes = {
            round(index * last_index / (max_points - 1))
            for index in range(max_points)
        }
        return [points[index] for index in sorted(sampled_indexes)]

    def _candidate_files(self, lookback_minutes: int) -> list[str]:
        file_paths = self._row_file_paths()
        if not file_paths:
            return []
        resolved_lookback = max(int(lookback_minutes), 1)
        cutoff_date = (datetime.now(timezone.utc) - timedelta(minutes=resolved_lookback)).date()
        selected_paths = [
            path for path in file_paths
            if (self._row_file_date(path) or cutoff_date) >= cutoff_date
        ]
        if selected_paths:
            return selected_paths
        days_needed = max(1, int(math.ceil(resolved_lookback / 1440.0)) + 1)
        return file_paths[-days_needed:]

    # Granularidade de mtime para o cache: o CSV é atualizado a cada captura (5-10 s),
    # então usar nanosegundos exatos invalida o cache em cada escrita.
    # Arredondamos para 30 s — o chart fica "ao vivo" sem re-ler 50-100 MB a cada request.
    _SIGNATURE_MTIME_GRANULARITY_NS: int = 30 * 10 ** 9

    def _history_signature(self, lookback_minutes: int) -> tuple[Any, ...]:
        signature: list[Any] = [int(max(lookback_minutes, 1))]
        gran = self._SIGNATURE_MTIME_GRANULARITY_NS
        for path in self._candidate_files(lookback_minutes):
            try:
                stat = os.stat(path)
            except OSError:
                continue
            # Arredonda mtime para bucket de 30 s → cache permanece válido
            # entre capturas consecutivas dentro da mesma janela.
            rounded_mtime = int(stat.st_mtime_ns) // gran
            signature.append((path, rounded_mtime, int(stat.st_size)))
        return tuple(signature)

    def _prune_cache(self, cache: dict[tuple[Any, ...], Any], max_entries: int = 12) -> None:
        while len(cache) > max_entries:
            oldest_key = next(iter(cache))
            cache.pop(oldest_key, None)

    def _resolve_symbol_cached(self, value: Any, cache: dict[str, str]) -> str:
        key = self._normalize_symbol(value)
        if not key:
            return ""
        cached = cache.get(key)
        if cached is not None:
            return cached
        resolved = self._resolve_symbol(value)
        cache[key] = resolved
        return resolved

    @staticmethod
    def _clone_asset(item: dict[str, Any] | None) -> dict[str, Any] | None:
        if not item:
            return None
        return dict(item)

    def _load_history_frame(self, lookback_minutes: int) -> pd.DataFrame:
        resolved_lookback = max(int(lookback_minutes), 1)
        signature = self._history_signature(resolved_lookback)
        with self._cache_lock:
            cached = self._frame_cache.get(signature)
            if cached is not None:
                return cached.copy()

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=resolved_lookback)
        frames: list[pd.DataFrame] = []
        symbol_cache: dict[str, str] = {}

        for path in self._candidate_files(resolved_lookback):
            try:
                if path.lower().endswith(".csv"):
                    raw_frame = pd.read_csv(
                        path,
                        usecols=[
                            "capture_id",
                            "captured_at",
                            "symbol",
                            "symbol_normalized",
                            "price",
                            "daily_change_pct",
                        ],
                    )
                    if raw_frame.empty:
                        continue

                    raw_frame["captured_at"] = pd.to_datetime(raw_frame["captured_at"], utc=True, errors="coerce")
                    raw_frame = raw_frame[raw_frame["captured_at"].notna()]
                    if raw_frame.empty:
                        continue

                    raw_frame = raw_frame[raw_frame["captured_at"] >= cutoff]
                    if raw_frame.empty:
                        continue

                    symbol_normalized = raw_frame.get("symbol_normalized")
                    symbol_source = symbol_normalized.fillna("").astype(str).str.strip() if symbol_normalized is not None else ""
                    if isinstance(symbol_source, str):
                        symbol_source = raw_frame["symbol"].fillna("").astype(str).str.strip()
                    else:
                        fallback_symbol = raw_frame["symbol"].fillna("").astype(str).str.strip()
                        symbol_source = symbol_source.where(symbol_source != "", fallback_symbol)

                    normalized_frame = pd.DataFrame(
                        {
                            "capture_id": raw_frame["capture_id"].astype(str).str.strip(),
                            "captured_at": raw_frame["captured_at"],
                            "symbol": symbol_source.map(lambda value: self._resolve_symbol_cached(value, symbol_cache)),
                            "price": pd.to_numeric(raw_frame["price"], errors="coerce"),
                            "daily_change_pct": pd.to_numeric(raw_frame["daily_change_pct"], errors="coerce"),
                        }
                    )
                    normalized_frame = normalized_frame[
                        normalized_frame["symbol"].astype(str).str.strip().ne("")
                        & normalized_frame["price"].notna()
                    ]
                    if not normalized_frame.empty:
                        frames.append(normalized_frame)
                    continue

                with open(path, "r", encoding="utf-8") as handle:
                    records: list[dict[str, Any]] = []
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except Exception:
                            continue

                        captured_at = _parse_iso_utc(payload.get("captured_at"))
                        if captured_at is None or captured_at < cutoff:
                            continue

                        symbol = self._resolve_symbol_cached(payload.get("symbol_normalized") or payload.get("symbol"), symbol_cache)
                        price = _safe_float(payload.get("price"))
                        if not symbol or price is None:
                            continue

                        records.append(
                            {
                                "capture_id": str(payload.get("capture_id") or "").strip(),
                                "captured_at": captured_at,
                                "symbol": symbol,
                                "price": price,
                                "daily_change_pct": _safe_float(payload.get("daily_change_pct")),
                            }
                        )
                    if records:
                        frames.append(pd.DataFrame.from_records(records))
            except Exception:
                logger.exception("Failed to read market screen history file: %s", path)

        if not frames:
            empty_frame = pd.DataFrame(
                columns=["capture_id", "captured_at", "symbol", "price", "daily_change_pct"]
            )
            with self._cache_lock:
                self._frame_cache[signature] = empty_frame
                self._prune_cache(self._frame_cache)
            return empty_frame.copy()

        frame = pd.concat(frames, ignore_index=True)
        if frame.empty:
            with self._cache_lock:
                self._frame_cache[signature] = frame
                self._prune_cache(self._frame_cache)
            return frame.copy()

        frame = frame.sort_values(["captured_at", "symbol", "capture_id"]).drop_duplicates(
            subset=["captured_at", "symbol"],
            keep="last",
        )
        normalized_frame = frame.reset_index(drop=True)
        with self._cache_lock:
            self._frame_cache[signature] = normalized_frame
            self._prune_cache(self._frame_cache)
        return normalized_frame.copy()

    def _load_benchmark_history_frame_from_store(
        self,
        *,
        lookback_minutes: int,
        benchmark_symbol: str,
    ) -> tuple[pd.DataFrame, datetime | None] | None:
        if not bool(getattr(Config, "MARKET_SCREEN_W32_HISTORY_DB_ENABLE", True)):
            return None

        resolved_lookback = max(int(lookback_minutes), 1)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=resolved_lookback)
        try:
            candidate_paths = [
                path for path in self._candidate_files(resolved_lookback)
                if path.lower().endswith(".csv")
            ]
            sync_symbols = {benchmark_symbol, *_security_match_variants(benchmark_symbol)}
            self.history_store.sync_csv_files(
                candidate_paths,
                needed_symbols=sync_symbols,
            )
            records = self.history_store.query_symbols_history(
                sync_symbols,
                since=cutoff,
            )
        except Exception:
            logger.exception("Failed to load benchmark history from SQLite; falling back to CSV")
            return None

        if not records:
            return None

        frame = pd.DataFrame.from_records(records)
        frame["captured_at"] = pd.to_datetime(frame["captured_at"], utc=True, errors="coerce")
        frame = frame[frame["captured_at"].notna()]
        if frame.empty:
            return None
        symbol_cache: dict[str, str] = {}
        frame["symbol"] = frame["symbol"].map(
            lambda value: self._resolve_symbol_cached(value, symbol_cache)
        )
        frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
        frame["daily_change_pct"] = pd.to_numeric(frame["daily_change_pct"], errors="coerce")
        frame = frame[
            frame["symbol"].astype(str).str.strip().eq(benchmark_symbol)
            & frame["price"].notna()
        ]
        if frame.empty:
            return None

        frame = frame.sort_values(["captured_at", "capture_id"]).drop_duplicates(
            subset=["captured_at", "symbol"],
            keep="last",
        )
        latest_capture_at = frame["captured_at"].max()
        latest_dt = (
            latest_capture_at.to_pydatetime()
            if hasattr(latest_capture_at, "to_pydatetime")
            else latest_capture_at
        )
        return frame.reset_index(drop=True), latest_dt if isinstance(latest_dt, datetime) else None

    def _load_benchmark_candles_from_store(
        self,
        *,
        lookback_minutes: int,
        benchmark_symbol: str,
        bar_minutes: int,
        max_points: int,
    ) -> tuple[list[dict[str, Any]], datetime | None] | None:
        if not bool(getattr(Config, "MARKET_SCREEN_W32_HISTORY_DB_ENABLE", True)):
            return None

        resolved_lookback = max(int(lookback_minutes), 1)
        resolved_bar_minutes = max(int(bar_minutes), 1)
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=resolved_lookback)
        try:
            records = self.history_store.query_symbol_candles(
                benchmark_symbol,
                bar_minutes=resolved_bar_minutes,
                since=cutoff,
            )
            if not records:
                candidate_paths = [
                    path for path in self._candidate_files(resolved_lookback)
                    if path.lower().endswith(".csv")
                ]
                sync_symbols = {benchmark_symbol, *_security_match_variants(benchmark_symbol)}
                self.history_store.sync_csv_files(
                    candidate_paths,
                    needed_symbols=sync_symbols,
                )
                self.history_store.ensure_candles_for_symbols(
                    {benchmark_symbol},
                    bar_minutes=resolved_bar_minutes,
                    since=cutoff,
                )
                records = self.history_store.query_symbol_candles(
                    benchmark_symbol,
                    bar_minutes=resolved_bar_minutes,
                    since=cutoff,
                )
        except Exception:
            logger.exception("Failed to load benchmark candles from SQLite")
            return None

        if not records:
            return None

        latest_capture_at: datetime | None = None
        candles: list[dict[str, Any]] = []
        for row in records:
            bucket_epoch = _safe_float(row.get("bucket_epoch"))
            last_epoch = _safe_float(row.get("last_capture_at_epoch"))
            if bucket_epoch is None:
                continue
            local_bucket = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc).astimezone(LOCAL_TZ)
            local_minutes = (local_bucket.hour * 60) + local_bucket.minute
            if local_minutes < 9 * 60 or local_minutes > 18 * 60:
                continue
            if last_epoch is not None:
                last_dt = datetime.fromtimestamp(last_epoch, tz=timezone.utc)
                if latest_capture_at is None or last_dt > latest_capture_at:
                    latest_capture_at = last_dt
            candles.append(
                {
                    "timestamp": row.get("bucket_at"),
                    "timestamp_ms": int(bucket_epoch * 1000),
                    "open": _safe_float(row.get("open")),
                    "high": _safe_float(row.get("high")),
                    "low": _safe_float(row.get("low")),
                    "close": _safe_float(row.get("close")),
                    "price": _safe_float(row.get("close")),
                    "daily_change_pct": _safe_float(row.get("daily_change_pct")),
                    "sample_count": int(row.get("sample_count") or 0),
                    "bar_minutes": resolved_bar_minutes,
                }
            )
        return self._downsample_points(candles, max_points), latest_capture_at

    def _load_benchmark_history_frame(
        self,
        *,
        lookback_minutes: int,
        benchmark_symbol: str,
    ) -> tuple[pd.DataFrame, datetime | None]:
        resolved_lookback = max(int(lookback_minutes), 1)
        store_result = self._load_benchmark_history_frame_from_store(
            lookback_minutes=resolved_lookback,
            benchmark_symbol=benchmark_symbol,
        )
        if store_result is not None:
            return store_result

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=resolved_lookback)
        symbol_cache: dict[str, str] = {}
        records: list[dict[str, Any]] = []
        latest_capture_at: datetime | None = None

        for path in self._candidate_files(resolved_lookback):
            try:
                if path.lower().endswith(".csv"):
                    with open(path, "r", encoding="utf-8", errors="replace", newline="") as handle:
                        reader = csv.DictReader(handle)
                        for row in reader:
                            captured_at = _parse_iso_utc(row.get("captured_at"))
                            if captured_at is None or captured_at < cutoff:
                                continue

                            resolved_symbol = self._resolve_symbol_cached(
                                row.get("symbol_normalized") or row.get("symbol") or row.get("symbol_raw"),
                                symbol_cache,
                            )
                            if resolved_symbol != benchmark_symbol:
                                continue

                            price = _safe_float(row.get("price"))
                            if price is None:
                                continue

                            records.append(
                                {
                                    "capture_id": str(row.get("capture_id") or "").strip(),
                                    "captured_at": captured_at,
                                    "symbol": resolved_symbol,
                                    "price": price,
                                    "daily_change_pct": _safe_float(row.get("daily_change_pct")),
                                }
                            )
                            if latest_capture_at is None or captured_at > latest_capture_at:
                                latest_capture_at = captured_at
                    continue

                with open(path, "r", encoding="utf-8") as handle:
                    for raw_line in handle:
                        line = raw_line.strip()
                        if not line:
                            continue
                        try:
                            payload = json.loads(line)
                        except Exception:
                            continue

                        captured_at = _parse_iso_utc(payload.get("captured_at"))
                        if captured_at is None or captured_at < cutoff:
                            continue

                        resolved_symbol = self._resolve_symbol_cached(
                            payload.get("symbol_normalized") or payload.get("symbol"),
                            symbol_cache,
                        )
                        if resolved_symbol != benchmark_symbol:
                            continue

                        price = _safe_float(payload.get("price"))
                        if price is None:
                            continue

                        records.append(
                            {
                                "capture_id": str(payload.get("capture_id") or "").strip(),
                                "captured_at": captured_at,
                                "symbol": resolved_symbol,
                                "price": price,
                                "daily_change_pct": _safe_float(payload.get("daily_change_pct")),
                            }
                        )
                        if latest_capture_at is None or captured_at > latest_capture_at:
                            latest_capture_at = captured_at
            except Exception:
                logger.exception("Failed to read benchmark-only market screen history file: %s", path)

        if not records:
            return (
                pd.DataFrame(
                    columns=["capture_id", "captured_at", "symbol", "price", "daily_change_pct"]
                ),
                latest_capture_at,
            )

        frame = pd.DataFrame.from_records(records)
        frame = frame.sort_values(["captured_at", "capture_id"]).drop_duplicates(
            subset=["captured_at", "symbol"],
            keep="last",
        )
        return frame.reset_index(drop=True), latest_capture_at

    @staticmethod
    def _default_symbol(symbols: list[str], benchmark_symbol: str) -> str | None:
        symbol_set = set(symbols)
        for symbol in DEFAULT_PREFERRED_SYMBOLS:
            if symbol != benchmark_symbol and symbol in symbol_set:
                return symbol
        for symbol in symbols:
            if symbol != benchmark_symbol:
                return symbol
        return benchmark_symbol if benchmark_symbol in symbol_set else (symbols[0] if symbols else None)

    @staticmethod
    def _latest_rolling_corr(
        left_series: pd.Series,
        right_series: pd.Series,
        window_points: int,
    ) -> float | None:
        paired = pd.concat([left_series, right_series], axis=1).dropna()
        if paired.empty:
            return None
        paired.columns = ["left_value", "right_value"]
        paired = paired.diff().dropna()
        if paired.empty:
            return None

        resolved_window = max(int(window_points), 4)
        min_points = max(6, min(resolved_window, 12))
        corr_series = paired["left_value"].rolling(
            resolved_window,
            min_periods=min_points,
        ).corr(paired["right_value"])
        valid = corr_series.dropna()
        if valid.empty:
            return None
        return _safe_float(valid.iloc[-1])

    def _build_assets_payload(
        self,
        *,
        frame: pd.DataFrame,
        benchmark_symbol: str,
        rolling_window_points: int,
        selected_symbol: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if frame.empty:
            return [], None

        latest_rows = (
            frame.sort_values("captured_at")
            .groupby("symbol", as_index=False)
            .tail(1)
            .set_index("symbol", drop=False)
        )
        sample_counts = frame.groupby("symbol")["captured_at"].nunique().to_dict()
        price_pivot = frame.pivot_table(
            index="captured_at",
            columns="symbol",
            values="price",
            aggfunc="last",
        ).sort_index()

        symbols = [str(symbol) for symbol in price_pivot.columns.tolist()]
        resolved_default = self._default_symbol(symbols, benchmark_symbol)
        resolved_selected = selected_symbol if selected_symbol in symbols else resolved_default
        benchmark_present = benchmark_symbol in price_pivot.columns

        assets: list[dict[str, Any]] = []
        for symbol in symbols:
            latest_row = latest_rows.loc[symbol]
            latest_corr = None
            if benchmark_present:
                if symbol == benchmark_symbol:
                    latest_corr = 1.0
                else:
                    latest_corr = self._latest_rolling_corr(
                        price_pivot.get(symbol, pd.Series(dtype="float64")),
                        price_pivot.get(benchmark_symbol, pd.Series(dtype="float64")),
                        rolling_window_points,
                    )

            assets.append(
                {
                    "symbol": symbol,
                    "is_benchmark": symbol == benchmark_symbol,
                    "selected": symbol == resolved_selected,
                    "latest_price": _safe_float(latest_row.get("price")),
                    "latest_daily_change_pct": _safe_float(latest_row.get("daily_change_pct")),
                    "latest_timestamp": latest_row.get("captured_at").isoformat()
                    if isinstance(latest_row.get("captured_at"), datetime)
                    else None,
                    "sample_count": int(sample_counts.get(symbol) or 0),
                    "latest_pearson_vs_xb1": latest_corr,
                }
            )

        preferred_rank = {
            symbol: index
            for index, symbol in enumerate((benchmark_symbol, *DEFAULT_PREFERRED_SYMBOLS))
        }
        assets.sort(
            key=lambda item: (
                preferred_rank.get(item["symbol"], 999),
                -abs(_safe_float(item.get("latest_pearson_vs_xb1")) or 0.0),
                -int(item.get("sample_count") or 0),
                str(item.get("symbol") or ""),
            )
        )
        return assets, resolved_selected

    def _analysis_cache_key(
        self,
        *,
        benchmark_symbol: str,
        lookback_minutes: int,
        rolling_window_points: int,
        max_points: int,
        history_signature: tuple[Any, ...],
    ) -> tuple[Any, ...]:
        return (
            benchmark_symbol,
            int(lookback_minutes),
            int(rolling_window_points),
            int(max_points),
            history_signature,
        )

    def _build_analysis_bundle(
        self,
        *,
        frame: pd.DataFrame,
        benchmark_symbol: str,
        rolling_window_points: int,
        max_points: int,
    ) -> dict[str, Any]:
        latest_rows = (
            frame.sort_values("captured_at")
            .groupby("symbol", as_index=False)
            .tail(1)
            .set_index("symbol", drop=False)
        )
        sample_counts = frame.groupby("symbol")["captured_at"].nunique().to_dict()
        price_pivot = frame.pivot_table(
            index="captured_at",
            columns="symbol",
            values="price",
            aggfunc="last",
        ).sort_index()
        symbol_frames = {
            str(symbol): symbol_frame.sort_values("captured_at").reset_index(drop=True)
            for symbol, symbol_frame in frame.groupby("symbol", sort=False)
        }

        symbols = [str(symbol) for symbol in price_pivot.columns.tolist()]
        resolved_default = self._default_symbol(symbols, benchmark_symbol)
        benchmark_present = benchmark_symbol in price_pivot.columns
        latest_corr_by_symbol: dict[str, float | None] = {}
        benchmark_series = price_pivot.get(benchmark_symbol, pd.Series(dtype="float64"))

        assets: list[dict[str, Any]] = []
        for symbol in symbols:
            latest_row = latest_rows.loc[symbol]
            latest_corr = None
            if benchmark_present:
                if symbol == benchmark_symbol:
                    latest_corr = 1.0
                else:
                    latest_corr = self._latest_rolling_corr(
                        price_pivot.get(symbol, pd.Series(dtype="float64")),
                        benchmark_series,
                        rolling_window_points,
                    )
            latest_corr_by_symbol[symbol] = latest_corr
            assets.append(
                {
                    "symbol": symbol,
                    "is_benchmark": symbol == benchmark_symbol,
                    "selected": symbol == resolved_default,
                    "latest_price": _safe_float(latest_row.get("price")),
                    "latest_daily_change_pct": _safe_float(latest_row.get("daily_change_pct")),
                    "latest_timestamp": latest_row.get("captured_at").isoformat()
                    if isinstance(latest_row.get("captured_at"), datetime)
                    else None,
                    "sample_count": int(sample_counts.get(symbol) or 0),
                    "latest_pearson_vs_xb1": latest_corr,
                }
            )

        preferred_rank = {
            symbol: index
            for index, symbol in enumerate((benchmark_symbol, *DEFAULT_PREFERRED_SYMBOLS))
        }
        assets.sort(
            key=lambda item: (
                preferred_rank.get(item["symbol"], 999),
                -abs(_safe_float(item.get("latest_pearson_vs_xb1")) or 0.0),
                -int(item.get("sample_count") or 0),
                str(item.get("symbol") or ""),
            )
        )

        benchmark_points = self._build_price_points(
            symbol_frames.get(benchmark_symbol, pd.DataFrame()),
            max_points,
        )
        latest_capture_at = frame["captured_at"].max()

        return {
            "assets": assets,
            "asset_map": {str(item["symbol"]): item for item in assets},
            "default_symbol": resolved_default,
            "latest_capture_at": latest_capture_at,
            "price_pivot": price_pivot,
            "symbol_frames": symbol_frames,
            "benchmark_points": benchmark_points,
            "price_points_cache": {
                benchmark_symbol: benchmark_points,
            } if benchmark_points else {},
            "pearson_points_cache": {},
        }

    @staticmethod
    def _build_price_points(symbol_frame: pd.DataFrame, max_points: int) -> list[dict[str, Any]]:
        if symbol_frame.empty:
            return []

        points: list[dict[str, Any]] = []
        previous_price: float | None = None

        for row in symbol_frame.sort_values("captured_at").itertuples(index=False):
            captured_at = getattr(row, "captured_at", None)
            price = _safe_float(getattr(row, "price", None))
            if not isinstance(captured_at, datetime) or price is None:
                continue

            open_price = previous_price if previous_price is not None else price
            points.append(
                {
                    "timestamp": captured_at.isoformat(),
                    "timestamp_ms": int(captured_at.timestamp() * 1000),
                    "open": open_price,
                    "high": max(open_price, price),
                    "low": min(open_price, price),
                    "close": price,
                    "price": price,
                    "daily_change_pct": _safe_float(getattr(row, "daily_change_pct", None)),
                }
            )
            previous_price = price

        return MarketScreenChartService._downsample_points(points, max_points)

    @staticmethod
    def _build_ohlc_points(
        symbol_frame: pd.DataFrame,
        max_points: int,
        bar_minutes: int,
    ) -> list[dict[str, Any]]:
        if symbol_frame.empty:
            return []

        frame = symbol_frame.copy()
        frame["captured_at"] = pd.to_datetime(frame["captured_at"], utc=True, errors="coerce")
        frame["price"] = pd.to_numeric(frame["price"], errors="coerce")
        frame["daily_change_pct"] = pd.to_numeric(frame.get("daily_change_pct"), errors="coerce")
        frame = frame[frame["captured_at"].notna() & frame["price"].notna()]
        if frame.empty:
            return []

        freq = f"{max(int(bar_minutes or 5), 1)}min"
        grouped = (
            frame.sort_values("captured_at")
            .assign(bucket=lambda item: item["captured_at"].dt.floor(freq))
            .groupby("bucket", as_index=False)
            .agg(
                open=("price", "first"),
                high=("price", "max"),
                low=("price", "min"),
                close=("price", "last"),
                daily_change_pct=("daily_change_pct", "last"),
                sample_count=("price", "count"),
            )
        )

        points: list[dict[str, Any]] = []
        for row in grouped.itertuples(index=False):
            bucket = getattr(row, "bucket", None)
            if not isinstance(bucket, datetime):
                continue
            close = _safe_float(getattr(row, "close", None))
            points.append(
                {
                    "timestamp": bucket.isoformat(),
                    "timestamp_ms": int(bucket.timestamp() * 1000),
                    "open": _safe_float(getattr(row, "open", None)),
                    "high": _safe_float(getattr(row, "high", None)),
                    "low": _safe_float(getattr(row, "low", None)),
                    "close": close,
                    "price": close,
                    "daily_change_pct": _safe_float(getattr(row, "daily_change_pct", None)),
                    "sample_count": int(getattr(row, "sample_count", 0) or 0),
                    "bar_minutes": max(int(bar_minutes or 5), 1),
                }
            )

        return MarketScreenChartService._downsample_points(points, max_points)

    @staticmethod
    def _build_pearson_points(
        *,
        paired_prices: pd.DataFrame,
        asset_symbol: str,
        benchmark_symbol: str,
        window_points: int,
        max_points: int,
    ) -> list[dict[str, Any]]:
        if paired_prices.empty or asset_symbol == benchmark_symbol:
            return []

        available_columns = {str(column) for column in paired_prices.columns.tolist()}
        if asset_symbol not in available_columns or benchmark_symbol not in available_columns:
            return []

        scoped = paired_prices[[asset_symbol, benchmark_symbol]].dropna()
        if scoped.empty:
            return []

        delta = scoped.diff().dropna()
        if delta.empty:
            return []

        resolved_window = max(int(window_points), 4)
        min_points = max(6, min(resolved_window, 12))
        corr_series = delta[asset_symbol].rolling(
            resolved_window,
            min_periods=min_points,
        ).corr(delta[benchmark_symbol])
        valid_corr = corr_series.dropna()
        if valid_corr.empty:
            return []

        points = [
            {
                "timestamp": timestamp.isoformat(),
                "timestamp_ms": int(timestamp.timestamp() * 1000),
                "value": round(float(value), 6),
                "window_points": resolved_window,
            }
            for timestamp, value in valid_corr.items()
            if isinstance(timestamp, datetime) and _safe_float(value) is not None
        ]
        return MarketScreenChartService._downsample_points(points, max_points)

    def build_payload(
        self,
        *,
        symbol: str | None = None,
        benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
        lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
        rolling_window_points: int = DEFAULT_ROLLING_WINDOW_POINTS,
        max_points: int = DEFAULT_MAX_POINTS,
        bar_minutes: int | None = None,
        include_assets: bool = True,
        benchmark_only: bool = False,
    ) -> dict[str, Any]:
        resolved_benchmark = self._resolve_symbol(benchmark_symbol) or DEFAULT_BENCHMARK_SYMBOL
        resolved_lookback = max(int(lookback_minutes or DEFAULT_LOOKBACK_MINUTES), 15)
        resolved_window = max(int(rolling_window_points or DEFAULT_ROLLING_WINDOW_POINTS), 4)
        resolved_max_points = max(int(max_points or DEFAULT_MAX_POINTS), 60)
        resolved_bar_minutes = max(int(bar_minutes or 0), 0)
        resolved_symbol = self._resolve_symbol(symbol)
        history_signature = self._history_signature(resolved_lookback)
        cache_key = (
            resolved_symbol,
            resolved_benchmark,
            resolved_lookback,
            resolved_window,
            resolved_max_points,
            resolved_bar_minutes,
            bool(include_assets),
            bool(benchmark_only),
            history_signature,
        )
        analysis_cache_key = self._analysis_cache_key(
            benchmark_symbol=resolved_benchmark,
            lookback_minutes=resolved_lookback,
            rolling_window_points=resolved_window,
            max_points=resolved_max_points,
            history_signature=history_signature,
        )
        with self._cache_lock:
            cached_payload = self._payload_cache.get(cache_key)
            if cached_payload is not None:
                payload = dict(cached_payload)
                payload["generated_at"] = datetime.now(timezone.utc).isoformat()
                return payload

        if benchmark_only and not resolved_symbol:
            benchmark_candles: list[dict[str, Any]] = []
            latest_capture_at: datetime | None = None
            benchmark_frame = pd.DataFrame()
            if resolved_bar_minutes > 0:
                candle_result = self._load_benchmark_candles_from_store(
                    lookback_minutes=resolved_lookback,
                    benchmark_symbol=resolved_benchmark,
                    bar_minutes=resolved_bar_minutes,
                    max_points=resolved_max_points,
                )
                if candle_result is not None:
                    benchmark_candles, latest_capture_at = candle_result

            if not benchmark_candles:
                benchmark_frame, latest_capture_at = self._load_benchmark_history_frame(
                    lookback_minutes=resolved_lookback,
                    benchmark_symbol=resolved_benchmark,
                )
                if resolved_bar_minutes > 0 and not benchmark_frame.empty:
                    benchmark_candles = self._build_ohlc_points(
                        benchmark_frame,
                        resolved_max_points,
                        resolved_bar_minutes,
                    )

            benchmark_points = [] if resolved_bar_minutes > 0 else self._build_price_points(
                benchmark_frame,
                resolved_max_points,
            )
            has_history = bool(benchmark_candles) or not benchmark_frame.empty
            payload = {
                "ok": has_history,
                "status": "ready" if has_history else "no_history",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "latest_capture_at": latest_capture_at.isoformat()
                if isinstance(latest_capture_at, datetime)
                else None,
                "benchmark_symbol": resolved_benchmark,
                "benchmark_available": has_history,
                "selected_symbol": resolved_benchmark,
                "default_symbol": resolved_benchmark,
                "lookback_minutes": resolved_lookback,
                "rolling_window_points": resolved_window,
                "bar_minutes": resolved_bar_minutes or None,
                "max_points": resolved_max_points,
                "asset_count": 1 if has_history else 0,
                "selected_asset": None,
                "benchmark_asset": None,
                "series": {
                    "price_points": [],
                    "pearson_points": [],
                    "benchmark_points": benchmark_points,
                    "benchmark_candles": benchmark_candles,
                },
            }
            with self._cache_lock:
                self._payload_cache[cache_key] = payload
                self._prune_cache(self._payload_cache, max_entries=24)
            return dict(payload)

        frame = self._load_history_frame(resolved_lookback)
        if frame.empty:
            payload = {
                "ok": False,
                "status": "no_history",
                "error": "market_screen_history_not_available",
                "benchmark_symbol": resolved_benchmark,
                "lookback_minutes": resolved_lookback,
                "rolling_window_points": resolved_window,
                "max_points": resolved_max_points,
                "assets": [],
                "series": {
                    "price_points": [],
                    "pearson_points": [],
                    "benchmark_points": [],
                },
            }
            with self._cache_lock:
                self._payload_cache[cache_key] = payload
                self._prune_cache(self._payload_cache, max_entries=24)
            return dict(payload)

        with self._cache_lock:
            analysis_bundle = self._analysis_cache.get(analysis_cache_key)
        if analysis_bundle is None:
            analysis_bundle = self._build_analysis_bundle(
                frame=frame,
                benchmark_symbol=resolved_benchmark,
                rolling_window_points=resolved_window,
                max_points=resolved_max_points,
            )
            with self._cache_lock:
                self._analysis_cache[analysis_cache_key] = analysis_bundle
                self._prune_cache(self._analysis_cache, max_entries=12)

        assets = analysis_bundle.get("assets") or []
        asset_map = analysis_bundle.get("asset_map") or {}
        symbols = list((analysis_bundle.get("symbol_frames") or {}).keys())
        benchmark_available = resolved_benchmark in set(symbols)
        resolved_default = analysis_bundle.get("default_symbol")
        resolved_selected = resolved_symbol if resolved_symbol in symbols else resolved_default
        if not resolved_selected:
            payload = {
                "ok": False,
                "status": "no_symbols",
                "error": "market_screen_history_has_no_symbols",
                "benchmark_symbol": resolved_benchmark,
                "lookback_minutes": resolved_lookback,
                "rolling_window_points": resolved_window,
                "max_points": resolved_max_points,
                "benchmark_available": benchmark_available,
                "assets": assets,
                "series": {
                    "price_points": [],
                    "pearson_points": [],
                    "benchmark_points": [],
                },
            }
            with self._cache_lock:
                self._payload_cache[cache_key] = payload
                self._prune_cache(self._payload_cache, max_entries=24)
            return dict(payload)

        price_points_cache = analysis_bundle.get("price_points_cache") or {}
        pearson_points_cache = analysis_bundle.get("pearson_points_cache") or {}
        symbol_frames = analysis_bundle.get("symbol_frames") or {}
        price_pivot = analysis_bundle.get("price_pivot")

        with self._cache_lock:
            price_points = price_points_cache.get(resolved_selected)
        if price_points is None:
            price_points = self._build_price_points(
                symbol_frames.get(resolved_selected, pd.DataFrame()),
                resolved_max_points,
            )
            with self._cache_lock:
                cache_bundle = self._analysis_cache.get(analysis_cache_key)
                if cache_bundle is not None:
                    cache_bundle.setdefault("price_points_cache", {})[resolved_selected] = price_points

        benchmark_points = analysis_bundle.get("benchmark_points") or []

        with self._cache_lock:
            pearson_points = pearson_points_cache.get(resolved_selected)
        if pearson_points is None:
            pearson_points = self._build_pearson_points(
                paired_prices=price_pivot,
                asset_symbol=resolved_selected,
                benchmark_symbol=resolved_benchmark,
                window_points=resolved_window,
                max_points=resolved_max_points,
            )
            with self._cache_lock:
                cache_bundle = self._analysis_cache.get(analysis_cache_key)
                if cache_bundle is not None:
                    cache_bundle.setdefault("pearson_points_cache", {})[resolved_selected] = pearson_points

        selected_asset = self._clone_asset(asset_map.get(resolved_selected))
        benchmark_asset = self._clone_asset(asset_map.get(resolved_benchmark))
        latest_capture_at = analysis_bundle.get("latest_capture_at")

        payload = {
            "ok": True,
            "status": "ready",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latest_capture_at": latest_capture_at.isoformat()
            if isinstance(latest_capture_at, datetime)
            else None,
            "benchmark_symbol": resolved_benchmark,
            "benchmark_available": benchmark_available,
            "selected_symbol": resolved_selected,
            "default_symbol": resolved_default,
            "lookback_minutes": resolved_lookback,
            "rolling_window_points": resolved_window,
            "max_points": resolved_max_points,
            "asset_count": len(assets),
            "selected_asset": selected_asset,
            "benchmark_asset": benchmark_asset,
            "series": {
                "price_points": price_points,
                "pearson_points": pearson_points,
                "benchmark_points": benchmark_points,
            },
        }
        if include_assets:
            payload["assets"] = assets
        with self._cache_lock:
            self._payload_cache[cache_key] = payload
            self._prune_cache(self._payload_cache, max_entries=24)
        return dict(payload)
