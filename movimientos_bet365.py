import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

# ================================================================
# CONFIG
# ================================================================
TELEGRAM_TOKEN = os.getenv("MOV_BOT_TOKEN")

def env_int(name: str):
    v = os.getenv(name)
    if not v:
        return None
    try:
        return int(v)
    except:
        return None

CHAT_IDS = [env_int("MOV_BOT_CHAT_ID_1"), env_int("MOV_BOT_CHAT_ID_2")]
CHAT_IDS = [x for x in CHAT_IDS if x is not None]

MOVIMIENTO_UMBRAL = 0.04  # 4%
MAX_HORAS_ADELANTE = 36.0  # ventana de alertas

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
HIST_DIR = os.path.join(DATA_DIR, "historico_bet365")
CUOTAS_FILE = os.path.join(DATA_DIR, "cuotas.json")


# ================================================================
# UTILIDADES
# ================================================================
def enviar_alerta(mensaje: str):
    if not TELEGRAM_TOKEN or not CHAT_IDS:
        print("❌ Faltan MOV_BOT_TOKEN o MOV_BOT_CHAT_ID_1/2 (en systemd o en tu shell).")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    for cid in CHAT_IDS:
        payload = {"chat_id": cid, "text": mensaje, "parse_mode": "HTML"}
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


def parse_fecha_a_lima(fecha_str: str):
    """
    Soporta formatos de tu cuotas.json y otros:
    - '2025-11-27 17:45 UTC'
    - '2025-11-27 17:45:00 UTC'
    - '2026-01-15T03:06:00.000'
    - '2026-01-15T03:06:00'
    - '2026-01-15 03:06:00.000'
    - con o sin 'Z'
    Asume UTC cuando no hay zona.
    """
    if not fecha_str or not isinstance(fecha_str, str):
        return None

    s = fecha_str.strip()
    s = s.replace(" UTC", "").strip()
    if s.endswith("Z"):
        s = s[:-1]

    fmts = [
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]

    for fmt in fmts:
        try:
            dt_utc = datetime.strptime(s, fmt).replace(tzinfo=ZoneInfo("UTC"))
            return dt_utc.astimezone(ZoneInfo("America/Lima"))
        except:
            pass

    return None


def dentro_ventana_partido(fecha_str: str, ahora_lima: datetime) -> bool:
    dt_lima = parse_fecha_a_lima(fecha_str)
    if dt_lima is None:
        return False
    horas = (dt_lima - ahora_lima).total_seconds() / 3600.0
    return 0 <= horas <= MAX_HORAS_ADELANTE


def obtener_fecha_partido_desde_cuotas(partido: str):
    """
    Busca el partido 'home vs away' del histórico bet365 en data/cuotas.json
    y retorna p['date'].
    """
    data = cargar_json(CUOTAS_FILE, default={})
    if not data:
        return None

    for liga, partidos in data.items():
        if liga == "metadata":
            continue
        if not isinstance(partidos, list):
            continue

        for p in partidos:
            home = (p.get("home") or "").strip().lower()
            away = (p.get("away") or "").strip().lower()
            if partido.strip().lower() == f"{home} vs {away}":
                return p.get("date", None)

    return None


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
<b>VARIACIÓN:</b> <code>{porc}%</code> {flecha}

⏱ {fecha}
""".strip()


# ================================================================
# PROCESO PRINCIPAL
# ================================================================
def detectar_movimientos_bet365():
    fecha_hoy = datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d")
    archivo = os.path.join(HIST_DIR, f"{fecha_hoy}.json")

    if not os.path.exists(archivo):
        print("❌ No existe histórico Bet365 hoy.")
        return

    historico = cargar_json(archivo, default={})
    ultimo = historico.get("ULTIMO", {})

    timestamps = [t for t in historico.keys() if t != "ULTIMO"]
    if len(timestamps) < 2:
        print("No hay suficiente histórico para detectar movimientos.")
        return

    anterior_key = sorted(timestamps)[-2]
    anterior = historico.get(anterior_key, {})

    ahora_lima_dt = datetime.now(ZoneInfo("America/Lima"))
    ahora_str = ahora_lima_dt.strftime("%Y-%m-%d %H:%M:%S")

    for partido, cuotas_nuevas in ultimo.items():
        # ✅ filtro 36h
        fecha_partido = obtener_fecha_partido_desde_cuotas(partido)
        if not fecha_partido:
            continue
        if not dentro_ventana_partido(fecha_partido, ahora_lima_dt):
            continue

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

        if abs(mov_local) >= MOVIMIENTO_UMBRAL:
            enviar_alerta(formato_alerta(partido, "Local", l1, l2, mov_local, ahora_str))
        if abs(mov_empate) >= MOVIMIENTO_UMBRAL:
            enviar_alerta(formato_alerta(partido, "Empate", e1, e2, mov_empate, ahora_str))
        if abs(mov_visita) >= MOVIMIENTO_UMBRAL:
            enviar_alerta(formato_alerta(partido, "Visita", v1, v2, mov_visita, ahora_str))

    print("✔ Movimientos revisados correctamente.")


if __name__ == "__main__":
    detectar_movimientos_bet365()
