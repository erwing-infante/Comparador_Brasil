import os,json,time,threading,hashlib
from datetime import datetime
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests

BASE=os.path.dirname(os.path.abspath(__file__))
SNAP=os.path.join(BASE,"data","snapshot.json")
POS=os.path.join(BASE,"data","posiciones.json")
ENV=os.path.join(BASE,".env")
TZ=ZoneInfo("America/Lima")
POLL=1
GIRO_MIN_PCT=0.40
WORKERS=6
VISTA=[]
VISTA_LOCK=threading.Lock()
SESSION=requests.Session()
ADAPTER=requests.adapters.HTTPAdapter(pool_connections=20,pool_maxsize=20,max_retries=1)
SESSION.mount("https://",ADAPTER)

def env():
    d={}
    try:
        for x in open(ENV,encoding="utf-8"):
            x=x.strip()
            if x and not x.startswith("#") and "=" in x:
                k,v=x.split("=",1);d[k.strip()]=v.strip()
    except:pass
    return d

E=env()
TOKEN=E.get("POSICIONES_BOT_TOKEN","")
CHAT=str(E.get("POSICIONES_BOT_CHAT_ID",""))
API=f"https://api.telegram.org/bot{TOKEN}/"

def api(m,data=None,timeout=15):
    try:
        r=SESSION.post(API+m,data=data or {},timeout=timeout)
        return r.json()
    except Exception as e:
        print("[TG]",e);return {}

def send(txt,markup=None):
    d={"chat_id":CHAT,"text":txt,"parse_mode":"HTML"}
    if markup:d["reply_markup"]=json.dumps(markup,ensure_ascii=False)
    return api("sendMessage",d)

def delete_msg(mid):return api("deleteMessage",{"chat_id":CHAT,"message_id":mid},8)
def answer(cid,txt=""):return api("answerCallbackQuery",{"callback_query_id":cid,"text":txt},5)

def load_snap():
    try:
        with open(SNAP,encoding="utf-8") as f:return json.load(f)
    except:return {"markets":[]}

def load_pos():
    try:
        with open(POS,encoding="utf-8") as f:return json.load(f)
    except:return {}

def save_pos(d):
    os.makedirs(os.path.dirname(POS),exist_ok=True)
    tmp=POS+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:json.dump(d,f,ensure_ascii=False,indent=2)
    os.replace(tmp,POS)

def runners(m):
    d={}
    for r in m.get("runners",{}).values():
        s=r.get("selection")
        if s:d[s]=r
    return d

def cuota(m,s):
    try:return float(runners(m).get(s,{}).get("best_back_odds"))
    except:return None

def mercados_index(snap=None):
    snap=snap or load_snap()
    return {str(m.get("eventId")):m for m in snap.get("markets",[])}

def mercado(event,snap=None):
    return mercados_index(snap).get(str(event))

def nombre_sel(s):return {"HOME":"LOCAL","DRAW":"EMPATE","AWAY":"VISITA"}.get(s,s)

def prepartido(m):
    try:
        ini=datetime.fromisoformat(m.get("start_pe",""))
        if ini.tzinfo is None:ini=ini.replace(tzinfo=TZ)
        return ini>datetime.now(TZ)
    except:return False

def ligas(snap=None):
    snap=snap or load_snap()
    return sorted(set(m.get("liga","Sin liga") for m in snap.get("markets",[]) if prepartido(m)))

def lid(liga):return hashlib.md5(liga.encode()).hexdigest()[:10]

def liga_id(x,snap=None):
    for l in ligas(snap):
        if lid(l)==x:return l

def registrar_vista(mid):
    if not mid:return
    with VISTA_LOCK:VISTA.append(mid)

def limpiar_vista():
    global VISTA
    with VISTA_LOCK:
        mids=VISTA[:]
        VISTA=[]
    if not mids:return
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(delete_msg,mids))

