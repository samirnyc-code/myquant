"""Killer-day forensics: extract the 2024-04-30 context window from killer_context.csv.

Writes the 2024-04-25 .. 2024-05-02 rows (lead-in, killer day, aftermath) to a
dated CSV under data/options_sim/backtest_full/killerday/ for the day-forensics
report on 2024-04-30 (IC -2607 / fly / puts-band loss day; ECI-hot + FOMC-eve +
month-end selloff, SPX -1.57%).

Run:  python scripts/killerday/extract_context_20240430.py
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "data/options_sim/backtest_full/killer_context.csv"
OUT_DIR = ROOT / "data/options_sim/backtest_full/killerday"
OUT = OUT_DIR / "context_window_20240430.csv"

def main():
    df = pd.read_csv(SRC, dtype={"date": str})
    win = df[(df["date"] >= "2024-04-25") & (df["date"] <= "2024-05-02")].copy()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    win.to_csv(OUT, index=False)
    print(f"wrote {OUT} ({len(win)} rows)")
    print(win.to_string(index=False))

if __name__ == "__main__":
    main()
