import os,json,time,html,urllib.parse,urllib.request
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import fusionar_cuotas_NoPA as F_NOPA
import fusionar_cuotas as F_PA

BASE=os.path.dirname(os.path.abspath(__file__))
DATA=os.path.join(BASE,"data")
TZ=ZoneInfo("America/Lima")
SOURCES={"betsson","teapuesto","pinnacle"}
TARGETS={"apuestatotal","1xbet"}
CONFIRM_SEC=90
MIN_DROP=1.00
MIN_REMAIN_DROP=0.50
MAX_DATE_DIFF=21600
POLL=.40
MAX_HOURS=18
COOLDOWN=600
BOT_TOKEN=os.getenv("ANTICIPADOR_BOT_TOKEN","").strip()
CHAT_ID=os.getenv("ANTICIPADOR_CHAT_ID","").strip()
LOG=os.path.join(DATA,"anticipador_at_resultados.jsonl")
SEL={"home":("LOCAL","Local Odd"),"draw":("EMPATE","Empate Odd"),"away":("VISITA","Visita Odd")}

def num(x):
    try:return float(x)
    except:return None

def drop(a,b):
    return ((a-b)/a*100) if a and b and a>0 else 0

def norm(x):return (x or "").replace(" ","").strip().lower()

def valid(r):
    dt=r.get("Fecha_dt")
    if not dt:return False
    try:
        d=dt-datetime.now(timezone.utc).replace(tzinfo=None)
        return timedelta(0)<d<=timedelta(hours=MAX_HOURS)
    except:return False

def match_score(a,b):
    if not a or not b:return None
    if (a.get("Liga") or "")!=(b.get("Liga") or ""):return None
    d1,d2=a.get("Fecha_dt"),b.get("Fecha_dt")
    if not d1 or not d2:return None
    if abs((d1-d2).total_seconds())>MAX_DATE_DIFF:return None
    h=F_NOPA.similitud(a.get("home_short",""),b.get("home_short",""))
    v=F_NOPA.similitud(a.get("away_short",""),b.get("away_short",""))
    if h<F_NOPA.SIM_THRESHOLD or v<F_NOPA.SIM_THRESHOLD:return None
    return h+v-(abs((d1-d2).total_seconds())/MAX_DATE_DIFF)*.05

def find_match(rows,anchor):
    best=None;score=-1
    for r in rows:
        s=match_score(anchor,r)
        if s is not None and s>score:best,score=r,s
    return best

def same_match(a,b):return match_score(a,b) is not None

