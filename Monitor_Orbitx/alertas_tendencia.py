# ALERTAS_TENDENCIA.py
import os
import io
import json
import math
from datetime import datetime, timezone

import pandas as pd
import requests

# =========================
# LIGAS / PERFILES
# =========================
STRICT_LIGAS = {
    "Premier League","Championship","La Liga","Serie A","Bundesliga","Ligue 1","Eredivisie",
    "UEFA Champions League","UEFA Europa League","UEFA Conference League",
}
RELAXED_LIGAS = {
    "FA Cup","EFL Cup","La Liga 2","Copa del Rey","Copa Italia","Copa Alemana",
    "Primeira Liga","Brasileirao","Liga MX",
}
NO_OPERAR_LIGAS = {
    "MLS","Liga 1 Perú","Eliminatorias Europa - WC26","Copa Libertadores","Copa Sudamericana",
}

def normalize_liga_name(liga: str) -> str:
    s = (liga or "").strip().replace("_", " ")
    s = " ".join(s.split())
    # Respeta UEFA
    if s.lower().startswith("uefa "):
        return "UEFA " + s[5:].strip().title()
    return s.title()

def profile_for_liga(liga: str) -> str:
    ln = normalize_liga_name(liga)
    if ln in NO_OPERAR_LIGAS: return "NO_OPERAR"
    if ln in STRICT_LIGAS: return "STRICT"
    if ln in RELAXED_LIGAS: return "RELAXED"
    return "UNKNOWN"

TEST_ALERT = os.getenv("TEST_ALERT", "0") == "1"

TV_MARKET_MIN_STRICT = float(os.getenv("TV_MARKET_MIN_STRICT", "10000"))
TV_MARKET_MIN_RELAXED = float(os.getenv("TV_MARKET_MIN_RELAXED", "5000"))
TV_RUNNER_MIN = float(os.getenv("TV_RUNNER_MIN", "2000"))

# =========================
# INPUT / TELEGRAM
# =========================
CSV_GLOB = os.getenv("CSV_GLOB", "/root/proyectos/Mancorabet/Monitor_Orbitx/data/history/orbitx_*.csv")
TAIL_LINES = int(os.getenv("TAIL_LINES", "20000"))

TELEGRAM_TOKEN = os.getenv("TREND_BOT_TOKEN", "").strip()
CHAT_IDS = [os.getenv("TREND_BOT_CHAT_ID_1", "").strip(), os.getenv("TREND_BOT_CHAT_ID_2", "").strip()]
CHAT_IDS = [int(x) for x in CHAT_IDS if x.isdigit()]
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

STATE_PATH = os.getenv("STATE_PATH", "/root/proyectos/Mancorabet/Monitor_Orbitx/data/alertas_tendencia_state.json")

# =========================
# TIME FILTERS
# =========================
MAX_TTS_HOURS = float(os.getenv("MAX_TTS_HOURS", "36"))
PRIORITY_TTS_HOURS = float(os.getenv("PRIORITY_TTS_HOURS", "18"))

# =========================
# PHASE ENABLE
# =========================
SEND_PHASE1 = os.getenv("SEND_PHASE1", "1") == "1"
SEND_PHASE2 = os.getenv("SEND_PHASE2", "1") == "1"
SEND_PHASE3 = os.getenv("SEND_PHASE3", "1") == "1"
PHASE_COOLDOWN_MIN = int(os.getenv("PHASE_COOLDOWN_MIN", "8"))

# =========================
# PREMIUM THRESHOLDS
# =========================
W_MIN = int(os.getenv("W_MIN", "9"))
P_MIN = int(os.getenv("P_MIN", "60"))

MOM_TICKS_TH = float(os.getenv("MOM_TICKS_TH", "2.0"))
IMB3_TH = float(os.getenv("IMB3_TH", "0.18"))
FLOW_PCTL_TH = float(os.getenv("FLOW_PCTL_TH", "80"))

