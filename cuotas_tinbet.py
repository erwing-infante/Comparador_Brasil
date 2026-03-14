import os
import re
import json
import time
import unicodedata
import requests
from datetime import datetime, timedelta, timezone

# ================= CONFIG =================
BASE = "https://prod20465-178940673.fssb.io"

OUT_DIR = "data"
os.makedirs(OUT_DIR, exist_ok=True)

OUT_JSON  = os.path.join(OUT_DIR, "cuotas_tinbet.json")
ERROR_LOG = os.path.join(OUT_DIR, "error_log.txt")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

# ========= TOKENS (LOS QUE ME PASASTE) =========
AUTHORIZATION_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJsYW5ndWFnZUNvZGUiOiJlcyIsImN1cnJlbmN5UmF0ZSI6MSwiY3VycmVuY3lSYXRlZXVyIjoxLCJjdXN0b21lckxpbWl0cyI6W10sImN1c3RvbWVyVHlwZSI6ImFub24iLCJjdXJyZW5jeUNvZGUiOiJQRU4iLCJjdXJyZW5jeUNvZGVBbm9uIjoiIiwiY3VzdG9tZXJJZCI6LTEsImJldHRpbmdWaWV3IjoiRXVyb3BlYW4gVmlldyIsInNvcnRpbmdUeXBlSWQiOjAsImJldHRpbmdMYXlvdXQiOjEsImRpc3BsYXlUeXBlSWQiOjEsInRpbWV6b25lSWQiOjgsImF1dG9UaW1lWm9uZSI6MSwibGFzdElucHV0U3Rha2UiOjAsImV1T2Rkc0lkIjoiMSIsImFzaWFuT2Rkc0lkIjoiMyIsImtvcmVhbk9kZHNJZCI6IjEiLCJpbnRUYWJFeHBhbmRlZCI6MSwiZG9tYWluSUQiOjQzODgsImFnZW50SUQiOjE3ODk0MDY3Mywic2l0ZUlkIjoyMDQ2NSwic2VsZWN0ZWRPcHRpb25JZCI6MCwiY3VzdG9tZXJMZXZlbCI6MCwiYmFsYW5jZVByaW9yaXR5IjoxLCJFUE9FbmFibGVkIjp0cnVlLCJpYXQiOjE3NzM0NjAwNjJ9.X67U0heMjtS47AAUDSecIHKYzSdNNnCoVYqTjF8x4Jg"
SESSION_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJjdXN0b21lcklkIjotMSwiZXhwaXJlZERhdGUiOjE3NzM1NDY0NjIzMzcsImlhdCI6MTc3MzQ2MDA2Mn0.6LOVg6Uado7E4XHDlMX9ftojZv4xic2YRBazgD-7LOE"

# ✅ solo 1X2 principal
MARKET_TYPE_IDS = "ML0"

# ✅ límite 72h
HORAS_ADELANTE = 72
NOW_UTC = datetime.now(timezone.utc)
CUTOFF_UTC = NOW_UTC + timedelta(hours=HORAS_ADELANTE)

# ========= LIGAS =========
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
    ("MLS", "Estados Unidos", "224", "MLS"),
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
def log_error(msg):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")

