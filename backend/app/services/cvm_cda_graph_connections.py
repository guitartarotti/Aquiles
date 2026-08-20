from __future__ import annotations

import sqlite3
from typing import Any

from .cvm_cda_contracts import CDA_TARGET_LABELS, CDA_TARGET_SQL


class CvmCdaGraphConnectionsMixin:
    def _fetch_participant_asset_coherence(self, con: sqlite3.Connection, month: str, *, limit: int) -> dict[str, Any]:
        participants = self._read_b3_participant_trends()
        labels = self._asset_lens_labels()
        tagged_cte = self._asset_lens_tagged_cte()
        bucket_rows = [dict(row) for row in con.execute(
            f"""
            {tagged_cte}
            SELECT
                asset_bucket AS bucket,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(DISTINCT asset_key) AS asset_count,
                SUM(CASE WHEN COALESCE(value_market, 0) > 0 THEN COALESCE(value_market, 0) ELSE 0 END) AS long_value,
                SUM(CASE WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) AS buy_value,
                SUM(COALESCE(value_sell, 0)) AS sell_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity,
                group_concat(DISTINCT asset_key) AS sample_assets
            FROM tagged
            GROUP BY asset_bucket
            HAVING gross_value > 0
            """,
            (month,),
        ).fetchall()]
        focus_buckets = {
            "equity",
            "fund_quotas",
            "fund_equity",
            "fund_multimarket",
            "fund_real_estate",
            "fund_structured",
            "options_call",
            "options_put",
            "options_unknown",
            "derivatives",
            "foreign",
        }
        bucket_rows = [row for row in bucket_rows if row.get("bucket") in focus_buckets]
        rows: list[dict[str, Any]] = []
        for participant in participants:
            participant_flow = self._num(participant.get("rolling_21d_net_flow_brl"))
            if abs(participant_flow) < 1:
                continue
            for bucket in bucket_rows:
                activity = self._num(bucket.get("reported_activity"))
                if abs(activity) < 1:
                    continue
                same_direction = participant_flow * activity > 0
                bucket_key = str(bucket.get("bucket") or "other")
                score = abs(participant_flow) * (abs(activity) + abs(self._num(bucket.get("net_value"))) * 0.15)
                relationship = "coerente" if same_direction else "divergente"
                participant_direction = "entrada" if participant_flow > 0 else "saida"
                bucket_direction = "compra liquida/aumento reportado" if activity > 0 else "venda liquida/reducao reportada"
                bucket_label = labels.get(bucket_key, bucket_key)
                sample_assets = [item for item in str(bucket.get("sample_assets") or "").split(",") if item][:4]
                rows.append({
                    "participant_type": participant.get("participant_type"),
                    "participant_flow_21d_brl": participant_flow,
                    "participant_flow_5d_brl": self._num(participant.get("rolling_5d_net_flow_brl")),
                    "participant_daily_flow_brl": self._num(participant.get("daily_net_flow_brl")),
                    "participant_date": participant.get("date"),
                    "bucket": bucket_key,
                    "bucket_label": bucket_label,
                    "fund_count": bucket.get("fund_count"),
                    "asset_count": bucket.get("asset_count"),
                    "bucket_activity": activity,
                    "bucket_buy_value": bucket.get("buy_value"),
                    "bucket_sell_value": bucket.get("sell_value"),
                    "bucket_net_value": bucket.get("net_value"),
                    "bucket_gross_value": bucket.get("gross_value"),
                    "sample_assets": sample_assets,
                    "relationship": relationship,
                    "participant_direction": participant_direction,
                    "bucket_direction": bucket_direction,
                    "window_note": (
                        f"B3 usa fluxo liquido de participante em 21 dias ate {participant.get('date') or 'a data BDI'}; "
                        f"CDA usa atividade reportada no mes {month}."
                    ),
                    "rule_note": (
                        "Classificacao por sinal: coerente quando fluxo B3 e atividade CDA apontam na mesma direcao; "
                        "divergente quando os sinais sao opostos. A leitura e coincidencia temporal, nao causalidade."
                    ),
                    "ranking_note": (
                        "O ranking prioriza materialidade: abs(fluxo B3 21d) multiplicado por "
                        "(abs(atividade CDA) + 15% de abs(posicao liquida CDA))."
                    ),
                    "explanation": (
                        f"{participant.get('participant_type')} registrou {participant_direction} liquida de "
                        f"{self._fmt_brl(participant_flow)} em 21d na B3. No CDA, {bucket_label} mostrou "
                        f"{bucket_direction} de {self._fmt_brl(activity)} no mes {month}. "
                        f"Por isso a tela marcou a relacao como {relationship}."
                    ),
                    "tone": "up" if same_direction and activity > 0 else "down" if same_direction else "warn",
                    "score": score,
                    "note": (
                        f"{participant.get('participant_type')} {'entrou' if participant_flow > 0 else 'saiu'} "
                        f"{self._fmt_brl(participant_flow)} em 21d na B3 enquanto {bucket_label} "
                        f"teve atividade CDA de {self._fmt_brl(activity)}."
                    ),
                })
        rows.sort(key=lambda row: row.get("score") or 0, reverse=True)
        item_limit = max(6, min(int(limit or 16), 32))
        max_score = max((self._num(row.get("score")) for row in rows), default=0)
        for index, row in enumerate(rows[:item_limit], start=1):
            row["rank"] = index
            row["score_share"] = self._num(row.get("score")) / max_score if max_score else 0
        return {
            "rows": rows[:item_limit],
            "source_note": (
                "B3 participant flow is daily/21d from BDI; CDA activity is monthly portfolio report. "
                "Rows are coincidence/coherence screens, not causal attribution."
            ),
            "participant_source": str(self._b3_trend_csv_path()),
        }

    def _fetch_bridge_path_details(
        self,
        con: sqlite3.Connection,
        month: str,
        bridge_paths: list[dict[str, Any]],
        *,
        limit: int,
    ) -> dict[str, Any]:
        details: dict[str, Any] = {}
        item_limit = max(5, min(int(limit or 12), 24))
        for bridge in bridge_paths:
            target = str(bridge.get("target") or "").strip()
            fund_type = str(bridge.get("fund_type") or "").strip()
            condition = CDA_TARGET_SQL.get(target)
            if not target or not fund_type or not condition:
                continue
            key = f"{target}|{fund_type}"
            params = (month, fund_type, item_limit)
            funds = [dict(row) for row in con.execute(
                f"""
                SELECT
                    h.fund_cnpj,
                    MAX(h.fund_name) AS fund_name,
                    COALESCE(NULLIF(MAX(h.fund_type), ''), 'Outros') AS fund_type,
                    COUNT(*) AS holding_count,
                    COUNT(DISTINCT NULLIF(h.issuer_name, '')) AS issuer_count,
                    COUNT(DISTINCT COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''))) AS asset_count,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS long_value,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(h.value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                    SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                    SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                    SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0)) AS reported_activity,
                    MAX(fs.pl) AS pl,
                    CASE WHEN MAX(fs.pl) != 0 THEN SUM(COALESCE(h.value_market, 0)) / MAX(fs.pl) * 100.0 ELSE NULL END AS target_pct_pl
                FROM cvm_cda_holdings h
                LEFT JOIN cvm_cda_fund_summary fs
                  ON fs.month = h.month AND fs.fund_cnpj = h.fund_cnpj
                WHERE h.month = ?
                  AND COALESCE(NULLIF(h.fund_type, ''), 'Outros') = ?
                  AND ({condition})
                GROUP BY h.fund_cnpj
                ORDER BY SUM(ABS(COALESCE(h.value_market, 0))) DESC,
                         ABS(SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0))) DESC
                LIMIT ?
                """,
                params,
            ).fetchall()]
            issuers = [dict(row) for row in con.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(h.issuer_name, ''), 'Emissor nao identificado') AS issuer_name,
                    COUNT(DISTINCT h.fund_cnpj) AS fund_count,
                    COUNT(*) AS holding_count,
                    COUNT(DISTINCT COALESCE(NULLIF(h.asset_class, ''), 'Outros')) AS asset_class_count,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS long_value,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(h.value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                    SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0)) AS reported_activity,
                    MAX(COALESCE(NULLIF(h.asset_class, ''), 'Outros')) AS sample_asset_class
                FROM cvm_cda_holdings h
                WHERE h.month = ?
                  AND COALESCE(NULLIF(h.fund_type, ''), 'Outros') = ?
                  AND ({condition})
                  AND COALESCE(NULLIF(h.issuer_name, ''), 'Emissor nao identificado') <> 'Emissor nao identificado'
                GROUP BY COALESCE(NULLIF(h.issuer_name, ''), 'Emissor nao identificado')
                ORDER BY SUM(ABS(COALESCE(h.value_market, 0))) DESC
                LIMIT ?
                """,
                params,
            ).fetchall()]
            assets = [dict(row) for row in con.execute(
                f"""
                SELECT
                    COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'UNCLASSIFIED') AS asset_key,
                    MAX(h.asset_desc) AS asset_desc,
                    MAX(h.issuer_name) AS issuer_name,
                    COALESCE(NULLIF(MAX(h.asset_class), ''), 'Outros') AS asset_class,
                    COUNT(DISTINCT h.fund_cnpj) AS fund_count,
                    COUNT(*) AS holding_count,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) > 0 THEN COALESCE(h.value_market, 0) ELSE 0 END) AS long_value,
                    SUM(CASE WHEN COALESCE(h.value_market, 0) < 0 THEN ABS(COALESCE(h.value_market, 0)) ELSE 0 END) AS short_value,
                    SUM(COALESCE(h.value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                    SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                    SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                    SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0)) AS reported_activity
                FROM cvm_cda_holdings h
                WHERE h.month = ?
                  AND COALESCE(NULLIF(h.fund_type, ''), 'Outros') = ?
                  AND ({condition})
                GROUP BY COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'UNCLASSIFIED')
                ORDER BY SUM(ABS(COALESCE(h.value_market, 0))) DESC,
                         ABS(SUM(COALESCE(h.value_buy, 0)) - SUM(COALESCE(h.value_sell, 0))) DESC
                LIMIT ?
                """,
                params,
            ).fetchall()]
            details[key] = {
                "target": target,
                "target_label": bridge.get("target_label") or CDA_TARGET_LABELS.get(target, target),
                "fund_type": fund_type,
                "summary": bridge,
                "funds": self._rank_rows(funds),
                "issuers": self._rank_rows(issuers),
                "assets": self._rank_rows(assets),
            }
        return details

    def _fetch_explanatory_connections(self, con: sqlite3.Connection, month: str, *, limit: int) -> list[dict[str, Any]]:
        per_query_limit = max(6, min(int(limit or 20), 40))
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        generic_terms = (
            "emissor nao identificado",
            "nao informado",
            "valor a pagar",
            "valores a pagar",
            "valor a receber",
            "valores a receber",
            "disponibilidade",
            "caixa",
            "outros",
            "sem ativo lider",
        )

        def is_generic_text(value: Any) -> bool:
            text = str(value or "").strip().lower()
            return not text or any(term in text for term in generic_terms)

        def tone_for(*values: Any) -> str:
            for value in values:
                number = self._num(value)
                if abs(number) > 0.000001:
                    return "up" if number > 0 else "down"
            return "flat"

        def add(
            *,
            connection_type: str,
            name: str,
            fact: str,
            score: float,
            category: str,
            tone: str = "flat",
            metrics: dict[str, Any] | None = None,
        ) -> None:
            key = self._hash(connection_type, name, fact[:180])
            if key in seen:
                return
            seen.add(key)
            rows.append({
                "uuid": f"cda:explanatory:{key}",
                "name": name,
                "fact": fact,
                "fact_type": connection_type,
                "category": category,
                "tone": tone,
                "score": float(score or 0),
                "metrics": metrics or {},
            })

        for target, condition in CDA_TARGET_SQL.items():
            target_rows = [dict(row) for row in con.execute(
                f"""
                SELECT
                    ? AS target,
                    ? AS target_label,
                    COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                    COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado') AS issuer_name,
                    COUNT(DISTINCT fund_cnpj) AS fund_count,
                    COUNT(*) AS holding_count,
                    COUNT(DISTINCT COALESCE(NULLIF(asset_class, ''), 'Outros')) AS asset_class_count,
                    SUM(COALESCE(value_market, 0)) AS net_value,
                    SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                    SUM(COALESCE(value_buy, 0)) AS buy_value,
                    SUM(COALESCE(value_sell, 0)) AS sell_value,
                    SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity,
                    MAX(COALESCE(NULLIF(asset_class, ''), 'Outros')) AS sample_asset_class
                FROM cvm_cda_holdings
                WHERE month = ?
                  AND ({condition})
                  AND COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado') <> 'Emissor nao identificado'
                GROUP BY
                    COALESCE(NULLIF(fund_type, ''), 'Outros'),
                    COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado')
                HAVING COUNT(DISTINCT fund_cnpj) >= 2
                   AND SUM(ABS(COALESCE(value_market, 0))) > 0
                ORDER BY SUM(ABS(COALESCE(value_market, 0))) DESC,
                         ABS(SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0))) DESC
                LIMIT ?
                """,
                (target, CDA_TARGET_LABELS[target], month, per_query_limit),
            ).fetchall()]
            for item in target_rows:
                if is_generic_text(item.get("issuer_name")):
                    continue
                activity = self._num(item.get("reported_activity"))
                gross = self._num(item.get("gross_value"))
                score = gross + abs(activity) * 0.65 + self._num(item.get("fund_count")) * 10_000_000_000
                add(
                    connection_type="TARGET_ISSUER_CLUSTER",
                    name=f"{item.get('target_label')} -> {item.get('issuer_name')}",
                    category="Tema + emissor",
                    tone=tone_for(activity, item.get("net_value")),
                    score=score,
                    metrics=item,
                    fact=(
                        f"{item.get('fund_count')} fundos {item.get('fund_type')} conectam {item.get('target_label')} "
                        f"a {item.get('issuer_name')}, com gross {self._fmt_brl(item.get('gross_value'))}, "
                        f"liquido {self._fmt_brl(item.get('net_value'))} e atividade declarada "
                        f"{self._fmt_brl(activity)}."
                    ),
                )

        activity_rows = [dict(row) for row in con.execute(
            """
            SELECT
                COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(asset_class, ''), 'Outros') AS asset_class,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(DISTINCT NULLIF(issuer_name, '')) AS issuer_count,
                COUNT(*) AS holding_count,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) AS buy_value,
                SUM(COALESCE(value_sell, 0)) AS sell_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings
            WHERE month = ?
            GROUP BY COALESCE(NULLIF(fund_type, ''), 'Outros'), COALESCE(NULLIF(asset_class, ''), 'Outros')
            HAVING SUM(ABS(COALESCE(value_market, 0))) > 0
            ORDER BY ABS(SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0))) DESC,
                     SUM(ABS(COALESCE(value_market, 0))) DESC
            LIMIT ?
            """,
            (month, per_query_limit),
        ).fetchall()]
        for item in activity_rows:
            if is_generic_text(item.get("asset_class")):
                continue
            activity = self._num(item.get("reported_activity"))
            gross = self._num(item.get("gross_value"))
            if abs(activity) < 1 and gross < 50_000_000:
                continue
            add(
                connection_type="FUND_TYPE_ASSET_ACTIVITY",
                name=f"{item.get('fund_type')} -> {item.get('asset_class')}",
                category="Tipo + classe",
                tone=tone_for(activity, item.get("net_value")),
                score=gross + abs(activity) + self._num(item.get("fund_count")) * 5_000_000_000,
                metrics=item,
                fact=(
                    f"{item.get('fund_type')} reportou atividade liquida de {self._fmt_brl(activity)} "
                    f"em {item.get('asset_class')} (compras {self._fmt_brl(item.get('buy_value'))}, "
                    f"vendas {self._fmt_brl(item.get('sell_value'))}) em {item.get('fund_count')} fundos; "
                    f"estoque liquido {self._fmt_brl(item.get('net_value'))}."
                ),
            )

        country_rows = [dict(row) for row in con.execute(
            """
            SELECT
                COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(country, ''), 'Nao informado') AS country,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(*) AS holding_count,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(CASE WHEN COALESCE(value_market, 0) > 0 THEN COALESCE(value_market, 0) ELSE 0 END) AS long_value,
                SUM(CASE WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings
            WHERE month = ?
              AND COALESCE(NULLIF(country, ''), 'Nao informado') <> 'Nao informado'
            GROUP BY COALESCE(NULLIF(fund_type, ''), 'Outros'), COALESCE(NULLIF(country, ''), 'Nao informado')
            HAVING COUNT(DISTINCT fund_cnpj) >= 2
               AND SUM(ABS(COALESCE(value_market, 0))) > 0
            ORDER BY SUM(ABS(COALESCE(value_market, 0))) DESC,
                     ABS(SUM(COALESCE(value_market, 0))) DESC
            LIMIT ?
            """,
            (month, per_query_limit),
        ).fetchall()]
        for item in country_rows:
            add(
                connection_type="GEOGRAPHIC_EXPOSURE_CLUSTER",
                name=f"{item.get('fund_type')} -> {item.get('country')}",
                category="Pais + tipo",
                tone=tone_for(item.get("net_value"), item.get("reported_activity")),
                score=self._num(item.get("gross_value")) + self._num(item.get("fund_count")) * 4_000_000_000,
                metrics=item,
                fact=(
                    f"No mapa geografico, {item.get('fund_type')} carrega {self._fmt_brl(item.get('gross_value'))} "
                    f"gross em {item.get('country')}, com long {self._fmt_brl(item.get('long_value'))}, "
                    f"short {self._fmt_brl(item.get('short_value'))} e {item.get('fund_count')} fundos conectados."
                ),
            )

        short_rows = [dict(row) for row in con.execute(
            """
            SELECT
                COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(asset_class, ''), 'Outros') AS asset_class,
                COALESCE(NULLIF(asset_code, ''), NULLIF(asset_desc, ''), NULLIF(issuer_name, ''), 'Sem ativo lider') AS sample_asset,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(*) AS holding_count,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(CASE WHEN COALESCE(value_market, 0) < 0 THEN ABS(COALESCE(value_market, 0)) ELSE 0 END) AS short_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings
            WHERE month = ?
              AND (COALESCE(is_derivative, 0) = 1 OR COALESCE(value_market, 0) < 0)
            GROUP BY
                COALESCE(NULLIF(fund_type, ''), 'Outros'),
                COALESCE(NULLIF(asset_class, ''), 'Outros'),
                COALESCE(NULLIF(asset_code, ''), NULLIF(asset_desc, ''), NULLIF(issuer_name, ''), 'Sem ativo lider')
            HAVING SUM(ABS(COALESCE(value_market, 0))) > 0
            ORDER BY SUM(ABS(COALESCE(value_market, 0))) DESC
            LIMIT ?
            """,
            (month, per_query_limit),
        ).fetchall()]
        for item in short_rows:
            if is_generic_text(item.get("sample_asset")) or is_generic_text(item.get("asset_class")):
                continue
            add(
                connection_type="SHORT_DERIVATIVE_POCKET",
                name=f"{item.get('fund_type')} -> {item.get('sample_asset')}",
                category="Short/derivativo",
                tone="down" if self._num(item.get("short_value")) > 0 else tone_for(item.get("net_value")),
                score=self._num(item.get("gross_value")) + self._num(item.get("short_value")) * 0.5,
                metrics=item,
                fact=(
                    f"Bolso vendido/derivativo: {item.get('fund_type')} aparece em {item.get('sample_asset')} "
                    f"({item.get('asset_class')}), com gross {self._fmt_brl(item.get('gross_value'))}, "
                    f"short {self._fmt_brl(item.get('short_value'))} e {item.get('fund_count')} fundos."
                ),
            )

        issuer_rows = [dict(row) for row in con.execute(
            """
            SELECT
                COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado') AS issuer_name,
                COUNT(DISTINCT fund_cnpj) AS fund_count,
                COUNT(DISTINCT COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_type_count,
                group_concat(DISTINCT COALESCE(NULLIF(fund_type, ''), 'Outros')) AS fund_types,
                COUNT(DISTINCT COALESCE(NULLIF(asset_class, ''), 'Outros')) AS asset_class_count,
                SUM(COALESCE(value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(value_market, 0))) AS gross_value,
                SUM(COALESCE(value_buy, 0)) - SUM(COALESCE(value_sell, 0)) AS reported_activity
            FROM cvm_cda_holdings
            WHERE month = ?
              AND COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado') <> 'Emissor nao identificado'
            GROUP BY COALESCE(NULLIF(issuer_name, ''), 'Emissor nao identificado')
            HAVING COUNT(DISTINCT fund_cnpj) >= 5
            ORDER BY COUNT(DISTINCT fund_cnpj) DESC,
                     SUM(ABS(COALESCE(value_market, 0))) DESC
            LIMIT ?
            """,
            (month, per_query_limit),
        ).fetchall()]
        for item in issuer_rows:
            if is_generic_text(item.get("issuer_name")):
                continue
            fund_types = ", ".join(str(item.get("fund_types") or "").split(",")[:4])
            add(
                connection_type="ISSUER_CROWDING_CLUSTER",
                name=f"Crowding -> {item.get('issuer_name')}",
                category="Crowding",
                tone=tone_for(item.get("reported_activity"), item.get("net_value")),
                score=self._num(item.get("fund_count")) * 12_000_000_000 + self._num(item.get("gross_value")),
                metrics=item,
                fact=(
                    f"{item.get('issuer_name')} e ponto de crowding: {item.get('fund_count')} fundos, "
                    f"{item.get('fund_type_count')} tipos ({fund_types}) e {self._fmt_brl(item.get('gross_value'))} "
                    f"gross; saldo liquido {self._fmt_brl(item.get('net_value'))}."
                ),
            )

        concentration_rows = [dict(row) for row in con.execute(
            """
            SELECT
                fund_name,
                fund_cnpj,
                COALESCE(NULLIF(fund_type, ''), 'Outros') AS fund_type,
                target,
                target_label,
                target_pct_pl,
                gross_value,
                net_value,
                concentration_pct,
                top_issuer,
                top_asset_class
            FROM cvm_cda_fund_target_exposure
            WHERE month = ?
              AND COALESCE(pl, 0) > 1000000
              AND ABS(COALESCE(target_pct_pl, 0)) <= 500
              AND (ABS(COALESCE(target_pct_pl, 0)) >= 5 OR COALESCE(gross_value, 0) >= 100000000)
            ORDER BY ABS(COALESCE(target_pct_pl, 0)) DESC,
                     COALESCE(gross_value, 0) DESC
            LIMIT ?
            """,
            (month, per_query_limit),
        ).fetchall()]
        for item in concentration_rows:
            add(
                connection_type="FUND_TARGET_CONCENTRATION",
                name=f"{item.get('fund_name')} -> {item.get('target_label')}",
                category="Concentracao",
                tone=tone_for(item.get("net_value")),
                score=abs(self._num(item.get("target_pct_pl"))) * 1_000_000_000 + self._num(item.get("gross_value")),
                metrics=item,
                fact=(
                    f"{item.get('fund_name')} tem {self._fmt_pct(item.get('target_pct_pl'))} do PL em "
                    f"{item.get('target_label')}, gross {self._fmt_brl(item.get('gross_value'))}, "
                    f"top emissor {item.get('top_issuer') or 'nao identificado'} e classe "
                    f"{item.get('top_asset_class') or 'nao informada'}."
                ),
            )

        rows.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        for index, row in enumerate(rows[:limit], start=1):
            row["rank"] = index
        return rows[:limit]
