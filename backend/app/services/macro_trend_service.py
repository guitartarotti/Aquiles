from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from ..models.project import ProjectManager
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .macro_live_service import MacroIngestionService, MacroStateStore
from .macro_persona_service import MacroPersonaService

logger = get_logger("aquiles.macro_trends")


class MacroTrendService:
    """Build trend candidates from the live macro snapshot and focus them for agent debate."""

    def __init__(
        self,
        store: Optional[MacroStateStore] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.store = store or MacroStateStore()
        self.ingestion = MacroIngestionService(store=self.store)
        self.personas = MacroPersonaService()
        self._llm_client = llm_client

    @property
    def llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def list_trends(
        self,
        limit: int = 8,
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        state = self.store.read_state()
        snapshot = state.get("snapshot", {}) or {}
        trends = self._build_trends(snapshot)
        resolved_graph_id = self._resolve_graph_id(project_id=project_id, graph_id=graph_id)

        return {
            "generated_at": snapshot.get("generated_at"),
            "count": len(trends),
            "graph_ready": bool(resolved_graph_id),
            "trends": trends[: max(1, limit)],
        }

    def focus_trend(
        self,
        trend_id: str,
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
        comment_count: int = 6,
    ) -> Dict[str, Any]:
        if not trend_id:
            raise ValueError("trend_id is required")

        state = self.store.read_state()
        snapshot = state.get("snapshot", {}) or {}
        trends = self._build_trends(snapshot)
        trend = next((item for item in trends if item.get("trend_id") == trend_id), None)
        if not trend:
            raise ValueError(f"Trend not found: {trend_id}")

        resolved_graph_id = self._resolve_graph_id(project_id=project_id, graph_id=graph_id)
        selected_agents = self._select_relevant_agents(
            trend=trend,
            graph_id=resolved_graph_id,
            count=max(3, min(int(comment_count or 6), 8)),
        )
        focus_pack = self._generate_focus_pack(trend=trend, selected_agents=selected_agents)

        return {
            "generated_at": snapshot.get("generated_at"),
            "trend": trend,
            "selected_agents": selected_agents,
            "agent_comments": focus_pack.get("agent_comments", []),
            "ai_summary": focus_pack.get("ai_summary", {}),
        }

    def _build_trends(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        market = snapshot.get("market", {}) or {}
        contracts = market.get("contracts", {}) or {}
        news_items = (snapshot.get("news", {}) or {}).get("items", []) or []
        contract_signals = {
            ticker: self.ingestion._build_contract_signal(ticker, contract)
            for ticker, contract in contracts.items()
        }
        top_mover_tickers: set[str] = {
            str(item.get("ticker"))
            for item in sorted(
                contract_signals.values(),
                key=lambda row: abs(row.get("net_change_pct_5m") or 0.0),
                reverse=True,
            )[:5]
            if item.get("ticker")
        }

        trends: List[Dict[str, Any]] = []
        seen_ids = set()

        for event in news_items:
            trend = self._build_news_trend(event, contract_signals, contracts)
            if trend and trend["trend_id"] not in seen_ids:
                trends.append(trend)
                seen_ids.add(trend["trend_id"])

        for ticker in top_mover_tickers:
            signal = contract_signals.get(ticker, {})
            contract = contracts.get(ticker, {})
            trend = self._build_market_trend(ticker, contract, signal)
            if trend and trend["trend_id"] not in seen_ids:
                trends.append(trend)
                seen_ids.add(trend["trend_id"])

        trends.sort(
            key=lambda item: (
                int(item.get("importance_score") or 0),
                abs(item.get("net_change_pct_5m") or 0.0),
            ),
            reverse=True,
        )
        return trends

    def _build_news_trend(
        self,
        event: Dict[str, Any],
        contract_signals: Dict[str, Dict[str, Any]],
        contracts: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        linked_contracts = list(dict.fromkeys(event.get("linked_contracts") or []))
        linked_securities = list(dict.fromkeys(event.get("linked_securities") or []))
        linked_buckets = list(dict.fromkeys(event.get("linked_buckets") or []))
        themes = list(dict.fromkeys(event.get("themes") or []))
        impact_score = int(event.get("impact_score") or 0)
        market_relevance = bool(event.get("market_relevance"))
        technical_operation = bool(event.get("technical_operation"))

        if not (
            linked_contracts
            or linked_securities
            or linked_buckets
            or market_relevance
            or impact_score >= 4
        ):
            return None

        primary_contract = linked_contracts[0] if linked_contracts else None
        primary_signal = contract_signals.get(primary_contract or "", {})
        direction = primary_signal.get("direction_5m") or "watch"
        probable_bias = "watch" if technical_operation else self._direction_to_bias(direction)
        net_change_pct = primary_signal.get("net_change_pct_5m")
        participant_summary = ((contracts.get(primary_contract or "", {}) or {}).get("participants") or {}).get("summary", {})
        top_5_share = self._to_float(participant_summary.get("top_5_share_percentage"))

        if technical_operation:
            importance_score = min(
                6,
                impact_score * 2 + int(abs(net_change_pct or 0.0) * 20) + int((top_5_share or 0.0) / 20),
            )
        else:
            importance_score = min(
                100,
                impact_score * 12
                + int(abs(net_change_pct or 0.0) * 220)
                + int(top_5_share or 0.0),
            )

        theme_text = ", ".join(themes) if themes else "macro flow"
        asset_text = ", ".join(linked_contracts[:2] + linked_securities[:2]) or "cross-asset basket"
        headline = str(event.get("headline") or "Macro event")
        title = headline if len(headline) <= 96 else f"{headline[:93]}..."
        summary = (
            f"Headline-driven setup around {asset_text}. "
            f"The system flagged this as {event.get('relevance') or 'market'} news, "
            f"with themes around {theme_text} and a probable bias of {probable_bias}."
        )
        if technical_operation:
            summary = (
                f"Technical liquidity headline around {asset_text}. "
                "This should stay low-conviction unless price, flow and cross-asset confirmation broaden meaningfully."
            )

        signal_evidence = []
        if primary_contract:
            signal_evidence.append(f"{primary_contract} direction_5m={direction}")
        if net_change_pct is not None:
            signal_evidence.append(f"net_change_pct_5m={round(net_change_pct, 4)}")
        if top_5_share is not None:
            signal_evidence.append(f"top_5_share={round(top_5_share, 2)}%")

        trend_id = self._trend_id(
            "news",
            headline,
            json.dumps(linked_contracts + linked_securities + linked_buckets, ensure_ascii=False),
        )

        return {
            "trend_id": trend_id,
            "kind": "news_driver",
            "title": title,
            "headline": headline,
            "summary": summary,
            "primary_asset": primary_contract or (linked_securities[0] if linked_securities else None),
            "focus_contracts": linked_contracts,
            "focus_securities": linked_securities,
            "focus_buckets": linked_buckets,
            "themes": themes,
            "probable_bias": probable_bias,
            "confidence": min(30, 12 + impact_score * 4) if technical_operation else min(95, 48 + impact_score * 8 + (10 if market_relevance else 0)),
            "importance_score": importance_score,
            "importance_label": self._importance_label(importance_score),
            "impact_score": impact_score,
            "technical_operation": technical_operation,
            "direction_5m": direction,
            "net_change_pct_5m": net_change_pct,
            "top_5_share_percentage": top_5_share,
            "signal_evidence": signal_evidence,
            "reasoning": [
                f"News relevance={event.get('relevance') or 'unknown'} impact_score={impact_score}",
                f"Detected assets: {asset_text}",
                f"Link reasons: {', '.join(event.get('link_reasons') or []) or 'explicit market relevance'}",
                "Treat as low-conviction technical news." if technical_operation else "Requires price and flow confirmation.",
            ],
        }

    def _build_market_trend(
        self,
        ticker: str,
        contract: Dict[str, Any],
        signal: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        latest_window = ((contract.get("ohlcv") or {}).get("latest_window")) or {}
        participant_summary = ((contract.get("participants") or {}).get("summary")) or {}
        top_5_share = self._to_float(participant_summary.get("top_5_share_percentage"))
        net_change_pct = self._to_float(latest_window.get("net_change_pct"))
        book_imbalance = self._to_float(((contract.get("book") or {}).get("summary") or {}).get("imbalance"))
        direction = latest_window.get("direction") or signal.get("direction_5m") or "watch"

        if net_change_pct is None:
            return None

        interesting = (
            abs(net_change_pct) >= 0.03
            or (top_5_share or 0.0) >= 48.0
            or abs(book_imbalance or 0.0) >= 0.35
        )
        if not interesting:
            return None

        probable_bias = self._direction_to_bias(direction)
        importance_score = min(
            100,
            int(abs(net_change_pct) * 500) + int(top_5_share or 0.0) + int(abs(book_imbalance or 0.0) * 25),
        )
        top_participants = signal.get("top_participants", [])[:3]
        participant_names = [
            row.get("broker_name") for row in top_participants if row.get("broker_name")
        ]

        title = f"{ticker} {direction} move with flow concentration in the latest 5-minute window"
        summary = (
            f"{ticker} is moving {direction} in the last 5-minute bucket. "
            f"Participant concentration and book shape suggest a live tradable discussion for this contract."
        )
        trend_id = self._trend_id("market", ticker, latest_window.get("window_start"), latest_window.get("window_end"))

        return {
            "trend_id": trend_id,
            "kind": "market_move",
            "title": title,
            "headline": None,
            "summary": summary,
            "primary_asset": ticker,
            "focus_contracts": [ticker],
            "focus_securities": [],
            "focus_buckets": [contract.get("bucket")] if contract.get("bucket") else [],
            "themes": [contract.get("bucket")] if contract.get("bucket") else [],
            "probable_bias": probable_bias,
            "confidence": min(90, 42 + int(abs(net_change_pct) * 380)),
            "importance_score": importance_score,
            "importance_label": self._importance_label(importance_score),
            "impact_score": int(abs(net_change_pct) * 100),
            "direction_5m": direction,
            "net_change_pct_5m": net_change_pct,
            "top_5_share_percentage": top_5_share,
            "signal_evidence": [
                f"window={latest_window.get('window_start')}->{latest_window.get('window_end')}",
                f"net_change_pct_5m={round(net_change_pct, 4)}",
                f"top_5_share={round(top_5_share or 0.0, 2)}%",
                f"book_imbalance={round(book_imbalance or 0.0, 4)}",
            ],
            "reasoning": [
                f"Top participants: {', '.join(participant_names) or 'no concentration read'}",
                f"Volume={latest_window.get('volume') or signal.get('volume_5m') or 'n/a'}",
                "No sufficiently impactful linked news was required for this price-action trend.",
            ],
        }

    def _select_relevant_agents(
        self,
        trend: Dict[str, Any],
        graph_id: Optional[str],
        count: int,
    ) -> List[Dict[str, Any]]:
        if not graph_id:
            return []

        try:
            filtered = self.personas.build_filtered_entities(graph_id=graph_id, enrich_with_edges=True)
        except Exception as exc:
            logger.warning(f"Failed to load macro personas for trend focus: {exc}")
            return []

        scored: List[Dict[str, Any]] = []
        trend_terms = {
            *[str(item).upper() for item in trend.get("focus_contracts", [])],
            *[str(item).upper() for item in trend.get("focus_securities", [])],
            *[str(item).upper().replace("_", " ") for item in trend.get("themes", [])],
            *[str(item).upper().replace("_", " ") for item in trend.get("focus_buckets", [])],
        }
        for entity in filtered.entities:
            attrs = entity.attributes or {}
            score = 0
            score += self._match_terms(trend_terms, attrs.get("contract_focus", []), 8)
            score += self._match_terms(trend_terms, attrs.get("security_focus", []), 6)
            score += self._match_terms(trend_terms, attrs.get("theme_focus", []), 5)
            score += self._match_terms(trend_terms, attrs.get("watch_signals", []), 4)
            summary_text = f"{entity.summary} {json.dumps(attrs, ensure_ascii=False)}".upper()
            score += sum(1 for term in trend_terms if term and term in summary_text)
            if trend.get("kind") == "market_move" and "flow" in summary_text.lower():
                score += 3
            if score <= 0:
                continue

            scored.append(
                {
                    "entity": entity,
                    "score": score,
                    "entity_type": entity.get_entity_type() or "MacroPersona",
                }
            )

        scored.sort(key=lambda item: int(item["score"]), reverse=True)

        selected: List[Dict[str, Any]] = []
        used_types = set()
        for item in scored:
            entity = item["entity"]
            entity_type = item["entity_type"]
            if entity_type in used_types and len(selected) < min(count, 4):
                continue
            used_types.add(entity_type)
            selected.append(self._persona_snapshot(entity, item["score"]))
            if len(selected) >= count:
                break

        if len(selected) < count:
            existing_ids = {item["agent_uuid"] for item in selected}
            for item in scored:
                entity = item["entity"]
                if entity.uuid in existing_ids:
                    continue
                selected.append(self._persona_snapshot(entity, item["score"]))
                if len(selected) >= count:
                    break

        return selected

    def _generate_focus_pack(
        self,
        trend: Dict[str, Any],
        selected_agents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not selected_agents:
            return self._fallback_focus_pack(trend, selected_agents)

        try:
            result = self.llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Voce e um trader macro brasileiro muito experiente, de mesa institucional. "
                            "Analise a trend e devolva JSON puro com comentarios de agentes e um resumo executivo final. "
                            "Os comentarios devem divergir entre si quando fizer sentido, mas todos devem usar os sinais fornecidos. "
                            "Nao trate headlines operacionais ou de liquidez rotineira como mudancas grandes de regime sem confirmacao ampla."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Trend em foco:\n"
                            f"{json.dumps(trend, ensure_ascii=False, indent=2)}\n\n"
                            "Agentes disponiveis:\n"
                            f"{json.dumps(selected_agents, ensure_ascii=False, indent=2)}\n\n"
                            "Retorne JSON neste formato:\n"
                            "{\n"
                            '  "agent_comments": [\n'
                            "    {\n"
                            '      "agent_uuid": "...",\n'
                            '      "agent_name": "...",\n'
                            '      "bias": "buy|sell|watch",\n'
                            '      "confidence": 0,\n'
                            '      "comment": "...",\n'
                            '      "reason": "..."\n'
                            "    }\n"
                            "  ],\n"
                            '  "ai_summary": {\n'
                            '    "probable_scenario": "...",\n'
                            '    "bias": "buy|sell|watch",\n'
                            '    "confidence": 0,\n'
                            '    "why": ["...", "..."],\n'
                            '    "risks": ["...", "..."],\n'
                            '    "what_to_monitor": ["...", "..."],\n'
                            '    "recommended_focus": "..."\n'
                            "  }\n"
                            "}"
                        ),
                    },
                ],
                temperature=0.35,
                max_tokens=2200,
            )

            comments = result.get("agent_comments") or []
            ai_summary = result.get("ai_summary") or {}

            agent_map = {agent["agent_uuid"]: agent for agent in selected_agents}
            normalized_comments = []
            for item in comments:
                agent_uuid = item.get("agent_uuid")
                base = agent_map.get(agent_uuid, {})
                normalized_comments.append(
                    {
                        "agent_uuid": agent_uuid or base.get("agent_uuid"),
                        "agent_name": item.get("agent_name") or base.get("agent_name"),
                        "entity_type": base.get("entity_type"),
                        "institution": base.get("institution"),
                        "bias": self._normalize_bias(item.get("bias") or trend.get("probable_bias")),
                        "confidence": self._normalize_confidence(
                            item.get("confidence"),
                            fallback=trend.get("confidence"),
                            minimum=35,
                        ),
                        "comment": item.get("comment") or "",
                        "reason": item.get("reason") or "",
                    }
                )

            if not normalized_comments:
                return self._fallback_focus_pack(trend, selected_agents)

            fallback_pack = self._fallback_focus_pack(trend, selected_agents)
            fallback_comments = {
                comment.get("agent_uuid"): comment
                for comment in fallback_pack.get("agent_comments", [])
                if comment.get("agent_uuid")
            }
            seen_comment_ids = {
                comment.get("agent_uuid")
                for comment in normalized_comments
                if comment.get("agent_uuid")
            }
            for agent in selected_agents:
                agent_uuid = agent.get("agent_uuid")
                if not agent_uuid or agent_uuid in seen_comment_ids:
                    continue
                fallback_comment = fallback_comments.get(agent_uuid)
                if fallback_comment:
                    normalized_comments.append(fallback_comment)

            return {
                "agent_comments": normalized_comments[: len(selected_agents)],
                "ai_summary": {
                    "probable_scenario": ai_summary.get("probable_scenario") or trend.get("summary"),
                    "bias": self._normalize_bias(ai_summary.get("bias") or trend.get("probable_bias")),
                    "confidence": self._normalize_confidence(
                        ai_summary.get("confidence"),
                        fallback=trend.get("confidence"),
                        minimum=40,
                    ),
                    "why": ai_summary.get("why") or trend.get("reasoning", [])[:2],
                    "risks": ai_summary.get("risks") or ["Reversal if the next 5-minute window contradicts the current move."],
                    "what_to_monitor": ai_summary.get("what_to_monitor") or trend.get("signal_evidence", [])[:3],
                    "recommended_action": self._normalize_bias(
                        ai_summary.get("recommended_action")
                        or ai_summary.get("bias")
                        or trend.get("probable_bias")
                    ),
                    "recommended_focus": ai_summary.get("recommended_focus") or "Monitor whether price action and participant flow remain aligned.",
                },
            }
        except Exception as exc:
            logger.warning(f"LLM trend focus generation failed, using fallback: {exc}")
            return self._fallback_focus_pack(trend, selected_agents)

    def _fallback_focus_pack(
        self,
        trend: Dict[str, Any],
        selected_agents: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        comments = []
        bias = self._normalize_bias(trend.get("probable_bias"))
        for agent in selected_agents:
            comments.append(
                {
                    "agent_uuid": agent.get("agent_uuid"),
                    "agent_name": agent.get("agent_name"),
                    "entity_type": agent.get("entity_type"),
                    "institution": agent.get("institution"),
                    "bias": bias,
                    "confidence": self._normalize_confidence(
                        trend.get("confidence"),
                        fallback=60,
                        minimum=45,
                    ),
                    "comment": (
                        f"{agent.get('agent_name')} enxerga {trend.get('title')} como uma discussao de {bias}. "
                        f"O foco recai sobre {', '.join(trend.get('focus_contracts') or trend.get('focus_securities') or ['mercado'])}."
                    ),
                    "reason": (
                        f"Sinais usados: {', '.join(trend.get('signal_evidence') or []) or 'news, flow and 5-minute move'}."
                    ),
                }
            )

        return {
            "agent_comments": comments,
            "ai_summary": {
                "probable_scenario": trend.get("summary"),
                "bias": bias,
                "confidence": self._normalize_confidence(
                    trend.get("confidence"),
                    fallback=60,
                    minimum=45,
                ),
                "why": trend.get("reasoning", [])[:3],
                "risks": [
                    "The next 5-minute window may reverse the current direction.",
                    "Participant concentration may fade quickly if the news impulse disappears.",
                ],
                "what_to_monitor": trend.get("signal_evidence", [])[:4],
                "recommended_action": bias,
                "recommended_focus": (
                    "Stay with the trade only if news, 5-minute move, and participant concentration continue to point in the same direction."
                ),
            },
        }

    def _persona_snapshot(self, entity: Any, score: int) -> Dict[str, Any]:
        attrs = entity.attributes or {}
        return {
            "agent_uuid": entity.uuid,
            "agent_name": entity.name,
            "entity_type": entity.get_entity_type() or "MacroPersona",
            "institution": attrs.get("institution"),
            "profession": attrs.get("profession"),
            "strategy": attrs.get("strategy"),
            "watch_signals": attrs.get("watch_signals", []),
            "contract_focus": attrs.get("contract_focus", []),
            "security_focus": attrs.get("security_focus", []),
            "theme_focus": attrs.get("theme_focus", []),
            "summary": entity.summary,
            "score": score,
        }

    def _resolve_graph_id(self, project_id: Optional[str], graph_id: Optional[str]) -> Optional[str]:
        if graph_id:
            return graph_id
        if project_id:
            project = ProjectManager.get_project(project_id)
            if project:
                return project.graph_id
        return None

    def _importance_label(self, score: int) -> str:
        if score >= 75:
            return "high"
        if score >= 50:
            return "medium"
        return "low"

    def _direction_to_bias(self, direction: Optional[str]) -> str:
        value = (direction or "").strip().lower()
        if value == "up":
            return "buy"
        if value == "down":
            return "sell"
        return "watch"

    def _normalize_bias(self, bias: Optional[str]) -> str:
        value = (bias or "").strip().lower()
        if value in {"buy", "sell", "watch"}:
            return value
        return "watch"

    def _normalize_confidence(self, value: Any, fallback: Any, minimum: int = 0) -> int:
        candidate = value if value not in (None, "") else fallback
        try:
            normalized = int(float(candidate))
        except (TypeError, ValueError):
            normalized = int(fallback or minimum or 0)
        normalized = max(minimum, normalized)
        return min(normalized, 100)

    def _trend_id(self, *parts: Any) -> str:
        text = "::".join(str(part or "") for part in parts)
        return f"trend_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}"

    def _match_terms(self, trend_terms: set[str], values: List[Any], weight: int) -> int:
        score = 0
        upper_values = [str(value).upper() for value in values]
        for term in trend_terms:
            if not term:
                continue
            if any(term in value or value in term for value in upper_values):
                score += weight
        return score

    def _to_float(self, value: Any) -> Optional[float]:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
