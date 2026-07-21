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

    # ==== NEW: major/minor HL (bull) and LH (bear) — coarse swing structure, distinct
    # from the fine-grained two-bar/OB tags above. A candidate L-pivot (any HL/LL/DL)
    # becomes the tracked "deepest pullback since last confirmation"; it is promoted to
    # MAJOR only when a later bar's raw High exceeds the running all-time-high that stood
    # when this candidate was set. Mirrored for H-pivots (HH/LH/DH) -> major LH, confirmed
    # when a later bar's raw Low undercuts the running all-time-low.
    #
    # An OB/equal bar can contain BOTH a high-side and low-side event in one bar — the
    # confirm-check, break-check, and candidate-update for each side must run in the
    # bar's actual tick order (already known via evs[i], the same tick-order info the
    # swing-pivot decomposition above uses), or a bar like an outside bar that broke down
    # first then rallied to a new extreme gets misread as its OWN new candidate low
    # instead of merely confirming the PRIOR candidate.
    #
    # standing_major_hl/lh = the last CONFIRMED major level, persists until superseded by
    # the next confirmation or BROKEN (a bar's Low undercuts standing_major_hl, or High
    # exceeds standing_major_lh) -> recorded in `breaks` as a trend-break-to-neutral event.
    major_hl = {}; minor_hl = {}   # bar -> low
    major_lh = {}; minor_lh = {}   # bar -> high
    breaks = []                    # (bar, "bull"|"bear") — standing major level taken out
    run_max_H = H[0]; run_min_L = L[0]
    standing_major_hl = None; standing_major_lh = None
    cand_lo = None    # (bar, low) deepest L-pivot pending confirmation as major HL
    cand_hi = None    # (bar, high) highest H-pivot pending confirmation as major LH
    bull_attempt = False   # since the last bull break: reconfirmation needs a genuine HH pivot,
    bear_attempt = False   # not just any bar poking a new extreme (S72 ATTEMPT-state intent)
    break_bar_bull = None  # the exact bar of the last bull break — its OWN pivot (if any)
    break_bar_bear = None  # doesn't seed the next candidate; the bar AFTER it can
    tagged_by_bar = {}
    for (bar, typ, t) in tagged: tagged_by_bar.setdefault(bar, []).append(typ)

    def do_up(i):
        nonlocal run_max_H, standing_major_lh, standing_major_hl, cand_lo, cand_hi, bull_attempt, bear_attempt, break_bar_bear
        if standing_major_lh is not None and H[i] > standing_major_lh:
            breaks.append((i, "bear")); standing_major_lh = None; cand_hi = None; bear_attempt = True; break_bar_bear = i
        ok_to_confirm = (not bull_attempt) or ("H" in tagged_by_bar.get(i, []))
        if H[i] > run_max_H and cand_lo is not None and cand_lo[0] != i and ok_to_confirm:
            major_hl[cand_lo[0]] = cand_lo[1]; standing_major_hl = cand_lo[1]; cand_lo = None; bull_attempt = False
        run_max_H = max(run_max_H, H[i])
        if "H" in tagged_by_bar.get(i, []):
            if i == break_bar_bear:
                minor_lh[i] = H[i]   # the break bar's own high doesn't seed the next candidate
            elif cand_hi is None or H[i] > cand_hi[1]:
                if cand_hi is not None: minor_lh[cand_hi[0]] = cand_hi[1]
                cand_hi = (i, H[i])
            else:
                minor_lh[i] = H[i]

    def do_down(i):
        nonlocal run_min_L, standing_major_hl, standing_major_lh, cand_hi, cand_lo, bull_attempt, bear_attempt, break_bar_bull
        if standing_major_hl is not None and L[i] < standing_major_hl:
            breaks.append((i, "bull")); standing_major_hl = None; cand_lo = None; bull_attempt = True; break_bar_bull = i
        ok_to_confirm = (not bear_attempt) or ("L" in tagged_by_bar.get(i, []))
        if L[i] < run_min_L and cand_hi is not None and cand_hi[0] != i and ok_to_confirm:
            major_lh[cand_hi[0]] = cand_hi[1]; standing_major_lh = cand_hi[1]; cand_hi = None; bear_attempt = False
        run_min_L = min(run_min_L, L[i])
        if "L" in tagged_by_bar.get(i, []):
            if i == break_bar_bull:
                minor_hl[i] = L[i]   # the break bar's own low doesn't seed the next candidate
            elif cand_lo is None or L[i] < cand_lo[1]:
                if cand_lo is not None: minor_hl[cand_lo[0]] = cand_lo[1]
                cand_lo = (i, L[i])
            else:
                minor_hl[i] = L[i]

    for i in range(n):
        for ev in evs.get(i, []):
            do_up(i) if ev == "U" else do_down(i)

    # ---- chart: candles + HH/HL/LH/LL labels only (stripped for bar-by-bar review) ----
    fig, ax = plt.subplots(figsize=(30, 12)); off = 0.014*(H.max()-L.min())

    for i in range(n):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.plot([i, i], [L[i], H[i]], color=col, lw=1.4, zorder=2)
        ax.add_patch(plt.Rectangle((i-0.34, min(O[i], C[i])), 0.68, max(abs(C[i]-O[i]), .02), facecolor=col, edgecolor="black", lw=0.4, zorder=3))
    for (bar, typ, t) in tagged:
        if t not in ("HH", "HL", "LH", "LL"): continue
        c = "darkgreen" if t in ("HH","HL") else "darkred"
        y = (H[bar]+off) if typ == "H" else (L[bar]-off)
        va = "bottom" if typ == "H" else "top"
        if typ == "L" and bar in major_hl:
            ax.text(bar, y, "HL", ha="center", va=va, fontsize=12, fontweight="bold", color=c, zorder=7,
                    bbox=dict(boxstyle="circle,pad=0.35", fc="none", ec=c, lw=1.4))
        elif typ == "H" and bar in major_lh:
            ax.text(bar, y, "LH", ha="center", va=va, fontsize=12, fontweight="bold", color=c, zorder=7,
                    bbox=dict(boxstyle="circle,pad=0.35", fc="none", ec=c, lw=1.4))
        elif typ == "L" and bar in minor_hl:
            ax.text(bar, y, "hl", ha="center", va=va, fontsize=7, fontweight="normal", color=c, alpha=0.55, zorder=7)
        elif typ == "H" and bar in minor_lh:
            ax.text(bar, y, "lh", ha="center", va=va, fontsize=7, fontweight="normal", color=c, alpha=0.55, zorder=7)
        else:
            ax.text(bar, y, t, ha="center", va=va, fontsize=8.5, fontweight="bold", color=c, zorder=7)

    for (bar, side) in breaks:
        ax.axvline(bar-0.5, color="black", lw=1.5, ls=(0, (2, 2)), zorder=4)
        ax.text(bar-0.5, H.max()+off*2, "%s BREAK\n→ NEUTRAL" % side.upper(), ha="center", va="bottom", fontsize=7.5, fontweight="bold", color="black", zorder=9)

    ax.set_ylim(L.min()-off*3, H.max()+off*7)
    ax.set_xticks(range(0, n, 3)); ax.set_xticklabels([str(i+1) for i in range(0, n, 3)], fontsize=9, fontweight="bold"); ax.grid(alpha=0.25, lw=0.5)
    ax.set_title("%s - HH/HL/LH/LL swing pivots, major HL/LH circled, standing-level breaks dotted" % DAY, fontsize=11, fontweight="bold")

    fig.tight_layout()
    out = ROOT/"docs"/"living"/("regime_layer_%s.png" % DAY.replace("-", "")); fig.savefig(out, dpi=115); plt.close(fig)
    print("saved %s  | major_hl=%s minor_hl=%s major_lh=%s minor_lh=%s breaks=%s" % (
        out,
        sorted(b+1 for b in major_hl), sorted(b+1 for b in minor_hl),
        sorted(b+1 for b in major_lh), sorted(b+1 for b in minor_lh),
        [(b+1, s) for (b, s) in breaks]))
    return str(out)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "2022-02-24"
    build(arg)
