from __future__ import annotations

import asyncio
import csv
import ctypes
import hashlib
import json
import os
import queue
import re
import tempfile
import threading
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Optional

from PIL import Image, ImageOps

try:
    import win32api  # type: ignore
    import win32gui  # type: ignore
except ImportError:  # Windows-only integration; the read APIs remain portable.
    win32api = None
    win32gui = None

from ..config import DEFAULT_MACRO_BLOOMBERG_REFERENCE_ASSETS, Config
from ..utils.atomic_io import atomic_json_dump
from ..utils.logger import get_logger
from .market_screen_history_store import MarketScreenHistoryStore

logger = get_logger("mirofish.market_screen_capture")


def _capture_disabled_in_process() -> bool:
    return str(os.environ.get("AQUILES_DISABLE_MARKET_SCREEN_COLLECTOR", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


PRICE_HEADER_HINTS = ("ULT PREGO", "ULT PRECO", "LAST")
CHANGE_HEADER_HINTS = ("%1D", "%ID", "1D%")
ASSET_SUFFIX_TOKENS = {"INDEX", "COMDTY", "EQUITY", "CURNCY", "CORP"}
OCR_TRAILING_NOISE_TOKENS = {"D"}
DEFAULT_WINDOW_WORKBOOK_NAME = "W 32: Basica"
DEFAULT_WINDOW_WORKBOOK_URI = "screen://w32-basica"
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
ARROW_CHARS = "↑↓→←"


W32_HEADER_ROW_SYMBOLS = {
    "TICKER",
    "ULT PRECO",
    "ULT PREGO",
    "LAST",
    "%1D",
    "%ID",
    "1D%",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_clone(data: Any) -> Any:
    if data is None:
        return None
    return json.loads(json.dumps(data, ensure_ascii=False))


def _strip_accents(value: Any) -> str:
    text = str(value or "")
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _normalize_match_text(value: Any) -> str:
    text = _strip_accents(value).upper()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_security(value: Any) -> str:
    return " ".join(_normalize_match_text(value).split())


def _slugify(value: Any) -> str:
    text = _normalize_match_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "capture"


def _parse_iso_utc(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("%", "")
    text = text.replace(" ", "")
    text = text.translate(str.maketrans("", "", ARROW_CHARS))
    text = re.sub(r"[^0-9,.\-+]", "", text)
    while len(text) > 1 and text[-1] in ".,":
        text = text[:-1]
    if not text:
        return None

    if text.count(",") and text.count("."):
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif text.count(",") == 1 and text.count(".") == 0:
        text = text.replace(",", ".")
    elif text.count(".") > 1 and text.count(",") == 0:
        whole, decimal = text.rsplit(".", 1)
        text = whole.replace(".", "") + "." + decimal

    try:
        parsed = float(text)
    except Exception:
        return None
    return parsed if parsed == parsed else None


def _split_security_candidates(raw_value: Any) -> list[str]:
    text = str(raw_value or "").strip()
    if not text:
        return []
    for separator in ("|", ";"):
        text = text.replace(separator, ",")
    return [item.strip() for item in text.split(",") if item.strip()]


def _normalize_symbol_token(token: Any) -> str:
    text = _normalize_security(token)
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
    parts = [part for part in _normalize_security(value).split() if part]
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


def _json_dump(path: str, payload: Any) -> None:
    atomic_json_dump(path, payload, ensure_ascii=False, indent=2)


def _append_jsonl(path: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


class MarketScreenCaptureService:
    """Capture a market screen region, OCR the table, and persist parsed quotes."""

    def __init__(self, root_dir: str | None = None) -> None:
        self.root_dir = os.path.abspath(
            root_dir or os.path.join(Config.OPTIONS_DATA_DIR, "market_screen_capture")
        )
        self.images_dir = os.path.join(self.root_dir, "images")
        self.snapshots_dir = os.path.join(self.root_dir, "snapshots")
        self.rows_dir = os.path.join(self.root_dir, "rows")
        self.latest_path = os.path.join(self.root_dir, "latest.json")
        self.latest_csv_path = os.path.join(self.root_dir, "latest.csv")
        self.history_store = MarketScreenHistoryStore(root_dir=self.root_dir)
        self._lock = threading.RLock()
        self._ocr_engine = None
        self._last_history_persist_monotonic = 0.0
        self._target_cache: dict[str, Any] | None = None
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for path in (self.root_dir, self.images_dir, self.snapshots_dir, self.rows_dir):
            os.makedirs(path, exist_ok=True)

    def _load_ocr_engine(self):
        if self._ocr_engine is not None:
            return self._ocr_engine
        from rapidocr_onnxruntime import RapidOCR  # type: ignore

        self._ocr_engine = RapidOCR(
            use_cls=bool(Config.MARKET_SCREEN_W32_OCR_USE_CLS),
            det_limit_side_len=int(Config.MARKET_SCREEN_W32_OCR_DET_LIMIT_SIDE_LEN),
            rec_batch_num=int(Config.MARKET_SCREEN_W32_OCR_REC_BATCH_NUM),
        )
        return self._ocr_engine

    @staticmethod
    def _window_matches(title: str, query: str) -> bool:
        normalized_title = _normalize_match_text(title)
        normalized_query = _normalize_match_text(query)
        return bool(normalized_query and normalized_query in normalized_title)

    def _find_window_bbox(self, title_query: str) -> dict[str, Any]:
        if win32gui is None:
            return {
                "ok": False,
                "error": "windows_capture_unavailable",
                "title_query": title_query,
            }

        matches: list[dict[str, Any]] = []

        def callback(hwnd: int, _extra: Any) -> bool:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            if win32gui.IsIconic(hwnd):
                return True
            title = str(win32gui.GetWindowText(hwnd) or "").strip()
            if not title or not self._window_matches(title, title_query):
                return True
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = max(int(right - left), 0)
            height = max(int(bottom - top), 0)
            if width < 80 or height < 80:
                return True
            matches.append(
                {
                    "hwnd": int(hwnd),
                    "title": title,
                    "bbox": [int(left), int(top), int(right), int(bottom)],
                    "width": width,
                    "height": height,
                    "area": width * height,
                }
            )
            return True

        win32gui.EnumWindows(callback, None)
        if not matches:
            return {"ok": False, "error": "window_not_found", "title_query": title_query}

        matches.sort(key=lambda item: item["area"], reverse=True)
        best = matches[0]
        return {
            "ok": True,
            "strategy": "window_title",
            "title_query": title_query,
            "window_title": best["title"],
            "hwnd": best["hwnd"],
            "bbox": best["bbox"],
            "width": best["width"],
            "height": best["height"],
        }

    def _cached_window_target(self, title_query: str) -> dict[str, Any] | None:
        if win32gui is None:
            return None

        with self._lock:
            cached = dict(self._target_cache or {})

        hwnd = int(cached.get("hwnd") or 0)
        if not hwnd or str(cached.get("title_query") or "") != title_query:
            return None

        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                return None
            title = str(win32gui.GetWindowText(hwnd) or "").strip()
            if not self._window_matches(title, title_query):
                return None
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        except Exception:
            return None

        width = max(int(right - left), 0)
        height = max(int(bottom - top), 0)
        if width < 80 or height < 80:
            return None

        cached.update(
            {
                "ok": True,
                "strategy": "window_title",
                "title_query": title_query,
                "window_title": title,
                "bbox": [int(left), int(top), int(right), int(bottom)],
                "width": width,
                "height": height,
            }
        )
        return cached

    def _remember_window_target(self, target: dict[str, Any]) -> None:
        if not target.get("ok") or not target.get("hwnd"):
            return
        with self._lock:
            self._target_cache = dict(target)

    def _clear_window_target_cache(self) -> None:
        with self._lock:
            self._target_cache = None

    @staticmethod
    def _monitor_rect(index: int) -> tuple[int, int, int, int] | None:
        if win32api is None:
            return None

        monitors = list(win32api.EnumDisplayMonitors())
        if index < 1 or index > len(monitors):
            return None
        handle = monitors[index - 1][0]
        info = win32api.GetMonitorInfo(handle)
        work = info.get("Work") or monitors[index - 1][2]
        return tuple(int(value) for value in work)

    def _fallback_bbox(self, monitor_index: int) -> dict[str, Any]:
        rect = self._monitor_rect(monitor_index)
        if rect is None:
            return {
                "ok": False,
                "error": "fallback_monitor_not_found",
                "monitor_index": monitor_index,
            }
        left, top, right, bottom = rect
        width = max(right - left, 1)
        height = max(bottom - top, 1)
        x_ratio = min(max(float(Config.MARKET_SCREEN_W32_FALLBACK_LEFT_RATIO), 0.0), 0.95)
        y_ratio = min(max(float(Config.MARKET_SCREEN_W32_FALLBACK_TOP_RATIO), 0.0), 0.95)
        width_ratio = min(max(float(Config.MARKET_SCREEN_W32_FALLBACK_WIDTH_RATIO), 0.05), 1.0)
        height_ratio = min(max(float(Config.MARKET_SCREEN_W32_FALLBACK_HEIGHT_RATIO), 0.05), 1.0)
        crop_left = int(left + (width * x_ratio))
        crop_top = int(top + (height * y_ratio))
        crop_right = int(crop_left + (width * width_ratio))
        crop_bottom = int(crop_top + (height * height_ratio))
        return {
            "ok": True,
            "strategy": "monitor_fallback",
            "monitor_index": monitor_index,
            "bbox": [crop_left, crop_top, crop_right, crop_bottom],
            "width": max(crop_right - crop_left, 1),
            "height": max(crop_bottom - crop_top, 1),
        }

    def _resolve_capture_target(
        self,
        *,
        title_query: str | None = None,
        fallback_monitor_index: int | None = None,
    ) -> dict[str, Any]:
        title_query = str(title_query or Config.MARKET_SCREEN_W32_WINDOW_TITLE or "").strip()
        if title_query:
            cached_target = self._cached_window_target(title_query)
            if cached_target is not None:
                return cached_target
            window_target = self._find_window_bbox(title_query)
            if window_target.get("ok"):
                self._remember_window_target(window_target)
                return window_target

        fallback_index = int(
            fallback_monitor_index
            or Config.MARKET_SCREEN_W32_FALLBACK_MONITOR_INDEX
            or 1
        )
        return self._fallback_bbox(fallback_index)

    @staticmethod
    def _token_from_ocr(raw_item: Any) -> dict[str, Any] | None:
        try:
            points, text, confidence = raw_item
        except Exception:
            return None
        normalized_text = str(text or "").strip()
        if not normalized_text:
            return None
        xs = [float(point[0]) for point in points]
        ys = [float(point[1]) for point in points]
        left = min(xs)
        right = max(xs)
        top = min(ys)
        bottom = max(ys)
        return {
            "text": normalized_text,
            "confidence": float(confidence or 0.0),
            "bbox": [[float(x), float(y)] for x, y in points],
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "center_x": (left + right) / 2.0,
            "center_y": (top + bottom) / 2.0,
        }

    def _prepare_ocr_image(self, image: Image.Image) -> Image.Image:
        scale = max(float(getattr(Config, "MARKET_SCREEN_W32_OCR_SCALE", 2.0)), 0.25)
        processed = image.convert("L")
        processed = ImageOps.autocontrast(processed)
        if scale != 1.0:
            width = max(1, int(processed.width * scale))
            height = max(1, int(processed.height * scale))
            processed = processed.resize((width, height), Image.Resampling.BICUBIC)
        return processed

    def _run_ocr(self, image: Image.Image) -> list[dict[str, Any]]:
        return asyncio.run(self._run_windows_ocr(image))

    async def _run_windows_ocr(self, image: Image.Image) -> list[dict[str, Any]]:
        from winsdk.windows.globalization import Language
        from winsdk.windows.graphics.imaging import BitmapDecoder
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage import FileAccessMode, StorageFile

        language = str(getattr(Config, "MARKET_SCREEN_W32_OCR_LANGUAGE", "en-US") or "").strip()
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
                tmp_path = tmp_file.name
            image.save(tmp_path)
            storage_file = await StorageFile.get_file_from_path_async(tmp_path)
            stream = await storage_file.open_async(FileAccessMode.READ)
            decoder = await BitmapDecoder.create_async(stream)
            bitmap = await decoder.get_software_bitmap_async()

            engine = None
            if language:
                try:
                    engine = OcrEngine.try_create_from_language(Language(language))
                except Exception:
                    engine = None
            if engine is None:
                engine = OcrEngine.try_create_from_user_profile_languages()
            if engine is None:
                raise RuntimeError("Windows OCR engine is not available.")

            raw_result = await engine.recognize_async(bitmap)
            tokens: list[dict[str, Any]] = []
            for line in raw_result.lines:
                for word in line.words:
                    text = str(word.text or "").strip()
                    if not text:
                        continue
                    rect = word.bounding_rect
                    left = float(rect.x)
                    top = float(rect.y)
                    right = float(rect.x + rect.width)
                    bottom = float(rect.y + rect.height)
                    tokens.append(
                        {
                            "text": text,
                            "confidence": 1.0,
                            "bbox": [
                                [left, top],
                                [right, top],
                                [right, bottom],
                                [left, bottom],
                            ],
                            "left": left,
                            "top": top,
                            "right": right,
                            "bottom": bottom,
                            "center_x": (left + right) / 2.0,
                            "center_y": (top + bottom) / 2.0,
                        }
                    )
            return tokens
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _cluster_lines(tokens: list[dict[str, Any]], y_tolerance: float) -> list[dict[str, Any]]:
        lines: list[dict[str, Any]] = []
        for token in sorted(tokens, key=lambda item: (item["center_y"], item["left"])):
            matched = None
            for line in reversed(lines[-4:]):
                if abs(token["center_y"] - line["center_y"]) <= y_tolerance:
                    matched = line
                    break
            if matched is None:
                matched = {"tokens": [], "center_y": token["center_y"]}
                lines.append(matched)
            matched["tokens"].append(token)
            matched["center_y"] = sum(item["center_y"] for item in matched["tokens"]) / len(matched["tokens"])
        for line in lines:
            line["tokens"] = sorted(line["tokens"], key=lambda item: item["left"])
            line["text"] = " ".join(item["text"] for item in line["tokens"])
        return lines

    @staticmethod
    def _find_header_token(tokens: list[dict[str, Any]], hints: tuple[str, ...]) -> dict[str, Any] | None:
        for token in tokens:
            normalized = _normalize_match_text(token["text"])
            if any(hint in normalized for hint in hints):
                return token
        return None

    @staticmethod
    def _clean_symbol_text(text: str) -> str:
        cleaned = str(text or "").strip()
        cleaned = cleaned.translate(str.maketrans("", "", ARROW_CHARS))
        cleaned = re.sub(r"^[^A-Z0-9.]+", "", _normalize_match_text(cleaned))
        cleaned = re.sub(r"[^A-Z0-9 .:/_-]+$", "", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    @staticmethod
    def _best_price_token(tokens: list[dict[str, Any]]) -> dict[str, Any] | None:
        best = None
        best_score = -1
        for token in tokens:
            text = str(token["text"] or "")
            score = sum(ch.isdigit() for ch in text)
            score += 2 if any(ch in text for ch in ARROW_CHARS) else 0
            score += 1 if "." in text or "," in text else 0
            if score > best_score:
                best = token
                best_score = score
        return best

    @staticmethod
    def _best_change_token(tokens: list[dict[str, Any]]) -> dict[str, Any] | None:
        best = None
        best_score = -1
        for token in tokens:
            text = str(token["text"] or "")
            score = sum(ch.isdigit() for ch in text)
            score += 3 if "%" in text else 0
            score += 1 if "+" in text or "-" in text else 0
            if score > best_score:
                best = token
                best_score = score
        return best

    def _parse_rows(
        self,
        *,
        tokens: list[dict[str, Any]],
        image_width: int,
        image_height: int,
    ) -> dict[str, Any]:
        price_header = self._find_header_token(tokens, PRICE_HEADER_HINTS)
        change_header = self._find_header_token(tokens, CHANGE_HEADER_HINTS)
        default_price_x = max(
            min(float(image_width) * 0.67, float(image_width) - 90.0),
            float(image_width) * 0.28,
        )
        default_change_x = max(
            min(float(image_width) * 0.89, float(image_width) - 20.0),
            default_price_x + 70.0,
        )
        price_x = float(price_header["center_x"]) if price_header else default_price_x
        change_x = float(change_header["center_x"]) if change_header else default_change_x
        if price_x <= 40.0 or price_x >= (float(image_width) - 50.0):
            price_x = default_price_x
        if change_x <= (price_x + 40.0) or change_x >= (float(image_width) - 5.0):
            change_x = default_change_x
        header_y = 0.0
        if price_header or change_header:
            header_y = max(
                float(price_header["center_y"]) if price_header else 0.0,
                float(change_header["center_y"]) if change_header else 0.0,
            )

        lines = self._cluster_lines(tokens, y_tolerance=max(8.0, image_height * 0.004))
        if not price_header or not change_header:
            inferred_price_x: list[float] = []
            inferred_change_x: list[float] = []
            for line in lines:
                if float(line["center_y"]) <= max(header_y + 8.0, image_height * 0.05):
                    continue
                numeric_tokens = [
                    token
                    for token in line["tokens"]
                    if _safe_float(token.get("text")) is not None
                ]
                if len(numeric_tokens) < 2:
                    continue
                signed_tokens = [
                    token
                    for token in numeric_tokens
                    if any(marker in str(token.get("text") or "") for marker in ("+", "-", "%", "*"))
                ]
                change_candidate = signed_tokens[-1] if signed_tokens else numeric_tokens[-1]
                price_pool = [
                    token
                    for token in numeric_tokens
                    if token is not change_candidate
                    and float(token.get("center_x") or 0.0) < float(change_candidate.get("center_x") or 0.0) - 30.0
                ]
                if not price_pool:
                    continue
                price_candidate = price_pool[-1]
                candidate_price_x = float(price_candidate.get("center_x") or 0.0)
                candidate_change_x = float(change_candidate.get("center_x") or 0.0)
                if candidate_price_x <= 0.0 or candidate_change_x <= candidate_price_x + 40.0:
                    continue
                inferred_price_x.append(candidate_price_x)
                inferred_change_x.append(candidate_change_x)

            if inferred_price_x and not price_header:
                midpoint = len(inferred_price_x) // 2
                price_x = sorted(inferred_price_x)[midpoint]
            if inferred_change_x and not change_header:
                midpoint = len(inferred_change_x) // 2
                change_x = sorted(inferred_change_x)[midpoint]

        rows: list[dict[str, Any]] = []
        for line in lines:
            line_y = float(line["center_y"])
            if line_y <= header_y + 8.0:
                continue

            symbol_tokens = [token for token in line["tokens"] if token["center_x"] < (price_x - 28.0)]
            price_tokens = [
                token
                for token in line["tokens"]
                if (price_x - 55.0) <= token["center_x"] < (change_x - 18.0)
            ]
            change_tokens = [token for token in line["tokens"] if token["center_x"] >= (change_x - 24.0)]

            symbol_text = " ".join(
                cleaned
                for cleaned in (self._clean_symbol_text(token["text"]) for token in symbol_tokens)
                if cleaned
            ).strip()
            price_token = self._best_price_token(price_tokens)
            change_token = self._best_change_token(change_tokens)
            price_raw = str((price_token or {}).get("text") or "").strip()
            change_raw = str((change_token or {}).get("text") or "").strip()
            price_value = _safe_float(price_raw)
            change_value = _safe_float(change_raw)

            if not symbol_text:
                continue
            if price_value is None and change_value is None:
                continue

            direction = None
            if "↑" in price_raw:
                direction = "up"
            elif "↓" in price_raw:
                direction = "down"
            elif "→" in price_raw:
                direction = "flat"

            rows.append(
                {
                    "symbol": symbol_text,
                    "price": price_value,
                    "daily_change_pct": change_value,
                    "direction": direction,
                    "price_raw": price_raw,
                    "daily_change_raw": change_raw,
                    "line_text": line["text"],
                    "line_center_y": round(line_y, 2),
                }
            )

        return {
            "price_header_x": round(price_x, 2),
            "change_header_x": round(change_x, 2),
            "header_y": round(header_y, 2),
            "rows": rows,
        }

    @staticmethod
    def _image_is_probably_blank(image: Image.Image) -> bool:
        extrema = image.convert("L").getextrema()
        return (extrema[1] - extrema[0]) <= 2

    @staticmethod
    def _bitmap_from_dc(mem_dc: int, bitmap: int, width: int, height: int) -> Image.Image:
        from ctypes import wintypes

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

        gdi32 = ctypes.windll.gdi32
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        buffer = ctypes.create_string_buffer(width * height * 4)
        lines = gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(bmi), 0)
        if lines != height:
            raise RuntimeError(f"GetDIBits copied {lines} of {height} lines.")
        return Image.frombuffer("RGB", (width, height), buffer, "raw", "BGRX", 0, 1).copy()

    def _capture_image_gdi(self, bbox: list[int]) -> Image.Image:
        left, top, right, bottom = [int(value) for value in bbox]
        width = max(right - left, 1)
        height = max(bottom - top, 1)
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        screen_dc = user32.GetDC(0)
        if not screen_dc:
            raise RuntimeError("GetDC failed.")
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
        try:
            srccopy = 0x00CC0020
            if not gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, left, top, srccopy):
                raise RuntimeError("BitBlt failed.")
            return self._bitmap_from_dc(mem_dc, bitmap, width, height)
        finally:
            if old_bitmap:
                gdi32.SelectObject(mem_dc, old_bitmap)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            if screen_dc:
                user32.ReleaseDC(0, screen_dc)

    def _capture_image_printwindow(self, hwnd: int, bbox: list[int]) -> Image.Image:
        from ctypes import wintypes

        left, top, right, bottom = [int(value) for value in bbox]
        width = max(right - left, 1)
        height = max(bottom - top, 1)
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        screen_dc = user32.GetDC(0)
        if not screen_dc:
            raise RuntimeError("GetDC failed.")
        mem_dc = gdi32.CreateCompatibleDC(screen_dc)
        bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
        old_bitmap = gdi32.SelectObject(mem_dc, bitmap)
        try:
            # PW_RENDERFULLCONTENT lets DWM render the Bloomberg window even when Chrome covers it.
            if not user32.PrintWindow(wintypes.HWND(int(hwnd)), mem_dc, 0x2):
                raise RuntimeError("PrintWindow failed.")
            image = self._bitmap_from_dc(mem_dc, bitmap, width, height)
            if self._image_is_probably_blank(image):
                raise RuntimeError("PrintWindow returned a blank image.")
            return image
        finally:
            if old_bitmap:
                gdi32.SelectObject(mem_dc, old_bitmap)
            if bitmap:
                gdi32.DeleteObject(bitmap)
            if mem_dc:
                gdi32.DeleteDC(mem_dc)
            if screen_dc:
                user32.ReleaseDC(0, screen_dc)

    def _capture_image(self, target: dict[str, Any]) -> Image.Image:
        bbox = [int(value) for value in (target.get("bbox") or [])]
        hwnd = target.get("hwnd")
        if hwnd:
            try:
                return self._capture_image_printwindow(int(hwnd), bbox)
            except Exception:
                logger.debug("PrintWindow capture failed; falling back to GDI screen capture.", exc_info=True)
        return self._capture_image_gdi(bbox)

    def _image_output_path(self, captured_at: str, capture_id: str) -> str:
        session_date = captured_at[:10]
        return os.path.join(self.images_dir, session_date, f"{capture_id}.png")

    def _snapshot_output_path(self, captured_at: str, capture_id: str) -> str:
        session_date = captured_at[:10]
        return os.path.join(self.snapshots_dir, session_date, f"{capture_id}.json")

    def _rows_output_path(self, captured_at: str) -> str:
        session_date = captured_at[:10]
        return os.path.join(self.rows_dir, f"{session_date}.jsonl")

    def _csv_output_path(self, captured_at: str) -> str:
        session_date = captured_at[:10]
        return os.path.join(self.rows_dir, f"{session_date}.csv")

    def _append_csv_rows(self, path: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_exists = os.path.exists(path)
        fieldnames = [
            "capture_id",
            "captured_at",
            "window_title",
            "symbol",
            "symbol_raw",
            "symbol_normalized",
            "price",
            "daily_change_pct",
            "direction",
            "price_raw",
            "daily_change_raw",
            "image_path",
        ]
        with open(path, "a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_latest_csv_rows(self, path: str, rows: list[dict[str, Any]]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fieldnames = [
            "capture_id",
            "captured_at",
            "window_title",
            "symbol",
            "symbol_raw",
            "symbol_normalized",
            "price",
            "daily_change_pct",
            "direction",
            "price_raw",
            "daily_change_raw",
            "image_path",
        ]
        tmp_path = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        with open(tmp_path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        last_error: Exception | None = None
        for attempt in range(6):
            try:
                os.replace(tmp_path, path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.05 * (attempt + 1))
            except FileNotFoundError as exc:
                last_error = exc
                break
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        if last_error is not None:
            raise last_error

    def _history_interval_seconds(self) -> float:
        return max(float(getattr(Config, "MARKET_SCREEN_W32_HISTORY_INTERVAL_SECONDS", 5.0)), 0.0)

    def _history_persist_due(self) -> bool:
        interval = self._history_interval_seconds()
        if interval <= 0:
            return True
        with self._lock:
            return (time.monotonic() - self._last_history_persist_monotonic) >= interval

    def _mark_history_persisted(self) -> None:
        with self._lock:
            self._last_history_persist_monotonic = time.monotonic()

    def _rewrite_payload_json(self, payload: dict[str, Any]) -> None:
        artifacts = payload.get("artifacts") or {}
        snapshot_path = str(artifacts.get("snapshot_path") or "").strip()
        with self._lock:
            if snapshot_path:
                _json_dump(snapshot_path, payload)
            _json_dump(self.latest_path, payload)

    def _persist_capture(self, payload: dict[str, Any], *, persist_history: bool) -> dict[str, Any]:
        captured_at = str(payload.get("captured_at") or _utc_now_iso())
        capture_id = str(payload.get("capture_id") or "")
        self._snapshot_output_path(captured_at, capture_id)
        self._rows_output_path(captured_at)
        csv_path = self._csv_output_path(captured_at)
        image_path = str(((payload.get("image") or {}).get("path")) or "")
        artifacts = {
            "latest_path": self.latest_path,
            "latest_csv_path": self.latest_csv_path,
            "history_sampled": bool(persist_history),
            "history_interval_seconds": self._history_interval_seconds(),
            "snapshot_path": None,
            "rows_path": None,
            "csv_path": csv_path if persist_history else None,
        }

        row_records = []
        csv_rows = []
        for row in payload.get("rows") or []:
            record = {
                "capture_id": capture_id,
                "captured_at": captured_at,
                "window_title": payload.get("window_title"),
                "symbol": row.get("symbol"),
                "symbol_raw": row.get("symbol_raw"),
                "symbol_normalized": row.get("symbol_normalized"),
                "price": row.get("price"),
                "daily_change_pct": row.get("daily_change_pct"),
                "direction": row.get("direction"),
                "price_raw": row.get("price_raw"),
                "daily_change_raw": row.get("daily_change_raw"),
                "image_path": image_path,
            }
            row_records.append(record)
            # Grava no CSV qualquer row com simbolo util e preco valido.
            # `symbol_normalized` so existe quando houve correcao OCR; a maioria
            # das linhas validas usa apenas `symbol`. Exigir o campo normalizado
            # derruba o universo quase inteiro do chart.
            sym_ok = bool(str(record.get("symbol") or record.get("symbol_normalized") or "").strip())
            price_ok = record.get("price") is not None and str(record.get("price", "")).strip() not in ("", "None")
            if sym_ok and price_ok:
                csv_rows.append(record)

        with self._lock:
            self._write_latest_csv_rows(self.latest_csv_path, csv_rows)
            if persist_history:
                self._append_csv_rows(csv_path, csv_rows)
                if bool(getattr(Config, "MARKET_SCREEN_W32_HISTORY_DB_ENABLE", True)):
                    try:
                        self.history_store.append_rows(csv_rows, source_file=csv_path)
                    except Exception:
                        logger.exception("Failed to append market screen history rows to SQLite")
                self._mark_history_persisted()

        return artifacts

    def capture_w32_basica(
        self,
        *,
        persist: bool = True,
        save_image: bool | None = None,
        title_query: str | None = None,
        fallback_monitor_index: int | None = None,
    ) -> dict[str, Any]:
        if save_image is None:
            save_image = bool(getattr(Config, "MARKET_SCREEN_W32_SAVE_IMAGE", True))
        started_at = datetime.now(timezone.utc)
        target = self._resolve_capture_target(
            title_query=title_query,
            fallback_monitor_index=fallback_monitor_index,
        )
        resolve_finished_at = datetime.now(timezone.utc)
        if not target.get("ok"):
            return {
                "ok": False,
                "source": "market_screen_capture",
                "error": target.get("error") or "capture_target_not_found",
                "target": target,
            }

        captured_at = started_at.isoformat()
        bbox = [int(value) for value in (target.get("bbox") or [])]
        capture_id = hashlib.sha1(
            f"{captured_at}|{bbox}|{target.get('window_title') or target.get('strategy')}".encode("utf-8")
        ).hexdigest()[:16]

        history_due = self._history_persist_due()

        try:
            image = self._capture_image(target)
            image_captured_at = datetime.now(timezone.utc)
        except Exception as exc:
            self._clear_window_target_cache()
            logger.exception("Failed to capture market screen")
            return {
                "ok": False,
                "source": "market_screen_capture",
                "error": f"image_capture_failed:{exc}",
                "target": target,
            }

        image_path = self._image_output_path(captured_at, capture_id)
        if save_image and history_due:
            os.makedirs(os.path.dirname(image_path), exist_ok=True)
            image.save(image_path)
        else:
            image_path = ""

        try:
            ocr_image = self._prepare_ocr_image(image)
            preprocess_finished_at = datetime.now(timezone.utc)
            tokens = self._run_ocr(ocr_image)
            ocr_finished_at = datetime.now(timezone.utc)
            parsed = self._parse_rows(
                tokens=tokens,
                image_width=int(ocr_image.size[0]),
                image_height=int(ocr_image.size[1]),
            )
            parse_finished_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception("OCR parsing failed for market screen capture")
            return {
                "ok": False,
                "source": "market_screen_capture",
                "error": f"ocr_failed:{exc}",
                "target": target,
                "image": {
                    "path": image_path if (save_image and image_path) else None,
                    "width": int(image.size[0]),
                    "height": int(image.size[1]),
                },
            }

        rows = self._sanitize_capture_rows(parsed.get("rows") or [])
        payload = {
            "ok": True,
            "source": "market_screen_capture",
            "capture_id": capture_id,
            "captured_at": captured_at,
            "target_strategy": target.get("strategy"),
            "window_title": target.get("window_title"),
            "title_query": target.get("title_query"),
            "monitor_index": target.get("monitor_index"),
            "bbox": bbox,
            "image": {
                "path": image_path if (save_image and image_path) else None,
                "width": int(image.size[0]),
                "height": int(image.size[1]),
            },
            "ocr": {
                "token_count": len(tokens),
                "price_header_x": parsed.get("price_header_x"),
                "change_header_x": parsed.get("change_header_x"),
                "header_y": parsed.get("header_y"),
                "image_width": int(ocr_image.size[0]),
                "image_height": int(ocr_image.size[1]),
                "engine": "windows",
            },
            "performance": {
                "resolve_ms": round(max((resolve_finished_at - started_at).total_seconds(), 0.0) * 1000.0, 2),
                "capture_ms": round(max((image_captured_at - resolve_finished_at).total_seconds(), 0.0) * 1000.0, 2),
                "preprocess_ms": round(max((preprocess_finished_at - image_captured_at).total_seconds(), 0.0) * 1000.0, 2),
                "ocr_ms": round(max((ocr_finished_at - preprocess_finished_at).total_seconds(), 0.0) * 1000.0, 2),
                "parse_ms": round(max((parse_finished_at - ocr_finished_at).total_seconds(), 0.0) * 1000.0, 2),
            },
            "row_count": len(rows),
            "rows": rows,
        }

        if persist:
            payload["artifacts"] = self._persist_capture(payload, persist_history=history_due)
            persisted_at = datetime.now(timezone.utc)
            payload["performance"]["persist_ms"] = round(
                max((persisted_at - parse_finished_at).total_seconds(), 0.0) * 1000.0,
                2,
            )
            payload["performance"]["total_ms"] = round(
                max((persisted_at - started_at).total_seconds(), 0.0) * 1000.0,
                2,
            )
            self._rewrite_payload_json(payload)
        else:
            payload["performance"]["persist_ms"] = 0.0
            payload["performance"]["total_ms"] = round(
                max((parse_finished_at - started_at).total_seconds(), 0.0) * 1000.0,
                2,
            )
        return payload

    def _expected_reference_securities(self) -> list[str]:
        expected: list[str] = []
        seen: set[str] = set()

        def add_security(value: Any) -> None:
            for candidate in _split_security_candidates(value):
                normalized = _normalize_security(candidate)
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
            logger.debug("Failed to load factor definitions for screen capture matching", exc_info=True)

        return expected

    def _canonical_display_symbols(self) -> list[str]:
        symbols: list[str] = []
        seen: set[str] = set()

        def add_symbol(value: Any) -> None:
            symbol = _display_symbol_from_security(value)
            normalized = _normalize_security(symbol)
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

    def _build_lookup(self, values: list[str]) -> dict[str, Any]:
        lookup: dict[str, Any] = {"by_variant": {}, "entries": []}
        seen: set[str] = set()
        for value in values:
            normalized = _normalize_security(value)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            variants = _security_match_variants(value)
            compact_variants = {
                re.sub(r"[^A-Z0-9]", "", variant)
                for variant in variants
                if variant
            }
            entry = {
                "value": value,
                "variants": variants,
                "compact_variants": {item for item in compact_variants if item},
            }
            lookup["entries"].append(entry)
            for variant in variants:
                lookup["by_variant"].setdefault(variant, []).append(value)
        return lookup

    def _match_lookup_value(
        self,
        raw_symbol: Any,
        lookup: dict[str, Any],
    ) -> str | None:
        variants = _security_match_variants(raw_symbol)
        if not variants:
            return None

        by_variant = lookup.get("by_variant") or {}
        for variant in variants:
            matches = by_variant.get(variant) or []
            if len(matches) == 1:
                return matches[0]
            if matches:
                return sorted(matches, key=len)[0]

        raw_compacts = {
            re.sub(r"[^A-Z0-9]", "", variant)
            for variant in variants
            if variant
        }
        raw_compacts = {item for item in raw_compacts if item}
        if not raw_compacts:
            return None

        best_match = None
        for entry in lookup.get("entries") or []:
            compact_variants = entry.get("compact_variants") or set()
            if raw_compacts & compact_variants:
                return entry["value"]
        return best_match

    def _sanitize_capture_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        canonical_lookup = self._build_lookup(self._canonical_display_symbols())
        sanitized_rows: list[dict[str, Any]] = []

        for row in rows or []:
            item = dict(row or {})
            raw_symbol = str(item.get("symbol") or "").strip()
            if not raw_symbol:
                sanitized_rows.append(item)
                continue

            contextual_symbol = _contextual_ocr_symbol_fix(raw_symbol) or raw_symbol
            if _normalize_security(contextual_symbol) in W32_HEADER_ROW_SYMBOLS:
                continue
            matched_symbol = self._match_lookup_value(contextual_symbol, canonical_lookup)
            final_symbol = matched_symbol or contextual_symbol

            item["symbol"] = final_symbol
            if final_symbol != raw_symbol:
                item["symbol_raw"] = raw_symbol
                item["symbol_normalized"] = contextual_symbol
                item["symbol_correction_applied"] = True
            sanitized_rows.append(item)

        return sanitized_rows

    def _match_expected_security(
        self,
        raw_symbol: Any,
        expected_lookup: dict[str, Any],
    ) -> str | None:
        matched = self._match_lookup_value(raw_symbol, expected_lookup)
        return str(matched or "").strip() or None

    def build_excel_compatible_payload(
        self,
        capture_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = capture_payload or self.read_latest_capture() or {}
        if not isinstance(payload, dict) or not payload.get("ok"):
            return {
                "ok": False,
                "source": "excel_live_workbook",
                "error": (payload or {}).get("error") or "market_screen_capture_unavailable",
            }

        expected_lookup = self._build_lookup(self._expected_reference_securities())

        captured_at = str(payload.get("captured_at") or _utc_now_iso())
        workbook_name = str(
            getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_WORKBOOK_HINT", "")
            or payload.get("window_title")
            or DEFAULT_WINDOW_WORKBOOK_NAME
        ).strip() or DEFAULT_WINDOW_WORKBOOK_NAME
        workbook_fullname = str(
            getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_WORKBOOK_HINT", "")
            or DEFAULT_WINDOW_WORKBOOK_URI
        ).strip() or DEFAULT_WINDOW_WORKBOOK_URI
        worksheet_name = str(
            getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_SHEET_HINT", "")
            or workbook_name
        ).strip() or workbook_name
        security_map: dict[str, dict[str, Any]] = {}
        normalized_security_map: dict[str, dict[str, Any]] = {}
        rows_payload: list[dict[str, Any]] = []

        for index, row in enumerate(payload.get("rows") or [], start=1):
            raw_symbol = str((row or {}).get("symbol") or "").strip()
            if not raw_symbol:
                continue
            matched_security = self._match_expected_security(raw_symbol, expected_lookup) or raw_symbol
            row_payload = {
                "security": matched_security,
                "price": _safe_float((row or {}).get("price")),
                "daily_change_pct": _safe_float((row or {}).get("daily_change_pct")),
                "timestamp": captured_at,
                "fallback_source": (
                    "market_screen_w32_ocr"
                    if bool(getattr(Config, "MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE", False))
                    else "excel_fair_value_basket"
                ),
                "workbook_name": workbook_name,
                "workbook_fullname": workbook_fullname,
                "worksheet_name": worksheet_name,
                "row_number": index,
                "fields": {
                    "PX_LAST": _safe_float((row or {}).get("price")),
                    "CHG_PCT_1D": _safe_float((row or {}).get("daily_change_pct")),
                },
            }
            security_map[matched_security] = row_payload
            normalized_security_map[_normalize_security(matched_security)] = row_payload
            rows_payload.append(row_payload)

        return {
            "ok": True,
            "source": (
                "market_screen_w32_ocr"
                if bool(getattr(Config, "MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE", False))
                else "excel_live_workbook"
            ),
            "captured_at": captured_at,
            "workbook_name": workbook_name,
            "workbook_fullname": workbook_fullname,
            "worksheet_name": worksheet_name,
            "row_count": len(rows_payload),
            "rows": rows_payload,
            "security_map": security_map,
            "normalized_security_map": normalized_security_map,
        }

    def read_latest_capture(self) -> dict[str, Any] | None:
        if not os.path.exists(self.latest_path):
            return None
        try:
            with open(self.latest_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
        except Exception:
            logger.exception("Failed to read latest market screen capture")
            return None

    def status(self) -> dict[str, Any]:
        latest = self.read_latest_capture() or {}
        return {
            "windows_capture_available": win32api is not None and win32gui is not None,
            "root_dir": self.root_dir,
            "latest_capture_id": latest.get("capture_id"),
            "latest_captured_at": latest.get("captured_at"),
            "latest_row_count": latest.get("row_count"),
            "window_title": latest.get("window_title"),
        }


class MarketScreenCaptureCollectorManager:
    _instance: Optional["MarketScreenCaptureCollectorManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self.service = MarketScreenCaptureService()
        self._runtime_lock = threading.RLock()
        self._capture_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._cleanup_stop_event = threading.Event()
        self._loop_thread: Optional[threading.Thread] = None
        self._cleanup_thread: Optional[threading.Thread] = None
        self._manual_stop_requested = False
        self._latest_capture: dict[str, Any] | None = None
        self._latest_excel_payload: dict[str, Any] | None = None
        self._last_error: str | None = None
        self._last_started_at: str | None = None
        self._last_completed_at: str | None = None
        self._run_count = 0
        self._cleanup_queue: queue.Queue[str] = queue.Queue()
        self._ensure_cleanup_worker()

    @classmethod
    def get_instance(cls) -> "MarketScreenCaptureCollectorManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_cleanup_worker(self) -> None:
        with self._runtime_lock:
            if self._cleanup_thread and self._cleanup_thread.is_alive():
                return
            self._cleanup_stop_event = threading.Event()
            self._cleanup_thread = threading.Thread(
                target=self._run_cleanup_loop,
                daemon=True,
                name="market-screen-cleanup",
            )
            self._cleanup_thread.start()

    def _run_cleanup_loop(self) -> None:
        while not self._cleanup_stop_event.is_set():
            try:
                path = self._cleanup_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if not path:
                    continue
                if os.path.exists(path):
                    os.remove(path)
                    parent = os.path.dirname(path)
                    if os.path.isdir(parent) and not os.listdir(parent):
                        os.rmdir(parent)
            except Exception:
                logger.debug("Failed to delete stale market screen image", exc_info=True)
            finally:
                self._cleanup_queue.task_done()

    def _loop_alive(self) -> bool:
        return bool(self._loop_thread and self._loop_thread.is_alive())

    def _queue_previous_image_for_cleanup(
        self,
        previous_capture: dict[str, Any] | None,
        new_capture: dict[str, Any] | None,
    ) -> None:
        if not bool(getattr(Config, "MARKET_SCREEN_W32_KEEP_LAST_IMAGE_ONLY", False)):
            return
        previous_path = str((((previous_capture or {}).get("image") or {}).get("path")) or "").strip()
        current_path = str((((new_capture or {}).get("image") or {}).get("path")) or "").strip()
        if not previous_path or previous_path == current_path:
            return
        self._cleanup_queue.put(previous_path)

    def _load_cached_payloads_from_disk(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        latest_capture = self.service.read_latest_capture()
        if not latest_capture:
            return None, None
        compatible = self.service.build_excel_compatible_payload(latest_capture)
        return latest_capture, compatible if compatible.get("ok") else None

    def _update_cached_payloads(self, capture_payload: dict[str, Any]) -> dict[str, Any]:
        compatible_payload = self.service.build_excel_compatible_payload(capture_payload)
        with self._runtime_lock:
            previous_capture = _json_clone(self._latest_capture)
            self._latest_capture = _json_clone(capture_payload)
            self._latest_excel_payload = _json_clone(compatible_payload)
            self._last_error = None
            self._last_completed_at = capture_payload.get("captured_at")
            self._run_count += 1
        self._queue_previous_image_for_cleanup(previous_capture, capture_payload)
        return compatible_payload

    def _run_loop(self) -> None:
        logger.info("Market screen collector loop started")
        while not self._stop_event.is_set():
            iteration_started = time.monotonic()
            try:
                self.capture_once()
            except Exception:
                logger.exception("Market screen collector iteration failed")
            interval_seconds = max(float(getattr(Config, "MARKET_SCREEN_W32_POLL_INTERVAL_SECONDS", 0.1)), 0.01)
            elapsed = max(time.monotonic() - iteration_started, 0.0)
            sleep_seconds = max(interval_seconds - elapsed, 0.0)
            if self._stop_event.wait(sleep_seconds):
                break

        with self._runtime_lock:
            current_thread = threading.current_thread()
            if self._loop_thread is current_thread:
                self._loop_thread = None
        logger.info("Market screen collector loop stopped")

    def _current_max_age_seconds(self) -> float:
        configured = getattr(Config, "MARKET_SCREEN_W32_MAX_AGE_SECONDS", None)
        if configured is not None:
            try:
                return max(float(configured), 0.0)
            except Exception:
                pass
        return max(float(getattr(Config, "MARKET_SCREEN_W32_POLL_INTERVAL_SECONDS", 5.0)) * 2.5, 10.0)

    def _payload_age_seconds(self, payload: dict[str, Any] | None) -> float | None:
        captured_at = _parse_iso_utc((payload or {}).get("captured_at"))
        if captured_at is None:
            return None
        return max((datetime.now(timezone.utc) - captured_at).total_seconds(), 0.0)

    def start(self) -> dict[str, Any]:
        with self._runtime_lock:
            if _capture_disabled_in_process():
                self._manual_stop_requested = True
                self._last_error = "market_screen_collector_disabled_in_this_process"
                return self.status()
            self._ensure_cleanup_worker()
            self._manual_stop_requested = False
            self._last_started_at = _utc_now_iso()
            if not self._loop_alive():
                self._stop_event = threading.Event()
                self._loop_thread = threading.Thread(
                    target=self._run_loop,
                    daemon=True,
                    name="market-screen-capture-loop",
                )
                self._loop_thread.start()
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._runtime_lock:
            self._manual_stop_requested = True
            if self._loop_alive():
                self._stop_event.set()
                self._loop_thread.join(timeout=3)
                if not self._loop_alive():
                    self._loop_thread = None
        return self.status()

    def resume_if_needed(self) -> dict[str, Any]:
        if _capture_disabled_in_process():
            return self.status()
        resident_enabled = bool(getattr(Config, "MARKET_SCREEN_W32_RESIDENT_ENABLE", False))
        auto_start = bool(getattr(Config, "MARKET_SCREEN_W32_AUTO_START", False))
        if resident_enabled and auto_start and not self._loop_alive():
            return self.start()
        return self.status()

    def capture_once(self) -> dict[str, Any]:
        if _capture_disabled_in_process():
            with self._runtime_lock:
                self._last_error = "market_screen_collector_disabled_in_this_process"
            return {
                "ok": False,
                "source": "market_screen_capture",
                "error": "market_screen_collector_disabled_in_this_process",
            }
        self._ensure_cleanup_worker()
        with self._capture_lock:
            result = self.service.capture_w32_basica(
                persist=True,
                save_image=bool(getattr(Config, "MARKET_SCREEN_W32_SAVE_IMAGE", True)),
            )
            if result.get("ok"):
                self._update_cached_payloads(result)
            else:
                with self._runtime_lock:
                    self._last_error = str(result.get("error") or "market_screen_capture_failed")
            return result

    def get_excel_compatible_payload(
        self,
        max_age_seconds: float | None = None,
    ) -> dict[str, Any]:
        self.resume_if_needed()
        max_age = self._current_max_age_seconds() if max_age_seconds is None else max(float(max_age_seconds), 0.0)

        with self._runtime_lock:
            latest_capture = _json_clone(self._latest_capture)
            latest_payload = _json_clone(self._latest_excel_payload)

        if not latest_capture or not latest_payload:
            latest_capture, latest_payload = self._load_cached_payloads_from_disk()
            if latest_capture and latest_payload:
                with self._runtime_lock:
                    self._latest_capture = _json_clone(latest_capture)
                    self._latest_excel_payload = _json_clone(latest_payload)

        age_seconds = self._payload_age_seconds(latest_capture)
        if latest_payload and (max_age <= 0.0 or age_seconds is None or age_seconds <= max_age):
            if age_seconds is not None:
                latest_payload["age_seconds"] = round(age_seconds, 3)
            return latest_payload

        if latest_payload and self._loop_alive():
            latest_payload["stale"] = True
            latest_payload["stale_reason"] = "collector_refresh_in_progress"
            if age_seconds is not None:
                latest_payload["age_seconds"] = round(age_seconds, 3)
            return latest_payload

        capture_result = self.capture_once()
        if capture_result.get("ok"):
            with self._runtime_lock:
                latest_capture = _json_clone(self._latest_capture)
                latest_payload = _json_clone(self._latest_excel_payload)
            age_seconds = self._payload_age_seconds(latest_capture)
            if latest_payload and age_seconds is not None:
                latest_payload["age_seconds"] = round(age_seconds, 3)
            return latest_payload or {
                "ok": False,
                "source": "excel_live_workbook",
                "error": "market_screen_capture_cache_missing",
            }

        if latest_payload:
            latest_payload["stale"] = True
            latest_payload["stale_error"] = capture_result.get("error")
            if age_seconds is not None:
                latest_payload["age_seconds"] = round(age_seconds, 3)
            return latest_payload

        return {
            "ok": False,
            "source": "excel_live_workbook",
            "error": capture_result.get("error") or "market_screen_capture_unavailable",
        }

    def status(self) -> dict[str, Any]:
        with self._runtime_lock:
            latest_capture = _json_clone(self._latest_capture)
            latest_payload = _json_clone(self._latest_excel_payload)
            last_error = self._last_error
            last_started_at = self._last_started_at
            last_completed_at = self._last_completed_at
            run_count = self._run_count

        if not latest_capture and not latest_payload:
            latest_capture, latest_payload = self._load_cached_payloads_from_disk()

        age_seconds = self._payload_age_seconds(latest_capture)
        return {
            "running": self._loop_alive(),
            "disabled_in_process": _capture_disabled_in_process(),
            "resident_enabled": bool(getattr(Config, "MARKET_SCREEN_W32_RESIDENT_ENABLE", False)),
            "auto_start": bool(getattr(Config, "MARKET_SCREEN_W32_AUTO_START", False)),
            "replace_excel_basket_enabled": bool(getattr(Config, "MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE", False)),
            "poll_interval_seconds": float(getattr(Config, "MARKET_SCREEN_W32_POLL_INTERVAL_SECONDS", 5.0)),
            "history_interval_seconds": self.service._history_interval_seconds(),
            "save_image": bool(getattr(Config, "MARKET_SCREEN_W32_SAVE_IMAGE", True)),
            "keep_last_image_only": bool(getattr(Config, "MARKET_SCREEN_W32_KEEP_LAST_IMAGE_ONLY", False)),
            "max_age_seconds": self._current_max_age_seconds(),
            "latest_capture_id": (latest_capture or {}).get("capture_id"),
            "latest_captured_at": (latest_capture or {}).get("captured_at"),
            "latest_row_count": (latest_capture or {}).get("row_count"),
            "latest_window_title": (latest_capture or {}).get("window_title"),
            "latest_image": (latest_capture or {}).get("image"),
            "latest_ocr": (latest_capture or {}).get("ocr"),
            "latest_performance": (latest_capture or {}).get("performance"),
            "latest_workbook_name": (latest_payload or {}).get("workbook_name"),
            "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
            "last_started_at": last_started_at,
            "last_completed_at": last_completed_at or (latest_capture or {}).get("captured_at"),
            "last_error": last_error,
            "run_count": run_count,
            "cleanup_queue_size": self._cleanup_queue.qsize(),
        }
