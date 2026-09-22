# Divergence check ANCHORED ON THE USER'S 6 MARKS (7/13).
# For each mark: test2 = the extreme touched at the setup (high for shorts / low for
# longs, within +/-3 bars of the mark); test1 = the prior push into that extreme
# (max/min over the 30 bars before). Compare session CVD (and bar delta) at the two
# tests. One zoomed panel-pair (price + CVD) per trade.
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = r"c:\Users\Admin\myquant"
DAY = "2026-07-13"
UP, DN = "#2e9e4f", "#d64545"
BULL, BEAR = "#0e7a3b", "#b02020"

bars = pd.read_csv(ROOT + r"\data\footprint\ES_bars.csv", parse_dates=["BarTime"])
met = pd.read_csv(ROOT + r"\data\footprint\ES_metrics.csv", parse_dates=["BarTime"])
df = bars.merge(met[["BarIdx", "BarTime", "cvd", "delta"]], on=["BarIdx", "BarTime"],
                suffixes=("", "_m"))
df = df[df.BarTime.dt.strftime("%Y-%m-%d") == DAY].reset_index(drop=True)
marks = pd.read_csv(ROOT + r"\data\annotations\marks.csv", parse_dates=["bar_time"])
marks = marks[marks.day == DAY].reset_index(drop=True)

hi, lo, cv, dlt = df.High.to_numpy(), df.Low.to_numpy(), df.cvd.to_numpy(), df.Delta.to_numpy()
n = len(df)

results = []
for _, m in marks.iterrows():
    mi = int(m.bar_idx)
    if m.direction == "short":
        j0, j1 = max(mi - 3, 0), min(mi + 4, n)
        t2 = j0 + int(hi[j0:j1].argmax())
        k0 = max(t2 - 30, 0)
        t1 = k0 + int(hi[k0:t2 - 1].argmax()) if t2 - 1 > k0 else t2
        p1, p2, c1, c2 = hi[t1], hi[t2], cv[t1], cv[t2]
        div = c2 < c1
    else:
        j0, j1 = max(mi - 3, 0), min(mi + 4, n)
        t2 = j0 + int(lo[j0:j1].argmin())
        k0 = max(t2 - 30, 0)
        t1 = k0 + int(lo[k0:t2 - 1].argmin()) if t2 - 1 > k0 else t2
        p1, p2, c1, c2 = lo[t1], lo[t2], cv[t1], cv[t2]
        div = c2 > c1
    results.append(dict(m=m, t1=t1, t2=t2, p1=p1, p2=p2, c1=c1, c2=c2, div=div))
    lab = {"fade2": "2nd-entry fade", "bopb": "BOPB"}.get(m.setup, m.setup)
    print(f"{m.bar_time:%H:%M} {lab} {m.direction.upper():5s}  "
          f"test1 {df.BarTime[t1]:%H:%M} p={p1:g} cvd={c1:g} delta={dlt[t1]:g}  ->  "
          f"test2 {df.BarTime[t2]:%H:%M} p={p2:g} cvd={c2:g} delta={dlt[t2]:g}  "
          f"dCVD={c2-c1:+g}  {'DIVERGED' if div else 'no divergence'}")

fig = plt.figure(figsize=(22, 16))
gs = fig.add_gridspec(6, 2, height_ratios=[2.2, 1] * 3, hspace=0.55, wspace=0.10)

for k, r in enumerate(results):
    row, col = (k // 2) * 2, k % 2
    axP = fig.add_subplot(gs[row, col])
    axC = fig.add_subplot(gs[row + 1, col], sharex=axP)
    m, t1, t2 = r["m"], r["t1"], r["t2"]
    a, b = max(t1 - 12, 0), min(t2 + 15, n)
    seg = df.iloc[a:b]
    for _, rr in seg.iterrows():
        c = UP if rr.Close >= rr.Open else DN
        x = rr.name
        axP.plot([x, x], [rr.Low, rr.High], color=c, linewidth=0.7, zorder=2)
        l, h = sorted([rr.Open, rr.Close])
        axP.add_patch(Rectangle((x - 0.38, l), 0.76, max(h - l, 0.05),
                                facecolor=c, edgecolor=c, linewidth=0.4, zorder=3))
    col_d = (BEAR if m.direction == "short" else BULL) if r["div"] else "#7a7a7a"
    off = 0.7 if m.direction == "short" else -0.7
    axP.plot([t1, t2], [r["p1"] + off, r["p2"] + off], color=col_d, linewidth=2.6, zorder=6)
    axP.scatter([t1, t2], [r["p1"] + off, r["p2"] + off], s=34, color=col_d, zorder=7)
    mi = int(m.bar_idx)
    my = df.Low[mi] - 0.8 if m.direction == "long" else df.High[mi] + 0.8
    axP.scatter([mi], [my], marker="^" if m.direction == "long" else "v", s=90,
                color=UP if m.direction == "long" else DN, edgecolor="black",
                linewidth=0.6, zorder=8)
    axC.plot(seg.index, seg.cvd, color="#1f5fa8", linewidth=1.5)
    axC.plot([t1, t2], [r["c1"], r["c2"]], color=col_d, linewidth=2.6, zorder=6)
    axC.scatter([t1, t2], [r["c1"], r["c2"]], s=30, color=col_d, zorder=7)
    lab = {"fade2": "2nd-entry fade", "bopb": "BOPB"}.get(m.setup, m.setup)
    verdict = "CVD DIVERGED" if r["div"] else "CVD confirmed (no div)"
    axP.set_title(f"{m.bar_time:%H:%M}  {lab} {m.direction.upper()}  —  "
                  f"tests {df.BarTime[t1]:%H:%M} vs {df.BarTime[t2]:%H:%M}:  "
                  f"CVD {r['c1']:.0f} → {r['c2']:.0f}  (Δ{r['c2']-r['c1']:+.0f})  •  {verdict}",
                  fontsize=11, fontweight="bold",
                  color=col_d if r["div"] else "#444444")
    axP.grid(alpha=0.18); axC.grid(alpha=0.18)
    axC.set_ylabel("CVD", fontsize=8)
    step = max((b - a) // 6, 1)
    axC.set_xticks(range(a, b, step))
    axC.set_xticklabels(df.BarTime[a:b:step].dt.strftime("%H:%M"), fontsize=8)
    plt.setp(axP.get_xticklabels(), visible=False)

fig.suptitle("ES 2026-07-13 — CVD at the two tests of the extreme, for YOUR 6 marks only "
             "(gray line = no divergence at that setup)", fontsize=14, y=0.995)
out = ROOT + r"\scratchpad\div_at_marks_20260713.png"
fig.savefig(out, dpi=110, bbox_inches="tight")
print("saved", out)
