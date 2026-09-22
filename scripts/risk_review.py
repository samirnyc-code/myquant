"""Tail-risk review of the 0DTE premium book: how bad can a day actually get?

Everything is a DEFINED-RISK 25-wide vertical, so per-trade loss is capped at
(width - credit). This script quantifies the day-level tail:
  - actual realized daily P&L (worst days)
  - theoretical WORST day if held to expiry on a full one-way move:
      crash = puts go full-loss, calls keep credit ; moon = the mirror
    (this is the real 'catastrophe' number — bounded, but the thing to size for)
Saves a dated CSV. No stops are modelled here — this is the unprotected floor.
"""
import datetime as dt
import json
from pathlib import Path

import pandas as pd
import options_trade_log as tlog

df = tlog.dedupe_mirrors(pd.read_parquet("data/options_log/trades.parquet"))
df = df[df["pnl"].notna()].copy()
df["day"] = df["entry_dt"].astype(str).str[:10]


def right_of(r):
    sid = str(r["strategy_id"]).lower()
    if sid.endswith("_p") or "bps" in sid:
        return "P"
    if sid.endswith("_c") or "bcs" in sid:
        return "C"
    try:
        return json.loads(r["legs"])[0]["right"]
    except Exception:
        return "?"


df["right"] = df.apply(right_of, axis=1)
df["max_loss"] = pd.to_numeric(df["max_loss"], errors="coerce").fillna(0)   # positive $
df["max_gain"] = pd.to_numeric(df["max_gain"], errors="coerce").fillna(0)

rows = []
for day, d in df.groupby("day"):
    puts, calls = d[d["right"] == "P"], d[d["right"] == "C"]
    crash = -puts["max_loss"].sum() + calls["max_gain"].sum()   # market craters
    moon = -calls["max_loss"].sum() + puts["max_gain"].sum()    # market rips up
    rows.append({"day": day, "n": len(d),
                 "realized": round(d["pnl"].sum(), 0),
                 "worst_hold_to_exp": round(min(crash, moon), 0),
                 "if_crash": round(crash, 0), "if_moon": round(moon, 0)})

r = pd.DataFrame(rows).sort_values("day")
pd.set_option("display.width", 200)
print("=== every day: realized vs theoretical worst (hold-to-expiry, full one-way move) ===")
print(r.to_string(index=False))

print("\n=== worst 5 REALIZED days ===")
print(r.nsmallest(5, "realized")[["day", "n", "realized", "worst_hold_to_exp"]].to_string(index=False))

print("\n=== the tail (theoretical worst-possible day, per day) ===")
w = r["worst_hold_to_exp"]
print(f"  deepest single-day floor ever carried : {w.min():,.0f}")
print(f"  median day's floor                    : {w.median():,.0f}")
print(f"  worst realized day so far             : {r['realized'].min():,.0f}")
print(f"  best  realized day so far             : {r['realized'].max():,.0f}")
print(f"  single worst trade                    : {df['pnl'].min():,.0f}")
print(f"  trades that lost > $2000 (near-max)    : {(df['pnl'] < -2000).sum()} of {len(df)}")

outp = Path(f"data/options_log/risk_review_{dt.date.today():%Y%m%d}.csv")
r.to_csv(outp, index=False)
print(f"\nsaved {outp}")
