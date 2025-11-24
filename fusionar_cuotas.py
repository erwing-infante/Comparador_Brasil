# fusionador_cuotas.py
import os
import json
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from difflib import SequenceMatcher

# === IMPORTAR EQUIVALENCIAS PLANAS DESDE ARCHIVO EXTERNO ===
from equivalencias_equipos import EQUIVALENCIAS_EQUIPOS

# === CONFIG ===
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_FILE = os.path.join(DATA_DIR, "cuotas.json")

ARCHIVOS = {
    "oddsapi": os.path.join(DATA_DIR, "cuotas_oddsapi.json"),
    "apuestatotal": os.path.join(DATA_DIR, "cuotas_apuestatotal.json"),
    "doradobet": os.path.join(DATA_DIR, "cuotas_doradobet.json"),
    "atlanticcity": os.path.join(DATA_DIR, "cuotas_atlanticcity.json"),
    "olimpobet": os.path.join(DATA_DIR, "cuotas_olimpobet.json"),
}

# Similitud mínima
SIM_THRESHOLD = 0.40

# Casas excluidas en local/visita
BOOKMAKERS_EXCLUIR_HA = {"betcris", "betsson", "1xbet", "pinnacle"}

# ============================================================
# NORMALIZACIÓN
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

def limpiar_equipo(nombre: str) -> str:
    if not isinstance(nombre, str):
        return ""

    original = nombre.strip()

    # 🔥 1) BÚSQUEDA DIRECTA EN EL DICCIONARIO PLANO EXTERNO (exacto)
    if original in EQUIVALENCIAS_EQUIPOS:
        return EQUIVALENCIAS_EQUIPOS[original]

    # 🔥 2) Fallback → limpieza automática
    nombre = quitar_acentos(original).lower()
    nombre = nombre.replace("\t", " ").replace("\n", " ")
    nombre = nombre.replace("-", " ").replace("_", " ").replace("/", " ")

    tokens = [t for t in nombre.split() if t not in STOP_TOKENS]
    limpio = " ".join(tokens).strip()

    # Si este limpio coincide con una clave del diccionario → normalizar
    if limpio in EQUIVALENCIAS_EQUIPOS:
        return EQUIVALENCIAS_EQUIPOS[limpio]

    # Último fallback → devolver limpio
    return limpio or original

def team_short(name: str) -> str:
    limpio = limpiar_equipo(name)
    if not limpio:
        return "desconocido"
    tokens = [t for t in limpio.split() if t not in STOP_TOKENS]
    if not tokens:
        return "desconocido"
    return max(tokens, key=len)

