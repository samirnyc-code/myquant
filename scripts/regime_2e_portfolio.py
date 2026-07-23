"""Portfolio effect — the S83 books combined, daily closed equity + drawdown.

Books:
  A  headline 2E (strict fills)                 data/regime/headline_trades_detail_*.csv
  AL headline LONGS only
  B  f2E trap-fade shorts (K=2, EOD)           data/regime/failed2e_*.csv
Combos: A, AL, B, A+B, AL+B. Per-book and combined: 5yr net, ann. net, max daily
closed-trade DD, net/DD ratio, worst year. Answers "does stacking fix the capital
efficiency" with numbers.

  python scripts/regime_2e_portfolio.py
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "data" / "regime"
YEARS = 5.06

A = pd.read_csv(R / "headline_trades_detail_20260723.csv")[["Date", "dir", "net"]]
B = pd.read_csv(R / "failed2e_20260723.csv")
B = B[(B.K == 2) & (B["exit"] == "eod") & (B["dir"] == "S")][["Date", "dir", "net"]]

BOOKS = {
    "A  headline 2E": A,
    "AL headline longs-only": A[A["dir"] == "L"],
    "B  f2E short fade": B,
    "A + B": pd.concat([A, B]),
    "AL + B": pd.concat([A[A["dir"] == "L"], B]),
}

print(f"{'book':<26} {'n':>5} {'net 5yr':>10} {'net/yr':>8} {'maxDD':>9} {'net/DD':>7} {'worst yr':>12}")
for name, d in BOOKS.items():
    day = d.groupby("Date").net.sum().sort_index()
    eq = day.cumsum()
    dd = float((eq - eq.cummax()).min())
    yr = day.groupby(day.index.str[:4]).sum()
    wy = yr.idxmin(); wv = yr.min()
    net = day.sum()
    print(f"{name:<26} {len(d):>5} {net:>+10,.0f} {net/YEARS:>+8,.0f} {dd:>+9,.0f} "
          f"{net/-dd:>7.2f} {wy} {wv:>+8,.0f}")
