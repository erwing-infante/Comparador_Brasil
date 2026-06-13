# fusionador_cuotas.py (OPTIMIZADO sin pandas)
# - Mantiene tu normalización y equivalencias tal cual (misma lógica)
# - Mucho más rápido: sin pandas, con cache de normalización, y merge Orbitx (eventId/marketId)
# - ✅ CORREGIDO: ruta FIJA de watchlist (sin auto-find). Si falta, falla con error claro.
# - ✅ NUEVO: guarda all_odds por partido con todas las cuotas de todas las casas
# - ✅ NUEVO: guarda histórico diario en data/historico_cuotas/YYYY-MM-DD.json

import os
import json
import unicodedata
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher

# === IMPORTAR EQUIVALENCIAS PLANAS DESDE ARCHIVO EXTERNO ===
from equivalencias_equipos import EQUIVALENCIAS_EQUIPOS

# === CONFIG ===
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_FILE = os.path.join(DATA_DIR, "cuotas.json")

# ✅ NUEVO: directorio de histórico
HISTORICO_DIR = os.path.join(DATA_DIR, "historico_cuotas")
TZ_LOCAL = ZoneInfo("America/Lima")

ARCHIVOS = {
    #"oddsapi": os.path.join(DATA_DIR, "cuotas_oddsapi.json"),
    "apuestatotal": os.path.join(DATA_DIR, "cuotas_apuestatotal.json"),
    "doradobet": os.path.join(DATA_DIR, "cuotas_doradobet.json"),
    "atlanticcity": os.path.join(DATA_DIR, "cuotas_atlanticcity.json"),
    "olimpobet": os.path.join(DATA_DIR, "cuotas_olimpobet.json"),
    "gangabet": os.path.join(DATA_DIR, "cuotas_gangabet.json"),
    "betano": os.path.join(DATA_DIR, "cuotas_betano.json"),
    "stake": os.path.join(DATA_DIR, "cuotas_stake.json"),
    "1xbet": os.path.join(DATA_DIR, "cuotas_1xbet.json"),
    "pinnacle": os.path.join(DATA_DIR, "cuotas_pinnacle.json"),
    "betsson": os.path.join(DATA_DIR, "cuotas_betsson.json"),
    "betsafe": os.path.join(DATA_DIR, "cuotas_betsafe.json"),
    "inkabet": os.path.join(DATA_DIR, "cuotas_inkabet.json"),
    "teapuesto": os.path.join(DATA_DIR, "cuotas_teapuesto.json")
}

# Similitud mínima
SIM_THRESHOLD = 0.40

# Casas excluidas en local/visita
BOOKMAKERS_EXCLUIR_HA = {"betcris", "1xbet", "coolbet", "pinnacle"}

# ============================================================
# NORMALIZACIÓN DE EQUIPOS (MISMA LÓGICA)
# ============================================================

STOP_TOKENS = {
    "fc", "cf", "sc", "ec", "ac",
    "u19", "u20", "u21", "u23",
    "de", "the", "club",
    "sa", "sp", "mg", "ba", "ce", "rj", "rs"
}

def quitar_acentos(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s)
        if not unicodedata.combining(c)
    )

