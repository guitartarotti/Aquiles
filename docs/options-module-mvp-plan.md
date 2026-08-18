# Options Module MVP Plan

This document defines the production-style MVP plan for adding an options module to the existing MiroFish backend without creating a parallel system.

The design reuses the patterns that already exist in the project today:

- Flask blueprints under `backend/app/api`
- service-layer orchestration under `backend/app/services`
- config loaded from `backend/app/config.py`
- structured logging from `backend/app/utils/logger.py`
- background collectors managed with threads and persisted state
- file-backed persistence under `backend/uploads/...`

Important constraint discovered during repo analysis:

- the current backend does not have a shared application database for core app data
- the dominant persistence pattern is JSON/JSONL/file-based stores under `backend/uploads`
- SQLite exists only inside simulation scripts and simulation artifacts, not as a general backend persistence layer

Because of that, the MVP should reuse the existing file-backed persistence style instead of introducing a new application database. The "tables/collections" below are logical entities implemented by store classes and partitioned files.

## 1. Proposed architecture

### 1.1 Module scope

Create a new `options` module integrated with the current backend and Bloomberg Desktop connection.

Initial underlying:

- `IBOVE Index`

Initial operational mapping:

- options source underlying: `IBOVE Index`
- trading context target: `WIN` future
- optional config hook for mapping: `IBOVE Index -> BVMF:WINM26`

### 1.2 Main services

Add these services under `backend/app/services`:

- `options_bloomberg_service.py`
  - wraps Bloomberg Desktop option-chain, option snapshot, daily history and intraday tick requests
  - reuses the existing Bloomberg Desktop session pattern
- `options_store.py`
  - file-backed persistence layer
  - owns paths, idempotent writes, batch manifests and query helpers
- `options_contract_service.py`
  - discovers the chain
  - normalizes contract metadata
  - validates eligibility
  - registers contracts in the contract master
- `options_universe_service.py`
  - computes structural, liquid and critical universes
  - applies the 120-business-day and moneyness filters
  - recalculates dynamic relevance scores
- `options_snapshot_service.py`
  - captures structural/liquid/critical snapshots
  - calculates derived fields during ingestion
- `options_history_service.py`
  - handles daily open-interest history
  - performs backfill and incremental updates
  - derives daily OI change when Bloomberg does not provide it directly
- `options_collector_manager.py`
  - follows the same style as `MacroCollectorManager`
  - runs periodic jobs
  - persists job state and auto-restart metadata
- `options_query_service.py`
  - prepares simple query payloads for the dashboard
  - exposes latest chain, latest snapshots and OI history in a UI-friendly shape

### 1.3 API surface

Add a dedicated blueprint under `backend/app/api/options.py`, registered in `create_app()`.

Suggested initial endpoints:

- `GET /api/options/status`
- `POST /api/options/discover`
- `GET /api/options/contracts`
- `GET /api/options/universe`
- `POST /api/options/collect`
- `POST /api/options/history/backfill`
- `POST /api/options/history/update`
- `GET /api/options/snapshot/latest`
- `GET /api/options/history/oi`
- `GET /api/options/jobs/<job_id>`

Reason for a dedicated blueprint instead of folding into `/api/macro`:

- keeps the module self-contained
- still follows the same backend architecture
- avoids overloading the already large macro route file
- keeps the future options dashboard independent while remaining integrated

### 1.4 Runtime model

The module uses the same collector pattern already used in macro:

- one lightweight manager singleton
- thread-based loops
- persisted collector state
- manual start/stop
- auto-restart supervisor
- async task wrapper for manual long jobs

## 2. Data structures / logical tables

Because the app currently uses file-backed persistence, the MVP implements logical entities as partitioned files plus store indexes.

Base directory:

- `backend/uploads/options`

### 2.1 `option_contracts`

Purpose:

- contract master / metadata registry

Suggested physical representation:

- `backend/uploads/options/contracts/contracts_master.json`
- `backend/uploads/options/contracts/contracts_by_underlying.json`

Core fields:

- `option_id`
- `bloomberg_ticker`
- `root_symbol`
- `underlying_security`
- `underlying_trade_symbol`
- `put_call`
- `strike`
- `expiry_date`
- `days_to_expiry_calendar`
- `days_to_expiry_business`
- `status`
- `discovered_at`
- `last_seen_at`
- `expired_at`
- `contract_multiplier` placeholder
- `source`

Stable key:

- `option_id = sha1(underlying_security|expiry|put_call|strike|bloomberg_ticker)`

### 2.2 `option_universe_membership`

Purpose:

