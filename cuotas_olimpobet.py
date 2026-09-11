import json,os,time,random,threading
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timedelta,timezone
import requests

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
DATA_DIR=os.path.join(BASE_DIR,"data")
DEBUG_DIR=os.path.join(DATA_DIR,"debug_olimpobet")
os.makedirs(DATA_DIR,exist_ok=True)
os.makedirs(DEBUG_DIR,exist_ok=True)
OUTPUT_FILE=os.path.join(DATA_DIR,"cuotas_olimpobet.json")

BASE_LIST="https://us1.offering-api.kambicdn.com/offering/v2018/nexuspe/listView"
BASE_EVENT="https://us.offering-api.kambicdn.com/offering/v2018/nexuspe/prepackcoupon/event"

CASA="Olimpobet"
HORAS_ADELANTE=72
MAX_WORKERS_LIGAS=8
MAX_WORKERS_EVENTOS=4
TIMEOUT_LISTADO=25
TIMEOUT_EVENTO=25
MAX_INTENTOS_LISTADO=3
MAX_INTENTOS_EVENTO=4
INTERVALO_EVENTOS=0.07
MAX_FALLOS_PARA_GUARDAR=0.20

HEADERS={
    "accept":"application/json, text/javascript, */*; q=0.01",
    "accept-language":"es-US,es-PE;q=0.9,es-419;q=0.8,es;q=0.7,en;q=0.6",
    "cache-control":"no-cache",
    "origin":"https://www.olimpo.bet",
    "pragma":"no-cache",
    "priority":"u=1, i",
    "referer":"https://www.olimpo.bet/",
    "sec-ch-ua":'"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
    "sec-ch-ua-mobile":"?0",
    "sec-ch-ua-platform":'"Windows"',
    "sec-fetch-dest":"empty",
    "sec-fetch-mode":"cors",
    "sec-fetch-site":"cross-site",
    "user-agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
}

LIGAS_OLIMPO=[
    ("Premier League","football/england/premier_league",False),
    ("FA Cup","football/england/fa_cup",False),
    ("EFL Cup","football/england/efl_cup",False),
    ("La Liga","football/spain/la_liga",False),
    ("Copa del Rey","football/spain/copa_del_rey",False),
    ("Serie A","football/italy/serie_a",False),
    ("Bundesliga","football/germany/bundesliga",False),
    ("Copa Alemana","football/germany/dfb_pokal",False),
    ("Ligue 1","football/france/ligue_1",False),
    ("Copa Francia","football/france/coupe_de_france",False),
    ("Brasileirao","football/brazil/brasileirao_serie_a",False),
    ("Copa de Brasil","football/brazil/copa_do_brasil",False),
    ("MLS","football/usa/mls",False),
    ("Liga MX","football/mexico/liga_mx",False),
    ("Liga 1 Perú","football/peru/liga_1",False),
    ("Primeira Liga","football/portugal/primeira_liga",False),
    ("UEFA Champions League","football/champions_league",True),
    ("UEFA Europa League","football/europa_league",True),
    ("UEFA Conference League","football/conference_league",True),
    ("Copa Libertadores","football/copa_libertadores",True),
    ("Copa Sudamericana","football/copa_sudamericana",True),
    ("Eliminatorias Europa - WC26","football/world_cup_qualifying_-_europe",True),
]

request_lock=threading.Lock()
stats_lock=threading.Lock()
next_request_at=0.0
cooldown_until=0.0
stats={"detalle_ok":0,"detalle_fallo":0,"429":0}

def save_json(path,data):
    tmp=path+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(data,f,indent=2,ensure_ascii=False)
    os.replace(tmp,path)

def odds_to_float(value):
    if value is None:return None
    try:
        odds=float(value)/1000
        return round(odds,3) if odds>1 else None
    except (TypeError,ValueError):return None

