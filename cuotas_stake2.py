# cuotas_stake.py
# Stake -> prematch-by-tournaments.json por tournamentId
# Extrae 1X2
# Filtro 72 horas
# Genera: data/cuotas_stake.json

import os
import json
import time
import random
import requests
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# CONFIG
# ============================================================
OUT_DIR = "data"
os.makedirs(OUT_DIR, exist_ok=True)

OUT_JSON = os.path.join(OUT_DIR, "cuotas_stake.json")
ERROR_LOG = os.path.join(OUT_DIR, "error_stake_log.txt")
DEBUG_DIR = os.path.join(OUT_DIR, "debug_stake")
os.makedirs(DEBUG_DIR, exist_ok=True)

# ============================================================
# PROXY
# ============================================================
USE_PROXY = True

PROXY = "http://7b0f657793f8b923:exTpjJv7kcCPYnbL@res.proxy-seller.com:10000"

PROXIES = {
    "http": PROXY,
    "https": PROXY,
} if USE_PROXY else None

# ============================================================
# HIDENSEEK ACTUAL
# ============================================================
HIDENSEEK = "4ec05338971f6168281a9b87f7d242c927fc7758"

BASE = "https://pre-143o-sp.websbkt.com/cache/143/es/pe"

HORAS_ADELANTE = 72
NOW_UTC = datetime.now(timezone.utc)
CUTOFF_UTC = NOW_UTC + timedelta(hours=HORAS_ADELANTE)

REQUEST_TIMEOUT = 25
RETRIES = 2
PARALLEL_WORKERS = 3

HEADERS = {
    "accept": "*/*",
    "accept-language": "es-PE,es-419;q=0.9,es;q=0.8,en;q=0.7",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "origin": "https://stake.pe",
    "referer": "https://stake.pe/",
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
}

# ============================================================
# TOURNAMENT IDs
# Agrega aquí los IDs reales que captures del Network
# ============================================================
LIGAS_STAKE = [
    ("Copa Mundial 2026", "18736"),

    # Ejemplos anteriores, solo déjalos si confirmas que siguen vigentes:
    # ("Premier League", "49"),
    # ("La Liga", "60"),
    # ("Serie A", "64"),
    # ("Bundesliga", "53"),
    # ("Brasileirao", "179"),
    # ("UEFA Champions League", "260"),
    # ("UEFA Europa League", "262"),
    # ("Copa Libertadores", "217"),
    # ("Copa Sudamericana", "218"),
]

# ============================================================
# HELPERS
# ============================================================
def log_error(msg):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def save_debug(name, payload):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(name))
    path = os.path.join(DEBUG_DIR, f"{safe}.json")

    with open(path, "w", encoding="utf-8") as f:
        if isinstance(payload, (dict, list)):
            json.dump(payload, f, indent=2, ensure_ascii=False)
        else:
            f.write(str(payload))


def fecha_to_utc(value):
    if value is None or value == "":
        return None

    if isinstance(value, (int, float)):
        try:
            v = float(value)
            if v > 10_000_000_000:
                v = v / 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except Exception:
            return None

    s = str(value).strip()

    if not s:
        return None

    if s.isdigit():
        try:
            v = float(s)
            if v > 10_000_000_000:
                v = v / 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except Exception:
            return None

    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"

        dt = datetime.fromisoformat(s)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)

        return dt
    except Exception:
        return None


