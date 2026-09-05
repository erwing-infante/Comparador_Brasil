import requests
import time
import os
import re
import json
import unicodedata
import threading

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone


# ============================================================
# CONFIGURACIÓN
# ============================================================

OUT_DIR = "data"
os.makedirs(OUT_DIR, exist_ok=True)

ERROR_LOG = os.path.join(
    OUT_DIR,
    "error_log_atlanticcity.txt",
)

OUT_JSON = os.path.join(
    OUT_DIR,
    "cuotas_atlanticcity.json",
)


API_EVENTS = (
    "https://sb2frontend-altenar2.biahosted.com/"
    "api/Sportsbook/GetEvents"
)

API_DETAILS = (
    "https://sb2frontend-altenar2.biahosted.com/"
    "api/widget/GetEventDetails"
)


HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.atlanticcity.pe",
    "referer": "https://www.atlanticcity.pe/",
    "user-agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64)"
    ),
}


PARAMS_EVENTS = {
    "culture": "es-ES",
    "timezoneOffset": "300",
    "integration": "acity",
    "deviceType": "1",
    "numFormat": "en-GB",
    "countryCode": "PE",
    "sportids": "66",
}


# ============================================================
# VENTANA
# ============================================================

HORAS_ADELANTE = 72

NOW_UTC = datetime.now(timezone.utc)

CUTOFF_UTC = (
    NOW_UTC
    + timedelta(hours=HORAS_ADELANTE)
)


# ============================================================
# VELOCIDAD
# ============================================================

MAX_WORKERS_DETALLES = 12

TIMEOUT_EVENTOS = (6, 18)
TIMEOUT_DETALLE = (6, 18)

MAX_INTENTOS_EVENTOS = 3
MAX_INTENTOS_DETALLE = 2


# ============================================================
# LIGAS
# ============================================================

LIGAS_EQUIVALENCIAS = [
    ("Premier League", "Inglaterra", "Premier League"),
    # ("FA Cup", "Inglaterra", "FA Cup"),
    # ("EFL Cup", "Inglaterra", "EFL Cup"),

    ("Championship", "Inglaterra", "Championship"),

    ("LaLiga", "España", "La Liga"),
    ("Copa del Rey", "España", "Copa del Rey"),

    ("Serie A", "Italia", "Serie A"),
    ("Copa Italia", "Italia", "Copa Italia"),
    ("Supercopa", "Italia", "Supercopa de Italia"),

    ("Bundesliga", "Alemania", "Bundesliga"),
    ("DFB Pokal", "Alemania", "Copa Alemana"),
    ("Copa de Alemania", "Alemania", "Copa Alemana"),

    ("Ligue 1", "Francia", "Ligue 1"),
    ("Coupe de France", "Francia", "Copa Francia"),

    (
        "Brasileirao Serie A",
        "Brasil",
        "Brasileirao",
    ),
    ("Copa de Brasil", "Brasil", "Copa de Brasil"),

    ("Liga MX", "México", "Liga MX"),

    ("MLS", "Estados Unidos", "MLS"),

    ("Liga 1", "Perú", "Liga 1 Perú"),

    (
        "Primera División",
        "Portugal",
        "Primeira Liga",
    ),

    (
        "Eredivisie",
        "Países Bajos",
        "Eredivisie",
    ),

    (
        "Clasif. Mundial África",
        "Africa",
        "Eliminatorias Africa - WC26",
    ),

    (
        "Clasif. Mundial Asia",
        "Asia",
        "Eliminatorias Asia AFC - WC26",
    ),

    (
        "Clasif. Mundial CONCACAF",
        "Americas",
        "Eliminatorias CONCACAF - WC26",
    ),

    (
        "Clasif. Mundial UEFA",
        "Europa",
        "Eliminatorias Europa - WC26",
    ),

    (
        "Copa Libertadores",
        "Americas",
        "Copa Libertadores",
    ),

    (
        "Copa Sudamericana",
        "Americas",
        "Copa Sudamericana",
    ),

    (
        "UEFA Champions League",
        "Europa",
        "UEFA Champions League",
    ),

    (
        "UEFA Europa League",
        "Europa",
        "UEFA Europa League",
    ),

    (
        "UEFA Conference League",
        "Europa",
        "UEFA Conference League",
    ),

    (
        "Copa Mundial 2026",
        "Mundo",
        "Copa Mundial 2026",
    ),
]


