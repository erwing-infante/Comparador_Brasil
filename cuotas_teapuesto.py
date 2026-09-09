import json
import os
import time
import threading
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
TZ_LOCAL = ZoneInfo("America/Lima")
DIAS_A_FUTURO = 3

MAX_WORKERS_LIGAS = 8
MAX_WORKERS_MUNDIAL = 8

TIMEOUT_LISTADO = (6, 25)
TIMEOUT_MUNDIAL = (6, 20)
TIMEOUT_DETALLE = (6, 20)

AUTH_TEAPUESTO = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJ1c2VyX2lkIjowLCJ1c2VyX3R5cGUiOjAsIm1hY2hpbmVfaWQiOjAs"
    "ImlwIjoiIiwicm5kX2tleSI6IiIsInVzZXJfdGltZW91dCI6MH0."
    "xZ-p4NlhSRUB_UoIFQNILsSbYnpsF-ubCcNaKwVvzEY"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://www.teapuesto.pe",
    "Referer": "https://www.teapuesto.pe/",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
OUT_PATH = os.path.join(DATA_DIR, "cuotas_teapuesto.json")

# ==========================================================
# LIGAS
# ==========================================================

LIGAS_EQUIVALENCIAS = {
    "1105": "Premier League",
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
# SESSION
# ==========================================================

_thread_local = threading.local()

def get_session():
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(HEADERS)
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=16,
            pool_maxsize=16,
            max_retries=0,
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _thread_local.session = session
    return session

# ==========================================================
# UTILS
# ==========================================================

def to_iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")

def parse_start_time(value):
    if not value:
        return None

    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    )

    for fmt in formats:
        try:
            dt = datetime.strptime(value[:26], fmt)
            return dt.replace(tzinfo=TZ_LOCAL)
        except Exception:
            pass

    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo:
            return dt.astimezone(TZ_LOCAL)
        return dt.replace(tzinfo=TZ_LOCAL)
    except Exception:
        return None

def parse_teams(name):
    if not name:
        return None, None

    for sep in (" vs. ", " vs ", " - ", " v "):
        if sep in name:
            a, b = name.split(sep, 1)
            return a.strip(), b.strip()

    return None, None

# ==========================================================
# FILTRO PREMATCH
# ==========================================================

def has_live_flag(ev):
    keys = [
        "is_live", "isLive", "live", "Live", "in_live", "inLive",
        "inplay", "in_play", "is_inplay", "isInplay"
    ]

    for key in keys:
        value = ev.get(key)

        if value is True:
            return True

        if isinstance(value, (int, float)) and value == 1:
            return True

        if isinstance(value, str) and value.strip().lower() in (
            "1", "true", "yes", "live", "inplay", "in_play"
        ):
            return True

    return False

def has_live_status(ev):
    keys = [
        "status", "event_status", "eventStatus", "state", "phase",
        "match_status", "matchStatus"
    ]

    bad_words = [
        "live", "inplay", "in_play", "started", "inprogress",
        "in_progress", "running", "playing", "halftime", "half-time",
        "first half", "second half", "closed", "settled", "finished",
        "ended", "resulted", "cancelled", "canceled", "suspended"
    ]

    for key in keys:
        value = str(ev.get(key) or "").strip().lower()

        if not value:
            continue

        if any(word in value for word in bad_words):
            return True

    return False

def has_live_period_clock_score(ev):
    period = str(
        ev.get("period")
        or ev.get("current_period")
        or ev.get("period_name")
        or ""
    ).strip().lower()

    clock = str(
        ev.get("clock")
        or ev.get("timer")
        or ev.get("match_time")
        or ""
    ).strip()

    minute = str(
        ev.get("minute")
        or ev.get("matchMinute")
        or ""
    ).strip()

    if period not in (
        "", "0", "pre", "prematch", "pre-match",
        "notstarted", "not_started", "scheduled"
    ):
        return True

    if clock not in ("", "0", "00:00", "00:00:00"):
        return True

    if minute not in ("", "0"):
        return True

    return False

def is_future_prematch(ev, now, window_end):
    dt = parse_start_time(ev.get("start_time"))

    if not dt:
        return False, None

    if not (now < dt <= window_end):
        return False, dt

    if has_live_flag(ev):
        return False, dt

    if has_live_status(ev):
        return False, dt

    if has_live_period_clock_score(ev):
        return False, dt

    return True, dt

