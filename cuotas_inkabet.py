import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

# ==========================================================
# CONFIG
# ==========================================================
BASE_URL = "https://d-cf.inkabetplayground.net"

TZ_LOCAL = ZoneInfo("America/Lima")
TZ_FECHA_INKABET = ZoneInfo("UTC")  # Inkabet se guarda en formato UTC/casas
DIAS_A_FUTURO = 3

CASA = "Inkabet"

BRAND_ID = "02a22011-da9c-4b27-9ce6-10eb6b172707"
STATIC_CONTEXT_ID = "stc-943713193"

COOKIE = "OBG-SB-THEME=light"

SESSION_TOKEN = "ew0KICAiYWxnIjogIkhTMjU2IiwNCiAgInR5cCI6ICJKV1QiDQp9.ew0KICAianVyaXNkaWN0aW9uIjogIlVua25vd24iLA0KICAidXNlcklkIjogIjExMTExMTExLTExMTEtMTExMS0xMTExLTExMTExMTExMTExMSIsDQogICJsb2dpblNlc3Npb25JZCI6ICIxMTExMTExMS0xMTExLTExMTEtMTExMS0xMTExMTExMTExMTEiDQp9.yuBO_qNKJHtbCWK3z04cEqU59EKU8pZb2kXHhZ7IeuI"

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
DEBUG_DIR = os.path.join(DATA_DIR, "debug_inkabet")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_inkabet.json")
STATUS_PATH = os.path.join(DEBUG_DIR, "status_inkabet.json")

LIGAS_INKABET = {
    3: "Premier League",
    4: "Championship",
    9: "Serie A",
    15: "Bundesliga",
    38: "Brasileirao",
    569: "Copa de Brasil",
    275: "Copa Libertadores",
    691: "Copa Sudamericana",
    30899: "Copa Mundial 2026",
}

GROUPABLE_NORMAL = "MW3W"
GROUPABLE_PAGO = "MW3W2UPEP"

MAX_WORKERS = 20


# ==========================================================
# UTILS
# ==========================================================
def clean_cookie():
    return " ".join(COOKIE.strip().split())


def parse_iso_utc_to_local(s):
    if not s:
        return None

    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(s)

        return dt.astimezone(TZ_FECHA_INKABET)
    except Exception:
        return None


def to_iso_like_doradobet(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def parse_teams(label):
    if not label:
        return None, None

    for sep in [" - ", " vs. ", " vs ", " v "]:
        if sep in label:
            a, b = label.split(sep, 1)
            return a.strip(), b.strip()

    return None, None


def is_live_or_started(ev, now):
    dt = parse_iso_utc_to_local(ev.get("startDate") or ev.get("startTime"))

    if not dt:
        return True

    if dt <= now:
        return True

    event_type = str(ev.get("eventType") or "").lower()
    if event_type and event_type not in ("fixture", "prematch"):
        return True

    status = str(ev.get("status") or "").lower()
    if status in ("live", "inplay", "in_play", "started", "running", "closed", "settled"):
        return True

    return False


# ==========================================================
# HEADERS
# ==========================================================
def base_headers(referer, identifier):
    h = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "es-US,es-PE;q=0.9,es-419;q=0.8,es;q=0.7,en;q=0.6",
        "brandid": BRAND_ID,
        "cache-control": "no-cache",
        "content-type": "application/json",
        "cookie": clean_cookie(),
        "correlationid": str(uuid.uuid4()),
        "marketcode": "pe",
        "pragma": "no-cache",
        "referer": referer,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
        "x-obg-channel": "Web",
        "x-obg-device": "Desktop",
        "x-sb-app-version": "7.37.32.3653-r9beb24f",
        "x-sb-channel": "Web",
        "x-sb-content-id": BRAND_ID,
        "x-sb-country-code": "PE",
        "x-sb-currency-code": "PEN",
        "x-sb-device-type": "Desktop",
        "x-sb-frame-ancestors": "https://inkabet.pe",
        "x-sb-identifier": identifier,
        "x-sb-jurisdiction": "Mincetur",
        "x-sb-language-code": "pe",
        "x-sb-segment-id": "4d000eff-ed6d-45d3-ac37-e2b0ada84125",
        "x-sb-static-context-id": STATIC_CONTEXT_ID,
        "x-sb-type": "b2b",
        "x-sb-user-context-id": STATIC_CONTEXT_ID,
    }

    if SESSION_TOKEN.strip():
        h["sessiontoken"] = SESSION_TOKEN.strip()

    return h


