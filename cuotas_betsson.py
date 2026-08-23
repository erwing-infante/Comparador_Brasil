import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests


# ==========================================================
# CONFIG
# ==========================================================
BASE_URL = "https://www.betsson.pe"

TZ_FECHA_BETSSON = ZoneInfo("UTC")
DIAS_A_FUTURO = 3
CASA = "Betsson"

BRAND_ID = "6a6d80b9-16ac-4387-a413-244d93a74deb"

COOKIE = """OPTIMIZELY_USER_ID=19eb912c-912c-4000-8b912c9df0.-.8db; token=https%3A%2F%2Fwww.google.com%2F; affcode=hgjeap65; PartnerId=hgjeap65; fabricBeta=FABRICBETA; Acquisition_Status_Current=Prospect; Start_Acquisition=Prospect; Client_Status_Current=Prospect; Start_Client_Status=Prospect; Customer_Level=PC; OriginReferrer=https://www.google.com/; OriginLandingURL=https://www.betsson.co/; _ga=GA1.1.494929400.1781221478; OptanonAlertBoxClosed=2026-06-11T23:44:41.650Z; CONSENT=%7B%22marketing%22%3A1%2C%22functional%22%3A1%2C%22performance%22%3A1%2C%22targeting%22%3A1%7D; _gcl_au=1.1.625245873.1781221482; OBG-LOBBY=sportsbook; _twpid=tw.1781221482043.458901081859241210; _cs_c=0; _fbp=fb.1.1781221482238.75332610026634495; _tt_enable_cookie=1; _ttp=01KTWH5QXGXEMB5JTKC82JZMR9_.tt.1; OBG-SB-THEME=light; adformfrpid=1067354154662331118; _hjHasCachedUserAttributes=true; agentroutestate=eJQxSwiLZ2i7eFzd-uBJGQ; LAST-SAVED-VISITED-PAGE=%2Fapuestas-deportivas; __zzatgib-w-bab-betsson=MDA0dC0cTApcfEJcdGswPi17CT4VHThHKHIzd2UycCNQGEsTIkASVX8oFhV8KFhMOUEWQT50e188bCUZSWJSTFc/dRdZRkE2XBpLdWUvDDk6a2wkUlFDS2N8GgprLxoYf2wlUwoQY0VGcHMlLTFmJ3xLKTUdETJeV1U0O2dBVFg=/h6s1Q==; aws-waf-token=5bef74ea-ab4b-43ea-ac8e-1ce4b07d9663:NAoAnkgof+wPAAAA:wDbKWMiMIX6pLIjZTWtV90jpO7v3l4oO+lc15MiUueQE1GzgZP8Y5orufPkpNT8SRBT+RmmdgRhw4p9G6OvyrICHeUCXbE6YlNcdZbgJLK7p+1hncNBqPEslYbhNaGxr7/lnVxgJUzf80/aHUhIF432x7f2D1Vdd+fZMEWp//1g8Sty0sOfN2tgmkBDB1a4=; OptanonConsent=isGpcEnabled=0&datestamp=Fri+Jun+12+2026+00%3A53%3A09+GMT-0500+(hora+est%C3%A1ndar+de+Per%C3%BA)&version=202402.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=2ef8b319-e328-43f5-9a73-1eb5af3ca141&interactionCount=1&isAnonUser=1&landingPath=NotLandingPage&groups=C0001%3A1%2CC0003%3A1%2CC0002%3A1%2CC0004%3A1&geolocation=CO%3BANT&AwaitingReconsent=false; Initdone=1; TrafficType=Other Traffic; AffCookie=Missing AffCode; _hp5_meta.2604077862=%7B%22setPath%22%3A%7B%7D%2C%22userId%22%3A%222889130525335824%22%2C%22sessionId%22%3A%222096835443214029%22%2C%22sessionProperties%22%3A%7B%22time%22%3A1781243590389%2C%22id%22%3A%222096835443214029%22%2C%22initial_pageview_info%22%3A%7B%22time%22%3A1781243590389%2C%22id%22%3A%227873309535699598%22%2C%22title%22%3A%22Apuestas%20Deportivas%20-%20Casa%20de%20Apuestas%20%7C%20Betsson%22%2C%22url%22%3A%7B%22domain%22%3A%22www.betsson.co%22%2C%22path%22%3A%22%2Fapuestas-deportivas%22%2C%22query%22%3A%22%22%2C%22hash%22%3A%22%22%7D%7D%2C%22search_keyword%22%3A%22%22%2C%22referrer%22%3A%22%22%2C%22utm%22%3A%7B%22source%22%3A%22%22%2C%22medium%22%3A%22%22%2C%22term%22%3A%22%22%2C%22content%22%3A%22%22%2C%22campaign%22%3A%22%22%7D%7D%7D; _hp5_event_props.2604077862=%7B%22Contentsquare%20Replay%22%3A%22https%3A%2F%2Fapp.contentsquare.com%2Fquick-playback%2Findex.html%3Fpid%3D95872%26uu%3Dbaa51206-ec09-a2d7-f4bb-f9a2e3d33167%26sn%3D2%26pvid%3D1%26recordingType%3Dcs%26vd%3Dhe%22%7D; session=f46c5fa3de7b56f5-0000000001732e2e; _cs_id=baa51206-ec09-a2d7-f4bb-f9a2e3d33167.1781221483.2.1781243633.1781243590.1762942148.1815385483299.1.x; _ga_Y38E3N3WQC=GS2.1.s1781243590$o2$g1$t1781243633$j17$l0$h0; ttcsid_CRFGG4BC77U1F15PUH8G=1781243590219::qAMtbhpcKNJGY887A4YE.3.1781243633715.1; cfidsgib-w-bab-betsson=9C4XUIWfouEkQP+OmpSFLoX10MJnTw/rPk7FfLYa6oY0+scnuha5Wy1Ov96SfHlNW2UVzcwOyX/8rhY+FEKzge2TVR3r7xc+yqH72RYfaHrszRtvNZ4wH5STzdewQ+kUWkVK4MnjRxcAP645/q9fdL7rJ095eeT+C8XFaqs=; cfidsgib-w-bab-betsson=9C4XUIWfouEkQP+OmpSFLoX10MJnTw/rPk7FfLYa6oY0+scnuha5Wy1Ov96SfHlNW2UVzcwOyX/8rhY+FEKzge2TVR3r7xc+yqH72RYfaHrszRtvNZ4wH5STzdewQ+kUWkVK4MnjRxcAP645/q9fdL7rJ095eeT+C8XFaqs=; _cs_s=2.0.U.9.1781245482793; _hp5_let.2604077862=1781243687188; ttcsid=1781243590220::4qzmAYy1_jE9no2F27u9.4.1781243633715.0::1.43183.0::101148.5.331.276::0.0.0
"""

