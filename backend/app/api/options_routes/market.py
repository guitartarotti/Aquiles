import time as _time

from flask import jsonify, request

from ...container import get_container
from ...http import error_response
from .. import options_bp
from .shared import logger

_SPOT_CACHE: dict[str, tuple[float, float]] = {}
_SPOT_CACHE_TTL = 5 * 60


@options_bp.route("/market/spot", methods=["GET"])
def market_spot():
    """
    Retorna o preço spot atual do subjacente via OpLab.

    Query params:
      underlying  — símbolo OpLab (default: 'IBOV')

    Resposta:
      { spot: float, underlying: str, ts: float, cached: bool }
    """
    underlying = (request.args.get("underlying") or "IBOV").strip().upper()
    now = _time.time()

    cached_entry = _SPOT_CACHE.get(underlying)
    if cached_entry and (now - cached_entry[1]) < _SPOT_CACHE_TTL:
        spot, ts = cached_entry
        return jsonify(
            {
                "spot": spot,
                "underlying": underlying,
                "ts": ts,
                "cached": True,
                "age_seconds": round(now - ts),
            }
        )

    try:
        svc = get_container().oplab_options_service()
        spot = svc.fetch_live_spot(underlying)

        if spot is None:
            # Fallback: tenta extrair do modelo mais recente em cache
            model_svc = get_container().options_modeling_service()
            latest = model_svc.get_latest_result()
            if latest:
                ctx = getattr(latest, "market_context", None) or {}
                if isinstance(ctx, dict):
                    spot = ctx.get("spot_price")
                else:
                    spot = getattr(ctx, "spot_price", None)

        if spot is None:
            return error_response(
                logger,
                status_code=503,
                message="Spot price indisponível",
                extra={"underlying": underlying},
            )

        _SPOT_CACHE[underlying] = (float(spot), now)
        return jsonify(
            {
                "spot": float(spot),
                "underlying": underlying,
                "ts": now,
                "cached": False,
                "age_seconds": 0,
            }
        )

    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)


