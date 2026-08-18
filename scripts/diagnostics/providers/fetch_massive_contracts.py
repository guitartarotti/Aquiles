import requests
import json

from massive_common import artifact_path, massive_api_key

API_KEY = massive_api_key()
BASE_URL = "https://api.massive.com/futures/v1/contracts"

def fetch_all_contracts():
    all_contracts = []
    offset = 0
    limit = 1000

    while True:
        params = {
            "limit": limit,
            "offset": offset,
            "sort": "product_code.asc",
            "apiKey": API_KEY,
        }
        resp = requests.get(BASE_URL, params=params)
        resp.raise_for_status()
        data = resp.json()

        # handle both list and dict with 'data' key
        if isinstance(data, list):
            batch = data
        else:
            batch = data.get("results", data.get("data", data.get("contracts", [])))

        all_contracts.extend(batch)
        print(f"  página offset={offset}: {len(batch)} registros | total={len(all_contracts)}")

        if len(batch) < limit:
            break
        offset += limit

    return all_contracts

if __name__ == "__main__":
    contracts = fetch_all_contracts()
    out_path = artifact_path("massive_contracts.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(contracts, f, indent=2, ensure_ascii=False)
    print(f"\nSalvo {len(contracts)} contratos em {out_path}")
