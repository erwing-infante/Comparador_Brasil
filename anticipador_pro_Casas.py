import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests


# ==========================================================
# CONFIG
# ==========================================================
SNAPSHOT_FILE = Path("/root/proyectos/Mancorabet/Monitor_Orbitx/data/snapshot.json")
CUOTAS_FILE = Path("/root/proyectos/Mancorabet/data/cuotas.json")
STATE_FILE = Path("/root/proyectos/Mancorabet/Monitor_Orbitx/data/anticipador_pro_casas_state.json")

INTERVAL = int(os.getenv("ANTICIPADOR_PRO_CASAS_INTERVAL_SEC", "60"))
HTTP_TIMEOUT = int(os.getenv("ANTICIPADOR_PRO_CASAS_HTTP_TIMEOUT", "20"))
HISTORY_POINTS = int(os.getenv("ANTICIPADOR_PRO_CASAS_HISTORY_POINTS", "12"))

TZ = ZoneInfo("America/Lima")

TOKEN = os.getenv("SMART_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_IDS = [
    x.strip()
    for x in [
        os.getenv("SMART_BOT_CHAT_ID"),
        os.getenv("SMART_BOT_CHAT_ID_2"),
        os.getenv("SMART_BOT_CHAT_ID_3"),
    ]
    if x and x.strip()
]

EXCLUDE_LIVE = os.getenv("ANTICIPADOR_PRO_CASAS_EXCLUDE_LIVE", "1") == "1"

# ==========================================================
# CRUCE CASAS
# ==========================================================
CASAS_PRIORIDAD = [
    "apuesta total",
    "te apuesto",
    "stake",
    "bet365",
]

MIN_EDGE_PCT = float(os.getenv("ANTICIPADOR_PRO_CASAS_MIN_EDGE_PCT", "2.0"))

# ==========================================================
# MOTOR MEDIAS
# ==========================================================
MEDIA_MIN_ODD = float(os.getenv("ANTICIPADOR_PRO_MEDIA_MIN_ODD", "2.20"))
MEDIA_MAX_ODD = float(os.getenv("ANTICIPADOR_PRO_MEDIA_MAX_ODD", "4.50"))
MEDIA_COOLDOWN_MIN = float(os.getenv("ANTICIPADOR_PRO_MEDIA_COOLDOWN_MIN", "4"))

MEDIA_REBOUND_BLOCK = float(os.getenv("ANTICIPADOR_PRO_MEDIA_REBOUND_BLOCK", "0.35"))
MEDIA_BACK_GROWTH_BLOCK = float(os.getenv("ANTICIPADOR_PRO_MEDIA_BACK_GROWTH_BLOCK", "18"))
MEDIA_LAY_RELOAD_BLOCK = float(os.getenv("ANTICIPADOR_PRO_MEDIA_LAY_RELOAD_BLOCK", "12"))

MEDIA_SPREAD_MAX = float(os.getenv("ANTICIPADOR_PRO_MEDIA_SPREAD_MAX", "2.00"))
MEDIA_PRESSURE_MAX = float(os.getenv("ANTICIPADOR_PRO_MEDIA_PRESSURE_MAX", "0.82"))
MEDIA_TV_MIN = float(os.getenv("ANTICIPADOR_PRO_MEDIA_TV_MIN", "280"))

MEDIA_DROP1_MIN = float(os.getenv("ANTICIPADOR_PRO_MEDIA_DROP1_MIN", "0.90"))
MEDIA_DROP2_MIN = float(os.getenv("ANTICIPADOR_PRO_MEDIA_DROP2_MIN", "1.25"))
MEDIA_DROP3_MIN = float(os.getenv("ANTICIPADOR_PRO_MEDIA_DROP3_MIN", "1.65"))

