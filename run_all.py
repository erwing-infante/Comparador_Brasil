import subprocess
import time
import datetime
import os

PYTHON = "/root/proyectos/Mancorabet/venv/bin/python3"
BASE_DIR = "/root/proyectos/Mancorabet"
DATA_DIR = os.path.join(BASE_DIR, "data")

SCRIPTS_EXTRACTORES = [
    "cuotas_oddsapi.py",
    "cuotas_apuestatotal.py",
    "cuotas_doradobet.py",
    "cuotas_atlanticcity.py",
    "cuotas_olimpobet.py",
    "cuotas_gangabet.py"
]

SCRIPT_FUSION = "fusionar_cuotas.py"


def ejecutar_script(script):
    try:
        resultado = subprocess.run(
            [PYTHON, script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        return resultado.stdout, resultado.stderr
    except Exception as e:
        return "", str(e)


def oddsapi_fallo(output):
    """Detecta si OddsAPI falló para borrar archivo viejo."""
    texto = output.lower()
    return (
        "error" in texto or
        "no se encontraron cuotas" in texto or
        "oddsapi no responde" in texto or
        "failed" in texto or
        "timeout" in texto or
        len(texto.strip()) == 0
    )


def main():

    print("\n==============================")
    print(f"Iniciando ciclo {datetime.datetime.now()}")
    print("==============================\n")

    procesos = []

    # 1️⃣ Ejecutar extractores EN PARALELO
    print("[INFO] Ejecutando extractores de cuotas en paralelo...\n")

    for script in SCRIPTS_EXTRACTORES:
        full_path = os.path.join(BASE_DIR, script)
        print(f"[INFO] Lanzando: {script}")

        p = subprocess.Popen(
            [PYTHON, full_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        procesos.append((script, p))

    # Procesar resultados de extractores
    for script, p in procesos:
        stdout, stderr = p.communicate()

        print(f"\n----- Resultado {script} -----")

        output = (stdout or "") + "\n" + (stderr or "")
        print(output)

        # 🟨 Si OddsAPI falló → borrar archivo viejo
        if script == "cuotas_oddsapi.py" and oddsapi_fallo(output):
            ruta_odds = os.path.join(DATA_DIR, "cuotas_oddsapi.json")

            print("[WARN] OddsAPI falló — eliminando archivo cuotas_oddsapi.json...")

            try:
                if os.path.exists(ruta_odds):
                    os.remove(ruta_odds)
                    print("[OK] Archivo cuotas_oddsapi.json eliminado.")
                else:
                    print("[INFO] No existía archivo antiguo.")
            except Exception as e:
                print(f"[ERROR] No se pudo eliminar archivo OddsAPI: {e}")

    # 2️⃣ Ejecutar FUSIÓN → genera cuotas.json actualizado
    print("\n[INFO] Ejecutando fusión final...\n")
    fusion_path = os.path.join(BASE_DIR, SCRIPT_FUSION)
    stdout, stderr = ejecutar_script(fusion_path)

    print("----- Resultado fusionar_cuotas.py -----")
    if stderr:
        print("[ERROR]:")
        print(stderr)
    else:
        print(stdout)

    # =============================================
    # 3️⃣ SMART ALERTS (ahora sí con cuotas.json actualizado)
    # =============================================
    print("[INFO] Lanzando: smart_alerts.py")
    os.system(f"{PYTHON} smart_alerts.py")

    # =============================================
    # 4️⃣ HISTORICO BET365
    # =============================================
    print("[INFO] Histórico Bet365")
    os.system(f"{PYTHON} historico_bet365.py")

    # =============================================
    # 5️⃣ MOVIMIENTOS BET365
    # =============================================
    print("[INFO] Movimientos bruscos Bet365")
    os.system(f"{PYTHON} movimientos_bet365.py")

    print("\n==============================")
    print(f"Ciclo completado a las {datetime.datetime.now().strftime('%H:%M:%S')}")
    print("==============================\n")


if __name__ == "__main__":
    main()