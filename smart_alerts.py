# smart_alerts.py

import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests


BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")

CUOTAS_FILE = os.path.join(DATA_DIR, "cuotas.json")
ESTADO_FILE = os.path.join(DATA_DIR, "ultimo_estado_alertas.json")

TELEGRAM_TOKEN = os.getenv("SMART_BOT_TOKEN")


# ============================================================
# USUARIOS Y PERMISOS
# ============================================================
#
# Clasificación interna:
#
# A = margen_jugador >= 0.00
# B = margen_jugador entre -1.20 y 0.00
# C = margen_jugador entre -1.80 y -1.20
#
# Esta clasificación NO aparece en Telegram.
#
# CHAT 1 = ADMIN      -> A, B, C
# CHAT 2 = FULL       -> A, B, C
# CHAT 3 = B, C
# CHAT 4 = C
# ============================================================

USUARIOS = {}


def agregar_usuario(variable_entorno, categorias):
    valor = os.getenv(variable_entorno)

    if not valor:
        return

    try:
        chat_id = int(valor)

        USUARIOS[chat_id] = {
            "categorias": categorias
        }

    except Exception:
        print(f"⚠️ CHAT_ID inválido en {variable_entorno}: {valor}")


# ADMIN
agregar_usuario(
    "SMART_BOT_CHAT_ID_1",
    ["A", "B", "C"]
)

# FULL
agregar_usuario(
    "SMART_BOT_CHAT_ID_2",
    ["A", "B", "C"]
)

# B + C
agregar_usuario(
    "SMART_BOT_CHAT_ID_3",
    ["B", "C"]
)

# SOLO C
agregar_usuario(
    "SMART_BOT_CHAT_ID_4",
    ["C"]
)


# ============================================================
# UMBRALES
# ============================================================

LIMITE_B = -1.20
LIMITE_C = -1.80

# Ventana de alertas:
# próximos 1.5 días = 36 horas
MAX_HORAS_ADELANTE = 36.0


# ============================================================
# CLASIFICACIÓN INTERNA
# ============================================================

def clasificar_senal(margen_jugador):

    # Surebet
    if margen_jugador >= 0:
        return "A"

    # Entre 0% y 1.20% de distancia
    if margen_jugador >= LIMITE_B:
        return "B"

    # Entre 1.20% y 1.80% de distancia
    if margen_jugador >= LIMITE_C:
        return "C"

    return None


# ============================================================
# TELEGRAM
# ============================================================

