"""PROPER price/CVD divergence on 5M RTH bars (7/13-7/17). Big per-day charts.

Divergence = compare TWO pivots of the SAME type (high-to-prior-high, low-to-prior-low),
reading price AND cvd at THOSE SAME two bar timestamps:
  REGULAR BEARISH (at tops): price higher-high, CVD lower-high
  REGULAR BULLISH (at lows):  price lower-low,  CVD higher-low
Both pivots are joined on the price panel AND the CVD panel, with vertical lines at the
two identical x-positions so the alignment is auditable. Pivots use L=R=2 (confirmed 2
bars later — repaint lag noted).
"""
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = r"c:\Users\Admin\myquant"; TICK = 0.25; L = R = 2
D = pd.read_csv(ROOT + r"\scratchpad\turn_lab_table.csv", parse_dates=["t5"])
D = D.sort_values(["day", "t5"]).reset_index(drop=True)

def pivots(hi, lo, n):
    highs, lows = [], []
    for i in range(L, n - R):
        if hi[i] == max(hi[i-L:i+R+1]) and hi[i] > max(hi[i-L:i]) and hi[i] >= max(hi[i+1:i+R+1]):
            highs.append(i)
        if lo[i] == min(lo[i-L:i+R+1]) and lo[i] < min(lo[i-L:i]) and lo[i] <= min(lo[i+1:i+R+1]):
            lows.append(i)
    return highs, lows

UP, DN = "#2e9e4f", "#d64545"
BEAR, BULL = "#c22", "#0a8a3a"
for day, g in D.groupby("day"):
    g = g.reset_index(drop=True); g["x"] = np.arange(len(g))
    hi, lo, cvd = g.High.values, g.Low.values, g.cvd.values
    n = len(g)
    highs, lows = pivots(hi, lo, n)

    divs = []   # (kind, A, B)
    for piv, is_high in ((highs, True), (lows, False)):
        for a, b in zip(piv, piv[1:]):
            if is_high and hi[b] > hi[a] and cvd[b] < cvd[a]:      # HH price, LH cvd
                divs.append(("bearish", a, b))
            if (not is_high) and lo[b] < lo[a] and cvd[b] > cvd[a]:  # LL price, HL cvd
                divs.append(("bullish", a, b))

    fig, (axP, axC) = plt.subplots(2, 1, figsize=(26, 13), sharex=True,
                                   gridspec_kw={"height_ratios": [2.3, 1], "hspace": 0.04})
    for _, r in g.iterrows():
        c = UP if r.Close >= r.Open else DN
        axP.plot([r.x, r.x], [r.Low, r.High], color=c, lw=1.1, zorder=2)
        l, h = sorted([r.Open, r.Close])
        axP.add_patch(Rectangle((r.x-0.34, l), 0.68, max(h-l, .05), facecolor=c, edgecolor=c, lw=.5, zorder=3))
    axC.plot(g.x, g.cvd, color="#1f5fa8", lw=1.8, zorder=2)
    axC.axhline(0, color="#888", lw=.8)
    # mark all pivots (the candidate points being compared)
    axP.scatter([g.x[i] for i in highs], [hi[i]+0.6 for i in highs], marker="v", s=42, color="#a44", zorder=5)
    axP.scatter([g.x[i] for i in lows], [lo[i]-0.6 for i in lows], marker="^", s=42, color="#4a4", zorder=5)

    for kind, a, b in divs:
        col = BEAR if kind == "bearish" else BULL
        pa = hi[a] if kind == "bearish" else lo[a]
        pb = hi[b] if kind == "bearish" else lo[b]
        off = 1.0 if kind == "bearish" else -1.0
        # connect the two SAME-TYPE pivots on the price panel
        axP.plot([a, b], [pa+off, pb+off], color=col, lw=2.6, zorder=6)
        axP.scatter([a, b], [pa+off, pb+off], s=55, color=col, zorder=7, edgecolor="white", linewidth=.6)
        # connect the SAME two timestamps on the CVD panel
        axC.plot([a, b], [cvd[a], cvd[b]], color=col, lw=2.6, zorder=6)
        axC.scatter([a, b], [cvd[a], cvd[b]], s=55, color=col, zorder=7, edgecolor="white", linewidth=.6)
        # vertical lines at the EXACT SAME x on BOTH panels — auditable alignment
        for x in (a, b):
            axP.axvline(x, color=col, lw=0.8, ls=":", alpha=.55, zorder=1)
            axC.axvline(x, color=col, lw=0.8, ls=":", alpha=.55, zorder=1)
        midx = (a + b) / 2
        ytxt = max(pa, pb) + 2.4 if kind == "bearish" else min(pa, pb) - 2.4
        axP.annotate(f"{kind} div\n{g.t5[a]:%H:%M}→{g.t5[b]:%H:%M}", xy=(midx, ytxt),
                     ha="center", fontsize=9.5, fontweight="bold", color=col)

    axP.set_title(f"ES {day} — 5M RTH  ·  price/CVD divergence (same-type pivots, same timestamps)  "
                  f"·  ▼▲ = pivots · dotted verticals = the two compared points  ·  {len(divs)} divergences",
                  fontsize=13)
    axP.set_ylabel("price"); axC.set_ylabel("CVD (Σ Ask−Bid, session)")
    axP.grid(alpha=.16); axC.grid(alpha=.16)
    tk = g.x[:: max(n//18, 1)]
    axC.set_xticks(tk); axC.set_xticklabels(g.t5.dt.strftime("%H:%M")[:: max(n//18, 1)], fontsize=9)
    out = ROOT + rf"\scratchpad\divergence_5m_{day}.png"
    fig.savefig(out, dpi=100, bbox_inches="tight"); plt.close(fig)
    print(f"{day}: {len(highs)} high pivots, {len(lows)} low pivots, {len(divs)} regular divergences -> {out}")
