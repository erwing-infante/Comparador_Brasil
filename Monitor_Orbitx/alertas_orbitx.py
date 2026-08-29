import os
import json
import time
from datetime import datetime

import requests


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_DIR = "/root/proyectos/Mancorabet/Monitor_Orbitx"
DATA_DIR = os.path.join(BASE_DIR, "data")

SNAPSHOT_FILE = os.path.join(
    DATA_DIR,
    "snapshot.json"
)

STATE_FILE = os.path.join(
    DATA_DIR,
    "estado_caidas_orbitx.json"
)

LOG_FILE = os.path.join(
    DATA_DIR,
    "caidas_orbitx.jsonl"
)


# ============================================================
# TELEGRAM - BOT NUEVO
# ============================================================

TELEGRAM_TOKEN = os.getenv(
    "ORBITX_CAIDAS_BOT_TOKEN"
)

TELEGRAM_CHAT_ID = os.getenv(
    "ORBITX_CAIDAS_CHAT_ID"
)


# ============================================================
# CONFIGURACIÓN
# ============================================================

MAX_HOURS_AHEAD = 18

CHECK_EVERY_SEC = 5

TARGET_SELECTIONS = [
    "HOME",
    "AWAY"
]

DROP_ALERT_PCT = 2.0

REVERSAL_FROM_LOW_PCT = 1.5

ALERT_90_MIN = 90
ALERT_90_WINDOW = 3


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
            f"[ERROR JSON] {e}"
        )

        return default


def guardar_json(path, data):

    try:

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
        "ultimo_back",
        {}
    )

    estado.setdefault(
        "movimientos",
        {}
    )

    estado.setdefault(
        "alerta_90",
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

        print(
            "[TELEGRAM CAIDAS] "
            "NO CONFIGURADO"
        )

        return False


    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )


    payload = {
        "chat_id":
            TELEGRAM_CHAT_ID,

        "text":
            mensaje,

        "parse_mode":
            "HTML",

        "disable_web_page_preview":
            True
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
            f"{r.status_code}"
        )


    except Exception as e:

        print(
            f"[TELEGRAM ERROR] {e}"
        )


    return False


# ============================================================
# UTILIDADES
# ============================================================

def parse_start_pe(valor):

    if not valor:
        return None

    try:

        return datetime.fromisoformat(
            valor
        )

    except Exception:

        return None


def now_iso():

    return (
        datetime.now()
        .astimezone()
        .isoformat()
    )


def fmt_odds(valor):

    if valor is None:
        return "-"

    try:
        return f"{float(valor):.2f}"

    except Exception:
        return str(valor)


def fmt_money(valor):

    if valor is None:
        return "-"

    try:
        return f"{float(valor):,.2f}"

    except Exception:
        return str(valor)


def selection_nombre(selection):

    if selection == "HOME":
        return "LOCAL"

    return "VISITA"


def drop_pct(
    anterior,
    actual
):

    try:

        anterior = float(anterior)
        actual = float(actual)

        if anterior <= 0:
            return 0.0

        return (
            (
                anterior
                - actual
            )
            / anterior
        ) * 100.0

    except Exception:

        return 0.0


def pct_change(
    anterior,
    actual
):

    try:

        anterior = float(anterior)
        actual = float(actual)

        if anterior <= 0:
            return 0.0

        return (
            (
                actual
                / anterior
            )
            - 1
        ) * 100.0

    except Exception:

        return 0.0


# ============================================================
# PREMATCH
# ============================================================

def partido_prematch_valido(partido):

    start = parse_start_pe(
        partido.get(
            "start_pe"
        )
    )

    if not start:

        return False


    ahora = datetime.now(
        start.tzinfo
    )


    segundos = (
        start
        - ahora
    ).total_seconds()


    if segundos <= 0:

        return False


    if segundos > (
        MAX_HOURS_AHEAD * 3600
    ):

        return False


    return True


# ============================================================
# RUNNER
# ============================================================

def obtener_runner(
    partido,
    selection
):

    runners = partido.get(
        "runners",
        {}
    )


    for runner in runners.values():

        if (
            runner.get(
                "selection"
            )
            == selection
        ):

            return runner


    return None


# ============================================================
# CAÍDAS
# ============================================================

