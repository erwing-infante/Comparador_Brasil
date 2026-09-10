import os,json,time
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
import requests

BASE_DIR="/root/proyectos/Mancorabet/Monitor_Orbitx"
DATA_DIR=os.path.join(BASE_DIR,"data")
SNAPSHOT_FILE=os.path.join(DATA_DIR,"snapshot.json")
STATE_FILE=os.path.join(DATA_DIR,"estado_caidas_orbitx.json")
LOG_FILE=os.path.join(DATA_DIR,"caidas_orbitx.jsonl")

TELEGRAM_TOKEN=os.getenv("ORBITX_CAIDAS_BOT_TOKEN")
TELEGRAM_CHAT_ID=os.getenv("ORBITX_CAIDAS_CHAT_ID")

MAX_HOURS_AHEAD=18
CHECK_EVERY_SEC=5
TARGET_SELECTIONS=["HOME","AWAY"]

DROP_ALERT_TICKS=2
REVERSAL_TICKS=2

ALERT_90_MIN=90
ALERT_90_WINDOW=3
ALERT_10_MIN=10
ALERT_10_WINDOW=2

TZ_PE=ZoneInfo("America/Lima")
HORA_INICIO_TELEGRAM=7
HORA_FIN_TELEGRAM=23

def cargar_json(path,default=None):
    if default is None: default={}
    try:
        with open(path,"r",encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception as e:
        print(f"[ERROR JSON] {e}")
        return default

def guardar_json(path,data):
    try:
        tmp=path+".tmp"
        with open(tmp,"w",encoding="utf-8") as f:
            json.dump(data,f,ensure_ascii=False,indent=2)
        os.replace(tmp,path)
    except Exception as e:
        print(f"[ERROR GUARDAR] {e}")

def log_json(data):
    try:
        with open(LOG_FILE,"a",encoding="utf-8") as f:
            f.write(json.dumps(data,ensure_ascii=False)+"\n")
    except Exception as e:
        print(f"[ERROR LOG] {e}")

def cargar_estado():
    estado=cargar_json(STATE_FILE,{})
    estado.setdefault("ultimo_back",{})
    estado.setdefault("movimientos",{})
    estado.setdefault("alerta_90",{})
    estado.setdefault("alerta_10",{})
    return estado

def telegram_configurado():
    return bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)

def telegram_habilitado():
    ahora_pe=datetime.now(TZ_PE)
    return HORA_INICIO_TELEGRAM<=ahora_pe.hour<HORA_FIN_TELEGRAM

def enviar_telegram(mensaje):
    if not telegram_habilitado():
        print("[TELEGRAM CAIDAS] SILENCIADO POR HORARIO (23:00 - 07:00, hora Perú)")
        return False
    if not telegram_configurado():
        print("[TELEGRAM CAIDAS] NO CONFIGURADO")
        return False
    url=f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload={
        "chat_id":TELEGRAM_CHAT_ID,
        "text":mensaje,
        "parse_mode":"HTML",
        "disable_web_page_preview":True
    }
    try:
        r=requests.post(url,data=payload,timeout=15)
        if r.status_code==200:
            return True
        print(f"[TELEGRAM ERROR] {r.status_code} {r.text[:300]}")
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
    return False

def parse_start_pe(valor):
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except Exception:
        return None

def now_iso():
    return datetime.now().astimezone().isoformat()

def fmt_odds(valor):
    if valor is None:
        return "-"
    try:
        return f"{float(valor):.2f}"
    except Exception:
        return str(valor)

def fmt_money(valor):
    if valor is None:
        return "-"
    try:
        return f"{float(valor):,.2f}"
    except Exception:
        return str(valor)

def selection_nombre(selection):
    return "LOCAL" if selection=="HOME" else "VISITA"

def construir_escalera():
    ladder=[]
    def agregar(inicio,fin,paso):
        x=Decimal(str(inicio))
        fin=Decimal(str(fin))
        paso=Decimal(str(paso))
        while x<=fin:
            ladder.append(float(x))
            x+=paso
    agregar("1.01","2.00","0.01")
    agregar("2.02","3.00","0.02")
    agregar("3.05","4.00","0.05")
    agregar("4.10","6.00","0.10")
    agregar("6.20","10.00","0.20")
    agregar("10.50","20.00","0.50")
    agregar("21","30","1")
    agregar("32","50","2")
    agregar("55","100","5")
    agregar("110","1000","10")
    return ladder

TICK_LADDER=construir_escalera()
TICK_INDEX={round(v,2):i for i,v in enumerate(TICK_LADDER)}