SESSION_TOKEN = ""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEBUG_DIR = os.path.join(DATA_DIR, "debug_betsson")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_betsson.json")
STATUS_PATH = os.path.join(DEBUG_DIR, "status_betsson.json")


# ==========================================================
# LIGAS
# ==========================================================
LIGAS_BETSSON = {
    3: "Premier League",
    148: "EFL Cup",
    4: "Championship",
    12: "La Liga",
    121: "Copa del Rey",
    9: "Serie A",
    15: "Bundesliga",
    122: "Copa Alemana",
    19: "Ligue 1",
    38: "Brasileirao",
    253: "Liga MX",
    250: "MLS",
    22988: "Liga 1 Perú",
    231: "Primeira Liga",
    25: "Eredivisie",
    569: "Copa de Brasil",
    6134: "UEFA Champions League",
    2612: "UEFA Europa League",
    23462: "UEFA Conference League",
    275: "Copa Libertadores",
    691: "Copa Sudamericana",
}


# ==========================================================
# MERCADOS
# ==========================================================
GROUPABLE_NORMAL = "MW3W"
GROUPABLE_PAGO = "MW3W2UPEP"


# ==========================================================
# VELOCIDAD
# ==========================================================
MAX_WORKERS_LIGAS = 8
MAX_WORKERS_MERCADOS = 24

TIMEOUT_TABLE = (8, 20)
TIMEOUT_ACCORDION = (8, 20)

MAX_INTENTOS_TABLE = 2
MAX_INTENTOS_ACCORDION = 2

MOSTRAR_LIGAS_VACIAS = False


# ==========================================================
# SESIÓN POR HILO
# ==========================================================
_thread_local = threading.local()


def get_session():
    session = getattr(_thread_local, "session", None)

    if session is None:
        session = requests.Session()

        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=0,
        )

        session.mount("https://", adapter)
        session.mount("http://", adapter)

        _thread_local.session = session

    return session


