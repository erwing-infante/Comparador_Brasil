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
ERROR_LOG = os.path.join(OUT_DIR, "error_doradobet_log.txt")

API_EVENTS  = "https://sb2frontend-altenar2.biahosted.com/api/Sportsbook/GetEvents"
API_DETAILS = "https://sb2frontend-altenar2.biahosted.com/api/widget/GetEventDetails"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://www.doradobet.com",
    "referer": "https://www.doradobet.com/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

PARAMS_EVENTS = {
    "culture": "es-ES",
    "timezoneOffset": "300",
    "integration": "doradobet",
    "deviceType": "1",
    "numFormat": "en-GB",
    "countryCode": "PE",
    "sportids": "66"
}

# === LÍMITE DE DÍAS ===
HORAS_ADELANTE = 72  # 3 días
NOW_UTC = datetime.now(timezone.utc)
CUTOFF_UTC = NOW_UTC + timedelta(hours=HORAS_ADELANTE)

# === LIGAS DE MÁNCORABET ===
LIGAS_EQUIVALENCIAS = [
    ("Premier League", "Inglaterra", "Premier League"),
    ("FA Cup", "Inglaterra", "FA Cup"),
    ("EFL Cup (Inglaterra)", "Inglaterra", "EFL Cup"),
    ("Championship (2da División)", "Inglaterra", "Championship"),
    ("La Liga", "España", "La Liga"),
    ("Copa del Rey", "España", "Copa del Rey"),
    ("Serie A", "Italia", "Serie A"),
    ("Copa Italia", "Italia", "Copa Italia"),
    ("Supercopa de Italia", "Italia", "Supercopa de Italia"),
    ("Bundesliga", "Alemania", "Bundesliga"),
    ("Copa de Alemania", "Alemania", "Copa Alemana"),
    ("DFB Pokal", "Alemania", "Copa Alemana"),
    ("Ligue 1", "Francia", "Ligue 1"),
    ("Copa de Francia", "Francia", "Copa Francia"),
    ("Brasileirao, Serie A", "Brasil", "Brasileirao"),
    ("Copa de Brasil", "Brasil", "Copa de Brasil"),
    ("Liga MX", "México", "Liga MX"),
    ("MLS", "Estados Unidos", "MLS"),
    ("Liga 1 - Perú", "Perú", "Liga 1 Perú"),
    ("Liga de Portugal", "Portugal", "Primeira Liga"),
    ("Liga de Holanda Eredivisie", "Países Bajos", "Eredivisie"),
    ("UEFA Champions League", "Europa", "UEFA Champions League"),
    ("UEFA Europa League", "Europa", "UEFA Europa League"),
    ("UEFA Conference League", "Europa", "UEFA Conference League"),
    ("Copa Libertadores", "Américas", "Copa Libertadores"),
    ("Copa Sudamericana", "Américas", "Copa Sudamericana"),
    ("Eliminatorias Africa - WC26", "Africa", "Eliminatorias Africa - WC26"),
    ("Eliminatorias Asia AFC - WC26", "Asia", "Eliminatorias Asia AFC - WC26"),
    ("Eliminatorias CONCACAF - WC26", "Americas", "Eliminatorias CONCACAF - WC26"),
    ("Eliminatorias Europa - WC 2026", "Europa", "Eliminatorias Europa - WC26"),
    ("Copa Mundo 2026", "Mundo", "Copa Mundial 2026"),
]

NOMBRES_1X2 = {"1x2", "resultado final", "match result", "ft result", "ganador"}


# === FUNCIONES ===

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
    parts = [p for p in base.split(" ") if p]

    SIGLAS = {"fc", "cd", "rb", "ac", "sc", "ss", "st", "psv"}

    out = []
    for p in parts:
        if p in SIGLAS:
            out.append(p.upper())
        else:
            out.append(p.capitalize())
    return " ".join(out)


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


