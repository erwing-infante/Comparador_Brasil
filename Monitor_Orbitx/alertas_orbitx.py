import os
import json
import time
from datetime import datetime
from collections import defaultdict, deque

import requests


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

BASE_DIR = "/root/proyectos/Mancorabet/Monitor_Orbitx"
DATA_DIR = os.path.join(BASE_DIR, "data")

SNAPSHOT_FILE = os.path.join(
    DATA_DIR,
    "snapshot.json"
)

STATE_FILE = os.path.join(
    DATA_DIR,
    "estado_alertas_orbitx.json"
)

LOG_FILE = os.path.join(
    DATA_DIR,
    "predicciones_orbitx.jsonl"
)


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_TOKEN = (
    os.getenv("ORBITX_ALERT_BOT_TOKEN")
    or os.getenv("PREMATCH_BOT_TOKEN")
    or os.getenv("SMART_BOT_TOKEN")
)

TELEGRAM_CHAT_ID = (
    os.getenv("ORBITX_ALERT_CHAT_ID")
    or os.getenv("PREMATCH_BOT_CHAT_ID")
    or os.getenv("SMART_BOT_CHAT_ID_1")
)


# ============================================================
# TIEMPOS
# ============================================================

CHECK_EVERY_SEC = 5

# Historia mantenida en memoria
HISTORY_SECONDS = 600

WINDOW_30 = 30
WINDOW_60 = 60
WINDOW_120 = 120
WINDOW_180 = 180

# Predicción válida durante 3 minutos
PREDICTION_HORIZON_SEC = 180

# Evitar predicciones repetidas
PREDICTION_COOLDOWN_SEC = 300

# Alerta de 90 minutos
ALERT_90_MIN = 90
ALERT_90_WINDOW = 3


# ============================================================
# MOVIMIENTO CONFIRMADO
# ============================================================

DROP_ALERT_PCT = 2.0

DROP_LEVELS = [
    2.0,
    4.0,
    6.0
]

# Máximo reciente usado como referencia
DROP_REFERENCE_WINDOW_SEC = 300

# Rebote desde el mínimo para considerar reversión
REVERSAL_FROM_LOW_PCT = 1.5

# Cuando vuelve prácticamente a la referencia,
# permitimos un nuevo ciclo
RESET_DROP_PCT = 0.75


# ============================================================
# PREDICTOR
# ============================================================

TARGET_SELECTIONS = [
    "HOME",
    "AWAY"
]

PREDICTION_SCORE_MIN = 6.0

MIN_HISTORY_SEC = 120

MIN_MARKET_VOLUME = 300.0


# ============================================================
# MEMORIA
# ============================================================

history = defaultdict(
    lambda: defaultdict(deque)
)


# ============================================================
# JSON
# ============================================================

def cargar_json(path, default=None):

    if default is None:
        default = {}

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except FileNotFoundError:

        return default

    except Exception as e:

        print(
            f"[ERROR JSON] {path}: {e}"
        )

        return default


