from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from html import unescape
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from ..config import Config
from ..utils.atomic_io import atomic_json_dump
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .macro_context_tokenizer import aggregate_macro_event_tokens, build_driver_llm_context_packet
from .macro_live_service import MacroIngestionService, MacroStateStore

logger = get_logger("mirofish.macro_drivers")

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
STOPWORDS = {
    "de", "da", "do", "das", "dos", "para", "com", "sem", "sobre", "entre",
    "uma", "um", "uns", "umas", "that", "this", "from", "into", "after",
    "antes", "apos", "após", "pela", "pelo", "nos", "nas", "the", "and",
    "por", "em", "na", "no", "ao", "as", "os", "que", "mais", "less",
}
THEME_GROUP_WINDOWS_SECONDS = {
    "ormuz_blockade": 12 * 60 * 60,
    "iran_negotiation": 90 * 60,
    "iran_negotiation_setback": 2 * 60 * 60,
}
THEME_DRIVER_TITLES = {
    "ormuz_blockade": "Ormuz Blockade / Oil Shock",
    "iran_negotiation": "Iran Talks / Risk Relief",
    "iran_negotiation_setback": "Iran Talks / Hardliner Setback",
}
THEME_DRIVER_EXPLANATIONS = {
    "ormuz_blockade": (
        "This driver groups the Ormuz blockade narrative, naval enforcement headlines, "
        "oil shock follow-through, and the related FX / equity / long-end rates reaction."
    ),
    "iran_negotiation": (
        "This driver groups negotiation, dialogue and agreement-progress headlines around "
        "the US-Iran channel, together with the associated risk-relief move in equities, FX and long-end rates."
    ),
    "iran_negotiation_setback": (
        "This driver groups negotiation setbacks, hardliner pressure, moderate-exit headlines and successor uncertainty "
        "around the US-Iran channel, together with the associated risk-off move in equities, FX and long-end rates."
    ),
}
PERSISTED_CROSS_ASSET_VERSION = "cross-asset-driver-v4"
DRIVER_STATE_VERSION = "macro-driver-board-v15-contextual-memory"
DRIVER_ANALYSIS_VERSION = "macro-driver-analysis-v12-contextual-memory"
ELASTICITY_REFERENCE_MOVE_PCT = {
    "win": 0.22,
    "wdo": 0.18,
    "di": 0.03,
}
EXPECTED_IMPACT_BANDS = (
    (75, "regime_shift"),
    (40, "tradable_catalyst"),
    (12, "secondary_echo"),
    (0, "technical_noise"),
)
SESSION_RISK_THEMES = {"ormuz_blockade", "iran_negotiation", "iran_negotiation_setback"}
DIRECTIONAL_MACRO_TERMS = {
    "iran", "irã", "ormuz", "hormuz", "blockade", "bloqueio", "shipping", "tanker",
    "oil", "brent", "energia", "energy", "ceasefire", "cessar-fogo",
    "risk-on", "risk on", "bce", "ecb", "boj",
    "bank of japan", "alta de juros", "aumento de juros", "queda de juros",
    "corte de juros", "rates", "juros",
}


