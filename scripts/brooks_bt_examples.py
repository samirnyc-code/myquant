"""Render 5 representative example charts for each A+ setup, to eyeball correctness.

For each setup, picks 5 trades spanning the outcome range (biggest win, upper-mid,
median, lower-mid, biggest loss) from the 5m EOD book, re-derives that day's
signal, and renders it with the full markup via brooks_bt_chart.render().
Opens all PNGs in VSCode in one shot.
"""
import sys, subprocess
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import massive
from brooks_bt_core import load_bars, day_frame, resample_tf, compute
import brooks_bt_all as A
import brooks_bt_chart as CH

BOOK = "EOD"
NAMES = {"H2L2": "High 2 / Low 2 pullback", "BOPB": "Breakout pullback",
         "REV": "Second-entry reversal", "SPIKE": "Strong breakout / spike",
         "AIFT": "Always-in follow-through", "TFO": "Trend from the open",
         "OREV": "Opening reversal", "SPCH": "Spike and channel"}
OUTDIR = ROOT / "docs" / "living" / "charts_brooks"
OUTDIR.mkdir(parents=True, exist_ok=True)


def pick_examples(df, setup, k=5):
    d = df[(df.setup == setup) & (df.tf == "5m") & (df.book == BOOK)].copy()
    if len(d) < k:
        return d
    d = d.sort_values("Rmult").reset_index(drop=True)
    idx = np.linspace(0, len(d) - 1, k).round().astype(int)          # spread across outcomes
    return d.iloc[idx]


def render_one(setup, row, tag):
    d = row["Date"]; dirn = row["dirn"]
    g5 = day_frame(load_bars.cache if hasattr(load_bars, "cache") else B, d)
    g = resample_tf(g5, 1)
    f = compute(g)
    tk = massive.load_continuous_ticks(date.fromisoformat(d)).sort_values("DateTime")
    tP = tk["Price"].values
    tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, "right") - 1
    ev = A.two_leg_events(f)
    cands = [dict(s, dir=dd, fb=s["i"]) for (dd, s) in A.signals_for(setup, ev, f) if dd == dirn]
    if not cands:
        return None
    # match the parquet row by nearest fill price
    best, bestpath, bd = None, None, 1e9
    for s in cands:
        p = CH.trade_path(f, tP, tbar, s, BOOK)
        if p is None:
            continue
        gap = abs(p["fill"] - row["fill"])
        if gap < bd:
            bd, best, bestpath = gap, s, p
    if best is None:
        return None
    out = OUTDIR / f"{setup}_{tag}_{d}_{dirn}.png"
    return CH.render(g, f, best, bestpath, BOOK, f"{NAMES[setup]}  ({setup})",
                     str(out), open_vscode=False)


def main():
    global B
    B = load_bars()
    df = pd.read_parquet(ROOT / "docs" / "living" / "brooks_bt_all_trades.parquet")
    made = []
    for setup in A.SETUPS:
        ex = pick_examples(df, setup)
        tags = ["worst", "lo", "mid", "hi", "best"][:len(ex)]
        for tag, (_, row) in zip(tags, ex.iterrows()):
            try:
                p = render_one(setup, row, tag)
                if p:
                    made.append(p); print(f"  {setup:5s} {tag:5s} {row['Date']} {row['dirn']} R={row['Rmult']:+.2f} -> ok")
                else:
                    print(f"  {setup:5s} {tag:5s} {row['Date']} -> NO MATCH")
            except Exception as e:
                print(f"  {setup:5s} {tag:5s} {row['Date']} -> ERR {e}")
    print(f"\n{len(made)} charts in {OUTDIR}")
    # open all in one VSCode call
    if made:
        try:
            subprocess.run(["code"] + made, shell=True, timeout=40)
        except Exception as e:
            print("open err", e)


if __name__ == "__main__":
    main()
