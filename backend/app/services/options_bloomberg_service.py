from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from ..utils.logger import get_logger
from .bloomberg_desktop_service import BloombergDesktopService
from .excel_bloomberg_service import ExcelBloombergService

logger = get_logger("aquiles.options_bloomberg")
_excel_bloomberg = ExcelBloombergService()


class OptionsBloombergService(BloombergDesktopService):
    DISCOVERY_FIELDS = [
        "PX_LAST",
        "BID",
        "ASK",
        "PX_VOLUME",
        "VOLUME",
        "OPEN_INT",
        "OPT_OPEN_INTEREST",
        "IVOL_MID",
        "OPT_UNDL_PX",
        "OPT_STRIKE_PX",
        "OPT_EXPIRE_DT",
        "OPT_PUT_CALL",
    ]

    SNAPSHOT_FIELDS = [
        "PX_LAST",
        "BID",
        "ASK",
        "PX_VOLUME",
        "VOLUME",
        "OPEN_INT",
        "OPT_OPEN_INTEREST",
        "IVOL_BID",
        "IVOL_ASK",
        "IVOL_MID",
        "IVOL_LAST",
        "OPT_DELTA",
        "OPT_GAMMA",
        "OPT_VEGA",
        "OPT_THETA",
        "OPT_DELTA_BID",
        "OPT_DELTA_ASK",
        "OPT_DELTA_MID",
        "OPT_DELTA_LAST",
        "OPT_GAMMA_BID",
        "OPT_GAMMA_ASK",
        "OPT_GAMMA_MID",
        "OPT_GAMMA_LAST",
        "OPT_VEGA_BID",
        "OPT_VEGA_ASK",
        "OPT_VEGA_MID",
        "OPT_VEGA_LAST",
        "OPT_THETA_BID",
        "OPT_THETA_ASK",
        "OPT_THETA_MID",
        "OPT_THETA_LAST",
        "OPT_UNDL_PX",
        "OPT_STRIKE_PX",
        "OPT_EXPIRE_DT",
        "OPT_PUT_CALL",
    ]

    DAILY_HISTORY_FIELDS = [
        "OPEN_INT",
        "OPT_OPEN_INTEREST",
        "PX_VOLUME",
        "IVOL_MID",
        "PX_LAST",
        "BID",
        "ASK",
    ]

    AUXILIARY_REFERENCE_FIELDS = [
        "PX_LAST",
        "BID",
        "ASK",
        "PX_VOLUME",
        "CHG_NET_1D",
        "CHG_PCT_1D",
    ]

    def status(self) -> dict[str, Any]:
        status = super().status()
        status.update({
            "options_enabled": bool(self.config.OPTIONS_ENABLE),
            "underlyings_count": len(self.config.OPTIONS_BLOOMBERG_UNDERLYINGS),
            "underlyings": list(self.config.OPTIONS_BLOOMBERG_UNDERLYINGS),
        })
        return status

    def fetch_option_chain(self, underlying_security: str) -> dict[str, Any]:
        blpapi, session, service, status = self._open_refdata_session()
        if session is None or service is None or blpapi is None:
            return {
                "underlying_security": underlying_security,
                "chain": [],
                "status": status,
            }

        try:
            request = service.createRequest("ReferenceDataRequest")
            request.getElement("securities").appendValue(underlying_security)
            request.getElement("fields").appendValue("OPT_CHAIN")
            session.sendRequest(request)

            chain: list[str] = []
            field_exceptions: list[dict[str, Any]] = []
            security_error: dict[str, Any] | None = None
            response_error: str | None = None
            while True:
                event = session.nextEvent(int(self.config.MACRO_BLOOMBERG_TIMEOUT_SECONDS * 1000))
                event_type = event.eventType()
                for message in event:
                    if str(message.messageType()) != "ReferenceDataResponse":
                        continue
                    try:
                        if message.hasElement("responseError"):
                            response_error = str(message.getElement("responseError"))
                            continue
                    except Exception:
                        response_error = "Bloomberg option chain response error."
                        continue
                    try:
                        if not message.hasElement("securityData"):
                            response_error = response_error or "Bloomberg option chain response did not contain securityData."
                            continue
                    except Exception:
                        response_error = response_error or "Bloomberg option chain response did not contain securityData."
                        continue
                    security_data = message.getElement("securityData")
                    for index in range(security_data.numValues()):
                        sec_data = security_data.getValueAsElement(index)
                        if sec_data.hasElement("securityError"):
                            security_error = self._security_error(sec_data.getElement("securityError"))
                            continue

                        if sec_data.hasElement("fieldExceptions"):
                            exceptions = sec_data.getElement("fieldExceptions")
                            for idx in range(exceptions.numValues()):
                                item = exceptions.getValueAsElement(idx)
                                field_exceptions.append(self._field_exception(item))

                        field_data = sec_data.getElement("fieldData")
                        if not field_data.hasElement("OPT_CHAIN"):
                            continue
                        chain_el = field_data.getElement("OPT_CHAIN")
                        for idx in range(chain_el.numValues()):
                            value = chain_el.getValueAsElement(idx)
                            if value.hasElement("Security Description"):
                                chain.append(value.getElementAsString("Security Description"))
                if event_type == blpapi.Event.RESPONSE:
                    break

            chain = sorted({item.strip() for item in chain if item and item.strip()})
            status["session_ok"] = True
            if response_error:
                status["error"] = response_error
            return {
                "underlying_security": underlying_security,
                "chain": chain,
                "count": len(chain),
                "field_exceptions": field_exceptions,
                "security_error": security_error,
                "status": status,
            }
        finally:
            self._close_session(session)

    def fetch_option_snapshots(
        self,
        securities: list[str],
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        blpapi, session, service, status = self._open_refdata_session()
        if session is None or service is None or blpapi is None:
            return {"rows": [], "status": status}

        try:
            request = service.createRequest("ReferenceDataRequest")
            for security in securities:
                request.getElement("securities").appendValue(security)
            for field in (fields or self.SNAPSHOT_FIELDS):
                request.getElement("fields").appendValue(field)
            session.sendRequest(request)

            rows: list[dict[str, Any]] = []
            while True:
                event = session.nextEvent(int(self.config.MACRO_BLOOMBERG_TIMEOUT_SECONDS * 1000))
                event_type = event.eventType()
                for message in event:
                    if str(message.messageType()) != "ReferenceDataResponse":
                        continue
                    try:
                        if message.hasElement("responseError"):
                            status["error"] = str(message.getElement("responseError"))
                            continue
                    except Exception:
                        status["error"] = "Bloomberg snapshot response error."
                        continue
                    try:
                        if not message.hasElement("securityData"):
                            status["error"] = "Bloomberg snapshot response did not contain securityData."
                            continue
                    except Exception:
                        status["error"] = "Bloomberg snapshot response did not contain securityData."
                        continue
                    security_data = message.getElement("securityData")
                    for index in range(security_data.numValues()):
                        sec_data = security_data.getValueAsElement(index)
                        rows.append(self._parse_reference_security(sec_data, fields or self.SNAPSHOT_FIELDS, blpapi))
                if event_type == blpapi.Event.RESPONSE:
                    break

            status["session_ok"] = True
            status["captured_count"] = sum(1 for row in rows if row.get("ok"))
            status["failed_count"] = sum(1 for row in rows if not row.get("ok"))
            return {
                "rows": rows,
                "status": status,
            }
        finally:
            self._close_session(session)

    def fetch_reference_securities(
        self,
        securities: list[str],
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        cleaned_securities = [str(security).strip() for security in securities if str(security).strip()]
        if not cleaned_securities:
            return {"rows": [], "status": {"session_ok": False, "captured_count": 0, "failed_count": 0}}
        if not self.config.BLOOMBERG_REALTIME_REFERENCE_ENABLE:
            return {
                "rows": [
                    {
                        "security": security,
                        "ok": False,
                        "fields": {},
                        "field_exceptions": [],
                        "security_error": {"message": "Bloomberg realtime reference capture is temporarily disabled."},
                    }
                    for security in cleaned_securities
                ],
                "status": {
                    "session_ok": False,
                    "captured_count": 0,
                    "failed_count": len(cleaned_securities),
                    "error": "realtime_reference_disabled",
                },
            }

        blpapi, session, service, status = self._open_refdata_session()
        if session is None or service is None or blpapi is None:
            return {"rows": [], "status": status}

        requested_fields = fields or self.AUXILIARY_REFERENCE_FIELDS
        try:
            request = service.createRequest("ReferenceDataRequest")
            for security in cleaned_securities:
                request.getElement("securities").appendValue(security)
            for field in requested_fields:
                request.getElement("fields").appendValue(field)
            session.sendRequest(request)

            rows: list[dict[str, Any]] = []
            while True:
                event = session.nextEvent(int(self.config.MACRO_BLOOMBERG_TIMEOUT_SECONDS * 1000))
                event_type = event.eventType()
                for message in event:
                    if str(message.messageType()) != "ReferenceDataResponse":
                        continue
                    try:
                        if message.hasElement("responseError"):
                            status["error"] = str(message.getElement("responseError"))
                            continue
                    except Exception:
                        status["error"] = "Bloomberg reference response error."
                        continue
                    try:
                        if not message.hasElement("securityData"):
                            continue
                    except Exception:
                        status["error"] = "Bloomberg reference response did not contain securityData."
                        continue
                    security_data = message.getElement("securityData")
                    for index in range(security_data.numValues()):
                        sec_data = security_data.getValueAsElement(index)
                        rows.append(self._parse_reference_security(sec_data, requested_fields, blpapi))
                if event_type == blpapi.Event.RESPONSE:
                    break

            rows = self._apply_excel_last_price_fallback(rows, cleaned_securities, requested_fields)
            status["session_ok"] = True
            status["captured_count"] = sum(1 for row in rows if row.get("ok"))
            status["failed_count"] = sum(1 for row in rows if not row.get("ok"))
            return {
                "rows": rows,
                "status": status,
            }
        finally:
            self._close_session(session)

    def _apply_excel_last_price_fallback(
        self,
        rows: list[dict[str, Any]],
        requested_securities: list[str],
        requested_fields: list[str],
    ) -> list[dict[str, Any]]:
        if not self.config.BLOOMBERG_EXCEL_FALLBACK_ENABLE:
            return rows
        row_map = {str((row or {}).get("security") or ""): dict(row) for row in rows if str((row or {}).get("security") or "")}
        pending = []
        for security in requested_securities:
            row = row_map.get(security) or {}
            fields = row.get("fields") or {}
            if (not row.get("ok")) or fields.get("PX_LAST") in (None, ""):
                pending.append(security)
        if not pending:
            return list(row_map.values())

        excel_rows = _excel_bloomberg.fetch_last_price_rows(pending)
        for security in pending:
            excel_row = excel_rows.get(security) or {}
            price = excel_row.get("price")
            if price in (None, ""):
                if security not in row_map:
                    row_map[security] = {
                        "security": security,
                        "ok": False,
                        "fields": {},
                        "field_exceptions": [],
                        "security_error": None,
                    }
                continue

            row = row_map.get(security) or {
                "security": security,
                "ok": True,
                "fields": {},
                "field_exceptions": [],
                "security_error": None,
            }
            fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
            fields["PX_LAST"] = price
            if "LAST_PRICE" in requested_fields:
                fields["LAST_PRICE"] = price
            row["fields"] = fields
            row["ok"] = True
            row["fallback_source"] = "excel_bdp"
            row["fallback_field"] = "LAST_PRICE"
            row["fallback_payload"] = excel_row
            row_map[security] = row

        ordered_rows = []
        for security in requested_securities:
            row = row_map.get(security)
            if row:
                ordered_rows.append(row)
        return ordered_rows

    def fetch_option_history(
        self,
        security: str,
        start_date: str,
        end_date: str,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        blpapi, session, service, status = self._open_refdata_session()
        if session is None or service is None or blpapi is None:
            return {"rows": [], "status": status}

        try:
            request = service.createRequest("HistoricalDataRequest")
            request.getElement("securities").appendValue(security)
            for field in (fields or self.DAILY_HISTORY_FIELDS):
                request.getElement("fields").appendValue(field)
            request.set("startDate", start_date.replace("-", ""))
            request.set("endDate", end_date.replace("-", ""))
            request.set("periodicitySelection", "DAILY")
            session.sendRequest(request)

            rows: list[dict[str, Any]] = []
            field_exceptions: list[dict[str, Any]] = []
            while True:
                event = session.nextEvent(int(self.config.MACRO_BLOOMBERG_TIMEOUT_SECONDS * 1000))
                event_type = event.eventType()
                for message in event:
                    if str(message.messageType()) != "HistoricalDataResponse":
                        continue
                    if message.hasElement("responseError"):
                        status["error"] = str(message.getElement("responseError"))
                        continue
                    if not message.hasElement("securityData"):
                        continue
                    security_data = message.getElement("securityData")
                    if security_data.hasElement("fieldExceptions"):
                        exceptions = security_data.getElement("fieldExceptions")
                        for idx in range(exceptions.numValues()):
                            field_exceptions.append(self._field_exception(exceptions.getValueAsElement(idx)))
                    if not security_data.hasElement("fieldData"):
                        continue
                    field_data = security_data.getElement("fieldData")
                    for idx in range(field_data.numValues()):
                        entry = field_data.getValueAsElement(idx)
                        row = {
                            "security": security,
                            "trade_date": None,
                            "fields": {},
                        }
                        for child_index in range(entry.numElements()):
                            child = entry.getElement(child_index)
                            key = str(child.name())
                            value = self._element_to_python(child, blpapi)
                            if key == "date":
                                row["trade_date"] = str(value)[:10]
                            else:
                                row["fields"][key] = value
                        rows.append(row)
                if event_type == blpapi.Event.RESPONSE:
                    break

            status["session_ok"] = True
            return {
                "rows": rows,
                "field_exceptions": field_exceptions,
                "status": status,
            }
        finally:
            self._close_session(session)

    def fetch_option_ticks(
        self,
        security: str,
        start_dt: datetime | str,
        end_dt: datetime | str,
        event_types: Iterable[str] | None = None,
        include_condition_codes: bool = True,
    ) -> dict[str, Any]:
        blpapi, session, service, status = self._open_refdata_session()
        if session is None or service is None or blpapi is None:
            return {"rows": [], "status": status}

        try:
            request = service.createRequest("IntradayTickRequest")
            request.set("security", security)
            for event_type in (event_types or ("TRADE",)):
                request.getElement("eventTypes").appendValue(event_type)
            request.set("startDateTime", self._format_bloomberg_datetime(start_dt))
            request.set("endDateTime", self._format_bloomberg_datetime(end_dt))
            request.set("includeConditionCodes", include_condition_codes)
            request.set("includeNonPlottableEvents", True)
            session.sendRequest(request)

            rows: list[dict[str, Any]] = []
            while True:
                event = session.nextEvent(int(self.config.MACRO_BLOOMBERG_TIMEOUT_SECONDS * 1000))
                event_type = event.eventType()
                for message in event:
                    if str(message.messageType()) != "IntradayTickResponse":
                        continue
                    if message.hasElement("responseError"):
                        status["error"] = str(message.getElement("responseError"))
                        continue
                    if not message.hasElement("tickData"):
                        continue
                    tick_data = message.getElement("tickData").getElement("tickData")
                    for idx in range(tick_data.numValues()):
                        tick = tick_data.getValueAsElement(idx)
                        row = {
                            "security": security,
                            "event_time": None,
                            "event_type": None,
                            "price": None,
                            "size": None,
                            "condition_code": None,
                        }
                        for child_index in range(tick.numElements()):
                            child = tick.getElement(child_index)
                            key = str(child.name())
                            value = self._element_to_python(child, blpapi)
                            if key == "time":
                                row["event_time"] = str(value)
                            elif key == "type":
                                row["event_type"] = value
                            elif key == "value":
                                row["price"] = value
                            elif key == "size":
                                row["size"] = value
                            elif key == "conditionCodes":
                                row["condition_code"] = value
                        rows.append(row)
                if event_type == blpapi.Event.RESPONSE:
                    break

            status["session_ok"] = True
            status["captured_count"] = len(rows)
            return {
                "rows": rows,
                "status": status,
            }
        finally:
            self._close_session(session)

    def fetch_intraday_bars(
        self,
        security: str,
        start_dt: datetime | str,
        end_dt: datetime | str,
        interval_minutes: int = 5,
        event_type: str = "TRADE",
    ) -> dict[str, Any]:
        blpapi, session, service, status = self._open_refdata_session()
        if session is None or service is None or blpapi is None:
            return {"rows": [], "status": status}

        try:
            request = service.createRequest("IntradayBarRequest")
            request.set("security", security)
            request.set("eventType", event_type)
            request.set("interval", max(int(interval_minutes), 1))
            request.set("startDateTime", self._format_bloomberg_datetime(start_dt))
            request.set("endDateTime", self._format_bloomberg_datetime(end_dt))
            session.sendRequest(request)

            rows: list[dict[str, Any]] = []
            while True:
                event = session.nextEvent(int(self.config.MACRO_BLOOMBERG_TIMEOUT_SECONDS * 1000))
                event_type_value = event.eventType()
                for message in event:
                    if str(message.messageType()) != "IntradayBarResponse":
                        continue
                    if message.hasElement("responseError"):
                        status["error"] = str(message.getElement("responseError"))
                        continue
                    if not message.hasElement("barData"):
                        continue
                    bar_data = message.getElement("barData")
                    if not bar_data.hasElement("barTickData"):
                        continue
                    bars = bar_data.getElement("barTickData")
                    for idx in range(bars.numValues()):
                        bar = bars.getValueAsElement(idx)
                        row = {
                            "security": security,
                            "event_time": None,
                            "open": None,
                            "high": None,
                            "low": None,
                            "close": None,
                            "volume": None,
                            "num_events": None,
                        }
                        for child_index in range(bar.numElements()):
                            child = bar.getElement(child_index)
                            key = str(child.name())
                            value = self._element_to_python(child, blpapi)
                            if key == "time":
                                row["event_time"] = str(value)
                            elif key == "open":
                                row["open"] = value
                            elif key == "high":
                                row["high"] = value
                            elif key == "low":
                                row["low"] = value
                            elif key == "close":
                                row["close"] = value
                            elif key == "volume":
                                row["volume"] = value
                            elif key == "numEvents":
                                row["num_events"] = value
                        rows.append(row)
                if event_type_value == blpapi.Event.RESPONSE:
                    break

            status["session_ok"] = True
            status["captured_count"] = len(rows)
            return {
                "rows": rows,
                "status": status,
            }
        finally:
            self._close_session(session)

    def _open_refdata_session(self) -> tuple[Any, Any, Any, dict[str, Any]]:
        status = self.status()
        if not status["enabled"]:
            status["error"] = "Bloomberg Desktop capture is disabled."
            return None, None, None, status

        blpapi = self._load_blpapi()
        if blpapi is None:
            status["error"] = "Python blpapi is not installed."
            return None, None, None, status

        if not status["tcp_available"]:
            status["error"] = f"BBComm is not reachable at {status['host']}:{status['port']}."
            return blpapi, None, None, status

        options = blpapi.SessionOptions()
        options.setServerHost(self.config.MACRO_BLOOMBERG_HOST)
        options.setServerPort(int(self.config.MACRO_BLOOMBERG_PORT))
        session = blpapi.Session(options)
        if not session.start():
            status["error"] = "Failed to start Bloomberg Desktop session."
            return blpapi, None, None, status
        if not session.openService("//blp/refdata"):
            status["error"] = "Failed to open Bloomberg //blp/refdata service."
            self._close_session(session)
            return blpapi, None, None, status
        service = session.getService("//blp/refdata")
        return blpapi, session, service, status

    def _close_session(self, session: Any) -> None:
        try:
            if session is not None:
                session.stop()
        except Exception:
            logger.debug("Options Bloomberg session stop failed", exc_info=True)

    def _parse_reference_security(self, sec_data: Any, fields: list[str], blpapi: Any) -> dict[str, Any]:
        security = sec_data.getElementAsString("security")
        item = {
            "security": security,
            "ok": True,
            "fields": {},
            "field_exceptions": [],
            "security_error": None,
        }
        if sec_data.hasElement("securityError"):
            item["ok"] = False
            item["security_error"] = self._security_error(sec_data.getElement("securityError"))
            return item

        if sec_data.hasElement("fieldExceptions"):
            exceptions = sec_data.getElement("fieldExceptions")
            for idx in range(exceptions.numValues()):
                item["field_exceptions"].append(self._field_exception(exceptions.getValueAsElement(idx)))

        field_data = sec_data.getElement("fieldData")
        parsed_fields: dict[str, Any] = {}
        for field in fields:
            if field_data.hasElement(field):
                parsed_fields[field] = self._element_to_python(field_data.getElement(field), blpapi)
        item["fields"] = parsed_fields
        return item

    def _field_exception(self, field_exception: Any) -> dict[str, Any]:
        error_info = field_exception.getElement("errorInfo")
        return {
            "field_id": field_exception.getElementAsString("fieldId"),
            "source": error_info.getElementAsString("source") if error_info.hasElement("source") else None,
            "category": error_info.getElementAsString("category") if error_info.hasElement("category") else None,
            "message": error_info.getElementAsString("message") if error_info.hasElement("message") else None,
            "subcategory": error_info.getElementAsString("subcategory") if error_info.hasElement("subcategory") else None,
            "code": self._element_to_python(error_info.getElement("code"), self._load_blpapi()) if error_info.hasElement("code") else None,
        }

    def _format_bloomberg_datetime(self, value: datetime | str) -> str:
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%dT%H:%M:%S")
        return str(value)
