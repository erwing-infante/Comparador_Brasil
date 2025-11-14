import os
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd
from leagues_config import LEAGUES, BOOKMAKERS
import time
from requests.adapters import HTTPAdapter, Retry

# === CONFIGURACIÓN ===
API_KEY = "b74081b6d105c0c8bc5292cbc295fcd26b4f5b8f923a4ea63054cd9cf1c0b685"
OUT_JSON = os.path.join(os.path.dirname(__file__), "data", "cuotas_oddsapi.json")

# Ajustes de concurrencia y chunking
MAX_WORKERS = 25        # número concurrente razonable (ajusta según pruebas)
BATCH_SIZE = 200        # cuántas tareas encolar por bloque para evitar picos
REQUEST_TIMEOUT = 10    # timeout por request (segundos)
SESSION_RETRIES = 3     # reintentos por conexión
BACKOFF_FACTOR = 0.5    # factor backoff para retries

def build_session():
    s = requests.Session()
    retries = Retry(
        total=SESSION_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(['GET', 'POST'])
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=100, pool_maxsize=100)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "cuotas-batcher/1.0"})
    return s

# Crear una session global que se reutiliza en los workers
SESSION = build_session()

def obtener_cuotas_evento(ev, nombre_liga, session: requests.Session):
    """Consulta las cuotas ML de un solo evento usando session reutilizable."""
    event_id = ev.get("id")
    home = ev.get("home")
    away = ev.get("away")
    date = ev.get("date")

    if not event_id or not home or not away:
        return []

    # construye URL una sola vez
    url_odds = (
        "https://api.odds-api.io/v3/odds?"
        f"apiKey={API_KEY}&eventId={event_id}&market=ML&bookmakers={','.join(BOOKMAKERS)}"
    )

    try:
        r = session.get(url_odds, timeout=REQUEST_TIMEOUT)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.HTTPError as e:
        # si rate limit, espera un poco y devolvemos vacío (el Retry del adapter ya reintentó)
        if getattr(e.response, "status_code", None) == 429:
            time.sleep(1)
        return []
    except Exception:
        return []

    resultados = []
    bookmakers = data.get("bookmakers", {}) or {}
    for casa, mercados in bookmakers.items():
        for m in mercados:
            if m.get("name") == "ML" and m.get("odds"):
                odds = m["odds"][0]
                resultados.append({
                    "Liga": nombre_liga,
                    "Fecha": date,
                    "Partido": f"{home} vs {away}",
                    "Casa": casa,
                    "Cuota Local": odds.get("home"),
                    "Cuota Empate": odds.get("draw"),
                    "Cuota Visita": odds.get("away"),
                })
    return resultados

def obtener_eventos_liga(nombre_liga, league_id, session: requests.Session):
    """Obtiene todos los eventos de una liga (usa session)."""
    url_eventos = f"https://api.odds-api.io/v3/events?sport=football&league={league_id}&apiKey={API_KEY}"
    try:
        resp = session.get(url_eventos, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []

def chunked_iterable(iterable, size):
    it = iter(iterable)
    while True:
        chunk = []
        try:
            for _ in range(size):
                chunk.append(next(it))
        except StopIteration:
            if chunk:
                yield chunk
            break
        yield chunk

def obtener_cuotas_oddsapi_io():
    """Consulta todas las ligas en paralelo con control de carga (chunking)."""
    filas = []
    ligas_eventos = {}
    session = SESSION

    # 1) Obtener eventos por liga (serial: poco costoso)
    for nombre_liga, info in LEAGUES.items():
        if info.get("provider") != "odds-api.io":
            continue
        eventos = obtener_eventos_liga(nombre_liga, info.get("league_id"), session)
        if eventos:
            # filtrar eventos sin home/away temprano
            eventos = [e for e in eventos if e.get("id") and e.get("home") and e.get("away")]
            if eventos:
                ligas_eventos[nombre_liga] = eventos

    print(f"Ligas con eventos: {len(ligas_eventos)}")

    # 2) Preparar lista plana de (ev, nombre_liga)
    tareas = []
    for nombre_liga, eventos in ligas_eventos.items():
        for ev in eventos:
            tareas.append((ev, nombre_liga))

    if not tareas:
        print("\nAlerta No se encontraron cuotas válidas.")
        return None

    # 3) Ejecutar en batches para no saturar la API
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for batch in chunked_iterable(tareas, BATCH_SIZE):
            futures = {executor.submit(obtener_cuotas_evento, ev, nombre_liga, session): (ev, nombre_liga)
                       for ev, nombre_liga in batch}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        filas.extend(res)
                except Exception:
                    continue
            # pequeña pausa entre batches para amortiguar picos (ajustable)
            time.sleep(0.1)

    if not filas:
        print("\nAlerta No se encontraron cuotas válidas.")
        return None

    df = pd.DataFrame(filas)
    df["Fecha"] = pd.to_datetime(df["Fecha"], utc=True, errors="coerce")
    df["Fecha"] = df["Fecha"].dt.tz_localize(None)
    df.sort_values(by=["Liga", "Fecha"], inplace=True)
    return df

if __name__ == "__main__":
    print("Consultando cuotas 1X2 en todas las ligas (modo optimizado)...\n")
    df = obtener_cuotas_oddsapi_io()
    if df is not None:
        os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
        df.to_json(OUT_JSON, orient="records", indent=2, date_format="iso")
        print(f"Ok Archivo JSON actualizado: {OUT_JSON}")