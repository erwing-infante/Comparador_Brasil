# cuotas_stake.py
# Stake -> events-by-path.json
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

# Hidenseek actual capturado de Network
HIDENSEEK = "bcc0f2180733cb82ce70d7136680a27383fcbae3"

BASE_URL = "https://pre-143o-sp.websbkt.com/cache/143/es/pe/America-Lima/events-by-path.json"

RETRIES = 3
PARALLEL_WORKERS = 2
STAGGER_BETWEEN_SUBMITS = (0.20, 0.45)
SLEEP_BETWEEN_RETRIES_EXTRA = (0.50, 1.50)

# ✅ filtro 72 horas
HORAS_ADELANTE = 72
NOW_UTC = datetime.now(timezone.utc)
CUTOFF_UTC = NOW_UTC + timedelta(hours=HORAS_ADELANTE)

# ============================================================
# LIGAS
# ============================================================
LIGAS_STAKE = [
    ("Premier League", "football|england|premier-league"),
    ("La Liga", "football|spain|la-liga"),
    ("Serie A", "football|italy|serie-a"),
    ("Bundesliga", "football|germany|bundesliga"),
    ("Brasileirao", "football|brazil|serie-a"),
    ("UEFA Champions League", "football|europe|uefa-champions-league"),
    ("UEFA Europa League", "football|europe|uefa-europa-league"),

    ("Copa Libertadores", "football|south-america|copa-libertadores"),
    ("Copa Sudamericana", "football|south-america|copa-sudamericana"),

    ("Copa Mundial 2026", "football|world|fifa-world-cup"),
]

