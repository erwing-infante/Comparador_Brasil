import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests


# ==========================================================
# CONFIG
# ==========================================================
BASE = "https://guest.api.arcadia.pinnacle.com/0.1"

TZ_LOCAL = ZoneInfo("UTC")
DIAS_A_FUTURO = 3
CASA = "Pinnacle"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEBUG_DIR = os.path.join(DATA_DIR, "debug_pinnacle")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_pinnacle.json")
STATUS_PATH = os.path.join(DEBUG_DIR, "status_pinnacle.json")


PROXY = "http://ad9063918cd09688:0qAPgBHzQ1rdvs2O@res.proxy-seller.com:10000"

PROXIES = {
    "http": PROXY,
    "https": PROXY,
}

# ==========================================================
# LIGAS
# ==========================================================
# Solo IDs reales.
# Se retiraron todos los 999999 repetidos porque en un dict
# Python solo sobrevivía la última entrada.
LIGAS_PINNACLE = {
    1980: "Premier League",
    1982: "EFL Cup",
    1977: "Championship",
    2196: "La Liga",
    2436: "Serie A",
    1842: "Bundesliga",
    2036: "Ligue 1",
    1834: "Brasileirao",
    2242: "Liga MX",
    2663: "MLS",
    2366: "Liga 1 Perú",
    2386: "Primeira Liga",
    1928: "Eredivisie",
    1833: "Copa de Brasil",
    2627: "UEFA Champions League",
    1875: "Copa Libertadores",
    2472: "Copa Sudamericana",
}


# ==========================================================
# VELOCIDAD Y RED
# ==========================================================
MAX_WORKERS_LIGAS = 8
MAX_WORKERS_MERCADOS = 12

TIMEOUT_MATCHUPS = (8, 25)
TIMEOUT_MARKETS = (8, 25)

MAX_INTENTOS_MATCHUPS = 2
MAX_INTENTOS_MARKETS = 2

MOSTRAR_LIGAS_VACIAS = False


# ==========================================================
# HEADERS
# ==========================================================
HEADERS = {
    "accept": "application/json",
    "accept-language": (
        "es-US,es-PE;q=0.9,es-419;q=0.8,"
        "es;q=0.7,en;q=0.6"
    ),
    "content-type": "application/json",
    "origin": "https://www.pinnacle.com",
    "referer": "https://www.pinnacle.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "x-api-key": "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R",
    "x-device-uuid": "6f97bce1-ea2548d3-de8a9b22-4e4338ea",
}


# ==========================================================
# SESIÓN POR HILO
# ==========================================================
_thread_local = threading.local()


def get_session():
    session = getattr(_thread_local, "session", None)

    if session is None:
        session = requests.Session()

        # Usa Proxy-Seller (para VPS).
        session.trust_env = False
        session.headers.update(HEADERS)
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


def save_debug(filename, content):
    path = os.path.join(DEBUG_DIR, filename)

    if isinstance(content, str):
        with open(path, "w", encoding="utf-8") as file:
            file.write(content)
    else:
        save_json(path, content)

    return path


def american_to_decimal(price):
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None

    if price == 0:
        return None

    if price > 0:
        return round(1 + price / 100, 3)

    return round(1 + 100 / abs(price), 3)