def enviar_partido(m,liga):
    fila=[]
    for s,ico in [("HOME","🏠"),("DRAW","🤝"),("AWAY","✈️")]:
        q=cuota(m,s)
        if q:fila.append({"text":f"{ico} {nombre_sel(s)} {q:.2f}","callback_data":f"ADD|{m['eventId']}|{s}"})
    if not fila:return None
    hora=m.get("start_pe","")[:16].replace("T"," ")
    txt=f"🏆 <b>{liga}</b>\n⚽ <b>{m.get('eventName','')}</b>\n🕐 {hora}"
    r=send(txt,{"inline_keyboard":[fila]})
    try:return r["result"]["message_id"]
    except:return None

def menu_ligas(borrar=None):
    limpiar_vista()
    if borrar:
        threading.Thread(target=delete_msg,args=(borrar,),daemon=True).start()
    snap=load_snap();ls=ligas(snap)
    if not ls:return send("No hay ligas prepartido disponibles en OrbitX.")
    filas=[]
    for i in range(0,len(ls),2):
        filas.append([{"text":f"🏆 {l}","callback_data":f"LG|{lid(l)}"} for l in ls[i:i+2]])
    filas.append([{"text":"🔄 Actualizar ligas","callback_data":"LIGAS"}])
    r=send("🏆 <b>Selecciona una liga</b>",{"inline_keyboard":filas})
    try:registrar_vista(r["result"]["message_id"])
    except:pass

def partidos_liga(liga,borrar=None):
    limpiar_vista()
    if borrar:
        threading.Thread(target=delete_msg,args=(borrar,),daemon=True).start()
    snap=load_snap()
    ms=[m for m in snap.get("markets",[]) if prepartido(m) and m.get("liga","Sin liga")==liga]
    ms=sorted(ms,key=lambda x:x.get("start_pe",""))
    if not ms:
        kb={"inline_keyboard":[[{"text":"🔄 Actualizar","callback_data":f"REF|{lid(liga)}"}],[{"text":"⬅️ Volver a ligas","callback_data":"VOLVER"}]]}
        r=send(f"🏆 <b>{liga}</b>\n\nNo hay partidos prepartido disponibles.",kb)
        try:registrar_vista(r["result"]["message_id"])
        except:pass
        return
    resultados=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures={ex.submit(enviar_partido,m,liga):m.get("start_pe","") for m in ms}
        for f in as_completed(futures):
            try:
                mid=f.result()
                if mid:resultados.append(mid)
            except Exception as e:print("[ENVIO]",e)
    with VISTA_LOCK:VISTA.extend(resultados)
    kb={"inline_keyboard":[[{"text":"🔄 Actualizar cuotas","callback_data":f"REF|{lid(liga)}"}],[{"text":"⬅️ Volver a ligas","callback_data":"VOLVER"}]]}
    r=send(f"🏆 <b>{liga}</b>",kb)
    try:registrar_vista(r["result"]["message_id"])
    except:pass

def activas():
    p=load_pos()
    if not p:return send("No tienes cuotas vigilándose.")
    for k,x in p.items():
        txt=f"👁 <b>{x['eventName']}</b>\n🎯 {nombre_sel(x['selection'])}\n🔒 Asegurada: <b>{x['entry']:.2f}</b>\n📉 Mínimo: <b>{x['min']:.2f}</b>\n📊 Actual: <b>{x['last']:.2f}</b>"
        send(txt,{"inline_keyboard":[[{"text":"❌ Dejar de vigilar","callback_data":f"DEL|{k}"}]]})

def add(event,s,cid):
    snap=load_snap();m=mercados_index(snap).get(str(event))
    if not m:return answer(cid,"Partido no encontrado")
    if not prepartido(m):return answer(cid,"El partido ya comenzó")
    q=cuota(m,s)
    if not q:return answer(cid,"Cuota no disponible")
    k=f"{event}_{s}";p=load_pos()
    p[k]={"eventId":str(event),"marketId":m.get("marketId"),"liga":m.get("liga"),"eventName":m.get("eventName"),"selection":s,"entry":q,"min":q,"last":q,"alerted":False,"ts":time.time()}
    save_pos(p)
    answer(cid,f"{nombre_sel(s)} {q:.2f} vigilada")
    send(f"✅ <b>CUOTA ASEGURADA</b>\n\n⚽ <b>{m.get('eventName')}</b>\n🎯 {nombre_sel(s)} @ <b>{q:.2f}</b>\n\n👁 Desde ahora vigilo si la cuota se gira.")

