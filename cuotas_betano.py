import json
import os
import time
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

# ===========================
# ✅ FECHA EN GMT 0 (UTC)
# ===========================
TZ_LOCAL = timezone.utc

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_betano.json")
PROFILE_DIR = os.path.join(DATA_DIR, "betano_profile")
ERROR_LOG = os.path.join(DATA_DIR, "betano_errors.log")

HEADFUL = os.getenv("BETANO_HEADFUL", "") == "1"

REQ = "la,s,stnf,c,mb"
BT = "matchresult"
DIAS_A_FUTURO = 3  # próximos 3 días

# ===========================
# ✅ BETANO ALEMANIA (.de)
# ===========================
HOME_URL = "https://www.betano.de/"

# Warmup: Premier League
WARMUP_LEAGUE_PAGE = "https://www.betano.de/sport/fussball/england/premier-league/1/?bt=matchresult"
WARMUP_API = "https://www.betano.de/api/sport/fussball/england/premier-league/1/"

LIGAS = [
    {"name": "Premier League",
     "page": "https://www.betano.de/sport/fussball/england/premier-league/1/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/england/premier-league/1/"},
    {"name": "FA Cup",
     "page": "https://www.betano.de/sport/fussball/england/copa-de-la-fa/218/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/england/copa-de-la-fa/218/"},
    {"name": "EFL Cup",
     "page": "https://www.betano.de/sport/fussball/england/efl-cup/10215/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/england/efl-cup/10215/"},
    {"name": "Championship",
     "page": "https://www.betano.de/sport/fussball/england/championship/2/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/england/championship/2/"},

    {"name": "La Liga",
     "page": "https://www.betano.de/sport/fussball/espana/laliga/5/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/espana/laliga/5/"},
     
    {"name": "Copa del Rey",
     "page": "https://www.betano.de/sport/fussball/espana/copa-del-rey/10067/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/espana/copa-del-rey/10067/"},

    {"name": "Serie A",
     "page": "https://www.betano.de/sport/fussball/italia/serie-a/1635/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/italia/serie-a/1635/"},
    {"name": "Copa Italia",
     "page": "https://www.betano.de/sport/fussball/italia/coppa-italia/10815/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/italia/coppa-italia/10815/"},

    {"name": "Bundesliga",
     "page": "https://www.betano.de/sport/fussball/alemania/bundesliga/216/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/alemania/bundesliga/216/"},
    {"name": "Copa Alemana",
     "page": "https://www.betano.de/sport/fussball/alemania/dfb-pokal/10486/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/alemania/dfb-pokal/10486/"},

    {"name": "Ligue 1",
     "page": "https://www.betano.de/sport/fussball/francia/ligue-1/215/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/francia/ligue-1/215/"},

    {"name": "Brasileirao",
     "page": "https://www.betano.de/sport/fussball/brasil/brasileirao-serie-a-betano/10016/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/brasil/brasileirao-serie-a-betano/10016/"},
    {"name": "Copa de Brasil",
     "page": "https://www.betano.de/sport/fussball/brasil/copa-betano-do-brasil/10008/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/brasil/copa-betano-do-brasil/10008/"},

    {"name": "Liga MX",
     "page": "https://www.betano.de/sport/fussball/mexico/liga-mx/17264/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/mexico/liga-mx/17264/"},
    {"name": "MLS",
     "page": "https://www.betano.de/sport/fussball/ee-uu/mls/17103/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/ee-uu/mls/17103/"},
    {"name": "Liga 1 Perú",
     "page": "https://www.betano.de/sport/fussball/peru/liga-1/17079/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/peru/liga-1/17079/"},
    {"name": "Primeira Liga",
     "page": "https://www.betano.de/sport/fussball/portugal/primeira-liga/17083/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/portugal/primeira-liga/17083/"},
    {"name": "Eredivisie",
     "page": "https://www.betano.de/sport/fussball/paises-bajos/eredivisie/17067/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/paises-bajos/eredivisie/17067/"},

    {"name": "UEFA Champions League",
     "page": "https://www.betano.de/sport/fussball/campeonatos/champions-league/188566/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/campeonatos/champions-league/188566/"},
    {"name": "UEFA Europa League",
     "page": "https://www.betano.de/sport/fussball/campeonatos/europa-league/188567/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/campeonatos/europa-league/188567/"},
    {"name": "UEFA Conference League",
     "page": "https://www.betano.de/sport/fussball/campeonatos/conference-league/189602/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/campeonatos/conference-league/189602/"},
    {"name": "Copa Libertadores",
     "page": "https://www.betano.de/sport/fussball/campeonatos/copa-libertadores/189817/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/campeonatos/copa-libertadores/189817/"},
    {"name": "Copa Sudamericana",
     "page": "https://www.betano.de/sport/fussball/campeonatos/copa-sudamericana/189818/?bt=matchresult",
     "api":  "https://www.betano.de/api/sport/fussball/campeonatos/copa-sudamericana/189818/"},
]

def log_error(msg: str):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")

# ✅ ahora devuelve UTC
def ms_to_lima(ms: int) -> datetime:
    dt_utc = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return dt_utc.astimezone(TZ_LOCAL)

