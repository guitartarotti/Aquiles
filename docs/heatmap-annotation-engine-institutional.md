# Heatmap Annotation Engine

## Institutional Technical Documentation

### Status
- Current production implementation
- Scope: intraday heatmap annotation engine for `WIN`, `WDO` and `DI`
- Purpose: transform participant inventory variation, auction context, macro context and cross-cohort behavior into operational tags over a candle chart

## 1. Executive Summary

The heatmap annotation engine is an institutional-style heuristic decision layer built on top of:

- intraday candles
- participant inventory snapshots
- cohort segmentation (`foreign`, `retail`, `net market`)
- value-map / auction context
- cross-cohort divergence
- concentration and breadth
- macro-news context
- structural flow regime classification

The engine does **not** consume native aggressor/passive trade prints. Instead, it reconstructs a flow view from the **change in participant balance between consecutive snapshots**. This is a crucial design constraint: the system is best understood as an **inventory-variation intelligence engine**, not a native tape reader.

Its role is to answer:

- when is retail likely trapped?
- when is foreign flow aligned with macro and auction?
- when is the move fragile, squeezed, absorbed or likely to fail?
- where are likely stop regions and poor trade locations?

The final outputs are compact chart tags such as:

- `BT` bull trap
- `ST` sell trap
- `VT` retail buying top
- `VF` retail selling bottom
- `FC` foreign buy aligned
- `FV` foreign sell aligned
- `SQ` short squeeze
- `LF` long flush
- `LQ` thin liquidity
- `AB` foreign absorption buy
- `AV` foreign absorption sell
- `SA` stop above
- `SB` stop below
- `CT` retail countertrend

Each tag is backed by a structured explanation layer containing:

- severity
- bias side
- anchor price
- textual rationale
- supporting brokers
- gross/net/foreign/retail contract estimates
- optional related macro event

## 2. System Objectives

The engine exists to solve five practical trading-desk problems:

1. Detect poor positioning behavior from retail when it conflicts with stronger institutional flow.
2. Translate inventory, value and microstructure into chart-level signals that are readable in real time.
3. Surface event-type context that is normally implicit in raw flow data.
4. Connect local market flow with macro context.
5. Preserve auditability: every tag must be explainable back to measurable features.

## 3. Data Ingestion Architecture

### 3.1 Assets covered

The engine is currently designed around:

- `WIN`
- `WDO`
- `DI`

Each asset maintains its own participant snapshot history and intraday candle history.

### 3.2 Data collection cadence

The participant heatmap collector samples participant state on a fixed interval configured in the backend. The state records:

- `sample_interval_seconds`
- `history_minutes`
- `captured_at`
- current participant rows
- last price and book snapshot
- latest candle and merged session candles

The engine was designed to operate over a recurring snapshot cadence, historically centered around a `15s` participant sampling frequency, while candles are maintained in `1m` resolution and then re-aggregated into higher intraday buckets at visualization time.

### 3.3 Primary raw inputs

For each snapshot, the system persists:

- `captured_at`
- `last_price`
- `best_bid`
- `best_ask`
- `spread`
- `imbalance`
- `last_candle`
- `participants[]`

Each participant row may include:

- `broker_id`
- `broker_name`
- `average_price`
- `average_price_float`
- `quantity`
- `quantity_float`
- `percentage_float`
- `relative_percentage_float`
- `side`
- `broker_segment`
- `origin_scope`
- `origin_registry_key`
- `is_foreign_broker`
- `is_retail_broker`

### 3.4 Broker classification

Broker origin is normalized into three institutional buckets:

- `foreign`
- `retail`
- `local_or_unclassified`

This classification is performed either from previously stored origin metadata or from an alias registry. The retail registry is explicit, not inferred from generic heuristics.

### 3.5 Output panel payload

For each asset, the panel output contains:

- `candles_1m`
- `latest_candles_1m`
- `latest_participants`
- `participant_catalog`
- `heat_points`
- `pressure_model`
- `cohort_value_map`
- `flow_regime_classifier`
- `divergence_model`
- `level_defense_model`
- `concentration_model`

