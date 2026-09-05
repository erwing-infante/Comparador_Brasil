import json
import os
import re
import time
import threading
import unicodedata

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)

from datetime import (
    datetime,
    timedelta,
)

from zoneinfo import ZoneInfo

import requests


# ==========================================================
# CONFIGURACIÓN
# ==========================================================

URL_LIGA = (
    "https://col-1xbet.com/service-api/"
    "LineFeed/Get1x2_VZip"
)

URL_PARTIDO = (
    "https://col-1xbet.com/service-api/"
    "LineFeed/GetGameZip"
)


TZ_FECHA_1XBET = ZoneInfo("UTC")

DIAS_A_FUTURO = 3

CASA = "1xbet"

DEBUG = False


def debug_print(*args, **kwargs):

    if DEBUG:
        print(
            *args,
            **kwargs,
        )


# ==========================================================
# VELOCIDAD
# ==========================================================

MAX_INTENTOS_LIGA = 3
MAX_INTENTOS_PARTIDO = 2

MAX_WORKERS_LIGAS = 10

# IMPORTANTE:
# Ahora es un pool GLOBAL.
MAX_WORKERS_PARTIDOS = 16

TIMEOUT_LIGA = (8, 30)
TIMEOUT_PARTIDO = (7, 22)


# ==========================================================
# ARCHIVOS
# ==========================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data",
)

os.makedirs(
    DATA_DIR,
    exist_ok=True,
)

OUT_PATH = os.path.join(
    DATA_DIR,
    "cuotas_1xbet.json",
)


# ==========================================================
# LIGAS
# ==========================================================

LIGAS_1XBET = {

    88637: {
        "nombre": "Premier League",
        "slug": "england-premier-league",
    },

    # 108319: {
    #     "nombre": "FA Cup",
    #     "slug": "england-fa-cup",
    # },

    119237: {
        "nombre": "EFL Cup",
        "slug": "england-league-cup",
    },

    105759: {
        "nombre": "Championship",
        "slug": "england-championship",
    },

    127733: {
        "nombre": "La Liga",
        "slug": "spain-la-liga",
    },

    110163: {
        "nombre": "Serie A",
        "slug": "italy-serie-a",
    },

    96463: {
        "nombre": "Bundesliga",
        "slug": "germany-bundesliga",
    },

    # 119235: {
    #     "nombre": "Copa Alemana",
    #     "slug": "germany-dfb-pokal",
    # },

    12821: {
        "nombre": "Ligue 1",
        "slug": "france-ligue-1",
    },

    1268397: {
        "nombre": "Brasileirao",
        "slug":
            "brazil-campeonato-brasileiro-serie-a",
    },

    # 120013: {
    #     "nombre": "Copa de Brasil",
    #     "slug": "brazil-copa-do-brasil",
    # },

    2306111: {
        "nombre": "Liga MX",
        "slug": "mexico-liga-mx",
    },

    828065: {
        "nombre": "MLS",
        "slug": "usa-mls",
    },

    2892390: {
        "nombre": "Liga 1 Perú",
        "slug": "peru-liga-1",
    },

    3007689: {
        "nombre": "Primeira Liga",
        "slug": "portugal-primeira-liga",
    },

    2018750: {
        "nombre": "Eredivisie",
        "slug": "netherlands-eredivisie",
    },

    118587: {
        "nombre": "UEFA Champions League",
        "slug": "uefa-champions-league",
    },

    118593: {
        "nombre": "UEFA Europa League",
        "slug": "uefa-europa-league",
    },

    2252762: {
        "nombre": "UEFA Conference League",
        "slug": "uefa-conference-league",
    },

    142091: {
        "nombre": "Copa Libertadores",
        "slug": "copa-libertadores",
    },

    1528791: {
        "nombre": "Copa Sudamericana",
        "slug": "copa-sudamericana",
    },
}


# ==========================================================
# MERCADOS
# ==========================================================

GRUPO_1X2_NORMAL = 1

TIPO_LOCAL_NORMAL = 1
TIPO_EMPATE_NORMAL = 2
TIPO_VISITA_NORMAL = 3


GRUPO_1X2_2UP = 11581

TIPO_LOCAL_2UP = 16684
TIPO_EMPATE_2UP = 16685
TIPO_VISITA_2UP = 16686


