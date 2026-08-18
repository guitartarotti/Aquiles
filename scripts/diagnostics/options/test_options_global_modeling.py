from __future__ import annotations

import json
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


from backend.app.services.options_global_modeling import OptionsGlobalTriangulationService  # noqa: E402


def main() -> None:
    service = OptionsGlobalTriangulationService()
    payload = service.run_latest(
        underlying_security="IBOVE Index",
        refresh_local_model=False,
        persist=False,
    )
    summary = payload.get("summary") or {}
    print(json.dumps({
        "run_id": payload.get("run_id"),
        "underlying_security": payload.get("underlying_security"),
        "global_regime": summary.get("global_regime"),
        "global_regime_confidence": summary.get("global_regime_confidence"),
        "distortion_zscore": summary.get("distortion_zscore"),
        "distortion_band_low": summary.get("distortion_band_low"),
        "distortion_band_high": summary.get("distortion_band_high"),
        "global_absorption_score": summary.get("global_absorption_score"),
        "global_breakout_score": summary.get("global_breakout_score"),
        "global_sync_score": summary.get("global_sync_score"),
        "cross_asset_confluence_score": summary.get("cross_asset_confluence_score"),
        "cross_asset_strongest_cluster": summary.get("cross_asset_strongest_cluster"),
        "cross_asset_nearest_upside_cluster": summary.get("cross_asset_nearest_upside_cluster"),
        "cross_asset_nearest_downside_cluster": summary.get("cross_asset_nearest_downside_cluster"),
        "top_explaining_assets": summary.get("top_explaining_assets"),
        "desk_summary": summary.get("desk_summary"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
