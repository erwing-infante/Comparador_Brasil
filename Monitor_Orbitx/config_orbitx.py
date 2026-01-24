# config_orbitx.py
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "data")
DUMPS_DIR = os.path.join(DATA_DIR, "dumps")
CATALOGS_DIR = os.path.join(DATA_DIR, "catalogs")
WATCHLISTS_DIR = os.path.join(DATA_DIR, "watchlists")
HISTORY_DIR = os.path.join(DATA_DIR, "history")

SNAPSHOT_PATH = os.path.join(DATA_DIR, "snapshot.json")

for p in (DATA_DIR, DUMPS_DIR, CATALOGS_DIR, WATCHLISTS_DIR, HISTORY_DIR):
    os.makedirs(p, exist_ok=True)
