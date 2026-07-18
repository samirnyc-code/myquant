"""ORATS one-shot verification — confirm the sub delivers what the accountability
note guarantees (per-strike OI + greeks, history depth) BEFORE any bulk pull."""
import sys, json, datetime as dt
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
TOKEN = (ROOT / "scratchpad" / "orats_token.txt").read_text().strip()
GUARANTEE = ["callOpenInterest", "putOpenInterest", "gamma", "delta",
             "callMidIv", "putMidIv"]

def hit(url, params, label):
    print(f"\n=== {label} ===\n{url}  params={ {k:v for k,v in params.items() if k!='token'} }")
    try:
        r = requests.get(url, params={**params, "token": TOKEN}, timeout=60)
    except Exception as e:
        print(f"  REQUEST ERROR: {e}"); return None
    print(f"  HTTP {r.status_code}")
    if r.status_code != 200:
        print(f"  body: {r.text[:300]}"); return None
    js = r.json()
    data = js.get("data", [])
    print(f"  rows: {len(data)}")
    if not data:
        print("  (empty — holiday/no-data or tier not entitled)"); return js
    cols = sorted(data[0].keys())
    print(f"  {len(cols)} columns")
    miss = [c for c in GUARANTEE if c not in cols]
    print(f"  guaranteed fields present: {[c for c in GUARANTEE if c in cols]}")
    if miss: print(f"  *** MISSING GUARANTEED FIELDS: {miss} ***")
    row = data[len(data)//2]
    print("  sample mid-chain row:")
    for k in ["ticker","tradeDate","expirDate","dte","strike","stockPrice",
              "callOpenInterest","putOpenInterest","gamma","delta","callMidIv","putMidIv"]:
        if k in row: print(f"    {k:18} = {row[k]}")
    return js

# 1) recent date (freshness / delay check)
hit("https://api.orats.io/datav2/hist/strikes",
    {"ticker": "SPY", "tradeDate": "2026-07-15"}, "HIST strikes — SPY 2026-07-15 (recent)")
# 2) SPX (index — does the underlying work?)
hit("https://api.orats.io/datav2/hist/strikes",
    {"ticker": "SPX", "tradeDate": "2026-07-15"}, "HIST strikes — SPX 2026-07-15")
# 3) deep history (2007 depth claim)
hit("https://api.orats.io/datav2/hist/strikes",
    {"ticker": "SPY", "tradeDate": "2007-06-01"}, "HIST strikes — SPY 2007-06-01 (depth claim)")
