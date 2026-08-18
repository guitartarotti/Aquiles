# Options Global Triangulation Plan

## Objective

Build a global macro/quant overlay on top of the existing local options model so the desk can detect, in near real time:

- confirmed global breakouts
- local false breakouts
- strong global absorption
- idiosyncratic local dislocations with mean reversion potential
- resonance between gamma / IV / skew regions across multiple assets

This layer must **not** be coupled to ingestion. It must consume data already persisted by the options and macro pipelines and produce auditable operational outputs.

## Architectural Principles

- Keep ingestion, local options modeling, and global triangulation separated.
- Reuse persisted snapshots, model runs, and auxiliary reference assets already captured by the project.
- Prefer deterministic and auditable models over opaque black boxes.
- Support heterogeneous asset depth:
  - full options state
  - partial vol/skew state
  - price-only proxy state
- Degrade gracefully when options coverage is unavailable.

## Existing Building Blocks To Reuse

### Local options model

The current options stack already provides:

- prepared option inputs
- internal greek engine
- DEX / GEX / VEX / CEX
- spot pressure curve `HP(S)`
- zero-pressure
- max acceleration
- dealer inference by strike
- tactical range projection
- daily insight cache

### Macro / cross-asset layer

The macro stack already provides patterns that are directly reusable:

- normalized cross-asset buckets
- configurable reference assets
- cache/state persistence pattern
- timeline construction
- AI summary / panorama framing

## Global Overlay Scope

The new layer will sit above the local options model as a separate analytics package:

- `global_input_preparation`
- `dynamic_beta_model`
- `distortion_band_model`
- `global_option_state_extractor`
- `global_structural_score`
- `global_regime_classifier`
- `global_output_builder`
- `global_validation`

Recommended location:

- `backend/app/services/options_global_modeling/`

Recommended orchestrator:

- `OptionsGlobalTriangulationService`

This service will consume:

- latest local model runs from `OptionsStore`
- latest macro snapshots / reference assets
- intraday snapshot history
- optional price-only proxy history for assets without options depth

## Asset Universe And Conventions

The basket must be config-driven, not hardcoded.

Recommended config structure:

```yaml
OPTIONS_GLOBAL_TRIANGULATION_ASSETS:
  local_index:
    primary: "IBOVE Index"
    future: "XB1 Index"
    trade_symbol: "BVMF:WINM26"
    region: "BR"
    support_level: "A"
  spx_proxy:
    primary: "ESA Index"
    alternates: ["MES1 Index", "SPX Index"]
    region: "US"
    support_level: "B"
  russell:
    primary: "RTYA Index"
    alternates: ["RTY1 Index"]
    region: "US"
    support_level: "B"
  global_us_proxy:
    primary: "MES1 Index"
    region: "US"
    support_level: "C"
  emerging_markets:
    primary: "EEM US Equity"
    alternates: ["MXEF Index"]
    region: "EM"
    support_level: "B"
  europe:
    primary: "DAX Index"
    alternates: ["FDAX Index", "GXI Index"]
    region: "EU"
    support_level: "B"
  brazil_external_proxy:
    primary: "EWZ US Equity"
    region: "BR"
    support_level: "B"
```

### Support levels

- Level A: complete options-aware state
  - DEX / GEX / VEX / CEX
  - dealer core
  - zero-pressure
  - max acceleration
  - `HP(S)`
- Level B: partial options/vol state
  - ATM IV
  - skew proxy
  - term structure summary
  - local support/resistance from vol state
- Level C: price-only / proxy
  - returns
  - realized vol
  - dynamic beta
  - distortion residual

## Chosen MVP Methodology

### 1. Dynamic beta and correlation

For the MVP, use **EWMA covariance + rolling beta/correlation** instead of Kalman first.

Reason:

- robust
- easy to audit
- computationally light
- no new heavy dependencies
- deterministic for backtesting and validation

The model can later be extended to a Kalman beta as an optional mode.

### 2. Distortion band

Use a residual model of the local future against a global basket:

```text
r_local,t = alpha_t + Σ beta_i,t * r_i,t + epsilon_t
```

Where:

- `r_local,t`: local future return over the chosen intraday window
- `r_i,t`: basket asset return
- `beta_i,t`: dynamic EWMA beta
- `epsilon_t`: local-vs-global residual

Expected global-implied return:

```text
r_hat_global,t = alpha_t + Σ beta_i,t * r_i,t
```

Residual:

```text
epsilon_t = r_local,t - r_hat_global,t
```

Residual z-score:

```text
z_dist,t = epsilon_t / sigma_epsilon,t
```

Where `sigma_epsilon,t` is EWMA residual volatility.

### 3. Structural gamma / vol triangulation