def revisar_caida(
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
        "best_back_odds"
    )


    if actual is None:

        return


    actual = float(
        actual
    )


    key = (
        f"{market_id}|"
        f"{selection}"
    )


    anterior = (
        estado[
            "ultimo_back"
        ].get(
            key
        )
    )


    # Primera lectura.
    if anterior is None:

        estado[
            "ultimo_back"
        ][key] = actual

        return


    anterior = float(
        anterior
    )


    # La cuota no cambió.
    if actual == anterior:

        return


    # MUY IMPORTANTE:
    # actualizar inmediatamente.
    #
    # Esto impide duplicados.
    estado[
        "ultimo_back"
    ][key] = actual


    caida = drop_pct(
        anterior,
        actual
    )


    # ========================================================
    # REVISAR REVERSIÓN
    # ========================================================

    movimiento = (
        estado[
            "movimientos"
        ].get(
            key
        )
    )


    if (
        movimiento
        and movimiento.get(
            "activo",
            False
        )
    ):

        minimo = float(
            movimiento[
                "minimo"
            ]
        )


        if actual < minimo:

            minimo = actual

            movimiento[
                "minimo"
            ] = actual


        rebote = pct_change(
            minimo,
            actual
        )


        if (
            rebote
            >= REVERSAL_FROM_LOW_PCT
        ):

            mensaje = (
                "🔄 <b>MOVIMIENTO REVERTIDO</b>\n\n"

                f"🏆 "
                f"{partido.get('liga', '-')}\n"

                f"⚽ <b>"
                f"{partido.get('eventName', '-')}"
                f"</b>\n\n"

                f"📈 <b>"
                f"{selection_nombre(selection)}"
                f"</b>\n\n"

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
    # CAÍDA INSTANTÁNEA
    # ========================================================

    if (
        caida
        < DROP_ALERT_PCT
    ):

        return


    mensaje = (
        "📉 <b>CAÍDA ORBITX</b>\n\n"

        f"🏆 "
        f"{partido.get('liga', '-')}\n"

        f"⚽ <b>"
        f"{partido.get('eventName', '-')}"
        f"</b>\n\n"

        f"📉 <b>"
        f"{selection_nombre(selection)}"
        f"</b>\n\n"

        f"{fmt_odds(anterior)} "
        f"→ "
        f"<b>{fmt_odds(actual)}</b>\n"

        f"Caída: "
        f"<b>-{caida:.2f}%</b>"
    )


    enviar_telegram(
        mensaje
    )


    estado[
        "movimientos"
    ][key] = {
        "activo":
            True,

        "inicial":
            anterior,

        "minimo":
            actual,

        "timestamp":
            now_iso()
    }


    log_json({
        "tipo":
            "CAIDA",

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

        "anterior":
            anterior,

        "actual":
            actual,

        "caida_pct":
            caida
    })


# ============================================================
# ALERTA 90 MINUTOS
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
        event_id
        in estado[
            "alerta_90"
        ]
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
        start
        - ahora
    ).total_seconds() / 60.0


    if minutos > ALERT_90_MIN:

        return


    if minutos < (
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

        f"🏆 "
        f"{partido.get('liga', '-')}\n"

        f"⚽ <b>"
        f"{partido.get('eventName', '-')}"
        f"</b>\n"

        f"📅 "
        f"{start.strftime('%d/%m/%Y')}  "

        f"🕒 "
        f"{start.strftime('%H:%M')} 🇵🇪\n\n"

        "📊 <b>ORBITX</b>\n"

        f"L: "
        f"{fmt_odds(home.get('best_back_odds') if home else None)}\n"

        f"X: "
        f"{fmt_odds(draw.get('best_back_odds') if draw else None)}\n"

        f"V: "
        f"{fmt_odds(away.get('best_back_odds') if away else None)}\n\n"

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
# LIMPIEZA
# ============================================================

def limpiar_estado(
    estado,
    mercados_validos
):

    validos = set(
        mercados_validos.keys()
    )


    for grupo in [
        "ultimo_back",
        "movimientos"
    ]:

        borrar = []


        for key in (
            estado[
                grupo
            ].keys()
        ):

            market_id = (
                key.split(
                    "|",
                    1
                )[0]
            )


            if (
                market_id
                not in validos
            ):

                borrar.append(
                    key
                )


        for key in borrar:

            estado[
                grupo
            ].pop(
                key,
                None
            )


# ============================================================
# PROCESAR
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


    mercados_validos = {}


    for partido in mercados:

        if not partido_prematch_valido(
            partido
        ):

            continue


        market_id = str(
            partido.get(
                "marketId",
                ""
            )
        )


        if not market_id:

            continue


        mercados_validos[
            market_id
        ] = partido


    limpiar_estado(
        estado,
        mercados_validos
    )


    for market_id, partido in (
        mercados_validos.items()
    ):

        revisar_alerta_90(
            estado,
            partido
        )


        for selection in (
            TARGET_SELECTIONS
        ):

            revisar_caida(
                estado,
                partido,
                market_id,
                selection
            )


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
        " MANCORABET - CAIDAS ORBITX"
    )

    print(
        "=============================================="
    )

    print(
        f"Ventana: "
        f"0-{MAX_HOURS_AHEAD} horas"
    )

    print(
        "LIVE: IGNORADO"
    )

    print(
        f"Caída: "
        f">= {DROP_ALERT_PCT}%"
    )

    print(
        "Comparación: "
        "CUOTA ANTERIOR → NUEVA CUOTA"
    )

    print(
        f"Alerta: "
        f"{ALERT_90_MIN} min"
    )

    print(
        f"Telegram: "
        f"{'OK' if telegram_configurado() else 'NO CONFIGURADO'}"
    )

    print(
        "=============================================="
    )


    while True:

        try:

            procesar()

        except KeyboardInterrupt:

            break

        except Exception as e:

            print(
                "[ERROR] "
                f"{type(e).__name__}: "
                f"{e}"
            )


        time.sleep(
            CHECK_EVERY_SEC
        )


if __name__ == "__main__":

    main()