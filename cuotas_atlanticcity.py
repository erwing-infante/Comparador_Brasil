import requests
import pandas as pd
import time
import random
import os
import re
import json
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

# === CONFIGURACIÓN ===
OUT_DIR = "data"
os.makedirs(OUT_DIR, exist_ok=True)
ERROR_LOG = os.path.join(OUT_DIR, "error_log_atlanticcity.txt")

API_EVENTS = "https://sb2frontend-altenar2.biahosted.com/api/Sportsbook/GetEvents"
API_DETAILS = "https://sb2frontend-altenar2.biahosted.com/api/widget/GetEventDetails"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.atlanticcity.pe",
    "referer": "https://www.atlanticcity.pe/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

PARAMS_EVENTS = {
    "culture": "es-ES",
    "timezoneOffset": "300",
    "integration": "acity",
    "deviceType": "1",
    "numFormat": "en-GB",
    "countryCode": "PE",
    "sportids": "66"
}

# === LÍMITE DE DÍAS ===
HORAS_ADELANTE = 72  # 3 días
NOW_UTC = datetime.now(timezone.utc)
CUTOFF_UTC = NOW_UTC + timedelta(hours=HORAS_ADELANTE)

# === LIGAS EQUIVALENTES ===
LIGAS_EQUIVALENCIAS = [
    ("Premier League", "Inglaterra", "Premier League"),
    ("FA Cup", "Inglaterra", "FA Cup"),
    ("EFL Cup", "Inglaterra", "EFL Cup"),
    ("Championship", "Inglaterra", "Championship"),
    ("LaLiga", "España", "La Liga"),
    ("Copa del Rey", "España", "Copa del Rey"),
    ("Serie A", "Italia", "Serie A"),
    ("Copa Italia", "Italia", "Copa Italia"),
    ("Supercopa", "Italia", "Supercopa de Italia"),
    ("Bundesliga", "Alemania", "Bundesliga"),
    ("DFB Pokal", "Alemania", "Copa Alemana"),
    ("Copa de Alemania", "Alemania", "Copa Alemana"),
    ("Ligue 1", "Francia", "Ligue 1"),
    ("Coupe de France", "Francia", "Copa Francia"),
    ("Brasileirao Serie A", "Brasil", "Brasileirao"),
    ("Copa de Brasil", "Brasil", "Copa de Brasil"),
    ("Liga MX", "México", "Liga MX"),
    ("MLS", "Estados Unidos", "MLS"),
    ("Liga 1", "Perú", "Liga 1 Perú"),
    ("Primera División", "Portugal", "Primeira Liga"),
    ("Eredivisie", "Países Bajos", "Eredivisie"),
    ("Clasif. Mundial África", "Africa", "Eliminatorias Africa - WC26"),
    ("Clasif. Mundial Asia", "Asia", "Eliminatorias Asia AFC - WC26"),
    ("Clasif. Mundial CONCACAF", "Americas", "Eliminatorias CONCACAF - WC26"),
    ("Clasif. Mundial UEFA", "Europa", "Eliminatorias Europa - WC26"),
    ("Copa Libertadores", "Americas", "Copa Libertadores"),
    ("Copa Sudamericana", "Americas", "Copa Sudamericana"),
    ("UEFA Champions League", "Europa", "UEFA Champions League"),
    ("UEFA Europa League", "Europa", "UEFA Europa League"),
    ("UEFA Conference League", "Europa", "UEFA Conference League"),
]

NOMBRES_1X2 = {"1x2", "resultado final", "match result", "ft result", "ganador"}