For each asset, derive a normalized structural state:

- dealer core
- pinning band
- acceleration band
- zero-pressure
- skew regime
- IV state
- GEX / VEX / CEX balance

Then convert it to normalized scores:

- absorption score
- breakout score
- compression score
- release score

### 4. Global triangulation score

The global overlay score combines three blocks:

```text
FinalScore_t = a * DistortionScore_t + b * StructuralScore_t + c * CorrRegimeScore_t
```

Where:

- `DistortionScore_t`: normalized residual / band distortion
- `StructuralScore_t`: coincidence of critical dealer/gamma/vol regions across assets
- `CorrRegimeScore_t`: alignment and strength of dynamic correlation/beta transmission

## Pipeline Of Calculation

### Step 1. Build aligned intraday return windows

For each asset:

- align timestamps to common buckets, e.g. 1m or 5m
- compute returns on the same horizon
- compute EWMA realized vol
- store aligned intraday observations

### Step 2. Extract asset state

For each asset:

- if Level A:
  - read local options model run
  - extract dealer core, zero-pressure, pinning band, acceleration level, GEX/VEX/CEX, skew state
- if Level B:
  - build reduced vol state from ATM IV, downside-upside skew, term structure shape
- if Level C:
  - build price-only state using return, realized vol, distortion and location in its local range

### Step 3. Compute dynamic basket model

For the local index:

- compute EWMA covariance matrix
- derive dynamic betas versus each basket asset
- derive short correlation
- derive smoothed correlation
- estimate expected local return from basket
- compute residual and residual z-score

### Step 4. Build distortion regime

Classify:

- `fair`
- `attention`
- `strong_distortion`
- `extreme_distortion`

Suggested thresholds:

- `|z| < 1`: fair
- `1 <= |z| < 2`: attention
- `2 <= |z| < 3`: strong distortion
- `|z| >= 3`: extreme distortion

### Step 5. Build structural coincidence score

For each global asset with state:

- compute proximity to dealer core
- compute proximity to zero-pressure
- compute proximity to acceleration zone
- compute skew regime direction
- compute gamma sign / gamma dominance

Then aggregate coincidence metrics:

- number of assets near absorption zones
- number of assets near breakout zones
- weighted consistency of skew direction
- weighted consistency of gamma regime

### Step 6. Classify global regime

Initial classifier will be transparent and rule-based.

## Global State Model Per Asset

Each asset should emit a normalized local state:

```json
{
  "asset": "ESA Index",
  "support_level": "B",
  "spot": 5301.25,
  "return_intraday": 0.0041,
  "realized_vol_intraday": 0.012,
  "beta_to_local": 0.84,
  "corr_short": 0.62,
  "corr_smoothed": 0.57,
  "dealer_core": 5288.0,
  "pinning_band_low": 5279.0,
  "pinning_band_high": 5295.0,
  "acceleration_level": 5312.0,
  "zero_pressure": 5283.0,
  "gex_total": 0.0,
  "vex_total": 0.0,
  "cex_total": 0.0,
  "iv_skew_state": "downside_heavy",
  "dealer_regime_state": "compression",
  "dealer_regime_confidence": 0.71
}
```

## Structural Scores

### Local/global absorption score

High when:

- local index is near or inside pinning/dealer core
- multiple basket assets are also near their pinning/core
- GEX is positive or compressive
- skew is defensive but price is not breaking
- distortion z-score is stretched but beta/corr remain high

### Global breakout score

High when:

- local index and global basket move in same direction
- dynamic beta explains the move well
- distortion z-score is not screaming idiosyncratic divergence
- multiple assets are near acceleration zones
- skew/IV shape supports continuation
- gamma regime is non-compressive or release-oriented

### Local false breakout score

High when:

- local move is large but basket-implied move is much smaller
- distortion z-score is high
- global correlation regime is weak or fragmented
- local is near acceleration but globals are not
- global skew/gamma does not confirm

### Local mean reversion setup score

High when:

- distortion z-score is extreme
- beta model says local is far from basket-implied fair value
- structural states of global assets lean absorption/compression
- local move appears idiosyncratic, not globally confirmed

## Regime Classifier

Initial regime labels:

- `GLOBAL_BREAKOUT_CONFIRMED`
- `LOCAL_FALSE_BREAKOUT`
- `GLOBAL_ABSORPTION`
- `LOCAL_MEAN_REVERSION_SETUP`
- `SYNCED_RISK_ON`
- `SYNCED_RISK_OFF`
- `FRAGMENTED_REGIME`
- `GAMMA_COMPRESSION`
- `GAMMA_RELEASE`

### Suggested rule logic

#### `GLOBAL_BREAKOUT_CONFIRMED`

