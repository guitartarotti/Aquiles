"""
sabr_hedge_model.py

Modelo matemático de tesouraria para hedge de delta de opções IBOVESPA.

Camadas implementadas:
  1. SABR (Hagan et al. 2002) — calibração da superfície de vol e delta smile-consistent
  2. Delta smile-consistent = Δ_BS(σ_SABR) + vega × ∂σ_SABR/∂F  (correção de vanna)
  3. Whalley-Wilmott (1997) — banda ótima de rebalanceamento com custo de transação

Referências:
  - Hagan P.S. et al. (2002) "Managing Smile Risk" Wilmott Magazine
  - Whalley A.E. & Wilmott P. (1997) "An Asymptotic Analysis of an Optimal Hedging
    Model for Option Pricing with Transaction Costs" Mathematical Finance 7(3)
  - Leland H.E. (1985) "Option Pricing and Replication with Transaction Costs" JoF 40(5)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("aquiles.sabr_hedge_model")


def _native_scalar(value: Any) -> Any:
    """Converte escalares numpy/pandas para tipos nativos do Python."""
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return 0.0
        return float(value)
    return value


def _rounded_float(value: Any, digits: int) -> float:
    try:
        return round(float(_native_scalar(value) or 0.0), digits)
    except Exception:
        return 0.0

# ─── Constantes de mercado IBOVESPA / B3 ──────────────────────────────────────

# Fator de conversão de exposição IBOVE (opções) → IBOV (futuro)
# Calibrado empiricamente: 50k calls típicas (Δ 0.3-0.74) → 3-7k WIN
IBOVE_TO_IBOV = 0.04

# Multiplicador financeiro por ponto de IBOV (R$/pt por contrato)
FUT_MULT = {"WIN": 0.20, "IND": 1.00}

# Beta padrão para IBOVESPA (square-root process — entre log-normal e normal)
# β=0.5 é padrão para índices de equity; β=1.0 seria Black-Scholes puro
DEFAULT_BETA = 0.5

# Chute inicial para calibração
DEFAULT_ALPHA = 0.18   # vol ATM inicial
DEFAULT_RHO   = -0.30  # correlação negativa típica em equity (skew de baixa)
DEFAULT_NU    = 0.40   # vol-of-vol típico para IBOV

# Custo de transação padrão (bps round-trip por contrato WIN)
DEFAULT_TC_BPS = 10.0

# ─── SABR Vol Formula (Hagan et al. 2002) ─────────────────────────────────────

def sabr_vol(F: float, K: float, T: float,
             alpha: float, beta: float, rho: float, nu: float) -> float:
    """
    Volatilidade implícita SABR para forward F, strike K, maturidade T.

    Implementa a fórmula expandida de Hagan et al. (2002) §2.17b.
    β é mantido fixo (não calibrado) para estabilidade numérica.

    Retorna σ_SABR em decimal (ex: 0.20 = 20% a.a.).
    """
    if F <= 0 or K <= 0 or T <= 0 or alpha <= 0:
        return 0.0

    eps = 1e-7

    # Caso ATM: F ≈ K  (expansão separada para evitar divisão por zero em ln(F/K))
    if abs(F - K) < eps * F:
        FK_mid = F ** (1.0 - beta)
        atm_num = alpha
        atm_den = FK_mid
        corr_term = (
            ((1 - beta) ** 2 * alpha ** 2) / (24.0 * FK_mid ** 2)
            + (rho * beta * nu * alpha) / (4.0 * FK_mid)
            + (2.0 - 3.0 * rho ** 2) * nu ** 2 / 24.0
        )
        return (atm_num / atm_den) * (1.0 + corr_term * T)

    log_FK = math.log(F / K)
    FK_geom = (F * K) ** ((1.0 - beta) / 2.0)

    # z = (ν/α) × (FK)^((1-β)/2) × ln(F/K)
    z = (nu / alpha) * FK_geom * log_FK

    # χ(z) = ln((√(1-2ρz+z²) + z - rho) / (1-rho))
    discriminant = 1.0 - 2.0 * rho * z + z * z
    if discriminant <= 0:
        discriminant = eps
    chi_z_num = math.sqrt(discriminant) + z - rho
    chi_z_den = 1.0 - rho
    if chi_z_num <= 0 or chi_z_den <= 0:
        # Degenerate; return ATM approximation
        return sabr_vol(F, F, T, alpha, beta, rho, nu)
    chi_z = math.log(chi_z_num / chi_z_den)
    z_over_chi = z / chi_z if abs(chi_z) > eps else 1.0

    # Denominador da fórmula (expansão em (1-β)²)
    log_FK_sq = log_FK ** 2
    one_m_beta_sq = (1.0 - beta) ** 2
    denom_correction = (
        1.0
        + one_m_beta_sq / 24.0 * log_FK_sq
        + one_m_beta_sq ** 2 / 1920.0 * log_FK_sq ** 2
    )

    term1 = alpha / (FK_geom * denom_correction)

    # Correção temporal (expansão em T)
    FK_mid = FK_geom  # nota: FK_geom = (FK)^((1-β)/2)  →  FK_mid² = (FK)^(1-β)
    FK_mid_sq = FK_geom ** 2
    time_correction = (
        one_m_beta_sq * alpha ** 2 / (24.0 * FK_mid_sq)
        + rho * beta * nu * alpha / (4.0 * FK_geom)
        + (2.0 - 3.0 * rho ** 2) * nu ** 2 / 24.0
    )

    return term1 * z_over_chi * (1.0 + time_correction * T)


# ─── Black-Scholes helpers ─────────────────────────────────────────────────────

_SQRT2    = math.sqrt(2.0)
_SQRT2PI  = math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / _SQRT2))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT2PI


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    """d₁ e d₂ do modelo Black-Scholes (sem dividend yield)."""
    T = max(T, 1e-8)
    sigma = max(sigma, 1e-8)
    sv = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / sv
    d2 = d1 - sv
    return d1, d2


def bs_delta(pc: str, S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Delta Black-Scholes padrão (sem custo de carrego)."""
    d1, _ = _d1_d2(S, K, T, r, sigma)
    if pc.upper().startswith("C"):
        return _norm_cdf(d1)
    return _norm_cdf(d1) - 1.0


