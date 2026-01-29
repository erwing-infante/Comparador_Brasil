# scripts/multi_monitor_global.py
# ✅ Corregido: añade soporte de proxy SOCKS5 (Proxy-Seller) para el WebSocket (websocket-client)
# - Mantiene TODO tu comportamiento
# - Solo agrega:
#   - ORBITX_PROXY_SOCKS5 desde .env
#   - urlparse + kwargs en run_forever()
#
# ✅ EXTRA (LO ÚNICO QUE CAMBIÉ, como pediste):
#   - Copia snapshot.json a /var/www/mancorabet/static/data/snapshot.json
#   - Escritura ATÓMICA (tmp + replace) para evitar JSON corrupto al leer desde el navegador
#
# Requisitos en venv:
#   pip install "websocket-client[socks]"

import os
import sys
import csv
import json
import time
import uuid
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse  # ✅ NUEVO

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

# ✅ NUEVO: Proxy SOCKS5 para Orbitx (ej: socks5h://user:pass@res.proxy-seller.com:10000)
ORBITX_PROXY = os.getenv("ORBITX_PROXY_SOCKS5", "").strip()

WATCH_HOURS = int(os.getenv("WATCH_HOURS", "36"))
PING_INTERVAL = int(os.getenv("PING_INTERVAL", "20"))

# === ajustes por ENV ===
SAVE_EVERY_SEC = int(os.getenv("SAVE_EVERY_SEC", "3"))                # data-driven: no más de 1 write por market cada X sec
POLL_EVERY_SEC = float(os.getenv("POLL_EVERY_SEC", "10"))             # recomendado 8-15
STALE_SEC = int(os.getenv("STALE_SEC", "120"))                        # watchdog real
SNAPSHOT_EVERY_SEC = int(os.getenv("SNAPSHOT_EVERY_SEC", "5"))        # snapshot.json aunque no llegue data
CSV_SNAPSHOT_EVERY_SEC = int(os.getenv("CSV_SNAPSHOT_EVERY_SEC", "20"))  # ✅ escribe al CSV cada X sec aunque no llegue data
PRINT_MARKETS = os.getenv("PRINT_MARKETS", "1") == "1"

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

# ✅ NUEVO (solo para copiar snapshot a la web)
STATIC_SNAPSHOT_PATH = "/var/www/mancorabet/static/data/snapshot.json"

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
    arr = [{"marketId": m["marketId"], "eventId": m["eventId"], "applicationType": "WEB"} for m in markets]
    inner = json.dumps(arr, separators=(",", ":"))
    return json.dumps([inner])  # SockJS: array con string JSON

def ensure_csv_header(path: str):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(CSV_HEADER)

