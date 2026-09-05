import json
import os
import time
import threading

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


# ==========================================================
# CONFIG
# ==========================================================

TOURNAMENT_EVENTS_URL = (
    "https://api-latam.core-ix.com/api/v1/"
    "tournament-events"
)

EVENTS_URL = (
    "https://api-latam.core-ix.com/api/v1/events"
)

EVENT_DETAILS_URL = (
    "https://api-latam.core-ix.com/api/v1/"
    "event-details"
)


SPORT_ID = 1
LANG_EVENTS = "es"
TIME_RANGE = "all"

TZ_LOCAL = ZoneInfo("America/Lima")

DIAS_A_FUTURO = 3


# ==========================================================
# VELOCIDAD
# ==========================================================

# Divide las ligas normales en varios requests simultáneos.
MAX_WORKERS_GRUPOS = 4

# Detalles Mundial.
MAX_WORKERS_MUNDIAL = 8

TIMEOUT_LISTADO = (6, 25)
TIMEOUT_MUNDIAL = (6, 20)
TIMEOUT_DETALLE = (6, 20)


AUTH_TEAPUESTO = (
    "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9."
    "eyJpYXQiOjE3ODEyMTgwMDksImlzcyI6ImxhdGFtX2FwaSIs"
    "ImV4cCI6MTQ3Nzk4Njk5MCwidXNlcl9pZCI6MCwidXNlcl90"
    "eXBlIjowLCJtYWNoaW5lX2lkIjowLCJ1c2VyX3RpbWVvdXQi"
    "OjAsImlwIjoiMTkwLjIzNy4xMi4yMDQiLCJybmRfa2V5Ijow"
    "fQ.Zov-bnsXeQWC3vfC2BiilrLxuFt5jnUAgrwaZL9fZgM"
)


HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://www.teapuesto.pe",
    "Referer": "https://www.teapuesto.pe/",
}


HEADERS_POST = {
    **HEADERS,
    "Content-Type": "application/json",
}


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
    "cuotas_teapuesto.json",
)


# ==========================================================
# LIGAS
# ==========================================================

