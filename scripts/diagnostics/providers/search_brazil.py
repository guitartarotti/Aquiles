import requests
import json

from massive_common import artifact_path, massive_api_key

API_KEY = massive_api_key()
keywords = ["BZ", "BZ1", "IBOV", "WIN", "XB", "WDO", "DOL", "IND", "BGI", "ICF", "Brazil", "brazil"]

results = {}

# Search contracts
print("=== CONTRACTS ===")
for kw in keywords:
    for field in ["product_code", "contract_code"]:
        r = requests.get(
            "https://api.massive.com/futures/v1/contracts",
            params={"limit": 50, field: kw, "apiKey": API_KEY}
        )
        if r.status_code == 200:
            data = r.json()
            batch = data.get("results", []) if isinstance(data, dict) else data
            if batch:
                key = f"contracts:{field}={kw}"
                results[key] = batch
                print(f"  [{kw}] field={field} -> {len(batch)} hits")
                for item in batch[:3]:
                    print(f"    {item}")

# Search products
print("\n=== PRODUCTS ===")
for kw in keywords:
    r = requests.get(
        "https://api.massive.com/futures/v1/products",
        params={"limit": 50, "product_code": kw, "apiKey": API_KEY}
    )
    if r.status_code == 200:
        data = r.json()
        batch = data.get("results", [])
        if batch:
            key = f"products:product_code={kw}"
            results[key] = batch
            print(f"  [{kw}] -> {len(batch)} hits")
            for item in batch[:3]:
                print(f"    {item}")

output_path = artifact_path("massive_brazil_search.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print(f"\nTotal matches guardados em {output_path}")