def delete(k,cid):
    p=load_pos()
    if k in p:
        x=p.pop(k);save_pos(p);answer(cid,"Vigilancia eliminada")
        send(f"❌ Dejé de vigilar <b>{x['eventName']}</b> — {nombre_sel(x['selection'])}.")
    else:answer(cid,"Ya no estaba activa")

def telegram():
    off=0
    while True:
        try:
            r=api("getUpdates",{"offset":off,"timeout":20},25)
            for u in r.get("result",[]):
                off=u["update_id"]+1
                if "callback_query" in u:
                    c=u["callback_query"];z=c.get("data","").split("|");mid=c["message"]["message_id"]
                    if z[0]=="LIGAS":
                        answer(c["id"],"Actualizando...")
                        threading.Thread(target=menu_ligas,args=(mid,),daemon=True).start()
                    elif z[0]=="VOLVER":
                        answer(c["id"])
                        threading.Thread(target=menu_ligas,daemon=True).start()
                    elif z[0]=="LG" and len(z)==2:
                        snap=load_snap();l=liga_id(z[1],snap);answer(c["id"],"Cargando...")
                        if l:threading.Thread(target=partidos_liga,args=(l,mid),daemon=True).start()
                    elif z[0]=="REF" and len(z)==2:
                        snap=load_snap();l=liga_id(z[1],snap);answer(c["id"],"Actualizando...")
                        if l:threading.Thread(target=partidos_liga,args=(l,),daemon=True).start()
                    elif z[0]=="ADD" and len(z)==3:
                        threading.Thread(target=add,args=(z[1],z[2],c["id"]),daemon=True).start()
                    elif z[0]=="DEL" and len(z)==2:
                        threading.Thread(target=delete,args=(z[1],c["id"]),daemon=True).start()
                elif "message" in u and str(u["message"]["chat"]["id"])==CHAT:
                    t=u["message"].get("text","").strip().lower()
                    if t.startswith("/partidos"):threading.Thread(target=menu_ligas,daemon=True).start()
                    elif t.startswith("/activas"):threading.Thread(target=activas,daemon=True).start()
                    elif t.startswith("/start"):send("🟢 <b>MancoraBet Posiciones</b>\n\n/partidos — elegir liga y marcar cuota\n/activas — ver cuotas vigiladas")
        except Exception as e:
            print("[POLL]",e);time.sleep(1)

def monitor():
    while True:
        snap=load_snap();idx=mercados_index(snap);p=load_pos();changed=False
        for k,x in list(p.items()):
            m=idx.get(str(x["eventId"]))
            if not m:continue
            q=cuota(m,x["selection"])
            if not q:continue
            last=float(x["last"]);mn=float(x["min"])
            if q<mn:
                x["min"]=q;x["alerted"]=False;changed=True
            mn=float(x["min"]);giro=(q-mn)/mn*100 if mn else 0
            if q>last and giro>=GIRO_MIN_PCT and not x.get("alerted"):
                send(f"🚨 <b>SE GIRA TU CUOTA</b>\n\n⚽ <b>{x['eventName']}</b>\n🎯 {nombre_sel(x['selection'])}\n\n🔒 Asegurada: <b>{x['entry']:.2f}</b>\n📉 Mínimo: <b>{mn:.2f}</b>\n🔄 Ahora: <b>{q:.2f}</b>\n📈 Giro: <b>+{giro:.2f}%</b>\n\n⚠️ La cuota acaba de cambiar de dirección.")
                x["alerted"]=True;changed=True
            if q!=last:x["last"]=q;changed=True
        if changed:save_pos(p)
        time.sleep(POLL)

if __name__=="__main__":
    print("MancoraBet Posiciones iniciado")
    threading.Thread(target=telegram,daemon=True).start()
    monitor()