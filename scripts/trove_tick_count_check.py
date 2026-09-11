"""Sanity-check recent tick-trove days (data/ticks_continuous/): per-day row
counts, session bounds, price range; flag low-count outliers vs the window
median and any missing trading days (market_calendar). Default: last 30 files.

Usage: python scripts/trove_tick_count_check.py [n_days]
"""
import sys
import datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import market_calendar as MC

N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
files = sorted((ROOT / "data/ticks_continuous").glob("*.parquet"))[-N:]

rows = []
for f in files:
    d = pd.read_parquet(f)
    rows.append(dict(
        date=f.stem, n=len(d),
        first=str(d["DateTime"].min())[11:19], last=str(d["DateTime"].max())[11:19],
        lo=float(d["Price"].min()), hi=float(d["Price"].max()),
        vol=int(d["Volume"].sum())))
t = pd.DataFrame(rows)
med = t["n"].median()
t["flag"] = t["n"].apply(lambda n: "LOW" if n < 0.4 * med else
                         ("HIGH" if n > 2.5 * med else ""))
print(t.to_string(index=False))
print(f"\nmedian ticks/day {med:,.0f}  min {t['n'].min():,} ({t.loc[t['n'].idxmin(),'date']})"
      f"  max {t['n'].max():,} ({t.loc[t['n'].idxmax(),'date']})")

# missing trading days inside the window
have = set(t["date"])
d0 = dt.date.fromisoformat(t["date"].iloc[0])
d1 = dt.date.fromisoformat(t["date"].iloc[-1])
missing = []
d = d0
while d <= d1:
    if MC.is_trading_day(d) and d.isoformat() not in have:
        missing.append(d.isoformat())
    d += dt.timedelta(days=1)
print("missing trading days:", missing or "none")