# ==========================================================
# X-HD
# ==========================================================

X_HD = (
    "W8tmp0nzvxLM3JkPbaXUK5RTiNN3sTCxF/u06IoktbQrWFYdJGW/"
    "MDz8unhJjyDNcpbci4/UITBTSDW/dVucZKXDoyzbohCUe528uVvtY4d5n28u/"
    "RD0qsOLEs9hz50ZVXxVzKi++YBszToJ+IS3i9IwjFDF0quBkfK3ataV9dvfEhUvY"
    "322CHZop4yzjoIB30uOVNFwRxjtssWvNK4G+zG7C32+HjfNEzkgJ5KGQ4J8JJ4da"
    "wvU1sQuQKzc0gIM4WfEkRQwMpf7pBI+JKoA+g7Ja6NGUUU+sZFXndFuApv7cV2n"
    "StLmzrDYHlRKEZhDm5JXx0hoEX2rPOAA2FuG1uqj/sigdXmXyFnTvz8+LDgCJJeH"
    "aahRj4lHWiCCjaTJbvU5HFOKzokBbCTRk1nd168/b7bYrjFWCPUdSaZ+Dlz6/lmY"
    "dUBHUB+leAKFEImAl7Vak05rFsZUep3k6lTv7Z8FXhYe5kYMfIyhQsklsPWo+gGR"
    "JXBIO5r3aYBzZ0IosGB8yH/2pjsjy1U662v7q69Cdj23S5o+MpeWZO7GJUxJzNaQ"
    "UB7c/2QDY7amEQTYnR+vKRpE/9y+Bc8VeAZyo75kpWTdUvOOVJjnrPYxYhk7zYwb"
    "FZUNZm/QxSTT0iNKzpHP1QsZIArxFilU9o7BKKqrkuGnoZlOSsYhhNb4OQvx"
)


# ==========================================================
# COOKIES
# ==========================================================

COOKIES = {

    "fatman_uuid":
        "91f85e2c-fc1b-0d3e-454d-606522ab318a",

    "application_locale":
        "es",

    "sh.session.id":
        "3719ede6-7d40-46ed-ad00-f004018a9c9a",

    "_ga":
        "GA1.1.1923369091.1781219559",

    "_ym_uid":
        "1781219559948970978",

    "_ym_d":
        "1781219559",

    "che_g":
        "45013f7a-179e-4ae3-9738-e16d22fb2ba1",

    "platform_type":
        "desktop",

    "lng":
        "es",

    "cookies_agree_type":
        "3",

    "tzo":
        "-5",

    "is12h":
        "0",

    "auid":
        "ua4qX2puZostM5ZpA46tAg==",

    "SESSION":
        "84d7e98ed69e56905a0abb558692cc04",

    "_ym_visorc":
        "b",

    "_ym_isad":
        "2",

    "_gcl_au":
        (
            "1.1.1444229129.1781219559.315731183."
            "1785620433.1785620432.1932761416."
            "1785620433.1785620432"
        ),

    "ggru":
        "146",

    "che_i":
        "9",

    "window_width":
        "982",

    "_ga_7JGWL9SV66":
        (
            "GS2.1.s1785620113$o30$g1$t1785625156"
            "$j32$l0$h1126615946"
        ),
}


# ==========================================================
# HEADERS
# ==========================================================

HEADERS_BASE = {

    "accept":
        "application/json, text/plain, */*",

    "accept-language":
        (
            "es-US,es-PE;q=0.9,"
            "es-419;q=0.8,"
            "es;q=0.7,en;q=0.6"
        ),

    "cache-control":
        "no-cache",

    "content-type":
        "application/json",

    "is-srv":
        "false",

    "pragma":
        "no-cache",

    "priority":
        "u=1, i",

    "sec-ch-ua":
        (
            '"Not;A=Brand";v="8", '
            '"Chromium";v="150", '
            '"Google Chrome";v="150"'
        ),

    "sec-ch-ua-mobile":
        "?0",

    "sec-ch-ua-platform":
        '"Windows"',

    "sec-fetch-dest":
        "empty",

    "sec-fetch-mode":
        "cors",

    "sec-fetch-site":
        "same-origin",

    "user-agent":
        (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/150.0.0.0 "
            "Safari/537.36"
        ),

    "x-app-n":
        "__BETTING_APP__",

    "x-hd":
        X_HD,

    "x-mobile-project-id":
        "0",

    "x-requested-with":
        "XMLHttpRequest",

    "x-svc-source":
        "__BETTING_APP__",
}


