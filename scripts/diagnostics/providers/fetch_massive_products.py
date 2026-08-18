import requests
import json

from massive_common import artifact_path, massive_api_key

API_KEY = massive_api_key()
BASE_URL = "https://api.massive.com/futures/v1/products"

def fetch_all_products():
    all_products = []
    url = BASE_URL
    params = {"limit": 1000, "apiKey": API_KEY}
    page = 0

    while url:
        resp = requests.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        batch = data.get("results", [])
        all_products.extend(batch)
        page += 1
        print(f"  página {page}: {len(batch)} registros | total={len(all_products)}")

        next_url = data.get("next_url")
        if not next_url or len(batch) == 0:
            break

        # next_url já vem com cursor, mas sem apiKey
        url = next_url
        params = {"apiKey": API_KEY}

    return all_products

if __name__ == "__main__":
    products = fetch_all_products()
    out_path = artifact_path("massive_products.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
    print(f"\nSalvo {len(products)} products em {out_path}")
