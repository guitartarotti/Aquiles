"""
options_greeks_model.py
=======================
Modelo proprietário de Greeks para opções de índice (IBOV / WIN).

Implementa Black-Scholes-Merton europeu com taxa contínua r e carry q,
mais as derivadas de segunda ordem necessárias para GEX / DEX / Vanna / Charm:

  - IV implícita   — bisection + Newton robusto
  - Delta          — ∂V/∂S  (spot delta com ajuste de carry)
  - Gamma          — ∂²V/∂S²  (por 1 ponto e por 1% de movimento)
  - Vega           — ∂V/∂σ  (por 1.00 vol e por 1 vol-point = 0.01)
  - Theta          — ∂V/∂t  (por ano e por DU-252)
  - Rho            — ∂V/∂r  (por 1 bp)
  - Vanna          — ∂²V/∂S∂σ = ∂Δ/∂σ  (sensibilidade do delta à vol)
  - Charm          — ∂Δ/∂t  (decaimento do delta por DU-252)

Lógica de prioridade no pipeline:
  1. Se dados suficientes (S, K, T, price_mid > 0)  →  modelo proprietário
  2. Se modelo falha mas OpLab tem gregas salvas     →  mantém gregas OpLab
  3. Se nenhum dado disponível                       →  insufficient_data

"""
from __future__ import annotations

import math
from typing import Any, Literal

OptionType = Literal["C", "P"]

_SQRT_2PI = math.sqrt(2.0 * math.pi)
_BD_YEAR = 252.0          # dias úteis / ano
_MIN_T = 1.0 / 2520.0    # mínimo ~0.1 DU para evitar singularidade


# ─── Distribuição Normal ──────────────────────────────────────────────────────

def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ─── Conversões de taxa ───────────────────────────────────────────────────────

def aa_to_cont(r_aa: float) -> float:
    """Taxa efetiva anual (a.a.) → taxa contínua: r_cont = ln(1 + r_aa)."""
    if r_aa <= -1.0:
        raise ValueError(f"Taxa anual inválida (<= -100%): {r_aa}")
    return math.log(1.0 + r_aa)


def q_from_forward(S: float, F: float, T: float, r: float) -> float:
    """Infere carry q a partir do futuro: F = S·e^{(r-q)T} → q = r - ln(F/S)/T."""
    if T <= 0 or S <= 0 or F <= 0:
        return 0.0
    return r - math.log(F / S) / T


# ─── BSM core ─────────────────────────────────────────────────────────────────

def _bsm_d1_d2(
    S: float, K: float, T: float, r: float, q: float, sigma: float
) -> tuple[float, float]:
    sqrtT = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    return d1, d2


def bsm_price(
    S: float, K: float, T: float, r: float, q: float,
    sigma: float, opt: OptionType
) -> float:
    """Preço teórico BSM-Merton europeu."""
    if T <= 0:
        return max(S - K, 0.0) if opt == "C" else max(K - S, 0.0)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    if sigma <= 0:
        return max(S * disc_q - K * disc_r, 0.0) if opt == "C" else max(K * disc_r - S * disc_q, 0.0)
    d1, d2 = _bsm_d1_d2(S, K, T, r, q, sigma)
    if opt == "C":
        return S * disc_q * _norm_cdf(d1) - K * disc_r * _norm_cdf(d2)
    return K * disc_r * _norm_cdf(-d2) - S * disc_q * _norm_cdf(-d1)