# ==========================================================
# UTILIDADES
# ==========================================================
def save_json(path, data):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def clean_cookie():
    return " ".join(COOKIE.strip().split())


def parse_iso_utc(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        return dt.astimezone(TZ_FECHA_BETSSON)
    except Exception:
        return None


def format_fecha(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def parse_teams(label):
    if not label:
        return None, None

    for separator in (" - ", " vs. ", " vs ", " v "):
        if separator in label:
            local, visita = label.split(separator, 1)
            return local.strip(), visita.strip()

    return None, None


def is_live_or_started(event, now):
    dt = parse_iso_utc(
        event.get("startDate") or event.get("startTime")
    )

    if dt is None or dt <= now:
        return True

    event_type = str(event.get("eventType") or "").lower()

    if event_type and event_type not in ("fixture", "prematch"):
        return True

    status = str(event.get("status") or "").lower()

    return status in {
        "live",
        "inplay",
        "in_play",
        "started",
        "running",
        "closed",
        "settled",
    }


# ==========================================================
# HEADERS
# ==========================================================
def base_headers(referer, identifier):
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": (
            "es-US,es-PE;q=0.9,es-419;q=0.8,"
            "es;q=0.7,en;q=0.6"
        ),
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
        headers["sessiontoken"] = SESSION_TOKEN.strip()

    return headers


# ==========================================================
# LISTADO DE EVENTOS
# ==========================================================
def fetch_events_table(
    competition_id,
    league_name,
    window_start,
    window_end,
):
    session = get_session()

    url = f"{BASE_URL}/api/sb/v1/widgets/events-table/v2"
    referer = f"{BASE_URL}/apuestas-deportivas"

    params = {
        "categoryIds": "1",
        "competitionIds": str(competition_id),
        "eventPhase": "Prematch",
        "eventSortBy": "StartDate",
        "includeSkeleton": "false",
        "maxMarketCount": "1",
        "pageNumber": "1",
        "startsOnOrAfter": (
            window_start.astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S.000Z")
        ),
        "startsBefore": (
            window_end.astimezone(timezone.utc)
            .strftime("%Y-%m-%dT%H:%M:%S.999Z")
        ),
        "priceFormats": "1",
    }

    last_error = ""
    status_code = None

    for attempt in range(1, MAX_INTENTOS_TABLE + 1):
        try:
            response = session.get(
                url,
                headers=base_headers(referer, "EVENT_TABLE_REQUEST"),
                params=params,
                timeout=TIMEOUT_TABLE,
            )

            status_code = response.status_code

            if response.status_code == 200:
                content_type = str(
                    response.headers.get("content-type", "")
                ).lower()

                if "application/json" not in content_type:
                    last_error = "Respuesta no JSON"
                else:
                    payload = response.json()
                    events = (
                        payload.get("data", {}).get("events", [])
                        or []
                    )

                    return {
                        "competition_id": competition_id,
                        "liga": league_name,
                        "events": events,
                        "status": status_code,
                        "error": "",
                    }
            else:
                last_error = (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )

        except (requests.RequestException, ValueError) as error:
            last_error = str(error)

        if attempt < MAX_INTENTOS_TABLE:
            time.sleep(0.4)

    return {
        "competition_id": competition_id,
        "liga": league_name,
        "events": [],
        "status": status_code,
        "error": last_error,
    }


# ==========================================================
# MERCADOS
# ==========================================================
def fetch_groupable(event_id, groupable_id):
    session = get_session()

    url = f"{BASE_URL}/api/sb/v1/widgets/accordion/v1"
    referer = f"{BASE_URL}/apuestas-deportivas?eventId={event_id}"

    params = {
        "eventId": event_id,
        "groupableId": groupable_id,
        "_": str(int(time.time() * 1000)),
    }

    last_error = ""
    status_code = None

    for attempt in range(1, MAX_INTENTOS_ACCORDION + 1):
        try:
            response = session.get(
                url,
                headers=base_headers(referer, "ACCORDION_REQUEST"),
                params=params,
                timeout=TIMEOUT_ACCORDION,
            )

            status_code = response.status_code

            if response.status_code == 200:
                content_type = str(
                    response.headers.get("content-type", "")
                ).lower()

                if "application/json" not in content_type:
                    last_error = "Respuesta no JSON"
                else:
                    return {
                        "event_id": event_id,
                        "groupable_id": groupable_id,
                        "payload": response.json(),
                        "status": status_code,
                        "error": "",
                    }
            else:
                last_error = (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:200]}"
                )

        except (requests.RequestException, ValueError) as error:
            last_error = str(error)

        if attempt < MAX_INTENTOS_ACCORDION:
            time.sleep(0.3)

    return {
        "event_id": event_id,
        "groupable_id": groupable_id,
        "payload": None,
        "status": status_code,
        "error": last_error,
    }


