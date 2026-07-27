"""Build 5-minute RTH bars for ALL tick days -> one parquet.

Source: data/ticks_continuous/*.parquet  (RTH trade ticks, 2021-06..2026-07,
cols DateTime/Price/Volume, session 08:30-15:15 CT).
Output: research/scalp_swing/es_5m_rth.parquet  (one row per 5M bar, +Date, +session bar index).

Bars are LEFT-labelled (bar 08:30 covers [08:30,08:35)). This is the fast
iteration dataset for signal generation; final configs are re-checked on raw
ticks by engine.py for exact fills.
"""
import glob, os
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(r"c:\Users\Admin\myquant")
SRC = ROOT / "data" / "ticks_continuous"
OUT = ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet"

files = sorted(glob.glob(str(SRC / "*.parquet")))
print(f"{len(files)} tick days")

rows = []
for i, f in enumerate(files):
    t = pd.read_parquet(f, columns=["DateTime", "Price", "Volume"])
    if len(t) == 0:
        continue
    t = t.set_index("DateTime").sort_index()
    o = t["Price"].resample("5min", label="left", closed="left").first()
    h = t["Price"].resample("5min", label="left", closed="left").max()
    l = t["Price"].resample("5min", label="left", closed="left").min()
    c = t["Price"].resample("5min", label="left", closed="left").last()
    v = t["Volume"].resample("5min", label="left", closed="left").sum()
    n = t["Price"].resample("5min", label="left", closed="left").count()
    bar = pd.DataFrame({"Open": o, "High": h, "Low": l, "Close": c, "Volume": v, "Ticks": n}).dropna(subset=["Open"])
    bar = bar[bar["Ticks"] > 0]
    bar = bar.reset_index().rename(columns={"index": "DateTime", "DateTime": "DateTime"})
    bar["Date"] = bar["DateTime"].dt.date.astype(str)
    bar["bar"] = range(len(bar))  # session bar index (0 = 08:30)
    rows.append(bar)
    if i % 200 == 0:
        print(f"  {i}/{len(files)} {os.path.basename(f)}")

allb = pd.concat(rows, ignore_index=True)
allb.to_parquet(OUT)
print(f"WROTE {OUT}  shape={allb.shape}  {allb.Date.min()}..{allb.Date.max()}")
print(allb.head(4).to_string())
print("bars/day median:", allb.groupby("Date").size().median())
