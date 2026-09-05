"""Determine the RIGHT daily max-loss stop from the intraday record — not a guess.

Rebuilds each day's intraday PORTFOLIO P&L from data/options_sim/marks.csv
(per-trade unrealized P&L over time; a closed trade's last mark carries forward as
its realized value), then:

  1. measures how deep a NORMAL day dips intraday vs how deep the genuine
     bleed-out days go — the stop must sit BELOW routine noise and the deepest
     dip a WINNER ever recovered from, or it just converts comebacks into losses;
  2. shadow-tests a daily circuit breaker at many levels: for each level, how
     many days it fires, how much it SAVES on true bleed-outs vs COSTS on
     dip-then-recover days, and the net.

STMR is excluded (retired). No live behaviour is changed — this is measurement.
Saves two dated CSVs: per-day troughs, and the level sweep.
"""
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

SIM = Path("data/options_sim")
m = pd.read_csv(SIM / "marks.csv")
m = m[~m["trade_id"].astype(str).str.contains("stmr", case=False)]      # retired
m["ts"] = pd.to_datetime(m["ts_et"], errors="coerce")
m = m.dropna(subset=["ts"])
m["unreal_pnl"] = pd.to_numeric(m["unreal_pnl"], errors="coerce")
m["day"] = m["ts"].dt.strftime("%Y-%m-%d")

per_day = []
for day, d in m.groupby("day"):
    # intraday portfolio curve: pivot trades over time, carry each trade's last
    # mark forward (its realized value after it closes), leading NaN = not yet in book
    piv = d.pivot_table(index="ts", columns="trade_id", values="unreal_pnl", aggfunc="last")
    piv = piv.sort_index().ffill().fillna(0.0)
    curve = piv.sum(axis=1)
    if curve.empty:
        continue
    trough = curve.min()
    end = curve.iloc[-1]
    vix = pd.to_numeric(d["vix"], errors="coerce").dropna()
    per_day.append({
        "day": day, "n": d["trade_id"].nunique(),
        "end_pnl": round(end), "intraday_trough": round(trough),
        "trough_ct": curve.idxmin().strftime("%H:%M"),
        "recovered_by": round(end - trough),          # how much it climbed off the low
        "ended_green": end >= 0,
        "vix": round(vix.iloc[-1], 1) if len(vix) else np.nan,
    })

R = pd.DataFrame(per_day).sort_values("day")
pd.set_option("display.width", 200)

# VALIDATE the reconstruction against the actual realized book (deduped, non-STMR)
import options_trade_log as tlog
tr = tlog.dedupe_mirrors(pd.read_parquet("data/options_log/trades.parquet"))
tr = tr[tr["pnl"].notna() & ~tr["strategy_id"].astype(str).str.contains("stmr", case=False)].copy()
tr["day"] = tr["entry_dt"].astype(str).str[:10]
booked = tr.groupby("day")["pnl"].sum().round().rename("booked_realized")
R = R.merge(booked, on="day", how="left")
R["recon_gap"] = (R["end_pnl"] - R["booked_realized"]).round()
print("=== per-day intraday P&L vs booked realized (validation) ===")
print(R.to_string(index=False))

# ANALYSE ONLY THE CURRENT BOOK: auto_trigger era (validated vs parquet).
# July/early days (1-7 trades, old structures, no booked_realized) are a different
# strategy and would skew the level — exclude them, say so.
excluded = int(R["booked_realized"].isna().sum())
R = R[R["booked_realized"].notna()].copy()
print(f"\n[current book = {len(R)} auto-era days; excluded {excluded} pre-strategy July/early days]")

green = R[R["ended_green"]]
red = R[~R["ended_green"]]
deepest_recoverable = green["intraday_trough"].min()      # worst dip a WINNER climbed out of
print("\n=== how deep do days dip intraday? ===")
print(f"  ALL days   trough: median {R['intraday_trough'].median():,.0f} | "
      f"p90 {R['intraday_trough'].quantile(.10):,.0f} | worst {R['intraday_trough'].min():,.0f}")
print(f"  GREEN days trough: median {green['intraday_trough'].median():,.0f} | "
      f"DEEPEST a winner recovered from: {deepest_recoverable:,.0f}   <-- stop must sit BELOW this")
print(f"  RED days   trough: median {red['intraday_trough'].median():,.0f} | worst {red['intraday_trough'].min():,.0f}")
print(f"  worst realized end-of-day: {R['end_pnl'].min():,.0f}")

# ---- shadow circuit-breaker sweep ----
print("\n=== daily stop shadow-test (flatten the whole book at -level) ===")
print(f"{'level':>7} {'fires':>6} {'false*':>7} {'true_saves':>11} {'net_$':>9} {'worst_day_after':>16}")
sweep = []
for S in range(1000, 6001, 250):
    fires = false = 0
    net = 0.0
    worst_after = 0.0
    for _, r in R.iterrows():
        hit = r["intraday_trough"] <= -S
        after = -S if hit else r["end_pnl"]
        worst_after = min(worst_after, after)
        if hit:
            fires += 1
            if r["end_pnl"] > -S:            # would have ended better than the stop
                false += 1
            net += (after - r["end_pnl"])    # +saved / -cost vs no stop
    sweep.append({"level": -S, "fires": fires, "false_recover": false,
                  "true_saves": fires - false, "net": round(net), "worst_after": round(worst_after)})
    print(f"{-S:>7} {fires:>6} {false:>7} {fires-false:>11} {net:>9,.0f} {worst_after:>16,.0f}")
print("  * false = day hit the stop but would have RECOVERED to better than -level (a comeback you cut)")

sw = pd.DataFrame(sweep)
# pick: the shallowest stop that never cuts a comeback (false==0), i.e. only fires on true bleed-outs
clean = sw[sw["false_recover"] == 0]
best = clean.iloc[(clean["level"]).argmax()] if len(clean) else None
print("\n=== recommended level (reasoned) ===")
if best is not None:
    print(f"  Shallowest stop that NEVER cuts a comeback: {best['level']:,} "
          f"(fires {best['fires']}x, all true bleed-outs, caps worst day at {best['worst_after']:,})")
print(f"  Deepest dip a winner recovered from: {deepest_recoverable:,} — any stop above (shallower than) "
      f"this risks killing green days.")

R.to_csv(SIM / f"stop_troughs_{dt.date.today():%Y%m%d}.csv", index=False)
sw.to_csv(SIM / f"stop_sweep_{dt.date.today():%Y%m%d}.csv", index=False)
print(f"\nsaved stop_troughs + stop_sweep CSVs in {SIM}")
