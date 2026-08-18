# Macro Agent Playground

## Core Principle

In macro mode, `contracts`, `securities`, `brokers/participants`, and `news` are market context.
They are not simulation agents.

Agents are synthetic market personas that debate, react, hedge, explain, and allocate around that context.

## Agent Families

- `HedgeFundManager`: discretionary buy-side risk takers who connect rates, FX, equities, and policy.
- `MacroTrader`: fast local-market interpreters focused on DI, dollar, and index response.
- `OptionsTrader`: convexity and event-risk specialists.
- `PortfolioManager`: allocators who convert macro views into portfolio changes.
- `InstitutionalAllocator`: pensions and insurers with long-horizon risk budgets.
- `RetailPersonality`: educators, influencers, and short-term retail amplifiers.
- `SellSideStrategist`: economists and strategists who frame the consensus narrative.
- `TreasuryManager`: corporate hedgers reacting to funding and FX stress.
- `QuantTrader`: systematic desks reacting to features, flow, and volatility regimes.
- `FamilyOfficeManager`: private capital allocators seeking protection plus selective offense.
- `PropTrader`: short-horizon desks that press momentum.
- `EventDrivenTrader`: catalyst-focused participants.
- `CTAOperator`: trend-following systematic macro desks.
- `MacroResearcher`: independent scenario builders and narrative synthesizers.

## Persona Catalog

- `Helena Prado` (`HedgeFundManager`): long-end Brazil rates and BRL stress specialist, thesis-first and conviction-heavy.
- `Rafael Nogueira` (`HedgeFundManager`): event macro PM who hedges through index and dollar on policy or political shocks.
- `Sofia Almeida` (`HedgeFundManager`): cross-asset macro manager linking curve, banks, and commodity equities.
- `Bruno Lacerda` (`MacroTrader`): local rates trader focused on DI short-end and BCB repricing.
- `Renata Velloso` (`MacroTrader`): FX macro trader centered on BRL, dollar futures, and external shock transmission.
- `Thiago Moura` (`MacroTrader`): EM flow trader who reads participant concentration before changing bias.
- `Marina Teixeira` (`OptionsTrader`): index volatility specialist who prefers convexity around macro events.
- `Andre Falcao` (`OptionsTrader`): FX options trader focused on fiscal fear, skew, and tail hedges.
- `Felipe Azevedo` (`OptionsTrader`): rates volatility trader expressing uncertain directional views through DI options logic.
- `Carla Junqueira` (`PortfolioManager`): multimarket PM using banks and commodities as macro transmission assets.
- `Eduardo Salomao` (`PortfolioManager`): institutional PM that waits for cross-asset confirmation before rotating risk.
- `Renato Albuquerque` (`InstitutionalAllocator`): pension allocator anchored on long-end duration and liability matching.
- `Patricia Meirelles` (`InstitutionalAllocator`): insurance allocator focused on carry, solvency, and hedge efficiency.
- `Ana Beatriz Rocha` (`RetailPersonality`): retail-facing narrator who translates macro breaks into crowd language.
- `Gustavo Reis` (`RetailPersonality`): intraday retail personality amplifying momentum in index and dollar.
- `Camila Brandao` (`RetailPersonality`): educator who explains DI curve and macro linkages to non-professionals.
- `Marcelo Pires` (`SellSideStrategist`): sell-side economist who reframes the market baseline.
- `Fernanda Costa` (`SellSideStrategist`): equity strategist translating macro into sector and factor rotation.
- `Roberto Neves` (`TreasuryManager`): corporate treasury manager reacting to FX and funding stress with hedges.
- `Daniel Kim` (`QuantTrader`): systematic macro trader watching dispersion, slope, and broker concentration.
- `Laura Tavares` (`FamilyOfficeManager`): allocator balancing capital preservation with tactical offense.
- `Vinicius Monteiro` (`PropTrader`): short-term proprietary trader that pushes early momentum in index and dollar.
- `Gabriel Diniz` (`EventDrivenTrader`): policy and politics catalyst trader running branching scenarios.
- `Beatriz Siqueira` (`CTAOperator`): trend-following macro operator that scales only after breakout confirmation.
- `Isabela Ramos` (`MacroResearcher`): independent researcher synthesizing news, curve shape, and flow into scenarios.

## Context Mapping

- `DI1F27`, `DI1F28`: short-end curve context.
- `DI1F29`, `DI1F30`, `DI1F31`, `DI1F35`: long-end curve context.
- `WINJ26`: index context.
- `WDOK26`: dollar context.
- `VALE3`, `PETR4`, `ITUB4`, `BPAC11`, `BBDC4`: equity read-through assets.
- `Bleu news`: event and narrative triggers.
- `AQuant participants/books/ohlcv`: flow, conviction, and microstructure evidence.

## Intended Behavior

- The graph stores market facts and relationships.
- The simulation layer selects personas to interpret those facts.
- Initial posts should come from personas such as `HedgeFundManager`, `MacroTrader`, or `SellSideStrategist`.
- Contracts, securities, brokers, and news nodes should remain as references in `related_nodes` and `related_edges`, not as agents.
