import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

# ============================================
# CONFIG
# ============================================
DATASET_FILE = "/root/proyectos/Mancorabet/Monitor_Orbitx/data/dataset_premov.csv"

FEATURES = [
    "odd",
    "spread",
    "pressure",
    "laydrop1",
    "laydrop2",
    "spreadclose1",
    "tv_delta2",
    "drop1",
    "drop2"
]


# ============================================
# MAIN
# ============================================
df = pd.read_csv(DATASET_FILE)

print(f"📂 Dataset cargado: {DATASET_FILE}")
print(f"📊 Filas originales: {len(df)}")

work = df[FEATURES + ["target"]].copy()
work = work.dropna()

print(f"📊 Filas luego de dropna: {len(work)}")
print("📊 Distribución target:")
print(work["target"].value_counts(dropna=False))

if len(work) < 50:
    print("❌ Muy pocas filas útiles para entrenar")
    raise SystemExit

X = work[FEATURES]
y = work["target"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.30,
    random_state=42,
    stratify=y
)

model = RandomForestClassifier(
    n_estimators=100,
    random_state=42,
    n_jobs=-1
)

model.fit(X_train, y_train)

y_pred = model.predict(X_test)

print("\n================= CLASSIFICATION REPORT =================\n")
print(classification_report(y_test, y_pred, digits=4))

print("\n================= CONFUSION MATRIX =================\n")
print(confusion_matrix(y_test, y_pred))

print("\n================= FEATURE IMPORTANCE =================\n")
for name, val in zip(FEATURES, model.feature_importances_):
    print(f"{name}: {round(val, 6)}")

print("\n========================================================\n")