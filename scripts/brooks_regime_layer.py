"""Brooks multi-state regime layer (regime/v2-multistate kickoff, 2026-07-21) — built
ON TOP OF scripts/brooks_structure_engine.py, which is NOT modified. Its structure
primitives (two-bar labels, OB tick-order, swing-pivot HH/LH/HL/LL tagging, contracting/
expanding triangles, TTR zones) have no importable API — build() only returns a file
path — so the tagging logic is mirrored here verbatim and must be kept in sync by hand
if the structure engine ever changes. The OLD regime state machine (scripts/
brooks_regime_day.py) is banned per the S62 handoff note (inverted/frozen on both a
clean uptrend and a clean downtrend) and is neither touched nor reused here.

REGIME STATES (5, per the S72 design brief):
    BEAR  BEAR_ATTEMPT  NEUTRAL  BULL_ATTEMPT  BULL
    -2         -1           0          1         2

S62 INVARIANT (non-negotiable): a clean run of HH/HL pivots must hold BULL throughout;
a clean run of LH/LL pivots must hold BEAR throughout. The ATTEMPT states exist so a
single counter-direction pivot (one pullback) cannot instantly flip or freeze the regime
the way the old single-close flip did — it only steps the ladder one notch, so a lone
counter-pivot inside a clean trend lands in an ATTEMPT state next to the trend, not a
full flip, and a clean run never sees a same-direction pivot revert it.

RULE v1 (starting point — refine together bar-by-bar, per pivot event):
    HH or HL (a "higher" pivot)  -> score = min(score + 1, +2)
    LH or LL (a "lower" pivot)   -> score = max(score - 1, -2)
    DH or DL (equal, no info)    -> score unchanged
Regime holds constant bar-to-bar between pivot events (a step function), starting at
NEUTRAL (0) before the first pivot resolves.

Usage:  python scripts/brooks_regime_layer.py [YYYY-MM-DD]
Saves docs/living/regime_layer_<YYYYMMDD>.png
"""
import sys
from pathlib import Path
from datetime import date
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT)); import massive

B = pd.read_parquet(ROOT/"data"/"bars"/"_continuous.parquet"); B["Date"] = B["DateTime"].dt.date.astype(str)
ALL = sorted(B["Date"].unique())

