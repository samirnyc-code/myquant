"""drawn_zone_demo.py — mock of the trader-drawn TR-ZONE feature (matches how the user draws
S/R: a BAND from the wick extreme to the body cluster). You draw the zone(s); the indicator
finds springs / upthrusts as REJECTIONS at the zone:

  resistance zone (at a high): a bar tests UP into the zone and CLOSES back below it  -> UPTHRUST
  support zone   (at a low):   a bar tests DOWN into the zone and CLOSES back above it -> SPRING

Zone TYPE is auto-detected from where price sits (mostly below = resistance, mostly above =
support). Wyckoff tier (#3/#2/#1) from depth-beyond-extreme + volume + range.

    python tempo/scripts/drawn_zone_demo.py DAY  TOP1 BOT1  [TOP2 BOT2 ...]
    e.g. python tempo/scripts/drawn_zone_demo.py 2026-09-11 7681 7678  7657 7654
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

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"


def tier(i, h, l, v, rng, outer, up):
    avR = rng[max(0, i - 8):i].mean() if i > 0 else rng[i]
    avV = v[max(0, i - 8):i].mean() if i > 0 else v[i]
    pen = max(0.0, (h[i] - outer) if up else (outer - l[i]))   # how far beyond the extreme edge
    inten = ((pen / avR if avR > 0 else 0) + (v[i] / avV if avV > 0 else 1)
             + (rng[i] / avR if avR > 0 else 1)) / 3
    return 0 if inten <= 0.85 else (2 if inten >= 1.50 else 1)


def main():
    day = sys.argv[1]
    nums = [float(x) for x in sys.argv[2:]]
    zones = [(max(nums[k], nums[k + 1]), min(nums[k], nums[k + 1])) for k in range(0, len(nums), 2)]
    df = pd.read_parquet(ENG); df = df[df.state >= 0]
    g = df[df.date == day].reset_index(drop=True)
    o, h, l, c = (g[x].to_numpy() for x in ("open", "high", "low", "close"))
    v = g["vol"].to_numpy(dtype=float); rng = h - l; n = len(g)

    fig, ax = plt.subplots(figsize=(16, 8), facecolor="#0d0d0d"); ax.set_facecolor("#0d0d0d")
    for i in range(n):
        up = c[i] >= o[i]; col = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [l[i], h[i]], color=col, lw=0.8, alpha=0.9, zorder=2)
        ax.add_patch(Rectangle((i - 0.3, min(o[i], c[i])), 0.6, abs(c[i] - o[i]) or 0.25,
                     facecolor=col, edgecolor=col, lw=0.3, zorder=3))
    spc = {0: "#4dd0a6", 1: "#ffd700", 2: "#ef5350"}; tl = {0: "3", 1: "2", 2: "1"}
    for (top, bot) in zones:
        below = int(np.sum(c < bot)); above = int(np.sum(c > top))
        is_res = below >= above                                 # price mostly below => resistance
        ax.add_patch(Rectangle((0, bot), n - 1, top - bot, facecolor="#fff2b0", alpha=0.28,
                     edgecolor="none", zorder=1))
        ax.annotate("resistance zone" if is_res else "support zone", (2, top if is_res else bot),
                    color="#b8a24e", fontsize=9, family="monospace",
                    va="bottom" if is_res else "top", ha="left")
        ns = nu = 0
        for i in range(1, n):
            if is_res:
                hit = h[i] >= bot and c[i] < bot and h[i - 1] < bot   # tested into zone, closed below
                if hit:
                    tr = tier(i, h, l, v, rng, top, True); nm = "UT" + tl[tr]
                    ax.annotate(nm, (i, h[i]), xytext=(0, 9), textcoords="offset points",
                                ha="center", va="bottom", color=spc[tr], fontsize=8.5,
                                fontweight="bold", family="monospace", zorder=7,
                                arrowprops=dict(arrowstyle="-|>", color=spc[tr], lw=1.2)); nu += 1
            else:
                hit = l[i] <= top and c[i] > top and l[i - 1] > top   # tested into zone, closed above
                if hit:
                    tr = tier(i, h, l, v, rng, bot, False); nm = "SP" + tl[tr]
                    ax.annotate(nm, (i, l[i]), xytext=(0, -9), textcoords="offset points",
                                ha="center", va="top", color=spc[tr], fontsize=8.5,
                                fontweight="bold", family="monospace", zorder=7,
                                arrowprops=dict(arrowstyle="-|>", color=spc[tr], lw=1.2)); ns += 1
        print(f"  zone {bot:.2f}-{top:.2f} ({'RES' if is_res else 'SUP'}): "
              f"{nu} upthrusts, {ns} springs")

    ax.set_title(f"Drawn TR-ZONE demo  ·  {day}  ·  you draw the band (wick->body); indicator "
                 f"finds REJECTIONS: SP (spring at support) / UT (upthrust at resistance)",
                 color="#e8e6df", fontsize=10, family="monospace")
    ax.tick_params(colors="#8b877d")
    for s in ax.spines.values():
        s.set_color("#2c2c2a")
    ax.margins(x=0.01); ax.set_ylabel("ES price", color="#8b877d", family="monospace")
    fig.tight_layout()
    png = OUT / f"drawn_zone_demo_{day}.png"
    fig.savefig(png, dpi=110, facecolor="#0d0d0d"); print("wrote", png)


if __name__ == "__main__":
    main()
