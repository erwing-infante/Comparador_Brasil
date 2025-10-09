import requests
from datetime import datetime

API_KEY = "a7c3be24d5bee56ff994c1144d0b7b13"  # ⚠️ Usa tu API key aquí
SPORT = "soccer_brazil_campeonato"
REGIONS = "eu,uk,au"  # puedes ampliar si la API lo soporta
MARKETS = "h2h"

BOOKMAKERS = [
    "bet365_au",
    "leovegas_se",
    "betsson",
    "onexbet",
    "coolbet",
    "pinnacle",
    "suprabets",
    "casumo",
    "gtbets",
    "nordicbet",
    "williamhill",
    "betfair_ex_eu",
    "boombet",
    "matchbook",
    "paddypower",
    "skybet",
    "virginbet",
]

def obtener_cuotas():
    """Obtiene las cuotas 1X2 del Brasileirao desde The Odds API"""
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": REGIONS,
        "markets": MARKETS,
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print("❌ Error al obtener datos de la API:", e)
        return []

    resultados = []
    for match in data:
        home = match["home_team"]
        away = match["away_team"]
        time = datetime.fromisoformat(
            match["commence_time"].replace("Z", "+00:00")
        ).strftime("%Y-%m-%d %H:%M")

        for bookmaker in match["bookmakers"]:
            key = bookmaker["key"].lower()
            if key not in [b.lower() for b in BOOKMAKERS]:
                continue

            # Buscar mercado h2h (1X2)
            for market in bookmaker["markets"]:
                if market["key"] != "h2h":
                    continue

                outcomes = {o["name"]: o["price"] for o in market["outcomes"]}
                home_odds = outcomes.get(home)
                away_odds = outcomes.get(away)
                draw_odds = outcomes.get("Draw") or outcomes.get("Empate")

                resultados.append({
                    "fecha": time,
                    "local": home,
                    "visita": away,
                    "casa": bookmaker["title"],
                    "cuota_local": home_odds,
                    "cuota_empate": draw_odds,
                    "cuota_visita": away_odds,
                })
    return resultados