import requests

from massive_common import massive_api_key

API_KEY = massive_api_key()
for ep in ["products", "product_codes", "instruments", "product"]:
    r = requests.get(f"https://api.massive.com/futures/v1/{ep}", params={"limit": 1, "apiKey": API_KEY})
    print(ep, r.status_code, r.text[:300])
    print("---")