def parse_groupable(payload, groupable_id):
    cuotas = {
        "Local": None,
        "Empate": None,
        "Visita": None,
    }

    if not isinstance(payload, dict):
        return cuotas

    accordion = (
        payload.get("data", {})
        .get("accordions", {})
        .get(groupable_id, {})
        or {}
    )

    for selection in accordion.get("selections", []) or []:
        if str(selection.get("status") or "").lower() != "open":
            continue

        template = str(
            selection.get("selectionTemplateId") or ""
        ).upper()

        try:
            odds = float(selection.get("odds"))
        except (TypeError, ValueError):
            continue

        if odds <= 1:
            continue

        if template == "HOME":
            cuotas["Local"] = odds
        elif template == "DRAW":
            cuotas["Empate"] = odds
        elif template == "AWAY":
            cuotas["Visita"] = odds

    return cuotas


# ==========================================================
# FILTRAR EVENTOS
# ==========================================================
def prepare_event(
    event,
    competition_id,
    league_name,
    now,
    window_end,
):
    if is_live_or_started(event, now):
        return None

    dt = parse_iso_utc(
        event.get("startDate") or event.get("startTime")
    )

    if dt is None or not (now < dt <= window_end):
        return None

    event_id = event.get("id")
    local, visita = parse_teams(event.get("label") or "")

    if not event_id or not local or not visita:
        return None

    return {
        "event_id": event_id,
        "competition_id": competition_id,
        "liga": league_name,
        "local": local,
        "visita": visita,
        "fecha_dt": dt,
    }


# ==========================================================
# CONSTRUIR RESULTADO
# ==========================================================
def build_row(event, normal, pago):
    # Cuotas con Pago Anticipado.
    # Si el mercado PA no existe, permanecen en null.
    cuota_local = pago.get("Local")
    cuota_visita = pago.get("Visita")

    # Cuotas normales, sin Pago Anticipado.
    cuota_local_nopa = normal.get("Local")
    cuota_visita_nopa = normal.get("Visita")

    # Se conserva la lógica actual para el empate:
    # elegir la mayor cuota disponible entre normal y PA.
    empates = [
        value
        for value in (
            normal.get("Empate"),
            pago.get("Empate"),
        )
        if value is not None
    ]

    cuota_empate = max(empates) if empates else None

    # Solo se descarta si no existe empate.
    if cuota_empate is None:
        return None

    return {
        "Liga": event["liga"],
        "Partido": f"{event['local']} vs {event['visita']}",
        "Fecha": format_fecha(
            event["fecha_dt"].replace(tzinfo=None)
        ),
        "Casa": CASA,
        "Local": event["local"],
        "Visita": event["visita"],
        "Cuota Local": cuota_local,
        "Cuota Empate": cuota_empate,
        "Cuota Visita": cuota_visita,
        "Cuota Local NoPA": cuota_local_nopa,
        "Cuota Visita NoPA": cuota_visita_nopa,
        "EventId": event["event_id"],
    }