def indice_tick(cuota):
    try:
        return TICK_INDEX.get(round(float(cuota),2))
    except Exception:
        return None

def ticks_entre(desde,hasta):
    i1=indice_tick(desde)
    i2=indice_tick(hasta)
    if i1 is None or i2 is None:
        return None
    return i2-i1

def ticks_caida(anterior,actual):
    ticks=ticks_entre(anterior,actual)
    if ticks is None or ticks>=0:
        return 0
    return abs(ticks)

def ticks_subida(anterior,actual):
    ticks=ticks_entre(anterior,actual)
    if ticks is None or ticks<=0:
        return 0
    return ticks

def partido_prematch_valido(partido):
    start=parse_start_pe(partido.get("start_pe"))
    if not start:
        return False
    ahora=datetime.now(start.tzinfo)
    segundos=(start-ahora).total_seconds()
    if segundos<=0:
        return False
    if segundos>MAX_HOURS_AHEAD*3600:
        return False
    return True

def obtener_runner(partido,selection):
    for runner in partido.get("runners",{}).values():
        if runner.get("selection")==selection:
            return runner
    return None

def revisar_caida(estado,partido,market_id,selection):
    runner=obtener_runner(partido,selection)
    if not runner:
        return
    actual=runner.get("best_back_odds")
    if actual is None:
        return
    actual=float(actual)

    key=f"{market_id}|{selection}"
    anterior=estado["ultimo_back"].get(key)

    if anterior is None:
        estado["ultimo_back"][key]=actual
        return

    anterior=float(anterior)

    if actual==anterior:
        return

    estado["ultimo_back"][key]=actual
    movimiento=estado["movimientos"].get(key)

    if movimiento and movimiento.get("activo",False):
        minimo=float(movimiento["minimo"])

        if actual<minimo:
            movimiento["minimo"]=actual
            minimo=actual
            return

        rebote_ticks=ticks_subida(minimo,actual)

        if rebote_ticks>=REVERSAL_TICKS:
            mensaje=(
                "🔄 <b>MOVIMIENTO REVERTIDO</b>\n\n"
                f"🏆 {partido.get('liga','-')}\n"
                f"⚽ <b>{partido.get('eventName','-')}</b>\n\n"
                f"📈 <b>{selection_nombre(selection)}</b>\n\n"
                f"Mínimo: {fmt_odds(minimo)}\n"
                f"Ahora: <b>{fmt_odds(actual)}</b>\n\n"
                f"Rebote: <b>+{rebote_ticks} ticks</b>"
            )

            enviar_telegram(mensaje)

            movimiento["activo"]=False

            log_json({
                "tipo":"REVERSIÓN",
                "timestamp":now_iso(),
                "market_id":market_id,
                "event_name":partido.get("eventName"),
                "selection":selection,
                "minimo":minimo,
                "actual":actual,
                "rebote_ticks":rebote_ticks
            })

        return

    caida_ticks=ticks_caida(anterior,actual)

    if caida_ticks<DROP_ALERT_TICKS:
        return

    mensaje=(
        "📉 <b>CAÍDA ORBITX</b>\n\n"
        f"🏆 {partido.get('liga','-')}\n"
        f"⚽ <b>{partido.get('eventName','-')}</b>\n\n"
        f"📉 <b>{selection_nombre(selection)}</b>\n\n"
        f"{fmt_odds(anterior)} → <b>{fmt_odds(actual)}</b>\n"
        f"Caída: <b>-{caida_ticks} ticks</b>"
    )

    enviar_telegram(mensaje)

    estado["movimientos"][key]={
        "activo":True,
        "inicial":anterior,
        "minimo":actual,
        "timestamp":now_iso()
    }

    log_json({
        "tipo":"CAIDA",
        "timestamp":now_iso(),
        "market_id":market_id,
        "event_name":partido.get("eventName"),
        "selection":selection,
        "anterior":anterior,
        "actual":actual,
        "caida_ticks":caida_ticks
    })

