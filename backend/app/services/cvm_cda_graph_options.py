from __future__ import annotations

import sqlite3
from typing import Any


class CvmCdaGraphOptionsMixin:
    def _fetch_option_triangulation(self, con: sqlite3.Connection, month: str, *, limit: int) -> dict[str, Any]:
        item_limit = max(12, min(int(limit or 36), 80))
        option_rows = [dict(row) for row in con.execute(
            """
            SELECT
                h.fund_cnpj,
                MAX(h.fund_name) AS fund_name,
                COALESCE(NULLIF(MAX(h.fund_type), ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'OPCAO SEM TICKER') AS option_key,
                MAX(h.asset_code) AS asset_code,
                MAX(h.asset_desc) AS asset_desc,
                MAX(h.issuer_name) AS issuer_name,
                COALESCE(NULLIF(MAX(h.asset_class), ''), 'Outros') AS asset_class,
                MAX(h.tp_aplic) AS tp_aplic,
                MAX(h.tp_ativo) AS tp_ativo,
                MAX(h.country) AS country,
                SUM(COALESCE(h.value_market, 0)) AS net_value_raw,
                SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                SUM(COALESCE(h.qty_final, 0)) AS qty_final,
                COUNT(*) AS holding_count
            FROM cvm_cda_holdings h
            WHERE h.month = ?
              AND ABS(COALESCE(h.value_market, 0)) > 0
              AND (
                (h.tp_aplic LIKE 'Op%' AND h.tp_aplic NOT LIKE 'Opera%')
                OR h.tp_ativo LIKE 'Op%'
                OR UPPER(h.asset_desc) LIKE 'OPCAO%'
                OR UPPER(h.asset_desc) LIKE 'OPCOES%'
              )
            GROUP BY
                h.fund_cnpj,
                COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'OPCAO SEM TICKER'),
                COALESCE(NULLIF(h.asset_class, ''), 'Outros'),
                h.tp_aplic,
                h.tp_ativo
            """,
            (month,),
        ).fetchall()]
        equity_rows = [dict(row) for row in con.execute(
            """
            SELECT
                h.fund_cnpj,
                MAX(h.fund_name) AS fund_name,
                COALESCE(NULLIF(MAX(h.fund_type), ''), 'Outros') AS fund_type,
                COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'ACAO SEM TICKER') AS equity_key,
                MAX(h.asset_code) AS asset_code,
                MAX(h.asset_desc) AS asset_desc,
                MAX(h.issuer_name) AS issuer_name,
                COALESCE(NULLIF(MAX(h.asset_class), ''), 'Acoes') AS asset_class,
                MAX(h.tp_aplic) AS tp_aplic,
                MAX(h.tp_ativo) AS tp_ativo,
                SUM(COALESCE(h.value_market, 0)) AS net_value,
                SUM(ABS(COALESCE(h.value_market, 0))) AS gross_value,
                SUM(COALESCE(h.value_buy, 0)) AS buy_value,
                SUM(COALESCE(h.value_sell, 0)) AS sell_value,
                COUNT(*) AS holding_count
            FROM cvm_cda_holdings h
            WHERE h.month = ?
              AND ABS(COALESCE(h.value_market, 0)) > 0
              AND (
                h.asset_class = 'Acoes'
                OR h.tp_aplic LIKE 'A%'
                OR h.tp_aplic LIKE 'Brazilian Depository Receipt%'
                OR h.tp_ativo LIKE '%BDR%'
                OR h.tp_ativo LIKE '%Fundos de%'
              )
            GROUP BY
                h.fund_cnpj,
                COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'ACAO SEM TICKER')
            """,
            (month,),
        ).fetchall()]

        option_by_key: dict[str, dict[str, Any]] = {}
        option_entries: list[dict[str, Any]] = []
        for row in option_rows:
            option_key = str(row.get("option_key") or "").strip() or "OPCAO SEM TICKER"
            side = self._option_side_from_row(row)
            role = self._option_position_role_from_row(row)
            underlying = self._infer_option_underlying(row)
            gross = abs(self._num(row.get("gross_value")))
            raw_net = self._num(row.get("net_value_raw"))
            holder_value = gross if role != "written" and raw_net >= 0 else 0.0
            writer_value = gross if role == "written" or raw_net < 0 else 0.0
            signed_value = holder_value - writer_value if (holder_value or writer_value) else raw_net
            display = row.get("asset_desc") or row.get("asset_code") or row.get("issuer_name") or option_key
            entry = {
                "fund_cnpj": row.get("fund_cnpj"),
                "fund_name": row.get("fund_name"),
                "fund_type": row.get("fund_type"),
                "option_key": option_key,
                "display_name": display,
                "asset_key": option_key,
                "asset_desc": row.get("asset_desc"),
                "asset_class": row.get("asset_class") or "Opcoes",
                "tp_aplic": row.get("tp_aplic"),
                "tp_ativo": row.get("tp_ativo"),
                "issuer_name": row.get("issuer_name"),
                "option_side": side,
                "option_position_role": role,
                "underlying_key": underlying,
                "gross_value": gross,
                "holder_value": holder_value,
                "writer_value": writer_value,
                "net_value": signed_value,
                "buy_value": self._num(row.get("buy_value")),
                "sell_value": self._num(row.get("sell_value")),
                "qty_final": self._num(row.get("qty_final")),
                "holding_count": int(row.get("holding_count") or 0),
            }
            option_entries.append(entry)
            aggregate = option_by_key.setdefault(option_key, {
                "option_key": option_key,
                "asset_key": option_key,
                "display_name": display,
                "asset_desc": row.get("asset_desc"),
                "asset_class": row.get("asset_class") or "Opcoes",
                "bucket": "options_put" if side == "put" else "options_call" if side == "call" else "options_unknown",
                "bucket_label": "Opcoes put" if side == "put" else "Opcoes call" if side == "call" else "Opcoes sem ticker",
                "option_side": side,
                "option_position_role": role,
                "underlying_key": underlying,
                "funds": set(),
                "fund_types": set(),
                "holder_value": 0.0,
                "writer_value": 0.0,
                "net_value": 0.0,
                "gross_value": 0.0,
                "buy_value": 0.0,
                "sell_value": 0.0,
                "holding_count": 0,
            })
            aggregate["funds"].add(row.get("fund_cnpj"))
            aggregate["fund_types"].add(row.get("fund_type") or "Outros")
            aggregate["holder_value"] += holder_value
            aggregate["writer_value"] += writer_value
            aggregate["net_value"] += signed_value
            aggregate["gross_value"] += gross
            aggregate["buy_value"] += self._num(row.get("buy_value"))
            aggregate["sell_value"] += self._num(row.get("sell_value"))
            aggregate["holding_count"] += int(row.get("holding_count") or 0)
            if not aggregate.get("underlying_key") and underlying:
                aggregate["underlying_key"] = underlying

        equity_by_fund_underlying: dict[str, dict[str, dict[str, Any]]] = {}
        for row in equity_rows:
            underlying = self._infer_equity_underlying(row)
            if not underlying:
                continue
            fund = str(row.get("fund_cnpj") or "").strip()
            if not fund:
                continue
            by_underlying = equity_by_fund_underlying.setdefault(fund, {})
            equity_key = str(row.get("equity_key") or "").strip() or underlying
            current = by_underlying.setdefault(underlying, {
                "fund_cnpj": fund,
                "fund_name": row.get("fund_name"),
                "fund_type": row.get("fund_type"),
                "underlying_key": underlying,
                "equity_key": equity_key,
                "equity_display": row.get("asset_desc") or row.get("asset_code") or equity_key,
                "asset_class": row.get("asset_class") or "Acoes",
                "gross_value": 0.0,
                "net_value": 0.0,
                "buy_value": 0.0,
                "sell_value": 0.0,
                "holding_count": 0,
                "sample_equities": [],
            })
            gross = abs(self._num(row.get("gross_value")))
            current["gross_value"] += gross
            current["net_value"] += self._num(row.get("net_value"))
            current["buy_value"] += self._num(row.get("buy_value"))
            current["sell_value"] += self._num(row.get("sell_value"))
            current["holding_count"] += int(row.get("holding_count") or 0)
            if len(current["sample_equities"]) < 4 and equity_key not in current["sample_equities"]:
                current["sample_equities"].append(equity_key)
            if gross > abs(self._num(current.get("top_equity_gross"))):
                current["equity_key"] = equity_key
                current["equity_display"] = row.get("asset_desc") or row.get("asset_code") or equity_key
                current["top_equity_gross"] = gross

        fund_links: dict[str, dict[str, Any]] = {}
        pair_rows: dict[str, dict[str, Any]] = {}
        underlying_rows: dict[str, dict[str, Any]] = {}
        for option in option_entries:
            underlying = option.get("underlying_key")
            if not underlying:
                continue
            fund = str(option.get("fund_cnpj") or "").strip()
            equity = equity_by_fund_underlying.get(fund, {}).get(str(underlying))
            base = underlying_rows.setdefault(str(underlying), {
                "underlying_key": underlying,
                "funds": set(),
                "option_count": 0,
                "option_gross_value": 0.0,
                "equity_gross_value": 0.0,
                "triangulated_gross_value": 0.0,
                "call_value": 0.0,
                "put_value": 0.0,
                "written_value": 0.0,
                "holder_value": 0.0,
                "sample_options": [],
                "sample_equities": [],
            })
            base["funds"].add(fund)
            base["option_count"] += 1
            base["option_gross_value"] += self._num(option.get("gross_value"))
            base["call_value"] += self._num(option.get("gross_value")) if option.get("option_side") == "call" else 0.0
            base["put_value"] += self._num(option.get("gross_value")) if option.get("option_side") == "put" else 0.0
            base["written_value"] += self._num(option.get("writer_value"))
            base["holder_value"] += self._num(option.get("holder_value"))
            if len(base["sample_options"]) < 5 and option.get("option_key") not in base["sample_options"]:
                base["sample_options"].append(option.get("option_key"))
            if not equity:
                continue
            base["equity_gross_value"] += self._num(equity.get("gross_value"))
            base["triangulated_gross_value"] += min(self._num(option.get("gross_value")), self._num(equity.get("gross_value")))
            for eq in equity.get("sample_equities") or []:
                if len(base["sample_equities"]) < 5 and eq not in base["sample_equities"]:
                    base["sample_equities"].append(eq)
            link_key = self._hash(fund, option.get("option_key"), equity.get("equity_key"), underlying)
            link = fund_links.setdefault(link_key, {
                "fund_cnpj": fund,
                "fund_name": option.get("fund_name"),
                "fund_type": option.get("fund_type"),
                "underlying_key": underlying,
                "option_key": option.get("option_key"),
                "option_display": option.get("display_name"),
                "option_side": option.get("option_side"),
                "option_position_role": option.get("option_position_role"),
                "equity_key": equity.get("equity_key"),
                "equity_display": equity.get("equity_display"),
                "option_gross_value": 0.0,
                "option_net_value": 0.0,
                "equity_gross_value": self._num(equity.get("gross_value")),
                "equity_net_value": self._num(equity.get("net_value")),
                "link_score": 0.0,
            })
            link["option_gross_value"] += self._num(option.get("gross_value"))
            link["option_net_value"] += self._num(option.get("net_value"))
            link["link_score"] = min(link["option_gross_value"], link["equity_gross_value"]) + max(link["option_gross_value"], link["equity_gross_value"]) * 0.08
            pair_key = self._hash(option.get("option_key"), equity.get("equity_key"), underlying)
            pair = pair_rows.setdefault(pair_key, {
                "underlying_key": underlying,
                "option_key": option.get("option_key"),
                "option_display": option.get("display_name"),
                "option_side": option.get("option_side"),
                "option_position_role": option.get("option_position_role"),
                "equity_key": equity.get("equity_key"),
                "equity_display": equity.get("equity_display"),
                "funds": set(),
                "option_gross_value": 0.0,
                "equity_gross_value": 0.0,
                "pair_score": 0.0,
            })
            pair["funds"].add(fund)
            pair["option_gross_value"] += self._num(option.get("gross_value"))
            pair["equity_gross_value"] += self._num(equity.get("gross_value"))
            pair["pair_score"] = min(pair["option_gross_value"], pair["equity_gross_value"]) + len(pair["funds"]) * 1_000_000_000

        option_ranked = []
        for item in option_by_key.values():
            item["fund_count"] = len([fund for fund in item.pop("funds") if fund])
            item["fund_type_count"] = len([fund_type for fund_type in item.pop("fund_types") if fund_type])
            item["long_value"] = item.get("holder_value", 0.0)
            item["short_value"] = item.get("writer_value", 0.0)
            item["correlation_score"] = item["gross_value"] + item["fund_count"] * 1_500_000_000
            option_ranked.append(item)
        option_ranked.sort(key=lambda row: row.get("correlation_score") or 0, reverse=True)
        for index, row in enumerate(option_ranked[:item_limit], start=1):
            row["rank"] = index
            row["trail_key"] = self._asset_trail_key(row.get("asset_key"), row.get("asset_class"), "shorted" if self._num(row.get("short_value")) > self._num(row.get("long_value")) else "coveted")
            row["side"] = "shorted" if self._num(row.get("short_value")) > self._num(row.get("long_value")) else "coveted"
            row["tone"] = "down" if row["side"] == "shorted" else "up"

        underlyings = []
        for item in underlying_rows.values():
            item["fund_count"] = len([fund for fund in item.pop("funds") if fund])
            item["coverage_ratio"] = (
                item["triangulated_gross_value"] / item["option_gross_value"] * 100.0
                if item["option_gross_value"] else 0.0
            )
            item["score"] = item["triangulated_gross_value"] + item["option_gross_value"] * 0.35 + item["fund_count"] * 1_000_000_000
            underlyings.append(item)
        underlyings.sort(key=lambda row: row.get("score") or 0, reverse=True)
        for index, row in enumerate(underlyings[:item_limit], start=1):
            row["rank"] = index

        links = list(fund_links.values())
        links.sort(key=lambda row: row.get("link_score") or 0, reverse=True)
        for index, row in enumerate(links[:item_limit], start=1):
            row["rank"] = index
            row["tone"] = "down" if row.get("option_position_role") == "written" else "up"

        pairs = []
        for item in pair_rows.values():
            item["shared_fund_count"] = len([fund for fund in item.pop("funds") if fund])
            pairs.append(item)
        pairs.sort(key=lambda row: row.get("pair_score") or 0, reverse=True)
        for index, row in enumerate(pairs[:item_limit], start=1):
            row["rank"] = index
            row["tone"] = "down" if row.get("option_position_role") == "written" else "up"

        return {
            "summary": {
                "option_position_count": len(option_entries),
                "option_asset_count": len(option_ranked),
                "underlying_count": len(underlyings),
                "fund_option_equity_link_count": len(links),
                "pair_count": len(pairs),
            },
            "option_rows": option_ranked[:item_limit],
            "underlying_rows": underlyings[:item_limit],
            "fund_option_equity_links": links[:item_limit],
            "asset_pair_rows": pairs[:item_limit],
            "methodology": (
                "Triangulation links option positions to inferred underlyings from option tickers/descriptions "
                "and then to equity/ETF positions held by the same fund. It is a portfolio-overlap screen, not price correlation."
            ),
        }
