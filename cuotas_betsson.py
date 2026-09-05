import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

BASE_URL = "https://www.betsson.pe"
TZ_FECHA_BETSSON = ZoneInfo("UTC")
DIAS_A_FUTURO = 2
CASA = "Betsson"
BRAND_ID = "6a6d80b9-16ac-4387-a413-244d93a74deb"

COOKIE = 'OPTIMIZELY_USER_ID=19eb912c-912c-4000-8b912c9df0.-.8db; token=https%3A%2F%2Fwww.google.com%2F; affcode=hgjeap65; PartnerId=hgjeap65; fabricBeta=FABRICBETA; Acquisition_Status_Current=Prospect; Start_Acquisition=Prospect; Client_Status_Current=Prospect; Start_Client_Status=Prospect; Customer_Level=PC; OriginReferrer=https://www.google.com/; OriginLandingURL=https://www.betsson.co/; _ga=GA1.1.494929400.1781221478; OptanonAlertBoxClosed=2026-06-11T23:44:41.650Z; CONSENT=%7B%22marketing%22%3A1%2C%22functional%22%3A1%2C%22performance%22%3A1%2C%22targeting%22%3A1%7D; _gcl_au=1.1.625245873.1781221482; OBG-LOBBY=sportsbook; _twpid=tw.1781221482043.458901081859241210; _cs_c=0; _fbp=fb.1.1781221482238.75332610026634495; _tt_enable_cookie=1; _ttp=01KTWH5QXGXEMB5JTKC82JZMR9_.tt.1; OBG-SB-THEME=light; adformfrpid=1067354154662331118; _hjHasCachedUserAttributes=true; agentroutestate=eJQxSwiLZ2i7eFzd-uBJGQ; LAST-SAVED-VISITED-PAGE=%2Fapuestas-deportivas; __zzatgib-w-bab-betsson=MDA0dC0cTApcfEJcdGswPi17CT4VHThHKHIzd2UycCNQGEsTIkASVX8oFhV8KFhMOUEWQT50e188bCUZSWJSTFc/dRdZRkE2XBpLdWUvDDk6a2wkUlFDS2N8GgprLxoYf2wlUwoQY0VGcHMlLTFmJ3xLKTUdETJeV1U0O2dBVFg=/h6s1Q==; aws-waf-token=5bef74ea-ab4b-43ea-ac8e-1ce4b07d9663:NAoAnkgof+wPAAAA:wDbKWMiMIX6pLIjZTWtV90jpO7v3l4oO+lc15MiUueQE1GzgZP8Y5orufPkpNT8SRBT+RmmdgRhw4p9G6OvyrICHeUCXbE6YlNcdZbgJLK7p+1hncNBqPEslYbhNaGxr7/lnVxgJUzf80/aHUhIF432x7f2D1Vdd+fZMEWp//1g8Sty0sOfN2tgmkBDB1a4=; OptanonConsent=isGpcEnabled=0&datestamp=Fri+Jun+12+2026+00%3A53%3A09+GMT-0500+(hora+est%C3%A1ndar+de+Per%C3%BA)&version=202402.1.0&browserGpcFlag=0&isIABGlobal=false&hosts=&consentId=2ef8b319-e328-43f5-9a73-1eb5af3ca141&interactionCount=1&isAnonUser=1&landingPath=NotLandingPage&groups=C0001%3A1%2CC0003%3A1%2CC0002%3A1%2CC0004%3A1&geolocation=CO%3BANT&AwaitingReconsent=false; Initdone=1; TrafficType=Other Traffic; AffCookie=Missing AffCode; _hp5_meta.2604077862=%7B%22setPath%22%3A%7B%7D%2C%22userId%22%3A%222889130525335824%22%2C%22sessionId%22%3A%222096835443214029%22%2C%22sessionProperties%22%3A%7B%22time%22%3A1781243590389%2C%22id%22%3A%222096835443214029%22%2C%22initial_pageview_info%22%3A%7B%22time%22%3A1781243590389%2C%22id%22%3A%227873309535699598%22%2C%22title%22%3A%22Apuestas%20Deportivas%20-%20Casa%20de%20Apuestas%20%7C%20Betsson%22%2C%22url%22%3A%7B%22domain%22%3A%22www.betsson.co%22%2C%22path%22%3A%22%2Fapuestas-deportivas%22%2C%22query%22%3A%22%22%2C%22hash%22%3A%22%22%7D%7D%2C%22search_keyword%22%3A%22%22%2C%22referrer%22%3A%22%22%2C%22utm%22%3A%7B%22source%22%3A%22%22%2C%22medium%22%3A%22%22%2C%22term%22%3A%22%22%2C%22content%22%3A%22%22%2C%22campaign%22%3A%22%22%7D%7D%7D; _hp5_event_props.2604077862=%7B%22Contentsquare%20Replay%22%3A%22https%3A%2F%2Fapp.contentsquare.com%2Fquick-playback%2Findex.html%3Fpid%3D95872%26uu%3Dbaa51206-ec09-a2d7-f4bb-f9a2e3d33167%26sn%3D2%26pvid%3D1%26recordingType%3Dcs%26vd%3Dhe%22%7D; session=f46c5fa3de7b56f5-0000000001732e2e; _cs_id=baa51206-ec09-a2d7-f4bb-f9a2e3d33167.1781221483.2.1781243633.1781243590.1762942148.1815385483299.1.x; _ga_Y38E3N3WQC=GS2.1.s1781243590$o2$g1$t1781243633$j17$l0$h0; ttcsid_CRFGG4BC77U1F15PUH8G=1781243590219::qAMtbhpcKNJGY887A4YE.3.1781243633715.1; cfidsgib-w-bab-betsson=9C4XUIWfouEkQP+OmpSFLoX10MJnTw/rPk7FfLYa6oY0+scnuha5Wy1Ov96SfHlNW2UVzcwOyX/8rhY+FEKzge2TVR3r7xc+yqH72RYfaHrszRtvNZ4wH5STzdewQ+kUWkVK4MnjRxcAP645/q9fdL7rJ095eeT+C8XFaqs=; cfidsgib-w-bab-betsson=9C4XUIWfouEkQP+OmpSFLoX10MJnTw/rPk7FfLYa6oY0+scnuha5Wy1Ov96SfHlNW2UVzcwOyX/8rhY+FEKzge2TVR3r7xc+yqH72RYfaHrszRtvNZ4wH5STzdewQ+kUWkVK4MnjRxcAP645/q9fdL7rJ095eeT+C8XFaqs=; _cs_s=2.0.U.9.1781245482793; _hp5_let.2604077862=1781243687188; ttcsid=1781243590220::4qzmAYy1_jE9no2F27u9.4.1781243633715.0::1.43183.0::101148.5.331.276::0.0.0\n'
SESSION_TOKEN = ''
PROXY = 'http://ap-t4ubmz5dahmi_area-PE_session-orbitx01_life-120:C7WeSFR2NWTXjUmN@gw-rotate.aproxy.com:6641'
PROXIES = {"http": PROXY, "https": PROXY}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEBUG_DIR = os.path.join(DATA_DIR, "debug_betsson")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)
OUT_PATH = os.path.join(DATA_DIR, "cuotas_betsson.json")
STATUS_PATH = os.path.join(DEBUG_DIR, "status_betsson.json")
EVENT_CACHE_PATH = os.path.join(DEBUG_DIR, "eventos_betsson_cache.json")
EVENT_CACHE_TTL_SEC = 15 * 60