# ==========================================================
# SESIÓN POR HILO
# ==========================================================

_thread_local = threading.local()


def get_session():

    session = getattr(
        _thread_local,
        "session",
        None,
    )

    if session is None:

        session = requests.Session()

        session.cookies.update(
            COOKIES
        )

        adapter = (
            requests.adapters.HTTPAdapter(
                pool_connections=20,
                pool_maxsize=20,
                max_retries=0,
            )
        )

        session.mount(
            "https://",
            adapter,
        )

        session.mount(
            "http://",
            adapter,
        )

        _thread_local.session = session

    return session


# ==========================================================
# UTILS
# ==========================================================

def save_json(path, data):

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def safe_int(value):

    try:
        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def safe_float(value):

    try:

        number = float(value)

        if number <= 1:
            return None

        return number

    except (
        TypeError,
        ValueError,
    ):
        return None


def normalize_slug(value):

    text = str(
        value or ""
    ).strip().lower()

    text = unicodedata.normalize(
        "NFD",
        text,
    )

    text = "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    )

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text,
    )

    return text.strip("-")


def unix_to_datetime(timestamp):

    if timestamp in (
        None,
        "",
        0,
        "0",
    ):
        return None

    try:

        timestamp = float(
            timestamp
        )

        if timestamp > 10_000_000_000:
            timestamp /= 1000

        return datetime.fromtimestamp(
            timestamp,
            TZ_FECHA_1XBET,
        )

    except Exception:
        return None


def to_iso_like_doradobet(dt):

    return dt.strftime(
        "%Y-%m-%dT%H:%M:%S.000"
    )


def is_live_or_started(event):

    live_flags = [

        event.get("Live"),
        event.get("LIV"),
        event.get("InLive"),
        event.get("is_live"),
        event.get("IsLive"),
        event.get("InPlay"),
        event.get("IsInPlay"),

    ]


    if any(

        str(value).lower()
        in (
            "true",
            "1",
            "yes",
        )

        for value in live_flags

        if value is not None

    ):
        return True


    for key in (
        "SS",
        "MS",
        "SST",
    ):

        value = event.get(
            key
        )

        if value in (
            None,
            "",
            0,
            "0",
        ):
            continue

        text = str(
            value
        ).lower()

        if any(
            word in text
            for word in (
                "live",
                "started",
                "inplay",
                "in_play",
                "1st",
                "2nd",
                "half",
            )
        ):
            return True

    return False


def is_special_event(event):

    local = str(
        event.get("O1")
        or ""
    ).strip().lower()

    visita = str(
        event.get("O2")
        or ""
    ).strip().lower()


    special_words = (
        "apuestas especiales",
        "special bets",
        "equipos locales",
        "equipos visitantes",
        "locales",
        "visitantes",
    )


    for word in special_words:

        if word in local:
            return True

        if word in visita:
            return True


    return False


# ==========================================================
# NORMAL DESDE LISTADO
# ==========================================================

def extract_normal_from_list(
    event,
):

    local = None
    empate = None
    visita = None


    for odd in (
        event.get("E", [])
        or []
    ):

        if not isinstance(
            odd,
            dict,
        ):
            continue


        group = safe_int(
            odd.get("G")
        )

        odd_type = safe_int(
            odd.get("T")
        )

        coefficient = safe_float(
            odd.get("C")
        )


        if (
            group
            != GRUPO_1X2_NORMAL
        ):
            continue


        if coefficient is None:
            continue


        if (
            odd_type
            == TIPO_LOCAL_NORMAL
        ):

            local = coefficient


        elif (
            odd_type
            == TIPO_EMPATE_NORMAL
        ):

            empate = coefficient


        elif (
            odd_type
            == TIPO_VISITA_NORMAL
        ):

            visita = coefficient


    if (
        local is None
        or empate is None
        or visita is None
    ):
        return None


    return {
        "local": local,
        "empate": empate,
        "visita": visita,
    }


# ==========================================================
# EXTRAER GETGAMEZIP
# ==========================================================

