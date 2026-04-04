import os
from glob import glob
from pathlib import Path
import joblib
import pandas as pd

# ============================================
# PATHS DINÁMICOS
# ============================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent  # .../Monitor_Orbitx

INPUT_DIR = PROJECT_DIR / "data" / "history"
MODEL_FILE = PROJECT_DIR / "models" / "premov_v6_rf.joblib"
OUTPUT_FILE = PROJECT_DIR / "data" / "orbitx_snapshot_alerts_v6_all_history.csv"

# ============================================
# CONFIG
# ============================================
THRESHOLD_ALERT = 0.45

# rango de cuotas
MIN_ODD = 1.30
MAX_ODD = 14.00

# filtros de actividad
MIN_ABS_TV_ACCELERATION = 500
MIN_ABS_ACCELERATION = 0.05
MAX_SPREAD = 0.10

# ============================================
# HELPERS
# ============================================
def pct_drop(old, new):
    if pd.isna(old) or pd.isna(new) or old == 0:
        return None
    return (old - new) / old * 100.0


def safe_div(a, b):
    if pd.isna(a) or pd.isna(b) or b == 0:
        return None
    return a / b


def process_file(file_path: Path) -> pd.DataFrame:
    needed_cols = [
        "ts_pe",
        "event_id",
        "event_name",
        "market_id",
        "selection_id",
        "selection_name",
        "best_back_odds",
        "best_lay_amt",
        "spread",
        "blpr",
        "tv_runner"
    ]

    try:
        df = pd.read_csv(file_path, low_memory=False)
    except Exception as e:
        print(f"⚠️ Error leyendo {file_path.name}: {e}")
        return pd.DataFrame()

    missing = [c for c in needed_cols if c not in df.columns]
    if missing:
        print(f"⚠️ {file_path.name} sin columnas: {missing}")
        return pd.DataFrame()

    df = df[needed_cols].copy()

    df["best_back_odds"] = pd.to_numeric(df["best_back_odds"], errors="coerce")
    df["best_lay_amt"] = pd.to_numeric(df["best_lay_amt"], errors="coerce")
    df["spread"] = pd.to_numeric(df["spread"], errors="coerce")
    df["blpr"] = pd.to_numeric(df["blpr"], errors="coerce")
    df["tv_runner"] = pd.to_numeric(df["tv_runner"], errors="coerce")

    # filtro de cuota
    df = df[
        df["best_back_odds"].notna() &
        (df["best_back_odds"] >= MIN_ODD) &
        (df["best_back_odds"] <= MAX_ODD)
    ].copy()

    if df.empty:
        print(f"⚠️ {file_path.name} quedó vacío tras filtro de cuotas")
        return pd.DataFrame()

    df = df.sort_values(["event_id", "market_id", "selection_id", "ts_pe"]).reset_index(drop=True)

    rows = []

    for (_, _), g_event in df.groupby(["event_id", "market_id"], sort=False):
        g_event = g_event.copy()
        g_event["rank_odds"] = g_event.groupby("ts_pe")["best_back_odds"].rank(method="average")

        for (_, _), g in g_event.groupby(["market_id", "selection_id"], sort=False):
            g = g.reset_index(drop=True)

            if len(g) < 3:
                continue

            cur = g.iloc[-1]
            p1 = g.iloc[-2]
            p2 = g.iloc[-3]

            d1 = cur["best_back_odds"] - p1["best_back_odds"]
            d2 = p1["best_back_odds"] - p2["best_back_odds"]
            acceleration = d1 - d2

            tv1 = cur["tv_runner"] - p1["tv_runner"]
            tv2 = p1["tv_runner"] - p2["tv_runner"]
            tv_acceleration = tv1 - tv2

            pressure_ratio = safe_div(cur["blpr"], p1["blpr"])

            drop1 = pct_drop(p1["best_back_odds"], cur["best_back_odds"])
            drop2 = pct_drop(p2["best_back_odds"], cur["best_back_odds"])
            drop_velocity = None
            if drop1 is not None and drop2 is not None:
                drop_velocity = drop1 - drop2

            rows.append({
                "source_file": file_path.name,
                "ts_pe": cur["ts_pe"],
                "event_id": cur["event_id"],
                "event_name": cur["event_name"],
                "market_id": cur["market_id"],
                "selection_id": cur["selection_id"],
                "selection_name": cur["selection_name"],
                "odd": cur["best_back_odds"],
                "pressure": cur["blpr"],
                "spread": cur["spread"],
                "acceleration": acceleration,
                "tv_acceleration": tv_acceleration,
                "pressure_ratio": pressure_ratio,
                "drop_velocity": drop_velocity,
                "rank_odds": cur["rank_odds"]
            })

    out = pd.DataFrame(rows)
    print(f"✅ {file_path.name} -> filas construidas: {len(out)}")
    return out