# ==========================================================
# NUEVO POST TOURNAMENT-EVENTS
# ==========================================================

def fetch_tournament_events(tournament_id):
    session = get_session()

    payload = {
        "tournament_ids": [str(tournament_id)],
        "time_range": "all",
        "event_card_type": 1,
        "event_type_id": 1,
        "platform": "desktop",
        "language_id": 3,
        "code": "es-ES",
        "language_code": "spa",
        "version": "v3",
        "site_code": "ta",
        "auth": AUTH_TEAPUESTO,
    }

    r = session.post(
        TOURNAMENT_EVENTS_URL,
        json=payload,
        timeout=TIMEOUT_LISTADO,
    )

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:250]}")

    return r.json()

# ==========================================================
# EXTRAER DATOS DEL PAYLOAD
# ==========================================================

def get_tournaments(payload):
    if not isinstance(payload, dict):
        return {}

    data = payload.get("data", {})

    if isinstance(data, dict):
        tournaments = data.get("tournaments")

        if isinstance(tournaments, dict):
            return tournaments

        # Algunas versiones pueden devolver directamente
        # los torneos dentro de data.
        return data

    return {}

def extract_1x2_normal(payload, tournament_id, now, window_end):
    tid = str(tournament_id)
    liga = LIGAS_EQUIVALENCIAS.get(tid, tid)
    rows = []

    tournaments = get_tournaments(payload)

    tinfo = tournaments.get(tid)

    if not tinfo:
        # Buscar por tournament_id si la API cambia keys.
        for _, value in tournaments.items():
            if not isinstance(value, dict):
                continue

            candidate_id = str(
                value.get("id")
                or value.get("tournament_id")
                or ""
            )

            if candidate_id == tid:
                tinfo = value
                break

    if not isinstance(tinfo, dict):
        return rows, {"liga": liga, "eventos": 0, "odds": 0}

    events = tinfo.get("events", []) or []

    if isinstance(events, dict):
        events = list(events.values())

    candidatos = []

    for ev in events:
        if not isinstance(ev, dict):
            continue

        ok, dt = is_future_prematch(ev, now, window_end)

        if ok:
            candidatos.append((ev, dt))

    count_odds = 0

    for ev, dt in candidatos:
        event_id = ev.get("id")
        event_name = ev.get("name") or ""

        home, away = parse_teams(event_name)

        if not home or not away:
            continue

        market_1x2 = None

        for market in ev.get("markets", []) or []:
            if not isinstance(market, dict):
                continue

            name = str(market.get("name") or "").strip().lower()

            if name == "1x2":
                market_1x2 = market
                break

        if not market_1x2:
            continue

        odds_items = None

        for market_odd in market_1x2.get("market_odds", []) or []:
            odds = market_odd.get("odds") if isinstance(market_odd, dict) else None

            if odds:
                odds_items = odds
                break

        if not odds_items:
            continue

        cuota_local = None
        cuota_empate = None
        cuota_visita = None

        for odd in odds_items:
            if not isinstance(odd, dict):
                continue

            provider_id = str(odd.get("provider_odd_id") or "").strip()
            order = odd.get("order")
            value = odd.get("value")

            if value is None:
                continue

            try:
                value = float(value)
            except Exception:
                continue

            try:
                order_num = int(order) if order is not None else None
            except Exception:
                order_num = None

            if provider_id == "1" or order_num == 1:
                cuota_local = value
            elif provider_id == "2" or order_num == 2:
                cuota_empate = value
            elif provider_id == "3" or order_num == 3:
                cuota_visita = value

        if cuota_local is None or cuota_empate is None or cuota_visita is None:
            continue

        count_odds += 1

        rows.append({
            "Liga": liga,
            "Partido": f"{home} vs {away}",
            "Fecha": to_iso(dt.replace(tzinfo=None)),
            "Casa": "TeApuesto",
            "Local": home,
            "Visita": away,
            "Cuota Local": None,
            "Cuota Empate": cuota_empate,
            "Cuota Visita": None,
            "Cuota Local NoPA": cuota_local,
            "Cuota Visita NoPA": cuota_visita,
            "EventId": event_id,
        })

    return rows, {
        "liga": liga,
        "eventos": len(candidatos),
        "odds": count_odds,
    }

