#!/usr/bin/env bash
cd /c/Users/Admin/myquant
for r in "2007-01-01 2012-12-31" "2014-01-01 2016-12-31" "2018-01-01 2026-07-22"; do
  set -- $r
  echo "=== VIX $1 -> $2 ==="
  PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe -u scripts/orats_pull.py --instr VIX --from "$1" --to "$2"
done
echo "VIX PULL COMPLETE (skipped 2013+2017)"
