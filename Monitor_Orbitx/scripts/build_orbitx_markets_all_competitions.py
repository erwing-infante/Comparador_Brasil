import os, re, sys, json, unicodedata, requests
from datetime import datetime, timezone
from difflib import SequenceMatcher
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# pool/retry para requests (mejora velocidad/estabilidad)
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
except Exception:
    Retry = None

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from config_orbitx import CATALOGS_DIR  # noqa
from equivalencias_ligas_orbitx import LIGAS_COMPETITION_ID  # noqa

# Si ya tienes equivalencias_equipos.py completo en el proyecto, se usa:
try:
    from equivalencias_equipos import EQUIVALENCIAS_EQUIPOS  # noqa
except Exception:
    EQUIVALENCIAS_EQUIPOS = {}

load_dotenv()

BASE = "https://www.orbitxch.com"
PROXY = os.getenv("PROXY_SELLER_SOCKS5", "").strip()
WATCH_HOURS = int(os.getenv("WATCH_HOURS", "36"))  # no filtra aquí; solo útil más adelante

# ⚡ workers para paralelizar event/details (más = más rápido, pero puede rate-limitar)
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "24"))

STOP_TOKENS = {
    "fc", "cf", "sc", "ec", "ac",
    "u19", "u20", "u21", "u23",
    "de", "the", "club",
    "sa", "sp", "mg", "ba", "ce", "rj", "rs"
}