def bs_vega(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Vega Black-Scholes (∂V/∂σ)."""
    T = max(T, 1e-8)
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return S * _norm_pdf(d1) * math.sqrt(T)


def bs_gamma(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Gamma Black-Scholes (∂²V/∂S²)."""
    T = max(T, 1e-8)
    sigma = max(sigma, 1e-8)
    d1, _ = _d1_d2(S, K, T, r, sigma)
    denom = S * sigma * math.sqrt(T)
    return _norm_pdf(d1) / denom if denom > 0 else 0.0


# ─── Smile-consistent Delta (SABR) ────────────────────────────────────────────

def sabr_smile_delta(
    pc: str,
    S: float, K: float, T: float,
    r: float,
    alpha: float, beta: float, rho: float, nu: float,
    h_pct: float = 0.001,
) -> tuple[float, float]:
    """
    Delta smile-consistent (sticky smile) para o modelo SABR.

    Fórmula:
        Δ_smile = Δ_BS(σ_SABR(K)) + vega × ∂σ_SABR/∂S

    A sensibilidade ∂σ_SABR/∂S é aproximada numericamente por diferença central
    em S (mantendo K fixo = sticky-strike convention), que é a convenção usual para
    dealers de equity index.

    Retorna (delta_smile, sigma_impl).
    """
    F = S * math.exp(r * T)   # forward price (sem dividendos)
    sigma_impl = sabr_vol(F, K, T, alpha, beta, rho, nu)
    if sigma_impl <= 0:
        sigma_impl = DEFAULT_ALPHA   # fallback

    # BS delta avaliado na vol SABR
    d_bs = bs_delta(pc, S, K, T, r, sigma_impl)

    # Sensibilidade ∂σ_SABR/∂S por diferença central (sticky-strike)
    h = S * h_pct
    F_up   = (S + h) * math.exp(r * T)
    F_dn   = (S - h) * math.exp(r * T)
    sv_up  = sabr_vol(F_up, K, T, alpha, beta, rho, nu)
    sv_dn  = sabr_vol(F_dn, K, T, alpha, beta, rho, nu)
    d_sigma_dS = (sv_up - sv_dn) / (2.0 * h)

    # Correção de vanna: vega × ∂σ/∂S
    vega   = bs_vega(S, K, T, r, sigma_impl)
    delta  = d_bs + vega * d_sigma_dS

    # Clamp físico: delta ∈ [-1, 1]
    delta = max(-1.0, min(1.0, delta))
    return delta, sigma_impl


def sabr_smile_gamma(
    S: float, K: float, T: float,
    r: float,
    alpha: float, beta: float, rho: float, nu: float,
    h_pct: float = 0.001,
) -> float:
    """
    Gamma smile-consistent para o modelo SABR.
    Aproximado numericamente: Γ_smile ≈ (Δ(S+h) - Δ(S-h)) / (2h)
    """
    h = S * h_pct
    d_up, _ = sabr_smile_delta("C", S + h, K, T, r, alpha, beta, rho, nu)
    d_dn, _ = sabr_smile_delta("C", S - h, K, T, r, alpha, beta, rho, nu)
    return (d_up - d_dn) / (2.0 * h)


# ─── Calibração SABR ──────────────────────────────────────────────────────────

@dataclass
class SABRParams:
    """Parâmetros calibrados do modelo SABR."""
    alpha:  float = DEFAULT_ALPHA
    beta:   float = DEFAULT_BETA
    rho:    float = DEFAULT_RHO
    nu:     float = DEFAULT_NU
    rmse:   float = 0.0              # erro de calibração (RMSE em vol)
    n_pts:  int   = 0                # pontos usados na calibração
    source: str   = "default"        # "calibrated" | "atm_only" | "default"

    def to_dict(self) -> dict:
        return {
            "alpha": _rounded_float(self.alpha, 6),
            "beta":  _rounded_float(self.beta, 6),
            "rho":   _rounded_float(self.rho, 6),
            "nu":    _rounded_float(self.nu, 6),
            "rmse":  _rounded_float(self.rmse, 6),
            "n_pts": int(_native_scalar(self.n_pts) or 0),
            "source": str(_native_scalar(self.source) or "default"),
        }


def calibrate_sabr(
    surface_points: list[dict],
    S: float,
    T: float,
    r: float = 0.115,
    beta: float = DEFAULT_BETA,
    atm_vol: float | None = None,
) -> SABRParams:
    """
    Calibra os parâmetros SABR (α, ρ, ν) com β fixo a partir de pontos da
    superfície de vol (smile slice para um vencimento T).

    surface_points: lista de dicts com chaves 'strike' e 'iv'
                    (iv em decimal, ex: 0.20 para 20%)
    S: spot atual
    T: time-to-expiry em anos
    beta: mantido fixo (padrão 0.5 para equity index)
    atm_vol: vol ATM se disponível separadamente (usado como ponto âncora)

    Retorna SABRParams calibrados.
    """
    try:
        from scipy.optimize import minimize
    except ImportError:
        logger.warning("[SABR] scipy não disponível — usando parâmetros default")
        return SABRParams(source="default")

    F = S * math.exp(r * T)

    # Prepara pontos válidos
    pts: list[tuple[float, float]] = []
    for p in (surface_points or []):
        try:
            K  = float(p.get("strike", 0))
            iv = float(p.get("iv", 0))
            if K > 0 and 0.01 <= iv <= 2.0:
                pts.append((K, iv))
        except Exception:
            continue

    # Adiciona ponto ATM se fornecido e não estiver já incluso
    if atm_vol and 0.01 <= atm_vol <= 2.0:
        pts.append((F, atm_vol))

    if len(pts) < 2:
        # Sem dados suficientes — estima α para bater vol ATM
        atm = atm_vol or DEFAULT_ALPHA
        alpha0 = atm * (F ** (1 - beta))
        return SABRParams(
            alpha=alpha0, beta=beta,
            rho=DEFAULT_RHO, nu=DEFAULT_NU,
            n_pts=len(pts), source="atm_only",
        )

    # Pesos: mais peso para strikes próximos ao spot (ATM ± 5%)
    def _weight(K: float) -> float:
        m = abs(K / F - 1.0)
        return math.exp(-10.0 * m)

    def _objective(params: list) -> float:
        alpha_p, rho_p, nu_p = params
        if alpha_p <= 0 or not (-0.999 < rho_p < 0.999) or nu_p <= 0:
            return 1e6
        err = 0.0
        for K, iv_mkt in pts:
            iv_model = sabr_vol(F, K, T, alpha_p, beta, rho_p, nu_p)
            w = _weight(K)
            err += w * (iv_model - iv_mkt) ** 2
        return err

    # Chute inicial: estima alpha para bater vol ATM
    atm_est = atm_vol or (sum(iv for _, iv in pts) / len(pts))
    alpha0   = atm_est * (F ** (1 - beta))

    x0     = [alpha0, DEFAULT_RHO, DEFAULT_NU]
    bounds = [(1e-4, 5.0), (-0.999, 0.999), (1e-4, 5.0)]

    try:
        res = minimize(
            _objective, x0,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 500, "ftol": 1e-12},
        )
        alpha_c, rho_c, nu_c = res.x
        rmse = math.sqrt(res.fun / max(len(pts), 1))

        # Sanidade
        if not math.isfinite(alpha_c) or alpha_c <= 0:
            raise ValueError("alpha inválido pós-calibração")

        logger.info(
            "[SABR] calibrado — α=%.4f β=%.2f ρ=%.3f ν=%.4f RMSE=%.4f pts=%d",
            alpha_c, beta, rho_c, nu_c, rmse, len(pts),
        )
        return SABRParams(
            alpha=alpha_c, beta=beta, rho=rho_c, nu=nu_c,
            rmse=rmse, n_pts=len(pts), source="calibrated",
        )
    except Exception as exc:
        logger.warning("[SABR] calibração falhou (%s) — usando default", exc)
        return SABRParams(source="default")


