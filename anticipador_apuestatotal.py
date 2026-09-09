import os,json,time,html,urllib.parse,urllib.request
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import fusionar_cuotas_NoPA as F_NOPA
import fusionar_cuotas as F_PA

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
DATA_DIR=os.path.join(BASE_DIR,'data')
TZ=ZoneInfo('America/Lima')
TRIGGERS={'betsson','teapuesto'}
MAX_CONFIRM_SEC=30
MIN_DROP_PCT=1.00
ALIGN_TOL_PCT=2.50
BREAKAWAY_GAP_PCT=0.50
MIN_CONSENSUS_BOOKS=2
RESULT_WINDOW_SEC=180
RESULT_MIN_DROP_PCT=0.50
COOLDOWN_SEC=600
POLL_SEC=0.40
MAX_HOURS_AHEAD=18
STATE_FILE=os.path.join(DATA_DIR,'anticipador_at_state.json')
RESULT_FILE=os.path.join(DATA_DIR,'anticipador_at_resultados.jsonl')
BOT_TOKEN=os.getenv('ANTICIPADOR_BOT_TOKEN','').strip()
CHAT_ID=os.getenv('ANTICIPADOR_CHAT_ID','').strip()
SEL={'home':('LOCAL','Local Odd'),'draw':('EMPATE','Empate Odd'),'away':('VISITA','Visita Odd')}

def now():return datetime.now(TZ)
def fnum(x):
    try:return float(x)
    except:return None
def pct_drop(a,b):return ((a-b)/a*100.0) if a and b and a>0 else 0.0
def norm_bm(s):return (s or '').replace(' ','').strip().lower()
def key_str(k):return '||'.join(str(x) for x in k)
def event_key(r):return F_NOPA.partido_hash(r)
def valid_prematch(r):
    dt=r.get('Fecha_dt')
    if not dt:return True
    try:
        d=dt-datetime.now(timezone.utc).replace(tzinfo=None)
        return timedelta(0)<d<=timedelta(hours=MAX_HOURS_AHEAD)
    except:return True
def save_state(o):
    os.makedirs(DATA_DIR,exist_ok=True);tmp=STATE_FILE+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:json.dump(o,f,ensure_ascii=False,indent=2)
    os.replace(tmp,STATE_FILE)
def append_result(o):
    os.makedirs(DATA_DIR,exist_ok=True)
    with open(RESULT_FILE,'a',encoding='utf-8') as f:f.write(json.dumps(o,ensure_ascii=False)+'\n')
