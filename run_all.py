import subprocess
import datetime
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


PYTHON = "/root/proyectos/Mancorabet/venv/bin/python3"
BASE_DIR = "/root/proyectos/Mancorabet"
DATA_DIR = os.path.join(BASE_DIR, "data")


# ============================================================
# CASAS DE APUESTAS
# ============================================================

SCRIPTS_EXTRACTORES = [
    # "cuotas_oddsapi.py",

    "cuotas_apuestatotal.py",
    # "cuotas_doradobet.py",
    "cuotas_atlanticcity.py",
    "cuotas_olimpobet.py",
    # "cuotas_gangabet.py",
    "cuotas_teapuesto.py",
    # "cuotas_stake2.py",
    "cuotas_1xbet.py",
    "cuotas_pinnacle.py",
    #"cuotas_betsson.py",
    # "cuotas_tinbet.py",
    # "cuotas_inkabet.py",
    "cuotas_betano.py",
]


SCRIPT_FUSION_PA = "fusionar_cuotas.py"
SCRIPT_FUSION_NOPA = "fusionar_cuotas_NoPA.py"


# ============================================================
# ACTIVAR / DESACTIVAR MÓDULOS
# ============================================================

EJECUTAR_SMART_ALERTS = True
EJECUTAR_SMART_ALERTS_NOPA = True

EJECUTAR_HISTORICO_BET365 = False
EJECUTAR_MOVIMIENTOS_BET365 = False


# ============================================================
# UTILIDADES
# ============================================================

