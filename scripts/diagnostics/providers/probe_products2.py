import requests, json
from massive_common import massive_api_key

API_KEY = massive_api_key()
r = requests.get("https://api.massive.com/futures/v1/products", params={"limit": 2, "apiKey": API_KEY})
print(r.status_code)
print(json.dumps(r.json(), indent=2))