MEDIA_LAYDROP1_MIN = float(os.getenv("ANTICIPADOR_PRO_MEDIA_LAYDROP1_MIN", "14"))
MEDIA_LAYDROP3_MIN = float(os.getenv("ANTICIPADOR_PRO_MEDIA_LAYDROP3_MIN", "18"))
MEDIA_SPREAD_CLOSE1_MIN = float(os.getenv("ANTICIPADOR_PRO_MEDIA_SPREAD_CLOSE1_MIN", "9"))
MEDIA_SPREAD_CLOSE3_MIN = float(os.getenv("ANTICIPADOR_PRO_MEDIA_SPREAD_CLOSE3_MIN", "14"))
MEDIA_TV_DELTA2_MIN = float(os.getenv("ANTICIPADOR_PRO_MEDIA_TV_DELTA2_MIN", "125"))

MEDIA_SCORE_MIN = int(os.getenv("ANTICIPADOR_PRO_MEDIA_SCORE_MIN", "11"))

MEDIA_PREMIUM_SCORE = int(os.getenv("ANTICIPADOR_PRO_MEDIA_PREMIUM_SCORE", "14"))
MEDIA_GOOD_SCORE = int(os.getenv("ANTICIPADOR_PRO_MEDIA_GOOD_SCORE", "12"))

# ==========================================================
# MOTOR BAJAS (v10.2.1)
# ==========================================================
LOW_MIN_ODD = float(os.getenv("ANTICIPADOR_PRO_LOW_MIN_ODD", "1.35"))
LOW_MAX_ODD = float(os.getenv("ANTICIPADOR_PRO_LOW_MAX_ODD", "2.20"))
LOW_COOLDOWN_MIN = float(os.getenv("ANTICIPADOR_PRO_LOW_COOLDOWN_MIN", "2.5"))

LOW_MIN_DROP1 = float(os.getenv("ANTICIPADOR_PRO_LOW_MIN_DROP1", "0.15"))
LOW_MAX_DROP1 = float(os.getenv("ANTICIPADOR_PRO_LOW_MAX_DROP1", "0.48"))
LOW_MIN_DROP2 = float(os.getenv("ANTICIPADOR_PRO_LOW_MIN_DROP2", "0.30"))
LOW_MAX_DROP2 = float(os.getenv("ANTICIPADOR_PRO_LOW_MAX_DROP2", "0.90"))
LOW_MIN_CONTINUITY = float(os.getenv("ANTICIPADOR_PRO_LOW_MIN_CONTINUITY", "0.04"))

LOW_REBOUND_BLOCK = float(os.getenv("ANTICIPADOR_PRO_LOW_REBOUND_BLOCK", "0.22"))
LOW_MIN_LAY = float(os.getenv("ANTICIPADOR_PRO_LOW_MIN_LAY", "3"))
LOW_MIN_BACK = float(os.getenv("ANTICIPADOR_PRO_LOW_MIN_BACK", "0.5"))
LOW_MIN_REAL_MOVE = float(os.getenv("ANTICIPADOR_PRO_LOW_MIN_REAL_MOVE", "0.12"))
LOW_MAX_ACCEL = float(os.getenv("ANTICIPADOR_PRO_LOW_MAX_ACCEL", "0.75"))

LOW_PREMIUM_DROP1 = float(os.getenv("ANTICIPADOR_PRO_LOW_PREMIUM_DROP1", "0.28"))
LOW_PREMIUM_DROP2 = float(os.getenv("ANTICIPADOR_PRO_LOW_PREMIUM_DROP2", "0.55"))
LOW_GOOD_DROP1 = float(os.getenv("ANTICIPADOR_PRO_LOW_GOOD_DROP1", "0.20"))
LOW_GOOD_DROP2 = float(os.getenv("ANTICIPADOR_PRO_LOW_GOOD_DROP2", "0.40"))


# ==========================================================
# HELPERS
# ==========================================================
def now_dt() -> datetime:
    return datetime.now(TZ)


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
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


def pct_drop(old: Optional[float], new: Optional[float]) -> Optional[float]:
    if old in (None, 0) or new is None:
        return None
    return ((old - new) / old) * 100.0