def tg(text):
    if not BOT_TOKEN or not CHAT_ID:print('\n'+text+'\n');return
    try:
        data=urllib.parse.urlencode({'chat_id':CHAT_ID,'text':text,'parse_mode':'HTML','disable_web_page_preview':'true'}).encode()
        urllib.request.urlopen(urllib.request.Request(f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',data=data,method='POST'),timeout=10).read()
    except Exception as e:print('[TG ERROR]',e)

def load_nopa(path):
    out={}
    for r in F_NOPA.load_rows_from_file(path):
        if valid_prematch(r):out[event_key(r)]=r
    return out
def load_pa(path):
    out={}
    for r in F_PA.load_rows_from_file(path):
        if valid_prematch(r):out[event_key(r)]=r
    return out
def source_paths():return {norm_bm(b):p for b,p in F_NOPA.ARCHIVOS.items() if os.path.exists(p)}
def target_paths():return {norm_bm(b):p for b,p in F_PA.ARCHIVOS.items() if os.path.exists(p)}
def quote(states,bm,event,sel):
    r=states.get(bm,{}).get(event)
    return fnum(r.get(SEL[sel][1])) if r else None
def consensus(states,event,sel,exclude):
    vals=[];col=SEL[sel][1]
    for bm,m in states.items():
        if bm==exclude:continue
        r=m.get(event)
        if not r:continue
        v=fnum(r.get(col))
        if v and v>1:vals.append(v)
    if len(vals)<MIN_CONSENSUS_BOOKS:return None,len(vals)
    vals.sort();n=len(vals)
    return (vals[n//2] if n%2 else (vals[n//2-1]+vals[n//2])/2),n
def is_breakaway(old,new,cons):
    if not old or not new or not cons or new>=old:return False
    if pct_drop(old,new)<MIN_DROP_PCT:return False
    if abs(old-cons)/cons*100>ALIGN_TOL_PCT:return False
    if (cons-new)/cons*100<BREAKAWAY_GAP_PCT:return False
    return True
def event_info(states,event):
    for bm in ('betsson','teapuesto','pinnacle','1xbet','apuestatotal'):
        r=states.get(bm,{}).get(event)
        if r:return {'liga':r.get('Liga') or '','local':r.get('Local') or '','visita':r.get('Visita') or ''}
    return {'liga':'','local':'','visita':''}
def send_signal(rec,nopa,pa):
    event=tuple(rec['event']);sel=rec['sel'];lab=SEL[sel][0];info=event_info(nopa,event)
    at=quote(pa,'apuestatotal',event,sel);x1=quote(pa,'1xbet',event,sel);pin=quote(nopa,'pinnacle',event,sel)
    at0=rec.get('at_pa_base');x10=rec.get('x1_pa_base')
    at_txt='—' if at is None else f'{at:.3f}'+('  ✅ TODAVÍA SIN MOVERSE' if at0 is not None and abs(at-at0)<1e-9 else '')
    x1_txt='—' if x1 is None else f'{x1:.3f}'+('  ✅ TODAVÍA SIN MOVERSE' if x10 is not None and abs(x1-x10)<1e-9 else '')
    a=rec['moves']['betsson'];b=rec['moves']['teapuesto'];diff=abs(a['ts']-b['ts'])
    text=(f'🚨 <b>POSIBLE CAÍDA APUESTA TOTAL</b>\n\n🏆 {html.escape(info["liga"])}\n⚽ <b>{html.escape(info["local"])} vs {html.escape(info["visita"])}</b>\n📉 <b>{lab}</b>\n\n'
          f'🔥 <b>Betsson NoPA</b>\n{a["old"]:.3f} → <b>{a["new"]:.3f}</b> ({-a["drop"]:.2f}%)\n\n'
          f'🔥 <b>TeApuesto NoPA</b>\n{b["old"]:.3f} → <b>{b["new"]:.3f}</b> ({-b["drop"]:.2f}%)\n\n'
          f'⏱ Confirmación: <b>{diff:.1f} s</b>\n\n🎯 <b>APUESTA TOTAL PA</b>\n{at_txt}\n\n📌 <b>1XBET PA</b>\n{x1_txt}\n\n📊 Pinnacle NoPA: {pin if pin is not None else "—"}\n⚡ <b>POSIBLE CAÍDA INMINENTE</b>')
    tg(text)
def send_result(a,hit,new_at=None):
    lab=SEL[a['sel']][0];base=a['at_pa']
    if hit:
        d=pct_drop(base,new_at);e=time.time()-a['alert_ts']
        tg(f'✅ <b>RESULTADO ANTICIPADOR</b>\n\n📉 {lab}\nApuesta Total PA: {base:.3f} → <b>{new_at:.3f}</b>\nCaída: <b>-{d:.2f}%</b>\n⏱ Tardó: <b>{e:.1f} s</b>')
    else:tg(f'❌ <b>RESULTADO ANTICIPADOR</b>\n\n📉 {lab}\nApuesta Total PA permaneció en {base:.3f}\nSin caída ≥{RESULT_MIN_DROP_PCT:.2f}% en {RESULT_WINDOW_SEC} s.')

def main():
    print('MANCORABET - ANTICIPADOR APUESTA TOTAL PA')
    npaths=source_paths();ppaths=target_paths()
    miss=[x for x in TRIGGERS if x not in npaths]
    if miss:raise SystemExit(f'Faltan fuentes NoPA: {miss}')
    if 'apuestatotal' not in ppaths:raise SystemExit('Falta cuotas_apuestatotal.json')
    nopa={bm:load_nopa(p) for bm,p in npaths.items()}
    pa={bm:load_pa(p) for bm,p in ppaths.items() if bm in {'apuestatotal','1xbet'}}
    mn={bm:os.path.getmtime(p) for bm,p in npaths.items()}
    mp={bm:os.path.getmtime(p) for bm,p in ppaths.items() if bm in {'apuestatotal','1xbet'}}
    pending={};alerts={};cooldown={}
    while True:
        t=time.time()
        for bm,p in ppaths.items():
            if bm not in {'apuestatotal','1xbet'}:continue
            try:m=os.path.getmtime(p)
            except:continue
            if m!=mp.get(bm):mp[bm]=m;pa[bm]=load_pa(p)
        changed=[];olds={}
        for bm,p in npaths.items():
            try:m=os.path.getmtime(p)
            except:continue
            if m!=mn.get(bm):mn[bm]=m;olds[bm]=nopa.get(bm,{});nopa[bm]=load_nopa(p);changed.append(bm)
        for bm in changed:
            if bm not in TRIGGERS:continue
            for event,nr in nopa[bm].items():
                orow=olds[bm].get(event)
                if not orow:continue
                for sel,(_,col) in SEL.items():
                    old,new=fnum(orow.get(col)),fnum(nr.get(col))
                    if not old or not new or new>=old:continue
                    cons,ncons=consensus(nopa,event,sel,bm)
                    if not is_breakaway(old,new,cons):continue
                    pkey=key_str(event)+'||'+sel
                    if cooldown.get(pkey,0)>t:continue
                    move={'ts':t,'old':old,'new':new,'drop':pct_drop(old,new),'consensus':cons,'nconsensus':ncons}
                    rec=pending.get(pkey)
                    if not rec or t-rec['first_ts']>MAX_CONFIRM_SEC:
                        pending[pkey]={'event':list(event),'sel':sel,'first_ts':t,'moves':{bm:move},'at_pa_base':quote(pa,'apuestatotal',event,sel),'x1_pa_base':quote(pa,'1xbet',event,sel)}
                        continue
                    if bm in rec['moves']:rec['moves'][bm]=move;continue
                    rec['moves'][bm]=move
                    if not TRIGGERS.issubset(rec['moves']):continue
                    if abs(rec['moves']['betsson']['ts']-rec['moves']['teapuesto']['ts'])>MAX_CONFIRM_SEC:continue
                    at0=rec.get('at_pa_base');at=quote(pa,'apuestatotal',event,sel)
                    if at0 is None or at is None:pending.pop(pkey,None);continue
                    if at<at0-1e-9:print('[TARDE]',pkey,at0,'->',at);pending.pop(pkey,None);continue
                    send_signal(rec,nopa,pa)
                    aid=f'{int(t)}_{abs(hash(pkey))}'
                    alerts[aid]={'id':aid,'event':list(event),'sel':sel,'alert_ts':t,'expires':t+RESULT_WINDOW_SEC,'at_pa':at,'x1_pa':quote(pa,'1xbet',event,sel),'moves':rec['moves']}
                    append_result({'type':'signal','time':now().isoformat(),**alerts[aid]})
                    cooldown[pkey]=t+COOLDOWN_SEC;pending.pop(pkey,None);save_state({'cooldown':cooldown})
        done=[]
        for aid,a in alerts.items():
            event=tuple(a['event']);cur=quote(pa,'apuestatotal',event,a['sel'])
            if cur is not None and cur<a['at_pa'] and pct_drop(a['at_pa'],cur)>=RESULT_MIN_DROP_PCT:
                append_result({'type':'result','result':'HIT','time':now().isoformat(),'alert_id':aid,'event':a['event'],'selection':a['sel'],'at_old':a['at_pa'],'at_new':cur,'drop_pct':pct_drop(a['at_pa'],cur),'elapsed_sec':t-a['alert_ts']})
                send_result(a,True,cur);done.append(aid);continue
            if t>=a['expires']:
                append_result({'type':'result','result':'MISS','time':now().isoformat(),'alert_id':aid,'event':a['event'],'selection':a['sel'],'at_old':a['at_pa'],'at_new':cur,'elapsed_sec':RESULT_WINDOW_SEC})
                send_result(a,False);done.append(aid)
        for aid in done:alerts.pop(aid,None)
        for k in list(pending):
            if t-pending[k]['first_ts']>MAX_CONFIRM_SEC:pending.pop(k,None)
        for k in list(cooldown):
            if cooldown[k]<=t:cooldown.pop(k,None)
        time.sleep(POLL_SEC)

if __name__=='__main__':main()