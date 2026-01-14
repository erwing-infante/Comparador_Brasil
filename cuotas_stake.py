# cuotas_stake.py
# Stake (websbkt) -> prematch-by-tournaments.json por tournamentId
# Extrae SOLO 1X2 desde event["main_odds"]["main"] (odd_id 3/4/5)
# Genera: data/cuotas_stake.json

import os
import json
import time
import random
import subprocess
from datetime import datetime

import pandas as pd

# ============================================================
# CONFIG
# ============================================================
OUT_DIR = "data"
os.makedirs(OUT_DIR, exist_ok=True)

OUT_JSON = os.path.join(OUT_DIR, "cuotas_stake.json")
ERROR_LOG = os.path.join(OUT_DIR, "error_stake_log.txt")
DEBUG_DIR = os.path.join(OUT_DIR, "debug_stake")
os.makedirs(DEBUG_DIR, exist_ok=True)

CURL = r"C:\Windows\System32\curl.exe"

# ✅ usa el hidenseek que YA comprobaste que funciona
HIDENSEEK_FIXED = "c657b189ad9052496b210c3532578db50afd486b"

URL_WITH_HS = (
    "https://pre-143o-sp.websbkt.com/cache/143/es/pe/{tid}/prematch-by-tournaments.json"
    f"?hidenseek={HIDENSEEK_FIXED}"
)
URL_NO_HS = "https://pre-143o-sp.websbkt.com/cache/143/es/pe/{tid}/prematch-by-tournaments.json"

# Para no gatillar NotAcceptable: secuencial + delays
SLEEP_BETWEEN_LEAGUES = (0.9, 1.8)   # (min,max) segundos
RETRIES = 5

# ============================================================
# LIGAS (MancoraBet -> Stake tournamentId)
# Formato: (canon, stake_tournament_id)
# ============================================================
LIGAS_STAKE = [
    ("Premier League", 49),
    ("EFL Cup", 396),
    ("Championship", 26909),

    ("La Liga", 83),
    ("La Liga 2", 84),
    ("Copa del Rey", 12911),

    ("Serie A", 64),
    ("Copa Italia", 66),

    ("Bundesliga", 60),
    ("Copa Alemana", 62),  # DFB Pokal

    ("Ligue 1", 57),

    ("Brasileirao", 44),
    ("Liga MX", 1292),

    ("Primeira Liga", 75),
    ("Eredivisie", 70),

    ("UEFA Champions League", 34),
    ("UEFA Europa League", 35),

    ("Copa Libertadores", 317),
    ("Copa Sudamericana", 398),

    ("Eliminatorias Europa - WC26", 18773),
]

# ============================================================
# HTTP (curl) con perfiles anti-NotAcceptable
# ============================================================
def log_error(msg: str):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def curl_get(url: str, mode: str) -> str:
    # mode: "nav" (como abrir el link) o "xhr"
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

    out = subprocess.check_output([CURL, "-sL", *headers, url], text=True, encoding="utf-8", errors="replace")
    return out.strip()

def fetch_json(url: str, canon: str, tid: int) -> dict:
    """
    - Intenta NAV primero (es el que te devolvió OK keys)
    - Si NotAcceptable: backoff y reintentos
    - Fallback a XHR si hace falta
    """
    backoff = 1.2

    for attempt in range(1, RETRIES + 1):
        out = curl_get(url, "nav")

        if out == "NotAcceptable" or out.startswith("NotAcceptable"):
            time.sleep(backoff + random.uniform(0.2, 0.8))
            backoff *= 1.6
            continue

        if out.startswith("{") or out.startswith("["):
            return json.loads(out)

        # fallback xhr
        out2 = curl_get(url, "xhr")
        if out2 == "NotAcceptable" or out2.startswith("NotAcceptable"):
            time.sleep(backoff + random.uniform(0.2, 0.8))
            backoff *= 1.6
            continue

        if out2.startswith("{") or out2.startswith("["):
            return json.loads(out2)

        # guarda respuesta rara
        dbg = os.path.join(DEBUG_DIR, f"nonjson_{canon}_{tid}_attempt{attempt}.txt")
        with open(dbg, "w", encoding="utf-8") as f:
            f.write("===NAV===\n" + out[:2000] + "\n\n===XHR===\n" + out2[:2000])
        raise RuntimeError(f"Respuesta no JSON (ver {dbg})")

    dbg = os.path.join(DEBUG_DIR, f"notacceptable_{canon}_{tid}.txt")
    with open(dbg, "w", encoding="utf-8") as f:
        f.write(f"URL: {url}\nSiempre devolvió NotAcceptable.\n")
    raise RuntimeError("NotAcceptable (bloqueo/rate-limit)")