NOMBRES_1X2 = {
    "1x2",
    "resultado final",
    "match result",
    "ft result",
    "ganador",
}


# ============================================================
# SESIONES HTTP PERSISTENTES POR HILO
# ============================================================

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
            pool_connections=16,
            pool_maxsize=16,
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


# ============================================================
# UTILIDADES
# ============================================================

def log_error(msg):

    try:
        with open(
            ERROR_LOG,
            "a",
            encoding="utf-8",
        ) as f:

            f.write(
                f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"{msg}\n"
            )

    except Exception:
        pass


def normalizar_nombre_equipo(s):

    if not s:
        return ""

    s = unicodedata.normalize(
        "NFKD",
        str(s),
    )

    s = (
        s.encode(
            "ascii",
            "ignore",
        )
        .decode("ascii")
    )

    s = s.lower()

    s = (
        s.replace("ß", "ss")
        .replace("œ", "oe")
        .replace("æ", "ae")
    )

    s = re.sub(
        r'[\"\'´`¨]',
        "",
        s,
    )

    s = re.sub(
        r"[\t\r\n]",
        " ",
        s,
    )

    s = re.sub(
        r"[^a-z0-9 ]",
        " ",
        s,
    )

    return re.sub(
        r"\s+",
        " ",
        s,
    ).strip()


def format_nombre_equipo_title(s):

    if not s:
        return ""

    base = normalizar_nombre_equipo(s)

    return " ".join(
        p.capitalize()
        for p in base.split()
        if p
    )


# ============================================================
# ÍNDICE DE LIGAS
# ============================================================

LIGAS_INDEX = {}


for champ_ref, cat_ref, canon in LIGAS_EQUIVALENCIAS:

    key = (
        normalizar_nombre_equipo(champ_ref),
        normalizar_nombre_equipo(cat_ref),
    )

    LIGAS_INDEX[key] = canon


def mapear_liga(champ, cat):

    key = (
        normalizar_nombre_equipo(champ),
        normalizar_nombre_equipo(cat),
    )

    return LIGAS_INDEX.get(key)


# ============================================================
# EXTRAER EVENTOS
# ============================================================

def extraer_eventos(nodos):

    eventos = []

    if not isinstance(nodos, list):
        return eventos

    stack = list(nodos)

    while stack:

        nodo = stack.pop()

        if not isinstance(nodo, dict):
            continue

        for evento in (
            nodo.get("Events", [])
            or []
        ):

            if (
                isinstance(evento, dict)
                and evento.get("SportId") == 66
            ):
                eventos.append(evento)

        items = (
            nodo.get("Items", [])
            or []
        )

        if isinstance(items, list):
            stack.extend(items)

    return eventos


# ============================================================
# FECHAS
# ============================================================

def parse_event_date_utc(fecha_raw):

    if not fecha_raw:
        return None

    texto = str(fecha_raw).strip()

    try:

        if texto.endswith("Z"):

            dt = datetime.fromisoformat(
                texto.replace(
                    "Z",
                    "+00:00",
                )
            )

        else:

            dt = datetime.fromisoformat(
                texto
            )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        )

    except Exception:

        return None


def format_fecha_output(dt):

    if not dt:
        return None

    dt = dt.astimezone(
        timezone.utc
    )

    return dt.strftime(
        "%Y-%m-%dT%H:%M:%S.000"
    )


# ============================================================
# DESCARGAR EVENTOS
# ============================================================

