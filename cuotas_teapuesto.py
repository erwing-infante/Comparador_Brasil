import json
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

# ==========================================================
# CONFIG
# ==========================================================
TOURNAMENT_EVENTS_URL = "https://api-latam.core-ix.com/api/v1/tournament-events"
EVENTS_URL = "https://api-latam.core-ix.com/api/v1/events"
EVENT_DETAILS_URL = "https://api-latam.core-ix.com/api/v1/event-details"

SPORT_ID = 1
LANG_EVENTS = "es"
TIME_RANGE = "all"

TZ_LOCAL = ZoneInfo("America/Lima")
DIAS_A_FUTURO = 2

MAX_WORKERS_MUNDIAL = 8

AUTH_TEAPUESTO = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpYXQiOjE3ODEyMTgwMDksImlzcyI6ImxhdGFtX2FwaSIsImV4cCI6MTQ3Nzk4Njk5MCwidXNlcl9pZCI6MCwidXNlcl90eXBlIjowLCJtYWNoaW5lX2lkIjowLCJ1c2VyX3RpbWVvdXQiOjAsImlwIjoiMTkwLjIzNy4xMi4yMDQiLCJybmRfa2V5IjowfQ.Zov-bnsXeQWC3vfC2BiilrLxuFt5jnUAgrwaZL9fZgM"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.teapuesto.pe",
    "Referer": "https://www.teapuesto.pe/",
}

HEADERS_POST = {
    **HEADERS,
    "Content-Type": "application/json",
}

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_teapuesto.json")

LIGAS_EQUIVALENCIAS = {
    "1105": "Premier League",
    #"1745": "EFL Cup",
    "1141": "La Liga",
    "1109": "Serie A",
    "1139": "Bundesliga",
    "1510": "Ligue 1",
    "130": "Brasileirao",
    "1899": "Liga 1 Perú",
    "1417": "UEFA Champions League",
    "1952": "UEFA Europa League",
    "1956": "UEFA Conference League",
    "10009": "Copa Libertadores",
    "10531": "Copa Sudamericana",
}

MUNDIAL_ID = 1197
MUNDIAL_NAME = "Copa Mundial 2026"

