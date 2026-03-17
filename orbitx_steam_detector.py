import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


# ==========================================================
# CONFIG
# ==========================================================
BASE_DIR = Path("/root/proyectos/Mancorabet")

# SNAPSHOT REAL DE ORBITX
ORBITX_FILE = Path("/root/proyectos/Mancorabet/Monitor_Orbitx/data/snapshot.json")

# ARCHIVO DE ESTADO DEL DETECTOR
STATE_FILE = Path("/root/proyectos/Mancorabet/Monitor_Orbitx/data/orbitx_steam_state.json")

CHECK_INTERVAL = int(os.getenv("ORBITX_STEAM_INTERVAL_SEC", "60"))
HTTP_TIMEOUT = int(os.getenv("ORBITX_STEAM_HTTP_TIMEOUT", "20"))
HISTORY_POINTS = int(os.getenv("ORBITX_STEAM_HISTORY_POINTS", "8"))

TELEGRAM_BOT_TOKEN = os.getenv("SMART_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS = [
    x.strip()
    for x in [
        os.getenv("SMART_BOT_CHAT_ID"),
        os.getenv("SMART_BOT_CHAT_ID_2"),
        os.getenv("SMART_BOT_CHAT_ID_3"),
    ]
    if x and x.strip()
]

EXCLUDE_LIVE = os.getenv("ORBITX_STEAM_EXCLUDE_LIVE", "1") == "1"

# =========================
# UMBRALES DETECTOR POTENTE
# =========================
PRESSURE_RATIO_MAX = float(os.getenv("ORBITX_STEAM_PRESSURE_RATIO_MAX", "0.70"))
BEST_BACK_AMT_MAX = float(os.getenv("ORBITX_STEAM_BEST_BACK_AMT_MAX", "50"))
SPREAD_PCT_MIN = float(os.getenv("ORBITX_STEAM_SPREAD_PCT_MIN", "1.0"))
SPREAD_PCT_MAX = float(os.getenv("ORBITX_STEAM_SPREAD_PCT_MAX", "2.5"))

DROP_1M_MIN_PCT = float(os.getenv("ORBITX_STEAM_DROP_1M_MIN_PCT", "0.40"))
DROP_3M_MIN_PCT = float(os.getenv("ORBITX_STEAM_DROP_3M_MIN_PCT", "0.80"))
TV_RUNNER_DELTA_3M_MIN = float(os.getenv("ORBITX_STEAM_TV_DELTA_3M_MIN", "80"))
REBOUND_1M_BLOCK_PCT = float(os.getenv("ORBITX_STEAM_REBOUND_1M_BLOCK_PCT", "0.35"))

ALERT_SCORE_MIN = int(os.getenv("ORBITX_STEAM_ALERT_SCORE_MIN", "4"))
ALERT_SCORE_EXTREME = int(os.getenv("ORBITX_STEAM_ALERT_SCORE_EXTREME", "6"))


# ==========================================================
# HELPERS
# ==========================================================
def now_dt() -> datetime:
    return datetime.now()


def now_str() -> str:
    return now_dt().strftime("%Y-%m-%d %H:%M:%S")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def odds_drop_pct(old: Optional[float], new: Optional[float]) -> Optional[float]:
    """
    Positivo = la cuota bajó
    """
    if old is None or new is None or old <= 0:
        return None
    return ((old - new) / old) * 100.0


def fmt_num(x: Optional[float], ndigits: int = 2) -> str:
    if x is None:
        return "-"
    return f"{x:.{ndigits}f}"


def send_telegram_message(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: Falta TELEGRAM_BOT_TOKEN o SMART_BOT_TOKEN.")
        return

    if not TELEGRAM_CHAT_IDS:
        print("ERROR: No hay SMART_BOT_CHAT_ID configurados.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            r = requests.post(
                url,
                data={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": True,
                },
                timeout=HTTP_TIMEOUT,
            )
            r.raise_for_status()
        except Exception as e:
            print(f"ERROR enviando Telegram a {chat_id}: {e}")


def normalize_orbitx_snapshot(raw: Any) -> List[Dict[str, Any]]:
    """
    Soporta estas estructuras:
    - lista directa
    - {"events": [...]}
    - {"data": [...]}
    - {"items": [...]}
    - {"snapshots": [...]}
    - {"markets": [...]}   <-- TU CASO
    - dict que ya parece evento
    - dict con values que parecen eventos
    """
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]

    if isinstance(raw, dict):
        for key in ("markets", "events", "data", "items", "snapshots"):
            value = raw.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]

        if "eventId" in raw and "runners" in raw:
            return [raw]

        values = list(raw.values())

        event_like = [
            v for v in values
            if isinstance(v, dict) and ("eventId" in v or "runners" in v)
        ]
        if event_like:
            return event_like

        collected = []
        for v in values:
            if isinstance(v, list):
                collected.extend([x for x in v if isinstance(x, dict)])
        if collected:
            return collected

    raise ValueError("No se pudo interpretar snapshot.json")


