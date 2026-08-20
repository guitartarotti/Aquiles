from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ...config import Config
from ...utils.llm_client import LLMClient
from ...utils.logger import get_logger
from ..options_store import OptionsStore

logger = get_logger("aquiles.options_modeling.daily_insights")


class OptionsDailyInsightService:
    def __init__(
        self,
        store: OptionsStore | None = None,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.store = store or OptionsStore()
        self._llm_client = llm_client

    @property
    def llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def get_or_create(
        self,
        *,
        underlying_security: str,
        trade_date: str,
        sign_convention: str,
        summary: dict[str, Any],
        pressure: dict[str, Any],
        dealer_inference: dict[str, Any],
        strike_profiles: list[dict[str, Any]],
        gamma_flip_history: dict[str, Any],
    ) -> dict[str, Any]:
        if not Config.OPTIONS_MODEL_DAILY_INSIGHTS_ENABLE:
            return self._fallback_payload(
                underlying_security=underlying_security,
                trade_date=trade_date,
                sign_convention=sign_convention,
                summary=summary,
                pressure=pressure,
                dealer_inference=dealer_inference,
                strike_profiles=strike_profiles,
                gamma_flip_history=gamma_flip_history,
                source="disabled",
            )

        cached = self.store.read_daily_insight(underlying_security, trade_date, sign_convention)
        if cached:
            return cached

        payload = self._generate_payload(
            underlying_security=underlying_security,
            trade_date=trade_date,
            sign_convention=sign_convention,
            summary=summary,
            pressure=pressure,
            dealer_inference=dealer_inference,
            strike_profiles=strike_profiles,
            gamma_flip_history=gamma_flip_history,
        )
        self.store.write_daily_insight(underlying_security, trade_date, sign_convention, payload)
        return payload

    def _generate_payload(self, **kwargs: Any) -> dict[str, Any]:
        try:
            return self._generate_with_llm(**kwargs)
        except Exception:
            logger.exception("Failed to generate options daily insights with LLM, using fallback")
            return self._fallback_payload(source="fallback", **kwargs)

    @staticmethod
    def _looks_non_portuguese(text: str) -> bool:
        sample = str(text or "").strip().lower()
        if not sample:
            return False
        hard_english_markers = [
            "today", "trading", "market appears", "traders should", "current spot",
            "suggests", "with a notable", "remain vigilant", "potential pinning range",
        ]
        portuguese_markers = [
            "mercado", "pressão", "opções", "futuro", "região", "fluxo", "hoje",
            "strike", "gamma", "delta", "dealer", "leitura", "risco", "spot",
        ]
        english_hits = sum(1 for item in hard_english_markers if item in sample)
        portuguese_hits = sum(1 for item in portuguese_markers if item in sample)
        return english_hits >= 2 or (english_hits >= 1 and portuguese_hits == 0)

    def _coerce_pt_br(self, payload: dict[str, Any]) -> dict[str, Any]:
        texts = [str(payload.get("overview") or "")]
        texts.extend(str((payload.get("cards") or {}).get(key) or "") for key in ("pressure", "dealer", "gamma_gex", "delta_dex", "open_interest", "vanna_cex"))
        if not any(self._looks_non_portuguese(text) for text in texts):
            return payload
        translated = self.llm.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Traduza e adapte o conteúdo para português do Brasil, em linguagem de mesa institucional. "
                        "Preserve exatamente as mesmas chaves do JSON de entrada: overview, cards.pressure, "
                        "cards.dealer, cards.gamma_gex, cards.delta_dex, cards.open_interest, cards.vanna_cex. "
                        "Mantenha o sentido, deixe o overview mais denso e não adicione chaves novas."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            temperature=0.1,
            max_tokens=1600,
        )
        return {
            "overview": str(translated.get("overview") or payload.get("overview") or "").strip(),
            "cards": {
                "pressure": str(((translated.get("cards") or {}).get("pressure")) or (payload.get("cards") or {}).get("pressure") or "").strip(),
                "dealer": str(((translated.get("cards") or {}).get("dealer")) or (payload.get("cards") or {}).get("dealer") or "").strip(),
                "gamma_gex": str(((translated.get("cards") or {}).get("gamma_gex")) or (payload.get("cards") or {}).get("gamma_gex") or "").strip(),
                "delta_dex": str(((translated.get("cards") or {}).get("delta_dex")) or (payload.get("cards") or {}).get("delta_dex") or "").strip(),
                "open_interest": str(((translated.get("cards") or {}).get("open_interest")) or (payload.get("cards") or {}).get("open_interest") or "").strip(),
                "vanna_cex": str(((translated.get("cards") or {}).get("vanna_cex")) or (payload.get("cards") or {}).get("vanna_cex") or "").strip(),
            },
        }

    def _generate_with_llm(
        self,
        *,
        underlying_security: str,
        trade_date: str,
        sign_convention: str,
        summary: dict[str, Any],
        pressure: dict[str, Any],
        dealer_inference: dict[str, Any],
        strike_profiles: list[dict[str, Any]],
        gamma_flip_history: dict[str, Any],
    ) -> dict[str, Any]:
        comparison = summary.get("dealer_inference_comparison") or dealer_inference.get("comparison") or {}
        top_strikes = sorted(
            strike_profiles,
            key=lambda item: abs(float(item.get("gex_net") or 0.0)) + abs(float(item.get("dex_net") or 0.0)),
            reverse=True,
        )[:8]
        latest_flip_points = gamma_flip_history.get("latest_flip_points") or []
        latest_flip_status = gamma_flip_history.get("latest_data_status")

        payload = {
            "underlying_security": underlying_security,
            "trade_date": trade_date,
            "sign_convention": sign_convention,
            "summary": {
                "spot_price": summary.get("spot_price"),
                "forward_price": summary.get("forward_price"),
                "future_basis_points": summary.get("future_basis_points"),
                "future_basis_pct": summary.get("future_basis_pct"),
                "dex_total": summary.get("dex_total"),
                "gex_total": summary.get("gex_total"),
                "vex_total": summary.get("vex_total"),
                "cex_total": summary.get("cex_total"),
                "zero_pressure": summary.get("zero_pressure"),
                "max_acceleration": summary.get("max_acceleration"),
                "dominant_side": summary.get("dominant_side"),
                "signal_confidence": summary.get("signal_confidence"),
            },
            "dealer_reference": {
                "reference_strike": comparison.get("reference_strike"),
                "reference_value": comparison.get("reference_dealer_inference_value"),
                "reference_confidence": comparison.get("reference_confidence"),
                "gex_center_of_mass": comparison.get("gex_center_of_mass"),
            },
            "pressure": {
                "pinning_band": pressure.get("pinning_band"),
                "acceleration_band": pressure.get("acceleration_band"),
                "decompression_band": pressure.get("decompression_band"),
            },
            "top_strikes": top_strikes,
            "latest_flip_points": latest_flip_points,
            "latest_flip_status": latest_flip_status,
        }

        result = self.llm.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "Você é um trader veterano de opções de índice no Brasil, em mesa institucional. "
                        "Escreva em português do Brasil, com linguagem de mesa, cética e operacional. "
                        "Não exagere convicção. Separe o que é observado do que é heurístico. "
                        "Retorne JSON com as chaves overview, pressure_card, dealer_card, gamma_gex_card, "
                        "delta_dex_card, open_interest_card, vanna_cex_card. "
                        "A chave overview deve ter um texto mais extenso e denso, entre 140 e 220 palavras, "
                        "sintetizando o panorama do dia, o basis spot-futuro, a região do dealer, o zero-pressure, "
                        "a máxima aceleração, OI, gamma flip e riscos táticos. "
                        "Cada card deve ter entre 55 e 95 palavras, em português do Brasil, com uma leitura prática."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(payload, ensure_ascii=False),
                },
            ],
            temperature=0.2,
            max_tokens=1400,
        )
        normalized: dict[str, Any] = {
            "trade_date": trade_date,
            "underlying_security": underlying_security,
            "sign_convention": sign_convention,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "llm",
            "overview": str(result.get("overview") or "").strip(),
            "cards": {
                "pressure": str(result.get("pressure_card") or "").strip(),
                "dealer": str(result.get("dealer_card") or "").strip(),
                "gamma_gex": str(result.get("gamma_gex_card") or "").strip(),
                "delta_dex": str(result.get("delta_dex_card") or "").strip(),
                "open_interest": str(result.get("open_interest_card") or "").strip(),
                "vanna_cex": str(result.get("vanna_cex_card") or "").strip(),
            },
            "input_digest": payload,
        }
        coerced = self._coerce_pt_br(normalized)
        normalized["overview"] = coerced.get("overview") or normalized["overview"]
        normalized["cards"] = coerced.get("cards") or normalized["cards"]
        if self._looks_non_portuguese(normalized["overview"]):
            raise ValueError("daily insights overview is not in pt-BR")
        return normalized

    def _fallback_payload(
        self,
        *,
        underlying_security: str,
        trade_date: str,
        sign_convention: str,
        summary: dict[str, Any],
        pressure: dict[str, Any],
        dealer_inference: dict[str, Any],
        strike_profiles: list[dict[str, Any]],
        gamma_flip_history: dict[str, Any],
        source: str,
    ) -> dict[str, Any]:
        comparison = summary.get("dealer_inference_comparison") or dealer_inference.get("comparison") or {}
        latest_flip_points = gamma_flip_history.get("latest_flip_points") or []
        latest_flip_status = gamma_flip_history.get("latest_data_status") or "unknown"
        basis = float(summary.get("future_basis_points") or 0.0)
        side = summary.get("dominant_side") or "neutral"
        top_gex = max(strike_profiles, key=lambda item: abs(float(item.get("gex_net") or 0.0)), default={})
        top_dex = max(strike_profiles, key=lambda item: abs(float(item.get("dex_net") or 0.0)), default={})
        top_oi = max(strike_profiles, key=lambda item: float(item.get("open_interest_total") or 0.0), default={})

        flip_text = (
            f"Latest estimated gamma flip sits near {int(latest_flip_points[0])} and is marked {latest_flip_status}."
            if latest_flip_points
            else "No strong gamma flip level was estimated from the available OI history window."
        )
        return {
            "trade_date": trade_date,
            "underlying_security": underlying_security,
            "sign_convention": sign_convention,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "overview": (
                f"A leitura diária de {underlying_security} mostra uma estrutura de pressão {side}, com zero-pressure "
                f"perto de {int(float(summary.get('zero_pressure') or 0.0))} e máxima aceleração perto de "
                f"{int(float(summary.get('max_acceleration') or 0.0))}. O basis entre spot e futuro está em {basis:+.0f} pontos, "
                "então qualquer execução precisa ser lida pelo contrato ativo e não apenas pelo IBOV à vista. "
                f"{flip_text} O ponto principal aqui é separar o que é estrutura de hedge do que é apenas ruído intraday: "
                "strikes com OI relevante, gamma concentrado e pressão coerente com a curva HP(S) tendem a importar mais. "
                "Vanna e charm entram como aceleradores secundários, úteis para timing e sensibilidade de vol, mas ainda subordinados "
                "ao mapa principal por spot. A utilidade prática dessa leitura é reduzir a chance de operar um strike 'bonito' que não "
                "tem peso real no book do dia."
            ),
            "cards": {
                "pressure": (
                    f"O HP(S) está inclinado para {side}. Como o basis spot-futuro está em {basis:+.0f} pontos, "
                    "a leitura operacional precisa passar pelo futuro ativo. Se o mercado caminhar perto do zero-pressure, "
                    "a tendência é de menor urgência marginal de hedge; longe dele, a resposta tende a ficar mais sensível."
                ),
                "dealer": (
                    f"A camada auxiliar de dealer inference está ancorada no strike "
                    f"{int(float(comparison.get('reference_strike') or 0.0))}, com valor deslocado perto de "
                    f"{int(float(comparison.get('reference_dealer_inference_value') or 0.0))}. Ela ajuda no ajuste tático, "
                    "mas não substitui a curva principal por spot."
                ),
                "gamma_gex": (
                    f"A maior concentração de gamma/GEX está perto do strike {int(float(top_gex.get('strike') or 0.0))}. "
                    "Esse é o primeiro ponto para monitorar pressão de convexidade. Se o spot encostar nessa região com fluxo, "
                    "o ajuste tende a ficar mais rápido e mais visível no futuro."
                ),
                "delta_dex": (
                    f"A concentração de delta/DEX está mais forte perto do strike {int(float(top_dex.get('strike') or 0.0))}. "
                    "Isso costuma ser a área em que a necessidade de hedge direcional reage primeiro, especialmente quando "
                    "o basis e o book do futuro confirmam o movimento."
                ),
                "open_interest": (
                    f"O open interest está mais concentrado no strike {int(float(top_oi.get('strike') or 0.0))}. "
                    "Esse strike passa a importar mais no intraday quando também coincide com pressão de gamma, delta "
                    "ou com reação do futuro nas proximidades."
                ),
                "vanna_cex": (
                    "Vanna e charm devem ser lidos como aceleradores secundários. Eles ajudam no timing, na leitura de "
                    "decaimento e na sensibilidade a variações de vol, mas continuam subordinados à curva principal de pressão."
                ),
            },
            "input_digest": {
                "summary": summary,
                "dealer_reference": comparison,
                "latest_flip_points": latest_flip_points,
                "latest_flip_status": latest_flip_status,
            },
        }
