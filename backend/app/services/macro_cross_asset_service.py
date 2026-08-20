from __future__ import annotations

import bisect
import json
import os
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import unescape
from statistics import median, pstdev
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from ..utils.atomic_io import atomic_json_dump
from ..utils.logger import get_logger
from .macro_driver_service import PERSISTED_CROSS_ASSET_VERSION, MacroDriverService
from .macro_live_service import MacroIngestionService, MacroStateStore

logger = get_logger("aquiles.macro_cross_asset")

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
CROSS_ASSET_BUCKETS = ("general", "credit", "equity", "commodity", "fx", "rates")
KEY_CONFIRMATION_BUCKETS = ("credit", "equity", "fx", "rates")
CORE_BUCKETS = ("credit", "equity", "commodity", "fx", "rates")
DEFAULT_BUCKET_WEIGHTS: Dict[str, float] = {
    "credit": 0.22,
    "equity": 0.20,
    "commodity": 0.12,
    "fx": 0.18,
    "rates": 0.28,
}


@dataclass(frozen=True)
class CrossAssetSpec:
    asset_id: str
    label: str
    bucket: str
    source: str
    orientation: float
    sensitivity: float
    weight: float
    base_move_floor: float
    max_score: float
    role: str
    note: str


@dataclass(frozen=True)
class EntityLensSpec:
    slug: str
    label: str
    weights: Dict[str, float]
    style: str


ENTITY_LENSES: Sequence[EntityLensSpec] = (
    EntityLensSpec(
        slug="hedge_funds",
        label="Hedge Funds",
        weights={"credit": 0.3, "equity": 0.15, "commodity": 0.05, "fx": 0.2, "rates": 0.3},
        style="balance-sheet sensitive and confirmation driven",
    ),
    EntityLensSpec(
        slug="macro_traders",
        label="Macro Traders",
        weights={"credit": 0.18, "equity": 0.18, "commodity": 0.16, "fx": 0.22, "rates": 0.26},
        style="fast, catalyst aware and cross-market",
    ),
    EntityLensSpec(
        slug="institutionals",
        label="Institutionals",
        weights={"credit": 0.28, "equity": 0.24, "commodity": 0.06, "fx": 0.12, "rates": 0.3},
        style="risk-budget aware and slower moving",
    ),
    EntityLensSpec(
        slug="retail",
        label="Retail",
        weights={"credit": 0.08, "equity": 0.58, "commodity": 0.08, "fx": 0.1, "rates": 0.16},
        style="headline reactive and momentum heavy",
    ),
    EntityLensSpec(
        slug="options_desks",
        label="Options Desks",
        weights={"credit": 0.2, "equity": 0.28, "commodity": 0.12, "fx": 0.12, "rates": 0.28},
        style="volatility, convexity and hedge demand focused",
    ),
)

FOCUS_PROFILE_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "equity": {
        "bucket_weights": {"credit": 0.16, "equity": 0.38, "commodity": 0.08, "fx": 0.14, "rates": 0.24},
        "bucket_emphasis": {"credit": 0.9, "equity": 1.45, "commodity": 0.75, "fx": 0.8, "rates": 1.0},
        "confirmation_buckets": ["equity", "fx", "rates", "credit"],
    },
    "fx": {
        "bucket_weights": {"credit": 0.16, "equity": 0.12, "commodity": 0.08, "fx": 0.34, "rates": 0.30},
        "bucket_emphasis": {"credit": 0.95, "equity": 0.75, "commodity": 0.7, "fx": 1.5, "rates": 1.15},
        "confirmation_buckets": ["fx", "rates", "credit"],
    },
    "rates": {
        "bucket_weights": {"credit": 0.18, "equity": 0.12, "commodity": 0.06, "fx": 0.18, "rates": 0.46},
        "bucket_emphasis": {"credit": 1.0, "equity": 0.7, "commodity": 0.55, "fx": 0.9, "rates": 1.55},
        "confirmation_buckets": ["rates", "credit", "fx"],
    },
    "commodity": {
        "bucket_weights": {"credit": 0.16, "equity": 0.12, "commodity": 0.34, "fx": 0.18, "rates": 0.20},
        "bucket_emphasis": {"credit": 0.95, "equity": 0.75, "commodity": 1.6, "fx": 1.0, "rates": 1.0},
        "confirmation_buckets": ["commodity", "fx", "rates", "credit"],
    },
}

DRIVER_THEME_PROFILES: Dict[str, Dict[str, Any]] = {
    "iran_negotiation": {
        "bucket_weights": {"credit": 0.12, "equity": 0.26, "commodity": 0.08, "fx": 0.22, "rates": 0.32},
        "bucket_emphasis": {"credit": 0.85, "equity": 1.2, "commodity": 0.55, "fx": 1.15, "rates": 1.28},
        "confirmation_buckets": ["equity", "fx", "rates", "credit"],
    },
    "ormuz_blockade": {
        "bucket_weights": {"credit": 0.20, "equity": 0.10, "commodity": 0.28, "fx": 0.20, "rates": 0.22},
        "bucket_emphasis": {"credit": 1.05, "equity": 0.65, "commodity": 1.45, "fx": 1.18, "rates": 1.12},
        "confirmation_buckets": ["commodity", "fx", "credit", "rates"],
    },
    "dollar": {
        "bucket_weights": {"credit": 0.16, "equity": 0.12, "commodity": 0.08, "fx": 0.34, "rates": 0.30},
        "bucket_emphasis": {"credit": 0.95, "equity": 0.75, "commodity": 0.65, "fx": 1.55, "rates": 1.18},
        "confirmation_buckets": ["fx", "rates", "credit"],
    },
    "curve_long": {
        "bucket_weights": {"credit": 0.18, "equity": 0.10, "commodity": 0.06, "fx": 0.18, "rates": 0.48},
        "bucket_emphasis": {"credit": 1.05, "equity": 0.65, "commodity": 0.55, "fx": 0.9, "rates": 1.65},
        "confirmation_buckets": ["rates", "credit", "fx"],
    },
    "curve_short": {
        "bucket_weights": {"credit": 0.16, "equity": 0.10, "commodity": 0.06, "fx": 0.20, "rates": 0.48},
        "bucket_emphasis": {"credit": 0.95, "equity": 0.65, "commodity": 0.5, "fx": 1.0, "rates": 1.6},
        "confirmation_buckets": ["rates", "fx", "credit"],
    },
}

SECURITY_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "PETR4": {
        "bucket": "equity",
        "orientation": 1.0,
        "sensitivity": 7.8,
        "weight": 1.0,
        "base_move_floor": 0.10,
        "max_score": 22.0,
        "role": "lead",
        "note": "Petrobras as commodity-linked equity beta.",
    },
    "VALE3": {
        "bucket": "equity",
        "orientation": 1.0,
        "sensitivity": 7.5,
        "weight": 0.95,
        "base_move_floor": 0.09,
        "max_score": 21.0,
        "role": "lead",
        "note": "Vale as China and commodity beta.",
    },
    "ITUB4": {
        "bucket": "equity",
        "orientation": 1.0,
        "sensitivity": 6.2,
        "weight": 0.72,
        "base_move_floor": 0.07,
        "max_score": 18.0,
        "role": "echo",
        "note": "Domestic bank confirmation.",
    },
    "BPAC11": {
        "bucket": "equity",
        "orientation": 1.0,
        "sensitivity": 6.8,
        "weight": 0.78,
        "base_move_floor": 0.08,
        "max_score": 19.0,
        "role": "echo",
        "note": "Broker-dealer and market beta.",
    },
    "BBDC4": {
        "bucket": "equity",
        "orientation": 1.0,
        "sensitivity": 6.0,
        "weight": 0.68,
        "base_move_floor": 0.07,
        "max_score": 18.0,
        "role": "echo",
        "note": "Domestic bank confirmation.",
    },
}


REFERENCE_OVERRIDES: Dict[str, Dict[str, Any]] = {
        "MES1 Index": {"orientation": 1.0, "sensitivity": 8.6, "weight": 1.08, "base_move_floor": 0.04, "max_score": 25.0, "role": "lead", "note": "Emerging markets equity futures confirmation."},
    "DMA Index": {"orientation": 1.0, "sensitivity": 7.0, "weight": 0.68, "base_move_floor": 0.04, "max_score": 19.0, "role": "echo", "note": "Developed markets breadth."},
    "ESA Index": {"orientation": 1.0, "sensitivity": 8.1, "weight": 0.96, "base_move_floor": 0.04, "max_score": 23.0, "role": "lead", "note": "Large-cap US equity beta."},
    "RTYA Index": {"orientation": 1.0, "sensitivity": 8.4, "weight": 0.92, "base_move_floor": 0.05, "max_score": 23.0, "role": "lead", "note": "Small-cap equity beta."},
    "EMHY CDSI S44 5Y PRC Corp": {"orientation": 1.0, "sensitivity": 10.4, "weight": 1.1, "base_move_floor": 0.03, "max_score": 28.0, "role": "anchor", "note": "EM high-yield credit price confirmation."},
    "CDX EM CDSI S44 5Y PRC Corp": {"orientation": 1.0, "sensitivity": 9.2, "weight": 1.0, "base_move_floor": 0.025, "max_score": 26.0, "role": "anchor", "note": "EM credit price confirmation."},
    "CDX HY CDSI GEN 5Y SPRD Corp": {"orientation": -1.0, "sensitivity": 11.8, "weight": 1.35, "base_move_floor": 0.02, "max_score": 34.0, "role": "anchor", "note": "US HY spread move."},
    "BRAZIL CDS USD SR 3Y D14 Curncy": {"orientation": -1.0, "sensitivity": 12.0, "weight": 1.4, "base_move_floor": 0.018, "max_score": 36.0, "role": "anchor", "note": "Brazil sovereign CDS spread."},
    "EMBIV Index": {"orientation": -1.0, "sensitivity": 8.8, "weight": 0.92, "base_move_floor": 0.03, "max_score": 24.0, "role": "confirmer", "note": "EM volatility and stress signal."},
    ".JPYB U Index": {"orientation": -1.0, "sensitivity": 7.6, "weight": 0.84, "base_move_floor": 0.025, "max_score": 22.0, "role": "confirmer", "note": "JPY safe-haven strength."},
    "CLA Comdty": {"orientation": -0.95, "sensitivity": 6.6, "weight": 1.0, "base_move_floor": 0.08, "max_score": 24.0, "role": "lead", "note": "Oil shock and inflation stress."},
    "SCOA Comdty": {"orientation": -0.55, "sensitivity": 4.2, "weight": 0.55, "base_move_floor": 0.09, "max_score": 14.0, "role": "echo", "note": "Coal as a secondary inflation signal."},
}