# ==========================================================
# FETCH EVENTOS
# ==========================================================
def fetch_events_table(session, competition_id, window_start, window_end):
    url = f"{BASE_URL}/api/sb/v1/widgets/events-table/v2"
    referer = f"{BASE_URL}/{STATIC_CONTEXT_ID}/{STATIC_CONTEXT_ID}/futbol"

    start_utc = window_start.astimezone(timezone.utc)
    end_utc = window_end.astimezone(timezone.utc)

    params = {
        "categoryIds": "1",
        "competitionIds": str(competition_id),
        "eventPhase": "Prematch",
        "eventSortBy": "StartDate",
        "includeSkeleton": "true",
        "maxMarketCount": "1",
        "pageNumber": "1",
        "startsOnOrAfter": start_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "startsBefore": end_utc.strftime("%Y-%m-%dT%H:%M:%S.999Z"),
        "priceFormats": "1",
    }

    r = session.get(
        url,
        headers=base_headers(referer, "EVENT_TABLE_REQUEST"),
        params=params,
        timeout=30,
    )

    if r.status_code != 200:
        return [], r.status_code, r.text[:300]

    if "application/json" not in str(r.headers.get("content-type", "")):
        return [], r.status_code, r.text[:300]

    data = r.json()
    events = data.get("data", {}).get("events", []) or []

    return events, r.status_code, ""


# ==========================================================
# FETCH CUOTAS
# ==========================================================
def fetch_groupable(session, event_id, groupable_id):
    url = f"{BASE_URL}/api/sb/v1/widgets/accordion/v1"
    referer = (
        f"{BASE_URL}/{STATIC_CONTEXT_ID}/{STATIC_CONTEXT_ID}/"
        f"futbol/mundial/copa-del-mundo?tab=home&eventId={event_id}&fs=true&eti=0"
    )

    params = {
        "eventId": event_id,
        "groupableId": groupable_id,
        "_": str(int(time.time() * 1000)),
    }

    r = session.get(
        url,
        headers=base_headers(referer, "ACCORDION_REQUEST"),
        params=params,
        timeout=30,
    )

    if r.status_code != 200:
        return None

    if "application/json" not in str(r.headers.get("content-type", "")):
        return None

    return r.json()


def parse_groupable(payload, groupable_id):
    cuotas = {
        "Local": None,
        "Empate": None,
        "Visita": None,
    }

    if not payload:
        return cuotas

    acc = (
        payload.get("data", {})
        .get("accordions", {})
        .get(groupable_id, {})
    ) or {}

    selections = acc.get("selections", []) or []

    for s in selections:
        if s.get("status") != "Open":
            continue

        template = s.get("selectionTemplateId")
        odds = s.get("odds")

        if odds is None:
            continue

        try:
            odds = float(odds)
        except Exception:
            continue

        if template == "HOME":
            cuotas["Local"] = odds
        elif template == "DRAW":
            cuotas["Empate"] = odds
        elif template == "AWAY":
            cuotas["Visita"] = odds

    return cuotas