# ==========================================================
# MAIN
# ==========================================================
def main():
    if "PEGA_AQUI" in COOKIE:
        print("❌ Falta pegar COOKIE completa.")
        return

    started = time.perf_counter()

    now = datetime.now(TZ_FECHA_BETSSON)
    window_end = now + timedelta(days=DIAS_A_FUTURO)

    print(
        f"📆 Betsson: "
        f"{now:%Y-%m-%d %H:%M} -> "
        f"{window_end:%Y-%m-%d %H:%M}"
    )

    status = {
        str(competition_id): {
            "liga": league_name,
            "eventos": 0,
            "guardados": 0,
            "con_pago": 0,
            "sin_pago": 0,
            "sin_empate": 0,
            "table_status": None,
            "error": "",
        }
        for competition_id, league_name
        in LIGAS_BETSSON.items()
    }

    # 1. Descargar ligas en paralelo.
    league_results = []

    with ThreadPoolExecutor(
        max_workers=min(MAX_WORKERS_LIGAS, len(LIGAS_BETSSON))
    ) as executor:
        futures = [
            executor.submit(
                fetch_events_table,
                competition_id,
                league_name,
                now,
                window_end,
            )
            for competition_id, league_name
            in LIGAS_BETSSON.items()
        ]

        for future in as_completed(futures):
            league_results.append(future.result())

    events = []
    seen_events = set()

    for result in league_results:
        competition_id = result["competition_id"]
        league_name = result["liga"]
        status_key = str(competition_id)

        status[status_key]["table_status"] = result["status"]
        status[status_key]["error"] = result["error"]

        valid_count = 0

        for raw_event in result["events"]:
            event = prepare_event(
                raw_event,
                competition_id,
                league_name,
                now,
                window_end,
            )

            if event is None:
                continue

            event_key = str(event["event_id"])

            if event_key in seen_events:
                continue

            seen_events.add(event_key)
            events.append(event)
            valid_count += 1

        status[status_key]["eventos"] = valid_count

    # 2. Descargar ambos mercados en paralelo.
    market_results = {
        str(event["event_id"]): {}
        for event in events
    }

    tasks = []

    for event in events:
        tasks.append((event["event_id"], GROUPABLE_NORMAL))
        tasks.append((event["event_id"], GROUPABLE_PAGO))

    if tasks:
        with ThreadPoolExecutor(
            max_workers=min(MAX_WORKERS_MERCADOS, len(tasks))
        ) as executor:
            futures = [
                executor.submit(
                    fetch_groupable,
                    event_id,
                    groupable_id,
                )
                for event_id, groupable_id in tasks
            ]

            for future in as_completed(futures):
                result = future.result()
                event_key = str(result["event_id"])

                market_results[event_key][
                    result["groupable_id"]
                ] = result

    # 3. Construir filas.
    rows = []

    for event in events:
        event_key = str(event["event_id"])
        competition_key = str(event["competition_id"])

        event_markets = market_results.get(event_key, {})

        normal_result = event_markets.get(
            GROUPABLE_NORMAL,
            {},
        )

        pago_result = event_markets.get(
            GROUPABLE_PAGO,
            {},
        )

        normal = parse_groupable(
            normal_result.get("payload"),
            GROUPABLE_NORMAL,
        )

        pago = parse_groupable(
            pago_result.get("payload"),
            GROUPABLE_PAGO,
        )

        row = build_row(event, normal, pago)

        if row is None:
            status[competition_key]["sin_empate"] += 1
            continue

        rows.append(row)

        info = status[competition_key]
        info["guardados"] += 1

        if (
            row["Cuota Local"] is not None
            and row["Cuota Visita"] is not None
        ):
            info["con_pago"] += 1
        else:
            info["sin_pago"] += 1

    rows.sort(
        key=lambda item: (
            item["Fecha"],
            item["Liga"],
            item["Partido"],
        )
    )

    save_json(OUT_PATH, rows)
    save_json(STATUS_PATH, status)

    # Resumen compacto.
    print("\nRESUMEN")

    for info in sorted(
        status.values(),
        key=lambda value: value["liga"],
    ):
        if (
            info["eventos"] == 0
            and not info["error"]
            and not MOSTRAR_LIGAS_VACIAS
        ):
            continue

        if info["error"]:
            print(f"❌ {info['liga']}: {info['error']}")
        elif info["eventos"] == 0:
            print(f"— {info['liga']}: 0 eventos")
        else:
            print(
                f"✅ {info['liga']}: "
                f"{info['guardados']}/{info['eventos']} | "
                f"PA={info['con_pago']} | "
                f"sin PA={info['sin_pago']}"
            )

    elapsed = time.perf_counter() - started

    con_pago = sum(
        info["con_pago"]
        for info in status.values()
    )

    sin_pago = sum(
        info["sin_pago"]
        for info in status.values()
    )

    print(
        f"\n💾 {len(rows)} partidos | "
        f"PA={con_pago} | "
        f"sin PA={sin_pago} | "
        f"{elapsed:.2f}s"
    )

    print(OUT_PATH)


if __name__ == "__main__":
    main()