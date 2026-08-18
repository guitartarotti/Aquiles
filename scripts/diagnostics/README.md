# Manual diagnostics

This directory contains exploratory checks that depend on live providers,
desktop applications, local captures, or production-like data. They are not
part of the automated test suite.

## Layout

- `b3/`: B3 open-interest and COTAHIST investigations.
- `options/`: OpLab, Bloomberg, options-model, and volume diagnostics.
- `providers/`: Massive provider discovery scripts.
- `feeds/`: external WebSocket and market-feed smoke checks.
- `simulation/`: manual simulation/profile format checks.
- `artifacts/`: generated local output; ignored by Git.

Run scripts from the repository root with the backend environment, for example:

```powershell
uv run --project backend --no-sync python scripts/diagnostics/options/test_provider_wiring.py
```

Provider diagnostics read credentials from the local environment. Massive
scripts require `MASSIVE_API_KEY`; never place credentials in these files.

Automated tests belong in `backend/tests` or `frontend/tests` and run through
`npm test`.
