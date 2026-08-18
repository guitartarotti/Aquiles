from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.services.options_fair_value_modeling.asset_regime_engine import build_asset_regimes
from app.services.options_fair_value_modeling.global_regime_engine import build_global_regime
from app.services.options_fair_value_modeling.market_state_engine import build_market_state
from app.services.options_fair_value_modeling.nonlinear_dependence_engine import (
    build_nonlinear_dependence,
)
from app.services.options_fair_value_modeling.price_making_engine import build_leg_price_making
from app.services.options_fair_value_modeling.regime_state_machine import run_regime_state_machine


def _iso(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


class RegimePriceMakingEngineTest(unittest.TestCase):
    def test_asset_regime_classifies_positive_and_negative_assets(self) -> None:
        current_rows = [
            {"factor": "ewz", "daily_change_pct": 1.2, "timestamp": _iso(1), "feature_zscore": 1.1},
            {"factor": "usdbrl", "daily_change_pct": 0.9, "timestamp": _iso(1), "feature_zscore": 1.0},
            {"factor": "brazil_cds", "daily_change_pct": 1.4, "timestamp": _iso(1), "feature_zscore": 1.3},
            {"factor": "bbr_bond", "daily_change_pct": 0.8, "timestamp": _iso(45), "feature_zscore": 0.6},
        ]
        history_by_factor = {
            "ewz": [{"daily_change_pct": 0.5, "timestamp": _iso(10)}, {"daily_change_pct": 0.6, "timestamp": _iso(8)}],
            "usdbrl": [{"daily_change_pct": 0.2, "timestamp": _iso(10)}, {"daily_change_pct": 0.1, "timestamp": _iso(8)}],
            "brazil_cds": [{"daily_change_pct": 0.3, "timestamp": _iso(10)}, {"daily_change_pct": 0.2, "timestamp": _iso(8)}],
            "bbr_bond": [{"daily_change_pct": 0.1, "timestamp": _iso(90)}],
        }
        factor_defs = {
            "ewz": {"expected_direction_to_ibov": "positive_when_rising"},
            "usdbrl": {"expected_direction_to_ibov": "negative_when_rising"},
            "brazil_cds": {"expected_direction_to_ibov": "negative_when_rising"},
            "bbr_bond": {"expected_direction_to_ibov": "positive_when_rising"},
        }
        package = build_asset_regimes(
            current_rows=current_rows,
            history_by_factor=history_by_factor,
            factor_definitions=factor_defs,
            xb1_signed_return=0.35,
        )
        asset_map = package["asset_regime_map"]
        self.assertEqual(asset_map["ewz"]["asset_regime"], "bullish_pressure")
        self.assertEqual(asset_map["usdbrl"]["asset_regime"], "divergent")
        self.assertEqual(asset_map["brazil_cds"]["asset_regime"], "divergent")
        self.assertEqual(asset_map["bbr_bond"]["asset_regime"], "stale")

    def test_nonlinear_dependence_detects_relationship_and_tail(self) -> None:
        observations = []
        now = datetime.now(timezone.utc)
        for idx in range(50):
            ts = (now - timedelta(minutes=50 - idx)).isoformat()
            leg_value = (idx - 25) / 10.0
            xb1_return = (leg_value * leg_value) * 0.08
            observations.append({
                "timestamp": ts,
                "xb1_return": xb1_return,
                "core_legs": {"equity": {"contribution_points": leg_value}},
                "shadow_legs": {},
            })
        result = build_nonlinear_dependence(observations=observations, leg_key="equity", leg_type="core")
        self.assertGreater(result["distance_corr"], 0.2)
        self.assertGreaterEqual(result["dependence_confidence"], 0.05)

    def test_price_making_classifies_leading_vs_confirming(self) -> None:
        making = build_leg_price_making(
            leg_key="fx",
            leg_type="core",
            leg_payload={"score": 1.1, "contribution_points": 220.0, "implied_fair_value_xb1": 188200.0, "confidence": 0.8, "label": "Core FX"},
            dependence={"pearson_corr": 0.7, "spearman_corr": 0.65, "distance_corr": 0.6, "tail_dependence": 0.45, "nonlinear_dependence_score": 0.6, "quantile_beta": 0.8, "best_lag_minutes": -5, "lead_lag_score": 0.72, "dependence_confidence": 0.74, "windows": {}},
            xb1_return_z=0.9,
            dislocation_zscore=0.4,
            price_vs_core_fv=0.01,
            price_vs_quality_fv=0.008,
            price_vs_band=0.2,
        )
        ignored = build_leg_price_making(
            leg_key="equity",
            leg_type="core",
            leg_payload={"score": 1.3, "contribution_points": 260.0, "implied_fair_value_xb1": 188400.0, "confidence": 0.8, "label": "Core Equity"},
            dependence={"pearson_corr": 0.1, "spearman_corr": 0.12, "distance_corr": 0.08, "tail_dependence": 0.04, "nonlinear_dependence_score": 0.08, "quantile_beta": 0.1, "best_lag_minutes": 0, "lead_lag_score": 0.08, "dependence_confidence": 0.12, "windows": {}},
            xb1_return_z=0.05,
            dislocation_zscore=1.2,
            price_vs_core_fv=-0.012,
            price_vs_quality_fv=-0.013,
            price_vs_band=0.85,
        )
        self.assertEqual(making["status"], "leading")
        self.assertEqual(ignored["status"], "confirming_only")

    def test_market_state_detects_acceleration(self) -> None:
        state = build_market_state(
            dominant_price_making_score=0.82,
            dominant_theoretical_strength=0.75,
            xb1_momentum_score=0.78,
            dependence_increase=0.7,
            band_acceptance_score=0.66,
            flow_confirmation_score=0.6,
            persistence_score=0.72,
            decline_in_price_making_score=0.1,
            decline_in_elasticity=0.05,
            failed_breakout_score=0.05,
            volume_without_progress=0.08,
            extreme_dislocation_score=0.12,
            low_price_response=0.1,
            proximity_to_fv_band_or_gamma=0.2,
            failed_continuation=0.05,
            low_factor_alignment=0.08,
            low_realized_volatility=0.12,
            no_dominant_price_maker=0.05,
            mixed_leg_signals=0.08,
            shadow_against_core=0.1,
            fv_or_vwap_recross=0.05,
            new_opposite_price_maker=0.02,
            flow_reversal=0.05,
            divergence_pressure=0.08,
            latent_stress_pressure=0.1,
        )
        self.assertEqual(state["selected_state"], "acceleration")

    def test_global_regime_and_hysteresis(self) -> None:
        regime = build_global_regime(
            core_scores={"equity": 1.1, "fx": 0.8, "credit": 0.7, "rates": 0.2, "commodities": 0.4, "us_rates": 0.5},
            shadow_scores={"funding": 0.1, "volatility": 0.08, "em_stress": 0.05, "credit_shadow": 0.04, "sovereign_credit": 0.06, "brazil_relative": 0.02},
            price_making_scores={"equity": 78.0, "fx": 74.0},
            market_state={"selected_state": "acceleration", "confidence": 0.82, "latent_stress_score": 0.1},
            risk_quality_score=0.76,
            dislocation_zscore=0.35,
            price_vs_core_fv=0.01,
            price_vs_quality_fv=0.005,
            core_shadow_alignment=0.88,
            divergence_score=0.12,
        )
        self.assertEqual(regime["global_regime"], "divergent")
        self.assertGreater(regime["global_regime_confidence"], 0.5)

        first = run_regime_state_machine(
            regime_scores={"risk_on_confirmed": 62.0, "risk_off_confirmed": 41.0, "divergent": 30.0},
            previous_state=None,
            captured_at=_iso(0),
            switch_threshold=4.0,
            confirmation_snapshots=2,
            min_regime_duration_seconds=1,
        )
        second = run_regime_state_machine(
            regime_scores={"risk_off_confirmed": 71.0, "risk_on_confirmed": 58.0, "divergent": 35.0},
            previous_state=first,
            captured_at=(datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat(),
            switch_threshold=4.0,
            confirmation_snapshots=2,
            min_regime_duration_seconds=1,
        )
        third = run_regime_state_machine(
            regime_scores={"risk_off_confirmed": 72.0, "risk_on_confirmed": 54.0, "divergent": 39.0},
            previous_state=second,
            captured_at=(datetime.now(timezone.utc) + timedelta(seconds=4)).isoformat(),
            switch_threshold=4.0,
            confirmation_snapshots=2,
            min_regime_duration_seconds=1,
        )
        self.assertEqual(first["current_regime"], "risk_on_confirmed")
        self.assertEqual(second["current_regime"], "risk_on_confirmed")
        self.assertEqual(third["current_regime"], "risk_off_confirmed")


if __name__ == "__main__":
    unittest.main()
