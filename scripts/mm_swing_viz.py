#!/usr/bin/env python
"""mm_swing_viz.py — visual proof the NT swings are correct. Renders ETH 15M candles with
NT8 Swing(Strength) highs/lows marked, so it can be compared directly to the NinjaTrader
Swing indicator on the same window/strength.

Usage: python scripts/mm_swing_viz.py [start=2026-07-14] [end=2026-07-18] [strength=3]
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
BARS = ROOT / "data" / "bars" / "_db_es_1m_continuous_24h.parquet"
FIG = ROOT / "eminiaddict" / "figures"
sys.path.insert(0, str(ROOT / "scripts"))
from nt_swing import nt_swing  # noqa: E402


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else "2026-07-14"
    end = sys.argv[2] if len(sys.argv) > 2 else "2026-07-18"
    strength = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    m1 = pd.read_parquet(BARS)[["DateTime", "Open", "High", "Low", "Close"]]
    m1 = m1[(m1.DateTime >= start) & (m1.DateTime <= end + " 23:59")]
    g = m1.set_index("DateTime")
    b = pd.DataFrame({"O": g.Open.resample("15min").first(), "H": g.High.resample("15min").max(),
                      "L": g.Low.resample("15min").min(), "C": g.Close.resample("15min").last()}
                     ).dropna().reset_index().rename(columns={"DateTime": "dt"})
    H = b.H.to_numpy(); L = b.L.to_numpy(); O = b.O.to_numpy(); C = b.C.to_numpy()
    piv = nt_swing(H, L, strength)
    n = len(b)

    fig, ax = plt.subplots(figsize=(17, 8.5), facecolor="#0b0b0b")
    ax.set_facecolor("#0b0b0b"); ax.tick_params(colors="#aaa")
    for sp in ax.spines.values():
        sp.set_color("#333")
    ax.grid(True, color="#141414", lw=0.5)
    for i in range(n):
        col = "#26a65b" if C[i] >= O[i] else "#e2453c"
        ax.plot([i, i], [L[i], H[i]], color=col, lw=1.0, zorder=2)
        ax.add_patch(Rectangle((i - .3, min(O[i], C[i])), .6, abs(C[i] - O[i]) or .1,
                               facecolor=col, edgecolor=col, zorder=3))
    for pi, kind in piv:
        if kind == 'H':
            ax.scatter([pi], [H[pi] + (H.max()-L.min())*0.004], marker="v", s=70,
                       color="#00d0ff", zorder=6)   # NT SwingHigh = DarkCyan dot
        else:
            ax.scatter([pi], [L[pi] - (H.max()-L.min())*0.004], marker="^", s=70,
                       color="#e0b020", zorder=6)   # NT SwingLow = Goldenrod dot
    # session dividers (17:00 CT ETH open)
    for i in range(1, n):
        if b.dt[i].hour == 17 and b.dt[i].minute == 0:
            ax.axvline(i, color="#2a2f3a", lw=0.8, ls="--", zorder=1)
    ax.set_title(f"ES ETH(24H) 15M — NT Swing(Strength={strength})   {start}..{end}   "
                 f"cyan▼=SwingHigh  gold▲=SwingLow  ({len(piv)} swings)  — compare to your NT chart",
                 color="#eee", loc="left", fontsize=12)
    step = max(1, n // 16)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([b.dt[i].strftime("%m-%d %H:%M") for i in range(0, n, step)],
                       color="#aaa", fontsize=8, rotation=45)
    ax.set_xlim(-1, n + 1)
    FIG.mkdir(parents=True, exist_ok=True)
    out = FIG / f"nt_swings_ETH15M_s{strength}_{start}_{end}.png"
    fig.tight_layout(); fig.savefig(out, dpi=120, facecolor=fig.get_facecolor()); plt.close(fig)
    print(f"wrote {out.relative_to(ROOT)}  ({len(piv)} swings, strength {strength})")
    return out


if __name__ == "__main__":
    main()