def is_live_event(event: Dict[str, Any]) -> bool:
    if not EXCLUDE_LIVE:
        return False
    possible_flags = [
        event.get("is_live"),
        event.get("inplay"),
        event.get("in_play"),
        event.get("live"),
        event.get("isLive"),
    ]
    return any(bool(x) for x in possible_flags)


def selection_label(selection: str) -> str:
    selection = selection.upper().strip()
    return {
        "HOME": "LOCAL",
        "DRAW": "EMPATE",
        "AWAY": "VISITA",
    }.get(selection, selection)


def load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {"history": {}, "active_alerts": {}}
    try:
        data = load_json(STATE_FILE)
        if not isinstance(data, dict):
            return {"history": {}, "active_alerts": {}}
        if "history" not in data or not isinstance(data["history"], dict):
            data["history"] = {}
        if "active_alerts" not in data or not isinstance(data["active_alerts"], dict):
            data["active_alerts"] = {}
        return data
    except Exception:
        return {"history": {}, "active_alerts": {}}


def build_signature(obs: Dict[str, Any], signal: Dict[str, Any]) -> str:
    return "|".join(
        [
            signal.get("level", "-"),
            str(signal.get("score", 0)),
            str(round(obs.get("best_back_odds", 0.0), 4)),
            str(round(obs.get("pressure_ratio", 0.0), 4)),
            str(round(signal.get("drop_1m_pct", 0.0) or 0.0, 4)),
            str(round(signal.get("drop_3m_pct", 0.0) or 0.0, 4)),
            str(round(signal.get("tv_delta_3m", 0.0) or 0.0, 2)),
            str(signal.get("price_move_confirmed", False)),
        ]
    )


