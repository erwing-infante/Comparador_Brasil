import os
import json
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import pandas as pd
from leagues_config import LEAGUES, BOOKMAKERS
import time
from requests.adapters import HTTPAdapter, Retry

# === CONFIGURACIÓN ===
API_KEY = "b74081b6d105c0c8bc5292cbc295fcd26b4f5b8f923a4ea63054cd9cf1c0b685"
OUT_JSON = os.path.join(os.path.dirname(__file__), "data", "cuotas_oddsapi.json")

# Ajustes de concurrencia y chunking (OPTIMIZADOS)
MAX_WORKERS = 5          # número razonable para NO quemar solicitudes
BATCH_SIZE = 100         # tamaño de lote más controlado
REQUEST_TIMEOUT = 10
SESSION_RETRIES = 2       # reintentos reducidos a 2 (solicitado por el usuario)
BACKOFF_FACTOR = 0.3

# contador REAL de solicitudes hechas hacia la API
REQUEST_COUNT = 0


# ============================================================
# Crear una session global que se reutiliza en los workers
# Esto ayuda a bajar el tiempo total y evitar abrir conexiones nuevas
# ============================================================
def build_session():
    s = requests.Session()
    retries = Retry(
        total=SESSION_RETRIES,
        backoff_factor=BACKOFF_FACTOR,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(['GET'])
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=50, pool_maxsize=50)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({"User-Agent": "cuotas-batcher/1.0"})
    return s

# Session global reutilizable
SESSION = build_session()


# ============================================================
# Función para contar solicitudes reales usadas
# ============================================================
def contar_request():
    global REQUEST_COUNT
    REQUEST_COUNT += 1
    return REQUEST_COUNT


# ============================================================
# Obtener cuotas de 1 solo evento
# ============================================================
def obtener_cuotas_evento(ev, nombre_liga, session: requests.Session):
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

    contar_request()  # contamos esta solicitud real

    try:
        r = session.get(url_odds, timeout=REQUEST_TIMEOUT)
        if r.status_code == 404:
            return []
        r.raise_for_status()
        data = r.json()
    except:
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


# ============================================================
# Obtener todos los eventos de una liga
# ============================================================
def obtener_eventos_liga(nombre_liga, league_id, session: requests.Session):
    url_eventos = f"https://api.odds-api.io/v3/events?sport=football&league={league_id}&apiKey={API_KEY}"

    contar_request()  # contamos este llamado

    try:
        resp = session.get(url_eventos, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except:
        return []


# ============================================================
# Iterador para manejar listas grandes por lotes
# ============================================================
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


# ============================================================
# Función principal: obtener todas las cuotas optimizadas
# ============================================================
def obtener_cuotas_oddsapi_io():
    filas = []
    ligas_eventos = {}
    session = SESSION

    # Fecha actual AWARE (con UTC) para evitar errores de comparación
    AHORA = datetime.now(timezone.utc)
    LIMITE = AHORA + timedelta(days=3)  # solo partidos próximos 48 horas

    # 1) Obtener eventos por liga (serial)
    for nombre_liga, info in LEAGUES.items():
        if info.get("provider") != "odds-api.io":
            continue

        eventos = obtener_eventos_liga(nombre_liga, info.get("league_id"), session)
        if eventos:
            # excluir partidos en vivo
            eventos = [e for e in eventos if e.get("status") == "pending"]

            filtrados = []
            for e in eventos:
                fecha_str = e.get("date")
                if not fecha_str:
                    continue

                try:
                    fecha_dt = pd.to_datetime(fecha_str, utc=True)
                except:
                    continue

                # SOLO partidos próximos (48 horas)
                if AHORA <= fecha_dt <= LIMITE:
                    filtrados.append(e)

            if filtrados:
                ligas_eventos[nombre_liga] = filtrados

    print(f"Ligas con partidos próximos (48h): {len(ligas_eventos)}\n")

    # 2) Lista plana de tareas
    tareas = [(ev, nombre_liga) for nombre_liga, eventos in ligas_eventos.items() for ev in eventos]

    if not tareas:
        print("⚠️ Alerta: no hay partidos próximos.")
        return None

    # 3) Ejecutar en batches para no saturar la API
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for batch in chunked_iterable(tareas, BATCH_SIZE):
            futures = {
                executor.submit(obtener_cuotas_evento, ev, nombre_liga, session): (ev, nombre_liga)
                for ev, nombre_liga in batch
            }

            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        filas.extend(res)
                except:
                    pass

            # pequeña pausa para suavizar picos
            time.sleep(0.1)

    if not filas:
        print("⚠️ No se encontraron cuotas válidas.")
        return None

    df = pd.DataFrame(filas)
    df["Fecha"] = pd.to_datetime(df["Fecha"], utc=True, errors="coerce")
    df["Fecha"] = df["Fecha"].dt.tz_localize(None)
    df.sort_values(by=["Liga", "Fecha"], inplace=True)

    print(f"\n🔢 Solicitudes TOTALES usadas en esta ejecución: {REQUEST_COUNT}\n")

    return df


# ============================================================
# Script principal
# ============================================================
if __name__ == "__main__":
    print("Consultando cuotas 1X2 en todas las ligas (modo optimizado)...\n")
    df = obtener_cuotas_oddsapi_io()
    if df is not None:
        os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
        df.to_json(OUT_JSON, orient="records", indent=2, date_format="iso")
        print(f"✅ Ok Archivo JSON actualizado: {OUT_JSON}")
