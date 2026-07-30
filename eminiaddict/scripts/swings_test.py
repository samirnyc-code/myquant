"""Bar-by-bar STRUCTURAL swing detection (not a %-ZigZag) for calibration.

Rule (candidate — please validate/correct):
  Walk bars left→right. In an up-swing, keep extending the swing HIGH while bars make
  higher highs. Confirm the swing high the first time a later bar trades BELOW THE LOW
  of the bar that made the high (a reversal bar) — then start a down-swing. Symmetric
  for lows. This is granular: it catches small swings too. `MINBARS` optionally requires
  the extreme to be at least that many bars from the last pivot (0 = every swing).

Renders a recent window with every swing numbered so the detection can be judged.
Usage: python swings_test.py [15m|5m|1D] [n_bars] [minbars]
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import sequence_lib as S

OUT = "../figures/swings_test.png"
FS = 12


def struct_swings(H, L, minbars=0):
    n = len(H)
    piv = []
    d = 0
    hi_i, hi = 0, H[0]
    lo_i, lo = 0, L[0]

    def push(i, p, k):
        if piv and piv[-1][2] == k:      # same type: keep the more extreme
            if (k == 'H' and p >= piv[-1][1]) or (k == 'L' and p <= piv[-1][1]):
                piv[-1] = (i, p, k)
            return
        if minbars and piv and abs(i - piv[-1][0]) < minbars:
            return
        piv.append((i, p, k))

    for i in range(1, n):
        if d >= 0:                        # up-swing: tracking the high
            if H[i] >= hi:
                hi, hi_i = H[i], i
            elif L[i] < L[hi_i]:          # reversal bar → confirm swing high
                push(hi_i, hi, 'H'); d = -1; lo, lo_i = L[i], i
        if d <= 0:                        # down-swing: tracking the low
            if L[i] <= lo:
                lo, lo_i = L[i], i
            elif H[i] > H[lo_i]:          # reversal bar → confirm swing low
                push(lo_i, lo, 'L'); d = 1; hi, hi_i = H[i], i
    return piv


def main():
    tf = sys.argv[1] if len(sys.argv) > 1 else "15m"
    nbars = int(sys.argv[2]) if len(sys.argv) > 2 else 180
    minbars = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    df = S.load_tf(S.CFG[tf]["tf"]).tail(nbars).reset_index(drop=True)
    n = len(df)
    H = df.High.values; L = df.Low.values
    piv = struct_swings(H, L, minbars)

    fig, ax = plt.subplots(figsize=(16, 8.5), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b")
    for i in range(n):
        o, h, l, c = df.Open[i], df.High[i], df.Low[i], df.Close[i]
        col = "#26a65b" if c >= o else "#e2453c"
        ax.plot([i, i], [l, h], color=col, lw=0.8, zorder=2)
        ax.add_patch(Rectangle((i - .3, min(o, c)), .6, abs(c - o) or .02,
                               facecolor=col, edgecolor=col, zorder=3))
    # swing structure line + numbered pivots
    xs = [p[0] for p in piv]; ys = [p[1] for p in piv]
    ax.plot(xs, ys, color="#ffd400", lw=1.1, alpha=.7, zorder=5)
    for j, (pi, pp, pk) in enumerate(piv):
        ax.scatter([pi], [pp], color="#ffd400", s=48, zorder=6)
        ax.annotate(str(j + 1), (pi, pp), textcoords="offset points",
                    xytext=(0, 9 if pk == 'H' else -15), color="#ffd400",
                    fontsize=FS * .8, ha="center", fontweight="bold")
    ax.set_title(
        f"ES {tf} — bar-by-bar STRUCTURAL swings (reversal-bar rule, minbars={minbars})   "
        f"{len(piv)} swings\nswing high confirmed when a bar trades below the low of the high bar (mirror for lows)",
        color="#eee", fontsize=FS, loc="left")
    step = max(1, n // 12)
    fmt = "%m/%d %H:%M" if tf in ("5m", "15m") else "%m/%d/%y"
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([df.DateTime[i].strftime(fmt) for i in range(0, n, step)],
                       color="#aaa", fontsize=FS * .75)
    ax.tick_params(colors="#aaa")
    for sp in ax.spines.values():
        sp.set_color("#333")
    ax.set_xlim(-1, n + 2)
    ax.grid(True, color="#141414", lw=0.5)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115, facecolor=fig.get_facecolor())
    print("wrote", OUT, f"| {len(piv)} swings over {df.DateTime.iloc[0]} .. {df.DateTime.iloc[-1]}")


if __name__ == "__main__":
    main()