def parse_fecha(start_iso):
    try:return datetime.fromisoformat(start_iso.replace("Z","+00:00")).strftime("%Y-%m-%dT%H:%M:%S.000")
    except Exception:return start_iso

def fecha_to_dt_utc(start_iso):
    try:return datetime.fromisoformat(start_iso.replace("Z","+00:00")).astimezone(timezone.utc)
    except Exception:return None

def es_en_vivo(evt,event_info):
    state=str(event_info.get("state","")).upper()
    return state in ("STARTED","LIVE","IN_PROGRESS") or event_info.get("live") is True or event_info.get("inPlay") is True or evt.get("live") is True

def get_outcome_side(outcome):
    label=str(outcome.get("label","")).strip().upper()
    english=str(outcome.get("englishLabel","")).strip().upper()
    outcome_label=str(outcome.get("outcomeLabel","")).strip().upper()
    tipo=str(outcome.get("type","")).strip().upper()
    if label in ("1","X","2"):return label
    if english in ("1","X","2"):return english
    if outcome_label in ("1","X","2"):return outcome_label
    if tipo=="OT_ONE":return "1"
    if tipo=="OT_CROSS":return "X"
    if tipo=="OT_TWO":return "2"
    return None

def normalizar_nombre_mercado(value):
    return str(value or "").strip().lower().replace("–","-").replace("—","-")

def evento_en_ventana(evt,now_utc,cutoff_utc):
    event_info=evt.get("event",{}) or {}
    if not event_info or es_en_vivo(evt,event_info):return False
    dt=fecha_to_dt_utc(event_info.get("start",""))
    return dt is not None and now_utc<dt<=cutoff_utc

def esperar_turno():
    global next_request_at
    while True:
        with request_lock:
            ahora=time.monotonic()
            objetivo=max(next_request_at,cooldown_until)
            espera=objetivo-ahora
            if espera<=0:
                next_request_at=ahora+INTERVALO_EVENTOS
                return
        time.sleep(min(espera,1.0))

def activar_cooldown(segundos):
    global cooldown_until
    with request_lock:
        nuevo=time.monotonic()+segundos
        if nuevo>cooldown_until:cooldown_until=nuevo

def retry_after_seconds(response,intento):
    valor=response.headers.get("Retry-After")
    if valor:
        try:return max(1.0,float(valor))
        except Exception:pass
    return min(15.0,2**intento)+random.uniform(0.2,0.8)

def fetch_event_detail(event_id):
    url=f"{BASE_EVENT}/{event_id}.json"
    ultimo_error=None
    vio_429=False
    for intento in range(1,MAX_INTENTOS_EVENTO+1):
        esperar_turno()
        params={"lang":"es_PE","market":"PE","client_id":200,"channel_id":1,"ncid":int(time.time()*1000)}
        try:
            r=requests.get(url,headers=HEADERS,params=params,timeout=TIMEOUT_EVENTO)
            if r.status_code==200:
                with stats_lock:stats["detalle_ok"]+=1
                return r.json()
            if r.status_code==429:
                vio_429=True
                with stats_lock:stats["429"]+=1
                espera=retry_after_seconds(r,intento)
                activar_cooldown(espera)
                ultimo_error=f"HTTP 429"
            else:
                ultimo_error=f"HTTP {r.status_code}: {r.text[:200]}"
        except (requests.RequestException,ValueError) as e:
            ultimo_error=str(e)
        if intento<MAX_INTENTOS_EVENTO and not vio_429:
            time.sleep(min(intento,3)+random.uniform(0.1,0.4))
    with stats_lock:stats["detalle_fallo"]+=1
    print(f"   X Detalle {event_id}: {ultimo_error}")
    return None