# ==========================================================
# UTILS
# ==========================================================
def to_iso_like_doradobet(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def parse_start_time(start_time_str: str) -> datetime | None:
    if not start_time_str:
        return None

    try:
        dt_naive = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
        return dt_naive.replace(tzinfo=TZ_LOCAL)
    except Exception:
        return None


def parse_teams(event_name: str):
    if not event_name:
        return None, None

    for sep in [" - ", " vs. ", " vs ", " v "]:
        if sep in event_name:
            a, b = event_name.split(sep, 1)
            return a.strip(), b.strip()

    return None, None


def has_live_flag(ev: dict) -> bool:
    live_keys = [
        "is_live",
        "isLive",
        "live",
        "Live",
        "in_live",
        "inLive",
        "inplay",
        "in_play",
        "is_inplay",
        "isInplay",
    ]

    for k in live_keys:
        v = ev.get(k)

        if v is True:
            return True

        if isinstance(v, (int, float)) and v == 1:
            return True

        if isinstance(v, str) and v.strip().lower() in ("1", "true", "yes", "live", "inplay", "in_play"):
            return True

    return False


def has_live_status(ev: dict) -> bool:
    status_keys = [
        "status",
        "event_status",
        "eventStatus",
        "state",
        "phase",
        "match_status",
        "matchStatus",
    ]

    bad_words = [
        "live",
        "inplay",
        "in_play",
        "started",
        "inprogress",
        "in_progress",
        "running",
        "playing",
        "halftime",
        "half-time",
        "1st",
        "2nd",
        "first half",
        "second half",
        "closed",
        "settled",
        "finished",
        "ended",
        "resulted",
        "cancelled",
        "canceled",
        "suspended",
    ]

    for k in status_keys:
        s = str(ev.get(k) or "").strip().lower()

        if not s:
            continue

        if any(word in s for word in bad_words):
            return True

    return False


def has_live_period_clock_score(ev: dict) -> bool:
    period_s = str(ev.get("period") or ev.get("current_period") or ev.get("period_name") or "").strip().lower()
    clock_s = str(ev.get("clock") or ev.get("timer") or ev.get("match_time") or ev.get("time") or "").strip()
    minute_s = str(ev.get("minute") or ev.get("matchMinute") or "").strip()
    score_v = ev.get("score") or ev.get("scores") or ev.get("result")

    if period_s not in ("", "0", "pre", "prematch", "pre-match", "notstarted", "not_started", "scheduled"):
        return True

    if clock_s not in ("", "0", "00:00", "00:00:00"):
        return True

    if minute_s not in ("", "0"):
        return True

    if score_v not in (None, "", 0, "0"):
        s = str(score_v).strip()

        if s not in ("0-0", "0:0", "0 - 0", "0 : 0"):
            return True

    return False


def is_future_prematch(ev, now, window_end):
    dt = parse_start_time(ev.get("start_time"))

    if not dt:
        return False, None

    # Solo futuros dentro de ventana
    if not (now < dt <= window_end):
        return False, dt

    # Filtro fuerte contra live
    if has_live_flag(ev):
        return False, dt

    if has_live_status(ev):
        return False, dt

    if has_live_period_clock_score(ev):
        return False, dt

    return True, dt


# ==========================================================
# FETCH LIGAS NORMALES
# ==========================================================
def fetch_tournament_events(tournament_ids):
    params = [
        ("sport_id", SPORT_ID),
        ("lang", LANG_EVENTS),
        ("time_range", TIME_RANGE),
    ]

    for tid in tournament_ids:
        params.append(("tournament_ids[]", tid))

    r = requests.get(
        TOURNAMENT_EVENTS_URL,
        headers=HEADERS,
        params=params,
        timeout=45,
    )

    r.raise_for_status()
    return r.json()


# ==========================================================
# PARSER LIGAS NORMALES
# ==========================================================
def extract_1x2_normal(payload: dict, window_start: datetime, window_end: datetime):
    out = []
    data = payload.get("data", {})
    tournaments = data.get("tournaments", {}) or {}

    status_por_liga = {}

    for tid_str, liga_name in LIGAS_EQUIVALENCIAS.items():
        tinfo = tournaments.get(tid_str)

        if not tinfo:
            status_por_liga[tid_str] = {"liga": liga_name, "eventos": 0, "odds": 0}
            continue

        events = tinfo.get("events", []) or []
        events_filtrados = []

        for ev in events:
            ok, dt = is_future_prematch(ev, window_start, window_end)

            if ok:
                events_filtrados.append((ev, dt))

        if not events_filtrados:
            status_por_liga[tid_str] = {"liga": liga_name, "eventos": 0, "odds": 0}
            continue

        count_odds = 0

        for ev, dt in events_filtrados:
            ev_id = ev.get("id")
            ev_name = ev.get("name") or ""

            home, away = parse_teams(ev_name)
            partido = f"{home} vs {away}" if home and away else ev_name

            market_1x2 = None

            for m in ev.get("markets", []) or []:
                if str(m.get("name", "")).lower().strip() == "1x2":
                    market_1x2 = m
                    break

            if not market_1x2:
                continue

            odds_items = None

            for mo in market_1x2.get("market_odds", []) or []:
                if mo.get("odds"):
                    odds_items = mo["odds"]
                    break

            if not odds_items:
                continue

            cuota_local = cuota_empate = cuota_visita = None

            for o in odds_items:
                pid = str(o.get("provider_odd_id", "")).strip()
                order = o.get("order")
                val = o.get("value")

                if val is None:
                    continue

                try:
                    val = float(val)
                except Exception:
                    continue

                if pid == "1" or order == 1:
                    cuota_local = val
                elif pid == "2" or order == 2:
                    cuota_empate = val
                elif pid == "3" or order == 3:
                    cuota_visita = val

            if cuota_local is None or cuota_empate is None or cuota_visita is None:
                continue

            count_odds += 1

            out.append({
                "Liga": liga_name,
                "Partido": partido,
                "Fecha": to_iso_like_doradobet(dt.replace(tzinfo=None)),
                "Casa": "TeApuesto",
                "Local": home,
                "Visita": away,

                # Este endpoint entrega el mercado 1X2 normal.
                # No se ha identificado un mercado PA separado,
                # por lo que PA queda en null.
                "Cuota Local": None,
                "Cuota Empate": cuota_empate,
                "Cuota Visita": None,

                # Mercado 1X2 normal para surebets.
                "Cuota Local NoPA": cuota_local,
                "Cuota Visita NoPA": cuota_visita,

                "EventId": ev_id,
            })

        status_por_liga[tid_str] = {
            "liga": liga_name,
            "eventos": len(events_filtrados),
            "odds": count_odds,
        }

    return out, status_por_liga


# ==========================================================
# MUNDIAL
# ==========================================================
def fetch_mundial_events():
    r = requests.get(
        EVENTS_URL,
        headers=HEADERS,
        params={
            "sport_id": SPORT_ID,
            "lang": LANG_EVENTS,
            "tournament_id": MUNDIAL_ID,
        },
        timeout=30,
    )

    r.raise_for_status()
    data = r.json().get("data", [])

    if not isinstance(data, list):
        return []

    return data


def fetch_event_details(event_id):
    payload = {
        "event_id": str(event_id),
        "platform": "desktop",
        "language_id": 3,
        "code": "es-ES",
        "language_code": "spa",
        "version": "v3",
        "site_code": "ta",
        "auth": AUTH_TEAPUESTO,
    }

    try:
        r = requests.post(
            EVENT_DETAILS_URL,
            headers=HEADERS_POST,
            json=payload,
            timeout=25,
        )

        if r.status_code != 200:
            return None

        return r.json()

    except Exception:
        return None


def get_data_dict(payload):
    if not isinstance(payload, dict):
        return {}

    data = payload.get("data", {})

    if isinstance(data, dict):
        return data

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and ("market_groups" in item or "event" in item):
                return item

    return {}


def extract_1x2_from_event_details(payload):
    data = get_data_dict(payload)
    market_groups = data.get("market_groups", []) or []

    for group in market_groups:
        group_name = str(group.get("name") or "").lower().strip()

        if group_name != "apuestas principales":
            continue

        for market in group.get("markets", []) or []:
            market_name = str(market.get("name") or "").lower().strip()

            if market_name != "1x2":
                continue

            for mo in market.get("market_odds", []) or []:
                odds = mo.get("odds", []) or []

                cuotas = {
                    "Local": None,
                    "Empate": None,
                    "Visita": None,
                }

                for odd in odds:
                    order = odd.get("order")
                    value = odd.get("value")

                    if value is None:
                        continue

                    try:
                        value = float(value)
                    except Exception:
                        continue

                    if order == 1:
                        cuotas["Local"] = value
                    elif order == 2:
                        cuotas["Empate"] = value
                    elif order == 3:
                        cuotas["Visita"] = value

                if all(v is not None for v in cuotas.values()):
                    return cuotas

    return None


def get_teams_from_details(payload):
    data = get_data_dict(payload)
    ev = data.get("event", {}) or {}
    competitors = ev.get("competitors", {}) or {}

    home = away = None

    if isinstance(competitors, dict):
        for c in competitors.values():
            if not isinstance(c, dict):
                continue

            if str(c.get("type") or "").lower() == "home":
                home = c.get("name")
            elif str(c.get("type") or "").lower() == "away":
                away = c.get("name")

    return home, away


def is_details_still_prematch(payload):
    data = get_data_dict(payload)
    ev = data.get("event", {}) or {}

    if not ev:
        return True

    if has_live_flag(ev):
        return False

    if has_live_status(ev):
        return False

    if has_live_period_clock_score(ev):
        return False

    return True


def process_mundial_event(ev):
    event_id = ev.get("id")
    event_name = ev.get("name") or ""
    dt = parse_start_time(ev.get("start_time"))

    if not event_id or not dt:
        return None

    details = fetch_event_details(event_id)

    if not details:
        return None

    # Segundo filtro: por si el listado decía prematch pero el detalle ya está live
    if not is_details_still_prematch(details):
        return None

    cuotas = extract_1x2_from_event_details(details)

    if not cuotas:
        return None

    home, away = get_teams_from_details(details)

    if not home or not away:
        home, away = parse_teams(event_name)

    if not home or not away:
        return None

    return {
        "Liga": MUNDIAL_NAME,
        "Partido": f"{home} vs {away}",
        "Fecha": to_iso_like_doradobet(dt.replace(tzinfo=None)),
        "Casa": "TeApuesto",
        "Local": home,
        "Visita": away,

        # El detalle solo devuelve el 1X2 principal.
        # Sin mercado PA separado, estos campos quedan null.
        "Cuota Local": None,
        "Cuota Empate": cuotas["Empate"],
        "Cuota Visita": None,

        # Mercado normal para surebets.
        "Cuota Local NoPA": cuotas["Local"],
        "Cuota Visita NoPA": cuotas["Visita"],

        "EventId": event_id,
    }


def extract_mundial_1x2(window_start, window_end):
    events = fetch_mundial_events()

    candidatos = []

    for ev in events:
        event_name = ev.get("name") or ""

        if not any(sep in event_name for sep in [" vs. ", " vs ", " - ", " v "]):
            continue

        ok, dt = is_future_prematch(ev, window_start, window_end)

        if not ok:
            continue

        candidatos.append(ev)

    rows = []

    if not candidatos:
        return rows, {
            "liga": MUNDIAL_NAME,
            "eventos": 0,
            "odds": 0,
        }

    print(f"🌎 Mundial: consultando {len(candidatos)} eventos prematch en paralelo...")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS_MUNDIAL) as executor:
        futures = [executor.submit(process_mundial_event, ev) for ev in candidatos]

        for future in as_completed(futures):
            try:
                row = future.result()
            except Exception:
                row = None

            if row:
                rows.append(row)

    rows.sort(key=lambda x: x["Fecha"])

    return rows, {
        "liga": MUNDIAL_NAME,
        "eventos": len(candidatos),
        "odds": len(rows),
    }


