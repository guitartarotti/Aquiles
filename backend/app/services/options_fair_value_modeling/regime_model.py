from __future__ import annotations

from typing import Any

import pandas as pd


def _latest(frame: pd.DataFrame, column: str) -> float:
    if column not in frame.columns or frame.empty:
        return 0.0
    try:
        value = float(frame.iloc[-1][column])
    except Exception:
        return 0.0
    if value != value:
        return 0.0
    return value


def classify_market_regime(
    frame: pd.DataFrame,
    feature_meta: dict[str, dict[str, Any]],
    options_overlay: dict[str, Any],
    global_overlay: dict[str, Any],
    us_rates_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def z(name: str) -> float:
        meta = feature_meta.get(name) or {}
        return _latest(frame, str(meta.get("z_column") or ""))

    credit_stress = (z("cdx_hy") + z("cdx_em") + z("brazil_cds") + z("embiv")) / 4.0
    global_equities = (z("spx_proxy") + z("russell") + z("developed_markets")) / 3.0
    local_rates = (z("di_short") + z("di_long") + z("di_slope")) / 3.0
    fx_pressure = z("usdbrl")
    commodity_impulse = z("oil")
    us_rates_context = us_rates_context or {}
    ois_support = float(us_rates_context.get("ois_support_score") or 0.0)
    funding_pressure = float(us_rates_context.get("funding_pressure_score") or 0.0)
    us_rates_state = str(us_rates_context.get("summary_state") or "")

    regime = "mixed_transition"
    confidence = 0.35
    rationale: list[str] = []

    if options_overlay.get("state") == "gamma_compression":
        regime = "compressed_gamma_regime"
        confidence = max(confidence, 0.62)
        rationale.append("Opcoes indicam compressao de gamma em torno do dealer target.")
    elif options_overlay.get("state", "").startswith("gamma_release"):
        regime = "release_regime"
        confidence = max(confidence, 0.60)
        rationale.append("Overlay de opcoes mostra soltura de hedge nas regioes de aceleracao.")
    elif credit_stress > 0.8 and fx_pressure > 0.6 and local_rates > 0.4:
        regime = "stress_brasil"
        confidence = 0.76
        rationale.append("Credito, cambio e curva DI apontam stress local/Brasil.")
    elif global_equities < -0.75 and credit_stress > 0.45:
        regime = "risk_off_global"
        confidence = 0.74
        rationale.append("Basket global e credito caminham juntos em regime de risk-off.")
    elif global_equities > 0.75 and credit_stress < -0.20:
        regime = "risk_on_global"
        confidence = 0.74
        rationale.append("Global equities avancam com alivio de credito.")
    elif funding_pressure > 0.55:
        regime = "funding_deterioration"
        confidence = 0.77
        rationale.append("OIS, MOVE, DXY e spread Treasury/OIS apontam aperto financeiro global.")
    elif us_rates_state == "flight_to_quality":
        regime = "flight_to_quality"
        confidence = 0.72
        rationale.append("Treasury cai, mas OIS nao acompanha; leitura sugere flight-to-quality com funding mais fraco.")
    elif ois_support > 0.45 and global_equities >= -0.15:
        regime = "dovish_liquidity_support"
        confidence = 0.69
        rationale.append("Curva OIS alivia e melhora a leitura de liquidez para EM/equities.")
    elif commodity_impulse > 0.8 and global_equities >= 0:
        regime = "commodity_led"
        confidence = 0.61
        rationale.append("Commodities lideram o movimento do indice.")

    if global_overlay.get("state") in {"global_breakout_confirmed_up", "global_breakout_confirmed_down"}:
        confidence = max(confidence, 0.68)
        rationale.append("Overlay global reforca regime de ruptura.")
    elif global_overlay.get("state") in {"local_ahead_mean_reversion", "local_lagging_catchup"}:
        rationale.append("Overlay global sugere distorcao com vies de convergencia.")

    return {
        "market_regime": regime,
        "market_regime_confidence": min(max(confidence, 0.1), 0.95),
        "scores": {
            "credit_stress": credit_stress,
            "global_equities": global_equities,
            "local_rates": local_rates,
            "fx_pressure": fx_pressure,
            "commodity_impulse": commodity_impulse,
            "ois_support": ois_support,
            "funding_pressure": funding_pressure,
        },
        "rationale": rationale,
    }
