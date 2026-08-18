from __future__ import annotations

import socket
from typing import Any, Dict, Optional

from ..config import Config
from ..utils.logger import get_logger
from .excel_bloomberg_service import ExcelBloombergService

logger = get_logger("mirofish.bloomberg_desktop")
_excel_bloomberg = ExcelBloombergService()


class BloombergDesktopService:
    """Optional Bloomberg Desktop API connector via local BBComm."""

    def __init__(self, config_class=Config):
        self.config = config_class

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.config.MACRO_BLOOMBERG_ENABLE),
            "host": self.config.MACRO_BLOOMBERG_HOST,
            "port": int(self.config.MACRO_BLOOMBERG_PORT),
            "blpapi_available": self._blpapi_available(),
            "tcp_available": self._tcp_available(),
            "securities_count": len(self.config.MACRO_BLOOMBERG_REFERENCE_ASSETS),
            "fields": list(self.config.MACRO_BLOOMBERG_FIELDS),
        }

    def capture_reference_assets(self) -> tuple[Dict[str, Any], Dict[str, Any]]:
        status = self.status()
        if not status["enabled"]:
            status["error"] = "Bloomberg Desktop capture is disabled."
            return {}, status
        if not self.config.BLOOMBERG_REALTIME_REFERENCE_ENABLE:
            status["error"] = "Bloomberg realtime reference capture is temporarily disabled."
            return self._empty_assets("realtime_reference_disabled"), status

        blpapi = self._load_blpapi()
        if blpapi is None:
            status["error"] = "Python blpapi is not installed."
            return self._empty_assets("missing_blpapi"), status

        if not status["tcp_available"]:
            status["error"] = f"BBComm is not reachable at {status['host']}:{status['port']}."
            return self._empty_assets("bbcomm_unreachable"), status

        session = None
        try:
            options = blpapi.SessionOptions()
            options.setServerHost(self.config.MACRO_BLOOMBERG_HOST)
            options.setServerPort(int(self.config.MACRO_BLOOMBERG_PORT))

            session = blpapi.Session(options)
            if not session.start():
                status["error"] = "Failed to start Bloomberg Desktop session."
                return self._empty_assets("session_start_failed"), status

            if not session.openService("//blp/refdata"):
                status["error"] = "Failed to open Bloomberg //blp/refdata service."
                return self._empty_assets("service_open_failed"), status

            service = session.getService("//blp/refdata")
            request = service.createRequest("ReferenceDataRequest")

            securities_el = request.getElement("securities")
            for item in self.config.MACRO_BLOOMBERG_REFERENCE_ASSETS:
                securities_el.appendValue(item["security"])

            fields_el = request.getElement("fields")
            for field in self.config.MACRO_BLOOMBERG_FIELDS:
                fields_el.appendValue(field)

            session.sendRequest(request)
            assets = self._consume_reference_response(session, blpapi)
            assets = self._apply_excel_last_price_fallback(assets)
            status["session_ok"] = True
            status["captured_count"] = sum(1 for item in assets.values() if item.get("ok"))
            status["failed_count"] = sum(1 for item in assets.values() if not item.get("ok"))
            return assets, status
        except Exception as exc:
            logger.exception("Bloomberg Desktop capture failed")
            status["error"] = str(exc)
            assets = self._empty_assets("capture_failed", error=str(exc))
            assets = self._apply_excel_last_price_fallback(assets)
            status["captured_count"] = sum(1 for item in assets.values() if item.get("ok"))
            status["failed_count"] = sum(1 for item in assets.values() if not item.get("ok"))
            return assets, status
        finally:
            try:
                if session is not None:
                    session.stop()
            except Exception:
                logger.debug("Bloomberg session stop failed", exc_info=True)

    def _consume_reference_response(self, session: Any, blpapi: Any) -> Dict[str, Any]:
        assets: Dict[str, Any] = {}
        batch_error: Dict[str, Any] | None = None
        while True:
            event = session.nextEvent(int(self.config.MACRO_BLOOMBERG_TIMEOUT_SECONDS * 1000))
            event_type = event.eventType()

            for message in event:
                message_type = str(message.messageType())
                if message_type not in {"ReferenceDataResponse"} and event_type not in {
                    blpapi.Event.PARTIAL_RESPONSE,
                    blpapi.Event.RESPONSE,
                }:
                    continue

                try:
                    if message.hasElement("responseError"):
                        batch_error = self._security_error(message.getElement("responseError"))
                        continue
                except Exception:
                    batch_error = {"message": "Bloomberg response error while reading reference assets."}
                    continue

                try:
                    security_data = message.getElement("securityData")
                except Exception:
                    batch_error = {"message": "Bloomberg reference response did not contain securityData."}
                    continue

                for index in range(security_data.numValues()):
                    sec_data = security_data.getValueAsElement(index)
                    security = sec_data.getElementAsString("security")
                    metadata = self._asset_metadata(security)
                    item = {
                        **metadata,
                        "ok": True,
                        "fields": {},
                        "price": None,
                        "change_net": None,
                        "change_percent": None,
                        "open": None,
                        "high": None,
                        "low": None,
                        "volume": None,
                        "bid": None,
                        "ask": None,
                    }

                    if sec_data.hasElement("securityError"):
                        item["ok"] = False
                        item["error"] = self._security_error(sec_data.getElement("securityError"))
                        assets[security] = item
                        continue

                    field_data = sec_data.getElement("fieldData")
                    parsed_fields: Dict[str, Any] = {}
                    for field in self.config.MACRO_BLOOMBERG_FIELDS:
                        if field_data.hasElement(field):
                            parsed_fields[field] = self._element_to_python(field_data.getElement(field), blpapi)

                    item["fields"] = parsed_fields
                    item["price"] = parsed_fields.get("PX_LAST")
                    item["change_net"] = parsed_fields.get("CHG_NET_1D")
                    item["change_percent"] = parsed_fields.get("CHG_PCT_1D")
                    item["open"] = parsed_fields.get("PX_OPEN")
                    item["high"] = parsed_fields.get("PX_HIGH")
                    item["low"] = parsed_fields.get("PX_LOW")
                    item["volume"] = parsed_fields.get("PX_VOLUME")
                    item["bid"] = parsed_fields.get("BID")
                    item["ask"] = parsed_fields.get("ASK")
                    assets[security] = item

            if event_type == blpapi.Event.RESPONSE:
                break

        for item in self.config.MACRO_BLOOMBERG_REFERENCE_ASSETS:
            assets.setdefault(
                item["security"],
                self._asset_metadata(item["security"]) | {"ok": False, "error": batch_error or "No response from Bloomberg."},
            )
        return assets

    def _asset_metadata(self, security: str) -> Dict[str, Any]:
        for item in self.config.MACRO_BLOOMBERG_REFERENCE_ASSETS:
            if item["security"] == security:
                return dict(item)
        return {
            "security": security,
            "label": security,
            "category": "reference",
            "bucket": "reference",
        }

    def _apply_excel_last_price_fallback(self, assets: Dict[str, Any]) -> Dict[str, Any]:
        if not self.config.BLOOMBERG_EXCEL_FALLBACK_ENABLE:
            return assets
        pending = [
            security
            for security, item in (assets or {}).items()
            if not item.get("ok") or item.get("price") in (None, "")
        ]
        if not pending:
            return assets

        excel_rows = _excel_bloomberg.fetch_last_price_rows(pending)
        for security, excel_row in excel_rows.items():
            price = excel_row.get("price")
            if price in (None, ""):
                continue
            item = assets.setdefault(security, self._asset_metadata(security))
            item["ok"] = True
            item["price"] = price
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            fields["PX_LAST"] = price
            item["fields"] = fields
            item["fallback_source"] = "excel_bdp"
            item["fallback_field"] = "LAST_PRICE"
            item["fallback_payload"] = excel_row
            if not item.get("error"):
                item["error"] = None
        return assets

    def _empty_assets(self, reason: str, error: Optional[str] = None) -> Dict[str, Any]:
        assets = {}
        for item in self.config.MACRO_BLOOMBERG_REFERENCE_ASSETS:
            assets[item["security"]] = {
                **dict(item),
                "ok": False,
                "error": error or reason,
                "fields": {},
                "price": None,
                "change_net": None,
                "change_percent": None,
                "open": None,
                "high": None,
                "low": None,
                "volume": None,
                "bid": None,
                "ask": None,
            }
        return assets

    def _security_error(self, error_element: Any) -> Dict[str, Any]:
        result = {}
        for field in ("source", "code", "category", "message", "subcategory"):
            try:
                if error_element.hasElement(field):
                    result[field] = str(error_element.getElement(field))
            except Exception:
                continue
        return result

    def _element_to_python(self, element: Any, blpapi: Any) -> Any:
        dtype = element.datatype()
        if dtype in {blpapi.DataType.BOOL}:
            return element.getValueAsBool()
        if dtype in {blpapi.DataType.INT32, blpapi.DataType.INT64}:
            return element.getValueAsInteger()
        if dtype in {blpapi.DataType.FLOAT32, blpapi.DataType.FLOAT64}:
            return element.getValueAsFloat()
        if dtype in {blpapi.DataType.DATE, blpapi.DataType.DATETIME, blpapi.DataType.TIME}:
            return str(element.getValue())
        if dtype in {blpapi.DataType.STRING, blpapi.DataType.CHAR, blpapi.DataType.BYTEARRAY}:
            return element.getValueAsString()
        try:
            return element.getValue()
        except Exception:
            return str(element)

    def _load_blpapi(self) -> Any:
        try:
            import blpapi  # type: ignore
            return blpapi
        except Exception:
            return None

    def _blpapi_available(self) -> bool:
        return self._load_blpapi() is not None

    def _tcp_available(self) -> bool:
        try:
            with socket.create_connection(
                (self.config.MACRO_BLOOMBERG_HOST, int(self.config.MACRO_BLOOMBERG_PORT)),
                timeout=2,
            ):
                return True
        except OSError:
            return False
