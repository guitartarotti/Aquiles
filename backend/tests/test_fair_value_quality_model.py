from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.services.options_fair_value_modeling.fair_value_quality_model import (
    build_fair_value_quality_package,
)


def _iso_minutes_ago(minutes: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _row(zscore: float, minutes_ago: int = 2) -> dict:
    return {
        "feature_zscore": zscore,
        "timestamp": _iso_minutes_ago(minutes_ago),
        "raw_value": 1.0,
    }


class FairValueQualityModelTest(unittest.TestCase):
    def test_builds_leg_implied_fair_values_and_quality_ribbon(self) -> None:
        live_rows = [
            {"factor": "di_short", **_row(-0.9)},
            {"factor": "di_long", **_row(-0.7)},
            {"factor": "di_slope", **_row(-0.3)},
            {"factor": "spx_proxy", **_row(1.1)},
            {"factor": "russell", **_row(0.8)},
            {"factor": "developed_markets", **_row(0.7)},
            {"factor": "em_future", **_row(0.9)},
            {"factor": "ewz", **_row(1.2)},
            {"factor": "eem", **_row(0.6)},
            {"factor": "cdx_em", **_row(-0.5)},
            {"factor": "cdx_hy", **_row(-0.4)},
            {"factor": "brazil_cds", **_row(-0.8)},
            {"factor": "brazil_cds_3y", **_row(-0.7)},
            {"factor": "embiv", **_row(-0.45)},
            {"factor": "usdbrl", **_row(-0.5)},
            {"factor": "dxy_index", **_row(-0.4)},
            {"factor": "oil", **_row(0.2)},
            {"factor": "coal", **_row(0.3)},
            {"factor": "copper", **_row(0.4)},
            {"factor": "iron_ore", **_row(0.5)},
            {"factor": "usgg2_treasury", **_row(-0.6)},
            {"factor": "usgg10_treasury", **_row(-0.4)},
            {"factor": "us_ois_short_factor", **_row(-0.7)},
            {"factor": "us_ois_long_factor", **_row(-0.45)},
            {"factor": "us_monetary_policy_factor", **_row(-0.35)},
            {"factor": "us_term_premium_factor", **_row(-0.2)},
            {"factor": "vix_index", **_row(-0.3)},
            {"factor": "move_index", **_row(-0.2)},
            {"factor": "vxbr_index", **_row(-0.25)},
            {"factor": "jpy_basket", **_row(-0.2)},
        ]
        structural_model = {
            "factor_contributions_now": {
                "di_short": {"contribution_points": -120.0},
                "di_long": {"contribution_points": -80.0},
                "di_slope": {"contribution_points": -40.0},
                "spx_proxy": {"contribution_points": 210.0},
                "russell": {"contribution_points": 120.0},
                "developed_markets": {"contribution_points": 80.0},
                "em_future": {"contribution_points": 160.0},
                "ewz": {"contribution_points": 150.0},
                "eem": {"contribution_points": 90.0},
                "cdx_em": {"contribution_points": 70.0},
                "cdx_hy": {"contribution_points": 45.0},
                "brazil_cds": {"contribution_points": 110.0},
                "embiv": {"contribution_points": 50.0},
                "usdbrl": {"contribution_points": 95.0},
                "dxy_index": {"contribution_points": 40.0},
                "oil": {"contribution_points": 25.0},
                "coal": {"contribution_points": 35.0},
                "copper": {"contribution_points": 30.0},
                "iron_ore": {"contribution_points": 28.0},
                "usgg2_treasury": {"contribution_points": 55.0},
                "usgg10_treasury": {"contribution_points": 35.0},
                "us_ois_short_factor": {"contribution_points": 28.0},
                "us_ois_long_factor": {"contribution_points": 20.0},
                "us_monetary_policy_factor": {"contribution_points": 18.0},
                "us_term_premium_factor": {"contribution_points": 12.0},
            }
        }
        package = build_fair_value_quality_package(
            current_future_price=188000.0,
            core_fair_value_xb1=188420.0,
            band_half_width_points=180.0,
            live_factor_rows=live_rows,
            live_reference_rows={},
            structural_model=structural_model,
            options_overlay={},
            global_overlay={},
            regime={},
            us_rates_context={"funding_stress_factor": {"score": -0.35}},
            base_confidence=0.74,
            base_risk_quality_score=0.69,
            convergence_probability=0.61,
        )

        rates_leg = package["core_legs"]["rates"]
        self.assertLess(rates_leg["contribution_points"], 0.0)
        self.assertEqual(
            rates_leg["implied_fair_value_xb1"],
            188420.0 + rates_leg["contribution_points"],
        )
        self.assertIn(package["implicit_sentiment"], {"bullish_confirmed", "bullish_fragile", "recovery_candidate"})
        self.assertGreater(package["quality_ribbon"]["upper"], package["quality_ribbon"]["lower"])
        self.assertGreater(package["quality_ribbon"]["width"], 0.0)
        self.assertIn("rates", package["core_legs"])
        self.assertIn("funding", package["shadow_legs"])

    def test_missing_leg_data_disables_leg_and_penalizes_confidence(self) -> None:
        live_rows = [
            {"factor": "spx_proxy", **_row(0.6, minutes_ago=95)},
            {"factor": "ewz", **_row(0.5, minutes_ago=95)},
            {"factor": "move_index", **_row(0.9, minutes_ago=95)},
        ]
        package = build_fair_value_quality_package(
            current_future_price=188000.0,
            core_fair_value_xb1=187850.0,
            band_half_width_points=220.0,
            live_factor_rows=live_rows,
            live_reference_rows={},
            structural_model={"factor_contributions_now": {}},
            options_overlay={},
            global_overlay={},
            regime={},
            us_rates_context={"funding_stress_factor": {"score": 0.55}},
            base_confidence=0.48,
            base_risk_quality_score=0.42,
            convergence_probability=0.44,
        )

        self.assertFalse(package["core_legs"]["commodities"]["enabled"])
        self.assertLess(package["core_legs"]["commodities"]["confidence"], 0.4)
        self.assertIn("stale", " ".join(package["explanation"]["warnings"]).lower())


if __name__ == "__main__":
    unittest.main()
