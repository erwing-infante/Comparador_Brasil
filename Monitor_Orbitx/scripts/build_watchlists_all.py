import os
import sys
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from config_orbitx import CATALOGS_DIR, WATCHLISTS_DIR  # noqa

load_dotenv()

WATCH_HOURS = int(os.getenv("WATCH_HOURS", "36"))


def parse_start_utc(date_str: str) -> datetime:
    # "YYYY-MM-DD HH:MM UTC"
    dt = datetime.strptime(date_str.replace(" UTC", ""), "%Y-%m-%d %H:%M")
    return dt.replace(tzinfo=timezone.utc)


def main():
    now_utc = datetime.now(timezone.utc)
    limit_utc = now_utc + timedelta(hours=WATCH_HOURS)

    files = [
        f for f in os.listdir(CATALOGS_DIR)
        if f.startswith("orbitx_markets_") and f.endswith(".json")
    ]
    files.sort()

    print("Catálogos encontrados:", len(files))
    print("Ventana:", WATCH_HOURS, "horas")

    # ==========================================================
    # 1) GENERAR WATCHLIST POR LIGA (SIN CAMBIOS EN TU LÓGICA)
    # ==========================================================
    for fname in files:
        in_path = os.path.join(CATALOGS_DIR, fname)
        liga_slug = fname.replace("orbitx_markets_", "").replace(".json", "")
        out_path = os.path.join(WATCHLISTS_DIR, f"orbitx_watchlist_{liga_slug}.json")

        with open(in_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            print("⚠️ skip (no list):", fname)
            continue

        watch = []
        for m in data:
            date_str = m.get("date")
            if not date_str:
                continue
            try:
                start = parse_start_utc(date_str)
            except Exception:
                continue
            if start < now_utc:
                continue
            if start > limit_utc:
                continue
            watch.append(m)

        watch.sort(key=lambda x: x.get("date", ""))

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(watch, f, ensure_ascii=False, indent=2)

        print(f"✅ {liga_slug}: watchlist={len(watch)} -> {out_path}")

    # ==========================================================
    # 2) UNIFICAR TODOS LOS WATCHLIST EN UNO SOLO (NUEVO)
    #    - No toca los watchlist individuales
    #    - Crea: data/watchlists/watchlist.json
    # ==========================================================
    unified_watchlist = []

    watchlist_files = [
        f for f in os.listdir(WATCHLISTS_DIR)
        if f.startswith("orbitx_watchlist_") and f.endswith(".json")
    ]
    watchlist_files.sort()

    for wf in watchlist_files:
        path = os.path.join(WATCHLISTS_DIR, wf)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                unified_watchlist.extend(data)
            else:
                print(f"⚠️ skip (no list) en {wf}")
        except Exception as e:
            print(f"⚠️ Error leyendo {wf}: {e}")

    unified_watchlist.sort(key=lambda x: x.get("date", ""))

    unified_path = os.path.join(WATCHLISTS_DIR, "watchlist.json")
    with open(unified_path, "w", encoding="utf-8") as f:
        json.dump(unified_watchlist, f, ensure_ascii=False, indent=2)

    print(f"🧩 WATCHLIST GLOBAL: {len(unified_watchlist)} partidos -> {unified_path}")


if __name__ == "__main__":
    main()
