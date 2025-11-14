import os
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd
import time
from requests.adapters import HTTPAdapter, Retry

# =========================================================
#   CONFIGURACIONES INTERNAS (copiado de leagues_config.py)
# =========================================================

BOOKMAKERS = [
    "Betsson",
]

LEAGUES = {
    "Premier League": {"provider": "odds-api.io", "league_id": "england-premier-league"},
    "FA Cup": {"provider": "odds-api.io", "league_id": "england-fa-cup"},
    "Carabao Cup": {"provider": "odds-api.io", "league_id": "england-efl-trophy"},
    "Championship": {"provider": "odds-api.io", "league_id": "england-championship"},
    "League One": {"provider": "odds-api.io", "league_id": "england-league-one"},

    "La Liga": {"provider": "odds-api.io", "league_id": "spain-laliga"},
    "La Liga 2": {"provider": "odds-api.io", "league_id": "spain-laliga-2"},

    "Serie A": {"provider": "odds-api.io", "league_id": "italy-serie-a"},
    "Copa Italia": {"provider": "odds-api.io", "league_id": "italy-coppa-italia"},

    "Bundesliga": {"provider": "odds-api.io", "league_id": "germany-bundesliga"},
    "2 Bundesliga": {"provider": "odds-api.io", "league_id": "germany-2-bundesliga"},
    "Copa Alemana": {"provider": "odds-api.io", "league_id": "germany-dfb-pokal"},

    "Ligue 1": {"provider": "odds-api.io", "league_id": "france-ligue-1"},

    "Brasileirao": {"provider": "odds-api.io", "league_id": "brazil-brasileiro-serie-a"},
    "Copa de Brasil": {"provider": "odds-api.io", "league_id": "brazil-copa-do-brasil"},

    "Liga MX": {"provider": "odds-api.io", "league_id": "mexico-liga-mx-apertura"},
    "MLS": {"provider": "odds-api.io", "league_id": "usa-mls"},
    "Liga 1 Perú": {"provider": "odds-api.io", "league_id": "peru-liga-1"},
    "Primeira Liga": {"provider": "odds-api.io", "league_id": "portugal-liga-portugal"},
    "Eerste Divisie": {"provider": "odds-api.io", "league_id": "netherlands-eerste-divisie"},
    "Eredivisie": {"provider": "odds-api.io", "league_id": "netherlands-eredivisie"},

    "Eliminatorias Africa - WC26": {"provider": "odds-api.io", "league_id": "international-fifa-world-cup-qualification-caf"},
    "Eliminatorias Asia AFC - WC26": {"provider": "odds-api.io", "league_id": "international-world-cup-qualification-afc"},
    "Eliminatorias CONCACAF - WC26": {"provider": "odds-api.io", "league_id": "international-world-cup-qualification-concacaf"},
    "Eliminatorias Europa - WC26": {"provider": "odds-api.io", "league_id": "international-wc-qualification-uefa"},

    "UEFA Champions League": {"provider": "odds-api.io", "league_id": "international-clubs-uefa-champions-league"},
    "UEFA Europa League": {"provider": "odds-api.io", "league_id": "international-clubs-uefa-europa-league"},
    "UEFA Conference League": {"provider": "odds-api.io", "league_id": "international-clubs-uefa-conference-league"},

    "Copa Libertadores": {"provider": "odds-api.io", "league_id": "international-clubs-copa-libertadores"},
    "Copa Sudamericana": {"provider": "odds-api.io", "league_id": "international-clubs-copa-sudamericana"},
}

# =========================================================
#   CONFIG ORIGINAL (todo lo demás sigue igual)
# =========================================================

API_KEY = "b74081b6d105c0c8bc5292cbc295fcd26b4f5b8f923a4ea63054cd9cf1c0b685"
OUT_JSON = os.path.join(os.path.dirname(__file__), "data", "cuotas_oddsapi_betsson.json")

