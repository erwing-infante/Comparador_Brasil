#!/usr/bin/env bash
set -euo pipefail

cd /root/proyectos/Mancorabet/Monitor_Orbitx

# evitar solapamiento
exec /usr/bin/flock -n /tmp/orbitx-refresh.lock bash -lc '
  /root/proyectos/Mancorabet/Monitor_Orbitx/venv/bin/python3 scripts/build_orbitx_markets_all_competitions.py
  /root/proyectos/Mancorabet/Monitor_Orbitx/venv/bin/python3 scripts/build_watchlists_all.py
  /bin/systemctl restart orbitx-monitor.service
'