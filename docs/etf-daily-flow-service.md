# ETF Daily Flow Service

Dedicated microservice for daily ETF flow inference used by the Discovery Funds Flow Local roadmap.

## Runtime

- Runner: `backend/run_etf_daily_flow_service.py`
- PM2 wrapper: `scripts/run-etf-daily-flow-service.js`
- Default port: `5018`
- SQLite store: `backend/uploads/macro/etf_daily_flow/etf_daily_flows.sqlite`
- Default timezone: `America/Sao_Paulo`
- Default capture windows: `20:15,22:15,00:30`

The collector is intentionally separate from the main backend and from the CDA graph service. Slow issuer pages, scraper retries, or passive page changes should not block the Discovery dashboard.

## Endpoints

- `GET /health`
- `GET /api/v1/etf-daily-flow/status`
- `POST /api/v1/etf-daily-flow/discover`
- `POST /api/v1/etf-daily-flow/collect`
- `GET|POST /api/v1/etf-daily-flow/universe`
- `GET /api/v1/etf-daily-flow/observations`
- `GET /api/v1/etf-daily-flow/flows`
- `GET /api/v1/etf-daily-flow/runs`
- `GET /api/v1/etf-daily-flow/errors`
- `POST /api/v1/etf-daily-flow/collector/start`
- `POST /api/v1/etf-daily-flow/collector/stop`

## Flow Inference

The primary formula is:

```text
flow_usd = (shares_outstanding_t - shares_outstanding_t-1) * nav_t
```

If an issuer page exposes NAV and net assets but does not expose shares outstanding, the service infers shares as:

```text
shares_outstanding = total_net_assets / nav
```

Those rows are stored with lower confidence and a warning. Split-like share/NAV jumps are flagged for review and set to zero flow until reviewed.

## Scraper Health

The health payload reports:

- stale data, based on `ETF_DAILY_FLOW_MAX_STALE_HOURS`
- consecutive failures by provider/ticker
- `degraded` contracts after a failed collection
- `broken_contract` after `ETF_DAILY_FLOW_CONTRACT_FAILURE_THRESHOLD` consecutive failures
- `contract_changed` when extraction still works but the field fingerprint changed
- only active universe contracts are considered for service health, so stale contracts from deactivated catalog rows do not keep the service degraded

This is the passive break detector for page layout/API changes.

## Catalog Discovery

The first stage is `discover`: it reads the issuer's "our funds" or product-list page, extracts the ETF universe, and upserts `etf_universe`. The second stage is `collect`: it visits the fund detail pages from that discovered universe and captures NAV, shares outstanding, or AUM for inference.

By default, `collect` runs a catalog refresh first (`ETF_DAILY_FLOW_REFRESH_CATALOG_BEFORE_COLLECT=True`). That refresh:

- inserts newly listed ETFs
- reactivates ETFs still present in the issuer catalog
- deactivates ETFs missing from the latest issuer catalog when `reset_provider=true`
- records per-provider catalog health without blocking other providers when one source fails

Example:

```bash
curl -X POST http://localhost:5018/api/v1/etf-daily-flow/discover \
  -H "Content-Type: application/json" \
  -d '{"provider":"ishares","reset_provider":true}'
```

Implemented catalog adapters:

- iShares: static fallback table from the ETF investments page.
- VanEck: JSON dataset behind the ETF and mutual fund finder.
- ProShares: HTML table from the ETF finder page.
- Global X: product links from the explore page.
- State Street: JSON fund finder payload filtered to ETFs.
- Vanguard: JSON fund detail payload filtered by `profile.isETF`.
- Dimensional: public ETF fund center API with `x-selected-country: US`.
- Invesco: DNG product search API by CUSIP, with the older ETF search CSV kept as fallback.

## Capture Coverage

The collection stage stores all useful daily observations in `etf_observations`, even when a source only exposes NAV. Rows without shares or AUM are marked `shares_and_assets_missing_flow_unavailable` and do not create `etf_daily_flows` until a richer source is added.

Current source behavior:

- Flow-ready: iShares, State Street, VanEck, Invesco, ProShares, Global X.
- NAV-only: Vanguard and Dimensional through their public endpoints.
- Blocked: Schwab official site returns Akamai HTTP 403 from this runtime.

Latest capture snapshot, generated on 2026-05-28:

| Provider | Active universe | Captured funds | Flow-ready funds | NAV-only funds | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| iShares | 486 | 482 | 482 | 0 | 4 catalog links returned official HTTP 404: `EAOA`, `EAOK`, `EAOM`, `EAOR`. |
| State Street | 179 | 179 | 179 | 0 | Shares inferred from AUM/NAV. |
| VanEck | 81 | 81 | 80 | 1 | Detail page first, catalog NAV fallback when detail layout is unavailable. |
| Invesco | 238 | 238 | 238 | 0 | Uses DNG price endpoint with NAV, market value, and shares outstanding. |
| ProShares | 114 | 114 | 114 | 0 | Shares inferred from AUM/NAV where needed. |
| Global X | 115 | 115 | 115 | 0 | Non-fund `/funds/documents` link is filtered out. |
| Vanguard | 115 | 115 | 0 | 115 | Public price endpoint exposes NAV/market price, not shares/AUM. |
| Dimensional | 43 | 43 | 0 | 43 | Public fundcenter endpoint exposes NAV/market price, not shares/AUM. |
| Schwab | 1 seed | 0 | 0 | 0 | Official catalog/detail access blocked by Akamai HTTP 403. |

Schwab is implemented as a parser for the official product finder page, but the local runtime is currently blocked by Akamai with HTTP 403. The failure is recorded in catalog health as `catalog:schwab:last_status=failed` and leaves the seed fund active until an approved access path or partner API is available.

## Current Seed Universe

The bootstrap seed still covers one anchor fund for each requested issuer, but it is only a fallback until `discover` has populated the provider's full ETF universe:

- Schwab: `SCHX`
- State Street: `SPY`
- VanEck: `SMH`
- iShares: `IVV`
- Dimensional: `DFAU`
- Vanguard: `VOO`
- Invesco: `QQQ`
- ProShares: `TQQQ`
- Global X: `QYLD`

More ETFs can be added through `POST /api/v1/etf-daily-flow/universe` or `ETF_DAILY_FLOW_UNIVERSE_JSON`.
