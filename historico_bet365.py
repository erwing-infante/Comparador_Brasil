# historico_bet365.py
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

# ================================================
# CONFIG
# ================================================

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
ODDSAPI_FILE = os.path.join(DATA_DIR, "cuotas_oddsapi.json")

HIST_DIR = os.path.join(DATA_DIR, "historico_bet365")
os.makedirs(HIST_DIR, exist_ok=True)


# ================================================
# UTILIDADES
# ================================================

def cargar_json_seguro(path, default):
    """Carga JSON, devuelve default si no existe o está corrupto."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def guardar_json_seguro(path, data):
    """Guarda JSON de forma segura."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def normalizar_equipo(nombre):
    """Normaliza nombre para claves (simple y robusto)."""
    if not isinstance(nombre, str):
        return nombre
    return (
        nombre.lower()
        .replace("fc", "")
        .replace("sp", "")
        .replace("ce", "")
        .replace("sc", "")
        .replace(".", "")
        .replace(",", "")
        .replace("  ", " ")
        .strip()
    )


def generar_clave_partido(partido):
    """Convierte 'Sao Paulo FC SP vs EC Juventude RS' en 'sao paulo vs juventude'."""
    try:
        home, away = partido.split(" vs ")
    except:
        return partido.lower()

    home = normalizar_equipo(home)
    away = normalizar_equipo(away)

    return f"{home} vs {away}"


# ================================================
# PROCESO PRINCIPAL
# ================================================

def procesar_historico_bet365():

    # 1) Leer archivo fuente
    if not os.path.exists(ODDSAPI_FILE):
        print(f"❌ No existe {ODDSAPI_FILE}")
        return

    with open(ODDSAPI_FILE, "r", encoding="utf-8") as f:
        datos = json.load(f)

    # 2) Preparar archivo diario
    fecha_hoy = datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d")
    archivo_hoy = os.path.join(HIST_DIR, f"{fecha_hoy}.json")

    historico_hoy = cargar_json_seguro(archivo_hoy, default={})

    # Timestamp (HH:MM:SS)
    hora_actual = datetime.now(ZoneInfo("America/Lima")).strftime("%H:%M:%S")

    snapshot = {}

    # 3) Recorrer oddsapi buscando SOLO Bet365
    for item in datos:

        casa = item.get("Casa", "")
        if not isinstance(casa, str):
            continue

        casa_lower = casa.lower()

        # Solo tomamos Bet365
        if "bet365" not in casa_lower:
            continue

        partido = item.get("Partido", "").strip()
        if not partido:
            continue

        clave = generar_clave_partido(partido)

        # Extraer cuotas
        try:
            c_home = float(item.get("Cuota Local"))
            c_draw = float(item.get("Cuota Empate"))
            c_away = float(item.get("Cuota Visita"))
        except:
            continue

        snapshot[clave] = {
            "local": c_home,
            "empate": c_draw,
            "visita": c_away,
        }

    # 4) Comparar con el snapshot previo
    ultimo_snapshot = historico_hoy.get("ULTIMO", {})

    # Detectar si hay cambios (solo se guarda si algo cambió)
    hubo_cambios = False

    for p, cuotas in snapshot.items():

        if p not in ultimo_snapshot:
            hubo_cambios = True
            break

        prev = ultimo_snapshot.get(p, {})

        if (
            round(prev.get("local", 0), 4) != round(cuotas["local"], 4)
            or round(prev.get("empate", 0), 4) != round(cuotas["empate"], 4)
            or round(prev.get("visita", 0), 4) != round(cuotas["visita"], 4)
        ):
            hubo_cambios = True
            break

    if not hubo_cambios:
        print("No hay cambios en Bet365. No se guarda snapshot.")
        return

    # 5) Guardar snapshot actual
    historico_hoy[hora_actual] = snapshot

    # Guardar snapshot como último estado
    historico_hoy["ULTIMO"] = snapshot

    # 6) Guardar archivo final
    guardar_json_seguro(archivo_hoy, historico_hoy)

    print(f"✔ Snapshot Bet365 guardado en {archivo_hoy}")


# ================================================
if __name__ == "__main__":
    procesar_historico_bet365()
