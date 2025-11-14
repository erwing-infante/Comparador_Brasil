import subprocess
import time
import datetime
import os

SCRIPTS_EXTRACTORES = [
    "cuotas_oddsapi.py",
    "cuotas_apuestatotal.py",
    "cuotas_doradobet.py",
    "cuotas_atlanticcity.py"
]

SCRIPT_FUSION = "fusionar_cuotas.py"

def ejecutar_script(script):
    try:
        resultado = subprocess.run(
            ["python", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return resultado.stdout, resultado.stderr
    except Exception as e:
        return "", str(e)

def main():
    print("\n==============================")
    print(f"Iniciando ciclo {datetime.datetime.now()}")
    print("==============================\n")

    procesos = []

    # 1️⃣ Ejecutar extractores EN PARALELO
    print("[INFO] Ejecutando extractores de cuotas en paralelo...\n")

    for script in SCRIPTS_EXTRACTORES:
        print(f"[INFO] Lanzando: {script}")
        p = subprocess.Popen(
            ["python", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        procesos.append((script, p))

    # 2️⃣ Esperar a que TODOS terminen
    for script, p in procesos:
        stdout, stderr = p.communicate()
        print(f"\n----- Resultado {script} -----")
        if stderr:
            print("[ERROR]:")
            print(stderr)
        else:
            print(stdout)

    # 3️⃣ Ejecutar fusión SOLO cuando ya terminaron
    print("\n[INFO] Ejecutando fusión final...\n")
    stdout, stderr = ejecutar_script(SCRIPT_FUSION)

    print("----- Resultado fusionar_cuotas.py -----")
    if stderr:
        print("[ERROR]:")
        print(stderr)
    else:
        print(stdout)

    print("\n==============================")
    print(f"Ciclo completado correctamente a las {datetime.datetime.now().strftime('%H:%M:%S')}")
    print("==============================\n")


if __name__ == "__main__":
    main()