def procesar_evento(ev):
    session = requests.Session()

    event_id = ev.get("id")
    label = ev.get("label") or ""
    fecha_raw = ev.get("startDate") or ev.get("startTime")

    local, visita = parse_teams(label)

    if not event_id or not local or not visita:
        return None

    dt = parse_iso_utc_to_local(fecha_raw)

    if not dt:
        return None

    normal_payload = fetch_groupable(session, event_id, GROUPABLE_NORMAL)
    pago_payload = fetch_groupable(session, event_id, GROUPABLE_PAGO)

    normal = parse_groupable(normal_payload, GROUPABLE_NORMAL)
    pago = parse_groupable(pago_payload, GROUPABLE_PAGO)

    cuota_local = pago.get("Local")
    cuota_visita = pago.get("Visita")

    empate_candidates = [
        x for x in [
            normal.get("Empate"),
            pago.get("Empate"),
        ]
        if x is not None
    ]

    cuota_empate = max(empate_candidates) if empate_candidates else None

    if cuota_local is None or cuota_empate is None or cuota_visita is None:
        return None

    return {
        "Liga": ev.get("LigaMancorabet"),
        "Partido": f"{local} vs {visita}",
        "Fecha": to_iso_like_doradobet(dt.replace(tzinfo=None)),
        "Casa": CASA,
        "Local": local,
        "Visita": visita,
        "Cuota Local": cuota_local,
        "Cuota Empate": cuota_empate,
        "Cuota Visita": cuota_visita,
        "EventId": event_id,
    }


# ==========================================================
# MAIN
# ==========================================================
def main():
    now = datetime.now(TZ_FECHA_INKABET)
    window_end = now + timedelta(days=DIAS_A_FUTURO)

    print(f"📆 Ventana: {now:%Y-%m-%d %H:%M:%S} -> {window_end:%Y-%m-%d %H:%M:%S} (UTC/formato casas)")

    session = requests.Session()

    eventos_para_cuotas = []

    status = {
        str(cid): {
            "liga": liga,
            "eventos": 0,
            "odds": 0,
            "table_status": None,
            "error": "",
        }
        for cid, liga in LIGAS_INKABET.items()
    }

    for competition_id, liga_name in LIGAS_INKABET.items():
        events, table_status, error = fetch_events_table(
            session,
            competition_id,
            now,
            window_end,
        )

        status[str(competition_id)]["table_status"] = table_status
        status[str(competition_id)]["error"] = error

        filtrados = []

        for ev in events:
            if is_live_or_started(ev, now):
                continue

            dt = parse_iso_utc_to_local(ev.get("startDate") or ev.get("startTime"))

            if not dt:
                continue

            if not (now < dt <= window_end):
                continue

            ev["LigaMancorabet"] = liga_name
            filtrados.append(ev)

        status[str(competition_id)]["eventos"] = len(filtrados)
        eventos_para_cuotas.extend(filtrados)

    rows = []

    if eventos_para_cuotas:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(procesar_evento, ev) for ev in eventos_para_cuotas]

            for future in as_completed(futures):
                try:
                    row = future.result()
                except Exception:
                    row = None

                if not row:
                    continue

                rows.append(row)

                for cid, liga in LIGAS_INKABET.items():
                    if liga == row["Liga"]:
                        status[str(cid)]["odds"] += 1
                        break

    rows.sort(key=lambda x: x["Fecha"])

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    with open(STATUS_PATH, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

    for _, info in status.items():
        liga = info["liga"]
        evs = info["eventos"]
        odds = info["odds"]
        table_status = info["table_status"]

        if evs == 0:
            print(f"❌ {liga}: 0 eventos | table={table_status}")
        elif odds == 0:
            print(f"⚠️ {liga}: {evs} eventos, 0 odds | table={table_status}")
        else:
            print(f"✅ {liga}: OK ({evs} eventos, {odds} con cuotas) | table={table_status}")

    print(f"\n💾 Total guardado: {len(rows)} partidos -> {OUT_PATH}")
    print(f"🧾 Status guardado -> {STATUS_PATH}")


if __name__ == "__main__":
    main()