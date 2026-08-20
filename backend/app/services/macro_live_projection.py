"""Projection of macro snapshots into Aquiles projects."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from ..models.project import ProjectManager, ProjectStatus
from .macro_live_state_store import MacroStateStore
from .macro_live_utils import _parse_iso_datetime


class MacroProjectionService:
    DEFAULT_PROJECT_NAME = "Macro Live Feed"
    DEFAULT_SIMULATION_REQUIREMENT = (
        "Analyze macro scenarios for Brazilian futures and rates using impactful macro news, "
        "five-minute market windows, full participant pulls per contract, and order book context. "
        "Players should debate how news, flow concentration, and price action reinforce or contradict each other."
    )

    def __init__(self, store: Optional[MacroStateStore] = None):
        self.store = store or MacroStateStore()

    def build_macro_ontology(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        tracked_contracts = sorted((snapshot.get("market") or {}).get("contracts", {}).keys())
        tracked_securities = sorted((snapshot.get("market") or {}).get("securities", {}).keys())
        examples = tracked_contracts[:3] or ["BVMF:WINJ26", "BVMF:WDOJ26", "BVMF:DI1N26"]

        return {
            "entity_types": [
                {
                    "name": "Contract",
                    "description": "A listed futures or rates contract tracked in the macro feed.",
                    "attributes": [
                        {"name": "ticker", "description": "Exchange ticker or contract code."},
                        {"name": "asset_class", "description": "Short asset class label."},
                    ],
                    "examples": examples,
                },
                {
                    "name": "Security",
                    "description": "A spot or equity security used as contextual reference.",
                    "attributes": [
                        {"name": "ticker", "description": "Security code."},
                        {"name": "last_price", "description": "Latest price snapshot."},
                    ],
                    "examples": tracked_securities[:3] or ["AMBP3"],
                },
                {
                    "name": "Broker",
                    "description": "A market participant or broker in participant ranking or book data.",
                    "attributes": [
                        {"name": "broker_id", "description": "Broker identifier."},
                        {"name": "broker_name", "description": "Broker display name."},
                    ],
                    "examples": ["XP INVESTIMENTOS CCTVM S/A", "ITAU CV S/A"],
                },
                {
                    "name": "NewsSource",
                    "description": "A source that publishes macro news updates.",
                    "attributes": [
                        {"name": "source_name", "description": "Publisher or desk name."},
                    ],
                    "examples": ["Macro Trader News", "Premium News"],
                },
                {
                    "name": "NewsEvent",
                    "description": "A concrete macro news item or breaking headline.",
                    "attributes": [
                        {"name": "headline_text", "description": "The headline body."},
                        {"name": "relevance", "description": "Breaking or importance label."},
                    ],
                    "examples": ["Breaking geopolitical headline", "Central bank guidance change"],
                },
                {
                    "name": "MacroTheme",
                    "description": "A recurring macro theme, topic, or narrative bucket.",
                    "attributes": [
                        {"name": "theme_name", "description": "Short theme label."},
                    ],
                    "examples": ["US rates", "Brazil fiscal risk", "Geopolitics"],
                },
                {
                    "name": "Country",
                    "description": "A country or macro region referenced by the feed.",
                    "attributes": [
                        {"name": "country_name", "description": "Country or region name."},
                    ],
                    "examples": ["Brazil", "United States", "Iran"],
                },
                {
                    "name": "ParticipantFlowSnapshot",
                    "description": "A ranked participant flow snapshot for a contract, covering all brokers in the pull.",
                    "attributes": [
                        {
                            "name": "participant_count",
                            "description": "How many participants were captured in the pull.",
                        },
                        {
                            "name": "top_5_share_percentage",
                            "description": "Combined concentration of the top five participants.",
                        },
                    ],
                    "examples": ["WINJ26 participant ranking", "DI1F29 participant concentration"],
                },
                {
                    "name": "MarketMoveWindow",
                    "description": "A five-minute market movement summary for a contract.",
                    "attributes": [
                        {
                            "name": "direction_5m",
                            "description": "Directional summary for the 5-minute window.",
                        },
                        {
                            "name": "net_change_pct_5m",
                            "description": "Percent change over the last five-minute window.",
                        },
                    ],
                    "examples": ["WINJ26 5-minute move", "WDOK26 5-minute move"],
                },
                {
                    "name": "NewsImpactLink",
                    "description": "A structured link between an impactful news item and a moved contract or security.",
                    "attributes": [
                        {
                            "name": "link_reason",
                            "description": "Heuristic explanation for the link.",
                        },
                    ],
                    "examples": [
                        "Breaking headline linked to WINJ26 move",
                        "Fiscal theme linked to long-end DI move",
                    ],
                },
            ],
            "edge_types": [
                {
                    "name": "PUBLISHED_BY",
                    "description": "A news event was published by a news source.",
                    "source_targets": [{"source": "NewsEvent", "target": "NewsSource"}],
                    "attributes": [],
                },
                {
                    "name": "RELATES_TO_CONTRACT",
                    "description": "A news event or theme relates to a tracked contract.",
                    "source_targets": [
                        {"source": "NewsEvent", "target": "Contract"},
                        {"source": "MacroTheme", "target": "Contract"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "RELATES_TO_THEME",
                    "description": "A news event or contract references a macro theme.",
                    "source_targets": [
                        {"source": "NewsEvent", "target": "MacroTheme"},
                        {"source": "Contract", "target": "MacroTheme"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "HAS_PARTICIPANT",
                    "description": "A contract has a relevant broker participant.",
                    "source_targets": [{"source": "Contract", "target": "Broker"}],
                    "attributes": [],
                },
                {
                    "name": "SUMMARIZED_BY_FLOW",
                    "description": "A contract is summarized by a participant flow snapshot.",
                    "source_targets": [{"source": "Contract", "target": "ParticipantFlowSnapshot"}],
                    "attributes": [],
                },
                {
                    "name": "MOVED_IN_WINDOW",
                    "description": "A contract is described by a five-minute market move window.",
                    "source_targets": [{"source": "Contract", "target": "MarketMoveWindow"}],
                    "attributes": [],
                },
                {
                    "name": "IMPACTS_CONTRACT",
                    "description": "A news item or impact link is associated with a moved contract.",
                    "source_targets": [
                        {"source": "NewsEvent", "target": "Contract"},
                        {"source": "NewsImpactLink", "target": "Contract"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "QUOTES_SECURITY",
                    "description": "A contract or news event references a security snapshot.",
                    "source_targets": [
                        {"source": "Contract", "target": "Security"},
                        {"source": "NewsEvent", "target": "Security"},
                    ],
                    "attributes": [],
                },
                {
                    "name": "FOCUSES_ON_COUNTRY",
                    "description": "A news event or theme focuses on a country.",
                    "source_targets": [
                        {"source": "NewsEvent", "target": "Country"},
                        {"source": "MacroTheme", "target": "Country"},
                    ],
                    "attributes": [],
                },
            ],
            "analysis_summary": (
                "Auto-generated macro ontology for live feed ingestion. "
                f"Tracked contracts: {', '.join(tracked_contracts) if tracked_contracts else 'none'}."
            ),
        }

    def render_snapshot_markdown(
        self,
        snapshot: dict[str, Any],
        recent_events: list[dict[str, Any]],
        simulation_requirement: str,
    ) -> str:
        lines = [
            "# Macro Live Snapshot",
            "",
            f"Generated at: {snapshot.get('generated_at', 'unknown')}",
            "",
            "## Simulation Goal",
            simulation_requirement,
            "",
            "## Latest Macro News",
        ]

        impactful_recent_events = [
            event
            for event in recent_events
            if event.get("market_relevance")
            or event.get("linked_contracts")
            or event.get("linked_securities")
            or event.get("linked_buckets")
            or int(event.get("impact_score") or 0) >= 4
        ]

        if impactful_recent_events:
            sorted_events = sorted(
                impactful_recent_events,
                key=lambda item: (
                    int(item.get("impact_score") or 0),
                    (
                        _parse_iso_datetime(item.get("event_time"))
                        or datetime.min.replace(tzinfo=timezone.utc)
                    ).timestamp(),
                ),
                reverse=True,
            )
            for event in sorted_events:
                lines.append(
                    "- "
                    f"[{event.get('relevance') or 'unknown'}] "
                    f"{event.get('headline') or 'Untitled event'} | "
                    f"source={event.get('posted_by') or 'unknown'} | "
                    f"event_time={event.get('event_time') or 'unknown'} | "
                    f"impact_score={event.get('impact_score', 0)} | "
                    f"linked_contracts={', '.join(event.get('linked_contracts') or []) or 'none'} | "
                    f"themes={', '.join(event.get('themes') or []) or 'none'} | "
                    f"market_relevance={event.get('market_relevance', False)} | "
                    f"reasons={', '.join(event.get('link_reasons') or []) or 'none'}"
                )
        else:
            lines.append(
                "- No impactful macro news events were captured in the current lookback window."
            )
            lines.append(
                "- Generic non-market headlines were intentionally omitted from the scenario context."
            )

        market = snapshot.get("market", {})
        securities = market.get("securities") or {}
        contracts = market.get("contracts") or {}
        groups = market.get("groups") or {}
        reference_assets = market.get("reference_assets") or {}
        reference_groups = market.get("reference_groups") or {}
        overview = market.get("overview") or {}
        news_links = market.get("news_links") or []

        lines.extend(["", "## Security Headers"])
        if securities:
            for symbol, security in securities.items():
                lines.append(
                    "- "
                    f"{symbol}: price={security.get('price')} "
                    f"change_percent={security.get('change_percent')} "
                    f"updated_at={security.get('updated_at')}"
                )
        else:
            lines.append("- No security headers collected.")

        lines.extend(["", "## Market Groups"])
        if groups:
            for group_name, tickers in groups.items():
                lines.append(f"- {group_name}: {', '.join(tickers) if tickers else 'none'}")
        else:
            lines.append("- No market groups configured.")

        lines.extend(["", "## Bloomberg Reference Basket"])
        if reference_assets:
            for security, item in reference_assets.items():
                lines.append(
                    "- "
                    f"{security}: label={item.get('label')} "
                    f"bucket={item.get('bucket')} "
                    f"price={item.get('price')} "
                    f"change_percent={item.get('change_percent')} "
                    f"ok={item.get('ok')}"
                )
        else:
            lines.append("- No Bloomberg reference assets collected.")

        if reference_groups:
            lines.extend(["", "## Bloomberg Reference Groups"])
            for group_name, tickers in reference_groups.items():
                lines.append(f"- {group_name}: {', '.join(tickers) if tickers else 'none'}")

        lines.extend(["", "## Market Overview"])
        top_movers = overview.get("top_movers_5m") or []
        if top_movers:
            for item in top_movers:
                lines.append(
                    "- "
                    f"{item.get('ticker')}: direction_5m={item.get('direction_5m')} "
                    f"net_change_pct_5m={item.get('net_change_pct_5m')} "
                    f"volume_5m={item.get('volume_5m')} "
                    f"book_imbalance={item.get('book_imbalance')}"
                )
        else:
            lines.append("- No 5-minute market movers available.")

        impactful_news = overview.get("impactful_news") or []
        lines.extend(["", "## Impactful News Drivers"])
        if impactful_news:
            for item in impactful_news:
                lines.append(
                    "- "
                    f"[{item.get('relevance') or 'unknown'}] "
                    f"{item.get('headline')} | "
                    f"impact_score={item.get('impact_score')} | "
                    f"linked_contracts={', '.join(item.get('linked_contracts') or []) or 'none'} | "
                    f"themes={', '.join(item.get('themes') or []) or 'none'}"
                )
        else:
            lines.append(
                "- No impactful macro news drivers detected in the current lookback window."
            )

        lines.extend(["", "## News Impact Links"])
        if news_links:
            for link in news_links:
                lines.append(
                    "- "
                    f"{link.get('headline')} -> {link.get('ticker')} "
                    f"(bucket={link.get('bucket')}, direction_5m={link.get('direction_5m')}, "
                    f"net_change_pct_5m={link.get('net_change_pct_5m')}, "
                    f"themes={', '.join(link.get('themes') or []) or 'none'}, "
                    f"reasons={', '.join(link.get('link_reasons') or []) or 'none'})"
                )
        else:
            lines.append("- No explicit news-market links detected.")

        lines.extend(["", "## Contracts"])
        if contracts:
            for ticker, contract in contracts.items():
                lines.extend(["", f"### {ticker}"])
                lines.append(f"- Bucket: {contract.get('bucket', 'other')}")

                ohlcv = contract.get("ohlcv", {})
                last_candle = ohlcv.get("last") or {}
                lines.append(
                    "- OHLCV: "
                    f"ok={ohlcv.get('ok')} candles={ohlcv.get('candle_count')} "
                    f"last_close={last_candle.get('close')} last_volume={last_candle.get('volume')} "
                    f"last_time={last_candle.get('time')}"
                )
                latest_window = ohlcv.get("latest_window") or {}
                lines.append(
                    "- 5m Window: "
                    f"start={latest_window.get('window_start')} end={latest_window.get('window_end')} "
                    f"direction={latest_window.get('direction')} "
                    f"net_change={latest_window.get('net_change')} "
                    f"net_change_pct={latest_window.get('net_change_pct')} "
                    f"volume={latest_window.get('volume')}"
                )
                for window in (ohlcv.get("windows_5m") or [])[-4:]:
                    lines.append(
                        "  - "
                        f"window={window.get('window_start')} direction={window.get('direction')} "
                        f"net_change_pct={window.get('net_change_pct')} volume={window.get('volume')}"
                    )

                participants = contract.get("participants", {})
                lines.append(
                    f"- Participants: ok={participants.get('ok')} rows={participants.get('rows')} "
                    f"top_5_share={((participants.get('summary') or {}).get('top_5_share_percentage'))}"
                )
                for row in participants.get("all_rows", []):
                    lines.append(
                        "  - "
                        f"{row.get('broker_name')} quantity={row.get('quantity')} "
                        f"percentage={row.get('percentage')} relative_percentage={row.get('relative_percentage')} "
                        f"avg_price={row.get('average_price')}"
                    )

                book = contract.get("book", {})
                best_bid = book.get("best_bid") or {}
                best_ask = book.get("best_ask") or {}
                book_summary = book.get("summary") or {}
                lines.append(
                    "- Book: "
                    f"ok={book.get('ok')} bid_levels={book.get('bid_levels')} ask_levels={book.get('ask_levels')} "
                    f"best_bid={best_bid.get('price')} best_ask={best_ask.get('price')} "
                    f"spread={book_summary.get('spread')} imbalance={book_summary.get('imbalance')}"
                )
                if book.get("error"):
                    lines.append(f"- Book error: {book.get('error')}")
        else:
            lines.append("- No contract market data collected.")

        lines.extend(
            [
                "",
                "## Feed Health",
                json.dumps(snapshot.get("sources", {}), ensure_ascii=False, indent=2),
            ]
        )
        return "\n".join(lines)

    def sync_snapshot_to_project(
        self,
        project_id: str | None = None,
        project_name: str | None = None,
        simulation_requirement: str | None = None,
        include_recent_events: int = 20,
    ) -> dict[str, Any]:
        state = self.store.read_state()
        snapshot = state.get("snapshot", {})
        recent_events = state.get("recent_events", [])[:include_recent_events]

        if not snapshot.get("generated_at"):
            raise ValueError("No macro snapshot available. Run collection first.")

        simulation_requirement = simulation_requirement or self.DEFAULT_SIMULATION_REQUIREMENT

        if project_id:
            project = ProjectManager.get_project(project_id)
            if not project:
                raise ValueError(f"Project not found: {project_id}")
        else:
            project = ProjectManager.create_project(name=project_name or self.DEFAULT_PROJECT_NAME)

        markdown = self.render_snapshot_markdown(snapshot, recent_events, simulation_requirement)
        filename = f"macro_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        file_info = ProjectManager.save_text_file_to_project(project.project_id, filename, markdown)

        project.name = project_name or project.name or self.DEFAULT_PROJECT_NAME
        project.files.append(
            {
                "filename": file_info["original_filename"],
                "size": file_info["size"],
            }
        )
        project.total_text_length = len(markdown)
        project.simulation_requirement = simulation_requirement
        project.project_mode = "macro"
        project.agent_strategy = "macro_personas"
        project.ontology = self.build_macro_ontology(snapshot)
        project.analysis_summary = (
            f"Snapshot synced from live macro feeds at {snapshot.get('generated_at')}."
        )
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        project.graph_id = None
        project.graph_build_task_id = None
        project.error = None

        ProjectManager.save_extracted_text(project.project_id, markdown)
        ProjectManager.save_project(project)

        return {
            "project": project,
            "snapshot_generated_at": snapshot.get("generated_at"),
            "markdown_preview": markdown[:4000],
            "artifact_path": file_info["path"],
        }
