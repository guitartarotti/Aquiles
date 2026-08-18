"""
IV Surface extraction.

Given a list of PreparedOption TypedDicts and a MarketContext, extract:
  - iv_interpolated  : constant-maturity 30-day IV (VIX-style variance interpolation)
  - iv_atm           : blended IV at absolute delta ≈ 0.50 on the near expiry
  - iv_25d_put/call  : IV at |delta| = 0.25
  - iv_15d_put/call  : IV at |delta| = 0.15
  - iv_10d_put/call  : IV at |delta| = 0.10
  - skew_25d/15d/10d : put_iv - call_iv at each delta
  - term_structure   : [{dte, iv_atm}] sorted ascending
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from scipy.interpolate import interp1d

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────

def extract_iv_metrics(
    prepared_options: list,
    market_context,
    target_dte_days: int = 21,          # calendar days for constant-maturity
    min_opts_for_spline: int = 3,
) -> dict:
    """
    Returns a flat dict with IV surface metrics.
    All IV values are decimal (e.g. 0.22 = 22%).
    """
    spot    = _ctx(market_context, 'spot_price') or 0.0
    forward = _ctx(market_context, 'forward_price') or spot or 1.0
    forward = float(forward)

    by_dte = _group_by_dte(prepared_options)
    if not by_dte:
        logger.debug("iv_surface: no options after grouping")
        return _empty()

    # Build per-expiry vol curves (keyed by dte_calendar int)
    curves: dict[float, dict] = {}
    for dte, opts in by_dte.items():
        c = _build_smile(opts, forward, min_opts_for_spline)
        if c is not None:
            curves[dte] = c

    if not curves:
        logger.debug("iv_surface: no usable expiry curves")
        return _empty()

    # ── Nearest expiry to target_dte for smile metrics ──────────────────────
    near = _nearest_curve(curves, target_dte_days)
    if near is None:
        near = list(curves.values())[0]

    iv_atm = _blend(
        _at_delta(near, 0.50, 'call'),
        _at_delta(near, 0.50, 'put'),
    )
    iv_25c = _at_delta(near, 0.25, 'call')
    iv_25p = _at_delta(near, 0.25, 'put')
    iv_15c = _at_delta(near, 0.15, 'call')
    iv_15p = _at_delta(near, 0.15, 'put')
    iv_10c = _at_delta(near, 0.10, 'call')
    iv_10p = _at_delta(near, 0.10, 'put')

    # ── Constant-maturity 30-day IV (variance-weighted interpolation) ────────
    iv_interp = _const_maturity_iv(curves, target_dte_days)

    # ── Skews ────────────────────────────────────────────────────────────────
    skew_25d = _diff(iv_25p, iv_25c)
    skew_15d = _diff(iv_15p, iv_15c)
    skew_10d = _diff(iv_10p, iv_10c)

    # ── Term structure (ATM IV by expiry) ────────────────────────────────────
    term = []
    for dte in sorted(curves):
        atm = _blend(
            _at_delta(curves[dte], 0.50, 'call'),
            _at_delta(curves[dte], 0.50, 'put'),
        )
        if atm is not None:
            term.append({'dte': int(round(dte)), 'iv_atm': _r(atm)})

    return {
        'iv_interpolated': _r(iv_interp),
        'iv_atm':          _r(iv_atm),
        'iv_25d_put':      _r(iv_25p),
        'iv_25d_call':     _r(iv_25c),
        'iv_15d_put':      _r(iv_15p),
        'iv_15d_call':     _r(iv_15c),
        'iv_10d_put':      _r(iv_10p),
        'iv_10d_call':     _r(iv_10c),
        'skew_25d':        _r(skew_25d),
        'skew_15d':        _r(skew_15d),
        'skew_10d':        _r(skew_10d),
        'term_structure':  term,
        'near_expiry_dte': int(round(near['dte'])) if near else None,
    }


# ──────────────────────────────────────────────────────────
# Grouping
# ──────────────────────────────────────────────────────────

def _ctx(ctx, key: str):
    """Attribute-or-dict access on MarketContext."""
    if isinstance(ctx, dict):
        return ctx.get(key)
    return getattr(ctx, key, None)


def _opt(o, *keys):
    """Try multiple field names on a PreparedOption (TypedDict or dict)."""
    for k in keys:
        v = o.get(k) if isinstance(o, dict) else getattr(o, k, None)
        if v is not None:
            return v
    return None


def _group_by_dte(opts: list) -> dict[float, list]:
    """Group options by dte_calendar (round to nearest int)."""
    groups: dict[float, list] = {}
    for o in opts:
        dte = _opt(
            o,
            'dte_calendar',
            'days_to_expiry_calendar',
            'dte_business',
            'days_to_expiry_business',
            'days_to_expiry',
            'dte',
        )
        if dte is None:
            continue
        try:
            dte_f = round(float(dte))
        except (TypeError, ValueError):
            continue
        if dte_f < 1:
            continue
        groups.setdefault(dte_f, []).append(o)
    return groups


# ──────────────────────────────────────────────────────────
# Per-expiry smile
# ──────────────────────────────────────────────────────────

def _build_smile(opts: list, forward: float, min_opts: int) -> Optional[dict]:
    """
    Build call/put sub-curves of (abs_delta, iv) for one expiry.
    Delta convention: abs(observed_delta); for puts this is positive too.
    """
    calls: list[dict] = []
    puts:  list[dict] = []

    for o in opts:
        iv     = _opt(o, 'selected_iv', 'iv_mid', 'IVOL_MID', 'EFF_IV', 'MODEL_IV')
        delta  = _opt(o, 'observed_delta', 'EFF_DELTA', 'MODEL_DELTA', 'delta')
        strike = _opt(o, 'strike', 'Strike', 'STRIKE')
        pc     = _opt(o, 'put_call', 'option_type', 'PutCall', 'type')
        dte    = _opt(
            o,
            'dte_calendar',
            'days_to_expiry_calendar',
            'dte_business',
            'days_to_expiry_business',
            'days_to_expiry',
            'dte',
        )

        if iv is None or pc is None:
            continue
        try:
            iv_f = float(iv)
            if not (0.001 < iv_f < 4.0):       # reject garbage
                continue
        except (TypeError, ValueError):
            continue

        if delta is None and strike is not None:
            # Crude approximation when delta is missing
            try:
                delta = _approx_delta(float(strike), forward, str(pc))
            except Exception:
                delta = None

        if delta is None:
            continue
        try:
            d = abs(float(delta))
            if not (0.01 <= d <= 0.99):
                continue
        except (TypeError, ValueError):
            continue

        dte_f = float(dte) if dte is not None else 30.0
        pt = {'abs_delta': d, 'iv': iv_f, 'dte': dte_f}

        if str(pc).upper() in ('C', 'CALL'):
            calls.append(pt)
        else:
            puts.append(pt)

    if len(calls) < min_opts and len(puts) < min_opts:
        return None

    dte_ref = float(np.median([p['dte'] for p in (calls or puts)]))

    return {
        'calls': _sorted_unique(calls),
        'puts':  _sorted_unique(puts),
        'dte':   dte_ref,
    }


def _sorted_unique(pts: list[dict]) -> list[dict]:
    """Sort by abs_delta ascending, deduplicate."""
    pts.sort(key=lambda p: p['abs_delta'])
    seen = set()
    out  = []
    for p in pts:
        key = round(p['abs_delta'], 3)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _approx_delta(K: float, F: float, pc: str) -> float:
    """Rough moneyness-based delta proxy (no T/vol needed)."""
    m = F / max(K, 1e-8)
    if pc.upper() in ('C', 'CALL'):
        return float(np.clip(0.5 * m, 0.01, 0.99))
    else:
        return float(np.clip(0.5 / m, 0.01, 0.99))


# ──────────────────────────────────────────────────────────
# Interpolation
# ──────────────────────────────────────────────────────────

def _at_delta(curve: dict, target_d: float, side: str) -> Optional[float]:
    """Interpolate IV at a specific absolute delta using robust linear interpolation."""
    pts = curve.get('calls' if side == 'call' else 'puts', [])
    if len(pts) < 2:
        return None

    d_arr = np.array([p['abs_delta'] for p in pts])
    iv_arr = np.array([p['iv']       for p in pts])

    # Ensure strictly monotone (deduplicate)
    idx = np.argsort(d_arr)
    d_arr  = d_arr[idx]
    iv_arr = iv_arr[idx]

    # If target is outside the range, extrapolate linearly (capped)
    if target_d < d_arr[0]:
        slope = (iv_arr[1] - iv_arr[0]) / max(d_arr[1] - d_arr[0], 1e-6)
        val   = iv_arr[0] + slope * (target_d - d_arr[0])
        return float(max(0.001, val))

    if target_d > d_arr[-1]:
        slope = (iv_arr[-1] - iv_arr[-2]) / max(d_arr[-1] - d_arr[-2], 1e-6)
        val   = iv_arr[-1] + slope * (target_d - d_arr[-1])
        return float(max(0.001, val))

    try:
        f = interp1d(d_arr, iv_arr, kind='linear')
        v = float(f(target_d))
        return max(0.001, v) if np.isfinite(v) else None
    except Exception:
        return None


def _const_maturity_iv(curves: dict[float, dict], target_dte: int) -> Optional[float]:
    """
    VIX-style constant-maturity interpolation.

    Weights are proportional to dte so that:
      var_target * target_dte = w_near * var_near * dte_near
                               + w_far  * var_far  * dte_far
    with linear weights in time.
    """
    entries = []
    for dte, curve in curves.items():
        atm = _blend(
            _at_delta(curve, 0.50, 'call'),
            _at_delta(curve, 0.50, 'put'),
        )
        if atm is not None:
            entries.append((float(dte), float(atm)))

    if not entries:
        return None

    entries.sort(key=lambda x: x[0])

    if len(entries) == 1:
        return entries[0][1]

    # Find straddling pair
    near = far = None
    for dte, iv in entries:
        if dte <= target_dte:
            near = (dte, iv)
        elif far is None and dte > target_dte:
            far = (dte, iv)

    if near is None:
        return entries[0][1]
    if far is None:
        return near[1]

    dte_n, iv_n = near
    dte_f, iv_f = far

    # Interpolate in variance × time space
    var_n  = iv_n ** 2 * dte_n
    var_f  = iv_f ** 2 * dte_f
    span   = max(dte_f - dte_n, 1e-6)
    w_f    = (target_dte - dte_n) / span
    w_n    = 1.0 - w_f
    var_t  = (w_n * var_n + w_f * var_f) / max(target_dte, 1)

    return float(np.sqrt(max(var_t, 0.0))) if np.isfinite(var_t) else None


def _nearest_curve(curves: dict, target_dte: int) -> Optional[dict]:
    valid = [(dte, c) for dte, c in curves.items() if dte >= 3]
    if not valid:
        return None
    return min(valid, key=lambda x: abs(x[0] - target_dte))[1]


# ──────────────────────────────────────────────────────────
# Utils
# ──────────────────────────────────────────────────────────

def _r(v: Optional[float], d: int = 6) -> Optional[float]:
    return round(v, d) if (v is not None and np.isfinite(v)) else None


def _diff(a: Optional[float], b: Optional[float]) -> Optional[float]:
    return round(a - b, 6) if (a is not None and b is not None) else None


def _blend(a: Optional[float], b: Optional[float]) -> Optional[float]:
    values = [v for v in (a, b) if v is not None and np.isfinite(v)]
    if not values:
        return None
    return float(sum(values) / len(values))


def _empty() -> dict:
    return {
        'iv_interpolated': None,
        'iv_atm':          None,
        'iv_25d_put':      None,
        'iv_25d_call':     None,
        'iv_15d_put':      None,
        'iv_15d_call':     None,
        'iv_10d_put':      None,
        'iv_10d_call':     None,
        'skew_25d':        None,
        'skew_15d':        None,
        'skew_10d':        None,
        'term_structure':  [],
        'near_expiry_dte': None,
    }
