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
        "showNonBoosts": "false"
    }

    vacio = {
        "LocalPA": None,
        "Empate": None,
        "VisitaPA": None,
        "LocalNoPA": None,
        "VisitaNoPA": None,
    }

    data = None

    for intento in range(3):
        try:
            r = requests.get(
                API_DETAILS,
                params=params,
                headers=HEADERS,
                timeout=20
            )

            if r.status_code == 200:
                data = r.json()

                markets = data.get("markets", []) or data.get("Markets", [])
                odds = data.get("odds", []) or data.get("Odds", [])

                if markets and odds:
                    break

            time.sleep(0.7 * (intento + 1))

        except Exception as e:
            log_error(
                f"Error conexión detalle evento {event_id}: {e}"
            )
            time.sleep(2 * (intento + 1))

    if not data:
        return vacio

    try:
        markets = data.get("markets", []) or data.get("Markets", [])
        odds_all = data.get("odds", []) or data.get("Odds", [])

        def _market_name_norm(market):
            value = market.get("name", "") or ""

            if isinstance(value, dict):
                value = (
                    value.get("ES")
                    or value.get("es")
                    or value.get("ES-PE")
                    or value.get("es-PE")
                    or next(iter(value.values()), "")
                )

            return normalizar_nombre_equipo(value)

        def _extract_odd_ids(market):
            odd_ids = []

            for key in ("desktopOddIds", "oddIds"):
                for item in market.get(key, []) or []:
                    if isinstance(item, list) and item:
                        item = item[0]

                    try:
                        odd_ids.append(int(item))
                    except (TypeError, ValueError):
                        pass

            return odd_ids

        def _odds_map_for_market(market):
            ids = set(_extract_odd_ids(market))

            return {
                odd.get("id"): odd
                for odd in odds_all
                if odd.get("id") in ids
            }

        def _extract_1x2_prices(market):
            """
            Solo acepta mercados 1X2 reales:
              typeId 1 = Local
              typeId 2 = Empate
              typeId 3 = Visita

            Si falta una de las tres selecciones, el mercado se descarta.
            """
            odds_map = _odds_map_for_market(market)

            result = {
                "Local": None,
                "Empate": None,
                "Visita": None,
            }

            for odd in odds_map.values():
                tipo = odd.get("typeId")

                if tipo not in (1, 2, 3):
                    continue

                try:
                    price = float(odd.get("price"))
                except (TypeError, ValueError):
                    continue

                if price <= 1:
                    continue

                if tipo == 1:
                    result["Local"] = price
                elif tipo == 2:
                    result["Empate"] = price
                elif tipo == 3:
                    result["Visita"] = price

            if all(
                result[key] is not None
                for key in ("Local", "Empate", "Visita")
            ):
                return result

            return None

        def _has_pa_signal(market):
            odds_map = _odds_map_for_market(market)

            for odd in odds_map.values():
                if (
                    odd.get("IsDBB") is True
                    or odd.get("isDBB") is True
                ):
                    return True

                offers = odd.get("offers") or []

                if isinstance(offers, list):
                    for offer in offers:
                        try:
                            if int(offer.get("parameter", -1)) == 2:
                                return True
                        except (TypeError, ValueError):
                            continue

            return False

        def _is_main_1x2_name(name):
            return name in {
                "1x2",
                "resultado final",
                "resultado del partido",
                "match result",
                "ft result",
            }

        def _is_nopa_name(name):
            return any(
                token in name
                for token in (
                    "supercuota",
                    "super cuota",
                    "cuotaza dorada",
                    "cuota dorada",
                )
            )

        # ==================================================
        # 1) Reunir únicamente mercados 1X2 reales.
        # ==================================================
        real_1x2 = []

        for market in markets:
            prices = _extract_1x2_prices(market)

            if prices is None:
                continue

            real_1x2.append({
                "market": market,
                "name": _market_name_norm(market),
                "prices": prices,
                "has_pa": _has_pa_signal(market),
            })

        if not real_1x2:
            return vacio

        # ==================================================
        # 2) Mercado PA:
        # primero 1X2 principal exacto con señal PA;
        # luego 1X2 principal exacto aunque no exponga señal.
        # ==================================================
        pa_entry = None

        for entry in real_1x2:
            if (
                _is_main_1x2_name(entry["name"])
                and entry["has_pa"]
            ):
                pa_entry = entry
                break

        if pa_entry is None:
            for entry in real_1x2:
                if _is_main_1x2_name(entry["name"]):
                    pa_entry = entry
                    break

        # ==================================================
        # 3) Mercado NoPA:
        # exclusivamente mercado 1X2 real con nombre
        # Supercuota / Cuotaza Dorada.
        # Si no existe, queda null.
        # ==================================================
        nopa_entry = None

        for entry in real_1x2:
            if _is_nopa_name(entry["name"]):
                nopa_entry = entry
                break

        pa_prices = pa_entry["prices"] if pa_entry else None
        nopa_prices = nopa_entry["prices"] if nopa_entry else None

        empate_candidates = []

        if pa_prices:
            empate_candidates.append(pa_prices["Empate"])

        if nopa_prices:
            empate_candidates.append(nopa_prices["Empate"])

        cuota_empate = (
            max(empate_candidates)
            if empate_candidates
            else None
        )

        time.sleep(random.uniform(0.10, 0.25))

        return {
            "LocalPA": (
                pa_prices["Local"]
                if pa_prices
                else None
            ),
            "Empate": cuota_empate,
            "VisitaPA": (
                pa_prices["Visita"]
                if pa_prices
                else None
            ),
            "LocalNoPA": (
                nopa_prices["Local"]
                if nopa_prices
                else None
            ),
            "VisitaNoPA": (
                nopa_prices["Visita"]
                if nopa_prices
                else None
            ),
        }

    except Exception as e:
        log_error(
            f"Error procesando cuotas evento {event_id}: {e}"
        )
        return vacio


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

            # Pago Anticipado.
            "Cuota Local": cuotas["LocalNoPA"],
            "Cuota Empate": cuotas["Empate"],
            "Cuota Visita": cuotas["VisitaNoPA"],

            # Sin PA. Si no existe Supercuota/Cuotaza Dorada,
            # queda null.
            "Cuota Local NoPA": cuotas["LocalPA"],
            "Cuota Visita NoPA": cuotas["VisitaPA"],

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