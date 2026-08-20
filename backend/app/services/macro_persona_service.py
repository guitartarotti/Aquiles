from __future__ import annotations

from dataclasses import dataclass
from hashlib import md5
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ..utils.logger import get_logger
from .zep_entity_reader import EntityNode, FilteredEntities, ZepEntityReader

logger = get_logger("aquiles.macro_personas")


MACRO_PERSONA_ENTITY_TYPES = {
    "HedgeFundManager",
    "MacroTrader",
    "OptionsTrader",
    "PortfolioManager",
    "InstitutionalAllocator",
    "RetailPersonality",
    "SellSideStrategist",
    "TreasuryManager",
    "QuantTrader",
    "FamilyOfficeManager",
    "PropTrader",
    "EventDrivenTrader",
    "CTAOperator",
    "MacroResearcher",
}


@dataclass(frozen=True)
class MacroPersonaArchetype:
    slug: str
    name: str
    entity_type: str
    institution: str
    desk: str
    profession: str
    strategy: str
    time_horizon: str
    risk_style: str
    communication_style: str
    signature_move: str
    interested_topics: Sequence[str]
    watch_signals: Sequence[str]
    contract_focus: Sequence[str]
    security_focus: Sequence[str]
    theme_focus: Sequence[str]


MACRO_PERSONA_CATALOG: Sequence[MacroPersonaArchetype] = (
    MacroPersonaArchetype(
        slug="helena-prado",
        name="Helena Prado",
        entity_type="HedgeFundManager",
        institution="Aurora Latitude Capital",
        desk="Global Macro",
        profession="Hedge fund CIO",
        strategy="Discretionary macro with emphasis on the Brazilian long-end and BRL stress regimes.",
        time_horizon="multi-day to multi-week",
        risk_style="high conviction, hedged with futures and dollar overlays",
        communication_style="calm, probabilistic, thesis-first",
        signature_move="Builds curve steepener or flattening books only after macro narrative and flow align.",
        interested_topics=("Brazil rates", "central bank reaction", "fiscal credibility", "BRL stress"),
        watch_signals=("DI1 long-end steepening", "Bleu breaking macro headlines", "foreign flow"),
        contract_focus=("DI1F29", "DI1F30", "DI1F31", "DI1F35", "WDOK26"),
        security_focus=("VALE3", "PETR4"),
        theme_focus=("inflation", "fiscal", "central bank"),
    ),
    MacroPersonaArchetype(
        slug="rafael-nogueira",
        name="Rafael Nogueira",
        entity_type="HedgeFundManager",
        institution="Pontal 3G Macro",
        desk="Event Macro",
        profession="Portfolio manager",
        strategy="Trades policy events, political shocks and cross-asset gaps between rates, equities and FX.",
        time_horizon="intraday to one week",
        risk_style="opportunistic and fast de-risking",
        communication_style="decisive, headline-driven, concise",
        signature_move="Adds index and dollar hedges immediately when macro news changes the distribution.",
        interested_topics=("policy surprise", "politics", "index futures", "FX hedges"),
        watch_signals=("Bleu breaking", "WINJ26 momentum", "WDOK26 breakout"),
        contract_focus=("WINJ26", "WDOK26", "DI1F28", "DI1F29"),
        security_focus=("PETR4", "BBDC4"),
        theme_focus=("risk-off", "politics", "growth scare"),
    ),
    MacroPersonaArchetype(
        slug="sofia-almeida",
        name="Sofia Almeida",
        entity_type="HedgeFundManager",
        institution="Litoral Apex",
        desk="Cross-Asset Macro",
        profession="Hedge fund partner",
        strategy="Combines Brazil rates, banks and commodities to express a regime view.",
        time_horizon="one week to one month",
        risk_style="balanced, diversified, drawdown-aware",
        communication_style="structured, thematic, data-heavy",
        signature_move="Pairs commodity equities with curve expression to isolate the macro driver.",
        interested_topics=("banks", "commodities", "Brazil risk premium", "cross-asset correlation"),
        watch_signals=("bank stock relative strength", "commodity beta", "curve inflection"),
        contract_focus=("DI1F29", "DI1F31", "WINJ26"),
        security_focus=("VALE3", "PETR4", "ITUB4", "BPAC11", "BBDC4"),
        theme_focus=("terms of trade", "credit impulse", "domestic risk premium"),
    ),
    MacroPersonaArchetype(
        slug="bruno-lacerda",
        name="Bruno Lacerda",
        entity_type="MacroTrader",
        institution="Mesa Boreal",
        desk="Local Rates",
        profession="Senior macro trader",
        strategy="Reads local rates and central bank communication to reposition quickly along the curve.",
        time_horizon="intraday to three days",
        risk_style="active, tactical, stop-driven",
        communication_style="trader talk, focused on catalysts",
        signature_move="Uses DI short-end as expression of immediate BCB repricing and long-end as confirmation.",
        interested_topics=("short-end DI", "Copom", "activity data", "inflation surprise"),
        watch_signals=("DI1F27", "DI1F28", "Bleu important headlines"),
        contract_focus=("DI1F27", "DI1F28", "DI1F29"),
        security_focus=("ITUB4", "BBDC4"),
        theme_focus=("Copom", "inflation", "carry"),
    ),
    MacroPersonaArchetype(
        slug="renata-velloso",
        name="Renata Velloso",
        entity_type="MacroTrader",
        institution="Atlas Flow",
        desk="FX and Macro",
        profession="FX macro trader",
        strategy="Trades BRL sensitivity to local rates and global risk tone.",
        time_horizon="intraday to one week",
        risk_style="fast, hedge-aware, liquidity-sensitive",
        communication_style="sharp, flow-oriented",
        signature_move="Uses WDOK26 as the first responder to macro stress and confirms through long DI.",
        interested_topics=("BRL", "global rates", "Brazil risk", "foreign positioning"),
        watch_signals=("WDOK26", "DI1F35", "risk sentiment"),
        contract_focus=("WDOK26", "DI1F31", "DI1F35"),
        security_focus=("VALE3", "PETR4"),
        theme_focus=("external shock", "BRL carry", "foreign demand"),
    ),
    MacroPersonaArchetype(
        slug="thiago-moura",
        name="Thiago Moura",
        entity_type="MacroTrader",
        institution="Nexo Trading",
        desk="EM Flow",
        profession="Emerging markets trader",
        strategy="Tracks participant flow and basis moves to infer who is pressing Brazil macro markets.",
        time_horizon="intraday",
        risk_style="reactive and flow-dominant",
        communication_style="flow notes, tape-reading, blunt",
        signature_move="Changes bias when broker concentration confirms the price move.",
        interested_topics=("participant flow", "foreign desks", "index futures", "dollar basis"),
        watch_signals=("participants net", "WINJ26", "WDOK26"),
        contract_focus=("WINJ26", "WDOK26", "DI1F28"),
        security_focus=("BPAC11", "ITUB4"),
        theme_focus=("flow regime", "foreign positioning", "squeeze"),
    ),
    MacroPersonaArchetype(
        slug="marina-teixeira",
        name="Marina Teixeira",
        entity_type="OptionsTrader",
        institution="Convexa Derivativos",
        desk="Index Volatility",
        profession="Options trader",
        strategy="Trades implied volatility and convexity around macro catalysts in the index.",
        time_horizon="intraday to event window",
        risk_style="convex, asymmetric, premium-sensitive",
        communication_style="precise, scenario-based",
        signature_move="Expresses uncertainty through options before chasing outright direction.",
        interested_topics=("volatility", "event risk", "index gamma", "skew"),
        watch_signals=("WINJ26 realized vol", "macro headlines", "open risk window"),
        contract_focus=("WINJ26",),
        security_focus=("PETR4", "VALE3"),
        theme_focus=("event risk", "vol crush", "gap risk"),
    ),
    MacroPersonaArchetype(
        slug="andre-falcao",
        name="Andre Falcao",
        entity_type="OptionsTrader",
        institution="Sigma Vega",
        desk="FX Options",
        profession="FX options trader",
        strategy="Uses dollar convexity to express stress, fiscal fear and global repricing.",
        time_horizon="one day to two weeks",
        risk_style="tail-risk seeker",
        communication_style="defensive, hedge-centric",
        signature_move="Buys convex USD exposure when spot is still quiet but macro news broadens risk tails.",
        interested_topics=("FX skew", "tail hedges", "stress regimes", "macro hedging"),
        watch_signals=("WDOK26", "Bleu breaking", "DI long-end"),
        contract_focus=("WDOK26", "DI1F35"),
        security_focus=("BBDC4", "ITUB4"),
        theme_focus=("tail risk", "fiscal stress", "hedging demand"),
    ),
    MacroPersonaArchetype(
        slug="felipe-azevedo",
        name="Felipe Azevedo",
        entity_type="OptionsTrader",
        institution="Curva Vega House",
        desk="Rates Volatility",
        profession="Rates options trader",
        strategy="Trades curvature, implied vol and event premium across the DI strip.",
        time_horizon="event window to two weeks",
        risk_style="model-aware, mean-reverting, selective",
        communication_style="technical, Greeks-driven",
        signature_move="Prefers options when the narrative is strong but the direction is still noisy.",
        interested_topics=("rates vol", "curve convexity", "policy event premium"),
        watch_signals=("DI1F28", "DI1F31", "term premium shock"),
        contract_focus=("DI1F28", "DI1F29", "DI1F31"),
        security_focus=("BPAC11",),
        theme_focus=("curve convexity", "policy uncertainty", "term premium"),
    ),
    MacroPersonaArchetype(
        slug="carla-junqueira",
        name="Carla Junqueira",
        entity_type="PortfolioManager",
        institution="Serra Azul Asset",
        desk="Multimercado",
        profession="Asset manager PM",
        strategy="Balances directional macro with sector allocation and cash management.",
        time_horizon="one week to one quarter",
        risk_style="measured, committee-oriented",
        communication_style="balanced, allocative, explanatory",
        signature_move="Uses financials and commodity names to modulate a macro thesis without overlevering futures.",
        interested_topics=("asset allocation", "banks", "commodities", "macro overlay"),
        watch_signals=("long-end DI", "bank stocks", "Bleu relevant"),
        contract_focus=("DI1F29", "WINJ26"),
        security_focus=("VALE3", "PETR4", "ITUB4", "BPAC11", "BBDC4"),
        theme_focus=("allocation", "earnings sensitivity", "macro overlay"),
    ),
    MacroPersonaArchetype(
        slug="eduardo-salomao",
        name="Eduardo Salomao",
        entity_type="PortfolioManager",
        institution="Pilar Investimentos",
        desk="Institucional",
        profession="Portfolio manager",
        strategy="Translates macro views into portfolio weights with strict drawdown controls.",
        time_horizon="one month to one quarter",
        risk_style="risk-budgeted and deliberate",
        communication_style="institutional, low-noise",
        signature_move="Demands confirmation from both rates and equities before shifting risk materially.",
        interested_topics=("portfolio risk", "allocation gates", "macro confirmation"),
        watch_signals=("DI1F31", "WINJ26 breadth", "financials leadership"),
        contract_focus=("DI1F31", "WINJ26"),
        security_focus=("ITUB4", "BBDC4", "BPAC11"),
        theme_focus=("portfolio rotation", "macro confirmation", "risk budgeting"),
    ),
    MacroPersonaArchetype(
        slug="renato-albuquerque",
        name="Renato Albuquerque",
        entity_type="InstitutionalAllocator",
        institution="Fundacao Horizonte",
        desk="Pension Allocation",
        profession="Pension allocator",
        strategy="Focuses on long-duration liability matching and gradual rebalancing.",
        time_horizon="quarterly to annual",
        risk_style="slow moving, capital-preservation first",
        communication_style="formal, patient, benchmark-aware",
        signature_move="Uses long-end DI as the anchor for strategic allocation decisions.",
        interested_topics=("duration matching", "real return", "institutional allocation"),
        watch_signals=("DI1F31", "DI1F35", "fiscal regime"),
        contract_focus=("DI1F31", "DI1F35"),
        security_focus=("ITUB4", "VALE3"),
        theme_focus=("duration", "liability matching", "real rates"),
    ),
    MacroPersonaArchetype(
        slug="patricia-meirelles",
        name="Patricia Meirelles",
        entity_type="InstitutionalAllocator",
        institution="Seguradora Prisma",
        desk="Insurance Portfolio",
        profession="Insurance allocator",
        strategy="Rebalances gradually around long-duration carry, solvency and hedge efficiency.",
        time_horizon="monthly to annual",
        risk_style="conservative and carry-oriented",
        communication_style="measured, policy-aware",
        signature_move="Responds to long-end repricing with incremental hedges rather than outright directional churn.",
        interested_topics=("insurance carry", "duration", "solvency", "hedges"),
        watch_signals=("DI1F30", "DI1F35", "curve dislocation"),
        contract_focus=("DI1F30", "DI1F35"),
        security_focus=("BBDC4", "ITUB4"),
        theme_focus=("carry", "duration extension", "hedge efficiency"),
    ),
    MacroPersonaArchetype(
        slug="ana-beatriz-rocha",
        name="Ana Beatriz Rocha",
        entity_type="RetailPersonality",
        institution="Canal Radar de Bolsa",
        desk="Retail Media",
        profession="Retail market personality",
        strategy="Turns fast macro moves into narratives digestible for retail audiences.",
        time_horizon="intraday to two days",
        risk_style="high engagement, inconsistent conviction",
        communication_style="didactic, energetic, narrative-heavy",
        signature_move="Frames the move first in plain language and only later adds nuance.",
        interested_topics=("retail sentiment", "headline interpretation", "index swings"),
        watch_signals=("Bleu breaking", "WINJ26", "VALE3"),
        contract_focus=("WINJ26",),
        security_focus=("VALE3", "PETR4", "ITUB4"),
        theme_focus=("sentiment", "retail reaction", "headline shock"),
    ),
    MacroPersonaArchetype(
        slug="gustavo-reis",
        name="Gustavo Reis",
        entity_type="RetailPersonality",
        institution="Comunidade Gain Intraday",
        desk="Day Trade Community",
        profession="Retail trader personality",
        strategy="Reads index and dollar momentum and broadcasts conviction to short-term traders.",
        time_horizon="intraday",
        risk_style="aggressive and momentum-driven",
        communication_style="loud, tactical, momentum-first",
        signature_move="Amplifies whatever move already has tape and crowd participation.",
        interested_topics=("day trade", "index futures", "dollar breakout", "tape speed"),
        watch_signals=("WINJ26", "WDOK26", "broker flow"),
        contract_focus=("WINJ26", "WDOK26"),
        security_focus=("PETR4", "BBDC4"),
        theme_focus=("momentum", "squeeze", "retail crowding"),
    ),
    MacroPersonaArchetype(
        slug="camila-brandao",
        name="Camila Brandao",
        entity_type="RetailPersonality",
        institution="Macro sem Jargao",
        desk="Education",
        profession="Retail macro educator",
        strategy="Explains the curve, dollar and policy linkage to a non-professional audience.",
        time_horizon="same day to one week",
        risk_style="low directional risk, high narrative influence",
        communication_style="didactic, calm, accessible",
        signature_move="Translates complex DI moves into simple stories that shape retail expectations.",
        interested_topics=("curve education", "FX education", "macro explanation"),
        watch_signals=("DI1F27", "DI1F35", "macro headlines"),
        contract_focus=("DI1F27", "DI1F35", "WDOK26"),
        security_focus=("ITUB4", "BPAC11"),
        theme_focus=("education", "expectations", "macro literacy"),
    ),
    MacroPersonaArchetype(
        slug="marcelo-pires",
        name="Marcelo Pires",
        entity_type="SellSideStrategist",
        institution="Banco Cedro",
        desk="Economics Research",
        profession="Sell-side economist",
        strategy="Publishes baseline scenarios and pushes the market toward regime framing.",
        time_horizon="week to quarter",
        risk_style="scenario-based, forecast-centric",
        communication_style="formal, model-backed, influential",
        signature_move="Resets consensus by reframing the macro baseline rather than chasing the tape.",
        interested_topics=("economic forecasts", "fiscal path", "central bank reaction function"),
        watch_signals=("DI curve", "Bleu relevant", "policy communication"),
        contract_focus=("DI1F28", "DI1F31", "DI1F35"),
        security_focus=("ITUB4", "BBDC4"),
        theme_focus=("baseline scenario", "fiscal path", "central bank"),
    ),
    MacroPersonaArchetype(
        slug="fernanda-costa",
        name="Fernanda Costa",
        entity_type="SellSideStrategist",
        institution="Corretora Horizonte",
        desk="Equity Strategy",
        profession="Equity strategist",
        strategy="Connects macro regime changes to factor rotation and equity leadership.",
        time_horizon="week to month",
        risk_style="moderate, cross-asset aware",
        communication_style="top-down, allocation-friendly",
        signature_move="Uses banks and commodities as quick readouts for macro stance changes.",
        interested_topics=("equity rotation", "banks", "commodities", "top-down strategy"),
        watch_signals=("WINJ26 breadth", "VALE3", "PETR4", "financials"),
        contract_focus=("WINJ26",),
        security_focus=("VALE3", "PETR4", "ITUB4", "BPAC11", "BBDC4"),
        theme_focus=("rotation", "factor leadership", "macro beta"),
    ),
    MacroPersonaArchetype(
        slug="roberto-neves",
        name="Roberto Neves",
        entity_type="TreasuryManager",
        institution="Grupo Orla",
        desk="Corporate Treasury",
        profession="Treasury manager",
        strategy="Protects balance sheet exposure to BRL, rates and funding costs.",
        time_horizon="one week to quarter",
        risk_style="hedge-first, conservative",
        communication_style="pragmatic, balance-sheet focused",
        signature_move="Responds to market stress through hedges, not directional speculation.",
        interested_topics=("hedging", "funding cost", "BRL exposure", "cash management"),
        watch_signals=("WDOK26", "DI1F29", "curve volatility"),
        contract_focus=("WDOK26", "DI1F29", "DI1F31"),
        security_focus=("PETR4", "VALE3"),
        theme_focus=("hedging demand", "funding stress", "corporate risk"),
    ),
    MacroPersonaArchetype(
        slug="daniel-kim",
        name="Daniel Kim",
        entity_type="QuantTrader",
        institution="Arco Sistematico",
        desk="Systematic Macro",
        profession="Quant trader",
        strategy="Uses cross-asset features, flow proxies and volatility states to detect regime shifts.",
        time_horizon="intraday to one week",
        risk_style="model-driven, low-ego, adaptive",
        communication_style="sparse, statistical, unemotional",
        signature_move="Needs confirmation from price, volume and cross-asset dispersion before scaling.",
        interested_topics=("systematic macro", "features", "dispersion", "regime detection"),
        watch_signals=("WINJ26", "WDOK26", "DI1 curve slope", "broker concentration"),
        contract_focus=("WINJ26", "WDOK26", "DI1F27", "DI1F35"),
        security_focus=("BPAC11", "ITUB4"),
        theme_focus=("regime change", "dispersion", "systematic signal"),
    ),
    MacroPersonaArchetype(
        slug="laura-tavares",
        name="Laura Tavares",
        entity_type="FamilyOfficeManager",
        institution="Aroeira Family Office",
        desk="Asset Allocation",
        profession="Family office manager",
        strategy="Mixes macro protection with opportunistic allocation into quality liquid assets.",
        time_horizon="month to quarter",
        risk_style="capital preservation with selective offense",
        communication_style="discreet, selective, high signal",
        signature_move="Adds hedges before rotating cash into risk assets after a macro scare.",
        interested_topics=("capital preservation", "liquid hedges", "quality allocation"),
        watch_signals=("DI1F31", "WDOK26", "banks resilience"),
        contract_focus=("DI1F31", "WDOK26"),
        security_focus=("ITUB4", "BPAC11", "VALE3"),
        theme_focus=("wealth preservation", "tactical allocation", "macro hedge"),
    ),
    MacroPersonaArchetype(
        slug="vinicius-monteiro",
        name="Vinicius Monteiro",
        entity_type="PropTrader",
        institution="Mesa Alvorada",
        desk="Index and Dollar Proprietary",
        profession="Proprietary trader",
        strategy="Pushes short-term momentum in the index and dollar whenever news and flow align.",
        time_horizon="minutes to intraday",
        risk_style="aggressive and liquidity-seeking",
        communication_style="fast, punchy, tape-oriented",
        signature_move="Acts early in the impulse and exits before the narrative matures.",
        interested_topics=("prop flow", "momentum ignition", "short-term liquidity"),
        watch_signals=("WINJ26", "WDOK26", "broker activity"),
        contract_focus=("WINJ26", "WDOK26"),
        security_focus=("PETR4", "VALE3"),
        theme_focus=("momentum ignition", "liquidity vacuum", "short squeeze"),
    ),
    MacroPersonaArchetype(
        slug="gabriel-diniz",
        name="Gabriel Diniz",
        entity_type="EventDrivenTrader",
        institution="Catalisador Capital",
        desk="Event Driven Macro",
        profession="Event-driven trader",
        strategy="Focuses on discontinuities caused by policy, data and political catalysts.",
        time_horizon="same day to one week",
        risk_style="high beta around catalysts",
        communication_style="catalyst map, binary framing",
        signature_move="Prepares branching scenarios and then presses the path confirmed by the headline.",
        interested_topics=("catalysts", "politics", "data releases", "binary events"),
        watch_signals=("Bleu breaking", "DI1F28", "WINJ26"),
        contract_focus=("DI1F28", "WINJ26", "WDOK26"),
        security_focus=("PETR4", "BBDC4"),
        theme_focus=("binary event", "headline regime", "policy surprise"),
    ),
    MacroPersonaArchetype(
        slug="beatriz-siqueira",
        name="Beatriz Siqueira",
        entity_type="CTAOperator",
        institution="Helix Trend",
        desk="Trend Following",
        profession="CTA operator",
        strategy="Lets price define regime, then participates through systematic trend exposure.",
        time_horizon="days to weeks",
        risk_style="rules-based, trend-persistent",
        communication_style="minimal, process-driven",
        signature_move="Adds only after a clean breakout and survives noise better than discretionary desks.",
        interested_topics=("trend following", "breakouts", "systematic macro"),
        watch_signals=("WINJ26", "WDOK26", "DI curve trend"),
        contract_focus=("WINJ26", "WDOK26", "DI1F31"),
        security_focus=("VALE3",),
        theme_focus=("trend", "breakout", "persistence"),
    ),
    MacroPersonaArchetype(
        slug="isabela-ramos",
        name="Isabela Ramos",
        entity_type="MacroResearcher",
        institution="Independente Research Lab",
        desk="Independent Research",
        profession="Independent macro researcher",
        strategy="Synthesizes macro data, market moves and participant behavior into coherent scenarios.",
        time_horizon="same day to one month",
        risk_style="non-directional, thesis-building",
        communication_style="long-form, contextual, evidence-first",
        signature_move="Names the regime before the rest of the market agrees on it.",
        interested_topics=("scenario analysis", "policy", "participant behavior", "macro storytelling"),
        watch_signals=("news clusters", "curve shape", "flow dispersion"),
        contract_focus=("DI1F27", "DI1F35", "WINJ26", "WDOK26"),
        security_focus=("VALE3", "PETR4", "ITUB4", "BPAC11", "BBDC4"),
        theme_focus=("scenario building", "regime naming", "macro narrative"),
    ),
)


