import os
import re
import json
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import requests


# ==========================================================
# CONFIG
# ==========================================================
BASE = "https://prod20465-178940673.fssb.io"

OUT_DIR = "data"
os.makedirs(OUT_DIR, exist_ok=True)

OUT_JSON = os.path.join(OUT_DIR, "cuotas_tinbet.json")
ERROR_LOG = os.path.join(OUT_DIR, "error_tinbet_log.txt")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)

# Tokens del último curl enviado.
AUTHORIZATION_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJsYW5ndWFnZUNvZGUiOiJlcyIsImN1cnJlbmN5UmF0ZSI6MSwiY3VycmVuY3lSYXRlZXVyIjoxLCJjdXN0b21lckxpbWl0cyI6W10sImN1c3RvbWVyVHlwZSI6ImFub24iLCJjdXJyZW5jeUNvZGUiOiJQRU4iLCJjdXJyZW5jeUNvZGVBbm9uIjoiIiwiY3VzdG9tZXJJZCI6LTEsImJldHRpbmdWaWV3IjoiRXVyb3BlYW4gVmlldyIsInNvcnRpbmdUeXBlSWQiOjAsImJldHRpbmdMYXlvdXQiOjEsImRpc3BsYXlUeXBlSWQiOjEsInRpbWV6b25lSWQiOjE1LCJhdXRvVGltZVpvbmUiOjEsImxhc3RJbnB1dFN0YWtlIjowLCJldU9kZHNJZCI6IjEiLCJhc2lhbk9kZHNJZCI6IjMiLCJrb3JlYW5PZGRzSWQiOiIxIiwiaW50VGFiRXhwYW5kZWQiOjEsImRvbWFpbklEIjo0Mzg4LCJhZ2VudElEIjoxNzg5NDA2NzMsInNpdGVJZCI6MjA0NjUsInNlbGVjdGVkT3B0aW9uSWQiOjAsImN1c3RvbWVyTGV2ZWwiOjAsImJhbGFuY2VQcmlvcml0eSI6MSwiRVBPRW5hYmxlZCI6dHJ1ZSwiaGFzUGxhY2VkQmV0cyI6ZmFsc2UsImlhdCI6MTc4NTY5MjA4OX0."
    "sWBEx9gHDrUz0zpYLG_4bSopjqxwcjK30ozPXVWqRn8"
)

SESSION_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJjdXN0b21lcklkIjotMSwiZXhwaXJlZERhdGUiOjE3ODU3Nzg0ODkyNjYsImlhdCI6MTc4NTY5MjA4OX0."
    "kXmSNKp4kADx_OWA5YX2sT0I_SvX6GOf4TNMycaYdns"
)

# Listado de liga: suficiente para obtener eventos y ML0 preliminar.
MARKET_TYPE_IDS = (
    "ML39,ML169,ML1633,ML1,OU249,OU39,OU6001,"
    "OU1697,OU1633,OU201,QA158,QA1693,ML167,"
    "ML0,ML1,OU200,OU201,QA158,ML167"
)

HORAS_ADELANTE = 72
TIMEOUT = 30
MAX_INTENTOS = 3

# Detalles de partidos consultados simultáneamente.
MAX_WORKERS_DETALLE = 6

DEBUG = False


# ==========================================================
# LIGAS
# ==========================================================
LIGAS_EQUIVALENCIAS = [
    ("Premier League", "Inglaterra", "24", "Premier League"),
    ("Copa FA", "Inglaterra", "89", "FA Cup"),
    ("Copa EFL de Inglaterra", "Inglaterra", "197992793078919168", "EFL Cup"),
    ("Championship", "Inglaterra", "43", "Championship"),
    ("La Liga", "España", "38", "La Liga"),
    ("Copa del Rey", "España", "105", "Copa del Rey"),
    ("Serie A", "Italia", "74", "Serie A"),
    ("Copa Italia", "Italia", "255821541135360000", "Copa Italia"),
    ("Bundesliga", "Alemania", "110", "Bundesliga"),
    ("Copa DFB Alemania", "Alemania", "5768", "Copa Alemana"),
    ("Ligue 1", "Francia", "25", "Ligue 1"),
    ("Coupe de France", "Francia", "35", "Copa Francia"),
    ("Brasileirao, Serie A", "Brasil", "530", "Brasileirao"),
    ("Copa de Brasil", "Brasil", "136", "Copa de Brasil"),
    ("Liga MX", "México", "632", "Liga MX"),
    ("MLS", "Estados Unidos", "224", "MLS"),
    ("Liga 1", "Perú", "203110137349808128", "Liga 1 Perú"),
    ("Primeira Liga", "Portugal", "32", "Primeira Liga"),
    ("Eredivisie", "Países Bajos", "111", "Eredivisie"),
    ("UEFA Champions League", "Europa", "125", "UEFA Champions League"),
    ("UEFA Europa League", "Europa", "2719", "UEFA Europa League"),
    ("UEFA Europa Conference League", "Europa", "203553622255214592", "UEFA Conference League"),
    ("Clasificación Copa Libertadores", "Sudamérica", "7322", "Copa Libertadores"),
    ("Copa Sudamericana Clasificatoria", "Sudamérica", "552510194681483264", "Copa Sudamericana"),
    ("Eliminatorias europeas", "Internacional", "466", "Eliminatorias Europa - WC26"),
]


