from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import unescape
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from ..utils.llm_client import LLMClient
from ..utils.logger import get_logger
from .macro_live_service import MacroIngestionService, MacroStateStore

logger = get_logger("aquiles.macro_overview")

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
BUCKET_LABELS = {
    "index": "index",
    "dollar": "dollar",
    "curve_short": "short rates",
    "curve_long": "long rates",
    "other": "other",
}


class MacroMarketOverviewService:
    """Build a day-level macro dashboard from the latest snapshot."""

    def __init__(
        self,
        store: Optional[MacroStateStore] = None,
        llm_client: Optional[LLMClient] = None,
    ):
        self.store = store or MacroStateStore()
        self.ingestion = MacroIngestionService(store=self.store)
        self._llm_client = llm_client

    @property
    def llm(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = LLMClient()
        return self._llm_client

    def get_overview(self, participant_limit: int = 12, news_limit: int = 5) -> Dict[str, Any]:
        state = self.store.read_state()
        snapshot = state.get("snapshot", {}) or {}
        market = snapshot.get("market", {}) or {}
        contracts = market.get("contracts", {}) or {}
        securities = market.get("securities", {}) or {}
        reference_assets = market.get("reference_assets", {}) or {}

        contract_rows = self._build_contract_rows(contracts)
        security_rows = self._build_security_rows(securities)
        reference_rows = self._build_reference_asset_rows(reference_assets)
        bucket_rows = self._build_bucket_rows(contract_rows)
        participant_rows = self._build_participant_rows(contracts, contract_rows)
        news_rows = self._build_news_rows(
            snapshot_news=(snapshot.get("news", {}) or {}).get("items", []) or [],
            recent_events=state.get("recent_events", []) or [],
            contracts=contracts,
        )
        overall = self._build_overall_sentiment(contract_rows, security_rows, bucket_rows)

        return {
            "generated_at": snapshot.get("generated_at"),
            "overall": overall,
            "asset_behavior": {
                "contracts": contract_rows,
                "securities": security_rows,
                "reference_assets": reference_rows,
                "buckets": bucket_rows,
                "volume": self._build_volume_summary(contract_rows),
            },
            "participants": {
                "count": len(participant_rows),
                "items": participant_rows[: max(1, min(int(participant_limit or 12), 40))],
            },
            "impactful_news": news_rows[: max(1, min(int(news_limit or 5), 20))],
            "ai_commentary": self._build_ai_commentary(
                overall=overall,
                contracts=contract_rows[:6],
                securities=security_rows[:5],
                reference_assets=reference_rows[:8],
                participants=participant_rows[:8],
                news_rows=news_rows[:5],
            ),
        }

    def _build_contract_rows(self, contracts: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for ticker, contract in contracts.items():
            signal = self.ingestion._build_contract_signal(ticker, contract)
            latest = ((contract.get("ohlcv") or {}).get("latest_window")) or {}
            previous = ((contract.get("ohlcv") or {}).get("previous_window")) or {}
            latest_volume = self._to_float(latest.get("volume"))
            previous_volume = self._to_float(previous.get("volume"))
            volume_ratio = None
            if latest_volume is not None and previous_volume not in (None, 0):
                volume_ratio = latest_volume / previous_volume

            score = self._contract_sentiment_score(ticker, signal, volume_ratio)
            market_bias = self._contract_market_bias(ticker, signal.get("direction_5m"))
            rows.append(
                {
                    "ticker": ticker,
                    "bucket": contract.get("bucket") or "other",
                    "bucket_label": BUCKET_LABELS.get(contract.get("bucket") or "other", "other"),
                    "direction_5m": signal.get("direction_5m") or "flat",
                    "market_bias": market_bias,
                    "net_change_pct_5m": self._to_float(signal.get("net_change_pct_5m")),
                    "volume_5m": latest_volume,
                    "previous_volume_5m": previous_volume,
                    "volume_ratio_5m": volume_ratio,
                    "top_5_share_percentage": self._to_float(signal.get("top_5_share_percentage")),
                    "book_imbalance": self._to_float(signal.get("book_imbalance")),
                    "sentiment_score": score,
                    "implicit_sentiment": self._sentiment_label(score),
                    "summary": self._contract_summary(ticker, signal, latest_volume, volume_ratio),
                }
            )
        rows.sort(
            key=lambda item: (
                abs(item.get("sentiment_score") or 0.0),
                abs(item.get("net_change_pct_5m") or 0.0),
            ),
            reverse=True,
        )
        return rows

    def _build_security_rows(self, securities: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for symbol, security in securities.items():
            change_pct = self._to_float(security.get("change_percent"))
            rows.append(
                {
                    "ticker": symbol,
                    "name": security.get("name") or symbol,
                    "price": self._to_float(security.get("price")),
                    "change_percent": change_pct,
                    "market_bias": "buy" if (change_pct or 0.0) > 0 else "sell" if (change_pct or 0.0) < 0 else "watch",
                    "implicit_sentiment": self._sentiment_label((change_pct or 0.0) * 8.0),
                    "updated_at": security.get("updated_at"),
                }
            )
        rows.sort(key=lambda item: abs(item.get("change_percent") or 0.0), reverse=True)
        return rows

    def _build_reference_asset_rows(self, reference_assets: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for security, item in reference_assets.items():
            change_pct = self._to_float(item.get("change_percent"))
            rows.append(
                {
                    "ticker": security,
                    "label": item.get("label") or security,
                    "category": item.get("category") or "reference",
                    "bucket": item.get("bucket") or "reference",
                    "price": self._to_float(item.get("price")),
                    "change_percent": change_pct,
                    "market_bias": "buy" if (change_pct or 0.0) > 0 else "sell" if (change_pct or 0.0) < 0 else "watch",
                    "implicit_sentiment": self._sentiment_label((change_pct or 0.0) * 8.0),
                    "ok": bool(item.get("ok")),
                    "updated_at": item.get("updated_at"),
                    "summary": self._reference_asset_summary(item),
                }
            )
        rows.sort(
            key=lambda item: (not item.get("ok"), abs(item.get("change_percent") or 0.0)),
            reverse=False,
        )
        return rows

    def _build_bucket_rows(self, contract_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for row in contract_rows:
            grouped[row.get("bucket") or "other"].append(row)

        results: List[Dict[str, Any]] = []
        for bucket, rows in grouped.items():
            avg_score = self._avg(row.get("sentiment_score") for row in rows)
            results.append(
                {
                    "bucket": bucket,
                    "bucket_label": BUCKET_LABELS.get(bucket, bucket),
                    "contract_count": len(rows),
                    "average_move_5m": self._avg(row.get("net_change_pct_5m") for row in rows),
                    "average_sentiment_score": avg_score,
                    "average_top_5_share_percentage": self._avg(row.get("top_5_share_percentage") for row in rows),
                    "dominant_direction": self._dominant_direction([row.get("direction_5m") for row in rows]),
                    "market_bias": self._bias_from_score(avg_score),
                    "implicit_sentiment": self._sentiment_label(avg_score),
                }
            )
        results.sort(key=lambda item: abs(item.get("average_sentiment_score") or 0.0), reverse=True)
        return results

    def _build_participant_rows(
        self,
        contracts: Dict[str, Dict[str, Any]],
        contract_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        contract_map = {row["ticker"]: row for row in contract_rows}
        participant_map: Dict[str, Dict[str, Any]] = {}

        for ticker, contract in contracts.items():
            contract_row = contract_map.get(ticker)
            if not contract_row:
                continue
            move_pct = abs(contract_row.get("net_change_pct_5m") or 0.0)
            direction_sign = 1 if contract_row.get("market_bias") == "buy" else -1 if contract_row.get("market_bias") == "sell" else 0
            for row in (contract.get("participants") or {}).get("all_rows", []):
                broker_name = row.get("broker_name")
                if not broker_name:
                    continue
                percentage = self._to_float(row.get("percentage_float"))
                if percentage is None:
                    percentage = self._to_float(row.get("percentage"))
                percentage = percentage or 0.0
                impact = percentage * max(move_pct * 100.0, 1.0)
                exposure = {
                    "ticker": ticker,
                    "bucket": contract_row.get("bucket"),
                    "direction_5m": contract_row.get("direction_5m"),
                    "market_bias": contract_row.get("market_bias"),
                    "net_change_pct_5m": contract_row.get("net_change_pct_5m"),
                    "share_percentage": round(percentage, 2),
                    "impact_score": round(impact, 2),
                }

                broker = participant_map.setdefault(
                    broker_name,
                    {
                        "broker_name": broker_name,
                        "broker_id": row.get("broker_id"),
                        "sentiment_score": 0.0,
                        "activity_score": 0.0,
                        "contracts": [],
                        "buckets": set(),
                    },
                )
                broker["sentiment_score"] += direction_sign * impact
                broker["activity_score"] += impact
                broker["contracts"].append(exposure)
                broker["buckets"].add(contract_row.get("bucket") or "other")

        participants = []
        for broker in participant_map.values():
            exposures = sorted(broker["contracts"], key=lambda item: item.get("impact_score") or 0.0, reverse=True)
            score = broker.get("sentiment_score") or 0.0
            bias = self._bias_from_score(score)
            participants.append(
                {
                    "broker_name": broker["broker_name"],
                    "broker_id": broker.get("broker_id"),
                    "market_bias": bias,
                    "implicit_sentiment": self._sentiment_label(score),
                    "sentiment_score": round(score, 2),
                    "activity_score": round(broker.get("activity_score") or 0.0, 2),
                    "contracts_count": len(exposures),
                    "bucket_focus": sorted(broker["buckets"]),
                    "dominant_assets": [item["ticker"] for item in exposures[:3]],
                    "top_exposures": exposures[:4],
                    "general_comment": self._participant_comment(
                        broker["broker_name"],
                        bias,
                        self._sentiment_label(score),
                        exposures[:3],
                    ),
                }
            )
        participants.sort(key=lambda item: (item.get("activity_score") or 0.0, abs(item.get("sentiment_score") or 0.0)), reverse=True)
        return participants

    def _build_news_rows(
        self,
        snapshot_news: List[Dict[str, Any]],
        recent_events: List[Dict[str, Any]],
        contracts: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        signal_map = {
            ticker: self.ingestion._build_contract_signal(ticker, contract)
            for ticker, contract in contracts.items()
        }
        snapshot_news_by_id = {
            item.get("event_id"): item for item in snapshot_news if item.get("event_id")
        }

        today = datetime.now(LOCAL_TZ).date()
        day_events = []
        for event in recent_events:
            event_time = self._parse_iso_datetime(event.get("event_time"))
            if event_time and event_time.astimezone(LOCAL_TZ).date() == today:
                day_events.append(event)
        if not day_events:
            day_events = list(recent_events[:20])

        results = []
        for event in day_events:
            current = snapshot_news_by_id.get(event.get("event_id"))
            if current:
                merged = {**event, **current}
            else:
                detected = self.ingestion._detect_news_targets(event, signal_map)
                merged = {
                    **event,
                    "linked_contracts": detected["contracts"],
                    "linked_securities": detected["securities"],
                    "themes": detected["themes"],
                    "market_relevance": detected["market_relevant"],
                    "impact_score": self.ingestion._score_news_impact(event, detected),
                }

            linked_assets = list(
                dict.fromkeys(
                    (merged.get("linked_contracts") or [])
                    + (merged.get("linked_securities") or [])
                )
            )
            impact_score = int(merged.get("impact_score") or 0)
            results.append(
                {
                    "event_id": merged.get("event_id"),
                    "headline": unescape(str(merged.get("headline") or "")),
                    "posted_by": merged.get("posted_by"),
                    "relevance": merged.get("relevance"),
                    "event_time": merged.get("event_time"),
                    "impact_score": impact_score,
                    "impact_label": self._impact_label(impact_score),
                    "market_relevance": bool(merged.get("market_relevance")),
                    "linked_assets": linked_assets,
                    "themes": merged.get("themes") or [],
                    "summary": self._news_summary(merged, linked_assets),
                }
            )

        results.sort(
            key=lambda item: (
                1 if item.get("market_relevance") else 0,
                self._normalize_confidence(item.get("impact_score"), 0),
                self._relevance_rank(str(item.get("relevance") or "")),
                self._sort_timestamp(item.get("event_time")),
            ),
            reverse=True,
        )
        return results

    def _build_overall_sentiment(
        self,
        contract_rows: List[Dict[str, Any]],
        security_rows: List[Dict[str, Any]],
        bucket_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        contract_score = self._avg(row.get("sentiment_score") for row in contract_rows)
        security_score = self._avg((row.get("change_percent") or 0.0) * 8.0 for row in security_rows)
        total_score = round((contract_score * 0.7) + (security_score * 0.3), 2)

        index_bias = self._bucket_bias(bucket_rows, "index")
        dollar_bias = self._bucket_bias(bucket_rows, "dollar")
        short_rates_bias = self._bucket_bias(bucket_rows, "curve_short")
        long_rates_bias = self._bucket_bias(bucket_rows, "curve_long")
        equity_bias = self._bias_from_score(self._avg((row.get("change_percent") or 0.0) * 8.0 for row in security_rows))

        if index_bias == "buy" and equity_bias == "buy" and dollar_bias == "sell":
            implicit_sentiment = "constructive"
        elif index_bias == "sell" and equity_bias == "sell" and dollar_bias == "buy":
            implicit_sentiment = "defensive"
        else:
            implicit_sentiment = "mixed"

        volume = self._build_volume_summary(contract_rows)
        return {
            "market_bias": self._bias_from_score(total_score),
            "implicit_sentiment": implicit_sentiment,
            "score": total_score,
            "sentiment_shift": self._describe_sentiment_shift(contract_rows, volume),
            "summary": (
                f"Index is {index_bias}, dollar is {dollar_bias}, short rates are {short_rates_bias}, "
                f"long rates are {long_rates_bias}, and equities look {equity_bias}."
            ),
            "drivers": [
                f"index={index_bias}",
                f"dollar={dollar_bias}",
                f"short_rates={short_rates_bias}",
                f"long_rates={long_rates_bias}",
                f"equities={equity_bias}",
                f"volume={volume.get('pace_label')}",
            ],
        }

    def _build_volume_summary(self, contract_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        latest_total = sum(row.get("volume_5m") or 0.0 for row in contract_rows)
        previous_total = sum(row.get("previous_volume_5m") or 0.0 for row in contract_rows)
        ratio = (latest_total / previous_total) if previous_total else None

        if ratio is None:
            pace_label = "unknown"
        elif ratio >= 1.2:
            pace_label = "accelerating"
        elif ratio <= 0.8:
            pace_label = "cooling"
        else:
            pace_label = "stable"

        strongest = sorted(
            contract_rows,
            key=lambda item: abs((item.get("volume_ratio_5m") or 1.0) - 1.0),
            reverse=True,
        )[:4]
        return {
            "latest_total_5m": round(latest_total, 2),
            "previous_total_5m": round(previous_total, 2),
            "ratio": round(ratio, 3) if ratio is not None else None,
            "pace_label": pace_label,
            "strongest_changes": [
                {
                    "ticker": item.get("ticker"),
                    "volume_5m": item.get("volume_5m"),
                    "previous_volume_5m": item.get("previous_volume_5m"),
                    "volume_ratio_5m": item.get("volume_ratio_5m"),
                }
                for item in strongest
            ],
        }

    def _build_ai_commentary(
        self,
        overall: Dict[str, Any],
        contracts: List[Dict[str, Any]],
        securities: List[Dict[str, Any]],
        reference_assets: List[Dict[str, Any]],
        participants: List[Dict[str, Any]],
        news_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        fallback = self._fallback_ai_commentary(overall, contracts, reference_assets, participants, news_rows)
        if not contracts:
            return fallback

        try:
            response = self.llm.chat_json(
                [
                    {
                        "role": "system",
                        "content": (
                            "Voce e um trader macro brasileiro muito experiente, de mesa institucional. Leia o overview "
                            "do dia e devolva JSON puro com leitura do mercado, mudanca de sentimento, comportamento de "
                            "ativos/volume e noticias-chave. Diferencie mudanca real de regime de headlines operacionais, "
                            "tecnicas ou de plumbing de liquidez. Noticias de balance sheet, annual report, mark-to-market "
                            "ou unrealized loss do Fed devem ter peso minimo, salvo transmissao ampla e confirmada."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Overview: {overall}\n\n"
                            f"Contratos: {contracts}\n\n"
                            f"Acoes: {securities}\n\n"
                            f"Bloomberg refs: {reference_assets}\n\n"
                            f"Participantes: {participants}\n\n"
                            f"Noticias: {news_rows}\n\n"
                            "Retorne JSON com: market_commentary, sentiment_change_commentary, "
                            "asset_volume_commentary, news_commentary, action_bias, confidence, key_points, risks."
                        ),
                    },
                ],
                temperature=0.25,
                max_tokens=1400,
            )
            return {
                "market_commentary": response.get("market_commentary") or fallback["market_commentary"],
                "sentiment_change_commentary": response.get("sentiment_change_commentary") or fallback["sentiment_change_commentary"],
                "asset_volume_commentary": response.get("asset_volume_commentary") or fallback["asset_volume_commentary"],
                "news_commentary": response.get("news_commentary") or fallback["news_commentary"],
                "action_bias": self._direction_to_bias(response.get("action_bias")),
                "confidence": self._normalize_confidence(response.get("confidence"), fallback=55, minimum=40),
                "key_points": response.get("key_points") or fallback["key_points"],
                "risks": response.get("risks") or fallback["risks"],
            }
        except Exception as exc:
            logger.warning(f"Macro overview LLM generation failed, using fallback: {exc}")
            return fallback

    def _fallback_ai_commentary(
        self,
        overall: Dict[str, Any],
        contracts: List[Dict[str, Any]],
        reference_assets: List[Dict[str, Any]],
        participants: List[Dict[str, Any]],
        news_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        top_contracts = ", ".join(str(item.get("ticker")) for item in contracts[:3] if item.get("ticker")) or "macro basket"
        top_refs = ", ".join(str(item.get("ticker")) for item in reference_assets[:3] if item.get("ticker")) or "Bloomberg reference basket"
        top_participants = ", ".join(str(item.get("broker_name")) for item in participants[:3] if item.get("broker_name")) or "brokers spread out"
        top_news = news_rows[0]["headline"] if news_rows else "No clearly impactful headline was detected today."
        return {
            "market_commentary": (
                f"The market tone is {overall.get('implicit_sentiment')} with a {overall.get('market_bias')} bias. "
                f"The most active contracts are {top_contracts}, while Bloomberg reference assets center on {top_refs}."
            ),
            "sentiment_change_commentary": (
                f"Sentiment looks {overall.get('sentiment_shift')}. {overall.get('summary')}"
            ),
            "asset_volume_commentary": (
                f"Asset and volume behavior is being led by {top_contracts}, Bloomberg references highlight {top_refs}, "
                f"and participant concentration remains visible in {top_participants}."
            ),
            "news_commentary": top_news,
            "action_bias": overall.get("market_bias") or "watch",
            "confidence": self._normalize_confidence(overall.get("score"), fallback=55, minimum=40),
            "key_points": list(overall.get("drivers") or [])[:4],
            "risks": [
                "Price action can lose signal if the next 5-minute window reverses.",
                "Participant concentration may reflect short-lived positioning rather than session-long conviction.",
            ],
        }

    def _contract_sentiment_score(self, ticker: str, signal: Dict[str, Any], volume_ratio: Optional[float]) -> float:
        market_bias = self._contract_market_bias(ticker, signal.get("direction_5m"))
        direction_sign = 1 if market_bias == "buy" else -1 if market_bias == "sell" else 0
        move_pct = abs(self._to_float(signal.get("net_change_pct_5m")) or 0.0)
        top_5_share = self._to_float(signal.get("top_5_share_percentage")) or 0.0
        volume_bonus = 0.0
        if volume_ratio is not None:
            volume_bonus = max(min((volume_ratio - 1.0) * 6.0, 6.0), -6.0)
        return round(direction_sign * ((move_pct * 450.0) + (top_5_share / 8.0) + volume_bonus), 2)

    def _contract_summary(
        self,
        ticker: str,
        signal: Dict[str, Any],
        latest_volume: Optional[float],
        volume_ratio: Optional[float],
    ) -> str:
        direction = signal.get("direction_5m") or "flat"
        move_pct = self._to_float(signal.get("net_change_pct_5m"))
        top_5_share = self._to_float(signal.get("top_5_share_percentage"))
        volume_text = f"volume {round(latest_volume, 2)}" if latest_volume is not None else "volume n/a"
        ratio_text = f", volume ratio {round(volume_ratio, 2)}x" if volume_ratio is not None else ""
        share_text = f", top 5 share {round(top_5_share, 2)}%" if top_5_share is not None else ""
        return (
            f"{ticker} is {direction} over the latest 5-minute window with move {round(move_pct or 0.0, 4)}%, "
            f"{volume_text}{ratio_text}{share_text}."
        )

    def _reference_asset_summary(self, item: Dict[str, Any]) -> str:
        label = item.get("label") or item.get("security") or "reference asset"
        if not item.get("ok"):
            return f"{label} is configured but has not returned a live Bloomberg snapshot yet."
        change_pct = self._to_float(item.get("change_percent"))
        if change_pct is None:
            return f"{label} is connected to Bloomberg Desktop, but daily change is not available in this snapshot."
        direction = "higher" if change_pct > 0 else "lower" if change_pct < 0 else "flat"
        return f"{label} is {direction} on the day, with change_percent={round(change_pct, 4)}."

    def _participant_comment(
        self,
        broker_name: str,
        market_bias: str,
        implicit_sentiment: str,
        exposures: List[Dict[str, Any]],
    ) -> str:
        if not exposures:
            return f"{broker_name} has no clear concentration signal in the current snapshot."
        assets = ", ".join(f"{item.get('ticker')} ({item.get('share_percentage')}%)" for item in exposures[:2])
        if market_bias == "buy":
            return f"{broker_name} shows an implied bullish footprint, concentrated in {assets} while those contracts trade higher."
        if market_bias == "sell":
            return f"{broker_name} shows an implied bearish footprint, concentrated in {assets} while those contracts trade lower."
        return f"{broker_name} looks {implicit_sentiment}, with a mixed footprint spread across {assets}."

    def _news_summary(self, item: Dict[str, Any], linked_assets: List[str]) -> str:
        if item.get("market_relevance"):
            return f"Market-relevant headline linked to {', '.join(linked_assets[:3]) or 'macro basket'}."
        if int(item.get("impact_score") or 0) >= 4:
            return "High-urgency headline kept on the radar even without a clean asset link."
        return "Headline kept for awareness, but no strong direct market linkage was detected."

    def _describe_sentiment_shift(
        self,
        contract_rows: List[Dict[str, Any]],
        volume: Dict[str, Any],
    ) -> str:
        expanding = 0
        cooling = 0
        for row in contract_rows:
            previous_volume = row.get("previous_volume_5m")
            current_volume = row.get("volume_5m")
            if previous_volume and current_volume and current_volume > previous_volume:
                expanding += 1
            elif previous_volume and current_volume and current_volume < previous_volume:
                cooling += 1
        if expanding >= max(2, len(contract_rows) // 2) and volume.get("pace_label") == "accelerating":
            return "broadening"
        if cooling >= max(2, len(contract_rows) // 2) and volume.get("pace_label") == "cooling":
            return "fading"
        if cooling > expanding:
            return "mixed transition"
        return "stable"

    def _bucket_bias(self, bucket_rows: List[Dict[str, Any]], bucket: str) -> str:
        for item in bucket_rows:
            if item.get("bucket") == bucket:
                return item.get("market_bias") or "watch"
        return "watch"

    def _dominant_direction(self, values: List[Optional[str]]) -> str:
        counts = {"up": 0, "down": 0, "flat": 0}
        for value in values:
            key = (value or "flat").lower()
            counts[key] = counts.get(key, 0) + 1
        if counts["up"] > counts["down"]:
            return "up"
        if counts["down"] > counts["up"]:
            return "down"
        return "flat"

    def _direction_to_bias(self, direction: Optional[str]) -> str:
        value = (direction or "").strip().lower()
        if value in {"buy", "sell", "watch"}:
            return value
        if value == "up":
            return "buy"
        if value == "down":
            return "sell"
        return "watch"

    def _contract_market_bias(self, ticker: str, direction: Optional[str]) -> str:
        value = (direction or "").strip().lower()
        if value in {"buy", "sell", "watch"}:
            return value
        if str(ticker or "").upper().startswith("BVMF:DI1"):
            if value == "down":
                return "buy"
            if value == "up":
                return "sell"
            return "watch"
        return self._direction_to_bias(direction)

    def _bias_from_score(self, score: Optional[float]) -> str:
        value = float(score or 0.0)
        if value >= 1.5:
            return "buy"
        if value <= -1.5:
            return "sell"
        return "watch"

    def _sentiment_label(self, score: Optional[float]) -> str:
        value = float(score or 0.0)
        if value >= 3.0:
            return "bullish"
        if value <= -3.0:
            return "bearish"
        return "mixed"

    def _impact_label(self, score: int) -> str:
        if score >= 6:
            return "high"
        if score >= 4:
            return "medium"
        return "low"

    def _relevance_rank(self, value: Optional[str]) -> int:
        mapping = {"breaking": 3, "important": 2, "relevant": 1}
        return mapping.get((value or "").lower(), 0)

    def _signed_direction(self, value: Optional[str]) -> int:
        normalized = (value or "").strip().lower()
        if normalized == "up":
            return 1
        if normalized == "down":
            return -1
        return 0

    def _normalize_confidence(self, value: Any, fallback: Any, minimum: int = 0) -> int:
        candidate = value if value not in (None, "") else fallback
        try:
            normalized = int(float(candidate))
        except (TypeError, ValueError):
            normalized = int(float(fallback or minimum or 0))
        normalized = max(minimum, normalized)
        return min(normalized, 100)

    def _avg(self, values: Any) -> float:
        items = [float(value) for value in values if value not in (None, "")]
        if not items:
            return 0.0
        return round(sum(items) / len(items), 4)

    def _to_float(self, value: Any) -> Optional[float]:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

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
