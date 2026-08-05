# Price-vs-CVD divergence markup for 7/13, from OUR footprint pipeline.
# Mechanical: swing highs/lows = local extrema over +/-W bars; divergence when
# consecutive swings disagree between price and CVD:
#   bearish: price higher-high, CVD lower-high
#   bullish: price lower-low,  CVD higher-low
# NOTE: a swing is only CONFIRMED W bars after it prints (same repaint caveat as
# mzDeltaDivergence / backlog #4) — confirmation bar drawn as a gray tick.
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = r"c:\Users\Admin\myquant"
DAY = "2026-07-13"
W = 12  # swing window (bars each side); 2000-lot bars -> roughly 8-12 min

bars = pd.read_csv(ROOT + r"\data\footprint\ES_bars.csv", parse_dates=["BarTime"])
met = pd.read_csv(ROOT + r"\data\footprint\ES_metrics.csv", parse_dates=["BarTime"])
df = bars.merge(met[["BarIdx", "BarTime", "cvd"]], on=["BarIdx", "BarTime"])
df = df[df.BarTime.dt.strftime("%Y-%m-%d") == DAY].reset_index(drop=True)
df["x"] = np.arange(len(df))

hi, lo, cv = df.High.to_numpy(), df.Low.to_numpy(), df.cvd.to_numpy()
n = len(df)
swings = []  # (x, 'H'|'L', price, cvd)
for i in range(W, n - W):
    if hi[i] == hi[i - W:i + W + 1].max() and hi[i] > hi[i - W:i].max():
        swings.append((i, "H", hi[i], cv[i]))
    if lo[i] == lo[i - W:i + W + 1].min() and lo[i] < lo[i - W:i].min():
        swings.append((i, "L", lo[i], cv[i]))
swings.sort()

divs = []
last = {"H": None, "L": None}
for s in swings:
    i, t, p, c = s
    prev = last[t]
    if prev is not None:
        pi, _, pp, pc = prev
        if t == "H" and p > pp and c < pc:
            divs.append(("bearish", prev, s))
        if t == "L" and p < pp and c > pc:
            divs.append(("bullish", prev, s))
    last[t] = s

print(f"swings={len(swings)} divergences={len(divs)}")
for d, a, b in divs:
    print(f"  {d}: {df.BarTime[a[0]]:%H:%M} p={a[2]:g} cvd={a[3]:g} -> "
          f"{df.BarTime[b[0]]:%H:%M} p={b[2]:g} cvd={b[3]:g} (confirms {df.BarTime[min(b[0]+W, n-1)]:%H:%M})")

UP, DN = "#2e9e4f", "#d64545"
BULL, BEAR = "#0e7a3b", "#b02020"
fig, (axP, axC) = plt.subplots(2, 1, figsize=(24, 13), sharex=True,
                               gridspec_kw={"height_ratios": [2.4, 1], "hspace": 0.05})
for _, r in df.iterrows():
    c = UP if r.Close >= r.Open else DN
    axP.plot([r.x, r.x], [r.Low, r.High], color=c, linewidth=0.6, zorder=2)
    l, h = sorted([r.Open, r.Close])
    axP.add_patch(Rectangle((r.x - 0.38, l), 0.76, max(h - l, 0.05),
                            facecolor=c, edgecolor=c, linewidth=0.4, zorder=3))
axC.plot(df.x, df.cvd, color="#1f5fa8", linewidth=1.6)
axC.axhline(0, color="#666666", linewidth=0.8)

for kind, a, b in divs:
    col = BULL if kind == "bullish" else BEAR
    off = -2.0 if kind == "bullish" else 2.0
    axP.plot([a[0], b[0]], [a[2] + off * 0.4, b[2] + off * 0.4], color=col, linewidth=2.2,
             linestyle="-", zorder=6)
    axC.plot([a[0], b[0]], [a[3], b[3]], color=col, linewidth=2.2, zorder=6)
    axP.annotate(f"{kind} div\n{df.BarTime[b[0]]:%H:%M}", xy=(b[0], b[2] + off),
                 xytext=(b[0] + 6, b[2] + off * 5), fontsize=10, fontweight="bold", color=col,
                 arrowprops=dict(arrowstyle="->", color=col, lw=1.4))
    conf = min(b[0] + W, n - 1)
    axP.axvline(conf, color="#888888", linewidth=0.8, linestyle=":", alpha=0.6, zorder=1)
    axP.text(conf, axP.get_ylim()[0], "", fontsize=7)

axP.set_title(f"ES {DAY} — price vs CVD divergences (ours; swings = ±{W}-bar extrema; "
              "dotted gray = bar where the swing CONFIRMS, i.e. earliest honest signal)", fontsize=13)
axP.grid(alpha=0.18)
axC.grid(alpha=0.18)
axC.set_ylabel("CVD (session)")
ticks = df.x[:: max(n // 16, 1)]
axC.set_xticks(ticks)
axC.set_xticklabels(df.BarTime.dt.strftime("%H:%M")[:: max(n // 16, 1)], fontsize=9)
out = ROOT + r"\scratchpad\cvd_divergence_20260713.png"
fig.savefig(out, dpi=110, bbox_inches="tight")
print("saved", out)