# ─── Whalley-Wilmott Hedging Band ─────────────────────────────────────────────

def whalley_wilmott_band(
    gamma: float,
    spot: float,
    sigma: float,
    tc_bps: float = DEFAULT_TC_BPS,
    dt_minutes: float = 60.0,
) -> float:
    """
    Meia-largura da banda ótima de hedge (Whalley & Wilmott 1997).

    O dealer só rehedgeia quando o delta acumulado sair da banda ±ε.
    Fórmula assintótica (eq. 4.3 do paper):

        ε = ((3κ/2) × Γ² × S² × σ × √(2π × dt))^(1/3)

    onde:
        κ   = custo de transação round-trip (fração decimal)
        Γ   = gamma da posição
        S   = spot
        σ   = vol implícita
        dt  = intervalo de monitoramento em anos

    Retorna ε em unidades de delta (fração do nocional).
    Para converter em contratos WIN:
        ε_WIN = ε × volume × IBOVE_TO_IBOV / FUT_MULT_WIN
    """
    if abs(gamma) < 1e-16 or spot <= 0 or sigma <= 0:
        return 0.0

    tc = max(tc_bps, 0.0) / 10_000.0
    if tc <= 0:
        return 0.0

    # Converte dt de minutos para anos (252 dias × 6.5h × 60min)
    dt_years = dt_minutes / (252.0 * 6.5 * 60.0)

    inner = (3.0 / 2.0) * tc * (gamma ** 2) * (spot ** 2) * sigma * math.sqrt(2.0 * math.pi * dt_years)
    if inner <= 0:
        return 0.0
    return inner ** (1.0 / 3.0)


