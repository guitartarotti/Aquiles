from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from ..config import Config
from ..utils.atomic_io import atomic_json_dump
from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .macro_driver_service import PERSISTED_CROSS_ASSET_VERSION, MacroDriverService
from .macro_live_service import MacroStateStore
from .macro_market_overview_service import MacroMarketOverviewService
from .macro_persona_service import MACRO_PERSONA_CATALOG

logger = get_logger("mirofish.macro_thermometer")

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
THERMOMETER_BUCKETS = ("general", "credit", "equity", "fx")
THERMOMETER_SESSION_THEMES = {"ormuz_blockade", "iran_negotiation"}
THERMOMETER_DIRECTIONAL_TERMS = {
    "ormuz", "hormuz", "iran", "hegseth", "oil", "brent", "blockade",
    "bloqueio", "ceasefire", "cessar-fogo", "risk-on", "risk on",
    "risk-off", "risk off", "rba", "bce", "ecb", "boj", "fed",
    "alta de juros", "aumento de juros", "corte de juros", "queda de juros",
    "hawkish", "dovish", "tariff", "sanction", "sanções", "rates",
}


@dataclass(frozen=True)
class ThermometerGroupSpec:
    slug: str
    label: str
    entity_types: Sequence[str]
    bucket_weights: Dict[str, float]
    intensity: float
    style: str


THERMOMETER_GROUPS: Sequence[ThermometerGroupSpec] = (
    ThermometerGroupSpec(
        slug="hedge_funds",
        label="Hedge Funds",
        entity_types=("HedgeFundManager",),
        bucket_weights={"credit": 0.45, "equity": 0.2, "fx": 0.35},
        intensity=1.15,
        style="thesis driven and opportunistic",
    ),
    ThermometerGroupSpec(
        slug="macro_traders",
        label="Macro Traders",
        entity_types=("MacroTrader", "PropTrader", "EventDrivenTrader", "CTAOperator"),
        bucket_weights={"credit": 0.35, "equity": 0.3, "fx": 0.35},
        intensity=1.25,
        style="fast, catalyst sensitive and flow aware",
    ),
    ThermometerGroupSpec(
        slug="options_desks",
        label="Options Desks",
        entity_types=("OptionsTrader",),
        bucket_weights={"credit": 0.3, "equity": 0.4, "fx": 0.3},
        intensity=0.95,
        style="convexity driven and protection focused",
    ),
    ThermometerGroupSpec(
        slug="retail",
        label="Retail",
        entity_types=("RetailPersonality",),
        bucket_weights={"credit": 0.15, "equity": 0.6, "fx": 0.25},
        intensity=1.3,
        style="headline reactive and momentum heavy",
    ),
    ThermometerGroupSpec(
        slug="institutional",
        label="Institutionals",
        entity_types=("PortfolioManager", "InstitutionalAllocator", "FamilyOfficeManager", "TreasuryManager"),
        bucket_weights={"credit": 0.5, "equity": 0.2, "fx": 0.3},
        intensity=0.85,
        style="slower and risk-budget aware",
    ),
    ThermometerGroupSpec(
        slug="research",
        label="Research",
        entity_types=("SellSideStrategist", "MacroResearcher", "QuantTrader"),
        bucket_weights={"credit": 0.34, "equity": 0.33, "fx": 0.33},
        intensity=0.9,
        style="scenario and evidence driven",
    ),
)


