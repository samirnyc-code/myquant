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