def procesar_liga(tournament_id, now, window_end):
    tid = str(tournament_id)
    liga = LIGAS_EQUIVALENCIAS.get(tid, tid)

    try:
        payload = fetch_tournament_events(tid)
        rows, status = extract_1x2_normal(
            payload,
            tid,
            now,
            window_end,
        )
        return tid, rows, status

    except Exception as e:
        print(f"❌ Error TeApuesto {liga}: {e}")
        return tid, [], {
            "liga": liga,
            "eventos": 0,
            "odds": 0,
        }

# ==========================================================
# MUNDIAL
# ==========================================================

def fetch_mundial_events():
    session = get_session()

    payload = {
        "tournament_ids": [str(MUNDIAL_ID)],
        "time_range": "all",
        "event_card_type": 1,
        "event_type_id": 1,
        "platform": "desktop",
        "language_id": 3,
        "code": "es-ES",
        "language_code": "spa",
        "version": "v3",
        "site_code": "ta",
        "auth": AUTH_TEAPUESTO,
    }

    r = session.post(
        TOURNAMENT_EVENTS_URL,
        json=payload,
        timeout=TIMEOUT_MUNDIAL,
    )

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:250]}")

    return r.json()

def fetch_event_details(event_id):
    session = get_session()

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
        r = session.post(
            EVENT_DETAILS_URL,
            json=payload,
            timeout=TIMEOUT_DETALLE,
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
            if isinstance(item, dict) and (
                "market_groups" in item or "event" in item
            ):
                return item

    return {}

def extract_1x2_from_event_details(payload):
    data = get_data_dict(payload)
    market_groups = data.get("market_groups", []) or []

    for group in market_groups:
        if not isinstance(group, dict):
            continue

        group_name = str(group.get("name") or "").lower().strip()

        for market in group.get("markets", []) or []:
            if not isinstance(market, dict):
                continue

            market_name = str(market.get("name") or "").lower().strip()

            if market_name != "1x2":
                continue

            for mo in market.get("market_odds", []) or []:
                if not isinstance(mo, dict):
                    continue

                odds = mo.get("odds", []) or []

                cuotas = {
                    "Local": None,
                    "Empate": None,
                    "Visita": None,
                }

                for odd in odds:
                    if not isinstance(odd, dict):
                        continue

                    order = odd.get("order")
                    value = odd.get("value")

                    try:
                        order = int(order)
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

    home = None
    away = None

    if isinstance(competitors, dict):
        competitors = competitors.values()

    if isinstance(competitors, list) or hasattr(competitors, "__iter__"):
        for competitor in competitors:
            if not isinstance(competitor, dict):
                continue

            ctype = str(competitor.get("type") or "").lower()

            if ctype == "home":
                home = competitor.get("name")
            elif ctype == "away":
                away = competitor.get("name")

    return home, away

def process_mundial_event(ev, dt):
    event_id = ev.get("id")
    event_name = ev.get("name") or ""

    if not event_id:
        return None

    details = fetch_event_details(event_id)

    if not details:
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
        "Fecha": to_iso(dt.replace(tzinfo=None)),
        "Casa": "TeApuesto",
        "Local": home,
        "Visita": away,
        "Cuota Local": None,
        "Cuota Empate": cuotas["Empate"],
        "Cuota Visita": None,
        "Cuota Local NoPA": cuotas["Local"],
        "Cuota Visita NoPA": cuotas["Visita"],
        "EventId": event_id,
    }

def extract_mundial(now, window_end):
    payload = fetch_mundial_events()
    tournaments = get_tournaments(payload)

    tinfo = tournaments.get(str(MUNDIAL_ID))

    if not isinstance(tinfo, dict):
        return [], {
            "liga": MUNDIAL_NAME,
            "eventos": 0,
            "odds": 0,
        }

    events = tinfo.get("events", []) or []

    if isinstance(events, dict):
        events = list(events.values())

    candidatos = []

    for ev in events:
        if not isinstance(ev, dict):
            continue

        ok, dt = is_future_prematch(ev, now, window_end)

        if ok:
            candidatos.append((ev, dt))

    if not candidatos:
        return [], {
            "liga": MUNDIAL_NAME,
            "eventos": 0,
            "odds": 0,
        }

    print(f"🌎 Mundial: {len(candidatos)} eventos prematch")

    rows = []
    workers = min(MAX_WORKERS_MUNDIAL, len(candidatos))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(process_mundial_event, ev, dt)
            for ev, dt in candidatos
        ]

        for future in as_completed(futures):
            try:
                row = future.result()
            except Exception:
                row = None

            if row:
                rows.append(row)

    return rows, {
        "liga": MUNDIAL_NAME,
        "eventos": len(candidatos),
        "odds": len(rows),
    }

