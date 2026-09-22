"""3-panel stacked divergence chart (5M RTH, 7/13-7/17):
  1) price candles
  2) CVD candles  (cumulative delta OHLC — wicks from intrabar MinDelta/MaxDelta)
  3) delta histogram (per-5M-bar delta)
Divergence = same-type pivots (L=R=2, confirmed → tradeable at a LATER signal bar),
compared at the SAME two timestamps; connectors on price+CVD, vertical lines through
ALL THREE panels so the alignment is auditable. Method A = swing-anchored.
"""
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

ROOT = r"c:\Users\Admin\myquant"; TICK = 0.25; L = R = 2
RTH0, RTH1 = "08:30", "15:00"
b = pd.read_csv(ROOT + r"\data\footprint\ES_bars.csv", parse_dates=["BarTime"])
b["t5"] = b.BarTime.dt.floor("5min"); b["day"] = b.BarTime.dt.strftime("%Y-%m-%d")

UP, DN = "#2e9e4f", "#d64545"; BEAR, BULL = "#c22", "#0a8a3a"
for day, bd in b.groupby("day"):
    recs = []; run = 0.0
    for t5, g in bd.groupby("t5"):
        if not (RTH0 <= t5.strftime("%H:%M") < RTH1): continue
        g = g.sort_values("BarIdx")
        o, c = g.Open.iloc[0], g.Close.iloc[-1]; hi, lo = g.High.max(), g.Low.min()
        # CVD candle from intrabar excursions
        cvo = run; cur = run; ch = run; cl = run
        for _, s in g.iterrows():
            ch = max(ch, cur + s.MaxDelta); cl = min(cl, cur + s.MinDelta); cur += s.Delta
        recs.append(dict(t5=t5, O=o, C=c, H=hi, Lo=lo, delta=int(g.Delta.sum()),
                         cvo=cvo, cvc=cur, cvh=ch, cvl=cl)); run = cur
    d = pd.DataFrame(recs).reset_index(drop=True); d["x"] = np.arange(len(d)); n = len(d)
    hi, lo, cvc = d.H.values, d.Lo.values, d.cvc.values

    # pivots + regular divergences (same-type)
    highs = [i for i in range(L, n-R) if hi[i] == max(hi[i-L:i+R+1]) and hi[i] > max(hi[i-L:i]) and hi[i] >= max(hi[i+1:i+R+1])]
    lows  = [i for i in range(L, n-R) if lo[i] == min(lo[i-L:i+R+1]) and lo[i] < min(lo[i-L:i]) and lo[i] <= min(lo[i+1:i+R+1])]
    divs = []
    for a2, bb in zip(highs, highs[1:]):
        if hi[bb] > hi[a2] and cvc[bb] < cvc[a2]: divs.append(("bearish", a2, bb))
    for a2, bb in zip(lows, lows[1:]):
        if lo[bb] < lo[a2] and cvc[bb] > cvc[a2]: divs.append(("bullish", a2, bb))

    fig, (axP, axV, axD) = plt.subplots(3, 1, figsize=(26, 15), sharex=True,
                                        gridspec_kw={"height_ratios": [2.3, 1.3, 0.8], "hspace": 0.05})
    # price candles
    for _, r in d.iterrows():
        col = UP if r.C >= r.O else DN
        axP.plot([r.x, r.x], [r.Lo, r.H], color=col, lw=1.1, zorder=2)
        a, z = sorted([r.O, r.C]); axP.add_patch(Rectangle((r.x-.34, a), .68, max(z-a, .05), facecolor=col, edgecolor=col, lw=.5, zorder=3))
    # CVD candles
    for _, r in d.iterrows():
        col = UP if r.cvc >= r.cvo else DN
        axV.plot([r.x, r.x], [r.cvl, r.cvh], color=col, lw=1.1, zorder=2)
        a, z = sorted([r.cvo, r.cvc]); axV.add_patch(Rectangle((r.x-.34, a), .68, max(z-a, 1), facecolor=col, edgecolor=col, lw=.5, zorder=3))
    axV.axhline(0, color="#888", lw=.7)
    # delta histogram
    axD.bar(d.x, d.delta, width=.7, color=np.where(d.delta >= 0, UP, DN))
    axD.axhline(0, color="#888", lw=.7)
    # pivots
    axP.scatter([d.x[i] for i in highs], [hi[i]+.6 for i in highs], marker="v", s=40, color="#a44", zorder=5)
    axP.scatter([d.x[i] for i in lows], [lo[i]-.6 for i in lows], marker="^", s=40, color="#4a4", zorder=5)
    # divergences
    for kind, a2, bb in divs:
        col = BEAR if kind == "bearish" else BULL
        pa, pb = (hi[a2], hi[bb]) if kind == "bearish" else (lo[a2], lo[bb]); off = 1.0 if kind == "bearish" else -1.0
        axP.plot([a2, bb], [pa+off, pb+off], color=col, lw=2.6, zorder=6)
        axP.scatter([a2, bb], [pa+off, pb+off], s=52, color=col, zorder=7, edgecolor="white", lw=.6)
        axV.plot([a2, bb], [cvc[a2], cvc[bb]], color=col, lw=2.6, zorder=6)
        axV.scatter([a2, bb], [cvc[a2], cvc[bb]], s=52, color=col, zorder=7, edgecolor="white", lw=.6)
        for x in (a2, bb):
            for ax in (axP, axV, axD): ax.axvline(x, color=col, lw=.8, ls=":", alpha=.5, zorder=1)
        axP.annotate(f"{kind} div\n{d.t5[a2]:%H:%M}→{d.t5[bb]:%H:%M}", xy=((a2+bb)/2, (max(pa,pb)+2.4) if kind=="bearish" else (min(pa,pb)-2.4)),
                     ha="center", fontsize=9, fontweight="bold", color=col)
    axP.set_title(f"ES {day} — 5M RTH · price / CVD candles / delta · same-type-pivot divergence ({len(divs)}) · verticals = identical timestamps", fontsize=13)
    axP.set_ylabel("price"); axV.set_ylabel("CVD (candles)"); axD.set_ylabel("Δ / bar")
    for ax in (axP, axV, axD): ax.grid(alpha=.15)
    tk = d.x[:: max(n//18, 1)]; axD.set_xticks(tk); axD.set_xticklabels(d.t5.dt.strftime("%H:%M")[:: max(n//18, 1)], fontsize=9)
    out = ROOT + rf"\scratchpad\divstack_{day}.png"; fig.savefig(out, dpi=100, bbox_inches="tight"); plt.close(fig)
    print(f"{day}: {len(highs)}H/{len(lows)}L pivots · {len(divs)} divergences -> {out}")
