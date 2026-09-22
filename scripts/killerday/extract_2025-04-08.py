"""Killer-day forensics extract for 2025-04-08 (tariff-crisis whipsaw day).

Pulls the morning-context row and all backtest trade rows for the date from
local CSVs (no ThetaData calls) and saves a dated evidence CSV.

Outputs: data/options_sim/backtest_full/killerday/2025-04-08_evidence.csv
"""
import pandas as pd
from pathlib import Path

ROOT = Path(r"C:\Users\Admin\myquant")
BF = ROOT / "data" / "options_sim" / "backtest_full"
OUT = BF / "killerday"
OUT.mkdir(parents=True, exist_ok=True)

DATE = "2025-04-08"

ctx = pd.read_csv(BF / "killer_context.csv")
ctx_row = ctx[ctx["date"] == DATE]

rows = pd.read_csv(BF / "rows.csv")
day_rows = rows[rows["date"] == DATE]

fly_path = BF / "fly_rows.csv"
if fly_path.exists():
    fly = pd.read_csv(fly_path)
    fly_day = fly[fly["date"] == DATE]
else:
    fly_day = pd.DataFrame()

with open(OUT / f"{DATE}_evidence.csv", "w", newline="") as f:
    f.write("# context row (killer_context.csv)\n")
    ctx_row.to_csv(f, index=False)
    f.write("# IC trade rows (rows.csv, all methods)\n")
    day_rows.to_csv(f, index=False)
    if not fly_day.empty:
        f.write("# fly rows (fly_rows.csv)\n")
        fly_day.to_csv(f, index=False)

print(ctx_row.to_string(index=False))
print(day_rows.to_string(index=False))
if not fly_day.empty:
    print(fly_day.to_string(index=False))
