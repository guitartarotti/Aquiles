from __future__ import annotations

from typing import Any

from .funds_flow_utils import (
    _money_brl,
    _money_usd_mn,
    _pct,
    _safe_float,
)


class FundsFlowInsightAgent:
    """Deterministic guardrailed insights from the dashboard JSON."""

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        report = payload.get("report") or {}
        kpis = payload.get("kpis") or {}
        top_inflows = payload.get("top_inflows") or []
        top_outflows = payload.get("top_outflows") or []
        stress = payload.get("stress_panel") or {}
        as_of = report.get("as_of_date") or "n/d"
        source_text = ", ".join(report.get("sources") or ["CVM"])

        inflow = top_inflows[0] if top_inflows else {}
        outflow = top_outflows[0] if top_outflows else {}
        regime = str(kpis.get("regime") or "neutral").replace("_", " ")

        quick_read = [
            (
                f"Base com data de corte {as_of}: fluxo liquido 21d de "
                f"{_money_brl(kpis.get('net_flow_21d'))}, equivalente a "
                f"{_pct(kpis.get('flow_pct_pl_21d'))} do PL."
            ),
            (
                f"Regime proprietario em {regime}; indice de pressao "
                f"{_safe_float(kpis.get('pressure_index'), 2) if kpis.get('pressure_index') is not None else 'n/d'}."
            ),
            (
                f"Maior entrada: {inflow.get('name', 'n/d')} "
                f"({_money_brl(inflow.get('net_flow_21d'))}); maior saida: "
                f"{outflow.get('name', 'n/d')} ({_money_brl(outflow.get('net_flow_21d'))})."
            ),
        ]

        shareholders = f"{int(kpis.get('total_shareholders') or 0):,}".replace(",", ".")
        diagnosis = (
            f"A leitura usa apenas o payload consolidado de {source_text}. "
            f"A industria soma {_money_brl(kpis.get('industry_aum'))} de PL e "
            f"{shareholders} cotistas na data de corte. O fluxo 5d foi "
            f"{_money_brl(kpis.get('net_flow_5d'))}, enquanto o YTD acumula "
            f"{_money_brl(kpis.get('net_flow_ytd'))}."
        )

        concentration_note = "sem sinal claro de concentracao extrema"
        hhi = _safe_float(stress.get("hhi_redemptions")) or 0.0
        pct_negative = _safe_float(stress.get("pct_funds_negative")) or 0.0
        if hhi > 0.25:
            concentration_note = "saidas concentradas em poucos fundos"
        elif pct_negative > 0.65:
            concentration_note = "saida disseminada entre fundos"

        ici = ((payload.get("brazil_vs_global") or {}).get("ici_global_flows") or {})
        ici_weekly = ici.get("weekly") or {}
        ici_latest = ici_weekly.get("latest_by_vehicle") or {}
        combined_latest = ici_latest.get("combined") or {}
        etf_latest = ici_latest.get("etf") or {}
        mutual_latest = ici_latest.get("mutual_fund") or {}
        if ici.get("status") == "ok" and combined_latest:
            global_comment = (
                f"ICI ativo ate {combined_latest.get('date')}: fluxo global combinado MF+ETF de "
                f"{_money_usd_mn(combined_latest.get('total_flow_usd_mn'))}, "
                f"com ETFs em {_money_usd_mn(etf_latest.get('total_flow_usd_mn'))} e mutual funds em "
                f"{_money_usd_mn(mutual_latest.get('total_flow_usd_mn'))}. "
                "A leitura compara esse apetite global com o fluxo local CVM sem inferir causalidade."
            )
        else:
            global_comment = (
                "Comparacao Brasil vs global ainda depende das cargas ICI completas neste contrato; "
                "a camada B3 ja entra como fluxo secundario por tipo de investidor, separado da captacao CVM."
            )

        return {
            "agent": "FundsFlowInsightAgent",
            "quick_read": quick_read,
            "diagnosis": diagnosis,
            "top_inflows_comment": (
                f"As principais entradas estao lideradas por {inflow.get('name', 'n/d')}; "
                "a leitura diferencia fluxo nominal de percentual do PL nos rankings."
            ),
            "top_outflows_comment": (
                f"As principais saidas estao lideradas por {outflow.get('name', 'n/d')}; "
                f"o painel de stress indica {concentration_note}."
            ),
            "brazil_vs_global_comment": global_comment,
            "risks": [
                "Nao interpretar coincidencia de fluxo com mercado como causalidade.",
                "Classificacoes inferidas recebem confidence_score menor ate haver tabela ANBIMA versionada.",
                "CVM publica arquivos mensais; a ultima data util disponivel pode ficar abaixo da data corrente.",
            ],
            "what_to_monitor": [
                "Se a entrada em Renda Fixa fica em fundos DI/curto prazo ou migra para duration/inflacao.",
                "Se Multimercados e Acoes seguem com perda de cotistas em 21d.",
                "Se o HHI de resgates sobe junto com percentual de fundos negativos.",
            ],
        }
