import requests, json

from massive_common import massive_api_key

API_KEY = massive_api_key()
# List all unique trading_venues from products
r = requests.get("https://api.massive.com/futures/v1/products", params={"limit": 1000, "apiKey": API_KEY})
data = r.json()
venues = set(p.get("trading_venue") for p in data.get("results", []))
print("Venues na primeira página de products:", sorted(venues))

# Check contracts for ICE venues (IFEU=ICE Futures Europe, IFUS=ICE Futures US, XICE=ICE)
print("\n=== ICE venues nos contracts ===")
for venue in ["IFEU", "IFUS", "XICE", "NDEX", "ICUS"]:
    r = requests.get("https://api.massive.com/futures/v1/contracts",
                     params={"limit": 5, "trading_venue": venue, "apiKey": API_KEY})
    data = r.json()
    batch = data.get("results", []) if isinstance(data, dict) else data
    print(f"  {venue}: {len(batch)} hits")
    for item in batch[:2]:
        print(f"    {item}")

# Also check products for ICE
print("\n=== ICE venues nos products ===")
for venue in ["IFEU", "IFUS", "XICE", "NDEX", "ICUS"]:
    r = requests.get("https://api.massive.com/futures/v1/products",
                     params={"limit": 5, "trading_venue": venue, "apiKey": API_KEY})
    data = r.json()
    batch = data.get("results", [])
    print(f"  {venue}: {len(batch)} hits")
    for item in batch[:2]:
        print(f"    {item}")