# === FUNCIONES AUXILIARES ===
def log_error(msg: str):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def normalizar_nombre_equipo(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = s.replace("ß", "ss").replace("œ", "oe").replace("æ", "ae")
    s = re.sub(r'[\"\'´`¨]', "", s)
    s = re.sub(r"[\t\r\n]", " ", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def format_nombre_equipo_title(s: str) -> str:
    if not s:
        return ""
    base = normalizar_nombre_equipo(s)
    return " ".join([p.capitalize() for p in base.split(" ") if p])

def mapear_liga(champ: str, cat: str):
    n_champ = normalizar_nombre_equipo(champ)
    n_cat = normalizar_nombre_equipo(cat)
    for champ_ref, cat_ref, canon in LIGAS_EQUIVALENCIAS:
        if normalizar_nombre_equipo(champ_ref) == n_champ and normalizar_nombre_equipo(cat_ref) == n_cat:
            return canon
    return None

def extraer_eventos(nodos):
    evs = []
    for n in nodos:
        if "Events" in n:
            evs += [e for e in n["Events"] if e.get("SportId") == 66]
        if "Items" in n:
            evs += extraer_eventos(n["Items"])
    return evs

def parse_event_date_utc(fecha_raw: str):
    if not fecha_raw:
        return None
    try:
        dt = pd.to_datetime(fecha_raw, utc=True, errors="coerce")
        if pd.isna(dt):
            return None
        return dt.to_pydatetime()
    except:
        return None

def obtener_cuotas(event_id: int):
    params = {
        "culture": "es-ES",
        "timezoneOffset": "300",
        "integration": "acity",
        "deviceType": "1",
        "numFormat": "en-GB",
        "countryCode": "PE",
        "eventId": str(event_id),
        "showNonBoosts": "false"
    }

    data = None
    for intento in range(3):
        try:
            r = requests.get(API_DETAILS, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json()
                mk = data.get("markets", []) or data.get("Markets", [])
                od = data.get("odds", []) or data.get("Odds", [])
                if mk and od:
                    break
                time.sleep(0.7 * (intento + 1))
        except Exception as e:
            log_error(f"Error conexión detalle evento {event_id}: {e}")
            time.sleep(2 * (intento + 1))

    if not data:
        return {"Local": "", "Empate": "", "Visita": ""}

    try:
        markets = data.get("markets", []) or data.get("Markets", [])
        odds_all = data.get("odds", []) or data.get("Odds", [])

        market_1x2 = next(
            (m for m in markets if any(k in normalizar_nombre_equipo(m.get("name", "")) for k in NOMBRES_1X2)),
            None
        )
        if not market_1x2:
            return {"Local": "", "Empate": "", "Visita": ""}

        odd_ids = []
        for key in ("desktopOddIds", "oddIds"):
            for item in market_1x2.get(key, []):
                if isinstance(item, list) and item:
                    odd_ids.append(item[0])
                elif isinstance(item, (int, str)):
                    try:
                        odd_ids.append(int(item))
                    except:
                        pass

        cuotas = {"Local": "", "Empate": "", "Visita": ""}

        if odd_ids:
            mapa = {o.get("id"): o for o in odds_all if o.get("id") in odd_ids}
            for _, o in mapa.items():
                nombre = normalizar_nombre_equipo(o.get("name", ""))
                tipo = o.get("typeId")
                price = o.get("price", "")

                if tipo == 1 or "local" in nombre or nombre in {"1"}:
                    cuotas["Local"] = price
                elif tipo == 2 or "empate" in nombre or nombre in {"x", "empate"}:
                    cuotas["Empate"] = price
                elif tipo == 3 or "visit" in nombre or "away" in nombre or nombre in {"2"}:
                    cuotas["Visita"] = price

        time.sleep(random.uniform(0.10, 0.25))
        return cuotas

    except Exception as e:
        log_error(f"Error procesando cuotas evento {event_id}: {e}")
        return {"Local": "", "Empate": "", "Visita": ""}

def procesar_evento(ev):
    try:
        # --- filtro 72h ---
        dt_utc = parse_event_date_utc(ev.get("EventDate", ""))
        if dt_utc and dt_utc > CUTOFF_UTC:
            return None

        champ_raw, cat_raw = ev.get("ChampName", ""), ev.get("CategoryName", "")
        liga_canon = mapear_liga(champ_raw, cat_raw)
        if not liga_canon:
            return None

        eid = ev.get("Id")
        cuotas = obtener_cuotas(eid)

        comps = ev.get("Competitors", [{"Name": ""}, {"Name": ""}])
        local_raw = comps[0].get("Name", "")
        visita_raw = comps[1].get("Name", "")

        local_fmt = format_nombre_equipo_title(local_raw)
        visita_fmt = format_nombre_equipo_title(visita_raw)

        fecha_raw = ev.get("EventDate", "")
        try:
            fecha_local = pd.to_datetime(fecha_raw, utc=True, errors="coerce").tz_convert(None).strftime("%Y-%m-%d %H:%M:%S")
        except:
            fecha_local = fecha_raw

        return {
            "Liga": liga_canon,
            "Partido": f"{local_fmt} vs {visita_fmt}",
            "Fecha": fecha_local,
            "Casa": "Atlantic City",
            "Local": local_fmt,
            "Visita": visita_fmt,
            "Cuota Local": cuotas["Local"],
            "Cuota Empate": cuotas["Empate"],
            "Cuota Visita": cuotas["Visita"],
            "EventId": eid
        }

    except Exception as e:
        log_error(f"Error procesando evento: {e}")
        return None

# ======================================================
#  MAIN
# ======================================================
def main():
    print("Consultando eventos en Atlantic City...\n")

    for intento in range(3):
        try:
            r = requests.get(API_EVENTS, params=PARAMS_EVENTS, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json().get("Result", {}).get("Items", [])
                break
        except Exception as e:
            log_error(f"Error conexión GetEvents: {e}")
            time.sleep(3 * (intento + 1))
    else:
        log_error("Fallo definitivo en conexión GetEvents.")
        return

    eventos = extraer_eventos(data)

    # filtro 72h antes de threads
    eventos_filtrados = []
    for ev in eventos:
        dt_utc = parse_event_date_utc(ev.get("EventDate", ""))
        if dt_utc and dt_utc <= CUTOFF_UTC:
            eventos_filtrados.append(ev)

    print(f"🔍 Total eventos detectados: {len(eventos)}")
    print(f"⏳ Eventos dentro de {HORAS_ADELANTE}h: {len(eventos_filtrados)}")

    registros = []

    # workers moderados para evitar vacíos
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(procesar_evento, ev) for ev in eventos_filtrados]
        for future in as_completed(futures):
            result = future.result()
            if result:
                registros.append(result)

    if not registros:
        print("No se encontraron registros válidos.")
        return

    df = pd.DataFrame(registros)
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.tz_localize(None)
    df = df.sort_values(["Liga", "Fecha"])

    out_json = os.path.join(OUT_DIR, "cuotas_atlanticcity.json")
    df.to_json(out_json, orient="records", indent=2, date_format="iso", force_ascii=False)

    print(f"✅ Archivo JSON generado: {out_json}")
    print(f"✅ Total partidos: {len(df)}")

if __name__ == "__main__":
    main()
