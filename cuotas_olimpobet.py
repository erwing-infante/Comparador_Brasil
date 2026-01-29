import requests
import json
import os
from datetime import datetime, timedelta, timezone
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
    ("EFL Cup", "football/england/efl_cup", False),

    ("La Liga", "football/spain/la_liga", False),
    ("Copa del Rey", "football/spain/copa_del_rey", False),

    ("Serie A", "football/italy/serie_a", False),

    ("Bundesliga", "football/germany/bundesliga", False),
    ("Copa Alemana", "football/germany/dfb_pokal", False),

    ("Ligue 1", "football/france/ligue_1", False),
    ("Copa Francia", "football/france/coupe_de_france", False),

    ("Brasileirao", "football/brazil/brasileirao_serie_a", False),
    ("Copa de Brasil", "football/brazil/copa_do_brasil", False),

    ("MLS", "football/usa/mls", False),

    ("Liga 1 Perú", "football/peru/liga_1", False),

    ("Primeira Liga", "football/portugal/primeira_liga", False),


    ("UEFA Champions League", "football/champions_league", True),
    ("UEFA Europa League", "football/europa_league", True),
    ("UEFA Conference League", "football/conference_league", True),
    ("Copa Libertadores", "football/copa_libertadores", True),
    ("Copa Sudamericana", "football/copa_sudamericana", True),
    ("Eliminatorias Europa - WC26", "football/world_cup_qualifying_-_europe", True),
]

# ============================================================
# LÍMITE 3 DÍAS
# ============================================================
HORAS_ADELANTE = 72
NOW_UTC = datetime.now(timezone.utc)
CUTOFF_UTC = NOW_UTC + timedelta(hours=HORAS_ADELANTE)

# ============================================================
# FECHA
# ============================================================
def parse_fecha(start_iso: str) -> str:
    """Convierte 2025-11-22T12:30:00Z → 2025-11-22T12:30:00.000"""
    try:
        dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000")
    except:
        return start_iso

def fecha_to_dt_utc(start_iso: str):
    """Convierte start ISO (con Z) a datetime UTC."""
    if not start_iso:
        return None
    try:
        return datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    except:
        return None

# ============================================================
# PARSEAR EVENTO
# ============================================================
def parse_event(evt, liga_nombre):
    event_info = evt.get("event", {})
    if not event_info:
        return None

    home = event_info.get("homeName")
    away = event_info.get("awayName")
    start = event_info.get("start", "")
    event_id = event_info.get("id")

    # filtros mínimos
    if not home or not away or not start:
        return None

    # ✅ filtro: excluir partidos en vivo
    if (event_info.get("state") in ("STARTED", "LIVE", "IN_PROGRESS")) or (event_info.get("live") is True) or (event_info.get("inPlay") is True) or (evt.get("live") is True):
        return None

    # ✅ filtro 72h
    dt = fecha_to_dt_utc(start)
    if dt is None or dt > CUTOFF_UTC:
        return None

    fecha = parse_fecha(start)

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

            odds = odds_raw / 1000  # Kambi
            if label == "1":
                cuota1 = odds
            elif label == "X":
                cuotaX = odds
            elif label == "2":
                cuota2 = odds

    # ✅ (Mantengo tu opción A) incluir aunque no tenga 1X2, pero solo dentro 72h
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

        parsed = []
        for evt in events:
            x = parse_event(evt, nombre)
            if x:
                parsed.append(x)

        print(f"ok {nombre}: {len(parsed)} partidos (<= {HORAS_ADELANTE}h)")
        return parsed

    except Exception as e:
        print(f"X {nombre}: ERROR {e}")
        return []

# ============================================================
# MAIN
# ============================================================
def main():
    print("\n🔍 Descargando ligas de OLIMPO (<= 72h)...\n")

    resultados = []

    # 10 workers suele ser estable
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = [ex.submit(scrape_liga, nombre, path, intl) for nombre, path, intl in LIGAS_OLIMPO]
        for future in as_completed(futures):
            resultados.extend(future.result())

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)

    print(f"\nOK Archivo generado: {OUTPUT_FILE}")
    print(f" TOTAL PARTIDOS: {len(resultados)}")

if __name__ == "__main__":
    main()
