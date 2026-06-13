import json
import os
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

BASES = [
    "https://guest.api.arcadia.pinnacle.com/0.1",
    "https://api.arcadia.pinnacle.com/0.1",
]

TZ_LOCAL = ZoneInfo("America/Lima")
DIAS_A_FUTURO = 3
CASA = "Pinnacle"
MAX_WORKERS = 8

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
DEBUG_DIR = os.path.join(DATA_DIR, "debug_pinnacle")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_pinnacle.json")
STATUS_PATH = os.path.join(DEBUG_DIR, "status_pinnacle.json")

LIGAS_PINNACLE = {
    2686: "Copa Mundial 2026",
}

HEADERS = {
    "accept": "application/json",
    "accept-language": "es-US,es-PE;q=0.9,es-419;q=0.8,es;q=0.7,en;q=0.6",
    "content-type": "application/json",
    "origin": "https://www.pinnacle.com",
    "referer": "https://www.pinnacle.com/es/soccer",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
    "x-api-key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
    "x-device-uuid": "6f97bce1-ea2548d3-de8a9b22-4e4338ea",
}


def save_debug(name, content):
    path = os.path.join(DEBUG_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, indent=2))
    return path


def american_to_decimal(price):
    price = float(price)
    if price > 0:
        return round(1 + price / 100, 3)
    return round(1 + 100 / abs(price), 3)


def parse_utc_to_local(s):
    if not s:
        return None
    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(s)
        return dt.astimezone(TZ_LOCAL)
    except Exception:
        return None


def to_iso_like_doradobet(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def get_team(ev, alignment):
    for p in ev.get("participants", []) or []:
        if p.get("alignment") == alignment:
            return p.get("name")
    return None


def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)

    # Calienta cookies básicas
    try:
        s.get("https://www.pinnacle.com/es/soccer", timeout=20)
        time.sleep(random.uniform(0.4, 1.2))
    except Exception:
        pass

    return s


def request_json(session, url, debug_name):
    try:
        r = session.get(url, timeout=30)
    except Exception as e:
        save_debug(f"{debug_name}_exception.txt", str(e))
        return None, 0, str(e)

    ct = str(r.headers.get("content-type", ""))

    if r.status_code != 200:
        save_debug(f"{debug_name}_{r.status_code}.txt", r.text[:3000])
        return None, r.status_code, r.text[:500]

    if "application/json" not in ct:
        save_debug(f"{debug_name}_not_json.txt", r.text[:3000])
        return None, r.status_code, f"not_json: {ct}"

    try:
        return r.json(), r.status_code, ""
    except Exception as e:
        save_debug(f"{debug_name}_json_error.txt", r.text[:3000])
        return None, r.status_code, str(e)


def fetch_matchups(session, league_id):
    last_status = None
    last_error = ""

    for base in BASES:
        url = f"{base}/leagues/{league_id}/matchups"
        data, st, err = request_json(session, url, f"matchups_{league_id}_{base.split('//')[1].split('.')[0]}")
        last_status = st
        last_error = err

        if isinstance(data, list):
            return data, st, "", base

    return [], last_status, last_error, None


def fetch_markets(session, base, matchup_id):
    urls = [
        f"{base}/matchups/{matchup_id}/markets/straight",
        f"{base}/matchups/{matchup_id}/markets",
    ]

    for url in urls:
        data, st, err = request_json(session, url, f"markets_{matchup_id}")
        if isinstance(data, list):
            return data, st, ""
        if isinstance(data, dict):
            for key in ("markets", "straight"):
                if isinstance(data.get(key), list):
                    return data[key], st, ""

    return None, st if "st" in locals() else 0, err if "err" in locals() else ""


def is_valid_matchup(ev, now, window_end):
    if ev.get("type") != "matchup":
        return False
    if ev.get("parentId") is not None:
        return False
    if ev.get("isLive") is True:
        return False
    if str(ev.get("status", "")).lower() not in ("pending", "open"):
        return False
    if not ev.get("hasMarkets"):
        return False

    dt = parse_utc_to_local(ev.get("startTime"))
    if not dt:
        return False

    return now < dt <= window_end


