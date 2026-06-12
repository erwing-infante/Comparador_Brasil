import json
import os
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

# ==========================================================
# CONFIG
# ==========================================================
BASE_URL = "https://www.betsson.co"

TZ_LOCAL = ZoneInfo("America/Lima")
DIAS_A_FUTURO = 3  # 72 horas

CASA = "Betsson"

BRAND_ID = "6a6d80b9-16ac-4387-a413-244d93a74deb"

# IMPORTANTE:
# Pega aquí la cookie completa del curl bueno.
COOKIE = """OPTIMIZELY_USER_ID=19eb912c-912c-4000-8b912c9df0.-.8db; token=https%3A%2F%2Fwww.google.com%2F; affcode=hgjeap65; PartnerId=hgjeap65; fabricBeta=FABRICBETA; Acquisition_Status_Current=Prospect; Start_Acquisition=Prospect; Client_Status_Current=Prospect; Start_Client_Status=Prospect; Customer_Level=PC; OriginReferrer=https://www.google.com/; OriginLandingURL=https://www.betsson.co/; _ga=GA1.1.494929400.1781221478; OptanonAlertBoxClosed=2026-06-11T23:44:41.650Z; CONSENT=%7B%22marketing%22%3A1%2C%22functional%22%3A1%2C%22performance%22%3A1%2C%22targeting%22%3A1%7D; _gcl_au=1.1.625245873.1781221482; OBG-LOBBY=sportsbook; _twpid=tw.1781221482043.458901081859241210; _cs_c=0; _fbp=fb.1.1781221482238.75332610026634495; _tt_enable_cookie=1; _ttp=01KTWH5QXGXEMB5JTKC82JZMR9_.tt.1; OBG-SB-THEME=light; adformfrpid=1067354154662331118; _hjHasCachedUserAttributes=true; agentroutestate=eJQxSwiLZ2i7eFzd-uBJGQ; LAST-SAVED-VISITED-PAGE=%2Fapuestas-deportivas; __zzatgib-w-bab-betsson=MDA0dC0cTApcfEJcdGswPi17CT4VHThHKHIzd2UycCNQGEsTIkASVX8oFhV8KFhMOUEWQT50e188bCUZSWJSTFc/dRdZRkE2XBpLdWUvDDk6a2wkUlFDS2N8GgprLxoYf2wlUwoQY0VGcHMlLTFmJ3xLKTUdETJeV1U0O2dBVFg=/h6s1Q==; aws-waf-token=5bef74ea-ab4b-43ea-ac8e-1ce4b07d9663:NAoAnkgof+wPAAAA:wDbKWMiMIX6pLIjZTWtV90jpO7v3l4oO+lc15MiUueQE1GzgZP8Y5orufPkpNT8SRBT+RmmdgRhw4p9G6OvyrICHeUCXbE6YlNcdZbgJLK7p+1hncNBqPEslYbhNaGxr7/lnVxgJUzf80/aHUhIF432x7f2D1Vdd+fZMEWp//1g8Sty0sOfN2tgmkBDB1a4=; OptanonConsent=isGpcEnabled=0&datestamp=Fri+Jun+12+2026+00%3A53%3A09+GMT-0500+(hora+est%C3%A1ndar+de+Per%C3%BA)&version=202402.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=2ef8b319-e328-43f5-9a73-1eb5af3ca141&interactionCount=1&isAnonUser=1&landingPath=NotLandingPage&groups=C0001%3A1%2CC0003%3A1%2CC0002%3A1%2CC0004%3A1&geolocation=CO%3BANT&AwaitingReconsent=false; Initdone=1; TrafficType=Other Traffic; AffCookie=Missing AffCode; _hp5_meta.2604077862=%7B%22setPath%22%3A%7B%7D%2C%22userId%22%3A%222889130525335824%22%2C%22sessionId%22%3A%222096835443214029%22%2C%22sessionProperties%22%3A%7B%22time%22%3A1781243590389%2C%22id%22%3A%222096835443214029%22%2C%22initial_pageview_info%22%3A%7B%22time%22%3A1781243590389%2C%22id%22%3A%227873309535699598%22%2C%22title%22%3A%22Apuestas%20Deportivas%20-%20Casa%20de%20Apuestas%20%7C%20Betsson%22%2C%22url%22%3A%7B%22domain%22%3A%22www.betsson.co%22%2C%22path%22%3A%22%2Fapuestas-deportivas%22%2C%22query%22%3A%22%22%2C%22hash%22%3A%22%22%7D%7D%2C%22search_keyword%22%3A%22%22%2C%22referrer%22%3A%22%22%2C%22utm%22%3A%7B%22source%22%3A%22%22%2C%22medium%22%3A%22%22%2C%22term%22%3A%22%22%2C%22content%22%3A%22%22%2C%22campaign%22%3A%22%22%7D%7D%7D; _hp5_event_props.2604077862=%7B%22Contentsquare%20Replay%22%3A%22https%3A%2F%2Fapp.contentsquare.com%2Fquick-playback%2Findex.html%3Fpid%3D95872%26uu%3Dbaa51206-ec09-a2d7-f4bb-f9a2e3d33167%26sn%3D2%26pvid%3D1%26recordingType%3Dcs%26vd%3Dhe%22%7D; session=f46c5fa3de7b56f5-0000000001732e2e; _cs_id=baa51206-ec09-a2d7-f4bb-f9a2e3d33167.1781221483.2.1781243633.1781243590.1762942148.1815385483299.1.x; _ga_Y38E3N3WQC=GS2.1.s1781243590$o2$g1$t1781243633$j17$l0$h0; ttcsid_CRFGG4BC77U1F15PUH8G=1781243590219::qAMtbhpcKNJGY887A4YE.3.1781243633715.1; cfidsgib-w-bab-betsson=9C4XUIWfouEkQP+OmpSFLoX10MJnTw/rPk7FfLYa6oY0+scnuha5Wy1Ov96SfHlNW2UVzcwOyX/8rhY+FEKzge2TVR3r7xc+yqH72RYfaHrszRtvNZ4wH5STzdewQ+kUWkVK4MnjRxcAP645/q9fdL7rJ095eeT+C8XFaqs=; cfidsgib-w-bab-betsson=9C4XUIWfouEkQP+OmpSFLoX10MJnTw/rPk7FfLYa6oY0+scnuha5Wy1Ov96SfHlNW2UVzcwOyX/8rhY+FEKzge2TVR3r7xc+yqH72RYfaHrszRtvNZ4wH5STzdewQ+kUWkVK4MnjRxcAP645/q9fdL7rJ095eeT+C8XFaqs=; _cs_s=2.0.U.9.1781245482793; _hp5_let.2604077862=1781243687188; ttcsid=1781243590220::4qzmAYy1_jE9no2F27u9.4.1781243633715.0::1.43183.0::101148.5.331.276::0.0.0
"""

