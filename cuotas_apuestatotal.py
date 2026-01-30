import os
import re
import json
import time
import unicodedata
import requests
from datetime import datetime, timedelta, timezone

# ================= CONFIG =================
BASE = "https://prod20392.msjxk.com"

OUT_DIR = "data"
os.makedirs(OUT_DIR, exist_ok=True)

OUT_JSON  = os.path.join(OUT_DIR, "cuotas_apuestatotal.json")
ERROR_LOG = os.path.join(OUT_DIR, "error_log.txt")
TOKENS_FILE = os.path.join(OUT_DIR, "msjxk_tokens.json")

DEBUG_SAMPLE_FILE = os.path.join(OUT_DIR, "debug_markets_all_sample.json")

LEAGUE_EVENTS_URL = f"{BASE}/api/eventlist/eu/events/v2/league-events"
MARKETS_ALL_URL   = f"{BASE}/api/eventlist/eu/markets/all"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"

CHUNK_SIZE = 25
MARKET_CODES = ["ML0"]  # 1X2

# ✅ LÍMITE 3 DÍAS
HORAS_ADELANTE = 72
NOW_UTC = datetime.now(timezone.utc)
CUTOFF_UTC = NOW_UTC + timedelta(hours=HORAS_ADELANTE)

# ========= TUS LIGAS (NO SE TOCAN) =========
LIGAS_EQUIVALENCIAS = [
    ("Premier League", "Inglaterra", "24", "Premier League"),
    ("Copa FA", "Inglaterra", "89", "FA Cup"),
    ("Copa EFL de Inglaterra", "Inglaterra", "197992793078919168", "EFL Cup"),
    ("Championship", "Inglaterra", "43", "Championship"),
    ("La Liga", "España", "38", "La Liga"),
    ("Copa del Rey", "España", "105", "Copa del Rey"),
    ("Serie A", "Italia", "74", "Serie A"),
    ("Copa Italia", "Italia", "255821541135360000", "Copa Italia"),
    ("Bundesliga", "Alemania", "110", "Bundesliga"),
    ("Copa DFB Alemania", "Alemania", "5768", "Copa Alemana"),
    ("Ligue 1", "Francia", "25", "Ligue 1"),
    ("Coupe de France", "Francia", "35", "Copa Francia"),
    ("Brasileirao, Serie A", "Brasil", "530", "Brasileirao"),
    ("Liga MX", "México", "632", "Liga MX"),
    ("Liga 1", "Perú", "203110137349808128", "Liga 1 Perú"),
    ("Primeira Liga", "Portugal", "32", "Primeira Liga"),
    ("Eredivisie", "Países Bajos", "111", "Eredivisie"),
    ("UEFA Champions League", "Europa", "125", "UEFA Champions League"),
    ("UEFA Europa League", "Europa", "2719", "UEFA Europa League"),
    ("UEFA Europa Conference League", "Europa", "203553622255214592", "UEFA Conference League"),
    ("Clasificación Copa Libertadores", "Sudamérica", "7322", "Copa Libertadores"),
    ("Copa Sudamericana Clasificatoria", "Sudamérica", "552510194681483264", "Copa Sudamericana"),
    ("Eliminatorias europeas", "Internacional", "466", "Eliminatorias Europa - WC26"),
]

# ================= HELPERS =================
def log_error(msg: str):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def norm(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?(?:Z)?")

def normalize_fecha_iso(s: str) -> str:
    if not isinstance(s, str):
        return ""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1]
    return s

def find_fecha_in_row(row) -> str:
    if not isinstance(row, list):
        return ""
    for it in row:
        if isinstance(it, str):
            m = ISO_RE.search(it)
            if m:
                return normalize_fecha_iso(m.group(0))
        if isinstance(it, dict):
            for v in it.values():
                if isinstance(v, str):
                    m = ISO_RE.search(v)
                    if m:
                        return normalize_fecha_iso(m.group(0))
        if isinstance(it, list):
            for v in it:
                if isinstance(v, str):
                    m = ISO_RE.search(v)
                    if m:
                        return normalize_fecha_iso(m.group(0))
    return ""

def fecha_to_utc(fecha_iso_noz: str):
    """
    Convierte '2026-01-06T17:00:00.000' (sin Z) a UTC asumida.
    Si MSJXK te devuelve horas locales, esto podría tener offset; para tu filtro de 72h sirve igual.
    """
    if not fecha_iso_noz:
        return None
    try:
        dt = datetime.fromisoformat(fecha_iso_noz)
        # asumimos UTC si no trae tz
        return dt.replace(tzinfo=timezone.utc)
    except:
        return None