class MacroPersonaService:
    """Build synthetic macro personas that use market/news entities as discussion context."""

    def __init__(self) -> None:
        self.reader = ZepEntityReader()

    def build_filtered_entities(
        self,
        graph_id: str,
        defined_entity_types: Optional[List[str]] = None,
        enrich_with_edges: bool = True,
    ) -> FilteredEntities:
        all_nodes = self.reader.get_all_nodes(graph_id)
        all_edges = self.reader.get_all_edges(graph_id) if enrich_with_edges else []
        context_index = self._build_context_index(all_nodes)

        selected_entities: List[EntityNode] = []
        entity_types_found = set()

        for archetype in MACRO_PERSONA_CATALOG:
            if defined_entity_types and archetype.entity_type not in defined_entity_types:
                continue

            entity = self._build_persona_entity(
                graph_id=graph_id,
                archetype=archetype,
                context_index=context_index,
                all_edges=all_edges,
                enrich_with_edges=enrich_with_edges,
            )
            selected_entities.append(entity)
            entity_types_found.add(archetype.entity_type)

        return FilteredEntities(
            entities=selected_entities,
            entity_types=entity_types_found,
            total_count=len(MACRO_PERSONA_CATALOG),
            filtered_count=len(selected_entities),
        )

    def get_entity_with_context(self, graph_id: str, entity_uuid: str) -> Optional[EntityNode]:
        result = self.build_filtered_entities(graph_id=graph_id, enrich_with_edges=True)
        for entity in result.entities:
            if entity.uuid == entity_uuid:
                return entity
        return None

    def get_entities_by_type(
        self,
        graph_id: str,
        entity_type: str,
        enrich_with_edges: bool = True,
    ) -> List[EntityNode]:
        result = self.build_filtered_entities(
            graph_id=graph_id,
            defined_entity_types=[entity_type],
            enrich_with_edges=enrich_with_edges,
        )
        return result.entities

    def _build_context_index(self, nodes: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        buckets: Dict[str, List[Dict[str, Any]]] = {
            "contracts": [],
            "securities": [],
            "brokers": [],
            "flows": [],
            "windows": [],
            "impact_links": [],
            "themes": [],
            "news": [],
            "other": [],
        }

        for node in nodes:
            labels = {label.lower() for label in node.get("labels", [])}
            attributes = node.get("attributes", {}) or {}
            if "contract" in labels:
                buckets["contracts"].append(node)
            elif "security" in labels:
                buckets["securities"].append(node)
            elif "participantflowsnapshot" in labels:
                buckets["flows"].append(node)
            elif "marketmovewindow" in labels:
                buckets["windows"].append(node)
            elif "newsimpactlink" in labels:
                buckets["impact_links"].append(node)
            elif "broker" in labels or "participant" in labels:
                buckets["brokers"].append(node)
            elif "macrotheme" in labels or "theme" in labels:
                buckets["themes"].append(node)
            elif "news" in labels or attributes.get("headline"):
                buckets["news"].append(node)
            else:
                buckets["other"].append(node)

        return buckets

    def _build_persona_entity(
        self,
        graph_id: str,
        archetype: MacroPersonaArchetype,
        context_index: Dict[str, List[Dict[str, Any]]],
        all_edges: List[Dict[str, Any]],
        enrich_with_edges: bool,
    ) -> EntityNode:
        related_nodes = self._select_related_nodes(archetype, context_index)
        related_edges = self._build_related_edges(archetype, related_nodes) if enrich_with_edges else []
        connected_facts = self._collect_market_facts(related_nodes, all_edges) if enrich_with_edges else []
        summary = self._build_summary(archetype, related_nodes, connected_facts)

        return EntityNode(
            uuid=self._stable_uuid(graph_id, archetype.slug),
            name=archetype.name,
            labels=["Entity", archetype.entity_type, "MacroPersona"],
            summary=summary,
            attributes={
                "macro_persona": True,
                "institution": archetype.institution,
                "desk": archetype.desk,
                "profession": archetype.profession,
                "strategy": archetype.strategy,
                "time_horizon": archetype.time_horizon,
                "risk_style": archetype.risk_style,
                "communication_style": archetype.communication_style,
                "signature_move": archetype.signature_move,
                "interested_topics": list(archetype.interested_topics),
                "watch_signals": list(archetype.watch_signals),
                "contract_focus": list(archetype.contract_focus),
                "security_focus": list(archetype.security_focus),
                "theme_focus": list(archetype.theme_focus),
                "country": "Brazil",
                "market_role": archetype.entity_type,
            },
            related_edges=related_edges,
            related_nodes=related_nodes,
        )

    def _stable_uuid(self, graph_id: str, slug: str) -> str:
        digest = md5(f"{graph_id}:{slug}".encode("utf-8")).hexdigest()
        return f"macro_persona_{digest[:24]}"

    def _select_related_nodes(
        self,
        archetype: MacroPersonaArchetype,
        context_index: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        selected: List[Dict[str, Any]] = []
        seen = set()
        flow_focus = tuple(archetype.contract_focus) + tuple(archetype.watch_signals)
        impact_focus = (
            tuple(archetype.contract_focus)
            + tuple(archetype.security_focus)
            + tuple(archetype.theme_focus)
        )

        def add_nodes(nodes: Iterable[Dict[str, Any]], limit: int) -> None:
            count = 0
            for node in nodes:
                node_uuid = node.get("uuid")
                if not node_uuid or node_uuid in seen:
                    continue
                seen.add(node_uuid)
                selected.append(
                    {
                        "uuid": node.get("uuid", ""),
                        "name": node.get("name", ""),
                        "labels": node.get("labels", []),
                        "summary": node.get("summary", ""),
                    }
                )
                count += 1
                if count >= limit:
                    break

        add_nodes(self._match_focus(context_index["contracts"], archetype.contract_focus), 4)
        add_nodes(self._match_focus(context_index["securities"], archetype.security_focus), 4)
        add_nodes(self._match_focus(context_index["flows"], flow_focus), 3)
        add_nodes(self._match_focus(context_index["windows"], archetype.contract_focus), 3)
        add_nodes(self._match_focus(context_index["impact_links"], impact_focus), 3)
        add_nodes(context_index["flows"][:2], 2)
        add_nodes(context_index["windows"][:2], 2)
        add_nodes(context_index["impact_links"][:2], 2)
        add_nodes(self._match_focus(context_index["themes"], archetype.theme_focus), 3)
        add_nodes(context_index["brokers"][:4], 4)
        add_nodes(context_index["news"][:3], 3)

        if len(selected) < 6:
            add_nodes(context_index["flows"], 6 - len(selected))
        if len(selected) < 8:
            add_nodes(context_index["windows"], 8 - len(selected))
        if len(selected) < 10:
            add_nodes(context_index["impact_links"], 10 - len(selected))
        if len(selected) < 12:
            add_nodes(context_index["contracts"], 12 - len(selected))
        if len(selected) < 14:
            add_nodes(context_index["securities"], 14 - len(selected))
        if len(selected) < 16:
            add_nodes(context_index["themes"], 16 - len(selected))

        return selected

    def _match_focus(
        self,
        nodes: List[Dict[str, Any]],
        focus_terms: Sequence[str],
    ) -> List[Dict[str, Any]]:
        if not focus_terms:
            return []

        matches: List[Dict[str, Any]] = []
        seen = set()
        for term in focus_terms:
            term_upper = term.upper()
            for node in nodes:
                node_uuid = node.get("uuid")
                haystack = " ".join([
                    str(node.get("name") or ""),
                    str(node.get("summary") or ""),
                ]).upper()
                if node_uuid and node_uuid not in seen and term_upper in haystack:
                    matches.append(node)
                    seen.add(node_uuid)
        return matches

    def _build_related_edges(
        self,
        archetype: MacroPersonaArchetype,
        related_nodes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        edges: List[Dict[str, Any]] = []
        for node in related_nodes:
            labels = {label.lower() for label in node.get("labels", [])}
            if "contract" in labels:
                edge_name = "tracks_contract"
                fact = f"{archetype.name} acompanha {node.get('name')} para calibrar sua tese macro."
            elif "security" in labels:
                edge_name = "monitors_security"
                fact = f"{archetype.name} usa {node.get('name')} como termometro de confirmacao do cenario."
            elif "participantflowsnapshot" in labels:
                edge_name = "interprets_flow_snapshot"
                fact = f"{archetype.name} interpreta {node.get('name')} para medir concentracao e conviccao do fluxo."
            elif "marketmovewindow" in labels:
                edge_name = "anchors_on_5m_move"
                fact = f"{archetype.name} ancora sua leitura na janela de 5 minutos {node.get('name')}."
            elif "newsimpactlink" in labels:
                edge_name = "reacts_to_news_impact"
                fact = f"{archetype.name} reage ao elo causal {node.get('name')} entre noticia e preco."
            elif "broker" in labels or "participant" in labels:
                edge_name = "reads_participant_flow"
                fact = f"{archetype.name} observa o fluxo do participante {node.get('name')} para validar conviccao."
            elif "macrotheme" in labels or "theme" in labels:
                edge_name = "frames_narrative_with"
                fact = f"{archetype.name} ancora sua narrativa no tema {node.get('name')}."
            else:
                edge_name = "reacts_to_context"
                fact = f"{archetype.name} incorpora {node.get('name')} na discussao de mercado."

            edges.append(
                {
                    "direction": "outgoing",
                    "edge_name": edge_name,
                    "fact": fact,
                    "target_node_uuid": node.get("uuid", ""),
                }
            )
        return edges

    def _collect_market_facts(
        self,
        related_nodes: List[Dict[str, Any]],
        all_edges: List[Dict[str, Any]],
    ) -> List[str]:
        related_uuids = {node.get("uuid") for node in related_nodes if node.get("uuid")}
        facts: List[str] = []
        for edge in all_edges:
            if edge.get("source_node_uuid") in related_uuids or edge.get("target_node_uuid") in related_uuids:
                fact = edge.get("fact") or edge.get("name")
                if fact and fact not in facts:
                    facts.append(str(fact))
                if len(facts) >= 8:
                    break
        return facts

    def _build_summary(
        self,
        archetype: MacroPersonaArchetype,
        related_nodes: List[Dict[str, Any]],
        connected_facts: Sequence[str],
    ) -> str:
        context_names = ", ".join(node.get("name", "") for node in related_nodes[:5] if node.get("name"))
        facts_text = "; ".join(connected_facts[:3])
        flow_count = sum(
            1 for node in related_nodes if "participantflowsnapshot" in {label.lower() for label in node.get("labels", [])}
        )
        window_count = sum(
            1 for node in related_nodes if "marketmovewindow" in {label.lower() for label in node.get("labels", [])}
        )
        impact_count = sum(
            1 for node in related_nodes if "newsimpactlink" in {label.lower() for label in node.get("labels", [])}
        )
        summary = (
            f"{archetype.name} atua como {archetype.profession} na {archetype.institution}, "
            f"com foco em {archetype.strategy} e horizonte {archetype.time_horizon}. "
            f"Seu estilo de risco e '{archetype.risk_style}' e sua comunicacao e '{archetype.communication_style}'. "
            f"Os sinais prioritarios incluem {', '.join(archetype.watch_signals)}."
        )
        if context_names:
            summary += f" No playground, observa especialmente {context_names}."
        market_context_bits = []
        if flow_count:
            market_context_bits.append(f"{flow_count} leituras de fluxo de participantes")
        if window_count:
            market_context_bits.append(f"{window_count} janelas de movimento em 5 minutos")
        if impact_count:
            market_context_bits.append(f"{impact_count} elos entre noticia e mercado")
        if market_context_bits:
            summary += f" Sua leitura usa {', '.join(market_context_bits)} para diferenciar direcao, conviccao e timing."
        if facts_text:
            summary += f" Fatos recentes relevantes: {facts_text}."
        return summary