LIGAS_EQUIVALENCIAS = {

    "1105": "Premier League",

    # "1745": "EFL Cup",

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


MUNDIAL_ID = 1197
MUNDIAL_NAME = "Copa Mundial 2026"


# ==========================================================
# SESSION POR HILO
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

        session.headers.update(
            HEADERS
        )

        adapter = requests.adapters.HTTPAdapter(
            pool_connections=12,
            pool_maxsize=12,
            max_retries=0,
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

def to_iso_like_doradobet(dt):

    return dt.strftime(
        "%Y-%m-%dT%H:%M:%S.000"
    )


def parse_start_time(
    start_time_str,
):

    if not start_time_str:
        return None

    try:

        dt_naive = datetime.strptime(
            start_time_str,
            "%Y-%m-%d %H:%M:%S",
        )

        return dt_naive.replace(
            tzinfo=TZ_LOCAL
        )

    except Exception:
        return None


def parse_teams(
    event_name,
):

    if not event_name:
        return None, None

    for sep in (
        " - ",
        " vs. ",
        " vs ",
        " v ",
    ):

        if sep in event_name:

            a, b = event_name.split(
                sep,
                1,
            )

            return (
                a.strip(),
                b.strip(),
            )

    return None, None


# ==========================================================
# FILTROS LIVE
# ==========================================================

def has_live_flag(ev):

    live_keys = [
        "is_live",
        "isLive",
        "live",
        "Live",
        "in_live",
        "inLive",
        "inplay",
        "in_play",
        "is_inplay",
        "isInplay",
    ]

    for key in live_keys:

        value = ev.get(key)

        if value is True:
            return True

        if (
            isinstance(
                value,
                (int, float),
            )
            and value == 1
        ):
            return True

        if isinstance(
            value,
            str,
        ):

            if value.strip().lower() in (
                "1",
                "true",
                "yes",
                "live",
                "inplay",
                "in_play",
            ):
                return True

    return False


def has_live_status(ev):

    status_keys = [
        "status",
        "event_status",
        "eventStatus",
        "state",
        "phase",
        "match_status",
        "matchStatus",
    ]

    bad_words = [
        "live",
        "inplay",
        "in_play",
        "started",
        "inprogress",
        "in_progress",
        "running",
        "playing",
        "halftime",
        "half-time",
        "1st",
        "2nd",
        "first half",
        "second half",
        "closed",
        "settled",
        "finished",
        "ended",
        "resulted",
        "cancelled",
        "canceled",
        "suspended",
    ]

    for key in status_keys:

        value = str(
            ev.get(key)
            or ""
        ).strip().lower()

        if not value:
            continue

        if any(
            word in value
            for word in bad_words
        ):
            return True

    return False


def has_live_period_clock_score(ev):

    period_s = str(
        ev.get("period")
        or ev.get("current_period")
        or ev.get("period_name")
        or ""
    ).strip().lower()

    clock_s = str(
        ev.get("clock")
        or ev.get("timer")
        or ev.get("match_time")
        or ev.get("time")
        or ""
    ).strip()

    minute_s = str(
        ev.get("minute")
        or ev.get("matchMinute")
        or ""
    ).strip()

    score_v = (
        ev.get("score")
        or ev.get("scores")
        or ev.get("result")
    )


    if period_s not in (
        "",
        "0",
        "pre",
        "prematch",
        "pre-match",
        "notstarted",
        "not_started",
        "scheduled",
    ):
        return True


    if clock_s not in (
        "",
        "0",
        "00:00",
        "00:00:00",
    ):
        return True


    if minute_s not in (
        "",
        "0",
    ):
        return True


    if score_v not in (
        None,
        "",
        0,
        "0",
    ):

        score = str(
            score_v
        ).strip()

        if score not in (
            "0-0",
            "0:0",
            "0 - 0",
            "0 : 0",
        ):
            return True


    return False


def is_future_prematch(
    ev,
    now,
    window_end,
):

    dt = parse_start_time(
        ev.get("start_time")
    )

    if not dt:
        return False, None


    if not (
        now
        < dt
        <= window_end
    ):
        return False, dt


    if has_live_flag(ev):
        return False, dt


    if has_live_status(ev):
        return False, dt


    if has_live_period_clock_score(ev):
        return False, dt


    return True, dt


# ==========================================================
# DIVIDIR LIGAS
# ==========================================================

def dividir_lista(
    lista,
    cantidad_grupos,
):

    cantidad_grupos = min(
        cantidad_grupos,
        len(lista),
    )

    grupos = [
        []
        for _ in range(
            cantidad_grupos
        )
    ]

    for i, item in enumerate(
        lista
    ):

        grupos[
            i % cantidad_grupos
        ].append(item)

    return [
        grupo
        for grupo in grupos
        if grupo
    ]


# ==========================================================
# FETCH LIGAS NORMALES
# ==========================================================

def fetch_tournament_events(
    tournament_ids,
):

    session = get_session()

    params = [
        (
            "sport_id",
            SPORT_ID,
        ),
        (
            "lang",
            LANG_EVENTS,
        ),
        (
            "time_range",
            TIME_RANGE,
        ),
    ]


    for tid in tournament_ids:

        params.append(
            (
                "tournament_ids[]",
                tid,
            )
        )


    response = session.get(
        TOURNAMENT_EVENTS_URL,
        params=params,
        timeout=TIMEOUT_LISTADO,
    )

    response.raise_for_status()

    return response.json()


# ==========================================================
# EXTRAER PAYLOAD DE UN GRUPO
# ==========================================================

def extract_1x2_normal(
    payload,
    window_start,
    window_end,
):

    out = []

    status_por_liga = {}

    data = payload.get(
        "data",
        {},
    )

    tournaments = (
        data.get(
            "tournaments",
            {},
        )
        or {}
    )


    for (
        tid_str,
        liga_name
    ) in LIGAS_EQUIVALENCIAS.items():


        tinfo = tournaments.get(
            tid_str
        )


        # Esa liga puede pertenecer a otro
        # grupo de request.
        if not tinfo:
            continue


        events = (
            tinfo.get(
                "events",
                [],
            )
            or []
        )


        eventos_filtrados = []


        for ev in events:

            ok, dt = is_future_prematch(
                ev,
                window_start,
                window_end,
            )

            if ok:

                eventos_filtrados.append(
                    (
                        ev,
                        dt,
                    )
                )


        count_odds = 0


        for ev, dt in eventos_filtrados:

            ev_id = ev.get("id")

            ev_name = (
                ev.get("name")
                or ""
            )


            home, away = (
                parse_teams(
                    ev_name
                )
            )


            partido = (
                f"{home} vs {away}"
                if home and away
                else ev_name
            )


            market_1x2 = None


            for market in (
                ev.get(
                    "markets",
                    [],
                )
                or []
            ):

                if (
                    str(
                        market.get(
                            "name",
                            "",
                        )
                    )
                    .lower()
                    .strip()
                    == "1x2"
                ):

                    market_1x2 = market
                    break


            if not market_1x2:
                continue


            odds_items = None


            for market_odd in (
                market_1x2.get(
                    "market_odds",
                    [],
                )
                or []
            ):

                if market_odd.get(
                    "odds"
                ):

                    odds_items = (
                        market_odd[
                            "odds"
                        ]
                    )

                    break


            if not odds_items:
                continue


            cuota_local = None
            cuota_empate = None
            cuota_visita = None


            for odd in odds_items:

                provider_id = str(
                    odd.get(
                        "provider_odd_id",
                        "",
                    )
                ).strip()

                order = odd.get(
                    "order"
                )

                value = odd.get(
                    "value"
                )


                if value is None:
                    continue


                try:
                    value = float(value)

                except Exception:
                    continue


                if (
                    provider_id == "1"
                    or order == 1
                ):

                    cuota_local = value


                elif (
                    provider_id == "2"
                    or order == 2
                ):

                    cuota_empate = value


                elif (
                    provider_id == "3"
                    or order == 3
                ):

                    cuota_visita = value


            if (
                cuota_local is None
                or cuota_empate is None
                or cuota_visita is None
            ):
                continue


            count_odds += 1


            out.append({

                "Liga":
                    liga_name,

                "Partido":
                    partido,

                "Fecha":
                    to_iso_like_doradobet(
                        dt.replace(
                            tzinfo=None
                        )
                    ),

                "Casa":
                    "TeApuesto",

                "Local":
                    home,

                "Visita":
                    away,

                "Cuota Local":
                    None,

                "Cuota Empate":
                    cuota_empate,

                "Cuota Visita":
                    None,

                "Cuota Local NoPA":
                    cuota_local,

                "Cuota Visita NoPA":
                    cuota_visita,

                "EventId":
                    ev_id,
            })


        status_por_liga[
            tid_str
        ] = {

            "liga":
                liga_name,

            "eventos":
                len(
                    eventos_filtrados
                ),

            "odds":
                count_odds,
        }


    return (
        out,
        status_por_liga,
    )


# ==========================================================
# PROCESAR GRUPO
# ==========================================================

def procesar_grupo_ligas(
    ids,
    now,
    window_end,
):

    payload = fetch_tournament_events(
        ids
    )

    return extract_1x2_normal(
        payload,
        now,
        window_end,
    )


# ==========================================================
# MUNDIAL
# ==========================================================

def fetch_mundial_events():

    session = get_session()

    response = session.get(

        EVENTS_URL,

        params={
            "sport_id":
                SPORT_ID,

            "lang":
                LANG_EVENTS,

            "tournament_id":
                MUNDIAL_ID,
        },

        timeout=TIMEOUT_MUNDIAL,
    )


    response.raise_for_status()


    data = (
        response.json()
        .get(
            "data",
            [],
        )
    )


    if not isinstance(
        data,
        list,
    ):
        return []


    return data


def fetch_event_details(
    event_id,
):

    session = get_session()


    payload = {

        "event_id":
            str(event_id),

        "platform":
            "desktop",

        "language_id":
            3,

        "code":
            "es-ES",

        "language_code":
            "spa",

        "version":
            "v3",

        "site_code":
            "ta",

        "auth":
            AUTH_TEAPUESTO,
    }


    try:

        response = session.post(

            EVENT_DETAILS_URL,

            headers=HEADERS_POST,

            json=payload,

            timeout=TIMEOUT_DETALLE,
        )


        if response.status_code != 200:
            return None


        return response.json()


    except Exception:
        return None


def get_data_dict(
    payload,
):

    if not isinstance(
        payload,
        dict,
    ):
        return {}


    data = payload.get(
        "data",
        {},
    )


    if isinstance(
        data,
        dict,
    ):
        return data


    if isinstance(
        data,
        list,
    ):

        for item in data:

            if (
                isinstance(
                    item,
                    dict,
                )
                and (
                    "market_groups"
                    in item
                    or
                    "event"
                    in item
                )
            ):

                return item


    return {}


def extract_1x2_from_event_details(
    payload,
):

    data = get_data_dict(
        payload
    )


    market_groups = (
        data.get(
            "market_groups",
            [],
        )
        or []
    )


    for group in market_groups:

        group_name = str(
            group.get("name")
            or ""
        ).lower().strip()


        if (
            group_name
            != "apuestas principales"
        ):
            continue


        for market in (
            group.get(
                "markets",
                [],
            )
            or []
        ):

            market_name = str(
                market.get("name")
                or ""
            ).lower().strip()


            if market_name != "1x2":
                continue


            for mo in (
                market.get(
                    "market_odds",
                    [],
                )
                or []
            ):

                odds = (
                    mo.get(
                        "odds",
                        [],
                    )
                    or []
                )


                cuotas = {

                    "Local":
                        None,

                    "Empate":
                        None,

                    "Visita":
                        None,
                }


                for odd in odds:

                    order = odd.get(
                        "order"
                    )

                    value = odd.get(
                        "value"
                    )


                    if value is None:
                        continue


                    try:
                        value = float(value)

                    except Exception:
                        continue


                    if order == 1:
                        cuotas["Local"] = value

                    elif order == 2:
                        cuotas["Empate"] = value

                    elif order == 3:
                        cuotas["Visita"] = value


                if all(
                    value is not None
                    for value
                    in cuotas.values()
                ):
                    return cuotas


    return None


def get_teams_from_details(
    payload,
):

    data = get_data_dict(
        payload
    )


    ev = (
        data.get(
            "event",
            {},
        )
        or {}
    )


    competitors = (
        ev.get(
            "competitors",
            {},
        )
        or {}
    )


    home = None
    away = None


    if isinstance(
        competitors,
        dict,
    ):

        for competitor in (
            competitors.values()
        ):

            if not isinstance(
                competitor,
                dict,
            ):
                continue


            ctype = str(
                competitor.get(
                    "type"
                )
                or ""
            ).lower()


            if ctype == "home":

                home = competitor.get(
                    "name"
                )


            elif ctype == "away":

                away = competitor.get(
                    "name"
                )


    return home, away


def is_details_still_prematch(
    payload,
):

    data = get_data_dict(
        payload
    )


    ev = (
        data.get(
            "event",
            {},
        )
        or {}
    )


    if not ev:
        return True


    if has_live_flag(ev):
        return False


    if has_live_status(ev):
        return False


    if has_live_period_clock_score(ev):
        return False


    return True


def process_mundial_event(
    ev,
):

    event_id = ev.get("id")

    event_name = (
        ev.get("name")
        or ""
    )

    dt = parse_start_time(
        ev.get(
            "start_time"
        )
    )


    if (
        not event_id
        or not dt
    ):
        return None


    details = (
        fetch_event_details(
            event_id
        )
    )


    if not details:
        return None


    if not is_details_still_prematch(
        details
    ):
        return None


    cuotas = (
        extract_1x2_from_event_details(
            details
        )
    )


    if not cuotas:
        return None


    home, away = (
        get_teams_from_details(
            details
        )
    )


    if not home or not away:

        home, away = parse_teams(
            event_name
        )


    if not home or not away:
        return None


    return {

        "Liga":
            MUNDIAL_NAME,

        "Partido":
            f"{home} vs {away}",

        "Fecha":
            to_iso_like_doradobet(
                dt.replace(
                    tzinfo=None
                )
            ),

        "Casa":
            "TeApuesto",

        "Local":
            home,

        "Visita":
            away,

        "Cuota Local":
            None,

        "Cuota Empate":
            cuotas["Empate"],

        "Cuota Visita":
            None,

        "Cuota Local NoPA":
            cuotas["Local"],

        "Cuota Visita NoPA":
            cuotas["Visita"],

        "EventId":
            event_id,
    }


def extract_mundial_1x2(
    window_start,
    window_end,
):

    events = (
        fetch_mundial_events()
    )


    candidatos = []


    for ev in events:

        event_name = (
            ev.get("name")
            or ""
        )


        if not any(
            sep in event_name

            for sep in (
                " vs. ",
                " vs ",
                " - ",
                " v ",
            )
        ):
            continue


        ok, _ = is_future_prematch(

            ev,
            window_start,
            window_end,

        )


        if ok:
            candidatos.append(ev)


    rows = []


    if not candidatos:

        return rows, {

            "liga":
                MUNDIAL_NAME,

            "eventos":
                0,

            "odds":
                0,
        }


    print(
        f"🌎 Mundial: "
        f"{len(candidatos)} "
        "eventos prematch"
    )


    workers = min(
        MAX_WORKERS_MUNDIAL,
        len(candidatos),
    )


    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:


        futures = [

            executor.submit(
                process_mundial_event,
                ev,
            )

            for ev in candidatos
        ]


        for future in as_completed(
            futures
        ):

            try:
                row = future.result()

            except Exception:
                row = None


            if row:
                rows.append(row)


    rows.sort(
        key=lambda x: x["Fecha"]
    )


    return rows, {

        "liga":
            MUNDIAL_NAME,

        "eventos":
            len(candidatos),

        "odds":
            len(rows),
    }


# ==========================================================
# MAIN
# ==========================================================

def main():

    started = time.perf_counter()


    now = datetime.now(
        TZ_LOCAL
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
        "(Perú)"
    )

    print(
        "🔒 Filtro activo: "
        "SOLO PREMATCH / FUTUROS / NO LIVE"
    )


    all_rows = []
    status_total = {}


    tournament_ids = list(
        LIGAS_EQUIVALENCIAS.keys()
    )


    grupos = dividir_lista(

        tournament_ids,

        MAX_WORKERS_GRUPOS,

    )


    # ======================================================
    # LIGAS + MUNDIAL SIMULTÁNEAMENTE
    # ======================================================

    workers_total = (
        len(grupos)
        + 1
    )


    with ThreadPoolExecutor(
        max_workers=workers_total
    ) as executor:


        futures_grupos = [

            executor.submit(

                procesar_grupo_ligas,

                grupo,

                now,

                window_end,

            )

            for grupo in grupos
        ]


        future_mundial = executor.submit(

            extract_mundial_1x2,

            now,

            window_end,

        )


        for future in as_completed(
            futures_grupos
        ):

            try:

                rows, status = (
                    future.result()
                )

                all_rows.extend(
                    rows
                )

                status_total.update(
                    status
                )


            except Exception as e:

                print(
                    f"❌ Error grupo ligas: "
                    f"{e}"
                )


        try:

            (
                mundial_rows,
                mundial_status,
            ) = future_mundial.result()


            all_rows.extend(
                mundial_rows
            )


            status_total[
                str(MUNDIAL_ID)
            ] = mundial_status


        except Exception as e:

            print(
                f"❌ Error Mundial: "
                f"{e}"
            )


    # ======================================================
    # COMPLETAR STATUS DE LIGAS SIN EVENTOS
    # ======================================================

    for (
        tid,
        liga
    ) in LIGAS_EQUIVALENCIAS.items():


        if tid not in status_total:

            status_total[
                tid
            ] = {

                "liga":
                    liga,

                "eventos":
                    0,

                "odds":
                    0,
            }


    # ======================================================
    # DEDUPLICAR
    # ======================================================

    unique = {}

    for row in all_rows:

        key = (
            str(
                row.get(
                    "EventId"
                )
            ),
            row.get(
                "Liga"
            ),
        )

        unique[key] = row


    all_rows = list(
        unique.values()
    )


    all_rows.sort(
        key=lambda x: (
            x["Fecha"],
            x["Liga"],
            x["Partido"],
        )
    )


    # ======================================================
    # GUARDAR
    # ======================================================

    with open(
        OUT_PATH,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            all_rows,
            file,
            ensure_ascii=False,
            indent=2,
        )


    # ======================================================
    # RESUMEN
    # ======================================================

    for (
        tid,
        liga
    ) in LIGAS_EQUIVALENCIAS.items():


        info = status_total[
            tid
        ]


        evs = info[
            "eventos"
        ]

        odds = info[
            "odds"
        ]


        if evs == 0:

            print(
                f"❌ {liga}: "
                "0 eventos prematch"
            )


        elif odds == 0:

            print(
                f"⚠️ {liga}: "
                f"{evs} eventos prematch, "
                "0 odds 1x2"
            )


        else:

            print(
                f"✅ {liga}: "
                f"OK ({evs} eventos prematch, "
                f"{odds} con 1x2)"
            )


    mundial_info = status_total.get(
        str(MUNDIAL_ID),
        {
            "eventos": 0,
            "odds": 0,
        },
    )


    if mundial_info[
        "eventos"
    ] == 0:

        print(
            f"❌ {MUNDIAL_NAME}: "
            "0 eventos prematch"
        )

    else:

        print(
            f"✅ {MUNDIAL_NAME}: "
            f"{mundial_info['eventos']} eventos | "
            f"{mundial_info['odds']} con 1x2"
        )


    elapsed = (
        time.perf_counter()
        - started
    )


    print(
        f"\n💾 Total guardado: "
        f"{len(all_rows)} partidos "
        f"-> {OUT_PATH}"
    )


    print(
        f"⚡ Tiempo total: "
        f"{elapsed:.2f}s"
    )


if __name__ == "__main__":
    main()