def extraer_cuotas_desde_detail(detail,event_id=None):
    cuota1_normal=cuotaX_normal=cuota2_normal=None
    cuota1_pago=cuotaX_pago=cuota2_pago=None
    for betoffer in detail.get("betOffers",[]) or []:
        criterion=betoffer.get("criterion",{}) or {}
        mercado=normalizar_nombre_mercado(criterion.get("label",""))
        mercado_en=normalizar_nombre_mercado(criterion.get("englishLabel",""))
        outcomes=betoffer.get("outcomes",[]) or []
        es_normal=mercado=="resultado final" or mercado_en=="full time"
        if es_normal:
            for outcome in outcomes:
                side=get_outcome_side(outcome)
                odds=odds_to_float(outcome.get("odds"))
                if odds is None:continue
                if side=="1":cuota1_normal=odds
                elif side=="X":cuotaX_normal=odds
                elif side=="2":cuota2_normal=odds
            continue
        es_pago="pago anticipado" in mercado or "2up" in mercado_en or "2 up" in mercado_en
        if es_pago:
            for outcome in outcomes:
                side=get_outcome_side(outcome)
                odds=odds_to_float(outcome.get("odds"))
                if odds is None:continue
                if side=="1":cuota1_pago=odds
                elif side=="X":cuotaX_pago=odds
                elif side=="2":cuota2_pago=odds
    empates=[x for x in (cuotaX_normal,cuotaX_pago) if x is not None]
    return {
        "cuota1":cuota1_pago,
        "cuotaX":max(empates) if empates else None,
        "cuota2":cuota2_pago,
        "cuota1_normal":cuota1_normal,
        "cuotaX_normal":cuotaX_normal,
        "cuota2_normal":cuota2_normal,
        "cuota1_pago":cuota1_pago,
        "cuotaX_pago":cuotaX_pago,
        "cuota2_pago":cuota2_pago,
        "tiene_resultado_normal":cuota1_normal is not None and cuotaX_normal is not None and cuota2_normal is not None,
        "tiene_pago_anticipado":cuota1_pago is not None and cuota2_pago is not None,
    }

def parse_event(evt,liga_nombre,now_utc,cutoff_utc):
    event_info=evt.get("event",{}) or {}
    if not event_info:return None
    home=event_info.get("homeName")
    away=event_info.get("awayName")
    start=event_info.get("start","")
    event_id=event_info.get("id")
    if not home or not away or not start or not event_id:return None
    if es_en_vivo(evt,event_info):return None
    dt=fecha_to_dt_utc(start)
    if dt is None or not(now_utc<dt<=cutoff_utc):return None
    detail=fetch_event_detail(event_id)
    if not detail:return None
    cuotas=extraer_cuotas_desde_detail(detail,event_id)
    if cuotas["cuotaX"] is None:
        print(f"   X Sin empate disponible: {home} vs {away}")
        return None
    return {
        "Liga":liga_nombre,
        "Partido":f"{home} vs {away}",
        "Fecha":parse_fecha(start),
        "Casa":CASA,
        "Local":home,
        "Visita":away,
        "Cuota Local":cuotas["cuota1"],
        "Cuota Empate":cuotas["cuotaX"],
        "Cuota Visita":cuotas["cuota2"],
        "Cuota Local NoPA":cuotas["cuota1_normal"],
        "Cuota Visita NoPA":cuotas["cuota2_normal"],
        "EventId":event_id,
    }

def fetch_liga(nombre,path,internacional):
    if internacional:
        url=f"{BASE_LIST}/{path}/all/all/matches.json"
        params={"client_id":200,"channel_id":1,"lang":"es_PE","market":"PE","useCombined":"true","useCombinedLive":"true"}
    else:
        url=f"{BASE_LIST}/{path}/all/matches.json"
        params={"client_id":200,"channel_id":1,"lang":"es_PE","market":"PE"}
    ultimo_error=None
    for intento in range(1,MAX_INTENTOS_LISTADO+1):
        try:
            r=requests.get(url,headers=HEADERS,params=params,timeout=TIMEOUT_LISTADO)
            if r.status_code==200:
                data=r.json()
                return {"ok":True,"events":data.get("events",[]) or [],"error":None}
            ultimo_error=f"HTTP {r.status_code}: {r.text[:300]}"
        except (requests.RequestException,ValueError) as e:
            ultimo_error=str(e)
        if intento<MAX_INTENTOS_LISTADO:time.sleep(intento)
    return {"ok":False,"events":[],"error":ultimo_error}

