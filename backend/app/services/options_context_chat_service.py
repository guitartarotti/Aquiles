from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..config import Config
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .options_store import OptionsStore

logger = get_logger("aquiles.options_context_chat")


class OptionsContextChatService:
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

    def get_thread(
        self,
        *,
        underlying_security: str,
        sign_convention: str = "neutral",
        trade_date: str | None = None,
    ) -> dict[str, Any]:
        model_run = self.store.read_latest_model_run(underlying_security) or {}
        effective_trade_date = str(trade_date or model_run.get("session_date") or datetime.now(timezone.utc).date().isoformat())[:10]
        thread = self.store.read_chat_thread(underlying_security, effective_trade_date, sign_convention)
        if thread:
            return thread
        return {
            "underlying_security": underlying_security,
            "trade_date": effective_trade_date,
            "sign_convention": sign_convention,
            "updated_at": None,
            "messages": [],
        }

    def send_message(
        self,
        *,
        underlying_security: str,
        message: str,
        sign_convention: str = "neutral",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        user_text = str(message or "").strip()
        if not user_text:
            raise ValueError("message is required")

        model_run = self.store.read_model_run(run_id) if run_id else None
        if not model_run:
            model_run = self.store.read_latest_model_run(underlying_security)
        if not model_run:
            raise ValueError(f"No options model run was found for {underlying_security}")

        trade_date = str(model_run.get("session_date") or datetime.now(timezone.utc).date().isoformat())[:10]
        thread = self.get_thread(
            underlying_security=underlying_security,
            sign_convention=sign_convention,
            trade_date=trade_date,
        )

        conversation = list(thread.get("messages") or [])
        user_entry = {
            "role": "user",
            "content": user_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        conversation.append(user_entry)

        response_text = self._answer_from_context(
            model_run=model_run,
            conversation=conversation,
            sign_convention=sign_convention,
        )

        assistant_entry = {
            "role": "assistant",
            "content": response_text,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        conversation.append(assistant_entry)
        max_messages = max(int(getattr(Config, "OPTIONS_CHAT_MAX_MESSAGES", 30)), 6)
        if len(conversation) > max_messages:
            conversation = conversation[-max_messages:]

        payload = {
            "underlying_security": underlying_security,
            "trade_date": trade_date,
            "sign_convention": sign_convention,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": model_run.get("run_id"),
            "messages": conversation,
        }
        self.store.write_chat_thread(underlying_security, trade_date, sign_convention, payload)
        return payload

    def _answer_from_context(
        self,
        *,
        model_run: dict[str, Any],
        conversation: list[dict[str, Any]],
        sign_convention: str,
    ) -> str:
        summary = model_run.get("summary") or {}
        pressure = model_run.get("pressure") or {}
        dealer_inference = model_run.get("dealer_inference") or {}
        daily_insights = model_run.get("daily_insights") or {}
        range_projection = model_run.get("range_projection") or {}
        strike_profiles = model_run.get("strike_profiles") or []
        gamma_flip_history = model_run.get("gamma_flip_history") or {}

        top_strikes = sorted(
            strike_profiles,
            key=lambda row: abs(float(row.get("gex_net") or 0.0)) + abs(float(row.get("dex_net") or 0.0)),
            reverse=True,
        )[:10]

        context_payload = {
            "underlying_security": model_run.get("underlying_security"),
            "trade_date": model_run.get("session_date"),
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
                "center_of_mass": summary.get("center_of_mass"),
                "pinning_band": summary.get("pinning_band"),
                "acceleration_band": summary.get("acceleration_band"),
                "dominant_side": summary.get("dominant_side"),
                "win_delta_equivalent": summary.get("win_delta_equivalent"),
            },
            "dealer_inference_comparison": dealer_inference.get("comparison") or {},
            "range_projection": {
                "center": range_projection.get("center") or {},
                "bands": (range_projection.get("bands") or [])[:6],
                "methodology": range_projection.get("methodology"),
            },
            "top_strikes": top_strikes,
            "gamma_flip_history": {
                "methodology": gamma_flip_history.get("methodology"),
                "latest_trade_date": gamma_flip_history.get("latest_trade_date"),
                "latest_flip_points": gamma_flip_history.get("latest_flip_points"),
                "latest_data_status": gamma_flip_history.get("latest_data_status"),
                "historical_regime_flips": gamma_flip_history.get("historical_regime_flips") or [],
                "recent_dates": (gamma_flip_history.get("dates") or [])[-4:],
            },
            "daily_insights": daily_insights,
            "pressure": {
                "zero_pressure": pressure.get("zero_pressure"),
                "max_acceleration": pressure.get("max_acceleration"),
                "dominant_side": pressure.get("dominant_side"),
            },
        }

        history_messages = [
            {"role": item.get("role") or "user", "content": str(item.get("content") or "")}
            for item in conversation[-12:]
            if str(item.get("content") or "").strip()
        ]

        system_prompt = (
            "Você é um trader sênior de opções de índice no Brasil, falando em português do Brasil. "
            "Responda de forma analítica, prática e honesta. Separe o que é observado do que é heurístico. "
            "Use o contexto do model run atual para responder dúvidas sobre dealer positioning, gamma, delta, "
            "vanna, charm, zero-pressure, max acceleration, basis entre spot e futuro, open interest e gamma flips. "
            "Quando o usuário perguntar algo que o modelo não observa diretamente, deixe isso explícito. "
            "Não invente números fora do contexto fornecido."
        )

        user_prompt = (
            "Contexto do dia e do model run:\n"
            f"{json.dumps(context_payload, ensure_ascii=False)}\n\n"
            "Histórico recente da conversa:\n"
            f"{json.dumps(history_messages, ensure_ascii=False)}\n\n"
            "Responda à última mensagem do usuário em português do Brasil."
        )

        try:
            response = self.llm.chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.25,
                max_tokens=1400,
            ).strip()
            if self._looks_non_portuguese(response):
                response = self.llm.chat(
                    [
                        {
                            "role": "system",
                            "content": "Reescreva a resposta abaixo em português do Brasil, mantendo o conteúdo e o tom de mesa institucional.",
                        },
                        {"role": "user", "content": response},
                    ],
                    temperature=0.1,
                    max_tokens=1400,
                ).strip()
            return response
        except Exception:
            logger.exception("Options context chat failed, using fallback answer")
            latest = context_payload["summary"]
            return (
                "Não consegui consultar a IA agora, então vou responder com o contexto salvo. "
                f"O spot está perto de {latest.get('spot_price')}, o zero-pressure em {latest.get('zero_pressure')} "
                f"e a máxima aceleração em {latest.get('max_acceleration')}. "
                "Se você quiser, pode repetir a pergunta e eu tento de novo com a camada de IA."
            )

    @staticmethod
    def _looks_non_portuguese(text: str) -> bool:
        sample = str(text or "").strip().lower()
        if not sample:
            return False
        english_markers = ["today", "market", "options", "pressure", "dealer", "current", "spot", "should"]
        portuguese_markers = ["mercado", "opções", "pressão", "dealer", "spot", "hoje", "região", "futuro"]
        english_hits = sum(1 for item in english_markers if item in sample)
        portuguese_hits = sum(1 for item in portuguese_markers if item in sample)
        return english_hits >= 3 and portuguese_hits <= 1