@options_bp.route("/snapshot/by-strike", methods=["GET"])
def snapshot_by_strike():
    """
    Retorna dados do snapshot mais recente agregados por strike.
    Útil para IV smile (MODEL_IV por strike/put_call) e GEX calculation
    quando combinado com B3 OI.

    Query params:
      underlying_security  (str)  ex: 'IBOVE Index'
      tier                 (str)  'critical' | 'liquid' | 'structural' | 'all' (padrão: critical)
                                  'all' = mescla todos os tiers para máxima cobertura de strikes
    """
    try:
        from ...services.options_query_service import OptionsQueryService
        from ...services.options_store import OptionsStore

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        tier = request.args.get("tier") or "critical"

        store = OptionsStore()
        query = OptionsQueryService(store=store)

        if tier == "all":
            # Mescla todos os tiers para obter cobertura máxima de strikes
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
                    uid = (
                        r.get("bloomberg_ticker")
                        or r.get("option_id")
                        or f"{r.get('strike')}_{r.get('put_call') or r.get('OPT_PUT_CALL')}"
                    )
                    if uid and uid not in seen_ids:
                        seen_ids.add(uid)
                        all_rows.append(r)
            rows = all_rows
        else:
            # latest_snapshot retorna {"batch": {...}, "rows": [...dicts...]}
            result = query.latest_snapshot(
                universe_tier=tier,
                underlying_security=underlying,
                limit=2000,
            )
            rows = result.get("rows", []) if isinstance(result, dict) else []

        if not rows:
            return jsonify({"success": True, "data": {"by_strike": [], "options": []}})

        # Monta lista limpa por opção (para IV smile)
        options_list = []
        for r in rows:
            pc = str(r.get("put_call") or r.get("OPT_PUT_CALL") or "").capitalize()
            options_list.append(
                {
                    "symbol": r.get("bloomberg_ticker") or r.get("option_id"),
                    "put_call": pc,  # 'Call' | 'Put'
                    "strike": r.get("strike") or r.get("OPT_STRIKE_PX"),
                    "expiry_date": r.get("expiry_date") or r.get("OPT_EXPIRE_DT"),
                    "days_to_expiry": r.get("days_to_expiry_business")
                    or r.get("days_to_expiry_calendar"),
                    # IV — MODEL_IV é calculado do mid real (bid/ask), mais confiável que IVOL_MID histórico
                    "iv": r.get("MODEL_IV") or r.get("EFF_IV") or r.get("IVOL_MID"),
                    "iv_bid": r.get("IVOL_BID"),
                    "iv_ask": r.get("IVOL_ASK"),
                    # OI (geralmente null para IBOV — usar B3)
                    "open_int": r.get("OPEN_INT") or r.get("OPT_OPEN_INTEREST"),
                    # Preços
                    "bid": r.get("BID"),
                    "ask": r.get("ASK"),
                    "mid": r.get("MID") or r.get("bid_ask_mid"),
                    "last": r.get("PX_LAST"),
                    # Greeks (modelo interno)
                    "delta": r.get("MODEL_DELTA") or r.get("OPT_DELTA"),
                    "gamma": r.get("MODEL_GAMMA_POINT") or r.get("OPT_GAMMA"),
                    "vega": r.get("MODEL_VEGA_1PCTVOL") or r.get("OPT_VEGA"),
                    "theta": r.get("MODEL_THETA_BD252") or r.get("OPT_THETA"),
                    "vanna": r.get("MODEL_VANNA"),
                    "charm": r.get("MODEL_CHARM_BD252"),
                    # Score
                    "moneyness": r.get("moneyness_spot"),
                    "market_ok": r.get("market_ok"),
                    "spot_price": r.get("OPT_UNDL_PX"),
                }
            )

        # Agrega por strike para facilitar charts
        strike_map: dict[float, dict] = {}
        for o in options_list:
            s = float(o["strike"] or 0)
            if s <= 0:
                continue
            if s not in strike_map:
                strike_map[s] = {"strike": s, "calls": [], "puts": []}
            if o["put_call"] == "Call":
                strike_map[s]["calls"].append(o)
            else:
                strike_map[s]["puts"].append(o)

        by_strike = []
        for s, v in sorted(strike_map.items()):
            calls = v["calls"]
            puts = v["puts"]
            best_call = max(calls, key=lambda x: x.get("market_ok") or 0) if calls else {}
            best_put = max(puts, key=lambda x: x.get("market_ok") or 0) if puts else {}
            by_strike.append(
                {
                    "strike": s,
                    "iv_call": best_call.get("iv"),
                    "iv_put": best_put.get("iv"),
                    "gamma_call": best_call.get("gamma"),
                    "gamma_put": best_put.get("gamma"),
                    "delta_call": best_call.get("delta"),
                    "delta_put": best_put.get("delta"),
                    "vega_call": best_call.get("vega"),
                    "vega_put": best_put.get("vega"),
                    "open_int_call": best_call.get("open_int"),
                    "open_int_put": best_put.get("open_int"),
                }
            )

        return jsonify(
            {
                "success": True,
                "data": {
                    "by_strike": by_strike,
                    "options": options_list,
                },
            }
        )
    except Exception as e:
        return error_response(logger, status_code=500, exception=e)


