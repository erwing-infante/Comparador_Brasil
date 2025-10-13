# odds_service.py
import os, json, pathlib, requests
from datetime import datetime, timezone
from leagues_config import LEAGUES, BOOKMAKERS, REGIONS

API_KEY = os.getenv("ODDS_API_KEY")  # export ODDS_API_KEY=tu_key
BASE_URL = "https://api.the-odds-api.com/v4/sports/{sport_key}/odds"

def _fmt_time(iso_utc: str) -> str:
    # The Odds API devuelve Z (UTC). Lo dejamos legible.
    dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")

def _best_prices_for_event(event: dict, allowed_books: set) -> dict:
    """Devuelve mejores cuotas (home/draw/away) con su casa."""
    home = event["home_team"]
    away = event["away_team"]

    best = {
        "home": {"odd": None, "bookmaker": None},
        "draw": {"odd": None, "bookmaker": None},
        "away": {"odd": None, "bookmaker": None},
    }

    for bk in event.get("bookmakers", []):
        bk_key = bk.get("key", "").lower()
        if bk_key not in allowed_books:
            continue

        for market in bk.get("markets", []):
            if market.get("key") != "h2h":
                continue

            for o in market.get("outcomes", []):
                name = o.get("name")
                price = o.get("price")
                if name == home:
                    if best["home"]["odd"] is None or price > best["home"]["odd"]:
                        best["home"] = {"odd": price, "bookmaker": bk.get("title")}
                elif name == away:
                    if best["away"]["odd"] is None or price > best["away"]["odd"]:
                        best["away"] = {"odd": price, "bookmaker": bk.get("title")}
                elif str(name).lower() in ("draw", "empate"):
                    if best["draw"]["odd"] is None or price > best["draw"]["odd"]:
                        best["draw"] = {"odd": price, "bookmaker": bk.get("title")}

    return {
        "name": f"{home} vs {away}",
        "home": home,
        "away": away,
        "date": _fmt_time(event["commence_time"]),
        "best_home": best["home"],
        "best_draw": best["draw"],
        "best_away": best["away"],
    }

def fetch_league(sport_key: str) -> list:
    params = {
        "apiKey": API_KEY,
        "regions": REGIONS,
        "markets": "h2h",
        "oddsFormat": "decimal",
    }
    r = requests.get(BASE_URL.format(sport_key=sport_key), params=params, timeout=25)
    r.raise_for_status()
    data = r.json()

    allowed = set(b.lower() for b in BOOKMAKERS)
    matches = []
    for ev in data:
        matches.append(_best_prices_for_event(ev, allowed))
    return matches, {
        "remaining": r.headers.get("x-requests-remaining"),
        "used": r.headers.get("x-requests-used"),
    }

def update_all(save_path: str = "data/cuotas.json") -> dict:
    """Consulta todas las ligas y guarda un JSON {liga_visible: [partidos...]}."""
    if not API_KEY:
        raise RuntimeError("Falta ODDS_API_KEY en el entorno.")

    result = {}
    meta = {}
    for liga_visible, sport_key in LEAGUES.items():
        try:
            matches, m = fetch_league(sport_key)
            result[liga_visible] = matches
            meta[liga_visible] = m
        except Exception as e:
            # Si una liga falla, no rompe todo
            result[liga_visible] = []
            meta[liga_visible] = {"error": str(e)}

    pathlib.Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return {"data": result, "meta": meta}

if __name__ == "__main__":
    out = update_all()
    # Impresión de control mínima
    ok = [k for k, v in out["data"].items() if v]
    print("Ligas con datos:", ", ".join(ok) or "ninguna")
    print("Headers (uso de API):", out["meta"])