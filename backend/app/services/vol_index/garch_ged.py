"""
GARCH(1,1) with Generalized Error Distribution (GED) residuals.
Pure numpy/scipy — no arch/statsmodels dependency.

Model:
    r_t  = mu + eps_t
    eps_t = sigma_t * z_t,   z_t ~ GED(nu)
    h_t  = omega + alpha * eps_{t-1}^2 + beta * h_{t-1}

GED (Nelson 1991):
    f(z; nu) = [ nu * exp(-|z/lam|^nu / 2) ] / [ lam * 2^(1+1/nu) * Gamma(1/nu) ]
    lam      = sqrt( Gamma(1/nu) / Gamma(3/nu) ) / sqrt(2^(2/nu))
    => E[Z]=0, E[Z^2]=1 for all nu>0

nu=2  => standard normal
nu=1  => Laplace (fat tails)
nu<2  => fatter tails than normal
nu>2  => thinner tails
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import minimize
from scipy.special import gamma as _gamma

logger = logging.getLogger(__name__)

TRADING_DAYS_YEAR = 252


# ──────────────────────────────────────────────────────────
# GED helpers
# ──────────────────────────────────────────────────────────

def _ged_lambda(nu: float) -> float:
    """Scale factor so that Var(Z)=1 under GED(nu)."""
    return np.sqrt(_gamma(1.0 / nu) / _gamma(3.0 / nu)) / (2.0 ** (1.0 / nu))


def _log_ged_const(nu: float, lam: float) -> float:
    """Log of the GED normalizing constant (per observation, excluding sigma)."""
    return np.log(nu) - (1.0 + 1.0 / nu) * np.log(2.0) - np.log(lam) - np.log(_gamma(1.0 / nu))


def _ged_logpdf_vec(z: np.ndarray, nu: float) -> np.ndarray:
    """Vectorized log-PDF of standardized GED. E[Z^2]=1."""
    lam = _ged_lambda(nu)
    c   = _log_ged_const(nu, lam)
    # clip |z/lam|^nu to avoid overflow for very large residuals
    exponent = np.clip(np.abs(z / lam), 0, 1e6) ** nu
    return c - 0.5 * exponent


# ──────────────────────────────────────────────────────────
# Unconstrained → constrained parameter maps
# ──────────────────────────────────────────────────────────

def _sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    """Numerically stable sigmoid."""
    return np.where(x >= 0,
                    1.0 / (1.0 + np.exp(-np.clip(x, -30, 30))),
                    np.exp(np.clip(x, -30, 30)) / (1.0 + np.exp(np.clip(x, -30, 30))))


# Bounds for alpha and beta to ensure mean-reversion
_ALPHA_MAX = 0.25
_BETA_MAX  = 0.97


def _unpack(raw: np.ndarray) -> tuple[float, float, float, float, float]:
    """Unconstrained → (mu, omega, alpha, beta, nu)."""
    mu       = float(raw[0])
    omega    = float(np.exp(raw[1]))                      # > 0
    alpha    = float(_ALPHA_MAX * _sigmoid(raw[2]))       # (0, 0.25)
    beta     = float(_BETA_MAX  * _sigmoid(raw[3]))       # (0, 0.97)
    nu       = float(1.0 + np.exp(np.clip(raw[4], -10, 5)))  # > 1
    return mu, omega, alpha, beta, nu


def _pack(mu: float, omega: float, alpha: float, beta: float, nu: float) -> np.ndarray:
    """Constrained → unconstrained (rough inverse, used for initialization)."""
    log_omega   = np.log(max(omega, 1e-12))
    logit_alpha = np.log(max(alpha / _ALPHA_MAX, 1e-9) / max(1 - alpha / _ALPHA_MAX, 1e-9))
    logit_beta  = np.log(max(beta  / _BETA_MAX,  1e-9) / max(1 - beta  / _BETA_MAX,  1e-9))
    log_nu_m1   = np.log(max(nu - 1.0, 1e-9))
    return np.array([mu, log_omega, logit_alpha, logit_beta, log_nu_m1], dtype=np.float64)


# ──────────────────────────────────────────────────────────
# Variance filter
# ──────────────────────────────────────────────────────────

def _garch_filter(eps: np.ndarray, omega: float, alpha: float, beta: float) -> np.ndarray:
    """Run the GARCH(1,1) variance recursion. Returns h_t array (same length as eps)."""
    T = len(eps)
    h = np.empty(T, dtype=np.float64)
    h_uncond = omega / max(1.0 - alpha - beta, 1e-8)
    h[0] = h_uncond
    for t in range(1, T):
        h[t] = omega + alpha * eps[t - 1] ** 2 + beta * h[t - 1]
        if h[t] <= 0.0:
            h[t] = h_uncond  # safety floor
    return h


# ──────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────

@dataclass
class GarchGedParams:
    mu:           float
    omega:        float
    alpha:        float   # ARCH coefficient
    beta:         float   # GARCH coefficient
    nu:           float   # GED shape (2=normal, <2=fat tails)
    persistence:  float   # alpha + beta
    log_lik:      float
    converged:    bool
    n_obs:        int


@dataclass
class GarchGedForecast:
    sigma_1d:          float         # 1-step-ahead σ (annualized)
    sigma_30d:         float         # 30-day constant-maturity σ (annualized)
    sigma_N:           float         # horizon-N σ (annualized)
    variance_path:     list[float]   # per-day conditional variance path
    params:            GarchGedParams


# ──────────────────────────────────────────────────────────
# Negative log-likelihood
# ──────────────────────────────────────────────────────────

def _neg_loglik(raw: np.ndarray, returns: np.ndarray) -> float:
    mu, omega, alpha, beta, nu = _unpack(raw)

    if alpha + beta >= 0.9999 or omega <= 0:
        return 1e12

    eps = returns - mu
    h   = _garch_filter(eps, omega, alpha, beta)

    if np.any(h <= 0):
        return 1e12

    sigma = np.sqrt(h)
    z     = eps / sigma

    ll = np.sum(_ged_logpdf_vec(z, nu)) - np.sum(np.log(sigma))

    if not np.isfinite(ll):
        return 1e12
    return -float(ll)


# ──────────────────────────────────────────────────────────
# Public: fit
# ──────────────────────────────────────────────────────────

def fit_garch_ged(
    returns: np.ndarray,
    n_restarts: int = 4,
    max_iter: int = 600,
) -> GarchGedParams:
    """
    Fit GARCH(1,1)-GED via maximum likelihood.

    Parameters
    ----------
    returns : array of daily log-returns (fractions, e.g. 0.012 = 1.2%)
    """
    returns = np.asarray(returns, dtype=np.float64)
    returns = returns[np.isfinite(returns)]
    T = len(returns)
    if T < 30:
        raise ValueError(f"Too few observations: {T}")

    mu0    = float(np.mean(returns))
    var0   = float(np.var(returns, ddof=1))
    var0   = max(var0, 1e-8)

    # Multiple starting configurations
    starts = [
        _pack(mu0, var0 * 0.05, 0.07, 0.88, 1.5),   # typical equity GARCH
        _pack(mu0, var0 * 0.10, 0.12, 0.82, 1.2),   # more reactive
        _pack(mu0, var0 * 0.02, 0.05, 0.93, 2.0),   # high persistence, normal
        _pack(mu0, var0 * 0.15, 0.20, 0.70, 1.0),   # low persistence, Laplace
    ]

    best_nll    = np.inf
    best_result = None

    for x0 in starts[:n_restarts]:
        try:
            res = minimize(
                _neg_loglik,
                x0=x0,
                args=(returns,),
                method='L-BFGS-B',
                options={'maxiter': max_iter, 'ftol': 1e-14, 'gtol': 1e-8},
            )
            if np.isfinite(res.fun) and res.fun < best_nll:
                best_nll    = res.fun
                best_result = res
        except Exception as exc:
            logger.debug(f"GARCH-GED restart failed: {exc}")

    if best_result is None or not np.isfinite(best_nll):
        # Fallback: moment-matched parameters
        logger.warning("GARCH-GED optimization did not converge, using moment estimate.")
        alpha, beta = 0.08, 0.88
        omega = var0 * (1 - alpha - beta)
        return GarchGedParams(mu=mu0, omega=omega, alpha=alpha, beta=beta, nu=1.5,
                              persistence=alpha + beta, log_lik=0.0,
                              converged=False, n_obs=T)

    mu, omega, alpha, beta, nu = _unpack(best_result.x)

    return GarchGedParams(
        mu=round(mu, 8),
        omega=round(omega, 10),
        alpha=round(alpha, 8),
        beta=round(beta, 8),
        nu=round(nu, 6),
        persistence=round(alpha + beta, 8),
        log_lik=round(-best_nll, 4),
        converged=bool(best_result.success),
        n_obs=T,
    )


# ──────────────────────────────────────────────────────────
# Public: forecast
# ──────────────────────────────────────────────────────────

def forecast_garch_ged(
    params:          GarchGedParams,
    last_epsilon:    float,   # eps_T = r_T - mu
    last_variance:   float,   # h_T
    horizon:         int = 30,
    tdays_year:      int = TRADING_DAYS_YEAR,
) -> GarchGedForecast:
    """
    Multi-step GARCH(1,1) variance forecast.

    h_{T+1}   = omega + alpha*eps_T^2 + beta*h_T          (1-step)
    h_{T+h}   = σ_L^2 + (alpha+beta)^(h-1) * (h_{T+1} - σ_L^2)   h≥2

    Annualized vol = sqrt(252 * avg_h_horizon)
    """
    p   = params
    pers = p.alpha + p.beta
    s_L2 = p.omega / max(1.0 - pers, 1e-8)       # unconditional variance

    h1 = p.omega + p.alpha * last_epsilon ** 2 + p.beta * last_variance
    h1 = max(h1, 1e-10)

    var_path = [h1]
    for h in range(2, horizon + 1):
        hh = s_L2 + pers ** (h - 1) * (h1 - s_L2)
        var_path.append(max(hh, 1e-10))

    avg_var = float(np.mean(var_path))
    sigma_N = float(np.sqrt(avg_var * tdays_year))

    return GarchGedForecast(
        sigma_1d=float(np.sqrt(h1 * tdays_year)),
        sigma_30d=float(np.sqrt(max(float(np.mean(var_path[:30])), 1e-12) * tdays_year)),
        sigma_N=sigma_N,
        variance_path=[round(v, 12) for v in var_path],
        params=params,
    )


# ──────────────────────────────────────────────────────────
# Public: simple rolling RV (benchmark)
# ──────────────────────────────────────────────────────────

def realized_vol_simple(
    returns: np.ndarray,
    window: int = 21,
    tdays_year: int = TRADING_DAYS_YEAR,
) -> float:
    """Classic rolling std × sqrt(252) realized volatility."""
    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    w = min(window, len(r))
    if w < 2:
        return float('nan')
    return float(np.std(r[-w:], ddof=1) * np.sqrt(tdays_year))