# ==========================================================
# HELPERS
# ==========================================================
def log_error(message):
    with open(ERROR_LOG, "a", encoding="utf-8") as file:
        file.write(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"{message}\n"
        )


def norm(value):
    if not value:
        return ""

    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    return re.sub(r"\s+", " ", text).strip()


def safe_float(value):
    try:
        odd = float(value)
        return odd if odd > 1 else None
    except (TypeError, ValueError):
        return None


def fecha_to_utc(fecha_iso):
    if not fecha_iso:
        return None

    try:
        value = str(fecha_iso).strip()

        if value.endswith("Z"):
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).astimezone(timezone.utc)

        return datetime.fromisoformat(value).replace(
            tzinfo=timezone.utc
        )

    except Exception:
        return None


ISO_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,3})?(?:Z)?"
)


def find_fecha(value):
    if isinstance(value, str):
        match = ISO_RE.search(value)
        return match.group(0) if match else ""

    if isinstance(value, dict):
        for item in value.values():
            found = find_fecha(item)
            if found:
                return found

    if isinstance(value, list):
        for item in value:
            found = find_fecha(item)
            if found:
                return found

    return ""


def find_equipos(row):
    if not isinstance(row, list):
        return "", ""

    for block in row:
        if not isinstance(block, list):
            continue

        home = ""
        away = ""

        for item in block:
            if not isinstance(item, list) or len(item) < 3:
                continue

            name_obj = item[1]
            side = str(item[2]).lower()

            if isinstance(name_obj, dict) and name_obj:
                name = (
                    name_obj.get("ES")
                    or name_obj.get("ES-PE")
                    or name_obj.get("es-PE")
                    or next(iter(name_obj.values()), "")
                )
            elif isinstance(name_obj, str):
                name = name_obj
            else:
                name = ""

            if "home" in side:
                home = name
            elif "away" in side:
                away = name

        if home and away:
            return home, away

    return "", ""


def extract_1x2_from_market_list(markets, wanted_code):
    """
    Extrae un 1X2 desde la estructura del endpoint eventpage.
    market[5][0] contiene ML0 o ML5000.
    market[13] contiene las selecciones.
    selection[6] contiene la cuota decimal.
    selection[9] contiene side:
      1 = Local
      2 = Empate
      3 = Visita
    """
    if not isinstance(markets, list):
        return None

    for market in markets:
        if not isinstance(market, list) or len(market) < 14:
            continue

        market_info = market[5]

        if (
            not isinstance(market_info, list)
            or not market_info
            or str(market_info[0]) != wanted_code
        ):
            continue

        selections = market[13]

        if not isinstance(selections, list):
            continue

        result = {
            "Local": None,
            "Empate": None,
            "Visita": None,
        }

        for selection in selections:
            if not isinstance(selection, list) or len(selection) < 10:
                continue

            odd = safe_float(selection[6])
            side = selection[9]

            if odd is None:
                continue

            if side == 1:
                result["Local"] = odd
            elif side == 2:
                result["Empate"] = odd
            elif side == 3:
                result["Visita"] = odd

        if all(
            result[key] is not None
            for key in ("Local", "Empate", "Visita")
        ):
            return result

    return None


def extract_detail_markets(payload):
    """
    En eventpage, el primer evento está en data[0].
    La lista completa de mercados está en data[0][20].
    """
    if not isinstance(payload, dict):
        return None

    data = payload.get("data")

    if not isinstance(data, list) or not data:
        return None

    event_row = data[0]

    if not isinstance(event_row, list) or len(event_row) <= 20:
        return None

    markets = event_row[20]

    normal_pa = extract_1x2_from_market_list(
        markets,
        "ML0",
    )

    super_nopa = extract_1x2_from_market_list(
        markets,
        "ML5000",
    )

    if normal_pa is None:
        return None

    # Empate: se conserva la mayor cuota disponible.
    empate_candidates = [
        value
        for value in (
            normal_pa["Empate"],
            (
                super_nopa["Empate"]
                if super_nopa
                else None
            ),
        )
        if value is not None
    ]

    cuota_empate = max(empate_candidates)

    return {
        "pa": normal_pa,
        "nopa": super_nopa,
        "empate": cuota_empate,
    }


