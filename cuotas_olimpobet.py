import requests
import json
import os
import time
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

os.makedirs("data", exist_ok=True)
OUTPUT_FILE = os.path.join("data", "cuotas_olimpobet.json")
DEBUG_DIR = os.path.join("data", "debug_olimpobet")
os.makedirs(DEBUG_DIR, exist_ok=True)

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
    ("Copa Mundial 2026", "football/world_cup_2026", True),
]

HORAS_ADELANTE = 72
NOW_UTC = datetime.now(timezone.utc)
CUTOFF_UTC = NOW_UTC + timedelta(hours=HORAS_ADELANTE)

BASE_LIST = "https://us1.offering-api.kambicdn.com/offering/v2018/nexuspe/listView"
BASE_EVENT = "https://us.offering-api.kambicdn.com/offering/v2018/nexuspe/prepackcoupon/event"


def odds_to_float(x):
    if x is None:
        return None
    try:
        return round(x / 1000, 3)
    except Exception:
        return None


def parse_fecha(start_iso):
    try:
        dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000")
    except Exception:
        return start_iso


def fecha_to_dt_utc(start_iso):
    try:
        return datetime.fromisoformat(start_iso.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def es_en_vivo(evt, event_info):
    return (
        event_info.get("state") in ("STARTED", "LIVE", "IN_PROGRESS")
        or event_info.get("live") is True
        or event_info.get("inPlay") is True
        or evt.get("live") is True
    )


def get_outcome_side(oc):
    label = str(oc.get("label", "")).strip()
    outcome_label = str(oc.get("outcomeLabel", "")).strip()

    if label in ("1", "X", "2"):
        return label

    # respaldo por si Kambi cambia label
    if outcome_label in ("1", "X", "2"):
        return outcome_label

    return label


def fetch_event_detail(event_id):
    url = (
        f"{BASE_EVENT}/{event_id}.json"
        f"?lang=es_PE&market=PE&client_id=200&channel_id=1&ncid={int(time.time() * 1000)}"
    )

    r = requests.get(url, headers=HEADERS, timeout=20)

    if r.status_code != 200:
        return None

    return r.json()


def extraer_cuotas_desde_detail(detail, event_id=None):
    cuota1_normal = None
    cuotaX_normal = None
    cuota2_normal = None

    cuota1_pago = None
    cuota2_pago = None

    betoffers = detail.get("betOffers", [])

    mercados_debug = []

    for bo in betoffers:
        mercado = bo.get("criterion", {}).get("label", "").strip()
        mercados_debug.append(mercado)

        # Resultado Final normal: acá tomamos el empate
        if mercado == "Resultado Final":
            for oc in bo.get("outcomes", []):
                side = get_outcome_side(oc)
                odds = odds_to_float(oc.get("odds"))

                if odds is None:
                    continue

                if side == "1":
                    cuota1_normal = odds
                elif side == "X":
                    cuotaX_normal = odds
                elif side == "2":
                    cuota2_normal = odds

        # Pago anticipado: acá tomamos local y visita
        elif "Pago Anticipado" in mercado:
            for oc in bo.get("outcomes", []):
                side = get_outcome_side(oc)
                odds = odds_to_float(oc.get("odds"))

                if odds is None:
                    continue

                if side == "1":
                    cuota1_pago = odds
                elif side == "2":
                    cuota2_pago = odds

    # Debug si no encontró pago anticipado
    if event_id and (cuota1_pago is None or cuota2_pago is None):
        debug_path = os.path.join(DEBUG_DIR, f"event_{event_id}_mercados.json")
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(sorted(set(mercados_debug)), f, indent=2, ensure_ascii=False)

    return {
        "cuota1": cuota1_pago if cuota1_pago is not None else cuota1_normal,
        "cuotaX": cuotaX_normal,
        "cuota2": cuota2_pago if cuota2_pago is not None else cuota2_normal,
        "cuota1_normal": cuota1_normal,
        "cuota2_normal": cuota2_normal,
        "cuota1_pago": cuota1_pago,
        "cuota2_pago": cuota2_pago,
    }


def parse_event(evt, liga_nombre):
    event_info = evt.get("event", {})
    if not event_info:
        return None

    home = event_info.get("homeName")
    away = event_info.get("awayName")
    start = event_info.get("start", "")
    event_id = event_info.get("id")

    if not home or not away or not start or not event_id:
        return None

    if es_en_vivo(evt, event_info):
        return None

    dt = fecha_to_dt_utc(start)
    if dt is None or dt > CUTOFF_UTC:
        return None

    detail = fetch_event_detail(event_id)

    if not detail:
        return None

    cuotas = extraer_cuotas_desde_detail(detail, event_id)

    return {
        "Liga": liga_nombre,
        "Partido": f"{home} vs {away}",
        "Fecha": parse_fecha(start),
        "Casa": "Olimpobet",
        "Local": home,
        "Visita": away,

        # Local y visita = Pago Anticipado
        # Empate = Resultado Final normal
        "Cuota Local": cuotas["cuota1"],
        "Cuota Empate": cuotas["cuotaX"],
        "Cuota Visita": cuotas["cuota2"],

        "EventId": event_id
    }


def scrape_liga(nombre, path, internacional):
    if internacional:
        url = (
            f"{BASE_LIST}/{path}/all/all/matches.json"
            "?client_id=200&channel_id=1&lang=es_PE&market=PE"
            "&useCombined=true&useCombinedLive=true"
        )
    else:
        url = (
            f"{BASE_LIST}/{path}/all/matches.json"
            "?client_id=200&channel_id=1&lang=es_PE&market=PE"
        )

    try:
        r = requests.get(url, headers=HEADERS, timeout=20)

        if r.status_code != 200:
            print(f"X {nombre}: HTTP {r.status_code}")
            return []

        data = r.json()
        events = data.get("events", [])

        parsed = []
        for evt in events:
            item = parse_event(evt, nombre)
            if item:
                parsed.append(item)

        print(f"ok {nombre}: {len(parsed)} partidos")
        return parsed

    except Exception as e:
        print(f"X {nombre}: ERROR {e}")
        return []


def main():
    print("\nDescargando OLIMPO con prepackcoupon/event para Pago Anticipado...\n")

    resultados = []

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [
            ex.submit(scrape_liga, nombre, path, intl)
            for nombre, path, intl in LIGAS_OLIMPO
        ]

        for future in as_completed(futures):
            resultados.extend(future.result())

    resultados.sort(key=lambda x: x.get("Fecha", ""))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)

    print(f"\nOK Archivo generado: {OUTPUT_FILE}")
    print(f"TOTAL PARTIDOS: {len(resultados)}")


if __name__ == "__main__":
    main()