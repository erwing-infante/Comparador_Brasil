import json
import os
import time
import uuid
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

# ==========================================================
# CONFIG
# ==========================================================
BASE_URL = "https://www.betsafe.pe"

PROXY = "http://7b0f657793f8b923:exTpjJv7kcCPYnbL@res.proxy-seller.com:10000"
PROXIES = {
    "http": PROXY,
    "https": PROXY,
}

TZ_LOCAL = ZoneInfo("America/Lima")
TZ_FECHA_BETSAFE = ZoneInfo("UTC")
DIAS_A_FUTURO = 3

CASA = "Betsafe"

BRAND_ID = "cfe0dfc1-9a3c-41cb-8817-7b3e71fddc9f"

COOKIE = """OBG-MARKET=es; _ga=GA1.1.1630320344.1773758685; OBG-SB-THEME=dark; OptanonAlertBoxClosed=2026-03-17T14:44:52.278Z; CONSENT=%7B%22marketing%22%3A1%2C%22functional%22%3A1%2C%22performance%22%3A1%2C%22targeting%22%3A1%7D; fs_cid=1.1; _gcl_au=1.1.969978760.1773758693; adformfrpid=7190881648779138713; _fbp=fb.1.1773758694861.564566834397579583; __qca=P1-ae7a364c-d6b9-4f55-a6ce-51ad5240d116; Client_Status_Current=Existing Customer; clientstadium=RDC; Customer_Level=RDC; Acquisition_Status_Current=Existing; Start_Acquisition=Existing; Start_Client_Status=Existing Customer; fabricBeta=FABRICBETA; _hjSessionUser_152962=eyJpZCI6ImE1NWQ0MmJmLWIxMWUtNTJjNi05NmQyLTBkNDQ3MDNjNjFjZSIsImNyZWF0ZWQiOjE3NzY1MTY2NDEyMzgsImV4aXN0aW5nIjp0cnVlfQ==; GUID_Cookie=6373943e-102e-4386-baea-7cac863d8514; crw-_ga=2026-06-12-365; OPTIMIZELY_USER_ID=19ebd2c0-d2c0-4000-8bd2c0e850.-.a4b; __zzatgib-w-bab-betsafe=MDA0dC0cTApcfEJcdGswPi17CT4VHThHKHIzd2VbPyNRX3kWIUBdVgosFhU1JVZMDxAWRj5xdjFsZiJlfVonTBM/dRdZRkE2XBpLdWUvDDk6a2wkUlFDS2N8GgprLxoYf2wlWH8PW0JBbnglLTFmJ3xLKTUdETJeV1U0O2dBVH9NbHARGkBUC0wLXAlDNV8ga2tKTUQoFVlxEV5ERHZ3LHBiHl9JFhxHWFV/IktCNCQgVjo8FkVHcC8xQGYhUUNLX3gfGDpoXXsJXWYbRk0UdHZfbxt/JlocOWMgSlxVCC4cE390J08Nf00JEjUwG0VXXSN4Gl0PEh1FF2ZetFM7qw==; agentroutestate=gxPHxUxro-6cldINGo-7cQ; Initdone=1; OriginReferrer=; OriginLandingURL=https://www.betsafe.pe/es; TrafficType=Other Traffic; AffCookie=Missing AffCode; OptanonConsent=isGpcEnabled=0&datestamp=Fri+Jun+12+2026+13%3A53%3A35+GMT-0500+(hora+est%C3%A1ndar+de+Per%C3%BA)&version=202401.2.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=3dde03d8-4023-411f-976d-dc248f80cf9e&interactionCount=1&landingPath=NotLandingPage&groups=C0001%3A1%2CC0003%3A1%2CC0002%3A1%2CC0004%3A1&AwaitingReconsent=false&geolocation=PE%3BPIU; LAST-SAVED-VISITED-PAGE=%2Fes%2Fapuestas-deportivas; fs_uid=#o-AD9G-eu1#a017e8d2-8346-404f-a7b6-c47d34037efa:06f23cd7-9323-4dc3-8be7-9e6c64497045:1781290416096::1#78b534c6##/1810231846; OBG-LOBBY=sportsbook; session=d107007f2cc1ea7e-0000000000915861; fs_lua=1.1781290665874; aws-waf-token=201bf163-774f-473c-8048-a59892023626:EAoAmLuFUxMoAAAA:nb4XQlrPNc7+nLGCATdQ7jpHL9j+V/9TCIoZ9lNyx8T4RX2JyfBPLA6q1D2tdh7mmpOighfm8AqX6m+1sXmWMhvSXB986P2LfbZgXLsCed2OukJqPvMhj/SyfIOwDoS8PmrBsNF1AKi8304QcYZcuVkfA20c6F7kPnnqVHoFeS6yyOi3afNuB5vkRXnCjMI=; cfidsgib-w-bab-betsafe=X2R/XEcsuNFvs12ndRj4+lW8XKXnsqBIXGdob3U0DOIVXxtIdZgKldYDcCpAjzWma8wpIcM1NTgvfo932iQymY8dA2EMkjK8tOf7jRHySFoWy/6VoLv6dud+iJ1S/IhX1BPgnhWiTsn8pxDG+6ALC2J+cWu6Wi82dAatZ5o=; cfidsgib-w-bab-betsafe=X2R/XEcsuNFvs12ndRj4+lW8XKXnsqBIXGdob3U0DOIVXxtIdZgKldYDcCpAjzWma8wpIcM1NTgvfo932iQymY8dA2EMkjK8tOf7jRHySFoWy/6VoLv6dud+iJ1S/IhX1BPgnhWiTsn8pxDG+6ALC2J+cWu6Wi82dAatZ5o=; _ga_NDFXVTB6FL=GS2.1.s1781290417$o17$g1$t1781290975$j60$l0$h2085379371; FPGSID=1.1781290417.1781290976.G-NDFXVTB6FL.YGrPgeOV3vAsKb14dmjogg"""

