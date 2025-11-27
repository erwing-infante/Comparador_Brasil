# movimientos_bet365.py
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

# ================================
# CONFIG
# ================================
TELEGRAM_TOKEN = os.getenv("MOV_BOT_TOKEN")
CHAT_IDS = [
    int(os.getenv("MOV_BOT_CHAT_ID_1")),
    int(os.getenv("MOV_BOT_CHAT_ID_2")),
]
CHAT_IDS = [cid for cid in CHAT_IDS if cid]   # limpia nulos

MOVIMIENTO_UMBRAL = 0.04   # 4%

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
HIST_DIR = os.path.join(DATA_DIR, "historico_bet365")
CUOTAS_FILE = os.path.join(DATA_DIR, "cuotas.json")

# importar equivalencias
from equivalencias_equipos import EQUIVALENCIAS_EQUIPOS


# ================================================================
# UTILIDADES
# ================================================================
def enviar_alerta(msg: str):
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
            print("❌ Error Telegram:", r.text)
    except Exception as e:
        print("❌ Excepción enviando Telegram:", e)


def cargar_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


# ================================================================
# NORMALIZADOR: usa exactamente las mismas reglas del fusionador
# ================================================================
def normalizar_bet365_equipo(nombre: str) -> str:
    if not isinstance(nombre, str):
        return ""
    lookup = nombre.lower().strip()
    return EQUIVALENCIAS_EQUIPOS.get(lookup, nombre)


# ================================================================
# BUSCAR PARTIDO EN CUOTAS.JSON
# ================================================================
def buscar_en_cuotas(home, away):
    if not os.path.exists(CUOTAS_FILE):
        return None

    with open(CUOTAS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for liga, partidos in data.items():
        if liga == "metadata":
            continue

        for p in partidos:
            if p.get("home") == home and p.get("away") == away:
                return liga, p

    return None


# ================================================================
# ALERTA FORMATEADA
# ================================================================
def armar_alerta(
    home, away, liga, fecha_partido,
    mercado, antes, despues, var,
    margen, bh, bd, ba, timestamp
):
    porc = round(var * 100, 2)
    flecha = "📉" if var < 0 else "📈"

    return f"""
🔥 <b>MOVIMIENTO BRUSCO BET365 (+/-4%)</b>

<b>{home} vs {away}</b>
Liga: <b>{liga}</b>
Hora del partido (GMT-5): <b>{fecha_partido}</b>

<code>
MERCADO:   {mercado}
CAMBIO:    {antes} → {despues}
VARIACIÓN: {porc}%
</code>

<b>Cuotas máximas actuales:</b>
🏠 Local: <b>{bh.get("odd")}</b> ({bh.get("bookmaker")})
🤝 Empate: <b>{bd.get("odd")}</b> ({bd.get("bookmaker")})
🚶 Visita: <b>{ba.get("odd")}</b> ({ba.get("bookmaker")})

📊 Margen combinado: <b>{margen:.2f}%</b>
⏱ {timestamp}
""".strip()


# ================================================================
# PROCESO PRINCIPAL
# ================================================================
def detectar_movimientos_bet365():

    hoy = datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d")
    archivo = os.path.join(HIST_DIR, f"{hoy}.json")

    if not os.path.exists(archivo):
        print("❌ No existe histórico Bet365.")
        return

    historico = cargar_json(archivo, default={})
    ultimo = historico.get("ULTIMO", {})

    # debe haber mínimo dos snapshots
    timestamps = [t for t in historico.keys() if t != "ULTIMO"]
    if len(timestamps) < 2:
        print("No hay suficiente histórico.")
        return

    ts_sorted = sorted(timestamps)
    anterior_key = ts_sorted[-2]
    anterior = historico.get(anterior_key, {})

    # comparar
    for partido_raw, cuotas_new in ultimo.items():

        cuotas_old = anterior.get(partido_raw)
        if not cuotas_old:
            continue

        l1, e1, v1 = cuotas_old.get("local"), cuotas_old.get("empate"), cuotas_old.get("visita")
        l2, e2, v2 = cuotas_new.get("local"), cuotas_new.get("empate"), cuotas_new.get("visita")

        if None in [l1, e1, v1, l2, e2, v2]:
            continue

        # variación
        def var(a, b):
            try: return (b - a) / a
            except: return 0

        cambios = {
            "Local":  var(l1, l2),
            "Empate": var(e1, e2),
            "Visita": var(v1, v2)
        }

        # pasar por equivalencias (nombre limpio)
        home_raw, away_raw = partido_raw.split(" vs ")
        home = normalizar_bet365_equipo(home_raw)
        away = normalizar_bet365_equipo(away_raw)

        # buscar partido en cuotas.json
        res = buscar_en_cuotas(home, away)
        if not res:
            continue

        liga, p = res

        # obtener info
        fecha_partido = p.get("date")
        bh = p.get("best_home") or {}
        bd = p.get("best_draw") or {}
        ba = p.get("best_away") or {}

        # margen real
        try:
            c1, c2, c3 = float(bh["odd"]), float(bd["odd"]), float(ba["odd"])
            margen_real = (1/c1 + 1/c2 + 1/c3) * 100 - 100
            margen_jug = -margen_real
        except:
            margen_jug = 0

        timestamp = datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d %H:%M:%S")

        # enviar alertas solo si cruza el umbral
        for mercado, variacion in cambios.items():
            if abs(variacion) >= MOVIMIENTO_UMBRAL:

                antes = cuotas_old["local"] if mercado == "Local" else (
                        cuotas_old["empate"] if mercado == "Empate" else cuotas_old["visita"]
                )
                despues = cuotas_new["local"] if mercado == "Local" else (
                        cuotas_new["empate"] if mercado == "Empate" else cuotas_new["visita"]
                )

                msg = armar_alerta(
                    home, away, liga, fecha_partido,
                    mercado, antes, despues, variacion,
                    margen_jug, bh, bd, ba,
                    timestamp
                )

                enviar_alerta(msg)

    print("✔ Movimientos revisados correctamente.")


# ================================================================
if __name__ == "__main__":
    detectar_movimientos_bet365()