- global breakout score high
- absorption score low to medium
- distortion z-score moderate or low
- global sync score high

#### `LOCAL_FALSE_BREAKOUT`

- distortion z-score high
- global breakout score low
- local acceleration signal high but global confirmation weak

#### `GLOBAL_ABSORPTION`

- absorption score high
- global assets clustered near dealer core / pinning
- positive or compressive gamma regime dominant

#### `LOCAL_MEAN_REVERSION_SETUP`

- distortion z-score very high
- absorption score medium to high
- local is far from basket fair value

#### `FRAGMENTED_REGIME`

- low sync
- mixed beta/correlation regime
- mixed structural states across global assets

## Outputs

### Top-level outputs

- `global_beta_now`
- `global_corr_short`
- `global_corr_smoothed`
- `basket_expected_return`
- `local_return`
- `distortion_value`
- `distortion_sigma`
- `distortion_zscore`
- `distortion_band_low`
- `distortion_band_high`
- `distortion_regime`
- `global_absorption_score`
- `global_breakout_score`
- `global_sync_score`
- `global_structural_score`
- `global_regime`
- `global_regime_confidence`

### Asset-level outputs

Per global asset:

- `asset`
- `support_level`
- `spot`
- `return_intraday`
- `realized_vol_intraday`
- `beta_to_local`
- `corr_short`
- `corr_smoothed`
- `dealer_core`
- `pinning_band_low`
- `pinning_band_high`
- `acceleration_level`
- `zero_pressure`
- `skew_state`
- `iv_state`
- `local_absorption_score`
- `local_breakout_score`

### Desk summary output

Human-readable operational output:

- local index: `ahead / behind / fair`
- global absorption: `high / medium / low`
- global breakout confirmation: `high / medium / low`
- dealer zone alignment across assets: `yes / partial / no`
- top explaining assets now: ranked list

## Fallback Strategy

### When options data exists

Use full local options state.

### When only partial options state exists

Use:

- ATM IV
- downside vs upside skew
- short-end term structure
- realized vol

### When only price exists

Use:

- returns
- EWMA vol
- dynamic beta
- distortion residual
- local range position

This fallback must be explicit in payloads via:

- `support_level`
- `state_quality_score`
- `state_source`

## Data Interfaces

### Inputs

- local options model run payloads from `OptionsStore`
- macro/reference asset snapshot history
- Bloomberg auxiliary assets already configured
- historical local model runs for intraday validation

### Outputs

Persist under:

- `backend/uploads/options/analytics/global_runs/`
- optional manifest:
  - `global_runs_manifest.json`

Suggested API:

- `GET /api/options/global/latest`
- `POST /api/options/global/run`
- `GET /api/options/global/run/<run_id>`

## Suggested Code Modules

```text
backend/app/services/options_global_modeling/
  __init__.py
  types.py
  input_preparation.py
  dynamic_beta_model.py
  distortion_band_model.py
  option_state_extractor.py
  structural_score.py
  regime_classifier.py
  outputs.py
  service.py
  validation.py
```

## Chosen MVP

Implement first:

1. dynamic beta via EWMA covariance
2. local-vs-global distortion z-score
3. global asset state extraction with support levels A/B/C
4. structural score from dealer zones / skew / gamma regime
5. transparent regime classifier
6. operational summary output

Do **not** start with:

- DCC full model
- Kalman everywhere
- complex ML classifier
- dependency on complete chain coverage for every global asset

## Validation Plan

Minimum validation layer:

1. compare `price-only` vs `price + distortion` vs `price + distortion + structural triangulation`
2. check whether extreme `distortion_zscore` improves reversal detection
3. check whether dealer-zone coincidence improves breakout confirmation
4. compare true breakout vs false breakout separation

Suggested validation metrics:

- hit rate on next-window reversal
- hit rate on continuation after breakout
- precision of false breakout flag
- separation of regime labels versus realized follow-through

## Risks And Limitations

- Cross-market timestamps may not align perfectly.
- Some global assets will have only proxy-level options state.
- Dealer-zone semantics are stronger on the local index than on proxies like EWZ or EEM unless options modeling is added for them.
- Residual z-score can overreact around macro prints if buckets are too short and quotes are sparse.
- A global basket that is too US-heavy may bias the local fair-value model.

## Recommendation For MVP Choice

Use **EWMA beta + distortion band + heterogeneous structural states** first.

Why:

- enough rigor for real desk use
- low implementation risk
- strong auditability
- natural extension path to Kalman/DCC later

## Next Implementation Step

After approval, implement:

1. config schema for global assets
2. global input preparation
3. EWMA beta model
4. distortion band model
5. structural state extractor
6. regime classifier
7. persisted global run + API
