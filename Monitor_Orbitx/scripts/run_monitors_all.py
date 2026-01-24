import os
import sys
import json
import subprocess

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from config_orbitx import WATCHLISTS_DIR  # noqa

PY = sys.executable
MULTI_MONITOR = os.path.join("scripts", "multi_monitor.py")

def main():
    files = [f for f in os.listdir(WATCHLISTS_DIR) if f.startswith("orbitx_watchlist_") and f.endswith(".json")]
    files.sort()

    if not files:
        print("❌ No hay watchlists en data/watchlists. Ejecuta build_watchlists_all.py primero.")
        return

    procs = []

    for fname in files:
        path = os.path.join(WATCHLISTS_DIR, fname)
        liga_slug = fname.replace("orbitx_watchlist_", "").replace(".json", "")

        try:
            data = json.load(open(path, "r", encoding="utf-8"))
        except Exception:
            print("⚠️ No pude leer:", fname)
            continue

        if not isinstance(data, list) or len(data) == 0:
            print(f"⏭️ {liga_slug}: watchlist vacía, no arranco monitor.")
            continue

        env = os.environ.copy()
        env["WATCHLIST_FILE"] = path           # 🔥 multi_monitor debe leer esto
        env["CSV_LIGA_NAME"] = liga_slug       # 🔥 orbitx_<liga_slug>.csv
        print(f"✅ Arrancando monitor: {liga_slug} | markets={len(data)}")

        p = subprocess.Popen([PY, MULTI_MONITOR], env=env)
        procs.append((liga_slug, p))

    print("\n📌 Monitores corriendo:", len(procs))
    print("Para detenerlos: cierra esta terminal o Ctrl+C.\n")

    try:
        # Espera a que terminen
        for liga_slug, p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\n🛑 Deteniendo monitores...")
        for _, p in procs:
            try:
                p.terminate()
            except Exception:
                pass

if __name__ == "__main__":
    main()
