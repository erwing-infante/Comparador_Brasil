import requests

API_KEY = "b74081b6d105c0c8bc5292cbc295fcd26b4f5b8f923a4ea63054cd9cf1c0b685"

url_clear = f"https://api.odds-api.io/v3/bookmakers/selected/clear?apiKey={API_KEY}"
resp = requests.put(url_clear)

print("Status:", resp.status_code)
print("Response:", resp.text)
