"""Run the Python phase machine on the REAL continuous ticks for ALL available days
(2021-2026) and dump pivots -> data/regime/py_realtick_pivots.csv. This is the 5-year
reference to diff against NT's continuous-chart export.
Schema: session,bar,side,tag,major,majlab
"""
import sys, csv, glob, os
from pathlib import Path
import pandas as pd, numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from regime_second_entry_study import phase_transitions

MYQ = Path(r"c:/Users/Admin/myquant")
TICKS = MYQ / "data" / "ticks_continuous"
OUT = MYQ / "data" / "regime" / "py_realtick_pivots.csv"
files = sorted(glob.glob(str(TICKS / "*.parquet")))
print(f"{len(files)} tick-days")

with open(OUT, "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["session", "bar", "side", "tag", "major", "majlab"])
    for i, f in enumerate(files):
        ds = os.path.basename(f)[:-8]
        t = pd.read_parquet(f, columns=["DateTime", "Price"]).sort_values("DateTime", kind="mergesort").set_index("DateTime")
        if len(t) == 0:
            continue
        c = t["Price"].resample("5min", label="left", closed="left").last()
        h = t["Price"].resample("5min", label="left", closed="left").max()
        l = t["Price"].resample("5min", label="left", closed="left").min()
        bars = pd.DataFrame({"H": h, "L": l, "C": c})
        bars["C"] = bars["C"].ffill(); bars["H"] = bars["H"].fillna(bars["C"]); bars["L"] = bars["L"].fillna(bars["C"])
        bars = bars.reset_index()
        n = len(bars); H = bars["H"].values; L = bars["L"].values; b0 = bars["DateTime"].iloc[0]
        tt = t.reset_index(); tt["b"] = ((tt["DateTime"] - b0).dt.total_seconds() // 300).astype(int)
        tt = tt[(tt.b >= 0) & (tt.b < n)]
        tr = {}
        phase_transitions(H, L, n, tt["Price"].values.astype(float), tt["b"].values.astype(int), tr)
        for p in tr["piv"]:
            w.writerow([ds, p["bar"] + 1, p["side"], p["tag"], 1 if p["major"] else 0, p.get("majlab") or ""])
        if i % 200 == 0:
            print(f"  {i}/{len(files)} {ds}")
print(f"wrote {OUT}")
