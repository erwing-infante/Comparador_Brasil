# smart_alerts_PA.py

import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")

CUOTAS_FILE = os.path.join(DATA_DIR, "cuotas.json")
ESTADO_FILE = os.path.join(DATA_DIR, "ultimo_estado_alertas_PA.json")

TELEGRAM_TOKEN = os.getenv("SMART_PA_BOT_TOKEN")

USUARIOS = []

for variable in (
    "SMART_PA_BOT_CHAT_ID_1",
    "SMART_PA_BOT_CHAT_ID_2",
    "SMART_PA_BOT_CHAT_ID_3",
    "SMART_PA_BOT_CHAT_ID_4",
):
    valor = os.getenv(variable)

    if not valor:
        continue

    try:
        chat_id = int(valor)

        if chat_id not in USUARIOS:
            USUARIOS.append(chat_id)

    except Exception:
        print(f"⚠️ CHAT_ID inválido en {variable}: {valor}")


# ============================================================
# CONFIG
# ============================================================

MARGEN_MINIMO = -2.00

MAX_HORAS_ADELANTE = 36.0

TZ_PE = ZoneInfo("America/Lima")
HORA_INICIO_TELEGRAM = 7
HORA_FIN_TELEGRAM = 23


# ============================================================
# HORARIO TELEGRAM
# ============================================================

def telegram_habilitado():
    ahora_pe = datetime.now(TZ_PE)
    return HORA_INICIO_TELEGRAM <= ahora_pe.hour < HORA_FIN_TELEGRAM


# ============================================================
# TELEGRAM
# ============================================================

def enviar_alerta(msg):

    if not telegram_habilitado():
        print("🌙 Telegram PA silenciado por horario (23:00 - 07:00, hora Perú).")
        return False

    if not TELEGRAM_TOKEN:
        print("❌ SMART_PA_BOT_TOKEN no configurado.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    for cid in USUARIOS:

        payload = {
            "chat_id": cid,
            "text": msg,
            "parse_mode": "HTML"
        }

        try:
            r = requests.post(
                url,
                data=payload,
                timeout=10
            )

            if not r.ok:
                print(f"❌ Error Telegram PA chat {cid}: {r.text}")

        except Exception as e:
            print(f"❌ Excepción enviando Telegram PA chat {cid}: {e}")

    return True


# ============================================================
# MARGEN
# ============================================================

def calcular_margen(c1, c2, c3):

    try:
        return (1 / c1 + 1 / c2 + 1 / c3) * 100 - 100

    except Exception:
        return None


def margen_valido(margen_jugador):

    # Positivo, 0 y negativo hasta -2.00%
    return margen_jugador >= MARGEN_MINIMO


# ============================================================
# JSON
# ============================================================

def cargar_json(path, default):

    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return default


def guardar_json(path, data):

    tmp = path + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    os.replace(tmp, path)


# ============================================================
# CLAVE
# ============================================================

def generar_clave(liga, fecha, home, away):
    return f"{liga} | {fecha} | {home} vs {away}"


# ============================================================
# FECHAS
# ============================================================

def parse_fecha_utc_a_lima(fecha_str):

    if not fecha_str or not isinstance(fecha_str, str):
        return None

    try:
        s = fecha_str.replace(" UTC", "").strip()

        dt_utc = datetime.strptime(
            s,
            "%Y-%m-%d %H:%M"
        ).replace(
            tzinfo=ZoneInfo("UTC")
        )

        return dt_utc.astimezone(TZ_PE)

    except Exception:
        return None


def format_fecha_para_msg(fecha_str):

    dt_lima = parse_fecha_utc_a_lima(fecha_str)

    if dt_lima is None:
        return fecha_str

    return (
        dt_lima.strftime("%Y-%m-%d %H:%M")
        + " Perú (GMT-5)"
    )


def dentro_ventana_partido(fecha_str, ahora_lima):

    dt_lima = parse_fecha_utc_a_lima(fecha_str)

    if dt_lima is None:
        return False

    horas = (
        dt_lima - ahora_lima
    ).total_seconds() / 3600.0

    return 0 <= horas <= MAX_HORAS_ADELANTE


# ============================================================
# MENSAJE
# ============================================================

def enviar_alerta_armada(liga, p, margen_jugador):

    home = p.get("home")
    away = p.get("away")
    fecha = p.get("date")

    fecha_msg = format_fecha_para_msg(fecha)

    bh = p.get("best_home") or {}
    bd = p.get("best_draw") or {}
    ba = p.get("best_away") or {}

    msg = f"""
⚠️ <b>ALERTAS MANCORABET PA</b>

<b>{home} vs {away}</b>
Liga: <b>{liga}</b>
Fecha: <b>{fecha_msg}</b>

Margen combinado: <b>{margen_jugador:.2f}%</b>

Cuotas máximas:
🏠 Local: <b>{bh.get("odd")}</b> ({bh.get("bookmaker")})
🤝 Empate: <b>{bd.get("odd")}</b> ({bd.get("bookmaker")})
🚶 Visita: <b>{ba.get("odd")}</b> ({ba.get("bookmaker")})
"""

    enviar_alerta(msg.strip())


# ============================================================
# PROCESAR
# ============================================================

def procesar_alertas():

    if not os.path.exists(CUOTAS_FILE):
        return

    data = cargar_json(
        CUOTAS_FILE,
        default={}
    )

    estado_prev = cargar_json(
        ESTADO_FILE,
        default={}
    )

    estado_new = {}

    ahora_lima = datetime.now(TZ_PE)

    ahora_str = ahora_lima.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    for liga, partidos in data.items():

        if liga == "metadata":
            continue

        for p in partidos:

            home = p.get("home")
            away = p.get("away")
            fecha = p.get("date", "")

            if not dentro_ventana_partido(
                fecha,
                ahora_lima
            ):
                continue

            bh = p.get("best_home") or {}
            bd = p.get("best_draw") or {}
            ba = p.get("best_away") or {}

            c1 = bh.get("odd")
            c2 = bd.get("odd")
            c3 = ba.get("odd")

            if None in [c1, c2, c3]:
                continue

            try:
                c1 = float(c1)
                c2 = float(c2)
                c3 = float(c3)

            except Exception:
                continue

            margen_real = calcular_margen(
                c1,
                c2,
                c3
            )

            if margen_real is None:
                continue

            # Se mantiene exactamente la lógica original
            margen_jugador = -1 * margen_real

            clave = generar_clave(
                liga,
                fecha,
                home,
                away
            )

            valido = margen_valido(
                margen_jugador
            )

            estado_new[clave] = {
                "home_odd": c1,
                "draw_odd": c2,
                "away_odd": c3,
                "margen_jugador": margen_jugador,
                "valido": valido,
                "ultima_actualizacion": ahora_str,
            }

            if not valido:
                continue

            prev = estado_prev.get(clave)

            if prev is None:

                enviar_alerta_armada(
                    liga,
                    p,
                    margen_jugador
                )

                continue

            cambio = (
                round(prev.get("home_odd", 0), 3) != round(c1, 3)
                or
                round(prev.get("draw_odd", 0), 3) != round(c2, 3)
                or
                round(prev.get("away_odd", 0), 3) != round(c3, 3)
            )

            entro_rango = not prev.get(
                "valido",
                False
            )

            if cambio or entro_rango:

                enviar_alerta_armada(
                    liga,
                    p,
                    margen_jugador
                )

    guardar_json(
        ESTADO_FILE,
        estado_new
    )

    print(
        "✔ smart_alerts_PA ejecutado | "
        "Margen positivo/0 hasta -2.00%"
    )


if __name__ == "__main__":
    procesar_alertas()