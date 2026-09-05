import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import requests


# ==========================================================
# CONFIGURACIÓN
# ==========================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DEBUG_DIR = os.path.join(DATA_DIR, "debug_olimpobet")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(DEBUG_DIR, exist_ok=True)

OUTPUT_FILE = os.path.join(
    DATA_DIR,
    "cuotas_olimpobet.json",
)

BASE_LIST = (
    "https://us1.offering-api.kambicdn.com/"
    "offering/v2018/nexuspe/listView"
)

BASE_EVENT = (
    "https://us.offering-api.kambicdn.com/"
    "offering/v2018/nexuspe/prepackcoupon/event"
)

CASA = "Olimpobet"
HORAS_ADELANTE = 72

MAX_WORKERS_LIGAS = 8
MAX_WORKERS_EVENTOS = 8

TIMEOUT_LISTADO = 25
TIMEOUT_EVENTO = 25

MAX_INTENTOS_LISTADO = 3
MAX_INTENTOS_EVENTO = 3


# ==========================================================
# HEADERS
# ==========================================================
HEADERS = {
    "accept": (
        "application/json, text/javascript, "
        "*/*; q=0.01"
    ),
    "accept-language": (
        "es-US,es-PE;q=0.9,es-419;q=0.8,"
        "es;q=0.7,en;q=0.6"
    ),
    "cache-control": "no-cache",
    "origin": "https://www.olimpo.bet",
    "pragma": "no-cache",
    "priority": "u=1, i",
    "referer": "https://www.olimpo.bet/",
    "sec-ch-ua": (
        '"Not;A=Brand";v="8", '
        '"Chromium";v="150", '
        '"Google Chrome";v="150"'
    ),
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    ),
}


# ==========================================================
# LIGAS
# ==========================================================
LIGAS_OLIMPO = [
    (
        "Premier League",
        "football/england/premier_league",
        False,
    ),
    (
        "FA Cup",
        "football/england/fa_cup",
        False,
    ),
    (
        "EFL Cup",
        "football/england/efl_cup",
        False,
    ),

    (
        "La Liga",
        "football/spain/la_liga",
        False,
    ),
    (
        "Copa del Rey",
        "football/spain/copa_del_rey",
        False,
    ),

    (
        "Serie A",
        "football/italy/serie_a",
        False,
    ),

    (
        "Bundesliga",
        "football/germany/bundesliga",
        False,
    ),
    (
        "Copa Alemana",
        "football/germany/dfb_pokal",
        False,
    ),

    (
        "Ligue 1",
        "football/france/ligue_1",
        False,
    ),
    (
        "Copa Francia",
        "football/france/coupe_de_france",
        False,
    ),

    (
        "Brasileirao",
        "football/brazil/brasileirao_serie_a",
        False,
    ),
    (
        "Copa de Brasil",
        "football/brazil/copa_do_brasil",
        False,
    ),

    (
        "MLS",
        "football/usa/mls",
        False,
    ),
    (
        "Liga MX",
        "football/mexico/liga_mx",
        False,
    ),
    (
        "Liga 1 Perú",
        "football/peru/liga_1",
        False,
    ),
    (
        "Primeira Liga",
        "football/portugal/primeira_liga",
        False,
    ),

    (
        "UEFA Champions League",
        "football/champions_league",
        True,
    ),
    (
        "UEFA Europa League",
        "football/europa_league",
        True,
    ),
    (
        "UEFA Conference League",
        "football/conference_league",
        True,
    ),
    (
        "Copa Libertadores",
        "football/copa_libertadores",
        True,
    ),
    (
        "Copa Sudamericana",
        "football/copa_sudamericana",
        True,
    ),
    (
        "Eliminatorias Europa - WC26",
        "football/world_cup_qualifying_-_europe",
        True,
    ),
]


# ==========================================================
# UTILIDADES
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
            indent=2,
            ensure_ascii=False,
        )


def odds_to_float(value):
    if value is None:
        return None

    try:
        odds = float(value) / 1000

        if odds <= 1:
            return None

        return round(
            odds,
            3,
        )

    except (
        TypeError,
        ValueError,
    ):
        return None


def parse_fecha(start_iso):
    try:
        dt = datetime.fromisoformat(
            start_iso.replace(
                "Z",
                "+00:00",
            )
        )

        return dt.strftime(
            "%Y-%m-%dT%H:%M:%S.000"
        )

    except Exception:
        return start_iso


def fecha_to_dt_utc(start_iso):
    try:
        return datetime.fromisoformat(
            start_iso.replace(
                "Z",
                "+00:00",
            )
        ).astimezone(
            timezone.utc
        )

    except Exception:
        return None