def flatten_market_odds(
    market,
):

    odds = []

    columns = (
        market.get("E", [])
        or []
    )


    for column in columns:

        if isinstance(
            column,
            dict,
        ):

            odds.append(
                column
            )

            continue


        if not isinstance(
            column,
            list,
        ):
            continue


        for odd in column:

            if isinstance(
                odd,
                dict,
            ):

                odds.append(
                    odd
                )


    return odds


def extract_game_markets(
    payload,
):

    if not isinstance(
        payload,
        dict,
    ):
        return None


    value = payload.get(
        "Value",
        {},
    )

    if not isinstance(
        value,
        dict,
    ):
        return None


    normal = {
        "local": None,
        "empate": None,
        "visita": None,
    }


    two_up = {
        "local": None,
        "empate": None,
        "visita": None,
    }


    markets = (
        value.get("GE", [])
        or []
    )


    for market in markets:

        if not isinstance(
            market,
            dict,
        ):
            continue


        group = safe_int(
            market.get("G")
        )


        if group not in (
            GRUPO_1X2_NORMAL,
            GRUPO_1X2_2UP,
        ):
            continue


        odds = flatten_market_odds(
            market
        )


        if group == GRUPO_1X2_NORMAL:

            for odd in odds:

                odd_type = safe_int(
                    odd.get("T")
                )

                coefficient = safe_float(
                    odd.get("C")
                )

                if coefficient is None:
                    continue


                if (
                    odd_type
                    == TIPO_LOCAL_NORMAL
                ):
                    normal["local"] = coefficient

                elif (
                    odd_type
                    == TIPO_EMPATE_NORMAL
                ):
                    normal["empate"] = coefficient

                elif (
                    odd_type
                    == TIPO_VISITA_NORMAL
                ):
                    normal["visita"] = coefficient


        elif group == GRUPO_1X2_2UP:

            for odd in odds:

                odd_type = safe_int(
                    odd.get("T")
                )

                coefficient = safe_float(
                    odd.get("C")
                )

                if coefficient is None:
                    continue


                if (
                    odd_type
                    == TIPO_LOCAL_2UP
                ):
                    two_up["local"] = coefficient

                elif (
                    odd_type
                    == TIPO_EMPATE_2UP
                ):
                    two_up["empate"] = coefficient

                elif (
                    odd_type
                    == TIPO_VISITA_2UP
                ):
                    two_up["visita"] = coefficient


    if not all(

        normal[key] is not None

        for key in (
            "local",
            "empate",
            "visita",
        )

    ):
        return None


    empate_candidates = [

        value

        for value in (
            normal["empate"],
            two_up["empate"],
        )

        if value is not None

    ]


    return {

        "normal":
            normal,

        "two_up":
            two_up,

        "empate_final":
            max(
                empate_candidates
            ),

        "tiene_2up":
            (
                two_up["local"]
                is not None
                and
                two_up["visita"]
                is not None
            ),
    }


# ==========================================================
# REFERERS
# ==========================================================

def build_league_referer(
    league_id,
    league_slug,
):

    return (
        "https://col-1xbet.com/"
        "es/line/football/"
        f"{league_id}-"
        f"{league_slug}"
    )


def build_game_referer(
    league_id,
    league_slug,
    game_ci,
    local,
    visita,
):

    match_slug = normalize_slug(
        f"{local}-{visita}"
    )


    return (
        "https://col-1xbet.com/"
        "es/line/football/"
        f"{league_id}-"
        f"{league_slug}/"
        f"{game_ci}-"
        f"{match_slug}"
    )


def build_league_headers(
    league_id,
    league_slug,
):

    headers = dict(
        HEADERS_BASE
    )


    headers["referer"] = (
        build_league_referer(
            league_id,
            league_slug,
        )
    )


    return headers


def build_game_headers(
    league_id,
    league_slug,
    game_ci,
    local,
    visita,
):

    headers = dict(
        HEADERS_BASE
    )


    headers["referer"] = (
        build_game_referer(
            league_id,
            league_slug,
            game_ci,
            local,
            visita,
        )
    )


    return headers


def build_league_params(
    league_id,
):

    return {

        "sports": 1,
        "champs": league_id,
        "count": 40,
        "lng": "es",
        "mode": 4,
        "country": 145,
        "getEmpty": "true",
        "virtualSports": "true",

    }


