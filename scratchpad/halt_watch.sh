#!/usr/bin/env bash
cd /c/Users/Admin/myquant
F="data/depth/ES_09-26_depth_2026-07-21.csv"
for i in $(seq 1 40); do
  now=$(TZ=America/Chicago date +%H:%M 2>/dev/null || date +%H:%M)
  age=$(( $(date +%s) - $(stat -c %Y "$F" 2>/dev/null || echo 0) ))
  if [ "$age" -gt 100 ]; then
    echo "HALT DETECTED — depth recording stalled (${age}s stale) at ~16:00 CT."
    echo "The Strategy's file: $F  size $(stat -c %s "$F" 2>/dev/null) bytes"
    echo "Ready to deploy the AddOn (session reopens 17:00 CT)."
    exit 0
  fi
  sleep 45
done
echo "TIMEOUT: recording still active after 30 min — halt not detected."