VOL_ABS_WINDOW_MIN = int(os.getenv("VOL_ABS_WINDOW_MIN", "6"))
DELTA_TV_MIN = float(os.getenv("DELTA_TV_MIN", "150"))

# Pullback / Resume
PULLBACK_MAX_TICKS = float(os.getenv("PULLBACK_MAX_TICKS", "1.0"))
PULLBACK_INVALID_TICKS = float(os.getenv("PULLBACK_INVALID_TICKS", "2.0"))
RESUME_MIN_TICK = float(os.getenv("RESUME_MIN_TICK", "1.0"))  # reanudación requiere >=1 tick
RESUME_CONSEC = int(os.getenv("RESUME_CONSEC", "2"))          # 2 lecturas seguidas

# Spread sanity
SPREAD_MAX_ODDS = float(os.getenv("SPREAD_MAX_ODDS", "0.02"))

# =========================
# UTILS
# =========================
def utc_now():
    return datetime.now(timezone.utc)

def iso_now():
    return utc_now().isoformat().replace("+00:00","Z")

def tick_size(odds: float) -> float:
    if odds is None or not math.isfinite(odds) or odds <= 1.0: return 0.01
    if 1.01 <= odds < 2.0: return 0.01
    if 2.0 <= odds < 3.0: return 0.02
    if 3.0 <= odds < 4.0: return 0.05
    if 4.0 <= odds < 6.0: return 0.10
    if 6.0 <= odds < 10.0: return 0.20
    if 10.0 <= odds < 20.0: return 0.50
    if 20.0 <= odds < 30.0: return 1.0
    if 30.0 <= odds < 50.0: return 2.0
    return 5.0

def tail_csv(filepath: str, n_lines: int) -> str:
    with open(filepath, "rb") as f:
        header = f.readline().decode("utf-8", errors="ignore")
    with open(filepath, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        bs = 8192
        blocks = []
        lines = 0
        pos = size
        while pos > 0 and lines < n_lines + 2:
            rs = min(bs, pos)
            pos -= rs
            f.seek(pos)
            data = f.read(rs)
            blocks.append(data)
            lines += data.count(b"\n")
        data = b"".join(reversed(blocks)).decode("utf-8", errors="ignore")
        tail = data.splitlines()[-n_lines:]
    return header.rstrip("\n") + "\n" + "\n".join(tail) + "\n"

def glob_files(pattern: str):
    import glob
    return sorted(glob.glob(pattern))

def load_state():
    if not os.path.exists(STATE_PATH):
        return {"signals": {}}
    try:
        with open(STATE_PATH,"r",encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"signals": {}}

def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_PATH) or ".", exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp,"w",encoding="utf-8") as f:
        json.dump(state,f,ensure_ascii=False,indent=2)
    os.replace(tmp, STATE_PATH)

def can_send(sig: dict, key: str) -> bool:
    last = sig.get(key)
    if not last: return True
    try:
        dt = datetime.fromisoformat(last.replace("Z","+00:00"))
        mins = (utc_now()-dt).total_seconds()/60.0
        return mins >= PHASE_COOLDOWN_MIN
    except:
        return True

def send_telegram(text: str):
    if DRY_RUN or not TELEGRAM_TOKEN or not CHAT_IDS:
        print("\n" + "="*70)
        print(text)
        print("="*70 + "\n")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for cid in CHAT_IDS:
        try:
            requests.post(url, json={"chat_id":cid,"text":text,"disable_web_page_preview":True}, timeout=15)
        except Exception as e:
            print("[WARN] telegram:", e)

def percentile_rank(value: float, arr):
    s = pd.Series(arr).dropna().astype(float)
    if len(s)==0 or not math.isfinite(value): return -1
    return int(round(100.0*(s.le(value).sum()/len(s))))

def delta_tv_recent(g: pd.DataFrame, minutes: int) -> float:
    now_ts = g["ts_utc"].iloc[-1]
    lb = now_ts - pd.Timedelta(minutes=minutes)
    h = g[g["ts_utc"]>=lb].sort_values("ts_utc")
    if len(h)<2: return 0.0
    return max(float(h["tv_runner"].iloc[-1]) - float(h["tv_runner"].iloc[0]), 0.0)