def similitud(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

def limpiar_equipo(nombre: str) -> str:
    if not isinstance(nombre, str):
        return ""

    # 1) NOMBRE EXACTO DEL SCRAPER
    original = nombre.strip()
    lookup = quitar_acentos(original).lower().strip()

    if lookup in EQUIVALENCIAS_EQUIPOS:
        return EQUIVALENCIAS_EQUIPOS[lookup]

    for key in EQUIVALENCIAS_EQUIPOS:
        if similitud(lookup, key) >= 0.88:
            return EQUIVALENCIAS_EQUIPOS[key]

    # 2) Limpieza ligera
    limpio = quitar_acentos(original).lower()
    for bad in ["t/t", "t//t", "//", "/", "\\", "\t", "\n", "|"]:
        limpio = limpio.replace(bad, " ")
    limpio = " ".join(limpio.split()).strip()

    # 3) Fallback tokens
    tokens = [t for t in limpio.split() if t not in STOP_TOKENS]
    fallback = " ".join(tokens).strip()

    if fallback in EQUIVALENCIAS_EQUIPOS:
        return EQUIVALENCIAS_EQUIPOS[fallback]

    for key in EQUIVALENCIAS_EQUIPOS:
        if similitud(fallback, key) >= 0.88:
            return EQUIVALENCIAS_EQUIPOS[key]

    return fallback or original

def team_short(name: str) -> str:
    limpio = limpiar_equipo(name)
    if not limpio:
        return "desconocido"
    tokens = [t for t in limpio.split() if t not in STOP_TOKENS]
    if not tokens:
        return "desconocido"
    return max(tokens, key=len)

# ============================================================
# ⚡ CACHE (NO CAMBIA LÓGICA, SOLO EVITA REPETIR TRABAJO)
# ============================================================

_LIMPIAR_CACHE: dict[str, str] = {}
_SHORT_CACHE: dict[str, str] = {}

def limpiar_equipo_cached(nombre: str) -> str:
    if not isinstance(nombre, str):
        return ""
    k = nombre.strip()
    if k in _LIMPIAR_CACHE:
        return _LIMPIAR_CACHE[k]
    v = limpiar_equipo(k)
    _LIMPIAR_CACHE[k] = v
    return v

def team_short_cached(nombre: str) -> str:
    if not isinstance(nombre, str):
        return "desconocido"
    k = nombre.strip()
    if k in _SHORT_CACHE:
        return _SHORT_CACHE[k]
    v = team_short(k)
    _SHORT_CACHE[k] = v
    return v

# ============================================================
# FECHA → UTC naive
# ============================================================

def parse_fecha_utc_naive(fecha_str: str):
    if not fecha_str or not isinstance(fecha_str, str):
        return None

    s = fecha_str.strip()

    # ISO Z
    try:
        if s.endswith("Z"):
            s2 = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s2)
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        if "T" in s and ("+" in s[-6:] or "-" in s[-6:]):
            dt = datetime.fromisoformat(s)
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", ""))
            return dt.replace(tzinfo=timezone.utc).replace(tzinfo=None)
    except Exception:
        pass

    # "YYYY-MM-DD HH:MM UTC"
    try:
        if s.endswith(" UTC"):
            dt = datetime.strptime(s.replace(" UTC", ""), "%Y-%m-%d %H:%M")
            return dt
    except Exception:
        pass

    # "YYYY-MM-DD HH:MM"
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        return dt
    except Exception:
        return None

def fecha_to_str_utc(dt_naive):
    if not dt_naive:
        return ""
    return dt_naive.strftime("%Y-%m-%d %H:%M UTC")

def dt_hour_bucket(dt_naive):
    return dt_naive.replace(minute=0, second=0, microsecond=0)

# ============================================================
# ORBITX WATCHLIST INDEX (eventId/marketId) - ✅ RUTA FIJA
# ============================================================

def _watchlist_path_fixed() -> str:
    """
    Ruta fija:
    - VPS: /root/proyectos/Mancorabet/Monitor_Orbitx/data/watchlists/watchlist.json
    - Windows/VSCode: <proyecto>/Monitor_Orbitx/data/watchlists/watchlist.json
    """
    # 1) VPS (ruta absoluta fija)
    vps_path = "/root/proyectos/Mancorabet/Monitor_Orbitx/data/watchlists/watchlist.json"
    if os.path.exists(vps_path):
        return vps_path

    # 2) Windows / local: relativo al proyecto
    local_path = os.path.abspath(os.path.join(BASE_DIR, "Monitor_Orbitx", "data", "watchlists", "watchlist.json"))
    if os.path.exists(local_path):
        return local_path

    # 3) Si no existe, falla fuerte (nada de silencios)
    return ""

