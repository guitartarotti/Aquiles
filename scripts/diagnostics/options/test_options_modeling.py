from __future__ import annotations

import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


from backend.app.services.options_modeling import OptionsModelingService  # noqa: E402


def main() -> None:
    service = OptionsModelingService()
    payload = service.run_latest(
        underlying_security="IBOVE Index",
        universe_tier="structural",
        persist=False,
    )
    summary = payload.get("summary") or {}
    dealer = payload.get("dealer_inference") or {}
    comparison = dealer.get("comparison") or {}
    print(json.dumps({
        "run_id": payload.get("run_id"),
        "underlying_security": payload.get("underlying_security"),
        "spot_price": summary.get("spot_price"),
        "forward_price": summary.get("forward_price"),
        "dex_total": summary.get("dex_total"),
        "gex_total": summary.get("gex_total"),
        "vex_total": summary.get("vex_total"),
        "cex_total": summary.get("cex_total"),
        "zero_pressure": summary.get("zero_pressure"),
        "max_acceleration": summary.get("max_acceleration"),
        "win_delta_equivalent": summary.get("win_delta_equivalent"),
        "dealer_inference_reference_strike": comparison.get("reference_strike"),
        "dealer_inference_reference_value": comparison.get("reference_dealer_inference_value"),
        "dealer_inference_confidence": comparison.get("reference_confidence"),
        "gex_center_of_mass": comparison.get("gex_center_of_mass"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
