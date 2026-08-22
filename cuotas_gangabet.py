import requests
import pandas as pd
import time
import random
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

# === CONFIGURACIÓN ===
OUT_DIR = "data"
os.makedirs(OUT_DIR, exist_ok=True)
ERROR_LOG = os.path.join(OUT_DIR, "error_gangabet_log.txt")

API_EVENTS  = "https://sb2frontend-altenar2.biahosted.com/api/Sportsbook/GetEvents"
API_DETAILS = "https://sb2frontend-altenar2.biahosted.com/api/widget/GetEventDetails"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://gangabet.pe",
    "referer": "https://gangabet.pe/",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

PARAMS_EVENTS = {
    "culture": "es-ES",
    "timezoneOffset": "300",
    "integration": "gangabet.pe",
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
    ("La Liga", "España", "La Liga"),
    ("Serie A", "Italia", "Serie A"),
    ("Bundesliga", "Alemania", "Bundesliga"),
    ("Ligue 1", "Francia", "Ligue 1"),
    ("Brasileiro Serie A", "Brasil", "Brasileirao"),
    ("MLS", "Estados Unidos", "MLS"),
    ("Liga 1", "Perú", "Liga 1 Perú"),
    ("Primeira Liga", "Portugal", "Primeira Liga"),
    ("Liga Eredivisie", "Países Bajos", "Eredivisie"),
    ("UEFA Champions League", "Europa", "UEFA Champions League"),
    ("UEFA Europa League", "Europa", "UEFA Europa League"),
    ("UEFA Conference League", "Europa", "UEFA Conference League"),
    ("Copa Libertadores", "Americas", "Copa Libertadores"),
    ("Copa Sudamericana", "Americas", "Copa Sudamericana"),
    ("Eliminatorias Europeas — Europa", "Europa", "Eliminatorias Europa - WC26"),
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
        "integration": "gangabet.pe",
        "deviceType": "1",
        "numFormat": "en-GB",
        "countryCode": "PE",
        "eventId": str(event_id),
        # False permite recibir también mercados mejorados.
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
            return normalizar_nombre_equipo(
                market.get("name", "") or ""
            )

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

        def _prices_for_market(market):
            odds_map = _odds_map_for_market(market)

            result = {
                "Local": None,
                "Empate": None,
                "Visita": None,
            }

            for odd in odds_map.values():
                try:
                    price = float(odd.get("price"))
                except (TypeError, ValueError):
                    continue

                if price <= 1:
                    continue

                tipo = odd.get("typeId")

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

        # ==================================================
        # 1X2 principal con PA
        # ==================================================
        exact_main_names = {
            "1x2",
            "resultado final",
            "resultado del partido",
            "match result",
            "ft result",
        }

        pa_market = None

        # Primero, mercado 1X2 exacto con señal PA.
        for market in markets:
            name = _market_name_norm(market)

            if (
                name in exact_main_names
                and _has_pa_signal(market)
            ):
                pa_market = market
                break

        # Si no expone señal PA, usar el 1X2 principal exacto.
        if pa_market is None:
            for market in markets:
                name = _market_name_norm(market)

                if name in exact_main_names:
                    pa_market = market
                    break

        pa_prices = (
            _prices_for_market(pa_market)
            if pa_market is not None
            else None
        )

        # ==================================================
        # NoPA
        # Solo se llena si existe un mercado 1X2 cuyo nombre
        # real contiene "supercuota".
        # Si no existe, queda null.
        # ==================================================
        super_market = None

        for market in markets:
            name = _market_name_norm(market)

            if (
                "supercuota" in name
                or "super cuota" in name
            ):
                super_market = market
                break

        nopa_prices = (
            _prices_for_market(super_market)
            if super_market is not None
            else None
        )

        empate_candidates = []

        if pa_prices and pa_prices["Empate"] is not None:
            empate_candidates.append(
                pa_prices["Empate"]
            )

        if nopa_prices and nopa_prices["Empate"] is not None:
            empate_candidates.append(
                nopa_prices["Empate"]
            )

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
        local_raw = comps[0].get("Name", "") if len(comps) > 0 else ""
        visita_raw = comps[1].get("Name", "") if len(comps) > 1 else ""

        local_fmt = format_nombre_equipo_title(local_raw)
        visita_fmt = format_nombre_equipo_title(visita_raw)

        fecha_raw = ev.get("EventDate", "")
        try:
            fecha_local = pd.to_datetime(fecha_raw, utc=True, errors="coerce").tz_convert(None).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            fecha_local = fecha_raw

        return {
            "Liga": liga_canon,
            "Partido": f"{local_fmt} vs {visita_fmt}",
            "Fecha": fecha_local,
            "Casa": "GangaBet",
            "Local": local_fmt,
            "Visita": visita_fmt,

            # Pago Anticipado.
            "Cuota Local": cuotas["LocalNoPA"],
            "Cuota Empate": cuotas["Empate"],
            "Cuota Visita": cuotas["VisitaNoPA"],

            # Sin PA. Si no existe Supercuota, queda null.
            "Cuota Local NoPA": cuotas["LocalPA"],
            "Cuota Visita NoPA": cuotas["VisitaPA"],

            "EventId": eid
        }

    except Exception as e:
        log_error(f"Error procesando evento: {e}")
        return None


def main():
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

    # filtro 72h antes de threads (ahorra muchísimo)
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
        print("No se encontraron eventos válidos.")
        return

    df = pd.DataFrame(registros)
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.tz_localize(None)
    df = df.sort_values(["Liga", "Fecha"])

    out_json = os.path.join(OUT_DIR, "cuotas_gangabet.json")
    df.to_json(out_json, orient="records", indent=2, date_format="iso", force_ascii=False)

    print(f"✅ Archivo generado: {out_json}")
    print(f"✅ Total partidos: {len(df)}")


if __name__ == "__main__":
    main()