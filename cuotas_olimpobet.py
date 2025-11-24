import requests
import json
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

os.makedirs("data", exist_ok=True)
OUTPUT_FILE = os.path.join("data", "cuotas_olimpobet.json")

# ============================================================
# HEADERS reales (imprescindibles para OLIMPO)
# ============================================================

HEADERS = {
    "accept": "*/*",
    "accept-language": "es-PE,es-419;q=0.9,es;q=0.8",
    "origin": "https://www.olimpo.bet",
    "referer": "https://www.olimpo.bet/",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# ============================================================
# LISTA COMPLETA DE LIGAS (actualizada)
# ============================================================

LIGAS_OLIMPO = [
    ("Premier League", "football/england/premier_league", False),
    ("FA Cup", "football/england/fa_cup", False),
    ("Carabao", "football/england/efl_trophy", False),
    ("Championship", "football/england/the_championship", False),

    ("La Liga", "football/spain/la_liga", False),
    ("La Liga 2", "football/spain/la_liga_2", False),

    ("Serie A", "football/italy/serie_a", False),
    ("Copa Italia", "football/italy/coppa_italia", False),

    ("Bundesliga", "football/germany/bundesliga", False),
    ("Copa Alemana", "football/germany/dfb_pokal", False),

    ("Ligue 1", "football/france/ligue_1", False),

    ("Brasileirao", "football/brazil/brasileirao_serie_a", False),
    ("Copa de Brasil", "football/brazil/copa_do_brasil", False),

    ("Liga MX", "football/mexico/liga_mx", False),
    ("MLS", "football/usa/mls", False),

    ("Liga 1 Perú", "football/peru/liga_1", False),

    ("Primeira Liga", "football/portugal/primeira_liga", False),

    ("Eredivisie", "football/netherlands/eredivisie", False),

    ("UEFA Champions League", "football/champions_league", True),
    ("UEFA Europa League", "football/europa_league", True),
    ("UEFA Conference League", "football/conference_league", True),
    ("Copa Libertadores", "football/copa_libertadores", True),
    ("Copa Sudamericana", "football/copa_sudamericana", True),
    ("Eliminatorias Europa - WC26", "football/world_cup_qualifying_-_europe", True),
    ("Eliminatorias Asia - WC26", "football/world_cup_qualifying_-_asia", True),
    ("Eliminatorias CONCACAF - WC26", "football/world_cup_qualifying_-_north__central___caribbean", True),
]

# ============================================================
# FORMATO DE FECHA
# ============================================================

def parse_fecha(start_iso):
    """Convierte 2025-11-22T12:30:00Z → 2025-11-22T12:30:00.000"""
    try:
        dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000")
    except:
        return start_iso


# ============================================================
# PARSEAR EVENTO (OPCIÓN A: SIEMPRE INCLUIR)
# ============================================================

def parse_event(evt, liga_nombre):
    """Extraer mercado 1X2. Si no existe, incluir evento con cuotas null."""
    event_info = evt.get("event", {})
    if not event_info:
        return None

    home = event_info.get("homeName")
    away = event_info.get("awayName")
    fecha = parse_fecha(event_info.get("start", ""))
    event_id = event_info.get("id")

    cuota1 = cuotaX = cuota2 = None

    # Buscar solo el mercado Resultado Final
    for bo in evt.get("betOffers", []):
        if bo.get("criterion", {}).get("label") != "Resultado Final":
            continue

        for oc in bo.get("outcomes", []):
            label = oc.get("label")
            odds_raw = oc.get("odds")

            if odds_raw is None:
                continue

            odds = odds_raw / 1000  # Conversión correcta Kambi

            if label == "1":
                cuota1 = odds
            elif label == "X":
                cuotaX = odds
            elif label == "2":
                cuota2 = odds

    # OPCIÓN A: incluir el partido aunque NO tenga mercado 1X2
    return {
        "Liga": liga_nombre,
        "Partido": f"{home} vs {away}",
        "Fecha": fecha,
        "Casa": "Olimpobet",
        "Local": home,
        "Visita": away,
        "Cuota Local": cuota1,
        "Cuota Empate": cuotaX,
        "Cuota Visita": cuota2,
        "EventId": event_id
    }


# ============================================================
# SCRAPER DE UNA LIGA
# ============================================================

def scrape_liga(nombre, path, internacional):
    base = "https://us1.offering-api.kambicdn.com/offering/v2018/nexuspe/listView"

    if internacional:
        url = f"{base}/{path}/all/all/matches.json?client_id=200&channel_id=1&lang=es_PE&market=PE&useCombined=true&useCombinedLive=true"
    else:
        url = f"{base}/{path}/all/matches.json?client_id=200&channel_id=1&lang=es_PE&market=PE"

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"X {nombre}: HTTP {r.status_code}")
            return []

        data = r.json()
        events = data.get("events", [])

        print(f"ok {nombre}: {len(events)} partidos")

        return [parse_event(evt, nombre) for evt in events]

    except Exception as e:
        print(f"X {nombre}: ERROR {e}")
        return []


# ============================================================
# PROCESO PRINCIPAL (MULTIHILO)
# ============================================================

def main():
    print("\n🔍 Descargando todas las ligas de OLIMPO (modo rápido)...\n")

    resultados = []

    with ThreadPoolExecutor(max_workers=20) as ex:
        futures = [
            ex.submit(scrape_liga, nombre, path, intl)
            for nombre, path, intl in LIGAS_OLIMPO
        ]

        for future in as_completed(futures):
            resultados.extend(future.result())

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)

    print(f"\nOK Archivo generado: {OUTPUT_FILE}")
    print(f" TOTAL PARTIDOS: {len(resultados)}")


if __name__ == "__main__":
    main()
