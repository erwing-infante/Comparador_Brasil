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

# UMBRAL → ALARMAR SI margen_jugador >= -1%
UMBRAL_JUGADOR = -1.0   # -1%


# ================================================================
# UTILIDADES
# ================================================================

def enviar_alerta(mensaje: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        if not r.ok:
            print(f"❌ Error Telegram {r.status_code}: {r.text}")
    except Exception as e:
        print(f"❌ Excepción enviando Telegram: {e}")


def calcular_margen(c1: float, c2: float, c3: float):
    """
    Margen real del mercado (positivo = mala para jugador).
    """
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
# ALERTAS INTELIGENTES
# ================================================================

def procesar_alertas():
    # 1) Leer cuotas.json
    if not os.path.exists(CUOTAS_FILE):
        print(f"❌ No existe {CUOTAS_FILE}")
        return

    with open(CUOTAS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 2) Estado previo de cuotas (para detectar cambios)
    estado_prev = cargar_json(ESTADO_FILE, default={})
    estado_new = {}

    ahora = datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d %H:%M:%S")

    # 3) Recorrer todas las ligas
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

            # ==== 4) MARGEN REAL + MARGEN JUGADOR ====
            margen_real = calcular_margen(c1, c2, c3)
            if margen_real is None:
                continue

            # Margen que muestras en la web (invertido)
            margen_jugador = -1 * margen_real

            clave = generar_clave(liga, fecha, home, away)

            # Guardar estado nuevo
            estado_actual = {
                "home_odd": c1,
                "draw_odd": c2,
                "away_odd": c3,
                "margen_jugador": margen_jugador,
                "ultima_actualizacion": ahora,
            }
            estado_new[clave] = estado_actual

            # =====================================================
            # 🔥 CONDICIÓN PARA ALERTAR:
            #
            # margen_jugador >= -1%
            #
            # Ejemplos que SÍ alertan:
            # -0.99%
            # -0.50%
            #  0.00%
            # +0.50%
            # +1.00%
            # +10%
            #
            # =====================================================
            if margen_jugador < UMBRAL_JUGADOR:
                continue

            prev = estado_prev.get(clave)

            # 1) Primera vez que aparece
            if prev is None:
                enviar_alerta_armada(liga, p, margen_jugador)
                estado_actual["alert_enviada"] = True
                continue

            # 2) Detectar cambio en cuotas
            cambio_cuotas = (
                round(prev.get("home_odd", 0), 3) != round(c1, 3) or
                round(prev.get("draw_odd", 0), 3) != round(c2, 3) or
                round(prev.get("away_odd", 0), 3) != round(c3, 3)
            )

            # 3) Detectar cruce hacia el umbral
            cruce_umbral = (
                prev.get("margen_jugador", -999) < UMBRAL_JUGADOR
                and margen_jugador >= UMBRAL_JUGADOR
            )

            if cambio_cuotas or cruce_umbral:
                enviar_alerta_armada(liga, p, margen_jugador)
                estado_actual["alert_enviada"] = True

    # 5) Guardar estado actualizado
    guardar_json(ESTADO_FILE, estado_new)
    print(f"✔ smart_alerts ejecutado correctamente.")


# ================================================================
# ENVÍO DE MENSAJE
# ================================================================

def enviar_alerta_armada(liga, p, margen_jugador):
    home = p.get("home")
    away = p.get("away")
    fecha = p.get("date")

    bh = p.get("best_home") or {}
    bd = p.get("best_draw") or {}
    ba = p.get("best_away") or {}

    msg = f"""
⚠️ <b>ALERTA SMART (-1% o mejor)</b>

<b>{home} vs {away}</b>
Liga: <b>{liga}</b>
Fecha: <b>{fecha}</b>

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
