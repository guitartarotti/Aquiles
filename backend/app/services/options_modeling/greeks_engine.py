from __future__ import annotations

import math
from typing import Any

from .math_utils import normal_cdf, normal_pdf, normalize_rate, normalize_vol


def _safe_positive(value: float, floor: float) -> float:
    return max(float(value), floor)


def _d1_d2(spot: float, strike: float, time_years: float, rate: float, carry: float, sigma: float) -> tuple[float, float]:
    sigma = normalize_vol(sigma)
    time_years = _safe_positive(time_years, 1e-8)
    vol_term = sigma * math.sqrt(time_years)
    if vol_term <= 0:
        vol_term = 1e-8
    numerator = math.log(spot / strike) + (rate - carry + 0.5 * sigma * sigma) * time_years
    d1 = numerator / vol_term
    d2 = d1 - vol_term
    return d1, d2


def price(option_type: str, spot: float, strike: float, time_years: float, rate: float, carry: float, sigma: float) -> float:
    spot = _safe_positive(spot, 1e-8)
    strike = _safe_positive(strike, 1e-8)
    rate = normalize_rate(rate)
    carry = normalize_rate(carry)
    sigma = normalize_vol(sigma)
    time_years = _safe_positive(time_years, 1e-8)
    d1, d2 = _d1_d2(spot, strike, time_years, rate, carry, sigma)
    discount_r = math.exp(-rate * time_years)
    discount_q = math.exp(-carry * time_years)
    if str(option_type).lower().startswith("c"):
        return spot * discount_q * normal_cdf(d1) - strike * discount_r * normal_cdf(d2)
    return strike * discount_r * normal_cdf(-d2) - spot * discount_q * normal_cdf(-d1)


def delta(option_type: str, spot: float, strike: float, time_years: float, rate: float, carry: float, sigma: float) -> float:
    d1, _ = _d1_d2(_safe_positive(spot, 1e-8), _safe_positive(strike, 1e-8), time_years, normalize_rate(rate), normalize_rate(carry), normalize_vol(sigma))
    discount_q = math.exp(-normalize_rate(carry) * _safe_positive(time_years, 1e-8))
    if str(option_type).lower().startswith("c"):
        return discount_q * normal_cdf(d1)
    return discount_q * (normal_cdf(d1) - 1.0)


def gamma(option_type: str, spot: float, strike: float, time_years: float, rate: float, carry: float, sigma: float) -> float:
    del option_type
    spot = _safe_positive(spot, 1e-8)
    sigma = normalize_vol(sigma)
    time_years = _safe_positive(time_years, 1e-8)
    d1, _ = _d1_d2(spot, _safe_positive(strike, 1e-8), time_years, normalize_rate(rate), normalize_rate(carry), sigma)
    denom = spot * sigma * math.sqrt(time_years)
    if denom <= 0:
        return 0.0
    discount_q = math.exp(-normalize_rate(carry) * time_years)
    return discount_q * normal_pdf(d1) / denom


def vega(option_type: str, spot: float, strike: float, time_years: float, rate: float, carry: float, sigma: float) -> float:
    del option_type
    spot = _safe_positive(spot, 1e-8)
    time_years = _safe_positive(time_years, 1e-8)
    d1, _ = _d1_d2(spot, _safe_positive(strike, 1e-8), time_years, normalize_rate(rate), normalize_rate(carry), normalize_vol(sigma))
    discount_q = math.exp(-normalize_rate(carry) * time_years)
    return spot * discount_q * normal_pdf(d1) * math.sqrt(time_years)


def theta(option_type: str, spot: float, strike: float, time_years: float, rate: float, carry: float, sigma: float) -> float:
    spot = _safe_positive(spot, 1e-8)
    strike = _safe_positive(strike, 1e-8)
    rate = normalize_rate(rate)
    carry = normalize_rate(carry)
    sigma = normalize_vol(sigma)
    time_years = _safe_positive(time_years, 1e-8)
    d1, d2 = _d1_d2(spot, strike, time_years, rate, carry, sigma)
    discount_r = math.exp(-rate * time_years)
    discount_q = math.exp(-carry * time_years)
    first_term = -(spot * discount_q * normal_pdf(d1) * sigma) / (2.0 * math.sqrt(time_years))
    if str(option_type).lower().startswith("c"):
        return first_term - rate * strike * discount_r * normal_cdf(d2) + carry * spot * discount_q * normal_cdf(d1)
    return first_term + rate * strike * discount_r * normal_cdf(-d2) - carry * spot * discount_q * normal_cdf(-d1)


def vanna_numeric(
    option_type: str,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    carry: float,
    sigma: float,
    vol_epsilon: float,
) -> float:
    sigma = normalize_vol(sigma)
    epsilon = max(abs(vol_epsilon), 1e-5)
    sigma_up = max(sigma + epsilon, 1e-5)
    sigma_dn = max(sigma - epsilon, 1e-5)
    delta_up = delta(option_type, spot, strike, time_years, rate, carry, sigma_up)
    delta_dn = delta(option_type, spot, strike, time_years, rate, carry, sigma_dn)
    return (delta_up - delta_dn) / (sigma_up - sigma_dn)


def charm_numeric(
    option_type: str,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    carry: float,
    sigma: float,
    time_epsilon_days: float,
    min_time_years: float,
) -> float:
    epsilon = max(float(time_epsilon_days) / 252.0, 1e-6)
    t_minus = max(min_time_years, time_years - epsilon)
    t_plus = max(min_time_years, time_years + epsilon)
    delta_minus = delta(option_type, spot, strike, t_minus, rate, carry, sigma)
    delta_plus = delta(option_type, spot, strike, t_plus, rate, carry, sigma)
    return (delta_minus - delta_plus) / (t_plus - t_minus)


def calculate_full_greeks(
    option_type: str,
    spot: float,
    strike: float,
    time_years: float,
    rate: float,
    carry: float,
    sigma: float,
    vol_epsilon: float,
    time_epsilon_days: float,
    min_time_years: float,
) -> dict[str, Any]:
    sigma = max(normalize_vol(sigma), 1e-5)
    time_years = max(float(time_years), min_time_years)
    result = {
        "price": price(option_type, spot, strike, time_years, rate, carry, sigma),
        "delta": delta(option_type, spot, strike, time_years, rate, carry, sigma),
        "gamma": gamma(option_type, spot, strike, time_years, rate, carry, sigma),
        "vega": vega(option_type, spot, strike, time_years, rate, carry, sigma),
        "theta": theta(option_type, spot, strike, time_years, rate, carry, sigma),
    }
    result["vanna"] = vanna_numeric(option_type, spot, strike, time_years, rate, carry, sigma, vol_epsilon)
    result["charm"] = charm_numeric(
        option_type,
        spot,
        strike,
        time_years,
        rate,
        carry,
        sigma,
        time_epsilon_days,
        min_time_years,
    )
    result["theta_per_day"] = result["theta"] / 365.0
    result["sigma"] = sigma
    result["time_years"] = time_years
    return result