# ==========================================================
# EXTRACCIÓN DE OBSERVACIONES
# ==========================================================
def extract_observations(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    observations: List[Dict[str, Any]] = []

    for event in events:
        if not isinstance(event, dict):
            continue

        if is_live_event(event):
            continue

        event_id = str(event.get("eventId", "")).strip()
        if not event_id:
            continue

        liga = event.get("liga") or "-"
        event_name = event.get("eventName") or "-"
        market_id = str(event.get("marketId", "")).strip()
        start_utc = event.get("start_utc") or "-"
        start_pe = event.get("start_pe") or "-"
        runners = event.get("runners") or {}

        if not isinstance(runners, dict):
            continue

        for _, runner in runners.items():
            if not isinstance(runner, dict):
                continue

            selection = str(runner.get("selection", "")).upper().strip()
            if selection not in {"HOME", "DRAW", "AWAY"}:
                continue

            locked = bool(runner.get("locked", False))
            best_back_odds = safe_float(runner.get("best_back_odds"))
            best_back_amt = safe_float(runner.get("best_back_amt"))
            best_lay_odds = safe_float(runner.get("best_lay_odds"))
            best_lay_amt = safe_float(runner.get("best_lay_amt"))
            sum_back_top3 = safe_float(runner.get("sum_back_top3"))
            sum_lay_top3 = safe_float(runner.get("sum_lay_top3"))
            tv_runner = safe_float(runner.get("tv_runner"))
            spread_abs = safe_float(runner.get("spread"))

            if locked:
                continue
            if best_back_odds is None or best_back_odds <= 1.0:
                continue

            if best_lay_odds is not None and best_lay_odds > 0:
                spread_pct = ((best_lay_odds - best_back_odds) / best_back_odds) * 100.0
            elif spread_abs is not None:
                spread_pct = (spread_abs / best_back_odds) * 100.0
            else:
                spread_pct = None

            if sum_back_top3 is not None and sum_lay_top3 is not None and sum_lay_top3 > 0:
                pressure_ratio = sum_back_top3 / sum_lay_top3
            else:
                pressure_ratio = None

            observations.append(
                {
                    "key": f"{event_id}_{selection.lower()}",
                    "eventId": event_id,
                    "marketId": market_id,
                    "liga": liga,
                    "eventName": event_name,
                    "selection": selection,
                    "selection_label": selection_label(selection),
                    "start_utc": start_utc,
                    "start_pe": start_pe,
                    "best_back_odds": best_back_odds,
                    "best_back_amt": best_back_amt,
                    "best_lay_odds": best_lay_odds,
                    "best_lay_amt": best_lay_amt,
                    "sum_back_top3": sum_back_top3,
                    "sum_lay_top3": sum_lay_top3,
                    "pressure_ratio": pressure_ratio,
                    "tv_runner": tv_runner,
                    "spread_pct": spread_pct,
                    "locked": locked,
                    "observed_at": now_str(),
                }
            )

    return observations


# ==========================================================
# DETECTOR POTENTE
# ==========================================================
def compute_signal(history: List[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    prev1 = history[-1] if len(history) >= 1 else None
    prev2 = history[-2] if len(history) >= 2 else None
    prev3 = history[-3] if len(history) >= 3 else None

    current_odd = current.get("best_back_odds")
    current_tv = current.get("tv_runner")
    current_pressure = current.get("pressure_ratio")
    current_spread = current.get("spread_pct")
    current_back_amt = current.get("best_back_amt")

    score = 0
    reasons: List[str] = []

    # =========================
    # FILTROS ESTRUCTURALES
    # =========================
    pressure_ok = current_pressure is not None and current_pressure <= PRESSURE_RATIO_MAX
    if pressure_ok:
        score += 2
        reasons.append(f"pressure_ratio <= {PRESSURE_RATIO_MAX}")

    back_amt_ok = current_back_amt is not None and current_back_amt <= BEST_BACK_AMT_MAX
    if back_amt_ok:
        score += 1
        reasons.append(f"best_back_amt <= {BEST_BACK_AMT_MAX}")

    spread_ok = (
        current_spread is not None and
        SPREAD_PCT_MIN <= current_spread <= SPREAD_PCT_MAX
    )
    if spread_ok:
        score += 1
        reasons.append(f"{SPREAD_PCT_MIN}% <= spread_pct <= {SPREAD_PCT_MAX}%")

    # =========================
    # VELOCIDAD / CONTINUIDAD
    # =========================
    drop_1m_pct = None
    drop_3m_pct = None
    tv_delta_3m = None
    rebound_1m_pct = None
    persist_down_3 = False

    if prev1:
        drop_1m_pct = odds_drop_pct(prev1.get("best_back_odds"), current_odd)

        if prev1.get("best_back_odds") is not None and current_odd is not None and current_odd > prev1.get("best_back_odds"):
            rebound_1m_pct = ((current_odd - prev1.get("best_back_odds")) / prev1.get("best_back_odds")) * 100.0

    if prev3:
        drop_3m_pct = odds_drop_pct(prev3.get("best_back_odds"), current_odd)
        if prev3.get("tv_runner") is not None and current_tv is not None:
            tv_delta_3m = current_tv - prev3.get("tv_runner")

    if prev2 and prev1:
        odd2 = prev2.get("best_back_odds")
        odd1 = prev1.get("best_back_odds")
        if odd2 is not None and odd1 is not None and current_odd is not None:
            if odd2 > odd1 > current_odd:
                persist_down_3 = True

    # Precio moviéndose: obligatorio
    price_move_confirmed = any([
        drop_1m_pct is not None and drop_1m_pct >= DROP_1M_MIN_PCT,
        drop_3m_pct is not None and drop_3m_pct >= DROP_3M_MIN_PCT,
        persist_down_3,
    ])

    # Puntos por movimiento
    if drop_1m_pct is not None and drop_1m_pct >= DROP_1M_MIN_PCT:
        score += 1
        reasons.append(f"drop_1m >= {DROP_1M_MIN_PCT}%")

    if drop_3m_pct is not None and drop_3m_pct >= DROP_3M_MIN_PCT:
        score += 2
        reasons.append(f"drop_3m >= {DROP_3M_MIN_PCT}%")

    # TV solo suma, pero ya no confirma por sí solo
    if tv_delta_3m is not None and tv_delta_3m >= TV_RUNNER_DELTA_3M_MIN:
        score += 1
        reasons.append(f"tv_delta_3m >= {TV_RUNNER_DELTA_3M_MIN}")

    if persist_down_3:
        score += 1
        reasons.append("persistencia_bajista_3_puntos")

    blocked_by_rebound = False
    if rebound_1m_pct is not None and rebound_1m_pct >= REBOUND_1M_BLOCK_PCT:
        score -= 2
        blocked_by_rebound = True
        reasons.append(f"rebote_1m >= {REBOUND_1M_BLOCK_PCT}%")

    # Confirmación fuerte para EXTREMA
    strong_movement_confirmed = any([
        drop_3m_pct is not None and drop_3m_pct >= DROP_3M_MIN_PCT,
        (
            drop_1m_pct is not None and drop_1m_pct >= DROP_1M_MIN_PCT and
            persist_down_3
        ),
    ])

    level = None
    if not blocked_by_rebound and score >= ALERT_SCORE_EXTREME and strong_movement_confirmed and price_move_confirmed:
        level = "EXTREMA"
    elif not blocked_by_rebound and score >= ALERT_SCORE_MIN and price_move_confirmed:
        level = "FUERTE"

    return {
        "score": score,
        "level": level,
        "reasons": reasons,
        "drop_1m_pct": drop_1m_pct,
        "drop_3m_pct": drop_3m_pct,
        "tv_delta_3m": tv_delta_3m,
        "rebound_1m_pct": rebound_1m_pct,
        "persist_down_3": persist_down_3,
        "pressure_ok": pressure_ok,
        "back_amt_ok": back_amt_ok,
        "spread_ok": spread_ok,
        "blocked_by_rebound": blocked_by_rebound,
        "price_move_confirmed": price_move_confirmed,
        "strong_movement_confirmed": strong_movement_confirmed,
    }


def build_alert_message(obs: Dict[str, Any], signal: Dict[str, Any]) -> str:
    emoji = "🔴" if signal["level"] == "EXTREMA" else "🟠"

    lines = [
        f"{emoji} STEAM MOVE ORBITX {signal['level']}",
        "",
        f"{obs['eventName']}",
        f"Liga: {obs['liga']}",
        f"Mercado: {obs['selection_label']}",
        f"Fecha: {obs['start_utc']} | {obs['start_pe']}",
        "",
        "DATOS ACTUALES",
        f"• Best Back: {fmt_num(obs.get('best_back_odds'))}",
        f"• Best Back Amt: {fmt_num(obs.get('best_back_amt'))}",
        f"• Best Lay: {fmt_num(obs.get('best_lay_odds'))}",
        f"• Spread %: {fmt_num(obs.get('spread_pct'))}%",
        f"• Pressure Ratio: {fmt_num(obs.get('pressure_ratio'), 3)}",
        f"• TV Runner: {fmt_num(obs.get('tv_runner'))}",
        "",
        "MOVIMIENTO",
        f"• Caída 1m: {fmt_num(signal.get('drop_1m_pct'))}%",
        f"• Caída 3m: {fmt_num(signal.get('drop_3m_pct'))}%",
        f"• TV Δ 3m: {fmt_num(signal.get('tv_delta_3m'))}",
        f"• Persistencia 3: {'Sí' if signal.get('persist_down_3') else 'No'}",
    ]

    if signal.get("rebound_1m_pct") is not None:
        lines.append(f"• Rebote 1m: {fmt_num(signal.get('rebound_1m_pct'))}%")

    lines.extend([
        "",
        f"• Score: {signal['score']}",
        "",
        "TRIGGERS",
    ])

    for reason in signal["reasons"]:
        lines.append(f"• {reason}")

    lines.extend([
        "",
        "Lectura:",
        "• Ventana probable: 2 a 5 min",
        "• Si es EXTREMA, revisar de inmediato",
        "",
        f"⏱️ {now_str()}",
    ])

    return "\n".join(lines)


# ==========================================================
# PROCESO
# ==========================================================
def process_once() -> int:
    if not ORBITX_FILE.exists():
        print(f"ERROR: No existe {ORBITX_FILE}")
        return 1

    raw = load_json(ORBITX_FILE)
    events = normalize_orbitx_snapshot(raw)
    observations = extract_observations(events)

    state = load_state()
    history_store: Dict[str, List[Dict[str, Any]]] = state.get("history", {})
    active_alerts: Dict[str, str] = state.get("active_alerts", {})

    next_history: Dict[str, List[Dict[str, Any]]] = {}
    next_active_alerts: Dict[str, str] = {}

    alerts_sent = 0
    processed = 0

    for obs in observations:
        key = obs["key"]
        old_hist = history_store.get(key, [])
        if not isinstance(old_hist, list):
            old_hist = []

        signal = compute_signal(old_hist, obs)

        new_hist = old_hist + [obs]
        if len(new_hist) > HISTORY_POINTS:
            new_hist = new_hist[-HISTORY_POINTS:]
        next_history[key] = new_hist

        processed += 1

        if signal["level"] in {"FUERTE", "EXTREMA"}:
            signature = build_signature(obs, signal)
            next_active_alerts[key] = signature

            if active_alerts.get(key) != signature:
                msg = build_alert_message(obs, signal)
                send_telegram_message(msg)
                alerts_sent += 1
                print(
                    f"[ALERTA {signal['level']}] {key} | "
                    f"odd={obs.get('best_back_odds')} | "
                    f"score={signal['score']}"
                )

    save_json(
        STATE_FILE,
        {
            "history": next_history,
            "active_alerts": next_active_alerts,
        },
    )

    print(f"{now_str()} | procesados={processed} | alertas={alerts_sent}")
    return 0


def main() -> int:
    print(
        f"Iniciando orbitx_steam_detector.py | interval={CHECK_INTERVAL}s | "
        f"score_min={ALERT_SCORE_MIN} | extreme={ALERT_SCORE_EXTREME}"
    )

    while True:
        try:
            process_once()
        except Exception as e:
            print(f"ERROR en ciclo principal: {e}")
            import traceback
            traceback.print_exc()
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Detenido manualmente.")
        sys.exit(0)