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

TZ_LOCAL = ZoneInfo("America/Lima")
DIAS_A_FUTURO = 3
MAX_WORKERS_LIGAS = 8
TIMEOUT_LISTADO = (6, 25)

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
# PAGO ANTICIPADO
# ==========================================================

def has_early_payout(ev):
    labels = ev.get("event_labels", []) or []

    for label in labels:
        if not isinstance(label, dict):
            continue

        text = str(label.get("text") or "").strip().upper()
        description = str(label.get("description") or "").strip().lower()

        if "PAGO ANTICIPADO" in text or "early payout" in description:
            return True

    return False

# ==========================================================
# FILTRO PREMATCH / NO LIVE
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
# API
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
# EXTRAER TORNEOS
# ==========================================================

def get_tournaments(payload):
    if not isinstance(payload, dict):
        return {}

    data = payload.get("data", {})

    if isinstance(data, dict):
        tournaments = data.get("tournaments")

        if isinstance(tournaments, dict):
            return tournaments

        return data

    return {}

# ==========================================================
# EXTRAER 1X2 + PA / NoPA
# ==========================================================

def extract_1x2_normal(payload, tournament_id, now, window_end):
    tid = str(tournament_id)
    liga = LIGAS_EQUIVALENCIAS.get(tid, tid)
    rows = []

    tournaments = get_tournaments(payload)
    tinfo = tournaments.get(tid)

    if not tinfo:
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
        return rows, {
            "liga": liga,
            "eventos": 0,
            "odds": 0,
            "pa": 0,
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

    count_odds = 0
    count_pa = 0

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
            odds = (
                market_odd.get("odds")
                if isinstance(market_odd, dict)
                else None
            )

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

            provider_id = str(
                odd.get("provider_odd_id") or ""
            ).strip()

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

        if (
            cuota_local is None
            or cuota_empate is None
            or cuota_visita is None
        ):
            continue

        tiene_pa = has_early_payout(ev)

        count_odds += 1

        if tiene_pa:
            count_pa += 1

        rows.append({
            "Liga": liga,
            "Partido": f"{home} vs {away}",
            "Fecha": to_iso(dt.replace(tzinfo=None)),
            "Casa": "TeApuesto",
            "Local": home,
            "Visita": away,

            "Cuota Local": cuota_local if tiene_pa else None,
            "Cuota Empate": cuota_empate,
            "Cuota Visita": cuota_visita if tiene_pa else None,

            "Cuota Local NoPA": cuota_local,
            "Cuota Visita NoPA": cuota_visita,

            "EventId": event_id,
        })

    return rows, {
        "liga": liga,
        "eventos": len(candidatos),
        "odds": count_odds,
        "pa": count_pa,
    }

# ==========================================================
# PROCESAR LIGA
# ==========================================================

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
            "pa": 0,
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
        max_workers=min(MAX_WORKERS_LIGAS, len(tournament_ids))
    ) as executor:

        futures = {
            executor.submit(
                procesar_liga,
                tid,
                now,
                window_end,
            ): tid
            for tid in tournament_ids
        }

        for future in as_completed(futures):
            try:
                tid, rows, status = future.result()
                all_rows.extend(rows)
                status_total[tid] = status

            except Exception as e:
                print(f"❌ Error procesando liga: {e}")

    # ======================================================
    # DEDUPLICAR
    # ======================================================

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

    # ======================================================
    # GUARDAR
    # ======================================================

    if not all_rows:
        print("\n⚠️ TeApuesto devolvió 0 partidos.")
        print(
            "⚠️ NO se reemplaza cuotas_teapuesto.json "
            "para conservar el último resultado válido."
        )
    else:
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(
                all_rows,
                f,
                ensure_ascii=False,
                indent=2,
            )

    # ======================================================
    # RESUMEN
    # ======================================================

    for tid, liga in LIGAS_EQUIVALENCIAS.items():

        info = status_total.get(
            tid,
            {
                "eventos": 0,
                "odds": 0,
                "pa": 0,
            },
        )

        evs = info["eventos"]
        odds = info["odds"]
        pa = info.get("pa", 0)

        if evs == 0:
            print(f"❌ {liga}: 0 eventos prematch")

        elif odds == 0:
            print(
                f"⚠️ {liga}: "
                f"{evs} eventos prematch, 0 odds 1x2"
            )

        else:
            print(
                f"✅ {liga}: OK "
                f"({evs} eventos prematch, "
                f"{odds} con 1x2, "
                f"{pa} con PA)"
            )

    elapsed = time.perf_counter() - started

    print(f"\n💾 Total obtenido: {len(all_rows)} partidos")

    if all_rows:

        total_pa = sum(
            1
            for row in all_rows
            if row["Cuota Local"] is not None
            and row["Cuota Visita"] is not None
        )

        print(f"🟨 Con Pago Anticipado: {total_pa}")
        print(f"⬜ Sin Pago Anticipado: {len(all_rows) - total_pa}")
        print(f"💾 Guardado -> {OUT_PATH}")

    print(f"⚡ Tiempo total: {elapsed:.2f}s")


if __name__ == "__main__":
    main()