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
PROJECT_DIR = SCRIPT_DIR.parent
MAIN_PROJECT_DIR = PROJECT_DIR.parent

WATCHLIST_FILE = PROJECT_DIR / "data" / "watchlists" / "watchlist.json"
SNAPSHOT_FILE = PROJECT_DIR / "data" / "snapshot.json"
INDEX_FILE = PROJECT_DIR / "data" / "history_recent_index.json"
MODEL_FILE = PROJECT_DIR / "models" / "premov_v6_rf.joblib"
OUTPUT_FILE = PROJECT_DIR / "data" / "orbitx_snapshot_alerts_v7_1.csv"
STATE_FILE = PROJECT_DIR / "data" / "orbitx_alerts_state_v7_1.json"
CUOTAS_FILE = MAIN_PROJECT_DIR / "data" / "cuotas.json"

TZ_PE = ZoneInfo("America/Lima")

# ============================================
# CONFIG DEFAULTS
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
# ENV
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

def fmt_num(x, nd=2, default="-"):
    if x is None or pd.isna(x):
        return default
    return f"{float(x):.{nd}f}"

def build_alert_key(row):
    return f"{row['event_id']}|{row['market_id']}|{row['selection_id']}|{row['ts_pe']}"

def parse_iso_dt(value: str):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None

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

