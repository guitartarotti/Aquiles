from __future__ import annotations

import math
import re
import sqlite3
from typing import Any


class CvmCdaGraphPortfoliosMixin:
    def _fetch_portfolio_similarity(  # noqa: C901
        self, con: sqlite3.Connection, month: str, *, limit: int
    ) -> dict[str, Any]:
        labels = self._asset_lens_labels()
        tagged_cte = self._asset_lens_tagged_cte()
        item_limit = max(12, min(int(limit or 40), 80))
        base_candidate_limit = max(110, min(item_limit * 2, 180))
        focus_candidate_limit = max(28, min(item_limit, 72))
        niche_candidate_limit = max(18, min(item_limit // 2, 42))
        rows = [dict(row) for row in con.execute(
            f"""
            {tagged_cte},
            fund_stats AS (
                SELECT
                    fund_cnpj,
                    MAX(COALESCE(NULLIF(fund_name, ''), fund_cnpj)) AS fund_name,
                    MAX(COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_type,
                    COUNT(*) AS holding_count,
                    SUM(ABS(COALESCE(value_market, 0))) AS gross_total,
                    SUM(COALESCE(value_market, 0)) AS net_total,
                    SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS activity_total,
                    SUM(CASE WHEN asset_bucket LIKE 'options_%' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS option_gross,
                    SUM(CASE WHEN asset_bucket = 'equity' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS equity_gross,
                    SUM(CASE WHEN asset_bucket IN ('public_bonds', 'private_credit', 'fund_fixed_income', 'cash_if') THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS fixed_income_gross,
                    SUM(CASE WHEN asset_bucket = 'derivatives' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS derivatives_gross,
                    SUM(CASE WHEN asset_bucket = 'private_credit' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS private_credit_gross,
                    SUM(CASE WHEN asset_bucket = 'public_bonds' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS public_bonds_gross,
                    SUM(CASE WHEN asset_bucket IN ('fund_quotas', 'fund_fixed_income', 'fund_multimarket', 'fund_equity', 'fund_real_estate', 'fund_structured') THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS fund_quota_gross,
                    SUM(CASE WHEN asset_bucket = 'foreign' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS foreign_gross,
                    COUNT(DISTINCT asset_bucket) AS bucket_count,
                    (
                        SUM(ABS(COALESCE(value_market, 0)))
                        + SUM(CASE WHEN asset_bucket LIKE 'options_%' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) * 7.0
                        + SUM(CASE WHEN asset_bucket = 'equity' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) * 2.5
                        + SUM(CASE WHEN asset_bucket IN ('public_bonds', 'private_credit', 'fund_fixed_income', 'cash_if') THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) * 1.1
                        + SUM(CASE WHEN asset_bucket = 'derivatives' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) * 5.0
                        + SUM(CASE WHEN asset_bucket = 'foreign' THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) * 2.2
                        + ABS(SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0))) * 2.5
                    ) AS composite_score
                FROM tagged
                WHERE COALESCE(NULLIF(fund_cnpj, ''), '') <> ''
                GROUP BY fund_cnpj
                HAVING gross_total > 0
            ),
            candidate_funds AS (
                SELECT * FROM (
                    SELECT * FROM fund_stats ORDER BY composite_score DESC, gross_total DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE option_gross > 0 ORDER BY option_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE derivatives_gross > 0 ORDER BY derivatives_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE equity_gross > 0 ORDER BY equity_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE private_credit_gross > 0 ORDER BY private_credit_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE public_bonds_gross > 0 ORDER BY public_bonds_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE fund_quota_gross > 0 ORDER BY fund_quota_gross DESC LIMIT ?
                )
                UNION
                SELECT * FROM (
                    SELECT * FROM fund_stats WHERE foreign_gross > 0 ORDER BY foreign_gross DESC LIMIT ?
                )
                ORDER BY composite_score DESC, gross_total DESC
                LIMIT ?
            )
            SELECT
                t.*,
                cf.fund_name AS candidate_fund_name,
                cf.fund_type AS candidate_fund_type,
                cf.gross_total,
                cf.net_total,
                cf.activity_total,
                cf.option_gross,
                cf.equity_gross,
                cf.fixed_income_gross,
                cf.derivatives_gross,
                cf.private_credit_gross,
                cf.public_bonds_gross,
                cf.fund_quota_gross,
                cf.foreign_gross,
                cf.bucket_count
            FROM tagged t
            JOIN candidate_funds cf ON cf.fund_cnpj = t.fund_cnpj
            WHERE ABS(COALESCE(t.value_market, 0)) > 0
               OR ABS(COALESCE(t.value_buy, 0)) + ABS(COALESCE(t.value_sell, 0)) > 0
            ORDER BY cf.composite_score DESC, cf.gross_total DESC, ABS(COALESCE(t.value_market, 0)) DESC
            """,
            (
                month,
                base_candidate_limit,
                focus_candidate_limit,
                focus_candidate_limit,
                focus_candidate_limit,
                niche_candidate_limit,
                niche_candidate_limit,
                focus_candidate_limit,
                niche_candidate_limit,
                base_candidate_limit + focus_candidate_limit * 4,
            ),
        ).fetchall()]

        funds: dict[str, dict[str, Any]] = {}
        feature_info: dict[str, dict[str, Any]] = {}

        def clean_key(value: Any) -> str:
            return re.sub(r"\s+", " ", str(value or "").strip())[:120]

        def add_feature(
            fund: dict[str, Any],
            kind: str,
            key: Any,
            label: str,
            weight: float,
            *,
            bucket: str = "",
        ) -> None:
            if weight <= 0:
                return
            clean = clean_key(key)
            if not clean:
                return
            feature_id = f"{kind}:{clean.upper()}"
            fund["features"][feature_id] = fund["features"].get(feature_id, 0.0) + float(weight)
            if feature_id not in feature_info:
                feature_info[feature_id] = {
                    "feature_id": feature_id,
                    "feature_type": kind,
                    "feature_key": clean,
                    "label": label or clean,
                    "bucket": bucket,
                }

        def get_fund(row: dict[str, Any]) -> dict[str, Any]:
            cnpj = str(row.get("fund_cnpj") or "").strip()
            if cnpj not in funds:
                funds[cnpj] = {
                    "fund_cnpj": cnpj,
                    "fund_name": row.get("candidate_fund_name") or row.get("fund_name") or cnpj,
                    "fund_type": row.get("candidate_fund_type") or row.get("fund_type") or "Outros",
                    "gross_total": self._num(row.get("gross_total")),
                    "net_total": self._num(row.get("net_total")),
                    "activity_total": self._num(row.get("activity_total")),
                    "holding_count": 0,
                    "features": {},
                    "bucket_gross": {},
                    "asset_gross": {},
                    "issuer_gross": {},
                    "option_underlyings": {},
                    "equity_underlyings": {},
                    "structures": [],
                }
            return funds[cnpj]

        for row in rows:
            fund = get_fund(row)
            bucket = str(row.get("asset_bucket") or "other")
            bucket_label = labels.get(bucket, bucket)
            value_market = self._num(row.get("value_market"))
            activity = abs(self._num(row.get("value_buy"))) + abs(self._num(row.get("value_sell")))
            gross = abs(value_market) if abs(value_market) > 0 else activity * 0.45
            if gross <= 0:
                continue
            fund["holding_count"] += 1
            fund["bucket_gross"][bucket] = fund["bucket_gross"].get(bucket, 0.0) + gross
            asset_key = clean_key(row.get("asset_key") or row.get("asset_code") or row.get("asset_desc") or row.get("issuer_name"))
            issuer = clean_key(row.get("issuer_name"))
            issuer_doc = clean_key(row.get("issuer_doc") or row.get("risk_issuer"))
            asset_class = clean_key(row.get("asset_class"))
            maturity_bucket = clean_key(row.get("maturity_bucket"))
            country = clean_key(row.get("country") or row.get("country_code"))
            market = clean_key(row.get("market") or row.get("tp_negoc"))
            explanatory_bucket = bucket not in {"confidential", "other"}
            net_activity = self._num(row.get("value_buy")) - self._num(row.get("value_sell"))

            if explanatory_bucket:
                add_feature(fund, "bucket", bucket, bucket_label, gross * 0.55, bucket=bucket)
            if explanatory_bucket and asset_class and not self._is_generic_asset_text(asset_class) and asset_class.lower() not in {"confidencial", "outros"}:
                add_feature(fund, "asset_class", asset_class, asset_class, gross * 0.32, bucket=bucket)
            if explanatory_bucket and issuer and not self._is_generic_asset_text(issuer):
                fund["issuer_gross"][issuer] = fund["issuer_gross"].get(issuer, 0.0) + gross
                add_feature(fund, "issuer", issuer, issuer, gross * 0.9, bucket=bucket)
            if explanatory_bucket and issuer_doc and not self._is_generic_asset_text(issuer_doc):
                add_feature(fund, "issuer_doc", issuer_doc, issuer or issuer_doc, gross * 0.72, bucket=bucket)
            if explanatory_bucket and asset_key and not self._is_generic_asset_text(asset_key):
                fund["asset_gross"][asset_key] = fund["asset_gross"].get(asset_key, 0.0) + gross
                asset_weight = 1.35 if bucket in {"equity", "private_credit", "public_bonds", "fund_quotas"} else 1.15
                if bucket.startswith("options_"):
                    asset_weight = 1.85
                add_feature(fund, "asset", f"{bucket}|{asset_key}", asset_key, gross * asset_weight, bucket=bucket)
            if explanatory_bucket and country and country.lower() not in {"nao informado", "não informado", "brasil", "bra", "br"}:
                add_feature(fund, "country", country, country, gross * 0.46, bucket=bucket)
            if explanatory_bucket and market and market.lower() not in {"nao informado", "não informado", "sem mercado"}:
                add_feature(fund, "market", f"{bucket}|{market}", f"{bucket_label} / {market}", gross * 0.34, bucket=bucket)
            if explanatory_bucket and abs(net_activity) > 0:
                direction = "compra" if net_activity > 0 else "venda"
                add_feature(fund, "activity_direction", f"{bucket}|{direction}", f"{bucket_label} com {direction}", abs(net_activity) * 0.95, bucket=bucket)
            if maturity_bucket and bucket in {"public_bonds", "private_credit", "cash_if"} and maturity_bucket.lower() not in {"sem vencimento", "nao informado", "não informado"}:
                add_feature(
                    fund,
                    "fixed_income_maturity",
                    f"{bucket}|{maturity_bucket}",
                    f"{bucket_label} / {maturity_bucket}",
                    gross * 0.82,
                    bucket=bucket,
                )
            maturity_date = clean_key(row.get("maturity_date"))
            maturity_year = str(maturity_date)[:4] if re.match(r"^\d{4}", str(maturity_date or "")) else ""
            if maturity_year and bucket in {"public_bonds", "private_credit", "cash_if"}:
                add_feature(
                    fund,
                    "fixed_income_year",
                    f"{bucket}|{maturity_year}",
                    f"{bucket_label} venc. {maturity_year}",
                    gross * 0.72,
                    bucket=bucket,
                )

            if bucket.startswith("options_"):
                underlying = self._infer_option_underlying(row)
                if underlying:
                    side = self._option_side_from_row(row)
                    role = self._option_position_role_from_row(row)
                    option_map = fund["option_underlyings"].setdefault(underlying, {})
                    option_map[f"{side}_{role}"] = option_map.get(f"{side}_{role}", 0.0) + gross
                    option_map["gross"] = option_map.get("gross", 0.0) + gross
                    add_feature(fund, "option_underlying", underlying, f"Opcao sobre {underlying}", gross * 2.1, bucket=bucket)
                    add_feature(fund, "option_leg", f"{underlying}|{side}|{role}", f"{underlying} {side}/{role}", gross * 2.5, bucket=bucket)
            elif bucket == "equity":
                underlying = self._infer_equity_underlying(row)
                if underlying:
                    fund["equity_underlyings"][underlying] = fund["equity_underlyings"].get(underlying, 0.0) + gross
                    add_feature(fund, "equity_underlying", underlying, f"Acao/ETF {underlying}", gross * 1.8, bucket=bucket)

        structure_stats: dict[str, dict[str, Any]] = {}

        def add_structure(
            fund: dict[str, Any],
            key: str,
            label: str,
            value: float,
            *,
            score: float,
            underlyings: list[str] | None = None,
            detail: str = "",
        ) -> None:
            if value <= 0:
                return
            structure = {
                "structure_key": key,
                "label": label,
                "value": value,
                "score": score,
                "underlyings": underlyings or [],
                "detail": detail,
            }
            fund["structures"].append(structure)
            add_feature(fund, "structure", key, label, max(value, fund.get("gross_total") or 0) * max(score, 0.08) * 1.7)
            stats = structure_stats.setdefault(key, {
                "structure_key": key,
                "label": label,
                "fund_count": 0,
                "gross_value": 0.0,
                "score_sum": 0.0,
                "sample_funds": [],
                "sample_underlyings": [],
            })
            stats["fund_count"] += 1
            stats["gross_value"] += float(value or 0)
            stats["score_sum"] += float(score or 0)
            if len(stats["sample_funds"]) < 5:
                stats["sample_funds"].append(fund.get("fund_name"))
            for underlying in underlyings or []:
                if underlying and underlying not in stats["sample_underlyings"] and len(stats["sample_underlyings"]) < 8:
                    stats["sample_underlyings"].append(underlying)

        for fund in funds.values():
            gross_total = max(self._num(fund.get("gross_total")), 1.0)
            bucket_gross = fund.get("bucket_gross") or {}
            fixed_income = sum(bucket_gross.get(key, 0.0) for key in ("public_bonds", "private_credit", "fund_fixed_income", "cash_if"))
            fund_quota = sum(bucket_gross.get(key, 0.0) for key in ("fund_quotas", "fund_fixed_income", "fund_multimarket", "fund_equity", "fund_real_estate", "fund_structured"))
            option_total = sum(value.get("gross", 0.0) for value in (fund.get("option_underlyings") or {}).values())
            equity_total = sum((fund.get("equity_underlyings") or {}).values())
            derivative_total = bucket_gross.get("derivatives", 0.0)
            private_credit = bucket_gross.get("private_credit", 0.0)
            public_bonds = bucket_gross.get("public_bonds", 0.0)
            cash_if = bucket_gross.get("cash_if", 0.0)
            foreign_total = bucket_gross.get("foreign", 0.0)
            option_holder_total = 0.0
            option_writer_total = 0.0

            covered: list[str] = []
            protected: list[str] = []
            collar: list[str] = []
            synthetic: list[str] = []
            for underlying, option_map in (fund.get("option_underlyings") or {}).items():
                equity_value = (fund.get("equity_underlyings") or {}).get(underlying, 0.0)
                call_written = option_map.get("call_written", 0.0)
                put_holder = option_map.get("put_holder", 0.0)
                call_holder = option_map.get("call_holder", 0.0)
                put_written = option_map.get("put_written", 0.0)
                option_holder_total += call_holder + put_holder
                option_writer_total += call_written + put_written
                if equity_value > 0 and call_written > 0:
                    covered.append(underlying)
                if equity_value > 0 and put_holder > 0:
                    protected.append(underlying)
                if equity_value > 0 and call_written > 0 and put_holder > 0:
                    collar.append(underlying)
                if call_holder > 0 and put_written > 0:
                    synthetic.append(underlying)

            if collar:
                value = sum((fund["option_underlyings"][u].get("call_written", 0.0) + fund["option_underlyings"][u].get("put_holder", 0.0) + fund["equity_underlyings"].get(u, 0.0)) for u in collar)
                add_structure(fund, "equity_collar", "Collar acao + call lancada + put comprada", value, score=min(value / gross_total, 1.0), underlyings=collar[:6])
            if covered:
                value = sum((fund["option_underlyings"][u].get("call_written", 0.0) + fund["equity_underlyings"].get(u, 0.0)) for u in covered)
                add_structure(fund, "covered_call", "Acao com call lancada", value, score=min(value / gross_total, 1.0), underlyings=covered[:6])
            if protected:
                value = sum((fund["option_underlyings"][u].get("put_holder", 0.0) + fund["equity_underlyings"].get(u, 0.0)) for u in protected)
                add_structure(fund, "protective_put", "Acao com put comprada", value, score=min(value / gross_total, 1.0), underlyings=protected[:6])
            if synthetic:
                value = sum((fund["option_underlyings"][u].get("call_holder", 0.0) + fund["option_underlyings"][u].get("put_written", 0.0)) for u in synthetic)
                add_structure(fund, "synthetic_long_options", "Call comprada + put lancada", value, score=min(value / gross_total, 1.0), underlyings=synthetic[:6])
            if option_total / gross_total >= 0.015 and len(fund.get("option_underlyings") or {}) >= 3:
                add_structure(
                    fund,
                    "options_overlay_basket",
                    "Overlay diversificado de opcoes",
                    option_total,
                    score=min(option_total / gross_total, 1.0),
                    underlyings=list((fund.get("option_underlyings") or {}).keys())[:8],
                    detail="Carteira com opcoes em varios subjacentes.",
                )
            if option_writer_total > option_holder_total * 1.25 and option_writer_total / gross_total >= 0.002:
                add_structure(
                    fund,
                    "short_vol_options_overlay",
                    "Overlay vendedor de volatilidade",
                    option_writer_total,
                    score=min(option_writer_total / gross_total, 1.0),
                    underlyings=list((fund.get("option_underlyings") or {}).keys())[:8],
                )
            if option_holder_total > option_writer_total * 1.25 and option_holder_total / gross_total >= 0.002:
                add_structure(
                    fund,
                    "long_optionality_overlay",
                    "Overlay comprador de opcionalidade",
                    option_holder_total,
                    score=min(option_holder_total / gross_total, 1.0),
                    underlyings=list((fund.get("option_underlyings") or {}).keys())[:8],
                )
            if fixed_income / gross_total >= 0.55 and derivative_total / gross_total >= 0.003:
                add_structure(fund, "rates_hedged_fixed_income", "Renda fixa com overlay de derivativos", fixed_income + derivative_total, score=min((fixed_income + derivative_total) / gross_total, 1.0))
            if fixed_income / gross_total >= 0.65 and private_credit / gross_total >= 0.08:
                add_structure(fund, "credit_carry_core", "Nucleo renda fixa + credito privado", fixed_income, score=min(fixed_income / gross_total, 1.0))
            if public_bonds / gross_total >= 0.35 and private_credit / gross_total >= 0.08:
                add_structure(fund, "public_private_credit_barbell", "Barbell titulo publico + credito privado", public_bonds + private_credit, score=min((public_bonds + private_credit) / gross_total, 1.0))
            if (public_bonds + cash_if) / gross_total >= 0.7:
                add_structure(fund, "cash_duration_core", "Caixa/duration em titulos publicos", public_bonds + cash_if, score=min((public_bonds + cash_if) / gross_total, 1.0))
            if private_credit / gross_total >= 0.12 and cash_if / gross_total >= 0.1:
                add_structure(fund, "credit_liquidity_sleeve", "Credito privado com colchao de liquidez", private_credit + cash_if, score=min((private_credit + cash_if) / gross_total, 1.0))
            if fund_quota / gross_total >= 0.45:
                add_structure(fund, "fund_allocator", "Alocador em cotas de fundos", fund_quota, score=min(fund_quota / gross_total, 1.0))
            if equity_total / gross_total >= 0.15 and option_total / gross_total >= 0.005:
                add_structure(fund, "equity_options_overlay", "Acoes com overlay de opcoes", equity_total + option_total, score=min((equity_total + option_total) / gross_total, 1.0), underlyings=list((fund.get("equity_underlyings") or {}).keys())[:8])
            if equity_total / gross_total >= 0.12 and derivative_total / gross_total >= 0.006:
                add_structure(fund, "equity_derivatives_overlay", "Acoes com overlay de derivativos", equity_total + derivative_total, score=min((equity_total + derivative_total) / gross_total, 1.0), underlyings=list((fund.get("equity_underlyings") or {}).keys())[:8])
            if foreign_total / gross_total >= 0.08 and option_total / gross_total >= 0.003:
                add_structure(fund, "foreign_options_overlay", "Exterior/BDR com overlay de opcoes", foreign_total + option_total, score=min((foreign_total + option_total) / gross_total, 1.0), underlyings=list((fund.get("option_underlyings") or {}).keys())[:8])
            if fund_quota / gross_total >= 0.25 and derivative_total / gross_total >= 0.004:
                add_structure(fund, "fund_allocator_with_derivatives", "Cotas de fundos com overlay de derivativos", fund_quota + derivative_total, score=min((fund_quota + derivative_total) / gross_total, 1.0))

        feature_to_funds: dict[str, dict[str, float]] = {}
        norms: dict[str, float] = {}
        for cnpj, fund in funds.items():
            gross_total = max(self._num(fund.get("gross_total")), 1.0)
            norm_sq = 0.0
            for feature_id, raw_weight in (fund.get("features") or {}).items():
                info = feature_info.get(feature_id, {})
                kind = info.get("feature_type")
                normalized = max(float(raw_weight or 0) / gross_total, 0.0)
                if kind in {"asset", "option_leg", "option_underlying", "equity_underlying", "structure"}:
                    weight = math.sqrt(min(normalized, 4.0))
                elif kind in {"issuer", "issuer_doc", "fixed_income_maturity", "fixed_income_year"}:
                    weight = math.sqrt(min(normalized, 2.2)) * 0.85
                elif kind in {"activity_direction", "country", "market"}:
                    weight = math.sqrt(min(normalized, 1.8)) * 0.7
                else:
                    weight = math.sqrt(min(normalized, 1.3)) * 0.55
                if weight <= 0.00001:
                    continue
                feature_to_funds.setdefault(feature_id, {})[cnpj] = weight
                norm_sq += weight * weight
            norms[cnpj] = math.sqrt(norm_sq) if norm_sq > 0 else 1.0

        pair_stats: dict[tuple[str, str], dict[str, Any]] = {}
        max_feature_funds = max(42, min((base_candidate_limit + focus_candidate_limit * 4) // 4, 78))
        for feature_id, holdings in feature_to_funds.items():
            if len(holdings) < 2:
                continue
            info = feature_info.get(feature_id, {})
            items = sorted(holdings.items(), key=lambda item: item[1], reverse=True)
            if len(items) > max_feature_funds:
                if info.get("feature_type") not in {"structure", "option_leg", "option_underlying", "equity_underlying", "fixed_income_maturity", "fixed_income_year", "activity_direction", "issuer_doc", "country"}:
                    continue
                items = items[:max_feature_funds]
            for left_index in range(len(items)):
                left_cnpj, left_weight = items[left_index]
                for right_cnpj, right_weight in items[left_index + 1:]:
                    key = (left_cnpj, right_cnpj) if left_cnpj < right_cnpj else (right_cnpj, left_cnpj)
                    contribution = left_weight * right_weight
                    if contribution <= 0.000001:
                        continue
                    stat = pair_stats.setdefault(key, {"dot": 0.0, "features": []})
                    stat["dot"] += contribution
                    if len(stat["features"]) < 18:
                        stat["features"].append({
                            "feature_id": feature_id,
                            "label": info.get("label") or feature_id,
                            "feature_type": info.get("feature_type") or "",
                            "bucket": info.get("bucket") or "",
                            "contribution": contribution,
                        })

        pair_rows: list[dict[str, Any]] = []
        for (left_cnpj, right_cnpj), stat in pair_stats.items():
            left = funds.get(left_cnpj)
            right = funds.get(right_cnpj)
            if not left or not right:
                continue
            denominator = norms.get(left_cnpj, 1.0) * norms.get(right_cnpj, 1.0)
            score = stat["dot"] / denominator if denominator else 0.0
            if score < 0.18:
                continue
            features = sorted(stat.get("features") or [], key=lambda item: item.get("contribution") or 0, reverse=True)
            shared_structures = [feature.get("label") for feature in features if feature.get("feature_type") == "structure"][:5]
            shared_options = [feature.get("label") for feature in features if feature.get("feature_type") in {"option_leg", "option_underlying"}][:5]
            shared_fixed_income = [feature.get("label") for feature in features if feature.get("feature_type") in {"fixed_income_maturity", "fixed_income_year"}][:5]
            shared_activity = [feature.get("label") for feature in features if feature.get("feature_type") == "activity_direction"][:5]
            shared_macro = [feature.get("label") for feature in features if feature.get("feature_type") in {"country", "market"}][:5]
            shared_assets = [feature.get("label") for feature in features if feature.get("feature_type") in {"asset", "issuer", "equity_underlying"}][:7]
            specific_feature_count = len([
                feature for feature in features
                if feature.get("feature_type") in {
                    "asset",
                    "issuer",
                    "issuer_doc",
                    "equity_underlying",
                    "option_leg",
                    "option_underlying",
                    "fixed_income_maturity",
                    "fixed_income_year",
                    "activity_direction",
                    "country",
                    "market",
                    "structure",
                }
            ])
            if specific_feature_count < 2:
                continue
            left_structures = sorted(left.get("structures") or [], key=lambda item: item.get("score") or 0, reverse=True)[:4]
            right_structures = sorted(right.get("structures") or [], key=lambda item: item.get("score") or 0, reverse=True)[:4]
            if shared_options:
                profile_label = "opcoes + ativo-base"
            elif shared_fixed_income:
                profile_label = "renda fixa/duration"
            elif shared_activity:
                profile_label = "atividade semelhante"
            elif shared_macro:
                profile_label = "exposicao geografica/mercado"
            elif shared_structures:
                profile_label = "estrutura semelhante"
            else:
                profile_label = "carteira sobreposta"
            pair_rows.append({
                "fund_a": left.get("fund_name"),
                "fund_a_cnpj": left_cnpj,
                "fund_a_type": left.get("fund_type"),
                "fund_b": right.get("fund_name"),
                "fund_b_cnpj": right_cnpj,
                "fund_b_type": right.get("fund_type"),
                "similarity_score": score,
                "similarity_pct": score * 100,
                "profile_label": profile_label,
                "shared_feature_count": len(features),
                "shared_factors": features[:8],
                "shared_structures": shared_structures,
                "shared_options": shared_options,
                "shared_fixed_income": shared_fixed_income,
                "shared_activity": shared_activity,
                "shared_macro": shared_macro,
                "shared_assets": shared_assets,
                "fund_a_structures": left_structures,
                "fund_b_structures": right_structures,
                "fund_a_gross": left.get("gross_total"),
                "fund_b_gross": right.get("gross_total"),
                "explanation": (
                    f"Similaridade de {score * 100:.1f}% por {profile_label}; fatores principais: "
                    f"{', '.join(str(feature.get('label')) for feature in features[:4])}."
                ),
            })
        pair_rows.sort(key=lambda row: (row.get("similarity_score") or 0, row.get("shared_feature_count") or 0), reverse=True)

        structure_rows = []
        for item in structure_stats.values():
            avg_score = item["score_sum"] / item["fund_count"] if item["fund_count"] else 0
            structure_rows.append({
                **item,
                "avg_score": avg_score,
                "avg_score_pct": avg_score * 100,
            })
        structure_rows.sort(key=lambda row: (row.get("fund_count") or 0, row.get("gross_value") or 0), reverse=True)

        factor_rows = []
        for feature_id, holdings in feature_to_funds.items():
            if len(holdings) < 2:
                continue
            info = feature_info.get(feature_id, {})
            gross_proxy = sum(self._num(funds.get(cnpj, {}).get("gross_total")) * min(weight, 1.0) for cnpj, weight in holdings.items())
            factor_rows.append({
                **info,
                "fund_count": len(holdings),
                "gross_proxy": gross_proxy,
                "avg_weight": sum(holdings.values()) / len(holdings),
                "sample_funds": [funds.get(cnpj, {}).get("fund_name") for cnpj, _ in sorted(holdings.items(), key=lambda item: item[1], reverse=True)[:5]],
            })
        factor_rows.sort(key=lambda row: (row.get("fund_count") or 0, row.get("gross_proxy") or 0), reverse=True)

        profile_rows = []
        for fund in funds.values():
            structures = sorted(fund.get("structures") or [], key=lambda item: item.get("score") or 0, reverse=True)
            if not structures:
                continue
            top_buckets = sorted((fund.get("bucket_gross") or {}).items(), key=lambda item: item[1], reverse=True)[:5]
            profile_rows.append({
                "fund_cnpj": fund.get("fund_cnpj"),
                "fund_name": fund.get("fund_name"),
                "fund_type": fund.get("fund_type"),
                "gross_total": fund.get("gross_total"),
                "net_total": fund.get("net_total"),
                "activity_total": fund.get("activity_total"),
                "structure_count": len(structures),
                "structures": structures[:5],
                "top_buckets": [
                    {"bucket": key, "bucket_label": labels.get(key, key), "gross_value": value, "share_pct": value / max(self._num(fund.get("gross_total")), 1.0) * 100}
                    for key, value in top_buckets
                ],
            })
        profile_rows.sort(key=lambda row: (row.get("structure_count") or 0, row.get("gross_total") or 0), reverse=True)

        return {
            "pairs": self._rank_rows(pair_rows[:item_limit]),
            "structures": self._rank_rows(structure_rows[:item_limit]),
            "factors": self._rank_rows(factor_rows[:item_limit]),
            "fund_profiles": self._rank_rows(profile_rows[:item_limit]),
            "summary": {
                "candidate_fund_count": len(funds),
                "pair_count": len(pair_rows),
                "structure_count": len(structure_rows),
                "factor_count": len(factor_rows),
                "feature_count": len(feature_to_funds),
                "month": month,
            },
            "methodology": (
                "Portfolio profile similarity builds sparse vectors from CDA holdings: asset buckets, issuers, "
                "specific assets, option underlyings/legs, fixed-income maturities and detected structures. "
                "Pairs are ranked by cosine similarity over normalized portfolio features; it is a holdings-overlap "
                "screen, not return correlation or causal inference."
            ),
        }