This payload is the basis for all annotation logic.

## 4. Temporal Normalization and Bucketization

### 4.1 Core principle

The engine does not interpret a single participant row as a trade. It interprets the **difference between two consecutive rows for the same broker** as a local inventory change.

For each broker:

- previous snapshot quantity is stored as a baseline
- new snapshot quantity is observed
- `deltaQuantity = current_quantity - previous_quantity`

This delta is then assigned to a time bucket.

### 4.2 Time anchoring

The bucket reference time is:

- `sample_candle_time`, when available
- otherwise `captured_at`

This prevents the flow map from drifting ahead of the candle that was actually active when the snapshot was taken.

### 4.3 Supported timeframes

The front-end aggregates `1m` candles into:

- `1m`
- `3m`
- `5m`
- `10m`

The participant deltas are bucketized using the same timeframe so that flow and candle context stay aligned.

## 5. Feature Engineering Stack

The engine builds its tags from a layered feature stack.

### 5.1 Flow-map reconstruction

For each bucket, the system reconstructs:

- `buyQuantity`
- `sellQuantity`
- `netQuantity`
- `foreignBuyQuantity`
- `foreignSellQuantity`
- `retailBuyQuantity`
- `retailSellQuantity`
- `foreignPlayerCount`
- `retailPlayerCount`
- `playerCount`
- `topBuyers`
- `topSellers`
- `allPlayers`

It also estimates an execution hint for each participant using the relationship between weighted average price and candle range:

- `agressao compra (est.)`
- `passivo compra (est.)`
- `compra mista`
- `agressao venda (est.)`
- `passivo venda (est.)`
- `venda mista`

This is an estimation layer, not a native aggressor flag.

### 5.2 Indicator metrics

For each cohort (`net`, `foreign`, `retail`), the engine computes:

- `grossQuantity`
- `netQuantity`
- `grossShare`
- `flowCommitment`
- `pressureScore`
- `efficiencyScore`
- `absorptionScore`
- `fragilityScore`
- `confidenceScore`
- `responseState`
- `efficiencyState`

Interpretation:

- `pressureScore`: directional force of the cohort
- `efficiencyScore`: how much price moved in the same direction as inventory
- `absorptionScore`: high flow with limited range expansion
- `fragilityScore`: strong price travel with weak commitment
- `confidenceScore`: combination of participation share and player count

### 5.3 Divergence metrics

The engine compares `foreign` and `retail` using:

- `alignmentScore`
- `divergenceScore`
- `leadScore`
- `state`

Primary states:

- `inactive`
- `aligned_buy`
- `aligned_sell`
- `foreign_buy_vs_retail_sell`
- `foreign_sell_vs_retail_buy`
- `foreign_dominant_buy`
- `foreign_dominant_sell`
- `retail_dominant_buy`
- `retail_dominant_sell`
- `mixed_transition`

This is one of the strongest drivers of the annotation layer.

### 5.4 Concentration metrics

Using all players in the bucket, the engine computes:

- `HHI`
- `topShare`
- `effectivePlayers`
- `breadthScore`
- `concentrationScore`
- `state`

Primary states:

- `inactive`
- `single_name_push`
- `concentrated_drive`
- `broad_participation`
- `two_way_participation`
- `mixed_participation`

### 5.5 Auction / value context

The engine reads from the `cohort_value_map`:

- `poc_price`
- `value_area_low`
- `value_area_high`
- `net_ratio_score`
- per-level gross/net distribution

For each candle, it resolves:

- `above_value`
- `inside_value`
- `below_value`

This allows the annotation layer to distinguish continuation from poor trade location.

### 5.6 Flow regime classification

For each cohort and bucket, the engine classifies a regime:

- `inactive`
- `balanced_transition`
- `absorption_buy`
- `absorption_sell`
- `initiative_break_buy`
- `initiative_break_sell`
- `responsive_rejection_buy`
- `responsive_rejection_sell`
- `divergence_buy`
- `divergence_sell`
- `exhaustion_buy`
- `exhaustion_sell`

This regime combines:

- pressure
- efficiency
- absorption
- fragility
- confidence
- gross share
- event count
- value position

### 5.7 Level-defense context

The annotation engine also consumes support/resistance logic from `level_defense_model`, especially:

- `support_level`
- `resistance_level`
- `primary_state`

This is used heavily for stop-above / stop-below and rejection logic.

### 5.8 Macro context

The engine resolves the latest relevant macro news event for the bucket if it occurred within a recent time window before the candle.

This contributes:

- `newsTitle`
- `newsHeadline`
- `newsBias`
- `newsMarker`

This is used mainly in:

- `foreign_buy_aligned`
- `foreign_sell_aligned`
- trap scoring reinforcement

## 6. Annotation Construction Logic

The final annotations are built in the `buildLiquidityAnnotations(...)` stage. For each candle:

1. read bucket metrics
2. read divergence state
3. read concentration state
4. read value position
5. read level-defense state
6. read foreign and retail sub-regimes
7. read nearby macro event
8. collect the most important foreign buyers/sellers and retail buyers/sellers
9. apply deterministic rules
10. create structured annotation objects
11. rank by severity
12. keep top `3` per candle

Each annotation object contains:

- `lane`
- `type`
- `label`
- `shortLabel`
- `severity`
- `biasSide`
- `ts`
- `timeLabel`
- `detail`
- `anchorPrice`
- `characterization`
- `newsTitle`
- `newsHeadline`
- `foreignBrokerSummary`
- `retailBrokerSummary`
- `netContracts`
- `foreignContracts`
- `retailContracts`
- `grossContracts`

## 7. Institutional Pattern Definitions

### 7.1 `BT` — Bull Trap

#### Intent
Detect candles where retail buys into a structurally poor auction zone while foreign flow is the other side.

#### Inputs used
- divergence state
- retail pressure
- foreign pressure
- value position
- level-defense state
- net regime
- candle high

#### Trigger logic
The annotation is created when:

- divergence = `foreign_sell_vs_retail_buy`
- retail buying pressure is strong
- and the location is weak:
  - `above_value`
  - or rejection above
  - or `divergence_buy`
  - or `exhaustion_buy`

#### Interpretation
This is not “price went up and then failed”. It is specifically:

- retail lifting in a weak location
- foreign providing the other side
- auction context indicating poor acceptance

#### Output
- type: `bull_trap`
- short label: `BT`
- bias side: `sell`
- anchor price: `high`
- foreign seller summary
- retail buyer summary

### 7.2 `ST` — Sell Trap

#### Intent
Detect panic or poor-quality selling by retail into a strong counterparty zone.

#### Trigger logic
- divergence = `foreign_buy_vs_retail_sell`
- retail selling pressure is strong
- location is weak for selling:
  - `below_value`
  - rejection below
  - `divergence_sell`
  - `exhaustion_sell`

#### Output
- type: `sell_trap`
- short label: `ST`
- bias side: `buy`
- anchor price: `low`

### 7.3 `VT` — Retail Buying Top

#### Intent
Flag situations where retail demand is visibly pushing in the wrong place, especially with foreign flow leaning against it.

#### Trigger logic
- retail pressure is strongly positive
- foreign pressure is negative
- candle is positive

#### Interpretation
This is a behavioral tag:

- retail is chasing strength
- institutional side is not confirming
- often associated with late participation

#### Output
- type: `retail_buying_top`
- short label: `VT`
- bias side: `sell`
- anchor price: `high`

### 7.4 `VF` — Retail Selling Bottom

#### Intent
Flag capitulation or low-quality selling into stronger institutional demand.

#### Trigger logic
- retail pressure strongly negative
- foreign pressure positive
- candle negative

#### Output
- type: `retail_selling_bottom`
- short label: `VF`
- bias side: `buy`
- anchor price: `low`

