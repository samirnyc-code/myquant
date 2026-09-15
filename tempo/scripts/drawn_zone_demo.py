"""drawn_zone_demo.py — mock of the TRADER-DRAWN TR ZONE feature now in TempoSpeedometer.cs:
you draw a Rectangle; the indicator reads top=resistance / bottom=support and marks springs
(poke below support + close back above) and upthrusts (poke above resistance + close back
below), Wyckoff-tiered by depth+volume+range. Causal: each mark uses only that bar vs the level.

    python tempo/scripts/drawn_zone_demo.py DAY TOP BOT [START_BAR]
    e.g. python tempo/scripts/drawn_zone_demo.py 2026-09-14 7647 7624 150
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


def tier_at(i, h, l, v, rng, up, lvl):
    avR = rng[max(0, i - 8):i].mean() if i > 0 else rng[i]
    avV = v[max(0, i - 8):i].mean() if i > 0 else v[i]
    pen = (h[i] - lvl) if up else (lvl - l[i])
    inten = ((pen / avR if avR > 0 else 1) + (v[i] / avV if avV > 0 else 1)
             + (rng[i] / avR if avR > 0 else 1)) / 3
    return 0 if inten <= 0.85 else (2 if inten >= 1.50 else 1)


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-09-14"
    top = float(sys.argv[2]) if len(sys.argv) > 2 else 7647.0
    bot = float(sys.argv[3]) if len(sys.argv) > 3 else 7624.0
    start = int(sys.argv[4]) if len(sys.argv) > 4 else 150
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
    # the "drawn" rectangle (what the trader draws; indicator reads top/bot)
    ax.add_patch(Rectangle((start, bot), (n - 1) - start, top - bot, facecolor="#6fb0ff",
                 alpha=0.08, edgecolor="#6fb0ff", lw=1.3, ls="--", zorder=1))
    ax.annotate("drawn TR zone (Rectangle)", (start, top), color="#6fb0ff", fontsize=9,
                family="monospace", va="bottom", ha="left")

    spc = {0: "#4dd0a6", 1: "#ffd700", 2: "#ef5350"}; tl = {0: "3", 1: "2", 2: "1"}
    nsp = nut = 0
    for i in range(max(start, 1), n):
        up = h[i] > top and c[i] <= top and h[i - 1] <= top
        sp = l[i] < bot and c[i] >= bot and l[i - 1] >= bot
        if not (up or sp):
            continue
        tr = tier_at(i, h, l, v, rng, up, top if up else bot)
        nm = ("UT" if up else "SP") + tl[tr]
        yv = h[i] if up else l[i]
        ax.annotate(nm, (i, yv), xytext=(0, 9 if up else -9), textcoords="offset points",
                    ha="center", va="bottom" if up else "top", color=spc[tr], fontsize=8.5,
                    fontweight="bold", family="monospace", zorder=7,
                    arrowprops=dict(arrowstyle="-|>", color=spc[tr], lw=1.2))
        nut += up; nsp += sp
    print(f"{day}: drawn zone {bot:.2f}-{top:.2f} from bar {start} -> {nsp} springs, {nut} upthrusts")
    ax.set_title(f"Drawn-TR-zone demo  ·  {day}  ·  you draw the blue rectangle; indicator marks "
                 f"SP (spring, poke below support) / UT (upthrust, poke above resistance)",
                 color="#e8e6df", fontsize=10.5, family="monospace")
    ax.tick_params(colors="#8b877d")
    for s in ax.spines.values():
        s.set_color("#2c2c2a")
    ax.margins(x=0.01); ax.set_ylabel("ES price", color="#8b877d", family="monospace")
    fig.tight_layout()
    png = OUT / f"drawn_zone_demo_{day}.png"
    fig.savefig(png, dpi=110, facecolor="#0d0d0d"); print("wrote", png)


if __name__ == "__main__":
    main()