# ─── Cálculo de contratos de hedge ────────────────────────────────────────────

@dataclass
class HedgeResult:
    """Resultado do hedge para um único evento de volume."""
    strike:       float
    put_call:     str
    volume:       float
    spot:         float

    # Deltas
    delta_bs:     float    # Black-Scholes baseline
    delta_sabr:   float    # SABR smile-consistent (corrigido de vanna)
    sigma_impl:   float    # Vol implícita SABR no strike/maturidade

    # Gamma
    gamma_sabr:   float

    # Contratos de hedge
    n_win:        float    # WIN (mini Ibovespa)
    n_ind:        float    # IND (Ibovespa cheio)

    # Whalley-Wilmott
    band_win:     float    # meia-largura da banda em contratos WIN
    band_ind:     float    # meia-largura da banda em contratos IND
    needs_hedge:  bool     # True se delta saiu da banda desde último hedge

    def to_dict(self) -> dict:
        return {
            "strike":      _rounded_float(self.strike, 3),
            "put_call":    str(_native_scalar(self.put_call) or ""),
            "volume":      _rounded_float(self.volume, 3),
            "spot":        _rounded_float(self.spot, 3),
            "delta_bs":    _rounded_float(self.delta_bs, 5),
            "delta_sabr":  _rounded_float(self.delta_sabr, 5),
            "sigma_impl":  _rounded_float(self.sigma_impl, 5),
            "gamma_sabr":  _rounded_float(self.gamma_sabr, 8),
            "n_win":       _rounded_float(self.n_win, 1),
            "n_ind":       _rounded_float(self.n_ind, 1),
            "band_win":    _rounded_float(self.band_win, 1),
            "band_ind":    _rounded_float(self.band_ind, 1),
            "needs_hedge": bool(_native_scalar(self.needs_hedge)),
        }


