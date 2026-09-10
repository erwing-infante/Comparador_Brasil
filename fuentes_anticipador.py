import os,time,subprocess,threading,datetime,signal

BASE="/root/proyectos/Mancorabet"
PYTHON=os.path.join(BASE,"venv/bin/python3")
PAUSA=2
SCRIPTS=[
    "cuotas_apuestatotal.py",
    "cuotas_atlanticcity.py",
    "cuotas_olimpobet.py",
    "cuotas_teapuesto.py",
    "cuotas_1xbet.py",
    "cuotas_pinnacle.py",
]
stop=False

def worker(script):
    global stop
    path=os.path.join(BASE,script)
    while not stop:
        ini=time.time()
        try:
            print(f"[{datetime.datetime.now():%H:%M:%S}] INICIO {script}",flush=True)
            p=subprocess.run([PYTHON,path],cwd=BASE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,errors="replace")
            d=time.time()-ini
            if p.returncode==0:
                print(f"[{datetime.datetime.now():%H:%M:%S}] OK {script} {d:.1f}s",flush=True)
            else:
                print(f"[{datetime.datetime.now():%H:%M:%S}] ERROR {script} rc={p.returncode} {d:.1f}s {p.stderr[-500:]}",flush=True)
        except Exception as e:
            print(f"[ERROR] {script}: {e}",flush=True)
        if not stop:time.sleep(PAUSA)

def salir(*_):
    global stop
    stop=True

def main():
    signal.signal(signal.SIGTERM,salir)
    signal.signal(signal.SIGINT,salir)
    print("MANCORABET - EXTRACTORES INDEPENDIENTES",flush=True)
    hs=[]
    for s in SCRIPTS:
        h=threading.Thread(target=worker,args=(s,))
        h.start();hs.append(h);time.sleep(.2)
    for h in hs:h.join()

if __name__=="__main__":main()