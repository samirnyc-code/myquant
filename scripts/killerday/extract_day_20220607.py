"""Killer-day forensics extract: 2022-06-07.

Pulls the morning-context row plus all IC/fly trade rows for the date and the
surrounding days' context (2022-06-01..2022-06-10) into a dated CSV bundle.
Local CSVs only (no ThetaData). Output: data/options_sim/backtest_full/killerday/.
"""
import pandas as pd
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BT = REPO / "data" / "options_sim" / "backtest_full"
OUT = BT / "killerday"
OUT.mkdir(parents=True, exist_ok=True)

DAY = "2022-06-07"

ctx = pd.read_csv(BT / "killer_context.csv")
window = ctx[(ctx["date"] >= "2022-06-01") & (ctx["date"] <= "2022-06-10")]
window.to_csv(OUT / f"context_window_{DAY}.csv", index=False)

rows = pd.read_csv(BT / "rows.csv")
fly = pd.read_csv(BT / "fly_rows.csv")
day_rows = rows[rows["date"] == DAY].copy()
day_rows["book"] = "ic"
day_fly = fly[fly["date"] == DAY].copy()
day_fly["book"] = "fly"
day_fly["method"] = ""
combined = pd.concat([day_rows, day_fly], ignore_index=True)
combined.to_csv(OUT / f"day_{DAY}_rows.csv", index=False)

print(window.to_string(index=False))
print(combined.to_string(index=False))