def parse_utc(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
        return dt.astimezone(TZ_LOCAL)
    except Exception:
        return None


def to_json_fecha(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def get_team(event, alignment):
    for participant in event.get("participants", []) or []:
        if participant.get("alignment") == alignment:
            return participant.get("name")

    return None


def is_valid_matchup(event, now, window_end):
    if event.get("type") != "matchup":
        return False

    if event.get("parentId") is not None:
        return False

    if event.get("isLive") is True:
        return False

    if str(event.get("status", "")).lower() not in {
        "pending",
        "open",
    }:
        return False

    if not event.get("hasMarkets"):
        return False

    dt = parse_utc(event.get("startTime"))

    if dt is None:
        return False

    return now < dt <= window_end


# ==========================================================
# REQUEST JSON
# ==========================================================
def request_json(
    url,
    debug_name,
    timeout,
    max_intentos,
):
    session = get_session()

    last_error = ""
    status_code = None

    for intento in range(1, max_intentos + 1):
        try:
            response = session.get(
                url,
                timeout=timeout,
            )

            status_code = response.status_code
            content_type = str(
                response.headers.get("content-type", "")
            ).lower()

            if response.status_code != 200:
                last_error = (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                )

            elif "application/json" not in content_type:
                last_error = (
                    f"not_json: {content_type} | "
                    f"{response.text[:500]}"
                )

            else:
                return {
                    "ok": True,
                    "payload": response.json(),
                    "status_code": status_code,
                    "error": "",
                }

        except (requests.RequestException, ValueError) as error:
            last_error = str(error)

        if intento < max_intentos:
            time.sleep(0.4 * intento)

    save_debug(
        f"{debug_name}_error.json",
        {
            "url": url,
            "status_code": status_code,
            "error": last_error,
        },
    )

    return {
        "ok": False,
        "payload": None,
        "status_code": status_code,
        "error": last_error,
    }


# ==========================================================
# FETCH MATCHUPS
# ==========================================================
def fetch_matchups(league_id, league_name):
    url = f"{BASE}/leagues/{league_id}/matchups"

    result = request_json(
        url=url,
        debug_name=f"matchups_{league_id}",
        timeout=TIMEOUT_MATCHUPS,
        max_intentos=MAX_INTENTOS_MATCHUPS,
    )

    payload = result.get("payload")

    if isinstance(payload, list):
        matchups = payload
    else:
        matchups = []

    return {
        "league_id": league_id,
        "league_name": league_name,
        "matchups": matchups,
        "status_code": result.get("status_code"),
        "error": result.get("error", ""),
    }


# ==========================================================
# FETCH MARKETS
# ==========================================================
def fetch_markets(matchup):
    matchup_id = matchup["id"]

    url = (
        f"{BASE}/matchups/"
        f"{matchup_id}/markets/straight"
    )

    result = request_json(
        url=url,
        debug_name=f"markets_{matchup_id}",
        timeout=TIMEOUT_MARKETS,
        max_intentos=MAX_INTENTOS_MARKETS,
    )

    payload = result.get("payload")

    if not isinstance(payload, list):
        payload = []

    return {
        "matchup": matchup,
        "markets": payload,
        "status_code": result.get("status_code"),
        "error": result.get("error", ""),
    }


# ==========================================================
# PARSE ODDS
# ==========================================================
def extract_1x2(markets):
    candidates = []

    for market in markets:
        if market.get("type") != "moneyline":
            continue

        if str(market.get("status", "")).lower() != "open":
            continue

        if market.get("isAlternate") is True:
            continue

        prices = market.get("prices", []) or []

        designations = {
            price.get("designation")
            for price in prices
        }

        if {
            "home",
            "draw",
            "away",
        }.issubset(designations):
            candidates.append(market)

    if not candidates:
        return None

    selected = next(
        (
            market
            for market in candidates
            if market.get("period") == 0
        ),
        candidates[0],
    )

    cuotas = {
        "Local": None,
        "Empate": None,
        "Visita": None,
    }

    for price_item in selected.get("prices", []) or []:
        designation = price_item.get("designation")

        decimal = american_to_decimal(
            price_item.get("price")
        )

        if decimal is None:
            continue

        if designation == "home":
            cuotas["Local"] = decimal
        elif designation == "draw":
            cuotas["Empate"] = decimal
        elif designation == "away":
            cuotas["Visita"] = decimal

    if all(
        cuotas[key] is not None
        for key in (
            "Local",
            "Empate",
            "Visita",
        )
    ):
        return cuotas

    return None


# ==========================================================
# PREPARAR EVENTO
# ==========================================================
def prepare_matchup(
    event,
    league_id,
    league_name,
    now,
    window_end,
):
    if not is_valid_matchup(
        event,
        now,
        window_end,
    ):
        return None

    matchup_id = event.get("id")
    dt = parse_utc(event.get("startTime"))
    local = get_team(event, "home")
    visita = get_team(event, "away")

    if (
        not matchup_id
        or dt is None
        or not local
        or not visita
    ):
        return None

    return {
        "id": matchup_id,
        "league_id": league_id,
        "league_name": league_name,
        "local": local,
        "visita": visita,
        "fecha_dt": dt,
    }


# ==========================================================
# CONSTRUIR FILA
# ==========================================================
def build_row(matchup, cuotas):
    return {
        "Liga": matchup["league_name"],
        "Partido": (
            f"{matchup['local']} "
            f"vs {matchup['visita']}"
        ),
        "Fecha": to_json_fecha(
            matchup["fecha_dt"].replace(
                tzinfo=None
            )
        ),
        "Casa": CASA,
        "Local": matchup["local"],
        "Visita": matchup["visita"],

        # Pinnacle no tiene mercado de Pago Anticipado.
        # Estos campos quedan en null para no mezclar sus
        # cuotas con el programa actual de PA.
        "Cuota Local": None,
        "Cuota Empate": cuotas["Empate"],
        "Cuota Visita": None,

        # Mercado 1X2 normal para el escáner NoPA.
        "Cuota Local NoPA": cuotas["Local"],
        "Cuota Visita NoPA": cuotas["Visita"],

        "EventId": matchup["id"],
    }


# ==========================================================
# MAIN
# ==========================================================
def main():
    started = time.perf_counter()

    now = datetime.now(TZ_LOCAL)
    window_end = now + timedelta(
        days=DIAS_A_FUTURO
    )

    print(
        f"📆 Pinnacle: "
        f"{now:%Y-%m-%d %H:%M} -> "
        f"{window_end:%Y-%m-%d %H:%M} UTC"
    )

    status = {
        str(league_id): {
            "liga": league_name,
            "eventos_recibidos": 0,
            "eventos_72h": 0,
            "odds": 0,
            "matchups_status": None,
            "error": "",
        }
        for league_id, league_name
        in LIGAS_PINNACLE.items()
    }

    # ======================================================
    # 1. LIGAS EN PARALELO
    # ======================================================
    league_results = []

    with ThreadPoolExecutor(
        max_workers=min(
            MAX_WORKERS_LIGAS,
            len(LIGAS_PINNACLE),
        )
    ) as executor:
        futures = [
            executor.submit(
                fetch_matchups,
                league_id,
                league_name,
            )
            for league_id, league_name
            in LIGAS_PINNACLE.items()
        ]

        for future in as_completed(futures):
            league_results.append(
                future.result()
            )

    matchups = []
    seen_matchups = set()

    for result in league_results:
        league_id = result["league_id"]
        league_name = result["league_name"]
        status_key = str(league_id)

        status[status_key]["matchups_status"] = (
            result["status_code"]
        )
        status[status_key]["error"] = (
            result["error"]
        )
        status[status_key]["eventos_recibidos"] = len(
            result["matchups"]
        )

        valid_count = 0

        for event in result["matchups"]:
            matchup = prepare_matchup(
                event,
                league_id,
                league_name,
                now,
                window_end,
            )

            if matchup is None:
                continue

            matchup_key = str(matchup["id"])

            if matchup_key in seen_matchups:
                continue

            seen_matchups.add(matchup_key)
            matchups.append(matchup)
            valid_count += 1

        status[status_key]["eventos_72h"] = valid_count

    # ======================================================
    # 2. MERCADOS EN PARALELO
    # ======================================================
    rows = []

    if matchups:
        with ThreadPoolExecutor(
            max_workers=min(
                MAX_WORKERS_MERCADOS,
                len(matchups),
            )
        ) as executor:
            future_map = {
                executor.submit(
                    fetch_markets,
                    matchup,
                ): matchup
                for matchup in matchups
            }

            for future in as_completed(future_map):
                result = future.result()
                matchup = result["matchup"]

                if result["status_code"] != 200:
                    continue

                cuotas = extract_1x2(
                    result["markets"]
                )

                if not cuotas:
                    save_debug(
                        f"markets_no_1x2_"
                        f"{matchup['id']}.json",
                        result["markets"],
                    )
                    continue

                row = build_row(
                    matchup,
                    cuotas,
                )

                rows.append(row)

                status[
                    str(matchup["league_id"])
                ]["odds"] += 1

    # ======================================================
    # 3. DEDUPLICAR
    # ======================================================
    unique_rows = {}

    for row in rows:
        unique_rows[
            str(row["EventId"])
        ] = row

    rows = list(unique_rows.values())

    rows.sort(
        key=lambda item: (
            item["Fecha"],
            item["Liga"],
            item["Partido"],
        )
    )

    save_json(OUT_PATH, rows)
    save_json(STATUS_PATH, status)

    # ======================================================
    # RESUMEN COMPACTO
    # ======================================================
    print("\nRESUMEN")

    for info in sorted(
        status.values(),
        key=lambda item: item["liga"],
    ):
        if (
            info["eventos_72h"] == 0
            and not info["error"]
            and not MOSTRAR_LIGAS_VACIAS
        ):
            continue

        if info["error"]:
            print(
                f"❌ {info['liga']}: "
                f"{info['error'][:120]}"
            )
        elif info["eventos_72h"] == 0:
            print(
                f"— {info['liga']}: 0 eventos"
            )
        else:
            print(
                f"✅ {info['liga']}: "
                f"{info['odds']}/"
                f"{info['eventos_72h']} con 1X2"
            )

    elapsed = (
        time.perf_counter()
        - started
    )

    print(
        f"\n💾 {len(rows)} partidos | "
        f"{elapsed:.2f}s"
    )

    print(OUT_PATH)


if __name__ == "__main__":
    main()