# ==========================================================
# MAIN
# ==========================================================
def main():
    now = datetime.now(TZ_LOCAL)
    window_end = now + timedelta(days=DIAS_A_FUTURO)

    print(f"📆 Ventana: {now:%Y-%m-%d %H:%M:%S} -> {window_end:%Y-%m-%d %H:%M:%S} (Perú)")
    print("🔒 Filtro activo: SOLO PREMATCH / FUTUROS / NO LIVE")

    all_rows = []
    status_total = {}

    tournament_ids = [int(x) for x in LIGAS_EQUIVALENCIAS.keys()]

    try:
        payload = fetch_tournament_events(tournament_ids)
        rows, status = extract_1x2_normal(payload, window_start=now, window_end=window_end)
        all_rows.extend(rows)
        status_total.update(status)
    except Exception as e:
        print(f"❌ Error ligas normales: {e}")

    try:
        mundial_rows, mundial_status = extract_mundial_1x2(now, window_end)
        all_rows.extend(mundial_rows)
        status_total["1197"] = mundial_status
    except Exception as e:
        print(f"❌ Error Mundial: {e}")

    all_rows.sort(key=lambda x: x["Fecha"])

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=2)

    for tid_str, info in status_total.items():
        liga = info["liga"]
        evs = info["eventos"]
        odds = info["odds"]

        if evs == 0:
            print(f"❌ {liga}: 0 eventos prematch")
        elif odds == 0:
            print(f"⚠️ {liga}: {evs} eventos prematch, 0 odds 1x2")
        else:
            print(f"✅ {liga}: OK ({evs} eventos prematch, {odds} con 1x2)")

    print(f"\n💾 Total guardado: {len(all_rows)} partidos -> {OUT_PATH}")


if __name__ == "__main__":
    main()