def formato_tiempo(segundos):
    if segundos < 60:
        return f"{segundos:.2f} s"

    minutos = int(segundos // 60)
    segundos_restantes = segundos % 60

    return f"{minutos} min {segundos_restantes:.2f} s"


def ejecutar_script(script):
    inicio = time.perf_counter()

    try:
        resultado = subprocess.run(
            [PYTHON, script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=BASE_DIR,
        )

        duracion = time.perf_counter() - inicio

        return (
            resultado.returncode,
            resultado.stdout or "",
            resultado.stderr or "",
            duracion,
        )

    except Exception as e:
        duracion = time.perf_counter() - inicio

        return (
            1,
            "",
            str(e),
            duracion,
        )


def esperar_proceso(script, proceso, inicio):
    try:
        stdout, stderr = proceso.communicate()

        returncode = proceso.returncode
        duracion = time.perf_counter() - inicio

        return (
            script,
            returncode,
            stdout or "",
            stderr or "",
            duracion,
        )

    except Exception as e:
        duracion = time.perf_counter() - inicio

        return (
            script,
            1,
            "",
            str(e),
            duracion,
        )


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


def imprimir_resultado(
    script,
    returncode,
    stdout,
    stderr,
    duracion=None,
):
    print(f"\n----- Resultado {script} -----")

    if stdout.strip():
        print(stdout)

    if stderr.strip():
        print("[STDERR]")
        print(stderr)

    if returncode != 0:
        print(
            f"[ERROR] {script} terminó con código "
            f"{returncode}"
        )
    else:
        print(
            f"[OK] {script} finalizó correctamente."
        )

    if duracion is not None:
        print(
            f"[TIEMPO] {script}: "
            f"{formato_tiempo(duracion)}"
        )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    inicio_ciclo = time.perf_counter()
    hora_inicio = datetime.datetime.now()

    print("\n")
    print("=" * 70)
    print(
        f"INICIANDO CICLO: "
        f"{hora_inicio.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    print("=" * 70)
    print()

    tiempos_casas = {}
    tiempos_modulos = {}


    # ========================================================
    # XVFB BETANO
    # ========================================================

    print("[INFO] Verificando Xvfb para Betano...")

    os.system(
        "pgrep Xvfb >/dev/null || "
        "(Xvfb :99 -screen 0 1280x800x24 "
        ">/tmp/xvfb.log 2>&1 &)"
    )

    os.environ["DISPLAY"] = ":99"


    # ========================================================
    # 1. EXTRACTORES EN PARALELO
    # ========================================================

    print()
    print("=" * 70)
    print("EJECUTANDO CASAS DE APUESTAS EN PARALELO")
    print("=" * 70)
    print()

    inicio_extractores = time.perf_counter()

    procesos = []


    # --------------------------------------------------------
    # LANZAR TODOS LOS SCRAPERS
    # --------------------------------------------------------

    for script in SCRIPTS_EXTRACTORES:

        full_path = os.path.join(
            BASE_DIR,
            script,
        )

        print(
            f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
            f"[INICIO] {script}"
        )

        env = os.environ.copy()

        if script == "cuotas_betano.py":
            env["DISPLAY"] = ":99"
            env["BETANO_HEADFUL"] = "1"

        try:

            inicio_individual = time.perf_counter()

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

            procesos.append(
                (
                    script,
                    proceso,
                    inicio_individual,
                )
            )

        except Exception as e:

            print(
                f"[ERROR] No se pudo lanzar "
                f"{script}: {e}"
            )

            tiempos_casas[script] = 0


    # --------------------------------------------------------
    # ESPERAR TODOS EN PARALELO
    # --------------------------------------------------------

    max_workers = max(
        1,
        len(procesos),
    )

    with ThreadPoolExecutor(
        max_workers=max_workers
    ) as executor:

        futuros = []

        for (
            script,
            proceso,
            inicio_individual,
        ) in procesos:

            futuro = executor.submit(
                esperar_proceso,
                script,
                proceso,
                inicio_individual,
            )

            futuros.append(futuro)


        for futuro in as_completed(futuros):

            (
                script,
                returncode,
                stdout,
                stderr,
                duracion,
            ) = futuro.result()

            tiempos_casas[script] = duracion

            print()
            print(
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
                f"[FIN] {script}"
            )

            imprimir_resultado(
                script,
                returncode,
                stdout,
                stderr,
                duracion,
            )


            output = (
                (stdout or "")
                + "\n"
                + (stderr or "")
            )

            if (
                script == "cuotas_oddsapi.py"
                and oddsapi_fallo(output)
            ):

                ruta_odds = os.path.join(
                    DATA_DIR,
                    "cuotas_oddsapi.json",
                )

                print(
                    "[WARN] OddsAPI falló — "
                    "eliminando archivo antiguo..."
                )

                try:

                    if os.path.exists(ruta_odds):

                        os.remove(ruta_odds)

                        print(
                            "[OK] cuotas_oddsapi.json "
                            "eliminado."
                        )

                    else:

                        print(
                            "[INFO] No existía "
                            "archivo antiguo."
                        )

                except Exception as e:

                    print(
                        "[ERROR] No se pudo "
                        "eliminar OddsAPI: "
                        f"{e}"
                    )


    tiempo_extractores = (
        time.perf_counter()
        - inicio_extractores
    )


    # ========================================================
    # 2. FUSIONES PA + NoPA EN PARALELO
    # ========================================================

    print()
    print("=" * 70)
    print("FUSIONES PA + NoPA EN PARALELO")
    print("=" * 70)
    print()

    inicio_fusiones = time.perf_counter()

    fusiones = {
        "Fusion PA": os.path.join(
            BASE_DIR,
            SCRIPT_FUSION_PA,
        ),
        "Fusion NoPA": os.path.join(
            BASE_DIR,
            SCRIPT_FUSION_NOPA,
        ),
    }


    with ThreadPoolExecutor(
        max_workers=2
    ) as executor:

        futuros_fusiones = {
            executor.submit(
                ejecutar_script,
                script_path,
            ): (
                nombre,
                script_path,
            )
            for nombre, script_path in fusiones.items()
        }


        for futuro in as_completed(
            futuros_fusiones
        ):

            nombre, script_path = (
                futuros_fusiones[futuro]
            )

            (
                returncode,
                stdout,
                stderr,
                duracion,
            ) = futuro.result()

            tiempos_modulos[nombre] = duracion

            print()
            print(
                f"[{datetime.datetime.now().strftime('%H:%M:%S')}] "
                f"[FIN] {nombre}"
            )

            imprimir_resultado(
                os.path.basename(script_path),
                returncode,
                stdout,
                stderr,
                duracion,
            )


    tiempo_fusiones = (
        time.perf_counter()
        - inicio_fusiones
    )

    tiempos_modulos[
        "Fusiones paralelo TOTAL"
    ] = tiempo_fusiones


    # ========================================================
    # 3. SMART ALERTS PA
    # ========================================================

    if EJECUTAR_SMART_ALERTS:

        print()
        print("=" * 70)
        print("BOT SMART ALERTS PA")
        print("=" * 70)

        script = os.path.join(
            BASE_DIR,
            "smart_alerts.py",
        )

        (
            returncode,
            stdout,
            stderr,
            duracion,
        ) = ejecutar_script(script)

        tiempos_modulos[
            "Bot Smart Alerts PA"
        ] = duracion

        imprimir_resultado(
            "smart_alerts.py",
            returncode,
            stdout,
            stderr,
            duracion,
        )


    # ========================================================
    # 4. SMART ALERTS NoPA
    # ========================================================

    if EJECUTAR_SMART_ALERTS_NOPA:

        print()
        print("=" * 70)
        print("BOT SMART ALERTS NoPA")
        print("=" * 70)

        script = os.path.join(
            BASE_DIR,
            "smart_alerts_nopa.py",
        )

        (
            returncode,
            stdout,
            stderr,
            duracion,
        ) = ejecutar_script(script)

        tiempos_modulos[
            "Bot Smart Alerts NoPA"
        ] = duracion

        imprimir_resultado(
            "smart_alerts_nopa.py",
            returncode,
            stdout,
            stderr,
            duracion,
        )


    # ========================================================
    # 5. HISTÓRICO BET365
    # ========================================================

    if EJECUTAR_HISTORICO_BET365:

        print()
        print("=" * 70)
        print("HISTÓRICO BET365")
        print("=" * 70)

        script = os.path.join(
            BASE_DIR,
            "historico_bet365.py",
        )

        (
            returncode,
            stdout,
            stderr,
            duracion,
        ) = ejecutar_script(script)

        tiempos_modulos[
            "Historico Bet365"
        ] = duracion

        imprimir_resultado(
            "historico_bet365.py",
            returncode,
            stdout,
            stderr,
            duracion,
        )


    # ========================================================
    # 6. MOVIMIENTOS BET365
    # ========================================================

    if EJECUTAR_MOVIMIENTOS_BET365:

        print()
        print("=" * 70)
        print("MOVIMIENTOS BET365")
        print("=" * 70)

        script = os.path.join(
            BASE_DIR,
            "movimientos_bet365.py",
        )

        (
            returncode,
            stdout,
            stderr,
            duracion,
        ) = ejecutar_script(script)

        tiempos_modulos[
            "Movimientos Bet365"
        ] = duracion

        imprimir_resultado(
            "movimientos_bet365.py",
            returncode,
            stdout,
            stderr,
            duracion,
        )


    # ========================================================
    # FIN CICLO
    # ========================================================

    tiempo_total = (
        time.perf_counter()
        - inicio_ciclo
    )

    hora_fin = datetime.datetime.now()


    # ========================================================
    # RESUMEN CASAS
    # ========================================================

    print()
    print()
    print("=" * 70)
    print("RESUMEN DE TIEMPOS - CASAS DE APUESTAS")
    print("=" * 70)
    print()


    casas_ordenadas = sorted(
        tiempos_casas.items(),
        key=lambda x: x[1],
        reverse=True,
    )


    for script, segundos in casas_ordenadas:

        marca = ""

        if segundos >= 60:
            marca = "  <-- LENTO"

        print(
            f"{script:<32} "
            f"{formato_tiempo(segundos):>18}"
            f"{marca}"
        )


    print()
    print("-" * 70)

    print(
        f"{'FASE EXTRACTORES':<32} "
        f"{formato_tiempo(tiempo_extractores):>18}"
    )


    # ========================================================
    # RESUMEN FUSIONES + BOTS
    # ========================================================

    print()
    print("=" * 70)
    print("RESUMEN DE TIEMPOS - FUSIONES Y BOTS")
    print("=" * 70)
    print()


    for modulo, segundos in tiempos_modulos.items():

        print(
            f"{modulo:<32} "
            f"{formato_tiempo(segundos):>18}"
        )


    # ========================================================
    # RESUMEN GENERAL
    # ========================================================

    print()
    print("=" * 70)
    print("RESUMEN GENERAL")
    print("=" * 70)
    print()

    print(
        f"Inicio ciclo:  "
        f"{hora_inicio.strftime('%H:%M:%S')}"
    )

    print(
        f"Fin ciclo:     "
        f"{hora_fin.strftime('%H:%M:%S')}"
    )

    print()

    print(
        f"TIEMPO TOTAL DEL CICLO: "
        f"{formato_tiempo(tiempo_total)}"
    )

    print()
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()