def main():
    global stats,next_request_at,cooldown_until
    started=time.perf_counter()
    stats={"detalle_ok":0,"detalle_fallo":0,"429":0}
    next_request_at=0.0
    cooldown_until=0.0
    now_utc=datetime.now(timezone.utc)
    cutoff_utc=now_utc+timedelta(hours=HORAS_ADELANTE)
    print("\nOlimpoBet: descargando cuotas...")

    candidatos={}
    ligas_ok=0
    ligas_error=0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS_LIGAS) as executor:
        futures={
            executor.submit(fetch_liga,nombre,path,internacional):nombre
            for nombre,path,internacional in LIGAS_OLIMPO
        }
        for future in as_completed(futures):
            nombre=futures[future]
            try:
                result=future.result()
            except Exception as e:
                print(f"X {nombre}: {e}")
                ligas_error+=1
                continue
            if not result["ok"]:
                print(f"X {nombre}: {result['error']}")
                ligas_error+=1
                continue
            ligas_ok+=1
            for evt in result["events"]:
                if not evento_en_ventana(evt,now_utc,cutoff_utc):continue
                info=evt.get("event",{}) or {}
                event_id=info.get("id")
                if not event_id:continue
                key=str(event_id)
                if key not in candidatos:candidatos[key]=(evt,nombre)

    print(f"   Listados: {ligas_ok} OK / {ligas_error} error | {len(candidatos)} eventos únicos")

    resultados=[]
    if candidatos:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS_EVENTOS,len(candidatos))) as executor:
            futures=[
                executor.submit(parse_event,evt,liga,now_utc,cutoff_utc)
                for evt,liga in candidatos.values()
            ]
            for future in as_completed(futures):
                try:
                    item=future.result()
                    if item:resultados.append(item)
                except Exception as e:
                    print(f"   X Error evento: {e}")

    resultados.sort(key=lambda x:(x.get("Fecha",""),x.get("Liga",""),x.get("Partido","")))
    total_detalles=stats["detalle_ok"]+stats["detalle_fallo"]
    ratio_fallos=(stats["detalle_fallo"]/total_detalles) if total_detalles else 0.0
    guardar=True
    motivo=None

    if candidatos and total_detalles==0:
        guardar=False
        motivo="no se pudo consultar ningún detalle"
    elif total_detalles and ratio_fallos>MAX_FALLOS_PARA_GUARDAR:
        guardar=False
        motivo=f"{ratio_fallos*100:.0f}% de detalles fallaron"
    elif candidatos and not resultados and stats["detalle_fallo"]>0:
        guardar=False
        motivo="no hubo resultados válidos por fallos de red/API"

    if guardar:
        save_json(OUTPUT_FILE,resultados)
    else:
        print(f"⚠ Olimpobet: NO se reemplaza cuotas_olimpobet.json ({motivo}).")
        print("   Se conserva el último archivo válido.")

    elapsed=time.perf_counter()-started
    con_pago=sum(1 for x in resultados if x.get("Cuota Local") is not None and x.get("Cuota Visita") is not None)
    sin_pago=len(resultados)-con_pago
    print(
        f"OlimpoBet {'OK' if guardar else 'PARCIAL'}: {len(resultados)} partidos | "
        f"PA: {con_pago} | NoPA: {sin_pago} | "
        f"Detalles OK: {stats['detalle_ok']} | Fallos: {stats['detalle_fallo']} | "
        f"429 recibidos: {stats['429']} | {elapsed:.2f}s"
    )

if __name__=="__main__":
    main()