def spread_limit(mid: float) -> float:
    return max(SPREAD_MAX_ODDS, 2.0*tick_size(mid))

# =========================
# FORMATTERS
# =========================
def fmt_phase1(meta, profile, direction, odds_ini, odds_now, ticks_move, pct, dTV, tv_runner, imb3, tts_min):
    vol_txt = "FUERTE" if dTV >= DELTA_TV_MIN else "LEVE"
    prio = "ALTA" if tts_min <= int(PRIORITY_TTS_HOURS*60) else "BAJA"
    dir_txt = "📉 STEAM (baja cuota)" if direction=="STEAM" else "📈 DRIFT (sube cuota)"
    return (
        f"🟦 **FASE 1 — IMPULSO (NO ENTRAR)**\n"
        f"🏆 **{meta['liga']}** | 🧩 Perfil: {profile} | 🟣 Prioridad: {prio}\n"
        f"🎮 **{meta['event_name']}** — **{meta['selection']}**\n"
        f"🧭 Dirección: **{dir_txt}**\n\n"
        f"📊 Impulso\n"
        f"• Inicial: **{odds_ini:.3f}**\n"
        f"• Actual: **{odds_now:.3f}**\n"
        f"• Movimiento: **{odds_now-odds_ini:+.3f}** ({ticks_move:+.1f} ticks)\n"
        f"• % cambio: **{pct:+.2f}%**\n\n"
        f"💧 Volumen tv_runner: {vol_txt} | Δtv({VOL_ABS_WINDOW_MIN}m)={dTV:.2f} | tv_runner={tv_runner:,.0f}\n"
        f"📚 Libro imb3: {imb3:+.2f}\n"
        f"🕒 Faltan: {tts_min} min\n\n"
        f"📌 Acción: **NO entrar**. Esperar **pullback (Fase 2)**."
    )

def fmt_phase2(meta, profile, direction, imp_end, pull_mid, pull_ticks, dTV, imb3, tts_min, ok):
    prio = "ALTA" if tts_min <= int(PRIORITY_TTS_HOURS*60) else "BAJA"
    dir_txt = "📉 STEAM" if direction=="STEAM" else "📈 DRIFT"
    vol_txt = "FUERTE" if dTV >= DELTA_TV_MIN else "LEVE"
    if ok:
        status = "🟨 **PULLBACK SANO — señal sigue viva**"
        action = "Esperar reanudación (Fase 3)."
    else:
        status = "🚫 **INVALIDADO AQUÍ — rebote peligroso**"
        action = "NO entrar. Pérdida evitada."
    return (
        f"🟨 **FASE 2 — PULLBACK (OBSERVAR)**\n"
        f"🏆 **{meta['liga']}** | 🧩 Perfil: {profile} | 🟣 Prioridad: {prio}\n"
        f"🎮 **{meta['event_name']}** — **{meta['selection']}**\n"
        f"🧭 Dirección base: **{dir_txt}**\n\n"
        f"📊 Pullback\n"
        f"• Fin impulso: **{imp_end:.3f}**\n"
        f"• Pullback: **{pull_mid:.3f}**\n"
        f"• Retroceso: **{pull_ticks:+.1f} ticks**\n\n"
        f"💧 Volumen: {vol_txt} | Δtv({VOL_ABS_WINDOW_MIN}m)={dTV:.2f}\n"
        f"📚 Libro imb3: {imb3:+.2f}\n"
        f"🕒 Faltan: {tts_min} min\n\n"
        f"{status}\n"
        f"📌 Acción: {action}"
    )

