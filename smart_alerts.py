# smart_alerts.py
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

# ================================================================
# CONFIGURACIÓN
# ================================================================

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
CUOTAS_FILE = os.path.join(DATA_DIR, "cuotas.json")
ESTADO_FILE = os.path.join(DATA_DIR, "ultimo_estado_alertas.json")

# Bot Telegram
TELEGRAM_TOKEN = os.getenv("SMART_BOT_TOKEN")
CHAT_ID = int(os.getenv("SMART_BOT_CHAT_ID"))
CHAT_IDS = [
    int(os.getenv("SMART_BOT_CHAT_ID_1")),
    int(os.getenv("SMART_BOT_CHAT_ID_2")),
]
CHAT_IDS = [cid for cid in CHAT_IDS if cid]   # limpia nulos

# UMBRAL → ALARMAR SI margen_jugador >= -1.25%
UMBRAL_JUGADOR = -1.25   # -1.25%


# ================================================================
# UTILIDADES
# ================================================================

def enviar_alerta(mensaje: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for cid in CHAT_IDS:
    payload = {
        "chat_id": cid,
        "text": msg,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        if not r.ok:
            print(f"❌ Error Telegram {r.status_code}: {r.text}")
    except Exception as e:
        print(f"❌ Excepción enviando Telegram: {e}")


def calcular_margen(c1: float, c2: float, c3: float):
    try:
        return (1/c1 + 1/c2 + 1/c3) * 100 - 100
    except:
        return None


def cargar_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def guardar_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def generar_clave(liga, fecha, home, away):
    return f"{liga} | {fecha} | {home} vs {away}"


# ================================================================
# 🔄 CONVERTIR FECHA UTC → AMERICA/LIMA
# ================================================================

def convertir_a_lima(fecha_str):
    """
    Entrada viene así:  '2025-11-27 17:45 UTC'
    """
    try:
        fecha_str = fecha_str.replace(" UTC", "")
        dt_utc = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M")
        dt_utc = dt_utc.replace(tzinfo=ZoneInfo("UTC"))
        dt_lima = dt_utc.astimezone(ZoneInfo("America/Lima"))
        return dt_lima.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return fecha_str  # fallback


# ================================================================
# ALERTAS INTELIGENTES
# ================================================================

def procesar_alertas():
    if not os.path.exists(CUOTAS_FILE):
        print(f"❌ No existe {CUOTAS_FILE}")
        return

    with open(CUOTAS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    estado_prev = cargar_json(ESTADO_FILE, default={})
    estado_new = {}

    ahora = datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d %H:%M:%S")

    for liga, partidos in data.items():
        if liga == "metadata":
            continue
        if not isinstance(partidos, list):
            continue

        for p in partidos:

            home = p.get("home")
            away = p.get("away")
            fecha = p.get("date", "")

            bh = p.get("best_home") or {}
            bd = p.get("best_draw") or {}
            ba = p.get("best_away") or {}

            c1 = bh.get("odd")
            c2 = bd.get("odd")
            c3 = ba.get("odd")

            if c1 is None or c2 is None or c3 is None:
                continue

            try:
                c1 = float(c1)
                c2 = float(c2)
                c3 = float(c3)
            except:
                continue

            margen_real = calcular_margen(c1, c2, c3)
            if margen_real is None:
                continue

            margen_jugador = -1 * margen_real

            clave = generar_clave(liga, fecha, home, away)

            estado_actual = {
                "home_odd": c1,
                "draw_odd": c2,
                "away_odd": c3,
                "margen_jugador": margen_jugador,
                "ultima_actualizacion": ahora,
            }
            estado_new[clave] = estado_actual

            if margen_jugador < UMBRAL_JUGADOR:
                continue

            prev = estado_prev.get(clave)

            if prev is None:
                enviar_alerta_armada(liga, p, margen_jugador)
                estado_actual["alert_enviada"] = True
                continue

            cambio_cuotas = (
                round(prev.get("home_odd", 0), 3) != round(c1, 3) or
                round(prev.get("draw_odd", 0), 3) != round(c2, 3) or
                round(prev.get("away_odd", 0), 3) != round(c3, 3)
            )

            cruce_umbral = (
                prev.get("margen_jugador", -999) < UMBRAL_JUGADOR
                and margen_jugador >= UMBRAL_JUGADOR
            )

            if cambio_cuotas or cruce_umbral:
                enviar_alerta_armada(liga, p, margen_jugador)
                estado_actual["alert_enviada"] = True

    guardar_json(ESTADO_FILE, estado_new)
    print(f"✔ smart_alerts ejecutado correctamente.")


# ================================================================
# ENVÍO DE MENSAJE
# ================================================================

def enviar_alerta_armada(liga, p, margen_jugador):
    home = p.get("home")
    away = p.get("away")
    fecha_utc = p.get("date")
    fecha_lima = convertir_a_lima(fecha_utc)

    bh = p.get("best_home") or {}
    bd = p.get("best_draw") or {}
    ba = p.get("best_away") or {}

    msg = f"""
⚠️ <b>ALERTA SMART (-1% o mejor)</b>

<b>{home} vs {away}</b>
Liga: <b>{liga}</b>
Fecha: <b>{fecha_lima} (GMT-5)</b>

Margen combinado: <b>{margen_jugador:.2f}%</b>

Cuotas máximas:
🏠 Local: <b>{bh.get("odd")}</b> ({bh.get("bookmaker")})
🤝 Empate: <b>{bd.get("odd")}</b> ({bd.get("bookmaker")})
🚶 Visita: <b>{ba.get("odd")}</b> ({ba.get("bookmaker")})
"""

    print(f"[ALERTA] {home} vs {away} | margen {margen_jugador:.2f}%")
    enviar_alerta(msg.strip())


# ================================================================
if __name__ == "__main__":
    procesar_alertas()