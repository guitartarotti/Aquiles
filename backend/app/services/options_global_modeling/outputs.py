from __future__ import annotations

from typing import Any


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except Exception:
        return default


def build_global_output(
    *,
    underlying_security: str,
    local_model_run: dict[str, Any],
    prepared_inputs: dict[str, Any],
    dynamic_model: dict[str, Any],
    distortion_band: dict[str, Any],
    asset_states: list[dict[str, Any]],
    cross_asset_level_map: dict[str, Any],
    structural_scores: dict[str, Any],
    regime: dict[str, Any],
) -> dict[str, Any]:
    local_fairness = distortion_band.get("local_fairness") or "justo"
    absorption = _safe_float(regime.get("global_absorption_score"), 0.0)
    breakout = _safe_float(regime.get("global_breakout_score"), 0.0)
    zone_alignment = structural_scores.get("zone_alignment") or "nao"
    confluence_score = _safe_float(cross_asset_level_map.get("global_confluence_score"), 0.0)
    strongest_cluster = cross_asset_level_map.get("strongest_cluster") or {}
    nearest_upside_cluster = cross_asset_level_map.get("nearest_upside_cluster") or {}
    nearest_downside_cluster = cross_asset_level_map.get("nearest_downside_cluster") or {}

    def bucket_label(score: float) -> str:
        if score >= 70:
            return "alta"
        if score >= 45:
            return "média"
        return "baixa"

    asset_rows = []
    relationship_map = {
        str(item.get("slug")): item
        for item in (dynamic_model.get("relationships") or [])
        if item.get("slug")
    }
    score_map = {
        str(item.get("asset")): item
        for item in (structural_scores.get("per_asset_scores") or [])
        if item.get("asset")
    }
    for asset in asset_states:
        rel = relationship_map.get(str(asset.get("asset")), {})
        score_row = score_map.get(str(asset.get("asset")), {})
        asset_rows.append(
            {
                "asset": asset.get("asset"),
                "label": asset.get("label"),
                "support_level": asset.get("support_level"),
                "security": asset.get("security"),
                "model_underlying": asset.get("model_underlying"),
                "dealer_zone_source_underlying": asset.get("dealer_zone_source_underlying"),
                "dealer_zone_source_security": asset.get("dealer_zone_source_security"),
                "dealer_zone_source_mode": asset.get("dealer_zone_source_mode"),
                "spot": asset.get("spot"),
                "return_intraday": asset.get("return_intraday"),
                "latest_return": asset.get("latest_return"),
                "realized_vol_intraday": asset.get("realized_vol_intraday"),
                "beta_dynamic": rel.get("beta", 1.0 if asset.get("asset") == "local_index" else 0.0),
                "corr_short": rel.get("corr_short", 1.0 if asset.get("asset") == "local_index" else 0.0),
                "corr_smoothed": rel.get("corr_smoothed", 1.0 if asset.get("asset") == "local_index" else 0.0),
                "dealer_core": asset.get("dealer_core"),
                "pinning_band_low": asset.get("pinning_band_low"),
                "pinning_band_high": asset.get("pinning_band_high"),
                "acceleration_level": asset.get("acceleration_level"),
                "zero_pressure": asset.get("zero_pressure"),
                "gex_total": asset.get("gex_total"),
                "vex_total": asset.get("vex_total"),
                "cex_total": asset.get("cex_total"),
                "skew_dominant": asset.get("iv_skew_state"),
                "iv_skew_numeric": asset.get("iv_skew_numeric"),
                "vol_deviation_score": asset.get("vol_deviation_score"),
                "dealer_regime_state": asset.get("dealer_regime_state"),
                "dealer_regime_confidence": asset.get("dealer_regime_confidence"),
                "score_local_absorption": score_row.get("absorption_score", asset.get("local_absorption_score")),
                "score_local_breakout": score_row.get("breakout_score", asset.get("local_breakout_score")),
                "state_quality_score": asset.get("state_quality_score"),
            }
        )

    return {
        "underlying_security": underlying_security,
        "local_model_run_id": local_model_run.get("run_id"),
        "local_model_captured_at": local_model_run.get("captured_at"),
        "bar_interval_minutes": prepared_inputs.get("bar_interval_minutes"),
        "lookback_hours": prepared_inputs.get("lookback_hours"),
        "global_beta_now": dynamic_model.get("global_beta_now"),
        "global_corr_short": dynamic_model.get("global_corr_short"),
        "global_corr_smoothed": dynamic_model.get("global_corr_smoothed"),
        "basket_expected_return": dynamic_model.get("basket_expected_return"),
        "local_return": dynamic_model.get("local_return"),
        "distortion_value": distortion_band.get("distortion_value"),
        "distortion_sigma": distortion_band.get("distortion_sigma"),
        "distortion_zscore": distortion_band.get("distortion_zscore"),
        "distortion_band_low": distortion_band.get("distortion_band_low"),
        "distortion_band_high": distortion_band.get("distortion_band_high"),
        "distortion_regime": distortion_band.get("distortion_regime"),
        "global_absorption_score": regime.get("global_absorption_score"),
        "global_breakout_score": regime.get("global_breakout_score"),
        "global_sync_score": structural_scores.get("global_sync_score"),
        "global_structural_score": structural_scores.get("structural_gamma_vol_score"),
        "global_regime": regime.get("global_regime"),
        "global_regime_confidence": regime.get("global_regime_confidence"),
        "cross_asset_confluence_score": confluence_score,
        "cross_asset_strongest_cluster": strongest_cluster,
        "cross_asset_nearest_upside_cluster": nearest_upside_cluster,
        "cross_asset_nearest_downside_cluster": nearest_downside_cluster,
        "alignment_global_dealer_zones": zone_alignment,
        "top_explaining_assets": dynamic_model.get("top_explaining_assets") or [],
        "asset_states": asset_rows,
        "desk_summary": {
            "indice_local_vs_global": local_fairness,
            "absorcao_global": bucket_label(absorption),
            "ruptura_global": bucket_label(breakout),
            "alinhamento_zonas_dealer": zone_alignment,
            "ativos_que_mais_explicam": [item.get("label") for item in (dynamic_model.get("top_explaining_assets") or [])],
            "desvios_casados": "sim" if confluence_score >= 60 else "parcial" if confluence_score >= 35 else "nao",
        },
        "diagnostics": {
            "asset_count": len(asset_rows),
            "active_relationships": len([item for item in (dynamic_model.get("relationships") or []) if item.get("active")]),
            "reference_status": prepared_inputs.get("reference_status") or {},
        },
    }
