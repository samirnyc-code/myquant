"""Equity curves for the RevFT x regime books. 2026-07-25 (S85). Reads the saved parquet.
    python scripts/revft_regime_chart.py
"""
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
T = ROOT / "data" / "regime" / "revft_regime_full_20260725.parquet"
OUT = ROOT / "docs" / "living" / "revft_regime_equity_20260725.png"

t = pd.read_parquet(T).sort_values("Date").reset_index(drop=True)
L, S = t.dir == "L", t.dir == "S"
bull, bear, neu = t.reg == "BULL", t.reg == "BEAR", t.reg == "NEUTRAL"
WT = (L & bull) | (S & bear); CT = (L & bear) | (S & bull); notCT = WT | neu
neg = t.mq == "negative_gamma"

books = [
    ("BASE  all / 1R target", pd.Series(True, t.index), "n1r", "#b23a2e", "--"),
    ("CT  fade-a-trend / wide+EOD", CT, "w30eod", "#8b5cf6", ":"),
    ("DROP-CT (WT|NEU) / wide+EOD", notCT, "w30eod", "#2a78d6", "-"),
    ("NEG-gamma & DROP-CT / wide+EOD", neg & notCT, "w30eod", "#1f7a3d", "-"),
]
fig, ax = plt.subplots(figsize=(12, 6.2))
for name, m, col, c, ls in books:
    d = t[m]
    eq = d[col].cumsum().values
    x = pd.to_datetime(d.Date).values
    ax.plot(x, eq, label=f"{name}   (end ${eq[-1]:>+,.0f}, n={len(d)})", color=c, ls=ls, lw=1.8)
ax.axhline(0, color="#999", lw=0.8)
ax.set_title("RevFT x regime engine — cumulative net $ (1 ES, $5 RT + 1t slip, EOD flat)\n"
             "gate = phase-machine (drop counter-trend) + MQ gamma;  exit = 2E wide-vol stop, hold to close",
             fontsize=11)
ax.set_ylabel("cumulative net $"); ax.legend(loc="upper left", fontsize=9, framealpha=0.9)
ax.grid(alpha=0.25)
for s in ("top", "right"): ax.spines[s].set_visible(False)
fig.tight_layout(); fig.savefig(OUT, facecolor="white", dpi=110)
print("saved", OUT)
