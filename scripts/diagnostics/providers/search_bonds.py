import requests, json
from collections import defaultdict

from massive_common import massive_api_key

API_KEY = massive_api_key()
# 1. Varre asset_class / asset_sub_class disponiveis nos products
print("=== Todas as asset_class / asset_sub_class disponíveis ===")
url = "https://api.massive.com/futures/v1/products"
params = {"limit": 1000, "apiKey": API_KEY}
by_class = defaultdict(set)
pages = 0

while url and pages < 5:  # apenas primeiras 5k linhas para ter ideia
    r = requests.get(url, params=params)
    data = r.json()
    batch = data.get("results", [])
    for p in batch:
        ac = p.get("asset_class", "—")
        asc = p.get("asset_sub_class", "—")
        by_class[ac].add(asc)
    url = data.get("next_url")
    params = {"apiKey": API_KEY}
    pages += 1

for ac, ascs in sorted(by_class.items()):
    print(f"  {ac}: {sorted(ascs)}")

# 2. Busca especifica por bonds / fixed income
print("\n=== Busca por 'bond' / 'fixed_income' / 'sovereign' / 'credit' ===")
for kw in ["bond", "fixed_income", "fixed income", "sovereign", "credit", "corporate", "treasury"]:
    r = requests.get("https://api.massive.com/futures/v1/products",
                     params={"limit": 5, "asset_class": kw, "apiKey": API_KEY})
    batch = r.json().get("results", [])
    print(f"  asset_class={kw}: {len(batch)} hits")

    r = requests.get("https://api.massive.com/futures/v1/products",
                     params={"limit": 5, "asset_sub_class": kw, "apiKey": API_KEY})
    batch = r.json().get("results", [])
    if batch:
        print(f"  asset_sub_class={kw}: {len(batch)} hits -> ex: {batch[0].get('name','')}")

# 3. Tenta endpoint /bonds ou /fixed-income
print("\n=== Outros endpoints ===")
for ep in ["bonds", "fixed-income", "securities", "equities", "options"]:
    r = requests.get(f"https://api.massive.com/futures/v1/{ep}",
                     params={"limit": 1, "apiKey": API_KEY})
    print(f"  /futures/v1/{ep}: {r.status_code}")

# also try non-futures base
for ep in ["bonds", "securities"]:
    r = requests.get(f"https://api.massive.com/v1/{ep}",
                     params={"limit": 1, "apiKey": API_KEY})
    print(f"  /v1/{ep}: {r.status_code}")