def extract_1x2(markets):
    if not markets:
        return None

    candidates = []

    for m in markets:
        if m.get("type") != "moneyline":
            continue
        if str(m.get("status", "")).lower() != "open":
            continue
        if m.get("isAlternate") is True:
            continue

        prices = m.get("prices", []) or []
        designations = {p.get("designation") for p in prices}

        if {"home", "draw", "away"}.issubset(designations):
            candidates.append(m)

    if not candidates:
        return None

    market = None
    for m in candidates:
        if m.get("period") == 0:
            market = m
            break

    if market is None:
        market = candidates[0]

    cuotas = {
        "Local": None,
        "Empate": None,
        "Visita": None,
    }

    for p in market.get("prices", []) or []:
        d = p.get("designation")
        price = p.get("price")

        if price is None:
            continue

        dec = american_to_decimal(price)

        if d == "home":
            cuotas["Local"] = dec
        elif d == "draw":
            cuotas["Empate"] = dec
        elif d == "away":
            cuotas["Visita"] = dec

    if cuotas["Local"] and cuotas["Empate"] and cuotas["Visita"]:
        return cuotas

    return None


def procesar_evento(ev):
    session = make_session()

    matchup_id = ev.get("id")
    base = ev.get("_base")
    dt = parse_utc_to_local(ev.get("startTime"))

    local = get_team(ev, "home")
    visita = get_team(ev, "away")

    if not matchup_id or not base or not dt or not local or not visita:
        return None

    time.sleep(random.uniform(0.2, 1.0))

    markets, st, err = fetch_markets(session, base, matchup_id)

    if st and st != 200:
        return None

    cuotas = extract_1x2(markets)

    if not cuotas:
        save_debug(f"markets_no_1x2_{matchup_id}.json", markets or [])
        return None

    return {
        "Liga": ev.get("LigaMancorabet"),
        "Partido": f"{local} vs {visita}",
        "Fecha": to_iso_like_doradobet(dt.replace(tzinfo=None)),
        "Casa": CASA,
        "Local": local,
        "Visita": visita,
        "Cuota Local": cuotas["Local"],
        "Cuota Empate": cuotas["Empate"],
        "Cuota Visita": cuotas["Visita"],
        "EventId": matchup_id,
    }


def main():
    now = datetime.now(TZ_LOCAL)
    window_end = now + timedelta(days=DIAS_A_FUTURO)

    print(f"📆 Ventana: {now:%Y-%m-%d %H:%M:%S} -> {window_end:%Y-%m-%d %H:%M:%S} Perú")

    session = make_session()
    eventos_para_cuotas = []

    status = {
        str(lid): {
            "liga": liga,
            "eventos_recibidos": 0,
            "eventos_72h": 0,
            "odds": 0,
            "matchups_status": None,
            "base_usada": None,
            "error": "",
        }
        for lid, liga in LIGAS_PINNACLE.items()
    }

    for league_id, liga_name in LIGAS_PINNACLE.items():
        matchups, st, err, base_usada = fetch_matchups(session, league_id)

        status[str(league_id)]["matchups_status"] = st
        status[str(league_id)]["base_usada"] = base_usada
        status[str(league_id)]["error"] = err
        status[str(league_id)]["eventos_recibidos"] = len(matchups)

        filtrados = []

        for ev in matchups:
            if not is_valid_matchup(ev, now, window_end):
                continue

            ev["LigaMancorabet"] = liga_name
            ev["_base"] = base_usada
            filtrados.append(ev)

        status[str(league_id)]["eventos_72h"] = len(filtrados)
        eventos_para_cuotas.extend(filtrados)

        print(
            f"🌐 {liga_name}: recibidos={len(matchups)} | "
            f"72h={len(filtrados)} | status={st} | base={base_usada}"
        )

        if st == 403:
            print(f"🚫 {liga_name}: Pinnacle bloqueó la request con 403. Revisa debug_pinnacle/matchups_*_403.txt")

    rows = []

    if eventos_para_cuotas:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = [ex.submit(procesar_evento, ev) for ev in eventos_para_cuotas]

            for fut in as_completed(futures):
                try:
                    row = fut.result()
                except Exception as e:
                    print(f"⚠️ Error procesando evento: {e}")
                    row = None

                if not row:
                    continue

                rows.append(row)

                for lid, liga in LIGAS_PINNACLE.items():
                    if liga == row["Liga"]:
                        status[str(lid)]["odds"] += 1
                        break

    rows.sort(key=lambda x: x["Fecha"])

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    for _, info in status.items():
        liga = info["liga"]
        evs = info["eventos_72h"]
        odds = info["odds"]
        st = info["matchups_status"]

        if st == 403:
            print(f"🚫 {liga}: bloqueado 403")
        elif evs == 0:
            print(f"❌ {liga}: 0 eventos dentro de 72h")
        elif odds == 0:
            print(f"⚠️ {liga}: {evs} eventos, 0 odds")
        else:
            print(f"✅ {liga}: OK ({evs} eventos, {odds} con 1X2)")

    print(f"\n💾 Total guardado: {len(rows)} partidos -> {OUT_PATH}")
    print(f"🧾 Status guardado -> {STATUS_PATH}")


if __name__ == "__main__":
    main()