def similitud(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

# ============================================================
# CARGA JSON
# ============================================================

def cargar_json(ruta: str) -> pd.DataFrame:
    if not os.path.exists(ruta):
        return pd.DataFrame()
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except:
        return pd.DataFrame()

    if not isinstance(raw, list):
        return pd.DataFrame()

    df = pd.DataFrame(raw)

    df.rename(columns={
        "Cuota Local": "Local Odd",
        "Cuota Empate": "Empate Odd",
        "Cuota Visita": "Visita Odd"
    }, inplace=True)

    for col in ["Liga", "Partido", "Casa", "Fecha", "Local", "Visita"]:
        if col not in df.columns:
            df[col] = ""

    for c in ["Local Odd", "Empate Odd", "Visita Odd"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    vacios = (df["Local"].astype(str).str.strip() == "") | \
             (df["Visita"].astype(str).str.strip() == "")

    if vacios.any():
        equipos = df.loc[vacios, "Partido"].astype(str).str.split(
            r"\s+vs\.?\s+|\s+v\s+|\s+VS\s+",
            n=1, regex=True, expand=True
        )
        if equipos.shape[1] == 2:
            df.loc[vacios, "Local"] = equipos[0].str.strip()
            df.loc[vacios, "Visita"] = equipos[1].str.strip()

    # 🔥 NORMALIZACIÓN EXTERNA DEFINITIVA
    df["Local"] = df["Local"].astype(str).apply(limpiar_equipo)
    df["Visita"] = df["Visita"].astype(str).apply(limpiar_equipo)

    df["home_short"] = df["Local"].apply(team_short)
    df["away_short"] = df["Visita"].apply(team_short)

    df["Fecha_dt"] = (
        pd.to_datetime(df["Fecha"], errors="coerce", utc=True)
          .dt.tz_convert("UTC")
          .dt.tz_localize(None)
    )

    return df

# ============================================================
# FUSIÓN CON BUCKETS
# ============================================================

def partido_hash(row):
    return (
        row["Liga"],
        row["Fecha_dt"].replace(minute=0, second=0, microsecond=0),
        row["home_short"],
        row["away_short"]
    )

def fusionar_cuotas():
    print("Fusionando con equivalencias externas (diccionario plano)...")

    df_list = []
    fuentes_ok = []
    fuentes_error = []

    for nombre, ruta in ARCHIVOS.items():
        df = cargar_json(ruta)
        if not df.empty:
            df["Origen"] = nombre
            df_list.append(df)
            fuentes_ok.append(nombre)
        else:
            fuentes_error.append(nombre)

    if not df_list:
        print("F No hay datos.")
        return

    df = pd.concat(df_list, ignore_index=True)

    df = df[
        (df["home_short"] != "desconocido") &
        (df["away_short"] != "desconocido")
    ]

    buckets = {}
    for idx, row in df.iterrows():
        if pd.isna(row["Fecha_dt"]):
            continue
        key = partido_hash(row)
        buckets.setdefault(key, []).append(idx)

    usados = set()
    filas = []
    llaves_existentes = set()

    for key, indices in buckets.items():
        for i in indices:
            if i in usados:
                continue
            row = df.loc[i]
            grupo = [i]

            for j in indices:
                if j == i or j in usados:
                    continue
                row2 = df.loc[j]

                if abs((row["Fecha_dt"] - row2["Fecha_dt"]).total_seconds()) > 21600:
                    continue

                if similitud(row["home_short"], row2["home_short"]) >= SIM_THRESHOLD and \
                   similitud(row["away_short"], row2["away_short"]) >= SIM_THRESHOLD:
                    grupo.append(j)
                    usados.add(j)

            subset = df.loc[grupo]
            usados.update(grupo)

            def mejor(col):
                col_lower = col.lower()
                if "empate" in col_lower:
                    s = subset[subset[col].notna()]
                    if s.empty:
                        return None, ""
                    idx = s[col].idxmax()
                    return float(s.loc[idx, col]), s.loc[idx, "Casa"]

                s = subset[
                    subset[col].notna() &
                    (~subset["Casa"].str.replace(" ", "").str.lower()
                    .isin(BOOKMAKERS_EXCLUIR_HA))
                ]

                if not s.empty:
                    idx = s[col].idxmax()
                    return float(s[col].max()), s.loc[idx, "Casa"]

                s_all = subset[subset[col].notna()]
                if s_all.empty:
                    return None, ""
                idx = s_all[col].idxmax()
                return float(s_all.loc[idx, col]), s_all.loc[idx, "Casa"]

            bh, bh_bm = mejor("Local Odd")
            bd, bd_bm = mejor("Empate Odd")
            ba, ba_bm = mejor("Visita Odd")

            base = subset.iloc[0]
            fecha_dt = base["Fecha_dt"]
            fecha_str = fecha_dt.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(fecha_dt) else ""

            clave = (base["Liga"], fecha_str, base["Local"], base["Visita"])
            if clave in llaves_existentes:
                continue
            llaves_existentes.add(clave)

            filas.append({
                "Liga": base["Liga"],
                "name": f"{base['Local'].title()} vs {base['Visita'].title()}",
                "home": base["Local"],
                "away": base["Visita"],
                "date": fecha_str,
                "best_home": {"odd": bh, "bookmaker": bh_bm},
                "best_draw": {"odd": bd, "bookmaker": bd_bm},
                "best_away": {"odd": ba, "bookmaker": ba_bm},
            })

    # ============================================================
    # SALIDA FINAL
    # ============================================================

    salida = {
        "metadata": {
            "updated": datetime.now(ZoneInfo("America/Lima")).strftime("%Y-%m-%d %H:%M:%S"),
            "fuentes_ok": fuentes_ok,
            "fuentes_error": fuentes_error
        }
    }

    for fila in filas:
        salida.setdefault(fila["Liga"], []).append(fila)

    for liga in salida:
        if liga == "metadata":
            continue
        try:
            salida[liga].sort(key=lambda x: datetime.strptime(x["date"], "%Y-%m-%d %H:%M"))
        except:
            pass

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    print(f"✔ Archivo actualizado: {OUT_FILE}")


if __name__ == "__main__":
    fusionar_cuotas()
