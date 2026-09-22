"""Draw a REAL completed Halsey measured move on 15-minute ES (from find_mm_trades):
the leg, the Fib, the pullback that TAGS the 50% HWB, holds the 61.8%, and the run
to the 123.6% target. Entry / pullback-low / target-hit are marked.

Usage: python draw_mm_trade.py [rank]   (rank into the recent-first list; default picks
a clean recent LONG). Output: figures/es_15m_mm_trade.png
Labels use the no-overlap style (lines stop at data end + leaders); FONT_SCALE knob.
"""
import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

import find_mm_trades as F

OUT = "../figures/es_15m_mm_trade.png"
PAD_L, PAD_R = 10, 10        # bars of context on each side
FONT_SCALE = float(os.environ.get("EA_FONT_SCALE", 1.25))
LABEL_FS, TICK_FS, TITLE_FS = 12.5 * FONT_SCALE, 10.5 * FONT_SCALE, 12.5 * FONT_SCALE


def pick(res, rank):
    if rank is not None:
        return res[rank]
    # default: a clean recent LONG with a visible pullback and run
    for r in res:  # res is recent-first
        if r["up"] and 3 <= r["bars_pull"] <= 22 and 6 <= r["bars_tgt"] <= 34 and r["R"] >= 60:
            return r
    return res[0]


