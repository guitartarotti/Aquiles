from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from ...config import Config
from ...utils.logger import get_logger
from ..options_bloomberg_service import OptionsBloombergService
from ..options_modeling import OptionsModelingService
from ..options_snapshot_service import OptionsSnapshotService
from ..options_store import OptionsStore
from .cross_asset_level_mapping import build_cross_asset_level_map
from .distortion_band_model import build_distortion_band
from .dynamic_beta_model import build_dynamic_beta_model
from .input_preparation import (
    load_asset_configs,
    load_global_triangulation_config,
    prepare_global_inputs,
)
from .option_state_extractor import extract_asset_states
from .outputs import build_global_output
from .regime_classifier import classify_global_regime
from .structural_score import build_structural_scores

logger = get_logger("mirofish.options_global.service")


class OptionsGlobalTriangulationService:
    def __init__(
        self,
        store: OptionsStore | None = None,
        bloomberg: OptionsBloombergService | None = None,
        local_modeling: OptionsModelingService | None = None,
    ):
        self.store = store or OptionsStore()
        self.bloomberg = bloomberg or OptionsBloombergService()
        self.snapshot_service = OptionsSnapshotService(store=self.store, bloomberg=self.bloomberg)
        self.local_modeling = local_modeling or OptionsModelingService(store=self.store, bloomberg=self.bloomberg)

    def _ensure_local_model_run(
        self,
        underlying_security: str,
        refresh_local_model: bool,
        max_age_seconds: int,
        now: datetime,
    ) -> dict:
        payload = self.store.read_latest_model_run(underlying_security) or {}

        def model_is_stale(run_payload: dict) -> bool:
            if not run_payload or not run_payload.get("captured_at"):
                return True
            try:
                captured_at = datetime.fromisoformat(str(run_payload["captured_at"]).replace("Z", "+00:00")).astimezone(timezone.utc)
                return (now - captured_at).total_seconds() > max_age_seconds
            except Exception:
                return True

        needs_refresh = refresh_local_model or model_is_stale(payload)
        if not needs_refresh:
            return payload

        try:
            return self.local_modeling.run_latest(underlying_security, persist=True)
        except Exception as exc:
            error_text = str(exc)
            if "No snapshot available" not in error_text:
                raise
            logger.info("No snapshot available for %s; collecting structural snapshot before modeling", underlying_security)
            self.snapshot_service.collect_underlying_snapshot(
                underlying_security=underlying_security,
                include_structural=True,
                include_liquid=False,
                include_critical=False,
                include_ticks=False,
            )
            return self.local_modeling.run_latest(
                underlying_security=underlying_security,
                universe_tier="structural",
                persist=True,
            )

    def _load_or_refresh_local_runs(
        self,
        underlying_security: str,
        refresh_local_model: bool = False,
    ) -> tuple[dict, dict[str, dict]]:
        model_runs_by_underlying: dict[str, dict] = {}
        asset_configs = load_asset_configs()
        required_underlyings = {
            str(config.model_underlying or "").strip()
            for config in asset_configs
            if config.model_underlying
        }
        required_underlyings.add(underlying_security)
        max_age_seconds = max(int(Config.OPTIONS_GLOBAL_TRIANGULATION_LOCAL_MODEL_MAX_AGE_SECONDS), 0)
        now = datetime.now(timezone.utc)

        for item in required_underlyings:
            if not item:
                continue
            payload: dict = {}
            try:
                payload = self._ensure_local_model_run(
                    item,
                    refresh_local_model=refresh_local_model,
                    max_age_seconds=max_age_seconds,
                    now=now,
                )
            except Exception:
                logger.exception("Failed to refresh local model run for %s", item)
            if payload:
                model_runs_by_underlying[item] = payload

        primary_run = model_runs_by_underlying.get(underlying_security) or {}
        if not primary_run:
            raise ValueError(f"No local options model run available for {underlying_security}")
        return primary_run, model_runs_by_underlying

    def run_latest(
        self,
        underlying_security: str | None = None,
        refresh_local_model: bool = False,
        persist: bool = True,
    ) -> dict:
        if not Config.OPTIONS_GLOBAL_TRIANGULATION_ENABLE:
            raise ValueError("Global triangulation is disabled")

        underlying = str(underlying_security or "IBOVE Index").strip()
        run_config = load_global_triangulation_config()
        local_model_run, model_runs_by_underlying = self._load_or_refresh_local_runs(
            underlying,
            refresh_local_model=refresh_local_model,
        )
        prepared_inputs = prepare_global_inputs(
            local_model_run=local_model_run,
            model_runs_by_underlying=model_runs_by_underlying,
            bloomberg_service=self.bloomberg,
            run_config=run_config,
        )
        dynamic_model = build_dynamic_beta_model(prepared_inputs, run_config)
        distortion_band = build_distortion_band(dynamic_model, run_config.distortion_sigma_multiplier)
        asset_states = extract_asset_states(prepared_inputs)
        cross_asset_level_map = build_cross_asset_level_map(
            prepared_inputs=prepared_inputs,
            dynamic_model=dynamic_model,
            asset_states=asset_states,
            run_config=run_config,
        )
        structural_scores = build_structural_scores(asset_states, dynamic_model, distortion_band)
        regime = classify_global_regime(
            dynamic_model=dynamic_model,
            distortion_band=distortion_band,
            structural_scores=structural_scores,
            asset_states=asset_states,
        )
        summary = build_global_output(
            underlying_security=underlying,
            local_model_run=local_model_run,
            prepared_inputs=prepared_inputs,
            dynamic_model=dynamic_model,
            distortion_band=distortion_band,
            asset_states=asset_states,
            cross_asset_level_map=cross_asset_level_map,
            structural_scores=structural_scores,
            regime=regime,
        )

        captured_at = datetime.now(timezone.utc).isoformat()
        run_id = hashlib.sha1(
            f"global|{underlying}|{local_model_run.get('run_id')}|{captured_at}".encode("utf-8")
        ).hexdigest()
        payload = {
            "run_id": run_id,
            "captured_at": captured_at,
            "session_date": str(local_model_run.get("session_date") or captured_at[:10]),
            "underlying_security": underlying,
            "config": {
                "bar_interval_minutes": run_config.bar_interval_minutes,
                "lookback_hours": run_config.lookback_hours,
                "min_points": run_config.min_points,
                "ewma_alpha": run_config.ewma_alpha,
                "corr_short_window": run_config.corr_short_window,
                "corr_smooth_window": run_config.corr_smooth_window,
                "distortion_sigma_multiplier": run_config.distortion_sigma_multiplier,
                "distortion_weight": run_config.distortion_weight,
                "structural_weight": run_config.structural_weight,
                "corr_weight": run_config.corr_weight,
                "level_cluster_points": run_config.level_cluster_points,
                "level_match_points": run_config.level_match_points,
                "min_corr_for_mapping": run_config.min_corr_for_mapping,
                "vol_band_sigma": run_config.vol_band_sigma,
                "top_mapped_levels": run_config.top_mapped_levels,
            },
            "source": {
                "local_model_run_id": local_model_run.get("run_id"),
                "local_model_captured_at": local_model_run.get("captured_at"),
            },
            "prepared_inputs": {
                "generated_at": prepared_inputs.get("generated_at"),
                "asset_count": len(prepared_inputs.get("assets") or []),
                "reference_status": prepared_inputs.get("reference_status") or {},
                "assets": [
                    {
                        "slug": item.get("slug"),
                        "label": item.get("label"),
                        "support_level": item.get("support_level"),
                        "selected_security": item.get("selected_security"),
                        "point_count": item.get("point_count"),
                        "state_quality_score": item.get("state_quality_score"),
                    }
                    for item in (prepared_inputs.get("assets") or [])
                ],
            },
            "dynamic_beta_model": dynamic_model,
            "distortion_band": distortion_band,
            "cross_asset_level_map": cross_asset_level_map,
            "structural_scores": structural_scores,
            "regime": regime,
            "summary": summary,
        }
        if persist:
            payload["persisted"] = self.store.write_global_run(payload)
        return payload

    def read_latest_run(self, underlying_security: str) -> dict | None:
        return self.store.read_latest_global_run(underlying_security)

    def read_run(self, run_id: str) -> dict | None:
        return self.store.read_global_run(run_id)
