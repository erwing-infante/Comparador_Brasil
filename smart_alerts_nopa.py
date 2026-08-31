# smart_alerts_nopa.py
#
# Bot independiente para alertas de SUREBET NoPA.
# - Lee data/cuotas_NoPA.json
# - Solo alerta cuando el margen es POSITIVO (> 0)
# - Sin categorías A/B/C
# - Envía la misma alerta a 3 usuarios
# - Estado independiente para evitar duplicados
# - Ventana de partidos: próximas 36 horas

import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


# ============================================================
# RUTAS
# ============================================================

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")

CUOTAS_FILE = os.path.join(
    DATA_DIR,
    "cuotas_NoPA.json",
)

ESTADO_FILE = os.path.join(
    DATA_DIR,
    "ultimo_estado_alertas_nopa.json",
)


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_TOKEN = os.getenv(
    "SMART_NOPA_BOT_TOKEN"
)

CHAT_IDS = []


def agregar_chat_id(variable_entorno):
    valor = os.getenv(variable_entorno)

    if not valor:
        return

    try:
        chat_id = int(valor)

        if chat_id not in CHAT_IDS:
            CHAT_IDS.append(chat_id)

    except Exception:
        print(
            f"⚠️ CHAT_ID inválido en "
            f"{variable_entorno}: {valor}"
        )


agregar_chat_id("SMART_NOPA_CHAT_ID_1")
agregar_chat_id("SMART_NOPA_CHAT_ID_2")
agregar_chat_id("SMART_NOPA_CHAT_ID_3")


# ============================================================
# CONFIG
# ============================================================

# Solo partidos dentro de las próximas 36 horas.
MAX_HORAS_ADELANTE = 36.0

# Solo surebet real:
# margen_jugador > 0
UMBRAL_SUREBET = 0.0


# ============================================================
# TELEGRAM
# ============================================================

def enviar_alerta(msg: str):

    if not TELEGRAM_TOKEN:
        print(
            "❌ SMART_NOPA_BOT_TOKEN "
            "no configurado."
        )
        return

    if not CHAT_IDS:
        print(
            "❌ No hay CHAT_ID configurados "
            "para el bot NoPA."
        )
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_TOKEN}/sendMessage"
    )

    for chat_id in CHAT_IDS:

        payload = {
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "HTML",
        }

        try:
            r = requests.post(
                url,
                data=payload,
                timeout=10,
            )

            if not r.ok:
                print(
                    f"❌ Error Telegram "
                    f"chat {chat_id}: "
                    f"{r.text}"
                )

        except Exception as e:
            print(
                f"❌ Excepción enviando "
                f"Telegram chat {chat_id}: "
                f"{e}"
            )


# ============================================================
# CÁLCULO DE MARGEN
# ============================================================

def calcular_margen(c1, c2, c3):
    """
    Mantiene la misma convención del bot PA:

    margen_real =
        (1/c1 + 1/c2 + 1/c3) * 100 - 100

    margen_jugador = -margen_real

    Si margen_jugador > 0:
        existe surebet.
    """

    try:
        return (
            1 / c1
            + 1 / c2
            + 1 / c3
        ) * 100 - 100

    except Exception:
        return None


# ============================================================
# JSON
# ============================================================

def cargar_json(path, default):

    if not os.path.exists(path):
        return default

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except Exception:
        return default


def guardar_json(path, data):

    tmp = path + ".tmp"

    with open(
        tmp,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )

    os.replace(
        tmp,
        path,
    )


# ============================================================
# CLAVE DEL PARTIDO
# ============================================================

def generar_clave(
    liga,
    fecha,
    home,
    away,
    event_id=None,
):
    """
    Prioriza EventId si existe.
    Si no existe, usa liga + fecha + equipos.
    """

    event_id = str(
        event_id or ""
    ).strip()

    if event_id:
        return f"EVENTID:{event_id}"

    return (
        f"{liga} | {fecha} | "
        f"{home} vs {away}"
    )


# ============================================================
# FECHAS
# ============================================================

def parse_fecha_utc_a_lima(
    fecha_str: str
):

    if (
        not fecha_str
        or not isinstance(
            fecha_str,
            str,
        )
    ):
        return None

    try:
        s = (
            fecha_str
            .replace(" UTC", "")
            .strip()
        )

        dt_utc = datetime.strptime(
            s,
            "%Y-%m-%d %H:%M",
        ).replace(
            tzinfo=ZoneInfo("UTC")
        )

        return dt_utc.astimezone(
            ZoneInfo("America/Lima")
        )

    except Exception:
        return None


def format_fecha_para_msg(
    fecha_str: str
) -> str:

    dt_lima = parse_fecha_utc_a_lima(
        fecha_str
    )

    if dt_lima is None:
        return fecha_str

    return (
        dt_lima.strftime(
            "%Y-%m-%d %H:%M"
        )
        + " Perú (GMT-5)"
    )


def dentro_ventana_partido(
    fecha_str: str,
    ahora_lima: datetime,
) -> bool:

    dt_lima = parse_fecha_utc_a_lima(
        fecha_str
    )

    if dt_lima is None:
        return False

    horas = (
        dt_lima - ahora_lima
    ).total_seconds() / 3600.0

    return (
        0
        <= horas
        <= MAX_HORAS_ADELANTE
    )