# ================= TOKENS =================
def load_tokens():
    if not os.path.exists(TOKENS_FILE):
        raise RuntimeError("Falta data/msjxk_tokens.json (primero genera el JWT con tu bootstrap).")
    with open(TOKENS_FILE, "r", encoding="utf-8") as f:
        t = json.load(f)
    if not t.get("jwt"):
        raise RuntimeError("msjxk_tokens.json no tiene 'jwt'.")
    return t

def make_session(tokens):
    s = requests.Session()
    if isinstance(tokens.get("cookies"), dict) and tokens["cookies"]:
        s.cookies.update(tokens["cookies"])
    if tokens.get("operatorToken"):
        s.cookies.set("operatorToken", tokens["operatorToken"])
    return s

def make_headers(tokens):
    jwt = tokens["jwt"]
    h = {
        "user-agent": UA,
        "accept": "application/json",
        "accept-language": "es-PE,es;q=0.9,en;q=0.6",
        "origin": BASE,
        "referer": f"{BASE}/es-pe/spbkv3/",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "authorization": jwt,
        "session": jwt,
    }
    if tokens.get("operatorToken"):
        h["operatorToken"] = tokens["operatorToken"]
    return h

# ================= EVENTOS =================
def get_events_by_league(s, h, league_id: str):
    r = s.get(LEAGUE_EVENTS_URL, headers=h, params={"leagueId": str(league_id)}, timeout=60)
    if r.status_code != 200:
        log_error(f"LEAGUE_EVENTS HTTP {r.status_code} leagueId={league_id} body={r.text[:300]}")
        return {}
    return r.json()

def parse_events(data):
    evs = []
    payload = data.get("data", [])
    if not isinstance(payload, list):
        return evs

    for row in payload:
        if not isinstance(row, list) or len(row) < 2:
            continue

        eid = str(row[0]) if row[0] is not None else ""
        if not eid:
            continue

        home = ""
        away = ""

        comps = row[8] if len(row) > 8 else None
        if isinstance(comps, list):
            for c in comps:
                if isinstance(c, list) and len(c) >= 3:
                    name_obj = c[1]
                    side = str(c[2]).lower()
                    name = ""
                    if isinstance(name_obj, dict) and name_obj:
                        name = name_obj.get("ES-PE") or name_obj.get("es-PE") or next(iter(name_obj.values()), "")
                    elif isinstance(name_obj, str):
                        name = name_obj

                    if "home" in side:
                        home = name
                    elif "away" in side:
                        away = name

        start_time = find_fecha_in_row(row)

        evs.append({
            "EventId": eid,
            "Local": home,
            "Visita": away,
            "Fecha": start_time
        })

    return evs

# ================= MARKETS (BULK + RETRY) =================
def get_markets(s, h, event_ids, max_retries=6):
    markets_param = "|".join(event_ids) + ":" + "|".join(MARKET_CODES)
    params = {"markets": markets_param}

    last_status = None
    last_text = ""

    for attempt in range(1, max_retries + 1):
        try:
            r = s.get(MARKETS_ALL_URL, headers=h, params=params, timeout=60)
            last_status = r.status_code
            last_text = r.text[:300]

            if r.status_code == 200:
                return r.json()

            if r.status_code in (429, 500, 502, 503, 504):
                wait = min(2 ** attempt, 30) + (0.2 * attempt)
                log_error(f"MARKETS_ALL {r.status_code} (attempt {attempt}/{max_retries}) -> sleep {wait:.1f}s")
                time.sleep(wait)
                continue

            log_error(f"MARKETS_ALL HTTP {r.status_code}: {last_text}")
            return {}

        except requests.exceptions.RequestException as e:
            wait = min(2 ** attempt, 30) + (0.2 * attempt)
            log_error(f"MARKETS_ALL EXC (attempt {attempt}/{max_retries}): {e} -> sleep {wait:.1f}s")
            time.sleep(wait)

    log_error(f"MARKETS_ALL FAIL definitivo. Last status={last_status} body={last_text}")
    return {}

