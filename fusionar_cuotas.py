import os
import json
import unicodedata
from datetime import datetime
import pandas as pd
from difflib import SequenceMatcher

# === CONFIG ===
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUT_FILE = os.path.join(DATA_DIR, "cuotas.json")

ARCHIVOS = {
    "oddsapi": os.path.join(DATA_DIR, "cuotas_oddsapi.json"),
    "apuestatotal": os.path.join(DATA_DIR, "cuotas_apuestatotal.json"),
    "doradobet": os.path.join(DATA_DIR, "cuotas_doradobet.json"),
    "atlanticcity": os.path.join(DATA_DIR, "cuotas_atlanticcity.json"),
}

# Similitud mínima
SIM_THRESHOLD = 0.40

# Casas excluidas en local/visita
BOOKMAKERS_EXCLUIR_HA = {"betcris", "betsson", "1xbet"}

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
    nombre = quitar_acentos(nombre).lower()
    nombre = nombre.replace("\t", " ").replace("\n", " ")
    nombre = nombre.replace("-", " ").replace("_", " ").replace("/", " ")
    tokens = nombre.split()
    tokens = [t for t in tokens if t not in STOP_TOKENS]
    return " ".join(tokens).strip()

def team_short(name: str) -> str:
    limpio = limpiar_equipo(name)
    if not limpio:
        return "desconocido"
    return max(limpio.split(), key=len)

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

    # Reconstruir Local vs Visita si están vacíos
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

    df["Local"] = df["Local"].astype(str).apply(limpiar_equipo)
    df["Visita"] = df["Visita"].astype(str).apply(limpiar_equipo)
    df["home_short"] = df["Local"].apply(team_short)
    df["away_short"] = df["Visita"].apply(team_short)

    df["Fecha_dt"] = pd.to_datetime(df["Fecha"], errors="coerce").dt.tz_localize(None)

    return df

# ============================================================
# FUSIÓN RÁPIDA CON BUCKETS
# ============================================================

def fusionar_cuotas():
    print("Fusionando mucho más rápido...")

    # CARGAR TODO
    df_list = []
    for nombre, ruta in ARCHIVOS.items():
        df = cargar_json(ruta)
        if not df.empty:
            df["Origen"] = nombre
            df_list.append(df)

    if not df_list:
        print("F No hay datos.")
        return

    df = pd.concat(df_list, ignore_index=True)

    # Filtrar inválidos
    df = df[
        (df["home_short"] != "desconocido") &
        (df["away_short"] != "desconocido")
    ]

    # Creamos BUCKETS para acelerar
    buckets = {}

    for idx, row in df.iterrows():
        liga = row["Liga"]
        fecha = row["Fecha_dt"]

        if pd.isna(fecha):
            continue

        fecha_clave = fecha.replace(minute=0, second=0, microsecond=0)
        h0 = row["home_short"][:1]
        a0 = row["away_short"][:1]

        key = (liga, fecha_clave, h0, a0)
        buckets.setdefault(key, []).append(idx)

    usados = set()
    filas = []

    # PROCESO 40x MÁS RÁPIDO
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

                # chequeo rápido: mismo liga & ±2h
                if abs((row["Fecha_dt"] - row2["Fecha_dt"]).total_seconds()) > 7200:
                    continue

                # coincidencia difusa
                if similitud(row["home_short"], row2["home_short"]) >= SIM_THRESHOLD and \
                   similitud(row["away_short"], row2["away_short"]) >= SIM_THRESHOLD:
                    grupo.append(j)
                    usados.add(j)

            subset = df.loc[grupo]
            usados.update(grupo)

            # Selección de mejores cuotas
            def mejor(col):
                col_lower = col.lower()

                # EMPATE = no excluir
                if "empate" in col_lower:
                    s = subset[subset[col].notna()]
                    if s.empty:
                        return None, ""
                    idx = s[col].idxmax()
                    return float(s.loc[idx, col]), s.loc[idx, "Casa"]

                # LOCAL / VISITA excluyendo casas
                s = subset[
                    subset[col].notna() &
                    (~subset["Casa"].str.replace(" ", "").str.lower().isin(BOOKMAKERS_EXCLUIR_HA))
                ]

                if not s.empty:
                    idx = s[col].idxmax()
                    return float(s.loc[idx, col]), s.loc[idx, "Casa"]

                # fallback – si quedaron solo casas prohibidas
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

            filas.append({
                "Liga": base["Liga"],
                "name": base["Partido"],
                "home": base["Local"],
                "away": base["Visita"],
                "date": fecha_str,
                "best_home": {"odd": bh, "bookmaker": bh_bm},
                "best_draw": {"odd": bd, "bookmaker": bd_bm},
                "best_away": {"odd": ba, "bookmaker": ba_bm},
            })

    # ORDENAR Y GUARDAR
    salida = {}
    for fila in filas:
        salida.setdefault(fila["Liga"], []).append(fila)

    for liga in salida:
        try:
            salida[liga].sort(key=lambda x: datetime.strptime(x["date"], "%Y-%m-%d %H:%M UTC"))
        except:
            pass

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(salida, f, indent=2, ensure_ascii=False)

    print(f"Ok Archivo actualizado: {OUT_FILE}")


if __name__ == "__main__":
    fusionar_cuotas()
