import os,json,time,re,unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
from difflib import SequenceMatcher
import requests

BASE_DIR="/root/proyectos/Mancorabet/Monitor_Orbitx"
DATA_DIR=os.path.join(BASE_DIR,"data")
SNAPSHOT_FILE=os.path.join(DATA_DIR,"snapshot.json")
STATE_FILE=os.path.join(DATA_DIR,"estado_caidas_orbitx.json")
LOG_FILE=os.path.join(DATA_DIR,"caidas_orbitx.jsonl")
APUESTATOTAL_FILE=os.path.join(DATA_DIR,"cuotas_apuestatotal.json")
XBET_FILE=os.path.join(DATA_DIR,"cuotas_1xbet.json")

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
CASAS_LOOKBACK_MIN=5
CASAS_HISTORY_KEEP_MIN=12
MATCH_THRESHOLD=0.54

TZ_PE=ZoneInfo("America/Lima")
HORA_INICIO_TELEGRAM=7
HORA_FIN_TELEGRAM=23

def cargar_json(path,default=None):
    if default is None: default={}
    try:
        with open(path,"r",encoding="utf-8") as f:return json.load(f)
    except FileNotFoundError:return default
    except Exception as e:
        print(f"[ERROR JSON] {path}: {e}");return default

def guardar_json(path,data):
    try:
        tmp=path+".tmp"
        with open(tmp,"w",encoding="utf-8") as f:json.dump(data,f,ensure_ascii=False,indent=2)
        os.replace(tmp,path)
    except Exception as e:print(f"[ERROR GUARDAR] {e}")

def log_json(data):
    try:
        with open(LOG_FILE,"a",encoding="utf-8") as f:f.write(json.dumps(data,ensure_ascii=False)+"\n")
    except Exception as e:print(f"[ERROR LOG] {e}")

def cargar_estado():
    e=cargar_json(STATE_FILE,{})
    e.setdefault("ultimo_back",{})
    e.setdefault("movimientos",{})
    e.setdefault("alerta_90",{})
    e.setdefault("alerta_10",{})
    e.setdefault("historial_casas",{})
    e.setdefault("estado_casas",{})
    return e

def telegram_configurado():return bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)
def telegram_habilitado():return HORA_INICIO_TELEGRAM<=datetime.now(TZ_PE).hour<HORA_FIN_TELEGRAM

def enviar_telegram(mensaje):
    if not telegram_habilitado():
        print("[TELEGRAM CAIDAS] SILENCIADO POR HORARIO (23:00 - 07:00, hora Perú)");return False
    if not telegram_configurado():
        print("[TELEGRAM CAIDAS] NO CONFIGURADO");return False
    try:
        r=requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",data={"chat_id":TELEGRAM_CHAT_ID,"text":mensaje,"parse_mode":"HTML","disable_web_page_preview":True},timeout=15)
        if r.status_code==200:return True
        print(f"[TELEGRAM ERROR] {r.status_code} {r.text[:300]}")
    except Exception as e:print(f"[TELEGRAM ERROR] {e}")
    return False

def parse_start_pe(v):
    if not v:return None
    try:return datetime.fromisoformat(v)
    except:return None

def now_iso():return datetime.now().astimezone().isoformat()

def fmt_odds(v):
    if v is None:return "-"
    try:return f"{float(v):.2f}"
    except:return str(v)

def fmt_casa(v):
    if v is None:return "-"
    try:return f"{float(v):.3f}".rstrip("0").rstrip(".")
    except:return str(v)

def fmt_money(v):
    if v is None:return "-"
    try:return f"{float(v):,.2f}"
    except:return str(v)

def selection_nombre(s):return "LOCAL" if s=="HOME" else "VISITA"

def construir_escalera():
    l=[]
    def add(a,b,p):
        x,end,step=Decimal(str(a)),Decimal(str(b)),Decimal(str(p))
        while x<=end:l.append(float(x));x+=step
    add("1.01","2.00","0.01");add("2.02","3.00","0.02");add("3.05","4.00","0.05")
    add("4.10","6.00","0.10");add("6.20","10.00","0.20");add("10.50","20.00","0.50")
    add("21","30","1");add("32","50","2");add("55","100","5");add("110","1000","10")
    return l

TICK_LADDER=construir_escalera()
TICK_INDEX={round(v,2):i for i,v in enumerate(TICK_LADDER)}

def indice_tick(c):
    try:return TICK_INDEX.get(round(float(c),2))
    except:return None

def ticks_entre(a,b):
    i1,i2=indice_tick(a),indice_tick(b)
    return None if i1 is None or i2 is None else i2-i1

def ticks_caida(a,b):
    t=ticks_entre(a,b)
    return abs(t) if t is not None and t<0 else 0