def slug(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return re.sub(r"_+", "_", s).strip("_")

def quitar_acentos(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def similitud(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def limpiar_equipo(nombre: str) -> str:
    if not isinstance(nombre, str):
        return ""
    original = nombre.strip()
    lookup = quitar_acentos(original).lower().strip()

    if lookup in EQUIVALENCIAS_EQUIPOS:
        return EQUIVALENCIAS_EQUIPOS[lookup]

    for key in EQUIVALENCIAS_EQUIPOS:
        if similitud(lookup, key) >= 0.88:
            return EQUIVALENCIAS_EQUIPOS[key]

    limpio = quitar_acentos(original).lower()
    for bad in ["t/t", "t//t", "//", "/", "\\", "\t", "\n", "|"]:
        limpio = limpio.replace(bad, " ")
    limpio = " ".join(limpio.split()).strip()

    tokens = [t for t in limpio.split() if t not in STOP_TOKENS]
    fallback = " ".join(tokens).strip()

    if fallback in EQUIVALENCIAS_EQUIPOS:
        return EQUIVALENCIAS_EQUIPOS[fallback]

    for key in EQUIVALENCIAS_EQUIPOS:
        if similitud(fallback, key) >= 0.88:
            return EQUIVALENCIAS_EQUIPOS[key]

    return fallback or original

def parse_cookie(cookie_str: str) -> dict:
    out={}
    for part in cookie_str.split(";"):
        part=part.strip()
        if not part or "=" not in part:
            continue
        k,v=part.split("=",1)
        out[k.strip()]=v.strip()
    return out

def extract_csrf(cookie_str: str) -> str:
    m=re.search(r"(?:^|;\s*)CSRF-TOKEN=([^;]+)", cookie_str)
    return m.group(1) if m else ""

def ms_to_utc_str(ms: int) -> str:
    dt = datetime.fromtimestamp(ms/1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")

def get_json(sess: requests.Session, url: str, cookies: dict):
    r = sess.get(url, cookies=cookies, timeout=30, allow_redirects=False)
    if r.status_code != 200:
        return None
    if "application/json" not in (r.headers.get("content-type") or ""):
        return None
    return r.json()

def extract_match_odds(details: dict):
    # event/details suele traer marketCatalogues dentro de tabs o directo
    def scan(obj):
        if isinstance(obj, dict):
            if isinstance(obj.get("marketCatalogues"), list):
                for m in obj["marketCatalogues"]:
                    yield m
            if isinstance(obj.get("marketCatalogueList"), list):
                for m in obj["marketCatalogueList"]:
                    yield m
            for v in obj.values():
                yield from scan(v)
        elif isinstance(obj, list):
            for it in obj:
                yield from scan(it)

    for m in scan(details):
        desc = m.get("description") or {}
        mtype = desc.get("marketType") or m.get("marketType")
        if mtype == "MATCH_ODDS" or m.get("marketName") == "Match Odds":
            return m
    return None

def main():
    cookie_raw = os.getenv("ORBITX_COOKIE", "").strip()
    if not cookie_raw:
        raise SystemExit("❌ Falta ORBITX_COOKIE en .env")
    cookies = parse_cookie(cookie_raw)
    csrf = extract_csrf(cookie_raw)

    sess = requests.Session()
    sess.headers.update({
        "user-agent":"Mozilla/5.0",
        "accept":"application/json, text/plain, */*",
        "accept-encoding":"gzip, deflate",
        "x-requested-with":"XMLHttpRequest",
        "origin":BASE,
        "x-device":"MOBILE",
    })
    
    if PROXY:
        sess.proxies.update({"http": PROXY, "https": PROXY})
        print("🛰️ Usando proxy:", PROXY.split("@")[-1])  # imprime host:puerto sin usuario/pass

    if csrf:
        sess.headers["x-csrf-token"] = csrf

    # ✅ Pool de conexiones (más rápido) + retry suave (más estable)
    if Retry is not None:
        retry = Retry(
            total=2,
            backoff_factor=0.2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            pool_connections=MAX_WORKERS * 2,
            pool_maxsize=MAX_WORKERS * 2,
            max_retries=retry
        )
    else:
        adapter = HTTPAdapter(
            pool_connections=MAX_WORKERS * 2,
            pool_maxsize=MAX_WORKERS * 2
        )

    sess.mount("https://", adapter)
    sess.mount("http://", adapter)

    for liga, comp_id in LIGAS_COMPETITION_ID.items():
        print(f"\n=== {liga} (competitionId={comp_id}) ===")
        out_path = os.path.join(CATALOGS_DIR, f"orbitx_markets_{slug(liga)}.json")

        comp_url = f"{BASE}/customer/api/v2/competition/{comp_id}"
        comp = get_json(sess, comp_url, cookies)
        if not comp:
            print("❌ No pude leer competition.")
            continue

        children = comp.get("children", []) or []
        match_events = [c for c in children if c.get("type") == "EVENT" and c.get("id")]

        print("Eventos (partidos) encontrados:", len(match_events))
        seen = set()

        # worker: procesa un evento y devuelve (idx, market_id, item)
        def worker(ev, idx):
            event_id = str(ev.get("id"))
            det_url = f"{BASE}/customer/api/event/details/{event_id}?showGroups=true"
            det = get_json(sess, det_url, cookies)
            if not det:
                return idx, None, None

            mo = extract_match_odds(det)
            if not mo:
                return idx, None, None

            market_id = mo.get("marketId")
            if not market_id:
                return idx, None, None

            event_obj = mo.get("event") or {}
            event_name = event_obj.get("name") or ev.get("name") or ""
            start_ms = mo.get("marketStartTime") or (event_obj.get("openDate"))
            date_utc = ms_to_utc_str(int(start_ms)) if start_ms else None

            home_raw = away_raw = None
            home_id = away_id = draw_id = None

            for rr in (mo.get("runners") or []):
                sid = rr.get("selectionId")
                rname = rr.get("runnerName", "")
                sp = rr.get("sortPriority")
                if sid is None:
                    continue
                sid = int(sid)

                if rname.lower() == "the draw":
                    draw_id = sid
                else:
                    if sp == 1 and home_raw is None:
                        home_raw = rname; home_id = sid
                    elif sp == 2 and away_raw is None:
                        away_raw = rname; away_id = sid
                    else:
                        if home_raw is None:
                            home_raw = rname; home_id = sid
                        elif away_raw is None:
                            away_raw = rname; away_id = sid

            home = limpiar_equipo(home_raw or "")
            away = limpiar_equipo(away_raw or "")

            item = {
                "Liga": liga,  # ✅ canon MancoraBet
                "eventId": event_id,
                "eventName": event_name,
                "marketId": str(market_id),
                "startTimeMs": int(start_ms) if start_ms else None,
                "date": date_utc,  # ✅ mismo formato que api/cuotas
                "home": home,
                "away": away,
                "name": f"{home.title()} vs {away.title()}",
                "orbitx": {"home_id": home_id, "away_id": away_id, "draw_id": draw_id},
            }
            return idx, str(market_id), item

        # Ejecutar en paralelo
        results = {}
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = [ex.submit(worker, ev, idx) for idx, ev in enumerate(match_events)]
            for fu in as_completed(futures):
                idx, market_id, item = fu.result()
                results[idx] = (market_id, item)

        # Reconstruir catalog en mismo orden + aplicar "seen" como antes
        catalog = []
        for idx in range(len(match_events)):
            market_id, item = results.get(idx, (None, None))
            if not item or not market_id:
                continue
            if market_id in seen:
                continue
            seen.add(market_id)
            catalog.append(item)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)

        print("✅ Guardado:", out_path, "| markets:", len(catalog))

if __name__ == "__main__":
    main()
