from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from typing import Any

from ...config import Config
from ...utils.logger import get_logger
from ..options_store import OptionsStore
from .asset_regime_engine import build_asset_regimes
from .factor_preparation import load_factor_definitions
from .global_regime_engine import build_global_regime
from .market_state_engine import build_market_state
from .nonlinear_dependence_engine import build_nonlinear_dependence
from .price_making_engine import build_leg_price_making
from .regime_state_machine import run_regime_state_machine

logger = get_logger("aquiles.options_fair_value.regime_price_making")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _deep_copy_json(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


class RegimePriceMakingService:
    def __init__(self, store: OptionsStore | None = None):
        self.store = store or OptionsStore()

    @staticmethod
    def _feature_flags() -> dict[str, bool]:
        return {
            "enable_asset_regime_engine": bool(Config.OPTIONS_ASSET_REGIME_ENGINE_ENABLE),
            "enable_nonlinear_dependence_engine": bool(Config.OPTIONS_NONLINEAR_DEPENDENCE_ENGINE_ENABLE),
            "enable_price_making_engine": bool(Config.OPTIONS_PRICE_MAKING_ENGINE_ENABLE),
            "enable_market_state_engine": bool(Config.OPTIONS_MARKET_STATE_ENGINE_ENABLE),
            "enable_global_regime_engine": bool(Config.OPTIONS_GLOBAL_REGIME_ENGINE_ENABLE),
        }

    @staticmethod
    def _context_state_path() -> str:
        return os.path.join(Config.MACRO_DATA_DIR, "options_heatmap_context.json")

    def _load_context_state(self) -> dict[str, Any]:
        path = self._context_state_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle) or {}
        except Exception:
            logger.debug("Failed to load options heatmap context for regime engine", exc_info=True)
            return {}

    @staticmethod
    def _normalize_leg_payloads(summary: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        core_legs = _deep_copy_json(summary.get("core_legs") or {})
        shadow_legs = _deep_copy_json(summary.get("shadow_legs") or {})
        live_rows = {
            str(item.get("factor") or "").strip(): dict(item or {})
            for item in (summary.get("live_factor_rows") or [])
            if str(item.get("factor") or "").strip()
        }
        factor_contributions = (((summary.get("factor_ranking") or [])) or [])
        factor_map = {
            str(item.get("factor") or "").strip(): dict(item or {})
            for item in factor_contributions
            if str(item.get("factor") or "").strip()
        }
        if "curve_medium_long" not in core_legs:
            contribution = _safe_float(((factor_map.get("di_medium_long") or {}).get("contribution_points")))
            score = _safe_float((live_rows.get("di_medium_long") or {}).get("feature_zscore"))
            current_px = _safe_float(summary.get("current_future_price"))
            if contribution or score:
                core_legs["curve_medium_long"] = {
                    "key": "curve_medium_long",
                    "name": "curve_medium_long",
                    "label": "Core Curve Medium Long",
                    "score": score,
                    "direction": "bullish" if contribution > 0 else "bearish" if contribution < 0 else "neutral",
                    "strength": min(abs(score) * 40.0, 100.0),
                    "contribution_points": contribution,
                    "confidence": 0.55,
                    "enabled": True,
                    "implied_fair_value_xb1": (current_px + contribution) if current_px else None,
                    "explanation": "Perna dedicada ao médio-longo da curva DI.",
                }
        return core_legs, shadow_legs

    def _load_observations(self, underlying_security: str) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        latest_run = self.store.read_latest_fair_value_run(underlying_security) or {}
        if not latest_run:
            raise ValueError(f"No fair value run available for {underlying_security}")
        context_state = self._load_context_state()
        context_samples = [
            dict(item or {})
            for item in (((context_state.get("fair_value_history") or {}).get("samples") or []))
        ]
        run_history = self.store.list_recent_fair_value_runs(underlying_security, limit=320)
        merged_by_ts: dict[str, dict[str, Any]] = {}
        for run in run_history:
            summary = dict(run.get("summary") or {})
            core_legs, shadow_legs = self._normalize_leg_payloads(summary)
            ts = str(run.get("captured_at") or summary.get("timestamp") or "")
            if not ts:
                continue
            merged_by_ts[ts] = {
                "timestamp": ts,
                "xb1_last": _safe_float(summary.get("xb1_last") or summary.get("current_future_price")),
                "ibov_last": _safe_float(summary.get("ibov_last") or summary.get("current_spot_price")),
                "core_fair_value_xb1": _safe_float(summary.get("core_fair_value_xb1")),
                "quality_adjusted_fair_value_xb1": _safe_float(summary.get("quality_adjusted_fair_value_xb1")),
                "band_low": _safe_float(summary.get("fair_value_band_low")),
                "band_high": _safe_float(summary.get("fair_value_band_high")),
                "confidence": _safe_float(summary.get("confidence")),
                "risk_quality_score": _safe_float(summary.get("risk_quality_score")),
                "core_shadow_alignment": _safe_float(summary.get("core_shadow_alignment")),
                "divergence_score": _safe_float(summary.get("divergence_score")),
                "implicit_sentiment": summary.get("implicit_sentiment"),
                "core_legs": core_legs,
                "shadow_legs": shadow_legs,
                "live_factor_rows": summary.get("live_factor_rows") or [],
            }
        for sample in context_samples:
            ts = str(sample.get("captured_at") or "")
            if not ts:
                continue
            base = merged_by_ts.get(ts) or {}
            sample_core = _deep_copy_json(sample.get("core_legs") or base.get("core_legs") or {})
            sample_shadow = _deep_copy_json(sample.get("shadow_legs") or base.get("shadow_legs") or {})
            merged_by_ts[ts] = {
                "timestamp": ts,
                "xb1_last": _safe_float(sample.get("current_future_price"), _safe_float(base.get("xb1_last"))),
                "ibov_last": _safe_float(sample.get("current_spot_price"), _safe_float(base.get("ibov_last"))),
                "core_fair_value_xb1": _safe_float(sample.get("core_fair_value_xb1"), _safe_float(base.get("core_fair_value_xb1"))),
                "quality_adjusted_fair_value_xb1": _safe_float(sample.get("quality_adjusted_fair_value_xb1"), _safe_float(base.get("quality_adjusted_fair_value_xb1"))),
                "band_low": _safe_float(sample.get("fair_value_band_low"), _safe_float(base.get("band_low"))),
                "band_high": _safe_float(sample.get("fair_value_band_high"), _safe_float(base.get("band_high"))),
                "confidence": _safe_float(sample.get("confidence"), _safe_float(base.get("confidence"))),
                "risk_quality_score": _safe_float(sample.get("risk_quality_score"), _safe_float(base.get("risk_quality_score"))),
                "core_shadow_alignment": _safe_float(sample.get("core_shadow_alignment"), _safe_float(base.get("core_shadow_alignment"))),
                "divergence_score": _safe_float(sample.get("divergence_score"), _safe_float(base.get("divergence_score"))),
                "implicit_sentiment": sample.get("implicit_sentiment") or base.get("implicit_sentiment"),
                "core_legs": sample_core,
                "shadow_legs": sample_shadow,
                "live_factor_rows": base.get("live_factor_rows") or [],
            }
        observations = sorted(merged_by_ts.values(), key=lambda item: str(item.get("timestamp") or ""))
        return observations, latest_run, context_state

    @staticmethod
    def _enrich_price_series(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not observations:
            return []
        first_xb1 = _safe_float(observations[0].get("xb1_last"), 0.0)
        first_ibov = _safe_float(observations[0].get("ibov_last"), 0.0)
        previous_xb1 = None
        previous_ibov = None
        rolling_returns: list[float] = []
        enriched = []
        for item in observations:
            row = dict(item)
            xb1_last = _safe_float(row.get("xb1_last"), 0.0)
            ibov_last = _safe_float(row.get("ibov_last"), 0.0)
            xb1_return_intraday = math.log(xb1_last / first_xb1) if xb1_last > 0 and first_xb1 > 0 else 0.0
            ibov_return_intraday = math.log(ibov_last / first_ibov) if ibov_last > 0 and first_ibov > 0 else 0.0
            xb1_log_return = math.log(xb1_last / previous_xb1) if xb1_last > 0 and previous_xb1 and previous_xb1 > 0 else 0.0
            ibov_log_return = math.log(ibov_last / previous_ibov) if ibov_last > 0 and previous_ibov and previous_ibov > 0 else 0.0
            rolling_returns.append(xb1_log_return)
            recent_returns = rolling_returns[-30:]
            xb1_rolling_vol = math.sqrt(sum(value * value for value in recent_returns) / max(len(recent_returns), 1))
            row["xb1_return_intraday"] = xb1_return_intraday
            row["ibov_return_intraday"] = ibov_return_intraday
            row["xb1_log_return"] = xb1_log_return
            row["ibov_log_return"] = ibov_log_return
            row["xb1_rolling_volatility"] = xb1_rolling_vol
            row["ibov_rolling_volatility"] = abs(ibov_log_return)
            row["xb1_return"] = xb1_log_return
            enriched.append(row)
            previous_xb1 = xb1_last or previous_xb1
            previous_ibov = ibov_last or previous_ibov
        return enriched

    @staticmethod
    def _build_factor_definition_map() -> dict[str, dict[str, Any]]:
        return {
            definition.name: definition.__dict__
            for definition in load_factor_definitions()
        }

    @staticmethod
    def _build_factor_history(runs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        history: dict[str, list[dict[str, Any]]] = {}
        for run in runs:
            summary = dict(run.get("summary") or {})
            captured_at = str(run.get("captured_at") or summary.get("timestamp") or "")
            for row in (summary.get("live_factor_rows") or []):
                factor = str((row or {}).get("factor") or "").strip()
                if not factor:
                    continue
                item = dict(row or {})
                item.setdefault("timestamp", captured_at)
                history.setdefault(factor, []).append(item)
        return history

    @staticmethod
    def _core_score_map(core_legs: dict[str, dict[str, Any]]) -> dict[str, float]:
        return {
            key: _safe_float((value or {}).get("score"))
            for key, value in (core_legs or {}).items()
        }

    @staticmethod
    def _shadow_score_map(shadow_legs: dict[str, dict[str, Any]]) -> dict[str, float]:
        return {
            key: _safe_float((value or {}).get("score"))
            for key, value in (shadow_legs or {}).items()
        }

    @staticmethod
    def _price_acceptance_state(current: dict[str, Any]) -> str:
        price = _safe_float(current.get("xb1_last"))
        core_fv = _safe_float(current.get("core_fair_value_xb1"))
        qadj = _safe_float(current.get("quality_adjusted_fair_value_xb1"))
        band_low = _safe_float(current.get("band_low"))
        band_high = _safe_float(current.get("band_high"))
        if price and band_low and band_high:
            if price > band_high:
                return "accepted_above_band"
            if price < band_low:
                return "accepted_below_band"
            return "inside_band"
        if price and core_fv and qadj:
            if price > max(core_fv, qadj):
                return "above_fair_value"
            if price < min(core_fv, qadj):
                return "below_fair_value"
        return "around_fair_value"

    def build_latest(self, underlying_security: str = "IBOVE Index", persist: bool = True) -> dict[str, Any]:
        if not Config.OPTIONS_REGIME_PRICE_MAKING_ENABLE:
            raise ValueError("RegimePriceMakingEngine is disabled")

        try:
            observations, latest_run, context_state = self._load_observations(underlying_security)
            observations = self._enrich_price_series(observations)
            if not observations:
                raise ValueError("No observations available for regime price making")
            current = dict(observations[-1])
            summary = dict((latest_run.get("summary") or {}))
            core_legs, shadow_legs = self._normalize_leg_payloads(summary)
            current["core_legs"] = current.get("core_legs") or core_legs
            current["shadow_legs"] = current.get("shadow_legs") or shadow_legs

            factor_defs = self._build_factor_definition_map()
            factor_history = self._build_factor_history(self.store.list_recent_fair_value_runs(underlying_security, limit=260))
            current_live_rows = summary.get("live_factor_rows") or []
            xb1_return_z = _safe_float(current.get("xb1_log_return")) / max(_safe_float(current.get("xb1_rolling_volatility"), 0.0001), 0.0001)
            asset_package = build_asset_regimes(
                current_rows=current_live_rows,
                history_by_factor=factor_history,
                factor_definitions=factor_defs,
                xb1_signed_return=xb1_return_z,
            )

            core_score_map = self._core_score_map(current.get("core_legs") or {})
            shadow_score_map = self._shadow_score_map(current.get("shadow_legs") or {})

            leg_outputs: dict[str, dict[str, Any]] = {}
            price_making_scores: dict[str, float] = {}
            warnings: list[str] = []
            price = _safe_float(current.get("xb1_last"))
            core_fv = _safe_float(current.get("core_fair_value_xb1"))
            qadj = _safe_float(current.get("quality_adjusted_fair_value_xb1"))
            band_low = _safe_float(current.get("band_low"))
            band_high = _safe_float(current.get("band_high"))
            price_vs_core_fv = ((price - core_fv) / max(abs(core_fv), 1.0)) if price and core_fv else 0.0
            price_vs_quality_fv = ((price - qadj) / max(abs(qadj), 1.0)) if price and qadj else 0.0
            if price and band_low and band_high:
                midpoint = (band_low + band_high) / 2.0
                half_width = max(abs(band_high - band_low) / 2.0, 1.0)
                price_vs_band = (price - midpoint) / half_width
            else:
                price_vs_band = 0.0
            dislocation_zscore = ((price - core_fv) / max(abs(band_high - band_low) / 2.0, 1.0)) if price and core_fv and band_low and band_high else 0.0

            for leg_type, mapping in (("core", current.get("core_legs") or {}), ("shadow", current.get("shadow_legs") or {})):
                for leg_key, leg_payload in mapping.items():
                    dependence = build_nonlinear_dependence(
                        observations=observations,
                        leg_key=leg_key,
                        leg_type=leg_type,
                    )
                    leg_output = build_leg_price_making(
                        leg_key=leg_key,
                        leg_type=leg_type,
                        leg_payload=dict(leg_payload or {}),
                        dependence=dependence,
                        xb1_return_z=xb1_return_z,
                        dislocation_zscore=dislocation_zscore,
                        price_vs_core_fv=price_vs_core_fv,
                        price_vs_quality_fv=price_vs_quality_fv,
                        price_vs_band=price_vs_band,
                        microstructure_context={"flow_confirmation": 0.35},
                    )
                    leg_output["type"] = leg_type
                    leg_output["name"] = leg_key
                    leg_output["label"] = (
                        (leg_payload or {}).get("label")
                        or (leg_payload or {}).get("name")
                        or leg_key
                    )
                    leg_outputs[leg_key] = leg_output
                    price_making_scores[leg_key] = _safe_float(leg_output.get("price_making_score"))

            dominant_price_maker_key = max(price_making_scores.items(), key=lambda item: item[1])[0] if price_making_scores else None
            theoretical_map = {
                key: abs(_safe_float((payload or {}).get("contribution_points")))
                for key, payload in (current.get("core_legs") or {}).items()
            }
            if "curve_medium_long" in current.get("core_legs", {}):
                theoretical_map["curve_medium_long"] = abs(_safe_float(((current.get("core_legs") or {}).get("curve_medium_long") or {}).get("contribution_points")))
            dominant_theoretical_driver = max(theoretical_map.items(), key=lambda item: item[1])[0] if theoretical_map else dominant_price_maker_key
            ignored_candidates = [
                (key, payload)
                for key, payload in leg_outputs.items()
                if str(payload.get("status") or "") == "ignored"
            ]
            ignored_driver = max(
                ignored_candidates,
                key=lambda item: abs(_safe_float(item[1].get("contribution_points"))),
            )[0] if ignored_candidates else None

            top_price_leg = leg_outputs.get(dominant_price_maker_key or "") or {}
            dominant_theoretical = leg_outputs.get(dominant_theoretical_driver or "") or {}
            price_making_quality = _clamp(sum(sorted(price_making_scores.values(), reverse=True)[:3]) / 300.0, 0.0, 1.0)
            macro_to_price_alignment = _clamp(
                (0.5 * _safe_float(current.get("core_shadow_alignment"), 0.0))
                + (0.5 * (_safe_float(top_price_leg.get("alignment")) + 1.0) / 2.0),
                0.0,
                1.0,
            )

            market_state = build_market_state(
                dominant_price_making_score=_safe_float(top_price_leg.get("price_making_score")) / 100.0,
                dominant_theoretical_strength=_safe_float(dominant_theoretical.get("theoretical_strength")),
                xb1_momentum_score=_clamp(abs(xb1_return_z), 0.0, 1.0),
                dependence_increase=_clamp(_safe_float(top_price_leg.get("nonlinear_dependence_score")), 0.0, 1.0),
                band_acceptance_score=_clamp(abs(price_vs_band), 0.0, 1.0),
                flow_confirmation_score=0.35,
                persistence_score=_clamp(abs(_safe_float(top_price_leg.get("pressure_score"))) / 2.5, 0.0, 1.0),
                decline_in_price_making_score=_clamp(max(0.0, 0.75 - (_safe_float(top_price_leg.get("price_making_score")) / 100.0)), 0.0, 1.0),
                decline_in_elasticity=_clamp(max(0.0, 0.40 - abs(_safe_float(top_price_leg.get("price_elasticity")))), 0.0, 1.0),
                failed_breakout_score=_clamp(abs(price_vs_band) if abs(xb1_return_z) < 0.10 else 0.15, 0.0, 1.0),
                volume_without_progress=0.20,
                extreme_dislocation_score=_clamp(abs(dislocation_zscore) / 3.0, 0.0, 1.0),
                low_price_response=_clamp(max(0.0, 0.45 - abs(xb1_return_z)), 0.0, 1.0),
                proximity_to_fv_band_or_gamma=_clamp(1.0 - min(abs(price_vs_band), 1.0), 0.0, 1.0),
                failed_continuation=_clamp(max(0.0, abs(_safe_float(dominant_theoretical.get("alignment"))) - abs(xb1_return_z)), 0.0, 1.0),
                low_factor_alignment=_clamp(1.0 - _safe_float(current.get("core_shadow_alignment"), 0.0), 0.0, 1.0),
                low_realized_volatility=_clamp(max(0.0, 0.30 - _safe_float(current.get("xb1_rolling_volatility")) * 100.0), 0.0, 1.0),
                no_dominant_price_maker=_clamp(max(0.0, 0.55 - (_safe_float(top_price_leg.get("price_making_score")) / 100.0)), 0.0, 1.0),
                mixed_leg_signals=_clamp(_safe_float(current.get("divergence_score"), 0.0), 0.0, 1.0),
                shadow_against_core=_clamp(1.0 - _safe_float(current.get("core_shadow_alignment"), 0.0), 0.0, 1.0),
                fv_or_vwap_recross=_clamp(abs(price_vs_core_fv) < 0.0015 and abs(xb1_return_z) > 0.05, 0.0, 1.0),
                new_opposite_price_maker=_clamp(1.0 if ignored_driver and ignored_driver != dominant_price_maker_key else 0.0, 0.0, 1.0),
                flow_reversal=_clamp(max(0.0, -_safe_float(top_price_leg.get("alignment"))), 0.0, 1.0),
                divergence_pressure=_clamp(_safe_float(current.get("divergence_score"), 0.0), 0.0, 1.0),
                latent_stress_pressure=_clamp(max(shadow_score_map.get("funding", 0.0), shadow_score_map.get("volatility", 0.0)), 0.0, 1.0),
            )

            global_regime = build_global_regime(
                core_scores=core_score_map,
                shadow_scores=shadow_score_map,
                price_making_scores=price_making_scores,
                market_state=market_state,
                risk_quality_score=_safe_float(current.get("risk_quality_score"), 0.5),
                dislocation_zscore=dislocation_zscore,
                price_vs_core_fv=price_vs_core_fv,
                price_vs_quality_fv=price_vs_quality_fv,
                core_shadow_alignment=_safe_float(current.get("core_shadow_alignment"), 0.5),
                divergence_score=_safe_float(current.get("divergence_score"), 0.0),
            )

            previous_state = ((self.store.read_latest_regime_price_making_run(underlying_security) or {}).get("regime_snapshot") or {})
            regime_snapshot = run_regime_state_machine(
                regime_scores=global_regime.get("regime_scores") or {},
                previous_state=previous_state,
                captured_at=str(current.get("timestamp") or summary.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            )

            confidence_multiplier = _clamp(
                1.06 if regime_snapshot["current_regime"] == "risk_on_confirmed" else
                0.84 if regime_snapshot["current_regime"] in {"global_funding_stress", "risk_off_confirmed"} else
                0.92 if regime_snapshot["current_regime"] in {"risk_on_fragile", "latent_stress", "divergent"} else 1.0,
                0.65,
                1.15,
            )
            band_width_multiplier = _clamp(
                1.30 if regime_snapshot["current_regime"] in {"global_funding_stress", "risk_off_confirmed", "latent_stress"} else
                1.12 if regime_snapshot["current_regime"] in {"risk_on_fragile", "divergent"} else
                0.92 if regime_snapshot["current_regime"] == "risk_on_confirmed" else 1.0,
                0.80,
                1.45,
            )
            upside_band_multiplier = 0.94 if regime_snapshot["current_regime"] == "risk_on_confirmed" else 1.08
            downside_band_multiplier = 1.18 if regime_snapshot["current_regime"] in {"risk_off_confirmed", "global_funding_stress"} else 1.0
            convergence_probability = _clamp(
                _safe_float(current.get("confidence"), 0.5) * confidence_multiplier * (0.95 if market_state["selected_state"] == "reversal" else 1.05),
                0.02,
                0.98,
            )
            regime_break_probability = _clamp(
                _safe_float(global_regime.get("global_regime_score"), 0.0) / 100.0 * (1.05 if market_state["selected_state"] in {"divergence", "latent_stress"} else 0.85),
                0.02,
                0.98,
            )

            if not Config.OPTIONS_NONLINEAR_DEPENDENCE_ENGINE_ENABLE:
                warnings.append("NonlinearDependenceEngine desabilitado; leituras de cauda e lead-lag foram simplificadas.")
            if not Config.OPTIONS_PRICE_MAKING_ENGINE_ENABLE:
                warnings.append("PriceMakingEngine desabilitado; usando inferência estrutural simplificada.")
            if not Config.OPTIONS_MARKET_STATE_ENGINE_ENABLE:
                warnings.append("MarketStateEngine desabilitado; estado de mercado simplificado.")
            if not current_live_rows:
                warnings.append("Sem live_factor_rows recentes; asset regimes usando fallback persistido.")

            price_making_summary = {
                "dominant_price_maker": dominant_price_maker_key,
                "dominant_theoretical_driver": dominant_theoretical_driver,
                "ignored_driver": ignored_driver,
                "price_making_quality": round(price_making_quality * 100.0, 4),
                "macro_to_price_alignment": round(macro_to_price_alignment, 6),
                "price_acceptance_state": self._price_acceptance_state(current),
            }

            explanation = {
                "summary": (
                    f"Regime dominante {regime_snapshot['current_regime']} com "
                    f"{dominant_price_maker_key or 'sem líder claro'} fazendo preço e "
                    f"{ignored_driver or 'sem driver ignorado evidente'} como alerta secundário."
                ),
                "regime_message": (
                    f"O regime atual está em {regime_snapshot['current_regime']} "
                    f"({global_regime['global_regime_score']:.1f}/100)."
                ),
                "price_making_message": (
                    f"{dominant_price_maker_key or 'Nenhuma perna'} está com maior score de price-making, "
                    f"enquanto {dominant_theoretical_driver or 'nenhuma perna'} puxa teoricamente o índice."
                ),
                "market_state_message": market_state["reason"],
                "nonlinear_dependency_message": (
                    f"A perna líder mostra distance correlation "
                    f"{_safe_float(top_price_leg.get('distance_corr')):.2f} e tail dependence "
                    f"{_safe_float(top_price_leg.get('tail_dependence')):.2f}."
                ),
            }

            payload_timestamp = str(current.get("timestamp") or summary.get("timestamp") or datetime.now(timezone.utc).isoformat())
            session_date = str((latest_run.get("session_date") or payload_timestamp[:10]))
            run_id = hashlib.sha1(
                f"regime-price-making|{underlying_security}|{payload_timestamp}|{latest_run.get('run_id')}".encode("utf-8")
            ).hexdigest()

            asset_rows = []
            for row in asset_package.get("asset_regime_snapshots") or []:
                enriched_row = dict(row)
                enriched_row["underlying_security"] = underlying_security
                asset_rows.append(enriched_row)
            leg_rows = []
            for leg_key, leg_payload in leg_outputs.items():
                leg_row = dict(leg_payload)
                leg_row["timestamp"] = payload_timestamp
                leg_row["leg_name"] = leg_key
                leg_row["underlying_security"] = underlying_security
                leg_rows.append(leg_row)

            payload = {
                "run_id": run_id,
                "captured_at": payload_timestamp,
                "session_date": session_date,
                "underlying_security": underlying_security,
                "feature_flags": self._feature_flags(),
                "source": {
                    "fair_value_run_id": latest_run.get("run_id"),
                    "options_context_generated_at": context_state.get("generated_at"),
                },
                "input_snapshot": {
                    "timestamp": payload_timestamp,
                    "xb1_last": current.get("xb1_last"),
                    "ibov_last": current.get("ibov_last"),
                    "xb1_return_intraday": current.get("xb1_return_intraday"),
                    "ibov_return_intraday": current.get("ibov_return_intraday"),
                    "xb1_log_return": current.get("xb1_log_return"),
                    "ibov_log_return": current.get("ibov_log_return"),
                    "xb1_rolling_volatility": current.get("xb1_rolling_volatility"),
                    "ibov_rolling_volatility": current.get("ibov_rolling_volatility"),
                    "vwap": None,
                    "distance_to_core_fair_value": price_vs_core_fv,
                    "distance_to_quality_adjusted_fair_value": price_vs_quality_fv,
                    "distance_to_fair_value_band": price_vs_band,
                },
                "global_regime": regime_snapshot["current_regime"],
                "global_regime_score": global_regime["global_regime_score"],
                "global_regime_confidence": global_regime["global_regime_confidence"],
                "second_best_regime": regime_snapshot["second_best_regime"],
                "second_best_score": regime_snapshot["second_best_score"],
                "price_making_summary": price_making_summary,
                "market_state": {
                    "state": market_state["selected_state"],
                    "confidence": market_state["confidence"],
                    "direction": market_state["direction"],
                    "reason": market_state["reason"],
                },
                "legs": leg_outputs,
                "warnings": warnings,
                "explanation": explanation,
                "regime_multipliers": {
                    "confidence_multiplier": round(confidence_multiplier, 6),
                    "band_width_multiplier": round(band_width_multiplier, 6),
                    "upside_band_multiplier": round(upside_band_multiplier, 6),
                    "downside_band_multiplier": round(downside_band_multiplier, 6),
                    "convergence_probability": round(convergence_probability, 6),
                    "regime_break_probability": round(regime_break_probability, 6),
                    "factor_weight_adjustments": {
                        "equity_core": round(1.0 + max(core_score_map.get("equity", 0.0), 0.0) * 0.10, 6),
                        "rates_core": round(1.0 + abs(core_score_map.get("rates", 0.0)) * 0.08, 6),
                        "funding_shadow": round(1.0 + max(shadow_score_map.get("funding", 0.0), 0.0) * 0.14, 6),
                    },
                },
                "asset_regime_snapshots": asset_rows,
                "leg_price_making_snapshots": leg_rows,
                "market_state_snapshot": {
                    "timestamp": payload_timestamp,
                    "underlying_security": underlying_security,
                    **market_state,
                },
                "regime_snapshot": {
                    "timestamp": payload_timestamp,
                    "underlying_security": underlying_security,
                    **regime_snapshot,
                    "global_regime_confidence": global_regime["global_regime_confidence"],
                    "confidence_multiplier": confidence_multiplier,
                    "band_width_multiplier": band_width_multiplier,
                    "convergence_probability": convergence_probability,
                    "regime_break_probability": regime_break_probability,
                },
                "summary": {
                    "timestamp": payload_timestamp,
                    "global_regime": regime_snapshot["current_regime"],
                    "global_regime_score": global_regime["global_regime_score"],
                    "global_regime_confidence": global_regime["global_regime_confidence"],
                    "dominant_price_maker": dominant_price_maker_key,
                    "dominant_theoretical_driver": dominant_theoretical_driver,
                    "ignored_driver": ignored_driver,
                    "market_state": market_state["selected_state"],
                    "market_state_confidence": market_state["confidence"],
                    "price_making_quality": price_making_summary["price_making_quality"],
                    "macro_to_price_alignment": price_making_summary["macro_to_price_alignment"],
                    "price_acceptance_state": price_making_summary["price_acceptance_state"],
                    "warnings": warnings,
                    "regime_multipliers": {
                        "confidence_multiplier": confidence_multiplier,
                        "band_width_multiplier": band_width_multiplier,
                        "upside_band_multiplier": upside_band_multiplier,
                        "downside_band_multiplier": downside_band_multiplier,
                        "convergence_probability": convergence_probability,
                        "regime_break_probability": regime_break_probability,
                    },
                },
            }

            if persist:
                payload["persisted"] = self.store.write_regime_price_making_run(payload)
                self.store.append_regime_price_making_snapshots(
                    session_date=session_date,
                    asset_rows=asset_rows,
                    leg_rows=leg_rows,
                    market_state_row=payload["market_state_snapshot"],
                    regime_row=payload["regime_snapshot"],
                )
            return payload
        except Exception as exc:
            logger.exception("RegimePriceMakingEngine failed")
            latest = self.store.read_latest_regime_price_making_run(underlying_security)
            if latest:
                latest = _deep_copy_json(latest)
                warnings = list(latest.get("warnings") or [])
                warnings.append(f"regime_price_making_engine_fallback: {exc}")
                latest["warnings"] = warnings
                latest.setdefault("summary", {})["warnings"] = warnings
                return latest
            raise