# ============================================================
# FORMATO ALERTA
# ============================================================

def enviar_alerta_armada(
    liga,
    partido,
    margen_jugador,
):

    home = partido.get("home")
    away = partido.get("away")
    fecha = partido.get("date")

    fecha_msg = format_fecha_para_msg(
        fecha
    )

    bh = (
        partido.get("best_home")
        or {}
    )
    bd = (
        partido.get("best_draw")
        or {}
    )
    ba = (
        partido.get("best_away")
        or {}
    )

    msg = f"""
💰 <b>SUREBET MANCORABET NoPA</b>

⚽ <b>{home} vs {away}</b>
🏆 Liga: <b>{liga}</b>
🕒 Fecha: <b>{fecha_msg}</b>

✅ Margen: <b>+{margen_jugador:.2f}%</b>

Cuotas máximas:
🏠 Local: <b>{bh.get("odd")}</b> ({bh.get("bookmaker")})
🤝 Empate: <b>{bd.get("odd")}</b> ({bd.get("bookmaker")})
🚶 Visita: <b>{ba.get("odd")}</b> ({ba.get("bookmaker")})
"""

    enviar_alerta(
        msg.strip()
    )


# ============================================================
# PROCESAR ALERTAS
# ============================================================

def procesar_alertas():

    if not os.path.exists(
        CUOTAS_FILE
    ):
        print(
            "❌ No existe "
            f"{CUOTAS_FILE}"
        )
        return

    data = cargar_json(
        CUOTAS_FILE,
        default={},
    )

    estado_prev = cargar_json(
        ESTADO_FILE,
        default={},
    )

    estado_new = {}

    ahora_lima = datetime.now(
        ZoneInfo("America/Lima")
    )

    ahora_str = ahora_lima.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    total_surebets = 0
    total_alertas = 0

    for liga, partidos in data.items():

        if liga == "metadata":
            continue

        if not isinstance(
            partidos,
            list,
        ):
            continue

        for partido in partidos:

            home = partido.get("home")
            away = partido.get("away")
            fecha = partido.get(
                "date",
                "",
            )

            event_id = (
                partido.get("eventId")
                or partido.get("EventId")
            )

            # =============================================
            # SOLO PRÓXIMAS 36 HORAS
            # =============================================

            if not dentro_ventana_partido(
                fecha,
                ahora_lima,
            ):
                continue

            bh = (
                partido.get("best_home")
                or {}
            )
            bd = (
                partido.get("best_draw")
                or {}
            )
            ba = (
                partido.get("best_away")
                or {}
            )

            c1 = bh.get("odd")
            c2 = bd.get("odd")
            c3 = ba.get("odd")

            if None in [
                c1,
                c2,
                c3,
            ]:
                continue

            try:
                c1 = float(c1)
                c2 = float(c2)
                c3 = float(c3)

            except Exception:
                continue

            if (
                c1 <= 1
                or c2 <= 1
                or c3 <= 1
            ):
                continue

            # =============================================
            # CÁLCULO SUREBET
            # =============================================

            margen_real = calcular_margen(
                c1,
                c2,
                c3,
            )

            if margen_real is None:
                continue

            margen_jugador = (
                -1 * margen_real
            )

            # =============================================
            # SOLO SUREBET POSITIVA
            # =============================================

            if (
                margen_jugador
                <= UMBRAL_SUREBET
            ):
                continue

            total_surebets += 1

            clave = generar_clave(
                liga,
                fecha,
                home,
                away,
                event_id,
            )

            estado_new[clave] = {
                "eventId": event_id,
                "home_odd": c1,
                "draw_odd": c2,
                "away_odd": c3,
                "margen_jugador": (
                    margen_jugador
                ),
                "ultima_actualizacion": (
                    ahora_str
                ),
            }

            prev = estado_prev.get(
                clave
            )

            # =============================================
            # SUREBET NUEVA
            # =============================================

            if prev is None:

                enviar_alerta_armada(
                    liga,
                    partido,
                    margen_jugador,
                )

                total_alertas += 1
                continue

            # =============================================
            # DETECTAR CAMBIO DE CUOTAS
            # =============================================

            cambio_cuotas = (
                round(
                    float(
                        prev.get(
                            "home_odd",
                            0,
                        )
                    ),
                    3,
                )
                != round(c1, 3)

                or

                round(
                    float(
                        prev.get(
                            "draw_odd",
                            0,
                        )
                    ),
                    3,
                )
                != round(c2, 3)

                or

                round(
                    float(
                        prev.get(
                            "away_odd",
                            0,
                        )
                    ),
                    3,
                )
                != round(c3, 3)
            )

            # =============================================
            # ENVIAR DE NUEVO SOLO SI CAMBIÓ ALGUNA CUOTA
            # =============================================

            if cambio_cuotas:

                enviar_alerta_armada(
                    liga,
                    partido,
                    margen_jugador,
                )

                total_alertas += 1

    guardar_json(
        ESTADO_FILE,
        estado_new,
    )

    print(
        "✔ smart_alerts_nopa ejecutado "
        f"| Surebets activas: "
        f"{total_surebets} "
        f"| Alertas enviadas: "
        f"{total_alertas}"
    )


if __name__ == "__main__":
    procesar_alertas()
