# cuotas_stake.py
# Stake (websbkt) -> prematch-by-tournaments.json por tournamentId
# Extrae SOLO 1X2 desde event["main_odds"]["main"] (odd_id 3/4/5)
# Genera: data/cuotas_stake.json

import os
import json
import time
import random
import subprocess
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

CURL = "curl"

# ✅ tu proxy real
PROXY = "http://df74ae506e168856:JZjsITW0@res.proxy-seller.com:10000"

# ✅ usa el hidenseek que ya te funciona
HIDENSEEK_FIXED = "c657b189ad9052496b210c3532578db50afd486b"

URL_WITH_HS = (
    "https://pre-143o-sp.websbkt.com/cache/143/es/pe/{tid}/prematch-by-tournaments.json"
    f"?hidenseek={HIDENSEEK_FIXED}"
)
URL_NO_HS = "https://pre-143o-sp.websbkt.com/cache/143/es/pe/{tid}/prematch-by-tournaments.json"

# velocidad / estabilidad
RETRIES = 4
PARALLEL_WORKERS = 2
STAGGER_BETWEEN_SUBMITS = (0.20, 0.45)
SLEEP_BETWEEN_RETRIES_EXTRA = (0.15, 0.45)

# ✅ límite 72 horas
HORAS_ADELANTE = 72
NOW_UTC = datetime.now(timezone.utc)
CUTOFF_UTC = NOW_UTC + timedelta(hours=HORAS_ADELANTE)

# ============================================================
# LIGAS
# ============================================================
LIGAS_STAKE = [
    ("Premier League", 49),
    ("La Liga", 83),
    ("Serie A", 64),
    ("Bundesliga", 60),
    ("Ligue 1", 57),
    ("Brasileirao", 44),
    ("UEFA Champions League", 34),
    ("UEFA Europa League", 35),

    ("Copa Libertadores", 317),
    ("Copa Sudamericana", 398),

    ("Eliminatorias Europa - WC26", 18773),
]

# ============================================================
# HELPERS
# ============================================================
def log_error(msg: str):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def fecha_to_utc(fecha_raw):
    """
    Soporta:
    - '2026-03-14T13:00:00Z'
    - '2026-03-14T13:00:00.000Z'
    - '2026-03-14T13:00:00'
    - '2026-03-14 13:00:00'
    - 1710536400          (unix segundos)
    - 1710536400000       (unix milisegundos)
    """
    if fecha_raw is None or fecha_raw == "":
        return None

    # unix timestamp numérico
    if isinstance(fecha_raw, (int, float)):
        try:
            val = float(fecha_raw)
            if val > 10_000_000_000:  # milisegundos
                val = val / 1000.0
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None

    s = str(fecha_raw).strip()
    if not s:
        return None

    # unix timestamp en string
    if s.isdigit():
        try:
            val = float(s)
            if val > 10_000_000_000:
                val = val / 1000.0
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
    dt = fecha_to_utc(reg.get("Fecha", ""))
    if dt is None:
        return datetime.max.replace(tzinfo=timezone.utc)
    return dt

