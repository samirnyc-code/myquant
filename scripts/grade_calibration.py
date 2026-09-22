"""Grade calibration — does the entry grade predict realized P&L?

Reads the options trade log, groups CLOSED trades by grade, and reports
n / avg / median / win% and a monotonicity check across A>B>C>D. Also dumps
the exact trades in any hybrid bucket (e.g. 'A/B'). Saves a dated CSV.
No inline analysis.
"""
import csv
import datetime as dt
from pathlib import Path

import pandas as pd
import options_trade_log as tlog

OUT = Path("data/options_log")
df = tlog.dedupe_mirrors(pd.read_parquet(OUT / "trades.parquet"))  # count STMR once
df = df[df["pnl"].notna()].copy()          # realized only
df["grade"] = df["grade"].astype(str).str.strip()

RANK = {"A": 6, "B": 5, "B-": 4, "C+": 4, "C": 3, "C-": 2, "D": 1, "F": 0}
rows = []
for g, d in df.groupby("grade"):
    wins = d.loc[d["pnl"] > 0, "pnl"]
    losses = d.loc[d["pnl"] < 0, "pnl"]
    gw, gl = wins.sum(), -losses.sum()
    rows.append({
        "grade": g, "n": len(d),
        "n_win": int((d["pnl"] > 0).sum()), "n_loss": int((d["pnl"] < 0).sum()),
        "avg_pnl": round(d["pnl"].mean(), 2),
        "win_pct": round(100 * (d["pnl"] > 0).mean(), 1),
        "gross_win": round(gw, 2), "gross_loss": round(gl, 2),
        "pf": round(gw / gl, 2) if gl > 0 else None,
        "total_pnl": round(d["pnl"].sum(), 2),
    })
tab = pd.DataFrame(rows)
tab["rank"] = tab["grade"].map(RANK)
tab = tab.sort_values(["rank", "grade"], ascending=[False, True], na_position="last")

pd.set_option("display.width", 200)
print("=== avg P&L per trade by grade (realized only) ===")
print(tab[["grade", "n", "n_win", "n_loss", "win_pct", "gross_win", "gross_loss",
           "pf", "avg_pnl", "total_pnl"]].to_string(index=False))

# clean-ladder monotonicity (letter grades only, drop hybrids/tiny)
clean = tab[tab["grade"].isin(["A", "B", "C", "D"])].sort_values("rank", ascending=False)
seq = clean["avg_pnl"].tolist()
mono = all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))
print(f"\nA>B>C>D avg-P&L sequence: {seq}  -> monotonic decreasing: {mono}")

# what is the 'A/B' (or any non-standard) bucket?
odd = df[~df["grade"].isin(["A", "B", "B-", "C+", "C", "C-", "D", "F"])]
if len(odd):
    print(f"\n=== non-standard grade buckets ({len(odd)} trades) ===")
    print(odd[["trade_id", "grade", "structure", "credit", "pnl", "close_reason"]].to_string(index=False))

outp = OUT / f"grade_calibration_{dt.date.today():%Y%m%d}.csv"
tab.to_csv(outp, index=False)
print(f"\nsaved {outp}  ({len(df)} realized trades)")
