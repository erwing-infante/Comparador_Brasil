# movimientos_bet365.py
import os
import json
import time
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
from difflib import SequenceMatcher

from equivalencias_equipos import EQUIVALENCIAS_EQUIPOS

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
MAX_HORAS_ADELANTE = 36.0

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
HIST_DIR = os.path.join(DATA_DIR, "historico_bet365")
CUOTAS_JSON = os.path.join(DATA_DIR, "cuotas.json")

ERROR_LOG = os.path.join(DATA_DIR, "error_movimientos_bet365.txt")
ESTADO_MOV_FILE = os.path.join(DATA_DIR, "ultimo_estado_movimientos.json")


# ---------------- JSON / LOG ----------------
def log_error(msg: str):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ERROR_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except:
        pass

def cargar_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def guardar_json_atomico(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def cargar_estado_mov():
    return cargar_json(ESTADO_MOV_FILE, default={"sent": [], "last_ts": ""})

def firma_alerta(partido_key: str, mercado: str, antes: float, despues: float) -> str:
    try:
        a = round(float(antes), 4)
        b = round(float(despues), 4)
    except:
        a = antes
        b = despues
    return f"{partido_key}::{mercado}::{a}->{b}"


# ---------------- Telegram ----------------
def enviar_alerta(mensaje: str):
    if not TELEGRAM_TOKEN or not CHAT_IDS:
        print("❌ Faltan MOV_BOT_TOKEN o MOV_BOT_CHAT_ID_1/2 (systemd/env).")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for cid in CHAT_IDS:
        payload = {"chat_id": cid, "text": mensaje, "parse_mode": "HTML"}
        try:
            r = requests.post(url, data=payload, timeout=10)
            if not r.ok:
                print(f"❌ Error Telegram {r.status_code}: {r.text[:200]}")
        except Exception as e:
            print(f"❌ Error enviando Telegram: {e}")


# ---------------- Normalización (igual idea fusionador) ----------------
STOP_TOKENS = {
    "fc", "cf", "sc", "ec", "ac",
    "cd", "ca",  # importante para casos como "cd guadalajara"
    "u19", "u20", "u21", "u23",
    "de", "the", "club",
    "sa", "sp", "mg", "ba", "ce", "rj", "rs"
}

def quitar_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def similitud(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def limpiar_equipo(nombre: str) -> str:
    if not isinstance(nombre, str):
        return ""

    original = nombre.strip()
    lookup = quitar_acentos(original).lower().strip()

    if lookup in EQUIVALENCIAS_EQUIPOS:
        return EQUIVALENCIAS_EQUIPOS[lookup]

    for key in EQUIVALENCIAS_EQUIPOS:
        if similitud(lookup, key) >= 0.88:
            return EQUIVALENCIAS_EQUIPOS[key]

    limpio = quitar_acentos(original).lower()
    for bad in ["t/t", "t//t", "//", "/", "\\", "\t", "\n", "|"]:
        limpio = limpio.replace(bad, " ")
    limpio = " ".join(limpio.split()).strip()

    tokens = [t for t in limpio.split() if t not in STOP_TOKENS]
    fallback = " ".join(tokens).strip()

    if fallback in EQUIVALENCIAS_EQUIPOS:
        return EQUIVALENCIAS_EQUIPOS[fallback]

    for key in EQUIVALENCIAS_EQUIPOS:
        if similitud(fallback, key) >= 0.88:
            return EQUIVALENCIAS_EQUIPOS[key]

    return fallback or original

def team_short(name: str) -> str:
    limpio = limpiar_equipo(name)
    if not limpio:
        return "desconocido"
    tokens = [t for t in limpio.split() if t not in STOP_TOKENS]
    if not tokens:
        return "desconocido"
    return max(tokens, key=len)

def split_vs(partido: str):
    if not isinstance(partido, str):
        return ("", "")
    p = " ".join(partido.strip().lower().split())
    if " vs " in p:
        a, b = p.split(" vs ", 1)
        return (a.strip(), b.strip())
    return ("", "")


# ---------------- Fechas ----------------
def parse_fecha_utc_a_lima(fecha_str: str):
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

def dentro_ventana(fecha_partido_str: str, ahora_lima_dt: datetime) -> bool:
    dt_lima = parse_fecha_utc_a_lima(fecha_partido_str)
    if dt_lima is None:
        return False
    horas = (dt_lima - ahora_lima_dt).total_seconds() / 3600.0
    return 0 <= horas <= MAX_HORAS_ADELANTE


# ---------------- cuotas.json candidatos ----------------
def construir_index_cuotas_json():
    data = cargar_json(CUOTAS_JSON, default={})
    candidatos = []
    if not isinstance(data, dict):
        return candidatos

    for liga, partidos in data.items():
        if liga == "metadata":
            continue
        if not isinstance(partidos, list):
            continue

        for p in partidos:
            home = (p.get("home") or "").strip()
            away = (p.get("away") or "").strip()
            date = (p.get("date") or "").strip()

            if not home or not away:
                continue

            candidatos.append({
                "liga": liga,
                "date": date,
                "home": home,
                "away": away,
                "home_short": team_short(home),
                "away_short": team_short(away),
                "name": p.get("name") or f"{home} vs {away}",
                "best_home": p.get("best_home") or {},
                "best_draw": p.get("best_draw") or {},
                "best_away": p.get("best_away") or {},
            })
    return candidatos


def encontrar_partido_en_cuotas(partido_hist_key: str, candidatos: list):
    """
    Match usando equivalencias+similitud ANTES de comparar (igual idea fusionador).
    Retorna (match, in_window) para que el main decida si alerta o no.
    """
    h_raw, a_raw = split_vs(partido_hist_key)
    if not h_raw or not a_raw:
        return (None, False)

    # Canoniza histórico con equivalencias + similitud (la clave del fix)
    h_canon = limpiar_equipo(h_raw)
    a_canon = limpiar_equipo(a_raw)

    h_short = team_short(h_canon)
    a_short = team_short(a_canon)

    best = None
    best_score = -1.0

    for c in candidatos:
        sh = similitud(h_short, c["home_short"])
        sa = similitud(a_short, c["away_short"])
        score = (sh + sa) / 2.0

        if score < 0.60:
            continue

        if score > best_score:
            best = c
            best_score = score

    if not best:
        return (None, False)

    # ventana se calcula fuera (para no forzar fallback)
    return (best, True)


# ---------------- Mensajes ----------------
def fmt_best(label: str, obj: dict) -> str:
    odd = obj.get("odd")
    bm = obj.get("bookmaker") or "-"
    if odd is None or odd == "":
        return f"• <b>{label}:</b> -"
    return f"• <b>{label}:</b> {odd} — <b>{bm}</b>"

def formato_alerta_completo(match: dict, mercado: str, antes: float, despues: float, var: float, hora_alerta: str):
    porc = round(var * 100, 2)
    flecha = "📉" if var < 0 else "📈"

    liga = match.get("liga") or "(no encontrada)"
    fecha_partido_str = match.get("date") or ""
    dt_lima = parse_fecha_utc_a_lima(fecha_partido_str) if fecha_partido_str else None
    fecha_partido_txt = dt_lima.strftime("%Y-%m-%d %H:%M") + " (Perú)" if dt_lima else (fecha_partido_str or "(no encontrada)")

    return (
        f"🔥 <b>MOVIMIENTO BRUSCO BET365 (+/-4%)</b>\n\n"
        f"<b>{match.get('name') or (match.get('home','') + ' vs ' + match.get('away',''))}</b>\n"
        f"<b>Liga:</b> {liga}\n"
        f"<b>Fecha:</b> {fecha_partido_txt}\n\n"
        f"<b>MOVIMIENTO (Bet365)</b>\n"
        f"• <b>Mercado:</b> {mercado.upper()}\n"
        f"• <b>Cambio:</b> {antes} → {despues}\n"
        f"• <b>Variación:</b> {porc}% {flecha}\n\n"
        f"<b>MEJOR 1X2 ACTUAL</b>\n"
        f"{fmt_best('Local', match.get('best_home') or {})}\n"
        f"{fmt_best('Empate', match.get('best_draw') or {})}\n"
        f"{fmt_best('Visita', match.get('best_away') or {})}\n\n"
        f"⏱ <code>{hora_alerta}</code> (hora alerta)"
    )

def formato_alerta_fallback(partido_key: str, mercado: str, antes: float, despues: float, var: float, hora_alerta: str):
    porc = round(var * 100, 2)
    flecha = "📉" if var < 0 else "📈"
    return (
        f"🔥 <b>MOVIMIENTO BRUSCO BET365 (+/-4%)</b>\n\n"
        f"<b>{partido_key}</b>\n"
        f"<b>Liga:</b> (no encontrada)\n"
        f"<b>Fecha:</b> (no encontrada)\n\n"
        f"<b>MOVIMIENTO (Bet365)</b>\n"
        f"• <b>Mercado:</b> {mercado.upper()}\n"
        f"• <b>Cambio:</b> {antes} → {despues}\n"
        f"• <b>Variación:</b> {porc}% {flecha}\n\n"
        f"<b>MEJOR 1X2 ACTUAL</b>\n"
        f"• <b>Local:</b> -\n"
        f"• <b>Empate:</b> -\n"
        f"• <b>Visita:</b> -\n\n"
        f"⏱ <code>{hora_alerta}</code> (hora alerta)"
    )


# ================================================================
# MAIN
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

    estado = cargar_estado_mov()
    enviadas = set(estado.get("sent", []))

    candidatos = construir_index_cuotas_json()

    total_enviadas = 0

    for partido_key, cuotas_nuevas in ultimo.items():
        cuotas_antes = anterior.get(partido_key)
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

        movimientos = []
        if abs(mov_local) >= MOVIMIENTO_UMBRAL:
            movimientos.append(("LOCAL", l1, l2, mov_local))
        if abs(mov_empate) >= MOVIMIENTO_UMBRAL:
            movimientos.append(("EMPATE", e1, e2, mov_empate))
        if abs(mov_visita) >= MOVIMIENTO_UMBRAL:
            movimientos.append(("VISITA", v1, v2, mov_visita))

        if not movimientos:
            continue

        match, _ = encontrar_partido_en_cuotas(partido_key, candidatos)

        # ✅ Si hay match pero está fuera de 36h -> NO alertar
        if match and match.get("date"):
            if not dentro_ventana(match["date"], ahora_lima_dt):
                continue

        for mercado, antes, despues, var in movimientos:
            sig = firma_alerta(partido_key, mercado, antes, despues)
            if sig in enviadas:
                continue

            if match:
                msg = formato_alerta_completo(match, mercado, antes, despues, var, ahora_str)
            else:
                # ✅ fallback solo si NO hay match (no podemos conocer fecha)
                msg = formato_alerta_fallback(partido_key, mercado, antes, despues, var, ahora_str)

            enviar_alerta(msg)
            enviadas.add(sig)
            total_enviadas += 1

    sent_list = list(enviadas)
    if len(sent_list) > 2000:
        sent_list = sent_list[-2000:]

    estado_out = {
        "last_ts": sorted(timestamps)[-1] if timestamps else "",
        "sent": sent_list
    }
    guardar_json_atomico(ESTADO_MOV_FILE, estado_out)

    print(f"✔ Movimientos revisados correctamente. Alertas nuevas: {total_enviadas}")


if __name__ == "__main__":
    detectar_movimientos_bet365()
