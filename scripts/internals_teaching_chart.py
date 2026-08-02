#!/usr/bin/env python
"""internals_teaching_chart.py — one plain-English annotated day: does TICK confirm the turn?

Top panel: ES 5M candles with the day's HIGH and LOW marked.
Bottom panel: NYSE TICK, with +/-800 and +/-1000 extreme lines.
Text is written ON the chart, computed from the data, so the reading is self-explanatory:
  - at the day low: was TICK at an extreme (confirmed) and how far did price bounce after?
  - at the day high: same question.

Usage: python scripts/internals_teaching_chart.py YYYY-MM-DD [YYYY-MM-DD ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"
FIG_DIR = ROOT / "eminiaddict" / "figures"
C_UP, C_DN = "#26a65b", "#e2453c"


def load():
    files = sorted(MASTER_DIR.glob("internals_es_5m_*.parquet"))
    if not files:
        raise SystemExit("! run ingest_nt_internals.py first")
    return pd.read_parquet(files[-1]).reset_index(drop=True)


def draw(m, day):
    g = m[m["DateTime"].dt.normalize() == pd.Timestamp(day)].reset_index(drop=True)
    if len(g) < 10:
        print(f"! no data for {day}"); return None
    H = g["es_high"].values; L = g["es_low"].values; O = g["es_open"].values; C = g["es_close"].values
    n = len(g)
    hi_i = int(np.argmax(H)); lo_i = int(np.argmin(L))
    tick_at_hi = g.loc[hi_i, "tick_high"]; tick_at_lo = g.loc[lo_i, "tick_low"]
    # bounce after the low = highest high AFTER the low; drop after the high = lowest low AFTER
    bounce = (H[lo_i + 1:].max() - L[lo_i]) if lo_i + 1 < n else 0.0
    drop = (H[hi_i] - L[hi_i + 1:].min()) if hi_i + 1 < n else 0.0

    fig, (ax, axt) = plt.subplots(2, 1, figsize=(16, 9.5), height_ratios=[3, 1.25],
                                  sharex=True, facecolor="#0b0b0b")
    for a in (ax, axt):
        a.set_facecolor("#0b0b0b"); a.tick_params(colors="#aaa")
        for sp in a.spines.values():
            sp.set_color("#333")
        a.grid(True, color="#141414", lw=0.5)

    for i in range(n):
        col = C_UP if C[i] >= O[i] else C_DN
        ax.plot([i, i], [L[i], H[i]], color=col, lw=1.0, zorder=2)
        ax.add_patch(Rectangle((i - .34, min(O[i], C[i])), .68, abs(C[i] - O[i]) or .06,
                               facecolor=col, edgecolor=col, zorder=3))

    def tick_word(v, side):
        a = abs(v)
        if a >= 1000: return "EXTREME (>=1000)"
        if a >= 800: return "extreme (>=800)"
        return "NOT extreme"

    # mark day low
    ax.scatter([lo_i], [L[lo_i]], marker="^", s=260, color="#33dd88", edgecolor="#000", zorder=7)
    lo_conf = tick_word(tick_at_lo, "lo")
    lo_txt = (f"DAY LOW\nTICK here = {tick_at_lo:.0f}  ->  {lo_conf}\n"
              f"price then bounced +{bounce:.0f} pts")
    ax.annotate(lo_txt, (lo_i, L[lo_i]), textcoords="offset points", xytext=(20, 30),
                color="#eaffea", fontsize=11, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.5", fc="#0e2a17", ec="#33dd88", lw=1.5),
                arrowprops=dict(arrowstyle="->", color="#33dd88", lw=1.5))
    # mark day high
    ax.scatter([hi_i], [H[hi_i]], marker="v", s=260, color="#ff5566", edgecolor="#000", zorder=7)
    hi_conf = tick_word(tick_at_hi, "hi")
    hi_txt = (f"DAY HIGH\nTICK here = {tick_at_hi:.0f}  ->  {hi_conf}\n"
              f"price then dropped -{drop:.0f} pts")
    ax.annotate(hi_txt, (hi_i, H[hi_i]), textcoords="offset points", xytext=(-40, -70),
                color="#ffecec", fontsize=11, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.5", fc="#2a0e12", ec="#ff5566", lw=1.5),
                arrowprops=dict(arrowstyle="->", color="#ff5566", lw=1.5))

    # TICK panel
    tkh = g["tick_high"].values; tkl = g["tick_low"].values
    for i in range(n):
        if np.isnan(tkh[i]):
            continue
        c = "#888"
        axt.plot([i, i], [tkl[i], tkh[i]], color=c, lw=1.0, zorder=2)
    axt.scatter([lo_i], [tick_at_lo], s=90, color="#33dd88", zorder=6, edgecolor="#000")
    axt.scatter([hi_i], [tick_at_hi], s=90, color="#ff5566", zorder=6, edgecolor="#000")
    for lv in (1000, 800, -800, -1000):
        axt.axhline(lv, color="#e2453c", ls="--" if abs(lv) == 800 else "-", lw=1.0, alpha=.7)
        axt.annotate(f"{lv:+d}", (n - 1, lv), color="#e2453c", fontsize=8, va="center")
    axt.axhline(0, color="#555", lw=0.7)
    axt.set_ylabel("NYSE TICK", color="#aaa", fontsize=11)
    axt.annotate("TICK spike past +/-800 AT a turn = the turn is real",
                 (0.5, 0.02), xycoords="axes fraction", color="#ffd400", fontsize=10,
                 ha="center", fontweight="bold")

    ax.set_title(f"Does NYSE TICK confirm the turn?   ES 5-min — {pd.Timestamp(day).date()}",
                 color="#fff", loc="left", fontsize=14, fontweight="bold")
    step = max(1, n // 14)
    axt.set_xticks(range(0, n, step))
    axt.set_xticklabels([g["DateTime"][i].strftime("%H:%M") for i in range(0, n, step)],
                        color="#aaa", fontsize=9)
    ax.set_xlim(-1, n + 3)
    fig.tight_layout()
    out = FIG_DIR / f"teaching_{pd.Timestamp(day).strftime('%Y%m%d')}.png"
    fig.savefig(out, dpi=120, facecolor=fig.get_facecolor()); plt.close(fig)
    print(f"wrote {out.relative_to(ROOT)}  | dayLow TICK {tick_at_lo:.0f} bounce +{bounce:.0f} | "
          f"dayHigh TICK {tick_at_hi:.0f} drop -{drop:.0f}")
    return out


def main():
    days = sys.argv[1:] or ["2025-04-09"]
    m = load()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for d in days:
        draw(m, d)


if __name__ == "__main__":
    main()