SESSION_TOKEN = ""

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
DEBUG_DIR = os.path.join(DATA_DIR, "debug_betsafe")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_betsafe.json")
STATUS_PATH = os.path.join(DEBUG_DIR, "status_betsafe.json")

LIGAS_BETSAFE = {
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

MAX_WORKERS = 6


# ==========================================================
# UTILS
# ==========================================================
def save_debug(filename, content):
    path = os.path.join(DEBUG_DIR, filename)

    with open(path, "w", encoding="utf-8") as f:
        if isinstance(content, str):
            f.write(content)
        else:
            json.dump(content, f, ensure_ascii=False, indent=2)

    return path


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

        return dt.astimezone(TZ_FECHA_BETSAFE)
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
# HEADERS / SESSION
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
        "x-sb-content-id": "1b2a4488-06ec-4e18-bda0-38782e01b26c",
        "x-sb-country-code": "PE",
        "x-sb-currency-code": "PEN",
        "x-sb-device-type": "Desktop",
        "x-sb-identifier": identifier,
        "x-sb-jurisdiction": "Mincetur",
        "x-sb-language-code": "pe",
        "x-sb-segment-id": "183c5c88-9447-4651-acce-913b6327e91a",
        "x-sb-static-context-id": "stc--1733859257",
        "x-sb-type": "b2b",
        "x-sb-user-context-id": "stc--1733859257",
    }

    if SESSION_TOKEN.strip():
        h["sessiontoken"] = SESSION_TOKEN.strip()

    return h


def make_session():
    session = requests.Session()
    session.proxies.update(PROXIES)

    try:
        r = session.get(
            BASE_URL,
            headers=base_headers(
                BASE_URL + "/es/apuestas-deportivas",
                "WARMUP_REQUEST",
            ),
            timeout=30,
            allow_redirects=True,
        )
        print(f"🔌 Warmup Betsafe con proxy: {r.status_code}")
    except Exception as e:
        print(f"⚠️ Warmup Betsafe error: {e}")

    return session


# ==========================================================
# REQUESTS
# ==========================================================
def safe_get_json(session, url, headers, params, debug_name):
    try:
        r = session.get(
            url,
            headers=headers,
            params=params,
            timeout=30,
        )
    except Exception as e:
        save_debug(f"{debug_name}_exception.txt", str(e))
        return None, 0, str(e)

    content_type = str(r.headers.get("content-type", ""))

    if r.status_code != 200:
        save_debug(
            f"{debug_name}_{r.status_code}.txt",
            {
                "url": r.url,
                "status_code": r.status_code,
                "headers": dict(r.headers),
                "body": r.text[:5000],
            },
        )
        return None, r.status_code, r.text[:300]

    if "application/json" not in content_type:
        save_debug(
            f"{debug_name}_not_json.txt",
            {
                "url": r.url,
                "status_code": r.status_code,
                "content_type": content_type,
                "body": r.text[:5000],
            },
        )
        return None, r.status_code, f"not_json: {content_type}"

    try:
        return r.json(), r.status_code, ""
    except Exception as e:
        save_debug(
            f"{debug_name}_json_error.txt",
            {
                "url": r.url,
                "status_code": r.status_code,
                "body": r.text[:5000],
                "error": str(e),
            },
        )
        return None, r.status_code, str(e)


