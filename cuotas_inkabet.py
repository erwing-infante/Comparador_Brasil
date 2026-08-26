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
BASE_URL = "https://d-cf.inkabetplayground.net"

TZ_FECHA_INKABET = ZoneInfo("UTC")
DIAS_A_FUTURO = 3
CASA = "Inkabet"

BRAND_ID = "02a22011-da9c-4b27-9ce6-10eb6b172707"
STATIC_CONTEXT_ID = "stc-943713193"

COOKIE = "OBG-SB-THEME=light"

SESSION_TOKEN = (
    "ew0KICAiYWxnIjogIkhTMjU2IiwNCiAgInR5cCI6ICJKV1QiDQp9."
    "ew0KICAianVyaXNkaWN0aW9uIjogIlVua25vd24iLA0KICAidXNl"
    "cklkIjogIjExMTExMTExLTExMTEtMTExMS0xMTExLTExMTExMTEx"
    "MTExMSIsDQogICJsb2dpblNlc3Npb25JZCI6ICIxMTExMTExMS0x"
    "MTExLTExMTEtMTExMS0xMTExMTExMTExMTEiDQp9."
    "yuBO_qNKJHtbCWK3z04cEqU59EKU8pZb2kXHhZ7IeuI"
)


# ==========================================================
# PROXY-SELLER
# ==========================================================
PROXY = (
    "http://ap-t4ubmz5dahmi_area-PE_session-orbitx01_life-120:"
    "C7WeSFR2NWTXjUmN@"
    "gw-rotate.aproxy.com:6641"
)

PROXIES = {
    "http": PROXY,
    "https": PROXY,
}


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEBUG_DIR = os.path.join(DATA_DIR, "debug_inkabet")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_inkabet.json")
STATUS_PATH = os.path.join(DEBUG_DIR, "status_inkabet.json")


