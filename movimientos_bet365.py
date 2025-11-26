# movimientos_bet365.py
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

# ================================================================
# CONFIGURACIÓN DEL BOT DE MOVIMIENTOS
# ================================================================
TELEGRAM_TOKEN = "8410540459:AAGSji8uIRoNb1J8L1x9LW27PYVCq0674EM"
CHAT_ID = 1925286468

# Umbral del movimiento brusco (5%)
MOVIMIENTO_UMBRAL = 0.05    # 5%

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
HIST_DIR = os.path.join(DATA_DIR, "historico_bet365")


# ================================================================
# UTILIDADES
# ================================================================
def enviar_alerta(mensaje: str):
    """Enviar mensaje al bot de movimientos bruscos."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML"
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        if not r.ok:
            print(f"❌ Error Telegram {r.status_code}: {r.text}")
    except Exception as e:
        print(f"❌ Error enviando Telegram: {e}")


def cargar_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


# ================================================================
# PROCESO PRINCIPAL
# ================================================================
def detectar_movimientos_bet365():

    # Archivo del día actual
    fecha = datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d")
    archivo = os.path.join(HIST_DIR, f"{fecha}.json")

    if not os.path.exists(archivo):
        print("❌ No existe histórico Bet365 hoy.")
        return

    historico = cargar_json(archivo, default={})
    ultimo = historico.get("ULTIMO", {})

    # Buscar el snapshot previo al último
    # (El penúltimo para comparar correctamente)
    timestamps = [t for t in historico.keys() if t != "ULTIMO"]
    if len(timestamps) < 2:
        print("No hay suficiente histórico para detectar movimientos.")
        return

    timestamps_sorted = sorted(timestamps)
    anterior_key = timestamps_sorted[-2]
    anterior = historico.get(anterior_key, {})

    # Comparación
    for partido, cuotas_nuevas in ultimo.items():

        cuotas_antes = anterior.get(partido)
        if not cuotas_antes:
            continue

        # --- extracción de cuotas ---
        l1 = cuotas_antes.get("local")
        e1 = cuotas_antes.get("empate")
        v1 = cuotas_antes.get("visita")

        l2 = cuotas_nuevas.get("local")
        e2 = cuotas_nuevas.get("empate")
        v2 = cuotas_nuevas.get("visita")

        if None in [l1, e1, v1, l2, e2, v2]:
            continue

        # --- calcular movimientos ---
        def variacion(a, b):
            try:
                return (b - a) / a
            except:
                return 0

        mov_local = variacion(l1, l2)
        mov_empate = variacion(e1, e2)
        mov_visita = variacion(v1, v2)

        # --- DETECCIÓN DE MOVIMIENTOS BRUSCOS ---
        if abs(mov_local) >= MOVIMIENTO_UMBRAL:
            enviar_alerta(formato_alerta(partido, "Local", l1, l2, mov_local))

        if abs(mov_empate) >= MOVIMIENTO_UMBRAL:
            enviar_alerta(formato_alerta(partido, "Empate", e1, e2, mov_empate))

        if abs(mov_visita) >= MOVIMIENTO_UMBRAL:
            enviar_alerta(formato_alerta(partido, "Visita", v1, v2, mov_visita))

    print("✔ Movimientos revisados correctamente.")


# ================================================================
# FORMATO DE ALERTA
# ================================================================
def formato_alerta(partido, mercado, antes, despues, var):
    porc = round(var * 100, 2)
    fecha = datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d %H:%M:%S")

    flecha = "📉" if var < 0 else "📈"

    return f"""
🔥 <b>MOVIMIENTO BRUSCO BET365 (+/-5%)</b>

<b>{partido}</b>
Mercado: <b>{mercado}</b>

{flecha} Cambio: <b>{antes} → {despues}</b>
Variación: <b>{porc}%</b>

⏱ {fecha}
"""


# ================================================================
if __name__ == "__main__":
    detectar_movimientos_bet365()
