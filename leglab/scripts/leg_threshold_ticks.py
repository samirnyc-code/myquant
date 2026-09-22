"""
What is 0.15 x ADR(8) — the leg/"scalp" threshold — in ES points and TICKS?
ES: 1 tick = 0.25 pts = $12.50; 1 pt = 4 ticks = $50.
ADR(8) = mean of the prior 8 RTH daily ranges (high-low). Data ends 2026-07-24.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
df = pd.read_parquet(ROOT / "data" / "bars" / "_db_es_5m_rth.parquet")
df["DateTime"] = pd.to_datetime(df["DateTime"]); df["date"] = df["DateTime"].dt.date
d = df.groupby("date").agg(h=("High", "max"), l=("Low", "min"))
d["range"] = d["h"] - d["l"]
d["adr8"] = d["range"].shift(1).rolling(8).mean()
d["thr_pts"] = 0.15 * d["adr8"]
d["thr_ticks"] = d["thr_pts"] / 0.25
d.index = pd.to_datetime(d.index)

latest = d.dropna().iloc[-1]
last90 = d.dropna().iloc[-90:]
last1y = d[d.index >= d.index.max() - pd.Timedelta(days=365)].dropna()

print("0.15 x ADR(8) leg/scalp threshold (ES):\n")
print(f"LATEST ({d.dropna().index[-1].date()}): ADR8={latest['adr8']:.1f} pts | "
      f"0.15xADR = {latest['thr_pts']:.1f} pts = {latest['thr_ticks']:.0f} ticks (${latest['thr_ticks']*12.5:.0f})")
for name, w in [("last 90 sessions", last90), ("last 12 months", last1y)]:
    print(f"\n{name}:  ADR8 median={w['adr8'].median():.1f} pts")
    print(f"   0.15xADR: median={w['thr_pts'].median():.1f} pts ({w['thr_ticks'].median():.0f} ticks) | "
          f"range {w['thr_pts'].min():.1f}-{w['thr_pts'].max():.1f} pts "
          f"({w['thr_ticks'].min():.0f}-{w['thr_ticks'].max():.0f} ticks)")

# ---- by year (avg scalp = 0.15 x ADR(8)) ----
dd = d.dropna().copy()
dd["year"] = dd.index.year
by = dd.groupby("year").agg(
    days=("thr_pts", "size"),
    adr8_pts=("adr8", "mean"),
    scalp_pts=("thr_pts", "mean"),
    scalp_ticks=("thr_ticks", "mean"),
).round(2)
by["scalp_$"] = (by["scalp_ticks"] * 12.5).round(0)
print("\nAVG SCALP (0.15 x ADR8) BY YEAR — ES:")
print(by.to_string())
print("(2010 & 2026 are partial years)")

OUT = ROOT / "leglab" / "outputs"
by.to_csv(OUT / "leg_scalp_by_year_20260906.csv")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(13, 6))
partial = {2010, 2026}
colors = ["#9db8d6" if y in partial else "#2b5fa8" for y in by.index]
bars = ax.bar(by.index.astype(str), by["scalp_ticks"], color=colors)
ax.bar_label(bars, labels=[f"{t:.0f}t\n{p:.1f}pt" for t, p in zip(by["scalp_ticks"], by["scalp_pts"])],
             fontsize=8, padding=2)
ax.set_ylabel("avg scalp = 0.15 x ADR(8)  [ES ticks]")
ax.set_title("ES avg 'scalp' (0.15xADR8) by year, 2010-2026  (light = partial year)")
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
png = OUT / "leg_scalp_by_year_20260906.png"
fig.savefig(png, dpi=130)
print(f"\ncsv -> {OUT / 'leg_scalp_by_year_20260906.csv'}")
print(f"png -> {png}")