def fmt_phase3(meta, profile, direction, confidence, odds_ini, odds_now, ticks_move, mom_ticks, spread, imb3, flow_pctl, dTV, tv_runner, tv_market, tts_min):
    prio = "ALTA" if tts_min <= int(PRIORITY_TTS_HOURS*60) else "BAJA"
    dir_txt = "📉 STEAM (baja cuota)" if direction=="STEAM" else "📈 DRIFT (sube cuota)"
    return (
        f"🚦 **FASE 3 — REANUDACIÓN (ENTRADA)**\n"
        f"🏆 **{meta['liga']}** | 🧩 Perfil: {profile} | 🟣 Prioridad: {prio}\n"
        f"🎮 **{meta['event_name']}** — **{meta['selection']}**\n"
        f"🧭 Dirección: **{dir_txt}**\n"
        f"🎯 Confianza: **{confidence}/100**\n\n"
        f"📊 Cuotas\n"
        f"• Inicial (fase 1): **{odds_ini:.3f}**\n"
        f"• Entrada (fase 3): **{odds_now:.3f}**\n"
        f"• Movimiento: **{odds_now-odds_ini:+.3f}** ({ticks_move:+.1f} ticks)\n\n"
        f"📌 Spread: {spread:.2f}\n"
        f"⏱️ Momentum({W_MIN}m): {mom_ticks:+.1f} ticks\n"
        f"📚 Orderbook(imb3): {imb3:+.2f} ✅\n"
        f"💧 Flow: pctl {flow_pctl} ✅ | Δtv({VOL_ABS_WINDOW_MIN}m)={dTV:.2f} ✅\n"
        f"💰 tv_runner={tv_runner:,.0f} | tv_market={tv_market:,.0f}\n"
        f"🕒 Faltan: {tts_min} min\n\n"
        f"📍 Recomendación: **ENTRAR**"
    )

