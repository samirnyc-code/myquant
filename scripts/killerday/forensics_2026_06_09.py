"""Killer-day forensics: 2026-06-09 (IC -2210, fly -1378).

Extracts from LOCAL data only (no ThetaData — terminal busy):
  - SPX daily OHLC for 2026-06-03 .. 2026-06-12 window, with gap/oc/range/close-close
  - VIX closes for the window
  - the day's vix252 IC trade rows + fly rows (strikes, credits, stops, pnl)

Output: data/options_sim/backtest_full/killerday/forensics_2026_06_09.csv
        (+ trade rows file forensics_2026_06_09_trades.csv), printed to stdout.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BT = ROOT / "data" / "options_sim" / "backtest_full"
OUT = BT / "killerday"
OUT.mkdir(exist_ok=True)

DAY = "2026-06-09"
W0, W1 = "2026-06-03", "2026-06-12"

spx = pd.read_csv(BT / "spx_daily_ohlc.csv")
spx = spx[(spx.date >= W0) & (spx.date <= W1)].reset_index(drop=True)
vix = pd.read_csv(ROOT / "data" / "vix_daily.csv").set_index("date")["close"]

spx["gap_pct"] = round(100 * (spx.open / spx.close.shift(1) - 1), 2)
spx["oc_pct"] = round(100 * (spx.close / spx.open - 1), 2)
spx["cc_pct"] = round(100 * (spx.close / spx.close.shift(1) - 1), 2)
spx["range_pct"] = round(100 * (spx.high - spx.low) / spx.close, 2)
spx["lo_vs_open_pct"] = round(100 * (spx.low / spx.open - 1), 2)
spx["hi_vs_open_pct"] = round(100 * (spx.high / spx.open - 1), 2)
spx["vix_close"] = spx.date.map(vix).round(2)

spx.to_csv(OUT / "forensics_2026_06_09.csv", index=False)
print(spx.to_string(index=False))

ic = pd.read_csv(BT / "rows.csv")
tr = ic[(ic.date == DAY) & (ic.method == "vix252")]
fly = pd.read_csv(BT / "fly_rows.csv")
ftr = fly[fly.date == DAY]
trades = pd.concat([tr, ftr], ignore_index=True)
trades.to_csv(OUT / "forensics_2026_06_09_trades.csv", index=False)
print("\nIC rows (vix252):")
print(tr.to_string(index=False))
print("\nfly rows:")
print(ftr.to_string(index=False))
