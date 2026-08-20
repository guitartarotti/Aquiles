from flask import jsonify, request

from ...http import error_response
from ...services.options_bloomberg_service import OptionsBloombergService
from ...services.options_query_service import OptionsQueryService
from ...services.options_snapshot_service import OptionsSnapshotService
from .. import options_bp
from .shared import _options_collector_status_payload, logger


@options_bp.route("/status", methods=["GET"])
def get_options_status():
    try:
        query = OptionsQueryService()
        bloomberg = OptionsBloombergService()
        data = query.status()
        data["bloomberg"] = bloomberg.status()
        data["collector"] = _options_collector_status_payload()
        return jsonify({"success": True, "data": data})
    except ValueError:
        return error_response(
            logger,
            status_code=422,
            message="Options status is unavailable",
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/bloomberg/diagnose", methods=["GET"])
def diagnose_bloomberg_options():
    """
    Diagnóstico de conectividade Bloomberg para opções.
    Testa: status da sessão → chain do underlying → snapshot de 3 contratos.
    Retorna o que veio de cada etapa para identificar onde a cadeia quebra.
    """
    try:
        underlying = request.args.get("underlying_security") or "IBOVE Index"
        bloomberg = OptionsBloombergService()

        result: dict = {
            "underlying_security": underlying,
            "steps": {},
        }

        # Passo 1 — status da conexão
        status = bloomberg.status()
        result["steps"]["connection"] = {
            "enabled": status.get("enabled"),
            "blpapi_available": status.get("blpapi_available"),
            "tcp_available": status.get("tcp_available"),
            "host": status.get("host"),
            "port": status.get("port"),
            "ok": bool(
                status.get("enabled")
                and status.get("blpapi_available")
                and status.get("tcp_available")
            ),
        }

        if not result["steps"]["connection"]["ok"]:
            result["diagnosis"] = (
                "Bloomberg não está disponível — verifique se o BBComm está rodando e o blpapi instalado."
            )
            return jsonify({"success": True, "data": result})

        # Passo 2 — busca chain de opções
        chain_result = bloomberg.fetch_option_chain(underlying)
        chain = chain_result.get("chain") or []
        result["steps"]["option_chain"] = {
            "ok": len(chain) > 0,
            "contract_count": len(chain),
            "sample": chain[:5],
            "security_error": chain_result.get("security_error"),
            "field_exceptions": chain_result.get("field_exceptions") or [],
            "status": chain_result.get("status") or {},
        }

        if not chain:
            result["diagnosis"] = (
                "Bloomberg conectado mas cadeia de opções vazia — verifique se o ticker do underlying está correto ou se há opções disponíveis."
            )
            return jsonify({"success": True, "data": result})

        # Passo 3 — snapshot dos primeiros 3 contratos
        sample_tickers = chain[:3]
        snapshot_result = bloomberg.fetch_option_snapshots(
            sample_tickers,
            bloomberg.DISCOVERY_FIELDS,
        )
        snapshot_rows = snapshot_result.get("rows") or []
        rows_ok = [row for row in snapshot_rows if row.get("ok")]
        rows_fail = [row for row in snapshot_rows if not row.get("ok")]

        result["steps"]["snapshot_sample"] = {
            "ok": len(rows_ok) > 0,
            "requested": len(sample_tickers),
            "returned": len(snapshot_rows),
            "success_count": len(rows_ok),
            "fail_count": len(rows_fail),
            "status": snapshot_result.get("status") or {},
            "rows": [
                {
                    "security": row.get("security"),
                    "ok": row.get("ok"),
                    "fields": {
                        k: v for k, v in (row.get("fields") or {}).items() if v not in (None, "")
                    },
                    "security_error": row.get("security_error"),
                    "field_exceptions": [
                        fe.get("field_id") for fe in (row.get("field_exceptions") or [])
                    ],
                }
                for row in snapshot_rows
            ],
        }

        if rows_ok:
            has_strike = any(
                row.get("fields", {}).get("OPT_STRIKE_PX") is not None for row in rows_ok
            )
            has_undl = any(row.get("fields", {}).get("OPT_UNDL_PX") is not None for row in rows_ok)
            has_iv = any(row.get("fields", {}).get("IVOL_MID") is not None for row in rows_ok)
            result["diagnosis"] = (
                f"Bloomberg OK — {len(rows_ok)}/{len(snapshot_rows)} contratos retornados. "
                f"Strike: {'✓' if has_strike else '✗'}  "
                f"UnderlyingPx: {'✓' if has_undl else '✗'}  "
                f"IV: {'✓' if has_iv else '✗'}"
            )
            result["fields_present"] = {
                "OPT_STRIKE_PX": has_strike,
                "OPT_UNDL_PX": has_undl,
                "IVOL_MID": has_iv,
            }
        else:
            result["diagnosis"] = (
                "Bloomberg retornou contratos mas todos falharam — verifique permissões de dados ou tickers."
            )

        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/discover", methods=["POST"])
def discover_options_contracts():
    try:
        payload = request.get_json(silent=True) or {}
        underlying = (
            payload.get("underlying_security")
            or request.args.get("underlying_security")
            or "IBOVE Index"
        )
        service = OptionsSnapshotService()
        result = service.discover_underlying(underlying)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/contracts", methods=["GET"])
def list_options_contracts():
    try:
        underlying = request.args.get("underlying_security")
        only_active = str(request.args.get("only_active", "false")).lower() == "true"
        limit = request.args.get("limit")
        service = OptionsQueryService()
        result = service.contracts(
            underlying_security=underlying,
            only_active=only_active,
            limit=int(limit) if limit else None,
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/universe", methods=["GET"])
def get_options_universe():
    try:
        underlying = request.args.get("underlying_security")
        query = OptionsQueryService()
        result = query.universe(underlying_security=underlying)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/snapshot/latest", methods=["GET"])
def get_latest_options_snapshot():
    try:
        tier = request.args.get("tier", "critical")
        underlying = request.args.get("underlying_security")
        limit = max(1, min(int(request.args.get("limit", 200)), 2000))
        query = OptionsQueryService()
        result = query.latest_snapshot(
            universe_tier=tier, underlying_security=underlying, limit=limit
        )
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)