MAX_WORKERS = 25
BATCH_SIZE = 200
REQUEST_TIMEOUT = 10
SESSION_RETRIES = 3
BACKOFF_FACTOR = 0.5

def build_session():
    s = requests.Session()
    retries = Retry(
        total=SESSION_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(['GET', 'POST'])
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "cuotas-batcher/1.0"})
    return s

SESSION = build_session()


def obtener_cuotas_evento(ev, nombre_liga, session: requests.Session):
    event_id = ev.get("id")
    home = ev.get("home")
    away = ev.get("away")
    date = ev.get("date")

    if not event_id or not home or not away:
        return []

    url_odds = (
        "https://api.odds-api.io/v3/odds?"
        f"apiKey={API_KEY}&eventId={event_id}&market=ML&bookmakers={','.join(BOOKMAKERS)}"
    )

    try:
        r = session.get(url_odds, timeout=REQUEST_TIMEOUT)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.HTTPError as e:
        if getattr(e.response, "status_code", None) == 429:
            time.sleep(1)
        return []
    except Exception:
        return []

    resultados = []
    bookmakers = data.get("bookmakers", {}) or {}
    for casa, mercados in bookmakers.items():
        for m in mercados:
            if m.get("name") == "ML" and m.get("odds"):
                odds = m["odds"][0]
                resultados.append({
                    "Liga": nombre_liga,
                    "Fecha": date,
                    "Partido": f"{home} vs {away}",
                    "Casa": casa,
                    "Cuota Local": odds.get("home"),
                    "Cuota Empate": odds.get("draw"),
                    "Cuota Visita": odds.get("away"),
                })
    return resultados


def obtener_eventos_liga(nombre_liga, league_id, session: requests.Session):
    url_eventos = (
        f"https://api.odds-api.io/v3/events?"
        f"sport=football&league={league_id}&apiKey={API_KEY}"
    )
    try:
        resp = session.get(url_eventos, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def chunked_iterable(iterable, size):
    it = iter(iterable)
    while True:
        chunk = []
        try:
            for _ in range(size):
                chunk.append(next(it))
        except StopIteration:
            if chunk:
                yield chunk
            break
        yield chunk


def obtener_cuotas_oddsapi_io():
    filas = []
    ligas_eventos = {}
    session = SESSION

    for nombre_liga, info in LEAGUES.items():
        if info.get("provider") != "odds-api.io":
            continue

        eventos = obtener_eventos_liga(nombre_liga, info.get("league_id"), session)

        if eventos:
            eventos = [
                e for e in eventos
                if e.get("id") and e.get("home") and e.get("away")
            ]
            if eventos:
                ligas_eventos[nombre_liga] = eventos

    print(f"* Ligas con eventos: {len(ligas_eventos)}")

    tareas = []
    for nombre_liga, eventos in ligas_eventos.items():
        for ev in eventos:
            tareas.append((ev, nombre_liga))

    if not tareas:
        print("\nF No se encontraron cuotas válidas.")
        return None

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for batch in chunked_iterable(tareas, BATCH_SIZE):
            futures = {
                executor.submit(obtener_cuotas_evento, ev, nombre_liga, session):
                (ev, nombre_liga)
                for ev, nombre_liga in batch
            }
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        filas.extend(res)
                except Exception:
                    continue

            time.sleep(0.1)

    if not filas:
        print("\nF No se encontraron cuotas válidas.")
        return None

    df = pd.DataFrame(filas)
    df["Fecha"] = pd.to_datetime(df["Fecha"], utc=True, errors="coerce")
    df["Fecha"] = df["Fecha"].dt.tz_localize(None)
    df.sort_values(by=["Liga", "Fecha"], inplace=True)
    return df

if __name__ == "__main__":
    print("Consultando cuotas 1X2 en todas las ligas (modo optimizado)...\n")
    df = obtener_cuotas_oddsapi_io()
    if df is not None:
        os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
        df.to_json(OUT_JSON, orient="records", indent=2, date_format="iso")
        print(f"Ok Archivo JSON actualizado: {OUT_JSON}")