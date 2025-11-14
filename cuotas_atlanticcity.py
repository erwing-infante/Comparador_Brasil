import requests
import pandas as pd
import time
import random
import os
import re
import json
import unicodedata
from concurrent.futures import ThreadPoolExecutor

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

# === LIGAS EQUIVALENTES ===
LIGAS_EQUIVALENCIAS = [
    ("Premier League", "Inglaterra", "Premier League"),
    ("FA Cup", "Inglaterra", "FA Cup"),
    ("EFL Trophy", "Inglaterra", "Carabao Cup"),
    ("Championship", "Inglaterra", "Championship"),
    ("League One", "Inglaterra", "League One"),
    ("Serie A", "Italia", "Serie A"),
    ("Copa Italia", "Italia", "Copa Italia"),
    ("Supercopa", "Italia", "Supercopa de Italia"),
    ("Bundesliga", "Alemania", "Bundesliga"),
    ("2ª Bundesliga", "Alemania", "2 Bundesliga"),
    ("DFB Pokal", "Alemania", "Copa Alemana"),
    ("Copa de Alemania", "Alemania", "Copa Alemana"),
    ("Ligue 1", "Francia", "Ligue 1"),
    ("LaLiga", "España", "La Liga"),
    ("LaLiga 2", "España", "La Liga 2"),
    ("Brasileirao Serie A", "Brasil", "Brasileirao"),
    ("Copa de Brasil", "Brasil", "Copa de Brasil"),
    ("Liga MX", "México", "Liga MX"),
    ("MLS", "Estados Unidos", "MLS"),
    ("Liga 1", "Perú", "Liga 1 Perú"),
    ("Primera División", "Portugal", "Primeira Liga"),
    ("Eredivisie", "Países Bajos", "Eredivisie"),
    ("Eerste Divisie", "Países Bajos", "Eerste Divisie"),
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
    parts = [p.capitalize() for p in base.split(" ") if p]
    return " ".join(parts)

def auditar_nombres_equipo(raw: str, cleaned: str):
    if raw and raw != cleaned:
        log_error(f"NOMBRE AJUSTADO: '{raw}' -> '{cleaned}'")

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

def obtener_cuotas(event_id: int):
    params = {
        "culture": "es-ES", "timezoneOffset": "300",
        "integration": "acity", "deviceType": "1",
        "numFormat": "en-GB", "countryCode": "PE",
        "eventId": str(event_id), "showNonBoosts": "false"
    }
    for intento in range(3):
        try:
            r = requests.get(API_DETAILS, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json()
                break
        except requests.exceptions.RequestException as e:
            log_error(f"Error conexión detalle evento {event_id}: {e}")
            time.sleep(5 * (intento + 1))
    else:
        return {"Local": "", "Empate": "", "Visita": ""}

    try:
        markets = data.get("markets", []) or data.get("Markets", [])
        odds_all = data.get("odds", []) or data.get("Odds", [])
        market_1x2 = next((m for m in markets
                           if any(k in normalizar_nombre_equipo(m.get("name", "")) for k in NOMBRES_1X2)), None)
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
            for oid, o in mapa.items():
                nombre_raw = o.get("name", "")
                nombre = normalizar_nombre_equipo(nombre_raw)
                tipo = o.get("typeId")
                price = o.get("price", "")
                if tipo == 1 or "local" in nombre or nombre in {"1"}:
                    cuotas["Local"] = price
                elif tipo == 2 or "empate" in nombre or nombre in {"x", "empate"}:
                    cuotas["Empate"] = price
                elif tipo == 3 or "visit" in nombre or "away" in nombre or nombre in {"2"}:
                    cuotas["Visita"] = price
                if nombre_raw and nombre_raw != nombre:
                    log_error(f"ODD NAME AJUSTADO (event {event_id}): '{nombre_raw}' -> '{nombre}'")
        time.sleep(random.uniform(0.3, 0.7))
        return cuotas
    except Exception as e:
        log_error(f"Error procesando cuotas evento {event_id}: {e}")
        return {"Local": "", "Empate": "", "Visita": ""}

def procesar_evento(ev):
    champ_raw, cat_raw = ev.get("ChampName", ""), ev.get("CategoryName", "")
    liga_canon = mapear_liga(champ_raw, cat_raw)
    if not liga_canon:
        log_error(f"LIGA NO MAPEADA: champ='{champ_raw}' cat='{cat_raw}'")
        return None
    eid = ev.get("Id")
    cuotas = obtener_cuotas(eid)
    comps = ev.get("Competitors", [{"Name": ""}, {"Name": ""}])
    local_raw = comps[0].get("Name", "") if len(comps) > 0 else ""
    visita_raw = comps[1].get("Name", "") if len(comps) > 1 else ""
    local_clean = normalizar_nombre_equipo(local_raw)
    visita_clean = normalizar_nombre_equipo(visita_raw)
    auditar_nombres_equipo(local_raw, local_clean)
    auditar_nombres_equipo(visita_raw, visita_clean)

    local_fmt = format_nombre_equipo_title(local_clean)
    visita_fmt = format_nombre_equipo_title(visita_clean)

    fecha_raw = ev.get("EventDate", "")
    try:
        fecha_local = pd.to_datetime(fecha_raw).tz_convert(None).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
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

def main():
    print("Consultando eventos en Atlantic City...\n")
    for intento in range(3):
        try:
            r = requests.get(API_EVENTS, params=PARAMS_EVENTS, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json().get("Result", {}).get("Items", [])
                break
        except requests.exceptions.RequestException as e:
            log_error(f"Error conexión GetEvents: {e}")
            time.sleep(5 * (intento + 1))
    else:
        log_error("Fallo definitivo en conexión GetEvents después de 3 intentos.")
        return

    try:
        eventos = extraer_eventos(data)
        with ThreadPoolExecutor(max_workers=10) as executor:
            registros = list(filter(None, executor.map(procesar_evento, eventos)))
        if not registros:
            print("Alerta No se encontraron registros válidos.")
            return

        df = pd.DataFrame(registros)
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.tz_localize(None)
        df = df.sort_values(["Liga", "Fecha"])

        out_json = os.path.join(OUT_DIR, "cuotas_atlanticcity.json")
        df.to_json(out_json, orient="records", indent=2, date_format="iso", force_ascii=False)
        print(f"Ok Archivo JSON generado correctamente: {out_json}")
    except Exception as e:
        log_error(f"Error general: {e}")
        print(f"F Error general: {e}")

if __name__ == "__main__":
    main()