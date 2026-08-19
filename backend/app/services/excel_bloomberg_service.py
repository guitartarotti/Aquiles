from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

from ..utils.logger import get_logger

logger = get_logger("aquiles.excel_bloomberg")

BRIDGE_SHEET_NAME = "AquilesBloombergBridge"
BRIDGE_WORKBOOK_NAME = "AquilesBloombergBridge.xlsx"
BRIDGE_MARKER_CELL = "Z1"
BRIDGE_TIMESTAMP_CELL = "Z2"
SINGLE_VALUE_CELL = "B1"
BULK_START_COLUMN = "A"


class ExcelBloombergService:
    """Read Bloomberg Excel formulas from an already-open interactive Excel session."""

    def __init__(self) -> None:
        self._win32 = None
        self._pythoncom = None

    def _load_modules(self) -> bool:
        if self._win32 and self._pythoncom:
            return True
        try:
            import pythoncom  # type: ignore
            import win32com.client  # type: ignore

            self._pythoncom = pythoncom
            self._win32 = win32com.client
            return True
        except Exception:
            return False

    def _helper_script_path(self) -> str:
        return os.path.join(os.path.dirname(__file__), "excel_bloomberg_helper.py")

    def _bridge_workbook_path(self) -> str:
        bridge_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "excel_bridge"))
        os.makedirs(bridge_dir, exist_ok=True)
        return os.path.join(bridge_dir, BRIDGE_WORKBOOK_NAME)

    def _ensure_bridge_workbook_file(self) -> str:
        target_path = self._bridge_workbook_path()
        if os.path.exists(target_path):
            return target_path

        sheet_name = escape(BRIDGE_SHEET_NAME)
        files = {
            "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
""",
            "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
""",
            "xl/workbook.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="{sheet_name}" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
""",
            "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>
""",
            "xl/worksheets/sheet1.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData/>
</worksheet>
""",
            "xl/styles.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>
  <fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
  <borders count="1"><border/></borders>
  <cellStyleXfs count="1"><xf/></cellStyleXfs>
  <cellXfs count="1"><xf xfId="0"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
""",
            "docProps/core.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
 xmlns:dc="http://purl.org/dc/elements/1.1/"
 xmlns:dcterms="http://purl.org/dc/terms/"
 xmlns:dcmitype="http://purl.org/dc/dcmitype/"
 xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>Aquiles Bloomberg Bridge</dc:title>
</cp:coreProperties>
""",
            "docProps/app.xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Aquiles</Application>
</Properties>
""",
        }

        with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as workbook_zip:
            for arcname, content in files.items():
                workbook_zip.writestr(arcname, content)
        return target_path

    @staticmethod
    def _escape_formula_text(value: str) -> str:
        return str(value or "").replace('"', '""')

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            numeric = float(value)
        except Exception:
            return None
        return numeric if numeric == numeric else None

    def _excel_application(self):
        if not self._load_modules():
            return None
        try:
            return self._win32.GetActiveObject("Excel.Application")
        except Exception:
            return None

    def _stamp_bridge_sheet(self, sheet) -> None:
        try:
            sheet.Range(BRIDGE_MARKER_CELL).Value = "__AQUILES_BLOOMBERG_BRIDGE__"
            sheet.Range(BRIDGE_TIMESTAMP_CELL).Value = datetime.now(timezone.utc).isoformat()
        except Exception:
            logger.debug("Failed to stamp Excel bridge sheet", exc_info=True)

    def _mark_workbook_saved(self, workbook) -> None:
        try:
            workbook.Saved = True
        except Exception:
            logger.debug("Failed to mark Excel bridge workbook as saved", exc_info=True)

    def _get_or_create_bridge_workbook(self, excel):
        target_path = os.path.abspath(self._ensure_bridge_workbook_file())
        target_name = os.path.basename(target_path).lower()
        workbook_count = int(getattr(excel.Workbooks, "Count", 0) or 0)

        for workbook_index in range(1, workbook_count + 1):
            try:
                workbook = excel.Workbooks[workbook_index]
            except Exception:
                continue
            workbook_name = str(getattr(workbook, "Name", "") or "").strip().lower()
            workbook_full_name = os.path.abspath(str(getattr(workbook, "FullName", "") or "").strip() or workbook_name)
            if workbook_name == target_name or workbook_full_name == target_path:
                return workbook

        raise RuntimeError(
            f"excel_bridge_workbook_not_open:{target_path}"
        )

    def _get_or_create_bridge_sheet(self, workbook):
        bridge_sheet = None
        worksheet_count = int(getattr(workbook.Worksheets, "Count", 0) or 0)
        for worksheet_index in range(1, worksheet_count + 1):
            try:
                sheet = workbook.Worksheets[worksheet_index]
            except Exception:
                continue
            if str(getattr(sheet, "Name", "") or "").strip().lower() == BRIDGE_SHEET_NAME.lower():
                bridge_sheet = sheet
                break

        if bridge_sheet is None:
            try:
                bridge_sheet = workbook.Worksheets[1]
            except Exception:
                bridge_sheet = workbook.Worksheets.Add()
            try:
                bridge_sheet.Name = BRIDGE_SHEET_NAME
            except Exception:
                logger.debug("Failed to rename persistent bridge worksheet", exc_info=True)

        try:
            bridge_sheet.Cells.ClearContents()
        except Exception:
            logger.debug("Failed to clear persistent bridge worksheet", exc_info=True)
        self._stamp_bridge_sheet(bridge_sheet)
        self._mark_workbook_saved(workbook)
        return workbook, bridge_sheet

    def _prepare_bridge_range(self, sheet, rows: int) -> None:
        safe_rows = max(int(rows or 1), 1)
        try:
            sheet.Range(f"{BULK_START_COLUMN}1:B{safe_rows}").ClearContents()
        except Exception:
            logger.debug("Failed to clear Excel bridge range", exc_info=True)

    def _fetch_last_price_rows_via_subprocess(
        self,
        securities: list[str],
        timeout_seconds: int,
        poll_seconds: float,
    ) -> dict[str, dict[str, Any]] | None:
        cleaned = [str(security).strip() for security in securities if str(security).strip()]
        if not cleaned:
            return {}
        helper_path = self._helper_script_path()
        if not os.path.exists(helper_path):
            return None
        try:
            completed = subprocess.run(
                [sys.executable, helper_path],
                input=json.dumps({
                    "securities": cleaned,
                    "timeout_seconds": timeout_seconds,
                    "poll_seconds": poll_seconds,
                }),
                capture_output=True,
                text=True,
                timeout=max(timeout_seconds + 10, 20),
            )
            if completed.returncode != 0:
                logger.warning("Excel Bloomberg helper failed: %s", completed.stderr.strip())
                return None
            payload = json.loads(completed.stdout or "{}")
            if isinstance(payload, dict):
                return payload
        except Exception:
            logger.exception("Excel Bloomberg helper subprocess failed")
        return None

    def fetch_bdp_value(
        self,
        security: str,
        field: str = "LAST_PRICE",
        timeout_seconds: int = 12,
        poll_seconds: float = 1.0,
    ) -> dict[str, Any]:
        if str(field or "").strip().upper() == "LAST_PRICE":
            return (self.fetch_last_price_rows(
                [security],
                timeout_seconds=timeout_seconds,
                poll_seconds=poll_seconds,
            ).get(security) or {
                "ok": False,
                "source": "excel_bdp",
                "security": security,
                "field": field,
                "error": "excel_bdp_unresolved",
            })

        excel = self._excel_application()
        if excel is None:
            error = "pywin32_not_available" if not self._load_modules() else "excel_not_open"
            return {
                "ok": False,
                "source": "excel_bdp",
                "security": security,
                "field": field,
                "error": error,
            }

        self._pythoncom.CoInitialize()
        try:
            workbook = self._get_or_create_bridge_workbook(excel)
            _, sheet = self._get_or_create_bridge_sheet(workbook)
            self._prepare_bridge_range(sheet, rows=4)
            formula = f'=BDP("{self._escape_formula_text(security)}","{self._escape_formula_text(field)}")'
            sheet.Range(SINGLE_VALUE_CELL).Formula = formula

            loops = max(1, int(timeout_seconds / max(poll_seconds, 0.25)))
            last_value: Any = None
            last_text = ""
            for _ in range(loops):
                try:
                    excel.CalculateFullRebuild()
                except Exception:
                    logger.debug("Excel CalculateFullRebuild failed", exc_info=True)
                time.sleep(poll_seconds)
                cell = sheet.Range(SINGLE_VALUE_CELL)
                last_value = cell.Value
                last_text = str(cell.Text)
                numeric = self._to_float(last_value)
                if numeric is not None:
                    self._stamp_bridge_sheet(sheet)
                    self._mark_workbook_saved(workbook)
                    return {
                        "ok": True,
                        "source": "excel_bdp",
                        "security": security,
                        "field": field,
                        "price": numeric,
                        "raw_value": last_value,
                        "display_text": last_text,
                    }
                if isinstance(last_value, str) and "Review" in last_value:
                    break

            return {
                "ok": False,
                "source": "excel_bdp",
                "security": security,
                "field": field,
                "error": str(last_value or last_text or "excel_bdp_unresolved"),
                "display_text": last_text,
            }
        except Exception as exc:
            if "excel_bridge_workbook_not_open:" in str(exc):
                logger.warning("Excel bridge workbook is not open: %s", exc)
            else:
                logger.exception("Excel Bloomberg read failed")
            return {
                "ok": False,
                "source": "excel_bdp",
                "security": security,
                "field": field,
                "error": str(exc),
            }
        finally:
            try:
                self._pythoncom.CoUninitialize()
            except Exception:
                logger.debug("pythoncom CoUninitialize failed", exc_info=True)

    def fetch_last_price_rows(
        self,
        securities: list[str],
        timeout_seconds: int = 12,
        poll_seconds: float = 1.0,
    ) -> dict[str, dict[str, Any]]:
        subprocess_result = self._fetch_last_price_rows_via_subprocess(
            securities=securities,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        )
        if isinstance(subprocess_result, dict) and subprocess_result:
            return subprocess_result

        results: dict[str, dict[str, Any]] = {}
        cleaned = [str(security).strip() for security in securities if str(security).strip()]
        if not cleaned:
            return results

        excel = self._excel_application()
        if excel is None:
            error = "pywin32_not_available" if not self._load_modules() else "excel_not_open"
            return {
                security: {
                    "ok": False,
                    "source": "excel_bdp",
                    "security": security,
                    "field": "LAST_PRICE",
                    "error": error,
                }
                for security in cleaned
            }

        self._pythoncom.CoInitialize()
        try:
            workbook = self._get_or_create_bridge_workbook(excel)
            _, sheet = self._get_or_create_bridge_sheet(workbook)
            self._prepare_bridge_range(sheet, rows=max(len(cleaned), 4))
            cell_map: dict[str, str] = {}
            for index, security in enumerate(cleaned, start=1):
                cell = f"{BULK_START_COLUMN}{index}"
                cell_map[cell] = security
                formula = f'=BDP("{self._escape_formula_text(security)}","LAST_PRICE")'
                sheet.Range(cell).Formula = formula

            loops = max(1, int(timeout_seconds / max(poll_seconds, 0.25)))
            for _ in range(loops):
                try:
                    excel.CalculateFullRebuild()
                except Exception:
                    logger.debug("Excel CalculateFullRebuild failed", exc_info=True)
                time.sleep(poll_seconds)
                unresolved = False
                for cell in cell_map:
                    current_value = sheet.Range(cell).Value
                    if self._to_float(current_value) is not None:
                        continue
                    if isinstance(current_value, str) and "Review" in current_value:
                        continue
                    unresolved = True
                    break
                if not unresolved:
                    break

            for cell, security in cell_map.items():
                rng = sheet.Range(cell)
                numeric = self._to_float(rng.Value)
                if numeric is not None:
                    results[security] = {
                        "ok": True,
                        "source": "excel_bdp",
                        "security": security,
                        "field": "LAST_PRICE",
                        "price": numeric,
                        "raw_value": rng.Value,
                        "display_text": str(rng.Text),
                    }
                else:
                    results[security] = {
                        "ok": False,
                        "source": "excel_bdp",
                        "security": security,
                        "field": "LAST_PRICE",
                        "error": str(rng.Value or rng.Text or "excel_bdp_unresolved"),
                        "display_text": str(rng.Text),
                    }
            self._stamp_bridge_sheet(sheet)
            self._mark_workbook_saved(workbook)
            return results
        except Exception as exc:
            if "excel_bridge_workbook_not_open:" in str(exc):
                logger.warning("Excel bridge workbook is not open: %s", exc)
            else:
                logger.exception("Excel Bloomberg bulk read failed")
            return {
                security: {
                    "ok": False,
                    "source": "excel_bdp",
                    "security": security,
                    "field": "LAST_PRICE",
                    "error": str(exc),
                }
                for security in cleaned
            }
        finally:
            try:
                self._pythoncom.CoUninitialize()
            except Exception:
                logger.debug("pythoncom CoUninitialize failed", exc_info=True)
