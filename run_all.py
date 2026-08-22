import subprocess
import datetime
import os

PYTHON = "/root/proyectos/Mancorabet/venv/bin/python3"
BASE_DIR = "/root/proyectos/Mancorabet"
DATA_DIR = os.path.join(BASE_DIR, "data")

SCRIPTS_EXTRACTORES = [
    # "cuotas_oddsapi.py",
    "cuotas_apuestatotal.py",
    "cuotas_doradobet.py",
    "cuotas_atlanticcity.py",
    "cuotas_olimpobet.py",
    "cuotas_gangabet.py",
    "cuotas_teapuesto.py",
    # "cuotas_stake2.py",
    "cuotas_1xbet.py",
    "cuotas_pinnacle.py",
    "cuotas_betsson.py",
    # "cuotas_betsafe.py",
    "cuotas_inkabet.py",
    "cuotas_betano.py",
]

SCRIPT_FUSION_PA = "fusionar_cuotas.py"
SCRIPT_FUSION_NOPA = "fusionar_cuotas_NoPA.py"

# ======================================
# ACTIVAR / DESACTIVAR MÓDULOS
# ======================================

EJECUTAR_SMART_ALERTS = True
EJECUTAR_HISTORICO_BET365 = False
EJECUTAR_MOVIMIENTOS_BET365 = False


def ejecutar_script(script):
    try:
        resultado = subprocess.run(
            [PYTHON, script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=BASE_DIR,
        )
        return (
            resultado.returncode,
            resultado.stdout or "",
            resultado.stderr or "",
        )
    except Exception as e:
        return 1, "", str(e)


def oddsapi_fallo(output):
    texto = output.lower()
    return (
        "error" in texto
        or "no se encontraron cuotas" in texto
        or "oddsapi no responde" in texto
        or "failed" in texto
        or "timeout" in texto
        or len(texto.strip()) == 0
    )


def imprimir_resultado(script, returncode, stdout, stderr):
    print(f"\n----- Resultado {script} -----")

    if stdout.strip():
        print(stdout)

    if stderr.strip():
        print("[STDERR]")
        print(stderr)

    if returncode != 0:
        print(f"[ERROR] {script} terminó con código {returncode}")
    else:
        print(f"[OK] {script} finalizó correctamente.")


def main():
    print("\n==============================")
    print(f"Iniciando ciclo {datetime.datetime.now()}")
    print("==============================\n")

    # Asegurar Xvfb para Betano (DISPLAY :99)
    os.system(
        "pgrep Xvfb >/dev/null || "
        "(Xvfb :99 -screen 0 1280x800x24 >/tmp/xvfb.log 2>&1 &)"
    )
    os.environ["DISPLAY"] = ":99"

    procesos = []

    # 1. Ejecutar extractores en paralelo
    print("[INFO] Ejecutando extractores de cuotas en paralelo...\n")

    for script in SCRIPTS_EXTRACTORES:
        full_path = os.path.join(BASE_DIR, script)
        print(f"[INFO] Lanzando: {script}")

        env = os.environ.copy()

        if script == "cuotas_betano.py":
            env["DISPLAY"] = ":99"
            env["BETANO_HEADFUL"] = "1"

        try:
            proceso = subprocess.Popen(
                [PYTHON, full_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                cwd=BASE_DIR,
            )
            procesos.append((script, proceso))
        except Exception as e:
            print(f"[ERROR] No se pudo lanzar {script}: {e}")

    for script, proceso in procesos:
        stdout, stderr = proceso.communicate()
        returncode = proceso.returncode
        output = (stdout or "") + "\n" + (stderr or "")

        imprimir_resultado(
            script,
            returncode,
            stdout or "",
            stderr or "",
        )

        if script == "cuotas_oddsapi.py" and oddsapi_fallo(output):
            ruta_odds = os.path.join(DATA_DIR, "cuotas_oddsapi.json")

            print(
                "[WARN] OddsAPI falló — eliminando archivo "
                "cuotas_oddsapi.json..."
            )

            try:
                if os.path.exists(ruta_odds):
                    os.remove(ruta_odds)
                    print("[OK] Archivo cuotas_oddsapi.json eliminado.")
                else:
                    print("[INFO] No existía archivo antiguo.")
            except Exception as e:
                print(f"[ERROR] No se pudo eliminar archivo OddsAPI: {e}")

    # 2. Fusión PA
    print("\n[INFO] Ejecutando fusión PA → cuotas.json...\n")

    fusion_pa_path = os.path.join(BASE_DIR, SCRIPT_FUSION_PA)
    returncode, stdout, stderr = ejecutar_script(fusion_pa_path)

    imprimir_resultado(
        SCRIPT_FUSION_PA,
        returncode,
        stdout,
        stderr,
    )

    # 3. Fusión NoPA
    print("\n[INFO] Ejecutando fusión NoPA → cuotas_NoPA.json...\n")

    fusion_nopa_path = os.path.join(BASE_DIR, SCRIPT_FUSION_NOPA)
    returncode, stdout, stderr = ejecutar_script(fusion_nopa_path)

    imprimir_resultado(
        SCRIPT_FUSION_NOPA,
        returncode,
        stdout,
        stderr,
    )

    # 4. Smart Alerts
    if EJECUTAR_SMART_ALERTS:
        print("\n[INFO] Lanzando: smart_alerts.py")
        returncode, stdout, stderr = ejecutar_script(
            os.path.join(BASE_DIR, "smart_alerts.py")
        )
        imprimir_resultado("smart_alerts.py", returncode, stdout, stderr)

    # 5. Histórico Bet365
    if EJECUTAR_HISTORICO_BET365:
        print("\n[INFO] Histórico Bet365")
        returncode, stdout, stderr = ejecutar_script(
            os.path.join(BASE_DIR, "historico_bet365.py")
        )
        imprimir_resultado("historico_bet365.py", returncode, stdout, stderr)

    # 6. Movimientos Bet365
    if EJECUTAR_MOVIMIENTOS_BET365:
        print("\n[INFO] Movimientos bruscos Bet365")
        returncode, stdout, stderr = ejecutar_script(
            os.path.join(BASE_DIR, "movimientos_bet365.py")
        )
        imprimir_resultado("movimientos_bet365.py", returncode, stdout, stderr)

    print("\n==============================")
    print(
        "Ciclo completado a las "
        f"{datetime.datetime.now().strftime('%H:%M:%S')}"
    )
    print("==============================\n")


if __name__ == "__main__":
    main()