class MacroDriverService:
    """Creates persistent impact drivers from live news and market context."""

    def __init__(
        self,
        store: Optional[MacroStateStore] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.store = store or MacroStateStore()
        self.ingestion = MacroIngestionService(store=self.store)
        self._llm_client = llm_client
        self.drivers_path = os.path.join(self.store.root_dir, "drivers_state.json")

    @property
    def llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def list_drivers(self, limit: int = 12, refresh: bool = True) -> Dict[str, Any]:
        state = self.refresh_drivers() if refresh else self._load_state(refresh_if_stale=False)
        drivers = state.get("drivers", []) or []
        news_feed = state.get("news_feed", []) or []
        return {
            "generated_at": state.get("generated_at"),
            "driver_count": len(drivers),
            "news_count": len(news_feed),
            "drivers": drivers[: max(1, limit)],
            "news_feed": news_feed,
        }

    def focus_driver(self, driver_id: str, refresh: bool = False) -> Dict[str, Any]:
        if not driver_id:
            raise ValueError("driver_id is required")

        state = self.refresh_drivers() if refresh else self._load_state(refresh_if_stale=False)
        drivers = state.get("drivers", []) or []
        driver = next((item for item in drivers if item.get("driver_id") == driver_id), None)
        if not driver:
            raise ValueError(f"Driver not found: {driver_id}")

        return {
            "generated_at": state.get("generated_at"),
            "driver": driver,
            "related_drivers": [
                item for item in drivers
                if item.get("driver_id") in (driver.get("related_driver_ids") or [])
            ][:4],
        }

    def refresh_drivers(self) -> Dict[str, Any]:
        previous_state = self._read_saved_state()
        previous_drivers = {
            item.get("driver_id"): item
            for item in (previous_state.get("drivers", []) or [])
            if item.get("driver_id")
        }
        prior_day_drivers = list(previous_drivers.values())
        macro_state = self.store.read_state()
        snapshot = macro_state.get("snapshot", {}) or {}
        active_day_events = self._load_active_day_events(macro_state)
        recent_events = self._reclassify_recent_events(
            active_day_events,
            snapshot=snapshot,
            persist=False,
        )
        snapshot_history = self.store.list_snapshot_history(limit=80)

        candidate_events = self._candidate_events(recent_events)
        groups = self._group_events(candidate_events)
        groups.sort(
            key=lambda item: self._sort_timestamp(
                ((item.get("events") or [{}])[0]).get("event_time")
            )
        )
        drivers: List[Dict[str, Any]] = []
        for group in groups:
            driver = self._build_driver(
                group,
                snapshot=snapshot,
                snapshot_history=snapshot_history,
                previous_driver=previous_drivers,
                prior_day_drivers=prior_day_drivers,
                drivers_built_so_far=drivers,
            )
            if driver:
                drivers.append(driver)
        drivers = [driver for driver in drivers if driver]
        drivers.sort(
            key=lambda item: (
                int(item.get("importance_score") or 0),
                self._sort_timestamp(item.get("last_event_time")),
            ),
            reverse=True,
        )
        self._attach_related_drivers(drivers)

        state = {
            "driver_engine_version": DRIVER_STATE_VERSION,
            "generated_at": snapshot.get("generated_at"),
            "source_signature": self._current_source_signature(snapshot=snapshot, candidate_events=candidate_events),
            "news_feed": self._build_news_feed(candidate_events, drivers),
            "drivers": drivers,
        }
        self._save_state(state)
        return state

    def _load_state(self, refresh_if_stale: bool = True) -> Dict[str, Any]:
        if not os.path.exists(self.drivers_path):
            return self.refresh_drivers()
        state = self._read_saved_state()
        if not state:
            return self.refresh_drivers()
        if state.get("driver_engine_version") != DRIVER_STATE_VERSION:
            return self.refresh_drivers()
        if refresh_if_stale and self._driver_state_is_stale(state):
            return self.refresh_drivers()
        return state

    def _save_state(self, state: Dict[str, Any]) -> None:
        atomic_json_dump(self.drivers_path, state)

    def _read_saved_state(self) -> Dict[str, Any]:
        if not os.path.exists(self.drivers_path):
            return {}
        try:
            with open(self.drivers_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception("Failed to load driver state")
            return {}

    def persist_driver_cross_asset_batch(self, analyses: Dict[str, Dict[str, Any]]) -> None:
        if not analyses:
            return

        state = self._load_state(refresh_if_stale=False)
        drivers = list(state.get("drivers", []) or [])
        changed = False

        for index, driver in enumerate(drivers):
            driver_id = driver.get("driver_id")
            payload = analyses.get(driver_id)
            if not payload:
                continue
            if driver.get("event_chain_signature") != payload.get("event_chain_signature"):
                continue

            updated_driver = dict(driver)
            updated_driver["persisted_cross_asset"] = {
                "version": PERSISTED_CROSS_ASSET_VERSION,
                "event_chain_signature": payload.get("event_chain_signature"),
                "saved_at": datetime.now(LOCAL_TZ).isoformat(),
                "analysis": payload.get("analysis") or {},
            }
            drivers[index] = updated_driver
            changed = True

        if not changed:
            return

        state["drivers"] = drivers
        self._save_state(state)

    def _reclassify_recent_events(
        self,
        recent_events: List[Dict[str, Any]],
        snapshot: Dict[str, Any],
        persist: bool = True,
    ) -> List[Dict[str, Any]]:
        market_snapshot = (snapshot.get("market") or {}) if isinstance(snapshot, dict) else {}
        enriched = self.ingestion.reclassify_news_events(recent_events, market_snapshot=market_snapshot)
        if persist and enriched != recent_events:
            try:
                self.store.replace_recent_events(enriched)
            except Exception:
                logger.exception("Failed to persist frozen recent events")
        enriched.sort(key=lambda item: self._sort_timestamp(item.get("event_time")), reverse=True)
        return enriched

    def _load_active_day_events(self, macro_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        snapshot = (macro_state or {}).get("snapshot", {}) or {}
        snapshot_generated_at = snapshot.get("generated_at")
        reference_dt = self._parse_iso_datetime(snapshot_generated_at)
        if reference_dt:
            reference_local = reference_dt.astimezone(LOCAL_TZ)
        else:
            reference_local = datetime.now(LOCAL_TZ)

        session_start = (
            reference_local.replace(hour=20, minute=0, second=0, microsecond=0)
            - timedelta(days=1)
        )
        events = self.store.list_events_in_local_window(
            start_local=session_start,
            end_local=reference_local,
            include_state=True,
        )
        if events:
            return events
        return list((macro_state or {}).get("recent_events", []) or [])

    def _current_source_signature(
        self,
        snapshot: Dict[str, Any],
        candidate_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        latest_event = candidate_events[-1] if candidate_events else {}
        event_signature = hashlib.sha1(
            json.dumps(
                [
                    {
                        "event_id": item.get("event_id"),
                        "event_time": item.get("event_time"),
                        "impact_score": int(item.get("impact_score") or 0),
                        "scenario_classification": item.get("scenario_classification"),
                        "linked_contracts": item.get("linked_contracts") or [],
                        "linked_buckets": item.get("linked_buckets") or [],
                        "linked_securities": item.get("linked_securities") or [],
                        "themes": item.get("themes") or [],
                        "classification_version": item.get("classification_version"),
                    }
                    for item in candidate_events
                ],
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        return {
            "engine_version": "macro-candidate-v3-frozen",
            "latest_event_id": latest_event.get("event_id"),
            "latest_event_time": latest_event.get("event_time"),
            "candidate_event_count": len(candidate_events),
            "event_signature": event_signature,
        }

    def _event_is_directional_macro_driver(self, event: Dict[str, Any]) -> bool:
        themes = {str(item).strip().lower() for item in (event.get("themes") or []) if item}
        high_conviction_terms = {
            str(item).strip().lower()
            for item in (event.get("high_conviction_macro_terms") or [])
            if item
        }
        headline = unescape(str(event.get("headline") or "")).lower()
        linked_buckets = list(event.get("linked_buckets") or [])
        linked_contracts = list(event.get("linked_contracts") or [])
        linked_securities = list(event.get("linked_securities") or [])
        term_hit = bool(high_conviction_terms & DIRECTIONAL_MACRO_TERMS)
        headline_hit = any(term in headline for term in DIRECTIONAL_MACRO_TERMS)
        theme_hit = bool(themes & SESSION_RISK_THEMES)
        if theme_hit:
            return True
        if not (term_hit or headline_hit):
            return False
        if linked_buckets:
            return True
        if len(linked_contracts) >= 3:
            return True
        if linked_securities:
            return True
        return False

    def _events_are_directional_macro_cluster(self, events: List[Dict[str, Any]]) -> bool:
        return any(self._event_is_directional_macro_driver(event) for event in events)

    def _driver_state_is_stale(self, state: Dict[str, Any]) -> bool:
        saved_signature = state.get("source_signature")
        if not saved_signature:
            return True

        macro_state = self.store.read_state()
        snapshot = macro_state.get("snapshot", {}) or {}
        recent_events = self._reclassify_recent_events(
            self._load_active_day_events(macro_state),
            snapshot=snapshot,
            persist=False,
        )
        candidate_events = self._candidate_events(recent_events)
        current_signature = self._current_source_signature(snapshot=snapshot, candidate_events=candidate_events)
        return current_signature != saved_signature

    def _candidate_events(self, recent_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        candidates = []
        for event in recent_events:
            scope = str(event.get("macro_scope") or "")
            scenario = str(event.get("scenario_classification") or "secondary_echo")
            signal_strength = str(event.get("signal_strength") or "low")
            impact_score = int(event.get("impact_score") or 0)
            transmission_score = float(event.get("macro_transmission_score") or 0.0)
            directional_macro = self._event_is_directional_macro_driver(event)
            has_links = bool(
                event.get("linked_contracts")
                or event.get("linked_securities")
                or event.get("linked_buckets")
            )
            if scope == "idiosyncratic":
                continue
            if transmission_score < 3.5 and scenario != "regime_shift":
                continue
            if not (
                event.get("market_relevance")
                or event.get("linked_contracts")
                or event.get("linked_securities")
                or event.get("linked_buckets")
                or scope == "tracked_security"
            ):
                continue
            if not event.get("market_relevance") and not (
                event.get("linked_contracts")
                or event.get("linked_securities")
                or event.get("linked_buckets")
            ):
                continue
            if scope == "tracked_security":
                if impact_score < 4 or signal_strength not in {"high", "medium"} or not event.get("linked_securities"):
                    continue
            elif scenario == "regime_shift":
                if directional_macro:
                    if impact_score < 4 and signal_strength not in {"high", "medium"}:
                        continue
                    if not has_links and not directional_macro:
                        continue
                else:
                    if impact_score < 12 and not (
                        signal_strength == "high"
                        and len(event.get("linked_buckets") or []) >= 2
                    ):
                        continue
                    if not has_links:
                        continue
            elif scenario == "tradable_catalyst":
                if directional_macro:
                    if impact_score >= 5:
                        pass
                    elif signal_strength in {"high", "medium"} and (
                        len(event.get("linked_buckets") or []) >= 1
                        or has_links
                    ):
                        pass
                    else:
                        continue
                elif impact_score >= 12:
                    pass
                elif signal_strength == "high" and len(event.get("linked_buckets") or []) >= 2:
                    pass
                else:
                    continue
            elif scenario == "secondary_echo":
                if directional_macro:
                    if impact_score < 4:
                        continue
                    if signal_strength == "technical_low":
                        continue
                    if not has_links and not directional_macro:
                        continue
                else:
                    if impact_score < 8 or signal_strength != "high" or not has_links:
                        continue
            else:
                continue
            candidates.append(event)

        candidates.sort(key=lambda item: self._sort_timestamp(item.get("event_time")))
        return candidates

    def _group_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups: List[Dict[str, Any]] = []
        for event in events:
            signature = self._event_signature(event)
            event_time = self._parse_iso_datetime(event.get("event_time")) or datetime.now(LOCAL_TZ)
            matched_group = None
            for group in groups:
                if group["signature"] != signature:
                    continue
                last_time = group.get("last_event_dt") or event_time
                allowed_window = max(
                    self._group_window_seconds(event.get("themes") or []),
                    self._group_window_seconds(group.get("themes") or []),
                )
                if abs((event_time - last_time).total_seconds()) <= allowed_window:
                    matched_group = group
                    break

            if matched_group is None:
                matched_group = {
                    "signature": signature,
                    "events": [],
                    "focus_contracts": set(),
                    "focus_securities": set(),
                    "focus_buckets": set(),
                    "themes": set(),
                    "last_event_dt": event_time,
                }
                groups.append(matched_group)

            matched_group["events"].append(event)
            matched_group["last_event_dt"] = max(matched_group["last_event_dt"], event_time)
            matched_group["focus_contracts"].update(event.get("linked_contracts") or [])
            matched_group["focus_securities"].update(event.get("linked_securities") or [])
            matched_group["focus_buckets"].update(event.get("linked_buckets") or [])
            matched_group["themes"].update(event.get("themes") or [])

        return groups

    def _build_driver(
        self,
        group: Dict[str, Any],
        snapshot: Dict[str, Any],
        snapshot_history: List[Dict[str, Any]],
        previous_driver: Dict[str, Dict[str, Any]] | None = None,
        prior_day_drivers: List[Dict[str, Any]] | None = None,
        drivers_built_so_far: List[Dict[str, Any]] | None = None,
    ) -> Optional[Dict[str, Any]]:
        events = group.get("events", [])
        if not events:
            return None

        sorted_events = sorted(events, key=lambda item: self._sort_timestamp(item.get("event_time")))
        first_event = sorted_events[0]
        last_event = sorted_events[-1]
        focus_contracts = list(dict.fromkeys(sorted(group.get("focus_contracts") or [])))
        focus_securities = list(dict.fromkeys(sorted(group.get("focus_securities") or [])))
        focus_buckets = list(dict.fromkeys(sorted(group.get("focus_buckets") or [])))
        themes = list(dict.fromkeys(sorted(group.get("themes") or [])))
        contracts_snapshot = ((snapshot.get("market") or {}).get("contracts")) or {}
        securities_snapshot = ((snapshot.get("market") or {}).get("securities")) or {}
        primary_asset = (
            focus_contracts[0] if focus_contracts
            else focus_securities[0] if focus_securities
            else None
        )
        technical_operation = self._is_technical_driver(sorted_events)
        signal_strength = self._driver_signal_strength(sorted_events)
        canonical_theme = self._canonical_theme(themes)
        driver_id = self._driver_id(first_event, last_event, primary_asset, themes, focus_contracts, focus_securities)
        event_chain_signature = self._event_chain_signature(sorted_events)
        existing_driver = (previous_driver or {}).get(driver_id)
        day_context = self._build_day_context(
            current_driver_id=driver_id,
            current_events=sorted_events,
            primary_asset=primary_asset,
            focus_buckets=focus_buckets,
            themes=themes,
            snapshot=snapshot,
            prior_day_drivers=prior_day_drivers or [],
            drivers_built_so_far=drivers_built_so_far or [],
        )

        price_evolution = self._build_price_evolution(
            focus_contracts=focus_contracts,
            focus_securities=focus_securities,
            contracts_snapshot=contracts_snapshot,
            first_event_time=first_event.get("event_time"),
            snapshot_history=snapshot_history,
        )
        market_elasticity = self._build_market_elasticity(
            first_event_time=first_event.get("event_time"),
            focus_contracts=focus_contracts,
            focus_buckets=focus_buckets,
            contracts_snapshot=contracts_snapshot,
            snapshot_history=snapshot_history,
            snapshot_generated_at=snapshot.get("generated_at"),
        )

        if self._can_reuse_driver(existing_driver, event_chain_signature, last_event.get("event_time"), len(sorted_events)):
            reused_driver = dict(existing_driver)
            reused_driver.update({
                "price_evolution": price_evolution,
                "market_elasticity": market_elasticity,
                "first_event_time": first_event.get("event_time"),
                "last_event_time": last_event.get("event_time"),
                "headline_count": len(sorted_events),
                "headline_updates": [
                    {
                        "event_id": event.get("event_id"),
                        "headline": unescape(str(event.get("headline") or "")),
                        "event_time": event.get("event_time"),
                        "posted_by": event.get("posted_by"),
                        "relevance": event.get("relevance"),
                        "impact_score": int(event.get("impact_score") or 0),
                        "technical_operation": bool(event.get("technical_operation")),
                        "signal_strength": event.get("signal_strength") or "low",
                    }
                    for event in sorted_events
                ],
                "focus_contracts": focus_contracts,
                "focus_securities": focus_securities,
                "focus_buckets": focus_buckets,
                "themes": themes,
                "canonical_theme": canonical_theme,
                "technical_operation": technical_operation,
                "signal_strength": signal_strength,
                "event_chain_signature": event_chain_signature,
                "day_context_meta": reused_driver.get("day_context_meta") or day_context.get("meta") or {},
                "directional_consensus_bias": reused_driver.get("directional_consensus_bias"),
                "directional_consensus_confidence": reused_driver.get("directional_consensus_confidence"),
                "directional_consensus_reason": reused_driver.get("directional_consensus_reason"),
            })
            reused_driver["agent_audit_report"] = self._build_agent_audit_report(
                driver=reused_driver,
                generated_at=snapshot.get("generated_at"),
            )
            return reused_driver

        participant_reactions = self._build_participant_reactions(focus_contracts, contracts_snapshot)
        asset_asymmetry = self._build_asset_asymmetry(
            focus_contracts=focus_contracts,
            focus_securities=focus_securities,
            contracts_snapshot=contracts_snapshot,
            securities_snapshot=securities_snapshot,
        )
        importance_score = self._driver_importance(sorted_events, asset_asymmetry, participant_reactions)
        ai_analysis = self._generate_driver_analysis(
            events=sorted_events,
            primary_asset=primary_asset,
            focus_contracts=focus_contracts,
            focus_securities=focus_securities,
            focus_buckets=focus_buckets,
            themes=themes,
            asset_asymmetry=asset_asymmetry,
            price_evolution=price_evolution,
            participant_reactions=participant_reactions,
            importance_score=importance_score,
            day_context=day_context,
        )
        expected_impact = self._expected_impact_payload(
            ai_analysis=ai_analysis,
            events=sorted_events,
            focus_contracts=focus_contracts,
            focus_securities=focus_securities,
            focus_buckets=focus_buckets,
            participant_reactions=participant_reactions,
            asset_asymmetry=asset_asymmetry,
            importance_score=importance_score,
        )
        driver_title = self._canonical_theme_title(canonical_theme) or ai_analysis.get("title") or self._fallback_driver_title(sorted_events, primary_asset)
        macro_explanation = (
            self._canonical_theme_explanation(canonical_theme)
            or ai_analysis.get("macro_explanation")
            or self._fallback_macro_explanation(sorted_events, primary_asset)
        )

        driver_payload = {
            "driver_id": driver_id,
            "canonical_theme": canonical_theme,
            "title": driver_title,
            "driver_status": "active",
            "analysis_version": DRIVER_ANALYSIS_VERSION,
            "first_event_time": first_event.get("event_time"),
            "last_event_time": last_event.get("event_time"),
            "headline_count": len(sorted_events),
            "event_chain_signature": event_chain_signature,
            "importance_score": importance_score,
            "importance_label": self._importance_label(importance_score),
            "expected_impact_score": expected_impact["score"],
            "expected_impact_band": expected_impact["band"],
            "expected_impact_reason": expected_impact["reason"],
            "scenario_classification": expected_impact["scenario_classification"],
            "max_impact_score": max(int(item.get("impact_score") or 0) for item in sorted_events),
            "primary_asset": primary_asset,
            "focus_contracts": focus_contracts,
            "focus_securities": focus_securities,
            "focus_buckets": focus_buckets,
            "themes": themes,
            "technical_operation": technical_operation,
            "signal_strength": signal_strength,
            "macro_explanation": macro_explanation,
            "driver_summary": ai_analysis.get("driver_summary") or self._fallback_driver_summary(sorted_events, price_evolution),
            "probable_playbook": ai_analysis.get("probable_playbook") or self._fallback_playbook(asset_asymmetry),
            "importance_reason": ai_analysis.get("importance_reason") or "Importance is derived from impact, asset linkage, and immediate market follow-through.",
            "agent_context_packet": ai_analysis.get("agent_context_packet") or {},
            "headline_updates": [
                {
                    "event_id": event.get("event_id"),
                    "headline": unescape(str(event.get("headline") or "")),
                    "event_time": event.get("event_time"),
                    "posted_by": event.get("posted_by"),
                    "relevance": event.get("relevance"),
                    "impact_score": int(event.get("impact_score") or 0),
                    "technical_operation": bool(event.get("technical_operation")),
                    "signal_strength": event.get("signal_strength") or "low",
                    "scenario_classification": event.get("scenario_classification") or "secondary_echo",
                    "scenario_reason": event.get("scenario_reason") or "",
                }
                for event in sorted_events
            ],
            "asset_asymmetry": asset_asymmetry,
            "price_evolution": price_evolution,
            "market_elasticity": market_elasticity,
            "participant_reactions": participant_reactions,
            "driver_graph": self._build_driver_graph(
                driver_id=driver_id,
                title=ai_analysis.get("title") or self._fallback_driver_title(sorted_events, primary_asset),
                updates=sorted_events,
                asset_asymmetry=asset_asymmetry,
                participant_reactions=participant_reactions,
            ),
            "simulation_context": {
                "prompt_seed": ai_analysis.get("simulation_prompt_seed") or self._build_simulation_seed(primary_asset, sorted_events, asset_asymmetry),
                "market_regime": ai_analysis.get("market_regime") or "intraday macro reaction",
                "recommended_action": self._normalize_bias(ai_analysis.get("recommended_action")),
            },
            "directional_consensus_bias": self._normalize_bias(ai_analysis.get("directional_consensus_bias")),
            "directional_consensus_confidence": int(ai_analysis.get("directional_consensus_confidence") or 0),
            "directional_consensus_reason": ai_analysis.get("directional_consensus_reason") or "",
            "day_context_meta": day_context.get("meta") or {},
            "related_driver_ids": [],
        }
        driver_payload["agent_audit_report"] = self._build_agent_audit_report(
            driver=driver_payload,
            generated_at=snapshot.get("generated_at"),
        )
        return driver_payload

    def _build_news_feed(self, events: List[Dict[str, Any]], drivers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        event_to_driver = {}
        for driver in drivers:
            for item in driver.get("headline_updates", []):
                event_to_driver[item.get("event_id")] = {
                    "driver_id": driver.get("driver_id"),
                    "driver_title": driver.get("title"),
                    "importance_score": driver.get("importance_score"),
                }

        items = []
        for event in sorted(events, key=lambda item: self._sort_timestamp(item.get("event_time")), reverse=True):
            assigned = event_to_driver.get(event.get("event_id"), {})
            items.append(
                {
                    "event_id": event.get("event_id"),
                    "headline": unescape(str(event.get("headline") or "")),
                    "event_time": event.get("event_time"),
                    "posted_by": event.get("posted_by"),
                    "relevance": event.get("relevance"),
                    "impact_score": int(event.get("impact_score") or 0),
                    "market_relevance": bool(event.get("market_relevance")),
                    "macro_scope": event.get("macro_scope") or "none",
                    "macro_transmission_score": float(event.get("macro_transmission_score") or 0.0),
                    "idiosyncratic_only": bool(event.get("idiosyncratic_only")),
                    "tracked_security_only": bool(event.get("tracked_security_only")),
                    "technical_operation": bool(event.get("technical_operation")),
                    "signal_strength": event.get("signal_strength") or "low",
                    "scenario_classification": event.get("scenario_classification") or "secondary_echo",
                    "scenario_reason": event.get("scenario_reason") or "",
                    "linked_assets": list(dict.fromkeys((event.get("linked_contracts") or []) + (event.get("linked_securities") or []))),
                    "linked_buckets": list(dict.fromkeys(event.get("linked_buckets") or [])),
                    "themes": list(dict.fromkeys(event.get("themes") or [])),
                    "driver_id": assigned.get("driver_id"),
                    "driver_title": assigned.get("driver_title"),
                    "driver_importance_score": assigned.get("importance_score"),
                }
            )
        return items

    def _build_day_context(
        self,
        current_driver_id: str,
        current_events: List[Dict[str, Any]],
        primary_asset: Optional[str],
        focus_buckets: List[str],
        themes: List[str],
        snapshot: Dict[str, Any],
        prior_day_drivers: List[Dict[str, Any]],
        drivers_built_so_far: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        trading_date = datetime.now(LOCAL_TZ).date()
        seen_driver_ids = set()
        comparable_drivers: List[Dict[str, Any]] = []

        for driver in list(drivers_built_so_far) + list(prior_day_drivers):
            driver_id = driver.get("driver_id")
            if not driver_id or driver_id == current_driver_id or driver_id in seen_driver_ids:
                continue
            driver_dt = self._parse_iso_datetime(driver.get("last_event_time"))
            if driver_dt and driver_dt.astimezone(LOCAL_TZ).date() != trading_date:
                continue
            comparable_drivers.append(driver)
            seen_driver_ids.add(driver_id)

        comparable_drivers.sort(
            key=lambda item: (
                int(item.get("importance_score") or 0),
                int(item.get("expected_impact_score") or 0),
                self._sort_timestamp(item.get("last_event_time")),
            ),
            reverse=True,
        )
        top_drivers = [self._driver_context_meta(driver) for driver in comparable_drivers[:6]]
        fragile_drivers = [
            self._driver_context_meta(driver)
            for driver in comparable_drivers
            if self._is_fragile_driver(driver)
        ][:6]
        narrative_memory = self._build_narrative_memory(
            current_events=current_events,
            primary_asset=primary_asset,
            focus_buckets=focus_buckets,
            themes=themes,
            comparable_drivers=comparable_drivers,
        )

        return {
            "market_panorama": self._build_market_panorama(snapshot),
            "top_drivers": top_drivers,
            "fragile_drivers": fragile_drivers,
            "narrative_memory": narrative_memory,
            "meta": {
                "comparison_driver_count": len(comparable_drivers),
                "top_driver_count": len(top_drivers),
                "fragile_driver_count": len(fragile_drivers),
                "current_primary_asset": primary_asset or "macro basket",
                "current_focus_buckets": focus_buckets,
                "current_themes": themes,
                "headline_count": len(current_events),
                "narrative_match_count": len((narrative_memory.get("related_drivers") or [])),
                "narrative_verdict": narrative_memory.get("contextual_verdict") or "mixed_context",
            },
        }

    def _build_narrative_memory(
        self,
        current_events: List[Dict[str, Any]],
        primary_asset: Optional[str],
        focus_buckets: List[str],
        themes: List[str],
        comparable_drivers: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        current_semantic = aggregate_macro_event_tokens(current_events)
        current_bias = self._normalize_bias(current_semantic.get("aggregate_bias"))
        if current_bias == "watch":
            current_bias = self._theme_directional_bias({str(theme).strip().lower() for theme in themes if theme})

        current_assets = {
            str(asset).strip()
            for event in current_events
            for asset in ((event.get("linked_contracts") or []) + (event.get("linked_securities") or []))
            if str(asset or "").strip()
        }
        current_buckets = {str(bucket).strip().lower() for bucket in focus_buckets if str(bucket or "").strip()}
        current_themes = {str(theme).strip().lower() for theme in themes if str(theme or "").strip()}
        current_headline_tokens = {
            token
            for event in current_events
            for token in self._headline_tokens(event.get("headline"))
        }

        related_drivers: List[Dict[str, Any]] = []
        for driver in comparable_drivers:
            overlap = self._driver_contextual_overlap(
                driver=driver,
                current_assets=current_assets,
                current_buckets=current_buckets,
                current_themes=current_themes,
                current_headline_tokens=current_headline_tokens,
            )
            if overlap["score"] < 5:
                continue

            driver_events = self._driver_headline_events(driver)
            driver_semantic = aggregate_macro_event_tokens(driver_events) if driver_events else {}
            relation_bias = self._normalize_bias(
                ((driver.get("simulation_context") or {}).get("recommended_action"))
                or driver_semantic.get("aggregate_bias")
            )
            if current_bias in {"buy", "sell"} and relation_bias == current_bias:
                narrative_role = "reinforcing"
            elif current_bias in {"buy", "sell"} and relation_bias in {"buy", "sell"} and relation_bias != current_bias:
                narrative_role = "dissolving"
            else:
                narrative_role = "adjacent"

            realized_impact = self._driver_realized_impact_meta(driver)
            related_drivers.append(
                {
                    "driver_id": driver.get("driver_id"),
                    "title": driver.get("title"),
                    "last_event_time": driver.get("last_event_time"),
                    "primary_asset": driver.get("primary_asset"),
                    "importance_score": int(driver.get("importance_score") or 0),
                    "expected_impact_score": int(driver.get("expected_impact_score") or 0),
                    "recommended_action": relation_bias,
                    "market_regime": (driver.get("simulation_context") or {}).get("market_regime") or "intraday macro reaction",
                    "narrative_role": narrative_role,
                    "overlap_score": overlap["score"],
                    "overlap_reasons": overlap["reasons"],
                    "headline_examples": [
                        unescape(str(item.get("headline") or ""))[:180]
                        for item in driver_events[:2]
                        if str(item.get("headline") or "").strip()
                    ],
                    "themes": list(driver.get("themes") or []),
                    "posted_by": list(
                        dict.fromkeys(
                            str(item.get("posted_by") or "").strip()
                            for item in driver_events[:3]
                            if str(item.get("posted_by") or "").strip()
                        )
                    ),
                    "semantic_summary": driver_semantic.get("aggregate_summary") or "",
                    "realized_impact": realized_impact,
                }
            )

        related_drivers.sort(
            key=lambda item: (
                int(item.get("overlap_score") or 0),
                int(item.get("importance_score") or 0),
                self._sort_timestamp(item.get("last_event_time")),
            ),
            reverse=True,
        )
        related_drivers = related_drivers[:6]

        reinforcing = [item for item in related_drivers if item.get("narrative_role") == "reinforcing"]
        dissolving = [item for item in related_drivers if item.get("narrative_role") == "dissolving"]
        low_followthrough = [
            item for item in related_drivers
            if float((((item.get("realized_impact") or {}).get("strongest_probe") or {}).get("elasticity_score")) or 0.0) < 15.0
        ]
        distinct_sources = {
            source
            for item in related_drivers
            for source in (item.get("posted_by") or [])
            if source
        }
        contextual_flags: List[str] = []
        if len(reinforcing) >= 2 and not dissolving:
            contextual_flags.append("reinforcing_sequence")
        if len(dissolving) >= 1:
            contextual_flags.append("dissolving_sequence")
        if len(low_followthrough) >= 2 and len(related_drivers) >= 2:
            contextual_flags.append("headline_repetition_without_followthrough")
        if len(distinct_sources) >= 3:
            contextual_flags.append("speaker_rotation")
        if "iran_negotiation_setback" in current_themes and any(
            "iran_negotiation" in {str(theme).strip().lower() for theme in (driver.get("themes") or [])}
            for driver in related_drivers
        ):
            contextual_flags.append("setback_after_relief_sequence")

        if "reinforcing_sequence" in contextual_flags and "headline_repetition_without_followthrough" not in contextual_flags:
            contextual_verdict = "reinforcing_sequence"
        elif "dissolving_sequence" in contextual_flags and not reinforcing:
            contextual_verdict = "dissolving_sequence"
        elif "headline_repetition_without_followthrough" in contextual_flags:
            contextual_verdict = "headline_repetition_without_followthrough"
        else:
            contextual_verdict = "mixed_context"

        summary_bits: List[str] = []
        if related_drivers:
            top = related_drivers[0]
            top_probe = ((top.get("realized_impact") or {}).get("strongest_probe") or {})
            top_bias = top.get("recommended_action") or "watch"
            summary_bits.append(
                f"Closest prior context: {top.get('title') or 'driver'} as {top_bias}, overlap {int(top.get('overlap_score') or 0)}"
            )
            if top_probe.get("label") and top_probe.get("elasticity_score") is not None:
                summary_bits.append(
                    f"{top_probe.get('label')} elasticity {float(top_probe.get('elasticity_score') or 0.0):.1f}"
                )
        if contextual_verdict == "reinforcing_sequence":
            summary_bits.append("Recent related headlines reinforced the same regime instead of dissolving it.")
        elif contextual_verdict == "dissolving_sequence":
            summary_bits.append("Recent related headlines point to tension or reversal versus the current read.")
        elif contextual_verdict == "headline_repetition_without_followthrough":
            summary_bits.append("Recent similar headlines failed to generate strong 5-minute follow-through.")
        else:
            summary_bits.append("Recent related context is mixed and should not dominate the current classification.")

        return {
            "current_bias": current_bias,
            "contextual_verdict": contextual_verdict,
            "contextual_flags": contextual_flags,
            "contextual_summary": " ".join(summary_bits).strip(),
            "related_drivers": related_drivers,
        }

    def _driver_headline_events(self, driver: Dict[str, Any]) -> List[Dict[str, Any]]:
        return [item for item in (driver.get("headline_updates") or []) if isinstance(item, dict)]

    def _driver_contextual_overlap(
        self,
        driver: Dict[str, Any],
        current_assets: set[str],
        current_buckets: set[str],
        current_themes: set[str],
        current_headline_tokens: set[str],
    ) -> Dict[str, Any]:
        driver_assets = {
            str(asset).strip()
            for asset in ((driver.get("focus_contracts") or []) + (driver.get("focus_securities") or []))
            if str(asset or "").strip()
        }
        driver_buckets = {str(bucket).strip().lower() for bucket in (driver.get("focus_buckets") or []) if str(bucket or "").strip()}
        driver_themes = {str(theme).strip().lower() for theme in (driver.get("themes") or []) if str(theme or "").strip()}
        driver_tokens = {
            token
            for item in self._driver_headline_events(driver)
            for token in self._headline_tokens(item.get("headline"))
        }

        overlap_assets = current_assets & driver_assets
        overlap_buckets = current_buckets & driver_buckets
        overlap_themes = current_themes & driver_themes
        overlap_tokens = current_headline_tokens & driver_tokens

        score = 0
        reasons: List[str] = []
        if overlap_themes:
            score += len(overlap_themes) * 6
            reasons.append("same_theme")
        if overlap_assets:
            score += len(overlap_assets) * 5
            reasons.append("same_asset")
        if overlap_buckets:
            score += len(overlap_buckets) * 3
            reasons.append("same_bucket")
        if overlap_tokens:
            score += min(len(overlap_tokens), 4) * 2
            reasons.append("headline_token_overlap")

        return {
            "score": score,
            "reasons": reasons,
        }

    def _driver_realized_impact_meta(self, driver: Dict[str, Any]) -> Dict[str, Any]:
        probes: List[Dict[str, Any]] = []
        for row in (((driver.get("market_elasticity") or {}).get("rows")) or []):
            impact = (row.get("impact") or {}) if isinstance(row, dict) else {}
            if not impact:
                continue
            probes.append(
                {
                    "key": row.get("key"),
                    "label": row.get("label"),
                    "ticker": row.get("ticker"),
                    "state": row.get("state"),
                    "direction": impact.get("direction") or "watch",
                    "price_delta_pct": self._to_float(impact.get("price_delta_pct")),
                    "elasticity_score": self._to_float(impact.get("elasticity_score")),
                }
            )

        probes.sort(
            key=lambda item: abs(float(item.get("elasticity_score") or 0.0)),
            reverse=True,
        )
        strongest_probe = probes[0] if probes else {}
        return {
            "strongest_probe": strongest_probe,
            "probes": probes[:3],
        }

    def _build_market_panorama(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        market = (snapshot.get("market") or {}) if isinstance(snapshot, dict) else {}
        overview = (market.get("overview") or {}) if isinstance(market, dict) else {}
        reference_assets = (market.get("reference_assets") or {}) if isinstance(market, dict) else {}

        top_contract_movers = []
        for item in (overview.get("top_movers_5m") or [])[:5]:
            top_contract_movers.append(
                {
                    "ticker": item.get("ticker"),
                    "bucket": item.get("bucket"),
                    "direction_5m": item.get("direction_5m"),
                    "move_pct_5m": self._to_float(item.get("net_change_pct_5m")),
                    "volume_5m": self._to_float(item.get("volume_5m")),
                    "top_5_share_percentage": self._to_float(item.get("top_5_share_percentage")),
                }
            )

        reference_asset_moves = []
        for ticker, asset in reference_assets.items():
            change_pct = self._to_float((asset or {}).get("change_percent"))
            if change_pct is None:
                continue
            reference_asset_moves.append(
                {
                    "ticker": ticker,
                    "label": asset.get("label") or ticker,
                    "change_percent": round(change_pct, 4),
                }
            )

        reference_asset_moves.sort(
            key=lambda item: abs(item.get("change_percent") or 0.0),
            reverse=True,
        )
        return {
            "snapshot_generated_at": snapshot.get("generated_at"),
            "market_relevant_news_count": int(overview.get("market_relevant_news_count") or 0),
            "impactful_news_count": int(overview.get("impactful_news_count") or 0),
            "top_contract_movers": top_contract_movers,
            "reference_asset_moves": reference_asset_moves[:6],
        }

    def _driver_context_meta(self, driver: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "driver_id": driver.get("driver_id"),
            "title": driver.get("title"),
            "primary_asset": driver.get("primary_asset"),
            "importance_score": int(driver.get("importance_score") or 0),
            "importance_label": driver.get("importance_label") or self._importance_label(int(driver.get("importance_score") or 0)),
            "expected_impact_score": int(driver.get("expected_impact_score") or 0),
            "expected_impact_band": driver.get("expected_impact_band") or self._expected_impact_band(int(driver.get("expected_impact_score") or 0)),
            "scenario_classification": driver.get("scenario_classification") or "secondary_echo",
            "recommended_action": self._normalize_bias(((driver.get("simulation_context") or {}).get("recommended_action"))),
            "focus_buckets": list(driver.get("focus_buckets") or []),
            "themes": list(driver.get("themes") or []),
            "last_event_time": driver.get("last_event_time"),
        }

    def _is_fragile_driver(self, driver: Dict[str, Any]) -> bool:
        if bool(driver.get("technical_operation")):
            return True

        expected_impact = int(driver.get("expected_impact_score") or 0)
        importance_score = int(driver.get("importance_score") or 0)
        recommended_action = self._normalize_bias(((driver.get("simulation_context") or {}).get("recommended_action")))
        if expected_impact <= 15:
            return True
        if importance_score <= 18 and recommended_action == "watch":
            return True

        cross_asset = (((driver.get("persisted_cross_asset") or {}).get("analysis")) or {})
        cross_signals = (cross_asset.get("cross_signals") or {}) if isinstance(cross_asset, dict) else {}
        if float(cross_signals.get("fake_move_risk") or 0.0) >= 65:
            return True
        if (
            float(cross_signals.get("confirmation_ratio") or 100.0) <= 35.0
            and abs(float(cross_asset.get("general_score") or 0.0)) >= 8.0
        ):
            return True
        return False

    def _expected_impact_payload(
        self,
        ai_analysis: Dict[str, Any],
        events: List[Dict[str, Any]],
        focus_contracts: List[str],
        focus_securities: List[str],
        focus_buckets: List[str],
        participant_reactions: List[Dict[str, Any]],
        asset_asymmetry: List[Dict[str, Any]],
        importance_score: int,
    ) -> Dict[str, Any]:
        fallback = self._expected_impact_fallback(
            events=events,
            focus_contracts=focus_contracts,
            focus_securities=focus_securities,
            focus_buckets=focus_buckets,
            participant_reactions=participant_reactions,
            asset_asymmetry=asset_asymmetry,
            importance_score=importance_score,
        )
        raw_score = ai_analysis.get("expected_impact_score")
        try:
            score = int(float(raw_score))
        except (TypeError, ValueError):
            score = fallback["score"]
        score = int(round((fallback["score"] * 0.7) + (score * 0.3)))
        score = max(0, min(100, score))
        score = min(
            score,
            self._expected_impact_cap(
                events=events,
                focus_contracts=focus_contracts,
                focus_securities=focus_securities,
                focus_buckets=focus_buckets,
                importance_score=importance_score,
                participant_reactions=participant_reactions,
                asset_asymmetry=asset_asymmetry,
            ),
        )
        band = str(ai_analysis.get("expected_impact_band") or "").strip().lower() or self._expected_impact_band(score)
        if band not in {item[1] for item in EXPECTED_IMPACT_BANDS}:
            band = self._expected_impact_band(score)
        band = self._expected_impact_band(score)
        reason = str(ai_analysis.get("expected_impact_reason") or "").strip() or fallback["reason"]
        scenario_classification = (
            str(ai_analysis.get("scenario_classification") or "").strip().lower()
            or fallback["scenario_classification"]
        )
        scenario_classification = self._expected_impact_band(score) if scenario_classification == "regime_shift" and score < 60 else scenario_classification
        if scenario_classification not in {item[1] for item in EXPECTED_IMPACT_BANDS}:
            scenario_classification = self._expected_impact_band(score)
        return {
            "score": score,
            "band": band,
            "reason": reason,
            "scenario_classification": scenario_classification,
        }

    def _expected_impact_fallback(
        self,
        events: List[Dict[str, Any]],
        focus_contracts: List[str],
        focus_securities: List[str],
        focus_buckets: List[str],
        participant_reactions: List[Dict[str, Any]],
        asset_asymmetry: List[Dict[str, Any]],
        importance_score: int,
    ) -> Dict[str, Any]:
        technical_driver = self._is_technical_driver(events)
        directional_macro = self._events_are_directional_macro_cluster(events)
        directional_consensus = self._directional_consensus(events, asset_asymmetry, participant_reactions)
        max_event_impact = max((int(item.get("impact_score") or 0) for item in events), default=0)
        strongest_asset = max((float(item.get("asymmetry_score") or 0.0) for item in asset_asymmetry), default=0.0)
        strongest_participant = max((float(item.get("activity_score") or 0.0) for item in participant_reactions), default=0.0)

        if technical_driver:
            score = min(8, max(1, max_event_impact))
            reason = (
                "This cluster looks technical or operational, so the expected impact stays close to zero unless "
                "cross-asset confirmation proves otherwise."
            )
        else:
            breadth_bonus = len(focus_buckets) * 7 + min(len(focus_contracts), 3) * 4 + min(len(focus_securities), 3) * 2
            flow_bonus = min(14, int(strongest_asset * 0.18) + int(strongest_participant / 18))
            score = max(0, min(100, int(importance_score * 0.62 + breadth_bonus + flow_bonus)))
            if len(focus_buckets) <= 1 and len(focus_contracts) <= 1 and len(focus_securities) <= 1:
                score = min(score, 38 if directional_macro else 24)
            if directional_consensus.get("confirmed"):
                score = max(score, 32)
                if any(str(item.get("scenario_classification") or "").strip().lower() == "regime_shift" for item in events):
                    score = max(score, 58)
            elif self._normalize_bias(directional_consensus.get("bias")) in {"buy", "sell"}:
                score = max(score, 24)
            reason = (
                f"Expected impact is anchored by current importance ({importance_score}), breadth across "
                f"{max(1, len(focus_buckets))} macro buckets and immediate follow-through in price/flow."
            )
            if directional_consensus.get("confirmed"):
                reason = f"{reason} {directional_consensus.get('reason')}"

        band = self._expected_impact_band(score)
        return {
            "score": score,
            "band": band,
            "reason": reason,
            "scenario_classification": band,
        }

    def _expected_impact_band(self, score: int) -> str:
        for threshold, label in EXPECTED_IMPACT_BANDS:
            if score >= threshold:
                return label
        return "technical_noise"

    def _expected_impact_cap(
        self,
        events: List[Dict[str, Any]],
        focus_contracts: List[str],
        focus_securities: List[str],
        focus_buckets: List[str],
        importance_score: int,
        participant_reactions: List[Dict[str, Any]],
        asset_asymmetry: List[Dict[str, Any]],
    ) -> int:
        if self._is_technical_driver(events):
            return 8

        scenario_classes = {str(item.get("scenario_classification") or "") for item in events}
        directional_macro = self._events_are_directional_macro_cluster(events)
        directional_consensus = self._directional_consensus(events, asset_asymmetry, participant_reactions)
        if scenario_classes and scenario_classes <= {"technical_noise"}:
            return 8
        if scenario_classes and scenario_classes <= {"secondary_echo"} and len(focus_buckets) <= 1:
            return 32 if directional_macro else 24
        if len(focus_buckets) == 0 and len(focus_contracts) <= 1 and len(focus_securities) <= 2:
            return 28 if directional_macro else 18
        if len(focus_buckets) <= 1 and len(focus_contracts) <= 1 and len(focus_securities) <= 3:
            if directional_consensus.get("confirmed"):
                return 60
            return 45 if directional_macro else 28
        if "regime_shift" not in scenario_classes and len(focus_buckets) <= 1:
            if directional_consensus.get("confirmed"):
                return 72
            return 60 if directional_macro else 45
        if importance_score <= 20:
            return 32 if directional_macro else 24
        if importance_score <= 35:
            return 48 if directional_macro else 40
        return 100

    def _build_asset_asymmetry(
        self,
        focus_contracts: List[str],
        focus_securities: List[str],
        contracts_snapshot: Dict[str, Dict[str, Any]],
        securities_snapshot: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for ticker in focus_contracts:
            contract = contracts_snapshot.get(ticker) or {}
            signal = self.ingestion._build_contract_signal(ticker, contract)
            direction = signal.get("direction_5m") or "flat"
            move = self._to_float(signal.get("net_change_pct_5m")) or 0.0
            top_5 = self._to_float(signal.get("top_5_share_percentage")) or 0.0
            asymmetry_score = round(abs(move) * 450 + (top_5 / 5), 2)
            items.append(
                {
                    "asset": ticker,
                    "asset_type": "contract",
                    "bias": self._direction_to_bias_for_asset(ticker, direction),
                    "asymmetry_score": asymmetry_score,
                    "direction_5m": direction,
                    "net_change_pct_5m": move,
                    "explanation": f"{ticker} is {direction} with {round(move, 4)}% move and top-5 flow share of {round(top_5, 2)}%.",
                }
            )

        for symbol in focus_securities:
            security = securities_snapshot.get(symbol) or {}
            change_pct = self._to_float(security.get("change_percent")) or 0.0
            bias = "buy" if change_pct > 0 else "sell" if change_pct < 0 else "watch"
            items.append(
                {
                    "asset": symbol,
                    "asset_type": "security",
                    "bias": bias,
                    "asymmetry_score": round(abs(change_pct) * 12, 2),
                    "direction_5m": None,
                    "net_change_pct_5m": change_pct,
                    "explanation": f"{symbol} shows {round(change_pct, 3)}% change in the latest security header snapshot.",
                }
            )

        items.sort(key=lambda item: item.get("asymmetry_score") or 0.0, reverse=True)
        return items

    def _build_price_evolution(
        self,
        focus_contracts: List[str],
        focus_securities: List[str],
        contracts_snapshot: Dict[str, Dict[str, Any]],
        first_event_time: Any,
        snapshot_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        event_dt = self._parse_iso_datetime(first_event_time)
        contract_series = []
        for ticker in focus_contracts[:3]:
            timeline = self._build_contract_timeline(
                ticker=ticker,
                current_contract=contracts_snapshot.get(ticker) or {},
                snapshot_history=snapshot_history,
                event_dt=event_dt,
            )
            pre_event = None
            post_event = None
            impact_5m = None

            for point in timeline:
                point_dt = self._parse_iso_datetime(point.get("time"))
                if not point_dt:
                    continue
                if event_dt and point_dt <= event_dt:
                    pre_event = point
                if event_dt and point_dt >= event_dt and post_event is None:
                    post_event = point
                if event_dt and point_dt >= (event_dt + timedelta(minutes=5)) and impact_5m is None:
                    impact_5m = point

            impact_summary = self._build_impact_summary(ticker, pre_event, impact_5m)

            contract_series.append(
                {
                    "ticker": ticker,
                    "pre_event": pre_event,
                    "first_after_event": post_event,
                    "impact_5m_point": impact_5m,
                    "impact_5m": impact_summary,
                    "timeline_1m": timeline[-20:],
                }
            )

        baseline_snapshot = None
        if event_dt:
            for record in reversed(snapshot_history):
                generated_at = self._parse_iso_datetime(record.get("generated_at"))
                if generated_at and generated_at <= event_dt:
                    baseline_snapshot = {
                        "generated_at": record.get("generated_at"),
                        "contracts": {
                            ticker: (((record.get("snapshot") or {}).get("market") or {}).get("contracts") or {}).get(ticker)
                            for ticker in focus_contracts[:3]
                        },
                    }
                    break

        return {
            "event_time": first_event_time,
            "baseline_snapshot": baseline_snapshot,
            "series": contract_series,
            "focus_securities": focus_securities[:3],
        }

    def _build_contract_timeline(
        self,
        ticker: str,
        current_contract: Dict[str, Any],
        snapshot_history: List[Dict[str, Any]],
        event_dt: Optional[datetime],
    ) -> List[Dict[str, Any]]:
        points_by_time: Dict[str, Dict[str, Any]] = {}

        def ingest_contract(contract: Dict[str, Any]) -> None:
            candles = (((contract or {}).get("ohlcv") or {}).get("candles_1m")) or []
            for candle in candles:
                candle_dt = self._parse_iso_datetime(candle.get("time"))
                if not candle_dt:
                    continue
                if event_dt and abs((candle_dt - event_dt).total_seconds()) > 40 * 60:
                    continue
                point = {
                    "time": candle.get("time"),
                    "close": self._to_float(candle.get("close")),
                    "volume": self._to_float(candle.get("volume")),
                }
                existing = points_by_time.get(point["time"])
                if existing is None or (existing.get("volume") or 0.0) <= (point.get("volume") or 0.0):
                    points_by_time[point["time"]] = point

        ingest_contract(current_contract)

        for record in snapshot_history:
            snapshot_contract = (
                (((record.get("snapshot") or {}).get("market") or {}).get("contracts") or {}).get(ticker)
            ) or {}
            ingest_contract(snapshot_contract)

        timeline = list(points_by_time.values())
        timeline.sort(key=lambda item: self._sort_timestamp(item.get("time")))
        return timeline

    def _build_impact_summary(
        self,
        ticker: str,
        pre_event: Optional[Dict[str, Any]],
        impact_5m: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not pre_event or not impact_5m:
            return None

        pre_close = self._to_float(pre_event.get("close"))
        impact_close = self._to_float(impact_5m.get("close"))
        pre_volume = self._to_float(pre_event.get("volume"))
        impact_volume = self._to_float(impact_5m.get("volume"))

        if pre_close is None or impact_close is None:
            return None

        price_delta = impact_close - pre_close
        price_delta_pct = (price_delta / pre_close * 100) if pre_close else None
        volume_delta = None
        if pre_volume is not None and impact_volume is not None:
            volume_delta = impact_volume - pre_volume

        return {
            "price_delta": round(price_delta, 6),
            "price_delta_pct": round(price_delta_pct, 6) if price_delta_pct is not None else None,
            "volume_delta": round(volume_delta, 2) if volume_delta is not None else None,
            "direction": self._direction_to_bias_for_asset(
                ticker,
                "up" if price_delta > 0 else "down" if price_delta < 0 else "flat",
            ),
        }

    def _build_market_elasticity(
        self,
        first_event_time: Any,
        focus_contracts: List[str],
        focus_buckets: List[str],
        contracts_snapshot: Dict[str, Dict[str, Any]],
        snapshot_history: List[Dict[str, Any]],
        snapshot_generated_at: Any,
    ) -> Dict[str, Any]:
        event_dt = self._parse_iso_datetime(first_event_time)
        now_dt = self._parse_iso_datetime(snapshot_generated_at) or datetime.now(LOCAL_TZ)
        if not event_dt:
            return {
                "generated_at": snapshot_generated_at,
                "event_time": first_event_time,
                "live_window_open": False,
                "rows": [],
            }

        rows = []
        for probe in self._market_probe_contracts(focus_contracts=focus_contracts, focus_buckets=focus_buckets):
            ticker = probe.get("ticker")
            if not ticker:
                continue

            timeline = self._build_contract_timeline(
                ticker=ticker,
                current_contract=contracts_snapshot.get(ticker) or {},
                snapshot_history=snapshot_history,
                event_dt=event_dt,
            )
            rows.append(
                self._build_market_elasticity_row(
                    key=str(probe.get("key") or ticker).lower(),
                    label=str(probe.get("label") or ticker),
                    ticker=ticker,
                    timeline=timeline,
                    event_dt=event_dt,
                    now_dt=now_dt,
                )
            )

        return {
            "generated_at": snapshot_generated_at,
            "event_time": first_event_time,
            "live_window_open": any(bool(item.get("live_window_open")) for item in rows),
            "rows": rows,
        }

    def _market_probe_contracts(
        self,
        focus_contracts: List[str],
        focus_buckets: List[str],
    ) -> List[Dict[str, str]]:
        di_focus = next((ticker for ticker in focus_contracts if self._is_rate_contract(ticker)), None)
        if not di_focus:
            if "curve_short" in focus_buckets and Config.MACRO_CURVE_SHORT_TICKERS:
                di_focus = Config.MACRO_CURVE_SHORT_TICKERS[0]
            elif "curve_long" in focus_buckets and Config.MACRO_CURVE_LONG_TICKERS:
                di_focus = Config.MACRO_CURVE_LONG_TICKERS[0]
            elif Config.MACRO_CURVE_LONG_TICKERS:
                di_focus = Config.MACRO_CURVE_LONG_TICKERS[0]
            elif Config.MACRO_CURVE_SHORT_TICKERS:
                di_focus = Config.MACRO_CURVE_SHORT_TICKERS[0]

        probes = [
            {"key": "win", "label": "WIN", "ticker": (Config.MACRO_INDEX_TICKERS or [None])[0]},
            {"key": "wdo", "label": "WDO", "ticker": (Config.MACRO_DOLLAR_TICKERS or [None])[0]},
            {"key": "di", "label": "DI", "ticker": di_focus},
        ]

        seen = set()
        normalized = []
        for item in probes:
            ticker = str(item.get("ticker") or "").strip()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            normalized.append({**item, "ticker": ticker})
        return normalized

    def _build_market_elasticity_row(
        self,
        key: str,
        label: str,
        ticker: str,
        timeline: List[Dict[str, Any]],
        event_dt: datetime,
        now_dt: datetime,
    ) -> Dict[str, Any]:
        pre_event = None
        first_after_event = None
        latest_after_event = None
        impact_5m_point = None

        for point in timeline:
            point_dt = self._parse_iso_datetime(point.get("time"))
            if not point_dt:
                continue
            if point_dt <= event_dt:
                pre_event = point
            if point_dt >= event_dt and first_after_event is None:
                first_after_event = point
            if point_dt >= event_dt:
                latest_after_event = point
            if point_dt >= (event_dt + timedelta(minutes=5)) and impact_5m_point is None:
                impact_5m_point = point

        effective_point = impact_5m_point or latest_after_event or first_after_event
        effective_summary = self._build_impact_summary(ticker, pre_event, effective_point)
        elapsed_minutes = max(0.0, (now_dt - event_dt).total_seconds() / 60.0)
        live_window_open = elapsed_minutes < 5.0 and impact_5m_point is None
        completion_ratio = max(0.0, min(1.0, elapsed_minutes / 5.0))

        elasticity_score = 0.0
        if effective_summary and effective_summary.get("price_delta_pct") is not None:
            reference_move = ELASTICITY_REFERENCE_MOVE_PCT.get(key, 0.15)
            elasticity_score = min(
                100.0,
                abs(float(effective_summary.get("price_delta_pct") or 0.0)) / max(reference_move, 0.0001) * 100.0,
            )

        effective_dt = self._parse_iso_datetime((effective_point or {}).get("time"))
        state = (
            "live"
            if live_window_open
            else "frozen"
            if impact_5m_point is not None
            else "pending"
        )

        return {
            "key": key,
            "label": label,
            "ticker": ticker,
            "state": state,
            "live_window_open": live_window_open,
            "freeze_at": (event_dt + timedelta(minutes=5)).isoformat(),
            "elapsed_minutes": round(elapsed_minutes, 2),
            "completion_ratio": round(completion_ratio, 4),
            "pre_event": pre_event,
            "first_after_event": first_after_event,
            "effective_point": effective_point,
            "effective_time": effective_dt.isoformat() if effective_dt else None,
            "impact": {
                **(effective_summary or {}),
                "elasticity_score": round(elasticity_score, 2),
            } if effective_summary else None,
        }

    def _build_agent_audit_report(
        self,
        driver: Dict[str, Any],
        generated_at: Any,
    ) -> Dict[str, Any]:
        simulation_context = driver.get("simulation_context") or {}
        context_packet = (driver.get("agent_context_packet") or {}) if isinstance(driver, dict) else {}
        context_semantic = (context_packet.get("semantic") or {}) if isinstance(context_packet, dict) else {}
        narrative_memory = (context_packet.get("narrative_memory") or {}) if isinstance(context_packet, dict) else {}
        return {
            "generated_at": generated_at,
            "importance_score": int(driver.get("importance_score") or 0),
            "importance_label": driver.get("importance_label") or self._importance_label(int(driver.get("importance_score") or 0)),
            "expected_impact_score": int(driver.get("expected_impact_score") or 0),
            "expected_impact_band": driver.get("expected_impact_band") or self._expected_impact_band(int(driver.get("expected_impact_score") or 0)),
            "scenario_classification": driver.get("scenario_classification") or "secondary_echo",
            "market_regime": simulation_context.get("market_regime") or "intraday macro reaction",
            "recommended_action": self._normalize_bias(simulation_context.get("recommended_action")),
            "macro_explanation": driver.get("macro_explanation") or "",
            "driver_summary": driver.get("driver_summary") or "",
            "probable_playbook": driver.get("probable_playbook") or "",
            "importance_reason": driver.get("importance_reason") or "",
            "expected_impact_reason": driver.get("expected_impact_reason") or "",
            "directional_consensus": {
                "bias": self._normalize_bias(driver.get("directional_consensus_bias")),
                "confidence": int(driver.get("directional_consensus_confidence") or 0),
                "reason": driver.get("directional_consensus_reason") or "",
            },
            "context_tokens": {
                "aggregate_bias": context_semantic.get("aggregate_bias"),
                "aggregate_confidence": context_semantic.get("aggregate_confidence"),
                "aggregate_regime": context_semantic.get("aggregate_regime"),
                "aggregate_summary": context_semantic.get("aggregate_summary"),
                "top_tokens": context_semantic.get("top_tokens") or [],
                "contradiction_flags": context_packet.get("contradiction_flags") or [],
            },
            "narrative_memory": {
                "contextual_verdict": narrative_memory.get("contextual_verdict") or "mixed_context",
                "contextual_flags": narrative_memory.get("contextual_flags") or [],
                "contextual_summary": narrative_memory.get("contextual_summary") or "",
                "related_driver_titles": [
                    item.get("title")
                    for item in (narrative_memory.get("related_drivers") or [])[:4]
                    if item.get("title")
                ],
            },
        }

    def _build_participant_reactions(
        self,
        focus_contracts: List[str],
        contracts_snapshot: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        reactions = []
        broker_scores: Dict[str, Dict[str, Any]] = {}
        for ticker in focus_contracts:
            contract = contracts_snapshot.get(ticker) or {}
            signal = self.ingestion._build_contract_signal(ticker, contract)
            direction_sign = self._market_direction_sign_for_contract(ticker, signal.get("direction_5m"))
            move = abs(self._to_float(signal.get("net_change_pct_5m")) or 0.0)
            for row in ((contract.get("participants") or {}).get("all_rows")) or []:
                name = row.get("broker_name")
                if not name:
                    continue
                share = self._to_float(row.get("percentage_float"))
                if share is None:
                    share = self._to_float(row.get("percentage"))
                share = share or 0.0
                activity = share * max(move * 100, 1.0)
                current = broker_scores.setdefault(
                    name,
                    {
                        "broker_name": name,
                        "activity_score": 0.0,
                        "sentiment_score": 0.0,
                        "assets": [],
                    },
                )
                current["activity_score"] += activity
                current["sentiment_score"] += direction_sign * activity
                current["assets"].append({
                    "ticker": ticker,
                    "share_percentage": round(share, 2),
                    "market_bias": self._direction_to_bias(signal.get("direction_5m")),
                })

        for item in broker_scores.values():
            score = item.get("sentiment_score") or 0.0
            reactions.append(
                {
                    "broker_name": item.get("broker_name"),
                    "activity_score": round(item.get("activity_score") or 0.0, 2),
                    "sentiment_score": round(score, 2),
                    "market_bias": self._normalize_bias("buy" if score > 1 else "sell" if score < -1 else "watch"),
                    "assets": item.get("assets", [])[:4],
                }
            )

        reactions.sort(key=lambda item: item.get("activity_score") or 0.0, reverse=True)
        return reactions[:10]

    def _build_driver_graph(
        self,
        driver_id: str,
        title: str,
        updates: List[Dict[str, Any]],
        asset_asymmetry: List[Dict[str, Any]],
        participant_reactions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        nodes = [
            {"id": driver_id, "label": title, "type": "driver"},
        ]
        edges = []

        for update in updates[:6]:
            event_id = update.get("event_id")
            nodes.append({
                "id": event_id,
                "label": unescape(str(update.get("headline") or ""))[:88],
                "type": "news",
            })
            edges.append({"source": driver_id, "target": event_id, "relation": "updated_by"})

        for asset in asset_asymmetry[:6]:
            asset_id = f"asset::{asset.get('asset')}"
            nodes.append({
                "id": asset_id,
                "label": asset.get("asset"),
                "type": "asset",
            })
            edges.append({"source": driver_id, "target": asset_id, "relation": f"impacts::{asset.get('bias')}"})

        for participant in participant_reactions[:6]:
            participant_id = f"broker::{participant.get('broker_name')}"
            nodes.append({
                "id": participant_id,
                "label": participant.get("broker_name"),
                "type": "participant",
            })
            edges.append({"source": driver_id, "target": participant_id, "relation": f"moves::{participant.get('market_bias')}"})

        return {"nodes": nodes, "edges": edges}

    def _generate_driver_analysis(
        self,
        events: List[Dict[str, Any]],
        primary_asset: Optional[str],
        focus_contracts: List[str],
        focus_securities: List[str],
        focus_buckets: List[str],
        themes: List[str],
        asset_asymmetry: List[Dict[str, Any]],
        price_evolution: Dict[str, Any],
        participant_reactions: List[Dict[str, Any]],
        importance_score: int,
        day_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        technical_driver = self._is_technical_driver(events)
        directional_consensus = self._directional_consensus(events, asset_asymmetry, participant_reactions)
        expected_impact_fallback = self._expected_impact_fallback(
            events=events,
            focus_contracts=focus_contracts,
            focus_securities=focus_securities,
            focus_buckets=focus_buckets,
            participant_reactions=participant_reactions,
            asset_asymmetry=asset_asymmetry,
            importance_score=importance_score,
        )
        context_packet = build_driver_llm_context_packet(
            events=events,
            primary_asset=primary_asset,
            focus_contracts=focus_contracts,
            focus_securities=focus_securities,
            focus_buckets=focus_buckets,
            themes=themes,
            asset_asymmetry=asset_asymmetry,
            participant_reactions=participant_reactions,
            day_context=day_context,
            directional_consensus=directional_consensus,
            expected_impact_fallback=expected_impact_fallback,
            importance_score=importance_score,
            technical_driver=technical_driver,
        )
        context_semantic = (context_packet.get("semantic") or {})
        context_bias = self._normalize_bias(context_semantic.get("aggregate_bias"))
        context_confidence = int(context_semantic.get("aggregate_confidence") or 0)
        fallback = {
            "title": self._fallback_driver_title(events, primary_asset),
            "macro_explanation": self._fallback_macro_explanation(events, primary_asset),
            "driver_summary": self._fallback_driver_summary(events, price_evolution),
            "probable_playbook": (
                "Treat this as a technical liquidity headline. Keep the default stance at watch unless credit, FX and rates all confirm a real regime change."
                if technical_driver
                else self._fallback_playbook(asset_asymmetry)
            ),
            "importance_reason": "Impact, follow-through and player concentration are keeping this driver on the board.",
            "expected_impact_score": expected_impact_fallback["score"],
            "expected_impact_band": expected_impact_fallback["band"],
            "expected_impact_reason": expected_impact_fallback["reason"],
            "scenario_classification": expected_impact_fallback["scenario_classification"],
            "market_regime": context_semantic.get("aggregate_regime") or directional_consensus.get("market_regime") or "intraday macro reaction",
            "recommended_action": (
                "watch"
                if technical_driver
                else self._regime_implied_action(
                    context_semantic.get("aggregate_regime") or directional_consensus.get("market_regime"),
                    context_bias
                    if context_bias in {"buy", "sell"} and context_confidence >= 38
                    else self._normalize_bias(directional_consensus.get("bias"))
                    if directional_consensus.get("confirmed")
                    else asset_asymmetry[0]["bias"] if asset_asymmetry else "watch",
                )
            ),
            "simulation_prompt_seed": self._build_simulation_seed(primary_asset, events, asset_asymmetry, context_packet=context_packet),
            "directional_consensus_bias": self._normalize_bias(directional_consensus.get("bias")),
            "directional_consensus_confidence": int(directional_consensus.get("confidence") or 0),
            "directional_consensus_reason": directional_consensus.get("reason") or "",
            "agent_context_packet": context_packet,
        }
        try:
            result = self.llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Voce e um trader macro brasileiro veterano, de mesa institucional, acostumado a separar "
                            "mudanca real de regime de ruido de tape, eco de manchete, fala secundaria e noticia "
                            "tecnica. Sua funcao e classificar apenas o que realmente pode deslocar preco, fluxo, "
                            "posicionamento e narrativa do dia. Pense como um operador que ja viu milhares de falsas "
                            "quebras de intraday.\n\n"
                            "Mandamentos:\n"
                            "1. Use o panorama do dia como ancora. Compare a headline atual com os drivers mais fortes "
                            "ja vistos e com os falsos sinais/eco tecnico ja observados.\n"
                            "2. Nao premie noticia so porque parece importante no texto. O score depende de transmissao "
                            "provavel para credito, equity, FX, commodities e juros, alem de follow-through observado.\n"
                            "3. Peso alto so quando a headline muda distribuicao de cenarios, reabre pricing de regime, "
                            "mexe em politica monetaria, crescimento, inflacao, energia, geopol ou liquidez sistemica.\n"
                            "4. Headlines de operacao rotineira do Fed de Nova York, reinvestimento, reserve management, "
                            "repo, plumbing, annual report, balance sheet, unrealized loss, disclosure contabil e "
                            "mark-to-market quase nunca mudam o regime macro por si so. Trate como technical_noise "
                            "ou secondary_echo, a menos que haja confirmacao ampla em credito, FX, bolsa e juros.\n"
                            "5. Para contratos DI, queda de taxa normalmente significa alivio de premio/risk-on e alta "
                            "de taxa normalmente significa risk-off. Nao erre esse sinal.\n"
                            "6. Um bom trader macro nao superestima headlines isoladas. Se credito nao confirma, se FX "
                            "nao acompanha, se o movimento fica restrito a um bolso de equity, considere movimento fragil, "
                            "falso ou local.\n"
                            "7. Score esperado e impacto esperado nao sao popularidade da noticia. Sao potencial de "
                            "mudar cenario e deslocar o pricing do dia.\n"
                            "8. Se a headline reforca um driver direcional real de risk-on ou risk-off ja ativo no dia, "
                            "nao esconda isso em watch por excesso de conservadorismo. Use buy ou sell quando a assimetria "
                            "de mercado e a transmissao justificarem.\n"
                            "9. Se asset asymmetry, fluxo de participantes e buckets macro apontarem o mesmo lado, "
                            "trate isso como confirmacao direcional. Nao devolva watch por reflexo.\n"
                            "10. Use watch apenas quando houver conflito real entre pernas importantes do mercado "
                            "ou quando o follow-through for claramente insuficiente.\n"
                            "11. Headlines com perfil claro de risk-on ou risk-off na sessao devem receber "
                            "market_regime textual explicito, como risk-on follow-through ou risk-off follow-through.\n\n"
                            "12. Trate iran_negotiation / diplomatic relief como vies primario de buy, ormuz_blockade / "
                            "oil shock como vies primario de sell, e iran_negotiation_setback / hardliner shift / saida do "
                            "negociador moderado / sucessor incerto como vies primario de sell, salvo contradicao ampla do tape.\n"
                            "13. Use o CONTEXT TOKEN PACKET como ancora semantica. Ele resume polaridade, vetores de transmissao, "
                            "gatilhos geopoliticos, contradicoes e regime provavel. Se ele indicar diplomatic setback com hardliner "
                            "pressure, nao trate isso como risk relief.\n"
                            "14. Use a NARRATIVE MEMORY apenas quando houver relacao real de tema, buckets, ativos ou semantica. "
                            "Nao herde automaticamente o regime do dia para uma headline corporativa, single-name, IPO, AI deal, "
                            "earnings ou noticia idiossincratica fora do cluster.\n"
                            "15. Se o historico recente mostrar repeticao de headlines parecidas sem follow-through, trate isso como "
                            "dissolucao de narrativa ou headline repetition without follow-through, e nao como reforco cego.\n\n"
                            "Escala obrigatoria:\n"
                            "- 0-8: technical_noise\n"
                            "- 9-24: secondary_echo\n"
                            "- 25-59: tradable_catalyst\n"
                            "- 60-100: regime_shift\n\n"
                            "Sempre explique por que o score nao e maior. Seja conservador com ruido, mas nao transforme "
                            "catalisador macro relevante em neutro. Em caso realmente marginal, use recommended_action=watch. "
                            "Retorne apenas JSON valido."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Headlines: {json.dumps(events, ensure_ascii=False)}\n\n"
                            f"Primary asset: {primary_asset}\n"
                            f"Focus contracts: {focus_contracts}\n"
                            f"Focus securities: {focus_securities}\n"
                            f"Focus buckets: {focus_buckets}\n"
                            f"Themes: {themes}\n"
                            f"Asset asymmetry: {json.dumps(asset_asymmetry, ensure_ascii=False)}\n"
                            f"Price evolution: {json.dumps(price_evolution, ensure_ascii=False)}\n"
                            f"Participant reactions: {json.dumps(participant_reactions[:6], ensure_ascii=False)}\n"
                            f"Importance score: {importance_score}\n"
                            f"Fallback expected impact: {json.dumps(expected_impact_fallback, ensure_ascii=False)}\n"
                            f"Directional consensus: {json.dumps(directional_consensus, ensure_ascii=False)}\n"
                            f"Context token packet: {json.dumps(context_packet, ensure_ascii=False)}\n"
                            f"Day context: {json.dumps(day_context, ensure_ascii=False)}\n\n"
                            f"Technical operation only: {technical_driver}\n"
                            f"Signal strengths: {json.dumps([event.get('signal_strength') for event in events], ensure_ascii=False)}\n\n"
                            "Retorne JSON com: title, macro_explanation, driver_summary, probable_playbook, "
                            "importance_reason, expected_impact_score, expected_impact_band, expected_impact_reason, "
                            "scenario_classification, market_regime, recommended_action, simulation_prompt_seed. "
                            "expected_impact_score deve ser inteiro de 0 a 100. expected_impact_reason deve citar "
                            "o panorama do dia e dizer por que este driver merece, ou nao merece, deslocar o cenario."
                        ),
                    },
                ],
                temperature=0.1,
                max_tokens=1800,
            )
            merged = {
                **fallback,
                **{key: value for key, value in result.items() if value not in (None, "", [])},
            }
            return self._sanitize_driver_analysis(merged, fallback)
        except Exception as exc:
            logger.warning(f"Driver AI generation failed, using fallback: {exc}")
            return fallback

    def _sanitize_driver_analysis(
        self,
        payload: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        normalized = dict(payload)
        context_packet = fallback.get("agent_context_packet") or {}
        context_semantic = (context_packet.get("semantic") or {}) if isinstance(context_packet, dict) else {}
        context_bias = self._normalize_bias(context_semantic.get("aggregate_bias"))
        context_confidence = int(context_semantic.get("aggregate_confidence") or 0)
        context_regime = context_semantic.get("aggregate_regime")
        text_keys = (
            "title",
            "macro_explanation",
            "driver_summary",
            "probable_playbook",
            "importance_reason",
            "expected_impact_reason",
            "market_regime",
            "simulation_prompt_seed",
        )
        for key in text_keys:
            value = normalized.get(key)
            if not isinstance(value, str) or not value.strip():
                normalized[key] = fallback.get(key)

        normalized["recommended_action"] = self._normalize_bias(normalized.get("recommended_action"))
        fallback_consensus_bias = self._normalize_bias(fallback.get("directional_consensus_bias"))
        fallback_consensus_confidence = int(fallback.get("directional_consensus_confidence") or 0)

        try:
            normalized["expected_impact_score"] = int(float(normalized.get("expected_impact_score")))
        except (TypeError, ValueError):
            normalized["expected_impact_score"] = fallback.get("expected_impact_score")

        valid_bands = {item[1] for item in EXPECTED_IMPACT_BANDS}
        band = str(normalized.get("expected_impact_band") or "").strip().lower()
        normalized["expected_impact_band"] = band if band in valid_bands else fallback.get("expected_impact_band")

        scenario_classification = str(normalized.get("scenario_classification") or "").strip().lower()
        normalized["scenario_classification"] = (
            scenario_classification
            if scenario_classification in valid_bands
            else fallback.get("scenario_classification")
        )
        fallback_action = self._normalize_bias(fallback.get("recommended_action"))
        if (
            normalized["recommended_action"] == "watch"
            and fallback_action in {"buy", "sell"}
            and int(normalized.get("expected_impact_score") or 0) >= 40
            and normalized.get("scenario_classification") in {"tradable_catalyst", "regime_shift"}
        ):
            normalized["recommended_action"] = fallback_action
        if (
            normalized["recommended_action"] == "watch"
            and fallback_consensus_bias in {"buy", "sell"}
            and fallback_consensus_confidence >= 28
            and int(normalized.get("expected_impact_score") or 0) >= 28
        ):
            normalized["recommended_action"] = fallback_consensus_bias
        if (
            normalized["recommended_action"] == "watch"
            and int(normalized.get("expected_impact_score") or 0) >= 55
        ):
            regime_hint = str(normalized.get("market_regime") or fallback.get("market_regime") or "").strip().lower()
            if any(token in regime_hint for token in ("risk-off", "risk off", "hawkish", "tightening", "oil shock")):
                normalized["recommended_action"] = "sell"
            elif any(token in regime_hint for token in ("risk-on", "risk on", "relief", "dovish", "easing")):
                normalized["recommended_action"] = "buy"
        if (
            normalized["recommended_action"] == "watch"
            and context_bias in {"buy", "sell"}
            and context_confidence >= 36
            and int(normalized.get("expected_impact_score") or 0) >= 24
        ):
            normalized["recommended_action"] = context_bias
        if (
            normalized.get("scenario_classification") == "secondary_echo"
            and fallback_consensus_confidence >= 36
            and int(normalized.get("expected_impact_score") or 0) >= 26
        ):
            normalized["scenario_classification"] = "tradable_catalyst"
        if (
            normalized.get("scenario_classification") == "secondary_echo"
            and context_bias in {"buy", "sell"}
            and context_confidence >= 48
            and int(normalized.get("expected_impact_score") or 0) >= 28
        ):
            normalized["scenario_classification"] = "tradable_catalyst"
        if (
            not str(normalized.get("market_regime") or "").strip()
            or str(normalized.get("market_regime") or "").strip().lower() == "intraday macro reaction"
        ) and fallback.get("market_regime"):
            normalized["market_regime"] = fallback.get("market_regime")
        if (
            context_regime
            and str(normalized.get("market_regime") or "").strip().lower() in {"", "intraday macro reaction", "mixed macro tape"}
            and context_bias in {"buy", "sell"}
            and context_confidence >= 34
        ):
            normalized["market_regime"] = context_regime
        regime_implied_action = self._regime_implied_action(
            normalized.get("market_regime") or fallback.get("market_regime"),
            normalized.get("recommended_action"),
        )
        if regime_implied_action in {"buy", "sell"}:
            normalized["recommended_action"] = regime_implied_action
        normalized["agent_context_packet"] = context_packet
        return normalized

    def _attach_related_drivers(self, drivers: List[Dict[str, Any]]) -> None:
        for driver in drivers:
            related = []
            assets = set(driver.get("focus_contracts") or []) | set(driver.get("focus_securities") or [])
            themes = set(driver.get("themes") or [])
            for other in drivers:
                if other.get("driver_id") == driver.get("driver_id"):
                    continue
                score = 0
                score += len(assets & (set(other.get("focus_contracts") or []) | set(other.get("focus_securities") or []))) * 3
                score += len(themes & set(other.get("themes") or [])) * 2
                if abs(self._sort_timestamp(driver.get("last_event_time")) - self._sort_timestamp(other.get("last_event_time"))) <= 60 * 60:
                    score += 1
                if score > 0:
                    related.append((score, other.get("driver_id")))
            related.sort(reverse=True)
            driver["related_driver_ids"] = [item[1] for item in related[:4]]

    def _group_window_seconds(self, themes: List[str]) -> int:
        matched = [THEME_GROUP_WINDOWS_SECONDS.get(theme, 45 * 60) for theme in themes]
        return max(matched) if matched else 45 * 60

    def _event_chain_signature(self, events: List[Dict[str, Any]]) -> str:
        payload = json.dumps(
            [
                {
                    "event_id": item.get("event_id"),
                    "event_time": item.get("event_time"),
                    "impact_score": int(item.get("impact_score") or 0),
                }
                for item in events
            ],
            ensure_ascii=False,
        )
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    def _can_reuse_driver(
        self,
        existing_driver: Optional[Dict[str, Any]],
        event_chain_signature: str,
        last_event_time: Any,
        headline_count: int,
    ) -> bool:
        if not existing_driver:
            return False
        return (
            existing_driver.get("analysis_version") == DRIVER_ANALYSIS_VERSION
            and existing_driver.get("expected_impact_score") is not None
            and bool(existing_driver.get("scenario_classification"))
            and existing_driver.get("day_context_meta") is not None
            and existing_driver.get("event_chain_signature") == event_chain_signature
            and existing_driver.get("last_event_time") == last_event_time
            and int(existing_driver.get("headline_count") or 0) == int(headline_count)
        )

    def _canonical_theme(self, themes: List[str]) -> Optional[str]:
        for theme in themes:
            if theme in THEME_DRIVER_TITLES:
                return theme
        return None

    def _canonical_theme_title(self, theme: Optional[str]) -> Optional[str]:
        if not theme:
            return None
        return THEME_DRIVER_TITLES.get(theme)

    def _canonical_theme_explanation(self, theme: Optional[str]) -> Optional[str]:
        if not theme:
            return None
        return THEME_DRIVER_EXPLANATIONS.get(theme)

    def _event_signature(self, event: Dict[str, Any]) -> str:
        assets = sorted(set((event.get("linked_contracts") or []) + (event.get("linked_securities") or [])))
        buckets = sorted(set(event.get("linked_buckets") or []))
        themes = sorted(set(event.get("themes") or []))
        session_theme = next((theme for theme in themes if theme in THEME_DRIVER_TITLES), None)
        if session_theme:
            return json.dumps({"session_theme": session_theme}, ensure_ascii=False)
        headline_tokens = self._headline_tokens(event.get("headline"))[:4]
        generic_themes_only = bool(themes) and set(themes) <= {"curve_short", "curve_long", "index", "dollar"}
        if assets or buckets or themes:
            if (
                assets
                and not buckets
                and not themes
                and all(
                    isinstance(asset, str)
                    and asset.startswith(("BVMF:WIN", "BVMF:WDO", "BVMF:DI1"))
                    for asset in assets
                )
            ):
                return json.dumps(
                    {
                        "assets": assets,
                        "headline_tokens": self._headline_tokens(event.get("headline"))[:4],
                    },
                    ensure_ascii=False,
                )
            if (not themes and len(buckets) <= 1) or (generic_themes_only and len(set(buckets or themes)) <= 1):
                return json.dumps(
                    {
                        "assets": assets,
                        "buckets": buckets,
                        "themes": themes,
                        "headline_tokens": headline_tokens,
                    },
                    ensure_ascii=False,
                )
            return json.dumps({"assets": assets, "buckets": buckets, "themes": themes}, ensure_ascii=False)
        return "|".join(headline_tokens) or str(event.get("headline") or "")

    def _headline_tokens(self, headline: Any) -> List[str]:
        text = unescape(str(headline or "")).lower()
        tokens = re.findall(r"[a-zA-ZÀ-ÿ0-9]{4,}", text)
        deduped = []
        for token in tokens:
            if token in STOPWORDS or token in deduped:
                continue
            deduped.append(token)
        return deduped[:8]

    def _driver_importance(
        self,
        events: List[Dict[str, Any]],
        asset_asymmetry: List[Dict[str, Any]],
        participant_reactions: List[Dict[str, Any]],
    ) -> int:
        max_impact = max(int(item.get("impact_score") or 0) for item in events)
        asymmetry = max((item.get("asymmetry_score") or 0.0) for item in asset_asymmetry) if asset_asymmetry else 0.0
        participant = max((item.get("activity_score") or 0.0) for item in participant_reactions) if participant_reactions else 0.0
        technical_ratio = (
            sum(1 for item in events if item.get("technical_operation")) / len(events)
            if events else 0.0
        )
        scenario_classes = [str(item.get("scenario_classification") or "") for item in events]
        bucket_breadth = len(
            {
                bucket
                for item in events
                for bucket in (item.get("linked_buckets") or [])
                if bucket
            }
        )
        asset_breadth = len(
            {
                asset
                for item in events
                for asset in ((item.get("linked_contracts") or []) + (item.get("linked_securities") or []))
                if asset
            }
        )
        if technical_ratio >= 0.999:
            technical_score = int(max_impact + (asymmetry * 0.04) + min(participant / 45, 2))
            return max(1, min(3, technical_score))

        score = int(
            (max_impact * 2.6)
            + (min(asymmetry, 45) * 0.65)
            + min(participant / 14, 12)
            + min(len(events) * 2, 8)
        )
        directional_macro = self._events_are_directional_macro_cluster(events)
        if scenario_classes and all(value == "secondary_echo" for value in scenario_classes):
            score = min(score, 40 if directional_macro else 28)
        if scenario_classes and all(value == "technical_noise" for value in scenario_classes):
            score = min(score, 8)
        if "regime_shift" not in scenario_classes and bucket_breadth == 0 and asset_breadth <= 2:
            score = min(score, 34 if directional_macro else 22)
        elif "regime_shift" not in scenario_classes and bucket_breadth <= 1 and asset_breadth <= 3:
            score = min(score, 56 if directional_macro else 42)
        if any(value == "regime_shift" for value in scenario_classes):
            score = min(100, score + (10 if directional_macro else 8))
        elif any(value == "tradable_catalyst" for value in scenario_classes):
            score = min(100, score + (5 if directional_macro else 3))
        consensus = self._directional_consensus(events, asset_asymmetry, participant_reactions)
        if consensus.get("confirmed"):
            score = min(100, score + min(18, int((float(consensus.get("confidence") or 0.0)) * 0.18)))
        elif self._normalize_bias(consensus.get("bias")) in {"buy", "sell"}:
            score = min(100, score + min(8, int((float(consensus.get("confidence") or 0.0)) * 0.08)))
        if technical_ratio > 0:
            score = int(score * max(0.2, 1.0 - technical_ratio * 0.7))
        return min(100, score)

    def _fallback_driver_title(self, events: List[Dict[str, Any]], primary_asset: Optional[str]) -> str:
        if primary_asset:
            return f"{primary_asset} impact driver"
        headline = unescape(str((events[0] if events else {}).get("headline") or "Macro impact driver"))
        return headline[:88]

    def _fallback_macro_explanation(self, events: List[Dict[str, Any]], primary_asset: Optional[str]) -> str:
        if self._is_technical_driver(events):
            return (
                "This driver is mostly a technical liquidity or operational headline. "
                "It belongs on the tape, but it should only matter for macro sentiment if broader cross-asset confirmation shows up."
            )
        headline_count = len(events)
        return (
            f"This driver groups {headline_count} related headlines around {primary_asset or 'the macro tape'}, "
            "combining repeated news flow with immediate market reaction."
        )

    def _fallback_driver_summary(self, events: List[Dict[str, Any]], price_evolution: Dict[str, Any]) -> str:
        timeline = (price_evolution.get("series") or [{}])[0].get("timeline_1m") or []
        if timeline:
            return f"Minute-by-minute evolution is available across {len(timeline)} points after the initial headline cluster."
        return "The driver is active, but minute-by-minute evolution is still being collected."

    def _fallback_playbook(self, asset_asymmetry: List[Dict[str, Any]]) -> str:
        if not asset_asymmetry:
            return "Watch for a clearer directional response before acting."
        top = asset_asymmetry[0]
        return f"Bias is {top.get('bias')} in {top.get('asset')} while this driver remains active."

    def _is_technical_driver(self, events: List[Dict[str, Any]]) -> bool:
        return bool(events) and all(bool(item.get("technical_operation")) for item in events)

    def _driver_signal_strength(self, events: List[Dict[str, Any]]) -> str:
        if not events:
            return "low"
        strengths = [str(item.get("signal_strength") or "low") for item in events]
        if all(value == "technical_low" for value in strengths):
            return "technical_low"
        if any(value == "high" for value in strengths):
            return "high"
        if any(value == "medium" for value in strengths):
            return "medium"
        return strengths[0]

    def _directional_consensus(
        self,
        events: List[Dict[str, Any]],
        asset_asymmetry: List[Dict[str, Any]],
        participant_reactions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        semantic_signal = aggregate_macro_event_tokens(events)
        theme_set = {
            str(theme).strip().lower()
            for event in events
            for theme in (event.get("themes") or [])
            if theme
        }
        focus_buckets = {
            str(bucket).strip().lower()
            for event in events
            for bucket in (event.get("linked_buckets") or [])
            if bucket
        }
        directional_macro = self._events_are_directional_macro_cluster(events)
        semantic_bias = self._normalize_bias(semantic_signal.get("aggregate_bias"))
        semantic_confidence = int(semantic_signal.get("aggregate_confidence") or 0)
        theme_bias = (
            semantic_bias
            if semantic_bias in {"buy", "sell"} and semantic_confidence >= 26
            else self._theme_directional_bias(theme_set)
        )

        buy_score = 0.0
        sell_score = 0.0
        buy_votes = 0
        sell_votes = 0

        for asset in asset_asymmetry[:6]:
            bias = self._normalize_bias(asset.get("bias"))
            weight = min(float(asset.get("asymmetry_score") or 0.0), 28.0)
            if bias == "buy":
                buy_score += weight
                buy_votes += 1
            elif bias == "sell":
                sell_score += weight
                sell_votes += 1

        for participant in participant_reactions[:6]:
            bias = self._normalize_bias(participant.get("market_bias"))
            weight = min((float(participant.get("activity_score") or 0.0) / 2.2), 18.0)
            if bias == "buy":
                buy_score += weight
                buy_votes += 1
            elif bias == "sell":
                sell_score += weight
                sell_votes += 1

        if theme_bias == "buy":
            buy_score += 18.0
            buy_votes += 1
        elif theme_bias == "sell":
            sell_score += 18.0
            sell_votes += 1

        if semantic_bias == "buy":
            buy_score += min(max(semantic_confidence / 2.5, 6.0), 24.0)
            buy_votes += 1
        elif semantic_bias == "sell":
            sell_score += min(max(semantic_confidence / 2.5, 6.0), 24.0)
            sell_votes += 1

        scenario_bonus = 0.0
        for event in events:
            scenario = str(event.get("scenario_classification") or "").strip().lower()
            if scenario == "regime_shift":
                scenario_bonus += 12.0
            elif scenario == "tradable_catalyst":
                scenario_bonus += 6.0
            elif scenario == "secondary_echo":
                scenario_bonus += 2.0

        theme_bonus = 12.0 if theme_set & SESSION_RISK_THEMES else 0.0
        breadth_bonus = min(len(focus_buckets), 3) * 4.0
        directional_bonus = 8.0 if directional_macro else 0.0

        if buy_score > sell_score:
            bias = "buy"
            winning_score = buy_score
            losing_score = sell_score
            winning_votes = buy_votes
        elif sell_score > buy_score:
            bias = "sell"
            winning_score = sell_score
            losing_score = buy_score
            winning_votes = sell_votes
        else:
            bias = "watch"
            winning_score = max(buy_score, sell_score)
            losing_score = min(buy_score, sell_score)
            winning_votes = max(buy_votes, sell_votes)

        margin = max(0.0, winning_score - losing_score)
        confidence = int(min(100.0, winning_score + (margin * 0.75) + scenario_bonus + theme_bonus + breadth_bonus + directional_bonus))
        confirmed = (
            bias in {"buy", "sell"}
            and confidence >= 34
            and (
                margin >= 8.0
                or winning_votes >= 2
                or bool(theme_set & SESSION_RISK_THEMES)
            )
        )

        semantic_regime = str(semantic_signal.get("aggregate_regime") or "").strip()
        if bias == "buy" and semantic_bias == "buy" and semantic_regime:
            market_regime = semantic_regime
        elif bias == "buy":
            market_regime = "risk-on relief" if theme_bias == "buy" else "risk-on follow-through"
        elif bias == "sell" and semantic_bias == "sell" and semantic_regime:
            market_regime = semantic_regime
        elif bias == "sell" and "ormuz_blockade" in theme_set:
            market_regime = "risk-off oil shock"
        elif bias == "sell" and {"curve_short", "curve_long"} & focus_buckets:
            market_regime = "risk-off rates pressure"
        elif bias == "sell":
            market_regime = "risk-off follow-through"
        else:
            market_regime = "mixed macro tape"

        if bias == "watch":
            reason = "Asset asymmetry and participant flow are mixed, so the tape still lacks a clean directional consensus."
        else:
            reason = (
                f"Directional consensus is {bias}, with confidence {confidence}, "
                f"{len(focus_buckets)} macro buckets involved and "
                f"{'session-theme confirmation' if theme_set & SESSION_RISK_THEMES else 'broad tape confirmation'}."
            )
            if theme_bias in {"buy", "sell"}:
                reason = f"{reason} Canonical theme bias is {theme_bias}."
            if semantic_signal.get("aggregate_summary"):
                reason = f"{reason} Semantic packet: {semantic_signal.get('aggregate_summary')}"

        return {
            "bias": bias,
            "confidence": confidence,
            "confirmed": confirmed,
            "market_regime": market_regime,
            "reason": reason,
            "buy_score": round(buy_score, 2),
            "sell_score": round(sell_score, 2),
            "margin": round(margin, 2),
            "semantic_bias": semantic_bias,
            "semantic_confidence": semantic_confidence,
        }

    def _theme_directional_bias(self, theme_set: set[str]) -> str:
        if "iran_negotiation_setback" in theme_set:
            return "sell"
        if "iran_negotiation" in theme_set:
            return "buy"
        if "ormuz_blockade" in theme_set:
            return "sell"
        return "watch"

    def _regime_implied_action(self, regime_hint: Any, fallback_bias: Any = "watch") -> str:
        text = str(regime_hint or "").strip().lower()
        if any(token in text for token in ("risk-off", "risk off", "oil shock", "hawkish", "tightening", "stress")):
            return "sell"
        if any(token in text for token in ("risk-on", "risk on", "relief", "dovish", "easing")):
            return "buy"
        return self._normalize_bias(fallback_bias)

    def _build_simulation_seed(
        self,
        primary_asset: Optional[str],
        events: List[Dict[str, Any]],
        asset_asymmetry: List[Dict[str, Any]],
        context_packet: Optional[Dict[str, Any]] = None,
    ) -> str:
        headlines = "; ".join(unescape(str(item.get("headline") or "")) for item in events[:3])
        top_assets = ", ".join(item.get("asset") for item in asset_asymmetry[:3])
        semantic_summary = (((context_packet or {}).get("semantic") or {}).get("aggregate_summary")) or ""
        return (
            f"Simulate the market around driver {primary_asset or 'macro'} with headlines [{headlines}] "
            f"and focus on assets [{top_assets or primary_asset or 'macro basket'}]. "
            f"Semantic context: {semantic_summary or 'no semantic overlay'}."
        )

    def _driver_id(self, first_event: Dict[str, Any], last_event: Dict[str, Any], primary_asset: Any, themes: List[str], focus_contracts: List[str], focus_securities: List[str]) -> str:
        text = json.dumps(
            {
                "first": first_event.get("event_id"),
                "last": last_event.get("event_id"),
                "asset": primary_asset,
                "themes": themes,
                "contracts": focus_contracts,
                "securities": focus_securities,
            },
            ensure_ascii=False,
        )
        return f"driver_{hashlib.sha1(text.encode('utf-8')).hexdigest()[:16]}"

    def _importance_label(self, score: int) -> str:
        if score >= 75:
            return "high"
        if score >= 50:
            return "medium"
        return "low"

    def _direction_to_bias(self, direction: Optional[str]) -> str:
        value = (direction or "").strip().lower()
        if value in {"buy", "sell", "watch"}:
            return value
        if value == "up":
            return "buy"
        if value == "down":
            return "sell"
        return "watch"

    def _direction_to_bias_for_asset(self, asset: Optional[str], direction: Optional[str]) -> str:
        value = (direction or "").strip().lower()
        if value in {"buy", "sell", "watch"}:
            return value
        if self._is_rate_contract(asset):
            if value == "down":
                return "buy"
            if value == "up":
                return "sell"
            return "watch"
        return self._direction_to_bias(direction)

    def _market_direction_sign_for_contract(self, asset: Optional[str], direction: Optional[str]) -> int:
        bias = self._direction_to_bias_for_asset(asset, direction)
        if bias == "buy":
            return 1
        if bias == "sell":
            return -1
        return 0

    def _is_rate_contract(self, asset: Optional[str]) -> bool:
        return str(asset or "").upper().startswith("BVMF:DI1")

    def _normalize_bias(self, bias: Optional[str]) -> str:
        if isinstance(bias, dict):
            for key in ("bias", "action", "recommended_action", "direction"):
                candidate = bias.get(key)
                if isinstance(candidate, str):
                    bias = candidate
                    break
            else:
                bias = ""
        elif bias is None:
            bias = ""

        value = str(bias).strip().lower()
        if value in {"buy", "sell", "watch"}:
            return value
        return "watch"

    def _parse_iso_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _sort_timestamp(self, value: Any) -> float:
        parsed = self._parse_iso_datetime(value)
        return parsed.timestamp() if parsed else 0.0

    def _to_float(self, value: Any) -> Optional[float]:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