def parse_event_date_utc(fecha_raw: str):
    """Convierte EventDate a datetime UTC (si se puede)."""
    if not fecha_raw:
        return None
    try:
        # Altenar suele devolver ISO con Z
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
        "integration": "doradobet",
        "deviceType": "1",
        "numFormat": "en-GB",
        "countryCode": "PE",
        "eventId": str(event_id),
        # Mantener en false para que también aparezcan boosts (Cuotaza Dorada) y poder comparar el empate
        "showNonBoosts": "false"
    }

    data = None
    for intento in range(3):
        try:
            r = requests.get(API_DETAILS, params=params, headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json()
                # si viene incompleto, reintenta
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

        # ==========================
        # CAMBIO: Selección de mercado
        # Base = PA si existe, sino 1x2 normal (no boost)
        # Empate = max( empate base, empate dorada si existe )
        # ==========================

        def _market_name_norm(m):
            return normalizar_nombre_equipo(m.get("name", "") or "")

        def _is_boost_market(m):
            n = _market_name_norm(m)
            return any(w in n for w in ("cuotaza", "dorada", "boost", "supercuota"))

        def _extract_odd_ids(m):
            odd_ids = []
            for key in ("desktopOddIds", "oddIds"):
                for item in m.get(key, []) or []:
                    if isinstance(item, list) and item:
                        try:
                            odd_ids.append(int(item[0]))
                        except:
                            pass
                    elif isinstance(item, (int, str)):
                        try:
                            odd_ids.append(int(item))
                        except:
                            pass
            return odd_ids

        def _odds_map_for_ids(ids):
            ids_set = set(ids)
            return {o.get("id"): o for o in odds_all if o.get("id") in ids_set}

        def _has_pa_signal(odds_map):
            # Señales vistas en tu JSON: offers.parameter == 2 y/o IsDBB == true
            for o in odds_map.values():
                if o.get("IsDBB") is True or o.get("isDBB") is True:
                    return True
                offers = o.get("offers") or []
                if isinstance(offers, list):
                    for off in offers:
                        try:
                            if int(off.get("parameter", -1)) == 2:
                                return True
                        except:
                            continue
            return False

        def _prices_from_odds_map(odds_map):
            # Devuelve (local, empate, visita) como floats o "" si falta
            out = {"Local": "", "Empate": "", "Visita": ""}

            for o in odds_map.values():
                tipo = o.get("typeId")
                price = o.get("price", "")
                if price == "" or price is None:
                    continue
                try:
                    price_val = float(price)
                except:
                    continue

                if tipo == 1:
                    out["Local"] = price_val
                elif tipo == 2:
                    out["Empate"] = price_val
                elif tipo == 3:
                    out["Visita"] = price_val

            return out

        # 1) candidatos 1x2
        cand_1x2 = []
        for m in markets:
            nm = _market_name_norm(m)
            if any(k in nm for k in NOMBRES_1X2):
                cand_1x2.append(m)

        if not cand_1x2:
            return {"Local": "", "Empate": "", "Visita": ""}

        # 2) separar boost vs no-boost
        boost_markets = [m for m in cand_1x2 if _is_boost_market(m)]
        non_boost_markets = [m for m in cand_1x2 if not _is_boost_market(m)]

        if not non_boost_markets:
            # si no hay normal, no tenemos base (evitamos usar dorada como base)
            return {"Local": "", "Empate": "", "Visita": ""}

        # 3) elegir base: PA si existe, sino primer non-boost
        base_market = None
        for m in non_boost_markets:
            ids = _extract_odd_ids(m)
            if not ids:
                continue
            om = _odds_map_for_ids(ids)
            if _has_pa_signal(om):
                base_market = m
                break

        if base_market is None:
            base_market = non_boost_markets[0]

        base_ids = _extract_odd_ids(base_market)
        base_odds_map = _odds_map_for_ids(base_ids)
        base_prices = _prices_from_odds_map(base_odds_map)

        # 4) dorada (para comparar empate)
        dorada_draw = ""
        if boost_markets:
            dorada_ids = _extract_odd_ids(boost_markets[0])
            dorada_odds_map = _odds_map_for_ids(dorada_ids)
            dorada_prices = _prices_from_odds_map(dorada_odds_map)
            dorada_draw = dorada_prices.get("Empate", "")

        # 5) salida final:
        # Local y Visita SIEMPRE del base (PA si existe, si no normal)
        # Empate = mejor entre base y dorada (si existe)
        cuotas = {"Local": "", "Empate": "", "Visita": ""}

        cuotas["Local"] = base_prices.get("Local", "")
        cuotas["Visita"] = base_prices.get("Visita", "")

        base_draw = base_prices.get("Empate", "")
        if base_draw != "" and dorada_draw != "":
            try:
                cuotas["Empate"] = max(float(base_draw), float(dorada_draw))
            except:
                cuotas["Empate"] = base_draw
        else:
            cuotas["Empate"] = dorada_draw if base_draw == "" else base_draw

        # micro-sleep pequeño (no grande)
        time.sleep(random.uniform(0.10, 0.25))
        return cuotas

    except Exception as e:
        log_error(f"Error procesando cuotas evento {event_id}: {e}")
        return {"Local": "", "Empate": "", "Visita": ""}


# === ENVOLTORIO PARA USAR EN MULTIHILO ===
def procesar_evento(ev):
    try:
        # --- filtro 72h ---
        fecha_raw = ev.get("EventDate", "")
        dt_utc = parse_event_date_utc(fecha_raw)
        if dt_utc and dt_utc > CUTOFF_UTC:
            return None

        champ_raw, cat_raw = ev.get("ChampName", ""), ev.get("CategoryName", "")
        liga_canon = mapear_liga(champ_raw, cat_raw)
        if not liga_canon:
            return None

        eid = ev.get("Id")
        cuotas = obtener_cuotas(eid)

        comps = ev.get("Competitors", [{"Name": ""}, {"Name": ""}])
        local_raw = comps[0].get("Name", "") if len(comps) > 0 else ""
        visita_raw = comps[1].get("Name", "") if len(comps) > 1 else ""

        local_clean = normalizar_nombre_equipo(local_raw)
        visita_clean = normalizar_nombre_equipo(visita_raw)

        local_fmt = format_nombre_equipo_title(local_clean)
        visita_fmt = format_nombre_equipo_title(visita_clean)

        # fecha_local para salida
        try:
            fecha_local = pd.to_datetime(fecha_raw, utc=True, errors="coerce").tz_convert(None).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            fecha_local = fecha_raw

        return {
            "Liga": liga_canon,
            "Partido": f"{local_fmt} vs {visita_fmt}",
            "Fecha": fecha_local,
            "Casa": "DoradoBet",
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


# === MAIN ===
def main():
    # limpiar log viejo (opcional)
    # open(ERROR_LOG, "w").close()

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
        log_error("Fallo definitivo en conexión GetEvents después de 3 intentos.")
        return

    eventos = extraer_eventos(data)

    # filtro 72h antes de mandar a threads (ahorra muchísimo)
    eventos_filtrados = []
    for ev in eventos:
        dt_utc = parse_event_date_utc(ev.get("EventDate", ""))
        if dt_utc and dt_utc <= CUTOFF_UTC:
            eventos_filtrados.append(ev)

    print(f"🔍 Total eventos detectados: {len(eventos)}")
    print(f"⏳ Eventos dentro de {HORAS_ADELANTE}h: {len(eventos_filtrados)}")

    registros = []

    # =============================================================
    #  MULTIHILO moderado — 6 workers (reduce vacíos)
    # =============================================================
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(procesar_evento, ev) for ev in eventos_filtrados]
        for future in as_completed(futures):
            result = future.result()
            if result:
                registros.append(result)
    # =============================================================

    if not registros:
        print("No se encontraron eventos válidos.")
        return

    df = pd.DataFrame(registros)
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.tz_localize(None)
    df = df.sort_values(["Liga", "Fecha"])

    out_json = os.path.join(OUT_DIR, "cuotas_doradobet.json")
    df.to_json(out_json, orient="records", indent=2, date_format="iso", force_ascii=False)

    print(f"✅ Archivo generado: {out_json}")
    print(f"✅ Total partidos: {len(df)}")


if __name__ == "__main__":
    main()