"""flip_spring_render.py — preview the Wyckoff spring-type marking (SP3/SP2/TSO)
that TempoSpeedometer.cs now draws, rendered in python on the engine bars so it can
be eyeballed before an NT8 F5. Classifies each climax-flip by reversal/trap volume
ratio: SP3<=0.94 (green, best) / SP2 (amber) / TSO>=1.03 (red, weak).

    python tempo/scripts/flip_spring_render.py [YYYY-MM-DD]   # default: busiest recent day
"""
from __future__ import annotations
import sys
import datetime as dt
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
TICK = 0.25
SP3_MAX, TSO_MIN, MIN_BODY = 0.94, 1.03, 4 * TICK


def bar_dir(o, c, h, l):
    rg = h - l
    if rg < TICK / 2:
        return 0
    ibs = (c - l) / rg
    return 1 if ibs >= 0.55 else (-1 if ibs <= 0.45 else 0)


def flips(g):
    o, h, l, c = (g[x].to_numpy() for x in ("open", "high", "low", "close"))
    cx, vol = g["climax"].to_numpy(), g["vol"].to_numpy(dtype=float)
    out = []
    for i in range(1, len(g)):
        if not (cx[i] and cx[i - 1]):
            continue
        if abs(c[i - 1] - o[i - 1]) < TICK / 2:
            continue
        if abs(c[i] - o[i]) < MIN_BODY - TICK / 2:
            continue
        d1 = 1 if c[i - 1] >= o[i - 1] else -1
        d2 = bar_dir(o[i], c[i], h[i], l[i])
        if d2 == 0 or d1 == d2:
            continue
        ratio = vol[i] / vol[i - 1] if vol[i - 1] > 0 else np.nan
        sp = 0 if ratio <= SP3_MAX else (2 if ratio >= TSO_MIN else 1)
        out.append({"i": i, "short": d1 == 1, "ratio": ratio, "sp": sp})
    return out


