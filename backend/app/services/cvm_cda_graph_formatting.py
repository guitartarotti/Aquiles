from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from ..config import Config
from ..utils.logger import get_logger

logger = get_logger("aquiles.cvm_cda_graph.formatting")


class CvmCdaGraphFormattingMixin:
    def _node_summary(self, labels: list[str], props: dict[str, Any]) -> str:
        if "CdaFund" in labels:
            return f"Fundo CDA {props.get('cnpj')} com PL reportado de {self._fmt_brl(props.get('pl'))}."
        if "CdaAsset" in labels:
            return f"Ativo CDA de classe {props.get('asset_class') or 'nao informada'}."
        if "CdaIssuer" in labels:
            return "Emissor/contraparte presente nas carteiras CVM CDA."
        return "No deterministico do grafo CVM CDA."

    def _edge_fact(self, rel_type: str, source: dict[str, Any], target: dict[str, Any], props: dict[str, Any]) -> str:
        if rel_type == "HOLDS_POSITION":
            return (
                f"{source.get('name')} reportou posicao {props.get('side')} em {target.get('name')} "
                f"no valor de {self._fmt_brl(props.get('value_market'))}; "
                f"classe {props.get('asset_class') or 'nao informada'} e {self._fmt_pct(props.get('pct_pl'))} do PL."
            )
        if rel_type == "HAS_TARGET_EXPOSURE":
            return (
                f"{source.get('name')} tem exposicao ao tema {target.get('name')} "
                f"com valor liquido de {self._fmt_brl(props.get('net_value'))}, "
                f"gross de {self._fmt_brl(props.get('gross_value'))} e {self._fmt_pct(props.get('target_pct_pl'))} do PL."
            )
        if rel_type == "ISSUED_BY":
            return f"{source.get('name')} foi associado ao emissor/contraparte {target.get('name')}."
        if rel_type == "CLASSIFIED_AS":
            return f"{source.get('name')} entra na camada de ativo {target.get('name')}."
        if rel_type == "LOCATED_IN":
            return f"{source.get('name')} foi mapeado para exposicao geografica {target.get('name')}."
        return f"{source.get('name')} -> {rel_type} -> {target.get('name')}."

    @staticmethod
    def _rank_row(row: dict[str, Any], rank: int) -> dict[str, Any]:
        cleaned = dict(row)
        cleaned["rank"] = rank
        return cleaned

    @classmethod
    def _rank_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = []
        for index, row in enumerate(rows, start=1):
            item = cls._rank_row(row, index)
            item["activity_direction"] = cls._activity_direction(item.get("reported_activity"))
            ranked.append(item)
        return ranked

    @staticmethod
    def _activity_direction(value: Any) -> str:
        try:
            number = float(value or 0)
        except Exception:
            number = 0.0
        if number > 0:
            return "inflow"
        if number < 0:
            return "outflow"
        return "neutral"

    @staticmethod
    def _is_generic_asset_text(value: Any) -> bool:
        text = str(value or "").strip().lower()
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
            "unclassified",
            "sem ativo lider",
        )
        return not text or any(term in text for term in generic_terms)

    def _asset_trail_key(self, asset_key: Any, asset_class: Any, side: Any) -> str:
        return self._hash("asset_trail", asset_key, asset_class, side)

    @classmethod
    def _option_side_from_row(cls, row: dict[str, Any]) -> str:
        text = cls._symbol_text(row.get("tp_ativo"), row.get("asset_desc"), row.get("asset_code"))
        if "VENDA" in text or " PUT " in f" {text} ":
            return "put"
        if "COMPRA" in text or " CALL " in f" {text} ":
            return "call"
        return "unknown"

    @classmethod
    def _option_position_role_from_row(cls, row: dict[str, Any]) -> str:
        text = cls._symbol_text(row.get("tp_aplic"))
        if "LANC" in text or "LAN " in text:
            return "written"
        if "TITULAR" in text:
            return "holder"
        return "unknown"

    @classmethod
    def _infer_option_underlying(cls, row: dict[str, Any]) -> str:
        candidates = [
            row.get("asset_code"),
            row.get("asset_desc"),
            row.get("issuer_name"),
            row.get("option_key"),
        ]
        for raw in candidates:
            symbol = cls._infer_symbol_prefix(raw)
            if symbol:
                return symbol
        return ""

    @classmethod
    def _infer_equity_underlying(cls, row: dict[str, Any]) -> str:
        candidates = [
            row.get("asset_code"),
            row.get("asset_desc"),
            row.get("issuer_name"),
            row.get("equity_key"),
        ]
        for raw in candidates:
            symbol = cls._infer_symbol_prefix(raw, equity=True)
            if symbol:
                return symbol
        return ""

    @classmethod
    def _infer_symbol_prefix(cls, value: Any, *, equity: bool = False) -> str:
        text = cls._symbol_text(value)
        if not text:
            return ""
        if re.search(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", str(value or "")):
            return ""
        compact = re.sub(r"[^A-Z0-9]+", "", text)
        spaced = re.sub(r"[^A-Z0-9]+", " ", text).strip()
        if compact.startswith(("DOLOP", "DOL", "DOV", "WDO")) or "DOLAR" in spaced:
            return "USD/BRL"
        if compact.startswith(("IBOV", "WIN", "IND")):
            return "IBOV"
        if compact.startswith("BOVA"):
            return "BOVA11"
        if compact.startswith("SMAL"):
            return "SMAL11"
        if compact.startswith("IDIV"):
            return "IDIV"
        first = re.match(r"^([A-Z]{4})(?:[A-Z0-9]|\\s|$)", compact)
        if first:
            prefix = first.group(1)
            if prefix in {"OPCA", "OPCO", "OPFC", "OPCAO", "OFCF"}:
                return ""
            return prefix
        if equity:
            spaced_first = re.match(r"^([A-Z]{4})\\s", spaced)
            if spaced_first:
                return spaced_first.group(1)
        return ""

    @staticmethod
    def _symbol_text(*values: Any) -> str:
        raw = " ".join(str(value or "") for value in values if value is not None)
        replacements = {
            "Á": "A",
            "À": "A",
            "Â": "A",
            "Ã": "A",
            "Ä": "A",
            "Ç": "C",
            "É": "E",
            "Ê": "E",
            "Í": "I",
            "Ó": "O",
            "Ô": "O",
            "Õ": "O",
            "Ú": "U",
            "Ü": "U",
        }
        text = raw.upper()
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    @staticmethod
    def _asset_lens_labels() -> dict[str, str]:
        return {
            "all": "Todos",
            "equity": "Acoes/BDR",
            "fund_quotas": "Cotas de fundos",
            "fund_fixed_income": "Fundos RF/DI",
            "fund_multimarket": "Fundos multimercado",
            "fund_equity": "Fundos de acoes",
            "fund_real_estate": "Fundos imobiliarios",
            "fund_structured": "FIDC/FIP/FIAGRO",
            "options_call": "Opcoes call",
            "options_put": "Opcoes put",
            "options_unknown": "Opcoes sem ticker",
            "derivatives": "Derivativos/swaps",
            "foreign": "Exterior/BDR/ETF global",
            "public_bonds": "Titulos publicos",
            "private_credit": "Credito privado",
            "cash_if": "Depositos/IF",
            "confidential": "Confidencial",
            "other": "Outros",
        }

    @staticmethod
    def _asset_lens_tagged_cte() -> str:
        return """
            WITH tagged AS (
                SELECT
                    h.*,
                    COALESCE(NULLIF(h.asset_code, ''), NULLIF(h.asset_desc, ''), NULLIF(h.issuer_name, ''), 'UNCLASSIFIED') AS asset_key,
                    CASE
                        WHEN (
                            (h.tp_aplic LIKE 'Op%' AND h.tp_aplic NOT LIKE 'Opera%')
                            OR h.tp_ativo LIKE 'Op%'
                            OR UPPER(h.asset_desc) LIKE 'OPCAO%'
                            OR UPPER(h.asset_desc) LIKE 'OPCOES%'
                          )
                          AND (
                            LOWER(h.tp_ativo) LIKE '%compra%'
                            OR UPPER(h.asset_desc) LIKE '%CALL%'
                            OR UPPER(h.asset_code) LIKE '%CALL%'
                          )
                            THEN 'options_call'
                        WHEN (
                            (h.tp_aplic LIKE 'Op%' AND h.tp_aplic NOT LIKE 'Opera%')
                            OR h.tp_ativo LIKE 'Op%'
                            OR UPPER(h.asset_desc) LIKE 'OPCAO%'
                            OR UPPER(h.asset_desc) LIKE 'OPCOES%'
                          )
                          AND (
                            LOWER(h.tp_ativo) LIKE '%venda%'
                            OR UPPER(h.asset_desc) LIKE '%PUT%'
                            OR UPPER(h.asset_code) LIKE '%PUT%'
                          )
                            THEN 'options_put'
                        WHEN (
                            (h.tp_aplic LIKE 'Op%' AND h.tp_aplic NOT LIKE 'Opera%')
                            OR h.tp_ativo LIKE 'Op%'
                            OR UPPER(h.asset_desc) LIKE 'OPCAO%'
                            OR UPPER(h.asset_desc) LIKE 'OPCOES%'
                          )
                            THEN 'options_unknown'
                        WHEN h.tp_ativo LIKE '%Opção de compra%'
                          OR h.asset_desc LIKE 'OPCAO CALL%'
                          OR (h.tp_aplic LIKE '%Opções%' AND h.tp_ativo LIKE '%compra%')
                            THEN 'options_call'
                        WHEN h.tp_ativo LIKE '%Opção de venda%'
                          OR h.asset_desc LIKE 'OPCAO PUT%'
                          OR (h.tp_aplic LIKE '%Opções%' AND h.tp_ativo LIKE '%venda%')
                            THEN 'options_put'
                        WHEN h.asset_class = 'Acoes'
                          OR h.tp_aplic = 'Ações'
                          OR h.tp_aplic LIKE 'Brazilian Depository Receipt%'
                          OR h.tp_aplic LIKE 'Obrigações por ações%'
                          OR h.tp_ativo LIKE 'Ação%'
                          OR h.tp_ativo LIKE '%BDR%'
                          OR h.tp_ativo LIKE '%Fundos de Índice%'
                            THEN 'equity'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          AND (
                            h.tp_ativo LIKE '%Imobili%'
                            OR h.asset_desc LIKE '%IMOBILI%'
                            OR h.issuer_name LIKE '%IMOBILI%'
                            OR h.asset_desc LIKE '% FII%'
                            OR h.issuer_name LIKE '% FII%'
                          )
                            THEN 'fund_real_estate'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          AND (
                            h.tp_ativo LIKE '%FIDC%'
                            OR h.tp_ativo LIKE '%FIP%'
                            OR h.tp_ativo LIKE '%FIAGRO%'
                            OR h.asset_desc LIKE '%FIDC%'
                            OR h.asset_desc LIKE '%FIP%'
                            OR h.asset_desc LIKE '%FIAGRO%'
                          )
                            THEN 'fund_structured'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          AND (
                            h.asset_desc LIKE '%MULTIMERCADO%'
                            OR h.issuer_name LIKE '%MULTIMERCADO%'
                            OR h.asset_desc LIKE '% FIM%'
                            OR h.issuer_name LIKE '% FIM%'
                          )
                            THEN 'fund_multimarket'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          AND (
                            h.asset_desc LIKE '%AÇÕES%'
                            OR h.issuer_name LIKE '%AÇÕES%'
                            OR h.asset_desc LIKE '%ACOES%'
                            OR h.issuer_name LIKE '%ACOES%'
                            OR h.asset_desc LIKE '%EQUITY%'
                            OR h.issuer_name LIKE '%EQUITY%'
                          )
                            THEN 'fund_equity'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          AND (
                            h.asset_desc LIKE '%RENDA FIXA%'
                            OR h.issuer_name LIKE '%RENDA FIXA%'
                            OR h.asset_desc LIKE '%REFERENCIADO%'
                            OR h.issuer_name LIKE '%REFERENCIADO%'
                            OR h.asset_desc LIKE '% DI %'
                            OR h.issuer_name LIKE '% DI %'
                          )
                            THEN 'fund_fixed_income'
                        WHEN COALESCE(h.is_fund_quota, 0) = 1
                          OR h.asset_class = 'Cotas de Fundos'
                            THEN 'fund_quotas'
                        WHEN COALESCE(h.is_derivative, 0) = 1
                          OR h.asset_class = 'Derivativos'
                          OR h.tp_ativo LIKE '%SWAP%'
                            THEN 'derivatives'
                        WHEN COALESCE(h.is_foreign, 0) = 1
                          OR h.asset_class = 'Investimento Exterior'
                            THEN 'foreign'
                        WHEN h.asset_class = 'Titulos Publicos'
                          OR h.tp_aplic LIKE '%Títulos Públicos%'
                            THEN 'public_bonds'
                        WHEN h.asset_class = 'Credito Privado'
                          OR h.tp_aplic LIKE '%Debêntures%'
                          OR h.tp_ativo LIKE '%Debênture%'
                            THEN 'private_credit'
                        WHEN h.asset_class = 'Depositos e IF'
                          OR h.tp_aplic LIKE '%Depósitos%'
                            THEN 'cash_if'
                        WHEN h.asset_class = 'Confidencial'
                            THEN 'confidential'
                        ELSE 'other'
                    END AS asset_bucket,
                    CASE
                        WHEN LOWER(h.tp_ativo) LIKE '%compra%' OR UPPER(h.asset_desc) LIKE '%CALL%' THEN 'call'
                        WHEN LOWER(h.tp_ativo) LIKE '%venda%' OR UPPER(h.asset_desc) LIKE '%PUT%' THEN 'put'
                        WHEN h.tp_ativo LIKE '%Opção de compra%' OR h.asset_desc LIKE 'OPCAO CALL%' THEN 'call'
                        WHEN h.tp_ativo LIKE '%Opção de venda%' OR h.asset_desc LIKE 'OPCAO PUT%' THEN 'put'
                        ELSE ''
                    END AS option_side,
                    CASE
                        WHEN h.tp_aplic LIKE '%lan%' THEN 'written'
                        WHEN h.tp_aplic LIKE '%titular%' THEN 'holder'
                        ELSE ''
                    END AS option_position_role
                FROM cvm_cda_holdings h
                WHERE h.month = ?
            )
        """

    def _b3_trend_csv_path(self) -> Path:
        return Path(Config.MACRO_DATA_DIR) / "funds_flow_local" / "derived" / "b3_trend_by_participant.csv"

    def _read_b3_participant_trends(self) -> list[dict[str, Any]]:
        path = self._b3_trend_csv_path()
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    rows.append({
                        "participant_type": row.get("participant_type"),
                        "date": row.get("date"),
                        "daily_net_flow_brl": self._num(row.get("daily_net_flow_brl")),
                        "rolling_5d_net_flow_brl": self._num(row.get("rolling_5d_net_flow_brl")),
                        "rolling_21d_net_flow_brl": self._num(row.get("rolling_21d_net_flow_brl")),
                        "buy_participation_pct": self._num(row.get("buy_participation_pct")),
                        "sell_participation_pct": self._num(row.get("sell_participation_pct")),
                    })
        except Exception as exc:
            logger.warning("Failed to read B3 participant trend CSV for CDA graph coherence: %s", exc)
            return []
        return rows

    @staticmethod
    def _chunks(rows: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
        for index in range(0, len(rows), size):
            yield rows[index:index + size]

    def _props(self, row: dict[str, Any]) -> dict[str, Any]:
        props = {}
        for key, value in row.items():
            cleaned = self._clean_value(value)
            if cleaned is not None:
                props[key] = cleaned
        return props

    @staticmethod
    def _clean_value(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                return None
            return value
        if isinstance(value, (list, tuple)):
            return [CvmCdaGraphFormattingMixin._clean_value(item) for item in value if CvmCdaGraphFormattingMixin._clean_value(item) is not None]
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _digits(value: Any) -> str:
        return re.sub(r"\D+", "", str(value or ""))

    @staticmethod
    def _clean_label(value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        return text if text else fallback

    @staticmethod
    def _num(value: Any) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    @staticmethod
    def _bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        try:
            return int(value or 0) == 1
        except Exception:
            return False

    def _asset_key(self, row: dict[str, Any]) -> str:
        for key in ("asset_code", "isin", "asset_desc", "issuer_name"):
            value = str(row.get(key) or "").strip()
            if value:
                return value
        return f"{row.get('source_block') or 'CDA'}:{row.get('fund_cnpj') or ''}:{row.get('position_rank') or ''}"

    def _fund_id(self, month: str, cnpj: Any) -> str:
        return self._node_id(month, "fund", self._digits(cnpj))

    def _asset_id(self, month: str, security_key: str, asset_class: str) -> str:
        return self._node_id(month, "asset", security_key, asset_class)

    def _issuer_id(self, month: str, issuer_name: str, issuer_doc: str | None = None) -> str:
        return self._node_id(month, "issuer", issuer_doc or issuer_name)

    def _target_id(self, month: str, target: Any) -> str:
        return self._node_id(month, "target", target)

    def _node_id(self, month: str, node_type: str, *parts: Any) -> str:
        digest = self._hash(*parts)
        return f"cda:{month}:{node_type}:{digest}"

    def _edge_id(self, edge_type: str, *parts: Any) -> str:
        digest = self._hash(edge_type, *parts)
        return f"cda:edge:{digest}"

    @staticmethod
    def _hash(*parts: Any) -> str:
        raw = "|".join(str(part or "").strip().lower() for part in parts)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _month_label(month: str) -> str:
        text = re.sub(r"[^0-9]", "", str(month or ""))
        if len(text) == 6:
            return f"{text[:4]}-{text[4:]}"
        return str(month)

    @staticmethod
    def _fmt_brl(value: Any) -> str:
        try:
            number = float(value or 0)
        except Exception:
            number = 0
        abs_number = abs(number)
        sign = "-" if number < 0 else ""
        if abs_number >= 1e12:
            return f"{sign}R$ {abs_number / 1e12:.2f} tri"
        if abs_number >= 1e9:
            return f"{sign}R$ {abs_number / 1e9:.1f} bi"
        if abs_number >= 1e6:
            return f"{sign}R$ {abs_number / 1e6:.1f} mi"
        return f"{sign}R$ {abs_number:,.0f}"

    @staticmethod
    def _fmt_pct(value: Any) -> str:
        try:
            number = float(value or 0)
        except Exception:
            number = 0
        return f"{number:.2f}%"
