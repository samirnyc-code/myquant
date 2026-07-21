"""Causal backtest of Cadaver's trendline claim: 'trade the TL poke -> >50%, steeper better.'
Bar-only pivots (fast). Shallowest-hull bull/bear TL built ONLY from confirmed past pivots.
Entry = price pokes the line (within POKE ticks) then closes back with-trend. Stop 1t beyond
the bar's extreme; target = R * risk. One trade at a time. Bucket win-rate by TL slope."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parent.parent.parent; sys.path.insert(0, str(ROOT))
B = pd.read_parquet(ROOT/"data"/"bars"/"_continuous.parquet"); B["Date"] = B["DateTime"].dt.date.astype(str)
TICK = 0.25; POKE = 2*TICK; R = 2.0

def bar_pivots(H, L, C, O, n):
    # bar-only leg engine; OB resolved by close position (upper half -> up-first)
    evs = {}
    for i in range(1, n):
        bt = H[i] > H[i-1]; bb = L[i] < L[i-1]; eq = (H[i] == H[i-1]) and (L[i] == L[i-1])
        if (bt and bb) or eq:
            up_first = (C[i]-L[i]) >= (H[i]-L[i])/2
            evs[i] = ["U", "D"] if up_first else ["D", "U"]
        elif bt: evs[i] = ["U"]
        elif bb: evs[i] = ["D"]
        else: evs[i] = []
    d = [None]; ext = [0]; piv = []
    def proc(ev, i):
        if ev == "U":
            if d[0] == -1: piv.append((ext[0], "L")); d[0] = 1; ext[0] = i
            else: d[0] = 1; ext[0] = i if H[i] >= H[ext[0]] else ext[0]
        else:
            if d[0] == 1: piv.append((ext[0], "H")); d[0] = -1; ext[0] = i
            else: d[0] = -1; ext[0] = i if L[i] <= L[ext[0]] else ext[0]
    for i in range(1, n):
        for ev in evs[i]: proc(ev, i)
    piv.append((ext[0], "H" if d[0] == 1 else "L"))
    return piv

def shallow_bull(lows):
    # anchored lower-hull first edge from the lowest low; returns (x0,y0,slope) or None
    if len(lows) < 2: return None
    o = min(range(len(lows)), key=lambda k: lows[k][1])
    pts = lows[o:]
    if len(pts) < 2: return None
    b0 = pts[0]
    # min-slope point keeps all lows above
    best = None
    for p in pts[1:]:
        if p[0] == b0[0]: continue
        m = (p[1]-b0[1])/(p[0]-b0[0])
        if best is None or m < best: best = m
    if best is None: return None
    return (b0[0], b0[1], best)

def shallow_bear(highs):
    if len(highs) < 2: return None
    o = min(range(len(highs)), key=lambda k: -highs[k][1])
    pts = highs[o:]
    if len(pts) < 2: return None
    b0 = pts[0]; best = None
    for p in pts[1:]:
        if p[0] == b0[0]: continue
        m = (p[1]-b0[1])/(p[0]-b0[0])
        if best is None or m > best: best = m
    if best is None: return None
    return (b0[0], b0[1], best)

trades = []
for day, g in B.groupby("Date"):
    g = g.sort_values("DateTime").reset_index(drop=True)
    if not (20 < len(g) < 200): continue
    O, H, L, C = (g[c].values.astype(float) for c in ["Open", "High", "Low", "Close"]); n = len(g)
    piv = bar_pivots(H, L, C, O, n)
    # confirmed pivots become "known" at the bar they occur's NEXT reversal; approximate: known at pivot bar+? use pivot bar (minor)
    pl = [(b, L[b]) for (b, t) in piv if t == "L"]
    ph = [(b, H[b]) for (b, t) in piv if t == "H"]
    open_until = -1  # bar index until which a trade is open
    for side in ("bull", "bear"):
        seq = pl if side == "bull" else ph
        for i in range(3, n):
            if i <= open_until: continue
            past = [p for p in seq if p[0] < i]      # only confirmed-past pivots
            tl = shallow_bull(past) if side == "bull" else shallow_bear(past)
            if tl is None: continue
            x0, y0, m = tl
            # require rising lows (bull) / falling highs (bear) = a trend context
            if side == "bull" and m <= 0: continue
            if side == "bear" and m >= 0: continue
            line = y0 + m*(i-x0)
            if side == "bull":
                poke = L[i] <= line + POKE and L[i] >= line - 4*TICK  # near the line, not far below
                hold = C[i] > line
                if poke and hold:
                    entry = C[i]; stop = min(line, L[i]) - TICK; risk = entry-stop
                    if risk <= 0: continue
                    tgt = entry + R*risk
                    res = None
                    for j in range(i+1, n):
                        if L[j] <= stop: res = 0; open_until = j; break
                        if H[j] >= tgt: res = 1; open_until = j; break
                    if res is None: res = 1 if C[-1] > entry else 0; open_until = n
                    trades.append((day, side, m, risk, res))
            else:
                poke = H[i] >= line - POKE and H[i] <= line + 4*TICK
                hold = C[i] < line
                if poke and hold:
                    entry = C[i]; stop = max(line, H[i]) + TICK; risk = stop-entry
                    if risk <= 0: continue
                    tgt = entry - R*risk
                    res = None
                    for j in range(i+1, n):
                        if H[j] >= stop: res = 0; open_until = j; break
                        if L[j] <= tgt: res = 1; open_until = j; break
                    if res is None: res = 1 if C[-1] < entry else 0; open_until = n
                    trades.append((day, side, m, risk, res))

d = pd.DataFrame(trades, columns=["day", "side", "slope", "risk", "win"])
print(f"N trades: {len(d)}   overall win-rate: {d['win'].mean():.1%}   (R={R}, so breakeven ~ {1/(1+R):.0%})")
print(f"expectancy per trade (R units): {(d['win']*R - (1-d['win'])).mean():+.3f}R")
print()
print("=== by absolute slope quartile (Cadaver: steeper = better) ===")
d["absslope"] = d["slope"].abs()
d["sq"] = pd.qcut(d["absslope"], 4, labels=["Q1flat", "Q2", "Q3", "Q4steep"])
g2 = d.groupby("sq", observed=True).agg(slope_med=("absslope", "median"), win=("win", "mean"), n=("win", "size"))
g2["expR"] = g2["win"]*R - (1-g2["win"])
print(g2.round(3))
print()
print("by side:"); print(d.groupby("side").agg(win=("win","mean"), n=("win","size")).round(3))
