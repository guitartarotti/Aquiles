from __future__ import annotations

import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape

BRIDGE_SHEET_NAME = "AquilesBloombergBridge"
BRIDGE_WORKBOOK_NAME = "AquilesBloombergBridge.xlsx"
BRIDGE_MARKER_CELL = "Z1"
BRIDGE_TIMESTAMP_CELL = "Z2"
START_COLUMN = "A"


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except Exception:
        return None
    return numeric if numeric == numeric else None


def _escape_formula_text(value: str) -> str:
    return str(value or "").replace('"', '""')


def _is_retryable_excel_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return (
        "rejeitada pelo chamado" in text
        or "call was rejected by callee" in text
        or "excel.application.workbooks" in text
        or "<unknown>.workbooks" in text
        or "0x800ac472" in text
        or "ole error 0x800ac472" in text
    )


def _excel_call(fn, attempts: int = 20, sleep_seconds: float = 0.25):
    last_exc = None
    for _ in range(max(attempts, 1)):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not _is_retryable_excel_error(exc):
                raise
            time.sleep(sleep_seconds)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("excel_call_failed")


def _get_range(sheet, address: str):
    return _excel_call(lambda: sheet.Range(address))


def _set_formula(sheet, address: str, formula: str) -> None:
    rng = _get_range(sheet, address)
    _excel_call(lambda: setattr(rng, "Formula", formula))


def _set_value(sheet, address: str, value: Any) -> None:
    rng = _get_range(sheet, address)
    _excel_call(lambda: setattr(rng, "Value", value))


def _get_value(sheet, address: str):
    rng = _get_range(sheet, address)
    return _excel_call(lambda: rng.Value)


def _get_text(sheet, address: str) -> str:
    rng = _get_range(sheet, address)
    return str(_excel_call(lambda: rng.Text))


def _stamp_bridge_sheet(sheet) -> None:
    try:
        _set_value(sheet, BRIDGE_MARKER_CELL, "__AQUILES_BLOOMBERG_BRIDGE__")
        _set_value(sheet, BRIDGE_TIMESTAMP_CELL, datetime.now(timezone.utc).isoformat())
    except Exception:
        pass


def _bridge_workbook_path() -> str:
    bridge_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "excel_bridge"))
    os.makedirs(bridge_dir, exist_ok=True)
    return os.path.join(bridge_dir, BRIDGE_WORKBOOK_NAME)


def _ensure_bridge_workbook_file() -> str:
    target_path = _bridge_workbook_path()
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


def _mark_workbook_saved(workbook) -> None:
    try:
        _excel_call(lambda: setattr(workbook, "Saved", True))
    except Exception:
        pass


def _get_or_create_bridge_workbook(excel):
    target_path = os.path.abspath(_ensure_bridge_workbook_file())
    target_name = os.path.basename(target_path).lower()
    workbook_count = int(_excel_call(lambda: excel.Workbooks.Count) or 0)
    for workbook_index in range(1, workbook_count + 1):
        try:
            workbook = _excel_call(lambda workbook_index=workbook_index: excel.Workbooks[workbook_index])
        except Exception:
            continue
        workbook_name = str(getattr(workbook, "Name", "") or "").strip().lower()
        workbook_full_name = os.path.abspath(str(getattr(workbook, "FullName", "") or "").strip() or workbook_name)
        if workbook_name == target_name or workbook_full_name == target_path:
            return workbook

    raise RuntimeError(f"excel_bridge_workbook_not_open:{target_path}")


