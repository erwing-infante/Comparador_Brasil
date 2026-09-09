import os,json,time,threading,urllib.request,urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo
BASE=os.path.dirname(os.path.abspath(__file__))
SNAP=os.path.join(BASE,"data","snapshot.json")
POS=os.path.join(BASE,"data","posiciones.json")
ENV=os.path.join(BASE,".env")
TZ=ZoneInfo("America/Lima")
POLL=1
GIRO_MIN_PCT=0.40
def env():
    d={}
    try:
        for x in open(ENV,encoding="utf-8"):
            x=x.strip()
            if x and not x.startswith("#") and "=" in x:
                k,v=x.split("=",1);d[k.strip()]=v.strip()
    except:pass
    return d
E=env();TOKEN=E.get("POSICIONES_BOT_TOKEN","");CHAT=str(E.get("POSICIONES_BOT_CHAT_ID",""));API=f"https://api.telegram.org/bot{TOKEN}/"
def api(m,data=None):
    try:
        b=urllib.parse.urlencode(data or {}).encode()
        with urllib.request.urlopen(API+m,b,timeout=20) as r:return json.loads(r.read())
    except Exception as e:print("[TG]",e);return {}
def send(txt,markup=None):
    d={"chat_id":CHAT,"text":txt,"parse_mode":"HTML"}
    if markup:d["reply_markup"]=json.dumps(markup)
    return api("sendMessage",d)
def edit(mid,txt,markup=None):
    d={"chat_id":CHAT,"message_id":mid,"text":txt,"parse_mode":"HTML"}
    if markup:d["reply_markup"]=json.dumps(markup)
    return api("editMessageText",d)
def answer(cid,txt=""):api("answerCallbackQuery",{"callback_query_id":cid,"text":txt})
def load_snap():
    try:return json.load(open(SNAP,encoding="utf-8"))
    except:return {"markets":[]}
def load_pos():
    try:return json.load(open(POS,encoding="utf-8"))
    except:return {}
def save_pos(d):
    os.makedirs(os.path.dirname(POS),exist_ok=True);tmp=POS+".tmp"
    with open(tmp,"w",encoding="utf-8") as f:json.dump(d,f,ensure_ascii=False,indent=2)
    os.replace(tmp,POS)
def runners(m):
    out={}
    for r in m.get("runners",{}).values():
        s=r.get("selection")
        if s:out[s]=r
    return out
def cuota(m,s):
    try:return float(runners(m).get(s,{}).get("best_back_odds"))
    except:return None
def mercado(event):
    for m in load_snap().get("markets",[]):
        if str(m.get("eventId"))==str(event):return m
def nombre_sel(s):return {"HOME":"LOCAL","DRAW":"EMPATE","AWAY":"VISITA"}.get(s,s)
def prepartido(m):
    try:
        ini=datetime.fromisoformat(m.get("start_pe",""))
        if ini.tzinfo is None:ini=ini.replace(tzinfo=TZ)
        return ini>datetime.now(TZ)
    except:return False
def encode_liga(s):return urllib.parse.quote(s,safe="")
def decode_liga(s):return urllib.parse.unquote(s)
def ligas_disponibles():
    return sorted(set(m.get("liga","Sin liga") for m in load_snap().get("markets",[]) if prepartido(m)))
def menu_ligas(mid=None):
    ligas=ligas_disponibles()
    if not ligas:
        if mid:return edit(mid,"No hay ligas prepartido disponibles en OrbitX.")
        return send("No hay ligas prepartido disponibles en OrbitX.")
    filas=[]
    for i in range(0,len(ligas),2):
        fila=[]
        for l in ligas[i:i+2]:fila.append({"text":f"🏆 {l}","callback_data":f"LIGA|{encode_liga(l)}"})
        filas.append(fila)
    filas.append([{"text":"🔄 Actualizar ligas","callback_data":"LIGAS"}])
    txt="🏆 <b>Selecciona una liga</b>"
    return edit(mid,txt,{"inline_keyboard":filas}) if mid else send(txt,{"inline_keyboard":filas})