def es_en_vivo(evt, event_info):
    state = str(
        event_info.get(
            "state",
            "",
        )
    ).upper()

    return (
        state
        in (
            "STARTED",
            "LIVE",
            "IN_PROGRESS",
        )
        or event_info.get("live") is True
        or event_info.get("inPlay") is True
        or evt.get("live") is True
    )


def get_outcome_side(outcome):
    label = str(
        outcome.get(
            "label",
            "",
        )
    ).strip().upper()

    english_label = str(
        outcome.get(
            "englishLabel",
            "",
        )
    ).strip().upper()

    outcome_label = str(
        outcome.get(
            "outcomeLabel",
            "",
        )
    ).strip().upper()

    outcome_type = str(
        outcome.get(
            "type",
            "",
        )
    ).strip().upper()

    if label in (
        "1",
        "X",
        "2",
    ):
        return label

    if english_label in (
        "1",
        "X",
        "2",
    ):
        return english_label

    if outcome_label in (
        "1",
        "X",
        "2",
    ):
        return outcome_label

    if outcome_type == "OT_ONE":
        return "1"

    if outcome_type == "OT_CROSS":
        return "X"

    if outcome_type == "OT_TWO":
        return "2"

    return None


def normalizar_nombre_mercado(value):
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("–", "-")
        .replace("—", "-")
    )


def evento_en_ventana(evt, now_utc, cutoff_utc):
    event_info = (
        evt.get(
            "event",
            {},
        )
        or {}
    )

    if not event_info:
        return False

    if es_en_vivo(
        evt,
        event_info,
    ):
        return False

    start = event_info.get(
        "start",
        "",
    )

    dt = fecha_to_dt_utc(
        start
    )

    if dt is None:
        return False

    return (
        now_utc
        < dt
        <= cutoff_utc
    )