def obtener_eventos():

    session = get_session()

    last_error = ""

    for intento in range(
        1,
        MAX_INTENTOS_EVENTOS + 1,
    ):

        try:

            response = session.get(
                API_EVENTS,
                params=PARAMS_EVENTS,
                timeout=TIMEOUT_EVENTOS,
            )

            if response.status_code == 200:

                payload = response.json()

                return (
                    payload
                    .get("Result", {})
                    .get("Items", [])
                    or []
                )

            last_error = (
                f"HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

        except Exception as e:

            last_error = str(e)

        if intento < MAX_INTENTOS_EVENTOS:

            time.sleep(
                0.5 * intento
            )

    log_error(
        "GetEvents fallo definitivo: "
        f"{last_error}"
    )

    return []


# ============================================================
# MERCADOS
# ============================================================

def _market_name_norm(m):

    return normalizar_nombre_equipo(
        m.get("name", "")
        or ""
    )


def _is_supercuota_market(m):

    n = _market_name_norm(m)

    return (
        "supercuota" in n
        or "super cuota" in n
    )


def _extract_odd_ids(m):

    odd_ids = []

    for key in (
        "desktopOddIds",
        "oddIds",
    ):

        for item in (
            m.get(key, [])
            or []
        ):

            if (
                isinstance(item, list)
                and item
            ):

                try:
                    odd_ids.append(
                        int(item[0])
                    )
                except Exception:
                    pass

            elif isinstance(
                item,
                (int, str),
            ):

                try:
                    odd_ids.append(
                        int(item)
                    )
                except Exception:
                    pass

    return odd_ids


def _has_pa_signal(odds_map):

    for o in odds_map.values():

        if (
            o.get("IsDBB") is True
            or o.get("isDBB") is True
        ):
            return True

        offers = (
            o.get("offers")
            or []
        )

        if isinstance(
            offers,
            list,
        ):

            for off in offers:

                try:

                    if int(
                        off.get(
                            "parameter",
                            -1,
                        )
                    ) == 2:
                        return True

                except Exception:
                    pass

    return False


def _prices_from_odds_map(
    odds_map,
):

    out = {
        "Local": "",
        "Empate": "",
        "Visita": "",
    }

    for o in odds_map.values():

        tipo = o.get("typeId")

        price = o.get(
            "price",
            "",
        )

        if (
            price == ""
            or price is None
        ):
            continue

        try:
            price = float(price)

        except Exception:
            continue

        if tipo == 1:
            out["Local"] = price

        elif tipo == 2:
            out["Empate"] = price

        elif tipo == 3:
            out["Visita"] = price

    return out


# ============================================================
# OBTENER CUOTAS
# ============================================================

def obtener_cuotas(event_id):

    session = get_session()

    params = {
        "culture": "es-ES",
        "timezoneOffset": "300",
        "integration": "acity",
        "deviceType": "1",
        "numFormat": "en-GB",
        "countryCode": "PE",
        "eventId": str(event_id),
        "showNonBoosts": "false",
    }

    data = None

    for intento in range(
        1,
        MAX_INTENTOS_DETALLE + 1,
    ):

        try:

            response = session.get(
                API_DETAILS,
                params=params,
                timeout=TIMEOUT_DETALLE,
            )

            if response.status_code == 200:

                data = response.json()

                markets = (
                    data.get("markets", [])
                    or
                    data.get("Markets", [])
                )

                odds_all = (
                    data.get("odds", [])
                    or
                    data.get("Odds", [])
                )

                if markets and odds_all:
                    break

            else:

                log_error(
                    f"Detalle {event_id}: "
                    f"HTTP {response.status_code}"
                )

        except Exception as e:

            log_error(
                f"Detalle {event_id}: {e}"
            )

        if intento < MAX_INTENTOS_DETALLE:

            time.sleep(
                0.35 * intento
            )

    if not data:

        return {
            "LocalPA": "",
            "Empate": "",
            "VisitaPA": "",
            "LocalNoPA": None,
            "VisitaNoPA": None,
        }


    try:

        markets = (
            data.get("markets", [])
            or
            data.get("Markets", [])
        )

        odds_all = (
            data.get("odds", [])
            or
            data.get("Odds", [])
        )


        # ----------------------------------------------------
        # Crear mapa de odds una sola vez
        # ----------------------------------------------------

        odds_by_id = {
            o.get("id"): o
            for o in odds_all
            if isinstance(o, dict)
        }


        def odds_map_for_ids(ids):

            return {
                odd_id: odds_by_id[odd_id]
                for odd_id in ids
                if odd_id in odds_by_id
            }


        # ----------------------------------------------------
        # Buscar mercados 1X2
        # ----------------------------------------------------

        candidatos_1x2 = []

        for market in markets:

            nombre = _market_name_norm(
                market
            )

            if any(
                nombre_ref in nombre
                for nombre_ref in NOMBRES_1X2
            ):
                candidatos_1x2.append(
                    market
                )


        if not candidatos_1x2:

            return {
                "LocalPA": "",
                "Empate": "",
                "VisitaPA": "",
                "LocalNoPA": None,
                "VisitaNoPA": None,
            }


        supercuota_markets = [
            market
            for market in candidatos_1x2
            if _is_supercuota_market(
                market
            )
        ]


        normal_markets = [
            market
            for market in candidatos_1x2
            if not _is_supercuota_market(
                market
            )
        ]


        if not normal_markets:

            return {
                "LocalPA": "",
                "Empate": "",
                "VisitaPA": "",
                "LocalNoPA": None,
                "VisitaNoPA": None,
            }


        # ----------------------------------------------------
        # PA
        # ----------------------------------------------------

        base_market = None

        for market in normal_markets:

            ids = _extract_odd_ids(
                market
            )

            if not ids:
                continue

            odds_map = (
                odds_map_for_ids(ids)
            )

            if _has_pa_signal(
                odds_map
            ):

                base_market = market
                break


        if base_market is None:
            base_market = normal_markets[0]


        base_ids = _extract_odd_ids(
            base_market
        )

        base_odds_map = (
            odds_map_for_ids(
                base_ids
            )
        )

        base_prices = (
            _prices_from_odds_map(
                base_odds_map
            )
        )


        # ----------------------------------------------------
        # NoPA = Supercuota real
        # ----------------------------------------------------

        super_prices = None

        for market in supercuota_markets:

            ids = _extract_odd_ids(
                market
            )

            odds_map = (
                odds_map_for_ids(ids)
            )

            candidate = (
                _prices_from_odds_map(
                    odds_map
                )
            )

            if (
                candidate["Local"] != ""
                and candidate["Empate"] != ""
                and candidate["Visita"] != ""
            ):

                super_prices = candidate
                break


        # ----------------------------------------------------
        # EMPATE = MAYOR
        # ----------------------------------------------------

        base_draw = base_prices.get(
            "Empate",
            "",
        )

        super_draw = (
            super_prices.get(
                "Empate",
                "",
            )
            if super_prices
            else ""
        )


        if (
            base_draw != ""
            and super_draw != ""
        ):

            try:
                empate = max(
                    float(base_draw),
                    float(super_draw),
                )

            except Exception:
                empate = base_draw

        else:

            empate = (
                super_draw
                if base_draw == ""
                else base_draw
            )


        return {
            "LocalPA":
                base_prices.get(
                    "Local",
                    "",
                ),

            "Empate":
                empate,

            "VisitaPA":
                base_prices.get(
                    "Visita",
                    "",
                ),

            "LocalNoPA":
                (
                    super_prices.get(
                        "Local"
                    )
                    if super_prices
                    else None
                ),

            "VisitaNoPA":
                (
                    super_prices.get(
                        "Visita"
                    )
                    if super_prices
                    else None
                ),
        }


    except Exception as e:

        log_error(
            f"Procesando cuotas "
            f"{event_id}: {e}"
        )

        return {
            "LocalPA": "",
            "Empate": "",
            "VisitaPA": "",
            "LocalNoPA": None,
            "VisitaNoPA": None,
        }


# ============================================================
# PREPARAR EVENTOS ANTES DEL THREADPOOL
# ============================================================

def preparar_evento(ev):

    fecha_raw = ev.get(
        "EventDate",
        "",
    )

    dt_utc = parse_event_date_utc(
        fecha_raw
    )

    if dt_utc is None:
        return None

    if not (
        NOW_UTC
        < dt_utc
        <= CUTOFF_UTC
    ):
        return None


    champ_raw = ev.get(
        "ChampName",
        "",
    )

    cat_raw = ev.get(
        "CategoryName",
        "",
    )


    liga = mapear_liga(
        champ_raw,
        cat_raw,
    )

    if not liga:
        return None


    eid = ev.get("Id")

    if not eid:
        return None


    comps = (
        ev.get("Competitors")
        or []
    )

    if len(comps) < 2:
        return None


    local_raw = (
        comps[0].get("Name", "")
    )

    visita_raw = (
        comps[1].get("Name", "")
    )


    local = (
        format_nombre_equipo_title(
            local_raw
        )
    )

    visita = (
        format_nombre_equipo_title(
            visita_raw
        )
    )


    if not local or not visita:
        return None


    return {
        "event_id": eid,
        "liga": liga,
        "local": local,
        "visita": visita,
        "fecha_dt": dt_utc,
    }


# ============================================================
# PROCESAR EVENTO
# ============================================================

def procesar_evento(evento):

    try:

        cuotas = obtener_cuotas(
            evento["event_id"]
        )

        return {
            "Liga":
                evento["liga"],

            "Partido":
                (
                    f"{evento['local']} vs "
                    f"{evento['visita']}"
                ),

            "Fecha":
                format_fecha_output(
                    evento["fecha_dt"]
                ),

            "Casa":
                "Atlantic City",

            "Local":
                evento["local"],

            "Visita":
                evento["visita"],

            "Cuota Local":
                cuotas["LocalPA"],

            "Cuota Empate":
                cuotas["Empate"],

            "Cuota Visita":
                cuotas["VisitaPA"],

            "Cuota Local NoPA":
                cuotas["LocalNoPA"],

            "Cuota Visita NoPA":
                cuotas["VisitaNoPA"],

            "EventId":
                evento["event_id"],
        }

    except Exception as e:

        log_error(
            "Error procesando evento "
            f"{evento.get('event_id')}: "
            f"{e}"
        )

        return None


# ============================================================
# MAIN
# ============================================================

def main():

    started = time.perf_counter()

    print(
        "Consultando eventos "
        "en Atlantic City...\n"
    )


    # --------------------------------------------------------
    # DESCARGAR ÁRBOL
    # --------------------------------------------------------

    data = obtener_eventos()

    if not data:

        print(
            "❌ No se pudo descargar "
            "el listado de eventos."
        )

        return


    eventos = extraer_eventos(
        data
    )


    # --------------------------------------------------------
    # FILTRO DE TIEMPO
    # --------------------------------------------------------

    dentro_ventana = []

    for ev in eventos:

        dt = parse_event_date_utc(
            ev.get(
                "EventDate",
                "",
            )
        )

        if (
            dt is not None
            and NOW_UTC < dt <= CUTOFF_UTC
        ):
            dentro_ventana.append(
                ev
            )


    # --------------------------------------------------------
    # FILTRO DE LIGAS ANTES DE CREAR THREADS
    # --------------------------------------------------------

    candidatos = []

    seen = set()

    for ev in dentro_ventana:

        preparado = preparar_evento(
            ev
        )

        if preparado is None:
            continue

        event_id = preparado[
            "event_id"
        ]

        if event_id in seen:
            continue

        seen.add(event_id)

        candidatos.append(
            preparado
        )


    print(
        f"🔍 Total eventos detectados: "
        f"{len(eventos)}"
    )

    print(
        f"⏳ Eventos dentro de "
        f"{HORAS_ADELANTE}h: "
        f"{len(dentro_ventana)}"
    )

    print(
        f"🎯 Eventos de ligas objetivo: "
        f"{len(candidatos)}"
    )


    if not candidatos:

        print(
            "No se encontraron partidos "
            "de ligas objetivo."
        )

        return


    # --------------------------------------------------------
    # DETALLES EN PARALELO
    # --------------------------------------------------------

    registros = []

    workers = min(
        MAX_WORKERS_DETALLES,
        len(candidatos),
    )


    with ThreadPoolExecutor(
        max_workers=workers
    ) as executor:

        futures = [
            executor.submit(
                procesar_evento,
                evento,
            )
            for evento in candidatos
        ]


        for future in as_completed(
            futures
        ):

            try:

                result = future.result()

            except Exception as e:

                log_error(
                    f"Future detalle: {e}"
                )

                result = None


            if result:
                registros.append(
                    result
                )


    # --------------------------------------------------------
    # ORDENAR
    # --------------------------------------------------------

    registros.sort(
        key=lambda x: (
            x["Liga"],
            x["Fecha"],
            x["Partido"],
        )
    )


    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

    with open(
        OUT_JSON,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            registros,
            f,
            ensure_ascii=False,
            indent=2,
        )


    elapsed = (
        time.perf_counter()
        - started
    )


    print(
        f"✅ Archivo JSON generado: "
        f"{OUT_JSON}"
    )

    print(
        f"✅ Total partidos: "
        f"{len(registros)}"
    )

    print(
        f"⚡ Tiempo total: "
        f"{elapsed:.2f}s"
    )


if __name__ == "__main__":
    main()