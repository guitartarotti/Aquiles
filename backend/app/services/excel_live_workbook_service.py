from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

from ..config import Config
from ..utils.logger import get_logger
from .market_screen_capture_service import MarketScreenCaptureCollectorManager

logger = get_logger("mirofish.excel_live_workbook")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except Exception:
        return None
    return numeric if numeric == numeric else None


def _normalize_security(value: Any) -> str:
    return " ".join(str(value or "").strip().upper().split())


def _safe_text_attr(target: Any, attr_name: str) -> str:
    try:
        return str(getattr(target, attr_name, "") or "").strip()
    except Exception:
        return ""


class ExcelLiveWorkbookService:
    """Read a live fair value basket from an already-open Excel workbook."""

    def __init__(self) -> None:
        self._pythoncom = None
        self._win32 = None

    def _load_modules(self) -> bool:
        if self._pythoncom and self._win32:
            return True
        try:
            import pythoncom  # type: ignore
            import win32com.client  # type: ignore

            self._pythoncom = pythoncom
            self._win32 = win32com.client
            return True
        except Exception:
            logger.exception("Failed to import Excel COM modules")
            return False

    def _excel_application(self):
        if not self._load_modules():
            return None
        try:
            return self._win32.GetActiveObject("Excel.Application")
        except Exception:
            return None

    def _helper_script_path(self) -> str:
        return os.path.join(os.path.dirname(__file__), "excel_live_workbook_helper.py")

    def _helper_python_path(self) -> str:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        candidate = os.path.join(project_root, "backend", ".venv", "Scripts", "python.exe")
        if os.path.exists(candidate):
            return candidate
        return sys.executable

    def _read_via_subprocess(self) -> dict[str, Any] | None:
        helper_path = self._helper_script_path()
        if not os.path.exists(helper_path):
            return None
        payload = {
            "workbook_hint": getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_WORKBOOK_HINT", ""),
            "sheet_hint": getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_SHEET_HINT", ""),
            "row_start": getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_ROW_START", 85),
            "row_end": getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_ROW_END", 188),
            "name_column": getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_NAME_COLUMN", "H"),
            "price_column": getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_PRICE_COLUMN", "I"),
            "change_column": getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_DAILY_CHANGE_COLUMN", "L"),
        }
        try:
            completed = subprocess.run(
                [self._helper_python_path(), helper_path],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=25,
            )
            parsed = json.loads(completed.stdout or "{}")
            if isinstance(parsed, dict) and parsed.get("ok"):
                return parsed
            if isinstance(parsed, dict) and parsed.get("error"):
                logger.debug("Excel live workbook helper returned error: %s", parsed.get("error"))
        except Exception:
            logger.debug("Excel live workbook helper subprocess failed", exc_info=True)
        return None

    def _find_workbook(self, excel) -> Any | None:
        workbook_hint = str(getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_WORKBOOK_HINT", "") or "").strip().lower()
        workbook_count = int(getattr(excel.Workbooks, "Count", 0) or 0)
        for index in range(1, workbook_count + 1):
            try:
                workbook = excel.Workbooks.Item(index)
            except Exception:
                continue
            name = str(getattr(workbook, "Name", "") or "").strip()
            fullname = str(getattr(workbook, "FullName", "") or "").strip()
            haystack = f"{name} {fullname}".lower()
            if workbook_hint and workbook_hint in haystack:
                return workbook
        return None

    def _candidate_sheets(self, workbook) -> list[Any]:
        sheet_hint = str(getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_SHEET_HINT", "") or "").strip().lower()
        worksheets: list[Any] = []
        count = int(getattr(workbook.Worksheets, "Count", 0) or 0)
        hinted: list[Any] = []
        others: list[Any] = []
        for index in range(1, count + 1):
            try:
                sheet = workbook.Worksheets.Item(index)
            except Exception:
                continue
            name = str(getattr(sheet, "Name", "") or "").strip()
            if sheet_hint and sheet_hint == name.lower():
                hinted.append(sheet)
            else:
                others.append(sheet)
        worksheets.extend(hinted)
        worksheets.extend(others)
        return worksheets

    def _read_rows_from_sheet(self, sheet) -> list[dict[str, Any]]:
        row_start = max(int(getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_ROW_START", 85) or 85), 1)
        row_end = max(int(getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_ROW_END", 188) or 188), row_start)
        name_col = str(getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_NAME_COLUMN", "H") or "H").strip().upper()
        price_col = str(getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_PRICE_COLUMN", "I") or "I").strip().upper()
        change_col = str(getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_DAILY_CHANGE_COLUMN", "L") or "L").strip().upper()

        names = sheet.Range(f"{name_col}{row_start}:{name_col}{row_end}").Value
        prices = sheet.Range(f"{price_col}{row_start}:{price_col}{row_end}").Value
        changes = sheet.Range(f"{change_col}{row_start}:{change_col}{row_end}").Value

        rows: list[dict[str, Any]] = []
        total_rows = row_end - row_start + 1
        for offset in range(total_rows):
            name_value = names[offset][0] if isinstance(names, tuple) else None
            if name_value in (None, ""):
                continue
            security = str(name_value).strip()
            if not security:
                continue
            price_value = prices[offset][0] if isinstance(prices, tuple) else None
            change_value = changes[offset][0] if isinstance(changes, tuple) else None
            price = _safe_float(price_value)
            daily_change = _safe_float(change_value)
            rows.append({
                "row_number": row_start + offset,
                "security": security,
                "normalized_security": _normalize_security(security),
                "price": price,
                "daily_change_pct": daily_change,
            })
        return rows

    def read_fair_value_basket(self) -> dict[str, Any]:
        if getattr(Config, "MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE", False):
            manager = MarketScreenCaptureCollectorManager.get_instance()
            manager.resume_if_needed()
            return manager.get_excel_compatible_payload(
                max_age_seconds=getattr(Config, "MARKET_SCREEN_W32_MAX_AGE_SECONDS", None),
            )

        if not getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_ENABLE", False):
            return {
                "ok": False,
                "source": "excel_live_workbook",
                "error": "excel_fair_value_basket_disabled",
            }

        subprocess_result = self._read_via_subprocess()
        if isinstance(subprocess_result, dict) and subprocess_result.get("ok"):
            return subprocess_result

        excel = self._excel_application()
        if excel is None:
            return {
                "ok": False,
                "source": "excel_live_workbook",
                "error": "excel_not_open",
            }

        self._pythoncom.CoInitialize()
        try:
            workbook = self._find_workbook(excel)
            if workbook is None:
                return {
                    "ok": False,
                    "source": "excel_live_workbook",
                    "error": "workbook_not_found",
                    "workbook_hint": str(getattr(Config, "OPTIONS_FAIR_VALUE_EXCEL_BASKET_WORKBOOK_HINT", "") or ""),
                }

            best_rows: list[dict[str, Any]] = []
            best_sheet_name = None
            for sheet in self._candidate_sheets(workbook):
                try:
                    rows = self._read_rows_from_sheet(sheet)
                except Exception:
                    logger.debug("Failed to read rows from sheet", exc_info=True)
                    continue
                if len(rows) > len(best_rows):
                    best_rows = rows
                    best_sheet_name = str(getattr(sheet, "Name", "") or "").strip()

            captured_at = _utc_now_iso()
            workbook_name = _safe_text_attr(workbook, "Name")
            workbook_fullname = _safe_text_attr(workbook, "FullName")
            security_map: dict[str, dict[str, Any]] = {}
            normalized_security_map: dict[str, dict[str, Any]] = {}
            for row in best_rows:
                payload = {
                    "security": row["security"],
                    "price": row["price"],
                    "daily_change_pct": row["daily_change_pct"],
                    "timestamp": captured_at,
                    "fallback_source": "excel_fair_value_basket",
                    "workbook_name": workbook_name,
                    "workbook_fullname": workbook_fullname,
                    "worksheet_name": best_sheet_name,
                    "row_number": row["row_number"],
                    "fields": {
                        "PX_LAST": row["price"],
                        "CHG_PCT_1D": row["daily_change_pct"],
                    },
                }
                security_map[row["security"]] = payload
                normalized_security_map[row["normalized_security"]] = payload

            return {
                "ok": True,
                "source": "excel_live_workbook",
                "captured_at": captured_at,
                "workbook_name": workbook_name,
                "workbook_fullname": workbook_fullname,
                "worksheet_name": best_sheet_name,
                "row_count": len(best_rows),
                "rows": list(security_map.values()),
                "security_map": security_map,
                "normalized_security_map": normalized_security_map,
            }
        except Exception as exc:
            logger.exception("Failed to read live Excel fair value basket")
            return {
                "ok": False,
                "source": "excel_live_workbook",
                "error": str(exc),
            }
        finally:
            try:
                self._pythoncom.CoUninitialize()
            except Exception:
                logger.debug("pythoncom CoUninitialize failed", exc_info=True)