def ticks_subida(a,b):
    t=ticks_entre(a,b)
    return t if t is not None and t>0 else 0

def partido_prematch_valido(p):
    start=parse_start_pe(p.get("start_pe"))
    if not start:return False
    seg=(start-datetime.now(start.tzinfo)).total_seconds()
    return 0<seg<=MAX_HOURS_AHEAD*3600

def obtener_runner(p,s):
    for r in p.get("runners",{}).values():
        if r.get("selection")==s:return r
    return None

STOPWORDS={"fc","cf","ac","sc","afc","cd","ss","sv","rc","club","de","del","da","do","dos","das","the","futbol","football"}

def normalizar(t):
    t=str(t or "").lower().strip()
    t="".join(c for c in unicodedata.normalize("NFD",t) if unicodedata.category(c)!="Mn")
    t=t.replace("&"," and ")
    t=re.sub(r"[^a-z0-9 ]+"," ",t)
    return " ".join(x for x in t.split() if x not in STOPWORDS)

def similitud(a,b):
    a,b=normalizar(a),normalizar(b)
    if not a or not b:return 0
    if a==b:return 1
    seq=SequenceMatcher(None,a,b).ratio()
    sa,sb=set(a.split()),set(b.split())
    jac=len(sa&sb)/len(sa|sb) if sa|sb else 0
    contiene=.90 if a in b or b in a else 0
    return max(seq,(seq+jac)/2,contiene)

def nombres_orbitx(p):
    h,a=obtener_runner(p,"HOME"),obtener_runner(p,"AWAY")
    if h and a and h.get("name") and a.get("name"):return h["name"],a["name"]
    n=str(p.get("eventName",""))
    for sep in [" v "," vs "," - "]:
        if sep in n:
            x=n.split(sep,1);return x[0].strip(),x[1].strip()
    return "",""

def buscar_partido_casa(p,lista):
    ho,ao=nombres_orbitx(p)
    if not ho or not ao or not isinstance(lista,list):return None
    mejor,score=None,0
    for x in lista:
        sh,sa=similitud(ho,x.get("Local","")),similitud(ao,x.get("Visita",""))
        if sh<.30 or sa<.30:continue
        s=(sh+sa)/2
        if s>score:mejor,score=x,s
    return mejor if score>=MATCH_THRESHOLD else None

def cuota_pa(item,selection):
    if not item:return None
    campo="Cuota Local" if selection=="HOME" else "Cuota Visita"
    v=item.get(campo)
    try:return float(v) if v is not None else None
    except:return None

def agregar_historial(estado,key,casa,cuota,ts,encontrado):
    fk=f"{key}|{casa}"
    estado["estado_casas"][fk]={"encontrado":bool(encontrado),"pa":cuota is not None}
    if cuota is None:return
    hist=estado["historial_casas"].setdefault(fk,[])
    if not hist or abs(float(hist[-1]["cuota"])-cuota)>.000001:hist.append({"ts":ts,"cuota":cuota})
    cutoff=ts-CASAS_HISTORY_KEEP_MIN*60
    viejos=[x for x in hist if float(x.get("ts",0))<cutoff]
    nuevos=[x for x in hist if float(x.get("ts",0))>=cutoff]
    if viejos:nuevos.insert(0,viejos[-1])
    estado["historial_casas"][fk]=nuevos

def actualizar_historial_casas(estado,mercados):
    at=cargar_json(APUESTATOTAL_FILE,[])
    xb=cargar_json(XBET_FILE,[])
    ts=time.time()
    for market_id,p in mercados.items():
        pa=buscar_partido_casa(p,at)
        px=buscar_partido_casa(p,xb)
        for s in TARGET_SELECTIONS:
            key=f"{market_id}|{s}"
            agregar_historial(estado,key,"APUESTATOTAL",cuota_pa(pa,s),ts,pa is not None)
            agregar_historial(estado,key,"1XBET",cuota_pa(px,s),ts,px is not None)

def movimiento_casa(estado,key,casa):
    fk=f"{key}|{casa}"
    status=estado["estado_casas"].get(fk,{})
    if not status.get("encontrado"):return {"estado":"SIN_DATOS"}
    if not status.get("pa"):return {"estado":"SIN_PA"}
    hist=estado["historial_casas"].get(fk,[])
    if not hist:return {"estado":"SIN_DATOS"}
    ahora=time.time();objetivo=ahora-CASAS_LOOKBACK_MIN*60
    actual=float(hist[-1]["cuota"])
    candidatos=[x for x in hist if float(x.get("ts",0))<=objetivo]
    if candidatos:
        ant=float(candidatos[-1]["cuota"])
        return {"estado":"OK","anterior":ant,"actual":actual}
    primero=hist[0];edad=ahora-float(primero.get("ts",ahora))
    if edad<(CASAS_LOOKBACK_MIN-.5)*60:return {"estado":"INSUFICIENTE","actual":actual}
    return {"estado":"OK","anterior":float(primero["cuota"]),"actual":actual}

