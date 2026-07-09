"""Brooks structure engine (S63, 2026-07-09) — built bar-by-bar WITH the user.

Layers, all bar-close / 1-indexed (bar 1 = first bar's close, e.g. 08:35 CT):
  1. Two-bar labels    : each bar vs prior -> H (broke prior high only), L (broke
                         prior low only), OB (both), IB (neither), equal=both.
  2. Swing pivots      : legs from the two-bar rule; OB bars are decomposed by
                         FIRST-BREAK TICK ORDER (down-first -> low then high, etc.).
                         Each turning point tagged HH/LH (vs prior swing high) or
                         HL/LL (vs prior swing low); bar 1 seeds the first labels.
  3. Triangles         :
       - CONTRACTING = LH (lower highs) + HL (higher lows) converging; two straight
         boundary lines (first->last high, first->last low). Breakout ends it.
       - EXPANDING   = 5-point broadening (P1..P5), highs rising + lows falling.
         Scan all valid 5-windows; reject a window whose final leg is a
         disproportionate breakout (>2.2x prior legs); keep latest-starting on overlap.
  4. TTR (tight range) : bar-level, NO pivots. Trigger = EMA20 "flat" (>=2 direction
         changes over 8 bars  OR  4-bar drift < 0.20 ATR) AND contained band
         (<2.5 ATR). Boundaries drawn as ZONES: bottom = lowest low -> lowest close,
         top = highest close -> highest high (bodies contained; wick pokes / fBOs ok).

Usage:  python scripts/brooks_structure_engine.py [YYYY-MM-DD | rand]
Saves docs/living/tri_<YYYYMMDD>.png
"""
import sys, random
from pathlib import Path
from datetime import date
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT)); import massive

B = pd.read_parquet(ROOT/"data"/"bars"/"_continuous.parquet"); B["Date"] = B["DateTime"].dt.date.astype(str)
ALL = sorted(B["Date"].unique())