def enviar_alerta(msg: str, categoria: str):

    if not TELEGRAM_TOKEN:
        print("❌ SMART_BOT_TOKEN no configurado.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    for cid, config in USUARIOS.items():

        categorias_usuario = config.get("categorias", [])

        # Este usuario no recibe esta categoría
        if categoria not in categorias_usuario:
            continue

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
                print(
                    f"❌ Error Telegram chat {cid}:",
                    r.text
                )

        except Exception as e:
            print(
                f"❌ Excepción enviando Telegram chat {cid}:",
                e
            )


# ============================================================
# CÁLCULO DE MARGEN
# ============================================================
#
# SE MANTIENE EXACTAMENTE LA MISMA LÓGICA
# QUE TENÍAS EN TU CÓDIGO.
# ============================================================

def calcular_margen(c1, c2, c3):
    try:
        return (1 / c1 + 1 / c2 + 1 / c3) * 100 - 100
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
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return default


def guardar_json(path, data):

    tmp = path + ".tmp"

    with open(
        tmp,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )

    os.replace(tmp, path)


# ============================================================
# CLAVE DEL PARTIDO
# ============================================================

def generar_clave(liga, fecha, home, away):
    return f"{liga} | {fecha} | {home} vs {away}"


# ============================================================
# FECHAS
# ============================================================

def parse_fecha_utc_a_lima(fecha_str: str):

    """
    Entrada típica:
    '2025-11-27 17:45 UTC'

    Retorna datetime aware en America/Lima
    o None si no se puede parsear.
    """

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

        return dt_utc.astimezone(
            ZoneInfo("America/Lima")
        )

    except Exception:
        return None


def format_fecha_para_msg(fecha_str: str) -> str:

    """
    Convierte:
    YYYY-MM-DD HH:MM UTC

    a hora Perú.
    """

    dt_lima = parse_fecha_utc_a_lima(fecha_str)

    if dt_lima is None:
        return fecha_str

    return (
        dt_lima.strftime("%Y-%m-%d %H:%M")
        + " Perú (GMT-5)"
    )


def dentro_ventana_partido(
    fecha_str: str,
    ahora_lima: datetime
) -> bool:

    """
    True si el partido ocurre entre ahora
    y las próximas MAX_HORAS_ADELANTE.
    """

    dt_lima = parse_fecha_utc_a_lima(fecha_str)

    if dt_lima is None:
        return False

    horas = (
        dt_lima - ahora_lima
    ).total_seconds() / 3600.0

    return 0 <= horas <= MAX_HORAS_ADELANTE


# ============================================================
# ARMAR ALERTA
# ============================================================

def enviar_alerta_armada(
    liga,
    p,
    margen_jugador,
    categoria
):

    home = p.get("home")
    away = p.get("away")
    fecha = p.get("date")

    fecha_msg = format_fecha_para_msg(fecha)

    bh = p.get("best_home") or {}
    bd = p.get("best_draw") or {}
    ba = p.get("best_away") or {}


    # IMPORTANTE:
    # NO se muestra A, B o C en el mensaje.

    msg = f"""
⚠️ <b>ALERTAS MANCORABET</b>

<b>{home} vs {away}</b>
Liga: <b>{liga}</b>
Fecha: <b>{fecha_msg}</b>

Margen combinado: <b>{margen_jugador:.2f}%</b>

Cuotas máximas:
🏠 Local: <b>{bh.get("odd")}</b> ({bh.get("bookmaker")})
🤝 Empate: <b>{bd.get("odd")}</b> ({bd.get("bookmaker")})
🚶 Visita: <b>{ba.get("odd")}</b> ({ba.get("bookmaker")})
"""

    enviar_alerta(
        msg.strip(),
        categoria
    )


# ============================================================
# PROCESAR ALERTAS
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


    ahora_lima = datetime.now(
        ZoneInfo("America/Lima")
    )

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


            # =================================================
            # SOLO PARTIDOS EN LAS PRÓXIMAS 36 HORAS
            # =================================================

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


            # =================================================
            # CÁLCULO ORIGINAL
            # =================================================

            margen_real = calcular_margen(
                c1,
                c2,
                c3
            )

            if margen_real is None:
                continue


            # =================================================
            # SE MANTIENE TAL CUAL ESTABA EN TU CÓDIGO
            # =================================================

            margen_jugador = -1 * margen_real


            # =================================================
            # CLASIFICACIÓN INTERNA
            # =================================================

            categoria = clasificar_senal(
                margen_jugador
            )


            clave = generar_clave(
                liga,
                fecha,
                home,
                away
            )


            # =================================================
            # GUARDAR ESTADO ACTUAL
            # =================================================

            estado_new[clave] = {
                "home_odd": c1,
                "draw_odd": c2,
                "away_odd": c3,
                "margen_jugador": margen_jugador,
                "categoria": categoria,
                "ultima_actualizacion": ahora_str,
            }


            # =================================================
            # POR DEBAJO DE -1.80% NO SE ENVÍA
            # =================================================

            if categoria is None:
                continue


            prev = estado_prev.get(clave)


            # =================================================
            # PARTIDO NUEVO
            # =================================================

            if prev is None:

                enviar_alerta_armada(
                    liga,
                    p,
                    margen_jugador,
                    categoria
                )

                continue


            # =================================================
            # DETECTAR CAMBIO DE CUOTAS
            # =================================================

            cambio = (
                round(
                    prev.get("home_odd", 0),
                    3
                )
                != round(c1, 3)

                or

                round(
                    prev.get("draw_odd", 0),
                    3
                )
                != round(c2, 3)

                or

                round(
                    prev.get("away_odd", 0),
                    3
                )
                != round(c3, 3)
            )


            # =================================================
            # DETECTAR CAMBIO DE CATEGORÍA
            # =================================================

            categoria_anterior = prev.get(
                "categoria"
            )

            cambio_categoria = (
                categoria_anterior != categoria
            )


            # =================================================
            # ENVIAR SI CAMBIÓ ALGUNA CUOTA
            # O CAMBIÓ DE CATEGORÍA
            # =================================================

            if cambio or cambio_categoria:

                enviar_alerta_armada(
                    liga,
                    p,
                    margen_jugador,
                    categoria
                )


    guardar_json(
        ESTADO_FILE,
        estado_new
    )


    print(
        "✔ smart_alerts ejecutado correctamente."
    )


if __name__ == "__main__":
    procesar_alertas()