def texto_casa(nombre,m):
    if m["estado"]=="SIN_PA":return f"{nombre}: ❓ SIN PA"
    if m["estado"]=="SIN_DATOS":return f"{nombre}: ❓ SIN DATOS"
    if m["estado"]=="INSUFICIENTE":return f"{nombre}: {fmt_casa(m['actual'])} ⏳ HISTORIAL INSUFICIENTE"
    a,b=m["anterior"],m["actual"]
    pct=((b-a)/a)*100 if a else 0
    if b<a:e="✅ YA CAYÓ"
    elif b>a:e="⬆️ SUBIÓ"
    else:e="🟢 SIN MOVER"
    return f"{nombre}: {fmt_casa(a)} → {fmt_casa(b)} ({pct:+.2f}%) {e}"

def resumen_casas(estado,key):
    return (
        f"\n\n🔎 <b>CUOTA PA - ÚLTIMOS {CASAS_LOOKBACK_MIN} MINUTOS</b>\n\n"
        f"{texto_casa('Apuesta Total',movimiento_casa(estado,key,'APUESTATOTAL'))}\n"
        f"{texto_casa('1xBet',movimiento_casa(estado,key,'1XBET'))}"
    )

def revisar_caida(estado,p,market_id,selection):
    r=obtener_runner(p,selection)
    if not r:return
    actual=r.get("best_back_odds")
    if actual is None:return
    actual=float(actual);key=f"{market_id}|{selection}"
    anterior=estado["ultimo_back"].get(key)
    if anterior is None:estado["ultimo_back"][key]=actual;return
    anterior=float(anterior)
    if actual==anterior:return
    estado["ultimo_back"][key]=actual
    mov=estado["movimientos"].get(key)
    if mov and mov.get("activo",False):
        minimo=float(mov["minimo"])
        if actual<minimo:mov["minimo"]=actual;return
        rebote=ticks_subida(minimo,actual)
        if rebote>=REVERSAL_TICKS:
            msg=("🔄 <b>MOVIMIENTO REVERTIDO</b>\n\n"
                 f"🏆 {p.get('liga','-')}\n"
                 f"⚽ <b>{p.get('eventName','-')}</b>\n\n"
                 f"📈 <b>{selection_nombre(selection)}</b>\n\n"
                 f"Mínimo: {fmt_odds(minimo)}\n"
                 f"Ahora: <b>{fmt_odds(actual)}</b>\n\n"
                 f"Rebote: <b>+{rebote} ticks</b>")
            enviar_telegram(msg);mov["activo"]=False
            log_json({"tipo":"REVERSIÓN","timestamp":now_iso(),"market_id":market_id,"event_name":p.get("eventName"),"selection":selection,"minimo":minimo,"actual":actual,"rebote_ticks":rebote})
        return
    caida=ticks_caida(anterior,actual)
    if caida<DROP_ALERT_TICKS:return
    at=movimiento_casa(estado,key,"APUESTATOTAL")
    xb=movimiento_casa(estado,key,"1XBET")
    msg=("📉 <b>CAÍDA ORBITX</b>\n\n"
         f"🏆 {p.get('liga','-')}\n"
         f"⚽ <b>{p.get('eventName','-')}</b>\n\n"
         f"📉 <b>{selection_nombre(selection)}</b>\n\n"
         f"{fmt_odds(anterior)} → <b>{fmt_odds(actual)}</b>\n"
         f"Caída: <b>-{caida} ticks</b>"
         f"{resumen_casas(estado,key)}")
    enviar_telegram(msg)
    estado["movimientos"][key]={"activo":True,"inicial":anterior,"minimo":actual,"timestamp":now_iso()}
    log_json({"tipo":"CAIDA","timestamp":now_iso(),"market_id":market_id,"event_name":p.get("eventName"),"selection":selection,"anterior":anterior,"actual":actual,"caida_ticks":caida,"apuestatotal":at,"1xbet":xb})

