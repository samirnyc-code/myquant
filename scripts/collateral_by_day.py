"""Daily concurrent collateral + running max ('max collateral used'), to explain
the step in the dashboard Capital curve. For each calendar day, sums the
collateral of every trade active that day (entryDay..exitDay), then tracks the
running max. Flags the days where the running max steps up, and lists the trades
active on those days. Saves a dated CSV.
"""
import datetime as dt
from pathlib import Path

import pandas as pd
import options_trade_log as tlog

df = tlog.dedupe_mirrors(pd.read_parquet("data/options_log/trades.parquet"))  # STMR once
df = df[df["pnl"].notna() | df["exit_dt"].isna()].copy()   # realized + still-open
df["entry_day"] = df["entry_dt"].astype(str).str[:10]
df["exit_day"] = df["exit_dt"].astype(str).str[:10].where(df["exit_dt"].notna(),
                                                           df["entry_day"])
df["coll"] = pd.to_numeric(df["collateral"], errors="coerce").fillna(0)

days = sorted(set(df["entry_day"]) | set(df["exit_day"]))
rows, runmax = [], 0.0
step_days = []
for d in days:
    active = df[(df["entry_day"] <= d) & (df["exit_day"] >= d)]
    c = active["coll"].sum()
    prev = runmax
    runmax = max(runmax, c)
    rows.append({"day": d, "concurrent_coll": round(c), "running_max": round(runmax),
                 "n_active": len(active)})
    if runmax > prev + 1:
        step_days.append((d, c, active))

out = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print("=== daily concurrent collateral (running max) ===")
print(out.to_string(index=False))

print("\n=== days where running-max stepped UP ===")
for d, c, active in step_days:
    print(f"\n{d}: concurrent ${c:,.0f} across {len(active)} active trades")
    print(active[["trade_id", "strategy_id", "structure", "coll", "entry_day", "exit_day"]]
          .to_string(index=False))

outp = Path(f"data/options_log/collateral_by_day_{dt.date.today():%Y%m%d}.csv")
out.to_csv(outp, index=False)
print(f"\nsaved {outp}")