def parse_start_utc(s: str) -> Optional[datetime]:
    try:
        dt = datetime.strptime(s.replace(" UTC",""), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def load_all_watchlists() -> List[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    limit = now + timedelta(hours=WATCH_HOURS)

    files = [f for f in os.listdir(WATCHLISTS_DIR) if f.startswith("orbitx_watchlist_") and f.endswith(".json")]
    files.sort()

    all_markets: List[Dict[str, Any]] = []
    for fname in files:
        path = os.path.join(WATCHLISTS_DIR, fname)
        try:
            wl = json.load(open(path, "r", encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(wl, list) or not wl:
            continue

        for m in wl:
            start_utc = m.get("date","")
            dt = parse_start_utc(start_utc)
            if not dt:
                continue
            if dt < now or dt > limit:
                continue

            liga = m.get("Liga","")
            all_markets.append({
                "Liga": liga,
                "marketId": str(m["marketId"]),
                "eventId": str(m["eventId"]),
                "eventName": m.get("eventName") or m.get("name") or "Unknown",
                "start_utc": start_utc,
                "start_pe": start_utc_to_pe_iso(start_utc),
                "runners_map": m.get("runners", {}),
                "orbitx": m.get("orbitx", {}),
            })

    return all_markets

class MarketState:
    def __init__(self, m: Dict[str, Any]):
        self.liga = m["Liga"] or "UNKNOWN"
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
        self._last_save_ts = 0.0               # data-driven limiter
        self._last_csv_snapshot_ts = 0.0       # periodic writer limiter

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

    def _append_csv(self, t_utc: str, t_pe: str):
        if not self.runners_state:
            return

        out_csv = os.path.join(HISTORY_DIR, f"orbitx_{self.liga.lower().replace(' ','_')}.csv")
        ensure_csv_header(out_csv)

        with open(out_csv, "a", newline="", encoding="utf-8") as f:
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

    # === 1) escritura por llegada de data (igual que antes, solo limitada por SAVE_EVERY_SEC)
    def append_csv_if_due_data(self):
        now = time.time()
        if now - self._last_save_ts < SAVE_EVERY_SEC:
            return
        self._last_save_ts = now
        t_utc = ts_utc_iso()
        t_pe = ts_pe_iso()
        self._append_csv(t_utc, t_pe)

    # === 2) escritura periódica (aunque no llegue data)
    def append_csv_if_due_snapshot(self):
        now = time.time()
        if now - self._last_csv_snapshot_ts < CSV_SNAPSHOT_EVERY_SEC:
            return
        self._last_csv_snapshot_ts = now
        t_utc = ts_utc_iso()
        t_pe = ts_pe_iso()
        self._append_csv(t_utc, t_pe)

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

class GlobalMonitor:
    def __init__(self, markets: List[Dict[str, Any]]):
        self.markets = markets
        self.states = {m["marketId"]: MarketState(m) for m in markets}

        self.ws: Optional[websocket.WebSocketApp] = None
        self._lock = threading.Lock()
        self._stop = False

        self._last_msg_ts = time.time()
        self._last_data_ts = time.time()
        self._last_data_print = time.time()
        self._data_msgs = 0

        self._poll_started = False
        self._watchdog_started = False
        self._snapshot_started = False
        self._csvsnap_started = False

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

            # ✅ Escritura ATÓMICA al SNAPSHOT_PATH
            try:
                os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)
                tmp_path = SNAPSHOT_PATH + ".tmp"
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(snap, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, SNAPSHOT_PATH)
            except Exception:
                pass

            # ✅ Copia ATÓMICA al static para el front-end
            try:
                os.makedirs(os.path.dirname(STATIC_SNAPSHOT_PATH), exist_ok=True)
                tmp_static = STATIC_SNAPSHOT_PATH + ".tmp"
                with open(tmp_static, "w", encoding="utf-8") as f:
                    json.dump(snap, f, ensure_ascii=False, indent=2)
                os.replace(tmp_static, STATIC_SNAPSHOT_PATH)
            except Exception:
                pass

    def csv_snapshot_loop(self):
        # ✅ escribe al CSV aunque no llegue data, cada CSV_SNAPSHOT_EVERY_SEC
        while not self._stop:
            time.sleep(1)
            for st in self.states.values():
                st.append_csv_if_due_snapshot()

    def on_open(self, ws):
        with self._lock:
            self.ws = ws
        self._last_msg_ts = time.time()

        print(f"✅ [{ts_pe_iso()}] Conectado al WebSocket (GLOBAL)")

        if PRINT_MARKETS:
            print("📌 Markets suscritos:")
            for m in self.markets:
                print(f" - {m['Liga']} | {m['eventName']} | marketId={m['marketId']}")

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
        if not self._csvsnap_started:
            self._csvsnap_started = True
            threading.Thread(target=self.csv_snapshot_loop, daemon=True).start()

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

        now = time.time()
        self._last_msg_ts = now
        self._last_data_ts = now
        self._data_msgs += 1

        if now - self._last_data_print >= 10:
            age_data = now - self._last_data_ts
            print(f"📥 [{ts_pe_iso()}] Data msgs a[...]: {self._data_msgs} | last_data_age={age_data:.1f}s")
            self._last_data_print = now

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
        st.append_csv_if_due_data()

    def on_error(self, ws, error):
        print("❌ WS Error:", error)

    def on_close(self, ws, code, msg):
        print("🔌 WS cerrado:", code, msg)
        with self._lock:
            self.ws = None

    def run(self):
        if not self.markets:
            raise SystemExit("❌ No hay markets en ventana.")

        headers = [
            f"Origin: {BASE}",
            f"Cookie: {ORBITX_COOKIE}",
            "User-Agent: Mozilla/5.0",
        ]

        # ✅ NUEVO: si hay proxy SOCKS5, lo aplicamos al WebSocket
        proxy_kwargs = {}
        if ORBITX_PROXY:
            try:
                u = urlparse(ORBITX_PROXY)
                if u.hostname and u.port:
                    proxy_kwargs = {
                        "http_proxy_host": u.hostname,
                        "http_proxy_port": int(u.port),
                        "proxy_type": "socks5",
                    }
                    if u.username and u.password:
                        proxy_kwargs["http_proxy_auth"] = (u.username, u.password)

                    # log sin exponer credenciales
                    print(f"🛰️ Usando SOCKS5 proxy: {u.hostname}:{u.port}")
            except Exception as e:
                print("⚠️ Proxy inválido, continuando sin proxy. Error:", e)
                proxy_kwargs = {}

        while not self._stop:
            try:
                ws_url = build_ws_url_fixed().strip()
                print("🔌 WS URL:", ws_url)

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
                    **proxy_kwargs
                )
            except Exception as e:
                print("❌ Excepción WS:", e)

            print("🔁 Reintentando en 5s...")
            time.sleep(5)

def main():
    markets = load_all_watchlists()
    print(f"📦 Markets dentro de {WATCH_HOURS}h:", len(markets))
    gm = GlobalMonitor(markets)
    gm.run()

if __name__ == "__main__":
    main()
