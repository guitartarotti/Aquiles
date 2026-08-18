# Options Quantitative Modeling MVP

## Architecture

The quantitative layer sits on top of the existing options capture and persistence flow and does not write into ingestion paths. It reads persisted snapshots and daily OI history from `backend/uploads/options`, reconstructs market context, computes deterministic exposures and saves model runs into `backend/uploads/options/analytics/runs`.

Logical modules:

- `options_modeling/market_context.py`
  Loads spot/forward/dividend proxies and the rate curve context.
- `options_modeling/input_preparation.py`
  Normalizes persisted option snapshots into modeling-ready contracts.
- `options_modeling/greeks_engine.py`
  Internal Black-Scholes repricing and greek engine.
- `options_modeling/signal_inference.py`
  Isolated heuristic sign layer.
- `options_modeling/exposures.py`
  Primary DEX/GEX/VEX/CEX calculations and aggregations.
- `options_modeling/spot_grid.py`
  Repricing across the spot grid.
- `options_modeling/pressure.py`
  Hedge pressure curve and dealer-region metrics.
- `options_modeling/outputs.py`
  Snapshot-level operational outputs.
- `options_modeling/service.py`
  Orchestrates a model run from persisted inputs.

## Mathematical conventions

### Time

- Base time uses business days divided by `252`.
- A positive time floor is enforced for same-day expiries to keep the engine stable.

### Forward / rate / carry

- Spot comes first from observed option snapshot `OPT_UNDL_PX`.
- Configured spot/future/dividend securities are used when available.
- Rate is linearly interpolated from configured business-day curve points.
- Carry/dividend proxy is inferred from:

`q = r - ln(F / S) / T`

When forward is unavailable, the run falls back to a deterministic zero-basis proxy and flags the source.

### Greeks

Internal repricing uses Black-Scholes with continuous carry:

- `price`
- `delta`
- `gamma`
- `vega`
- `theta`

Vanna and charm are calculated numerically:

- `vanna ~= (delta(sigma + eps) - delta(sigma - eps)) / (2 * eps)`
- `charm ~= (delta(T - eps) - delta(T + eps)) / (2 * eps)`

Observed Bloomberg greeks are used as market references and preferred current-state inputs for DEX/GEX when present.

### Exposures

- `DEX_i = s_i * OI_i * Mult_i * Delta_i`
- `GEX_i = s_i * OI_i * Mult_i * Gamma_i`
- `VEX_i = s_i * OI_i * Mult_i * Vanna_i`
- `CEX_i = s_i * OI_i * Mult_i * Charm_i`

The engine stores both raw exposures and monetized variants.

### Pressure curve

For each point in the spot grid:

- reprices all contracts
- recalculates `DEX(S)`, `GEX(S)`, `VEX(S)`, `CEX(S)`

Then:

- `HP(S) = a * GEX(S) + b * VEX(S) + c * CEX(S)`

with configurable weights.

### Dealer-region metrics

- Zero-pressure: sign crossing or nearest absolute minimum of `HP(S)`
- Max acceleration: `argmax |dHP / dS|`
- Center of mass: `sum(S * |HP|) / sum(|HP|)`
- Bands:
  - pinning
  - acceleration
  - decompression

## Sign conventions

Supported conventions:

- `neutral`
- `dealer_short_optionality`
- `heuristic`

The heuristic layer is intentionally isolated from the greek math and only uses persisted activity inputs:

- daily OI change
- volume
- ATM proximity
- time to expiry
- spread
- liquidity

When heuristic confidence is too low, the run falls back to the neutral convention.

## Pipeline

1. Load persisted snapshot batch.
2. Load latest daily OI map for the same contracts.
3. Build market context.
4. Normalize contracts into prepared modeling inputs.
5. Infer sign convention payload per option.
6. Compute primary exposures at current spot.
7. Reprice across the configured spot grid.
8. Build hedge-pressure curve and dealer-region metrics.
9. Save a deterministic model run artifact.

## Current MVP limits

- Forward selection is currently rule-based and uses the first configured observed future.
- Rate curve is config-driven for the MVP.
- Carry/dividend uses observed basis when available, otherwise deterministic fallback.
- The heuristic sign layer is intentionally simple and explicit.

## Dealer inference auxiliary layer

The modeling layer also supports an auxiliary strike-based heuristic called `dealer_inference_value`.

For each strike:

- `dealer_inference_shift = clip(R * Score_K, -R, +R)`
- `dealer_inference_value = strike + dealer_inference_shift`

with configurable default `R = 300` points.

Combined score:

- `Score_K = w_iv * S_iv + w_oi * S_oi + w_gex * S_gex + w_gamma * S_gamma`

Default weights:

- `w_iv = 0.45`
- `w_oi = 0.25`
- `w_gex = 0.20`
- `w_gamma = 0.10`

Components:

- `S_iv` from call-vs-put IV skew
- `S_oi` from call-vs-put OI imbalance
- `S_gex` from net GEX by strike
- `S_gamma` from net gamma by strike

Fallbacks:

- missing call/put pairing pushes the heuristic back toward neutral
- low IV quality reduces the effective IV weight
- low OI and low liquidity reduce confidence
- missing GEX/gamma leaves the score partial with weight renormalization

The auxiliary layer does not replace:

- `DEX(S)`
- `GEX(S)`
- `VEX(S)`
- `CEX(S)`
- `HP(S)`
- zero-pressure
- max acceleration

It is only a tactical, auditable overlay for strike-level interpretation.
