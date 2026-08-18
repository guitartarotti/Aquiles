from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any


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


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}

    workbook_hint = str(payload.get("workbook_hint") or "").strip().lower()
    sheet_hint = str(payload.get("sheet_hint") or "").strip().lower()
    row_start = max(int(payload.get("row_start") or 85), 1)
    row_end = max(int(payload.get("row_end") or 188), row_start)
    name_col = str(payload.get("name_column") or "H").strip().upper()
    price_col = str(payload.get("price_column") or "I").strip().upper()
    change_col = str(payload.get("change_column") or "L").strip().upper()

    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"import:{exc}"}))
        return 0

    pythoncom.CoInitialize()
    try:
        excel = win32com.client.GetActiveObject("Excel.Application")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"active:{exc}"}))
        return 0

    try:
        workbook = None
        count = int(getattr(excel.Workbooks, "Count", 0) or 0)
        for index in range(1, count + 1):
            wb = excel.Workbooks.Item(index)
            name = str(getattr(wb, "Name", "") or "").strip()
            fullname = str(getattr(wb, "FullName", "") or "").strip()
            haystack = f"{name} {fullname}".lower()
            if workbook_hint and workbook_hint in haystack:
                workbook = wb
                break

        if workbook is None:
            print(json.dumps({"ok": False, "error": "workbook_not_found"}))
            return 0

        worksheets = []
        hinted = []
        others = []
        for index in range(1, int(getattr(workbook.Worksheets, "Count", 0) or 0) + 1):
            ws = workbook.Worksheets.Item(index)
            name = str(getattr(ws, "Name", "") or "").strip()
            if sheet_hint and name.lower() == sheet_hint:
                hinted.append(ws)
            else:
                others.append(ws)
        worksheets.extend(hinted)
        worksheets.extend(others)

        best_rows = []
        best_sheet_name = None
        total_rows = row_end - row_start + 1
        for ws in worksheets:
            names = ws.Range(f"{name_col}{row_start}:{name_col}{row_end}").Value
            prices = ws.Range(f"{price_col}{row_start}:{price_col}{row_end}").Value
            changes = ws.Range(f"{change_col}{row_start}:{change_col}{row_end}").Value
            rows = []
            for offset in range(total_rows):
                name_value = names[offset][0] if isinstance(names, tuple) else None
                if name_value in (None, ""):
                    continue
                security = str(name_value).strip()
                if not security:
                    continue
                price = _safe_float(prices[offset][0] if isinstance(prices, tuple) else None)
                daily_change = _safe_float(changes[offset][0] if isinstance(changes, tuple) else None)
                rows.append({
                    "row_number": row_start + offset,
                    "security": security,
                    "normalized_security": _normalize_security(security),
                    "price": price,
                    "daily_change_pct": daily_change,
                })
            if len(rows) > len(best_rows):
                best_rows = rows
                best_sheet_name = str(getattr(ws, "Name", "") or "").strip()

        captured_at = _utc_now_iso()
        workbook_name = _safe_text_attr(workbook, "Name")
        workbook_fullname = _safe_text_attr(workbook, "FullName")
        security_map = {}
        normalized_security_map = {}
        for row in best_rows:
            item = {
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
            security_map[row["security"]] = item
            normalized_security_map[row["normalized_security"]] = item

        print(json.dumps({
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
        }, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 0
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
