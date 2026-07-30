"""Draw measured-move Fibs on bar-by-bar STRUCTURAL swings, with ALL 6 levels per fib
and ONE consistent color per level (not colored by classification). Classification
(Trad/Ext/Fail) is a text tag. Impulse (with-trend) legs above a size filter get a fib.

Usage: python fib_render.py [15m|5m|1D] [n_bars] [minR_pct]
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
from swings_test import struct_swings

OUT = "../figures/fib_render.png"
FS = 12
# consistent per-level color coding (same everywhere)
LVL = [("100", "start", "#8a8f98", ":", 0.9),
       ("61.8", "fail", "#e2453c", "-", 1.5),
       ("50", "hwb", "#e3b341", "-", 1.7),
       ("38.2", "d382", "#e08a2b", "--", 1.1),
       ("0", "end", "#8a8f98", ":", 0.9),
       ("123.6", "tgt", "#26a65b", "--", 1.5)]


def fib(lo, hi, up):
    R = hi - lo
    L = {"start": lo, "fail": lo + .382 * R, "hwb": lo + .5 * R, "d382": lo + .618 * R,
         "end": hi, "tgt": hi + .236 * R} if up else \
        {"start": hi, "fail": hi - .382 * R, "hwb": hi - .5 * R, "d382": hi - .618 * R,
         "end": lo, "tgt": lo - .236 * R}
    L["R"] = R
    return L


def main():
    tf = sys.argv[1] if len(sys.argv) > 1 else "15m"
    nbars = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    minR_pct = float(sys.argv[3]) if len(sys.argv) > 3 else 0.35   # min leg size, % of price
    df = S.load_tf(S.CFG[tf]["tf"]).tail(nbars).reset_index(drop=True)
    n = len(df); H = df.High.values; L = df.Low.values
    piv = struct_swings(H, L)
    up_trend = df.Close.iloc[n // 2:].mean() >= df.Close.iloc[:n // 2].mean()

    fig, ax = plt.subplots(figsize=(16, 8.7), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b")
    for i in range(n):
        o, h, l, c = df.Open[i], df.High[i], df.Low[i], df.Close[i]
        col = "#2a7d54" if c >= o else "#8f3b34"
        ax.plot([i, i], [l, h], color=col, lw=0.7, zorder=2)
        ax.add_patch(Rectangle((i - .3, min(o, c)), .6, abs(c - o) or .02,
                               facecolor=col, edgecolor=col, zorder=2))

    prev_tgt = None; drawn = 0
    for k in range(len(piv) - 1):
        (a, pa, ka), (b, pb, kb) = piv[k], piv[k + 1]
        up = (ka == 'L' and kb == 'H')
        if up != up_trend:
            continue
        lo, hi = (pa, pb) if up else (pb, pa)
        fb = fib(lo, hi, up)
        if fb["R"] < minR_pct / 100.0 * hi:        # skip tiny legs (keeps it readable)
            continue
        pull = piv[k + 2][1] if k + 2 < len(piv) else None
        seg = df.iloc[b:min(n, b + 40)]
        reached = ((up and seg.High.max() >= fb["tgt"]) or
                   ((not up) and seg.Low.min() <= fb["tgt"])) if len(seg) else False
        pierced = pull is not None and ((up and pull < fb["fail"]) or ((not up) and pull > fb["fail"]))
        typ = "Trad" if reached else ("FAIL" if pierced else "weak")
        if typ == "Trad" and prev_tgt is not None and (
                (up and lo >= prev_tgt - .05 * fb["R"]) or ((not up) and hi <= prev_tgt + .05 * fb["R"])):
            typ = "Ext"
        prev_tgt = fb["tgt"]
        x1 = min(n - 1, (piv[k + 2][0] if k + 2 < len(piv) else b + 5) + 2)
        # draw ALL levels with consistent colors
        for lab, key, cc, ls, lw in LVL:
            ax.plot([b, x1], [fb[key], fb[key]], color=cc, ls=ls, lw=lw, alpha=.92, zorder=5)
            ax.text(x1 + 0.2, fb[key], lab, color=cc, fontsize=FS * .6, va="center", zorder=6)
        ax.plot([a, b], [fb["start"], fb["end"]], color="#aaa", lw=0.8, alpha=.4, zorder=4)
        tagc = "#e2453c" if typ == "FAIL" else "#e6edf3"
        ax.text(b + 0.3, fb["end"], f"{typ}{drawn+1}", color=tagc, fontsize=FS * .8,
                fontweight="bold", va="center", zorder=8)
        drawn += 1

    # consistent-color legend
    lx = 0.012
    for j, (lab, key, cc, ls, lw) in enumerate(LVL):
        ax.text(lx + j * 0.095, 0.02, f"■ {lab}", color=cc, transform=ax.transAxes,
                fontsize=FS * .8, fontweight="bold")
    ax.set_title(
        f"ES {tf} — MM Fibs on structural swings ({'UP' if up_trend else 'DOWN'} trend)   "
        f"{drawn} impulse legs, min size {minR_pct}%\nALL levels shown, one color per level (consistent). "
        f"Tag = classification (Trad hit target / Ext / FAIL pierced 61.8).",
        color="#eee", fontsize=FS, loc="left")
    step = max(1, n // 12)
    fmt = "%m/%d %H:%M" if tf in ("5m", "15m") else "%m/%d/%y"
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([df.DateTime[i].strftime(fmt) for i in range(0, n, step)],
                       color="#aaa", fontsize=FS * .75)
    ax.tick_params(colors="#aaa")
    for sp in ax.spines.values():
        sp.set_color("#333")
    ax.set_xlim(-1, n + 6)
    ax.grid(True, color="#141414", lw=0.5)
    fig.tight_layout()
    fig.savefig(OUT, dpi=115, facecolor=fig.get_facecolor())
    print("wrote", OUT, f"| {drawn} impulse fibs, {len(piv)} swings")


if __name__ == "__main__":
    main()