@options_bp.route("/diagnostics", methods=["GET"])
def options_diagnostics():
    """
    Retorna estatísticas de cobertura de dados de opções para debugging de pipeline.

    Query params:
      underlying_security  (str)  ex: 'IBOVE Index'
    """
    try:
        from ...services.options_query_service import OptionsQueryService
        from ...services.options_store import OptionsStore

        underlying = request.args.get("underlying_security") or "IBOVE Index"
        store = OptionsStore()
        query = OptionsQueryService(store=store)

        # ── Contratos ─────────────────────────────────────────────────────────
        contracts = store.list_contracts(underlying_security=underlying)
        active = [c for c in contracts if c.get("status") == "active"]
        eligible = [c for c in active if c.get("mvp_eligible")]

        # ── Snapshot por tier ─────────────────────────────────────────────────
        tier_stats: dict[str, dict] = {}
        all_rows_merged: list[dict] = []
        seen_ids: set = set()

        for tier_name in ("full", "structural", "liquid", "critical"):
            try:
                res = query.latest_snapshot(
                    universe_tier=tier_name, underlying_security=underlying, limit=5000
                )
                rows = res.get("rows", []) if isinstance(res, dict) else []
            except Exception:
                rows = []

            iv_count = sum(
                1 for r in rows if r.get("MODEL_IV") or r.get("EFF_IV") or r.get("IVOL_MID")
            )
            oi_count = sum(1 for r in rows if r.get("OPEN_INT") or r.get("OPT_OPEN_INTEREST"))
            greek_count = sum(
                1 for r in rows if r.get("MODEL_DELTA") or r.get("EFF_DELTA") or r.get("OPT_DELTA")
            )
            stale_count = sum(1 for r in rows if r.get("stale_flag"))
            market_ok = sum(1 for r in rows if r.get("market_ok"))

            tier_stats[tier_name] = {
                "rows": len(rows),
                "iv_coverage": iv_count,
                "oi_coverage": oi_count,
                "greek_coverage": greek_count,
                "stale_count": stale_count,
                "market_ok": market_ok,
                "iv_pct": round(100 * iv_count / max(len(rows), 1)),
                "oi_pct": round(100 * oi_count / max(len(rows), 1)),
                "greek_pct": round(100 * greek_count / max(len(rows), 1)),
                "ok_pct": round(100 * market_ok / max(len(rows), 1)),
            }

            for r in rows:
                uid = r.get("bloomberg_ticker") or r.get("option_id")
                if uid and uid not in seen_ids:
                    seen_ids.add(uid)
                    all_rows_merged.append(r)

        # ── Cobertura global (todos os tiers) ─────────────────────────────────
        n_total = len(all_rows_merged)
        n_iv = sum(
            1 for r in all_rows_merged if r.get("MODEL_IV") or r.get("EFF_IV") or r.get("IVOL_MID")
        )
        n_oi = sum(1 for r in all_rows_merged if r.get("OPEN_INT") or r.get("OPT_OPEN_INTEREST"))
        n_greeks = sum(
            1
            for r in all_rows_merged
            if r.get("MODEL_DELTA") or r.get("EFF_DELTA") or r.get("OPT_DELTA")
        )
        n_model_iv = sum(1 for r in all_rows_merged if r.get("MODEL_IV"))
        n_eff_iv = sum(1 for r in all_rows_merged if r.get("EFF_IV") and not r.get("MODEL_IV"))
        n_oplab_iv = sum(
            1
            for r in all_rows_merged
            if r.get("IVOL_MID") and not r.get("MODEL_IV") and not r.get("EFF_IV")
        )

        expiries = sorted({r.get("expiry_date") for r in all_rows_merged if r.get("expiry_date")})

        # ── B3 OI ──────────────────────────────────────────────────────────────
        try:
            b3_dates = store.list_b3_oi_dates()
            latest_b3_date = b3_dates[-1] if b3_dates else None
            b3_rows = store.load_b3_oi_rows(latest_b3_date) if latest_b3_date else []
            b3_symbols = [r.get("symbol") for r in b3_rows if r.get("symbol")]
        except Exception:
            b3_dates, latest_b3_date, b3_symbols = [], None, []

        # ── Model run ──────────────────────────────────────────────────────────
        try:
            latest_run = query.latest_model_run(underlying)
        except Exception:
            latest_run = None

        model_diag: dict = {}
        if latest_run:
            diag = latest_run.get("diagnostics") or {}
            model_diag = {
                "available": True,
                "captured_at": latest_run.get("captured_at"),
                "prepared_count": diag.get("prepared_count"),
                "strike_profiles": len(latest_run.get("strike_profiles") or []),
                "has_nonzero_gex": any(
                    abs(sp.get("gex_net") or 0) > 0
                    for sp in (latest_run.get("strike_profiles") or [])
                ),
                "has_nonzero_oi": any(
                    (sp.get("open_interest_total") or 0) > 0
                    for sp in (latest_run.get("strike_profiles") or [])
                ),
                "sign_convention": (latest_run.get("config") or {}).get("sign_convention"),
            }
        else:
            model_diag = {"available": False}

        return jsonify(
            {
                "success": True,
                "data": {
                    "underlying": underlying,
                    "contracts": {
                        "total": len(contracts),
                        "active": len(active),
                        "eligible": len(eligible),
                    },
                    "snapshot": {
                        "total_unique_options": n_total,
                        "expiries": expiries,
                        "expiry_count": len(expiries),
                        "iv_coverage": n_iv,
                        "iv_pct": round(100 * n_iv / max(n_total, 1)),
                        "model_iv_count": n_model_iv,
                        "eff_iv_count": n_eff_iv,
                        "oplab_iv_count": n_oplab_iv,
                        "oi_coverage": n_oi,
                        "oi_pct": round(100 * n_oi / max(n_total, 1)),
                        "greek_coverage": n_greeks,
                        "greek_pct": round(100 * n_greeks / max(n_total, 1)),
                    },
                    "tiers": tier_stats,
                    "b3_oi": {
                        "dates_available": len(b3_dates),
                        "latest_date": latest_b3_date,
                        "symbol_count": len(b3_symbols),
                    },
                    "model_run": model_diag,
                },
            }
        )
    except Exception as exc:
        return error_response(logger, status_code=500, exception=exc)