def main():
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].copy()
    if len(sys.argv) > 1:
        day = sys.argv[1]
    else:                                    # busiest flip day in the last 120 sessions
        days = sorted(df["date"].unique())[-120:]
        best, bn = days[-1], -1
        for d in days:
            n = len(flips(df[df.date == d].reset_index(drop=True)))
            if n > bn:
                best, bn = d, n
        day = best
    g = df[df.date == day].reset_index(drop=True)
    fl = flips(g)
    print(f"{day}: {len(fl)} flips  "
          f"[SP3 {sum(f['sp']==0 for f in fl)} · SP2 {sum(f['sp']==1 for f in fl)} · "
          f"TSO {sum(f['sp']==2 for f in fl)}]")

    o, h, l, c = (g[x].to_numpy() for x in ("open", "high", "low", "close"))
    cxs = g["climax"].to_numpy()
    fig, ax = plt.subplots(figsize=(16, 8), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    for i in range(len(g)):
        up = c[i] >= o[i]
        col = "#26a69a" if up else "#ef5350"
        ax.plot([i, i], [l[i], h[i]], color=col, lw=0.8, alpha=0.9, zorder=2)
        ax.add_patch(Rectangle((i - 0.3, min(o[i], c[i])), 0.6, abs(c[i] - o[i]) or TICK,
                     facecolor=col, edgecolor=("#ffd700" if cxs[i] else col),
                     lw=(1.4 if cxs[i] else 0.3), zorder=3))
    spc = {0: "#4dd0a6", 1: "#ffd700", 2: "#ef5350"}   # tier color: 0 low(best) / 1 mid / 2 high(weak)
    tier = {0: "3", 1: "2", 2: "1"}
    for f in fl:
        i = f["i"]
        h2, l2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        lab = ("UT" if f["short"] else "SP") + tier[f["sp"]]   # short=upthrust, long=spring
        ax.add_patch(Rectangle((i - 1.4, l2), 2.8, h2 - l2, fill=False,
                     edgecolor="#ffd700", lw=1.2, alpha=0.8, zorder=4))
        # UT (short) label above the box, SP (long) label below
        anch = (i, h2) if f["short"] else (i, l2)
        ax.annotate(f"{lab} {f['ratio']:.2f}\n{'SHORT' if f['short'] else 'LONG'}",
                    anch, xytext=(0, 14 if f["short"] else -14), textcoords="offset points",
                    ha="center", va="bottom" if f["short"] else "top",
                    color=spc[f["sp"]], fontsize=8.5,
                    fontweight="bold", family="monospace", zorder=6)

    # #2 whole-chart beyond-prior-day spring/upthrust detector (independent of the flip)
    days_all = sorted(df["date"].unique())
    di = days_all.index(day)
    if di > 0:
        prev = df[df.date == days_all[di - 1]]
        pdh, pdl = prev["high"].max(), prev["low"].min()
        ax.axhline(pdh, color="#8b877d", lw=0.8, ls="--", alpha=0.6, zorder=1)
        ax.axhline(pdl, color="#8b877d", lw=0.8, ls="--", alpha=0.6, zorder=1)
        ax.annotate("PDH", (len(g) - 1, pdh), color="#8b877d", fontsize=8,
                    family="monospace", va="bottom", ha="right")
        ax.annotate("PDL", (len(g) - 1, pdl), color="#8b877d", fontsize=8,
                    family="monospace", va="top", ha="right")
        vol = g["vol"].to_numpy(dtype=float)
        rng = h - l
        nsp = nut = 0
        for i in range(1, len(g)):
            ut = h[i] > pdh and c[i] <= pdh and h[i - 1] <= pdh
            sp = l[i] < pdl and c[i] >= pdl and l[i - 1] >= pdl
            if not (ut or sp):
                continue
            # Wyckoff 3-factor classification: depth + volume + range
            avR = rng[max(0, i - 8):i].mean() if i > 0 else rng[i]
            avV = vol[max(0, i - 8):i].mean() if i > 0 else vol[i]
            pen = (h[i] - pdh) if ut else (pdl - l[i])
            pen_f = pen / avR if avR > 0 else 1
            vol_r = vol[i] / avV if avV > 0 else 1
            rng_r = rng[i] / avR if avR > 0 else 1
            inten = (pen_f + vol_r + rng_r) / 3
            tr = 0 if inten <= 0.85 else (2 if inten >= 1.50 else 1)
            lab = ("UT" if ut else "SP") + tier[tr]
            if ut:
                ax.annotate(lab, (i, h[i]), xytext=(0, 8), textcoords="offset points",
                            ha="center", va="bottom", color=spc[tr], fontsize=8,
                            fontweight="bold", family="monospace", zorder=7,
                            arrowprops=dict(arrowstyle="-|>", color=spc[tr], lw=1.2))
                nut += 1
            else:
                ax.annotate(lab, (i, l[i]), xytext=(0, -8), textcoords="offset points",
                            ha="center", va="top", color=spc[tr], fontsize=8,
                            fontweight="bold", family="monospace", zorder=7,
                            arrowprops=dict(arrowstyle="-|>", color=spc[tr], lw=1.2))
                nsp += 1
        print(f"  beyond-PD: {nsp} springs · {nut} upthrusts (PDH {pdh:.2f} / PDL {pdl:.2f})")
    ax.set_title(f"Wyckoff on the tempo chart  ·  {day}  ·  boxed = climax-flip (SP/UT by vol) "
                 f"·  triangles = beyond-PD poke  ·  tier 3 low-vol best / 1 high-vol weak",
                 color="#e8e6df", fontsize=11, family="monospace")
    ax.tick_params(colors="#8b877d")
    for s in ax.spines.values():
        s.set_color("#2c2c2a")
    ax.margins(x=0.01)
    ax.set_ylabel("ES price", color="#8b877d", family="monospace")
    fig.tight_layout()
    png = OUT / f"flip_spring_render_{day}.png"
    fig.savefig(png, dpi=110, facecolor="#0d0d0d")
    print("wrote", png)


if __name__ == "__main__":
    main()