# Déjalo vacío. Si lo pones vencido/mal, da E_INVALIDSESSIONTOKEN.
SESSION_TOKEN = ""

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
DEBUG_DIR = os.path.join(DATA_DIR, "debug_betsson")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_betsson.json")
STATUS_PATH = os.path.join(DEBUG_DIR, "status_betsson.json")

# CompetitionIds ya detectados
LIGAS_BETSSON = {
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

GROUPABLE_NORMAL = "MW3W"        # Ganador del partido
GROUPABLE_PAGO = "MW3W2UPEP"    # Ganador del partido - Pago Anticipado

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

        return dt.astimezone(TZ_LOCAL)
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
        "marketcode": "co",
        "pragma": "no-cache",
        "referer": referer,
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/149.0.0.0 Safari/537.36"
        ),
        "x-obg-channel": "Web",
        "x-obg-device": "Desktop",
        "x-sb-app-version": "7.37.31.3608-rd8be260",
        "x-sb-channel": "Web",
        "x-sb-content-id": "2d543995-acff-41c1-bc73-9ec46bd70602",
        "x-sb-country-code": "CO",
        "x-sb-currency-code": "COP",
        "x-sb-device-type": "Desktop",
        "x-sb-identifier": identifier,
        "x-sb-jurisdiction": "Coljuegos",
        "x-sb-language-code": "co",
        "x-sb-segment-id": "1a68008c-4da6-4f77-acbc-0614cb030d7d",
        "x-sb-static-context-id": "stc--55774027",
        "x-sb-type": "b2b",
        "x-sb-user-context-id": "stc--55774027",
    }

    if SESSION_TOKEN.strip():
        h["sessiontoken"] = SESSION_TOKEN.strip()

    return h


# ==========================================================
# FETCH EVENTOS
# ==========================================================
def fetch_events_table(session, competition_id, window_start, window_end):
    url = f"{BASE_URL}/api/sb/v1/widgets/events-table/v2"
    referer = f"{BASE_URL}/apuestas-deportivas"

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
    referer = f"{BASE_URL}/apuestas-deportivas?eventId={event_id}"

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
    if "PEGA_AQUI" in COOKIE:
        print("❌ Falta pegar COOKIE completa del curl bueno.")
        return

    now = datetime.now(TZ_LOCAL)
    window_end = now + timedelta(days=DIAS_A_FUTURO)

    print(f"📆 Ventana: {now:%Y-%m-%d %H:%M:%S} -> {window_end:%Y-%m-%d %H:%M:%S} (Perú)")

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
        for cid, liga in LIGAS_BETSSON.items()
    }

    for competition_id, liga_name in LIGAS_BETSSON.items():
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

                for cid, liga in LIGAS_BETSSON.items():
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