# Same analysis as render_div_at_marks.py (CVD at the two tests, anchored on the
# user's 6 marks, 7/13) but rendered as SIX SEPARATE large PNGs — one per setup —
# so the artifact can interleave chart -> explanation. Wider context window and
# bigger fonts than the 2x3 composite.
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

for k, (_, m) in enumerate(marks.iterrows(), start=1):
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

    fig, (axP, axC) = plt.subplots(
        2, 1, figsize=(15, 8.5), sharex=True,
        gridspec_kw={"height_ratios": [2.4, 1], "hspace": 0.08})
    a, b = max(t1 - 18, 0), min(t2 + 22, n)
    seg = df.iloc[a:b]
    for _, rr in seg.iterrows():
        c = UP if rr.Close >= rr.Open else DN
        x = rr.name
        axP.plot([x, x], [rr.Low, rr.High], color=c, linewidth=1.0, zorder=2)
        l, h = sorted([rr.Open, rr.Close])
        axP.add_patch(Rectangle((x - 0.38, l), 0.76, max(h - l, 0.05),
                                facecolor=c, edgecolor=c, linewidth=0.5, zorder=3))
    col_d = (BEAR if m.direction == "short" else BULL) if div else "#7a7a7a"
    off = 0.7 if m.direction == "short" else -0.7
    axP.plot([t1, t2], [p1 + off, p2 + off], color=col_d, linewidth=3.2, zorder=6)
    axP.scatter([t1, t2], [p1 + off, p2 + off], s=55, color=col_d, zorder=7)
    for t, p, lab in [(t1, p1, "test 1"), (t2, p2, "test 2")]:
        axP.annotate(f"{lab}\n{df.BarTime[t]:%H:%M}",
                     (t, p + (1.9 if m.direction == "short" else -1.9)),
                     ha="center", fontsize=11, fontweight="bold", color=col_d)
    my = df.Low[mi] - 0.8 if m.direction == "long" else df.High[mi] + 0.8
    axP.scatter([mi], [my], marker="^" if m.direction == "long" else "v", s=160,
                color=UP if m.direction == "long" else DN, edgecolor="black",
                linewidth=0.8, zorder=8)
    axC.plot(seg.index, seg.cvd, color="#1f5fa8", linewidth=2.0)
    axC.plot([t1, t2], [c1, c2], color=col_d, linewidth=3.2, zorder=6)
    axC.scatter([t1, t2], [c1, c2], s=50, color=col_d, zorder=7)
    lab = {"fade2": "2nd-entry fade", "bopb": "BOPB"}.get(m.setup, m.setup)
    verdict = "CVD DIVERGED" if div else "CVD confirmed (no classic divergence)"
    axP.set_title(f"{m.bar_time:%H:%M}  {lab} {m.direction.upper()}  —  "
                  f"tests {df.BarTime[t1]:%H:%M} vs {df.BarTime[t2]:%H:%M}:  "
                  f"CVD {c1:.0f} → {c2:.0f}  (Δ{c2 - c1:+.0f})  •  {verdict}",
                  fontsize=14, fontweight="bold",
                  color=col_d if div else "#444444", pad=12)
    y0, y1 = axP.get_ylim()
    axP.set_ylim(y0 - 2.0, y1 + 2.0)
    axP.grid(alpha=0.18); axC.grid(alpha=0.18)
    axP.set_ylabel("ES price", fontsize=11)
    axC.set_ylabel("session CVD", fontsize=11)
    step = max((b - a) // 9, 1)
    axC.set_xticks(range(a, b, step))
    axC.set_xticklabels(df.BarTime[a:b:step].dt.strftime("%H:%M"), fontsize=10)
    axP.tick_params(labelsize=10); axC.tick_params(labelsize=10)
    ym = np.concatenate([seg.Low.to_numpy(), [my]])
    out = ROOT + rf"\scratchpad\div_mark_{k}_{m.bar_time:%H%M}.png"
    fig.savefig(out, dpi=125, bbox_inches="tight")
    plt.close(fig)
    print("saved", out)