LIGAS_BETSSON = {
    3: "Premier League", 148: "EFL Cup", 4: "Championship", 12: "La Liga",
    121: "Copa del Rey", 9: "Serie A", 15: "Bundesliga", 122: "Copa Alemana",
    19: "Ligue 1", 38: "Brasileirao", 253: "Liga MX", 250: "MLS",
    22988: "Liga 1 Perú", 231: "Primeira Liga", 25: "Eredivisie",
    569: "Copa de Brasil", 6134: "UEFA Champions League", 2612: "UEFA Europa League",
    23462: "UEFA Conference League", 275: "Copa Libertadores", 691: "Copa Sudamericana",
}

GROUPABLE_NORMAL = "MW3W"
GROUPABLE_PAGO = "MW3W2UPEP"

# Estable antes que agresivo.
MAX_WORKERS_LIGAS = 5
MAX_WORKERS_RECUP_LIGAS = 2
MAX_WORKERS_MERCADOS = 20
MAX_WORKERS_RECUP_MERCADOS = 6

TIMEOUT_TABLE = (8, 18)
TIMEOUT_TABLE_RECOVERY = (10, 30)
TIMEOUT_ACCORDION = (8, 20)
TIMEOUT_ACCORDION_RECOVERY = (10, 30)

MAX_INTENTOS_TABLE = 2
MAX_INTENTOS_MERCADO = 2
MAX_BLOQUEOS_MERCADO = 8
MOSTRAR_LIGAS_VACIAS = False