def pct_up(old: Optional[float], new: Optional[float]) -> Optional[float]:
    if old in (None, 0) or new is None:
        return None
    return ((new - old) / old) * 100.0


def edge_pct(orbitx_odd: float, house_odd: float) -> float:
    if orbitx_odd <= 0:
        return 0.0
    return ((house_odd - orbitx_odd) / orbitx_odd) * 100.0


def fmt_num(x: Optional[float], ndigits: int = 2) -> str:
    if x is None:
        return "-"
    return f"{x:.{ndigits}f}"


def normalize_casa_name(casa: str) -> str:
    casa = str(casa or "").strip().lower()
    alias = {
        "apuesta total": "apuesta total",
        "apuestatotal": "apuesta total",
        "apuesta_total": "apuesta total",
        "te apuesto": "te apuesto",
        "teapuesto": "te apuesto",
        "stake": "stake",
        "bet365": "bet365",
        "bet 365": "bet365",
    }
    return alias.get(casa, casa)


def selection_label(selection: str) -> str:
    selection = str(selection).upper().strip()
    return {"HOME": "LOCAL", "DRAW": "EMPATE", "AWAY": "VISITA"}.get(selection, selection)


def selection_to_cuota_field(selection: str) -> Optional[str]:
    selection = str(selection).upper().strip()
    return {
        "HOME": "Cuota Local",
        "DRAW": "Cuota Empate",
        "AWAY": "Cuota Visita",
    }.get(selection)


def load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {"history": {}, "alerts": {}}
    try:
        data = load_json(STATE_FILE)
        if not isinstance(data, dict):
            return {"history": {}, "alerts": {}}
        if "history" not in data or not isinstance(data["history"], dict):
            data["history"] = {}
        if "alerts" not in data or not isinstance(data["alerts"], dict):
            data["alerts"] = {}
        return data
    except Exception:
        return {"history": {}, "alerts": {}}


def send_telegram_message(text: str) -> None:
    if not TOKEN or not CHAT_IDS:
        print(text)
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    for chat_id in CHAT_IDS:
        try:
            r = requests.post(
                url,
                data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
                timeout=HTTP_TIMEOUT,
            )
            r.raise_for_status()
        except Exception as e:
            print(f"ERROR enviando Telegram a {chat_id}: {e}")


# ==========================================================
# SNAPSHOT
# ==========================================================
def normalize_snapshot(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]

    if isinstance(raw, dict):
        for key in ("markets", "events", "data", "items", "snapshots"):
            value = raw.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]

        if "eventId" in raw and "runners" in raw:
            return [raw]

        vals = list(raw.values())
        out = []
        for v in vals:
            if isinstance(v, dict) and ("eventId" in v or "runners" in v):
                out.append(v)
            elif isinstance(v, list):
                out.extend([x for x in v if isinstance(x, dict)])
        if out:
            return out

    raise ValueError("No se pudo interpretar snapshot.json")


def is_live_event(event: Dict[str, Any]) -> bool:
    if not EXCLUDE_LIVE:
        return False
    flags = [
        event.get("is_live"),
        event.get("inplay"),
        event.get("in_play"),
        event.get("live"),
        event.get("isLive"),
    ]
    return any(bool(x) for x in flags)