# ============================================================
# PARSEO (tu estructura real)
# ============================================================
def parse_events(payload: dict):
    """
    En tu JSON real: payload['events'] es LISTA.
    """
    evs = payload.get("events")
    if isinstance(evs, list):
        return [e for e in evs if isinstance(e, dict)]
    # fallback si alguna liga viniera distinto
    if isinstance(evs, dict):
        return [e for e in evs.values() if isinstance(e, dict)]
    return []

def extract_teams(ev: dict):
    teams = ev.get("teams")
    # en tu JSON: teams = {"home":"...", "away":"..."}
    if isinstance(teams, dict):
        home = teams.get("home") or teams.get("Home")
        away = teams.get("away") or teams.get("Away")
        if home and away:
            return str(home), str(away)
    # fallback raro
    if isinstance(teams, list) and len(teams) >= 2:
        return str(teams[0]), str(teams[1])
    return "", ""

def extract_1x2_from_main_odds(ev: dict):
    """
    El 1X2 está dentro de ev['main_odds']['main'].
    En tu muestra:
      odd_id 3 -> Local
      odd_id 4 -> Empate
      odd_id 5 -> Visita
    Alternativamente, 'name' viene como "1","X","2".
    """
    cuotas = {"Local": "", "Empate": "", "Visita": ""}

    mo = ev.get("main_odds") or {}
    main = mo.get("main") or {}
    if not isinstance(main, dict) or not main:
        return cuotas

    # Recorremos todos los odds del main
    for _k, o in main.items():
        if not isinstance(o, dict):
            continue
        val = o.get("odd_value", "")
        name = str(o.get("name", "")).upper().strip()  # "1","X","2"
        odd_id = o.get("odd_id")

        # Primero por name
        if name == "1":
            cuotas["Local"] = val
        elif name == "X":
            cuotas["Empate"] = val
        elif name == "2":
            cuotas["Visita"] = val

        # Fallback por odd_id (3/4/5)
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

    # delay humano entre ligas
    time.sleep(random.uniform(*SLEEP_BETWEEN_LEAGUES))

    for u in urls:
        try:
            payload = fetch_json(u, canon, tid)
            break
        except Exception as e:
            last_err = e

    if payload is None:
        log_error(f"[{canon}] tid={tid} FAIL: {last_err}")
        return []

    # opcional: guarda una muestra por liga si quieres auditar
    # with open(os.path.join(DEBUG_DIR, f"payload_{canon}_{tid}.json"), "w", encoding="utf-8") as f:
    #     json.dump(payload, f, ensure_ascii=False, indent=2)

    events = parse_events(payload)
    regs = []

    for ev in events:
        local, visita = extract_teams(ev)
        if not local or not visita:
            continue

        cuotas = extract_1x2_from_main_odds(ev)

        regs.append({
            "Liga": canon,
            "Partido": f"{local} vs {visita}",
            "Fecha": ev.get("date_start", ""),
            "Casa": "Stake",
            "Local": local,
            "Visita": visita,
            "Cuota Local": cuotas["Local"],
            "Cuota Empate": cuotas["Empate"],
            "Cuota Visita": cuotas["Visita"],
            "EventId": ev.get("id"),
        })

    return regs

def main():
    # limpia logs viejos
    if os.path.exists(ERROR_LOG):
        os.remove(ERROR_LOG)

    print(f"✅ Ligas Stake a consultar: {len(LIGAS_STAKE)} (secuencial)")

    registros = []
    for canon, tid in LIGAS_STAKE:
        try:
            regs = procesar_liga(canon, tid)
            registros.extend(regs)
            print(f"  - {canon}: {len(regs)} partidos")
        except Exception as e:
            log_error(f"[{canon}] tid={tid} EXCEPTION: {e}")
            print(f"  - {canon}: ERROR (ver log)")

    if not registros:
        print("❌ No se generaron registros.")
        print("   Revisa:")
        print("   - data/error_stake_log.txt")
        print("   - data/debug_stake/")
        return

    df = pd.DataFrame(registros)
    df["_Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.sort_values(["Liga", "_Fecha"], kind="stable").drop(columns=["_Fecha"])

    df.to_json(OUT_JSON, orient="records", indent=2, force_ascii=False, date_format="iso")
    print(f"\n✅ Generado: {OUT_JSON}")
    print(f"✅ Total partidos: {len(df)}")

if __name__ == "__main__":
    main()