# =========================
# CORE LOGIC
# =========================
def main():
    state = load_state()
    files = glob_files(CSV_GLOB)
    if not files:
        print("[ERROR] No CSV files found:", CSV_GLOB)
        return

    if TEST_ALERT:
        send_telegram("✅ TEST OK: alertas_tendencia.py está enviando mensajes (Monitor_Orbitx).")
        return

    # Leemos todos y procesamos candidatos (para mandar pocas)
    candidates = []

    for fp in files:
        try:
            csv_text = tail_csv(fp, TAIL_LINES)
            df = pd.read_csv(io.StringIO(csv_text))
        except Exception as e:
            print("[WARN] read csv:", fp, e)
            continue

        needed = {"ts_utc","start_utc","liga","market_id","selection_id","event_name","selection",
                  "best_back_odds","best_lay_odds","tv_runner","tv_market","sum_back_top3","sum_lay_top3","spread","locked"}
        if not needed.issubset(set(df.columns)):
            continue

        df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="coerce")
        df["start_utc"] = pd.to_datetime(df["start_utc"], utc=True, errors="coerce")
        df = df.dropna(subset=["ts_utc","start_utc"])
        if df.empty:
            continue

        # recorta para eficiencia
        max_ts = df["ts_utc"].max()
        df = df[df["ts_utc"] >= max_ts - pd.Timedelta(minutes=max(P_MIN, W_MIN, VOL_ABS_WINDOW_MIN)+60)]

        for (market_id, selection_id), g in df.groupby(["market_id","selection_id"]):
            g = g.sort_values("ts_utc")
            last = g.iloc[-1]

            liga_raw = str(last.get("liga","")).strip()
            liga = normalize_liga_name(liga_raw)
            profile = profile_for_liga(liga)

            if profile == "NO_OPERAR":
                continue

            tv_market_min = TV_MARKET_MIN_STRICT if profile in ("STRICT","UNKNOWN") else TV_MARKET_MIN_RELAXED

            # tts
            tts_min = int(round((last["start_utc"].to_pydatetime() - last["ts_utc"].to_pydatetime()).total_seconds()/60))
            if tts_min < 0 or tts_min > int(MAX_TTS_HOURS*60):
                continue

            # básicos de liquidez/spread
            back = float(last["best_back_odds"])
            lay = float(last["best_lay_odds"])
            mid = (back+lay)/2.0
            tick = tick_size(mid)
            spread = float(last["spread"]) if pd.notna(last["spread"]) else (lay-back)
            locked = bool(last.get("locked", False))
            tv_runner = float(last["tv_runner"])
            tv_market = float(last["tv_market"])

            if locked or tv_market < tv_market_min or tv_runner < TV_RUNNER_MIN or spread > spread_limit(mid):
                continue

            # state key
            key = f"{market_id}|{selection_id}"
            sig = state["signals"].get(key, {})
            phase = sig.get("phase","IDLE")

            meta = {
                "liga": liga,
                "event_name": str(last.get("event_name","—")),
                "selection": str(last.get("selection","—"))
            }

            # momentum
            now_ts = g["ts_utc"].iloc[-1]
            ref_ts = now_ts - pd.Timedelta(minutes=W_MIN)
            ref_df = g[g["ts_utc"]<=ref_ts]
            if not ref_df.empty:
                ref = ref_df.iloc[-1]
            else:
                ref = g.iloc[0]
            ref_mid = (float(ref["best_back_odds"])+float(ref["best_lay_odds"]))/2.0
            mom_ticks = (mid-ref_mid)/(tick if tick>0 else 0.01)
            direction = None
            if mom_ticks >= MOM_TICKS_TH:
                direction="DRIFT"
            elif mom_ticks <= -MOM_TICKS_TH:
                direction="STEAM"

            # imbalance
            sb3 = float(last.get("sum_back_top3",0.0) or 0.0)
            sl3 = float(last.get("sum_lay_top3",0.0) or 0.0)
            imb3 = (sb3-sl3)/(sb3+sl3+1e-9)

            # vol abs
            dTV = delta_tv_recent(g, VOL_ABS_WINDOW_MIN)

            # ----------------
            # FASE 1 (IMPULSO)
            # ----------------
            if phase == "IDLE" and direction:
                sig["phase"]="IMPULSE"
                sig["dir"]=direction
                sig["imp_start_mid"]=mid
                sig["imp_end_mid"]=mid
                sig["last_p1"]=sig.get("last_p1","")
                state["signals"][key]=sig

                if SEND_PHASE1 and can_send(sig, "last_p1"):
                    ticks_move = (mid - sig["imp_start_mid"])/(tick if tick>0 else 0.01)
                    pct = (mid/sig["imp_start_mid"] - 1.0)*100.0
                    msg = fmt_phase1(meta, profile, direction, sig["imp_start_mid"], mid, ticks_move, pct, dTV, tv_runner, imb3, tts_min)
                    send_telegram(msg)
                    sig["last_p1"]=iso_now()
                    state["signals"][key]=sig

            # actualiza impulso extremo y detecta pullback
            sig = state["signals"].get(key, sig)
            if sig.get("phase") == "IMPULSE":
                direction = sig.get("dir")
                imp_end = float(sig.get("imp_end_mid", mid))

                # actualiza extremo
                if direction == "STEAM" and mid < imp_end:
                    sig["imp_end_mid"]=mid
                if direction == "DRIFT" and mid > imp_end:
                    sig["imp_end_mid"]=mid

                imp_end = float(sig.get("imp_end_mid", mid))
                pull_ticks = (mid - imp_end)/(tick if tick>0 else 0.01)

                # pullback detect
                is_pull = False
                if direction == "STEAM" and pull_ticks >= 0.5:
                    is_pull=True
                if direction == "DRIFT" and pull_ticks <= -0.5:
                    is_pull=True

                if is_pull:
                    sig["phase"]="PULLBACK"
                    sig["pull_mid"]=mid
                    sig["pull_ticks"]=pull_ticks
                    state["signals"][key]=sig

                    ok=True
                    # invalida por rebote fuerte
                    if direction == "STEAM" and pull_ticks > PULLBACK_INVALID_TICKS:
                        ok=False
                    if direction == "DRIFT" and pull_ticks < -PULLBACK_INVALID_TICKS:
                        ok=False
                    # invalida por giro de libro básico
                    if direction == "STEAM" and imb3 < -0.05:
                        ok=False
                    if direction == "DRIFT" and imb3 > 0.05:
                        ok=False

                    if SEND_PHASE2 and can_send(sig, "last_p2"):
                        msg = fmt_phase2(meta, profile, direction, imp_end, mid, pull_ticks, dTV, imb3, tts_min, ok)
                        send_telegram(msg)
                        sig["last_p2"]=iso_now()
                        state["signals"][key]=sig

                    if not ok:
                        state["signals"].pop(key, None)
                        continue

            # ----------------
            # FASE 3 (REANUDACIÓN / ENTRADA)
            # ----------------
            sig = state["signals"].get(key, sig)
            if sig.get("phase") == "PULLBACK":
                direction = sig.get("dir")
                # Reanudación: 2 lecturas seguidas con >=1 tick en dirección (Δ=0 no cuenta)
                mid_series = (g["best_back_odds"].astype(float)+g["best_lay_odds"].astype(float))/2.0
                if len(mid_series) >= 3:
                    a,b,c = mid_series.iloc[-3], mid_series.iloc[-2], mid_series.iloc[-1]
                    d1 = (b-a)/(tick if tick>0 else 0.01)
                    d2 = (c-b)/(tick if tick>0 else 0.01)

                    if direction == "STEAM":
                        resumed = (d1 <= -RESUME_MIN_TICK) and (d2 <= -RESUME_MIN_TICK)
                    else:
                        resumed = (d1 >= RESUME_MIN_TICK) and (d2 >= RESUME_MIN_TICK)

                    if resumed:
                        # premium checks (libro + flow + volabs)
                        # libro alineado
                        book_ok = (imb3 >= IMB3_TH) if direction=="STEAM" else (imb3 <= -IMB3_TH)

                        # flow pctl
                        lb = now_ts - pd.Timedelta(minutes=P_MIN)
                        gf = g[g["ts_utc"]>=lb].copy().sort_values("ts_utc")
                        flow_vals=[]
                        prev_tv=None; prev_ts=None
                        for _,r in gf.iterrows():
                            cur_tv=float(r["tv_runner"])
                            cur_ts=r["ts_utc"]
                            if prev_tv is None:
                                prev_tv=cur_tv; prev_ts=cur_ts; continue
                            dt=(cur_ts-prev_ts).total_seconds()
                            if dt<=0: prev_tv=cur_tv; prev_ts=cur_ts; continue
                            d=max(cur_tv-prev_tv,0.0)
                            flow_vals.append(d*60.0/dt)
                            prev_tv=cur_tv; prev_ts=cur_ts
                        if len(flow_vals)==0:
                            flow_pctl=-1
                            flow_ok=False
                        else:
                            flow_pctl=percentile_rank(flow_vals[-1], flow_vals)
                            flow_ok = flow_pctl >= FLOW_PCTL_TH

                        volabs_ok = dTV >= DELTA_TV_MIN

                        if book_ok and flow_ok and volabs_ok:
                            # confidence simple
                            confidence = 85 if profile=="STRICT" else 75
                            # señal 3
                            if SEND_PHASE3 and can_send(sig, "last_p3"):
                                odds_ini=float(sig.get("imp_start_mid", mid))
                                ticks_move=(mid-odds_ini)/(tick if tick>0 else 0.01)
                                msg = fmt_phase3(meta, profile, direction, confidence, odds_ini, mid, ticks_move, mom_ticks, spread, imb3, flow_pctl, dTV, tv_runner, tv_market, tts_min)
                                candidates.append((tts_min, -confidence, msg, key))

                                sig["phase"]="ACTIVE"
                                sig["last_p3"]=iso_now()
                                state["signals"][key]=sig

    # manda máximo 8 por corrida (prioriza tts menor)
    candidates.sort(key=lambda x: (x[0], x[1]))
    for _,_,msg,key in candidates[:8]:
        send_telegram(msg)

    save_state(state)

if __name__ == "__main__":
    main()