def partidos_liga(liga,mid=None):
    ms=[m for m in load_snap().get("markets",[]) if prepartido(m) and m.get("liga","Sin liga")==liga]
    ms=sorted(ms,key=lambda x:x.get("start_pe",""))
    if not ms:
        txt=f"🏆 <b>{liga}</b>\n\nNo hay partidos prepartido disponibles."
        kb={"inline_keyboard":[[{"text":"🔄 Actualizar","callback_data":f"LIGA|{encode_liga(liga)}"}],[{"text":"⬅️ Volver a ligas","callback_data":"LIGAS"}]]}
        return edit(mid,txt,kb) if mid else send(txt,kb)
    txt=f"🏆 <b>{liga}</b>\n\n"
    filas=[]
    for m in ms:
        hora=m.get("start_pe","")[:16].replace("T"," ")
        txt+=f"⚽ <b>{m.get('eventName','')}</b>\n🕐 {hora}\n\n"
        fila=[]
        for s,ico in [("HOME","🏠"),("DRAW","🤝"),("AWAY","✈️")]:
            q=cuota(m,s)
            if q:fila.append({"text":f"{ico} {nombre_sel(s)} {q:.2f}","callback_data":f"ADD|{m['eventId']}|{s}|{encode_liga(liga)}"})
        if fila:filas.append(fila)
    filas.append([{"text":"🔄 Actualizar","callback_data":f"LIGA|{encode_liga(liga)}"}])
    filas.append([{"text":"⬅️ Volver a ligas","callback_data":"LIGAS"}])
    kb={"inline_keyboard":filas}
    return edit(mid,txt,kb) if mid else send(txt,kb)
def activas():
    p=load_pos()
    if not p:return send("No tienes cuotas vigilándose.")
    for k,x in p.items():
        txt=f"👁 <b>{x['eventName']}</b>\n🎯 {nombre_sel(x['selection'])}\n🔒 Asegurada: <b>{x['entry']:.2f}</b>\n📉 Mínimo: <b>{x['min']:.2f}</b>\n📊 Actual: <b>{x['last']:.2f}</b>"
        send(txt,{"inline_keyboard":[[{"text":"❌ Dejar de vigilar","callback_data":f"DEL|{k}"}]]})
def add(event,s,liga,cid):
    m=mercado(event)
    if not m:return answer(cid,"Partido no encontrado")
    if not prepartido(m):return answer(cid,"El partido ya comenzó")
    q=cuota(m,s)
    if not q:return answer(cid,"Cuota no disponible")
    k=f"{event}_{s}";p=load_pos()
    p[k]={"eventId":str(event),"marketId":m.get("marketId"),"liga":m.get("liga"),"eventName":m.get("eventName"),"selection":s,"entry":q,"min":q,"last":q,"alerted":False,"ts":time.time()}
    save_pos(p);answer(cid,f"{nombre_sel(s)} {q:.2f} vigilada")
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
            r=api("getUpdates",{"offset":off,"timeout":15})
            for u in r.get("result",[]):
                off=u["update_id"]+1
                if "callback_query" in u:
                    c=u["callback_query"];d=c.get("data","");z=d.split("|");mid=c["message"]["message_id"]
                    if z[0]=="LIGAS":answer(c["id"]);menu_ligas(mid)
                    elif z[0]=="LIGA" and len(z)==2:answer(c["id"]);partidos_liga(decode_liga(z[1]),mid)
                    elif z[0]=="ADD" and len(z)==4:add(z[1],z[2],decode_liga(z[3]),c["id"])
                    elif z[0]=="DEL" and len(z)==2:delete(z[1],c["id"])
                elif "message" in u and str(u["message"]["chat"]["id"])==CHAT:
                    t=u["message"].get("text","").strip().lower()
                    if t.startswith("/partidos"):menu_ligas()
                    elif t.startswith("/activas"):activas()
                    elif t.startswith("/start"):send("🟢 <b>MancoraBet Posiciones</b>\n\n/partidos — elegir liga y marcar cuota\n/activas — ver cuotas vigiladas")
        except Exception as e:print("[POLL]",e);time.sleep(2)
def monitor():
    while True:
        p=load_pos();changed=False
        for k,x in list(p.items()):
            m=mercado(x["eventId"])
            if not m:continue
            q=cuota(m,x["selection"])
            if not q:continue
            last=float(x["last"]);mn=float(x["min"])
            if q<mn:x["min"]=q;x["alerted"]=False;changed=True
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