def build(DAY):
    g = B[B["Date"] == DAY].sort_values("DateTime").reset_index(drop=True)
    if not (20 < len(g) < 200): return None
    try:
        tk = massive.load_continuous_ticks(date.fromisoformat(DAY)).sort_values("DateTime")
    except Exception:
        return None
    if tk is None or len(tk) < 100: return None
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"]); n = len(g)
    tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1; tP = tk["Price"].values

    # ---- OB first-break by tick order ----
    def first_break(i):
        s = tP[tbar == i]; up = np.nonzero(s > H[i-1])[0]; dn = np.nonzero(s < L[i-1])[0]
        if not len(up) and not len(dn): up = np.nonzero(s >= H[i-1])[0]; dn = np.nonzero(s <= L[i-1])[0]
        tu = up[0] if len(up) else np.inf; td = dn[0] if len(dn) else np.inf
        return "D" if td < tu else "U"

    ob_side = {}; evs = {}
    for i in range(1, n):
        bt = H[i] > H[i-1]; bb = L[i] < L[i-1]; eq = (H[i] == H[i-1]) and (L[i] == L[i-1])
        if (bt and bb) or eq: fb = first_break(i); ob_side[i] = fb; evs[i] = ["D", "U"] if fb == "D" else ["U", "D"]
        elif bt: evs[i] = ["U"]
        elif bb: evs[i] = ["D"]
        else: evs[i] = []

    # ---- legs -> swing pivots ----
    st = {"d": None, "ext": 0}; piv = []
    def proc(ev, i):
        if ev == "U":
            if st["d"] == -1: piv.append((st["ext"], "L")); st["d"] = 1; st["ext"] = i
            else: st["d"] = 1; st["ext"] = i if H[i] >= H[st["ext"]] else st["ext"]
        else:
            if st["d"] == 1: piv.append((st["ext"], "H")); st["d"] = -1; st["ext"] = i
            else: st["d"] = -1; st["ext"] = i if L[i] <= L[st["ext"]] else st["ext"]
    for i in range(1, n):
        for ev in evs[i]: proc(ev, i)
    piv.append((st["ext"], "H" if st["d"] == 1 else "L"))

    tagged = []; prevH = 0; prevL = 0
    for (bar, typ) in piv:
        if typ == "H": t = "HH" if H[bar] > H[prevH] else ("LH" if H[bar] < H[prevH] else "DH"); prevH = bar
        else: t = "HL" if L[bar] > L[prevL] else ("LL" if L[bar] < L[prevL] else "DL"); prevL = bar
        tagged.append((bar, typ, t))
    def px(m): return H[tagged[m][0]] if tagged[m][1] == "H" else L[tagged[m][0]]

    lastH = lastL = None; state = []
    key = {("HH","HL"):"bull", ("LH","LL"):"bear", ("LH","HL"):"contract", ("HH","LL"):"expand"}
    for (bar, typ, t) in tagged:
        if typ == "H": lastH = t
        else: lastL = t
        state.append(key.get((lastH, lastL)) if (lastH in ("HH","LH") and lastL in ("HL","LL")) else None)

    # ---- CONTRACTING ----
    contract = []; k = 0
    while k < len(state):
        if state[k] == "contract":
            j = k
            while j+1 < len(state) and state[j+1] == "contract": j += 1
            refH = next((m for m in range(k-1,-1,-1) if tagged[m][1] == "H"), None)
            refL = next((m for m in range(k-1,-1,-1) if tagged[m][1] == "L"), None)
            start = min(x for x in (refH, refL, k) if x is not None)
            mem = list(range(start, j+1))
            Hs = [(tagged[m][0], H[tagged[m][0]]) for m in mem if tagged[m][1] == "H"]
            Ls = [(tagged[m][0], L[tagged[m][0]]) for m in mem if tagged[m][1] == "L"]
            if len(Hs) >= 2 and len(Ls) >= 2 and Hs[-1][1] < Hs[0][1] and Ls[-1][1] > Ls[0][1]: contract.append((Hs, Ls, mem))
            k = j+1
        else: k += 1

    # ---- EXPANDING (5-pt broadening) ----
    ecands = []
    for s in range(0, len(tagged)-4):
        w = list(range(s, s+5)); ty = [tagged[m][1] for m in w]
        if not all(ty[a] != ty[a+1] for a in range(4)): continue
        vals = [px(m) for m in w]
        His = [vals[q] for q in range(5) if tagged[w[q]][1] == "H"]
        Lis = [vals[q] for q in range(5) if tagged[w[q]][1] == "L"]
        if not (len(His) >= 2 and len(Lis) >= 2
                and all(His[a] < His[a+1] for a in range(len(His)-1))
                and all(Lis[a] > Lis[a+1] for a in range(len(Lis)-1))): continue
        legs = [abs(vals[q+1]-vals[q]) for q in range(4)]
        if legs[-1] > 2.2*max(legs[:-1]): continue          # last leg = breakout
        ecands.append((s, w))
    ecands.sort(key=lambda c: -c[0])                         # latest-starting first
    expand = []; eused = set()
    for s, w in ecands:
        if any(q in eused for q in w): continue
        brk = tagged[s+5][0] if s+5 < len(tagged) else None
        expand.append((w, brk)); eused |= set(w)
    expand = sorted(expand, key=lambda e: e[0][0])

    # ---- TTR (bar-level): EMA flat + contained band ----
    rng = H - L
    tr = np.maximum(H[1:]-L[1:], np.maximum(abs(H[1:]-C[:-1]), abs(L[1:]-C[:-1])))
    tr = np.concatenate([[H[0]-L[0]], tr]); A = np.array([tr[max(0,i-13):i+1].mean() for i in range(n)])
    def _ema(x, p):
        aa = 2/(p+1); e = np.full(n, np.nan); e[0] = x[0]
        for i in range(1, n): e[i] = aa*x[i] + (1-aa)*e[i-1]
        return e
    E20 = _ema(C, 20); ed = np.sign(np.diff(E20)); Wb = 8
    dchg = np.zeros(n, dtype=int)
    for i in range(1, n):
        a0 = max(1, i-Wb+1)
        dchg[i] = sum(1 for j in range(a0+1, i+1) if ed[j-1] and ed[j-2] and ed[j-1] != ed[j-2])
    flagB = np.zeros(n, dtype=bool)
    for i in range(Wb, n):
        band = H[i-Wb+1:i+1].max() - L[i-Wb+1:i+1].min()
        slope4 = abs(E20[i] - E20[i-4]) / A[i]
        flagB[i] = ((dchg[i] >= 2) or (slope4 < 0.20)) and (band < 2.5*A[i])
    ttr = []; k = 0
    while k < n:
        if flagB[k]:
            j = k
            while j+1 < n and flagB[j+1]: j += 1
            if j - k + 1 >= 4: ttr.append((max(0, k-3), j))
            k = j+1
        else: k += 1
    merged = []
    for (a, z) in ttr:
        if merged and a <= merged[-1][1] + 1: merged[-1] = (merged[-1][0], max(merged[-1][1], z))
        else: merged.append((a, z))
    ttr = merged

    # ---- chart ----
    pb = [p[0] for p in piv]; pp = [H[p[0]] if p[1] == "H" else L[p[0]] for p in piv]
    fig, ax = plt.subplots(figsize=(30, 12)); off = 0.014*(H.max()-L.min())
    for i in range(n):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.plot([i, i], [L[i], H[i]], color=col, lw=1.4, zorder=2)
        ax.add_patch(plt.Rectangle((i-0.34, min(O[i], C[i])), 0.68, max(abs(C[i]-O[i]), .02), facecolor=col, edgecolor="black", lw=0.4, zorder=3))
    for i, s in ob_side.items():
        ax.plot(i, H[i]+off*0.6 if s == "U" else L[i]-off*0.6, "o", ms=7, color="gold", mec="black", mew=0.6, zorder=8)
    ax.plot(pb, pp, color="steelblue", lw=1.0, ls=":", marker="o", ms=4, alpha=0.5, zorder=5)
    for (bar, typ, t) in tagged:
        c = "darkgreen" if t in ("HH","HL") else ("darkred" if t in ("LH","LL") else "gray")
        ax.text(bar, (H[bar]+off) if typ == "H" else (L[bar]-off), t, ha="center", va="bottom" if typ == "H" else "top", fontsize=8.5, fontweight="bold", color=c, zorder=7)

    def draw_tri(mem, color, fill, label, brk=None):
        Hs = [(tagged[m][0], px(m)) for m in mem if tagged[m][1] == "H"]
        Ls = [(tagged[m][0], px(m)) for m in mem if tagged[m][1] == "L"]
        x0 = min(Hs[0][0], Ls[0][0])-0.5; x1 = max(Hs[-1][0], Ls[-1][0])+0.5
        ax.axvspan(x0, x1, color=fill, alpha=0.42, zorder=0)
        ax.plot([Hs[0][0], Hs[-1][0]], [Hs[0][1], Hs[-1][1]], color=color, lw=2.4, zorder=6)
        ax.plot([Ls[0][0], Ls[-1][0]], [Ls[0][1], Ls[-1][1]], color=color, lw=2.4, zorder=6)
        ax.text((x0+x1)/2, H.max()+off, label, ha="center", va="bottom", fontsize=9, fontweight="bold", color=color, zorder=9)
        if brk is not None:
            ax.annotate("breakout", (brk, H[brk]), (brk, H[brk]+off*3), fontsize=8, color="black", fontweight="bold", ha="center", arrowprops=dict(arrowstyle="->", color="black"))
    for (Hs, Ls, mem) in contract: draw_tri(mem, "navy", "#cfe8ff", "CONTRACTING")
    for (mem, brk) in expand: draw_tri(mem, "darkorange", "#ffe0b3", "EXPANDING (5pt)", brk)
    for (a, z) in ttr:  # TTR boundary ZONES
        top_body = C[a:z+1].max(); top_wick = H[a:z+1].max()
        bot_body = C[a:z+1].min(); bot_wick = L[a:z+1].min()
        x0, x1 = a-0.5, z+0.5
        ax.add_patch(plt.Rectangle((x0, top_body), x1-x0, top_wick-top_body, facecolor="green", alpha=0.22, edgecolor="green", lw=1.4, zorder=11))
        ax.add_patch(plt.Rectangle((x0, bot_wick), x1-x0, bot_body-bot_wick, facecolor="green", alpha=0.22, edgecolor="green", lw=1.4, zorder=11))
        ax.text((x0+x1)/2, top_wick+off*1.0, "TTR", ha="center", va="bottom", fontsize=9, fontweight="bold", color="green", zorder=11)

    ax.set_ylim(L.min()-off*3, H.max()+off*5)
    ax.set_xticks(range(0, n, 2)); ax.set_xticklabels([str(i+1) for i in range(0, n, 2)], fontsize=7); ax.grid(alpha=0.25, lw=0.5)
    ax.set_title("%s - pivots (HH/LH/HL/LL, OB tick-dots) + contracting/expanding triangles + TTR zones" % DAY, fontsize=12, fontweight="bold")
    fig.tight_layout()
    out = ROOT/"docs"/"living"/("tri_%s.png" % DAY.replace("-", "")); fig.savefig(out, dpi=115); plt.close(fig)
    print("saved %s  | contracting=%d expanding=%d ttr=%d" % (out, len(contract), len(expand), len(ttr)))
    return str(out)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "2022-02-24"
    if arg == "rand":
        random.seed()
        cand = ALL[:]; random.shuffle(cand)
        got = 0
        for dd in cand:
            if build(dd): got += 1
            if got == 2: break
    else:
        build(arg)
