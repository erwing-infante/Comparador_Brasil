# movimientos_bet365.py
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

# ================================================================
# CONFIGURACIÓN DEL BOT DE MOVIMIENTOS
# ================================================================

TELEGRAM_TOKEN = os.getenv("MOV_BOT_TOKEN")

# Múltiples chat IDs
CHAT_IDS = [
    int(os.getenv("MOV_BOT_CHAT_ID_1")),
    int(os.getenv("MOV_BOT_CHAT_ID_2")),
]

MOVIMIENTO_UMBRAL = 0.04  # 4%

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
HIST_DIR = os.path.join(DATA_DIR, "historico_bet365")


# ================================================================
# UTILIDADES
# ================================================================
def enviar_alerta(mensaje: str):
    """Envia mensaje a TODOS los suscriptores."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    for cid in CHAT_IDS:
        if not cid:
            continue

        payload = {
            "chat_id": cid,
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
# FORMATO DE ALERTA
# ================================================================
def formato_alerta(partido, mercado, antes, despues, var, fecha):
    porc = round(var * 100, 2)
    flecha = "📉" if var < 0 else "📈"

    return f"""
🔥 <b>MOVIMIENTO BRUSCO BET365 (+/-4%)</b>

<b>{partido}</b>
<b>MERCADO AFECTADO:</b> <code>{mercado.upper()}</code>
<b>CAMBIO:</b> <code>{antes} → {despues}</code>
<b>VARIACIÓN:</b> <code>{porc}%</code>

⏱ {fecha}
"""


# ================================================================
# PROCESO PRINCIPAL
# ================================================================
def detectar_movimientos_bet365():

    fecha = datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d")
    archivo = os.path.join(HIST_DIR, f"{fecha}.json")

    if not os.path.exists(archivo):
        print("❌ No existe histórico Bet365 hoy.")
        return

    historico = cargar_json(archivo, default={})
    ultimo = historico.get("ULTIMO", {})

    timestamps = [t for t in historico.keys() if t != "ULTIMO"]
    if len(timestamps) < 2:
        print("No hay suficiente histórico para detectar movimientos.")
        return

    timestamps_sorted = sorted(timestamps)
    anterior_key = timestamps_sorted[-2]
    anterior = historico.get(anterior_key, {})

    ahora = datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d %H:%M:%S")

    # Comparación de cuotas
    for partido, cuotas_nuevas in ultimo.items():

        cuotas_antes = anterior.get(partido)
        if not cuotas_antes:
            continue

        l1, e1, v1 = cuotas_antes.get("local"), cuotas_antes.get("empate"), cuotas_antes.get("visita")
        l2, e2, v2 = cuotas_nuevas.get("local"), cuotas_nuevas.get("empate"), cuotas_nuevas.get("visita")

        if None in [l1, e1, v1, l2, e2, v2]:
            continue

        def variacion(a, b):
            try:
                return (b - a) / a
            except:
                return 0

        mov_local = variacion(l1, l2)
        mov_empate = variacion(e1, e2)
        mov_visita = variacion(v1, v2)

        # Enviar alertas
        if abs(mov_local) >= MOVIMIENTO_UMBRAL:
            enviar_alerta(formato_alerta(partido, "Local", l1, l2, mov_local, ahora))

        if abs(mov_empate) >= MOVIMIENTO_UMBRAL:
            enviar_alerta(formato_alerta(partido, "Empate", e1, e2, mov_empate, ahora))

        if abs(mov_visita) >= MOVIMIENTO_UMBRAL:
            enviar_alerta(formato_alerta(partido, "Visita", v1, v2, mov_visita, ahora))

    print("✔ Movimientos revisados correctamente.")


# ================================================================
if __name__ == "__main__":
    detectar_movimientos_bet365()
