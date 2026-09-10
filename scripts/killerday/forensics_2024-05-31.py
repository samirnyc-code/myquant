"""Killer-day forensics extract: 2024-05-31 (MSCI semi-annual rebalance / month-end whipsaw).

Pulls the morning-context row + all trade rows (IC rows.csv, fly_rows.csv) for the day
from local CSVs (no ThetaData) and writes a dated evidence CSV plus a findings block.

Findings (verified 2026-09-10, sources in FINDINGS below):
- Day: Fri 2024-05-31. Month-end AND MSCI semi-annual index rebalance date.
- Premarket: April core PCE 08:30 ET (07:30 CT) +0.2% m/m in-line, 2.8% y/y. Benign.
  Gap +0.15%, VIX prior 14.47 (chg +0.19). Quiet open, no warning in the signal stack.
- Intraday: SPX opened ~5243, sold off through morning/midday (megacap drag: DELL -18/-20%
  post-earnings, NVDA down) to ~5192 low (~-1% from open), then a massive FINAL-HOUR
  rebalance-flow rally: Dow +574.84 (+1.51%, best day of 2024 to date), SPX +0.80% to
  5277.51, Nasdaq -0.01%. Classic month-end/MSCI MOC buy-imbalance ramp.
- Damage: whipsaw killed the ATM flies BOTH ways. Centers 5235/5240, shorts 5210/5260.
  Morning drop stopped both put flies; last-hour ramp stopped both call flies.
  eodfly_p -626.52, eodfly_c -396.52, openfly_p -406.52, openfly_c -1076.52 = -2506.
  vix252 ICs (puts 5190/5195, calls 5285/5290, EM 47.7) survived BOTH extremes by
  ~2 pts (low ~5192 vs 5190 short; close 5277.51 vs 5285 short) -> +197.
- Prior days: Wed 5/29 SPX -0.74% (10y yield to 4-wk high ~4.6% on weak auctions);
  Thu 5/30 SPX -0.60% (Salesforce -20% drag). Mild two-day drip, VIX still 14.5.
- After: Mon 6/03 SPX +0.11% to 5283.40 (ISM 48.7 miss, yields fell). No continuation;
  vol snapped back to calm. One-day flow event.
- 08:30 CT verdict: genuine intraday ambush by the signal stack (VIX/gap/credits/EM all
  quiet; credits 0.75c/0.50p were thin, not rich). The ONLY premarket-knowable flag was
  the CALENDAR: month-end Friday + MSCI semi-annual rebalance -> known late-day MOC-flow
  risk. A mechanical calendar rule could have said "no tight ATM flies today", but could
  not have predicted the two-sided path.
"""
import csv, os

REPO = r"C:\Users\Admin\myquant"
BT = os.path.join(REPO, "data", "options_sim", "backtest_full")
OUT = os.path.join(BT, "killerday")
DAY = "2024-05-31"

os.makedirs(OUT, exist_ok=True)

def rows_for(path, datecol="date"):
    with open(path, newline="") as f:
        r = csv.DictReader(f)
        return [row for row in r if row[datecol] == DAY]

ctx = rows_for(os.path.join(BT, "killer_context.csv"))
ic = rows_for(os.path.join(BT, "rows.csv"))
fly = rows_for(os.path.join(BT, "fly_rows.csv"))

out_path = os.path.join(OUT, f"forensics_{DAY}_evidence.csv")
with open(out_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["section", "detail"])
    for row in ctx:
        w.writerow(["context", str(row)])
    for row in ic:
        w.writerow(["ic_row", str(row)])
    for row in fly:
        w.writerow(["fly_row", str(row)])
    w.writerow(["finding", "MSCI semi-annual rebalance + month-end; morning megacap selloff (DELL -18%) to ~5192 then final-hour MOC-flow ramp to 5277.51; both fly wings stopped = -2506; vix252 IC survived both extremes by ~2pts = +197"])
    w.writerow(["premarket", "April core PCE in-line (+0.2% m/m, 2.8% y/y) at 07:30 CT; gap +0.15%; VIX 14.47; quiet open"])
    w.writerow(["prior_days", "5/29 -0.74% (yields 4.6% weak auctions); 5/30 -0.60% (CRM -20%)"])
    w.writerow(["aftermath", "6/03 +0.11% to 5283.40 (ISM 48.7); no continuation, calm"])
    w.writerow(["verdict", "intraday ambush; only premarket-knowable flag = month-end + MSCI rebalance calendar (late-day flow risk)"])

print(f"wrote {out_path}: ctx={len(ctx)} ic={len(ic)} fly={len(fly)}")
