"""EXPLAIN the HVL-proximity finding visually (Samir asked "show me on a chart").

The finding in one sentence: the closer prior-day SPX spot sits to the HVL
(high-volume / gamma-flip level), the better our 2E trades do that day; trades on
days where spot is stranded >2% from the HVL actually LOSE money.

4 panels:
  A  scatter: each trade's net vs |spot-HVL|% + binned mean (the monotonic decay).
  B  two equity curves: near-HVL half vs far-HVL half of the trades.
  C  concrete NEAR example: daily spot hugging its HVL -> that day's trade won.
  D  concrete FAR  example: daily spot stranded far from HVL -> that day's trade lost.

  python scripts/regime_2e_gamma_hvl_explain.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

WT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")

gm = pd.read_csv(MAIN / "data" / "regime" / "mq_regime_daily_2007_2026_v2.csv")
gm["date"] = pd.to_datetime(gm.date).dt.date.astype(str)
gm = gm.sort_values("date").reset_index(drop=True)
gm["distpct"] = (gm.spot - gm.hvl) / gm.spot * 100

d = pd.read_csv(WT / "data" / "regime" / "gamma_hvl_20260725.csv")
d = d.sort_values("Date").reset_index(drop=True)
med = d.absdist.median()

fig = plt.figure(figsize=(15, 9), dpi=120)
gs = fig.add_gridspec(2, 2, hspace=0.32, wspace=0.22)
BLU, RED, GRN, INK = "#2a78d6", "#b23a2e", "#2e8b57", "#33454d"

# ---- A: scatter net vs proximity ----
ax = fig.add_subplot(gs[0, 0])
win = d.net > 0
ax.scatter(d.absdist[win], d.net[win], s=14, c=GRN, alpha=.5, label="winner")
ax.scatter(d.absdist[~win], d.net[~win], s=14, c=RED, alpha=.5, label="loser")
bins = np.array([0, 0.59, 1.26, 2.11, 12])
cen = [(bins[i] + min(bins[i + 1], 3)) / 2 for i in range(4)]
mean = [d[(d.absdist >= bins[i]) & (d.absdist < bins[i + 1])].net.mean() for i in range(4)]
ax.plot(cen, mean, "-o", color=INK, lw=2.5, ms=9, label="bin mean $/tr", zorder=5)
for c, m in zip(cen, mean):
    ax.annotate(f"${m:+.0f}", (c, m), textcoords="offset points", xytext=(0, 10),
                ha="center", fontweight="bold", color=INK)
for b in bins[1:-1]:
    ax.axvline(b, ls=":", color="#c3c2b7")
ax.axhline(0, color="#999", lw=1); ax.set_xlim(0, 3.2)
ax.set_xlabel("|prior-day spot − HVL|  (% of spot)  →  farther"); ax.set_ylabel("trade net ($)")
ax.set_title("A · Closer to HVL = bigger edge (bin means fall monotonically)", fontweight="bold")
ax.legend(frameon=False, fontsize=8, loc="upper right")

# ---- B: equity near vs far ----
ax = fig.add_subplot(gs[0, 1])
near = d[d.absdist <= med]; far = d[d.absdist > med]
ax.plot(range(len(near)), near.net.cumsum().values, color=BLU, lw=2.2,
        label=f"NEAR-HVL (≤{med:.2f}%)  PF {round(near.net[near.net>0].sum()/-near.net[near.net<0].sum(),2)}  +${near.net.sum()/1000:.0f}k")
ax.plot(range(len(far)), far.net.cumsum().values, color=RED, lw=2.2,
        label=f"FAR-HVL (>{med:.2f}%)  PF {round(far.net[far.net>0].sum()/-far.net[far.net<0].sum(),2)}  {far.net.sum()/1000:+.0f}k")
ax.axhline(0, color="#999", lw=1)
ax.set_xlabel("trade # (chronological, each half)"); ax.set_ylabel("cumulative net ($)")
ax.set_title("B · Same system, split by HVL distance", fontweight="bold")
ax.legend(frameon=False, fontsize=9, loc="upper left")


def day_panel(ax, exrow, title, col):
    dt = exrow.Date
    i = gm.index[gm.date == dt]
    if not len(i):
        ax.set_visible(False); return
    i = i[0]; lo, hi = max(0, i - 20), min(len(gm), i + 20)
    w = gm.iloc[lo:hi]
    x = range(len(w))
    ax.plot(x, w.spot.values, color=INK, lw=1.8, label="SPX spot (daily)")
    ax.plot(x, w.hvl.values, color=col, lw=2.2, ls="--", label="HVL level")
    ax.fill_between(x, w.spot.values, w.hvl.values, color=col, alpha=.12)
    k = i - lo
    ax.scatter([k], [w.spot.values[k]], s=140, color=col, zorder=6, edgecolor="white",
               label=f"trade day  (net ${exrow.net:+.0f})")
    ax.annotate(f"|dist| {exrow.absdist:.2f}%", (k, w.spot.values[k]), textcoords="offset points",
                xytext=(8, 12), fontweight="bold", color=col)
    ax.set_xlabel(f"trading days around {dt}"); ax.set_ylabel("index level")
    ax.set_title(title, fontweight="bold"); ax.legend(frameon=False, fontsize=8, loc="best")


# ---- C: near winner  /  D: far loser ----
nearwin = d[(d.absdist < 0.4) & (d.net > 400)].sort_values("net").iloc[-1]
farloss = d[(d.absdist > 2.5) & (d.net < 0)].sort_values("net").iloc[0]
day_panel(fig.add_subplot(gs[1, 0]), nearwin,
          "C · NEAR example: spot hugs HVL → trade WON", GRN)
day_panel(fig.add_subplot(gs[1, 1]), farloss,
          "D · FAR example: spot stranded from HVL → trade LOST", RED)

fig.suptitle("Why HVL proximity matters — the HVL acts as a magnet; 2E trades near it follow through, far from it they don't",
             fontsize=12, fontweight="bold", y=0.985)
fig.savefig(WT / "docs" / "living" / "gamma_hvl_explain_20260725.png", facecolor="white", bbox_inches="tight")
print("saved docs/living/gamma_hvl_explain_20260725.png")
print(f"near example: {nearwin.Date}  |dist| {nearwin.absdist:.2f}%  net {nearwin.net:+.0f}")
print(f"far  example: {farloss.Date}  |dist| {farloss.absdist:.2f}%  net {farloss.net:+.0f}")
print(f"NEAR half: n={len(near)} net {near.net.sum():+,.0f}   FAR half: n={len(far)} net {far.net.sum():+,.0f}")