def format_fecha(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000")


def sort_key_fecha(reg):
    return fecha_to_utc(reg.get("Fecha", "")) or datetime.max.replace(tzinfo=timezone.utc)


def odd_to_float(v):
    if v in (None, ""):
        return ""

    try:
        v = float(v)

        # Stake puede venir como 7500
        if v > 100:
            v = v / 1000

        return round(v, 3)
    except Exception:
        return v


def get_nombre_team(x):
    if isinstance(x, dict):
        return (
            x.get("name")
            or x.get("short_name")
            or x.get("shortName")
            or x.get("team_name")
            or x.get("title")
            or ""
        )

    return str(x or "")


# ============================================================
# HTTP
# ============================================================
def fetch_tournament(liga, tournament_id):
    url = f"{BASE}/{tournament_id}/prematch-by-tournaments.json"

    last_err = None

    for attempt in range(1, RETRIES + 1):
        try:
            print(f"[{liga}] intento {attempt}/{RETRIES} | proxy={USE_PROXY}")

            r = requests.get(
                url,
                headers=HEADERS,
                params={"hidenseek": HIDENSEEK},
                proxies=PROXIES,
                timeout=REQUEST_TIMEOUT,
            )

            text = r.text.strip()

            print(f"[{liga}] HTTP {r.status_code}")

            if r.status_code == 200:
                if text.startswith("{") or text.startswith("["):
                    data = r.json()
                    save_debug(f"raw_{liga}_{tournament_id}", data)
                    return data

                save_debug(f"nonjson_{liga}_{tournament_id}", text[:5000])
                raise RuntimeError(f"Respuesta no JSON: {text[:150]}")

            if r.status_code == 406:
                save_debug(f"406_{liga}_{tournament_id}", {
                    "url": r.url,
                    "status": r.status_code,
                    "text": text,
                    "hidenseek": HIDENSEEK,
                    "use_proxy": USE_PROXY,
                    "proxy": PROXY if USE_PROXY else None,
                })
                raise RuntimeError("406 NotAcceptable: hidenseek vencido, IP/proxy bloqueado o request rechazada")

            save_debug(f"status_{r.status_code}_{liga}_{tournament_id}", {
                "url": r.url,
                "status": r.status_code,
                "text": text[:5000],
                "use_proxy": USE_PROXY,
                "proxy": PROXY if USE_PROXY else None,
            })

            raise RuntimeError(f"HTTP {r.status_code}: {text[:150]}")

        except requests.exceptions.ProxyError as e:
            last_err = RuntimeError(f"PROXY ERROR: {e}")
            save_debug(f"proxy_error_{liga}_{tournament_id}_attempt{attempt}", str(e))

        except requests.exceptions.ConnectTimeout as e:
            last_err = RuntimeError(f"CONNECT TIMEOUT: {e}")
            save_debug(f"connect_timeout_{liga}_{tournament_id}_attempt{attempt}", str(e))

        except requests.exceptions.ReadTimeout as e:
            last_err = RuntimeError(f"READ TIMEOUT: {e}")
            save_debug(f"read_timeout_{liga}_{tournament_id}_attempt{attempt}", str(e))

        except requests.exceptions.RequestException as e:
            last_err = RuntimeError(f"REQUEST ERROR: {e}")
            save_debug(f"request_error_{liga}_{tournament_id}_attempt{attempt}", str(e))

        except Exception as e:
            last_err = e

        if attempt < RETRIES:
            time.sleep(1.5 + random.random())

    raise last_err


# ============================================================
# PARSEO
# ============================================================
def buscar_eventos(payload):
    eventos = []

    def scan(x):
        if isinstance(x, dict):
            tiene_id = x.get("id") or x.get("event_id") or x.get("eventId")
            parece_evento = (
                x.get("main_odds")
                or x.get("home_team")
                or x.get("away_team")
                or x.get("homeTeam")
                or x.get("awayTeam")
                or x.get("home")
                or x.get("away")
                or x.get("teams")
            )

            if tiene_id and parece_evento:
                eventos.append(x)

            for v in x.values():
                scan(v)

        elif isinstance(x, list):
            for item in x:
                scan(item)

    scan(payload)

    uniq = {}
    for ev in eventos:
        eid = ev.get("id") or ev.get("event_id") or ev.get("eventId")
        if eid:
            uniq[str(eid)] = ev

    return list(uniq.values())


def extraer_equipos(ev):
    home = ev.get("home_team") or ev.get("homeTeam") or ev.get("home")
    away = ev.get("away_team") or ev.get("awayTeam") or ev.get("away")

    if home or away:
        return get_nombre_team(home), get_nombre_team(away)

    teams = ev.get("teams")

    if isinstance(teams, list) and len(teams) >= 2:
        return get_nombre_team(teams[0]), get_nombre_team(teams[1])

    if isinstance(teams, dict):
        return get_nombre_team(teams.get("home")), get_nombre_team(teams.get("away"))

    return "", ""


def extraer_fecha(ev):
    for k in (
        "date_start",
        "dateStart",
        "startTime",
        "start_time",
        "eventDate",
        "date",
        "starts_at",
        "start_at",
    ):
        if ev.get(k):
            return ev.get(k)

    return None


def extraer_1x2(ev):
    cuota_local = ""
    cuota_empate = ""
    cuota_visita = ""

    posibles = []

    main_odds = ev.get("main_odds", {})

    if isinstance(main_odds, dict):
        if isinstance(main_odds.get("main"), list):
            posibles.extend(main_odds.get("main"))

        if isinstance(main_odds.get("odds"), list):
            posibles.extend(main_odds.get("odds"))

    def scan(x):
        if isinstance(x, dict):
            odd_id = x.get("odd_id") or x.get("oddId") or x.get("id")
            name = str(x.get("name", "")).strip().upper()

            val = (
                x.get("odd_value")
                or x.get("value")
                or x.get("price")
                or x.get("coef")
                or x.get("odds")
                or x.get("decimal")
            )

            if val not in (None, ""):
                posibles.append({
                    "odd_id": odd_id,
                    "name": name,
                    "odd_value": val,
                })

            for v in x.values():
                scan(v)

        elif isinstance(x, list):
            for item in x:
                scan(item)

    scan(ev)

    for oc in posibles:
        odd_id = oc.get("odd_id") or oc.get("oddId") or oc.get("id")
        name = str(oc.get("name", "")).strip().upper()

        val = (
            oc.get("odd_value")
            or oc.get("value")
            or oc.get("price")
            or oc.get("coef")
            or oc.get("odds")
            or oc.get("decimal")
        )

        val = odd_to_float(val)

        if val in ("", None):
            continue

        if name == "1" or str(odd_id) == "3":
            cuota_local = cuota_local or val
        elif name == "X" or str(odd_id) == "4":
            cuota_empate = cuota_empate or val
        elif name == "2" or str(odd_id) == "5":
            cuota_visita = cuota_visita or val

    return cuota_local, cuota_empate, cuota_visita


# ============================================================
# PIPELINE
# ============================================================
def procesar_liga(liga, tournament_id):
    try:
        payload = fetch_tournament(liga, tournament_id)
    except Exception as e:
        log_error(f"[{liga}] FAIL: {e}")
        return []

    eventos = buscar_eventos(payload)
    registros = []

    for ev in eventos:
        event_id = ev.get("id") or ev.get("event_id") or ev.get("eventId")

        fecha_raw = extraer_fecha(ev)
        dt = fecha_to_utc(fecha_raw)

        if not dt:
            log_error(f"[{liga}] eventId={event_id} fecha inválida: {fecha_raw}")
            continue

        if dt > CUTOFF_UTC:
            continue

        local, visita = extraer_equipos(ev)

        if not local or not visita:
            log_error(f"[{liga}] eventId={event_id} sin equipos")
            continue

        c1, cx, c2 = extraer_1x2(ev)

        registros.append({
            "Liga": liga,
            "Partido": f"{local} vs {visita}",
            "Fecha": format_fecha(dt),
            "Casa": "Stake",
            "Local": local,
            "Visita": visita,
            "Cuota Local": c1,
            "Cuota Empate": cx,
            "Cuota Visita": c2,
            "EventId": event_id,
            "TournamentId": tournament_id,
        })

    print(f"[{liga}] eventos encontrados={len(eventos)} | guardados={len(registros)}")
    return registros


def main():
    if os.path.exists(ERROR_LOG):
        os.remove(ERROR_LOG)

    print("\nStake scraper con proxy")
    print(f"Ligas: {len(LIGAS_STAKE)}")
    print(f"Filtro: <= {HORAS_ADELANTE}h")
    print(f"Proxy activo: {USE_PROXY}")
    print(f"Workers: {PARALLEL_WORKERS}\n")

    resultados = []

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = [
            ex.submit(procesar_liga, liga, tournament_id)
            for liga, tournament_id in LIGAS_STAKE
        ]

        for fut in as_completed(futures):
            try:
                regs = fut.result()
                resultados.extend(regs)
                print(f"OK lote: {len(regs)} partidos")
            except Exception as e:
                log_error(f"[FUTURE] EXCEPTION: {e}")
                print(f"ERROR future: {e}")

    resultados.sort(key=lambda r: (r.get("Liga", ""), sort_key_fecha(r)))

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    print(f"\nOK generado: {OUT_JSON}")
    print(f"Total partidos guardados: {len(resultados)}")

    if os.path.exists(ERROR_LOG):
        print(f"Revisa: {ERROR_LOG}")


if __name__ == "__main__":
    main()