def build_game_params(
    game_ci,
):

    return {

        "id": game_ci,
        "lng": "es",
        "isSubGames": "true",
        "GroupEvents": "true",
        "countevents": 250,
        "grMode": 4,
        "topGroups": "",
        "country": 145,
        "marketType": 1,
        "isNewBuilder": "true",

    }


# ==========================================================
# LIGA
# ==========================================================

def fetch_league(
    league_id,
    league_name,
    league_slug,
):

    session = get_session()


    headers = build_league_headers(
        league_id,
        league_slug,
    )


    params = build_league_params(
        league_id
    )


    last_error = None


    for attempt in range(
        1,
        MAX_INTENTOS_LIGA + 1,
    ):

        try:

            response = session.get(
                URL_LIGA,
                headers=headers,
                params=params,
                timeout=TIMEOUT_LIGA,
            )


            if response.status_code == 200:

                payload = response.json()


                events = (

                    payload.get(
                        "Value",
                        [],
                    )

                    if isinstance(
                        payload,
                        dict,
                    )

                    else []

                ) or []


                return {

                    "ok":
                        True,

                    "events":
                        events,

                    "error":
                        None,

                }


            last_error = (
                f"HTTP "
                f"{response.status_code}: "
                f"{response.text[:300]}"
            )


        except (
            requests.RequestException,
            ValueError,
        ) as error:

            last_error = str(
                error
            )


        if attempt < MAX_INTENTOS_LIGA:

            time.sleep(
                attempt
            )


    return {

        "ok":
            False,

        "events":
            [],

        "error":
            last_error,

    }


# ==========================================================
# DETALLE PARTIDO
# ==========================================================

def fetch_game_detail(
    candidate,
):

    session = get_session()


    headers = build_game_headers(

        league_id=
            candidate["league_id"],

        league_slug=
            candidate["league_slug"],

        game_ci=
            candidate["game_ci"],

        local=
            candidate["local"],

        visita=
            candidate["visita"],

    )


    params = build_game_params(
        candidate["game_ci"]
    )


    last_error = None


    for attempt in range(
        1,
        MAX_INTENTOS_PARTIDO + 1,
    ):

        try:

            response = session.get(
                URL_PARTIDO,
                headers=headers,
                params=params,
                timeout=TIMEOUT_PARTIDO,
            )


            if response.status_code == 200:

                return {

                    "ok":
                        True,

                    "payload":
                        response.json(),

                    "error":
                        None,

                    "candidate":
                        candidate,

                }


            last_error = (

                f"HTTP "
                f"{response.status_code}: "
                f"{response.text[:300]}"

            )


            if response.status_code == 406:
                break


        except (
            requests.RequestException,
            ValueError,
        ) as error:

            last_error = str(
                error
            )


        if attempt < MAX_INTENTOS_PARTIDO:

            time.sleep(
                0.5 * attempt
            )


    return {

        "ok":
            False,

        "payload":
            None,

        "error":
            last_error,

        "candidate":
            candidate,

    }


# ==========================================================
# CANDIDATOS
# ==========================================================

def build_candidates(
    league_id,
    league_name,
    league_slug,
    events,
    now,
    window_end,
):

    candidates = []

    seen_ci = set()


    for event in events:

        event_datetime = (
            unix_to_datetime(
                event.get("S")
            )
        )


        if event_datetime is None:
            continue


        if not (
            now
            < event_datetime
            <= window_end
        ):
            continue


        if is_live_or_started(
            event
        ):
            continue


        if is_special_event(
            event
        ):
            continue


        local = event.get(
            "O1"
        )

        visita = event.get(
            "O2"
        )


        if not local or not visita:
            continue


        game_ci = safe_int(
            event.get("CI")
        )


        if game_ci is None:
            continue


        if game_ci in seen_ci:
            continue


        seen_ci.add(
            game_ci
        )


        candidates.append({

            "league_id":
                league_id,

            "league_name":
                league_name,

            "league_slug":
                league_slug,

            "event":
                event,

            "event_datetime":
                event_datetime,

            "local":
                local,

            "visita":
                visita,

            "game_ci":
                game_ci,

        })


    return candidates


# ==========================================================
# FILA
# ==========================================================

