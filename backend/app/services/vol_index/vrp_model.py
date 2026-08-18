"""
Volatility Risk Premium (VRP) model.

VRP_t = IV_{30d,t}  −  RV_GARCH_{30d,t}

Positive VRP → options priced above expected realized vol (sellers earn premium).
Negative VRP → realized vol exceeds implied (unexpected vol regime).

Robust statistics:
- Outlier detection via MAD (Median Absolute Deviation, 1.4826-normalized)
- Winsorization at configurable percentiles before rolling statistics
- Percentile rank in history
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def compute_vrp(
    iv_30d:               Optional[float],
    rv_garch_30d:         Optional[float],
    history:              list[dict],          # list of past snapshot dicts
    winsorize_pct:        float = 0.02,        # clip at 2nd / 98th pct for rolling stats
    mad_threshold:        float = 3.5,         # flag outlier beyond this many MADs
) -> dict:
    """
    Compute VRP snapshot and rolling statistics against history.

    Returns
    -------
    dict with keys:
        vrp_raw, vrp_z_score, vrp_percentile,
        vrp_rolling_20d, vrp_rolling_60d, vrp_is_outlier
    """
    if iv_30d is None or rv_garch_30d is None:
        return _empty()

    vrp_raw = float(iv_30d) - float(rv_garch_30d)

    # ── Build historical VRP array ───────────────────────────────────────────
    hist = np.array([
        v for r in history
        if (v := r.get('vrp_raw')) is not None and np.isfinite(v)
    ], dtype=np.float64)

    if len(hist) < 5:
        return {
            'vrp_raw':        round(vrp_raw, 6),
            'vrp_z_score':    None,
            'vrp_percentile': None,
            'vrp_rolling_20d': None,
            'vrp_rolling_60d': None,
            'vrp_is_outlier':  False,
        }

    # ── Robust statistics (winsorized history) ───────────────────────────────
    lo = np.percentile(hist, winsorize_pct * 100)
    hi = np.percentile(hist, (1.0 - winsorize_pct) * 100)
    hist_w = np.clip(hist, lo, hi)

    # Outlier detection on raw value via MAD
    med   = float(np.median(hist_w))
    mad   = float(np.median(np.abs(hist_w - med))) * 1.4826   # normalized MAD ≈ σ
    mad   = max(mad, 1e-6)
    z_mad = (vrp_raw - med) / mad
    is_out = abs(z_mad) > mad_threshold

    # Percentile rank of current VRP in history
    pct = float(np.mean(hist_w <= vrp_raw) * 100.0)

    roll20 = float(np.mean(hist_w[-20:])) if len(hist_w) >= 5  else None
    roll60 = float(np.mean(hist_w[-60:])) if len(hist_w) >= 20 else None

    return {
        'vrp_raw':         round(vrp_raw, 6),
        'vrp_z_score':     round(float(z_mad), 4),
        'vrp_percentile':  round(pct, 2),
        'vrp_rolling_20d': round(roll20, 6) if roll20 is not None else None,
        'vrp_rolling_60d': round(roll60, 6) if roll60 is not None else None,
        'vrp_is_outlier':  bool(is_out),
    }


def _empty() -> dict:
    return {
        'vrp_raw':         None,
        'vrp_z_score':     None,
        'vrp_percentile':  None,
        'vrp_rolling_20d': None,
        'vrp_rolling_60d': None,
        'vrp_is_outlier':  False,
    }
