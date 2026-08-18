from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont


BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.services.fair_value_legs_chart_service import (  # noqa: E402
    BENCHMARK_SYMBOL,
    DEFAULT_LEG_DEFINITIONS,
    RPC_COMPONENT_DEFINITIONS,
    FairValueLegsChartService,
)


WINDOWS_SECONDS = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "60min": 3600,
}
PRIMARY_WINDOW = "15min"
LAGS_SECONDS = [0, 1, 5, 15, 30, 60, -1, -5, -15, -30, -60]


def safe_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    return parsed if math.isfinite(parsed) else None


def minutes_from_hhmm(value: str, fallback: int) -> int:
    try:
        hour, minute = value.split(":", 1)
        return int(hour) * 60 + int(minute)
    except Exception:
        return fallback


def clean_symbol_filename(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", symbol.strip())[:90]


def stats(values: pd.Series | list[float] | np.ndarray) -> dict[str, float | None]:
    series = pd.Series(values, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if series.empty:
        return {"mean": None, "median": None, "std": None, "min": None, "max": None}
    return {
        "mean": round(float(series.mean()), 8),
        "median": round(float(series.median()), 8),
        "std": round(float(series.std(ddof=0)), 8),
        "min": round(float(series.min()), 8),
        "max": round(float(series.max()), 8),
    }


def error_stats(values: pd.Series) -> dict[str, float | None]:
    series = pd.Series(values, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if series.empty:
        return {
            "erro_mean": None,
            "erro_median": None,
            "erro_std": None,
            "erro_min": None,
            "erro_max": None,
            "mae": None,
            "rmse": None,
        }
    return {
        "erro_mean": round(float(series.mean()), 6),
        "erro_median": round(float(series.median()), 6),
        "erro_std": round(float(series.std(ddof=0)), 6),
        "erro_min": round(float(series.min()), 6),
        "erro_max": round(float(series.max()), 6),
        "mae": round(float(series.abs().mean()), 6),
        "rmse": round(float(math.sqrt((series**2).mean())), 6),
    }


def collect_default_symbols() -> set[str]:
    symbols = {BENCHMARK_SYMBOL}
    for leg in DEFAULT_LEG_DEFINITIONS:
        symbols.update(str(symbol) for symbol in leg.get("assets") or [] if str(symbol).strip())
    for component in RPC_COMPONENT_DEFINITIONS:
        symbols.update(str(symbol) for symbol in component.get("symbols") or [] if str(symbol).strip())
        symbols.update(str(symbol) for symbol in component.get("short_symbols") or [] if str(symbol).strip())
        symbols.update(str(symbol) for symbol in component.get("long_symbols") or [] if str(symbol).strip())
    return symbols


def load_frame(
    service: FairValueLegsChartService,
    *,
    sessions: int,
    session_start: str,
    session_end: str,
    symbols: set[str],
) -> tuple[pd.DataFrame, list[str]]:
    paths = service._candidate_row_files(sessions)
    frame = service._read_rows(
        paths=paths,
        needed_symbols=symbols,
        session_start_minutes=minutes_from_hhmm(session_start, 9 * 60),
        session_end_minutes=minutes_from_hhmm(session_end, (18 * 60) + 30),
    )
    valid_sessions = service._latest_valid_sessions(frame, sessions)
    if valid_sessions:
        frame = frame[frame["session_date"].isin(valid_sessions)].copy()
    return frame, valid_sessions


def build_aligned_data(
    frame: pd.DataFrame,
    symbols: list[str],
    *,
    freq: str = "1s",
    ffill_limit_seconds: int = 30,
) -> dict[str, Any]:
    price_frames: list[pd.DataFrame] = []
    intraday_frames: list[pd.DataFrame] = []
    session_frames: list[pd.Series] = []
    previous_close_frames: list[pd.DataFrame] = []

    for session_date, session_frame in frame.groupby("session_date", sort=True):
        scoped = session_frame.copy()
        scoped["clean_price"] = scoped["price"].where(scoped["intraday_return_decimal"].notna())
        scoped["aligned_at"] = scoped["captured_at"].dt.floor(freq)
        scoped = scoped[scoped["symbol"].isin(symbols)]
        if scoped.empty:
            continue
        start = scoped["aligned_at"].min()
        end = scoped["aligned_at"].max().ceil(freq)
        index = pd.date_range(start=start, end=end, freq=freq, tz="UTC")
        limit = max(int(ffill_limit_seconds / pd.Timedelta(freq).total_seconds()), 1)

        prices = (
            scoped.pivot_table(index="aligned_at", columns="symbol", values="clean_price", aggfunc="last")
            .sort_index()
            .reindex(index)
            .ffill(limit=limit)
        )
        intraday = (
            scoped.pivot_table(index="aligned_at", columns="symbol", values="intraday_return_decimal", aggfunc="last")
            .sort_index()
            .reindex(index)
            .ffill(limit=limit)
        )
        prev_close_map = (
            scoped.sort_values("captured_at")
            .groupby("symbol")["asset_previous_close"]
            .last()
            .to_dict()
        )
        previous_close = pd.DataFrame(index=index)
        for symbol in symbols:
            value = safe_float(prev_close_map.get(symbol))
            if value is not None:
                previous_close[symbol] = value

        price_frames.append(prices)
        intraday_frames.append(intraday)
        session_frames.append(pd.Series(str(session_date), index=index, name="session_date"))
        previous_close_frames.append(previous_close)

    prices = pd.concat(price_frames).sort_index() if price_frames else pd.DataFrame()
    intraday_returns = pd.concat(intraday_frames).sort_index() if intraday_frames else pd.DataFrame()
    sessions = pd.concat(session_frames).sort_index() if session_frames else pd.Series(dtype="object")
    previous_closes = pd.concat(previous_close_frames).sort_index() if previous_close_frames else pd.DataFrame()

    log_returns = prices.groupby(sessions, group_keys=False).apply(lambda item: np.log(item / item.shift(1)))
    log_returns = log_returns.replace([np.inf, -np.inf], np.nan)

    return {
        "prices": prices,
        "intraday_returns": intraday_returns,
        "log_returns": log_returns,
        "sessions": sessions,
        "previous_closes": previous_closes,
    }


def rolling_metrics(
    asset_returns: pd.Series,
    xb1_returns: pd.Series,
    window_seconds: int,
    *,
    beta_clip: float,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    min_periods = max(20, int(window_seconds * 0.25))
    corr = asset_returns.rolling(window_seconds, min_periods=min_periods).corr(xb1_returns)
    sigma_xb1 = xb1_returns.rolling(window_seconds, min_periods=min_periods).std(ddof=0)
    sigma_asset = asset_returns.rolling(window_seconds, min_periods=min_periods).std(ddof=0)
    elasticity = sigma_xb1 / sigma_asset.where(sigma_asset > 1e-10)
    beta = (corr * elasticity).clip(lower=-beta_clip, upper=beta_clip)
    return corr.replace([np.inf, -np.inf], np.nan), elasticity.replace([np.inf, -np.inf], np.nan), beta.replace([np.inf, -np.inf], np.nan)


def session_shift(series: pd.Series, sessions: pd.Series, periods: int) -> pd.Series:
    return series.groupby(sessions, group_keys=False).shift(periods)


def lag_label(seconds: int) -> str:
    if seconds == 0:
        return "sync_0s"
    if seconds > 0:
        return f"ativo_lidera_XB1_{seconds}s"
    return f"XB1_lidera_ativo_{abs(seconds)}s"


def compute_lag_metrics(
    *,
    lag_seconds: int,
    asset_returns: pd.Series,
    asset_intraday: pd.Series,
    xb1_returns: pd.Series,
    xb1_price: pd.Series,
    xb1_previous_close: pd.Series,
    sessions: pd.Series,
    beta_clip: float,
) -> dict[str, Any] | None:
    shifted_returns = session_shift(asset_returns, sessions, lag_seconds)
    shifted_intraday = session_shift(asset_intraday, sessions, lag_seconds)
    paired = pd.concat([shifted_returns, xb1_returns], axis=1, keys=["asset", "xb1"]).dropna()
    if len(paired) < 60:
        return None
    pearson = safe_float(paired["asset"].corr(paired["xb1"]))
    sigma_asset = safe_float(paired["asset"].std(ddof=0))
    sigma_xb1 = safe_float(paired["xb1"].std(ddof=0))
    if pearson is None or sigma_asset is None or sigma_xb1 is None or sigma_asset <= 1e-10:
        return None
    beta = max(-beta_clip, min(beta_clip, pearson * (sigma_xb1 / sigma_asset)))
    projected = xb1_previous_close + (xb1_previous_close * shifted_intraday * beta)
    error = xb1_price - projected
    err = error_stats(error)
    corr_rolling, _, beta_rolling = rolling_metrics(shifted_returns, xb1_returns, WINDOWS_SECONDS[PRIMARY_WINDOW], beta_clip=beta_clip)
    beta_std = safe_float(beta_rolling.std(ddof=0))
    stability = abs(beta) / (abs(beta) + (beta_std or 0.0) + 1e-9)
    rmse_value = err.get("rmse")
    xb1_scale = safe_float(xb1_price.std(ddof=0)) or 1.0
    rmse_score = 1.0 - min((rmse_value or xb1_scale) / xb1_scale, 1.0)
    lead_bonus = 0.08 if lag_seconds > 0 else -0.03 if lag_seconds < 0 else 0.0
    score = (0.45 * abs(pearson)) + (0.35 * rmse_score) + (0.15 * stability) + lead_bonus
    return {
        "lag_seconds": lag_seconds,
        "label": lag_label(lag_seconds),
        "pearson": round(float(pearson), 8),
        "beta": round(float(beta), 8),
        "rmse": err.get("rmse"),
        "mae": err.get("mae"),
        "beta_std": round(float(beta_std), 8) if beta_std is not None else None,
        "stability": round(float(stability), 8),
        "score": round(float(score), 8),
        "samples": int(len(paired)),
    }


def percentile_rank(values: list[float], value: float, *, higher_is_better: bool = True) -> float:
    clean = [float(item) for item in values if math.isfinite(float(item))]
    if not clean:
        return 0.0
    if not higher_is_better:
        clean = [-item for item in clean]
        value = -value
    return sum(1 for item in clean if item <= value) / len(clean)


def analyze_asset(
    symbol: str,
    data: dict[str, Any],
    *,
    beta_clip: float,
    chart_dir: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    prices: pd.DataFrame = data["prices"]
    intraday_returns: pd.DataFrame = data["intraday_returns"]
    log_returns: pd.DataFrame = data["log_returns"]
    previous_closes: pd.DataFrame = data["previous_closes"]
    sessions: pd.Series = data["sessions"]

    if symbol not in prices.columns or BENCHMARK_SYMBOL not in prices.columns:
        return None, None

    xb1_price = prices[BENCHMARK_SYMBOL]
    xb1_returns = log_returns[BENCHMARK_SYMBOL]
    xb1_previous_close = previous_closes[BENCHMARK_SYMBOL]
    asset_returns = log_returns[symbol]
    asset_intraday = intraday_returns[symbol]

    paired = pd.concat([asset_returns, xb1_returns], axis=1, keys=["asset", "xb1"]).dropna()
    if len(paired) < 60:
        return None, None

    rolling: dict[str, dict[str, Any]] = {}
    primary_corr = primary_elasticity = primary_beta = None
    for window_name, window_seconds in WINDOWS_SECONDS.items():
        corr, elasticity, beta = rolling_metrics(asset_returns, xb1_returns, window_seconds, beta_clip=beta_clip)
        rolling[window_name] = {
            "pearson": stats(corr),
            "elasticidade": stats(elasticity),
            "beta": stats(beta),
        }
        if window_name == PRIMARY_WINDOW:
            primary_corr, primary_elasticity, primary_beta = corr, elasticity, beta

    full_pearson = safe_float(paired["asset"].corr(paired["xb1"]))
    full_sigma_asset = safe_float(paired["asset"].std(ddof=0))
    full_sigma_xb1 = safe_float(paired["xb1"].std(ddof=0))
    full_elasticity = None
    full_beta = None
    if full_pearson is not None and full_sigma_asset and full_sigma_asset > 1e-10 and full_sigma_xb1 is not None:
        full_elasticity = full_sigma_xb1 / full_sigma_asset
        full_beta = max(-beta_clip, min(beta_clip, full_pearson * full_elasticity))

    beta_for_projection = primary_beta.ffill().fillna(full_beta or 0.0)
    impact_return = asset_intraday * beta_for_projection
    impact_points = xb1_previous_close * impact_return
    projected_line = xb1_previous_close + impact_points
    error = xb1_price - projected_line

    lag_metrics = []
    for lag in LAGS_SECONDS:
        item = compute_lag_metrics(
            lag_seconds=lag,
            asset_returns=asset_returns,
            asset_intraday=asset_intraday,
            xb1_returns=xb1_returns,
            xb1_price=xb1_price,
            xb1_previous_close=xb1_previous_close,
            sessions=sessions,
            beta_clip=beta_clip,
        )
        if item:
            lag_metrics.append(item)
    best_lag = max(lag_metrics, key=lambda item: item["score"]) if lag_metrics else None

    pearson_stats = stats(primary_corr if primary_corr is not None else [])
    elasticity_stats = stats(primary_elasticity if primary_elasticity is not None else [])
    beta_stats = stats(primary_beta if primary_beta is not None else [])
    impact_stats = stats(impact_points)
    line_stats = stats(projected_line)
    err = error_stats(error)

    record = {
        "ativo": symbol,
        "samples": int(len(paired)),
        "primary_window": PRIMARY_WINDOW,
        "pearson_full": round(float(full_pearson), 8) if full_pearson is not None else None,
        "elasticidade_full": round(float(full_elasticity), 8) if full_elasticity is not None else None,
        "beta_full": round(float(full_beta), 8) if full_beta is not None else None,
        "pearson_mean": pearson_stats["mean"],
        "pearson_median": pearson_stats["median"],
        "pearson_std": pearson_stats["std"],
        "pearson_min": pearson_stats["min"],
        "pearson_max": pearson_stats["max"],
        "elasticidade_mean": elasticity_stats["mean"],
        "elasticidade_median": elasticity_stats["median"],
        "elasticidade_std": elasticity_stats["std"],
        "elasticidade_min": elasticity_stats["min"],
        "elasticidade_max": elasticity_stats["max"],
        "beta_mean": beta_stats["mean"],
        "beta_median": beta_stats["median"],
        "beta_std": beta_stats["std"],
        "beta_min": beta_stats["min"],
        "beta_max": beta_stats["max"],
        "impacto_pontos_mean": impact_stats["mean"],
        "impacto_pontos_median": impact_stats["median"],
        "impacto_pontos_std": impact_stats["std"],
        "impacto_pontos_min": impact_stats["min"],
        "impacto_pontos_max": impact_stats["max"],
        "linha_projetada_mean": line_stats["mean"],
        "linha_projetada_median": line_stats["median"],
        "linha_projetada_std": line_stats["std"],
        "linha_projetada_min": line_stats["min"],
        "linha_projetada_max": line_stats["max"],
        **err,
        "melhor_lag": best_lag["label"] if best_lag else None,
        "melhor_lag_seconds": best_lag["lag_seconds"] if best_lag else None,
        "melhor_lag_pearson": best_lag["pearson"] if best_lag else None,
        "melhor_lag_beta": best_lag["beta"] if best_lag else None,
        "melhor_lag_rmse": best_lag["rmse"] if best_lag else None,
        "ranking_score": None,
    }

    detail = {
        "ativo": symbol,
        "full": {
            "pearson": record["pearson_full"],
            "elasticidade": record["elasticidade_full"],
            "beta": record["beta_full"],
        },
        "rolling_windows": rolling,
        "lags": lag_metrics,
        "projection": {
            "impacto_pontos": impact_stats,
            "linha_projetada": line_stats,
            "erro": err,
        },
    }

    save_chart(
        symbol=symbol,
        xb1_price=xb1_price,
        projected_line=projected_line,
        error=error,
        beta=primary_beta,
        pearson=primary_corr,
        output_path=os.path.join(chart_dir, f"{clean_symbol_filename(symbol)}.png"),
    )
    detail["chart_path"] = os.path.join(chart_dir, f"{clean_symbol_filename(symbol)}.png")
    return record, detail


def save_chart(
    *,
    symbol: str,
    xb1_price: pd.Series,
    projected_line: pd.Series,
    error: pd.Series,
    beta: pd.Series,
    pearson: pd.Series,
    output_path: str,
) -> None:
    chart_frame = pd.concat(
        [
            xb1_price.rename("XB1"),
            projected_line.rename("Linha projetada"),
            error.rename("Erro"),
            beta.rename("Beta rolling"),
            pearson.rename("Pearson rolling"),
        ],
        axis=1,
    ).replace([np.inf, -np.inf], np.nan)
    chart_frame = chart_frame.resample("1min").last().dropna(how="all")
    if chart_frame.empty:
        return
    width, height = 1400, 900
    margin_left, margin_right = 92, 32
    panel_gap = 24
    panel_heights = [310, 145, 145, 145]
    top = 64
    image = Image.new("RGB", (width, height), "#f8fafc")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    title_font = ImageFont.load_default()

    draw.text((margin_left, 24), f"{symbol} -> XB1 transmission", fill="#111827", font=title_font)
    draw.text((width - 420, 24), "Primary rolling window: 15min | sampled to 1min", fill="#475569", font=font)

    def finite_min_max(series_list: list[pd.Series]) -> tuple[float, float]:
        values: list[float] = []
        for series in series_list:
            values.extend(float(value) for value in series.dropna().tolist() if math.isfinite(float(value)))
        if not values:
            return -1.0, 1.0
        low, high = min(values), max(values)
        if abs(high - low) < 1e-9:
            pad = max(abs(high) * 0.01, 1.0)
            return low - pad, high + pad
        pad = (high - low) * 0.08
        return low - pad, high + pad

    def x_coord(position: int, count: int, x0: int, x1: int) -> int:
        if count <= 1:
            return x0
        return int(x0 + ((x1 - x0) * position / (count - 1)))

    def y_coord(value: float, low: float, high: float, y0: int, y1: int) -> int:
        return int(y1 - ((value - low) / (high - low)) * (y1 - y0))

    def draw_panel(
        *,
        y0: int,
        panel_height: int,
        label: str,
        series_specs: list[tuple[str, pd.Series, str]],
        zero_line: bool = False,
    ) -> None:
        x0, x1 = margin_left, width - margin_right
        y1 = y0 + panel_height
        draw.rectangle((x0, y0, x1, y1), outline="#cbd5e1", width=1)
        draw.text((18, y0 + 8), label, fill="#334155", font=font)
        for tick in range(1, 4):
            yy = int(y0 + (panel_height * tick / 4))
            draw.line((x0, yy, x1, yy), fill="#e2e8f0", width=1)

        low, high = finite_min_max([spec[1] for spec in series_specs])
        if zero_line and low < 0 < high:
            yy = y_coord(0.0, low, high, y0, y1)
            draw.line((x0, yy, x1, yy), fill="#64748b", width=1)
        draw.text((x0 - 70, y0 + 4), f"{high:,.2f}", fill="#64748b", font=font)
        draw.text((x0 - 70, y1 - 14), f"{low:,.2f}", fill="#64748b", font=font)

        count = len(chart_frame.index)
        for name, series, color in series_specs:
            points: list[tuple[int, int]] = []
            for position, value in enumerate(series.tolist()):
                parsed = safe_float(value)
                if parsed is None:
                    if len(points) > 1:
                        draw.line(points, fill=color, width=2)
                    points = []
                    continue
                points.append((x_coord(position, count, x0, x1), y_coord(parsed, low, high, y0, y1)))
            if len(points) > 1:
                draw.line(points, fill=color, width=2)

        legend_x = x0 + 8
        for name, _, color in series_specs:
            draw.rectangle((legend_x, y0 + 8, legend_x + 12, y0 + 20), fill=color)
            draw.text((legend_x + 16, y0 + 8), name, fill="#111827", font=font)
            legend_x += 160

    current_y = top
    draw_panel(
        y0=current_y,
        panel_height=panel_heights[0],
        label="XB1 / linha",
        series_specs=[
            ("XB1 real", chart_frame["XB1"], "#111827"),
            ("Projetada", chart_frame["Linha projetada"], "#2563eb"),
        ],
    )
    current_y += panel_heights[0] + panel_gap
    draw_panel(
        y0=current_y,
        panel_height=panel_heights[1],
        label="Erro pts",
        series_specs=[("Erro", chart_frame["Erro"], "#dc2626")],
        zero_line=True,
    )
    current_y += panel_heights[1] + panel_gap
    draw_panel(
        y0=current_y,
        panel_height=panel_heights[2],
        label="Beta rolling",
        series_specs=[("Beta", chart_frame["Beta rolling"], "#7c3aed")],
        zero_line=True,
    )
    current_y += panel_heights[2] + panel_gap
    draw_panel(
        y0=current_y,
        panel_height=panel_heights[3],
        label="Pearson rolling",
        series_specs=[("Pearson", chart_frame["Pearson rolling"], "#059669")],
        zero_line=True,
    )

    first_label = chart_frame.index[0].strftime("%Y-%m-%d %H:%M")
    last_label = chart_frame.index[-1].strftime("%Y-%m-%d %H:%M")
    draw.text((margin_left, height - 24), first_label, fill="#475569", font=font)
    draw.text((width - margin_right - 138, height - 24), last_label, fill="#475569", font=font)
    image.save(output_path, "PNG")


def add_ranking(records: list[dict[str, Any]]) -> None:
    corr_values = [abs(safe_float(item.get("melhor_lag_pearson")) or safe_float(item.get("pearson_full")) or 0.0) for item in records]
    rmse_values = [safe_float(item.get("rmse")) or float("nan") for item in records]
    beta_std_values = [safe_float(item.get("beta_std")) or float("nan") for item in records]
    stability_values = []
    for item in records:
        beta = abs(safe_float(item.get("beta_median")) or safe_float(item.get("beta_full")) or 0.0)
        beta_std = safe_float(item.get("beta_std")) or 0.0
        stability_values.append(beta / (beta + beta_std + 1e-9))

    for index, item in enumerate(records):
        corr_rank = percentile_rank(corr_values, corr_values[index], higher_is_better=True)
        rmse_rank = percentile_rank(rmse_values, rmse_values[index], higher_is_better=False)
        stability_rank = percentile_rank(stability_values, stability_values[index], higher_is_better=True)
        beta_std_rank = percentile_rank(beta_std_values, beta_std_values[index], higher_is_better=False)
        best_lag_seconds = safe_float(item.get("melhor_lag_seconds")) or 0.0
        lead_score = 1.0 if best_lag_seconds > 0 else 0.45 if best_lag_seconds == 0 else 0.15
        ranking_score = 100.0 * (
            (0.32 * corr_rank)
            + (0.26 * rmse_rank)
            + (0.20 * stability_rank)
            + (0.12 * beta_std_rank)
            + (0.10 * lead_score)
        )
        item["ranking_score"] = round(ranking_score, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-asset beta transmission calibration vs XB1")
    parser.add_argument("--sessions", type=int, default=3)
    parser.add_argument("--session-start", default="09:00")
    parser.add_argument("--session-end", default="18:30")
    parser.add_argument("--freq", default="1s")
    parser.add_argument("--ffill-limit-seconds", type=int, default=30)
    parser.add_argument("--beta-clip", type=float, default=3.0)
    parser.add_argument("--output-dir", default=os.path.abspath(os.path.join(BACKEND_DIR, "..", "static", "cross_asset_transmission")))
    args = parser.parse_args()

    service = FairValueLegsChartService()
    symbols = sorted(collect_default_symbols())
    frame, valid_sessions = load_frame(
        service,
        sessions=args.sessions,
        session_start=args.session_start,
        session_end=args.session_end,
        symbols=symbols,
    )
    if frame.empty or BENCHMARK_SYMBOL not in set(frame["symbol"].unique()):
        raise RuntimeError("No aligned XB1 data found for cross-asset transmission analysis.")

    symbols = [symbol for symbol in symbols if symbol in set(frame["symbol"].unique())]
    os.makedirs(args.output_dir, exist_ok=True)
    chart_dir = os.path.join(args.output_dir, "charts")
    os.makedirs(chart_dir, exist_ok=True)

    data = build_aligned_data(
        frame,
        symbols,
        freq=args.freq,
        ffill_limit_seconds=args.ffill_limit_seconds,
    )

    records: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for symbol in symbols:
        if symbol == BENCHMARK_SYMBOL:
            continue
        record, detail = analyze_asset(
            symbol,
            data,
            beta_clip=args.beta_clip,
            chart_dir=chart_dir,
        )
        if record and detail:
            records.append(record)
            details.append(detail)

    add_ranking(records)
    records.sort(key=lambda item: item.get("ranking_score") or 0.0, reverse=True)
    detail_by_symbol = {item["ativo"]: item for item in details}
    details = [detail_by_symbol[item["ativo"]] for item in records if item["ativo"] in detail_by_symbol]

    generated_at = datetime.now(timezone.utc).isoformat()
    base_name = f"xb1_cross_asset_transmission_{valid_sessions[0]}_to_{valid_sessions[-1]}_{args.freq}"
    csv_path = os.path.join(args.output_dir, f"{base_name}.csv")
    json_path = os.path.join(args.output_dir, f"{base_name}.json")
    summary_path = os.path.join(args.output_dir, f"{base_name}_summary.md")

    pd.DataFrame(records).to_csv(csv_path, index=False, encoding="utf-8-sig")
    payload = {
        "generated_at": generated_at,
        "benchmark_symbol": BENCHMARK_SYMBOL,
        "sessions": valid_sessions,
        "frequency": args.freq,
        "ffill_limit_seconds": args.ffill_limit_seconds,
        "primary_window": PRIMARY_WINDOW,
        "rolling_windows_seconds": WINDOWS_SECONDS,
        "lags_seconds": LAGS_SECONDS,
        "beta_clip": args.beta_clip,
        "csv_path": csv_path,
        "chart_dir": chart_dir,
        "records": records,
        "details": details,
    }
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)

    top_lines = [
        "# XB1 Cross-Asset Transmission",
        "",
        f"- Generated at: {generated_at}",
        f"- Sessions: {', '.join(valid_sessions)}",
        f"- Frequency: {args.freq}; ffill limit: {args.ffill_limit_seconds}s; primary window: {PRIMARY_WINDOW}",
        f"- Assets analysed: {len(records)}",
        "",
        "## Top 20 Ranking",
        "",
    ]
    for item in records[:20]:
        top_lines.append(
            f"- {item['ativo']}: score={item['ranking_score']}, beta_median={item['beta_median']}, "
            f"pearson_full={item['pearson_full']}, rmse={item['rmse']}, lag={item['melhor_lag']}"
        )
    with open(summary_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(top_lines) + "\n")

    print(json.dumps({
        "csv_path": csv_path,
        "json_path": json_path,
        "summary_path": summary_path,
        "chart_dir": chart_dir,
        "sessions": valid_sessions,
        "assets": len(records),
        "top_10": records[:10],
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