def _get_or_create_bridge_sheet(workbook):
    bridge_sheet = None
    worksheet_count = int(_excel_call(lambda workbook=workbook: workbook.Worksheets.Count) or 0)
    for worksheet_index in range(1, worksheet_count + 1):
        try:
            sheet = _excel_call(lambda workbook=workbook, worksheet_index=worksheet_index: workbook.Worksheets[worksheet_index])
        except Exception:
            continue
        if str(getattr(sheet, "Name", "") or "").strip().lower() == BRIDGE_SHEET_NAME.lower():
            bridge_sheet = sheet
            break

    if bridge_sheet is None:
        try:
            bridge_sheet = _excel_call(lambda workbook=workbook: workbook.Worksheets[1])
        except Exception:
            bridge_sheet = _excel_call(lambda workbook=workbook: workbook.Worksheets.Add())
        try:
            _excel_call(lambda bridge_sheet=bridge_sheet: setattr(bridge_sheet, "Name", BRIDGE_SHEET_NAME))
        except Exception:
            pass

    try:
        _excel_call(lambda bridge_sheet=bridge_sheet: bridge_sheet.Cells.ClearContents())
    except Exception:
        pass
    _stamp_bridge_sheet(bridge_sheet)
    _mark_workbook_saved(workbook)
    return workbook, bridge_sheet


def _prepare_bridge_range(sheet, rows: int) -> None:
    safe_rows = max(int(rows or 1), 1)
    try:
        _excel_call(lambda: _get_range(sheet, f"{START_COLUMN}1:B{safe_rows}").ClearContents())
    except Exception:
        pass


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    securities = [str(security).strip() for security in (payload.get("securities") or []) if str(security).strip()]
    timeout_seconds = max(int(payload.get("timeout_seconds") or 12), 1)
    poll_seconds = max(float(payload.get("poll_seconds") or 1.0), 0.25)
    result: dict[str, dict[str, Any]] = {}

    if not securities:
        print(json.dumps(result, ensure_ascii=False))
        return 0

    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception as exc:
        result = {
            security: {
                "ok": False,
                "source": "excel_bdp",
                "security": security,
                "field": "LAST_PRICE",
                "error": f"pywin32_unavailable:{exc}",
            }
            for security in securities
        }
        print(json.dumps(result, ensure_ascii=False))
        return 0

    pythoncom.CoInitialize()
    try:
        try:
            excel = _excel_call(lambda: win32com.client.GetActiveObject("Excel.Application"))
        except Exception:
            result = {
                security: {
                    "ok": False,
                    "source": "excel_bdp",
                    "security": security,
                    "field": "LAST_PRICE",
                    "error": "excel_not_open",
                }
                for security in securities
            }
            print(json.dumps(result, ensure_ascii=False))
            return 0

        workbook = _get_or_create_bridge_workbook(excel)
        _, sheet = _get_or_create_bridge_sheet(workbook)
        _prepare_bridge_range(sheet, rows=max(len(securities), 4))

        cell_map: dict[str, str] = {}
        for index, security in enumerate(securities, start=1):
            cell = f"{START_COLUMN}{index}"
            cell_map[cell] = security
            _set_formula(sheet, cell, f'=BDP("{_escape_formula_text(security)}","LAST_PRICE")')

        loops = max(1, int(timeout_seconds / poll_seconds))
        for _ in range(loops):
            try:
                _excel_call(lambda: excel.CalculateFullRebuild())
            except Exception:
                pass
            time.sleep(poll_seconds)
            unresolved = False
            for cell in cell_map:
                current_value = _get_value(sheet, cell)
                if _to_float(current_value) is not None:
                    continue
                if isinstance(current_value, str) and "Review" in current_value:
                    continue
                unresolved = True
                break
            if not unresolved:
                break

        for cell, security in cell_map.items():
            current_value = _get_value(sheet, cell)
            current_text = _get_text(sheet, cell)
            numeric = _to_float(current_value)
            if numeric is not None:
                result[security] = {
                    "ok": True,
                    "source": "excel_bdp",
                    "security": security,
                    "field": "LAST_PRICE",
                    "price": numeric,
                    "raw_value": current_value,
                    "display_text": current_text,
                }
            else:
                result[security] = {
                    "ok": False,
                    "source": "excel_bdp",
                    "security": security,
                    "field": "LAST_PRICE",
                    "error": str(current_value or current_text or "excel_bdp_unresolved"),
                    "display_text": current_text,
                }

        _stamp_bridge_sheet(sheet)
        _mark_workbook_saved(workbook)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
