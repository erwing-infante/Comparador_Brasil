import time
import subprocess

# Ruta absoluta al script que actualiza las cuotas
SCRIPT_PATH = "/root/proyectos/Comparador_Brasil/odds_service.py"
PYTHON_PATH = "/root/proyectos/Comparador_Brasil/venv/bin/python"

while True:
    print("🔄 Ejecutando actualización de cuotas...")
    try:
        result = subprocess.run([PYTHON_PATH, SCRIPT_PATH], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Actualización completada correctamente")
        else:
            print(f"⚠️ Error al ejecutar odds_service.py: {result.stderr}")
    except Exception as e:
        print(f"❌ Excepción inesperada: {e}")

    print("⏸ Esperando 180 segundos para la próxima actualización...")
    time.sleep(180)  # 3 minutos
