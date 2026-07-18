"""Settle today's expired 0DTE trades at the official SPX close (S73 EOD)."""
import sys
sys.path.insert(0, "scripts")
import datetime as dt
import json
import urllib.request

import pandas as pd

import options_trade_log as tlog

FEE = 1.30
TODAY = "2026-07-14"

# official close from Yahoo (today's completed daily bar), fallback = last parity sample
try:
    req = urllib.request.Request(
        "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=1d&interval=1d",
        headers={"User-Agent": "Mozilla/5.0"})
    r = json.loads(urllib.request.urlopen(req, timeout=30).read())["chart"]["result"][0]
    S = float(r["indicators"]["quote"][0]["close"][-1])
    src = "yahoo close"
except Exception:
    S = 7547.57
    src = "last parity sample (fallback)"
print(f"SPX settle = {S:.2f} ({src})\n")

df = tlog.load()
for _, tr in df[df.exit_dt.isna()].iterrows():
    legs = json.loads(tr.legs)
    exps = {l["expiry"] for l in legs}
    if exps != {"20260714"}:
        if "20260714" in exps:
            print(f"{tr.trade_id}: MIXED expiries — 0DTE leg expires, trade stays open (calendar)")
        continue
    cost = sum((1 if l["side"] == "sell" else -1) * l.get("qty", 1)
               * max(0.0, (S - l["strike"]) if l["right"] == "C" else (l["strike"] - S))
               for l in legs)
    n = sum(l.get("qty", 1) for l in legs)
    r = tlog.update_exit(tr.trade_id, TODAY, cost, n * FEE, fill_model="settlement")
    print(f"SETTLED {tr.trade_id:34s} intrinsic cost {cost:7.2f}  pnl ${r['pnl']:+8,.2f}")

print("\n" + tlog.summary())