class MacroThermometerService:
    """Builds a day thermometer from news, drivers, microstructure and persona groups."""

    def __init__(
        self,
        store: Optional[MacroStateStore] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.store = store or MacroStateStore()
        self._llm_client = llm_client
        self.overview_service = MacroMarketOverviewService(store=self.store, llm_client=llm_client)
        self.driver_service = MacroDriverService(store=self.store, llm_client=llm_client)
        self.cache_path = os.path.join(self.store.root_dir, "thermometer_state.json")

    @property
    def llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def get_thermometer(self, refresh: bool = False) -> Dict[str, Any]:
        state = self.store.read_state()
        snapshot = state.get("snapshot", {}) or {}
        driver_state = self.driver_service.refresh_drivers() if refresh else self.driver_service._load_state(refresh_if_stale=False)
        signature = self._build_signature(snapshot, driver_state)
        cached = self._read_cache()
        if cached and cached.get("source_signature") == signature and cached.get("data"):
            return cached["data"]

        contracts = (((snapshot.get("market") or {}).get("contracts")) or {})
        overview = self.overview_service.get_overview(participant_limit=8, news_limit=8)
        drivers = driver_state.get("drivers", []) or []
        news_feed = driver_state.get("news_feed", []) or []
        timeline = self._build_timeline(news_feed, drivers)
        latest = timeline[-1]["scores"] if timeline else self._empty_scores()
        entity_views = self._build_entity_views(timeline, drivers, contracts)
        trading_plan = self._build_bucket_trade_plan(latest, drivers, contracts)

        result = {
            "generated_at": snapshot.get("generated_at") or driver_state.get("generated_at"),
            "thermometer": {
                "overall": self._build_bucket_status("general", latest.get("general", 0.0)),
                "credit": self._build_bucket_status("credit", latest.get("credit", 0.0)),
                "equity": self._build_bucket_status("equity", latest.get("equity", 0.0)),
                "fx": self._build_bucket_status("fx", latest.get("fx", 0.0)),
                "timeline": timeline,
                "drivers_count": len(drivers),
                "news_count": len(news_feed),
            },
            "entity_views": entity_views,
            "trading_plan": trading_plan,
            "overview_bridge": {
                "implicit_sentiment": (overview.get("overall") or {}).get("implicit_sentiment"),
                "market_bias": (overview.get("overall") or {}).get("market_bias"),
                "summary": (overview.get("overall") or {}).get("summary"),
            },
            "ai_summary": self._build_ai_summary(
                overview=overview,
                latest_scores=latest,
                timeline=timeline,
                entity_views=entity_views,
                trading_plan=trading_plan,
            ),
        }
        self._save_cache({
            "generated_at": result.get("generated_at"),
            "source_signature": signature,
            "data": result,
        })
        return result

    def _build_signature(self, snapshot: Dict[str, Any], driver_state: Dict[str, Any]) -> Dict[str, Any]:
        drivers = driver_state.get("drivers", []) or []
        news_feed = driver_state.get("news_feed", []) or []
        frozen_signature = hashlib.sha1(
            json.dumps(
                [
                    {
                        "driver_id": driver.get("driver_id"),
                        "event_chain_signature": driver.get("event_chain_signature"),
                        "persisted_cross_asset": ((driver.get("persisted_cross_asset") or {}).get("event_chain_signature")),
                        "persisted_version": ((driver.get("persisted_cross_asset") or {}).get("version")),
                    }
                    for driver in drivers
                ],
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        news_feed_signature = hashlib.sha1(
            json.dumps(
                [
                    {
                        "event_id": item.get("event_id"),
                        "driver_id": item.get("driver_id"),
                        "event_time": item.get("event_time"),
                        "impact_score": int(item.get("impact_score") or 0),
                        "macro_scope": item.get("macro_scope"),
                        "macro_transmission_score": float(item.get("macro_transmission_score") or 0.0),
                        "scenario_classification": item.get("scenario_classification"),
                    }
                    for item in news_feed
                ],
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        return {
            "engine_version": "event-local-bias-v7-hf-live",
            "driver_engine_version": driver_state.get("driver_engine_version"),
            "driver_source_signature": driver_state.get("source_signature"),
            "driver_generated_at": driver_state.get("generated_at"),
            "driver_count": len(drivers),
            "news_count": len(news_feed),
            "news_feed_signature": news_feed_signature,
            "frozen_signature": frozen_signature,
        }

    def _read_cache(self) -> Dict[str, Any]:
        if not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception("Failed to load thermometer cache")
            return {}

    def _save_cache(self, state: Dict[str, Any]) -> None:
        try:
            atomic_json_dump(self.cache_path, state)
        except Exception:
            logger.exception("Failed to save thermometer cache")

    def _build_timeline(
        self,
        news_feed: List[Dict[str, Any]],
        drivers: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        driver_map = {item.get("driver_id"): item for item in drivers}
        items = sorted(news_feed, key=lambda item: self._sort_timestamp(item.get("event_time")))
        running = self._empty_scores()
        timeline = []

        for item in items:
            driver = driver_map.get(item.get("driver_id"))
            simulation_context = (driver or {}).get("simulation_context") or {}
            agent_audit = (driver or {}).get("agent_audit_report") or {}
            directional_consensus = agent_audit.get("directional_consensus") or {}
            if not self._should_include_event(item, driver):
                continue
            delta = self._event_delta(item, driver)
            importance_weight = self._driver_importance_weight(event=item, driver=driver)
            for bucket in THERMOMETER_BUCKETS:
                weighted_delta = delta.get(bucket, 0.0) * importance_weight
                running[bucket] = self._clamp((running[bucket] * 0.82) + weighted_delta)

            timeline.append(
                {
                    "event_id": item.get("event_id"),
                    "driver_id": item.get("driver_id"),
                    "time": item.get("event_time"),
                    "headline": item.get("headline"),
                    "posted_by": item.get("posted_by"),
                    "importance": driver.get("importance_label") if driver else self._impact_label(item.get("impact_score")),
                    "delta": {bucket: round(delta.get(bucket, 0.0) * importance_weight, 2) for bucket in THERMOMETER_BUCKETS},
                    "raw_delta": {bucket: round(delta.get(bucket, 0.0), 2) for bucket in THERMOMETER_BUCKETS},
                    "importance_weight": round(importance_weight, 4),
                    "scores": {bucket: round(running[bucket], 2) for bucket in THERMOMETER_BUCKETS},
                    "risk_marker": self._risk_marker(running),
                    "driver_title": item.get("driver_title") or (driver.get("title") if driver else None),
                    "impact_score": int(item.get("impact_score") or 0),
                    "scenario_classification": item.get("scenario_classification") or (driver.get("scenario_classification") if driver else None),
                    "recommended_action": simulation_context.get("recommended_action") or agent_audit.get("recommended_action"),
                    "market_regime": agent_audit.get("market_regime") or simulation_context.get("market_regime"),
                    "driver_importance_score": int((driver or {}).get("importance_score") or item.get("driver_importance_score") or 0),
                    "expected_impact_score": int((driver or {}).get("expected_impact_score") or 0),
                    "directional_consensus_bias": directional_consensus.get("bias"),
                    "directional_consensus_confidence": directional_consensus.get("confidence"),
                    "directional_consensus_reason": directional_consensus.get("reason"),
                    "macro_explanation": agent_audit.get("macro_explanation") or (driver.get("macro_explanation") if driver else None),
                    "driver_summary": agent_audit.get("driver_summary") or (driver.get("driver_summary") if driver else None),
                    "probable_playbook": agent_audit.get("probable_playbook") or (driver.get("probable_playbook") if driver else None),
                    "importance_reason": agent_audit.get("importance_reason") or (driver.get("importance_reason") if driver else None),
                    "expected_impact_reason": agent_audit.get("expected_impact_reason") or (driver.get("expected_impact_reason") if driver else None),
                    "agent_summary": agent_audit.get("expected_impact_reason")
                    or agent_audit.get("importance_reason")
                    or (driver.get("driver_summary") if driver else None),
                }
            )

        return timeline

    def _event_delta(self, event: Dict[str, Any], driver: Optional[Dict[str, Any]]) -> Dict[str, float]:
        frozen_delta = self._frozen_event_delta(event=event, driver=driver)
        if frozen_delta is not None:
            return frozen_delta

        driver_importance = float((driver or {}).get("importance_score") or event.get("driver_importance_score") or 0.0)
        expected_impact = float((driver or {}).get("expected_impact_score") or 0.0)
        scenario = str(event.get("scenario_classification") or (driver or {}).get("scenario_classification") or "secondary_echo")
        impact_score = max(
            float(event.get("impact_score") or 0.0),
            driver_importance,
            expected_impact,
        )
        scope = str(event.get("macro_scope") or "macro")
        transmission_score = float(event.get("macro_transmission_score") or 0.0)
        technical_operation = bool(event.get("technical_operation") or ((driver or {}).get("technical_operation")))
        directional_macro = self._is_directional_macro_event(event=event, driver=driver)
        if scope == "idiosyncratic" or transmission_score < 3.5:
            return self._empty_scores()

        base = min(28.0, 2.5 + (impact_score / 4.0))
        if scenario == "regime_shift":
            base = max(base, 8.0 if directional_macro else 6.0)
        elif scenario == "tradable_catalyst":
            base = max(base, 5.5 if directional_macro else 4.5)

        if expected_impact >= 75:
            base *= 1.20
        elif expected_impact >= 50:
            base *= 1.12
        elif expected_impact >= 25:
            base *= 1.05

        if directional_macro:
            base *= 1.15

        base = min(base, 28.0)
        if technical_operation:
            base = min(base, 0.10)
        if scope == "tracked_security":
            base = min(base, 4.0)
        if transmission_score < 4.5:
            base = min(base, 1.4)

        result = self._empty_scores()
        headline_bias = self._headline_bias(event.get("headline") or "", driver)
        headline_sign = self._headline_direction_sign(headline_bias)
        event_buckets = self._event_buckets(event, driver)

        if headline_sign != 0 and event_buckets:
            for bucket in event_buckets:
                result[bucket] += base * headline_sign
        elif driver:
            for asset in (driver.get("asset_asymmetry") or []):
                bucket = self._asset_bucket(asset.get("asset"))
                if not bucket:
                    continue
                bucket_delta = base * self._asset_direction_sign(asset.get("asset"), asset.get("bias"))
                result[bucket] += bucket_delta

        if result["credit"] == 0 and result["equity"] == 0 and result["fx"] == 0:
            if scope == "macro":
                result["general"] += headline_bias * base * 0.8
        else:
            non_zero = [value for key, value in result.items() if key != "general" and value != 0.0]
            bucket_general = sum(non_zero) / len(non_zero) if non_zero else result["general"]
            if scope == "tracked_security":
                result["general"] = bucket_general * 0.15
            elif headline_sign != 0:
                headline_general = headline_bias * base * 0.8
                result["general"] = (bucket_general * 0.6) + (headline_general * 0.4)
            else:
                result["general"] = bucket_general

        if technical_operation:
            for bucket in THERMOMETER_BUCKETS:
                result[bucket] *= 0.08 if bucket == "general" else 0.12

        for bucket in THERMOMETER_BUCKETS:
            result[bucket] = round(result[bucket], 2)
        return result

    def _frozen_event_delta(self, event: Dict[str, Any], driver: Optional[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        matched = self._frozen_event_payload(event=event, driver=driver)
        if not matched:
            return None

        delta = matched.get("delta") or {}
        return {
            "general": round(float(delta.get("general") or 0.0), 2),
            "credit": round(float(delta.get("credit") or 0.0), 2),
            "equity": round(float(delta.get("equity") or 0.0), 2),
            "fx": round(float(delta.get("fx") or 0.0), 2),
        }

    def _driver_importance_weight(
        self,
        event: Dict[str, Any],
        driver: Optional[Dict[str, Any]],
    ) -> float:
        frozen_payload = self._frozen_event_payload(event=event, driver=driver)
        if frozen_payload and frozen_payload.get("importance_weight") is not None:
            return round(float(frozen_payload.get("importance_weight") or 0.0), 4)

        technical_operation = bool(event.get("technical_operation") or ((driver or {}).get("technical_operation")))
        scope = str(event.get("macro_scope") or "")
        transmission_score = float(event.get("macro_transmission_score") or 0.0)
        signal_strength = str(event.get("signal_strength") or (driver or {}).get("signal_strength") or "low")
        scenario = str(event.get("scenario_classification") or (driver or {}).get("scenario_classification") or "secondary_echo")
        impact_score = int(event.get("impact_score") or 0)
        expected_impact = int((driver or {}).get("expected_impact_score") or 0)
        driver_importance = int((driver or {}).get("importance_score") or event.get("driver_importance_score") or 0)

        if technical_operation or signal_strength == "technical_low" or transmission_score < 3.5:
            return 0.01
        if scope == "tracked_security":
            base = 0.05 + min(impact_score, 4) * 0.018
            if expected_impact >= 35:
                base += 0.03
            if transmission_score < 4.5:
                base = min(base, 0.06)
            return round(max(0.02, min(0.16, base)), 4)

        directional_macro = self._is_directional_macro_event(event=event, driver=driver)
        base = {
            "regime_shift": 0.36,
            "tradable_catalyst": 0.22,
            "secondary_echo": 0.08,
            "technical_noise": 0.02,
        }.get(scenario, 0.06)
        base += min(impact_score, 6) * 0.03

        if signal_strength == "high":
            base += 0.06
        elif signal_strength == "medium":
            base += 0.03

        if expected_impact >= 75:
            base += 0.18
        elif expected_impact >= 50:
            base += 0.12
        elif expected_impact >= 25:
            base += 0.06
        elif expected_impact <= 12:
            base *= 0.72

        if driver_importance >= 70:
            base += 0.08
        elif driver_importance >= 40:
            base += 0.04
        elif driver_importance <= 15:
            base *= 0.85

        if directional_macro:
            base += 0.08
            if scenario == "regime_shift" and expected_impact >= 50:
                base = max(base, 0.34)

        return round(max(0.01, min(0.85, base)), 4)

    def _frozen_event_payload(self, event: Dict[str, Any], driver: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not driver:
            return None

        persisted_root = driver.get("persisted_cross_asset") or {}
        if persisted_root.get("version") != PERSISTED_CROSS_ASSET_VERSION:
            return None

        persisted = (persisted_root.get("analysis") or {})
        timeline = ((persisted.get("headline_thermometer") or {}).get("timeline")) or []
        if not timeline:
            return None

        event_id = event.get("event_id")
        if not event_id:
            return None

        payload = next((item for item in timeline if item.get("event_id") == event_id), None)
        if not payload:
            return None

        targeted_buckets = payload.get("targeted_buckets") or []
        delta = payload.get("delta") or {}
        compatible_delta = any(
            abs(float(delta.get(bucket) or 0.0)) > 0.0
            for bucket in THERMOMETER_BUCKETS
        )
        if not targeted_buckets or not compatible_delta:
            return None

        return payload

    def _should_include_event(self, event: Dict[str, Any], driver: Optional[Dict[str, Any]]) -> bool:
        scope = str(event.get("macro_scope") or "none")
        transmission_score = float(event.get("macro_transmission_score") or 0.0)
        if scope in {"none", "idiosyncratic"}:
            return False
        if transmission_score < 3.5:
            return False

        technical_operation = bool(event.get("technical_operation") or ((driver or {}).get("technical_operation")))
        signal_strength = str(event.get("signal_strength") or (driver or {}).get("signal_strength") or "low")
        scenario = str(event.get("scenario_classification") or (driver or {}).get("scenario_classification") or "secondary_echo")
        impact_score = int(event.get("impact_score") or 0)
        market_relevance = bool(event.get("market_relevance"))
        expected_impact = int((driver or {}).get("expected_impact_score") or 0)
        driver_importance = int((driver or {}).get("importance_score") or 0)
        confirmation_ratio = float(((((driver or {}).get("persisted_cross_asset") or {}).get("analysis") or {}).get("cross_signals") or {}).get("confirmation_ratio") or 0.0)

        if technical_operation:
            return expected_impact >= 45 and confirmation_ratio >= 55
        if scope == "tracked_security":
            return expected_impact >= 35 or driver_importance >= 28
        if scenario == "technical_noise":
            return False
        if scenario in {"regime_shift", "tradable_catalyst"} and impact_score >= 2:
            return True
        if expected_impact >= 18 or driver_importance >= 20:
            return True
        if market_relevance and signal_strength == "high" and impact_score >= 2:
            return True
        return False

    def _build_entity_views(
        self,
        timeline: List[Dict[str, Any]],
        drivers: List[Dict[str, Any]],
        contracts: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        {item.get("driver_id"): item for item in drivers}
        views = []
        for group in THERMOMETER_GROUPS:
            series = []
            score = 0.0
            for item in timeline:
                scores = item.get("scores") or {}
                bucket_score = sum(
                    (scores.get(bucket, 0.0) * weight)
                    for bucket, weight in group.bucket_weights.items()
                )
                score = self._clamp(bucket_score * group.intensity)
                series.append(
                    {
                        "time": item.get("time"),
                        "score": round(score, 2),
                        "action": self._bias_from_score(score),
                        "headline": item.get("headline"),
                    }
                )

            dominant_driver = self._pick_group_driver(group, drivers)
            action = self._bias_from_score(score)
            probability = self._probability_from_score(score)
            focus_asset = self._pick_focus_asset(group, dominant_driver, contracts)
            trade_plan = self._build_trade_plan(focus_asset, action, contracts)
            persona_names = [
                archetype.name
                for archetype in MACRO_PERSONA_CATALOG
                if archetype.entity_type in group.entity_types
            ][:4]
            views.append(
                {
                    "slug": group.slug,
                    "label": group.label,
                    "style": group.style,
                    "current_score": round(score, 2),
                    "current_action": action,
                    "probability": probability,
                    "risk_marker": self._risk_label(score),
                    "dominant_driver_id": dominant_driver.get("driver_id") if dominant_driver else None,
                    "dominant_driver_title": dominant_driver.get("title") if dominant_driver else None,
                    "focus_asset": focus_asset,
                    "trade_plan": trade_plan,
                    "personas": persona_names,
                    "what_they_would_do": self._group_comment(group, action, dominant_driver, trade_plan),
                    "timeline": series,
                }
            )
        return views

    def _build_bucket_trade_plan(
        self,
        scores: Dict[str, float],
        drivers: List[Dict[str, Any]],
        contracts: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        return {
            "general_bias": self._bias_from_score(scores.get("general", 0.0)),
            "general_probability": self._probability_from_score(scores.get("general", 0.0)),
            "credit": self._trade_plan_for_bucket("credit", scores.get("credit", 0.0), drivers, contracts),
            "equity": self._trade_plan_for_bucket("equity", scores.get("equity", 0.0), drivers, contracts),
            "fx": self._trade_plan_for_bucket("fx", scores.get("fx", 0.0), drivers, contracts),
        }

    def _trade_plan_for_bucket(
        self,
        bucket: str,
        score: float,
        drivers: List[Dict[str, Any]],
        contracts: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        bias = self._bias_from_score(score)
        asset = self._pick_bucket_asset(bucket, drivers, contracts)
        trade_plan = self._build_trade_plan(asset, bias, contracts)
        return {
            "bucket": bucket,
            "bias": bias,
            "probability": self._probability_from_score(score),
            "asset": asset,
            "trade_plan": trade_plan,
        }

    def _build_trade_plan(
        self,
        asset: Optional[str],
        bias: str,
        contracts: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        if not asset or asset not in contracts or bias == "watch":
            return None

        contract = contracts.get(asset) or {}
        candles = (((contract.get("ohlcv") or {}).get("candles_1m")) or [])[-30:]
        if not candles:
            return None

        points = []
        for candle in candles:
            close = self._to_float(candle.get("close"))
            high = self._to_float(candle.get("high"))
            low = self._to_float(candle.get("low"))
            volume = self._to_float(candle.get("volume")) or 0.0
            if close is None:
                continue
            points.append({"close": close, "high": high or close, "low": low or close, "volume": volume})
        if not points:
            return None

        last_close = points[-1]["close"]
        day_high = max(point["high"] for point in points)
        day_low = min(point["low"] for point in points)
        avg_range = max(sum((point["high"] - point["low"]) for point in points) / len(points), 0.001)
        precision = 3 if abs(last_close) < 1000 else 1 if abs(last_close) < 10000 else 0

        volume_profile: Dict[float, float] = {}
        for point in points:
            price_key = round(point["close"], precision)
            volume_profile[price_key] = volume_profile.get(price_key, 0.0) + point["volume"]
        poc_price = max(volume_profile.items(), key=lambda item: item[1])[0]

        if bias == "buy":
            entry = max(poc_price, last_close - avg_range * 0.25)
            stop = min(day_low, entry - avg_range * 1.2)
            take = max(day_high, entry + avg_range * 1.8)
        else:
            entry = min(poc_price, last_close + avg_range * 0.25)
            stop = max(day_high, entry + avg_range * 1.2)
            take = min(day_low, entry - avg_range * 1.8)

        return {
            "entry": round(entry, precision),
            "take": round(take, precision),
            "stop": round(stop, precision),
            "poc": round(poc_price, precision),
            "last_close": round(last_close, precision),
            "volume_region": round(poc_price, precision),
        }

    def _build_ai_summary(
        self,
        overview: Dict[str, Any],
        latest_scores: Dict[str, float],
        timeline: List[Dict[str, Any]],
        entity_views: List[Dict[str, Any]],
        trading_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        fallback = self._fallback_ai_summary(overview, latest_scores, entity_views, trading_plan)
        if not Config.MACRO_THERMOMETER_ENABLE_LLM:
            return fallback
        try:
            response = self.llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Voce e um trader macro brasileiro muito experiente, de mesa institucional. Leia um termometro "
                            "intradiario com buckets de credito, equity e cambio, evolucao por noticia e grupos de agentes. "
                            "Separe mudanca real de regime de ruido operacional. Headlines rotineiras de reinvestimento, "
                            "reserve management, repo ou plumbing de liquidez do Fed devem receber peso minimo, a menos que "
                            "haja confirmacao ampla de mercado. Balance sheet, annual report, mark-to-market e unrealized "
                            "loss do Fed tambem devem ter peso quase nulo no sentimento do dia, salvo transmissao clara. "
                            "Retorne apenas JSON."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Overview: {json.dumps(overview, ensure_ascii=False)}\n\n"
                            f"Latest scores: {json.dumps(latest_scores, ensure_ascii=False)}\n\n"
                            f"Timeline tail: {json.dumps(timeline[-8:], ensure_ascii=False)}\n\n"
                            f"Entity views: {json.dumps(entity_views[:6], ensure_ascii=False)}\n\n"
                            f"Trading plan: {json.dumps(trading_plan, ensure_ascii=False)}\n\n"
                            "Retorne JSON com: implicit_sentiment, market_commentary, action_bias, probability, "
                            "why, risks, execution_commentary."
                        ),
                    },
                ],
                temperature=0.2,
                max_tokens=1200,
            )
            return {
                "implicit_sentiment": response.get("implicit_sentiment") or fallback["implicit_sentiment"],
                "market_commentary": response.get("market_commentary") or fallback["market_commentary"],
                "action_bias": self._bias_from_score_string(response.get("action_bias"), fallback["action_bias"]),
                "probability": self._normalize_probability(response.get("probability"), fallback["probability"]),
                "why": response.get("why") or fallback["why"],
                "risks": response.get("risks") or fallback["risks"],
                "execution_commentary": response.get("execution_commentary") or fallback["execution_commentary"],
            }
        except Exception as exc:
            logger.warning(f"Macro thermometer LLM generation failed, using fallback: {exc}")
            return fallback

    def _fallback_ai_summary(
        self,
        overview: Dict[str, Any],
        latest_scores: Dict[str, float],
        entity_views: List[Dict[str, Any]],
        trading_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        action_bias = self._bias_from_score(latest_scores.get("general", 0.0))
        top_groups = ", ".join(item.get("label") for item in entity_views[:3]) or "macro desks"
        return {
            "implicit_sentiment": (overview.get("overall") or {}).get("implicit_sentiment") or self._risk_label(latest_scores.get("general", 0.0)),
            "market_commentary": (
                f"The macro thermometer is {self._risk_label(latest_scores.get('general', 0.0))} with {action_bias} bias. "
                f"The most relevant entity groups right now are {top_groups}."
            ),
            "action_bias": action_bias,
            "probability": self._probability_from_score(latest_scores.get("general", 0.0)),
            "why": [
                f"credit={round(latest_scores.get('credit', 0.0), 2)}",
                f"equity={round(latest_scores.get('equity', 0.0), 2)}",
                f"fx={round(latest_scores.get('fx', 0.0), 2)}",
            ],
            "risks": [
                "A new headline can reset the thermometer quickly if flow confirms it.",
                "Microstructure levels are tactical and can fail when volume migrates to a new region.",
            ],
            "execution_commentary": (
                f"Current top-down idea is {action_bias}. Probability is {self._probability_from_score(latest_scores.get('general', 0.0))}% "
                f"based on the latest cross-asset score and flow alignment."
            ),
        }

    def _pick_group_driver(
        self,
        group: ThermometerGroupSpec,
        drivers: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        best_driver = None
        best_score = -1.0
        for driver in drivers:
            overlap_score = 0.0
            for bucket, weight in group.bucket_weights.items():
                if self._driver_matches_bucket(driver, bucket):
                    overlap_score += weight * 10.0
            overlap_score += float(driver.get("importance_score") or 0.0) / 10.0
            if overlap_score > best_score:
                best_driver = driver
                best_score = overlap_score
        return best_driver

    def _pick_focus_asset(
        self,
        group: ThermometerGroupSpec,
        driver: Optional[Dict[str, Any]],
        contracts: Dict[str, Dict[str, Any]],
    ) -> Optional[str]:
        if not driver:
            return None
        candidates = [item.get("asset") for item in driver.get("asset_asymmetry") or [] if item.get("asset") in contracts]
        if candidates:
            return candidates[0]
        for bucket, _weight in sorted(group.bucket_weights.items(), key=lambda item: item[1], reverse=True):
            asset = self._pick_bucket_asset(bucket, [driver], contracts)
            if asset:
                return asset
        return None

    def _pick_bucket_asset(
        self,
        bucket: str,
        drivers: List[Dict[str, Any]],
        contracts: Dict[str, Dict[str, Any]],
    ) -> Optional[str]:
        preferred = {
            "credit": ("BVMF:DI1F28", "BVMF:DI1F31", "BVMF:DI1F27", "BVMF:DI1F30", "BVMF:DI1F35"),
            "equity": ("BVMF:WINJ26",),
            "fx": ("BVMF:WDOK26",),
        }
        for driver in drivers:
            for asset in driver.get("focus_contracts") or []:
                if asset in preferred.get(bucket, ()) and asset in contracts:
                    return asset
        for asset in preferred.get(bucket, ()):
            if asset in contracts:
                return asset
        return None

    def _group_comment(
        self,
        group: ThermometerGroupSpec,
        action: str,
        dominant_driver: Optional[Dict[str, Any]],
        trade_plan: Optional[Dict[str, Any]],
    ) -> str:
        driver_title = dominant_driver.get("title") if dominant_driver else "the current macro tape"
        if action == "buy":
            return f"{group.label} would likely lean long on {driver_title}, using {trade_plan.get('entry') if trade_plan else 'current microstructure'} as the preferred entry zone."
        if action == "sell":
            return f"{group.label} would likely fade risk on {driver_title}, respecting {trade_plan.get('entry') if trade_plan else 'the active volume region'} as a short trigger."
        return f"{group.label} would stay selective around {driver_title}, waiting for clearer follow-through from flow and microstructure."

    def _driver_matches_bucket(self, driver: Dict[str, Any], bucket: str) -> bool:
        focus_contracts = driver.get("focus_contracts") or []
        asset_asymmetry = driver.get("asset_asymmetry") or []
        for asset in focus_contracts:
            if self._asset_bucket(asset) == bucket:
                return True
        for asset in asset_asymmetry:
            if self._asset_bucket(asset.get("asset")) == bucket:
                return True
        return False

    def _asset_bucket(self, asset: Optional[str]) -> Optional[str]:
        value = str(asset or "").upper()
        if value.startswith("BVMF:DI1"):
            return "credit"
        if value.startswith("BVMF:WDO"):
            return "fx"
        if value.startswith("BVMF:WIN"):
            return "equity"
        if value in {"VALE3", "PETR4", "ITUB4", "BPAC11", "BBDC4"}:
            return "equity"
        return None

    def _asset_direction_sign(self, asset: Optional[str], bias: Optional[str]) -> float:
        normalized = self._bias_from_score_string(bias, "watch")
        if normalized == "watch":
            return 0.0
        sign = 1.0 if normalized == "buy" else -1.0
        if self._asset_bucket(asset) == "fx":
            sign *= -1.0
        return sign

    def _headline_direction_sign(self, bias: float) -> int:
        if bias >= 0.2:
            return 1
        if bias <= -0.2:
            return -1
        return 0

    def _event_buckets(self, event: Dict[str, Any], driver: Optional[Dict[str, Any]]) -> List[str]:
        buckets: List[str] = []

        for bucket in event.get("linked_buckets") or []:
            if bucket in {"curve_short", "curve_long"}:
                buckets.append("credit")
            elif bucket == "index":
                buckets.append("equity")
            elif bucket == "dollar":
                buckets.append("fx")

        for asset in event.get("linked_assets") or []:
            bucket = self._asset_bucket(asset)
            if bucket:
                buckets.append(bucket)

        if not buckets and driver:
            for bucket in driver.get("focus_buckets") or []:
                if bucket in {"curve_short", "curve_long"}:
                    buckets.append("credit")
                elif bucket == "index":
                    buckets.append("equity")
                elif bucket == "dollar":
                    buckets.append("fx")

        return list(dict.fromkeys(bucket for bucket in buckets if bucket in {"credit", "equity", "fx"}))

    def _headline_bias(self, headline: str, driver: Optional[Dict[str, Any]]) -> float:
        text = unescape(str(headline or "")).lower()
        if any(
            token in text
            for token in (
                "reinvestment", "reinvest", "reserve management", "gestao de reservas",
                "compras de reinvestimento", "new york fed", "fed de nova york", "repo",
            )
        ):
            return 0.03
        if any(token in text for token in ("apetite por risco", "risk-on", "risk on", "negoci", "dialog", "progresso", "chegar a um acordo", "rodada de negoci")):
            return 0.55
        if any(token in text for token in ("vendas de imóveis", "housing", "imóveis usados", "growth scare")):
            return -0.45
        if any(token in text for token in ("cessar-fogo", "truce", "calma", "estáveis")):
            return 0.25
        if any(token in text for token in ("oru", "ormuz", "guerra", "bloqueio", "stress")):
            return -0.55
        if driver and driver.get("simulation_context", {}).get("recommended_action") == "buy":
            return 0.35
        if driver and driver.get("simulation_context", {}).get("recommended_action") == "sell":
            return -0.35
        return 0.0

    def _build_bucket_status(self, bucket: str, score: float) -> Dict[str, Any]:
        return {
            "bucket": bucket,
            "score": round(score, 2),
            "marker": self._risk_label(score),
            "bias": self._bias_from_score(score),
            "probability": self._probability_from_score(score),
        }

    def _risk_marker(self, scores: Dict[str, float]) -> Dict[str, str]:
        return {
            "general": self._risk_label(scores.get("general", 0.0)),
            "credit": self._risk_label(scores.get("credit", 0.0)),
            "equity": self._risk_label(scores.get("equity", 0.0)),
            "fx": self._risk_label(scores.get("fx", 0.0)),
        }

    def _risk_label(self, score: float) -> str:
        if score >= 8:
            return "risk-on"
        if score <= -8:
            return "risk-off"
        return "neutral"

    def _bias_from_score(self, score: float) -> str:
        if score >= 5:
            return "buy"
        if score <= -5:
            return "sell"
        return "watch"

    def _is_directional_macro_event(self, event: Dict[str, Any], driver: Optional[Dict[str, Any]]) -> bool:
        themes = {
            str(theme).strip().lower()
            for theme in (event.get("themes") or [])
            if str(theme).strip()
        }
        themes.update(
            str(theme).strip().lower()
            for theme in ((driver or {}).get("themes") or [])
            if str(theme).strip()
        )
        if themes & THERMOMETER_SESSION_THEMES:
            return True

        text = " ".join(
            str(part or "")
            for part in (
                event.get("headline"),
                (driver or {}).get("title"),
                " ".join(themes),
            )
        ).lower()
        return any(term in text for term in THERMOMETER_DIRECTIONAL_TERMS)

    def _bias_from_score_string(self, value: Any, fallback: str) -> str:
        normalized = str(value or fallback).strip().lower()
        if normalized in {"buy", "sell", "watch"}:
            return normalized
        return fallback

    def _probability_from_score(self, score: float) -> int:
        return max(0, min(100, int(abs(score) * 2.2)))

    def _normalize_probability(self, value: Any, fallback: int) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            parsed = int(fallback)
        return max(0, min(100, parsed))

    def _impact_label(self, score: Any) -> str:
        try:
            value = int(score or 0)
        except (TypeError, ValueError):
            value = 0
        if value >= 6:
            return "high"
        if value >= 4:
            return "medium"
        return "low"

    def _sort_timestamp(self, value: Any) -> float:
        parsed = self._parse_iso_datetime(value)
        return parsed.timestamp() if parsed else 0.0

    def _parse_iso_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _clamp(self, value: float, limit: float = 100.0) -> float:
        return max(-limit, min(limit, value))

    def _empty_scores(self) -> Dict[str, float]:
        return {bucket: 0.0 for bucket in THERMOMETER_BUCKETS}

    def _to_float(self, value: Any) -> Optional[float]:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