- current structural/liquid/critical membership
- relevance score and reason trail

Suggested physical representation:

- `backend/uploads/options/universe/universe_state.json`
- `backend/uploads/options/universe/universe_history.jsonl`

Core fields:

- `option_id`
- `underlying_security`
- `session_date`
- `structural_eligible`
- `liquid_eligible`
- `critical_eligible`
- `relevance_score`
- `relevance_components`
- `selection_reason`
- `universe_version`
- `updated_at`

### 2.3 `option_market_snapshots`

Purpose:

- intraday snapshots for the selected universe

Suggested physical representation:

- `backend/uploads/options/snapshots/structural/YYYY-MM-DD/<batch_key>.jsonl`
- `backend/uploads/options/snapshots/liquid/YYYY-MM-DD/<batch_key>.jsonl`
- `backend/uploads/options/snapshots/critical/YYYY-MM-DD/<batch_key>.jsonl`
- `backend/uploads/options/snapshots/batches.jsonl`

Core fields:

- `snapshot_id`
- `batch_id`
- `batch_key`
- `universe_tier`
- `captured_at`
- `source_timestamp`
- `option_id`
- all raw Bloomberg snapshot fields
- all derived ingestion fields
- `quality_flags`
- `capture_status`

Idempotent key:

- `(option_id, batch_key, universe_tier)`

### 2.4 `option_open_interest_daily`

Purpose:

- historical daily OI layer
- the most important durable historical series in the MVP

Suggested physical representation:

- `backend/uploads/options/history/oi_daily/YYYY-MM-DD.jsonl`
- `backend/uploads/options/history/oi_daily/manifest.json`

Core fields:

- `trade_date`
- `option_id`
- `bloomberg_ticker`
- `underlying_security`
- `expiry_date`
- `strike`
- `put_call`
- `open_int`
- `opt_open_interest`
- `px_volume`
- `ivol_mid`
- `px_last`
- `bid`
- `ask`
- `oi_change_abs`
- `oi_change_pct`
- `history_load_type` (`backfill` or `incremental`)
- `captured_at`

Idempotent key:

- `(option_id, trade_date)`

### 2.5 `option_ticks_recent`

Purpose:

- restricted intraday raw tick store for liquid/critical only

Suggested physical representation:

- `backend/uploads/options/ticks/YYYY-MM-DD/<option_id>.jsonl`

Core fields:

- `option_id`
- `event_time`
- `event_type`
- `price`
- `size`
- `condition_code`
- `batch_id`

Retention:

- hot only

### 2.6 `option_capture_jobs`

Purpose:

- operational state, checkpoints and backfill resume

Suggested physical representation:

- `backend/uploads/options/jobs/state.json`
- `backend/uploads/options/jobs/history.jsonl`
- `backend/uploads/options/jobs/backfill_checkpoints.json`

Core fields:

- `job_id`
- `job_type`
- `status`
- `underlying_security`
- `started_at`
- `finished_at`
- `checkpoint`
- `rows_written`
- `error`

### 2.7 `option_data_quality_flags`

Purpose:

- explicit operational audit trail

Suggested physical representation:

- `backend/uploads/options/quality/flags.jsonl`

Core fields:

- `flag_id`
- `option_id`
- `snapshot_id`
- `trade_date`
- `flag_type`
- `severity`
- `message`
- `created_at`

## 3. Intraday capture flow

### 3.1 Discovery phase

1. Request `OPT_CHAIN` for `IBOVE Index`
2. Parse Bloomberg tickers
3. Normalize metadata:
   - ticker
   - underlying
   - put/call
   - strike
   - expiry
4. Compute:
   - calendar days to expiry
   - business days to expiry
5. Drop contracts that fail mandatory identity fields
6. Register/update the contract master

### 3.2 Structural universe selection

Apply these filters:

- up to `120` business days
- within configurable moneyness band
- initial band `+-12%`
- include contract only if at least one is true:
  - `OPEN_INT > 0`
  - `PX_VOLUME > 0`
  - valid bid/ask
  - near ATM
  - strategic strike

### 3.3 Snapshot capture

For selected contracts, fetch these fields:

- market:
  - `PX_LAST`
  - `BID`
  - `ASK`
  - `PX_VOLUME`
  - `VOLUME`
  - `OPEN_INT`
  - `OPT_OPEN_INTEREST`
- IV:
  - `IVOL_BID`
  - `IVOL_ASK`
  - `IVOL_MID`
  - `IVOL_LAST`
- greeks:
  - `OPT_DELTA`
  - `OPT_GAMMA`
  - `OPT_VEGA`
  - `OPT_THETA`