def build_row(
    candidate,
    normal_odds,
    pago_odds,
    cuota_empate,
):

    event = candidate[
        "event"
    ]


    fecha = (
        to_iso_like_doradobet(
            candidate[
                "event_datetime"
            ].replace(
                tzinfo=None
            )
        )
    )


    return {

        "Liga":
            candidate[
                "league_name"
            ],

        "Partido":
            (
                f"{candidate['local']} "
                f"vs "
                f"{candidate['visita']}"
            ),

        "Fecha":
            fecha,

        "Casa":
            CASA,

        "Local":
            candidate["local"],

        "Visita":
            candidate["visita"],

        "Cuota Local":
            pago_odds.get(
                "local"
            ),

        "Cuota Empate":
            cuota_empate,

        "Cuota Visita":
            pago_odds.get(
                "visita"
            ),

        "Cuota Local NoPA":
            normal_odds.get(
                "local"
            ),

        "Cuota Visita NoPA":
            normal_odds.get(
                "visita"
            ),

        "EventId":
            event.get("I"),

    }


# ==========================================================
# PROCESAR RESULTADO DE DETALLE
# ==========================================================

def procesar_resultado_detalle(
    result,
):

    candidate = result[
        "candidate"
    ]


    market_data = None


    if result["ok"]:

        market_data = (
            extract_game_markets(
                result["payload"]
            )
        )


    if market_data is None:

        normal_odds = (
            extract_normal_from_list(
                candidate["event"]
            )
        )


        if normal_odds is None:

            return {
                "row": None,
                "tiene_2up": False,
                "sin_1x2": True,
                "error":
                    not result["ok"],
            }


        pago_odds = {
            "local": None,
            "empate": None,
            "visita": None,
        }


        cuota_empate = (
            normal_odds[
                "empate"
            ]
        )


        tiene_2up = False


    else:

        normal_odds = (
            market_data[
                "normal"
            ]
        )


        pago_odds = (
            market_data[
                "two_up"
            ]
        )


        cuota_empate = (
            market_data[
                "empate_final"
            ]
        )


        tiene_2up = (
            market_data[
                "tiene_2up"
            ]
        )


    row = build_row(

        candidate=
            candidate,

        normal_odds=
            normal_odds,

        pago_odds=
            pago_odds,

        cuota_empate=
            cuota_empate,

    )


    return {

        "row":
            row,

        "tiene_2up":
            tiene_2up,

        "sin_1x2":
            False,

        "error":
            not result["ok"],

    }


# ==========================================================
# MAIN
# ==========================================================