# ============================================
# LOADERS
# ============================================
def load_json(path: Path, label: str):
    if not path.exists():
        print(f"⚠️ No existe {label}: {path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"⚠️ Error leyendo {label}: {e}")
        return None

def load_watchlist():
    data = load_json(WATCHLIST_FILE, "watchlist.json")
    if not isinstance(data, list):
        return {}
    out = {}
    for item in data:
        event_id = str(item.get("eventId", "")).strip()
        market_id = str(item.get("marketId", "")).strip()
        if event_id and market_id:
            out[(event_id, market_id)] = item
    print(f"✅ watchlist.json cargado: {len(out)} mercados activos")
    return out

def load_snapshot():
    data = load_json(SNAPSHOT_FILE, "snapshot.json")
    if not isinstance(data, dict):
        return [], None
    markets = data.get("markets", [])
    generated_at = data.get("generated_at")
    if not isinstance(markets, list):
        return [], generated_at
    print(f"✅ snapshot.json cargado: {len(markets)} mercados")
    return markets, generated_at

def load_cuotas():
    data = load_json(CUOTAS_FILE, "cuotas.json")
    if not isinstance(data, dict):
        return {}
    out = {}
    for liga, matches in data.items():
        if liga == "metadata":
            continue
        if not isinstance(matches, list):
            continue
        for item in matches:
            event_id = str(item.get("eventId", "")).strip()
            if event_id:
                out[event_id] = item
    print(f"✅ cuotas.json cargado: {len(out)} eventos indexados")
    return out

def load_index():
    data = load_json(INDEX_FILE, "history_recent_index.json")
    if not isinstance(data, dict):
        return {}
    rows = data.get("rows", {})
    if not isinstance(rows, dict):
        return {}
    print(f"✅ history_recent_index.json cargado: {len(rows)} keys")
    return rows

# ============================================
# CUOTAS HELPERS
# ============================================
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

    liga = match_data.get("Liga", row.liga)
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

    return (
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

# ============================================
# SNAPSHOT UNIVERSE
# ============================================
def build_active_snapshot_rows(markets, watchlist_map, cuotas_map, min_odd, max_odd, snapshot_generated_at):
    rows = []

    for market in markets:
        event_id = str(market.get("eventId", "")).strip()
        market_id = str(market.get("marketId", "")).strip()
        key = (event_id, market_id)

        if key not in watchlist_map:
            continue

        if event_id not in cuotas_map:
            continue

        runners = market.get("runners", {})
        if not isinstance(runners, dict):
            continue

        valid = []
        for selection_id, runner in runners.items():
            odd = pd.to_numeric(runner.get("best_back_odds"), errors="coerce")
            if pd.isna(odd):
                continue
            if odd < min_odd or odd > max_odd:
                continue
            valid.append((str(selection_id), float(odd), runner))

        if not valid:
            continue

        sorted_odds = sorted([odd for _, odd, _ in valid])

        for selection_id, odd, runner in valid:
            rows.append({
                "liga": market.get("liga", watchlist_map[key].get("Liga", "-")),
                "ts_pe": snapshot_generated_at,
                "snapshot_ts": snapshot_generated_at,
                "event_id": event_id,
                "event_name": market.get("eventName", watchlist_map[key].get("eventName", "-")),
                "market_id": market_id,
                "market_type": str(runner.get("selection", "")).upper().strip(),
                "selection_id": selection_id,
                "selection_name": runner.get("name", f"SEL_{selection_id}"),
                "odd": odd,
                "pressure": pd.to_numeric(runner.get("blpr"), errors="coerce"),
                "spread": pd.to_numeric(runner.get("spread"), errors="coerce"),
                "tv_runner": pd.to_numeric(runner.get("tv_runner"), errors="coerce"),
                "rank_odds": sorted_odds.index(odd) + 1,
                "start_pe": market.get("start_pe", ""),
            })

    return rows

# ============================================
# PREV ROW SELECTION
# ============================================
def same_snapshot_as_history(cur: dict, hist_row: dict) -> bool:
    cur_ts = str(cur.get("snapshot_ts", "")).strip()
    hist_ts = str(hist_row.get("ts_pe", "")).strip()

    cur_odd = pd.to_numeric(cur.get("odd"), errors="coerce")
    hist_odd = pd.to_numeric(hist_row.get("best_back_odds"), errors="coerce")
    if pd.isna(hist_odd):
        hist_odd = pd.to_numeric(hist_row.get("odd"), errors="coerce")

    if cur_ts and hist_ts and cur_ts == hist_ts:
        return True

    if pd.notna(cur_odd) and pd.notna(hist_odd):
        if abs(float(cur_odd) - float(hist_odd)) < 1e-9:
            cur_dt = parse_iso_dt(cur_ts)
            hist_dt = parse_iso_dt(hist_ts)
            if cur_dt and hist_dt and abs((cur_dt - hist_dt).total_seconds()) <= 2:
                return True

    return False

def pick_prev_rows(cur: dict, history_rows: list):
    if len(history_rows) < 2:
        return None, None

    rows = list(history_rows)

    if len(rows) >= 3 and same_snapshot_as_history(cur, rows[-1]):
        return rows[-2], rows[-3]

    if len(rows) >= 2:
        return rows[-1], rows[-2]

    return None, None

# ============================================
# FEATURES
# ============================================
def build_feature_rows(snapshot_rows, index_rows):
    out = []

    for cur in snapshot_rows:
        key = f"{cur['event_id']}|{cur['market_id']}|{cur['selection_id']}"
        hist = index_rows.get(key, [])

        if len(hist) < 2:
            continue

        p1, p2 = pick_prev_rows(cur, hist)
        if p1 is None or p2 is None:
            continue

        p1_odd = pd.to_numeric(p1.get("best_back_odds", p1.get("odd")), errors="coerce")
        p2_odd = pd.to_numeric(p2.get("best_back_odds", p2.get("odd")), errors="coerce")
        p1_pressure = pd.to_numeric(p1.get("blpr", p1.get("pressure")), errors="coerce")
        p2_pressure = pd.to_numeric(p2.get("blpr", p2.get("pressure")), errors="coerce")
        p1_tv = pd.to_numeric(p1.get("tv_runner"), errors="coerce")
        p2_tv = pd.to_numeric(p2.get("tv_runner"), errors="coerce")

        if any(pd.isna(x) for x in [p1_odd, p2_odd, p1_pressure, p1_tv, p2_tv]):
            continue

        d1 = cur["odd"] - p1_odd
        d2 = p1_odd - p2_odd
        acceleration = d1 - d2

        tv1 = cur["tv_runner"] - p1_tv
        tv2 = p1_tv - p2_tv
        tv_acceleration = tv1 - tv2

        pressure_ratio = safe_div(cur["pressure"], p1_pressure)

        drop1 = pct_drop(p1_odd, cur["odd"])
        drop2 = pct_drop(p2_odd, cur["odd"])
        drop_velocity = None
        if drop1 is not None and drop2 is not None:
            drop_velocity = drop1 - drop2

        out.append({
            "liga": cur["liga"],
            "ts_pe": cur["ts_pe"],
            "start_pe": cur["start_pe"],
            "event_id": cur["event_id"],
            "event_name": cur["event_name"],
            "market_id": cur["market_id"],
            "market_type": cur["market_type"],
            "selection_id": cur["selection_id"],
            "selection_name": cur["selection_name"],
            "odd": cur["odd"],
            "pressure": cur["pressure"],
            "spread": cur["spread"],
            "acceleration": acceleration,
            "tv_acceleration": tv_acceleration,
            "pressure_ratio": pressure_ratio,
            "drop_velocity": drop_velocity,
            "rank_odds": cur["rank_odds"],
        })

    return out

# ============================================
# MAIN
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

    watchlist_map = load_watchlist()
    cuotas_map = load_cuotas()
    snapshot_markets, snapshot_generated_at = load_snapshot()
    index_rows = load_index()

    if not watchlist_map:
        print("⚠️ Watchlist vacía")
        return

    if not snapshot_markets:
        print("⚠️ Snapshot vacío")
        return

    if not snapshot_generated_at:
        snapshot_generated_at = now_pe_str()

    bundle = joblib.load(MODEL_FILE)
    model = bundle["model"]
    features = bundle["features"]

    snapshot_rows = build_active_snapshot_rows(
        snapshot_markets,
        watchlist_map=watchlist_map,
        cuotas_map=cuotas_map,
        min_odd=min_odd,
        max_odd=max_odd,
        snapshot_generated_at=snapshot_generated_at
    )

    if not snapshot_rows:
        print("⚠️ No hay selecciones snapshot válidas")
        return

    feature_rows = build_feature_rows(snapshot_rows, index_rows)
    if not feature_rows:
        print("⚠️ No se pudieron construir features")
        return

    score_df = pd.DataFrame(feature_rows)
    score_df = score_df.dropna(subset=features).copy()

    if score_df.empty:
        print("⚠️ No quedaron filas válidas tras dropna(features)")
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

    score_df["alert_key"] = score_df.apply(build_alert_key, axis=1)
    score_df = score_df.sort_values(
        ["proba_fall", "tv_acceleration", "acceleration", "event_name"],
        ascending=[False, False, False, True]
    ).reset_index(drop=True)

    score_df.to_csv(OUTPUT_FILE, index=False)

    state = load_state(STATE_FILE)
    sent_keys = set(state.get("sent_keys", []))

    new_alerts = score_df[~score_df["alert_key"].isin(sent_keys)].copy()

    print(f"📊 Snapshot rows activas: {len(snapshot_rows)}")
    print(f"📊 Features válidas: {len(feature_rows)}")
    print(f"📊 Alertas operables actuales: {len(score_df)}")
    print(f"🆕 Alertas nuevas a enviar: {len(new_alerts)}")

    if new_alerts.empty:
        print("✅ No hay alertas nuevas")
        return

    sent_now = 0

    for row in new_alerts.itertuples(index=False):
        match_data = cuotas_map.get(str(row.event_id))
        if not match_data:
            print(f"⚠️ Skip sin cuotas.json: {row.event_id}")
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