# ==========================================================
# SESSION / HEADERS
# ==========================================================
def make_session():
    session = requests.Session()
    session.cookies.set(
        "authorization",
        AUTHORIZATION_TOKEN,
    )
    session.cookies.set(
        "session",
        SESSION_TOKEN,
    )
    return session


def make_headers(referer):
    return {
        "accept": "application/json",
        "accept-language": (
            "es-US,es-PE;q=0.9,es-419;q=0.8,"
            "es;q=0.7,en;q=0.6"
        ),
        "authorization": AUTHORIZATION_TOKEN,
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": referer,
        "sec-ch-ua": (
            '"Not;A=Brand";v="8", '
            '"Chromium";v="150", '
            '"Google Chrome";v="150"'
        ),
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "sec-fetch-storage-access": "active",
        "session": SESSION_TOKEN,
        "user-agent": UA,
    }


# ==========================================================
# REQUESTS
# ==========================================================
def get_gameodds(session, headers, league_id):
    url = (
        f"{BASE}/api/eventlist/eu/leagues/v2/"
        f"{league_id}/gameOdds"
    )

    params = {
        "marketTypeIds": MARKET_TYPE_IDS,
        "IsLive": "false",
    }

    for attempt in range(1, MAX_INTENTOS + 1):
        try:
            response = session.get(
                url,
                headers=headers,
                params=params,
                timeout=TIMEOUT,
            )

            if response.status_code == 200:
                return response.json()

            error = (
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

            if response.status_code == 401:
                log_error(
                    f"TINBET league={league_id}: {error}"
                )
                return {}

        except (requests.RequestException, ValueError) as exc:
            error = str(exc)

        if attempt < MAX_INTENTOS:
            time.sleep(attempt)

    log_error(
        f"TINBET league={league_id}: {error}"
    )

    return {}


def get_event_detail(candidate):
    event_id = candidate["EventId"]

    local_slug = requests.utils.quote(
        candidate["Local"].replace(" ", "-"),
        safe="",
    )
    visita_slug = requests.utils.quote(
        candidate["Visita"].replace(" ", "-"),
        safe="",
    )
    pais_slug = requests.utils.quote(
        candidate["Pais"],
        safe="",
    )
    liga_slug = requests.utils.quote(
        candidate["Liga"].replace(" ", "-"),
        safe="",
    )

    referer = (
        f"{BASE}/es/spbk/F%C3%BAtbol/"
        f"{pais_slug}/{liga_slug}/"
        f"{local_slug}-vs-{visita_slug}/"
        f"{event_id}?operatorToken=logout"
    )

    headers = make_headers(referer)
    url = (
        f"{BASE}/api/eventpage/events/{event_id}"
    )
    params = {
        "hideX25X75Selections": "false",
    }

    session = make_session()
    last_error = ""

    try:
        for attempt in range(1, MAX_INTENTOS + 1):
            try:
                response = session.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=TIMEOUT,
                )

                if response.status_code == 200:
                    return {
                        "ok": True,
                        "candidate": candidate,
                        "payload": response.json(),
                        "error": None,
                    }

                last_error = (
                    f"HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )

                if response.status_code == 401:
                    break

            except (
                requests.RequestException,
                ValueError,
            ) as exc:
                last_error = str(exc)

            if attempt < MAX_INTENTOS:
                time.sleep(attempt)

    finally:
        session.close()

    return {
        "ok": False,
        "candidate": candidate,
        "payload": None,
        "error": last_error,
    }


# ==========================================================
# LISTADO DE EVENTOS
# ==========================================================
def extract_candidates_from_league(
    payload,
    pais,
    liga,
    now_utc,
    cutoff_utc,
):
    candidates = []

    rows = payload.get("data", [])

    if not isinstance(rows, list):
        return candidates

    for row in rows:
        if not isinstance(row, list) or not row:
            continue

        event_id = str(row[0])
        fecha = find_fecha(row)
        dt = fecha_to_utc(fecha)

        if (
            dt is None
            or dt <= now_utc
            or dt > cutoff_utc
        ):
            continue

        local, visita = find_equipos(row)

        if not local or not visita:
            continue

        candidates.append({
            "Liga": liga,
            "Pais": pais,
            "Partido": f"{local} vs {visita}",
            "Fecha": fecha,
            "Casa": "Tinbet",
            "Local": local,
            "Visita": visita,
            "EventId": event_id,
        })

    return candidates


# ==========================================================
# MAIN
# ==========================================================
def main():
    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc + timedelta(
        hours=HORAS_ADELANTE
    )

    print(
        f"📆 Tinbet: "
        f"{now_utc:%Y-%m-%d %H:%M} -> "
        f"{cutoff_utc:%Y-%m-%d %H:%M} UTC"
    )

    session = make_session()
    candidates = []

    try:
        for _, pais, league_id, liga in LIGAS_EQUIVALENCIAS:
            country_slug = requests.utils.quote(
                pais,
                safe="",
            )
            league_slug = requests.utils.quote(
                liga.replace(" ", "-"),
                safe="",
            )

            referer = (
                f"{BASE}/es/spbk/F%C3%BAtbol/"
                f"{country_slug}/{league_slug}"
                "?operatorToken=logout"
            )

            headers = make_headers(referer)
            payload = get_gameodds(
                session,
                headers,
                league_id,
            )

            if not payload:
                continue

            league_candidates = (
                extract_candidates_from_league(
                    payload=payload,
                    pais=pais,
                    liga=liga,
                    now_utc=now_utc,
                    cutoff_utc=cutoff_utc,
                )
            )

            candidates.extend(
                league_candidates
            )

            if DEBUG:
                print(
                    f"🔎 {liga}: "
                    f"{len(league_candidates)} candidatos"
                )

    finally:
        session.close()

    # Dedupe por EventId.
    unique = {}

    for candidate in candidates:
        unique[candidate["EventId"]] = candidate

    candidates = list(unique.values())

    if not candidates:
        with open(
            OUT_JSON,
            "w",
            encoding="utf-8",
        ) as file:
            json.dump(
                [],
                file,
                ensure_ascii=False,
                indent=2,
            )

        print("💾 0 partidos")
        return

    rows = []
    with_pa = 0
    without_pa = 0
    errors = 0

    workers = min(
        MAX_WORKERS_DETALLE,
        len(candidates),
    )

    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:
        future_map = {
            executor.submit(
                get_event_detail,
                candidate,
            ): candidate
            for candidate in candidates
        }

        for future in as_completed(future_map):
            candidate = future_map[future]

            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "ok": False,
                    "candidate": candidate,
                    "payload": None,
                    "error": str(exc),
                }

            if not result["ok"]:
                errors += 1
                log_error(
                    f"DETAIL event={candidate['EventId']}: "
                    f"{result['error']}"
                )
                continue

            markets = extract_detail_markets(
                result["payload"]
            )

            if markets is None:
                errors += 1
                log_error(
                    f"DETAIL event={candidate['EventId']}: "
                    "sin ML0"
                )
                continue

            pa = markets["pa"]
            nopa = markets["nopa"]

            if nopa is None:
                # Si no hay Supercuota, se conserva el partido,
                # PA queda con ML0 y NoPA queda null.
                without_pa += 1
                local_nopa = None
                visita_nopa = None
            else:
                with_pa += 1
                local_nopa = nopa["Local"]
                visita_nopa = nopa["Visita"]

            row = {
                "Liga": candidate["Liga"],
                "Partido": candidate["Partido"],
                "Fecha": candidate["Fecha"],
                "Casa": "Tinbet",
                "Local": candidate["Local"],
                "Visita": candidate["Visita"],

                # Resultado del Partido ML0 = PA.
                "Cuota Local": pa["Local"],
                "Cuota Empate": markets["empate"],
                "Cuota Visita": pa["Visita"],

                # Resultado - Supercuotas ML5000 = NoPA.
                "Cuota Local NoPA": local_nopa,
                "Cuota Visita NoPA": visita_nopa,

                "EventId": (
                    int(candidate["EventId"])
                    if candidate["EventId"].isdigit()
                    else candidate["EventId"]
                ),
            }

            rows.append(row)

            if DEBUG:
                print(
                    f"✅ {candidate['Partido']} | "
                    f"PA={pa['Local']}/{pa['Empate']}/{pa['Visita']} | "
                    f"NoPA={local_nopa}/{visita_nopa}"
                )

    rows.sort(
        key=lambda item: (
            item["Fecha"],
            item["Liga"],
            item["Partido"],
        )
    )

    with open(
        OUT_JSON,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            rows,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"✅ Partidos: {len(rows)} | "
        f"Con Supercuota: {with_pa} | "
        f"Sin Supercuota: {without_pa} | "
        f"Errores: {errors}"
    )
    print(f"💾 Archivo: {OUT_JSON}")


if __name__ == "__main__":
    main()