def compute_hedge(
    events: list[dict],
    spot: float,
    sabr_params: SABRParams,
    market_ctx: dict | None = None,
    fut_type: str = "WIN",
    tc_bps: float = DEFAULT_TC_BPS,
    dt_minutes: float = 60.0,
) -> list[HedgeResult]:
    """
    Calcula contratos de hedge para uma lista de eventos de volume.

    Cada evento deve ter:
        strike      (float) — strike da opção
        put_call    (str)   — 'C' ou 'P'
        volume      (float) — volume de contratos movimentados
        spot_price  (float) — spot no momento (opcional, usa `spot` como fallback)
        days_to_maturity (int) — dias até vencimento (opcional)
        observed_delta (float) — delta observado da Bloomberg (override prioritário)

    Retorna lista de HedgeResult.
    """
    ctx    = market_ctx or {}
    r      = float(ctx.get("risk_free_rate") or 0.115)
    sigma0 = float(ctx.get("implied_vol")    or DEFAULT_ALPHA)
    dte0   = int(  ctx.get("days_to_expiry") or 21)

    FUT_MULT.get(fut_type.upper(), FUT_MULT["WIN"])
    results: list[HedgeResult] = []

    alpha = sabr_params.alpha
    beta  = sabr_params.beta
    rho   = sabr_params.rho
    nu    = sabr_params.nu

    for ev in events:
        try:
            K   = float(ev.get("strike")   or 0)
            vol = float(ev.get("volume")   or ev.get("volume_delta") or 0)
            pc  = str(  ev.get("put_call") or "C").upper().strip()
            pc  = "P" if pc.startswith("P") else "C"

            ev_spot = float(ev.get("spot_price") or 0) or spot
            dte     = int(  ev.get("days_to_maturity") or dte0)
            T       = max(dte / 252.0, 1.0 / 252.0)

            if K <= 0 or vol <= 0 or ev_spot <= 0:
                continue

            # ── Delta e vol implícita ────────────────────────────────────────
            obs_delta = ev.get("observed_delta")
            if obs_delta is not None:
                # Bloomberg delta observado — prioridade máxima
                d_sabr   = max(-1.0, min(1.0, float(obs_delta)))
                sigma_impl = sabr_vol(
                    ev_spot * math.exp(r * T), K, T,
                    alpha, beta, rho, nu,
                ) or sigma0
                d_bs = bs_delta(pc, ev_spot, K, T, r, sigma_impl)
            else:
                d_sabr, sigma_impl = sabr_smile_delta(
                    pc, ev_spot, K, T, r, alpha, beta, rho, nu,
                )
                d_bs = bs_delta(pc, ev_spot, K, T, r, sigma_impl)

            # ── Gamma SABR ───────────────────────────────────────────────────
            gamma = sabr_smile_gamma(ev_spot, K, T, r, alpha, beta, rho, nu)

            # ── Contratos de hedge ───────────────────────────────────────────
            n_win = (d_sabr * vol * IBOVE_TO_IBOV) / FUT_MULT["WIN"]
            n_ind = (d_sabr * vol * IBOVE_TO_IBOV) / FUT_MULT["IND"]

            # ── Banda Whalley-Wilmott ────────────────────────────────────────
            eps_delta = whalley_wilmott_band(gamma, ev_spot, sigma_impl, tc_bps, dt_minutes)
            eps_win   = (eps_delta * vol * IBOVE_TO_IBOV) / FUT_MULT["WIN"]
            eps_ind   = (eps_delta * vol * IBOVE_TO_IBOV) / FUT_MULT["IND"]

            # needs_hedge: True se a diferença entre delta SABR e BS sai da banda
            # (na prática o front-end pode comparar com posição acumulada)
            delta_diff = abs(d_sabr - d_bs)
            needs_hedge = delta_diff * abs(vol) * IBOVE_TO_IBOV / FUT_MULT["WIN"] > eps_win

            results.append(HedgeResult(
                strike      = K,
                put_call    = pc,
                volume      = vol,
                spot        = ev_spot,
                delta_bs    = d_bs,
                delta_sabr  = d_sabr,
                sigma_impl  = sigma_impl,
                gamma_sabr  = gamma,
                n_win       = n_win,
                n_ind       = n_ind,
                band_win    = eps_win,
                band_ind    = eps_ind,
                needs_hedge = needs_hedge,
            ))
        except Exception as exc:
            logger.debug("[SABR] evento ignorado por erro: %s — ev=%s", exc, ev)
            continue

    return results