# ============================================================
# HTTP (curl)
# ============================================================
def curl_get(url: str, mode: str) -> str:
    if mode == "nav":
        headers = [
            "-H", "accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "-H", "accept-language: es-ES,es;q=0.9,en;q=0.8",
            "-H", "cache-control: no-cache",
            "-H", "pragma: no-cache",
            "-H", "upgrade-insecure-requests: 1",
            "-H", "sec-fetch-dest: document",
            "-H", "sec-fetch-mode: navigate",
            "-H", "sec-fetch-site: none",
            "-H", "sec-fetch-user: ?1",
            "-H", 'sec-ch-ua: "Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "-H", "sec-ch-ua-mobile: ?0",
            "-H", 'sec-ch-ua-platform: "Windows"',
            "-H", "referer: https://stake.pe/sports",
            "-H", "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        ]
    else:
        headers = [
            "-H", "accept: application/json, text/plain, */*",
            "-H", "accept-language: es-ES,es;q=0.9,en;q=0.8",
            "-H", "cache-control: no-cache",
            "-H", "pragma: no-cache",
            "-H", "sec-fetch-dest: empty",
            "-H", "sec-fetch-mode: cors",
            "-H", "sec-fetch-site: cross-site",
            "-H", 'sec-ch-ua: "Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            "-H", "sec-ch-ua-mobile: ?0",
            "-H", 'sec-ch-ua-platform: "Windows"',
            "-H", "referer: https://stake.pe/sports",
            "-H", "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        ]

    cmd = [
        CURL,
        "-sL",
        "--http1.1",
        "--compressed",
        "--proxy", PROXY,
        "--connect-timeout", "15",
        "--max-time", "30",
        *headers,
        url,
    ]

    out = subprocess.check_output(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    return out.strip()

def fetch_json(url: str, canon: str, tid: int) -> dict:
    backoff = 0.9

    for attempt in range(1, RETRIES + 1):
        out = curl_get(url, "nav")

        if out == "NotAcceptable" or out.startswith("NotAcceptable"):
            time.sleep(backoff + random.uniform(*SLEEP_BETWEEN_RETRIES_EXTRA))
            backoff *= 1.5
            continue

        if out.startswith("{") or out.startswith("["):
            return json.loads(out)

        out2 = curl_get(url, "xhr")
        if out2 == "NotAcceptable" or out2.startswith("NotAcceptable"):
            time.sleep(backoff + random.uniform(*SLEEP_BETWEEN_RETRIES_EXTRA))
            backoff *= 1.5
            continue

        if out2.startswith("{") or out2.startswith("["):
            return json.loads(out2)

        dbg = os.path.join(DEBUG_DIR, f"nonjson_{canon}_{tid}_attempt{attempt}.txt")
        with open(dbg, "w", encoding="utf-8") as f:
            f.write("===NAV===\n" + out[:2000] + "\n\n===XHR===\n" + out2[:2000])
        raise RuntimeError(f"Respuesta no JSON (ver {dbg})")

    dbg = os.path.join(DEBUG_DIR, f"notacceptable_{canon}_{tid}.txt")
    with open(dbg, "w", encoding="utf-8") as f:
        f.write(f"URL: {url}\nSiempre devolvió NotAcceptable.\n")
    raise RuntimeError("NotAcceptable (bloqueo/rate-limit)")

# ============================================================
# PARSEO
# ============================================================
def parse_events(payload: dict):
    evs = payload.get("events")
    if isinstance(evs, list):
        return [e for e in evs if isinstance(e, dict)]
    if isinstance(evs, dict):
        return [e for e in evs.values() if isinstance(e, dict)]
    return []

def extract_teams(ev: dict):
    teams = ev.get("teams")
    if isinstance(teams, dict):
        home = teams.get("home") or teams.get("Home")
        away = teams.get("away") or teams.get("Away")
        if home and away:
            return str(home), str(away)

    if isinstance(teams, list) and len(teams) >= 2:
        return str(teams[0]), str(teams[1])

    return "", ""

def extract_1x2_from_main_odds(ev: dict):
    cuotas = {"Local": "", "Empate": "", "Visita": ""}

    mo = ev.get("main_odds") or {}
    main = mo.get("main") or {}
    if not isinstance(main, dict) or not main:
        return cuotas

    for _k, o in main.items():
        if not isinstance(o, dict):
            continue

        val = o.get("odd_value", "")
        name = str(o.get("name", "")).upper().strip()
        odd_id = o.get("odd_id")

        if name == "1":
            cuotas["Local"] = val
        elif name == "X":
            cuotas["Empate"] = val
        elif name == "2":
            cuotas["Visita"] = val

        if odd_id == 3 and not cuotas["Local"]:
            cuotas["Local"] = val
        elif odd_id == 4 and not cuotas["Empate"]:
            cuotas["Empate"] = val
        elif odd_id == 5 and not cuotas["Visita"]:
            cuotas["Visita"] = val

    return cuotas

# ============================================================
# PIPELINE
# ============================================================
def procesar_liga(canon: str, tid: int):
    urls = [
        URL_WITH_HS.format(tid=tid),
        URL_NO_HS.format(tid=tid),
    ]

    payload = None
    last_err = None

    for u in urls:
        try:
            payload = fetch_json(u, canon, tid)
            break
        except Exception as e:
            last_err = e

    if payload is None:
        log_error(f"[{canon}] tid={tid} FAIL: {last_err}")
        return canon, []

    events = parse_events(payload)
    regs = []

    print(f"  [debug] {canon}: {len(events)} eventos recibidos")

    for ev in events:
        local, visita = extract_teams(ev)
        if not local or not visita:
            continue

        fecha_raw = ev.get("date_start", "")
        dt = fecha_to_utc(fecha_raw)
        if dt is None:
            continue

        # ✅ igual que Apuesta Total: solo <= 72h
        if dt > CUTOFF_UTC:
            continue

        cuotas = extract_1x2_from_main_odds(ev)

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
            "EventId": ev.get("id"),
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

        for canon, tid in LIGAS_STAKE:
            futures.append(ex.submit(procesar_liga, canon, tid))
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

if __name__ == "__main__":
    main()