def norm(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def fecha_to_utc(fecha_iso):
    try:
        if not fecha_iso:
            return None
        if fecha_iso.endswith("Z"):
            return datetime.fromisoformat(fecha_iso.replace("Z", "+00:00"))
        return datetime.fromisoformat(fecha_iso).replace(tzinfo=timezone.utc)
    except:
        return None

ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")

def find_fecha(row):
    for x in row:
        if isinstance(x, str):
            m = ISO_RE.search(x)
            if m:
                return m.group(0)
    return ""

def find_equipos(row):
    for x in row:
        if not isinstance(x, list):
            continue

        home = ""
        away = ""

        for item in x:
            if not isinstance(item, list) or len(item) < 3:
                continue

            nombre_obj = item[1]
            side = str(item[2]).lower()

            nombre = ""
            if isinstance(nombre_obj, dict):
                nombre = nombre_obj.get("ES") or nombre_obj.get("ES-PE") or next(iter(nombre_obj.values()), "")
            elif isinstance(nombre_obj, str):
                nombre = nombre_obj

            if "home" in side:
                home = nombre
            elif "away" in side:
                away = nombre

        if home or away:
            return home, away

    return "", ""

def find_markets(row):
    for x in row:
        if not isinstance(x, list):
            continue

        for m in x:
            if isinstance(m, list) and len(m) > 3 and isinstance(m[3], list):
                code = str(m[3][0])
                if code.startswith("ML") or code.startswith("OU") or code.startswith("QA"):
                    return x

    return []

def extract_ml0(markets):
    L = E = V = ""

    for m in markets:
        if not isinstance(m, list) or len(m) < 8:
            continue

        market_info = m[3]
        if not isinstance(market_info, list):
            continue

        code = str(market_info[0])

        if code != "ML0":
            continue

        selections = m[7]

        for s in selections:
            if not isinstance(s, list) or len(s) < 8:
                continue

            cuota = str(s[4])
            side = s[7]

            if side == 1:
                L = cuota
            elif side == 2:
                E = cuota
            elif side == 3:
                V = cuota

        break

    return L, E, V

# ================= SESSION =================
def make_session():
    s = requests.Session()
    s.cookies.set("authorization", AUTHORIZATION_TOKEN)
    s.cookies.set("session", SESSION_TOKEN)
    return s

def make_headers(league_name_slug="La-Liga", country_slug="Espa%C3%B1a"):
    return {
        "user-agent": UA,
        "accept": "application/json",
        "accept-language": "es-US,es-PE;q=0.9,es-419;q=0.8,es;q=0.7,en;q=0.6",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "authorization": AUTHORIZATION_TOKEN,
        "session": SESSION_TOKEN,
        "referer": f"{BASE}/es/spbk/F%C3%BAtbol/{country_slug}/{league_name_slug}"
    }

# ================= REQUEST =================
def get_gameodds(s, h, league_id):
    url = f"{BASE}/api/eventlist/eu/leagues/v2/{league_id}/gameOdds"
    params = {
        "marketTypeIds": MARKET_TYPE_IDS,
        "IsLive": "false"
    }

    try:
        r = s.get(url, headers=h, params=params, timeout=20)
        print(f"STATUS league={league_id}: {r.status_code}")

        if r.status_code != 200:
            log_error(f"TINBET HTTP {r.status_code} league={league_id} body={r.text[:400]}")
            return {}

        return r.json()
    except Exception as e:
        log_error(f"TINBET EXC league={league_id}: {e}")
        return {}

# ================= MAIN =================
def main():
    s = make_session()
    salida = []

    for _, pais, league_id, liga in LIGAS_EQUIVALENCIAS:
        country_slug = requests.utils.quote(pais, safe="")
        league_slug = requests.utils.quote(liga.replace(" ", "-"), safe="")
        h = make_headers(league_slug, country_slug)

        data = get_gameodds(s, h, league_id)

        if not data:
            print(f"❌ {liga}")
            continue

        payload = data.get("data", [])
        print(f"EVENTOS {liga}: {len(payload)}")

        count_liga = 0

        for row in payload:
            if not isinstance(row, list):
                continue

            try:
                event_id = str(row[0])
            except:
                continue

            fecha = find_fecha(row)
            dt = fecha_to_utc(fecha)

            if dt is None or dt > CUTOFF_UTC:
                continue

            local, visita = find_equipos(row)
            markets = find_markets(row)
            L, E, V = extract_ml0(markets)

            if not (L and E and V):
                continue

            salida.append({
                "Liga": liga,
                "Partido": f"{local} vs {visita}",
                "Fecha": fecha,
                "Casa": "Tinbet",
                "Local": local,
                "Visita": visita,
                "Cuota Local": L,
                "Cuota Empate": E,
                "Cuota Visita": V,
                "EventId": event_id
            })
            count_liga += 1

        print(f"✅ {liga}: {count_liga} partidos")
        time.sleep(0.15)

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)

    print(f"✅ PARTIDOS GUARDADOS: {len(salida)} -> {OUT_JSON}")

if __name__ == "__main__":
    main()