"""FALSIFICATION test for CVD divergence (5M RTH, 7/13-7/17). The honest question:
does a MECHANICAL divergence (no human point-picking), entered at CONFIRMATION (no
lookahead), beat a matched control? On 5 days this is UNDERPOWERED (machinery + a
directional hint only) — the real verdict comes from the 5-yr export.

Rules:
  - pivots L=R=2 (confirmed R bars after they print)
  - regular divergence between consecutive same-type pivots
  - ENTRY at pivot_B + R (the first bar the divergence is actually KNOWN)
  - bearish -> short, bullish -> long; forward return over K bars, signed by side
  - CONTROL: every other bar, entered same way, same forward window (base rate)
"""
import numpy as np, pandas as pd
ROOT = r"c:\Users\Admin\myquant"; TICK = 0.25; L = R = 2; K = 6; RTH0, RTH1 = "08:30", "15:00"
b = pd.read_csv(ROOT + r"\data\footprint\ES_bars.csv", parse_dates=["BarTime"])
b["t5"] = b.BarTime.dt.floor("5min"); b["day"] = b.BarTime.dt.strftime("%Y-%m-%d")

# build 5M bars + session CVD
rows = []
for day, bd in b.groupby("day"):
    run = 0.0
    for t5, g in bd.groupby("t5"):
        if not (RTH0 <= t5.strftime("%H:%M") < RTH1): continue
        g = g.sort_values("BarIdx")
        run += g.Delta.sum()
        rows.append(dict(day=day, t5=t5, O=g.Open.iloc[0], C=g.Close.iloc[-1],
                         H=g.High.max(), Lo=g.Low.min(), cvd=run))
D = pd.DataFrame(rows)

div_fr = []; ctrl_fr = []
for day, g in D.groupby("day"):
    g = g.reset_index(drop=True); n = len(g)
    hi, lo, cvd, cl = g.H.values, g.Lo.values, g.cvd.values, g.C.values
    highs = [i for i in range(L, n-R) if hi[i] == max(hi[i-L:i+R+1]) and hi[i] > max(hi[i-L:i]) and hi[i] >= max(hi[i+1:i+R+1])]
    lows  = [i for i in range(L, n-R) if lo[i] == min(lo[i-L:i+R+1]) and lo[i] < min(lo[i-L:i]) and lo[i] <= min(lo[i+1:i+R+1])]
    div_entries = {}   # entry_bar -> side (+1 long / -1 short)
    for a, bb in zip(highs, highs[1:]):
        if hi[bb] > hi[a] and cvd[bb] < cvd[a]:
            e = bb + R
            if e + K < n: div_entries[e] = -1   # bearish -> short
    for a, bb in zip(lows, lows[1:]):
        if lo[bb] < lo[a] and cvd[bb] > cvd[a]:
            e = bb + R
            if e + K < n: div_entries[e] = +1   # bullish -> long
    for e, side in div_entries.items():
        div_fr.append(side * (cl[e+K] - cl[e]))
    # control: every bar with a full forward window, both directions (base rate)
    for e in range(0, n-K):
        if e in div_entries: continue
        ctrl_fr.append(cl[e+K] - cl[e])          # long-side base rate
        ctrl_fr.append(-(cl[e+K] - cl[e]))       # short-side base rate

div_fr = np.array(div_fr); ctrl_fr = np.array(ctrl_fr)
print(f"K={K} bars forward ({K*5} min) · divergence entries n={len(div_fr)} · control n={len(ctrl_fr)}\n")
print(f"{'':12s}{'mean pts':>10s}{'median':>9s}{'win%':>7s}")
print(f"{'divergence':12s}{div_fr.mean():>10.2f}{np.median(div_fr):>9.2f}{(div_fr>0).mean()*100:>6.0f}%")
print(f"{'control':12s}{ctrl_fr.mean():>10.2f}{np.median(ctrl_fr):>9.2f}{(ctrl_fr>0).mean()*100:>6.0f}%")
edge = div_fr.mean() - ctrl_fr.mean()
print(f"\nedge over control: {edge:+.2f} pts/trade")
# crude significance: is the divergence mean outside control's noise?
se = ctrl_fr.std()/np.sqrt(max(len(div_fr),1))
print(f"(divergence mean is {edge/se:+.1f} standard errors from control — |z|>2 would be notable; "
      f"n={len(div_fr)} is TINY, treat as a hint only)")