def main():
    df = F.load()
    res = F.scan(df)
    res.sort(key=lambda r: -r["i1"])
    rank = int(sys.argv[1]) if len(sys.argv) > 1 else None
    t = pick(res, rank)
    up = t["up"]
    a = max(0, t["i0"] - PAD_L)
    b = min(len(df) - 1, t["i_tgt"] + PAD_R)
    win = df.iloc[a:b + 1].reset_index(drop=True)
    n = len(win)

    def gi(idx):  # global index -> window index
        return idx - a

    plt.rcParams.update({"font.size": 10})
    fig, ax = plt.subplots(figsize=(15, 8.5), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b")
    up_c, dn_c = "#26a65b", "#e2453c"
    w = 0.6
    for i in range(n):
        o, h, l, c = win.Open[i], win.High[i], win.Low[i], win.Close[i]
        col = up_c if c >= o else dn_c
        ax.plot([i, i], [l, h], color=col, lw=0.8, zorder=2)
        ax.add_patch(Rectangle((i - w / 2, min(o, c)), w, abs(c - o) or 0.02,
                               facecolor=col, edgecolor=col, zorder=3))

    L, H, R = t["L"], t["H"], t["R"]
    lv100 = L if up else H
    lv0 = H if up else L
    hwb, fail, tgt = t["hwb"], t["fail"], t["tgt"]

    # anchor line (the seed leg)
    ax.plot([gi(t["i0"]), gi(t["i1"])], [lv100, lv0], color="#888", ls="--", lw=1.2, zorder=4)
    ax.scatter([gi(t["i0"]), gi(t["i1"])], [lv100, lv0], color="#ffd400", s=70, zorder=6)

    LINE_END = n - 0.5
    for y, color, lw, ls in [(lv100, "#bbbbbb", 1.2, ":"), (fail, "#e2453c", 1.6, "-"),
                             (hwb, "#ffd400", 1.6, "-"), (lv0, "#bbbbbb", 1.2, ":"),
                             (tgt, "#26a65b", 2.0, "-")]:
        ax.plot([gi(t["i0"]), LINE_END], [y, y], color=color, lw=lw, ls=ls, zorder=5)

    # trade markers
    ax.scatter([gi(t["i_entry"])], [hwb], marker="^" if up else "v", s=150,
               color="#26d07c", edgecolor="white", lw=0.8, zorder=8)
    ax.annotate("ENTRY (50%)", (gi(t["i_entry"]), hwb), textcoords="offset points",
                xytext=(0, -22 if up else 14), color="#26d07c", fontsize=LABEL_FS * .8,
                fontweight="bold", ha="center")
    ax.scatter([gi(t["i_tgt"])], [tgt], marker="*", s=260, color="#26a65b",
               edgecolor="white", lw=0.8, zorder=8)
    ax.annotate("TARGET HIT", (gi(t["i_tgt"]), tgt), textcoords="offset points",
                xytext=(0, 12 if up else -20), color="#26a65b", fontsize=LABEL_FS * .8,
                fontweight="bold", ha="center")

    # right-margin labels with de-collision (never overlap)
    labels = [
        {"y": lv100, "c": "#bbbbbb", "t": f"100% (start)  {lv100:,.2f}"},
        {"y": fail, "c": "#e2453c", "t": f"61.8% FAILURE  {fail:,.2f}"},
        {"y": hwb, "c": "#ffd400", "t": f"50% HWB (entry)  {hwb:,.2f}"},
        {"y": lv0, "c": "#bbbbbb", "t": f"0% (end)  {lv0:,.2f}"},
        {"y": tgt, "c": "#26a65b", "t": f"123.6% TARGET  {tgt:,.2f}"},
    ]
    lo_ = min(win.Low.min(), min(d["y"] for d in labels))
    hi_ = max(win.High.max(), max(d["y"] for d in labels))
    span = hi_ - lo_
    ax.set_ylim(lo_ - 0.05 * span, hi_ + 0.06 * span)
    ymax_l = ax.get_ylim()[1]
    gap = 0.052 * span * FONT_SCALE
    labels.sort(key=lambda d: d["y"])
    for d in labels:
        d["ty"] = d["y"]
    for k in range(1, len(labels)):
        if labels[k]["ty"] - labels[k - 1]["ty"] < gap:
            labels[k]["ty"] = labels[k - 1]["ty"] + gap
    over = labels[-1]["ty"] - (ymax_l - 0.01 * span)
    if over > 0:
        for d in labels:
            d["ty"] -= over
        for k in range(len(labels) - 2, -1, -1):
            if labels[k + 1]["ty"] - labels[k]["ty"] < gap:
                labels[k]["ty"] = labels[k + 1]["ty"] - gap
    for d in labels:
        ax.plot([LINE_END, n + 0.4], [d["y"], d["ty"]], color=d["c"], lw=0.7, alpha=.6,
                zorder=4, clip_on=False)
        ax.text(n + 1.0, d["ty"], d["t"], color=d["c"], va="center", fontsize=LABEL_FS,
                fontweight="bold", clip_on=False)

    dirtxt = "LONG" if up else "SHORT"
    ax.set_title(
        f"ES 15-min — COMPLETED Halsey Measured Move ({dirtxt})   "
        f"tagged 50%, held 61.8%, hit 123.6% target\n"
        f"leg {t['dL']} {lv100:,.2f} → {t['dH']} {lv0:,.2f}  (R {R:,.1f})   "
        f"entry {t['d_entry']} @ {hwb:,.2f}   target {t['d_tgt']} @ {tgt:,.2f}",
        color="#eee", fontsize=TITLE_FS, loc="left")

    step = max(1, n // 10)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([win.DateTime[i].strftime("%m/%d %H:%M") for i in range(0, n, step)],
                       color="#aaa", rotation=0, fontsize=TICK_FS)
    ax.tick_params(colors="#aaa", labelsize=TICK_FS)
    for s in ax.spines.values():
        s.set_color("#333")
    ax.set_xlim(-1, n + 12)
    ax.grid(True, color="#1c1c1c", lw=0.5)
    fig.tight_layout()
    fig.savefig(OUT, dpi=130, facecolor=fig.get_facecolor())
    print("wrote", OUT)
    print(f"{dirtxt}  leg {t['dL']} {lv100:,.2f} -> {t['dH']} {lv0:,.2f}  R={R:,.1f}")
    print(f"entry(HWB) {hwb:,.2f} @ {t['d_entry']}  fail {fail:,.2f}  target {tgt:,.2f} @ {t['d_tgt']}")


if __name__ == "__main__":
    main()