def to_iso_like(dt: datetime) -> str:
    return dt.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%S.000")

def parse_teams(name: str):
    if not name:
        return None, None
    for sep in [" - ", " vs. ", " vs ", " v "]:
        if sep in name:
            a, b = name.split(sep, 1)
            return a.strip(), b.strip()
    return None, None

def pick_1x2(markets):
    for m in markets or []:
        if str(m.get("type", "")).upper() == "MRES":
            return m
    for m in markets or []:
        if str(m.get("name", "")).strip().lower() in ("resultado del partido", "match result", "resultado", "spielergebnis"):
            return m
    return None

def extract_prices(market):
    one = x = two = None
    for s in market.get("selections", []) or []:
        k = str(s.get("name", "")).strip().upper()
        p = s.get("price", None)
        if p is None:
            continue
        if k == "1":
            one = float(p)
        elif k == "X":
            x = float(p)
        elif k == "2":
            two = float(p)
    return one, x, two

def looks_like_event(d: dict) -> bool:
    return isinstance(d, dict) and "id" in d and "startTime" in d and isinstance(d.get("markets"), list)

def collect_events(payload) -> list[dict]:
    found = []
    def walk(x):
        if isinstance(x, dict):
            if looks_like_event(x):
                found.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(payload)
    uniq = {}
    for ev in found:
        uniq[str(ev.get("id"))] = ev
    return list(uniq.values())

def fetch_raw(page, url: str):
    return page.evaluate(
        """async (u) => {
            const r = await fetch(u, { credentials: 'include' });
            return { status: r.status, ct: r.headers.get('content-type') || '', text: await r.text() };
        }""",
        url
    )

def fetch_json_with_retry(page, api_base: str, league_page: str):
    url = f"{api_base}?bt={BT}&req={REQ}"

    resp = fetch_raw(page, url)
    if resp["status"] == 200 and "application/json" in (resp["ct"] or "").lower():
        return json.loads(resp["text"])

    page.goto(league_page, wait_until="domcontentloaded")
    resp = fetch_raw(page, url)
    if resp["status"] == 200 and "application/json" in (resp["ct"] or "").lower():
        return json.loads(resp["text"])

    snippet = (resp["text"] or "")[:180].replace("\n", " ")
    raise RuntimeError(f"HTTP {resp['status']} | {resp['ct']} | {snippet}")

def warmup_access(page):
    page.goto(WARMUP_LEAGUE_PAGE, wait_until="domcontentloaded")
    for _ in range(60):
        resp = fetch_raw(page, f"{WARMUP_API}?bt={BT}&req={REQ}")
        if resp["status"] == 200 and "application/json" in (resp["ct"] or "").lower():
            return True
        time.sleep(1)
    return False

def main():
    try:
        if os.path.exists(ERROR_LOG):
            os.remove(ERROR_LOG)
    except Exception:
        pass

    # ✅ now/end en UTC
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=DIAS_A_FUTURO)

    resultados = []
    estado = {}

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=not HEADFUL,
            locale="de-DE",
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        page.goto(HOME_URL, wait_until="domcontentloaded")

        ok = warmup_access(page)
        if not ok:
            print("⚠️ Betano.de: no se habilitó el acceso al API (splash/consent). Revisa betano_errors.log.")
            context.close()
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                f.write("[]")
            return

        for lig in LIGAS:
            name = lig["name"]
            try:
                payload = fetch_json_with_retry(page, lig["api"], lig["page"])
                eventos = collect_events(payload)

                if not eventos:
                    estado[name] = 0
                    continue

                count = 0
                for ev in eventos:
                    ms = ev.get("startTime")
                    if ms is None:
                        continue

                    # ✅ dt en UTC
                    dt = ms_to_lima(int(ms))
                    if not (now <= dt <= end):
                        continue

                    market = pick_1x2(ev.get("markets", []))
                    if not market:
                        continue
                    one, x, two = extract_prices(market)
                    if None in (one, x, two):
                        continue

                    ev_name = ev.get("name") or ev.get("shortName") or ""
                    home, away = parse_teams(ev_name)

                    resultados.append({
                        "Liga": name,
                        "Partido": f"{home} vs {away}" if home and away else ev_name,
                        "Fecha": to_iso_like(dt),  # ✅ UTC
                        "Casa": "Betano",
                        "Local": home,
                        "Visita": away,
                        "Cuota Local": one,
                        "Cuota Empate": x,
                        "Cuota Visita": two,
                        "EventId": str(ev.get("id")),
                    })
                    count += 1

                estado[name] = count

            except Exception as e:
                estado[name] = "ERROR"
                log_error(f"[{name}] {e}")

        context.close()

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    for liga, st in estado.items():
        if st == "ERROR":
            print(f"⚠️ {liga}: ERROR")
        elif st == 0:
            print(f"❌ {liga}: 0 eventos")
        else:
            print(f"✅ {liga}: OK ({st} cuotas)")

    print(f"\n💾 Total guardado: {len(resultados)} -> {OUT_PATH}")
    if os.path.exists(ERROR_LOG):
        print(f"🧾 Detalles: {ERROR_LOG}")

if __name__ == "__main__":
    main()