def tg(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("\n"+text+"\n",flush=True);return
    try:
        data=urllib.parse.urlencode({"chat_id":CHAT_ID,"text":text,"parse_mode":"HTML","disable_web_page_preview":"true"}).encode()
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",data=data,method="POST"),timeout=10).read()
    except Exception as e:print("[TG ERROR]",e,flush=True)

def log(o):
    os.makedirs(DATA,exist_ok=True)
    o["time"]=datetime.now(TZ).isoformat()
    with open(LOG,"a",encoding="utf-8") as f:f.write(json.dumps(o,ensure_ascii=False,default=str)+"\n")

def load_rows(loader,path,old=None):
    for i in range(4):
        try:
            rows=[r for r in loader(path) if valid(r)]
            if rows:return rows
        except:pass
        time.sleep(.12)
    return old if old is not None else []

def nopa_paths():
    return {norm(b):p for b,p in F_NOPA.ARCHIVOS.items() if norm(b) in SOURCES and os.path.exists(p)}

def pa_paths():
    return {norm(b):p for b,p in F_PA.ARCHIVOS.items() if norm(b) in TARGETS and os.path.exists(p)}

def quote(states,bm,anchor,sel):
    r=find_match(states.get(bm,[]),anchor)
    return num(r.get(SEL[sel][1])) if r else None

def current_source(states,bm,anchor):
    return find_match(states.get(bm,[]),anchor)

def target_status(cur,base):
    if cur is None:return "—"
    if base is None:return f"{cur:.3f}"
    if cur<base-1e-9:return f"{cur:.3f} ⚠️ YA BAJÓ"
    if cur>base+1e-9:return f"{cur:.3f} ⬆️ SUBIÓ"
    return f"{cur:.3f} ✅ SIN MOVERSE"

def info(anchor):
    return anchor.get("Liga") or "",anchor.get("Local") or "",anchor.get("Visita") or ""

def prealert(rec,nopa,pa):
    anchor=rec["anchor"];sel=rec["sel"];lab=SEL[sel][0]
    liga,local,visita=info(anchor)
    bm,m=next(iter(rec["moves"].items()))
    at=quote(pa,"apuestatotal",anchor,sel)
    x1=quote(pa,"1xbet",anchor,sel)
    txt=(f'🟡 <b>PREAVISO</b>\n\n🏆 {html.escape(liga)}\n⚽ <b>{html.escape(local.title())} vs {html.escape(visita.title())}</b>\n📉 <b>{lab}</b>\n\n'
         f'🔥 <b>{bm.title()} NoPA</b>\n{m["old"]:.3f} → <b>{m["new"]:.3f}</b> (-{m["drop"]:.2f}%)\n\n'
         f'🎯 Apuesta Total PA: <b>{at if at is not None else "—"}</b>\n📌 1xBet PA: <b>{x1 if x1 is not None else "—"}</b>\n\n'
         f'⏳ Esperando confirmación hasta {CONFIRM_SEC} s...')
    tg(txt)

def confirm(rec,nopa,pa):
    anchor=rec["anchor"];sel=rec["sel"];lab=SEL[sel][0]
    liga,local,visita=info(anchor)
    moves=sorted(rec["moves"].items(),key=lambda x:x[1]["ts"])
    at=quote(pa,"apuestatotal",anchor,sel);x1=quote(pa,"1xbet",anchor,sel)
    secs=moves[-1][1]["ts"]-moves[0][1]["ts"]
    lines=[]
    for bm,m in moves:
        cur=current_source(nopa,bm,anchor)
        cv=num(cur.get(SEL[sel][1])) if cur else m["new"]
        lines.append(f'🔥 <b>{bm.title()} NoPA</b>\n{m["old"]:.3f} → <b>{cv:.3f}</b> (-{drop(m["old"],cv):.2f}%)')
    txt=(f'🔴 <b>MOVIMIENTO CONFIRMADO</b>\n\n🏆 {html.escape(liga)}\n⚽ <b>{html.escape(local.title())} vs {html.escape(visita.title())}</b>\n📉 <b>{lab}</b>\n\n'
         +"\n\n".join(lines)+
         f'\n\n⏱ Confirmación: <b>{secs:.1f} s</b>\n\n🎯 <b>APUESTA TOTAL PA</b>\n{target_status(at,rec["at_base"])}\n\n'
         f'📌 <b>1XBET PA</b>\n{target_status(x1,rec["x1_base"])}\n\n🔥 <b>CONFIRMADO</b>')
    tg(txt)

def rec_id(anchor,sel):
    dt=anchor.get("Fecha_dt")
    return f'{anchor.get("Liga","")}|{dt}|{anchor.get("home_short","")}|{anchor.get("away_short","")}|{sel}'

def find_pending(pending,anchor,sel):
    best=None;score=-1
    for k,r in pending.items():
        if r["sel"]!=sel:continue
        s=match_score(r["anchor"],anchor)
        if s is not None and s>score:best,score=k,s
    return best

def main():
    print("MANCORABET - ANTICIPADOR RAPIDO 2 DE 3",flush=True)
    np=nopa_paths();pp=pa_paths()
    faltan=[x for x in SOURCES if x not in np]
    if faltan:raise SystemExit(f"Faltan fuentes NoPA: {faltan}")
    if "apuestatotal" not in pp:raise SystemExit("Falta Apuesta Total PA")
    nopa={bm:load_rows(F_NOPA.load_rows_from_file,p) for bm,p in np.items()}
    pa={bm:load_rows(F_PA.load_rows_from_file,p) for bm,p in pp.items()}
    mn={bm:os.path.getmtime(p) for bm,p in np.items()}
    mp={bm:os.path.getmtime(p) for bm,p in pp.items()}
    pending={};cooldown={}

    while True:
        t=time.time()

        for bm,p in pp.items():
            try:m=os.path.getmtime(p)
            except:continue
            if m!=mp.get(bm):
                old=pa.get(bm,[])
                new=load_rows(F_PA.load_rows_from_file,p,old)
                if new is not old:
                    pa[bm]=new;mp[bm]=m

        for bm,p in np.items():
            try:m=os.path.getmtime(p)
            except:continue
            if m==mn.get(bm):continue
            oldrows=nopa.get(bm,[])
            newrows=load_rows(F_NOPA.load_rows_from_file,p,oldrows)
            if newrows is oldrows:continue
            nopa[bm]=newrows;mn[bm]=m

            for nr in newrows:
                oldr=find_match(oldrows,nr)
                if not oldr:continue

                for sel,(_,col) in SEL.items():
                    old=num(oldr.get(col));new=num(nr.get(col))
                    if not old or not new:continue

                    pk=find_pending(pending,nr,sel)

                    if pk:
                        rec=pending[pk]
                        if bm in rec["moves"]:
                            first=rec["moves"][bm]
                            if drop(first["old"],new)<MIN_REMAIN_DROP:
                                rec["moves"].pop(bm,None)
                                if not rec["moves"]:pending.pop(pk,None)
                            continue

                    if new>=old or drop(old,new)<MIN_DROP:continue

                    rid=rec_id(nr,sel)
                    if cooldown.get(rid,0)>t:continue
                    move={"ts":t,"old":old,"new":new,"drop":drop(old,new)}

                    pk=find_pending(pending,nr,sel)
                    if not pk:
                        at=quote(pa,"apuestatotal",nr,sel)
                        x1=quote(pa,"1xbet",nr,sel)
                        rec={"anchor":nr,"sel":sel,"first_ts":t,"moves":{bm:move},"at_base":at,"x1_base":x1}
                        pending[rid]=rec
                        prealert(rec,nopa,pa)
                        log({"type":"PREALERT","source":bm,"selection":sel,"liga":nr.get("Liga"),"local":nr.get("Local"),"visita":nr.get("Visita"),"source_old":old,"source_new":new,"source_drop":drop(old,new),"at_pa":at,"x1_pa":x1})
                        continue

                    rec=pending[pk]
                    if t-rec["first_ts"]>CONFIRM_SEC:
                        pending.pop(pk,None);continue
                    if bm in rec["moves"]:continue
                    rec["moves"][bm]=move

                    activos=[]
                    for sbm,sm in list(rec["moves"].items()):
                        cr=current_source(nopa,sbm,rec["anchor"])
                        cv=num(cr.get(col)) if cr else None
                        if cv is None or drop(sm["old"],cv)<MIN_REMAIN_DROP:
                            rec["moves"].pop(sbm,None)
                        else:activos.append(sbm)

                    if len(activos)<2:continue

                    at=quote(pa,"apuestatotal",rec["anchor"],sel)
                    x1=quote(pa,"1xbet",rec["anchor"],sel)
                    at_ok=at is not None and (rec["at_base"] is None or at>=rec["at_base"]-1e-9)
                    x1_ok=x1 is not None and (rec["x1_base"] is None or x1>=rec["x1_base"]-1e-9)

                    if not at_ok and not x1_ok:
                        print("[TARDE] ambos targets ya bajaron:",pk,flush=True)
                        pending.pop(pk,None);cooldown[rid]=t+COOLDOWN
                        continue

                    confirm(rec,nopa,pa)
                    log({"type":"CONFIRMED","sources":activos,"selection":sel,"liga":rec["anchor"].get("Liga"),"local":rec["anchor"].get("Local"),"visita":rec["anchor"].get("Visita"),"confirm_sec":t-rec["first_ts"],"at_base":rec["at_base"],"at_now":at,"x1_base":rec["x1_base"],"x1_now":x1})
                    pending.pop(pk,None);cooldown[rid]=t+COOLDOWN

        for k in list(pending):
            if t-pending[k]["first_ts"]>CONFIRM_SEC:pending.pop(k,None)
        for k in list(cooldown):
            if cooldown[k]<=t:cooldown.pop(k,None)

        time.sleep(POLL)

if __name__=="__main__":main()