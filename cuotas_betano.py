import json
import os
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright

TZ_LOCAL = ZoneInfo("America/Lima")

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

OUT_PATH = os.path.join(DATA_DIR, "cuotas_betano.json")
PROFILE_DIR = os.path.join(DATA_DIR, "betano_profile")
ERROR_LOG = os.path.join(DATA_DIR, "betano_errors.log")

HEADFUL = os.getenv("BETANO_HEADFUL", "") == "1"

REQ = "la,s,stnf,c,mb"
BT = "matchresult"
DIAS_A_FUTURO = 3  # ✅ próximos 3 días

# Warmup: probamos Serie A hasta que devuelva JSON (tú resuelves el consent en la ventana)
WARMUP_LEAGUE_PAGE = "https://www.betano.pe/sport/futbol/italia/serie-a/1635r/?bt=matchresult"
WARMUP_API = "https://www.betano.pe/api/sport/futbol/italia/serie-a/1635/"

LIGAS = [
    {"name": "Premier League", "page": "https://www.betano.pe/sport/futbol/inglaterra/premier-league/1r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/inglaterra/premier-league/1/"},
    {"name": "FA Cup", "page": "https://www.betano.pe/sport/futbol/inglaterra/copa-de-la-fa/218r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/inglaterra/copa-de-la-fa/218/"},
    {"name": "EFL Cup", "page": "https://www.betano.pe/sport/futbol/inglaterra/efl-cup/10215r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/inglaterra/efl-cup/10215/"},
    {"name": "Championship", "page": "https://www.betano.pe/sport/futbol/inglaterra/championship/2r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/inglaterra/championship/2/"},
    {"name": "La Liga", "page": "https://www.betano.pe/sport/futbol/espana/laliga/5r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/espana/laliga/5/"},
    {"name": "La Liga 2", "page": "https://www.betano.pe/sport/futbol/espana/segunda-division/10000r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/espana/segunda-division/10000/"},
    {"name": "Copa del Rey", "page": "https://www.betano.pe/sport/futbol/espana/copa-del-rey/10067r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/espana/copa-del-rey/10067/"},
    {"name": "Serie A", "page": "https://www.betano.pe/sport/futbol/italia/serie-a/1635r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/italia/serie-a/1635/"},
    {"name": "Copa Italia", "page": "https://www.betano.pe/sport/futbol/italia/coppa-italia/10815r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/italia/coppa-italia/10815/"},
    {"name": "Bundesliga", "page": "https://www.betano.pe/sport/futbol/alemania/bundesliga/216r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/alemania/bundesliga/216/"},
    {"name": "Copa Alemana", "page": "https://www.betano.pe/sport/futbol/alemania/dfb-pokal/10486r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/alemania/dfb-pokal/10486/"},
    {"name": "Ligue 1", "page": "https://www.betano.pe/sport/futbol/francia/ligue-1/215r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/francia/ligue-1/215/"},
    {"name": "Brasileirao", "page": "https://www.betano.pe/sport/futbol/brasil/brasileirao-serie-a-betano/10016r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/brasil/brasileirao-serie-a-betano/10016/"},
    {"name": "Copa de Brasil", "page": "https://www.betano.pe/sport/futbol/brasil/copa-betano-do-brasil/10008r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/brasil/copa-betano-do-brasil/10008/"},
    {"name": "Liga MX", "page": "https://www.betano.pe/sport/futbol/mexico/liga-mx/17264r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/mexico/liga-mx/17264/"},
    {"name": "MLS", "page": "https://www.betano.pe/sport/futbol/ee-uu/mls/17103r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/ee-uu/mls/17103/"},
    {"name": "Liga 1 Perú", "page": "https://www.betano.pe/sport/futbol/peru/liga-1/17079r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/peru/liga-1/17079/"},
    {"name": "Primeira Liga", "page": "https://www.betano.pe/sport/futbol/portugal/primeira-liga/17083r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/portugal/primeira-liga/17083/"},
    {"name": "Eredivisie", "page": "https://www.betano.pe/sport/futbol/paises-bajos/eredivisie/17067r/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/paises-bajos/eredivisie/17067/"},
    {"name": "UEFA Champions League", "page": "https://www.betano.pe/sport/futbol/campeonatos/champions-league/188566/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/campeonatos/champions-league/188566/"},
    {"name": "UEFA Europa League", "page": "https://www.betano.pe/sport/futbol/campeonatos/europa-league/188567/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/campeonatos/europa-league/188567/"},
    {"name": "UEFA Conference League", "page": "https://www.betano.pe/sport/futbol/campeonatos/conference-league/189602/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/campeonatos/conference-league/189602/"},
    {"name": "Copa Libertadores", "page": "https://www.betano.pe/sport/futbol/campeonatos/copa-libertadores/189817/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/campeonatos/copa-libertadores/189817/"},
    {"name": "Copa Sudamericana", "page": "https://www.betano.pe/sport/futbol/campeonatos/copa-sudamericana/189818/?bt=matchresult",
     "api": "https://www.betano.pe/api/sport/futbol/campeonatos/copa-sudamericana/189818/"},
]

def log_error(msg: str):
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")

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
        if str(m.get("name", "")).strip().lower() in ("resultado del partido", "match result", "resultado"):
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
    """
    1) intenta fetch
    2) si 403 splash -> navega a league_page y reintenta
    """
    url = f"{api_base}?bt={BT}&req={REQ}"

    resp = fetch_raw(page, url)
    if resp["status"] == 200 and "application/json" in (resp["ct"] or "").lower():
        return json.loads(resp["text"])

    # fallback: navegar a liga + reintentar
    page.goto(league_page, wait_until="domcontentloaded")
    resp = fetch_raw(page, url)
    if resp["status"] == 200 and "application/json" in (resp["ct"] or "").lower():
        return json.loads(resp["text"])

    snippet = (resp["text"] or "")[:180].replace("\n", " ")
    raise RuntimeError(f"HTTP {resp['status']} | {resp['ct']} | {snippet}")

def warmup_access(page):
    """
    En modo visible, te deja la ventana abierta para que el sitio setee cookies/challenge.
    Sin ENTER: simplemente reintenta el API hasta que sea JSON.
    """
    page.goto(WARMUP_LEAGUE_PAGE, wait_until="domcontentloaded")

    # intentos rápidos; si no está listo todavía, reintenta
    for _ in range(60):  # ~60 reintentos
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

    now = datetime.now(TZ_LOCAL)
    end = now + timedelta(days=DIAS_A_FUTURO)

    resultados = []
    estado = {}

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=not HEADFUL,
            locale="es-PE",
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        page.goto("https://www.betano.pe/", wait_until="domcontentloaded")

        # ✅ Warmup: asegura que el API ya responde JSON (sin pedir ENTER)
        ok = warmup_access(page)
        if not ok:
            print("⚠️ Betano: no se habilitó el acceso al API (splash). Revisa betano_errors.log.")
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
                        "Fecha": to_iso_like(dt),
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
