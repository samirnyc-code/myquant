#!/usr/bin/env bash
cd /c/Users/Admin/myquant
F=data/options_sim/gameplan_20260721.json
for i in $(seq 1 60); do
  if [ -f "$F" ]; then
    .venv/Scripts/python.exe -c "
import json,datetime as dt
from zoneinfo import ZoneInfo
d=json.load(open('data/options_sim/gameplan_20260721.json'))
print('GAMEPLAN LANDED')
print(' generated_at:',d.get('generated_at'))
print(' spot_preopen:',d.get('spot_preopen'),'src',d.get('spot_source'))
print(' regime:',d.get('regime'))
print(' scenarios:',len(d.get('scenarios',[])))
print(' now ET:',dt.datetime.now(ZoneInfo('America/New_York')).strftime('%H:%M:%S'))
"
    exit 0
  fi
  sleep 20
done
echo "TIMEOUT: gameplan file never appeared after 20 min"
