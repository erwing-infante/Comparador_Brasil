import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import joblib
import pandas as pd
import requests

# ============================================
# PATHS
# ============================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent                    # /root/proyectos/Mancorabet/Monitor_Orbitx
MAIN_PROJECT_DIR = PROJECT_DIR.parent             # /root/proyectos/Mancorabet

INPUT_DIR = PROJECT_DIR / "data" / "history"
WATCHLIST_FILE = PROJECT_DIR / "data" / "watchlists" / "watchlist.json"
MODEL_FILE = PROJECT_DIR / "models" / "premov_v6_rf.joblib"
OUTPUT_FILE = PROJECT_DIR / "data" / "orbitx_snapshot_alerts_v6_all_history.csv"
STATE_FILE = PROJECT_DIR / "data" / "orbitx_alerts_state_v6.json"
CUOTAS_FILE = MAIN_PROJECT_DIR / "data" / "cuotas.json"

TZ_PE = ZoneInfo("America/Lima")

# ============================================
# DEFAULT CONFIG
# ============================================
DEFAULT_CHECK_INTERVAL_SEC = 30
DEFAULT_THRESHOLD_ALERT = 0.45
DEFAULT_MIN_PROBA_TO_SEND = 0.45
DEFAULT_MIN_ODD = 1.30
DEFAULT_MAX_ODD = 14.00
DEFAULT_MIN_ABS_TV_ACCELERATION = 500.0
DEFAULT_MIN_ABS_ACCELERATION = 0.05
DEFAULT_MAX_SPREAD = 0.10
DEFAULT_MAX_STATE_KEYS = 5000

MARKET_LABELS = {
    "HOME": "LOCAL",
    "DRAW": "EMPATE",
    "AWAY": "VISITA"
}

# ============================================
# ENV HELPERS
# ============================================
def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


# ============================================
# HELPERS GENERALES
# ============================================
def pct_drop(old, new):
    if pd.isna(old) or pd.isna(new) or old == 0:
        return None
    return (old - new) / old * 100.0


def safe_div(a, b):
    if pd.isna(a) or pd.isna(b) or b == 0:
        return None
    return a / b


def build_alert_key(row):
    return f"{row['event_id']}|{row['market_id']}|{row['selection_id']}|{row['ts_pe']}"


def load_state(path: Path):
    if not path.exists():
        return {"sent_keys": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"sent_keys": []}


def save_state(path: Path, state: dict):
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def send_telegram(bot_token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    resp = requests.post(
        url,
        json={
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True
        },
        timeout=20
    )
    resp.raise_for_status()


def fmt_num(x, nd=2, default="-"):
    if x is None or pd.isna(x):
        return default
    return f"{float(x):.{nd}f}"


def parse_utc_to_pe(date_str: str):
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_PE)
    except Exception:
        return None


def now_pe_str():
    return datetime.now(TZ_PE).strftime("%Y-%m-%d %H:%M:%S")


# ============================================
# WATCHLIST
# ============================================
def load_watchlist(watchlist_path: Path):
    if not watchlist_path.exists():
        print(f"⚠️ No existe watchlist.json: {watchlist_path}")
        return {}

    try:
        data = json.loads(watchlist_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ Error leyendo watchlist.json: {e}")
        return {}

    if not isinstance(data, list):
        print("⚠️ watchlist.json no es una lista")
        return {}

    out = {}
    for item in data:
        event_id = str(item.get("eventId", "")).strip()
        market_id = str(item.get("marketId", "")).strip()
        if not event_id or not market_id:
            continue
        key = (event_id, market_id)
        out[key] = item

    print(f"✅ watchlist.json cargado: {len(out)} mercados activos")
    return out


# ============================================
# CUOTAS.JSON
# ============================================
def load_cuotas(cuotas_path: Path):
    if not cuotas_path.exists():
        print(f"⚠️ No existe cuotas.json: {cuotas_path}")
        return {}

    try:
        data = json.loads(cuotas_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ Error leyendo cuotas.json: {e}")
        return {}

    event_map = {}

    for liga, matches in data.items():
        if liga == "metadata":
            continue
        if not isinstance(matches, list):
            continue

        for item in matches:
            event_id = str(item.get("eventId", "")).strip()
            if not event_id:
                continue
            event_map[event_id] = item

    print(f"✅ cuotas.json cargado: {len(event_map)} eventos indexados")
    return event_map


def get_apuesta_total_odd(match_data: dict, market_code: str):
    all_odds = match_data.get("all_odds", [])
    for row in all_odds:
        if str(row.get("bookmaker", "")).strip().lower() == "apuesta total":
            if market_code == "HOME":
                return row.get("home")
            if market_code == "DRAW":
                return row.get("draw")
            if market_code == "AWAY":
                return row.get("away")
    return None


def calc_loss_pct(match_data: dict):
    try:
        h = float(match_data["best_home"]["odd"])
        d = float(match_data["best_draw"]["odd"])
        a = float(match_data["best_away"]["odd"])
        return ((1 / h) + (1 / d) + (1 / a) - 1) * 100
    except Exception:
        return None


def build_telegram_message(row, match_data: dict):
    market_code = str(row.market_type).upper()
    market_label = MARKET_LABELS.get(market_code, market_code)

    liga = match_data.get("Liga", row.liga if hasattr(row, "liga") else "-")
    partido = match_data.get("name", row.event_name)

    dt_pe = parse_utc_to_pe(match_data.get("date", ""))
    fecha_partido_pe = dt_pe.strftime("%Y-%m-%d %H:%M") if dt_pe else "-"

    odd_orbitx = row.odd
    odd_apuesta_total = get_apuesta_total_odd(match_data, market_code)

    variacion_pct = None
    if odd_apuesta_total is not None and odd_orbitx is not None:
        try:
            variacion_pct = ((float(odd_apuesta_total) - float(odd_orbitx)) / float(odd_orbitx)) * 100
        except Exception:
            variacion_pct = None

    best_home = match_data.get("best_home", {})
    best_draw = match_data.get("best_draw", {})
    best_away = match_data.get("best_away", {})

    loss_pct = calc_loss_pct(match_data)

    msg = (
        "🔥 MOVIMIENTO ORBITX\n\n"
        f"{partido}\n"
        f"Liga: {liga}\n"
        f"Fecha: {fecha_partido_pe} (Perú)\n\n"
        "MOVIMIENTO\n"
        f"• Mercado: {market_label}\n"
        f"• OrbitX: {fmt_num(odd_orbitx, 2)}\n"
        f"• Apuesta Total: {fmt_num(odd_apuesta_total, 2)}\n"
        f"• Variación: {fmt_num(variacion_pct, 2)}%\n"
        f"• Probabilidad: {fmt_num(row.proba_fall, 3)}\n"
        f"• Spread: {fmt_num(row.spread, 2)}\n"
        f"• Aceleración cuota: {fmt_num(row.acceleration, 3)}\n"
        f"• Aceleración volumen: {fmt_num(row.tv_acceleration, 2)}\n"
        f"• Pressure: {fmt_num(row.pressure, 3)}\n\n"
        "MEJOR 1X2 ACTUAL\n"
        f"• Local: {fmt_num(best_home.get('odd'), 2)} — {best_home.get('bookmaker', '-')}\n"
        f"• Empate: {fmt_num(best_draw.get('odd'), 2)} — {best_draw.get('bookmaker', '-')}\n"
        f"• Visita: {fmt_num(best_away.get('odd'), 2)} — {best_away.get('bookmaker', '-')}\n"
        f"• %Pérdida: {fmt_num(loss_pct, 3)}%\n\n"
        f"⏱️ {now_pe_str()} (Perú)"
    )
    return msg


# ============================================
# PROCESAR CADA CSV DE HISTORY
# ============================================
def process_file(file_path: Path, min_odd: float, max_odd: float, active_watchlist: dict) -> pd.DataFrame:
    needed_cols = [
        "ts_pe",
        "start_pe",
        "liga",
        "market_id",
        "event_id",
        "event_name",
        "selection",
        "selection_id",
        "selection_name",
        "best_back_odds",
        "best_back_amt",
        "best_lay_odds",
        "best_lay_amt",
        "spread",
        "sum_back_top3",
        "sum_lay_top3",
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
        print(f"⚠️ {file_path.name} sin columnas necesarias: {missing}")
        return pd.DataFrame()

    df = df[needed_cols].copy()

    df["best_back_odds"] = pd.to_numeric(df["best_back_odds"], errors="coerce")
    df["best_back_amt"] = pd.to_numeric(df["best_back_amt"], errors="coerce")
    df["best_lay_odds"] = pd.to_numeric(df["best_lay_odds"], errors="coerce")
    df["best_lay_amt"] = pd.to_numeric(df["best_lay_amt"], errors="coerce")
    df["spread"] = pd.to_numeric(df["spread"], errors="coerce")
    df["sum_back_top3"] = pd.to_numeric(df["sum_back_top3"], errors="coerce")
    df["sum_lay_top3"] = pd.to_numeric(df["sum_lay_top3"], errors="coerce")
    df["blpr"] = pd.to_numeric(df["blpr"], errors="coerce")
    df["tv_runner"] = pd.to_numeric(df["tv_runner"], errors="coerce")

    df["selection"] = df["selection"].astype(str).str.upper().str.strip()
    df["event_id"] = df["event_id"].astype(str).str.strip()
    df["market_id"] = df["market_id"].astype(str).str.strip()

    # 1) filtrar por watchlist activa
    df["watch_key"] = list(zip(df["event_id"], df["market_id"]))
    df = df[df["watch_key"].isin(active_watchlist.keys())].copy()

    if df.empty:
        return pd.DataFrame()

    # 2) filtrar cuotas
    df = df[
        df["best_back_odds"].notna() &
        (df["best_back_odds"] >= min_odd) &
        (df["best_back_odds"] <= max_odd)
    ].copy()

    if df.empty:
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
                "start_pe": cur["start_pe"],
                "liga": cur["liga"],
                "event_id": str(cur["event_id"]),
                "event_name": cur["event_name"],
                "market_id": str(cur["market_id"]),
                "market_type": str(cur["selection"]).upper(),
                "selection_id": str(cur["selection_id"]),
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

    return pd.DataFrame(rows)


# ============================================
# CICLO PRINCIPAL
# ============================================
def main():
    threshold_alert = env_float("ORBITX_ALERTS_THRESHOLD", DEFAULT_THRESHOLD_ALERT)
    min_proba_to_send = env_float("ORBITX_ALERTS_MIN_PROBA", DEFAULT_MIN_PROBA_TO_SEND)
    min_odd = env_float("ORBITX_ALERTS_MIN_ODD", DEFAULT_MIN_ODD)
    max_odd = env_float("ORBITX_ALERTS_MAX_ODD", DEFAULT_MAX_ODD)
    min_abs_tv_acceleration = env_float("ORBITX_ALERTS_MIN_TV_ACCEL", DEFAULT_MIN_ABS_TV_ACCELERATION)
    min_abs_acceleration = env_float("ORBITX_ALERTS_MIN_ACCEL", DEFAULT_MIN_ABS_ACCELERATION)
    max_spread = env_float("ORBITX_ALERTS_MAX_SPREAD", DEFAULT_MAX_SPREAD)
    max_state_keys = env_int("ORBITX_ALERTS_MAX_STATE_KEYS", DEFAULT_MAX_STATE_KEYS)

    telegram_token = env_str("SMART_BOT_TOKEN", "")
    chat_ids = [
        env_str("SMART_BOT_CHAT_ID", ""),
        env_str("SMART_BOT_CHAT_ID_2", ""),
        env_str("SMART_BOT_CHAT_ID_3", ""),
    ]
    chat_ids = [c for c in chat_ids if c]

    if not MODEL_FILE.exists():
        print(f"❌ No existe el modelo: {MODEL_FILE}")
        return

    if not telegram_token or not chat_ids:
        print("❌ Faltan SMART_BOT_TOKEN o SMART_BOT_CHAT_ID en orbitx_alerts_v6.env")
        return

    active_watchlist = load_watchlist(WATCHLIST_FILE)
    cuotas_map = load_cuotas(CUOTAS_FILE)

    if not active_watchlist:
        print("⚠️ Watchlist vacía, no hay mercados activos para evaluar")
        return

    bundle = joblib.load(MODEL_FILE)
    model = bundle["model"]
    features = bundle["features"]

    print(f"✅ Modelo cargado: {MODEL_FILE}")
    print(f"📂 Leyendo history desde: {INPUT_DIR}")

    files = sorted(INPUT_DIR.glob("*.csv"))
    if not files:
        print(f"❌ No se encontraron CSV en {INPUT_DIR}")
        return

    all_parts = []
    for file_path in files:
        part = process_file(
            file_path,
            min_odd=min_odd,
            max_odd=max_odd,
            active_watchlist=active_watchlist
        )
        print(f"✅ {file_path.name} -> filas construidas: {len(part)}")
        if not part.empty:
            all_parts.append(part)

    if not all_parts:
        print("❌ No se pudo construir ninguna fila para scoring")
        return

    score_df = pd.concat(all_parts, ignore_index=True)
    score_df = score_df.dropna(subset=features).copy()

    if score_df.empty:
        print("❌ No quedaron filas válidas tras dropna")
        return

    score_df["proba_fall"] = model.predict_proba(score_df[features])[:, 1]
    score_df["is_alert_model"] = (score_df["proba_fall"] >= threshold_alert).astype(int)

    score_df = score_df[
        (score_df["is_alert_model"] == 1) &
        (score_df["proba_fall"] >= min_proba_to_send) &
        (score_df["tv_acceleration"].abs() > min_abs_tv_acceleration) &
        (score_df["acceleration"].abs() > min_abs_acceleration) &
        (score_df["spread"] <= max_spread)
    ].copy()

    if score_df.empty:
        print("⚠️ No quedaron alertas operables")
        pd.DataFrame().to_csv(OUTPUT_FILE, index=False)
        return

    score_df["is_alert"] = 1
    score_df["alert_key"] = score_df.apply(build_alert_key, axis=1)

    score_df = score_df.sort_values(
        ["proba_fall", "tv_acceleration", "acceleration", "event_name"],
        ascending=[False, False, False, True]
    ).reset_index(drop=True)

    score_df.to_csv(OUTPUT_FILE, index=False)

    state = load_state(STATE_FILE)
    sent_keys = set(state.get("sent_keys", []))

    new_alerts = score_df[~score_df["alert_key"].isin(sent_keys)].copy()

    print(f"📊 Alertas operables actuales: {len(score_df)}")
    print(f"🆕 Alertas nuevas a enviar: {len(new_alerts)}")

    if new_alerts.empty:
        print("✅ No hay alertas nuevas")
        return

    sent_now = 0

    for row in new_alerts.itertuples(index=False):
        match_data = cuotas_map.get(str(row.event_id))
        if not match_data:
            print(f"⚠️ No se encontró eventId {row.event_id} en cuotas.json")
            continue

        msg = build_telegram_message(row, match_data)

        try:
            for chat_id in chat_ids:
                send_telegram(telegram_token, chat_id, msg)
            sent_keys.add(row.alert_key)
            sent_now += 1
            print(f"📨 Enviado: {row.event_name} | {row.market_type} | {row.odd}")
        except Exception as e:
            print(f"⚠️ Error enviando alerta: {e}")

    state["sent_keys"] = sorted(sent_keys)[-max_state_keys:]
    save_state(STATE_FILE, state)

    print(f"✅ Estado actualizado en: {STATE_FILE}")
    print(f"✅ CSV actualizado en: {OUTPUT_FILE}")
    print(f"✅ Alertas enviadas en este ciclo: {sent_now}")


# ============================================
# LOOP
# ============================================
if __name__ == "__main__":
    interval_sec = DEFAULT_CHECK_INTERVAL_SEC

    while True:
        try:
            interval_sec = env_int("ORBITX_ALERTS_INTERVAL_SEC", DEFAULT_CHECK_INTERVAL_SEC)
            print("==================================================")
            print(f"Iniciando ciclo: {now_pe_str()} (Perú)")
            main()
        except Exception as e:
            print(f"❌ Error en ciclo principal: {e}")

        print(f"⏳ Esperando {interval_sec} segundos...\n")
        time.sleep(interval_sec)