"""Scan the full 4.3yr backtest for negative-credit (crossed/garbage-quote)
rows the IC engine traded instead of standing down (fly v3 already guards),
and restate the headline totals ex-artifact.

Rule: credit < 0 = artifact (you cannot be forced to PAY to open a credit
spread; a negative touch credit means the quote snapshot was crossed).
Output: dated CSV of every artifact row + restated totals, stdout.
"""
import pandas as pd
from pathlib import Path
from datetime import date

BASE = Path(__file__).resolve().parent.parent
BT = BASE / "data" / "options_sim" / "backtest_full"
STAMP = date.today().strftime("%Y%m%d")

ic = pd.read_csv(BT / "rows.csv", parse_dates=["date"])
ic = ic[ic["method"] == "vix252"].drop(columns=["method"])

bad = ic[ic["credit"] < 0].sort_values("date")
bad.to_csv(BT / f"negative_credit_rows_{STAMP}.csv", index=False)
print(f"artifact rows (credit<0): {len(bad)}  pnl impact {bad['pnl'].sum():.0f}")
print(bad.to_string(index=False))

clean = ic[ic["credit"] >= 0]
for label, df in (("4.3yr ic AS-PUBLISHED", ic), ("4.3yr ic EX-ARTIFACT", clean)):
    daily = df.groupby("date")["pnl"].sum()
    cum = daily.cumsum()
    dd = (cum - cum.cummax()).min()
    gw, gl = df.loc[df["pnl"] > 0, "pnl"].sum(), df.loc[df["pnl"] < 0, "pnl"].sum()
    print(f"{label}: total {df['pnl'].sum():.0f}  n {len(df)}  "
          f"win {100*(df['pnl']>0).mean():.1f}%  exp {df['pnl'].mean():.1f}  "
          f"PF {gw/abs(gl):.2f}  maxDD {dd:.0f}")

yearly = (clean.assign(year=clean["date"].dt.year).groupby("year")["pnl"]
          .sum().round(0))
print("\nEX-ARTIFACT yearly:")
print(yearly.to_string())