def revisar_alerta_90(estado,partido):
    event_id=str(partido.get("eventId",""))
    if not event_id:
        return
    if event_id in estado["alerta_90"]:
        return

    start=parse_start_pe(partido.get("start_pe"))
    if not start:
        return

    ahora=datetime.now(start.tzinfo)
    minutos=(start-ahora).total_seconds()/60.0

    if minutos>ALERT_90_MIN:
        return
    if minutos<(ALERT_90_MIN-ALERT_90_WINDOW):
        return

    home=obtener_runner(partido,"HOME")
    draw=obtener_runner(partido,"DRAW")
    away=obtener_runner(partido,"AWAY")

    mensaje=(
        "⏰ <b>90 MINUTOS PARA EL PARTIDO</b>\n\n"
        f"🏆 {partido.get('liga','-')}\n"
        f"⚽ <b>{partido.get('eventName','-')}</b>\n"
        f"📅 {start.strftime('%d/%m/%Y')}  🕒 {start.strftime('%H:%M')} 🇵🇪\n\n"
        "📊 <b>ORBITX</b>\n"
        f"L: {fmt_odds(home.get('best_back_odds') if home else None)}\n"
        f"X: {fmt_odds(draw.get('best_back_odds') if draw else None)}\n"
        f"V: {fmt_odds(away.get('best_back_odds') if away else None)}\n\n"
        f"💰 Volumen mercado: {fmt_money(partido.get('tv_market'))}\n"
        f"⏳ Faltan: {minutos:.1f} min"
    )

    if enviar_telegram(mensaje):
        estado["alerta_90"][event_id]={"timestamp":now_iso()}

def revisar_alerta_10(estado,partido):
    event_id=str(partido.get("eventId",""))
    if not event_id:
        return
    if event_id in estado["alerta_10"]:
        return

    start=parse_start_pe(partido.get("start_pe"))
    if not start:
        return

    ahora=datetime.now(start.tzinfo)
    minutos=(start-ahora).total_seconds()/60.0

    if minutos>ALERT_10_MIN:
        return
    if minutos<(ALERT_10_MIN-ALERT_10_WINDOW):
        return

    home=obtener_runner(partido,"HOME")
    draw=obtener_runner(partido,"DRAW")
    away=obtener_runner(partido,"AWAY")

    mensaje=(
        "⏰ <b>10 MINUTOS PARA EL PARTIDO</b>\n\n"
        f"🏆 {partido.get('liga','-')}\n"
        f"⚽ <b>{partido.get('eventName','-')}</b>\n"
        f"📅 {start.strftime('%d/%m/%Y')}  🕒 {start.strftime('%H:%M')} 🇵🇪\n\n"
        "📊 <b>ORBITX</b>\n"
        f"L: {fmt_odds(home.get('best_back_odds') if home else None)}\n"
        f"X: {fmt_odds(draw.get('best_back_odds') if draw else None)}\n"
        f"V: {fmt_odds(away.get('best_back_odds') if away else None)}\n\n"
        f"💰 Volumen mercado: {fmt_money(partido.get('tv_market'))}\n"
        f"⏳ Faltan: {minutos:.1f} min"
    )

    if enviar_telegram(mensaje):
        estado["alerta_10"][event_id]={"timestamp":now_iso()}

def limpiar_estado(estado,mercados_validos):
    validos=set(mercados_validos.keys())

    for grupo in ["ultimo_back","movimientos"]:
        borrar=[]
        for key in estado[grupo].keys():
            market_id=key.split("|",1)[0]
            if market_id not in validos:
                borrar.append(key)

        for key in borrar:
            estado[grupo].pop(key,None)

def procesar():
    snapshot=cargar_json(SNAPSHOT_FILE,{})
    mercados=snapshot.get("markets",[])

    if not mercados:
        return

    estado=cargar_estado()
    mercados_validos={}

    for partido in mercados:
        if not partido_prematch_valido(partido):
            continue

        market_id=str(partido.get("marketId",""))

        if not market_id:
            continue

        mercados_validos[market_id]=partido

    limpiar_estado(estado,mercados_validos)

    for market_id,partido in mercados_validos.items():
        revisar_alerta_90(estado,partido)
        revisar_alerta_10(estado,partido)

        for selection in TARGET_SELECTIONS:
            revisar_caida(estado,partido,market_id,selection)

    guardar_json(STATE_FILE,estado)

def main():
    print()
    print("==============================================")
    print(" MANCORABET - CAIDAS ORBITX")
    print("==============================================")
    print(f"Ventana: 0-{MAX_HOURS_AHEAD} horas")
    print("LIVE: IGNORADO")
    print(f"Caída: >= {DROP_ALERT_TICKS} ticks")
    print(f"Reversión: >= {REVERSAL_TICKS} ticks desde mínimo")
    print("Comparación: CUOTA ANTERIOR → NUEVA CUOTA")
    print(f"Alertas previas: {ALERT_90_MIN} min y {ALERT_10_MIN} min")
    print(f"Telegram: {'OK' if telegram_configurado() else 'NO CONFIGURADO'}")
    print("==============================================")

    while True:
        try:
            procesar()
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[ERROR] {type(e).__name__}: {e}")

        time.sleep(CHECK_EVERY_SEC)

if __name__=="__main__":
    main()