# ─── Classe principal ──────────────────────────────────────────────────────────

class SABRHedgeModel:
    """
    Interface de alto nível para o modelo SABR + Whalley-Wilmott.

    Uso típico:
        model = SABRHedgeModel()
        params = model.calibrate(vol_surface_points, spot, T, r)
        results = model.hedge_contracts(events, spot, market_ctx, params)
    """

    def __init__(self, beta: float = DEFAULT_BETA, tc_bps: float = DEFAULT_TC_BPS):
        self.beta   = beta
        self.tc_bps = tc_bps

    def calibrate(
        self,
        vol_surface: list[dict],
        spot: float,
        T: float,
        r: float = 0.115,
        atm_vol: float | None = None,
    ) -> SABRParams:
        """
        Calibra os parâmetros SABR a partir dos pontos da superfície de vol.

        vol_surface: lista de {strike, iv, put_call, dte}
        Filtra automaticamente pelo dte mais próximo de T (em dias úteis).
        """
        T_days = T * 252
        # Usa pontos de uma fatia do smile (dte ± 5 dias de T_days)
        slice_pts = []
        for p in (vol_surface or []):
            dte = float(p.get("dte") or p.get("days_to_expiry") or T_days)
            if abs(dte - T_days) <= 10:
                slice_pts.append(p)

        # Fallback: usa todos os pontos se slice vazio
        if not slice_pts:
            slice_pts = vol_surface or []

        return calibrate_sabr(slice_pts, spot, T, r, self.beta, atm_vol)

    def hedge_contracts(
        self,
        events: list[dict],
        spot: float,
        market_ctx: dict | None = None,
        sabr_params: SABRParams | None = None,
        vol_surface: list[dict] | None = None,
        fut_type: str = "WIN",
        dt_minutes: float = 60.0,
    ) -> tuple[SABRParams, list[HedgeResult]]:
        """
        Pipeline completo: calibra (opcional) + calcula hedge de todos os eventos.

        Se sabr_params não fornecido, calibra automaticamente a partir de vol_surface.

        Retorna (params_usados, lista_de_HedgeResult).
        """
        ctx   = market_ctx or {}
        r     = float(ctx.get("risk_free_rate") or 0.115)
        dte   = int(  ctx.get("days_to_expiry") or 21)
        T     = max(dte / 252.0, 1.0 / 252.0)
        sigma = float(ctx.get("implied_vol") or DEFAULT_ALPHA)

        if sabr_params is None:
            sabr_params = self.calibrate(
                vol_surface or [], spot, T, r, atm_vol=sigma,
            )

        results = compute_hedge(
            events      = events,
            spot        = spot,
            sabr_params = sabr_params,
            market_ctx  = market_ctx,
            fut_type    = fut_type,
            tc_bps      = self.tc_bps,
            dt_minutes  = dt_minutes,
        )
        return sabr_params, results
