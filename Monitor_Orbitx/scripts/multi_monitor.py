# scripts/multi_monitor.py
# ✅ Mismo enfoque pero para un watchlist específico

import os
import sys
import csv
import json
import time
import uuid
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

import websocket
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from config_orbitx import HISTORY_DIR, SNAPSHOT_PATH, WATCHLISTS_DIR  # noqa

load_dotenv()

BASE = "https://www.orbitxch.com"
WS_BASE_PATH = "/customer/ws/multiple-market-prices"

ORBITX_COOKIE = os.getenv("ORBITX_COOKIE", "").strip()
if not ORBITX_COOKIE:
    raise SystemExit("❌ Falta ORBITX_COOKIE en .env")

PING_INTERVAL = int(os.getenv("PING_INTERVAL", "20"))

SAVE_EVERY_SEC = int(os.getenv("SAVE_EVERY_SEC", "3"))
POLL_EVERY_SEC = float(os.getenv("POLL_EVERY_SEC", "10"))
STALE_SEC = int(os.getenv("STALE_SEC", "120"))
SNAPSHOT_EVERY_SEC = int(os.getenv("SNAPSHOT_EVERY_SEC", "5"))

CSV_LIGA_NAME = os.getenv("CSV_LIGA_NAME", "premier_league")
CSV_PATH = os.path.join(HISTORY_DIR, f"orbitx_{CSV_LIGA_NAME}.csv")

WATCHLIST_FILE = os.getenv("WATCHLIST_FILE") or os.path.join(WATCHLISTS_DIR, "orbitx_watchlist_premier_league.json")

TZ_PE = timezone(timedelta(hours=-5))

CSV_HEADER = [
    "ts_utc","ts_pe",
    "start_utc","start_pe",
    "liga",
    "market_id","event_id","event_name",
    "selection","selection_id","selection_name",
    "best_back_odds","best_back_amt",
    "best_lay_odds","best_lay_amt",
    "spread",
    "sum_back_top3","sum_lay_top3","blpr",
    "tv_runner","tv_market",
    "overround","underround",
    "locked"
]

def ts_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def ts_pe_iso() -> str:
    return datetime.now(TZ_PE).isoformat(timespec="seconds")

def safe_json_loads(s: str):
    try:
        return json.loads(s)
    except Exception:
        return None

def start_utc_to_pe_iso(start_utc: str) -> str:
    if not start_utc:
        return ""
    try:
        dt = datetime.strptime(start_utc.replace(" UTC", ""), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        return dt.astimezone(TZ_PE).isoformat(timespec="minutes")
    except Exception:
        return ""

def build_ws_url_fixed() -> str:
    server_id = "473"
    session_id = str(uuid.uuid4())
    return f"wss://www.orbitxch.com{WS_BASE_PATH}/{server_id}/{session_id}/websocket"

def build_subscribe_payload(markets: List[Dict[str, Any]]) -> str:
    arr = [{"marketId": m["marketId"], "eventId": m["eventId"], "applicationType":"WEB"} for m in markets]
    inner = json.dumps(arr, separators=(",", ":"))
    return json.dumps([inner])

def ensure_csv_header():
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADER)