def parse_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    parsed = []

    for event in events:
        if not isinstance(event, dict):
            continue
        if is_live_event(event):
            continue

        event_id = str(event.get("eventId", "")).strip()
        if not event_id:
            continue

        runners = event.get("runners") or {}
        if not isinstance(runners, dict):
            continue

        event_rows = []
        for runner in runners.values():
            if not isinstance(runner, dict):
                continue

            selection = str(runner.get("selection", "")).upper().strip()
            if selection not in {"HOME", "DRAW", "AWAY"}:
                continue

            odd = safe_float(runner.get("best_back_odds"))
            lay = safe_float(runner.get("best_lay_odds"))
            tv = safe_float(runner.get("tv_runner"))
            back_amt = safe_float(runner.get("best_back_amt"))
            lay_amt = safe_float(runner.get("best_lay_amt"))
            sum_back_top3 = safe_float(runner.get("sum_back_top3"))
            sum_lay_top3 = safe_float(runner.get("sum_lay_top3"))
            locked = bool(runner.get("locked", False))

            if locked or odd is None or odd <= 1.0:
                continue

            spread = ((lay - odd) / odd) * 100.0 if lay not in (None, 0) else None
            pressure = (sum_back_top3 / sum_lay_top3) if (sum_back_top3 is not None and sum_lay_top3 not in (None, 0)) else None

            event_rows.append(
                {
                    "eventId": event_id,
                    "event": event.get("eventName") or "-",
                    "liga": event.get("liga") or "-",
                    "start_pe": event.get("start_pe") or "-",
                    "selection": selection,
                    "selection_label": selection_label(selection),
                    "odd": odd,
                    "lay": lay,
                    "spread": spread,
                    "tv": tv,
                    "back_amt": back_amt,
                    "lay_amt": lay_amt,
                    "pressure": pressure,
                    "key": f"{event_id}_{selection}",
                }
            )

        if event_rows:
            parsed.append(
                {
                    "eventId": event_id,
                    "event": event.get("eventName") or "-",
                    "liga": event.get("liga") or "-",
                    "start_pe": event.get("start_pe") or "-",
                    "runners": event_rows,
                }
            )

    return parsed