# ============================================
# LOAD MODEL
# ============================================
if not MODEL_FILE.exists():
    print(f"❌ No existe el modelo: {MODEL_FILE}")
    raise SystemExit

bundle = joblib.load(MODEL_FILE)
model = bundle["model"]
FEATURES = bundle["features"]

print(f"✅ Modelo cargado: {MODEL_FILE}")
print(f"📂 Carpeta history: {INPUT_DIR}")
print(f"📄 Archivo de salida: {OUTPUT_FILE}")

# ============================================
# READ ALL HISTORY FILES
# ============================================
files = sorted(INPUT_DIR.glob("*.csv"))

if not files:
    print(f"❌ No se encontraron CSV en: {INPUT_DIR}")
    raise SystemExit

print(f"📂 CSV detectados: {len(files)}")

all_parts = []
for file_path in files:
    part = process_file(file_path)
    if not part.empty:
        all_parts.append(part)

if not all_parts:
    print("❌ No se pudo construir ninguna fila para scoring")
    pd.DataFrame().to_csv(OUTPUT_FILE, index=False)
    print(f"✅ CSV vacío guardado en: {OUTPUT_FILE}")
    raise SystemExit

score_df = pd.concat(all_parts, ignore_index=True)

print(f"📊 Filas totales construidas: {len(score_df)}")

score_df = score_df.dropna(subset=FEATURES).copy()

print(f"📊 Filas tras dropna(features): {len(score_df)}")

if score_df.empty:
    print("❌ No quedaron filas válidas tras dropna")
    pd.DataFrame().to_csv(OUTPUT_FILE, index=False)
    print(f"✅ CSV vacío guardado en: {OUTPUT_FILE}")
    raise SystemExit

# ============================================
# SCORE
# ============================================
score_df["proba_fall"] = model.predict_proba(score_df[FEATURES])[:, 1]
score_df["is_alert_model"] = (score_df["proba_fall"] >= THRESHOLD_ALERT).astype(int)

print(f"📊 Filas puntuadas: {len(score_df)}")

# ============================================
# FILTRO FINAL OPERABLE
# ============================================
score_df = score_df[
    (score_df["is_alert_model"] == 1) &
    (score_df["tv_acceleration"].abs() > MIN_ABS_TV_ACCELERATION) &
    (score_df["acceleration"].abs() > MIN_ABS_ACCELERATION) &
    (score_df["spread"] <= MAX_SPREAD)
].copy()

print(f"📊 Filas tras filtro final operable: {len(score_df)}")

if score_df.empty:
    print("⚠️ No quedaron alertas operables")
    pd.DataFrame(columns=[
        "source_file", "ts_pe", "event_id", "event_name", "market_id",
        "selection_id", "selection_name", "odd", "pressure", "spread",
        "acceleration", "tv_acceleration", "pressure_ratio", "drop_velocity",
        "rank_odds", "proba_fall", "is_alert"
    ]).to_csv(OUTPUT_FILE, index=False)
    print(f"✅ CSV vacío guardado en: {OUTPUT_FILE}")
    raise SystemExit

score_df["is_alert"] = 1

score_df = score_df.sort_values(
    ["proba_fall", "tv_acceleration", "acceleration", "event_name"],
    ascending=[False, False, False, True]
).reset_index(drop=True)

score_df.to_csv(OUTPUT_FILE, index=False)

print(f"✅ Alertas guardadas en: {OUTPUT_FILE}")
print(f"🎯 Alertas finales: {len(score_df)}")
print(f"📌 Partidos únicos con alerta: {score_df['event_name'].nunique()}")

show_cols = [
    "source_file",
    "ts_pe",
    "event_name",
    "selection_name",
    "odd",
    "pressure",
    "spread",
    "acceleration",
    "tv_acceleration",
    "pressure_ratio",
    "drop_velocity",
    "rank_odds",
    "proba_fall",
    "is_alert"
]

print("\n================ ALERTAS V6 TODAS LAS LIGAS ================\n")
print(score_df[show_cols].head(50).to_string(index=False))
print("\n============================================================\n")