### 7.5 `FC` — Foreign Buy Aligned

#### Intent
Show that institutional buying is aligned with the macro regime instead of being merely mechanical.

#### Trigger logic
- divergence = `foreign_buy_vs_retail_sell`
- macro context says `buy` or `risk-on`

#### Output
- type: `foreign_buy_aligned`
- short label: `FC`
- bias side: `buy`
- anchor price: `close`

### 7.6 `FV` — Foreign Sell Aligned

#### Intent
Show that institutional selling is aligned with macro deterioration.

#### Trigger logic
- divergence = `foreign_sell_vs_retail_buy`
- macro context says `sell` or `risk-off`

#### Output
- type: `foreign_sell_aligned`
- short label: `FV`
- bias side: `sell`
- anchor price: `close`

### 7.7 `SQ` — Short Squeeze

#### Intent
Estimate conditions in which a weak short side is vulnerable to covering.

#### Trigger logic
- divergence = `foreign_buy_vs_retail_sell`
- candle advances
- `fragilityScore` high

#### Interpretation
This tag signals vulnerability, not guaranteed squeeze completion.

#### Output
- type: `short_squeeze`
- short label: `SQ`
- bias side: `buy`
- anchor price: `high`

### 7.8 `LF` — Long Flush

#### Intent
Estimate vulnerability of long inventory to a downside flush.

#### Trigger logic
- divergence = `foreign_sell_vs_retail_buy`
- candle falls
- `fragilityScore` high

#### Output
- type: `long_flush`
- short label: `LF`
- bias side: `sell`
- anchor price: `low`

### 7.9 `LQ` — Thin Liquidity

#### Intent
Highlight moves that are being carried by poor liquidity rather than broad participation.

#### Trigger logic
- concentration state = `single_name_push`
- fragility elevated

#### Interpretation
The move may travel easily but is structurally fragile.

#### Output
- type: `thin_liquidity`
- short label: `LQ`
- bias side: candle direction
- anchor price: `close`

### 7.10 `AB` — Foreign Absorption Buy

#### Intent
Show foreign absorption on the bid side without range concession.

#### Trigger logic
- foreign regime = `absorption_buy`
- foreign absorption score high

#### Output
- type: `foreign_absorption_buy`
- short label: `AB`
- bias side: `buy`
- anchor price: `close`

### 7.11 `AV` — Foreign Absorption Sell

#### Intent
Show foreign absorption on the offer side without clean upside extension.

#### Trigger logic
- foreign regime = `absorption_sell`
- foreign absorption score high

#### Output
- type: `foreign_absorption_sell`
- short label: `AV`
- bias side: `sell`
- anchor price: `close`

### 7.12 `SA` — Stop Above

#### Intent
Mark candles that are pressing into a stop-rich zone above resistance.

#### Trigger logic
- candle high near resistance
- fragility elevated

#### Output
- type: `stop_above`
- short label: `SA`
- bias side: `sell`
- anchor price: `high`

### 7.13 `SB` — Stop Below

#### Intent
Mark candles that are pressing into a stop-rich zone below support.

#### Trigger logic
- candle low near support
- fragility elevated

#### Output
- type: `stop_below`
- short label: `SB`
- bias side: `buy`
- anchor price: `low`

### 7.14 `CT` — Retail Countertrend

#### Intent
Show that retail is trading materially against the dominant directional flow.

#### Trigger logic
- foreign and retail pressures have opposite signs
- both have meaningful directional expression

#### Output
- type: `retail_contra_trend`
- short label: `CT`
- bias side: dominant foreign side
- anchor price: `close`

## 8. Liquidity Intelligence Layer Behind the Tags

The candle-tag engine is reinforced by a broader backend liquidity-intelligence layer that computes:

- `trap_state`
- `bull_trap_score`
- `sell_trap_score`
- `squeeze_state`
- `short_squeeze_score`
- `long_liquidation_score`
- `stop_run_state`
- `liquidity_provider_state`
- `retail_microstructure_state`
- `liquidity_density_score`
- `thin_liquidity_score`
- `retail_contra_trend_score`

