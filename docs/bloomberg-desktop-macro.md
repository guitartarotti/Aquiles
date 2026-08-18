# Bloomberg Desktop Macro Capture

This project can now read a Bloomberg Desktop API session running on the same Windows machine through `BBComm` on `127.0.0.1:8194`.

## What it captures

- A reference basket of Bloomberg assets kept separate from AQuant contracts.
- Snapshot fields:
  - `PX_LAST`
  - `CHG_NET_1D`
  - `CHG_PCT_1D`
  - `PX_OPEN`
  - `PX_HIGH`
  - `PX_LOW`
  - `PX_VOLUME`
  - `BID`
  - `ASK`

## Install

```powershell
backend\.venv\Scripts\pip.exe install -r backend\requirements-bloomberg.txt
```

## Environment

```env
MACRO_BLOOMBERG_ENABLE=True
MACRO_BLOOMBERG_HOST=127.0.0.1
MACRO_BLOOMBERG_PORT=8194
MACRO_BLOOMBERG_TIMEOUT_SECONDS=15
MACRO_BLOOMBERG_FIELDS=PX_LAST,CHG_NET_1D,CHG_PCT_1D,PX_OPEN,PX_HIGH,PX_LOW,PX_VOLUME,BID,ASK
MACRO_BLOOMBERG_REFERENCE_SECURITIES=ITRX XOVER CDSI GEN,SCOA Comdty,CLA Comdty,MES1 Index,DMA Index,ESA Index,RTYA Index,EMHY CDSI S44 5Y,EMBIV Index,CDX HY CDSI GEN,BRAZIL CDS USD,.JPYB U Index,CDX EM CDSI S44
```

## API

- `GET /api/macro/bloomberg/status`
- `POST /api/macro/bloomberg/capture`

## Notes

- The collector integrates Bloomberg snapshots into the existing `collect_all_once` market routine.
- Bloomberg reference assets are stored under `snapshot.market.reference_assets`.
- The macro overview exposes them under `asset_behavior.reference_assets`.
- Some tickers were inferred from the screenshot and may need exact Bloomberg terminal spelling if they return `BAD_SEC`.