- greeks by base:
  - `OPT_DELTA_BID`
  - `OPT_DELTA_ASK`
  - `OPT_DELTA_MID`
  - `OPT_DELTA_LAST`
  - `OPT_GAMMA_BID`
  - `OPT_GAMMA_ASK`
  - `OPT_GAMMA_MID`
  - `OPT_GAMMA_LAST`
  - `OPT_VEGA_BID`
  - `OPT_VEGA_ASK`
  - `OPT_VEGA_MID`
  - `OPT_VEGA_LAST`
  - `OPT_THETA_BID`
  - `OPT_THETA_ASK`
  - `OPT_THETA_MID`
  - `OPT_THETA_LAST`
- underlying metadata:
  - `OPT_UNDL_PX`
  - `OPT_STRIKE_PX`
  - `OPT_EXPIRE_DT`
  - `OPT_PUT_CALL`

### 3.4 Derived fields during ingestion

At ingestion time compute:

- `mid`
- `spread_abs`
- `spread_pct`
- `moneyness_spot`
- `moneyness_forward_placeholder`
- `distance_to_atm`
- `liquidity_score_initial`
- `stale_flag_initial`
- `snapshot_id`
- `batch_id`
- `batch_key`

### 3.5 Persistence

Persist one JSONL batch per universe tier and time bucket.

Important idempotency rule:

- use deterministic `batch_key`
- if a job reruns for the same bucket, rewrite the same batch file instead of appending duplicates

## 4. Daily open-interest history flow

### 4.1 Why separate it

The daily OI layer is cheap, stable and extremely valuable for future dealer positioning inference.

It should be treated as a first-class module, not a side effect of intraday capture.

### 4.2 Data source

Use Bloomberg `HistoricalDataRequest` for:

- `OPEN_INT`
- `OPT_OPEN_INTEREST`
- `PX_VOLUME`
- `IVOL_MID`
- `PX_LAST`
- `BID` / `ASK` when available

### 4.3 Daily persistence flow

1. Determine structural contracts for the session
2. For each eligible contract, request historical range or current day
3. Normalize rows by date
4. Upsert by `(option_id, trade_date)`
5. Derive `oi_change_abs` and `oi_change_pct` from stored history
6. Persist job checkpoint and metrics

## 5. First load / backfill logic

### 5.1 Discovery-first backfill

The first OI load must start with contract discovery.

Flow:

1. discover eligible chain
2. filter to structural universe
3. split contracts in batches
4. request daily history per batch or contract
5. persist incrementally
6. store checkpoints after each batch

### 5.2 Backfill range

Suggested initial rule:

- for each contract, backfill from:
  - `max(today - configurable_lookback_days, contract_first_eligible_date)`
  - until `today`

Initial config suggestion:

- `OPTIONS_OI_BACKFILL_LOOKBACK_DAYS=180`

This is enough for MVP and avoids exploding the first run.

### 5.3 Resume strategy

Use a resumable checkpoint file:

- last completed underlying
- last completed contract index
- last requested date range
- rows persisted

If interrupted:

- restart from the last incomplete contract batch

### 5.4 Idempotency

The backfill job must upsert by `(option_id, trade_date)`.

If rerun:

- existing rows are replaced or skipped deterministically
- no duplicate daily history rows are created

## 6. Incremental daily logic

Daily incremental job:

1. refresh structural universe membership
2. request current-day daily history for eligible contracts
3. upsert today rows
4. recompute daily OI change only for affected contracts
5. write a compact job log record

Gap filling rule:

- if the latest stored trade date for a contract is older than yesterday, request the missing date range before writing today

## 7. Universe selection strategy

### 7.1 Structural universe

Purpose:

- preserve the chain that matters for surface/OI/greeks later

Rules:

- `business_days_to_expiry <= 120`
- `abs(moneyness_spot) <= configurable band`
- include if any:
  - `OPEN_INT > 0`
  - `PX_VOLUME > 0`
  - valid bid/ask
  - near ATM
  - strategic strike

### 7.2 Liquid universe

Purpose:

- more frequent intraday tracking

Dynamic criteria:

- top `N` OI by expiry
- top `N` intraday volume
- ATM neighborhood
- recent trades
- acceptable spread
- optional greek importance proxy

Recomputed periodically.

Suggested initial config:

- `OPTIONS_LIQUID_TOP_N_PER_EXPIRY=12`
- `OPTIONS_LIQUID_MAX_CONTRACTS=150`

### 7.3 Critical universe

Purpose:

- small realtime-ready set for the dashboard

Rules:

- subset of liquid universe
- nearest expiry
- ATM and close neighbors
- top OI and best current activity

Suggested initial config:

- `OPTIONS_CRITICAL_MAX_CONTRACTS=40`

### 7.4 Relevance score

Initial weighted score:

- `0.30 * atm_proximity_score`
- `0.20 * oi_rank_score`
- `0.15 * day_volume_rank_score`
- `0.10 * recent_trade_score`
- `0.10 * spread_quality_score`
- `0.10 * expiry_urgency_score`
- `0.05 * greek_importance_proxy`

Notes:

- keep the score fully configurable
- store score components for auditability
- do not use advanced dealer modeling yet

## 8. Retention and data economy

### 8.1 Hot layer

Keep only:

- critical snapshots
- liquid snapshots
- recent ticks

Suggested retention:

- `1 to 2` business days

### 8.2 Warm layer

Keep:

- consolidated intraday snapshots
- future 1m/5m aggregates

Suggested retention:

- `30 to 90` days

### 8.3 Cold layer

Keep:

- contract master
- daily OI history
- structural snapshots
- daily structural context
- job history

Suggested retention:

- long-term / primary history

### 8.4 Economy rules

- never tick-capture the full chain
- never high-frequency snapshot illiquid far-OTM contracts
- never include expiries beyond `120` business days
- re-score and demote/promo contracts across universes

## 9. Estimated data volume

These are rough MVP estimates for one underlying like `IBOVE Index`.

Assumptions:

- structural universe: `400-800` contracts
- liquid universe: `100-150` contracts initially
- critical universe: `30-40` contracts

### 9.1 Structural snapshots

At `5 min` frequency:

- `~78` batches per trading day
- `400-800` rows per batch
- roughly `31k-62k` rows/day
- expected raw JSONL footprint: roughly `40-120 MB/day`

### 9.2 Liquid snapshots

At `1 min` frequency:

- `~390` batches/day
- `100-150` rows per batch
- roughly `39k-58k` rows/day
- expected raw JSONL footprint: roughly `50-120 MB/day`

### 9.3 Critical ticks

Highly market-dependent:

- small enough to keep only in hot storage
- likely `10-80 MB/day` if restricted correctly

### 9.4 Daily OI history

Very cheap:

- a few hundred to a few thousand rows/day
- typically only a few MB/day

Conclusion:

- the expensive part is intraday snapshots
- the valuable and cheap part is daily OI history
- so the MVP should start conservative on liquid/critical frequencies

## 10. Risks and attention points

### 10.1 No central app DB today

This is the most important architectural fact.

Risk:

- if we pretend there is already an application DB, we will build the wrong thing

Decision:

- use the current file-backed persistence style
- isolate it behind store classes so a real DB can be added later without rewriting the module API

### 10.2 Business-day calculation

Risk:

- true B3 business days require a holiday calendar

MVP decision:

- implement weekday-based business-day counting with holiday-hook support
- leave a clean extension point for a proper B3 calendar later

### 10.3 Bloomberg permissions vary by field

Already observed in live tests:

- some fields work well
- some model/carry/theoretical fields may be invalid or entitlement-gated

MVP decision:

- persist the fields that were confirmed working
- mark unavailable fields explicitly instead of failing the whole batch

### 10.4 Chain churn and contract expiry

Risk:

- contract set changes every day

MVP decision:

- treat contract discovery as a routine job, not a one-off load
- maintain contract status transitions

### 10.5 Snapshot idempotency on file storage

Risk:

- append-only JSONL easily duplicates data

MVP decision:

- deterministic batch keys
- overwrite batch files per time bucket
- append only to job history, not to raw snapshot buckets

## 11. Suggested config additions

Add to `Config` later:

- `OPTIONS_DATA_DIR`
- `OPTIONS_ENABLE`
- `OPTIONS_BLOOMBERG_UNDERLYINGS`
- `OPTIONS_UNDERLYING_TO_TRADE_MAP`
- `OPTIONS_MAX_BUSINESS_DAYS`
- `OPTIONS_MONEYNESS_BAND_PCT`
- `OPTIONS_STRUCTURAL_SNAPSHOT_INTERVAL_SECONDS`
- `OPTIONS_LIQUID_SNAPSHOT_INTERVAL_SECONDS`
- `OPTIONS_CRITICAL_SNAPSHOT_INTERVAL_SECONDS`
- `OPTIONS_LIQUID_TOP_N_PER_EXPIRY`
- `OPTIONS_LIQUID_MAX_CONTRACTS`
- `OPTIONS_CRITICAL_MAX_CONTRACTS`
- `OPTIONS_OI_BACKFILL_LOOKBACK_DAYS`
- `OPTIONS_TICK_CAPTURE_ENABLE`
- `OPTIONS_TICK_RETENTION_DAYS`
- `OPTIONS_HOT_RETENTION_DAYS`
- `OPTIONS_WARM_RETENTION_DAYS`