This layer turns raw flow and value relationships into higher-order market narratives such as:

- foreign absorbing offers
- foreign absorbing bids
- retail serving liquidity
- thin liquidity
- retail buying top
- retail selling bottom
- bull trap risk
- sell trap risk
- short squeeze risk
- long liquidation risk

The front-end annotation logic then uses a simplified, candle-local version of this same reasoning.

## 9. Why Each Functionality Exists

### Bull / sell traps
Because a move can be directionally active and still be structurally wrong if the weaker cohort is the aggressor in poor auction territory.

### Retail top / bottom tags
Because retail behavior is often most informative at poor location, especially when contrasted with foreign flow.

### Foreign aligned tags
Because not every foreign-vs-retail divergence is equal; macro alignment strengthens conviction.

### Thin liquidity
Because some moves are driven by poor participation width and should not be treated as healthy initiative.

### Absorption tags
Because not all non-moving candles are neutral; some are inventory transfer events.

### Squeeze / flush
Because directional continuation can come from vulnerable inventory rather than conviction buying/selling.

### Stop above / below
Because stop zones can create non-linear motion and help explain local acceleration.

### Retail countertrend
Because the same absolute flow intensity means very different things depending on who is on the wrong side.

## 10. Final Outputs Consumed by the Chart

The chart consumes:

- small markers plotted over the relevant candle
- a filtered tag strip above the chart
- hover cards below the chart with detailed explanation

For each visible candle event, the chart can display:

- short label
- complete label
- textual detail
- characterization
- related news headline
- foreign broker summary
- retail broker summary
- market / foreign / retail contract estimates

This design preserves readability while keeping institutional-level auditability.

## 11. Strengths

- Highly explainable
- Strong integration between auction context and player behavior
- Practical distinction between retail and foreign behavior
- Designed for chart-readability and desk usage
- Good at identifying poor-location activity and inventory asymmetry

## 12. Structural Limitations

1. No native aggressor/passive feed
   - execution style is estimated, not observed

2. Snapshot-based flow reconstruction
   - participant deltas are inferred from state transitions, not prints

3. Dependence on broker classification quality
   - foreign vs retail classification errors propagate into several tags

4. Rule-based thresholds
   - robust and explainable, but still heuristic

5. Candle-local interpretation
   - very useful tactically, but not a substitute for longer-horizon state modeling

## 13. Recommended Institutional Interpretation

The system should be interpreted as:

- a **microstructure event engine**
- a **cohort behavior interpreter**
- a **poor-location and inventory-fragility detector**
- a **macro-aware flow annotation layer**

It should **not** be interpreted as:

- native tape reading
- official open interest by broker
- precise stop positioning truth
- full aggressor-side reconstruction

## 14. Suggested Next Evolution

The most natural institutional upgrades are:

1. Move from deterministic tags to:
   - tag probability
   - follow-through probability
   - failure probability

2. Separate:
   - context
   - trigger
   - confirmation
   - invalidation

3. Add sequence persistence:
   - repeated absorption
   - failed auction persistence
   - repeated retail wrong-way participation

4. Introduce label quality review:
   - confirmed good tag
   - noisy tag
   - false positive

5. Build a training corpus using:
   - bucket metrics
   - macro context
   - resulting path after the candle
   - human review labels

## 15. Institutional Bottom Line

This engine is already more than a visual overlay. It is a rule-based, explainable, multi-layer event classifier that fuses:

- inventory variation
- cohort behavior
- value location
- macro alignment
- concentration
- fragility
- absorption
- stop vulnerability

Its strongest current edge is not predicting every move, but identifying:

- when the wrong cohort is pressing in the wrong place
- when the right cohort is aligned with context
- when the market is structurally fragile
- when price movement is inconsistent with healthy inventory transfer

That is exactly why the annotation layer exists.
