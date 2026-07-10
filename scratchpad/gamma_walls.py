"""
Call-resistance / Put-support levels from OptionsDX SPX EOD chains.

CAVEAT: this dataset has NO open interest, only daily VOLUME + per-strike gamma.
Classic SpotGamma/MenthorQ walls use OI x gamma. Here we proxy positioning with:
  - VOLUME  (where the day's flow concentrated)          -> "volume wall"
  - GAMMA x VOLUME (flow weighted by gamma intensity)    -> "gamma-weighted wall"
Both aggregate across ALL expirations quoted that day (total book, EOD snapshot).

Call resistance = strike ABOVE spot with the biggest CALL metric.
Put support     = strike BELOW spot with the biggest PUT  metric.
"""
import sys, glob, os
import pandas as pd
import numpy as np

DATE = sys.argv[1] if len(sys.argv) > 1 else "2023-12-29"
DDIR = r"c:\Users\Admin\myquant\data\optionsdx"

ym = DATE[:4] + DATE[5:7]
path = os.path.join(DDIR, f"spx_eod_{ym}.txt")
if not os.path.exists(path):
    sys.exit(f"No file {path}")

df = pd.read_csv(path)
df.columns = [c.strip().strip("[]").lower() for c in df.columns]
df = df[["quote_date","underlying_last","dte","c_gamma","c_volume",
         "strike","p_gamma","p_volume"]]
df["quote_date"] = df["quote_date"].astype(str).str.strip()
d = df[df["quote_date"] == DATE].copy()
if d.empty:
    sys.exit(f"No rows for {DATE}. Available tail: {sorted(df.quote_date.unique())[-5:]}")

for c in ["underlying_last","dte","c_gamma","c_volume","strike","p_gamma","p_volume"]:
    d[c] = pd.to_numeric(d[c], errors="coerce")
spot = d["underlying_last"].iloc[0]

# aggregate across all expirations by strike
g = d.groupby("strike").agg(
    c_vol=("c_volume","sum"), p_vol=("p_volume","sum"),
    c_gam=("c_gamma","mean"), p_gam=("p_gamma","mean"),
).reset_index()
g["c_gv"] = g["c_vol"] * g["c_gam"].abs()
g["p_gv"] = g["p_vol"] * g["p_gam"].abs()

above = g[g["strike"] > spot]
below = g[g["strike"] < spot]

def wall(sub, col):
    if sub.empty or sub[col].max() == 0: return (np.nan, 0)
    r = sub.loc[sub[col].idxmax()]
    return (r["strike"], r[col])

print(f"\n=== SPX {DATE}  spot={spot:.2f}  ({len(d)} chain rows, "
      f"{d['dte'].nunique()} expiries) ===\n")

cr_v = wall(above, "c_vol");  ps_v = wall(below, "p_vol")
cr_g = wall(above, "c_gv");   ps_g = wall(below, "p_gv")

print(f"CALL RESISTANCE (strike above spot, max call metric)")
print(f"   volume wall        : {cr_v[0]:.0f}   (call vol {cr_v[1]:,.0f})   {cr_v[0]-spot:+.0f} pts")
print(f"   gamma-weighted wall: {cr_g[0]:.0f}   {cr_g[0]-spot:+.0f} pts")
print(f"\nPUT SUPPORT (strike below spot, max put metric)")
print(f"   volume wall        : {ps_v[0]:.0f}   (put vol {ps_v[1]:,.0f})   {ps_v[0]-spot:+.0f} pts")
print(f"   gamma-weighted wall: {ps_g[0]:.0f}   {ps_g[0]-spot:+.0f} pts")

def top(sub, col, label, n=8, asc=False):
    t = sub.sort_values(col, ascending=asc).head(n)
    print(f"\n-- top {label} by {col} --")
    for _, r in t.iterrows():
        bar = "#" * int(40 * r[col] / (sub[col].max() or 1))
        print(f"   {r['strike']:>7.0f}  {r[col]:>10,.0f}  {bar}")

top(above, "c_vol", "CALL strikes above spot")
top(below, "p_vol", "PUT strikes below spot")