def guardar_json(path, data):

    try:

        os.makedirs(
            os.path.dirname(path),
            exist_ok=True
        )

        tmp = path + ".tmp"

        with open(
            tmp,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

        os.replace(
            tmp,
            path
        )

    except Exception as e:

        print(
            f"[ERROR GUARDAR] {e}"
        )


def log_json(data):

    try:

        os.makedirs(
            os.path.dirname(LOG_FILE),
            exist_ok=True
        )

        with open(
            LOG_FILE,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                json.dumps(
                    data,
                    ensure_ascii=False
                )
                + "\n"
            )

    except Exception as e:

        print(
            f"[ERROR LOG] {e}"
        )


# ============================================================
# ESTADO
# ============================================================

def cargar_estado():

    estado = cargar_json(
        STATE_FILE,
        {}
    )

    estado.setdefault(
        "alerta_90",
        {}
    )

    estado.setdefault(
        "predicciones",
        {}
    )

    estado.setdefault(
        "movimientos",
        {}
    )

    estado.setdefault(
        "ultimo_predict",
        {}
    )

    return estado


# ============================================================
# TELEGRAM
# ============================================================

def telegram_configurado():

    return bool(
        TELEGRAM_TOKEN
        and TELEGRAM_CHAT_ID
    )


def enviar_telegram(mensaje):

    if not telegram_configurado():

        print()
        print(
            "========== TELEGRAM =========="
        )

        print(
            mensaje
            .replace("<b>", "")
            .replace("</b>", "")
        )

        print(
            "=============================="
        )
        print()

        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:

        r = requests.post(
            url,
            data=payload,
            timeout=15
        )

        if r.status_code == 200:
            return True

        print(
            f"[TELEGRAM ERROR] "
            f"{r.status_code}: "
            f"{r.text[:300]}"
        )

    except Exception as e:

        print(
            f"[TELEGRAM ERROR] {e}"
        )

    return False


# ============================================================
# FORMATOS
# ============================================================

def fmt_odds(x):

    if x is None:
        return "-"

    try:
        return f"{float(x):.2f}"

    except Exception:
        return str(x)


def fmt_money(x):

    if x is None:
        return "-"

    try:
        return f"{float(x):,.2f}"

    except Exception:
        return str(x)


def selection_nombre(selection):

    if selection == "HOME":
        return "LOCAL"

    if selection == "AWAY":
        return "VISITA"

    return "EMPATE"


def selection_corta(selection):

    if selection == "HOME":
        return "L"

    if selection == "AWAY":
        return "V"

    return "X"


# ============================================================
# TIEMPO
# ============================================================

def now_ts():

    return time.time()


def now_iso():

    return (
        datetime.now()
        .astimezone()
        .isoformat()
    )


def parse_start_pe(valor):

    if not valor:
        return None

    try:
        return datetime.fromisoformat(valor)

    except Exception:
        return None


# ============================================================
# RUNNERS
# ============================================================

def obtener_runner(
    partido,
    selection
):

    runners = partido.get(
        "runners",
        {}
    )

    for runner_id, runner in runners.items():

        if (
            runner.get("selection")
            == selection
        ):

            return {

                "runner_id":
                    str(runner_id),

                "selection":
                    selection,

                "back":
                    runner.get(
                        "best_back_odds"
                    ),

                "back_amt":
                    runner.get(
                        "best_back_amt"
                    ),

                "lay":
                    runner.get(
                        "best_lay_odds"
                    ),

                "lay_amt":
                    runner.get(
                        "best_lay_amt"
                    ),

                "spread":
                    runner.get(
                        "spread"
                    ),

                "sum_back_top3":
                    runner.get(
                        "sum_back_top3"
                    ),

                "sum_lay_top3":
                    runner.get(
                        "sum_lay_top3"
                    ),

                "blpr":
                    runner.get(
                        "blpr"
                    ),

                "tv_runner":
                    runner.get(
                        "tv_runner"
                    ),

                "locked":
                    runner.get(
                        "locked",
                        False
                    )
            }

    return None


# ============================================================
# MATEMÁTICAS
# ============================================================

def pct_change(
    old,
    new
):

    try:

        old = float(old)
        new = float(new)

        if old <= 0:
            return 0.0

        return (
            (new / old) - 1.0
        ) * 100.0

    except Exception:

        return 0.0


def drop_pct(
    reference,
    current
):

    try:

        reference = float(reference)
        current = float(current)

        if reference <= 0:
            return 0.0

        return (
            (reference - current)
            / reference
        ) * 100.0

    except Exception:

        return 0.0


# ============================================================
# HISTORIAL
# ============================================================

def limpiar_deque(
    q,
    ahora
):

    limite = (
        ahora
        - HISTORY_SECONDS
    )

    while (
        q
        and q[0]["ts"] < limite
    ):
        q.popleft()


def agregar_historia(
    market_id,
    partido,
    selection,
    runner
):

    if not runner:
        return

    back = runner.get(
        "back"
    )

    if back is None:
        return

    ahora = now_ts()

    punto = {

        "ts":
            ahora,

        "back":
            runner.get("back"),

        "lay":
            runner.get("lay"),

        "back_amt":
            runner.get("back_amt"),

        "lay_amt":
            runner.get("lay_amt"),

        "spread":
            runner.get("spread"),

        "sum_back_top3":
            runner.get(
                "sum_back_top3"
            ),

        "sum_lay_top3":
            runner.get(
                "sum_lay_top3"
            ),

        "blpr":
            runner.get("blpr"),

        "tv_runner":
            runner.get("tv_runner"),

        "tv_market":
            partido.get("tv_market")
    }

    q = history[
        market_id
    ][selection]

    # Evitar duplicados prácticamente iguales
    if q:

        last = q[-1]

        if (
            ahora - last["ts"] < 2
            and last["back"]
            == punto["back"]
            and last["tv_market"]
            == punto["tv_market"]
            and last["back_amt"]
            == punto["back_amt"]
            and last["lay_amt"]
            == punto["lay_amt"]
        ):

            return

    q.append(
        punto
    )

    limpiar_deque(
        q,
        ahora
    )


def punto_hace(
    market_id,
    selection,
    segundos
):

    q = (
        history
        .get(
            market_id,
            {}
        )
        .get(
            selection
        )
    )

    if not q:
        return None

    objetivo = (
        now_ts()
        - segundos
    )

    mejor = None

    for p in q:

        if p["ts"] <= objetivo:
            mejor = p

        else:
            break

    return mejor


def primer_punto(
    market_id,
    selection
):

    q = (
        history
        .get(
            market_id,
            {}
        )
        .get(
            selection
        )
    )

    if not q:
        return None

    return q[0]


def ultimo_punto(
    market_id,
    selection
):

    q = (
        history
        .get(
            market_id,
            {}
        )
        .get(
            selection
        )
    )

    if not q:
        return None

    return q[-1]


def historia_suficiente(
    market_id,
    selection
):

    primero = primer_punto(
        market_id,
        selection
    )

    ultimo = ultimo_punto(
        market_id,
        selection
    )

    if not primero or not ultimo:
        return False

    return (
        ultimo["ts"]
        - primero["ts"]
    ) >= MIN_HISTORY_SEC


# ============================================================
# MÁXIMO RECIENTE
# ============================================================

def max_back_reciente(
    market_id,
    selection,
    segundos
):

    q = (
        history
        .get(
            market_id,
            {}
        )
        .get(
            selection
        )
    )

    if not q:
        return None

    limite = (
        now_ts()
        - segundos
    )

    valores = [
        float(p["back"])
        for p in q

        if (
            p["ts"] >= limite
            and p.get("back")
            is not None
        )
    ]

    if not valores:
        return None

    return max(
        valores
    )


# ============================================================
# PREDICTOR
# ============================================================

def calcular_score(
    market_id,
    partido,
    target
):

    actual = ultimo_punto(
        market_id,
        target
    )

    if not actual:
        return 0.0, []

    if not historia_suficiente(
        market_id,
        target
    ):
        return 0.0, []

    actual_back = actual.get(
        "back"
    )

    if actual_back is None:
        return 0.0, []

    tv_market = (
        actual.get(
            "tv_market"
        )
        or 0
    )

    if (
        tv_market
        < MIN_MARKET_VOLUME
    ):

        return 0.0, []

    p30 = punto_hace(
        market_id,
        target,
        WINDOW_30
    )

    p60 = punto_hace(
        market_id,
        target,
        WINDOW_60
    )

    p120 = punto_hace(
        market_id,
        target,
        WINDOW_120
    )

    p180 = punto_hace(
        market_id,
        target,
        WINDOW_180
    )

    if not p60 or not p120:
        return 0.0, []

    score = 0.0
    razones = []


    # ========================================================
    # 1. PRECIO PROPIO
    # ========================================================

    d30 = (
        pct_change(
            p30["back"],
            actual_back
        )
        if p30
        else 0.0
    )

    d60 = pct_change(
        p60["back"],
        actual_back
    )

    d120 = pct_change(
        p120["back"],
        actual_back
    )

    if (
        -1.20
        <= d60
        <= -0.25
    ):

        score += 1.5

        razones.append(
            "precio presionando"
        )

    elif d60 < -1.20:

        # Ya está demasiado avanzado
        score -= 1.5

    if (
        d30 < -0.15
        and d60 < -0.20
    ):

        score += 0.75


    # ========================================================
    # 2. CONFIRMACIÓN CRUZADA
    # ========================================================

    opposite = (
        "AWAY"
        if target == "HOME"
        else "HOME"
    )

    opp_now = ultimo_punto(
        market_id,
        opposite
    )

    opp_60 = punto_hace(
        market_id,
        opposite,
        WINDOW_60
    )

    opp_120 = punto_hace(
        market_id,
        opposite,
        WINDOW_120
    )

    if (
        opp_now
        and opp_60
    ):

        opp_d60 = pct_change(
            opp_60["back"],
            opp_now["back"]
        )

        if opp_d60 >= 0.50:

            score += 2.0

            razones.append(
                f"{selection_corta(opposite)} subiendo"
            )

        elif opp_d60 >= 0.25:

            score += 1.0

    if (
        opp_now
        and opp_120
    ):

        opp_d120 = pct_change(
            opp_120["back"],
            opp_now["back"]
        )

        if opp_d120 >= 0.80:

            score += 0.75


    # ========================================================
    # 3. EMPATE COMO CONTEXTO
    # ========================================================

    draw_now = ultimo_punto(
        market_id,
        "DRAW"
    )

    draw_60 = punto_hace(
        market_id,
        "DRAW",
        WINDOW_60
    )

    if (
        draw_now
        and draw_60
    ):

        draw_d60 = abs(
            pct_change(
                draw_60["back"],
                draw_now["back"]
            )
        )

        if draw_d60 <= 0.75:

            score += 0.25


    # ========================================================
    # 4. VOLUMEN TOTAL
    # ========================================================

    tv_now = actual.get(
        "tv_market"
    )

    tv_60 = p60.get(
        "tv_market"
    )

    tv_120 = p120.get(
        "tv_market"
    )

    if (
        tv_now is not None
        and tv_60 is not None
    ):

        inc60 = (
            float(tv_now)
            - float(tv_60)
        )

        if inc60 > 0:

            rel60 = (
                inc60
                / max(
                    float(tv_60),
                    1.0
                )
            ) * 100

            if rel60 >= 5:

                score += 1.5

                razones.append(
                    "volumen acelerando"
                )

            elif rel60 >= 2:

                score += 1.0

            elif rel60 >= 0.5:

                score += 0.5


    # ========================================================
    # 5. ACELERACIÓN DE VOLUMEN
    # ========================================================

    if (
        tv_now is not None
        and tv_60 is not None
        and tv_120 is not None
    ):

        ultimo_tramo = (
            float(tv_now)
            - float(tv_60)
        )

        tramo_anterior = (
            float(tv_60)
            - float(tv_120)
        )

        if (
            ultimo_tramo > 0
            and tramo_anterior >= 0
            and ultimo_tramo
            > max(
                tramo_anterior * 1.8,
                tramo_anterior + 100
            )
        ):

            score += 1.0

            razones.append(
                "aceleración volumen"
            )


    # ========================================================
    # 6. BEST BACK AMOUNT
    # ========================================================

    back_amt_now = actual.get(
        "back_amt"
    )

    back_amt_60 = p60.get(
        "back_amt"
    )

    if (
        back_amt_now is not None
        and back_amt_60 is not None
        and float(back_amt_60) > 0
    ):

        cambio = pct_change(
            back_amt_60,
            back_amt_now
        )

        if cambio >= 100:

            score += 1.25

            razones.append(
                "liquidez back fuerte"
            )

        elif cambio >= 40:

            score += 0.75


    # ========================================================
    # 7. BEST LAY AMOUNT
    # ========================================================

    lay_amt_now = actual.get(
        "lay_amt"
    )

    lay_amt_60 = p60.get(
        "lay_amt"
    )

    if (
        lay_amt_now is not None
        and lay_amt_60 is not None
        and float(lay_amt_60) > 0
    ):

        cambio = pct_change(
            lay_amt_60,
            lay_amt_now
        )

        if cambio <= -50:

            score += 0.75

            razones.append(
                "lay debilitándose"
            )

        elif cambio <= -25:

            score += 0.35


    # ========================================================
    # 8. TOP 3 BACK
    # ========================================================

    top_back_now = actual.get(
        "sum_back_top3"
    )

    top_back_60 = p60.get(
        "sum_back_top3"
    )

    if (
        top_back_now is not None
        and top_back_60 is not None
        and float(top_back_60) > 0
    ):

        cambio = pct_change(
            top_back_60,
            top_back_now
        )

        if cambio >= 50:

            score += 0.5


    # ========================================================
    # 9. SPREAD
    # ========================================================

    spread = actual.get(
        "spread"
    )

    if spread is not None:

        try:

            spread = float(
                spread
            )

            if spread <= 0.03:

                score += 0.5

            elif spread <= 0.06:

                score += 0.25

            elif spread >= 0.15:

                score -= 0.75

        except Exception:

            pass


    # ========================================================
    # 10. EVITAR SERRUCHO
    # ========================================================

    if p30 and p60:

        d1 = pct_change(
            p60["back"],
            p30["back"]
        )

        d2 = pct_change(
            p30["back"],
            actual_back
        )

        if (
            (
                d1 < -0.3
                and d2 > 0.3
            )
            or
            (
                d1 > 0.3
                and d2 < -0.3
            )
        ):

            score -= 1.5


    return (
        round(
            score,
            2
        ),
        razones
    )


# ============================================================
# MENSAJE PREDICCIÓN
# ============================================================

def mensaje_prediccion(
    partido,
    selection,
    score
):

    home = obtener_runner(
        partido,
        "HOME"
    )

    draw = obtener_runner(
        partido,
        "DRAW"
    )

    away = obtener_runner(
        partido,
        "AWAY"
    )

    event_name = partido.get(
        "eventName",
        "-"
    )

    liga = partido.get(
        "liga",
        "-"
    )

    return (
        "🚨 <b>PREDICCIÓN ORBITX</b>\n\n"

        f"🏆 {liga}\n"

        f"⚽ <b>{event_name}</b>\n\n"

        f"📉 Posible caída: "
        f"<b>{selection_nombre(selection)}</b>\n\n"

        f"L: "
        f"{fmt_odds(home['back'] if home else None)}\n"

        f"X: "
        f"{fmt_odds(draw['back'] if draw else None)}\n"

        f"V: "
        f"{fmt_odds(away['back'] if away else None)}\n\n"

        f"📊 Presión: <b>ALTA</b>\n"

        f"⏱ Horizonte: 1–3 min"
    )


# ============================================================
# CREAR PREDICCIÓN
# ============================================================

def revisar_prediccion(
    estado,
    partido,
    market_id,
    selection
):

    runner = obtener_runner(
        partido,
        selection
    )

    if not runner:
        return

    cuota = runner.get(
        "back"
    )

    if cuota is None:
        return

    cuota = float(
        cuota
    )

    key = (
        f"{market_id}:"
        f"{selection}"
    )


    # ========================================================
    # CORRECCIÓN IMPORTANTE
    #
    # Si el movimiento real ya cayó 2% o más,
    # NO crear una predicción.
    #
    # Ejemplo:
    # 2.12 -> 2.06
    #
    # Ya ocurrió el movimiento.
    # ========================================================

    referencia_reciente = (
        max_back_reciente(
            market_id,
            selection,
            DROP_REFERENCE_WINDOW_SEC
        )
    )

    if referencia_reciente is not None:

        caida_ya_ocurrida = drop_pct(
            referencia_reciente,
            cuota
        )

        if (
            caida_ya_ocurrida
            >= DROP_ALERT_PCT
        ):

            return


    # ========================================================
    # TAMPOCO PREDECIR SI YA EXISTE
    # UN MOVIMIENTO ACTIVO DE ESA SELECCIÓN
    # ========================================================

    movimiento_actual = (
        estado["movimientos"]
        .get(key)
    )

    if movimiento_actual:

        if (
            movimiento_actual.get(
                "activo",
                False
            )
            or
            movimiento_actual.get(
                "max_nivel_enviado",
                0
            ) >= DROP_ALERT_PCT
        ):

            return


    # ========================================================
    # SCORE
    # ========================================================

    score, razones = calcular_score(
        market_id,
        partido,
        selection
    )

    if (
        score
        < PREDICTION_SCORE_MIN
    ):

        return


    # ========================================================
    # COOLDOWN
    # ========================================================

    ahora = now_ts()

    ultima = (
        estado["ultimo_predict"]
        .get(key)
    )

    if ultima:

        try:

            if (
                ahora
                - float(ultima)
                < PREDICTION_COOLDOWN_SEC
            ):

                return

        except Exception:

            pass


    # Ya existe una predicción pendiente
    if (
        key
        in estado["predicciones"]
    ):

        return


    mensaje = mensaje_prediccion(
        partido,
        selection,
        score
    )

    if not enviar_telegram(
        mensaje
    ):

        return


    pred = {

        "market_id":
            market_id,

        "event_id":
            str(
                partido.get(
                    "eventId"
                )
            ),

        "event_name":
            partido.get(
                "eventName"
            ),

        "liga":
            partido.get(
                "liga"
            ),

        "selection":
            selection,

        # ESTA ES LA ÚNICA CUOTA
        # DESDE LA CUAL PUEDE CONFIRMARSE
        # ESTA PREDICCIÓN.
        "cuota_inicial":
            cuota,

        "score":
            score,

        "razones":
            razones,

        "ts":
            ahora,

        "expires":
            (
                ahora
                + PREDICTION_HORIZON_SEC
            )
    }

    estado["predicciones"][
        key
    ] = pred

    estado["ultimo_predict"][
        key
    ] = ahora

    log_json({

        "tipo":
            "PREDICCION",

        "timestamp":
            now_iso(),

        **pred
    })

    print(
        f"[PREDICCION] "
        f"{partido.get('eventName')} "
        f"{selection} "
        f"{cuota} "
        f"score={score}"
    )


# ============================================================
# RESULTADOS DE PREDICCIONES
# ============================================================

def revisar_predicciones_pendientes(
    estado,
    mercados_por_id
):

    ahora = now_ts()

    eliminar = []

    for (
        key,
        pred
    ) in list(
        estado[
            "predicciones"
        ].items()
    ):

        market_id = str(
            pred.get(
                "market_id"
            )
        )

        partido = (
            mercados_por_id
            .get(
                market_id
            )
        )

        if not partido:
            continue

        selection = pred.get(
            "selection"
        )

        runner = obtener_runner(
            partido,
            selection
        )

        if not runner:
            continue

        actual = runner.get(
            "back"
        )

        if actual is None:
            continue

        inicial = float(
            pred[
                "cuota_inicial"
            ]
        )

        actual = float(
            actual
        )


        # ====================================================
        # SOLO COMPARAR:
        #
        # cuota al crear predicción
        # VS
        # cuota posterior
        # ====================================================

        caida_desde_prediccion = (
            drop_pct(
                inicial,
                actual
            )
        )


        # ====================================================
        # CONFIRMACIÓN VERDADERA
        # ====================================================

        if (
            caida_desde_prediccion
            >= DROP_ALERT_PCT
        ):

            segundos = int(
                ahora
                - pred["ts"]
            )

            mensaje = (
                "✅ <b>PREDICCIÓN CONFIRMADA</b>\n\n"

                f"🏆 {pred.get('liga', '-')}\n"

                f"⚽ <b>"
                f"{pred['event_name']}"
                f"</b>\n\n"

                f"📉 <b>"
                f"{selection_nombre(selection)}"
                f"</b>\n\n"

                f"{fmt_odds(inicial)} "
                f"→ "
                f"<b>{fmt_odds(actual)}</b>\n"

                f"Caída: "
                f"<b>-{caida_desde_prediccion:.2f}%</b>\n\n"

                f"⏱ Desde predicción: "
                f"{segundos} s"
            )

            enviar_telegram(
                mensaje
            )

            log_json({

                "tipo":
                    "PREDICCION_CONFIRMADA",

                "timestamp":
                    now_iso(),

                "market_id":
                    market_id,

                "selection":
                    selection,

                "inicial":
                    inicial,

                "actual":
                    actual,

                "caida_pct":
                    caida_desde_prediccion,

                "segundos":
                    segundos
            })

            eliminar.append(
                key
            )

            continue


        # ====================================================
        # PREDICCIÓN EXPIRÓ
        # ====================================================

        if (
            ahora
            >= pred["expires"]
        ):

            variacion = pct_change(
                inicial,
                actual
            )

            mensaje = (
                "❌ <b>PREDICCIÓN NO CONFIRMADA</b>\n\n"

                f"🏆 {pred.get('liga', '-')}\n"

                f"⚽ <b>"
                f"{pred['event_name']}"
                f"</b>\n\n"

                f"{selection_nombre(selection)}\n\n"

                f"{fmt_odds(inicial)} "
                f"→ "
                f"{fmt_odds(actual)}\n\n"

                f"Movimiento: "
                f"{variacion:+.2f}%\n"

                f"⏱ Pasaron 3 min"
            )

            enviar_telegram(
                mensaje
            )

            log_json({

                "tipo":
                    "PREDICCION_FALLIDA",

                "timestamp":
                    now_iso(),

                "market_id":
                    market_id,

                "selection":
                    selection,

                "inicial":
                    inicial,

                "actual":
                    actual,

                "variacion_pct":
                    variacion
            })

            eliminar.append(
                key
            )


    for key in eliminar:

        estado[
            "predicciones"
        ].pop(
            key,
            None
        )


# ============================================================
# MOVIMIENTO REAL >= 2%
# ============================================================

def revisar_movimiento_real(
    estado,
    partido,
    market_id,
    selection
):

    runner = obtener_runner(
        partido,
        selection
    )

    if not runner:
        return

    actual = runner.get(
        "back"
    )

    if actual is None:
        return

    actual = float(
        actual
    )


    # ========================================================
    # REFERENCIA DEL MOVIMIENTO REAL
    # ========================================================

    referencia = max_back_reciente(
        market_id,
        selection,
        DROP_REFERENCE_WINDOW_SEC
    )

    if referencia is None:
        return

    referencia = float(
        referencia
    )

    caida = drop_pct(
        referencia,
        actual
    )

    key = (
        f"{market_id}:"
        f"{selection}"
    )

    movimiento = (
        estado["movimientos"]
        .get(key)
    )


    # ========================================================
    # CREAR CICLO DE MOVIMIENTO
    # ========================================================

    if (
        movimiento is None
        and caida >= DROP_ALERT_PCT
    ):

        movimiento = {

            "referencia":
                referencia,

            "minimo":
                actual,

            "max_nivel_enviado":
                0,

            "activo":
                True,

            "ts_inicio":
                now_ts()
        }

        estado[
            "movimientos"
        ][key] = movimiento


    if movimiento is None:
        return


    # ========================================================
    # ACTUALIZAR MÍNIMO
    # ========================================================

    if (
        actual
        < float(
            movimiento[
                "minimo"
            ]
        )
    ):

        movimiento[
            "minimo"
        ] = actual


    referencia_mov = float(
        movimiento[
            "referencia"
        ]
    )

    caida_mov = drop_pct(
        referencia_mov,
        actual
    )


    # ========================================================
    # NIVELES -2 / -4 / -6
    # ========================================================

    for nivel in DROP_LEVELS:

        if not (
            caida_mov >= nivel
            and movimiento[
                "max_nivel_enviado"
            ] < nivel
        ):

            continue


        # ====================================================
        # VER SI EXISTÍA PREDICCIÓN
        # ====================================================

        pred = (
            estado["predicciones"]
            .get(key)
        )

        confirmar_prediccion = False

        cuota_mensaje_inicial = (
            referencia_mov
        )

        caida_mensaje = (
            caida_mov
        )

        extra = ""

        titulo = (
            "📉 "
            "<b>CAÍDA ORBITX</b>"
        )


        # ====================================================
        # CORRECCIÓN PRINCIPAL
        #
        # Solo confirmamos si cayó >=2%
        # DESDE LA CUOTA DE LA PREDICCIÓN.
        # ====================================================

        if pred:

            cuota_prediccion = float(
                pred[
                    "cuota_inicial"
                ]
            )

            caida_desde_prediccion = (
                drop_pct(
                    cuota_prediccion,
                    actual
                )
            )

            if (
                caida_desde_prediccion
                >= DROP_ALERT_PCT
            ):

                confirmar_prediccion = True

                segundos = int(
                    now_ts()
                    - pred["ts"]
                )

                titulo = (
                    "✅ "
                    "<b>PREDICCIÓN CONFIRMADA</b>"
                )

                cuota_mensaje_inicial = (
                    cuota_prediccion
                )

                caida_mensaje = (
                    caida_desde_prediccion
                )

                extra = (
                    f"\n⏱ Desde predicción: "
                    f"{segundos} s"
                )


        # ====================================================
        # MENSAJE
        # ====================================================

        mensaje = (
            f"{titulo}\n\n"

            f"🏆 "
            f"{partido.get('liga', '-')}\n"

            f"⚽ <b>"
            f"{partido.get('eventName', '-')}"
            f"</b>\n\n"

            f"📉 <b>"
            f"{selection_nombre(selection)}"
            f"</b>\n\n"

            f"{fmt_odds(cuota_mensaje_inicial)} "
            f"→ "
            f"<b>{fmt_odds(actual)}</b>\n"

            f"Caída: "
            f"<b>-{caida_mensaje:.2f}%</b>"
            f"{extra}"
        )

        enviar_telegram(
            mensaje
        )


        log_json({

            "tipo":
                (
                    "PREDICCION_CONFIRMADA"
                    if confirmar_prediccion
                    else "CAIDA_CONFIRMADA"
                ),

            "timestamp":
                now_iso(),

            "market_id":
                market_id,

            "event_name":
                partido.get(
                    "eventName"
                ),

            "selection":
                selection,

            "referencia":
                cuota_mensaje_inicial,

            "actual":
                actual,

            "caida_pct":
                caida_mensaje,

            "nivel_movimiento":
                nivel,

            "desde_prediccion":
                confirmar_prediccion
        })


        movimiento[
            "max_nivel_enviado"
        ] = nivel


        # Si fue confirmada de verdad,
        # quitamos la predicción pendiente.
        if confirmar_prediccion:

            estado[
                "predicciones"
            ].pop(
                key,
                None
            )


    # ========================================================
    # REVERSIÓN
    # ========================================================

    minimo = float(
        movimiento[
            "minimo"
        ]
    )

    rebote = pct_change(
        minimo,
        actual
    )

    if (
        movimiento.get(
            "activo"
        )
        and movimiento[
            "max_nivel_enviado"
        ] >= DROP_ALERT_PCT
        and rebote
        >= REVERSAL_FROM_LOW_PCT
    ):

        mensaje = (
            "🔄 <b>MOVIMIENTO REVERTIDO</b>\n\n"

            f"🏆 "
            f"{partido.get('liga', '-')}\n"

            f"⚽ <b>"
            f"{partido.get('eventName', '-')}"
            f"</b>\n\n"

            f"📈 "
            f"<b>{selection_nombre(selection)}</b>\n\n"

            f"Mínimo: "
            f"{fmt_odds(minimo)}\n"

            f"Ahora: "
            f"<b>{fmt_odds(actual)}</b>\n\n"

            f"Rebote: "
            f"<b>+{rebote:.2f}%</b>"
        )

        enviar_telegram(
            mensaje
        )

        movimiento[
            "activo"
        ] = False

        log_json({

            "tipo":
                "REVERSIÓN",

            "timestamp":
                now_iso(),

            "market_id":
                market_id,

            "selection":
                selection,

            "minimo":
                minimo,

            "actual":
                actual,

            "rebote_pct":
                rebote
        })


    # ========================================================
    # RESET DEL CICLO
    # ========================================================

    if not movimiento.get(
        "activo"
    ):

        caida_actual = drop_pct(
            referencia_mov,
            actual
        )

        if (
            caida_actual
            <= RESET_DROP_PCT
        ):

            estado[
                "movimientos"
            ].pop(
                key,
                None
            )


# ============================================================
# ALERTA 90 MIN
# ============================================================

def revisar_alerta_90(
    estado,
    partido
):

    event_id = str(
        partido.get(
            "eventId",
            ""
        )
    )

    if not event_id:
        return

    if (
        estado[
            "alerta_90"
        ].get(
            event_id
        )
    ):

        return

    start = parse_start_pe(
        partido.get(
            "start_pe"
        )
    )

    if not start:
        return

    ahora = datetime.now(
        start.tzinfo
    )

    minutos = (
        start - ahora
    ).total_seconds() / 60

    if (
        minutos
        > ALERT_90_MIN
    ):

        return

    if (
        minutos
        <
        ALERT_90_MIN
        - ALERT_90_WINDOW
    ):

        return

    home = obtener_runner(
        partido,
        "HOME"
    )

    draw = obtener_runner(
        partido,
        "DRAW"
    )

    away = obtener_runner(
        partido,
        "AWAY"
    )

    mensaje = (
        "⏰ <b>90 MINUTOS PARA EL PARTIDO</b>\n\n"

        f"🏆 {partido.get('liga', '-')}\n"

        f"⚽ <b>"
        f"{partido.get('eventName', '-')}"
        f"</b>\n"

        f"📅 "
        f"{start.strftime('%d/%m/%Y')}  "

        f"🕒 "
        f"{start.strftime('%H:%M')} 🇵🇪\n\n"

        "📊 <b>ORBITX</b>\n"

        f"L: "
        f"{fmt_odds(home['back'] if home else None)}\n"

        f"X: "
        f"{fmt_odds(draw['back'] if draw else None)}\n"

        f"V: "
        f"{fmt_odds(away['back'] if away else None)}\n\n"

        f"💰 Volumen mercado: "
        f"{fmt_money(partido.get('tv_market'))}\n"

        f"⏳ Faltan: "
        f"{minutos:.1f} min"
    )

    if enviar_telegram(
        mensaje
    ):

        estado[
            "alerta_90"
        ][event_id] = {

            "timestamp":
                now_iso()
        }


# ============================================================
# PROCESAR SNAPSHOT
# ============================================================

def procesar():

    snapshot = cargar_json(
        SNAPSHOT_FILE,
        {}
    )

    mercados = snapshot.get(
        "markets",
        []
    )

    if not mercados:
        return

    estado = cargar_estado()

    mercados_por_id = {}


    # ========================================================
    # PRIMERA PASADA
    # GUARDAR HISTORIA
    # ========================================================

    for partido in mercados:

        market_id = str(
            partido.get(
                "marketId",
                ""
            )
        )

        if not market_id:
            continue

        mercados_por_id[
            market_id
        ] = partido

        for selection in [
            "HOME",
            "DRAW",
            "AWAY"
        ]:

            runner = obtener_runner(
                partido,
                selection
            )

            agregar_historia(
                market_id,
                partido,
                selection,
                runner
            )


    # ========================================================
    # SEGUNDA PASADA
    # ALERTAS
    # ========================================================

    for partido in mercados:

        market_id = str(
            partido.get(
                "marketId",
                ""
            )
        )

        if not market_id:
            continue


        # ----------------------------------------------------
        # 90 MINUTOS
        # ----------------------------------------------------

        revisar_alerta_90(
            estado,
            partido
        )


        # ----------------------------------------------------
        # HOME / AWAY
        # ----------------------------------------------------

        for selection in (
            TARGET_SELECTIONS
        ):

            # Primero miramos si ya ocurrió
            # un movimiento real.
            revisar_movimiento_real(
                estado,
                partido,
                market_id,
                selection
            )

            # Después buscamos predicción.
            #
            # Esto evita crear una predicción
            # exactamente en el mismo snapshot
            # donde ya ocurrió una caída >=2%.
            revisar_prediccion(
                estado,
                partido,
                market_id,
                selection
            )


    # ========================================================
    # RESOLVER PREDICCIONES PENDIENTES
    # ========================================================

    revisar_predicciones_pendientes(
        estado,
        mercados_por_id
    )


    # ========================================================
    # GUARDAR ESTADO
    # ========================================================

    guardar_json(
        STATE_FILE,
        estado
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print(
        "=============================================="
    )

    print(
        " ORBITX PREDICTOR + MOVIMIENTOS - MANCORABET"
    )

    print(
        "=============================================="
    )

    print(
        f"Snapshot: "
        f"{SNAPSHOT_FILE}"
    )

    print(
        f"Revisión: "
        f"cada {CHECK_EVERY_SEC}s"
    )

    print(
        f"Predicción L/V: "
        f"score >= "
        f"{PREDICTION_SCORE_MIN}"
    )

    print(
        f"Caída confirmada: "
        f">= {DROP_ALERT_PCT}%"
    )

    print(
        f"Niveles: "
        f"{DROP_LEVELS}"
    )

    print(
        f"Telegram: "
        f"{'OK' if telegram_configurado() else 'NO CONFIGURADO'}"
    )

    print(
        "=============================================="
    )

    print()

    while True:

        try:

            procesar()

        except KeyboardInterrupt:

            print(
                "\nPrograma detenido."
            )

            break

        except Exception as e:

            print(
                "[ERROR GENERAL] "
                f"{type(e).__name__}: "
                f"{e}"
            )

        time.sleep(
            CHECK_EVERY_SEC
        )


if __name__ == "__main__":

    main()