HEADERS = {
    "accept": "*/*",
    "accept-language": "es-US,es-PE;q=0.9,es-419;q=0.8,es;q=0.7,en;q=0.6",
    "cache-control": "no-cache",
    "origin": "https://stake.pe",
    "pragma": "no-cache",
    "referer": "https://stake.pe/",
    "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
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
# HELPERS
# ============================================================
def log_error(msg):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")


def save_debug(name, payload):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    path = os.path.join(DEBUG_DIR, f"{safe}.json")
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(payload, (dict, list)):
            json.dump(payload, f, ensure_ascii=False, indent=2)
        else:
            f.write(str(payload))


def fecha_to_utc(fecha_raw):
    if fecha_raw is None or fecha_raw == "":
        return None

    if isinstance(fecha_raw, (int, float)):
        try:
            val = float(fecha_raw)
            if val > 10_000_000_000:
                val = val / 1000
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None

    s = str(fecha_raw).strip()
    if not s:
        return None

    if s.isdigit():
        try:
            val = float(s)
            if val > 10_000_000_000:
                val = val / 1000
            return datetime.fromtimestamp(val, tz=timezone.utc)
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


def sort_key_fecha(reg):
    return fecha_to_utc(reg.get("Fecha", "")) or datetime.max.replace(tzinfo=timezone.utc)


# ============================================================
# HTTP
# ============================================================
def fetch_path(canon, path_value):
    last_err = None

    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(
                BASE_URL,
                headers=HEADERS,
                params={
                    "path": path_value,
                    "hidenseek": HIDENSEEK,
                },
                timeout=30,
            )

            text = r.text.strip()

            if r.status_code == 200:
                if text.startswith("{") or text.startswith("["):
                    return r.json()

                save_debug(f"nonjson_{canon}_attempt{attempt}", text[:4000])
                raise RuntimeError(f"Respuesta no JSON: {text[:150]}")

            if r.status_code == 406:
                raise RuntimeError("406 NotAcceptable: hidenseek vencido o request no aceptado")

            save_debug(f"status_{r.status_code}_{canon}_attempt{attempt}", text[:4000])
            raise RuntimeError(f"Status {r.status_code}: {text[:150]}")

        except Exception as e:
            last_err = e
            if attempt < RETRIES:
                time.sleep(attempt + random.uniform(*SLEEP_BETWEEN_RETRIES_EXTRA))

    raise last_err


# ============================================================
# PARSEO
# ============================================================
def parece_evento(obj):
    if not isinstance(obj, dict):
        return False

    tiene_id = obj.get("id") or obj.get("eventId")
    tiene_fecha = (
        obj.get("date_start")
        or obj.get("dateStart")
        or obj.get("startTime")
        or obj.get("start_time")
        or obj.get("eventDate")
        or obj.get("date")
    )
    tiene_equipos = (
        obj.get("teams")
        or obj.get("homeTeam")
        or obj.get("awayTeam")
        or obj.get("home")
        or obj.get("away")
    )

    return bool(tiene_id and tiene_fecha and tiene_equipos)


def encontrar_eventos(payload):
    eventos = []

    def scan(x):
        if isinstance(x, dict):
            if parece_evento(x):
                eventos.append(x)
            for v in x.values():
                scan(v)
        elif isinstance(x, list):
            for item in x:
                scan(item)

    scan(payload)

    uniq = {}
    for ev in eventos:
        eid = ev.get("id") or ev.get("eventId")
        if eid:
            uniq[str(eid)] = ev

    return list(uniq.values())


def extract_fecha(ev):
    for k in ("date_start", "dateStart", "startTime", "start_time", "eventDate", "date"):
        if ev.get(k):
            return ev.get(k)
    return ""


def extract_teams(ev):
    teams = ev.get("teams")

    if isinstance(teams, list) and len(teams) >= 2:
        home, away = teams[0], teams[1]

        if isinstance(home, dict):
            home = home.get("name") or home.get("shortName")
        if isinstance(away, dict):
            away = away.get("name") or away.get("shortName")

        return str(home or ""), str(away or "")

    if isinstance(teams, dict):
        home = teams.get("home") or teams.get("Home") or teams.get("1")
        away = teams.get("away") or teams.get("Away") or teams.get("2")

        if isinstance(home, dict):
            home = home.get("name") or home.get("shortName")
        if isinstance(away, dict):
            away = away.get("name") or away.get("shortName")

        return str(home or ""), str(away or "")

    home = ev.get("homeTeam") or ev.get("home_team") or ev.get("home")
    away = ev.get("awayTeam") or ev.get("away_team") or ev.get("away")

    if isinstance(home, dict):
        home = home.get("name")
    if isinstance(away, dict):
        away = away.get("name")

    return str(home or ""), str(away or "")


def buscar_cuotas_1x2(obj):
    cuotas = {"Local": "", "Empate": "", "Visita": ""}

    def scan(x):
        if isinstance(x, dict):
            name = str(x.get("name", "")).upper().strip()
            odd_id = x.get("odd_id") or x.get("oddId") or x.get("id")

            val = (
                x.get("odd_value")
                or x.get("value")
                or x.get("price")
                or x.get("coef")
                or x.get("odds")
                or x.get("decimal")
                or ""
            )

            if val != "":
                if name == "1" or str(odd_id) == "3":
                    cuotas["Local"] = cuotas["Local"] or val
                elif name == "X" or str(odd_id) == "4":
                    cuotas["Empate"] = cuotas["Empate"] or val
                elif name == "2" or str(odd_id) == "5":
                    cuotas["Visita"] = cuotas["Visita"] or val

            for v in x.values():
                scan(v)

        elif isinstance(x, list):
            for item in x:
                scan(item)

    scan(obj)
    return cuotas


# ============================================================
# PIPELINE
# ============================================================
def procesar_liga(canon, path_value):
    try:
        payload = fetch_path(canon, path_value)
    except Exception as e:
        log_error(f"[{canon}] FAIL: {e}")
        return canon, []

    eventos = encontrar_eventos(payload)
    regs = []

    print(f"  [debug] {canon}: {len(eventos)} eventos recibidos")

    for ev in eventos:
        event_id = ev.get("id") or ev.get("eventId")

        fecha_raw = extract_fecha(ev)
        dt = fecha_to_utc(fecha_raw)

        if dt is None:
            log_error(f"[{canon}] eventId={event_id} Fecha inválida: {fecha_raw}")
            continue

        # ✅ filtro 72 horas
        if dt > CUTOFF_UTC:
            continue

        local, visita = extract_teams(ev)

        if not local or not visita:
            log_error(f"[{canon}] eventId={event_id} Sin equipos")
            continue

        cuotas = buscar_cuotas_1x2(ev)

        regs.append({
            "Liga": canon,
            "Partido": f"{local} vs {visita}",
            "Fecha": fecha_raw,
            "Casa": "Stake",
            "Local": local,
            "Visita": visita,
            "Cuota Local": cuotas["Local"],
            "Cuota Empate": cuotas["Empate"],
            "Cuota Visita": cuotas["Visita"],
            "EventId": event_id,
            "Path": path_value,
        })

    return canon, regs


def main():
    if os.path.exists(ERROR_LOG):
        os.remove(ERROR_LOG)

    print(f"✅ Ligas Stake a consultar: {len(LIGAS_STAKE)}")
    print(f"✅ Filtro activo: solo eventos <= {HORAS_ADELANTE} horas")
    print(f"✅ Paralelismo: {PARALLEL_WORKERS} workers")

    registros = []

    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as ex:
        futures = []

        for canon, path_value in LIGAS_STAKE:
            futures.append(ex.submit(procesar_liga, canon, path_value))
            time.sleep(random.uniform(*STAGGER_BETWEEN_SUBMITS))

        for fut in as_completed(futures):
            try:
                canon, regs = fut.result()
                registros.extend(regs)
                print(f"  - {canon}: {len(regs)} partidos")
            except Exception as e:
                log_error(f"[FUTURE] EXCEPTION: {e}")
                print("  - ERROR (ver log)")

    if not registros:
        print("❌ No se generaron registros.")
        print("   Revisa:")
        print("   - data/error_stake_log.txt")
        print("   - data/debug_stake/")
        return

    registros.sort(key=lambda r: (r.get("Liga", ""), sort_key_fecha(r)))

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(registros, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Generado: {OUT_JSON}")
    print(f"✅ Total partidos: {len(registros)}")

    for r in registros[:25]:
        print(
            f"- {r['Liga']} | {r['Partido']} | {r['Fecha']} | "
            f"{r['Cuota Local']} / {r['Cuota Empate']} / {r['Cuota Visita']}"
        )


if __name__ == "__main__":
    main()