def cargar_indice_orbitx():
    """
    key = (Liga, date_str_utc, home_norm, away_norm)
    val = {"eventId": "...", "marketId": "..."}
    """
    path = _watchlist_path_fixed()
    if not path:
        raise SystemExit(
            "❌ No se encontró watchlist.json de Orbitx.\n"
            "   Esperado en VPS: /root/proyectos/Mancorabet/Monitor_Orbitx/data/watchlists/watchlist.json\n"
            f"   Esperado en local: {os.path.abspath(os.path.join(BASE_DIR, 'Monitor_Orbitx', 'data', 'watchlists', 'watchlist.json'))}\n"
            "   Solución: asegúrate de generar watchlists en Monitor_Orbitx antes de correr el fusionador."
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        raise SystemExit(f"❌ Error leyendo watchlist.json ({path}): {e}")

    if not isinstance(raw, list):
        raise SystemExit(f"❌ watchlist.json no es una lista: {path}")

    idx = {}
    for it in raw:
        try:
            liga = (it.get("Liga") or "").strip()
            date = (it.get("date") or "").strip()
            home = limpiar_equipo_cached(it.get("home") or "")
            away = limpiar_equipo_cached(it.get("away") or "")
            event_id = str(it.get("eventId") or "").strip()
            market_id = str(it.get("marketId") or "").strip()
            if not liga or not date or not home or not away:
                continue
            if not event_id and not market_id:
                continue
            key = (liga, date, home, away)
            if key not in idx:
                idx[key] = {"eventId": event_id, "marketId": market_id}
        except Exception:
            continue

    print(f"✅ Índice Orbitx cargado: {len(idx)} matches (desde {path})")
    return idx

# ============================================================
# UTIL: lectura JSON y parsing de equipos desde Partido si faltan
# ============================================================

def split_partido(partido: str):
    if not isinstance(partido, str):
        return ("", "")
    s = " ".join(partido.strip().split())
    for sep in [" vs. ", " vs ", " v ", " VS ", " Vs ", " V "]:
        if sep in s:
            a, b = s.split(sep, 1)
            return a.strip(), b.strip()
    return ("", "")

def to_float(x):
    try:
        if x is None:
            return None
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip()
        if s == "" or s.lower() == "null":
            return None
        return float(s)
    except Exception:
        return None

def norm_bookmaker_name(s: str) -> str:
    if not isinstance(s, str):
        return ""
    return s.replace(" ", "").strip().lower()

def load_rows_from_file(path: str):
    if not os.path.exists(path):
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []

    if not isinstance(raw, list):
        return []

    out = []
    for it in raw:
        if not isinstance(it, dict):
            continue

        liga = it.get("Liga", "") or ""
        partido = it.get("Partido", "") or ""
        casa = it.get("Casa", "") or ""
        fecha = it.get("Fecha", "") or ""

        local = it.get("Local", "") or ""
        visita = it.get("Visita", "") or ""

        local_odd = to_float(it.get("Local Odd", it.get("Cuota Local")))
        empate_odd = to_float(it.get("Empate Odd", it.get("Cuota Empate")))
        visita_odd = to_float(it.get("Visita Odd", it.get("Cuota Visita")))

        if (not str(local).strip() or not str(visita).strip()) and str(partido).strip():
            a, b = split_partido(partido)
            if a and b:
                if not str(local).strip():
                    local = a
                if not str(visita).strip():
                    visita = b

        local_norm = limpiar_equipo_cached(str(local))
        visita_norm = limpiar_equipo_cached(str(visita))

        home_short = team_short_cached(local_norm)
        away_short = team_short_cached(visita_norm)

        fecha_dt = parse_fecha_utc_naive(str(fecha))

        out.append({
            "Liga": str(liga),
            "Casa": str(casa),
            "Fecha_dt": fecha_dt,
            "Fecha_raw": str(fecha),
            "Local": local_norm,
            "Visita": visita_norm,
            "home_short": home_short,
            "away_short": away_short,
            "Local Odd": local_odd,
            "Empate Odd": empate_odd,
            "Visita Odd": visita_odd,
        })

    return out

# ============================================================
# FUSIÓN
# ============================================================

def partido_hash(row):
    return (
        row["Liga"],
        dt_hour_bucket(row["Fecha_dt"]),
        row["home_short"],
        row["away_short"],
    )

def pick_best(subset, col):
    col_lower = col.lower()

    if "empate" in col_lower:
        best_val = None
        best_bm = ""
        for r in subset:
            v = r.get(col)
            if v is None:
                continue
            if (best_val is None) or (v > best_val):
                best_val = v
                best_bm = r.get("Casa", "") or ""
        return (best_val, best_bm)

    filtered = []
    for r in subset:
        v = r.get(col)
        if v is None:
            continue
        bm_norm = norm_bookmaker_name(r.get("Casa", ""))
        if bm_norm not in BOOKMAKERS_EXCLUIR_HA:
            filtered.append(r)

    if filtered:
        best_val = None
        best_bm = ""
        for r in filtered:
            v = r.get(col)
            if v is None:
                continue
            if (best_val is None) or (v > best_val):
                best_val = v
                best_bm = r.get("Casa", "") or ""
        return (best_val, best_bm)

    best_val = None
    best_bm = ""
    for r in subset:
        v = r.get(col)
        if v is None:
            continue
        if (best_val is None) or (v > best_val):
            best_val = v
            best_bm = r.get("Casa", "") or ""
    return (best_val, best_bm)

def bookmaker_sort_score(item):
    vals = [item.get("home"), item.get("draw"), item.get("away")]
    vals = [float(v) for v in vals if v is not None]
    if not vals:
        return -999999
    return max(vals)

def build_all_odds(grupo):
    """
    Devuelve todas las cuotas encontradas por casa para ese partido.
    Si una casa aparece más de una vez, conserva la mejor por columna.
    Luego ordena de mayor a menor según la mejor cuota total de esa casa.
    """
    by_book = {}

    for r in grupo:
        casa = (r.get("Casa") or "").strip()
        if not casa:
            continue

        if casa not in by_book:
            by_book[casa] = {
                "bookmaker": casa,
                "home": None,
                "draw": None,
                "away": None,
            }

        h = r.get("Local Odd")
        d = r.get("Empate Odd")
        a = r.get("Visita Odd")

        if h is not None and (by_book[casa]["home"] is None or h > by_book[casa]["home"]):
            by_book[casa]["home"] = h

        if d is not None and (by_book[casa]["draw"] is None or d > by_book[casa]["draw"]):
            by_book[casa]["draw"] = d

        if a is not None and (by_book[casa]["away"] is None or a > by_book[casa]["away"]):
            by_book[casa]["away"] = a

    out = list(by_book.values())
    out.sort(key=bookmaker_sort_score, reverse=True)
    return out

# ============================================================
# ✅ HISTÓRICO DIARIO DE CUOTAS
# ============================================================

def ensure_historico_dir():
    os.makedirs(HISTORICO_DIR, exist_ok=True)

def build_match_key(fila: dict) -> str:
    home = (fila.get("home") or "").strip()
    away = (fila.get("away") or "").strip()
    if home and away:
        return f"{home} vs {away}"
    return fila.get("name") or "partido_sin_nombre"

def compact_snapshot_from_filas(filas: list[dict]) -> dict:
    """
    Estructura compacta por snapshot:
    {
      "equipo a vs equipo b": {
        "Liga": ...,
        "date": ...,
        "eventId": ...,
        "marketId": ...,
        "best_home": {...},
        "best_draw": {...},
        "best_away": {...},
        "all_odds": [...]
      }
    }
    """
    out = {}
    for fila in filas:
        key = build_match_key(fila)
        out[key] = {
            "Liga": fila.get("Liga"),
            "name": fila.get("name"),
            "home": fila.get("home"),
            "away": fila.get("away"),
            "date": fila.get("date"),
            "eventId": fila.get("eventId"),
            "marketId": fila.get("marketId"),
            "best_home": fila.get("best_home"),
            "best_draw": fila.get("best_draw"),
            "best_away": fila.get("best_away"),
            "all_odds": fila.get("all_odds", []),
        }
    return out

def guardar_historico_cuotas(filas: list[dict], fuentes_ok: list[str], fuentes_error: list[str]) -> None:
    """
    Guarda un solo archivo por día en:
    data/historico_cuotas/YYYY-MM-DD.json

    Estructura:
    {
      "metadata": {...},
      "HH:MM:SS": { ...snapshot... },
      "ULTIMO": { ...snapshot... }
    }
    """
    ensure_historico_dir()

    now_local = datetime.now(TZ_LOCAL)
    fecha_archivo = now_local.strftime("%Y-%m-%d")
    hora_snapshot = now_local.strftime("%H:%M:%S")
    path_historico = os.path.join(HISTORICO_DIR, f"{fecha_archivo}.json")

    snapshot = compact_snapshot_from_filas(filas)

    historico = {}
    if os.path.exists(path_historico):
        try:
            with open(path_historico, "r", encoding="utf-8") as f:
                historico = json.load(f)
            if not isinstance(historico, dict):
                historico = {}
        except Exception:
            historico = {}

    metadata = historico.get("metadata", {})
    metadata.update({
        "date": fecha_archivo,
        "timezone": "America/Lima",
        "updated": now_local.strftime("%Y-%m-%d %H:%M:%S"),
        "fuentes_ok": fuentes_ok,
        "fuentes_error": fuentes_error,
    })
    historico["metadata"] = metadata

    # Guarda snapshot por hora exacta
    historico[hora_snapshot] = snapshot

    # Mantiene un acceso rápido al último snapshot
    historico["ULTIMO"] = snapshot

    with open(path_historico, "w", encoding="utf-8") as f:
        json.dump(historico, f, indent=2, ensure_ascii=False)

    print(f"✔ Histórico actualizado: {path_historico}")

def fusionar_cuotas():
    print("Fusionando con equivalencias externas + similitud (OPTIMIZADO)...")

    orbitx_idx = cargar_indice_orbitx()

    fuentes_ok = []
    fuentes_error = []
    all_rows = []

    for nombre, ruta in ARCHIVOS.items():
        rows = load_rows_from_file(ruta)
        if rows:
            fuentes_ok.append(nombre)
            for r in rows:
                r["Origen"] = nombre
            all_rows.extend(rows)
        else:
            fuentes_error.append(nombre)

    if not all_rows:
        print("F No hay datos.")
        return

    filtered = []
    for r in all_rows:
        if r.get("Fecha_dt") is None:
            continue
        if r.get("home_short") == "desconocido" or r.get("away_short") == "desconocido":
            continue
        filtered.append(r)

    buckets = {}
    for r in filtered:
        key = partido_hash(r)
        buckets.setdefault(key, []).append(r)

    filas = []
    llaves_existentes = set()

    for key, items in buckets.items():
        usados_idx = set()

        for i in range(len(items)):
            if i in usados_idx:
                continue
            base = items[i]
            grupo = [base]

            for j in range(len(items)):
                if j == i or j in usados_idx:
                    continue
                r2 = items[j]

                dt1 = base["Fecha_dt"]
                dt2 = r2["Fecha_dt"]
                if abs((dt1 - dt2).total_seconds()) > 21600:
                    continue

                if similitud(base["home_short"], r2["home_short"]) >= SIM_THRESHOLD and \
                   similitud(base["away_short"], r2["away_short"]) >= SIM_THRESHOLD:
                    grupo.append(r2)
                    usados_idx.add(j)

            usados_idx.add(i)

            bh, bh_bm = pick_best(grupo, "Local Odd")
            bd, bd_bm = pick_best(grupo, "Empate Odd")
            ba, ba_bm = pick_best(grupo, "Visita Odd")

            fecha_dt = base["Fecha_dt"]
            fecha_str = fecha_to_str_utc(fecha_dt)

            clave = (base["Liga"], fecha_str, base["Local"], base["Visita"])
            if clave in llaves_existentes:
                continue
            llaves_existentes.add(clave)

            orbitx_key = (base["Liga"], fecha_str, base["Local"], base["Visita"])
            orbitx_info = orbitx_idx.get(orbitx_key, {})
            event_id = orbitx_info.get("eventId") or None
            market_id = orbitx_info.get("marketId") or None

            filas.append({
                "Liga": base["Liga"],
                "name": f"{base['Local'].title()} vs {base['Visita'].title()}",
                "home": base["Local"],
                "away": base["Visita"],
                "date": fecha_str,
                "eventId": event_id,
                "marketId": market_id,
                "best_home": {"odd": bh, "bookmaker": bh_bm},
                "best_draw": {"odd": bd, "bookmaker": bd_bm},
                "best_away": {"odd": ba, "bookmaker": ba_bm},
                "all_odds": build_all_odds(grupo)
            })

    salida = {
        "metadata": {
            "updated": datetime.now(TZ_LOCAL).strftime("%Y-%m-%d %H:%M:%S"),
            "fuentes_ok": fuentes_ok,
            "fuentes_error": fuentes_error
        }
    }

    for fila in filas:
        salida.setdefault(fila["Liga"], []).append(fila)

    for liga in list(salida.keys()):
        if liga == "metadata":
            continue
        try:
            salida[liga].sort(key=lambda x: datetime.strptime(x["date"].replace(" UTC", ""), "%Y-%m-%d %H:%M"))
        except Exception:
            pass

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    print(f"✔ Archivo actualizado: {OUT_FILE}")

    # ✅ NUEVO: guardar histórico diario
    guardar_historico_cuotas(filas, fuentes_ok, fuentes_error)

if __name__ == "__main__":
    fusionar_cuotas()