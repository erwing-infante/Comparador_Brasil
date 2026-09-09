import requests
import json

URL = "https://api-latam.core-ix.com/api/v1/events"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/142.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.teapuesto.pe",
    "Referer": "https://www.teapuesto.pe/"
}

params = {
    "sport_id": 1,
    "lang": "es",
    "tournament_id": 1105
}

r = requests.get(URL, headers=HEADERS, params=params, timeout=20)

print("STATUS:", r.status_code)
print("URL:", r.url)
print("CONTENT-TYPE:", r.headers.get("content-type"))

try:
    data = r.json()
    print(json.dumps(data, ensure_ascii=False, indent=2)[:10000])
except Exception:
    print(r.text[:10000])