# ==========================================================
# REQUEST DEL DETALLE DEL PARTIDO
# ==========================================================
def fetch_event_detail(event_id):
    url = (
        f"{BASE_EVENT}/"
        f"{event_id}.json"
    )

    ultimo_error = None

    for intento in range(
        1,
        MAX_INTENTOS_EVENTO + 1,
    ):
        params = {
            "lang": "es_PE",
            "market": "PE",
            "client_id": 200,
            "channel_id": 1,
            "ncid": int(
                time.time() * 1000
            ),
        }

        try:
            response = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=TIMEOUT_EVENTO,
            )

            if response.status_code == 200:
                return response.json()

            ultimo_error = (
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

        except (
            requests.RequestException,
            ValueError,
        ) as error:
            ultimo_error = str(
                error
            )

        if intento < MAX_INTENTOS_EVENTO:
            time.sleep(
                intento
            )

    print(
        f"   X Detalle {event_id}: "
        f"{ultimo_error}"
    )

    return None


# ==========================================================
# EXTRAER RESULTADO FINAL Y PAGO ANTICIPADO
# ==========================================================
def extraer_cuotas_desde_detail(
    detail,
    event_id=None,
):
    # Resultado Final normal
    cuota1_normal = None
    cuotaX_normal = None
    cuota2_normal = None

    # Resultado Final - Pago Anticipado
    cuota1_pago = None
    cuotaX_pago = None
    cuota2_pago = None

    betoffers = (
        detail.get(
            "betOffers",
            [],
        )
        or []
    )

    mercados_debug = []

    for betoffer in betoffers:
        criterion = (
            betoffer.get(
                "criterion",
                {},
            )
            or {}
        )

        mercado = str(
            criterion.get(
                "label",
                "",
            )
        ).strip()

        mercado_ingles = str(
            criterion.get(
                "englishLabel",
                "",
            )
        ).strip()

        mercado_normalizado = (
            normalizar_nombre_mercado(
                mercado
            )
        )

        mercado_ingles_normalizado = (
            normalizar_nombre_mercado(
                mercado_ingles
            )
        )

        mercados_debug.append({
            "label": mercado,
            "englishLabel": mercado_ingles,
            "criterionId": criterion.get(
                "id"
            ),
            "betOfferId": betoffer.get(
                "id"
            ),
        })

        outcomes = (
            betoffer.get(
                "outcomes",
                [],
            )
            or []
        )

        # ==================================================
        # RESULTADO FINAL NORMAL
        # ==================================================
        es_resultado_final_normal = (
            mercado_normalizado
            == "resultado final"
            or mercado_ingles_normalizado
            == "full time"
        )

        if es_resultado_final_normal:
            for outcome in outcomes:
                side = get_outcome_side(
                    outcome
                )

                odds = odds_to_float(
                    outcome.get(
                        "odds"
                    )
                )

                if odds is None:
                    continue

                if side == "1":
                    cuota1_normal = odds

                elif side == "X":
                    cuotaX_normal = odds

                elif side == "2":
                    cuota2_normal = odds

            continue

        # ==================================================
        # RESULTADO FINAL - PAGO ANTICIPADO
        # ==================================================
        es_pago_anticipado = (
            "pago anticipado"
            in mercado_normalizado
            or "2up"
            in mercado_ingles_normalizado
            or "2 up"
            in mercado_ingles_normalizado
        )

        if es_pago_anticipado:
            for outcome in outcomes:
                side = get_outcome_side(
                    outcome
                )

                odds = odds_to_float(
                    outcome.get(
                        "odds"
                    )
                )

                if odds is None:
                    continue

                if side == "1":
                    cuota1_pago = odds

                elif side == "X":
                    cuotaX_pago = odds

                elif side == "2":
                    cuota2_pago = odds

    # ======================================================
    # CUOTAS FINALES
    # ======================================================

    # Local y visita SOLO se toman del mercado Pago Anticipado.
    # Si no existe Pago Anticipado, quedan como None/null.
    cuota1_final = cuota1_pago
    cuota2_final = cuota2_pago

    # El empate toma la mayor cuota disponible.
    empates_disponibles = [
        cuota
        for cuota in (
            cuotaX_normal,
            cuotaX_pago,
        )
        if cuota is not None
    ]

    cuotaX_final = (
        max(
            empates_disponibles
        )
        if empates_disponibles
        else None
    )

    tiene_resultado_normal = (
        cuota1_normal is not None
        and cuotaX_normal is not None
        and cuota2_normal is not None
    )

    tiene_pago_anticipado = (
        cuota1_pago is not None
        and cuota2_pago is not None
    )

    # Debug por partido desactivado para mantener la ejecución limpia.

    return {
        # Cuotas finales
        "cuota1": cuota1_final,
        "cuotaX": cuotaX_final,
        "cuota2": cuota2_final,

        # Resultado Final normal
        "cuota1_normal": cuota1_normal,
        "cuotaX_normal": cuotaX_normal,
        "cuota2_normal": cuota2_normal,

        # Pago Anticipado
        "cuota1_pago": cuota1_pago,
        "cuotaX_pago": cuotaX_pago,
        "cuota2_pago": cuota2_pago,

        "tiene_resultado_normal": (
            tiene_resultado_normal
        ),
        "tiene_pago_anticipado": (
            tiene_pago_anticipado
        ),
    }


# ==========================================================
# PARSEAR EVENTO
# ==========================================================
def parse_event(
    evt,
    liga_nombre,
    now_utc,
    cutoff_utc,
):
    event_info = (
        evt.get(
            "event",
            {},
        )
        or {}
    )

    if not event_info:
        return None

    home = event_info.get(
        "homeName"
    )

    away = event_info.get(
        "awayName"
    )

    start = event_info.get(
        "start",
        "",
    )

    event_id = event_info.get(
        "id"
    )

    if (
        not home
        or not away
        or not start
        or not event_id
    ):
        return None

    if es_en_vivo(
        evt,
        event_info,
    ):
        return None

    dt = fecha_to_dt_utc(
        start
    )

    if (
        dt is None
        or not (
            now_utc
            < dt
            <= cutoff_utc
        )
    ):
        return None

    detail = fetch_event_detail(
        event_id
    )

    if not detail:
        return None

    cuotas = extraer_cuotas_desde_detail(
        detail,
        event_id,
    )

    # Solo exigimos que exista empate.
    # Local y visita pueden quedar como None/null
    # cuando el partido no tiene Pago Anticipado.
    if cuotas["cuotaX"] is None:
        print(
            f"   X Sin empate disponible: "
            f"{home} vs {away}"
        )

        return None

    return {
        "Liga": liga_nombre,
        "Partido": (
            f"{home} vs {away}"
        ),
        "Fecha": parse_fecha(
            start
        ),
        "Casa": CASA,
        "Local": home,
        "Visita": away,

        # Local y visita:
        # Pago Anticipado o null.
        #
        # Empate:
        # mayor entre Resultado Final y Pago Anticipado.
        "Cuota Local": cuotas[
            "cuota1"
        ],
        "Cuota Empate": cuotas[
            "cuotaX"
        ],
        "Cuota Visita": cuotas[
            "cuota2"
        ],

        # Cuotas normales sin Pago Anticipado.
        "Cuota Local NoPA": cuotas[
            "cuota1_normal"
        ],
        "Cuota Visita NoPA": cuotas[
            "cuota2_normal"
        ],

        "EventId": event_id,
    }


# ==========================================================
# DESCARGAR LISTADO DE UNA LIGA
# ==========================================================
def fetch_liga(
    nombre,
    path,
    internacional,
):
    if internacional:
        url = (
            f"{BASE_LIST}/{path}/"
            "all/all/matches.json"
        )

        params = {
            "client_id": 200,
            "channel_id": 1,
            "lang": "es_PE",
            "market": "PE",
            "useCombined": "true",
            "useCombinedLive": "true",
        }

    else:
        url = (
            f"{BASE_LIST}/{path}/"
            "all/matches.json"
        )

        params = {
            "client_id": 200,
            "channel_id": 1,
            "lang": "es_PE",
            "market": "PE",
        }

    ultimo_error = None

    for intento in range(
        1,
        MAX_INTENTOS_LISTADO + 1,
    ):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                params=params,
                timeout=TIMEOUT_LISTADO,
            )

            if response.status_code == 200:
                data = response.json()

                events = (
                    data.get(
                        "events",
                        [],
                    )
                    or []
                )

                return {
                    "ok": True,
                    "events": events,
                    "error": None,
                }

            ultimo_error = (
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

        except (
            requests.RequestException,
            ValueError,
        ) as error:
            ultimo_error = str(
                error
            )

        if intento < MAX_INTENTOS_LISTADO:
            time.sleep(
                intento
            )

    return {
        "ok": False,
        "events": [],
        "error": ultimo_error,
    }


# ==========================================================
# SCRAPEAR LIGA
# ==========================================================
def scrape_liga(
    nombre,
    path,
    internacional,
    now_utc,
    cutoff_utc,
):
    result = fetch_liga(
        nombre,
        path,
        internacional,
    )

    if not result["ok"]:
        print(
            f"X {nombre}: "
            f"{result['error']}"
        )

        return []

    events = result["events"]

    events_validos = [
        evt
        for evt in events
        if evento_en_ventana(
            evt,
            now_utc,
            cutoff_utc,
        )
    ]

    if not events_validos:
        return []

    parsed = []

    workers = min(
        MAX_WORKERS_EVENTOS,
        len(events_validos),
    )

    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:
        futures = [
            executor.submit(
                parse_event,
                evt,
                nombre,
                now_utc,
                cutoff_utc,
            )
            for evt in events_validos
        ]

        for future in as_completed(
            futures
        ):
            try:
                item = future.result()

                if item:
                    parsed.append(
                        item
                    )

            except Exception as error:
                print(
                    f"   X Error evento "
                    f"{nombre}: {error}"
                )

    return parsed


# ==========================================================
# MAIN
# ==========================================================
def main():
    started = time.perf_counter()

    now_utc = datetime.now(
        timezone.utc
    )

    cutoff_utc = (
        now_utc
        + timedelta(
            hours=HORAS_ADELANTE
        )
    )

    print("\nOlimpoBet: descargando cuotas...")

    resultados = []

    with ThreadPoolExecutor(
        max_workers=MAX_WORKERS_LIGAS
    ) as executor:
        futures = [
            executor.submit(
                scrape_liga,
                nombre,
                path,
                internacional,
                now_utc,
                cutoff_utc,
            )
            for (
                nombre,
                path,
                internacional,
            ) in LIGAS_OLIMPO
        ]

        for future in as_completed(
            futures
        ):
            try:
                resultados.extend(
                    future.result()
                )

            except Exception as error:
                print(
                    f"X Error en hilo de liga: "
                    f"{error}"
                )

    # Eliminar duplicados por EventId.
    unicos = {}

    for item in resultados:
        event_id = item.get(
            "EventId"
        )

        if event_id is None:
            key = (
                item.get("Liga"),
                item.get("Partido"),
                item.get("Fecha"),
            )

        else:
            key = str(
                event_id
            )

        unicos[key] = item

    resultados = list(
        unicos.values()
    )

    resultados.sort(
        key=lambda item: (
            item.get(
                "Fecha",
                "",
            ),
            item.get(
                "Liga",
                "",
            ),
            item.get(
                "Partido",
                "",
            ),
        )
    )

    save_json(
        OUTPUT_FILE,
        resultados,
    )

    elapsed = (
        time.perf_counter()
        - started
    )

    con_pago = sum(
        1
        for item in resultados
        if (
            item.get("Cuota Local")
            is not None
            and item.get("Cuota Visita")
            is not None
        )
    )

    sin_pago = (
        len(resultados)
        - con_pago
    )

    print(
        f"OlimpoBet OK: {len(resultados)} partidos | "
        f"PA: {con_pago} | NoPA: {sin_pago} | "
        f"{elapsed:.2f}s"
    )


if __name__ == "__main__":
    main()