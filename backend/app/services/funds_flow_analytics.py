from __future__ import annotations

import copy
import json
import os
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ..utils.atomic_io import atomic_json_dump
from .funds_flow_contracts import (
    FUNDS_FLOW_LOCAL_SCHEMA_VERSION,
    SOURCE_INVENTORY,
    WINDOWS,
)
from .funds_flow_insights import FundsFlowInsightAgent
from .funds_flow_utils import (
    _clean_json,
    _max_iso_date_value,
    _max_iso_datetime_value,
    _now_iso,
    _path_mtime_iso,
    _regime_from_pressure,
    _safe_div,
    _safe_float,
    _zscore,
)


class FundsFlowAnalyticsMixin:
    def _build_dashboard(
        self,
        *,
        informe_df: pd.DataFrame,
        master_df: pd.DataFrame,
        as_of_date: date,
        requested_end_date: date,
        period: str,
        history_days: int,
        started_at: datetime,
        source_status: list[dict[str, Any]],
        anbima_funds: dict[str, Any] | None = None,
        ici_global_flows: dict[str, Any] | None = None,
        cftc_positioning: dict[str, Any] | None = None,
        b3_investor_participation: dict[str, Any] | None = None,
        b3_open_interest: dict[str, Any] | None = None,
        b3_investor_participation_monthly: dict[str, Any] | None = None,
        b3_market_data_report: dict[str, Any] | None = None,
        b3_etfs: dict[str, Any] | None = None,
        bcb_macro: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fund_df = self._build_fund_daily(informe_df, master_df)
        class_daily = self._build_class_daily(fund_df)
        industry_daily = self._build_industry_daily(fund_df)

        if industry_daily.empty:
            raise RuntimeError("Funds Flow Local analytics produced no industry rows.")

        industry_latest = industry_daily[industry_daily["dt"].dt.date <= as_of_date].tail(1)
        if industry_latest.empty:
            industry_latest = industry_daily.tail(1)
        latest = industry_latest.iloc[0]
        as_of_date = latest["dt"].date()

        kpis = self._build_kpis(industry_daily, latest=latest, as_of_date=as_of_date)
        class_latest = class_daily[class_daily["dt"].dt.date == as_of_date].copy()
        top_inflows = self._ranking_by_class(class_latest, ascending=False, top_n=5)
        top_outflows = self._ranking_by_class(class_latest, ascending=True, top_n=5)
        anbima_payload = copy.deepcopy(anbima_funds) if anbima_funds else {"status": "not_loaded"}
        anbima_payload["validation"] = self._build_anbima_validation(
            class_latest,
            anbima_payload,
            as_of_date=as_of_date,
        )

        payload: dict[str, Any] = {
            "ok": True,
            "generated_at": _now_iso(),
            "report": {
                "name": "Funds Flow Local",
                "as_of_date": as_of_date.isoformat(),
                "requested_date": requested_end_date.isoformat(),
                "period": period,
                "history_days": history_days,
                "schema_version": FUNDS_FLOW_LOCAL_SCHEMA_VERSION,
                "currency": "BRL",
                "sources": [
                    "CVM Informe Diario",
                    "CVM Cadastro FI",
                    "ANBIMA Estatisticas",
                    "BCB",
                    "ICI",
                    "FRED",
                    "B3",
                    "CFTC COT",
                ],
                "primary_source": "CVM Informe Diario FI",
                "last_updated_at": _now_iso(),
                "started_at": started_at.isoformat(),
                "completed_at": _now_iso(),
                "lineage": {
                    "raw_dir": self.raw_dir,
                    "derived_dir": self.derived_dir,
                    "informe_months": sorted(
                        {
                            str(item.get("month"))
                            for item in source_status
                            if str(item.get("id", "")).startswith("cvm_informe_diario_")
                        }
                    ),
                },
            },
            "kpis": kpis,
            "top_inflows": top_inflows,
            "top_outflows": top_outflows,
            "timeseries": {
                "flow_by_class": self._records_flow_by_class(class_daily, as_of_date=as_of_date),
                "industry_flow": self._records_industry_flow(industry_daily, as_of_date=as_of_date),
                "monthly_stacked_flow": self._records_monthly_flow(class_daily, as_of_date=as_of_date),
            },
            "heatmap": self._build_heatmap(class_daily, as_of_date=as_of_date),
            "rankings": {
                "by_fund": self._ranking_by_fund(fund_df, as_of_date=as_of_date),
                "by_class": self._ranking_by_class(class_latest, ascending=False, top_n=20),
                "by_manager": self._ranking_by_dimension(fund_df, as_of_date=as_of_date, dimension="gestor"),
                "by_strategy_tag": self._ranking_by_dimension(fund_df, as_of_date=as_of_date, dimension="strategy_tag"),
            },
            "anbima_funds": anbima_payload,
            "brazil_vs_global": self._build_brazil_vs_global_shell(
                class_daily,
                as_of_date=as_of_date,
                ici_global_flows=ici_global_flows,
                cftc_positioning=cftc_positioning,
            ),
            "b3_investor_participation": b3_investor_participation
            or {
                "status": "not_loaded",
                "participants": [],
            },
            "b3_open_interest": b3_open_interest
            or {
                "status": "not_loaded",
                "product_summary": [],
                "history": [],
            },
            "b3_investor_participation_monthly": b3_investor_participation_monthly
            or {
                "status": "not_loaded",
                "rows": [],
            },
            "b3_market_data_report": b3_market_data_report
            or {
                "status": "not_loaded",
                "summary": {},
            },
            "b3_etfs": b3_etfs
            or {
                "status": "not_loaded",
                "summary": {},
                "funds": [],
            },
            "bcb_macro": bcb_macro
            or {
                "status": "not_loaded",
                "series": [],
                "ptax_usd": [],
                "summary": {},
            },
            "etf_panel": self._build_etf_panel(
                fund_df,
                class_daily,
                as_of_date=as_of_date,
                b3_etfs=b3_etfs,
                anbima_funds=anbima_payload,
                ici_global_flows=ici_global_flows,
            ),
            "stress_panel": self._build_stress_panel(fund_df, as_of_date=as_of_date, latest_pressure=kpis.get("pressure_index")),
            "source_inventory": [item.as_dict() for item in SOURCE_INVENTORY],
            "source_status": self._merge_source_status(source_status),
        }
        payload["ai_insights"] = FundsFlowInsightAgent().generate(payload)
        return _clean_json(payload)

    def _build_fund_daily(self, informe_df: pd.DataFrame, master_df: pd.DataFrame) -> pd.DataFrame:
        df = informe_df.copy()
        if not master_df.empty:
            keep_cols = [
                column
                for column in [
                    "cnpj_fundo",
                    "nome_fundo",
                    "classe_cvm",
                    "macro_classe",
                    "subclasse",
                    "strategy_tag",
                    "administrador",
                    "gestor",
                    "situacao",
                    "data_registro",
                    "data_inicio",
                    "is_active",
                    "classification_confidence",
                ]
                if column in master_df.columns
            ]
            df = df.merge(master_df[keep_cols], on="cnpj_fundo", how="left")
        for column, fallback in {
            "nome_fundo": "",
            "classe_cvm": "",
            "macro_classe": "Unclassified",
            "subclasse": "unclassified",
            "strategy_tag": "unclassified",
            "administrador": "",
            "gestor": "",
            "situacao": "",
            "is_active": True,
            "classification_confidence": 0.25,
        }.items():
            if column not in df.columns:
                df[column] = fallback
            df[column] = df[column].where(df[column].notna(), fallback)
            if isinstance(fallback, bool):
                df[column] = df[column].astype(bool)

        df.loc[df["nome_fundo"].astype(str).str.strip() == "", "nome_fundo"] = (
            "Fundo " + df["cnpj_fundo"].astype(str)
        )
        if "id_subclasse" not in df.columns:
            df["id_subclasse"] = ""
        df["id_subclasse"] = df["id_subclasse"].fillna("").astype(str).str.strip()
        if "series_id" not in df.columns:
            df["series_id"] = np.where(
                df["id_subclasse"].ne(""),
                df["cnpj_fundo"].astype(str) + "::" + df["id_subclasse"].astype(str),
                df["cnpj_fundo"].astype(str),
            )
        df["captacao_liquida"] = df["captacao"].fillna(0.0) - df["resgate"].fillna(0.0)
        df = df.sort_values(["series_id", "dt"]).reset_index(drop=True)
        grouped = df.groupby("series_id", sort=False)
        df["pl_lag"] = grouped["pl"].shift(1)
        df["quota_lag"] = grouped["vl_quota"].shift(1)
        df["cotistas_lag"] = grouped["cotistas"].shift(1)
        df["flow_pct_pl"] = np.where(df["pl_lag"] > 0, df["captacao_liquida"] / df["pl_lag"], np.nan)
        df["delta_cotistas"] = df["cotistas"] - df["cotistas_lag"]
        df["quota_return"] = np.nan
        valid_quota = (df["vl_quota"] > 0) & (df["quota_lag"] > 0)
        df.loc[valid_quota, "quota_return"] = np.log(df.loc[valid_quota, "vl_quota"] / df.loc[valid_quota, "quota_lag"])
        for window in WINDOWS:
            df[f"rolling_flow_{window}d"] = grouped["captacao_liquida"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
            df[f"rolling_flow_pct_pl_{window}d"] = np.where(
                grouped["pl"].shift(window) > 0,
                df[f"rolling_flow_{window}d"] / grouped["pl"].shift(window),
                np.nan,
            )
        return df

    def _build_class_daily(self, fund_df: pd.DataFrame) -> pd.DataFrame:
        df = fund_df.copy()
        df["weighted_quota_return"] = df["quota_return"].fillna(0.0) * df["pl_lag"].fillna(0.0)
        class_daily = (
            df.groupby(["dt", "macro_classe"], as_index=False)
            .agg(
                pl_total=("pl", "sum"),
                captacao_total=("captacao", "sum"),
                resgate_total=("resgate", "sum"),
                captacao_liquida_total=("captacao_liquida", "sum"),
                cotistas_total=("cotistas", "sum"),
                delta_cotistas_total=("delta_cotistas", "sum"),
                num_fundos=("cnpj_fundo", "nunique"),
                pl_lag_sum=("pl_lag", "sum"),
                weighted_quota_return=("weighted_quota_return", "sum"),
            )
            .sort_values(["macro_classe", "dt"])
            .reset_index(drop=True)
        )
        class_daily["quota_return"] = np.where(
            class_daily["pl_lag_sum"] > 0,
            class_daily["weighted_quota_return"] / class_daily["pl_lag_sum"],
            np.nan,
        )
        class_daily["pl_lag"] = class_daily.groupby("macro_classe", sort=False)["pl_total"].shift(1)
        class_daily["flow_pct_pl"] = np.where(
            class_daily["pl_lag"] > 0,
            class_daily["captacao_liquida_total"] / class_daily["pl_lag"],
            np.nan,
        )
        for window in WINDOWS:
            group = class_daily.groupby("macro_classe", sort=False)
            class_daily[f"rolling_flow_{window}d"] = group["captacao_liquida_total"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
            base_pl = group["pl_total"].shift(window)
            class_daily[f"rolling_flow_pct_pl_{window}d"] = np.where(
                base_pl > 0,
                class_daily[f"rolling_flow_{window}d"] / base_pl,
                np.nan,
            )
            class_daily[f"quota_return_{window}d"] = group["quota_return"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
            class_daily[f"delta_cotistas_{window}d"] = group["delta_cotistas_total"].transform(
                lambda series: series.rolling(window, min_periods=1).sum()
            )
        class_daily["flow_zscore_21d"] = class_daily.groupby("macro_classe", sort=False)["flow_pct_pl"].transform(
            lambda series: _zscore(series.fillna(0.0), 21)
        )
        class_daily["flow_zscore_63d"] = class_daily.groupby("macro_classe", sort=False)["flow_pct_pl"].transform(
            lambda series: _zscore(series.fillna(0.0), 63)
        )
        class_daily["share_pl_industria"] = class_daily["pl_total"] / class_daily.groupby("dt")["pl_total"].transform("sum")
        daily_abs_flow = class_daily.groupby("dt")["captacao_liquida_total"].transform(lambda series: series.abs().sum())
        class_daily["share_flow_industria"] = np.where(
            daily_abs_flow > 0,
            class_daily["captacao_liquida_total"] / daily_abs_flow,
            0.0,
        )
        class_daily["delta_cotistas_zscore_21d"] = class_daily.groupby("macro_classe", sort=False)[
            "delta_cotistas_21d"
        ].transform(lambda series: _zscore(series.fillna(0.0), 21))
        class_daily["quota_return_zscore_21d"] = class_daily.groupby("macro_classe", sort=False)[
            "quota_return_21d"
        ].transform(lambda series: _zscore(series.fillna(0.0), 21))
        class_daily["flow_pct_pl_21d_zscore"] = class_daily.groupby("macro_classe", sort=False)[
            "rolling_flow_pct_pl_21d"
        ].transform(lambda series: _zscore(series.fillna(0.0), 21))
        class_daily["rolling_flow_pct_pl_63d_zscore"] = class_daily.groupby("macro_classe", sort=False)[
            "rolling_flow_pct_pl_63d"
        ].transform(lambda series: _zscore(series.fillna(0.0), 63))
        class_daily["pressure_index"] = (
            0.35 * class_daily["flow_pct_pl_21d_zscore"]
            + 0.25 * class_daily["rolling_flow_pct_pl_63d_zscore"]
            + 0.20 * class_daily["delta_cotistas_zscore_21d"]
            + 0.20 * class_daily["quota_return_zscore_21d"]
        ).fillna(0.0)
        return class_daily

    def _build_industry_daily(self, fund_df: pd.DataFrame) -> pd.DataFrame:
        df = fund_df.copy()
        df["weighted_quota_return"] = df["quota_return"].fillna(0.0) * df["pl_lag"].fillna(0.0)
        industry = (
            df.groupby("dt", as_index=False)
            .agg(
                pl_total=("pl", "sum"),
                captacao_total=("captacao", "sum"),
                resgate_total=("resgate", "sum"),
                captacao_liquida_total=("captacao_liquida", "sum"),
                cotistas_total=("cotistas", "sum"),
                delta_cotistas_total=("delta_cotistas", "sum"),
                num_fundos=("cnpj_fundo", "nunique"),
                pl_lag_sum=("pl_lag", "sum"),
                weighted_quota_return=("weighted_quota_return", "sum"),
            )
            .sort_values("dt")
            .reset_index(drop=True)
        )
        industry["quota_return"] = np.where(
            industry["pl_lag_sum"] > 0,
            industry["weighted_quota_return"] / industry["pl_lag_sum"],
            np.nan,
        )
        industry["pl_lag"] = industry["pl_total"].shift(1)
        industry["flow_pct_pl"] = np.where(
            industry["pl_lag"] > 0,
            industry["captacao_liquida_total"] / industry["pl_lag"],
            np.nan,
        )
        for window in WINDOWS:
            industry[f"rolling_flow_{window}d"] = industry["captacao_liquida_total"].rolling(
                window,
                min_periods=1,
            ).sum()
            base_pl = industry["pl_total"].shift(window)
            industry[f"rolling_flow_pct_pl_{window}d"] = np.where(
                base_pl > 0,
                industry[f"rolling_flow_{window}d"] / base_pl,
                np.nan,
            )
            industry[f"quota_return_{window}d"] = industry["quota_return"].rolling(window, min_periods=1).sum()
            industry[f"delta_cotistas_{window}d"] = industry["delta_cotistas_total"].rolling(window, min_periods=1).sum()
        industry["flow_zscore_21d"] = _zscore(industry["flow_pct_pl"].fillna(0.0), 21)
        industry["flow_zscore_63d"] = _zscore(industry["flow_pct_pl"].fillna(0.0), 63)
        industry["delta_cotistas_zscore_21d"] = _zscore(industry["delta_cotistas_21d"].fillna(0.0), 21)
        industry["quota_return_zscore_21d"] = _zscore(industry["quota_return_21d"].fillna(0.0), 21)
        industry["flow_pct_pl_21d_zscore"] = _zscore(industry["rolling_flow_pct_pl_21d"].fillna(0.0), 21)
        industry["rolling_flow_pct_pl_63d_zscore"] = _zscore(industry["rolling_flow_pct_pl_63d"].fillna(0.0), 63)
        industry["pressure_index"] = (
            0.35 * industry["flow_pct_pl_21d_zscore"]
            + 0.25 * industry["rolling_flow_pct_pl_63d_zscore"]
            + 0.20 * industry["delta_cotistas_zscore_21d"]
            + 0.20 * industry["quota_return_zscore_21d"]
        ).fillna(0.0)
        return industry

    def _build_etf_panel(
        self,
        fund_df: pd.DataFrame,
        class_daily: pd.DataFrame,
        *,
        as_of_date: date,
        b3_etfs: dict[str, Any] | None,
        anbima_funds: dict[str, Any] | None,
        ici_global_flows: dict[str, Any] | None,
    ) -> dict[str, Any]:
        etf_class = class_daily[
            class_daily["macro_classe"].astype(str).str.upper().eq("ETF")
        ].copy()
        latest_class = etf_class[etf_class["dt"].dt.date == as_of_date].tail(1)
        if latest_class.empty and not etf_class.empty:
            latest_class = etf_class.tail(1)

        local_summary: dict[str, Any] = {"status": "not_available"}
        if not latest_class.empty:
            row = latest_class.iloc[0]
            row_date = row.get("dt")
            local_summary = {
                "status": "ok",
                "date": row_date.date().isoformat() if hasattr(row_date, "date") else str(row_date or as_of_date),
                "aum": _safe_float(row.get("pl_total"), 2),
                "net_flow_1d": _safe_float(row.get("captacao_liquida_total"), 2),
                "net_flow_5d": _safe_float(row.get("rolling_flow_5d"), 2),
                "net_flow_21d": _safe_float(row.get("rolling_flow_21d"), 2),
                "net_flow_63d": _safe_float(row.get("rolling_flow_63d"), 2),
                "flow_pct_pl_21d": _safe_float(row.get("rolling_flow_pct_pl_21d"), 8),
                "zscore_21d": _safe_float(row.get("flow_zscore_21d"), 4),
                "pressure_index": _safe_float(row.get("pressure_index"), 4),
                "cotistas": _safe_float(row.get("cotistas_total"), 0),
                "delta_cotistas_21d": _safe_float(row.get("delta_cotistas_21d"), 0),
                "num_funds": int(row.get("num_fundos") or 0),
            }

        latest_funds = fund_df[
            (fund_df["dt"].dt.date == as_of_date)
            & fund_df["macro_classe"].astype(str).str.upper().eq("ETF")
        ].copy()
        if latest_funds.empty:
            top_funds: list[dict[str, Any]] = []
        else:
            latest_funds["abs_flow"] = latest_funds["rolling_flow_21d"].abs()
            top_funds = [
                {
                    "rank": rank,
                    "name": row.get("nome_fundo"),
                    "cnpj_fundo": row.get("cnpj_fundo"),
                    "net_flow_1d": _safe_float(row.get("captacao_liquida"), 2),
                    "net_flow_21d": _safe_float(row.get("rolling_flow_21d"), 2),
                    "flow_pct_pl_21d": _safe_float(row.get("rolling_flow_pct_pl_21d"), 6),
                    "aum": _safe_float(row.get("pl"), 2),
                    "cotistas": _safe_float(row.get("cotistas"), 0),
                    "gestor": row.get("gestor"),
                }
                for rank, (_, row) in enumerate(
                    latest_funds.sort_values("abs_flow", ascending=False).head(12).iterrows(),
                    start=1,
                )
            ]

        start = as_of_date - timedelta(days=180)
        timeseries = [
            {
                "date": row.dt.date().isoformat(),
                "net_flow": _safe_float(row.captacao_liquida_total, 2),
                "rolling_flow_21d": _safe_float(row.rolling_flow_21d, 2),
                "flow_pct_pl_21d": _safe_float(row.rolling_flow_pct_pl_21d, 8),
                "zscore_21d": _safe_float(row.flow_zscore_21d, 4),
                "aum": _safe_float(row.pl_total, 2),
            }
            for row in etf_class[etf_class["dt"].dt.date >= start].sort_values("dt").itertuples()
        ]

        anbima_daily = (anbima_funds or {}).get("consolidated_daily") or {}
        anbima_categories = [
            item
            for item in anbima_daily.get("categories") or []
            if str(item.get("macro_classe") or "").upper() == "ETF"
            or str(item.get("normalized_name") or "").upper() == "ETF"
        ]
        anbima_types = [
            item
            for item in anbima_daily.get("types") or []
            if str(item.get("macro_classe") or "").upper() == "ETF"
            or "ETF" in str(item.get("normalized_name") or "").upper()
        ]

        ici_weekly = ((ici_global_flows or {}).get("weekly") or {})
        ici_latest = (ici_weekly.get("latest_by_vehicle") or {}).get("etf") or {}
        ici_monthly = (ici_global_flows or {}).get("monthly_etf") or {}

        return {
            "status": "ok",
            "as_of_date": as_of_date.isoformat(),
            "local": {
                "summary": local_summary,
                "timeseries": timeseries,
                "top_funds": top_funds,
            },
            "b3": {
                "status": (b3_etfs or {}).get("status") or "not_loaded",
                "summary": (b3_etfs or {}).get("summary") or {},
                "categories": (b3_etfs or {}).get("categories") or [],
                "funds": (b3_etfs or {}).get("funds") or [],
            },
            "anbima": {
                "reference_date": anbima_daily.get("reference_date"),
                "categories": anbima_categories,
                "types": anbima_types[:24],
            },
            "ici": {
                "latest_weekly": ici_latest,
                "weekly_categories": (ici_latest.get("categories") or [])[:16],
                "monthly_assets_by_type": (ici_monthly.get("assets_by_type") or [])[:16],
                "monthly_issuance": (ici_monthly.get("issuance") or [])[:16],
            },
        }

    def _build_kpis(self, industry_daily: pd.DataFrame, *, latest: pd.Series, as_of_date: date) -> dict[str, Any]:
        year_rows = industry_daily[industry_daily["dt"].dt.year == as_of_date.year]
        idx = latest.name
        start_21_idx = max(0, int(idx) - 21)
        start_21_pl = industry_daily.iloc[start_21_idx]["pl_total"] if len(industry_daily) else None
        pressure = _safe_float(latest.get("pressure_index"), 4) or 0.0
        return {
            "industry_aum": _safe_float(latest.get("pl_total"), 2),
            "net_flow_1d": _safe_float(latest.get("captacao_liquida_total"), 2),
            "net_flow_5d": _safe_float(latest.get("rolling_flow_5d"), 2),
            "net_flow_21d": _safe_float(latest.get("rolling_flow_21d"), 2),
            "net_flow_63d": _safe_float(latest.get("rolling_flow_63d"), 2),
            "net_flow_ytd": _safe_float(year_rows["captacao_liquida_total"].sum() if not year_rows.empty else 0.0, 2),
            "flow_pct_pl_21d": _safe_div(latest.get("rolling_flow_21d"), start_21_pl),
            "total_shareholders": _safe_float(latest.get("cotistas_total"), 0),
            "delta_shareholders_21d": _safe_float(latest.get("delta_cotistas_21d"), 0),
            "num_funds": int(latest.get("num_fundos") or 0),
            "pressure_index": pressure,
            "regime": _regime_from_pressure(pressure),
        }

    def _ranking_by_class(self, class_latest: pd.DataFrame, *, ascending: bool, top_n: int) -> list[dict[str, Any]]:
        if class_latest.empty:
            return []
        ranked = class_latest.sort_values("rolling_flow_21d", ascending=ascending).head(top_n)
        records: list[dict[str, Any]] = []
        for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
            records.append(
                {
                    "rank": rank,
                    "name": row.get("macro_classe"),
                    "level": "macro_classe",
                    "net_flow_1d": _safe_float(row.get("captacao_liquida_total"), 2),
                    "net_flow_5d": _safe_float(row.get("rolling_flow_5d"), 2),
                    "net_flow_21d": _safe_float(row.get("rolling_flow_21d"), 2),
                    "flow_pct_pl_21d": _safe_float(row.get("rolling_flow_pct_pl_21d"), 6),
                    "zscore_21d": _safe_float(row.get("flow_zscore_21d"), 4),
                    "aum": _safe_float(row.get("pl_total"), 2),
                    "share_pl_industry": _safe_float(row.get("share_pl_industria"), 6),
                    "pressure_index": _safe_float(row.get("pressure_index"), 4),
                    "num_funds": int(row.get("num_fundos") or 0),
                }
            )
        return records

    def _ranking_by_fund(self, fund_df: pd.DataFrame, *, as_of_date: date) -> list[dict[str, Any]]:
        latest = fund_df[fund_df["dt"].dt.date == as_of_date].copy()
        if latest.empty:
            return []
        latest["abs_flow"] = latest["rolling_flow_21d"].abs()
        ranked = latest.sort_values("abs_flow", ascending=False).head(20)
        records: list[dict[str, Any]] = []
        for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
            records.append(
                {
                    "rank": rank,
                    "name": row.get("nome_fundo"),
                    "cnpj_fundo": row.get("cnpj_fundo"),
                    "series_id": row.get("series_id"),
                    "id_subclasse": row.get("id_subclasse"),
                    "level": "fundo",
                    "macro_classe": row.get("macro_classe"),
                    "net_flow_1d": _safe_float(row.get("captacao_liquida"), 2),
                    "net_flow_5d": _safe_float(row.get("rolling_flow_5d"), 2),
                    "net_flow_21d": _safe_float(row.get("rolling_flow_21d"), 2),
                    "flow_pct_pl_21d": _safe_float(row.get("rolling_flow_pct_pl_21d"), 6),
                    "aum": _safe_float(row.get("pl"), 2),
                    "cotistas": _safe_float(row.get("cotistas"), 0),
                    "delta_cotistas": _safe_float(row.get("delta_cotistas"), 0),
                    "classification_confidence": _safe_float(row.get("classification_confidence"), 3),
                }
            )
        return records

    def _ranking_by_dimension(self, fund_df: pd.DataFrame, *, as_of_date: date, dimension: str) -> list[dict[str, Any]]:
        latest = fund_df[fund_df["dt"].dt.date == as_of_date].copy()
        if latest.empty or dimension not in latest.columns:
            return []
        latest[dimension] = latest[dimension].fillna("").astype(str).str.strip()
        latest.loc[latest[dimension] == "", dimension] = "unclassified"
        grouped = (
            latest.groupby(dimension, as_index=False)
            .agg(
                net_flow_21d=("rolling_flow_21d", "sum"),
                net_flow_1d=("captacao_liquida", "sum"),
                aum=("pl", "sum"),
                cotistas=("cotistas", "sum"),
                num_funds=("cnpj_fundo", "nunique"),
            )
            .sort_values("net_flow_21d", ascending=False)
            .head(20)
        )
        return [
            {
                "rank": rank,
                "name": row.get(dimension),
                "level": dimension,
                "net_flow_1d": _safe_float(row.get("net_flow_1d"), 2),
                "net_flow_21d": _safe_float(row.get("net_flow_21d"), 2),
                "aum": _safe_float(row.get("aum"), 2),
                "cotistas": _safe_float(row.get("cotistas"), 0),
                "num_funds": int(row.get("num_funds") or 0),
            }
            for rank, (_, row) in enumerate(grouped.iterrows(), start=1)
        ]

    def _records_flow_by_class(self, class_daily: pd.DataFrame, *, as_of_date: date) -> list[dict[str, Any]]:
        start = as_of_date - timedelta(days=180)
        rows = class_daily[class_daily["dt"].dt.date >= start].sort_values(["dt", "macro_classe"])
        return [
            {
                "date": row.dt.date().isoformat(),
                "macro_classe": row.macro_classe,
                "net_flow": _safe_float(row.captacao_liquida_total, 2),
                "rolling_flow_5d": _safe_float(row.rolling_flow_5d, 2),
                "rolling_flow_21d": _safe_float(row.rolling_flow_21d, 2),
                "rolling_flow_63d": _safe_float(row.rolling_flow_63d, 2),
                "flow_pct_pl": _safe_float(row.flow_pct_pl, 8),
                "flow_pct_pl_21d": _safe_float(row.rolling_flow_pct_pl_21d, 8),
                "zscore": _safe_float(row.flow_zscore_21d, 4),
                "pressure_index": _safe_float(row.pressure_index, 4),
                "aum": _safe_float(row.pl_total, 2),
                "num_funds": int(row.num_fundos or 0),
            }
            for row in rows.itertuples(index=False)
        ]

    def _records_industry_flow(self, industry_daily: pd.DataFrame, *, as_of_date: date) -> list[dict[str, Any]]:
        start = as_of_date - timedelta(days=180)
        rows = industry_daily[industry_daily["dt"].dt.date >= start].sort_values("dt")
        return [
            {
                "date": row.dt.date().isoformat(),
                "net_flow": _safe_float(row.captacao_liquida_total, 2),
                "rolling_flow_5d": _safe_float(row.rolling_flow_5d, 2),
                "rolling_flow_21d": _safe_float(row.rolling_flow_21d, 2),
                "rolling_flow_63d": _safe_float(row.rolling_flow_63d, 2),
                "pressure_index": _safe_float(row.pressure_index, 4),
                "aum": _safe_float(row.pl_total, 2),
                "cotistas": _safe_float(row.cotistas_total, 0),
            }
            for row in rows.itertuples(index=False)
        ]

    def _records_monthly_flow(self, class_daily: pd.DataFrame, *, as_of_date: date) -> list[dict[str, Any]]:
        start = as_of_date - timedelta(days=395)
        rows = class_daily[class_daily["dt"].dt.date >= start].copy()
        if rows.empty:
            return []
        rows["month"] = rows["dt"].dt.to_period("M").astype(str)
        monthly = (
            rows.groupby(["month", "macro_classe"], as_index=False)
            .agg(
                net_flow_month=("captacao_liquida_total", "sum"),
                aum=("pl_total", "last"),
            )
            .sort_values(["month", "macro_classe"])
        )
        return [
            {
                "month": row.month,
                "macro_classe": row.macro_classe,
                "net_flow_month": _safe_float(row.net_flow_month, 2),
                "aum": _safe_float(row.aum, 2),
            }
            for row in monthly.itertuples(index=False)
        ]

    def _build_heatmap(self, class_daily: pd.DataFrame, *, as_of_date: date) -> dict[str, Any]:
        start = as_of_date - timedelta(days=90)
        rows = class_daily[class_daily["dt"].dt.date >= start].copy()
        if rows.empty:
            return {"x": [], "y": [], "z": [], "metric": "flow_zscore_21d", "cells": []}
        rows["week"] = rows["dt"].dt.to_period("W-FRI").apply(lambda period: period.end_time.date().isoformat())
        weekly = (
            rows.groupby(["week", "macro_classe"], as_index=False)
            .agg(
                zscore=("flow_zscore_21d", "last"),
                net_flow=("captacao_liquida_total", "sum"),
                flow_pct_pl=("rolling_flow_pct_pl_21d", "last"),
                num_funds=("num_fundos", "last"),
                aum=("pl_total", "last"),
            )
            .sort_values(["week", "macro_classe"])
        )
        x_values = sorted(weekly["week"].unique().tolist())
        y_values = sorted(weekly["macro_classe"].unique().tolist())
        z: list[list[float | None]] = []
        cells: list[dict[str, Any]] = []
        index = {
            (row.week, row.macro_classe): row
            for row in weekly.itertuples(index=False)
        }
        for macro in y_values:
            row_values: list[float | None] = []
            for week in x_values:
                item = index.get((week, macro))
                if item is None:
                    row_values.append(None)
                    continue
                z_value = _safe_float(item.zscore, 4)
                row_values.append(z_value)
                cells.append(
                    {
                        "date": week,
                        "macro_classe": macro,
                        "zscore": z_value,
                        "net_flow": _safe_float(item.net_flow, 2),
                        "flow_pct_pl": _safe_float(item.flow_pct_pl, 8),
                        "num_funds": int(item.num_funds or 0),
                        "aum": _safe_float(item.aum, 2),
                    }
                )
            z.append(row_values)
        return {"x": x_values, "y": y_values, "z": z, "metric": "flow_zscore_21d", "cells": cells}

    def _build_brazil_vs_global_shell(
        self,
        class_daily: pd.DataFrame,
        *,
        as_of_date: date,
        ici_global_flows: dict[str, Any] | None = None,
        cftc_positioning: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start = as_of_date - timedelta(days=140)
        rows = class_daily[class_daily["dt"].dt.date >= start].copy()
        if rows.empty:
            local = []
        else:
            rows["week"] = rows["dt"].dt.to_period("W-FRI").apply(lambda period: period.end_time.date().isoformat())
            weekly = (
                rows.groupby(["week", "macro_classe"], as_index=False)
                .agg(net_flow=("captacao_liquida_total", "sum"), flow_pct_pl=("rolling_flow_pct_pl_21d", "last"))
                .sort_values(["week", "macro_classe"])
            )
            local = [
                {
                    "date": row.week,
                    "category": row.macro_classe,
                    "net_flow": _safe_float(row.net_flow, 2),
                    "flow_pct_pl": _safe_float(row.flow_pct_pl, 8),
                    "frequency": "W",
                    "source": "CVM Informe Diario",
                }
                for row in weekly.itertuples(index=False)
            ]
        ici_payload = copy.deepcopy(ici_global_flows) if ici_global_flows else {"status": "not_loaded"}
        ici_weekly = ici_payload.get("weekly") or {}
        global_rows = [
            {
                "date": row.get("date"),
                "category": row.get("category"),
                "category_key": row.get("category_key"),
                "category_group": row.get("category_group"),
                "vehicle": row.get("vehicle"),
                "vehicle_label": row.get("vehicle_label"),
                "net_flow": row.get("flow_usd_mn"),
                "currency": "USD",
                "unit": "USD millions",
                "frequency": row.get("frequency"),
                "data_kind": row.get("data_kind"),
                "source": "ICI",
            }
            for row in (ici_weekly.get("weekly_series") or [])
        ]
        cftc_payload = copy.deepcopy(cftc_positioning) if cftc_positioning else {"status": "not_loaded"}
        return {
            "local": local,
            "global": global_rows,
            "macro": [],
            "ici_global_flows": ici_payload,
            "cftc_positioning": cftc_payload,
            "status": {
                "ici": "active" if ici_payload.get("status") == "ok" else ici_payload.get("status") or "configured_not_loaded",
                "cftc": "active" if cftc_payload.get("status") == "ok" else cftc_payload.get("status") or "configured_not_loaded",
                "fred": "configured_not_loaded",
                "bcb": "configured_not_loaded",
                "note": "Local CVM flow is live; ICI loads fund flows; CFTC loads weekly TFF positioning as of Tuesday with usual Friday release.",
            },
        }

    def _build_stress_panel(self, fund_df: pd.DataFrame, *, as_of_date: date, latest_pressure: Any) -> dict[str, Any]:
        latest = fund_df[fund_df["dt"].dt.date == as_of_date].copy()
        if latest.empty:
            return {
                "pct_funds_negative": 0,
                "pct_aum_negative": 0,
                "hhi_redemptions": 0,
                "largest_redemption_share": 0,
                "stress_level": "low",
            }
        negative = latest[latest["captacao_liquida"] < 0]
        total_funds = len(latest)
        total_aum = latest["pl"].sum()
        redemptions = negative["captacao_liquida"].abs()
        total_redemptions = redemptions.sum()
        hhi = float(((redemptions / total_redemptions) ** 2).sum()) if total_redemptions > 0 else 0.0
        largest = float(redemptions.max() / total_redemptions) if total_redemptions > 0 else 0.0
        pct_funds_negative = float(len(negative) / total_funds) if total_funds else 0.0
        pct_aum_negative = float(negative["pl"].sum() / total_aum) if total_aum > 0 else 0.0
        pressure = _safe_float(latest_pressure) or 0.0
        if pressure <= -2 or (pct_funds_negative > 0.65 and pct_aum_negative > 0.65):
            stress_level = "high"
        elif pressure <= -1 or pct_funds_negative > 0.55 or hhi > 0.25:
            stress_level = "medium"
        else:
            stress_level = "low"
        return {
            "pct_funds_negative": _safe_float(pct_funds_negative, 6),
            "pct_aum_negative": _safe_float(pct_aum_negative, 6),
            "hhi_redemptions": _safe_float(hhi, 6),
            "largest_redemption_share": _safe_float(largest, 6),
            "funds_with_negative_flow": int(len(negative)),
            "total_funds": int(total_funds),
            "stress_level": stress_level,
        }

    def _merge_source_status(self, runtime_status: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {item.id: item.as_dict() for item in SOURCE_INVENTORY}
        for status in runtime_status:
            source_id = str(status.get("id") or "")
            if source_id.startswith("cvm_informe_diario_"):
                key = "cvm_informe_diario"
            elif source_id == "cvm_cadastro_fi":
                key = "cvm_cadastro_fi"
            else:
                key = source_id
            current = by_id.get(key, {"id": key})
            status_capture = _max_iso_datetime_value(
                status.get("last_captured_at"),
                _path_mtime_iso(status.get("cached_path")),
                *[_path_mtime_iso(path) for path in (status.get("cached_paths") or [])],
            )
            current_capture = _max_iso_datetime_value(
                current.get("last_captured_at"),
                _path_mtime_iso(current.get("cached_path")),
                *[_path_mtime_iso(path) for path in (current.get("cached_paths") or [])],
            )
            current_ok = bool(current.get("ok"))
            status_ok = bool(status.get("ok"))
            combined_ok = current_ok or status_ok
            current.update(
                {
                    "ok": combined_ok,
                    "status": "active" if combined_ok else current.get("status", "configured"),
                    "rows": int(status.get("rows") or 0) + int(current.get("rows") or 0),
                    "latest_error": None if combined_ok else (status.get("error") or current.get("latest_error")),
                    "latency_ms": int(status.get("latency_ms") or 0) + int(current.get("latency_ms") or 0),
                    "cached_path": status.get("cached_path") if status_ok or not current.get("cached_path") else current.get("cached_path"),
                    "cached_paths": status.get("cached_paths") or current.get("cached_paths"),
                    "url": status.get("url") or current.get("url"),
                    "latest_data_date": _max_iso_date_value(
                        current.get("latest_data_date"),
                        status.get("latest_data_date"),
                    ),
                    "reference_label": status.get("reference_label") or current.get("reference_label"),
                    "report_date": status.get("report_date") or current.get("report_date"),
                    "publication_date": status.get("publication_date") or current.get("publication_date"),
                    "last_captured_at": _max_iso_datetime_value(current_capture, status_capture),
                }
            )
            by_id[key] = current
        return list(by_id.values())

    def _write_derived_files(self, payload: dict[str, Any]) -> None:
        os.makedirs(self.derived_dir, exist_ok=True)
        atomic_json_dump(os.path.join(self.derived_dir, "dashboard_payload.schema_sample.json"), payload, indent=2)
        for name in ["flow_by_class", "industry_flow", "monthly_stacked_flow"]:
            rows = payload.get("timeseries", {}).get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"{name}.csv"), index=False)
        for name in ["by_fund", "by_class", "by_manager", "by_strategy_tag"]:
            rows = payload.get("rankings", {}).get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"ranking_{name}.csv"), index=False)
        anbima_payload = payload.get("anbima_funds") or {}
        anbima_daily = anbima_payload.get("consolidated_daily") or {}
        for name in ["categories", "types", "top_type_inflows_mtd", "top_type_outflows_mtd"]:
            rows = anbima_daily.get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"anbima_{name}.csv"), index=False)
        validation_rows = (anbima_payload.get("validation") or {}).get("rows") or []
        if validation_rows:
            pd.DataFrame(validation_rows).to_csv(os.path.join(self.derived_dir, "anbima_cvm_validation.csv"), index=False)
        for name, ranking in (anbima_payload.get("rankings") or {}).items():
            rows = ranking.get("top_aum") or []
            if rows:
                normalized_rows = [
                    {key: value for key, value in row.items() if key != "values_by_class"}
                    for row in rows
                ]
                pd.DataFrame(normalized_rows).to_csv(
                    os.path.join(self.derived_dir, f"anbima_ranking_{name}.csv"),
                    index=False,
                )
        articles = ((anbima_payload.get("bulletin") or {}).get("latest_articles") or [])
        if articles:
            pd.DataFrame(articles).to_csv(os.path.join(self.derived_dir, "anbima_bulletin_articles.csv"), index=False)
        ici_payload = ((payload.get("brazil_vs_global") or {}).get("ici_global_flows") or {})
        ici_weekly = ici_payload.get("weekly") or {}
        for name in ["weekly_series", "monthly_series"]:
            rows = ici_weekly.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"ici_{name}.csv"), index=False)
        ici_monthly_etf = ici_payload.get("monthly_etf") or {}
        for name in ["assets_by_type", "issuance"]:
            rows = ici_monthly_etf.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"ici_monthly_etf_{name}.csv"), index=False)
        ici_worldwide = ici_payload.get("worldwide_quarterly") or {}
        for name in ["regions", "countries", "top_country_etf_net_sales", "bottom_country_etf_net_sales"]:
            rows = ici_worldwide.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"ici_worldwide_{name}.csv"), index=False)
        cftc_payload = ((payload.get("brazil_vs_global") or {}).get("cftc_positioning") or {})
        for name in ["latest_contracts", "focus_contracts", "weekly_series", "participant_summary", "asset_bucket_summary"]:
            rows = cftc_payload.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"cftc_tff_{name}.csv"), index=False)
        for name in [
            "datasets",
            "family_summaries",
            "extended_participant_summary",
            "extended_asset_bucket_summary",
            "extended_contracts",
            "position_matrix",
        ]:
            rows = cftc_payload.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"cftc_cot_{name}.csv"), index=False)
        b3_payload = payload.get("b3_investor_participation") or {}
        for name in ["history", "trend_by_participant", "daily_reports", "economic_indicators"]:
            rows = b3_payload.get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"b3_{name}.csv"), index=False)
        b3_monthly = payload.get("b3_investor_participation_monthly") or {}
        if b3_monthly.get("rows"):
            pd.DataFrame(b3_monthly["rows"]).to_csv(
                os.path.join(self.derived_dir, "b3_investor_participation_monthly.csv"),
                index=False,
            )
        b3_market_data = payload.get("b3_market_data_report") or {}
        for name in [
            "trading_volume_monthly",
            "average_daily_trading_value",
            "total_trades",
            "daily_average_trades",
            "investor_participation_monthly",
            "foreign_investor_flow_monthly",
        ]:
            rows = b3_market_data.get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"b3_market_data_{name}.csv"), index=False)
        b3_open_interest = payload.get("b3_open_interest") or {}
        for name in ["history", "product_summary", "latest_contracts", "futures_summary"]:
            rows = b3_open_interest.get(name, [])
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"b3_open_interest_{name}.csv"), index=False)
        b3_etfs = payload.get("b3_etfs") or {}
        for name in ["funds", "categories"]:
            rows = b3_etfs.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"b3_etfs_{name}.csv"), index=False)
        bcb_macro = payload.get("bcb_macro") or {}
        for name in ["series", "ptax_usd"]:
            rows = bcb_macro.get(name) or []
            if rows:
                pd.DataFrame(rows).to_csv(os.path.join(self.derived_dir, f"bcb_macro_{name}.csv"), index=False)
        etf_panel = payload.get("etf_panel") or {}
        etf_local = etf_panel.get("local") or {}
        if etf_local.get("timeseries"):
            pd.DataFrame(etf_local["timeseries"]).to_csv(os.path.join(self.derived_dir, "etf_local_timeseries.csv"), index=False)
        if etf_local.get("top_funds"):
            pd.DataFrame(etf_local["top_funds"]).to_csv(os.path.join(self.derived_dir, "etf_local_top_funds.csv"), index=False)

    def _append_snapshot_summary(self, payload: dict[str, Any]) -> None:
        report = payload.get("report") or {}
        kpis = payload.get("kpis") or {}
        summary = {
            "generated_at": payload.get("generated_at"),
            "as_of_date": report.get("as_of_date"),
            "period": report.get("period"),
            "industry_aum": kpis.get("industry_aum"),
            "net_flow_21d": kpis.get("net_flow_21d"),
            "pressure_index": kpis.get("pressure_index"),
            "regime": kpis.get("regime"),
        }
        os.makedirs(os.path.dirname(self.snapshots_path), exist_ok=True)
        with open(self.snapshots_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(_clean_json(summary), ensure_ascii=False) + "\n")