## 12. Initial code skeleton

Suggested file tree:

```text
backend/app/api/options.py
backend/app/services/options_bloomberg_service.py
backend/app/services/options_store.py
backend/app/services/options_contract_service.py
backend/app/services/options_universe_service.py
backend/app/services/options_snapshot_service.py
backend/app/services/options_history_service.py
backend/app/services/options_collector_manager.py
backend/app/services/options_query_service.py
backend/scripts/test_options_bloomberg.py
docs/options-module-mvp-plan.md
```

Suggested Python skeleton:

```python
# backend/app/services/options_store.py
class OptionsStore:
    def __init__(self, root_dir: str | None = None): ...
    def load_contract_master(self) -> dict: ...
    def upsert_contracts(self, contracts: list[dict]) -> dict: ...
    def write_snapshot_batch(self, universe_tier: str, batch_key: str, rows: list[dict]) -> dict: ...
    def upsert_oi_daily_rows(self, rows: list[dict]) -> dict: ...
    def record_job_state(self, payload: dict) -> dict: ...
    def append_quality_flags(self, flags: list[dict]) -> None: ...
```

```python
# backend/app/services/options_bloomberg_service.py
class OptionsBloombergService(BloombergDesktopService):
    def fetch_option_chain(self, underlying_security: str) -> list[dict]: ...
    def fetch_option_snapshot(self, securities: list[str], fields: list[str]) -> list[dict]: ...
    def fetch_option_history(self, securities: list[str], start_date: str, end_date: str, fields: list[str]) -> list[dict]: ...
    def fetch_option_ticks(self, security: str, start_dt: str, end_dt: str) -> list[dict]: ...
```

```python
# backend/app/services/options_contract_service.py
class OptionsContractService:
    def discover_underlying_contracts(self, underlying_security: str) -> dict: ...
    def normalize_contract(self, bloomberg_ticker: str, underlying_security: str) -> dict: ...
    def validate_contract(self, contract: dict) -> tuple[bool, list[str]]: ...
```

```python
# backend/app/services/options_universe_service.py
class OptionsUniverseService:
    def build_structural_universe(self, contracts: list[dict], market_rows: list[dict]) -> list[dict]: ...
    def build_liquid_universe(self, contracts: list[dict], market_rows: list[dict]) -> list[dict]: ...
    def build_critical_universe(self, liquid_rows: list[dict]) -> list[dict]: ...
    def score_contract(self, row: dict) -> dict: ...
```

```python
# backend/app/services/options_snapshot_service.py
class OptionsSnapshotService:
    def collect_structural_snapshot(self, underlying_security: str) -> dict: ...
    def collect_liquid_snapshot(self, underlying_security: str) -> dict: ...
    def collect_critical_snapshot(self, underlying_security: str) -> dict: ...
    def enrich_snapshot_row(self, row: dict, contract: dict, batch_id: str) -> dict: ...
```

```python
# backend/app/services/options_history_service.py
class OptionsHistoryService:
    def backfill_open_interest_history(self, underlying_security: str) -> dict: ...
    def update_daily_open_interest(self, underlying_security: str, trade_date: str | None = None) -> dict: ...
    def derive_oi_changes(self, option_id: str) -> dict: ...
```

```python
# backend/app/services/options_collector_manager.py
class OptionsCollectorManager:
    def start(self) -> dict: ...
    def stop(self) -> dict: ...
    def status(self) -> dict: ...
    def collect_once(self, structural: bool = True, liquid: bool = True, critical: bool = True) -> dict: ...
    def backfill_once(self, underlying_security: str) -> dict: ...
```

## 13. MVP implementation order

Recommended build order for Etapa 2:

1. config entries
2. options store
3. Bloomberg option-chain + snapshot service
4. contract discovery and contract master
5. structural universe
6. daily OI history backfill
7. incremental daily OI update
8. liquid universe selection
9. intraday snapshot scheduler
10. basic query endpoints
11. smoke test script

## 14. Blocking questions

None for the architecture phase.

Assumptions used:

- we will follow the existing file-backed persistence style
- `IBOVE Index` is the first underlying
- the options dashboard can consume `/api/options` later
- the MVP prioritizes structural snapshots plus daily OI history over realtime microstructure depth