def main():

    total_started = (
        time.perf_counter()
    )


    now = datetime.now(
        TZ_FECHA_1XBET
    )


    window_end = (

        now
        + timedelta(
            days=DIAS_A_FUTURO
        )

    )


    print(
        f"📆 Ventana: "
        f"{now:%Y-%m-%d %H:%M:%S} "
        f"-> "
        f"{window_end:%Y-%m-%d %H:%M:%S} "
        "(UTC/formato casas)"
    )


    # ======================================================
    # 1. DESCARGAR TODAS LAS LIGAS
    # ======================================================

    league_downloads = {}


    with ThreadPoolExecutor(

        max_workers=min(
            MAX_WORKERS_LIGAS,
            len(
                LIGAS_1XBET
            ),
        )

    ) as executor:


        future_map = {

            executor.submit(

                fetch_league,

                league_id,

                config[
                    "nombre"
                ],

                config[
                    "slug"
                ],

            ): (
                league_id,
                config,
            )

            for (
                league_id,
                config
            )
            in LIGAS_1XBET.items()

        }


        for future in as_completed(
            future_map
        ):

            league_id, config = (
                future_map[
                    future
                ]
            )


            try:

                result = (
                    future.result()
                )


            except Exception as error:

                result = {

                    "ok":
                        False,

                    "events":
                        [],

                    "error":
                        str(error),

                }


            league_downloads[
                league_id
            ] = result


    # ======================================================
    # 2. CONSTRUIR TODOS LOS CANDIDATOS
    # ======================================================

    all_candidates = []

    stats_ligas = {}


    for (
        league_id,
        config
    ) in LIGAS_1XBET.items():


        league_name = (
            config["nombre"]
        )

        league_slug = (
            config["slug"]
        )


        stats_ligas[
            league_name
        ] = {

            "partidos":
                0,

            "con_2up":
                0,

            "sin_2up":
                0,

            "errores":
                0,

        }


        league_result = (
            league_downloads.get(
                league_id
            )
        )


        if (
            not league_result
            or not league_result[
                "ok"
            ]
        ):

            print(
                f"❌ {league_name}: "
                "no se pudo descargar"
            )

            continue


        candidates = (
            build_candidates(

                league_id=
                    league_id,

                league_name=
                    league_name,

                league_slug=
                    league_slug,

                events=
                    league_result[
                        "events"
                    ],

                now=
                    now,

                window_end=
                    window_end,

            )
        )


        all_candidates.extend(
            candidates
        )


    print(
        f"⚡ Partidos a consultar "
        f"en detalle: "
        f"{len(all_candidates)}"
    )


    # ======================================================
    # 3. TODOS LOS DETALLES EN UN ÚNICO POOL
    # ======================================================

    all_rows = []


    workers = min(
        MAX_WORKERS_PARTIDOS,
        max(
            1,
            len(all_candidates),
        ),
    )


    if all_candidates:

        with ThreadPoolExecutor(
            max_workers=workers
        ) as executor:


            futures = [

                executor.submit(
                    fetch_game_detail,
                    candidate,
                )

                for candidate
                in all_candidates

            ]


            for future in as_completed(
                futures
            ):


                try:

                    result = (
                        future.result()
                    )


                except Exception:

                    continue


                candidate = result[
                    "candidate"
                ]


                league_name = (
                    candidate[
                        "league_name"
                    ]
                )


                parsed = (
                    procesar_resultado_detalle(
                        result
                    )
                )


                if parsed["error"]:

                    stats_ligas[
                        league_name
                    ][
                        "errores"
                    ] += 1


                row = parsed[
                    "row"
                ]


                if row is None:
                    continue


                all_rows.append(
                    row
                )


                stats_ligas[
                    league_name
                ][
                    "partidos"
                ] += 1


                if parsed[
                    "tiene_2up"
                ]:

                    stats_ligas[
                        league_name
                    ][
                        "con_2up"
                    ] += 1

                else:

                    stats_ligas[
                        league_name
                    ][
                        "sin_2up"
                    ] += 1


    # ======================================================
    # 4. ORDENAR
    # ======================================================

    all_rows.sort(

        key=lambda item: (

            item["Fecha"],
            item["Liga"],
            item["Partido"],

        )

    )


    # ======================================================
    # 5. GUARDAR
    # ======================================================

    save_json(
        OUT_PATH,
        all_rows,
    )


    # ======================================================
    # 6. RESUMEN
    # ======================================================

    for (
        league_name,
        info
    ) in stats_ligas.items():


        if (
            info["partidos"] == 0
            and info["errores"] == 0
        ):
            continue


        print(

            f"✅ {league_name}: "
            f"{info['partidos']} partidos | "
            f"2UP={info['con_2up']} | "
            f"Normal={info['sin_2up']} | "
            f"Errores={info['errores']}"

        )


    total_elapsed = (
        time.perf_counter()
        - total_started
    )


    total_2up = sum(

        info["con_2up"]

        for info
        in stats_ligas.values()

    )


    total_normal = sum(

        info["sin_2up"]

        for info
        in stats_ligas.values()

    )


    total_errores = sum(

        info["errores"]

        for info
        in stats_ligas.values()

    )


    print()
    print(
        "=" * 48
    )
    print(
        "RESUMEN 1XBET"
    )
    print(
        "=" * 48
    )

    print(
        f"Partidos: "
        f"{len(all_rows)}"
    )

    print(
        f"Con 2UP: "
        f"{total_2up}"
    )

    print(
        f"Sin 2UP: "
        f"{total_normal}"
    )

    print(
        f"Errores detalle: "
        f"{total_errores}"
    )

    print(
        f"Tiempo: "
        f"{total_elapsed:.2f}s"
    )

    print(
        f"Archivo: "
        f"{OUT_PATH}"
    )

    print(
        "=" * 48
    )


if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\n⚠️ Proceso detenido "
            "manualmente."
        )

    except Exception as error:

        print(
            "\n❌ Error inesperado: "
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise