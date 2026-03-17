import requests
import json

API_KEY = "b74081b6d105c0c8bc5292cbc295fcd26b4f5b8f923a4ea63054cd9cf1c0b685"
URL = "https://api.odds-api.io/v3/bookmakers"

params = {
    "apiKey": API_KEY
}

r = requests.get(URL, params=params)
print("Status:", r.status_code)
if r.status_code == 200:
    data = r.json()
    print(json.dumps(data, indent=2, ensure_ascii=False))
else:
    print(r.text)