# ==========================================================
# MAIN
# ==========================================================

def main():
    started = time.perf_counter()

    now = datetime.now(TZ_LOCAL)
    window_end = now + timedelta(days=DIAS_A_FUTURO)

    print(
        f"📆 Ventana: {now:%Y-%m-%d %H:%M:%S} -> "
        f"{window_end:%Y-%m-%d %H:%M:%S} (Perú)"
    )
    print("🔒 Filtro activo: SOLO PREMATCH / FUTUROS / NO LIVE")

    all_rows = []
    status_total = {}
    tournament_ids = list(LIGAS_EQUIVALENCIAS.keys())

    with ThreadPoolExecutor(
        max_workers=min(MAX_WORKERS_LIGAS, len(tournament_ids)) + 1
    ) as executor:

        futures_ligas = {
            executor.submit(
                procesar_liga,
                tid,
                now,
                window_end,
            ): tid
            for tid in tournament_ids
        }

        future_mundial = executor.submit(
            extract_mundial,
            now,
            window_end,
        )

        for future in as_completed(futures_ligas):
            try:
                tid, rows, status = future.result()
                all_rows.extend(rows)
                status_total[tid] = status
            except Exception as e:
                print(f"❌ Error procesando liga: {e}")

        try:
            mundial_rows, mundial_status = future_mundial.result()
            all_rows.extend(mundial_rows)
            status_total[str(MUNDIAL_ID)] = mundial_status
        except Exception as e:
            print(f"❌ Error Mundial: {e}")
            status_total[str(MUNDIAL_ID)] = {
                "liga": MUNDIAL_NAME,
                "eventos": 0,
                "odds": 0,
            }

    # Deduplicar
    unique = {}

    for row in all_rows:
        key = (
            str(row.get("EventId")),
            row.get("Liga"),
        )
        unique[key] = row

    all_rows = list(unique.values())

    all_rows.sort(
        key=lambda x: (
            x["Fecha"],
            x["Liga"],
            x["Partido"],
        )
    )

    # Seguridad: si todo falla, NO pisar JSON bueno con []
    if not all_rows:
        print("\n⚠️ TeApuesto devolvió 0 partidos.")
        print("⚠️ NO se reemplaza cuotas_teapuesto.json para conservar el último resultado válido.")
    else:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(
                all_rows,
                f,
                ensure_ascii=False,
                indent=2,
            )

    # Resumen
    for tid, liga in LIGAS_EQUIVALENCIAS.items():
        info = status_total.get(
            tid,
            {
                "eventos": 0,
                "odds": 0,
            },
        )

        evs = info["eventos"]
        odds = info["odds"]

        if evs == 0:
            print(f"❌ {liga}: 0 eventos prematch")
        elif odds == 0:
            print(f"⚠️ {liga}: {evs} eventos prematch, 0 odds 1x2")
        else:
            print(f"✅ {liga}: OK ({evs} eventos prematch, {odds} con 1x2)")

    info = status_total.get(
        str(MUNDIAL_ID),
        {
            "eventos": 0,
            "odds": 0,
        },
    )

    if info["eventos"] == 0:
        print(f"❌ {MUNDIAL_NAME}: 0 eventos prematch")
    elif info["odds"] == 0:
        print(
            f"⚠️ {MUNDIAL_NAME}: "
            f"{info['eventos']} eventos prematch, 0 odds 1x2"
        )
    else:
        print(
            f"✅ {MUNDIAL_NAME}: "
            f"{info['eventos']} eventos | {info['odds']} con 1x2"
        )

    elapsed = time.perf_counter() - started

    print(f"\n💾 Total obtenido: {len(all_rows)} partidos")

    if all_rows:
        print(f"💾 Guardado -> {OUT_PATH}")

    print(f"⚡ Tiempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    main()