def get_non_draw_favorite(runners: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    non_draw = [r for r in runners if r["selection"] in {"HOME", "AWAY"}]
    if not non_draw:
        return None
    return min(non_draw, key=lambda r: r["odd"])


# ==========================================================
# CUOTAS.JSON por eventId
# ==========================================================
def parse_cuotas_json(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in ("data", "items", "rows", "cuotas"):
            v = raw.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    return []


def build_cuotas_index_by_eventid(cuotas_rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    index: Dict[str, List[Dict[str, Any]]] = {}

    for row in cuotas_rows:
        event_id = str(
            row.get("EventId")
            or row.get("eventId")
            or row.get("event_id")
            or ""
        ).strip()

        if not event_id:
            continue

        item = {
            "Casa": normalize_casa_name(str(row.get("Casa") or row.get("casa") or "")),
            "Cuota Local": safe_float(row.get("Cuota Local") or row.get("cuota_local")),
            "Cuota Empate": safe_float(row.get("Cuota Empate") or row.get("cuota_empate")),
            "Cuota Visita": safe_float(row.get("Cuota Visita") or row.get("cuota_visita")),
            "Partido": row.get("Partido") or row.get("partido") or "",
            "Liga": row.get("Liga") or row.get("liga") or "",
            "Fecha": row.get("Fecha") or row.get("fecha") or "",
            "EventId": event_id,
        }

        index.setdefault(event_id, []).append(item)

    return index


def find_house_quotes_for_signal_by_eventid(
    cuotas_index: Dict[str, List[Dict[str, Any]]],
    event_id: str,
    selection: str,
) -> Dict[str, Any]:
    field = selection_to_cuota_field(selection)
    if not field:
        return {"priority_best": None, "overall_best": None, "houses_found": []}

    rows = cuotas_index.get(str(event_id), [])
    houses_found = []

    for row in rows:
        cuota = row.get(field)
        if cuota is None:
            continue

        houses_found.append(
            {
                "casa": row["Casa"],
                "odd": cuota,
                "partido": row.get("Partido"),
                "liga": row.get("Liga"),
                "fecha": row.get("Fecha"),
                "eventId": row.get("EventId"),
            }
        )

    if not houses_found:
        return {"priority_best": None, "overall_best": None, "houses_found": []}

    priority_best = None
    for casa_objetivo in CASAS_PRIORIDAD:
        opciones = [x for x in houses_found if x["casa"] == casa_objetivo]
        if opciones:
            priority_best = max(opciones, key=lambda x: x["odd"])
            break

    overall_best = max(houses_found, key=lambda x: x["odd"])

    return {
        "priority_best": priority_best,
        "overall_best": overall_best,
        "houses_found": houses_found,
    }


def value_still_available(
    orbitx_odd: float,
    quotes_info: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    priority_best = quotes_info.get("priority_best")
    overall_best = quotes_info.get("overall_best")

    if not priority_best and not overall_best:
        return None

    candidates = []
    if priority_best:
        candidates.append(("PRIORIDAD", priority_best))
    if overall_best:
        candidates.append(("GENERAL", overall_best))

    valid = []
    for source_type, q in candidates:
        if q["odd"] is None:
            continue
        e = edge_pct(orbitx_odd, q["odd"])
        if e >= MIN_EDGE_PCT:
            valid.append(
                {
                    "source_type": source_type,
                    "casa": q["casa"],
                    "odd": q["odd"],
                    "edge_pct": e,
                }
            )

    if not valid:
        return None

    valid.sort(key=lambda x: (0 if x["source_type"] == "PRIORIDAD" else 1, -x["odd"]))
    return valid[0]


# ==========================================================
# MÉTRICAS
# ==========================================================
def runner_metrics(hist: List[Dict[str, Any]], cur: Dict[str, Any]) -> Dict[str, Any]:
    p1 = hist[-1] if len(hist) >= 1 else None
    p2 = hist[-2] if len(hist) >= 2 else None
    p3 = hist[-3] if len(hist) >= 3 else None

    return {
        "drop1": pct_drop(p1["odd"], cur["odd"]) if p1 else None,
        "drop2": pct_drop(p2["odd"], cur["odd"]) if p2 else None,
        "drop3": pct_drop(p3["odd"], cur["odd"]) if p3 else None,
        "rebound1": pct_up(p1["odd"], cur["odd"]) if p1 and cur["odd"] > p1["odd"] else None,
        "laydrop1": pct_drop(p1["lay_amt"], cur["lay_amt"]) if p1 else None,
        "laydrop3": pct_drop(p3["lay_amt"], cur["lay_amt"]) if p3 else None,
        "spreadclose1": pct_drop(p1["spread"], cur["spread"]) if p1 and p1.get("spread") not in (None, 0) and cur.get("spread") is not None else None,
        "spreadclose3": pct_drop(p3["spread"], cur["spread"]) if p3 and p3.get("spread") not in (None, 0) and cur.get("spread") is not None else None,
        "back_growth1": pct_up(p1["back_amt"], cur["back_amt"]) if p1 else None,
        "tv_delta2": (cur["tv"] - p2["tv"]) if p2 and p2.get("tv") is not None and cur.get("tv") is not None else None,
        "persist2": bool(p2 and p1 and p2["odd"] >= p1["odd"] >= cur["odd"] and cur["odd"] < p2["odd"]),
    }


# ==========================================================
# CLASIFICACIÓN
# ==========================================================
def classify_media_quality(score: int, drop1: Optional[float], drop2: Optional[float], drop3: Optional[float]) -> str:
    d1 = drop1 or 0.0
    d2 = drop2 or 0.0
    d3 = drop3 or 0.0

    if score >= MEDIA_PREMIUM_SCORE and d1 >= 1.20 and d2 >= 1.60 and d3 >= 1.90:
        return "PREMIUM"
    if score >= MEDIA_GOOD_SCORE and d1 >= 0.95 and d2 >= 1.30:
        return "BUENA"
    return "NORMAL"


def classify_low_quality(setup: str, drop1: Optional[float], drop2: Optional[float]) -> str:
    d1 = drop1 or 0.0
    d2 = drop2 or 0.0

    if setup == "RUPTURA" and d1 >= LOW_PREMIUM_DROP1 and d2 >= LOW_PREMIUM_DROP2:
        return "PREMIUM"
    if d1 >= LOW_GOOD_DROP1 and d2 >= LOW_GOOD_DROP2:
        return "BUENA"
    return "NORMAL"


# ==========================================================
# DETECTORES
# ==========================================================
def detect_medias(cur: Dict[str, Any], hist: List[Dict[str, Any]], alerts_store: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not (MEDIA_MIN_ODD <= cur["odd"] <= MEDIA_MAX_ODD):
        return None
    if len(hist) < 3:
        return None

    m = runner_metrics(hist, cur)

    if m["rebound1"] is not None and m["rebound1"] >= MEDIA_REBOUND_BLOCK:
        return None
    if m["back_growth1"] is not None and m["back_growth1"] >= MEDIA_BACK_GROWTH_BLOCK:
        return None

    if len(hist) >= 3:
        p1 = hist[-1]
        p2 = hist[-2]
        if p2.get("lay_amt") and p1.get("lay_amt") and cur.get("lay_amt"):
            if p2["lay_amt"] > p1["lay_amt"] < cur["lay_amt"]:
                bounce = pct_up(p1["lay_amt"], cur["lay_amt"])
                if bounce is not None and bounce >= MEDIA_LAY_RELOAD_BLOCK:
                    return None

    score = 0

    if cur.get("spread") is not None and cur["spread"] <= MEDIA_SPREAD_MAX:
        score += 1
    if cur.get("pressure") is not None and cur["pressure"] <= MEDIA_PRESSURE_MAX:
        score += 1
    if cur.get("tv") is not None and cur["tv"] >= MEDIA_TV_MIN:
        score += 1
    if m["drop1"] is not None and m["drop1"] >= MEDIA_DROP1_MIN:
        score += 3
    if m["drop2"] is not None and m["drop2"] >= MEDIA_DROP2_MIN:
        score += 2
    if m["drop3"] is not None and m["drop3"] >= MEDIA_DROP3_MIN:
        score += 1
    if m["persist2"]:
        score += 2
    if m["laydrop1"] is not None and m["laydrop1"] >= MEDIA_LAYDROP1_MIN:
        score += 2
    if m["laydrop3"] is not None and m["laydrop3"] >= MEDIA_LAYDROP3_MIN:
        score += 1

    spread_ok = False
    if m["spreadclose1"] is not None and m["spreadclose1"] >= MEDIA_SPREAD_CLOSE1_MIN:
        spread_ok = True
    if m["spreadclose3"] is not None and m["spreadclose3"] >= MEDIA_SPREAD_CLOSE3_MIN:
        spread_ok = True
    if spread_ok:
        score += 2

    if m["tv_delta2"] is not None and m["tv_delta2"] >= MEDIA_TV_DELTA2_MIN:
        score += 2

    signal_ok = (
        m["drop1"] is not None and m["drop1"] >= MEDIA_DROP1_MIN
        and m["drop2"] is not None and m["drop2"] >= MEDIA_DROP2_MIN
        and m["persist2"]
        and score >= MEDIA_SCORE_MIN
    )

    if not signal_ok:
        return None

    quality = classify_media_quality(score, m["drop1"], m["drop2"], m["drop3"])

    alert_key = f"{cur['key']}_MEDIA"
    last = alerts_store.get(alert_key)

    if last:
        last_time = datetime.fromtimestamp(last["time"], TZ)
        if now_dt() - last_time < timedelta(minutes=MEDIA_COOLDOWN_MIN):
            return None
        if abs(last["odd"] - cur["odd"]) < 0.03:
            return None

    return {
        "type": "MEDIA",
        "quality": quality,
        "alert_key": alert_key,
        "odd": cur["odd"],
        "score": score,
        "drop1": m["drop1"],
        "drop2": m["drop2"],
        "drop3": m["drop3"],
    }


def detect_bajas(cur: Dict[str, Any], hist: List[Dict[str, Any]], alerts_store: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not (LOW_MIN_ODD <= cur["odd"] <= LOW_MAX_ODD):
        return None
    if len(hist) < 3:
        return None

    m = runner_metrics(hist, cur)

    if m["rebound1"] is not None and m["rebound1"] > LOW_REBOUND_BLOCK:
        return None

    if cur.get("lay_amt", 0) < LOW_MIN_LAY or cur.get("back_amt", 0) < LOW_MIN_BACK:
        return None

    if m["drop1"] is None or m["drop1"] < LOW_MIN_REAL_MOVE:
        return None

    if not (LOW_MIN_DROP1 <= (m["drop1"] or 0) <= LOW_MAX_DROP1):
        return None

    if not (LOW_MIN_DROP2 <= (m["drop2"] or 0) <= LOW_MAX_DROP2):
        return None

    if ((m["drop2"] or 0) - (m["drop1"] or 0)) < LOW_MIN_CONTINUITY:
        return None

    if ((m["drop2"] or 0) - (m["drop1"] or 0)) > LOW_MAX_ACCEL:
        return None

    setup = None

    if (m["drop1"] or 0) > 0.22 and (m["drop2"] or 0) > 0.45:
        setup = "RUPTURA"
    elif (m["drop1"] or 0) > 0.16 and (m["drop2"] or 0) > 0.32:
        setup = "CONTINUACION"
    elif (m["drop1"] or 0) > 0.18 and len(hist) >= 3:
        p2 = hist[-2]
        p3 = hist[-3]
        if p3["odd"] > p2["odd"] <= cur["odd"]:
            setup = "REENTRADA"

    if not setup:
        return None

    quality = classify_low_quality(setup, m["drop1"], m["drop2"])

    alert_key = f"{cur['key']}_{setup}_LOW"
    last = alerts_store.get(alert_key)

    if last:
        last_time = datetime.fromtimestamp(last["time"], TZ)
        if now_dt() - last_time < timedelta(minutes=LOW_COOLDOWN_MIN):
            return None
        if abs(last["odd"] - cur["odd"]) < 0.02:
            return None

    return {
        "type": "LOW",
        "quality": quality,
        "alert_key": alert_key,
        "odd": cur["odd"],
        "setup": setup,
        "drop1": m["drop1"],
        "drop2": m["drop2"],
    }


# ==========================================================
# MENSAJES
# ==========================================================
def build_media_message(cur: Dict[str, Any], sig: Dict[str, Any], house_pick: Dict[str, Any], quotes_info: Dict[str, Any]) -> str:
    priority_best = quotes_info.get("priority_best")
    overall_best = quotes_info.get("overall_best")

    return f"""
🟡 ANTICIPADOR_PRO - MEDIAS - {sig['quality']}

{cur['event']}
Liga: {cur['liga']}
Mercado: {cur['selection_label']}
Fecha: {cur['start_pe']}

ORBITX
• Cuota: {cur['odd']}
• Drop 1m: {round(sig['drop1'] or 0, 2)}%
• Drop 2m: {round(sig['drop2'] or 0, 2)}%
• Drop 3m: {round(sig['drop3'] or 0, 2)}%
• Score: {sig['score']}

CASA OBJETIVO
• Casa: {house_pick['casa']}
• Tipo: {house_pick['source_type']}
• Cuota casa: {house_pick['odd']}
• Edge: {round(house_pick['edge_pct'], 2)}%

REFERENCIA
• Mejor prioridad: {priority_best['casa'] if priority_best else '-'} @ {fmt_num(priority_best['odd']) if priority_best else '-'}
• Mejor general: {overall_best['casa'] if overall_best else '-'} @ {fmt_num(overall_best['odd']) if overall_best else '-'}

⏱️ {now_str()}
""".strip()


def build_low_message(cur: Dict[str, Any], sig: Dict[str, Any], house_pick: Dict[str, Any], quotes_info: Dict[str, Any]) -> str:
    priority_best = quotes_info.get("priority_best")
    overall_best = quotes_info.get("overall_best")

    return f"""
🔴 ANTICIPADOR_PRO - BAJAS - {sig['quality']}

{cur['event']}
Liga: {cur['liga']}
Mercado: {cur['selection_label']}
Fecha: {cur['start_pe']}

Setup: {sig['setup']}

ORBITX
• Cuota: {cur['odd']}
• Drop 1m: {round(sig['drop1'] or 0, 2)}%
• Drop 2m: {round(sig['drop2'] or 0, 2)}%

CASA OBJETIVO
• Casa: {house_pick['casa']}
• Tipo: {house_pick['source_type']}
• Cuota casa: {house_pick['odd']}
• Edge: {round(house_pick['edge_pct'], 2)}%

REFERENCIA
• Mejor prioridad: {priority_best['casa'] if priority_best else '-'} @ {fmt_num(priority_best['odd']) if priority_best else '-'}
• Mejor general: {overall_best['casa'] if overall_best else '-'} @ {fmt_num(overall_best['odd']) if overall_best else '-'}

⏱️ {now_str()}
""".strip()


# ==========================================================
# CORE
# ==========================================================
def process() -> None:
    raw_snapshot = load_json(SNAPSHOT_FILE)
    events = parse_events(normalize_snapshot(raw_snapshot))

    raw_cuotas = load_json(CUOTAS_FILE)
    cuotas_rows = parse_cuotas_json(raw_cuotas)
    cuotas_index = build_cuotas_index_by_eventid(cuotas_rows)

    state = load_state()
    history_store: Dict[str, List[Dict[str, Any]]] = state.get("history", {})
    alerts_store: Dict[str, Any] = state.get("alerts", {})

    new_history: Dict[str, List[Dict[str, Any]]] = {}
    new_alerts: Dict[str, Any] = alerts_store.copy()

    sent = 0

    for event in events:
        runners = event["runners"]

        runner_histories = {}
        for r in runners:
            hist = history_store.get(r["key"], [])
            if not isinstance(hist, list):
                hist = []
            runner_histories[r["key"]] = hist

        fav = get_non_draw_favorite(runners)

        for cur in runners:
            hist = runner_histories[cur["key"]]

            # --------------------------
            # MEDIAS
            # --------------------------
            media_signal = detect_medias(cur, hist, alerts_store)
            if media_signal:
                quotes_info = find_house_quotes_for_signal_by_eventid(
                    cuotas_index=cuotas_index,
                    event_id=cur["eventId"],
                    selection=cur["selection"],
                )

                house_pick = value_still_available(cur["odd"], quotes_info)

                if house_pick:
                    msg = build_media_message(cur, media_signal, house_pick, quotes_info)
                    send_telegram_message(msg)
                    print(msg)

                    new_alerts[media_signal["alert_key"]] = {
                        "time": now_dt().timestamp(),
                        "odd": media_signal["odd"],
                        "type": media_signal["type"],
                        "quality": media_signal["quality"],
                        "house": house_pick["casa"],
                    }
                    sent += 1

            # --------------------------
            # BAJAS
            # --------------------------
            if fav and fav["key"] == cur["key"]:
                low_signal = detect_bajas(cur, hist, alerts_store)
                if low_signal:
                    quotes_info = find_house_quotes_for_signal_by_eventid(
                        cuotas_index=cuotas_index,
                        event_id=cur["eventId"],
                        selection=cur["selection"],
                    )

                    house_pick = value_still_available(cur["odd"], quotes_info)

                    if house_pick:
                        msg = build_low_message(cur, low_signal, house_pick, quotes_info)
                        send_telegram_message(msg)
                        print(msg)

                        new_alerts[low_signal["alert_key"]] = {
                            "time": now_dt().timestamp(),
                            "odd": low_signal["odd"],
                            "type": low_signal["type"],
                            "quality": low_signal["quality"],
                            "setup": low_signal.get("setup"),
                            "house": house_pick["casa"],
                        }
                        sent += 1

        for cur in runners:
            hist = runner_histories[cur["key"]] + [cur]
            hist = hist[-HISTORY_POINTS:]
            new_history[cur["key"]] = hist

    save_json(STATE_FILE, {"history": new_history, "alerts": new_alerts})
    print(f"{now_str()} | alertas={sent}")


def main():
    print("🚀 ANTICIPADOR_PRO_CASAS activo")
    while True:
        try:
            process()
        except Exception as e:
            print("ERROR:", e)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)