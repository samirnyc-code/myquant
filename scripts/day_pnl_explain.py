"""Explain a day's desk P&L trade by trade vs the max-profit zone.

Prints: each trade (strikes, credit, exit, pnl), the day's max-profit zone
(highest short put .. lowest short call across the OPEN book after stops),
the settle close, and the arithmetic of why the day total is what it is.

Usage: python scripts/day_pnl_explain.py [YYYY-MM-DD]
"""
import json
import sys
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
day = sys.argv[1] if len(sys.argv) > 1 else dt.date.today().strftime("%Y-%m-%d")

t = pd.read_parquet(ROOT / "data/options_log/trades.parquet")
t["entry_dt"] = pd.to_datetime(t["entry_dt"])
d = t[t["entry_dt"].dt.strftime("%Y-%m-%d") == day].copy()

def short_long(legs_json):
    legs = json.loads(legs_json)
    s = next((l for l in legs if l["side"] == "sell"), {})
    return s.get("strike"), s.get("right")

d[["short_k", "right"]] = d["legs"].apply(lambda s: pd.Series(short_long(s)))
d["exit"] = d["close_reason"].fillna("").map(
    lambda r: "stop" if r.startswith("level") else
              ("time" if r.startswith("time") else ("expired" if r == "expired" else r or "open")))

pm_path = ROOT / f"data/options_sim/postmortem_{day.replace('-', '')}.json"
close = None
if pm_path.exists():
    pm = json.loads(pm_path.read_text(encoding="utf-8"))
    close = pm.get("close") or pm.get("settle_close") or pm.get("spx_close")

print(f"=== {day} ===  settle close: {close}")
cols = ["trade_id", "strategy_id", "right", "short_k", "credit", "pnl", "exit"]
print(d[cols].sort_values("trade_id").to_string(index=False))

stopped = d[d["exit"].isin(["stop", "time"])]
expired = d[d["exit"] == "expired"]
print(f"\nstopped/time: n={len(stopped)}  pnl {stopped['pnl'].sum():.1f}")
print(f"expired     : n={len(expired)}  pnl {expired['pnl'].sum():.1f}")
print(f"DAY TOTAL   : {d['pnl'].sum():.1f}")

surv = expired
puts = surv[surv["right"] == "P"]["short_k"]
calls = surv[surv["right"] == "C"]["short_k"]
if len(puts) and len(calls):
    print(f"\nmax-profit zone of the SURVIVING book: {puts.max():.0f} .. {calls.min():.0f}"
          f"  (close {close} -> {'INSIDE' if close and puts.max() <= close <= calls.min() else 'check'})")
print(f"credits kept by survivors: {surv['credit'].sum():.2f} "
      f"( x100 = {100 * surv['credit'].sum():.0f} gross)")
