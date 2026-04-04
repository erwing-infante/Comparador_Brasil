import csv
import json
import re
import unicodedata
from collections import defaultdict, deque
from pathlib import Path

# ============================================
# PATHS
# ============================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
HISTORY_DIR = PROJECT_DIR / "data" / "history"
OUTPUT_FILE = PROJECT_DIR / "data" / "history_recent_index.json"

# ============================================
# MAPA FIJO liga -> archivo
# ============================================
LIGA_TO_FILE = {
    "Brasileirao": "orbitx_brasileirao.csv",
    "Bundesliga": "orbitx_bundesliga.csv",
    "Championship": "orbitx_championship.csv",
    "Copa Alemana": "orbitx_copa_alemana.csv",
    "Copa del Rey": "orbitx_copa_del_rey.csv",
    "Copa Italia": "orbitx_copa_italia.csv",
    "Copa Libertadores": "orbitx_copa_libertadores.csv",
    "Copa Sudamericana": "orbitx_copa_sudamericana.csv",
    "EFL Cup": "orbitx_efl_cup.csv",
    "Eredivisie": "orbitx_eredivisie.csv",
    "FA Cup": "orbitx_fa_cup.csv",
    "La Liga": "orbitx_la_liga.csv",
    "La Liga 2": "orbitx_la_liga_2.csv",
    "Liga 1 Perú": "orbitx_liga_1_perú.csv",
    "Liga MX": "orbitx_liga_mx.csv",
    "Ligue 1": "orbitx_ligue_1.csv",
    "MLS": "orbitx_mls.csv",
    "Premier League": "orbitx_premier_league.csv",
    "Primeira Liga": "orbitx_primeira_liga.csv",
    "Serie A": "orbitx_serie_a.csv",
    "UEFA Champions League": "orbitx_uefa_champions_league.csv",
    "UEFA Conference League": "orbitx_uefa_conference_league.csv",
    "UEFA Europa League": "orbitx_uefa_europa_league.csv",
}

NEEDED_COLS = [
    "ts_pe",
    "liga",
    "market_id",
    "event_id",
    "event_name",
    "selection",
    "selection_id",
    "selection_name",
    "best_back_odds",
    "spread",
    "blpr",
    "tv_runner",
]

def build_key(row: dict) -> str:
    return f"{row['event_id']}|{row['market_id']}|{row['selection_id']}"

def main():
    recent = defaultdict(lambda: deque(maxlen=3))
    files_processed = 0
    rows_seen = 0

    for liga, filename in LIGA_TO_FILE.items():
        path = HISTORY_DIR / filename
        if not path.exists():
            print(f"⚠️ No existe: {filename}")
            continue

        files_processed += 1
        print(f"📄 Procesando: {filename}")

        with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
            reader = csv.DictReader(f)

            missing = [c for c in NEEDED_COLS if c not in (reader.fieldnames or [])]
            if missing:
                print(f"⚠️ {filename} sin columnas: {missing}")
                continue

            for row in reader:
                rows_seen += 1

                item = {
                    "ts_pe": row.get("ts_pe", ""),
                    "liga": row.get("liga", ""),
                    "market_id": str(row.get("market_id", "")).strip(),
                    "event_id": str(row.get("event_id", "")).strip(),
                    "event_name": row.get("event_name", ""),
                    "selection": str(row.get("selection", "")).upper().strip(),
                    "selection_id": str(row.get("selection_id", "")).strip(),
                    "selection_name": row.get("selection_name", ""),
                    "best_back_odds": row.get("best_back_odds", ""),
                    "spread": row.get("spread", ""),
                    "blpr": row.get("blpr", ""),
                    "tv_runner": row.get("tv_runner", ""),
                }

                key = build_key(item)
                recent[key].append(item)

    output = {
        "meta": {
            "files_processed": files_processed,
            "rows_seen": rows_seen,
            "keys_indexed": len(recent),
        },
        "rows": {k: list(v) for k, v in recent.items()},
    }

    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False), encoding="utf-8")

    print(f"✅ Índice guardado en: {OUTPUT_FILE}")
    print(f"📊 Files processed: {files_processed}")
    print(f"📊 Rows seen: {rows_seen}")
    print(f"📊 Keys indexed: {len(recent)}")

if __name__ == "__main__":
    main()