def _bsm_vega_raw(
    S: float, K: float, T: float, r: float, q: float, sigma: float
) -> float:
    """Vega bruta: ∂V/∂σ por +1.00 vol (para uso interno no solver de IV)."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, _ = _bsm_d1_d2(S, K, T, r, q, sigma)
    return S * math.exp(-q * T) * _norm_pdf(d1) * math.sqrt(T)


# ─── Solver de IV ─────────────────────────────────────────────────────────────

def implied_vol_bsm(
    price_mkt: float,
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    opt: OptionType,
    sigma_lo: float = 1e-6,
    sigma_hi: float = 5.0,
    tol: float = 1e-10,
    max_iter: int = 200,
) -> float:
    """
    IV implícita via bisection + Newton robusto (Bloomberg-like).
    Retorna 0.0 se não convergir ou dados inválidos.
    """
    if price_mkt <= 0 or T <= 0:
        return 0.0

    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)

    if opt == "C":
        lower = max(S * disc_q - K * disc_r, 0.0)
        upper = S * disc_q
    else:
        lower = max(K * disc_r - S * disc_q, 0.0)
        upper = K * disc_r

    pm = min(max(price_mkt, lower + 1e-9), upper - 1e-9)

    def f(sig: float) -> float:
        return bsm_price(S, K, T, r, q, sig, opt) - pm

    flo = f(sigma_lo)
    fhi = f(sigma_hi)
    if flo > 0:
        return sigma_lo
    if fhi < 0:
        return sigma_hi

    lo, hi = sigma_lo, sigma_hi
    sigma = 0.5 * (lo + hi)

    for _ in range(max_iter):
        price = bsm_price(S, K, T, r, q, sigma, opt)
        diff = price - pm
        if abs(diff) < tol:
            return sigma

        v = _bsm_vega_raw(S, K, T, r, q, sigma)
        sigma_new = sigma - diff / v if v > 1e-12 else float("nan")

        if not math.isfinite(sigma_new) or sigma_new <= lo or sigma_new >= hi:
            sigma_new = 0.5 * (lo + hi)

        if f(sigma_new) > 0:
            hi = sigma_new
        else:
            lo = sigma_new

        sigma = sigma_new
        if (hi - lo) < 1e-12:
            return sigma

    return sigma


# ─── Greeks completos (Delta, Gamma, Vega, Theta, Rho, Vanna, Charm) ─────────

def bsm_full_greeks(
    S: float, K: float, T: float, r: float, q: float,
    sigma: float, opt: OptionType
) -> dict[str, float]:
    """
    Retorna todos os Greeks (raw) incluindo Vanna e Charm.

    Campos retornados (sem escalonamento):
      delta_spot   — ∂V/∂S com carry
      gamma_point  — ∂²V/∂S² por 1 ponto
      vega_1vol    — ∂V/∂σ por +1.00 vol
      theta_year   — ∂V/∂t por ano (valor negativo = erosão)
      rho_1rate    — ∂V/∂r por +100% de taxa
      vanna        — ∂Δ/∂σ  (= ∂²V/∂S∂σ)
      charm_year   — ∂Δ/∂T_restante por ano  (positivo = delta sobe ao chegar no venc.)
    """
    if T <= _MIN_T or sigma <= 0:
        return {
            "delta_spot": 0.0, "gamma_point": 0.0,
            "vega_1vol": 0.0, "theta_year": 0.0,
            "rho_1rate": 0.0, "vanna": 0.0, "charm_year": 0.0,
        }

    sqrtT = math.sqrt(T)
    disc_q = math.exp(-q * T)
    disc_r = math.exp(-r * T)
    d1, d2 = _bsm_d1_d2(S, K, T, r, q, sigma)

    Nd1  = _norm_cdf(d1)
    Nd2  = _norm_cdf(d2)
    Nmd1 = _norm_cdf(-d1)
    Nmd2 = _norm_cdf(-d2)
    pdf1 = _norm_pdf(d1)

    # ── Delta ──────────────────────────────────────────────────────────────────
    delta = disc_q * Nd1 if opt == "C" else disc_q * (Nd1 - 1.0)

    # ── Gamma (por 1 ponto de S) ───────────────────────────────────────────────
    gamma = (disc_q * pdf1) / (S * sigma * sqrtT)

    # ── Vega (por +1.00 vol) ───────────────────────────────────────────────────
    vega = S * disc_q * pdf1 * sqrtT

    # ── Theta (por ano) ────────────────────────────────────────────────────────
    base_theta = -(S * disc_q * pdf1 * sigma) / (2.0 * sqrtT)
    if opt == "C":
        theta = base_theta - r * K * disc_r * Nd2 + q * S * disc_q * Nd1
        rho   = K * T * disc_r * Nd2
    else:
        theta = base_theta + r * K * disc_r * Nmd2 - q * S * disc_q * Nmd1
        rho   = -K * T * disc_r * Nmd2

    # ── Vanna = ∂Δ/∂σ = -e^{-qT}·n(d1)·d2/σ ─────────────────────────────────
    vanna = -disc_q * pdf1 * d2 / sigma

    # ── Charm = ∂Δ/∂T_restante por ano ───────────────────────────────────────
    # Derivada de ∂d1/∂T = [2(r-q)T - d2·σ√T] / (2T·σ√T)
    # CALL charm_year = -q·e^{-qT}·N(d1) + e^{-qT}·n(d1)·∂d1/∂T
    # PUT  charm_year =  q·e^{-qT}·N(-d1) - e^{-qT}·n(d1)·∂d1/∂T
    dd1_dT = (2.0 * (r - q) * T - d2 * sigma * sqrtT) / (2.0 * T * sigma * sqrtT)
    if opt == "C":
        charm_year = -q * disc_q * Nd1 + disc_q * pdf1 * dd1_dT
    else:
        charm_year = q * disc_q * Nmd1 - disc_q * pdf1 * dd1_dT

    return {
        "delta_spot": delta,
        "gamma_point": gamma,
        "vega_1vol": vega,
        "theta_year": theta,
        "rho_1rate": rho,
        "vanna": vanna,
        "charm_year": charm_year,
    }


# ─── API pública ──────────────────────────────────────────────────────────────

def compute_greeks_from_snapshot(
    S: float,
    K: float,
    T_du: int | float,
    price_mid: float,
    r_cont: float,
    q_cont: float = 0.0,
    F: float | None = None,
    opt: OptionType = "C",
) -> dict[str, Any] | None:
    """
    Calcula o conjunto completo de Greeks proprietários a partir dos dados do snapshot.

    Parâmetros
    ----------
    S         : preço spot do subjacente (OPT_UNDL_PX)
    K         : strike do contrato
    T_du      : dias úteis até o vencimento (DU-252)
    price_mid : preço mid do contrato (MID ou PX_LAST)
    r_cont    : taxa livre de risco contínua (ex.: 0.148 para CDI 14.8%)
    q_cont    : carry contínuo (default 0 — assume que F já embute q)
    F         : preço do futuro (se fornecido, q é inferido de F e ignora q_cont)
    opt       : "C" (call) ou "P" (put)

    Retorna
    -------
    dict com os Greeks escalados para uso direto no modelo, ou None se dados insuficientes.

    Campos retornados
    -----------------
      iv           — volatilidade implícita (decimal, ex.: 0.25 = 25%)
      delta        — delta spot (0–1 para call; -1–0 para put)
      gamma_point  — gamma por 1 ponto do subjacente
      gamma_1pct   — variação do delta para movimento de +1% no spot
      vega_1vol    — vega por +1.00 vol (100 vol points)
      vega_1pctvol — vega por 1 vol point (0.01)
      theta_year   — theta por ano
      theta_bd252  — theta por 1 dia útil (BD-252)
      rho_1bp      — rho por 1 basis point (0.01%)
      vanna        — ∂Δ/∂σ — como o delta muda com a vol
      charm_bd252  — ∂Δ/∂t por DU-252 (decaimento do delta por dia útil)
      model_ok     — True
    """
    # ── Verificação de suficiência de dados ────────────────────────────────────
    try:
        S_f = float(S)
        K_f = float(K)
        T_du_f = float(T_du)
        pm_f = float(price_mid)
        r_f = float(r_cont)
    except (TypeError, ValueError):
        return None

    if S_f <= 0 or K_f <= 0 or T_du_f < 1 or pm_f <= 0:
        return None

    T = T_du_f / _BD_YEAR
    if T < _MIN_T:
        return None

    # ── Resolve carry q ────────────────────────────────────────────────────────
    if F is not None:
        try:
            q = q_from_forward(S_f, float(F), T, r_f)
        except Exception:
            q = float(q_cont) if q_cont is not None else 0.0
    else:
        q = float(q_cont) if q_cont is not None else 0.0

    # ── IV implícita ───────────────────────────────────────────────────────────
    opt_code: OptionType = "P" if str(opt).upper().startswith("P") else "C"
    sigma = implied_vol_bsm(pm_f, S_f, K_f, T, r_f, q, opt_code)
    if sigma <= 0:
        return None

    # ── Greeks completos ───────────────────────────────────────────────────────
    g = bsm_full_greeks(S_f, K_f, T, r_f, q, sigma, opt_code)

    delta      = g["delta_spot"]
    gamma_pt   = g["gamma_point"]
    vega_1vol  = g["vega_1vol"]
    theta_yr   = g["theta_year"]
    rho_1rate  = g["rho_1rate"]
    vanna      = g["vanna"]
    charm_yr   = g["charm_year"]

    return {
        # IV
        "iv":           sigma,
        # Delta
        "delta":        delta,
        # Gamma (duas escalas)
        "gamma_point":  gamma_pt,
        "gamma_1pct":   gamma_pt * 0.01 * S_f,
        # Vega (duas escalas)
        "vega_1vol":    vega_1vol,
        "vega_1pctvol": vega_1vol * 0.01,
        # Theta (duas bases)
        "theta_year":   theta_yr,
        "theta_bd252":  theta_yr / _BD_YEAR,
        # Rho
        "rho_1bp":      rho_1rate * 0.0001,
        # Segunda ordem — específicos para GEX/DEX/Vanna/Charm
        "vanna":        vanna,
        "charm_bd252":  charm_yr / _BD_YEAR,
        # Metadado
        "model_ok":     True,
    }


def apply_priority_greeks(
    model_result: dict[str, Any] | None,
    oplab_delta: float | None,
    oplab_gamma: float | None,
    oplab_iv: float | None,
    oplab_vega: float | None,
    oplab_theta: float | None,
) -> dict[str, Any]:
    """
    Aplica a lógica de prioridade:
      1. Se modelo proprietário OK → usa modelo
      2. Se OpLab tem gregas       → usa OpLab (sem Vanna/Charm)
      3. Senão                     → insufficient_data

    Retorna dict com campos EFF_* e MODEL_SOURCE.
    """
    if model_result and model_result.get("model_ok"):
        return {
            "EFF_DELTA":      model_result["delta"],
            "EFF_GAMMA_PT":   model_result["gamma_point"],
            "EFF_GAMMA_1PCT": model_result["gamma_1pct"],
            "EFF_IV":         model_result["iv"],
            "EFF_VEGA":       model_result["vega_1pctvol"],
            "EFF_THETA":      model_result["theta_bd252"],
            "EFF_VANNA":      model_result["vanna"],
            "EFF_CHARM":      model_result["charm_bd252"],
            "MODEL_SOURCE":   "proprietary",
        }

    if oplab_delta is not None:
        return {
            "EFF_DELTA":      oplab_delta,
            "EFF_GAMMA_PT":   oplab_gamma,
            "EFF_GAMMA_1PCT": None,
            "EFF_IV":         oplab_iv,
            "EFF_VEGA":       oplab_vega,
            "EFF_THETA":      oplab_theta,
            "EFF_VANNA":      None,   # OpLab não fornece
            "EFF_CHARM":      None,   # OpLab não fornece
            "MODEL_SOURCE":   "oplab",
        }

    return {
        "EFF_DELTA":      None,
        "EFF_GAMMA_PT":   None,
        "EFF_GAMMA_1PCT": None,
        "EFF_IV":         None,
        "EFF_VEGA":       None,
        "EFF_THETA":      None,
        "EFF_VANNA":      None,
        "EFF_CHARM":      None,
        "MODEL_SOURCE":   "insufficient_data",
    }