POSITIVE_CREDIT_PRICE_MARKERS = (" PRC ", " PRICE ", " TOTAL RETURN ", " TR ")
NEGATIVE_CREDIT_SPREAD_MARKERS = (" SPRD ", " SPREAD ", " CDS USD ", " CDSUSD ", " XOVER ", " EMBIV ")

DEFAULT_CROSS_ASSET_ENGINE_LIMIT = 100


class MacroCrossAssetService:
    """Build a cross-asset reaction engine on top of live macro drivers."""

    def __init__(self, store: Optional[MacroStateStore] = None) -> None:
        self.store = store or MacroStateStore()
        self.ingestion = MacroIngestionService(store=self.store)
        self.driver_service = MacroDriverService(store=self.store)
        self.cache_path = os.path.join(self.store.root_dir, "cross_asset_state.json")

    def get_engine(self, limit: int = DEFAULT_CROSS_ASSET_ENGINE_LIMIT, refresh: bool = False) -> Dict[str, Any]:
        limit = max(1, min(int(limit or DEFAULT_CROSS_ASSET_ENGINE_LIMIT), 120))
        state = self.store.read_state()
        snapshot = state.get("snapshot", {}) or {}
        driver_state = self.driver_service.refresh_drivers() if refresh else self.driver_service._load_state(refresh_if_stale=False)
        signature = self._build_signature(snapshot=snapshot, driver_state=driver_state, limit=limit)
        cached = self._read_cache()
        if cached and cached.get("source_signature") == signature and cached.get("data"):
            cached_data = cached["data"]
            if isinstance(cached_data, dict):
                return cached_data

        market = snapshot.get("market") or {}
        analyzed = self._analyze_drivers(
            drivers=driver_state.get("drivers", []) or [],
            market=market,
            limit=limit,
        )
        timeline = self._build_timeline(analyzed)
        latest_scores = timeline[-1]["scores"] if timeline else self._empty_scores()
        entity_views = self._build_entity_views(analyzed, timeline)
        flattened_insights = self._flatten_insights(analyzed)
        result = {
            "generated_at": snapshot.get("generated_at") or driver_state.get("generated_at"),
            "summary": self._build_summary(latest_scores, analyzed, timeline),
            "timeline": timeline,
            "drivers": list(reversed(analyzed)),
            "insights": flattened_insights,
            "entity_views": entity_views,
            "ai_panorama": self._build_ai_panorama(
                latest_scores=latest_scores,
                analyzed=analyzed,
                timeline=timeline,
                entity_views=entity_views,
                insights=flattened_insights,
            ),
        }
        self._save_cache({
            "generated_at": result.get("generated_at"),
            "source_signature": signature,
            "data": result,
        })
        return result

    def focus_driver(self, driver_id: str, refresh: bool = False) -> Dict[str, Any]:
        if not driver_id:
            raise ValueError("driver_id is required")
        # Reuse the same engine footprint used by the macro dashboard so
        # focus requests hit cache instead of rebuilding a wider engine.
        engine = self.get_engine(limit=DEFAULT_CROSS_ASSET_ENGINE_LIMIT, refresh=refresh)
        driver = next((item for item in engine.get("drivers", []) or [] if item.get("driver_id") == driver_id), None)
        if not driver:
            raise ValueError(f"Cross-asset driver not found: {driver_id}")

        detail = dict(driver)
        if not detail.get("headline_thermometer"):
            detail["headline_thermometer"] = self._build_headline_thermometer(detail)
        if not detail.get("asset_interaction_graph"):
            detail["asset_interaction_graph"] = self._build_asset_interaction_graph(detail)
        if not detail.get("cross_asset_commentary"):
            detail["cross_asset_commentary"] = self._build_driver_cross_asset_commentary(detail)
        return {
            "driver": detail,
            "summary": engine.get("summary") or {},
        }

    def _build_signature(self, snapshot: Dict[str, Any], driver_state: Dict[str, Any], limit: int) -> Dict[str, Any]:
        drivers = driver_state.get("drivers", []) or []
        latest_driver: Dict[str, Any] = max(
            drivers,
            key=lambda item: self._sort_timestamp(item.get("last_event_time")),
            default={},
        )
        return {
            "engine_version": "cross-asset-v4-anchor-time",
            "driver_source_signature": driver_state.get("source_signature"),
            "driver_generated_at": driver_state.get("generated_at"),
            "limit": limit,
            "driver_count": len(drivers),
            "latest_driver_id": latest_driver.get("driver_id"),
            "latest_driver_time": latest_driver.get("last_event_time"),
        }

    def _read_cache(self) -> Dict[str, Any]:
        if not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            logger.exception("Failed to load cross-asset cache")
            return {}

    def _save_cache(self, payload: Dict[str, Any]) -> None:
        try:
            atomic_json_dump(self.cache_path, payload)
        except Exception:
            logger.exception("Failed to save cross-asset cache")

    def _analyze_drivers(
        self,
        drivers: List[Dict[str, Any]],
        market: Dict[str, Any],
        limit: int,
    ) -> List[Dict[str, Any]]:
        history = self._load_history_points(limit=320)
        specs = self._build_asset_specs(market)
        asset_history_stats = self._build_asset_history_stats(history=history, specs=specs)
        ordered = sorted(drivers, key=lambda item: self._sort_timestamp(self._driver_anchor_time(item)))
        selected = ordered[-limit:]
        analyzed = []
        persisted_updates: Dict[str, Dict[str, Any]] = {}
        for driver in selected:
            cached_driver = self._restore_persisted_driver_analysis(driver)
            if cached_driver:
                analyzed.append(cached_driver)
                continue
            analyzed_driver = self._analyze_driver(
                driver=driver,
                market=market,
                history=history,
                specs=specs,
                asset_history_stats=asset_history_stats,
            )
            if analyzed_driver:
                analyzed_driver["headline_thermometer"] = self._build_headline_thermometer(analyzed_driver)
                analyzed_driver["asset_interaction_graph"] = self._build_asset_interaction_graph(analyzed_driver)
                analyzed_driver["cross_asset_commentary"] = self._build_driver_cross_asset_commentary(analyzed_driver)
                analyzed.append(analyzed_driver)
                persisted_updates[analyzed_driver["driver_id"]] = {
                    "event_chain_signature": driver.get("event_chain_signature"),
                    "analysis": analyzed_driver,
                }
        analyzed.sort(key=lambda item: self._sort_timestamp(self._driver_anchor_time(item)))
        if persisted_updates:
            self.driver_service.persist_driver_cross_asset_batch(persisted_updates)
        return analyzed

    def _restore_persisted_driver_analysis(self, driver: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = (driver.get("persisted_cross_asset") or {})
        if payload.get("version") != PERSISTED_CROSS_ASSET_VERSION:
            return None
        if payload.get("event_chain_signature") != driver.get("event_chain_signature"):
            return None

        analysis = payload.get("analysis") or {}
        if not isinstance(analysis, dict) or not analysis.get("driver_id"):
            return None

        restored = deepcopy(analysis)
        restored["driver_id"] = driver.get("driver_id")
        restored["title"] = driver.get("title") or restored.get("title")
        restored["event_time"] = driver.get("first_event_time") or driver.get("last_event_time") or restored.get("event_time")
        restored["last_event_time"] = driver.get("last_event_time") or restored.get("last_event_time")
        restored["anchor_time"] = (
            self._driver_anchor_time(driver)
            or restored.get("anchor_time")
            or restored.get("last_event_time")
            or restored.get("event_time")
        )
        restored["headline_count"] = int(driver.get("headline_count") or restored.get("headline_count") or 0)
        restored["importance_score"] = int(driver.get("importance_score") or restored.get("importance_score") or 0)
        restored["importance_label"] = driver.get("importance_label") or restored.get("importance_label")
        restored["focus_contracts"] = list(driver.get("focus_contracts") or restored.get("focus_contracts") or [])
        restored["focus_securities"] = list(driver.get("focus_securities") or restored.get("focus_securities") or [])
        restored["focus_buckets"] = list((restored.get("driver_profile") or {}).get("focus_buckets") or restored.get("focus_buckets") or [])
        restored["themes"] = list(driver.get("themes") or restored.get("themes") or [])
        restored["headline_updates"] = list(driver.get("headline_updates") or restored.get("headline_updates") or [])
        return restored

    def _load_history_points(self, limit: int = 320) -> List[Dict[str, Any]]:
        raw_history = self.store.list_snapshot_history(limit=limit)
        history: List[Dict[str, Any]] = []
        for record in raw_history:
            generated_at = record.get("generated_at")
            dt = self._parse_datetime(generated_at)
            if not dt:
                continue
            history.append({
                "generated_at": generated_at,
                "dt": dt,
                "market": (((record.get("snapshot") or {}).get("market")) or {}),
            })
        history.sort(key=lambda item: item["dt"])
        return history

    def _build_asset_specs(self, market: Dict[str, Any]) -> Dict[str, CrossAssetSpec]:
        specs: Dict[str, CrossAssetSpec] = {}
        for ticker, contract in ((market.get("contracts") or {}).items()):
            bucket = str(contract.get("bucket") or "other")
            if bucket == "index":
                specs[ticker] = CrossAssetSpec(
                    ticker,
                    ticker,
                    "equity",
                    "aquant_contract",
                    1.0,
                    8.8,
                    1.08,
                    0.03,
                    28.0,
                    "lead",
                    "Local index confirmation and domestic risk appetite.",
                )
            elif bucket == "dollar":
                specs[ticker] = CrossAssetSpec(
                    ticker,
                    ticker,
                    "fx",
                    "aquant_contract",
                    -1.0,
                    8.4,
                    1.12,
                    0.02,
                    30.0,
                    "lead",
                    "USD/BRL stress channel.",
                )
            elif bucket in {"curve_short", "curve_long"}:
                specs[ticker] = CrossAssetSpec(
                    ticker,
                    ticker,
                    "rates",
                    "aquant_contract",
                    -1.0,
                    11.4 if bucket == "curve_long" else 10.0,
                    1.18 if bucket == "curve_long" else 0.98,
                    0.016 if bucket == "curve_long" else 0.018,
                    36.0 if bucket == "curve_long" else 32.0,
                    "anchor" if bucket == "curve_long" else "lead",
                    "Rates confirmation through DI curve repricing.",
                )

        for security, item in ((market.get("reference_assets") or {}).items()):
            bucket = str(item.get("bucket") or item.get("category") or "reference")
            override = REFERENCE_OVERRIDES.get(security, {})
            if bucket not in {"credit", "equity", "commodity", "fx"}:
                continue
            specs[security] = CrossAssetSpec(
                asset_id=security,
                label=str(item.get("label") or security),
                bucket=bucket,
                source="bloomberg_reference",
                orientation=float(override.get("orientation", self._default_reference_orientation(security=security, item=item, bucket=bucket))),
                sensitivity=float(override.get("sensitivity", 8.0)),
                weight=float(override.get("weight", 0.8)),
                base_move_floor=float(override.get("base_move_floor", 0.04)),
                max_score=float(override.get("max_score", 24.0)),
                role=str(override.get("role", "echo")),
                note=str(override.get("note") or self._default_reference_note(security=security, item=item, bucket=bucket)),
            )

        for security, item in ((market.get("securities") or {}).items()):
            security_override = SECURITY_OVERRIDES.get(security)
            if security_override is None:
                continue
            specs[security] = CrossAssetSpec(
                asset_id=security,
                label=str(item.get("label") or security),
                bucket=str(security_override.get("bucket") or "equity"),
                source="security_header",
                orientation=float(security_override.get("orientation", 1.0)),
                sensitivity=float(security_override.get("sensitivity", 6.0)),
                weight=float(security_override.get("weight", 0.7)),
                base_move_floor=float(security_override.get("base_move_floor", 0.08)),
                max_score=float(security_override.get("max_score", 18.0)),
                role=str(security_override.get("role", "echo")),
                note=str(security_override.get("note") or "Security header confirmation."),
            )
        return specs

    def _default_reference_orientation(self, security: str, item: Dict[str, Any], bucket: str) -> float:
        text = f" {security} {item.get('label') or ''} ".upper()
        if bucket == "equity":
            return 1.0
        if bucket in {"fx", "commodity"}:
            return -1.0
        if bucket == "credit":
            if any(marker in text for marker in POSITIVE_CREDIT_PRICE_MARKERS):
                return 1.0
            if any(marker in text for marker in NEGATIVE_CREDIT_SPREAD_MARKERS):
                return -1.0
            return -1.0
        return 1.0

    def _default_reference_note(self, security: str, item: Dict[str, Any], bucket: str) -> str:
        orientation = self._default_reference_orientation(security=security, item=item, bucket=bucket)
        if bucket == "credit":
            if orientation > 0:
                return "Credit price gauge: higher usually confirms risk-on, lower usually confirms stress."
            return "Credit spread/stress gauge: higher usually confirms risk-off, lower usually confirms relief."
        if bucket == "equity":
            return "Equity reference basket signal."
        if bucket == "fx":
            return "FX defensive signal."
        if bucket == "commodity":
            return "Commodity macro transmission signal."
        return f"{bucket} reference basket signal."

    def _build_asset_history_stats(
        self,
        history: List[Dict[str, Any]],
        specs: Dict[str, CrossAssetSpec],
    ) -> Dict[str, Dict[str, Any]]:
        changes_by_asset: Dict[str, List[float]] = defaultdict(list)
        for previous, current in zip(history, history[1:], strict=False):
            previous_market = previous.get("market") or {}
            current_market = current.get("market") or {}
            for asset_id in specs:
                previous_price = self._asset_price(asset_id, previous_market)
                current_price = self._asset_price(asset_id, current_market)
                if previous_price in (None, 0) or current_price is None:
                    continue
                delta_pct = ((current_price - previous_price) / previous_price) * 100.0
                if abs(delta_pct) > 25:
                    continue
                changes_by_asset[asset_id].append(delta_pct)

        stats: Dict[str, Dict[str, Any]] = {}
        for asset_id, spec in specs.items():
            values = changes_by_asset.get(asset_id, [])
            abs_values = [abs(value) for value in values if value is not None]
            stats[asset_id] = {
                "samples": len(values),
                "median_abs_move": round(median(abs_values), 6) if abs_values else spec.base_move_floor,
                "stdev_move": round(pstdev(values), 6) if len(values) >= 2 else 0.0,
            }
        return stats

    def _build_driver_profile(self, driver: Dict[str, Any]) -> Dict[str, Any]:
        themes = [str(theme) for theme in (driver.get("themes") or []) if str(theme)]
        focus_buckets = self._focus_buckets_from_driver(driver)

        weight_profiles = [DEFAULT_BUCKET_WEIGHTS]
        emphasis_profiles = [{bucket: 1.0 for bucket in CORE_BUCKETS}]
        confirmation_candidates: List[str] = list(KEY_CONFIRMATION_BUCKETS)

        for theme in themes:
            profile = DRIVER_THEME_PROFILES.get(theme)
            if not profile:
                continue
            weight_profiles.append(profile.get("bucket_weights") or DEFAULT_BUCKET_WEIGHTS)
            emphasis_profiles.append(profile.get("bucket_emphasis") or {bucket: 1.0 for bucket in CORE_BUCKETS})
            confirmation_candidates.extend(profile.get("confirmation_buckets") or [])

        for bucket in focus_buckets:
            profile = FOCUS_PROFILE_OVERRIDES.get(bucket)
            if not profile:
                continue
            weight_profiles.append(profile.get("bucket_weights") or DEFAULT_BUCKET_WEIGHTS)
            emphasis_profiles.append(profile.get("bucket_emphasis") or {bucket: 1.0 for bucket in CORE_BUCKETS})
            confirmation_candidates.extend(profile.get("confirmation_buckets") or [])

        merged_weights = {
            bucket: sum(float(profile.get(bucket) or 0.0) for profile in weight_profiles) / len(weight_profiles)
            for bucket in CORE_BUCKETS
        }
        merged_emphasis = {
            bucket: sum(float(profile.get(bucket) or 1.0) for profile in emphasis_profiles) / len(emphasis_profiles)
            for bucket in CORE_BUCKETS
        }
        normalized_weights = self._normalize_bucket_weights(merged_weights)

        unique_confirmation = []
        seen = set()
        for bucket in confirmation_candidates:
            if bucket in CORE_BUCKETS and bucket not in seen:
                seen.add(bucket)
                unique_confirmation.append(bucket)

        ordered_confirmation = sorted(
            unique_confirmation,
            key=lambda bucket: normalized_weights.get(bucket, 0.0),
            reverse=True,
        )
        return {
            "themes": themes,
            "focus_buckets": sorted(focus_buckets),
            "bucket_weights": normalized_weights,
            "bucket_emphasis": merged_emphasis,
            "confirmation_buckets": ordered_confirmation[:4] or list(KEY_CONFIRMATION_BUCKETS),
        }

    def _normalize_bucket_weights(self, weights: Dict[str, float]) -> Dict[str, float]:
        total = sum(max(float(weights.get(bucket) or 0.0), 0.0) for bucket in CORE_BUCKETS)
        if total <= 0:
            return dict(DEFAULT_BUCKET_WEIGHTS)
        return {
            bucket: round(max(float(weights.get(bucket) or 0.0), 0.0) / total, 6)
            for bucket in CORE_BUCKETS
        }

    def _focus_buckets_from_driver(self, driver: Dict[str, Any]) -> set[str]:
        buckets: set[str] = set()
        for theme in driver.get("themes") or []:
            profile = DRIVER_THEME_PROFILES.get(str(theme))
            if profile:
                for bucket, weight in (profile.get("bucket_weights") or {}).items():
                    if float(weight or 0.0) >= 0.18:
                        buckets.add(bucket)

        for contract in driver.get("focus_contracts") or []:
            text = str(contract)
            if "WDO" in text:
                buckets.add("fx")
            elif "WIN" in text:
                buckets.add("equity")
            elif "DI1" in text:
                buckets.add("rates")

        for security in driver.get("focus_securities") or []:
            security_text = str(security).upper()
            if security_text in {"PETR4"}:
                buckets.update({"equity", "commodity"})
            else:
                buckets.add("equity")
        return buckets

    def _analyze_driver(
        self,
        driver: Dict[str, Any],
        market: Dict[str, Any],
        history: List[Dict[str, Any]],
        specs: Dict[str, CrossAssetSpec],
        asset_history_stats: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        driver_id = driver.get("driver_id")
        event_dt = self._parse_datetime(driver.get("first_event_time") or driver.get("last_event_time"))
        if not driver_id or not event_dt:
            return None

        driver_profile = self._build_driver_profile(driver)
        baseline, after = self._find_snapshot_window(history, event_dt)
        asset_reactions = []
        handled_assets = set()
        price_series = ((driver.get("price_evolution") or {}).get("series")) or []
        for series_item in price_series:
            ticker = series_item.get("ticker")
            spec = specs.get(ticker)
            if not spec:
                continue
            reaction = self._build_reaction_from_series(
                series_item=series_item,
                spec=spec,
                market=market,
                driver=driver,
                driver_profile=driver_profile,
                asset_history_stats=asset_history_stats,
            )
            if reaction:
                asset_reactions.append(reaction)
                handled_assets.add(spec.asset_id)

        for asset_id, spec in specs.items():
            if asset_id in handled_assets:
                continue
            reaction = self._build_reaction_from_snapshots(
                spec=spec,
                baseline=baseline,
                after=after,
                market=market,
                driver=driver,
                driver_profile=driver_profile,
                asset_history_stats=asset_history_stats,
            )
            if reaction:
                asset_reactions.append(reaction)

        bucket_reactions = self._summarize_buckets(asset_reactions, driver_profile=driver_profile)
        participant_context = self._participant_context(driver.get("participant_reactions") or [])
        cross_signals = self._cross_signals(
            bucket_reactions=bucket_reactions,
            participant_context=participant_context,
            driver_profile=driver_profile,
        )
        insights = self._driver_insights(
            driver=driver,
            bucket_reactions=bucket_reactions,
            cross_signals=cross_signals,
            participant_context=participant_context,
        )
        general_score = self._overall_score(bucket_reactions, driver_profile=driver_profile)
        confidence = self._driver_confidence(
            bucket_reactions=bucket_reactions,
            participant_context=participant_context,
            headline_count=int(driver.get("headline_count") or 0),
        )

        return {
            "driver_id": driver_id,
            "title": driver.get("title"),
            "event_time": driver.get("first_event_time") or driver.get("last_event_time"),
            "last_event_time": driver.get("last_event_time"),
            "anchor_time": self._driver_anchor_time(driver),
            "headline_count": int(driver.get("headline_count") or 0),
            "importance_score": int(driver.get("importance_score") or 0),
            "importance_label": driver.get("importance_label"),
            "recommended_action": driver.get("recommended_action") or self._bias_from_score(general_score),
            "confidence": confidence,
            "focus_contracts": list(driver.get("focus_contracts") or []),
            "focus_securities": list(driver.get("focus_securities") or []),
            "themes": list(driver.get("themes") or []),
            "focus_buckets": list(driver_profile.get("focus_buckets") or []),
            "driver_profile": driver_profile,
            "headline_updates": list(driver.get("headline_updates") or []),
            "participant_context": participant_context,
            "bucket_reactions": bucket_reactions,
            "asset_reactions": sorted(asset_reactions, key=lambda item: abs(item.get("score") or 0.0), reverse=True)[:14],
            "cross_signals": cross_signals,
            "insights": insights,
            "general_score": round(general_score, 2),
            "general_bias": self._bias_from_score(general_score),
        }

    def _build_reaction_from_series(
        self,
        series_item: Dict[str, Any],
        spec: CrossAssetSpec,
        market: Dict[str, Any],
        driver: Dict[str, Any],
        driver_profile: Dict[str, Any],
        asset_history_stats: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        pre_event = series_item.get("pre_event") or {}
        impact_5m = series_item.get("impact_5m") or {}
        impact_point = series_item.get("impact_5m_point") or {}
        pre_price = self._to_float(pre_event.get("close"))
        post_price = self._to_float(impact_point.get("close"))
        delta_pct = self._to_float(impact_5m.get("price_delta_pct"))
        if delta_pct is None and pre_price not in (None, 0) and post_price is not None:
            delta_pct = ((post_price - pre_price) / pre_price) * 100.0
        if delta_pct is None:
            return None

        contract = ((market.get("contracts") or {}).get(spec.asset_id)) or {}
        signal = self.ingestion._build_contract_signal(spec.asset_id, contract)
        score_meta = self._score_reaction(
            delta_pct=delta_pct,
            spec=spec,
            signal=signal,
            driver=driver,
            driver_profile=driver_profile,
            asset_history_stats=asset_history_stats,
            data_quality="high",
        )
        return {
            "asset": spec.asset_id,
            "label": spec.label,
            "bucket": spec.bucket,
            "source": "driver_5m_window",
            "delta_pct": round(delta_pct, 6),
            "score": score_meta["score"],
            "direction": self._bias_from_score(score_meta["score"]),
            "from_time": pre_event.get("time"),
            "to_time": impact_point.get("time"),
            "baseline_price": pre_price,
            "follow_price": post_price,
            "note": spec.note,
            "volume_delta": self._to_float(impact_5m.get("volume_delta")),
            "data_quality": "high",
            "expected_move_pct": score_meta["expected_move_pct"],
            "normalized_move": score_meta["normalized_move"],
            "aggregation_weight": score_meta["aggregation_weight"],
            "relevance_multiplier": score_meta["relevance_multiplier"],
            "history_confidence": score_meta["history_confidence"],
            "role": spec.role,
        }

    def _build_reaction_from_snapshots(
        self,
        spec: CrossAssetSpec,
        baseline: Optional[Dict[str, Any]],
        after: Optional[Dict[str, Any]],
        market: Dict[str, Any],
        driver: Dict[str, Any],
        driver_profile: Dict[str, Any],
        asset_history_stats: Dict[str, Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        baseline_price = self._asset_price(spec.asset_id, (baseline or {}).get("market") or {})
        follow_price = self._asset_price(spec.asset_id, (after or {}).get("market") or {})
        data_quality = "medium"
        if follow_price is None:
            follow_price = self._asset_price(spec.asset_id, market)
            data_quality = "fallback"
        if baseline_price in (None, 0) or follow_price is None:
            return None

        delta_pct = ((follow_price - baseline_price) / baseline_price) * 100.0
        signal = None
        if spec.source == "aquant_contract":
            contract = ((market.get("contracts") or {}).get(spec.asset_id)) or {}
            signal = self.ingestion._build_contract_signal(spec.asset_id, contract)
        score_meta = self._score_reaction(
            delta_pct=delta_pct,
            spec=spec,
            signal=signal,
            driver=driver,
            driver_profile=driver_profile,
            asset_history_stats=asset_history_stats,
            data_quality=data_quality,
        )
        return {
            "asset": spec.asset_id,
            "label": spec.label,
            "bucket": spec.bucket,
            "source": spec.source,
            "delta_pct": round(delta_pct, 6),
            "score": score_meta["score"],
            "direction": self._bias_from_score(score_meta["score"]),
            "from_time": (baseline or {}).get("generated_at"),
            "to_time": (after or {}).get("generated_at"),
            "baseline_price": baseline_price,
            "follow_price": follow_price,
            "note": spec.note,
            "volume_delta": None,
            "data_quality": data_quality,
            "expected_move_pct": score_meta["expected_move_pct"],
            "normalized_move": score_meta["normalized_move"],
            "aggregation_weight": score_meta["aggregation_weight"],
            "relevance_multiplier": score_meta["relevance_multiplier"],
            "history_confidence": score_meta["history_confidence"],
            "role": spec.role,
        }

    def _score_reaction(
        self,
        delta_pct: float,
        spec: CrossAssetSpec,
        driver: Dict[str, Any],
        driver_profile: Dict[str, Any],
        asset_history_stats: Dict[str, Dict[str, Any]],
        signal: Optional[Dict[str, Any]] = None,
        data_quality: str = "medium",
    ) -> Dict[str, Any]:
        history_stats = asset_history_stats.get(spec.asset_id) or {}
        expected_move = max(
            spec.base_move_floor,
            float(history_stats.get("median_abs_move") or 0.0) * 1.15,
            float(history_stats.get("stdev_move") or 0.0) * 0.9,
        )
        normalized_move = (delta_pct / expected_move) if expected_move not in (None, 0) else 0.0

        signal_multiplier = 1.0
        if signal:
            top_5_share = self._to_float(signal.get("top_5_share_percentage")) or 0.0
            volume_ratio = self._to_float(signal.get("volume_ratio_5m")) or 1.0
            book_imbalance = abs(self._to_float(signal.get("book_imbalance")) or 0.0)
            signal_multiplier += min(top_5_share / 100.0, 0.65) * 0.22
            if volume_ratio > 1.0:
                signal_multiplier += min(volume_ratio - 1.0, 3.0) * 0.09
            signal_multiplier += min(book_imbalance, 0.6) * 0.08

        theme_relevance = float((driver_profile.get("bucket_emphasis") or {}).get(spec.bucket, 1.0))
        focus_multiplier = 1.0
        if spec.asset_id in set(driver.get("focus_contracts") or []) or spec.asset_id in set(driver.get("focus_securities") or []):
            focus_multiplier += 0.26
        elif spec.bucket in set(driver_profile.get("focus_buckets") or []):
            focus_multiplier += 0.14

        role_multiplier = 1.0
        if spec.role == "anchor":
            role_multiplier = 1.18
        elif spec.role == "lead":
            role_multiplier = 1.08
        elif spec.role == "confirmer":
            role_multiplier = 0.96
        elif spec.role == "echo":
            role_multiplier = 0.82

        history_confidence = 0.72 + min(float(history_stats.get("samples") or 0.0), 24.0) * 0.01
        data_quality_multiplier = {
            "high": 1.0,
            "medium": 0.92,
            "fallback": 0.78,
        }.get(str(data_quality or "medium"), 0.9)
        technical_multiplier = 1.0
        if driver.get("technical_operation") or str(driver.get("signal_strength") or "") == "technical_low":
            technical_multiplier = 0.08

        importance_score = int(driver.get("importance_score") or 0)
        if importance_score >= 80:
            importance_multiplier = 1.0
        elif importance_score >= 50:
            importance_multiplier = 0.82
        elif importance_score >= 25:
            importance_multiplier = 0.58
        elif importance_score >= 10:
            importance_multiplier = 0.34
        else:
            importance_multiplier = 0.14

        raw_score = (
            normalized_move
            * spec.orientation
            * spec.sensitivity
            * spec.weight
            * theme_relevance
            * focus_multiplier
            * role_multiplier
            * signal_multiplier
            * history_confidence
            * data_quality_multiplier
            * technical_multiplier
            * importance_multiplier
        )
        score = round(self._clamp(raw_score, -spec.max_score, spec.max_score), 2)
        aggregation_weight = round(
            spec.weight * theme_relevance * focus_multiplier * role_multiplier * history_confidence * data_quality_multiplier * technical_multiplier * importance_multiplier,
            4,
        )
        return {
            "score": score,
            "expected_move_pct": round(expected_move, 6),
            "normalized_move": round(normalized_move, 4),
            "aggregation_weight": aggregation_weight,
            "relevance_multiplier": round(theme_relevance * focus_multiplier * technical_multiplier * importance_multiplier, 4),
            "history_confidence": round(history_confidence * data_quality_multiplier, 4),
        }

    def _summarize_buckets(
        self,
        reactions: List[Dict[str, Any]],
        driver_profile: Dict[str, Any],
    ) -> Dict[str, Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for reaction in reactions:
            grouped.setdefault(reaction["bucket"], []).append(reaction)

        bucket_rows: Dict[str, Dict[str, Any]] = {}
        emphasis = driver_profile.get("bucket_emphasis") or {}
        for bucket in CORE_BUCKETS:
            items = grouped.get(bucket, [])
            if not items:
                bucket_rows[bucket] = {
                    "bucket": bucket,
                    "score": 0.0,
                    "bias": "watch",
                    "strength": "missing",
                    "coverage": 0,
                    "weighted_coverage": 0.0,
                    "leaders": [],
                }
                continue

            total_weight = sum(max(float(item.get("aggregation_weight") or 0.0), 0.1) for item in items)
            weighted = sum((item.get("score") or 0.0) * max(float(item.get("aggregation_weight") or 0.0), 0.1) for item in items)
            score = weighted / total_weight if total_weight else 0.0
            score *= float(emphasis.get(bucket) or 1.0) ** 0.2
            bucket_rows[bucket] = {
                "bucket": bucket,
                "score": round(score, 2),
                "bias": self._bias_from_score(score),
                "strength": self._strength_label(score),
                "coverage": len(items),
                "weighted_coverage": round(total_weight, 2),
                "leaders": [
                    {
                        "asset": item.get("asset"),
                        "label": item.get("label"),
                        "score": item.get("score"),
                        "delta_pct": item.get("delta_pct"),
                        "direction": item.get("direction"),
                        "normalized_move": item.get("normalized_move"),
                        "role": item.get("role"),
                    }
                    for item in sorted(items, key=lambda row: abs(row.get("score") or 0.0), reverse=True)[:3]
                ],
            }
        return bucket_rows

    def _cross_signals(
        self,
        bucket_reactions: Dict[str, Dict[str, Any]],
        participant_context: Dict[str, Any],
        driver_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        credit = bucket_reactions.get("credit", {}).get("score", 0.0)
        equity = bucket_reactions.get("equity", {}).get("score", 0.0)
        commodity = bucket_reactions.get("commodity", {}).get("score", 0.0)
        fx = bucket_reactions.get("fx", {}).get("score", 0.0)
        rates = bucket_reactions.get("rates", {}).get("score", 0.0)
        general = self._overall_score(bucket_reactions, driver_profile=driver_profile)
        bucket_weights = driver_profile.get("bucket_weights") or DEFAULT_BUCKET_WEIGHTS
        confirmation_buckets = list(driver_profile.get("confirmation_buckets") or KEY_CONFIRMATION_BUCKETS)

        aligned_weight = 0.0
        expected_weight = 0.0
        diverging_weight = 0.0
        missing_weight = 0.0
        general_sign = self._score_sign(general)
        for bucket in confirmation_buckets:
            score = bucket_reactions.get(bucket, {}).get("score", 0.0)
            importance = max(float(bucket_weights.get(bucket) or 0.0), 0.08)
            expected_weight += importance
            if abs(score) < 3:
                missing_weight += importance
                continue
            if self._score_sign(score) == general_sign and general_sign != 0:
                aligned_weight += importance
            elif general_sign != 0:
                diverging_weight += importance
        confirmation_ratio = round((aligned_weight / expected_weight) * 100.0, 1) if expected_weight else 0.0

        fake_move_risk = 12.0 + missing_weight * 115.0 + diverging_weight * 135.0
        if abs(equity) >= 8 and abs(credit) < 4 and abs(rates) < 4:
            fake_move_risk += 12.0
        if abs(fx) >= 8 and abs(rates) < 4 and abs(credit) < 4:
            fake_move_risk += 9.0
        fake_move_risk = min(fake_move_risk, 95.0)

        anchor_strength = (
            abs(credit) * float(bucket_weights.get("credit") or 0.0)
            + abs(rates) * float(bucket_weights.get("rates") or 0.0)
            + abs(fx) * float(bucket_weights.get("fx") or 0.0)
        )
        absorption_signal = 10.0
        if anchor_strength >= 6.5 and abs(equity) < 5.5:
            absorption_signal += 34.0
        if abs(credit) >= 8 and abs(equity) < 5:
            absorption_signal += 12.0
        if abs(rates) >= 8 and abs(equity) < 5:
            absorption_signal += 18.0
        if (participant_context.get("total_activity") or 0.0) >= 90:
            absorption_signal += 12.0
        if participant_context.get("alignment") == "mixed":
            absorption_signal += 14.0
        absorption_signal = min(absorption_signal, 95.0)

        commodity_transmission = 0.0
        if abs(commodity) >= 6:
            matching = 0
            if self._score_sign(commodity) == self._score_sign(fx) and self._score_sign(commodity) != 0:
                matching += 1
            if self._score_sign(commodity) == self._score_sign(rates) and self._score_sign(commodity) != 0:
                matching += 1
            commodity_transmission = round(35.0 + matching * 22.5, 1)

        if confirmation_ratio >= 72:
            regime = "confirmed"
        elif fake_move_risk >= 60:
            regime = "fragile"
        elif absorption_signal >= 60:
            regime = "absorption"
        else:
            regime = "mixed"

        return {
            "general_score": round(general, 2),
            "general_bias": self._bias_from_score(general),
            "confirmation_ratio": confirmation_ratio,
            "fake_move_risk": round(fake_move_risk, 1),
            "absorption_signal": round(absorption_signal, 1),
            "commodity_transmission": commodity_transmission,
            "regime": regime,
        }

    def _driver_insights(
        self,
        driver: Dict[str, Any],
        bucket_reactions: Dict[str, Dict[str, Any]],
        cross_signals: Dict[str, Any],
        participant_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        insights = []
        credit = bucket_reactions.get("credit", {}).get("score", 0.0)
        equity = bucket_reactions.get("equity", {}).get("score", 0.0)
        commodity = bucket_reactions.get("commodity", {}).get("score", 0.0)
        fx = bucket_reactions.get("fx", {}).get("score", 0.0)
        rates = bucket_reactions.get("rates", {}).get("score", 0.0)
        general_bias = cross_signals.get("general_bias") or "watch"
        driver_id = driver.get("driver_id")
        event_time = driver.get("first_event_time") or driver.get("last_event_time")

        if cross_signals.get("confirmation_ratio", 0.0) >= 72:
            insights.append({
                "driver_id": driver_id,
                "event_time": event_time,
                "kind": "confirmation",
                "title": "Cross-asset confirmation is broad",
                "message": f"Credit, FX and rates are aligned with {general_bias}, reducing the odds of an isolated headline reaction.",
                "bias": general_bias,
                "confidence": round(min(95.0, 58.0 + cross_signals.get("confirmation_ratio", 0.0) * 0.37), 1),
                "bucket_focus": ["credit", "equity", "fx", "rates"],
            })

        if cross_signals.get("fake_move_risk", 0.0) >= 60:
            insights.append({
                "driver_id": driver_id,
                "event_time": event_time,
                "kind": "fragility",
                "title": "Equity move lacks deeper confirmation",
                "message": "Equities moved harder than credit and rates, so the tape may be overstating conviction unless follow-through broadens.",
                "bias": "watch",
                "confidence": round(cross_signals.get("fake_move_risk", 0.0), 1),
                "bucket_focus": ["equity", "credit", "rates"],
            })

        if cross_signals.get("absorption_signal", 0.0) >= 60:
            insights.append({
                "driver_id": driver_id,
                "event_time": event_time,
                "kind": "absorption",
                "title": "Absorption is showing up under the surface",
                "message": "Credit and rates are moving with more conviction than equities while player activity is elevated, which often precedes a delayed tape response.",
                "bias": general_bias,
                "confidence": round(cross_signals.get("absorption_signal", 0.0), 1),
                "bucket_focus": ["credit", "rates", "equity"],
            })

        if abs(commodity) >= 7 and cross_signals.get("commodity_transmission", 0.0) >= 55:
            insights.append({
                "driver_id": driver_id,
                "event_time": event_time,
                "kind": "commodity",
                "title": "Commodity shock is transmitting into macro buckets",
                "message": "The commodity leg is no longer isolated; FX and rates are starting to echo the same inflation or stress impulse.",
                "bias": "sell" if commodity < 0 else "buy",
                "confidence": round(cross_signals.get("commodity_transmission", 0.0), 1),
                "bucket_focus": ["commodity", "fx", "rates"],
            })

        if not insights:
            dispersion = max(abs(credit - equity), abs(equity - fx), abs(credit - rates))
            insights.append({
                "driver_id": driver_id,
                "event_time": event_time,
                "kind": "mixed",
                "title": "Reaction is still mixed",
                "message": "Cross-asset transmission is incomplete. The driver is live, but confirmation is still building asset by asset.",
                "bias": general_bias,
                "confidence": round(min(78.0, 38.0 + dispersion * 1.6 + participant_context.get("total_activity", 0.0) * 0.08), 1),
                "bucket_focus": ["credit", "equity", "fx", "rates"],
            })

        insights.sort(key=lambda item: item.get("confidence") or 0.0, reverse=True)
        return insights[:3]

    def _participant_context(self, participant_reactions: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not participant_reactions:
            return {"total_activity": 0.0, "alignment": "light", "dominant_bias": "watch", "top_players": []}
        total_activity = round(sum(float(item.get("activity_score") or 0.0) for item in participant_reactions[:6]), 2)
        counts: Dict[str, int] = {}
        for item in participant_reactions[:6]:
            bias = str(item.get("market_bias") or "watch")
            counts[bias] = counts.get(bias, 0) + 1
        dominant_bias = max(counts.items(), key=lambda item: item[1])[0] if counts else "watch"
        if len([item for item in counts.values() if item > 0]) >= 3:
            alignment = "mixed"
        elif dominant_bias != "watch" and counts.get(dominant_bias, 0) >= 3:
            alignment = "aligned"
        else:
            alignment = "balanced"
        return {
            "total_activity": total_activity,
            "alignment": alignment,
            "dominant_bias": dominant_bias,
            "top_players": [
                {
                    "broker_name": item.get("broker_name"),
                    "market_bias": item.get("market_bias"),
                    "activity_score": item.get("activity_score"),
                }
                for item in participant_reactions[:4]
            ],
        }

    def _driver_confidence(self, bucket_reactions: Dict[str, Dict[str, Any]], participant_context: Dict[str, Any], headline_count: int) -> float:
        covered = sum(1 for bucket in ("credit", "equity", "commodity", "fx", "rates") if bucket_reactions.get(bucket, {}).get("coverage"))
        alignment_bonus = 10.0 if participant_context.get("alignment") == "aligned" else 4.0 if participant_context.get("alignment") == "balanced" else 0.0
        return round(min(95.0, 34.0 + covered * 9.0 + min(headline_count, 4) * 6.0 + alignment_bonus), 1)

    def _flatten_insights(self, analyzed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        flattened = []
        for driver in analyzed:
            for insight in driver.get("insights") or []:
                flattened.append({
                    **insight,
                    "driver_title": driver.get("title"),
                    "importance_score": driver.get("importance_score"),
                    "regime": (driver.get("cross_signals") or {}).get("regime"),
                })
        flattened.sort(
            key=lambda item: (float(item.get("confidence") or 0.0), self._sort_timestamp(item.get("event_time"))),
            reverse=True,
        )
        return flattened[:24]

    def _build_timeline(self, analyzed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        running = self._empty_scores()
        timeline = []
        ordered = sorted(analyzed, key=lambda item: self._sort_timestamp(self._driver_anchor_time(item)))
        for driver in ordered:
            reactions = driver.get("bucket_reactions") or {}
            for bucket in CORE_BUCKETS:
                raw_score = float((reactions.get(bucket) or {}).get("score") or 0.0)
                running[bucket] = self._clamp((running[bucket] * 0.62) + raw_score, -100.0, 100.0)
            running["general"] = self._overall_score({
                "credit": {"score": running["credit"]},
                "equity": {"score": running["equity"]},
                "commodity": {"score": running["commodity"]},
                "fx": {"score": running["fx"]},
                "rates": {"score": running["rates"]},
            }, driver_profile=driver.get("driver_profile"))
            timeline.append({
                "driver_id": driver.get("driver_id"),
                "time": self._driver_anchor_time(driver),
                "first_event_time": driver.get("event_time"),
                "last_event_time": driver.get("last_event_time"),
                "title": driver.get("title"),
                "scores": {bucket: round(running[bucket], 2) for bucket in CROSS_ASSET_BUCKETS},
                "current_driver_scores": {
                    bucket: round(float((reactions.get(bucket) or {}).get("score") or 0.0), 2)
                    for bucket in CORE_BUCKETS
                },
                "regime": (driver.get("cross_signals") or {}).get("regime"),
                "confirmation_ratio": (driver.get("cross_signals") or {}).get("confirmation_ratio"),
                "fake_move_risk": (driver.get("cross_signals") or {}).get("fake_move_risk"),
                "absorption_signal": (driver.get("cross_signals") or {}).get("absorption_signal"),
                "headline_count": driver.get("headline_count"),
                "insight_title": ((driver.get("insights") or [{}])[0]).get("title"),
            })
        return timeline

    def _build_entity_views(self, analyzed: List[Dict[str, Any]], timeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        views = []
        driver_map = {driver.get("driver_id"): driver for driver in analyzed}
        for lens in ENTITY_LENSES:
            score = 0.0
            series = []
            for item in timeline:
                raw = item.get("current_driver_scores") or {}
                step = 0.0
                for bucket, weight in lens.weights.items():
                    step += float(raw.get(bucket) or 0.0) * weight
                score = self._clamp((score * 0.58) + step, -100.0, 100.0)
                series.append({
                    "time": item.get("time"),
                    "driver_id": item.get("driver_id"),
                    "score": round(score, 2),
                    "action": self._bias_from_score(score),
                    "title": item.get("title"),
                })
            dominant = max(
                series,
                key=lambda row: abs(float(row.get("score") or 0.0)),
                default={},
            )
            dominant_driver = driver_map.get(dominant.get("driver_id"))
            current_action = self._bias_from_score(score)
            views.append({
                "slug": lens.slug,
                "label": lens.label,
                "style": lens.style,
                "current_score": round(score, 2),
                "current_action": current_action,
                "probability": self._probability_from_score(score),
                "dominant_driver_id": dominant_driver.get("driver_id") if dominant_driver else None,
                "dominant_driver_title": dominant_driver.get("title") if dominant_driver else None,
                "what_they_would_do": self._entity_comment(lens, current_action, dominant_driver),
                "timeline": series,
            })
        return views

    def _build_summary(self, latest_scores: Dict[str, float], analyzed: List[Dict[str, Any]], timeline: List[Dict[str, Any]]) -> Dict[str, Any]:
        latest = timeline[-1] if timeline else {}
        confirmation_values = [float((driver.get("cross_signals") or {}).get("confirmation_ratio") or 0.0) for driver in analyzed]
        fake_move_values = [float((driver.get("cross_signals") or {}).get("fake_move_risk") or 0.0) for driver in analyzed]
        return {
            "overall": self._bucket_status("general", latest_scores.get("general", 0.0)),
            "credit": self._bucket_status("credit", latest_scores.get("credit", 0.0)),
            "equity": self._bucket_status("equity", latest_scores.get("equity", 0.0)),
            "commodity": self._bucket_status("commodity", latest_scores.get("commodity", 0.0)),
            "fx": self._bucket_status("fx", latest_scores.get("fx", 0.0)),
            "rates": self._bucket_status("rates", latest_scores.get("rates", 0.0)),
            "confirmation_ratio": round(sum(confirmation_values) / len(confirmation_values), 1) if confirmation_values else 0.0,
            "fake_move_risk": round(sum(fake_move_values) / len(fake_move_values), 1) if fake_move_values else 0.0,
            "drivers_count": len(analyzed),
            "latest_regime": latest.get("regime") or "mixed",
        }

    def _build_ai_panorama(
        self,
        latest_scores: Dict[str, float],
        analyzed: List[Dict[str, Any]],
        timeline: List[Dict[str, Any]],
        entity_views: List[Dict[str, Any]],
        insights: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        latest_driver = analyzed[-1] if analyzed else {}
        bucket_rank = sorted(
            [
                ("credit", abs(latest_scores.get("credit", 0.0))),
                ("equity", abs(latest_scores.get("equity", 0.0))),
                ("commodity", abs(latest_scores.get("commodity", 0.0))),
                ("fx", abs(latest_scores.get("fx", 0.0))),
                ("rates", abs(latest_scores.get("rates", 0.0))),
            ],
            key=lambda item: item[1],
            reverse=True,
        )
        leader = bucket_rank[0][0] if bucket_rank else "general"
        laggard = bucket_rank[-1][0] if bucket_rank else "general"
        action_bias = self._bias_from_score(latest_scores.get("general", 0.0))
        confidence = round(min(95.0, 42.0 + (abs(latest_scores.get("general", 0.0)) * 0.45) + ((latest_driver.get("cross_signals") or {}).get("confirmation_ratio", 0.0) * 0.18)), 1)
        sentiment = self._sentiment_label(latest_scores.get("general", 0.0))
        regime = (timeline[-1] or {}).get("regime") if timeline else "mixed"
        top_entity = max(entity_views, key=lambda item: abs(item.get("current_score") or 0.0), default={})
        top_insight = insights[0] if insights else {}
        return {
            "implicit_sentiment": sentiment,
            "action_bias": action_bias,
            "probability": self._probability_from_score(latest_scores.get("general", 0.0)),
            "confidence": confidence,
            "regime": regime,
            "leading_bucket": leader,
            "lagging_bucket": laggard,
            "focus_driver_id": latest_driver.get("driver_id"),
            "focus_driver_title": latest_driver.get("title"),
            "market_commentary": f"{leader.title()} is leading the tape while {laggard.title()} is lagging. The aggregate tone is {sentiment}, with {action_bias} bias.",
            "divergence_commentary": f"Fake-move risk is sitting near {round((latest_driver.get('cross_signals') or {}).get('fake_move_risk', 0.0), 1)}%, while cross-asset confirmation is {round((latest_driver.get('cross_signals') or {}).get('confirmation_ratio', 0.0), 1)}%.",
            "entity_commentary": f"{top_entity.get('label') or 'Macro desks'} are the most tilted lens right now, reading the tape as {top_entity.get('current_action') or 'watch'}.",
            "top_call": top_insight.get("message") or "Cross-asset transmission is still building.",
        }

    def _build_headline_thermometer(self, driver: Dict[str, Any]) -> Dict[str, Any]:
        updates = sorted(driver.get("headline_updates") or [], key=lambda item: self._sort_timestamp(item.get("event_time")))
        if not updates:
            return {"timeline": [], "latest": self._empty_scores()}

        bucket_reactions = driver.get("bucket_reactions") or {}
        driver_profile = driver.get("driver_profile") or self._build_driver_profile(driver)
        previous_timeline = (
            ((((driver.get("persisted_cross_asset") or {}).get("analysis")) or {}).get("headline_thermometer") or {}).get("timeline")
        ) or []
        previous_by_event = {
            item.get("event_id"): item
            for item in previous_timeline
            if item.get("event_id")
        }
        running = self._empty_scores()
        timeline = []
        for update in updates:
            event_id = update.get("event_id")
            previous = previous_by_event.get(event_id)
            if previous:
                restored_scores = previous.get("scores") or {}
                for bucket in CROSS_ASSET_BUCKETS:
                    running[bucket] = float(restored_scores.get(bucket) or 0.0)
                timeline.append({
                    **previous,
                    "time": update.get("event_time") or previous.get("time"),
                    "headline": unescape(str(update.get("headline") or previous.get("headline") or "")),
                    "posted_by": update.get("posted_by") or previous.get("posted_by"),
                    "impact_score": int(update.get("impact_score") or previous.get("impact_score") or 0),
                    "technical_operation": bool(update.get("technical_operation") or previous.get("technical_operation")),
                    "scenario_classification": update.get("scenario_classification") or previous.get("scenario_classification"),
                    "signal_strength": update.get("signal_strength") or previous.get("signal_strength"),
                })
                continue

            targeted_buckets = self._headline_bucket_targets(update, driver)
            bias = self._headline_bias(update.get("headline") or "", driver)
            sign = self._headline_direction_sign(bias)
            technical_operation = bool(update.get("technical_operation") or driver.get("technical_operation"))
            impact_scale = min(1.75, 0.55 + (float(update.get("impact_score") or 0.0) / 20.0))
            if technical_operation:
                impact_scale = min(impact_scale, 0.08)
            event_delta = self._empty_scores()

            for bucket in CORE_BUCKETS:
                base_score = float((bucket_reactions.get(bucket) or {}).get("score") or 0.0)
                emphasis = float((driver_profile.get("bucket_emphasis") or {}).get(bucket, 1.0))
                target_multiplier = emphasis if bucket in targeted_buckets else 0.2 * emphasis if base_score != 0 else 0.0
                delta = base_score * impact_scale * 0.11 * target_multiplier
                if sign != 0 and bucket in targeted_buckets:
                    directional_push = sign * emphasis * (1.6 + min(float(update.get("impact_score") or 0.0), 25.0) * 0.18)
                    if technical_operation:
                        directional_push *= 0.04
                    delta += directional_push
                event_delta[bucket] = delta
                running[bucket] = self._clamp((running[bucket] * 0.52) + delta, -100.0, 100.0)

            running["general"] = self._overall_score({
                "credit": {"score": running["credit"]},
                "equity": {"score": running["equity"]},
                "commodity": {"score": running["commodity"]},
                "fx": {"score": running["fx"]},
                "rates": {"score": running["rates"]},
            }, driver_profile=driver_profile)
            event_delta["general"] = self._overall_score({
                "credit": {"score": event_delta["credit"]},
                "equity": {"score": event_delta["equity"]},
                "commodity": {"score": event_delta["commodity"]},
                "fx": {"score": event_delta["fx"]},
                "rates": {"score": event_delta["rates"]},
            }, driver_profile=driver_profile)

            timeline.append({
                "event_id": event_id,
                "time": update.get("event_time"),
                "headline": unescape(str(update.get("headline") or "")),
                "posted_by": update.get("posted_by"),
                "impact_score": int(update.get("impact_score") or 0),
                "technical_operation": technical_operation,
                "scenario_classification": update.get("scenario_classification"),
                "signal_strength": update.get("signal_strength"),
                "importance_weight": round(self._headline_thermometer_weight(update, driver), 4),
                "delta": {bucket: round(event_delta[bucket], 2) for bucket in CROSS_ASSET_BUCKETS},
                "scores": {bucket: round(running[bucket], 2) for bucket in CROSS_ASSET_BUCKETS},
                "targeted_buckets": targeted_buckets,
                "event_bias": "buy" if sign > 0 else "sell" if sign < 0 else "watch",
            })

        return {
            "timeline": timeline,
            "latest": {bucket: round(running[bucket], 2) for bucket in CROSS_ASSET_BUCKETS},
        }

    def _headline_thermometer_weight(self, update: Dict[str, Any], driver: Dict[str, Any]) -> float:
        technical_operation = bool(update.get("technical_operation") or driver.get("technical_operation"))
        scope = str(update.get("macro_scope") or "macro")
        transmission_score = float(update.get("macro_transmission_score") or 0.0)
        scenario = str(update.get("scenario_classification") or driver.get("scenario_classification") or "secondary_echo")
        signal_strength = str(update.get("signal_strength") or driver.get("signal_strength") or "low")
        impact_score = int(update.get("impact_score") or 0)
        expected_impact = int(driver.get("expected_impact_score") or 0)

        if technical_operation or transmission_score < 3.5:
            return 0.01
        if scope == "tracked_security":
            base = 0.05 + min(impact_score, 4) * 0.018
            if expected_impact >= 40:
                base += 0.03
            if transmission_score < 4.5:
                base = min(base, 0.06)
            return round(self._clamp(base, 0.02, 0.16), 4)

        base = {
            "regime_shift": 0.28,
            "tradable_catalyst": 0.16,
            "secondary_echo": 0.07,
            "technical_noise": 0.02,
        }.get(scenario, 0.06)
        base += min(impact_score, 4) * 0.025

        if signal_strength == "high":
            base += 0.05
        elif signal_strength == "medium":
            base += 0.02

        if expected_impact >= 75:
            base += 0.12
        elif expected_impact >= 50:
            base += 0.08
        elif expected_impact >= 25:
            base += 0.04
        elif expected_impact <= 12:
            base *= 0.72

        return round(self._clamp(base, 0.01, 0.55), 4)

    def _headline_bucket_targets(self, update: Dict[str, Any], driver: Dict[str, Any]) -> List[str]:
        if bool(update.get("idiosyncratic_only")) or float(update.get("macro_transmission_score") or 0.0) < 3.5:
            return []
        text = unescape(str(update.get("headline") or "")).lower()
        buckets: List[str] = []
        for theme in driver.get("themes") or []:
            buckets.extend(self._theme_buckets(theme))

        if any(token in text for token in ("juros", "yield", "treasury", "copom", "fed", "boe", "bce", "di1")):
            buckets.append("rates")
        if any(token in text for token in ("bolsa", "equity", "s&p", "dow", "russell", "ibov", "ações", "acoes", "risk-on", "risk on")):
            buckets.append("equity")
        if any(token in text for token in ("dólar", "dolar", "usd", "fx", "real", "jpy", "iene")):
            buckets.append("fx")
        if any(token in text for token in ("petróleo", "petroleo", "oil", "brent", "energia", "coal", "gás", "gas")):
            buckets.append("commodity")
        if any(token in text for token in ("cds", "credit", "hy", "embi", "spread", "default", "crédito", "credito")):
            buckets.append("credit")

        for bucket in driver.get("focus_buckets") or []:
            if bucket == "index":
                buckets.append("equity")
            elif bucket == "dollar":
                buckets.append("fx")
            elif bucket in {"curve_short", "curve_long"}:
                buckets.append("rates")

        for asset in driver.get("asset_reactions") or []:
            if asset.get("direction") != "watch" and abs(float(asset.get("score") or 0.0)) >= 8:
                buckets.append(asset.get("bucket"))

        return list(dict.fromkeys(bucket for bucket in buckets if bucket in {"credit", "equity", "commodity", "fx", "rates"}))

    def _theme_buckets(self, theme: str) -> List[str]:
        mapping = {
            "ormuz_blockade": ["commodity", "fx", "rates", "equity"],
            "iran_negotiation": ["equity", "fx", "rates"],
            "dollar": ["fx", "rates"],
            "index": ["equity"],
        }
        return mapping.get(str(theme or "").lower(), [])

    def _headline_bias(self, headline: str, driver: Dict[str, Any]) -> float:
        text = unescape(str(headline or "")).lower()
        if any(token in text for token in ("apetite por risco", "risk-on", "risk on", "negoci", "dialog", "progresso", "acordo", "cessar-fogo", "truce", "calma")):
            return 0.55
        if any(token in text for token in ("ormuz", "hormuz", "bloqueio", "guerra", "stress", "tensão", "tensao", "portos iranianos")):
            return -0.55
        if any(token in text for token in ("yield", "hawkish", "higher for longer", "mais aperto", "juros mais altos")):
            return -0.35
        if driver.get("recommended_action") == "buy":
            return 0.25
        if driver.get("recommended_action") == "sell":
            return -0.25
        return 0.0

    def _headline_direction_sign(self, bias: float) -> int:
        if bias >= 0.2:
            return 1
        if bias <= -0.2:
            return -1
        return 0

    def _build_asset_interaction_graph(self, driver: Dict[str, Any]) -> Dict[str, Any]:
        nodes = [
            {"id": driver.get("driver_id"), "label": driver.get("title"), "type": "driver", "weight": driver.get("confidence") or 0},
        ]
        edges = []
        bucket_reactions = driver.get("bucket_reactions") or {}
        active_buckets = [
            (bucket, row)
            for bucket, row in bucket_reactions.items()
            if (row.get("coverage") or 0) > 0 or abs(float(row.get("score") or 0.0)) >= 4
        ]

        for bucket, row in active_buckets:
            bucket_id = f"bucket::{bucket}"
            nodes.append({
                "id": bucket_id,
                "label": bucket,
                "type": "bucket",
                "weight": abs(float(row.get("score") or 0.0)),
                "bias": row.get("bias"),
            })
            relation = "pushes" if row.get("bias") != "watch" else "tests"
            edges.append({
                "source": driver.get("driver_id"),
                "target": bucket_id,
                "relation": relation,
                "strength": round(abs(float(row.get("score") or 0.0)), 2),
            })

        seen_assets = set()
        for reaction in (driver.get("asset_reactions") or [])[:10]:
            asset_id = f"asset::{reaction.get('asset')}"
            if asset_id in seen_assets:
                continue
            seen_assets.add(asset_id)
            nodes.append({
                "id": asset_id,
                "label": reaction.get("label") or reaction.get("asset"),
                "type": "asset",
                "bucket": reaction.get("bucket"),
                "weight": abs(float(reaction.get("score") or 0.0)),
                "bias": reaction.get("direction"),
            })
            edges.append({
                "source": f"bucket::{reaction.get('bucket')}",
                "target": asset_id,
                "relation": "leads" if abs(float(reaction.get("score") or 0.0)) >= 12 else "echoes",
                "strength": round(abs(float(reaction.get("score") or 0.0)), 2),
            })

        for index, (bucket, row) in enumerate(active_buckets):
            for other_bucket, other_row in active_buckets[index + 1:]:
                pair_relation = self._pair_bucket_relation(
                    float(row.get("score") or 0.0),
                    float(other_row.get("score") or 0.0),
                )
                if not pair_relation:
                    continue
                edges.append({
                    "source": f"bucket::{bucket}",
                    "target": f"bucket::{other_bucket}",
                    "relation": pair_relation,
                    "strength": round((abs(float(row.get("score") or 0.0)) + abs(float(other_row.get("score") or 0.0))) / 2.0, 2),
                })

        return {"nodes": nodes, "edges": edges}

    def _pair_bucket_relation(self, left_score: float, right_score: float) -> Optional[str]:
        left_sign = self._score_sign(left_score)
        right_sign = self._score_sign(right_score)
        if left_sign == 0 and right_sign == 0:
            return None
        if left_sign == right_sign and left_sign != 0:
            return "confirms"
        if left_sign == 0 or right_sign == 0:
            return "lags"
        return "diverges"

    def _build_driver_cross_asset_commentary(self, driver: Dict[str, Any]) -> str:
        cross = driver.get("cross_signals") or {}
        if cross.get("regime") == "confirmed":
            return "This driver is traveling well across markets. The move is no longer just a headline; the tape is confirming it."
        if cross.get("regime") == "fragile":
            return "This driver still looks fragile. Equities moved, but deeper buckets have not fully endorsed the move yet."
        if cross.get("regime") == "absorption":
            return "This driver is showing absorption: credit or rates are moving first while equities still look late."
        return "This driver is still building transmission. Watch for the next headline to see whether other buckets confirm or fade it."

    def _entity_comment(self, lens: EntityLensSpec, action: str, dominant_driver: Optional[Dict[str, Any]]) -> str:
        if not dominant_driver:
            return f"{lens.label} stay in watch mode until more buckets confirm the move."
        regime = (dominant_driver.get("cross_signals") or {}).get("regime") or "mixed"
        title = dominant_driver.get("title") or "the current driver"
        if action == "buy":
            return f"{lens.label} would lean with {title}, but only because the {regime} regime is giving them enough confirmation."
        if action == "sell":
            return f"{lens.label} would fade risk through {title}, with the {regime} regime reinforcing the defensive read."
        return f"{lens.label} would keep a tighter leash on risk because {title} is still reading as {regime}."

    def _find_snapshot_window(self, history: List[Dict[str, Any]], event_dt: datetime) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if not history:
            return None, None
        timestamps = [item["dt"] for item in history]
        baseline_index = bisect.bisect_right(timestamps, event_dt) - 1
        baseline = history[baseline_index] if baseline_index >= 0 else None
        target_dt = event_dt + timedelta(minutes=5)
        after_index = bisect.bisect_left(timestamps, target_dt)
        if after_index >= len(history) and baseline_index + 1 < len(history):
            after_index = baseline_index + 1
        after = history[after_index] if 0 <= after_index < len(history) else None
        return baseline, after

    def _asset_price(self, asset_id: str, market: Dict[str, Any]) -> Optional[float]:
        contracts = market.get("contracts") or {}
        if asset_id in contracts:
            contract = contracts.get(asset_id) or {}
            latest_window = ((contract.get("ohlcv") or {}).get("latest_window")) or {}
            price = self._to_float(latest_window.get("close"))
            if price is not None:
                return price
            candles = ((contract.get("ohlcv") or {}).get("candles_1m")) or []
            if candles:
                return self._to_float((candles[-1] or {}).get("close"))
            return None
        reference_assets = market.get("reference_assets") or {}
        if asset_id in reference_assets:
            return self._to_float((reference_assets.get(asset_id) or {}).get("price"))
        securities = market.get("securities") or {}
        if asset_id in securities:
            return self._to_float((securities.get(asset_id) or {}).get("price"))
        return None

    def _overall_score(self, bucket_reactions: Dict[str, Dict[str, Any]], driver_profile: Optional[Dict[str, Any]] = None) -> float:
        weights = (driver_profile or {}).get("bucket_weights") or DEFAULT_BUCKET_WEIGHTS
        total = 0.0
        used = 0.0
        for bucket, weight in weights.items():
            score = float((bucket_reactions.get(bucket) or {}).get("score") or 0.0)
            total += score * weight
            used += weight
        if used == 0:
            return 0.0
        return round(self._clamp(total / used, -100.0, 100.0), 2)

    def _bucket_status(self, bucket: str, score: float) -> Dict[str, Any]:
        return {
            "bucket": bucket,
            "score": round(score, 2),
            "bias": self._bias_from_score(score),
            "marker": self._risk_label(score),
            "probability": self._probability_from_score(score),
            "strength": self._strength_label(score),
        }

    def _probability_from_score(self, score: float) -> int:
        normalized = min(abs(float(score or 0.0)), 100.0)
        return int(round(min(98.0, 48.0 + normalized * 0.46)))

    def _bias_from_score(self, score: float) -> str:
        if score >= 6:
            return "buy"
        if score <= -6:
            return "sell"
        return "watch"

    def _risk_label(self, score: float) -> str:
        if score >= 10:
            return "risk-on"
        if score <= -10:
            return "risk-off"
        return "mixed"

    def _strength_label(self, score: float) -> str:
        absolute = abs(float(score or 0.0))
        if absolute >= 18:
            return "strong"
        if absolute >= 8:
            return "building"
        if absolute > 0:
            return "light"
        return "missing"

    def _sentiment_label(self, score: float) -> str:
        if score >= 18:
            return "constructive"
        if score >= 6:
            return "fragile risk-on"
        if score <= -18:
            return "defensive"
        if score <= -6:
            return "fragile risk-off"
        return "mixed"

    def _score_sign(self, score: float) -> int:
        if score > 2:
            return 1
        if score < -2:
            return -1
        return 0

    def _empty_scores(self) -> Dict[str, float]:
        return {bucket: 0.0 for bucket in CROSS_ASSET_BUCKETS}

    def _driver_anchor_time(self, driver: Dict[str, Any]) -> Any:
        return (
            driver.get("anchor_time")
            or driver.get("last_event_time")
            or driver.get("event_time")
            or driver.get("first_event_time")
        )

    def _sort_timestamp(self, value: Any) -> float:
        dt = self._parse_datetime(value)
        return dt.timestamp() if dt else 0.0

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=LOCAL_TZ)
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    def _to_float(self, value: Any) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except Exception:
            return None

    def _clamp(self, value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, float(value)))
