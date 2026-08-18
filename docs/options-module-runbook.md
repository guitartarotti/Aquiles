# Options Module Runbook

This runbook covers the MVP options module integrated into the existing backend.

## Scope

Current first underlying:

- `IBOVE Index`

Current trading context mapping:

- `IBOVE Index -> BVMF:WINM26`

## Environment

Set or review these variables in `.env`:

```env
OPTIONS_ENABLE=True
OPTIONS_INGEST_ENABLE=False
OPTIONS_BLOOMBERG_UNDERLYINGS=IBOVE Index
OPTIONS_UNDERLYING_TRADE_MAP=IBOVE Index=BVMF:WINM26
OPTIONS_MAX_BUSINESS_DAYS=120
OPTIONS_MONEYNESS_BAND_PCT=0.12
OPTIONS_STRUCTURAL_SNAPSHOT_INTERVAL_SECONDS=300
OPTIONS_LIQUID_SNAPSHOT_INTERVAL_SECONDS=60
OPTIONS_CRITICAL_SNAPSHOT_INTERVAL_SECONDS=30
OPTIONS_OI_BACKFILL_LOOKBACK_DAYS=180
```

## Backend API

Main endpoints:

- `GET /api/options/status`
- `POST /api/options/discover`
- `GET /api/options/contracts`
- `GET /api/options/universe`
- `POST /api/options/collect`
- `GET /api/options/snapshot/latest?tier=critical&underlying_security=IBOVE%20Index`
- `POST /api/options/history/backfill`
- `POST /api/options/history/update`
- `GET /api/options/history/oi`
- `GET /api/options/collector/status`
- `POST /api/options/collector/start`
- `POST /api/options/collector/stop`

## Smoke test

Run a manual smoke test:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\test_options_bloomberg.py --underlying "IBOVE Index"
```

Run a controlled backfill smoke test:

```powershell
backend\.venv\Scripts\python.exe backend\scripts\test_options_bloomberg.py --underlying "IBOVE Index" --backfill --lookback-days 5 --max-contracts 10
```

## Storage layout

Base folder:

- `backend/uploads/options`

Important files:

- `contracts/contracts_master.json`
- `contracts/contracts_by_underlying.json`
- `universe/universe_state.json`
- `snapshots/structural/YYYY-MM-DD/*.jsonl`
- `snapshots/liquid/YYYY-MM-DD/*.jsonl`
- `snapshots/critical/YYYY-MM-DD/*.jsonl`
- `history/oi_daily/YYYY-MM-DD.jsonl`
- `history/oi_daily/manifest.json`
- `jobs/backfill_checkpoints.json`
- `quality/flags.jsonl`

## Operational notes

- structural snapshots are the heavy layer; use them carefully
- daily OI history is cheap and should be kept as the durable history layer
- full backfills should be run in controlled batches
- use `max_contracts` in smoke runs and operational partial runs when needed
- current business-day logic is weekday-based and prepared for a future holiday calendar upgrade