def revisar_alerta_90(estado,p):
    eid=str(p.get("eventId",""))
    if not eid or eid in estado["alerta_90"]:return
    start=parse_start_pe(p.get("start_pe"))
    if not start:return
    mins=(start-datetime.now(start.tzinfo)).total_seconds()/60
    if mins>ALERT_90_MIN or mins<(ALERT_90_MIN-ALERT_90_WINDOW):return
    h,d,a=obtener_runner(p,"HOME"),obtener_runner(p,"DRAW"),obtener_runner(p,"AWAY")
    msg=("⏰ <b>90 MINUTOS PARA EL PARTIDO</b>\n\n"
         f"🏆 {p.get('liga','-')}\n"
         f"⚽ <b>{p.get('eventName','-')}</b>\n"
         f"📅 {start.strftime('%d/%m/%Y')}  🕒 {start.strftime('%H:%M')} 🇵🇪\n\n"
         "📊 <b>ORBITX</b>\n"
         f"L: {fmt_odds(h.get('best_back_odds') if h else None)}\n"
         f"X: {fmt_odds(d.get('best_back_odds') if d else None)}\n"
         f"V: {fmt_odds(a.get('best_back_odds') if a else None)}\n\n"
         f"💰 Volumen mercado: {fmt_money(p.get('tv_market'))}\n"
         f"⏳ Faltan: {mins:.1f} min")
    if enviar_telegram(msg):estado["alerta_90"][eid]={"timestamp":now_iso()}

def revisar_alerta_10(estado,p):
    eid=str(p.get("eventId",""))
    if not eid or eid in estado["alerta_10"]:return
    start=parse_start_pe(p.get("start_pe"))
    if not start:return
    mins=(start-datetime.now(start.tzinfo)).total_seconds()/60
    if mins>ALERT_10_MIN or mins<(ALERT_10_MIN-ALERT_10_WINDOW):return
    h,d,a=obtener_runner(p,"HOME"),obtener_runner(p,"DRAW"),obtener_runner(p,"AWAY")
    msg=("⏰ <b>10 MINUTOS PARA EL PARTIDO</b>\n\n"
         f"🏆 {p.get('liga','-')}\n"
         f"⚽ <b>{p.get('eventName','-')}</b>\n"
         f"📅 {start.strftime('%d/%m/%Y')}  🕒 {start.strftime('%H:%M')} 🇵🇪\n\n"
         "📊 <b>ORBITX</b>\n"
         f"L: {fmt_odds(h.get('best_back_odds') if h else None)}\n"
         f"X: {fmt_odds(d.get('best_back_odds') if d else None)}\n"
         f"V: {fmt_odds(a.get('best_back_odds') if a else None)}\n\n"
         f"💰 Volumen mercado: {fmt_money(p.get('tv_market'))}\n"
         f"⏳ Faltan: {mins:.1f} min")
    if enviar_telegram(msg):estado["alerta_10"][eid]={"timestamp":now_iso()}

def limpiar_estado(estado,mercados):
    validos=set(mercados.keys())
    for grupo in ["ultimo_back","movimientos"]:
        for key in list(estado[grupo].keys()):
            if key.split("|",1)[0] not in validos:estado[grupo].pop(key,None)
    for grupo in ["historial_casas","estado_casas"]:
        for key in list(estado[grupo].keys()):
            if key.split("|",1)[0] not in validos:estado[grupo].pop(key,None)

def procesar():
    snap=cargar_json(SNAPSHOT_FILE,{})
    mercados=snap.get("markets",[])
    if not mercados:return
    estado=cargar_estado();validos={}
    for p in mercados:
        if not partido_prematch_valido(p):continue
        mid=str(p.get("marketId",""))
        if mid:validos[mid]=p
    limpiar_estado(estado,validos)
    actualizar_historial_casas(estado,validos)
    for mid,p in validos.items():
        revisar_alerta_90(estado,p)
        revisar_alerta_10(estado,p)
        for s in TARGET_SELECTIONS:revisar_caida(estado,p,mid,s)
    guardar_json(STATE_FILE,estado)

def main():
    print("\n==============================================")
    print(" MANCORABET - CAIDAS ORBITX")
    print("==============================================")
    print(f"Ventana: 0-{MAX_HOURS_AHEAD} horas")
    print("LIVE: IGNORADO")
    print(f"Caída: >= {DROP_ALERT_TICKS} ticks")
    print(f"Reversión: >= {REVERSAL_TICKS} ticks desde mínimo")
    print(f"Apuesta Total / 1xBet: CUOTA PA últimos {CASAS_LOOKBACK_MIN} min")
    print(f"Alertas previas: {ALERT_90_MIN} min y {ALERT_10_MIN} min")
    print(f"Telegram: {'OK' if telegram_configurado() else 'NO CONFIGURADO'}")
    print("==============================================")
    while True:
        try:procesar()
        except KeyboardInterrupt:break
        except Exception as e:print(f"[ERROR] {type(e).__name__}: {e}")
        time.sleep(CHECK_EVERY_SEC)

if __name__=="__main__":main()