_thread_local = threading.local()
breaker_lock = threading.Lock()
breaker_bloqueos = 0
breaker_activo = False


def reset_breaker():
    global breaker_bloqueos, breaker_activo
    with breaker_lock:
        breaker_bloqueos = 0
        breaker_activo = False


def breaker_esta_activo():
    with breaker_lock:
        return breaker_activo


def registrar_bloqueo():
    global breaker_bloqueos, breaker_activo
    with breaker_lock:
        breaker_bloqueos += 1
        if breaker_bloqueos >= MAX_BLOQUEOS_MERCADO:
            breaker_activo = True
        return breaker_bloqueos, breaker_activo


def get_session():
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.proxies.update(PROXIES)
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=24, pool_maxsize=24, max_retries=0, pool_block=False
        )
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        _thread_local.session = session
    return session


def save_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_previous_rows():
    try:
        with open(OUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def load_event_cache(now, window_end):
    try:
        with open(EVENT_CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        saved_at = float(cache.get("saved_at", 0))
        age = time.time() - saved_at
        if age < 0 or age > EVENT_CACHE_TTL_SEC:
            return None, age
        events = []
        for item in cache.get("events", []):
            dt = parse_iso_utc(item.get("fecha"))
            if dt is None or not (now < dt <= window_end):
                continue
            events.append({
                "event_id": item.get("event_id"),
                "competition_id": item.get("competition_id"),
                "liga": item.get("liga"),
                "local": item.get("local"),
                "visita": item.get("visita"),
                "fecha_dt": dt,
            })
        if not events:
            return None, age
        return events, age
    except Exception:
        return None, None


def save_event_cache(events):
    payload = {
        "saved_at": time.time(),
        "events": [
            {
                "event_id": ev["event_id"],
                "competition_id": ev["competition_id"],
                "liga": ev["liga"],
                "local": ev["local"],
                "visita": ev["visita"],
                "fecha": ev["fecha_dt"].astimezone(timezone.utc).isoformat(),
            }
            for ev in events
        ],
    }
    save_json_atomic(EVENT_CACHE_PATH, payload)


def clean_cookie():
    return " ".join(COOKIE.strip().split())


def parse_iso_utc(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_FECHA_BETSSON)
    except Exception:
        return None


def format_fecha(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def parse_teams(label):
    if not label:
        return None, None
    for sep in (" - ", " vs. ", " vs ", " v "):
        if sep in label:
            a, b = label.split(sep, 1)
            return a.strip(), b.strip()
    return None, None


def is_live_or_started(event, now):
    dt = parse_iso_utc(event.get("startDate") or event.get("startTime"))
    if dt is None or dt <= now:
        return True
    event_type = str(event.get("eventType") or "").lower()
    if event_type and event_type not in ("fixture", "prematch"):
        return True
    status = str(event.get("status") or "").lower()
    return status in {"live", "inplay", "in_play", "started", "running", "closed", "settled"}


def base_headers(referer, identifier):
    headers = {
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
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
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


def fetch_events_table(competition_id, league_name, window_start, window_end, recovery=False):
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
        "startsOnOrAfter": window_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "startsBefore": window_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.999Z"),
        "priceFormats": "1",
    }
    timeout = TIMEOUT_TABLE_RECOVERY if recovery else TIMEOUT_TABLE
    attempts = 2 if recovery else MAX_INTENTOS_TABLE
    last_error = ""
    status_code = None
    blocked = False

    for attempt in range(1, attempts + 1):
        try:
            r = session.get(url, headers=base_headers(referer, "EVENT_TABLE_REQUEST"), params=params, timeout=timeout)
            status_code = r.status_code
            if status_code in (401, 403):
                blocked = True
                last_error = f"HTTP {status_code}"
                break
            if status_code == 200:
                ctype = str(r.headers.get("content-type", "")).lower()
                if "application/json" in ctype:
                    payload = r.json()
                    events = payload.get("data", {}).get("events", []) or []
                    return {
                        "competition_id": competition_id, "liga": league_name,
                        "events": events, "status": 200, "error": "", "blocked": False,
                    }
                last_error = "Respuesta no JSON"
            else:
                last_error = f"HTTP {status_code}"
                if 400 <= status_code < 500:
                    break
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = str(e)
        except (requests.RequestException, ValueError) as e:
            last_error = str(e)
            break
        if attempt < attempts:
            time.sleep(0.7 if recovery else 0.35)

    return {
        "competition_id": competition_id, "liga": league_name,
        "events": [], "status": status_code, "error": last_error, "blocked": blocked,
    }


def fetch_groupable(event_id, groupable_id, recovery=False):
    if breaker_esta_activo():
        return {"event_id": event_id, "groupable_id": groupable_id, "payload": None,
                "status": None, "error": "Circuit breaker activo", "blocked": True, "skipped": True}

    session = get_session()
    url = f"{BASE_URL}/api/sb/v1/widgets/accordion/v1"
    referer = f"{BASE_URL}/apuestas-deportivas?eventId={event_id}"
    params = {"eventId": event_id, "groupableId": groupable_id, "_": str(int(time.time() * 1000))}
    timeout = TIMEOUT_ACCORDION_RECOVERY if recovery else TIMEOUT_ACCORDION
    attempts = 2 if recovery else MAX_INTENTOS_MERCADO
    last_error = ""
    status_code = None

    for attempt in range(1, attempts + 1):
        if breaker_esta_activo():
            return {"event_id": event_id, "groupable_id": groupable_id, "payload": None,
                    "status": None, "error": "Circuit breaker activo", "blocked": True, "skipped": True}
        try:
            r = session.get(url, headers=base_headers(referer, "ACCORDION_REQUEST"), params=params, timeout=timeout)
            status_code = r.status_code
            if status_code in (401, 403):
                cantidad, _ = registrar_bloqueo()
                return {"event_id": event_id, "groupable_id": groupable_id, "payload": None,
                        "status": status_code, "error": f"HTTP {status_code} (bloqueos={cantidad})",
                        "blocked": True, "skipped": False}
            if status_code == 200:
                ctype = str(r.headers.get("content-type", "")).lower()
                if "application/json" not in ctype:
                    last_error = "Respuesta no JSON"
                else:
                    try:
                        payload = r.json()
                    except ValueError:
                        payload = None
                    if payload is not None:
                        return {"event_id": event_id, "groupable_id": groupable_id, "payload": payload,
                                "status": 200, "error": "", "blocked": False, "skipped": False}
                    last_error = "JSON vacío"
            elif 400 <= status_code < 500:
                return {"event_id": event_id, "groupable_id": groupable_id, "payload": None,
                        "status": status_code, "error": f"HTTP {status_code}", "blocked": False, "skipped": False}
            else:
                last_error = f"HTTP {status_code}"
        except (requests.Timeout, requests.ConnectionError) as e:
            last_error = str(e)
        except requests.RequestException as e:
            last_error = str(e)
            break
        if attempt < attempts:
            time.sleep(0.6 if recovery else 0.3)

    return {"event_id": event_id, "groupable_id": groupable_id, "payload": None,
            "status": status_code, "error": last_error, "blocked": False, "skipped": False}


def parse_groupable(payload, groupable_id):
    cuotas = {"Local": None, "Empate": None, "Visita": None}
    if not isinstance(payload, dict):
        return cuotas
    accordion = payload.get("data", {}).get("accordions", {}).get(groupable_id, {}) or {}
    for selection in accordion.get("selections", []) or []:
        if str(selection.get("status") or "").lower() != "open":
            continue
        template = str(selection.get("selectionTemplateId") or "").upper()
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


def market_result_incomplete(result, groupable_id, require_three_way=False):
    if not result:
        return True
    if result.get("error") or result.get("payload") is None:
        return True
    if require_three_way:
        q = parse_groupable(result.get("payload"), groupable_id)
        return not (q.get("Local") and q.get("Empate") and q.get("Visita"))
    return False


def fetch_event_markets(event):
    event_id = event["event_id"]
    normal = fetch_groupable(event_id, GROUPABLE_NORMAL, recovery=False)
    if breaker_esta_activo():
        return {"event": event, "normal": normal, "pago": None}
    pago = fetch_groupable(event_id, GROUPABLE_PAGO, recovery=False)
    return {"event": event, "normal": normal, "pago": pago}


def prepare_event(event, competition_id, league_name, now, window_end):
    if is_live_or_started(event, now):
        return None
    dt = parse_iso_utc(event.get("startDate") or event.get("startTime"))
    if dt is None or not (now < dt <= window_end):
        return None
    event_id = event.get("id")
    local, visita = parse_teams(event.get("label") or "")
    if not event_id or not local or not visita:
        return None
    return {
        "event_id": event_id, "competition_id": competition_id, "liga": league_name,
        "local": local, "visita": visita, "fecha_dt": dt,
    }


def build_row(event, normal, pago):
    cuota_local = pago.get("Local")
    cuota_visita = pago.get("Visita")
    cuota_local_nopa = normal.get("Local")
    cuota_visita_nopa = normal.get("Visita")
    empates = [x for x in (normal.get("Empate"), pago.get("Empate")) if x is not None]
    cuota_empate = max(empates) if empates else None
    if cuota_empate is None:
        return None
    return {
        "Liga": event["liga"],
        "Partido": f"{event['local']} vs {event['visita']}",
        "Fecha": format_fecha(event["fecha_dt"].replace(tzinfo=None)),
        "Casa": CASA,
        "Local": event["local"], "Visita": event["visita"],
        "Cuota Local": cuota_local, "Cuota Empate": cuota_empate, "Cuota Visita": cuota_visita,
        "Cuota Local NoPA": cuota_local_nopa, "Cuota Visita NoPA": cuota_visita_nopa,
        "EventId": event["event_id"],
    }


def main():
    reset_breaker()
    started = time.perf_counter()
    now = datetime.now(TZ_FECHA_BETSSON)
    window_end = now + timedelta(days=DIAS_A_FUTURO)
    previous_rows = load_previous_rows()
    previous_by_id = {str(r.get("EventId")): r for r in previous_rows if r.get("EventId") is not None}

    print(f"📆 Betsson: {now:%Y-%m-%d %H:%M} -> {window_end:%Y-%m-%d %H:%M}")
    print("🌐 Proxy-Seller: ACTIVADO")

    status = {
        str(cid): {"liga": liga, "eventos": 0, "guardados": 0, "con_pago": 0,
                   "sin_pago": 0, "sin_empate": 0, "table_status": None, "error": ""}
        for cid, liga in LIGAS_BETSSON.items()
    }

    # 1-3) LISTADO: usar cache por 15 min; refrescar completo solo cuando vence.
    events, cache_age = load_event_cache(now, window_end)

    if events is not None:
        print(f"⚡ Listado desde cache: {len(events)} eventos | edad={cache_age:.0f}s | 0 requests")
        for ev in events:
            status[str(ev["competition_id"])]["eventos"] += 1
    else:
        t0 = time.perf_counter()
        league_results = {}
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS_LIGAS, len(LIGAS_BETSSON))) as ex:
            futs = {
                ex.submit(fetch_events_table, cid, liga, now, window_end, False): (cid, liga)
                for cid, liga in LIGAS_BETSSON.items()
            }
            for fut in as_completed(futs):
                cid, liga = futs[fut]
                try:
                    league_results[cid] = fut.result()
                except Exception as e:
                    league_results[cid] = {"competition_id": cid, "liga": liga, "events": [],
                                           "status": None, "error": str(e), "blocked": False}

        failed = [r for r in league_results.values() if r.get("error")]
        print(f"⚡ Listados 1ª pasada: {time.perf_counter()-t0:.2f}s | fallidas={len(failed)}")

        if failed:
            print("🔁 Recuperando ligas fallidas: " + ", ".join(r["liga"] for r in failed))
            time.sleep(0.8)
            t1 = time.perf_counter()
            with ThreadPoolExecutor(max_workers=min(MAX_WORKERS_RECUP_LIGAS, len(failed))) as ex:
                futs = {
                    ex.submit(fetch_events_table, r["competition_id"], r["liga"], now, window_end, True): r["competition_id"]
                    for r in failed
                }
                for fut in as_completed(futs):
                    cid = futs[fut]
                    try:
                        league_results[cid] = fut.result()
                    except Exception as e:
                        league_results[cid]["error"] = str(e)
            failed = [r for r in league_results.values() if r.get("error")]
            print(f"🔁 Recuperación ligas: {time.perf_counter()-t1:.2f}s | siguen fallidas={len(failed)}")

        if failed:
            print("\n⛔ Listado incompleto. Se conserva cuotas_betsson.json anterior.")
            for r in failed:
                print(f"   - {r['liga']}: {r.get('error')}")
            print(f"⚡ Ciclo abortado en {time.perf_counter()-started:.2f}s")
            return

        events = []
        seen = set()
        for cid, result in league_results.items():
            liga = result["liga"]
            status[str(cid)]["table_status"] = result.get("status")
            for raw in result.get("events", []) or []:
                ev = prepare_event(raw, cid, liga, now, window_end)
                if ev is None:
                    continue
                key = str(ev["event_id"])
                if key in seen:
                    continue
                seen.add(key)
                events.append(ev)
                status[str(cid)]["eventos"] += 1

        print(f"⚡ Listado completo: {len(events)} eventos")
        if not events:
            print("⚠️ 0 eventos. Se conserva el JSON anterior.")
            return
        save_event_cache(events)
        print(f"💾 Cache de eventos actualizado por {EVENT_CACHE_TTL_SEC//60} min")

    # 4) Primera pasada de mercados: NORMAL y PA como tareas independientes.
    # Esto elimina la espera secuencial MW3W -> MW3W2UPEP de cada evento.
    total_market_tasks = len(events) * 2
    workers_mercados = min(MAX_WORKERS_MERCADOS, total_market_tasks)
    print(f"⚡ Mercados: {len(events)} partidos | {total_market_tasks} requests | {workers_mercados} workers")
    t2 = time.perf_counter()
    market_results = {
        str(ev["event_id"]): {"event": ev, "normal": None, "pago": None}
        for ev in events
    }

    with ThreadPoolExecutor(max_workers=workers_mercados) as ex:
        futs = {}
        for ev in events:
            if breaker_esta_activo():
                break
            eid = ev["event_id"]
            futs[ex.submit(fetch_groupable, eid, GROUPABLE_NORMAL, False)] = (ev, GROUPABLE_NORMAL)
            futs[ex.submit(fetch_groupable, eid, GROUPABLE_PAGO, False)] = (ev, GROUPABLE_PAGO)

        for fut in as_completed(futs):
            ev, gid = futs[fut]
            key = str(ev["event_id"])
            try:
                rr = fut.result()
            except Exception as e:
                rr = {
                    "event_id": ev["event_id"], "groupable_id": gid,
                    "payload": None, "status": None, "error": str(e),
                    "blocked": False, "skipped": False,
                }
            if gid == GROUPABLE_NORMAL:
                market_results[key]["normal"] = rr
            else:
                market_results[key]["pago"] = rr

    print(f"⚡ Mercados 1ª pasada: {time.perf_counter()-t2:.2f}s | bloqueos={breaker_bloqueos}")

    if breaker_esta_activo():
        print(f"⛔ Circuit breaker activado tras {breaker_bloqueos} bloqueos 401/403.")
        print("⛔ Se conserva cuotas_betsson.json anterior.")
        return

    # 5) Recuperación selectiva de mercados realmente fallidos/incompletos.
    recovery_tasks = []
    for ev in events:
        key = str(ev["event_id"])
        result = market_results.get(key, {})
        normal = result.get("normal")
        pago = result.get("pago")
        if market_result_incomplete(normal, GROUPABLE_NORMAL, require_three_way=True):
            recovery_tasks.append((ev, GROUPABLE_NORMAL))
        # PA puede no existir legítimamente. Solo reintentamos si hubo error real.
        if pago and pago.get("error"):
            recovery_tasks.append((ev, GROUPABLE_PAGO))

    if recovery_tasks:
        print(f"🔁 Recuperando {len(recovery_tasks)} mercados incompletos con {MAX_WORKERS_RECUP_MERCADOS} workers...")
        time.sleep(0.8)
        t3 = time.perf_counter()
        recovered = 0
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS_RECUP_MERCADOS, len(recovery_tasks))) as ex:
            futs = {
                ex.submit(fetch_groupable, ev["event_id"], gid, True): (ev, gid)
                for ev, gid in recovery_tasks
            }
            for fut in as_completed(futs):
                ev, gid = futs[fut]
                key = str(ev["event_id"])
                try:
                    rr = fut.result()
                except Exception as e:
                    rr = {"event_id": ev["event_id"], "groupable_id": gid, "payload": None,
                          "status": None, "error": str(e), "blocked": False, "skipped": False}
                if not rr.get("error") and rr.get("payload") is not None:
                    recovered += 1
                    if gid == GROUPABLE_NORMAL:
                        market_results[key]["normal"] = rr
                    else:
                        market_results[key]["pago"] = rr
        print(f"🔁 Recuperación mercados: {time.perf_counter()-t3:.2f}s | recuperados={recovered}/{len(recovery_tasks)}")

    if breaker_esta_activo():
        print(f"⛔ Circuit breaker activado tras {breaker_bloqueos} bloqueos.")
        print("⛔ Se conserva cuotas_betsson.json anterior.")
        return

    # 6) Construcción + fallback del último JSON solo para eventos cuyo mercado falló.
    rows = []
    fallback_count = 0
    missing_without_fallback = 0

    for ev in events:
        key = str(ev["event_id"])
        cid_key = str(ev["competition_id"])
        result = market_results.get(key, {})
        normal_result = result.get("normal") or {}
        pago_result = result.get("pago") or {}
        normal = parse_groupable(normal_result.get("payload"), GROUPABLE_NORMAL)
        pago = parse_groupable(pago_result.get("payload"), GROUPABLE_PAGO)
        row = build_row(ev, normal, pago)

        if row is None:
            prev = previous_by_id.get(key)
            if prev:
                row = prev
                fallback_count += 1
            else:
                status[cid_key]["sin_empate"] += 1
                missing_without_fallback += 1
                continue

        rows.append(row)
        info = status[cid_key]
        info["guardados"] += 1
        if row.get("Cuota Local") is not None and row.get("Cuota Visita") is not None:
            info["con_pago"] += 1
        else:
            info["sin_pago"] += 1

    # Si aun sin fallback faltan demasiados, no sobrescribimos.
    if len(events) >= 20 and missing_without_fallback > max(3, int(len(events) * 0.08)):
        print()
        print(f"⛔ Faltan {missing_without_fallback} partidos sin datos ni fallback.")
        print("⛔ Se conserva cuotas_betsson.json anterior.")
        return

    rows.sort(key=lambda x: (x.get("Fecha", ""), x.get("Liga", ""), x.get("Partido", "")))
    save_json_atomic(OUT_PATH, rows)
    save_json_atomic(STATUS_PATH, status)

    print("\nRESUMEN")
    for info in sorted(status.values(), key=lambda x: x["liga"]):
        if info["eventos"] == 0 and not info["error"] and not MOSTRAR_LIGAS_VACIAS:
            continue
        if info["error"]:
            print(f"❌ {info['liga']}: {info['error']}")
        else:
            print(f"✅ {info['liga']}: {info['guardados']}/{info['eventos']} | PA={info['con_pago']} | sin PA={info['sin_pago']}")

    con_pago = sum(x["con_pago"] for x in status.values())
    sin_pago = sum(x["sin_pago"] for x in status.values())
    elapsed = time.perf_counter() - started
    print(f"\n💾 {len(rows)} partidos | PA={con_pago} | sin PA={sin_pago} | fallback={fallback_count} | {elapsed:.2f}s")
    print(OUT_PATH)


if __name__ == "__main__":
    main()