def load_watchlist(path: str) -> List[Dict[str, Any]]:
    data = json.load(open(path, "r", encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("watchlist debe ser lista")

    out = []
    for m in data:
        start_utc = m.get("date", "")
        out.append({
            "Liga": m.get("Liga", CSV_LIGA_NAME),
            "eventId": str(m["eventId"]),
            "eventName": m.get("eventName") or m.get("name") or "Unknown",
            "marketId": str(m["marketId"]),
            "start_utc": start_utc,
            "start_pe": start_utc_to_pe_iso(start_utc),
            "runners_map": m.get("runners", {}),
            "orbitx": m.get("orbitx", {}),
        })
    return out

class MarketState:
    def __init__(self, m: Dict[str, Any]):
        self.liga = m["Liga"]
        self.marketId = m["marketId"]
        self.eventId = m["eventId"]
        self.eventName = m["eventName"]
        self.start_utc = m.get("start_utc")
        self.start_pe = m.get("start_pe")

        self.runners_map = {int(k): v for k, v in (m.get("runners_map") or {}).items()}
        self.home_id = m.get("orbitx", {}).get("home_id")
        self.away_id = m.get("orbitx", {}).get("away_id")
        self.draw_id = m.get("orbitx", {}).get("draw_id")

        self.tv_market: Optional[float] = None
        self.overround: Optional[float] = None
        self.underround: Optional[float] = None
        self.runners_state: Dict[int, Dict[str, Any]] = {}
        self._last_save_ts = 0.0

    def selection_tag(self, sid: int) -> str:
        if self.draw_id is not None and sid == int(self.draw_id):
            return "DRAW"
        if self.home_id is not None and sid == int(self.home_id):
            return "HOME"
        if self.away_id is not None and sid == int(self.away_id):
            return "AWAY"
        name = (self.runners_map.get(sid) or "").lower()
        if name in ("empate","the draw"):
            return "DRAW"
        return "UNKNOWN"

    def update(self, payload: Dict[str, Any]):
        if payload.get("tv") is not None:
            try: self.tv_market = float(payload["tv"])
            except: pass
        if payload.get("overround") is not None:
            try: self.overround = float(payload["overround"])
            except: pass
        if payload.get("underround") is not None:
            try: self.underround = float(payload["underround"])
            except: pass

        rc = payload.get("rc") or []
        if not isinstance(rc, list):
            return

        for r in rc:
            sid = r.get("id")
            if sid is None:
                continue
            sid = int(sid)

            bdatb = r.get("bdatb") or []
            bdatl = r.get("bdatl") or []
            tv_runner = r.get("tv")
            locked = bool(r.get("locked", False))

            best_back_odds = float(bdatb[0]["odds"]) if bdatb else None
            best_back_amt  = float(bdatb[0]["amount"]) if bdatb else None
            best_lay_odds  = float(bdatl[0]["odds"]) if bdatl else None
            best_lay_amt   = float(bdatl[0]["amount"]) if bdatl else None

            sum_back_top3 = float(sum(x.get("amount", 0) for x in bdatb[:3])) if bdatb else 0.0
            sum_lay_top3  = float(sum(x.get("amount", 0) for x in bdatl[:3])) if bdatl else 0.0
            blpr = (sum_back_top3 / sum_lay_top3) if sum_lay_top3 > 0 else None
            spread = (best_lay_odds - best_back_odds) if (best_lay_odds is not None and best_back_odds is not None) else None

            self.runners_state[sid] = {
                "selection": self.selection_tag(sid),
                "name": self.runners_map.get(sid, f"SEL_{sid}"),
                "best_back_odds": best_back_odds,
                "best_back_amt": best_back_amt,
                "best_lay_odds": best_lay_odds,
                "best_lay_amt": best_lay_amt,
                "spread": spread,
                "sum_back_top3": sum_back_top3,
                "sum_lay_top3": sum_lay_top3,
                "blpr": blpr,
                "tv_runner": float(tv_runner) if tv_runner is not None else None,
                "locked": locked,
            }

    def append_csv_if_due(self):
        now = time.time()
        if now - self._last_save_ts < SAVE_EVERY_SEC:
            return
        self._last_save_ts = now
        if not self.runners_state:
            return

        ensure_csv_header()
        t_utc = ts_utc_iso()
        t_pe = ts_pe_iso()

        with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for sid, st in self.runners_state.items():
                w.writerow([
                    t_utc, t_pe,
                    self.start_utc, self.start_pe,
                    self.liga,
                    self.marketId, self.eventId, self.eventName,
                    st.get("selection"), sid, st.get("name"),
                    st.get("best_back_odds"), st.get("best_back_amt"),
                    st.get("best_lay_odds"), st.get("best_lay_amt"),
                    st.get("spread"),
                    st.get("sum_back_top3"), st.get("sum_lay_top3"), st.get("blpr"),
                    st.get("tv_runner"), self.tv_market,
                    self.overround, self.underround,
                    st.get("locked"),
                ])

    def snapshot_dict(self):
        return {
            "liga": self.liga,
            "eventName": self.eventName,
            "eventId": self.eventId,
            "marketId": self.marketId,
            "start_utc": self.start_utc,
            "start_pe": self.start_pe,
            "tv_market": self.tv_market,
            "overround": self.overround,
            "underround": self.underround,
            "runners": self.runners_state,
        }

class OrbitXMultiMonitor:
    def __init__(self, markets: List[Dict[str, Any]]):
        self.markets = markets
        self.states = {m["marketId"]: MarketState(m) for m in markets}

        self.ws: Optional[websocket.WebSocketApp] = None
        self._lock = threading.Lock()
        self._stop = False

        self._last_msg_ts = time.time()
        self._poll_started = False
        self._watchdog_started = False
        self._snapshot_started = False

    def _send_subscribe_all(self):
        with self._lock:
            ws = self.ws
        if not ws:
            return
        try:
            ws.send(build_subscribe_payload(self.markets))
            print(f"📨 [{ts_pe_iso()}] SUBSCRIBE snapshot -> {len(self.markets)} markets")
        except Exception:
            pass

    def poll_loop(self):
        while not self._stop:
            time.sleep(POLL_EVERY_SEC)
            self._send_subscribe_all()

    def stale_watchdog_loop(self):
        while not self._stop:
            time.sleep(1)
            age = time.time() - self._last_msg_ts
            if age > STALE_SEC:
                print(f"⚠️ [{ts_pe_iso()}] STALE {age:.0f}s sin heartbeat/data -> reconectando...")
                try:
                    with self._lock:
                        if self.ws:
                            self.ws.close()
                except Exception:
                    pass
                self._last_msg_ts = time.time()

    def snapshot_loop(self):
        while not self._stop:
            time.sleep(SNAPSHOT_EVERY_SEC)
            snap = {"generated_at": ts_pe_iso(), "markets": [st.snapshot_dict() for st in self.states.values()]}
            try:
                with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
                    json.dump(snap, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    def on_open(self, ws):
        with self._lock:
            self.ws = ws
        self._last_msg_ts = time.time()

        print(f"✅ [{ts_pe_iso()}] Conectado al WebSocket (multi)")
        self._send_subscribe_all()

        if not self._poll_started:
            self._poll_started = True
            threading.Thread(target=self.poll_loop, daemon=True).start()
        if not self._watchdog_started:
            self._watchdog_started = True
            threading.Thread(target=self.stale_watchdog_loop, daemon=True).start()
        if not self._snapshot_started:
            self._snapshot_started = True
            threading.Thread(target=self.snapshot_loop, daemon=True).start()

    def on_message(self, ws, message: str):
        if message == "h" or message == "o":
            self._last_msg_ts = time.time()
            return

        if message.startswith("c["):
            self._last_msg_ts = time.time()
            try:
                ws.close()
            except Exception:
                pass
            return

        if not message.startswith("a["):
            return

        self._last_msg_ts = time.time()

        outer = safe_json_loads(message[1:])
        if not isinstance(outer, list) or not outer:
            return

        inner_str = outer[0]
        inner = safe_json_loads(inner_str) if isinstance(inner_str, str) else None
        if not isinstance(inner, dict):
            return

        market_id = str(inner.get("id") or "")
        st = self.states.get(market_id)
        if not st:
            return

        st.update(inner)
        st.append_csv_if_due()

    def on_error(self, ws, error):
        print(f"❌ WS Error: {error}")

    def on_close(self, ws, code, msg):
        print(f"🔌 WS cerrado: {code} {msg}")
        with self._lock:
            self.ws = None

    def run_forever(self):
        headers = [
            f"Origin: {BASE}",
            f"Cookie: {ORBITX_COOKIE}",
            "User-Agent: Mozilla/5.0",
        ]

        while not self._stop:
            try:
                ws_url = build_ws_url_fixed().strip()
                print(f"🔌 WS URL: {ws_url}")

                ws_app = websocket.WebSocketApp(
                    ws_url,
                    header=headers,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                )

                ws_app.run_forever(
                    ping_interval=PING_INTERVAL,
                    ping_timeout=10,
                )
            except Exception as e:
                print(f"❌ Excepción WS: {e}")

            print("🔁 Reintentando en 5s...")
            time.sleep(5)

def main():
    if not os.path.exists(WATCHLIST_FILE):
        raise SystemExit(f"❌ No existe watchlist: {WATCHLIST_FILE}")

    markets = load_watchlist(WATCHLIST_FILE)
    print(f"📦 Watchlist markets: {len(markets)} | file={WATCHLIST_FILE}")
    OrbitXMultiMonitor(markets).run_forever()

if __name__ == "__main__":
    main()
