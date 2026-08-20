from flask import jsonify, request

from ...http import error_response
from .. import options_bp
from .. import options_vol_index as _vol_index_routes  # noqa: F401
from .shared import _safe_float, logger


@options_bp.route("/vol-surface", methods=["GET"])
def options_vol_surface():
    """
    Retorna superfície de volatilidade implícita organizada por (expiry × strike).
    Usa MODEL_IV como fonte primária — mais confiável que IVOL_MID durante pregão.

    Query params:
      underlying_security  (str)   ex: 'IBOVE Index'
      tier                 (str)   'all' | 'structural' | 'liquid' | 'critical'
      min_dte              (int)   DTE mínimo em dias úteis (padrão: 1)
      max_dte              (int)   DTE máximo (padrão: 120)
    """
    try:
        from ...services.options_query_service import OptionsQueryService
        from ...services.options_store import OptionsStore

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        tier = request.args.get("tier") or "all"
        min_dte = int(request.args.get("min_dte") or 1)
        max_dte = int(request.args.get("max_dte") or 120)

        store = OptionsStore()
        query = OptionsQueryService(store=store)

        # Coleta rows (mesma lógica do snapshot_by_strike)
        if tier == "all":
            all_rows: list = []
            seen_ids: set = set()
            for t_name in ("structural", "liquid", "critical"):
                try:
                    res_t = query.latest_snapshot(
                        universe_tier=t_name, underlying_security=underlying, limit=5000
                    )
                    rows_t = res_t.get("rows", []) if isinstance(res_t, dict) else []
                except Exception:
                    rows_t = []
                for r in rows_t:
                    uid = r.get("bloomberg_ticker") or r.get("option_id")
                    if uid and uid not in seen_ids:
                        seen_ids.add(uid)
                        all_rows.append(r)
            rows = all_rows
        else:
            result = query.latest_snapshot(
                universe_tier=tier, underlying_security=underlying, limit=5000
            )
            rows = result.get("rows", []) if isinstance(result, dict) else []

        if not rows:
            return jsonify({"success": True, "data": {"slices": [], "spot": None, "forward": None}})

        # Spot price — tenta OPT_UNDL_PX nas rows, depois latest model run
        spot_price = None
        for r in rows:
            v = r.get("OPT_UNDL_PX") or r.get("underlying_px") or r.get("spot_price")
            if v:
                try:
                    spot_price = float(v)
                    break
                except Exception:
                    pass
        if not spot_price:
            try:
                _store2 = OptionsStore()
                _run = _store2.read_latest_model_run(underlying)
                if _run:
                    spot_price = (_run.get("market_context") or {}).get("spot_price")
            except Exception:
                pass

        # ── Monta pontos individuais ───────────────────────────────────────────
        points = []
        for r in rows:
            dte = r.get("days_to_expiry_business") or r.get("days_to_expiry_calendar") or 0
            try:
                dte = int(dte)
            except Exception:
                continue
            if dte < min_dte or dte > max_dte:
                continue

            strike = r.get("strike") or r.get("OPT_STRIKE_PX")
            try:
                strike = float(strike)
            except Exception:
                continue
            if strike <= 0:
                continue

            # IV — MODEL_IV é mais preciso (calculado do mid real)
            iv = r.get("MODEL_IV") or r.get("EFF_IV") or r.get("IVOL_MID")
            try:
                iv = float(iv) if iv is not None else None
            except Exception:
                iv = None

            if iv is None or iv < 0.005 or iv > 5.0:
                continue

            pc = str(r.get("put_call") or r.get("OPT_PUT_CALL") or "").strip().capitalize()
            expiry = r.get("expiry_date") or r.get("OPT_EXPIRE_DT") or ""
            moneyness = (strike / spot_price - 1.0) if spot_price else None

            points.append(
                {
                    "ticker": r.get("bloomberg_ticker") or r.get("option_id"),
                    "strike": strike,
                    "expiry": expiry,
                    "dte": dte,
                    "put_call": pc,
                    "iv": round(iv, 6),
                    "iv_observed": round(iv, 6),
                    "moneyness": round(moneyness, 6) if moneyness is not None else None,
                    "log_m": round(float(__import__("math").log(strike / spot_price)), 6)
                    if spot_price and strike > 0
                    else None,
                    "delta": _safe_float(
                        r.get("MODEL_DELTA") or r.get("EFF_DELTA") or r.get("OPT_DELTA")
                    ),
                    "bid": _safe_float(r.get("BID")),
                    "ask": _safe_float(r.get("ASK")),
                    "volume": _safe_float(
                        r.get("VOLUME")
                        or r.get("OPT_VOLUME")
                        or r.get("volume")
                        or r.get("volume_delta")
                    ),
                    "open_int": _safe_float(
                        r.get("OPEN_INT") or r.get("OPT_OPEN_INTEREST") or r.get("open_int")
                    ),
                    "market_ok": bool(r.get("market_ok")),
                    "spread_pct": _safe_float(r.get("spread_pct")),
                }
            )

        # ── Agrupa por expiry ─────────────────────────────────────────────────
        from collections import defaultdict

        by_expiry: dict[str, list] = defaultdict(list)
        for p in points:
            by_expiry[p["expiry"]].append(p)

        slices = []
        for expiry, pts in sorted(
            by_expiry.items(), key=lambda x: next(iter(x[1]), {}).get("dte") or 999
        ):
            dtes = [p["dte"] for p in pts]
            dte_val = round(sum(dtes) / len(dtes)) if dtes else 0

            # Separa calls e puts, ordena por strike
            calls = sorted([p for p in pts if p["put_call"] == "Call"], key=lambda x: x["strike"])
            puts = sorted([p for p in pts if p["put_call"] == "Put"], key=lambda x: x["strike"])
            all_sorted = sorted(pts, key=lambda x: x["strike"])

            slices.append(
                {
                    "expiry": expiry,
                    "dte": dte_val,
                    "point_count": len(pts),
                    "calls": calls,
                    "puts": puts,
                    "all": all_sorted,
                }
            )

        return jsonify(
            {
                "success": True,
                "data": {
                    "spot": spot_price,
                    "forward": spot_price,  # pode ser substituído pelo forward real se disponível
                    "slices": slices,
                    "total_points": len(points),
                },
            }
        )

    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)