# ==========================================================
# LIGAS
# ==========================================================
LIGAS_INKABET = {
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
MAX_WORKERS_LIGAS = 12

# Cada partido produce dos solicitudes:
# MW3W + MW3W2UPEP
MAX_WORKERS_MERCADOS = 32

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

        # Todas las peticiones realizadas por esta sesión
        # pasan por Proxy-Seller.
        session.proxies.update(PROXIES)

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
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def clean_cookie():
    return " ".join(COOKIE.strip().split())


def parse_iso_utc(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )

        return dt.astimezone(TZ_FECHA_INKABET)

    except Exception:
        return None


def format_fecha(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def parse_teams(label):
    if not label:
        return None, None

    for separator in (
        " - ",
        " vs. ",
        " vs ",
        " v ",
    ):
        if separator in label:
            local, visita = label.split(separator, 1)

            return (
                local.strip(),
                visita.strip(),
            )

    return None, None


def is_live_or_started(event, now):
    dt = parse_iso_utc(
        event.get("startDate")
        or event.get("startTime")
    )

    if dt is None or dt <= now:
        return True

    event_type = str(
        event.get("eventType") or ""
    ).lower()

    if event_type and event_type not in (
        "fixture",
        "prematch",
    ):
        return True

    status = str(
        event.get("status") or ""
    ).lower()

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
        "x-sb-segment-id": (
            "4d000eff-ed6d-45d3-ac37-e2b0ada84125"
        ),
        "x-sb-static-context-id": STATIC_CONTEXT_ID,
        "x-sb-type": "b2b",
        "x-sb-user-context-id": STATIC_CONTEXT_ID,
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

    url = (
        f"{BASE_URL}/api/sb/v1/"
        "widgets/events-table/v2"
    )

    referer = (
        f"{BASE_URL}/{STATIC_CONTEXT_ID}/"
        f"{STATIC_CONTEXT_ID}/futbol"
    )

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
                headers=base_headers(
                    referer,
                    "EVENT_TABLE_REQUEST",
                ),
                params=params,
                timeout=TIMEOUT_TABLE,
            )

            status_code = response.status_code

            if response.status_code == 200:
                if "application/json" not in str(
                    response.headers.get(
                        "content-type",
                        "",
                    )
                ).lower():
                    last_error = "Respuesta no JSON"

                else:
                    payload = response.json()

                    events = (
                        payload.get("data", {})
                        .get("events", [])
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

        except (
            requests.RequestException,
            ValueError,
        ) as error:
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

    url = (
        f"{BASE_URL}/api/sb/v1/"
        "widgets/accordion/v1"
    )

    referer = (
        f"{BASE_URL}/{STATIC_CONTEXT_ID}/"
        f"{STATIC_CONTEXT_ID}/futbol"
        f"?tab=home&eventId={event_id}"
        "&fs=true&eti=0"
    )

    params = {
        "eventId": event_id,
        "groupableId": groupable_id,
        "_": str(int(time.time() * 1000)),
    }

    last_error = ""
    status_code = None

    for attempt in range(
        1,
        MAX_INTENTOS_ACCORDION + 1,
    ):
        try:
            response = session.get(
                url,
                headers=base_headers(
                    referer,
                    "ACCORDION_REQUEST",
                ),
                params=params,
                timeout=TIMEOUT_ACCORDION,
            )

            status_code = response.status_code

            if response.status_code == 200:
                if "application/json" not in str(
                    response.headers.get(
                        "content-type",
                        "",
                    )
                ).lower():
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

        except (
            requests.RequestException,
            ValueError,
        ) as error:
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

    for selection in accordion.get(
        "selections",
        [],
    ) or []:
        if str(
            selection.get("status") or ""
        ).lower() != "open":
            continue

        template = str(
            selection.get("selectionTemplateId")
            or ""
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
        event.get("startDate")
        or event.get("startTime")
    )

    if dt is None or not (now < dt <= window_end):
        return None

    event_id = event.get("id")

    local, visita = parse_teams(
        event.get("label") or ""
    )

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
    # Pago Anticipado
    cuota_local = pago.get("Local")
    cuota_visita = pago.get("Visita")

    # Mercado normal 1X2
    cuota_local_nopa = normal.get("Local")
    cuota_visita_nopa = normal.get("Visita")

    # Empate: mayor disponible entre normal y PA
    empates = [
        value
        for value in (
            normal.get("Empate"),
            pago.get("Empate"),
        )
        if value is not None
    ]

    cuota_empate = max(empates) if empates else None

    if cuota_empate is None:
        return None

    return {
        "Liga": event["liga"],
        "Partido": (
            f"{event['local']} vs "
            f"{event['visita']}"
        ),
        "Fecha": format_fecha(
            event["fecha_dt"].replace(
                tzinfo=None
            )
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
    started = time.perf_counter()

    now = datetime.now(TZ_FECHA_INKABET)

    window_end = now + timedelta(
        days=DIAS_A_FUTURO
    )

    print(
        f"📆 Inkabet: "
        f"{now:%Y-%m-%d %H:%M} -> "
        f"{window_end:%Y-%m-%d %H:%M}"
    )

    print("🌐 Proxy-Seller: ACTIVADO")

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
        in LIGAS_INKABET.items()
    }

    # ======================================================
    # 1. DESCARGAR TODAS LAS LIGAS
    # ======================================================
    league_results = []

    with ThreadPoolExecutor(
        max_workers=min(
            MAX_WORKERS_LIGAS,
            len(LIGAS_INKABET),
        )
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
            in LIGAS_INKABET.items()
        ]

        for future in as_completed(futures):
            league_results.append(
                future.result()
            )

    events = []
    seen_events = set()

    for result in league_results:
        competition_id = result[
            "competition_id"
        ]

        league_name = result["liga"]

        status_key = str(
            competition_id
        )

        status[status_key][
            "table_status"
        ] = result["status"]

        status[status_key][
            "error"
        ] = result["error"]

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

            event_id = str(
                event["event_id"]
            )

            if event_id in seen_events:
                continue

            seen_events.add(event_id)

            events.append(event)

            valid_count += 1

        status[status_key][
            "eventos"
        ] = valid_count

    # ======================================================
    # 2. DESCARGAR MERCADOS
    # ======================================================
    market_results = {
        str(event["event_id"]): {}
        for event in events
    }

    tasks = []

    for event in events:
        tasks.append(
            (
                event["event_id"],
                GROUPABLE_NORMAL,
            )
        )

        tasks.append(
            (
                event["event_id"],
                GROUPABLE_PAGO,
            )
        )

    if tasks:
        with ThreadPoolExecutor(
            max_workers=min(
                MAX_WORKERS_MERCADOS,
                len(tasks),
            )
        ) as executor:

            futures = [
                executor.submit(
                    fetch_groupable,
                    event_id,
                    groupable_id,
                )
                for event_id, groupable_id
                in tasks
            ]

            for future in as_completed(futures):
                result = future.result()

                event_key = str(
                    result["event_id"]
                )

                market_results[
                    event_key
                ][
                    result["groupable_id"]
                ] = result

    # ======================================================
    # 3. CONSTRUIR FILAS
    # ======================================================
    rows = []

    for event in events:
        event_key = str(
            event["event_id"]
        )

        competition_key = str(
            event["competition_id"]
        )

        event_markets = market_results.get(
            event_key,
            {},
        )

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

        row = build_row(
            event,
            normal,
            pago,
        )

        if row is None:
            status[
                competition_key
            ]["sin_empate"] += 1

            continue

        rows.append(row)

        info = status[
            competition_key
        ]

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

    save_json(
        OUT_PATH,
        rows,
    )

    save_json(
        STATUS_PATH,
        status,
    )

    # ======================================================
    # RESUMEN
    # ======================================================
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
            print(
                f"❌ {info['liga']}: "
                f"{info['error']}"
            )

        elif info["eventos"] == 0:
            print(
                f"— {info['liga']}: "
                "0 eventos"
            )

        else:
            print(
                f"✅ {info['liga']}: "
                f"{info['guardados']}/"
                f"{info['eventos']} | "
                f"PA={info['con_pago']} | "
                f"sin PA={info['sin_pago']}"
            )

    elapsed = (
        time.perf_counter()
        - started
    )

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