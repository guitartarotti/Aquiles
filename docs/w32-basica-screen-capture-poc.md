# W 32 Basica Screen Capture PoC

This proof of concept captures the `W 32: Basica` Bloomberg window directly by HWND, runs local Windows OCR, and saves the parsed quotes and daily variation for low-latency live reads.

## What it does

- Finds the window by title match (`W 32: Basica`) using the Windows API.
- Captures only that panel, not the full desktop.
- Uses `PrintWindow` first so the capture is tied to the Bloomberg window instead of visible screen pixels.
- Falls back to a GDI screen crop only if HWND capture is unavailable.
- Runs OCR locally with Windows OCR through `winsdk`.
- Updates `latest.json` and `latest.csv` on every capture.
- Appends the historical daily CSV only every 5 seconds by default.
- Mirrors sampled historical rows into a local SQLite index for chart reads.
- Materializes the `XB1` cold path as 5-minute OHLC candles for Discovery.
- Groups OCR results by line and extracts:
  - `symbol`
  - `price`
  - `daily_change_pct`
- Avoids PNG snapshots and JSONL history on the live path unless image saving is explicitly re-enabled.

## Main files

- Service: `backend/app/services/market_screen_capture_service.py`
- Script: `backend/scripts/capture_w32_basica_quotes.py`
- API:
  - `POST /api/macro/screen-capture/w32-basica/capture`
  - `GET /api/macro/screen-capture/w32-basica/latest`
  - `GET /api/macro/screen-capture/w32-basica/collector/status`
  - `POST /api/macro/screen-capture/w32-basica/collector/start`
  - `POST /api/macro/screen-capture/w32-basica/collector/stop`
  - `GET /api/macro/screen-capture/w32-basica/excel-basket/latest`

## Run once

```powershell
backend\.venv\Scripts\python.exe backend\scripts\capture_w32_basica_quotes.py
```

## Run in a loop

```powershell
backend\.venv\Scripts\python.exe backend\scripts\capture_w32_basica_quotes.py --loop-seconds 0.5
```

## Useful flags

```powershell
backend\.venv\Scripts\python.exe backend\scripts\capture_w32_basica_quotes.py --json
backend\.venv\Scripts\python.exe backend\scripts\capture_w32_basica_quotes.py --loop-seconds 0.5 --iterations 10
backend\.venv\Scripts\python.exe backend\scripts\capture_w32_basica_quotes.py --window-title "W 32: Basica"
```

## Output location

Artifacts are written under:

```text
backend/uploads/options/market_screen_capture/
```

Important files:

- `latest.json`
- `latest.csv`
- `rows/YYYY-MM-DD.csv`
- `market_screen_history.sqlite3`

Optional debug artifacts can still be enabled through config, but the fast live path keeps them off.

## Config

Optional `.env` keys:

```env
MARKET_SCREEN_W32_WINDOW_TITLE=W 32: Basica
MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE=True
MARKET_SCREEN_W32_RESIDENT_ENABLE=True
MARKET_SCREEN_W32_AUTO_START=True
MARKET_SCREEN_W32_SAVE_IMAGE=False
MARKET_SCREEN_W32_KEEP_LAST_IMAGE_ONLY=True
MARKET_SCREEN_W32_MAX_AGE_SECONDS=15
MARKET_SCREEN_W32_CANONICAL_SYMBOLS_EXTRA=
MARKET_SCREEN_W32_FALLBACK_MONITOR_INDEX=2
MARKET_SCREEN_W32_FALLBACK_LEFT_RATIO=0.0
MARKET_SCREEN_W32_FALLBACK_TOP_RATIO=0.0
MARKET_SCREEN_W32_FALLBACK_WIDTH_RATIO=0.18
MARKET_SCREEN_W32_FALLBACK_HEIGHT_RATIO=0.98
MARKET_SCREEN_W32_MIN_CONFIDENCE=0.55
MARKET_SCREEN_W32_OCR_LANGUAGE=en-US
MARKET_SCREEN_W32_OCR_SCALE=2.0
MARKET_SCREEN_W32_POLL_INTERVAL_SECONDS=0.1
MARKET_SCREEN_W32_HISTORY_INTERVAL_SECONDS=5
MARKET_SCREEN_W32_HISTORY_DB_ENABLE=True
MARKET_SCREEN_W32_HISTORY_DB_PATH=
MARKET_SCREEN_W32_HISTORY_CANDLE_MINUTES=5
```

When `MARKET_SCREEN_W32_REPLACE_EXCEL_BASKET_ENABLE=True`, the backend serves the OCR payload through the same fair-value basket contract previously used by the live workbook reader.

The collector also applies a symbol-sanitization layer before persisting rows. Use `MARKET_SCREEN_W32_CANONICAL_SYMBOLS_EXTRA` to append extra canonical names when you want to lock in additional OCR corrections.

The service always tries title-based detection first. The monitor crop is only a fallback.

On the test machine, the warm live path generally updates in roughly 400-500ms per capture. A history append after the 5-second interval stays close to the same path because it appends only the daily CSV.

For Discovery chart reads, the CSV is now treated as a compatibility artifact. The `Candles XB1 + Gamma` benchmark-only path reads 5-minute OHLC candles from the SQLite index and lazily backfills missing CSV rows once, avoiding repeated full-file scans. After the cold load, the frontend polls only the latest `XB1` quote and mutates the open candle locally.

## Notes

- This is a PoC parser. It already works for the current `W 32: Basica` layout, but OCR cleanup can be refined if the table fonts, columns, or zoom level change.
- If the title changes slightly, adjust `MARKET_SCREEN_W32_WINDOW_TITLE`.
- If OCR starts missing rows, temporarily enable image saving and tune the parser bands using the latest capture.
