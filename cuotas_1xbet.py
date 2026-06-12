import json
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

# ==========================================================
# CONFIG
# ==========================================================
URL = "https://col-1xbet.com/service-api/LineFeed/Get1x2_VZip"

TZ_LOCAL = ZoneInfo("America/Lima")
TZ_FECHA_1XBET = ZoneInfo("UTC")  # 1xbet viene 5 horas atrás; se toma como UTC
DIAS_A_FUTURO = 3  # 72 horas

CASA = "1xbet"

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_1xbet.json")

# Ligas detectadas desde los URLs de 1xbet
LIGAS_1xbet = {
    2708736: "Copa Mundial 2026",
    2779: "UEFA Super Cup",
    142091: "Copa Libertadores",
    1528791: "Copa Sudamericana",
    127603: "FA Cup",
    1268397: "Brasileirao",
}

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "es-US,es-PE;q=0.9,es-419;q=0.8,es;q=0.7,en;q=0.6",
    "cache-control": "no-cache",
    "content-type": "application/json",
    "is-srv": "false",
    "pragma": "no-cache",
    "referer": "https://col-1xbet.com/es/line/football/2708736-world-cup-2026",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "x-app-n": "__BETTING_APP__",
    "x-mobile-project-id": "0",
    "x-requested-with": "XMLHttpRequest",
    "x-svc-source": "__BETTING_APP__",
}

COOKIES = {
    "lng": "es",
    "tzo": "-5",
    "is12h": "0",
    "platform_type": "desktop",
    "application_locale": "es",
    "window_width": "982",
}

PARAMS = {
    "count": 500,
    "lng": "es",
    "mode": 4,
    "country": 91,
    "top": "true",
    "virtualSports": "true",
}


# ==========================================================
# UTILS
# ==========================================================
def unix_to_local_datetime(ts):
    if not ts:
        return None

    try:
        return datetime.fromtimestamp(int(ts), TZ_FECHA_1XBET)
    except Exception:
        return None


def to_iso_like_doradobet(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def is_live_or_started(ev):
    live_flags = [
        ev.get("Live"),
        ev.get("LIV"),
        ev.get("InLive"),
        ev.get("is_live"),
        ev.get("IsLive"),
    ]

    if any(str(x).lower() in ("true", "1", "yes") for x in live_flags if x is not None):
        return True

    for k in ("SS", "MS", "SST"):
        v = ev.get(k)

        if v in (None, "", 0, "0"):
            continue

        s = str(v).lower()

        if any(word in s for word in ("live", "started", "inplay", "in_play", "1st", "2nd", "half")):
            return True

    return False


def extract_1x2(ev):
    cuota_local = None
    cuota_empate = None
    cuota_visita = None

    for odd in ev.get("E", []) or []:
        if odd.get("G") != 1:
            continue

        t = odd.get("T")
        c = odd.get("C")

        if c is None:
            continue

        try:
            c = float(c)
        except Exception:
            continue

        if t == 1:
            cuota_local = c
        elif t == 2:
            cuota_empate = c
        elif t == 3:
            cuota_visita = c

    if cuota_local is None or cuota_empate is None or cuota_visita is None:
        return None

    return {
        "Cuota Local": cuota_local,
        "Cuota Empate": cuota_empate,
        "Cuota Visita": cuota_visita,
    }


# ==========================================================
# FETCH
# ==========================================================
def fetch_1xbet():
    t0 = time.time()

    r = requests.get(
        URL,
        headers=HEADERS,
        cookies=COOKIES,
        params=PARAMS,
        timeout=30,
    )

    elapsed = round(time.time() - t0, 3)

    print("GET 1xbet:", r.status_code, f"{elapsed}s")
    print("URL:", r.url)

    r.raise_for_status()

    return r.json()


# ==========================================================
# MAIN
# ==========================================================
def main():
    now = datetime.now(TZ_FECHA_1XBET)
    window_end = now + timedelta(days=DIAS_A_FUTURO)

    print(f"📆 Ventana: {now:%Y-%m-%d %H:%M:%S} -> {window_end:%Y-%m-%d %H:%M:%S} (UTC/formato casas)")

    payload = fetch_1xbet()
    events = payload.get("Value", []) or []

    rows = []

    status = {
        str(li): {
            "liga": liga,
            "eventos": 0,
            "odds": 0,
        }
        for li, liga in LIGAS_1xbet.items()
    }

    for ev in events:
        li = ev.get("LI")

        if li not in LIGAS_1xbet:
            continue

        liga_name = LIGAS_1xbet[li]

        dt = unix_to_local_datetime(ev.get("S"))

        if not dt:
            continue

        if not (now < dt <= window_end):
            continue

        if is_live_or_started(ev):
            continue

        local = ev.get("O1")
        visita = ev.get("O2")

        if not local or not visita:
            continue

        status[str(li)]["eventos"] += 1

        cuotas = extract_1x2(ev)

        if not cuotas:
            continue

        status[str(li)]["odds"] += 1

        rows.append({
            "Liga": liga_name,
            "Partido": f"{local} vs {visita}",
            "Fecha": to_iso_like_doradobet(dt.replace(tzinfo=None)),
            "Casa": CASA,
            "Local": local,
            "Visita": visita,
            "Cuota Local": cuotas["Cuota Local"],
            "Cuota Empate": cuotas["Cuota Empate"],
            "Cuota Visita": cuotas["Cuota Visita"],
            "EventId": ev.get("I"),
        })

    rows.sort(key=lambda x: x["Fecha"])

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    for _, info in status.items():
        liga = info["liga"]
        evs = info["eventos"]
        odds = info["odds"]

        if evs == 0:
            print(f"❌ {liga}: 0 eventos")
        elif odds == 0:
            print(f"⚠️ {liga}: {evs} eventos, 0 odds 1x2")
        else:
            print(f"✅ {liga}: OK ({evs} eventos, {odds} con 1x2)")

    print(f"\n💾 Total guardado: {len(rows)} partidos -> {OUT_PATH}")


if __name__ == "__main__":
    main()