# ==========================================================
# FETCH EVENTOS
# ==========================================================
def fetch_events_table(session, competition_id, window_start, window_end):
    url = f"{BASE_URL}/api/sb/v1/widgets/events-table/v2"
    referer = f"{BASE_URL}/es/apuestas-deportivas"

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

    data, status_code, error = safe_get_json(
        session=session,
        url=url,
        headers=base_headers(referer, "EVENT_TABLE_REQUEST"),
        params=params,
        debug_name=f"events_table_{competition_id}",
    )

    if status_code != 200 or not isinstance(data, dict):
        return [], status_code, error

    events = data.get("data", {}).get("events", []) or []

    return events, status_code, ""


# ==========================================================
# FETCH CUOTAS
# ==========================================================
def fetch_groupable(session, event_id, groupable_id):
    url = f"{BASE_URL}/api/sb/v1/widgets/accordion/v1"
    referer = f"{BASE_URL}/es/apuestas-deportivas?eventId={event_id}"

    params = {
        "eventId": event_id,
        "groupableId": groupable_id,
        "_": str(int(time.time() * 1000)),
    }

    data, status_code, error = safe_get_json(
        session=session,
        url=url,
        headers=base_headers(referer, "ACCORDION_REQUEST"),
        params=params,
        debug_name=f"accordion_{event_id}_{groupable_id}",
    )

    if status_code != 200:
        return None

    return data


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


def procesar_evento(ev, session):
    event_id = ev.get("id")
    label = ev.get("label") or ""
    fecha_raw = ev.get("startDate") or ev.get("startTime")

    local, visita = parse_teams(label)

    if not event_id or not local or not visita:
        return None

    dt = parse_iso_utc_to_local(fecha_raw)

    if not dt:
        return None

    time.sleep(random.uniform(0.2, 0.8))

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
        save_debug(
            f"no_1x2_{event_id}.json",
            {
                "event_id": event_id,
                "label": label,
                "normal": normal,
                "pago": pago,
            },
        )
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
        print("❌ Falta pegar COOKIE completa del curl bueno de Betsafe.")
        return

    now = datetime.now(TZ_FECHA_BETSAFE)
    window_end = now + timedelta(days=DIAS_A_FUTURO)

    print(
        f"📆 Ventana: {now:%Y-%m-%d %H:%M:%S} -> "
        f"{window_end:%Y-%m-%d %H:%M:%S} UTC/formato casas"
    )

    session = make_session()

    eventos_para_cuotas = []

    status = {
        str(cid): {
            "liga": liga,
            "eventos": 0,
            "odds": 0,
            "table_status": None,
            "error": "",
        }
        for cid, liga in LIGAS_BETSAFE.items()
    }

    for competition_id, liga_name in LIGAS_BETSAFE.items():
        events, table_status, error = fetch_events_table(
            session=session,
            competition_id=competition_id,
            window_start=now,
            window_end=window_end,
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

        print(
            f"🌐 {liga_name}: eventos={len(filtrados)} | "
            f"table={table_status}"
        )

    rows = []

    if eventos_para_cuotas:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [
                executor.submit(procesar_evento, ev, session)
                for ev in eventos_para_cuotas
            ]

            for future in as_completed(futures):
                try:
                    row = future.result()
                except Exception as e:
                    print(f"⚠️ Error procesando evento: {e}")
                    row = None

                if not row:
                    continue

                rows.append(row)

                for cid, liga in LIGAS_BETSAFE.items():
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

        if table_status in (401, 403, 406, 429):
            print(f"🚫 {liga}: bloqueado/rechazado | table={table_status}")
        elif evs == 0:
            print(f"❌ {liga}: 0 eventos | table={table_status}")
        elif odds == 0:
            print(f"⚠️ {liga}: {evs} eventos, 0 odds | table={table_status}")
        else:
            print(f"✅ {liga}: OK ({evs} eventos, {odds} con cuotas) | table={table_status}")

    print(f"\n💾 Total guardado: {len(rows)} partidos -> {OUT_PATH}")
    print(f"🧾 Status guardado -> {STATUS_PATH}")


if __name__ == "__main__":
    main()