STATE_NAME = {-2: "BEAR", -1: "BEAR_ATTEMPT", 0: "NEUTRAL", 1: "BULL_ATTEMPT", 2: "BULL"}
STATE_COLOR = {
    -2: "#b23a2e",  # BEAR
    -1: "#e8a598",  # BEAR_ATTEMPT
     0: "#9aa0a6",  # NEUTRAL
     1: "#8bc98f",  # BULL_ATTEMPT
     2: "#1f7a3d",  # BULL
}


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

    # ---- OB first-break by tick order (mirrors brooks_structure_engine.py) ----
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

    # ---- legs -> swing pivots (mirrors brooks_structure_engine.py) ----
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

    # ---- CONTRACTING (mirrors brooks_structure_engine.py) ----
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

    # ---- EXPANDING 5-pt broadening (mirrors brooks_structure_engine.py) ----
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

    # ---- TTR bar-level (mirrors brooks_structure_engine.py) ----
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

    # ==== NEW: regime ladder (BEAR=-2 .. BULL=+2), one score update per pivot ====
    score = 0; regime_at_pivot = []   # [(bar, score_after_this_pivot)]
    for (bar, typ, t) in tagged:
        if t in ("HH", "HL"): score = min(score + 1, 2)
        elif t in ("LH", "LL"): score = max(score - 1, -2)
        # DH/DL: no info, score unchanged
        regime_at_pivot.append((bar, score))

    regime = np.zeros(n, dtype=int)  # per-bar score, step function, NEUTRAL before first pivot
    cur = 0; ptr = 0
    for i in range(n):
        while ptr < len(regime_at_pivot) and regime_at_pivot[ptr][0] == i:
            cur = regime_at_pivot[ptr][1]; ptr += 1
        regime[i] = cur
    flips = [i for i in range(1, n) if regime[i] != regime[i-1]]

    # ---- chart (base layers mirror brooks_structure_engine.py, regime is new) ----
    pb = [p[0] for p in piv]; pp = [H[p[0]] if p[1] == "H" else L[p[0]] for p in piv]
    fig, ax = plt.subplots(figsize=(30, 12)); off = 0.014*(H.max()-L.min())

    # regime background shading — drawn first, lowest z-order, full height
    k = 0
    while k < n:
        j = k
        while j+1 < n and regime[j+1] == regime[k]: j += 1
        ax.axvspan(k-0.5, j+0.5, color=STATE_COLOR[regime[k]], alpha=0.16, zorder=0)
        k = j+1

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
        ax.plot([Hs[0][0], Hs[-1][0]], [Hs[0][1], Hs[-1][1]], color=color, lw=2.4, zorder=6)
        ax.plot([Ls[0][0], Ls[-1][0]], [Ls[0][1], Ls[-1][1]], color=color, lw=2.4, zorder=6)
        ax.text((x0+x1)/2, H.max()+off, label, ha="center", va="bottom", fontsize=9, fontweight="bold", color=color, zorder=9)
        if brk is not None:
            ax.annotate("breakout", (brk, H[brk]), (brk, H[brk]+off*3), fontsize=8, color="black", fontweight="bold", ha="center", arrowprops=dict(arrowstyle="->", color="black"))
    for (Hs, Ls, mem) in contract: draw_tri(mem, "navy", None, "CONTRACTING")
    for (mem, brk) in expand: draw_tri(mem, "darkorange", None, "EXPANDING (5pt)", brk)
    for (a, z) in ttr:  # TTR boundary ZONES
        top_body = C[a:z+1].max(); top_wick = H[a:z+1].max()
        bot_body = C[a:z+1].min(); bot_wick = L[a:z+1].min()
        x0, x1 = a-0.5, z+0.5
        ax.add_patch(plt.Rectangle((x0, top_body), x1-x0, top_wick-top_body, facecolor="green", alpha=0.22, edgecolor="green", lw=1.4, zorder=11))
        ax.add_patch(plt.Rectangle((x0, bot_wick), x1-x0, bot_body-bot_wick, facecolor="green", alpha=0.22, edgecolor="green", lw=1.4, zorder=11))
        ax.text((x0+x1)/2, top_wick+off*1.0, "TTR", ha="center", va="bottom", fontsize=9, fontweight="bold", color="green", zorder=11)

    # NEW: dotted flip lines + state-name tag at each regime transition
    for i in flips:
        ax.axvline(i-0.5, color="#555555", lw=1.3, ls=(0, (2, 2)), zorder=4)
        ax.text(i-0.5, H.max()+off*3.2, STATE_NAME[regime[i]], ha="center", va="bottom", fontsize=7.5, fontweight="bold", color="#333333", rotation=90, zorder=9)

    ax.set_ylim(L.min()-off*3, H.max()+off*7)
    ax.set_xticks(range(0, n, 2)); ax.set_xticklabels([str(i+1) for i in range(0, n, 2)], fontsize=7); ax.grid(alpha=0.25, lw=0.5)
    ax.set_title("%s - regime layer v1 (%s) + pivots/triangles/TTR from brooks_structure_engine" % (DAY, "/".join(STATE_NAME[s] for s in (-2,-1,0,1,2))), fontsize=11, fontweight="bold")

    # legend for regime shading
    handles = [plt.Rectangle((0,0),1,1, color=STATE_COLOR[s], alpha=0.5) for s in (-2,-1,0,1,2)]
    ax.legend(handles, [STATE_NAME[s] for s in (-2,-1,0,1,2)], loc="upper left", fontsize=8, ncol=5, framealpha=0.85)

    fig.tight_layout()
    out = ROOT/"docs"/"living"/("regime_layer_%s.png" % DAY.replace("-", "")); fig.savefig(out, dpi=115); plt.close(fig)
    print("saved %s  | contracting=%d expanding=%d ttr=%d flips=%d final=%s" % (out, len(contract), len(expand), len(ttr), len(flips), STATE_NAME[regime[-1]]))
    return str(out)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "2022-02-24"
    build(arg)