# ================= EXTRACT 1X2 (MSJXK REAL) =================
def extract_1x2_msjxk(root):
    out = {}

    markets = root
    if isinstance(root, dict):
        if isinstance(root.get("data"), list):
            markets = root["data"]
        elif isinstance(root.get("Data"), list):
            markets = root["Data"]

    if not isinstance(markets, list):
        return out

    for m in markets:
        if not isinstance(m, dict):
            continue

        mt = m.get("MarketType") or {}
        mt_id = str(mt.get("_id") or "") if isinstance(mt, dict) else ""

        if mt_id != "ML0":
            continue

        eid = str(m.get("EventId") or "").strip()
        if not eid:
            continue

        sels = m.get("Selections") or []
        if not isinstance(sels, list):
            continue

        L = E = V = ""

        for s in sels:
            if not isinstance(s, dict):
                continue

            outcome = norm(s.get("OutcomeType") or "")
            side = s.get("Side")

            dec = ""
            odds = s.get("DisplayOdds") or {}
            if isinstance(odds, dict):
                dec = str(odds.get("Decimal") or "").strip()

            if not dec and isinstance(s.get("TrueOdds"), (int, float)):
                dec = str(s.get("TrueOdds"))

            if not dec:
                continue

            if outcome == "local" or side == 1:
                L = dec
            elif outcome == "empate" or side == 2:
                E = dec
            elif outcome == "visita" or side == 3:
                V = dec

        if L and E and V:
            out[eid] = {"Local": L, "Empate": E, "Visita": V}

    return out

# ================= MAIN =================
def main():
    try:
        tokens = load_tokens()
    except Exception as e:
        print(f"❌ {e}")
        return

    s = make_session(tokens)
    h = make_headers(tokens)

    eventos = []
    liga_por_evento = {}

    # 1) eventos por liga
    for _, _, league_id, liga_out in LIGAS_EQUIVALENCIAS:
        data = get_events_by_league(s, h, league_id)
        evs = parse_events(data)

        # ✅ FILTRO 72h AQUÍ (antes de juntar todo)
        evs_fil = []
        for e in evs:
            dt = fecha_to_utc(e.get("Fecha", ""))
            if dt is None:
                continue
            if dt <= CUTOFF_UTC:
                evs_fil.append(e)

        print(f"✅ {liga_out}: {len(evs_fil)} eventos (<= {HORAS_ADELANTE}h)")
        for e in evs_fil:
            liga_por_evento[e["EventId"]] = liga_out
        eventos.extend(evs_fil)

    # dedupe por EventId
    uniq = {}
    for e in eventos:
        uniq[e["EventId"]] = e
    eventos = list(uniq.values())

    event_ids = [e["EventId"] for e in eventos]
    if not event_ids:
        print("❌ No hay eventos en ventana 72h. Revisa error_log.txt")
        return

    # 2) cuotas bulk
    cuotas = {}
    total_chunks = 0
    ok_chunks = 0
    saved_sample = False

    for ch in chunked(event_ids, CHUNK_SIZE):
        total_chunks += 1
        mj = get_markets(s, h, ch)
        if mj:
            ok_chunks += 1

            if not saved_sample:
                try:
                    with open(DEBUG_SAMPLE_FILE, "w", encoding="utf-8") as f:
                        json.dump(mj, f, ensure_ascii=False, indent=2)
                    saved_sample = True
                except Exception as e:
                    log_error(f"No pude guardar debug sample: {e}")

            cuotas.update(extract_1x2_msjxk(mj))

        time.sleep(0.10)

    print(f"✅ chunks OK: {ok_chunks}/{total_chunks}")
    print(f"✅ 1X2 detectadas: {len(cuotas)}")

    # 3) salida final
    salida = []
    for e in eventos:
        eid = e["EventId"]
        c = cuotas.get(eid)
        if not c:
            continue

        local = e.get("Local", "")
        visita = e.get("Visita", "")

        salida.append({
            "Liga": liga_por_evento.get(eid, ""),
            "Partido": f"{local} vs {visita}",
            "Fecha": e.get("Fecha", ""),
            "Casa": "Apuesta Total",
            "Local": local,
            "Visita": visita,
            "Cuota Local": c["Local"],
            "Cuota Empate": c["Empate"],
            "Cuota Visita": c["Visita"],
            "EventId": int(eid) if str(eid).isdigit() else eid
        })

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(salida)} partidos guardados -> {OUT_JSON}")

if __name__ == "__main__":
    main()
