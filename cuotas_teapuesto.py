import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests

# ==========================================================
# CONFIG
# ==========================================================
TOURNAMENT_EVENTS_URL = "https://api-latam.core-ix.com/api/v1/tournament-events"

SPORT_ID = 1
LANG_EVENTS = "es"
TIME_RANGE = "all"  # ✅ el único que trae todo (hoy confirmaste)

TZ_LOCAL = ZoneInfo("America/Lima")
DIAS_A_FUTURO = 3  # ✅ próximos 3 días

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.teapuesto.pe",
    "Referer": "https://www.teapuesto.pe/",
}

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_teapuesto.json")

# ==========================================================
# LIGAS EQUIVALENTES (EMBEBIDAS)
# ==========================================================
LIGAS_EQUIVALENCIAS = {
    "1105": "Premier League",
    "1745": "EFL Cup",
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
# UTILS
# ==========================================================
def to_iso_like_doradobet(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def parse_start_time(start_time_str: str) -> datetime | None:
    """
    API devuelve 'YYYY-MM-DD HH:MM:SS' (sin zona).
    Lo interpretamos como hora local Perú (America/Lima).
    """
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
    seps = [" - ", " vs. ", " vs ", " v "]
    for sep in seps:
        if sep in event_name:
            a, b = event_name.split(sep, 1)
            return a.strip(), b.strip()
    return None, None


# ==========================================================
# FETCH
# ==========================================================
def fetch_tournament_events(tournament_ids):
    params = [
        ("sport_id", SPORT_ID),
        ("lang", LANG_EVENTS),
        ("time_range", TIME_RANGE),
    ]
    for tid in tournament_ids:
        params.append(("tournament_ids[]", tid))

    r = requests.get(TOURNAMENT_EVENTS_URL, headers=HEADERS, params=params, timeout=45)
    r.raise_for_status()
    return r.json()


# ==========================================================
# PARSER
# ==========================================================
def extract_1x2(payload: dict, window_start: datetime, window_end: datetime):
    out = []
    data = payload.get("data", {})
    tournaments = data.get("tournaments", {}) or {}

    status_por_liga = {}  # tid_str -> dict(count_eventos, count_odds)

    for tid_str, liga_name in LIGAS_EQUIVALENCIAS.items():
        tinfo = tournaments.get(tid_str)

        if not tinfo:
            status_por_liga[tid_str] = {"liga": liga_name, "eventos": 0, "odds": 0}
            continue

        events = tinfo.get("events", []) or []

        # filtrado por próximos 3 días
        events_filtrados = []
        for ev in events:
            dt = parse_start_time(ev.get("start_time"))
            if not dt:
                continue
            if window_start <= dt <= window_end:
                events_filtrados.append(ev)

        if not events_filtrados:
            status_por_liga[tid_str] = {"liga": liga_name, "eventos": 0, "odds": 0}
            continue

        count_odds = 0

        for ev in events_filtrados:
            ev_id = ev.get("id")
            ev_name = ev.get("name") or ""
            dt = parse_start_time(ev.get("start_time"))
            if not dt:
                continue

            # ✅ filtro: excluir partidos en vivo
            if (str(ev.get("state", "")).upper() in ("LIVE", "INPLAY", "IN_PLAY", "STARTED", "IN_PROGRESS")) or (ev.get("is_live") is True) or (ev.get("live") is True) or (ev.get("in_play") is True) or (ev.get("inPlay") is True):
                continue

            home, away = parse_teams(ev_name)
            partido = f"{home} vs {away}" if home and away else ev_name

            # mercado 1x2
            market_1x2 = None
            for m in (ev.get("markets", []) or []):
                if str(m.get("name", "")).lower() == "1x2":
                    market_1x2 = m
                    break
            if not market_1x2:
                continue

            odds_items = None
            for mo in (market_1x2.get("market_odds", []) or []):
                if mo.get("odds"):
                    odds_items = mo["odds"]
                    break
            if not odds_items:
                continue

            cuota_local = cuota_empate = cuota_visita = None

            for o in odds_items:
                pid = str(o.get("provider_odd_id", "")).strip()
                val = o.get("value")
                if val is None:
                    continue
                if pid == "1":
                    cuota_local = float(val)
                elif pid == "2":
                    cuota_empate = float(val)
                elif pid == "3":
                    cuota_visita = float(val)

            # fallback por order
            if cuota_local is None or cuota_empate is None or cuota_visita is None:
                for o in odds_items:
                    order = o.get("order")
                    val = o.get("value")
                    if val is None:
                        continue
                    if order == 1 and cuota_local is None:
                        cuota_local = float(val)
                    elif order == 2 and cuota_empate is None:
                        cuota_empate = float(val)
                    elif order == 3 and cuota_visita is None:
                        cuota_visita = float(val)

            if cuota_local is None or cuota_empate is None or cuota_visita is None:
                continue

            count_odds += 1

            out.append({
                "Liga": liga_name,
                "Partido": partido,
                "Fecha": to_iso_like_doradobet(dt.replace(tzinfo=None)),  # ISO sin zona como DoradoBet
                "Casa": "TeApuesto",
                "Local": home,
                "Visita": away,
                "Cuota Local": cuota_local,
                "Cuota Empate": cuota_empate,
                "Cuota Visita": cuota_visita,
                "EventId": ev_id,
            })

        status_por_liga[tid_str] = {
            "liga": liga_name,
            "eventos": len(events_filtrados),
            "odds": count_odds,
        }

    return out, status_por_liga


# ==========================================================
# MAIN
# ==========================================================
def main():
    now = datetime.now(TZ_LOCAL)
    window_end = now + timedelta(days=DIAS_A_FUTURO)

    tournament_ids = [int(x) for x in LIGAS_EQUIVALENCIAS.keys()]

    payload = fetch_tournament_events(tournament_ids)
    rows, status = extract_1x2(payload, window_start=now, window_end=window_end)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    # Logs limpios por liga
    print(f"📆 Ventana: {now.strftime('%Y-%m-%d %H:%M:%S')} -> {window_end.strftime('%Y-%m-%d %H:%M:%S')} (Perú)")
    for tid_str, info in status.items():
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
