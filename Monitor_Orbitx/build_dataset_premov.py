import os
from glob import glob
import pandas as pd

# ============================================
# CONFIG
# ============================================
DATA_PATH = "/root/proyectos/Mancorabet/Monitor_Orbitx/data/history/"
OUTPUT_FILE = "/root/proyectos/Mancorabet/Monitor_Orbitx/data/dataset_premov.csv"

FUTURE_WINDOW = 5   # cuantos snapshots mirar adelante
TARGET_DROP = 0.8   # % mínimo de caída futura para target=1


# ============================================
# HELPERS
# ============================================
def pct_drop(old, new):
    if pd.isna(old) or pd.isna(new) or old == 0:
        return None
    return (old - new) / old * 100.0


# ============================================
# MAIN
# ============================================
rows = []

files = glob(os.path.join(DATA_PATH, "*.csv"))

if not files:
    print(f"❌ No se encontraron archivos CSV en {DATA_PATH}")
    raise SystemExit

print(f"📂 CSV encontrados: {len(files)}")

for file in files:
    try:
        df = pd.read_csv(file)
    except Exception as e:
        print(f"⚠️ Error leyendo {file}: {e}")
        continue

    if df.empty:
        print(f"⚠️ Archivo vacío: {file}")
        continue

    # Nos quedamos solo con columnas necesarias
    needed_cols = [
        "ts_pe",
        "market_id",
        "selection_id",
        "event_id",
        "event_name",
        "selection_name",
        "best_back_odds",
        "best_lay_amt",
        "spread",
        "blpr",
        "tv_runner"
    ]

    missing = [c for c in needed_cols if c not in df.columns]
    if missing:
        print(f"⚠️ {os.path.basename(file)} no tiene columnas: {missing}")
        continue

    df = df[needed_cols].copy()

    # convertir numéricas
    df["best_back_odds"] = pd.to_numeric(df["best_back_odds"], errors="coerce")
    df["best_lay_amt"] = pd.to_numeric(df["best_lay_amt"], errors="coerce")
    df["spread"] = pd.to_numeric(df["spread"], errors="coerce")
    df["blpr"] = pd.to_numeric(df["blpr"], errors="coerce")
    df["tv_runner"] = pd.to_numeric(df["tv_runner"], errors="coerce")

    # ordenar por timestamp dentro de cada selección
    df = df.sort_values(["market_id", "selection_id", "ts_pe"]).reset_index(drop=True)

    # procesar por selección para no mezclar runners
    grouped = df.groupby(["market_id", "selection_id"], sort=False)

    file_rows = 0

    for (market_id, selection_id), g in grouped:
        g = g.reset_index(drop=True)

        if len(g) < FUTURE_WINDOW + 3:
            continue

        for i in range(2, len(g) - FUTURE_WINDOW):
            cur = g.iloc[i]
            p1 = g.iloc[i - 1]
            p2 = g.iloc[i - 2]

            # FEATURES
            odd = cur["best_back_odds"]
            spread = cur["spread"]
            pressure = cur["blpr"]
            lay_amt = cur["best_lay_amt"]
            tv = cur["tv_runner"]

            drop1 = pct_drop(p1["best_back_odds"], cur["best_back_odds"])
            drop2 = pct_drop(p2["best_back_odds"], cur["best_back_odds"])

            laydrop1 = pct_drop(p1["best_lay_amt"], cur["best_lay_amt"])
            laydrop2 = pct_drop(p2["best_lay_amt"], cur["best_lay_amt"])

            spreadclose1 = pct_drop(p1["spread"], cur["spread"])

            tv_delta2 = None
            if not pd.isna(cur["tv_runner"]) and not pd.isna(p2["tv_runner"]):
                tv_delta2 = cur["tv_runner"] - p2["tv_runner"]

            # TARGET
            future_prices = g.iloc[i + 1:i + 1 + FUTURE_WINDOW]["best_back_odds"].dropna().values

            if len(future_prices) == 0:
                continue

            min_future = future_prices.min()
            future_drop = pct_drop(cur["best_back_odds"], min_future)

            target = 1 if future_drop is not None and future_drop >= TARGET_DROP else 0

            rows.append({
                "source_file": os.path.basename(file),
                "ts_pe": cur["ts_pe"],
                "event_id": cur["event_id"],
                "event_name": cur["event_name"],
                "market_id": cur["market_id"],
                "selection_id": cur["selection_id"],
                "selection_name": cur["selection_name"],
                "odd": odd,
                "spread": spread,
                "pressure": pressure,
                "laydrop1": laydrop1,
                "laydrop2": laydrop2,
                "spreadclose1": spreadclose1,
                "tv_delta2": tv_delta2,
                "drop1": drop1,
                "drop2": drop2,
                "future_drop": future_drop,
                "target": target
            })

            file_rows += 1

    print(f"✅ {os.path.basename(file)} -> {file_rows} filas dataset")

if not rows:
    print("❌ No se generaron filas para el dataset")
    raise SystemExit

dataset = pd.DataFrame(rows)
dataset.to_csv(OUTPUT_FILE, index=False)

print("\n====================================")
print(f"✅ Dataset creado: {OUTPUT_FILE}")
print(f"📊 Total filas: {len(dataset)}")
print("📊 Distribución target:")
print(dataset["target"].value_counts(dropna=False))
print("====================================")