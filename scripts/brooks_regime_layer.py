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


def build(DAY, out=None, crop_majors=None):
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

    # An OUTSIDE bar's range is always BIGGER than the prior bar's: one side may be equal, but
    # never both. A bar with the SAME high AND the same low is a perfect INSIDE bar — it breaks
    # neither side, so it contributes nothing (it is NOT an OB and gets no tick-order treatment).
    # The two one-sided OB variants only extend on one side, so that side is the break by
    # construction and no tick order is needed.
    ob_side = {}; evs = {}
    for i in range(1, n):
        bt = H[i] > H[i-1]; bb = L[i] < L[i-1]
        eqH = H[i] == H[i-1]; eqL = L[i] == L[i-1]
        if bt and bb: fb = first_break(i); ob_side[i] = fb; evs[i] = ["D", "U"] if fb == "D" else ["U", "D"]
        elif bt and eqL: ob_side[i] = "U"; evs[i] = ["U"]   # OB, high side extends
        elif bb and eqH: ob_side[i] = "D"; evs[i] = ["D"]   # OB, low side extends
        elif bt: evs[i] = ["U"]
        elif bb: evs[i] = ["D"]
        else: evs[i] = []                                   # inside bar, incl. the equal bar

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
    major_hh = {}                  # bar -> the major HL confirmed against this reference high
    major_ll = {}                  # bar -> the major LH confirmed against this reference low
    newext = {}                    # HL/LH pullback bar -> the NEW-EXTREME bar that confirmed it
    breaks = []                    # (bar, "bull"|"bear") — standing major level taken out
    run_max_H = H[0]; run_max_H_bar = 0
    run_min_L = L[0]; run_min_L_bar = 0
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
        nonlocal run_max_H, run_max_H_bar, standing_major_lh, standing_major_hl, cand_lo, cand_hi, bull_attempt, bear_attempt, break_bar_bear
        if standing_major_lh is not None and H[i] > standing_major_lh:
            breaks.append((i, "bear")); standing_major_lh = None; cand_hi = None; bear_attempt = True; break_bar_bear = i
        ok_to_confirm = (not bull_attempt) or ("H" in tagged_by_bar.get(i, []))
        if H[i] > run_max_H and cand_lo is not None and cand_lo[0] != i and ok_to_confirm:
            major_hl[cand_lo[0]] = cand_lo[1]; newext[cand_lo[0]] = i   # HL known at this NEW HIGH
            if "H" in tagged_by_bar.get(i, []):
                major_hh[i] = H[i]  # confirming bar is itself the fresh peak
            else:
                major_hh[run_max_H_bar] = H[run_max_H_bar]
            standing_major_hl = cand_lo[1]; cand_lo = None; bull_attempt = False
        if H[i] > run_max_H: run_max_H = H[i]; run_max_H_bar = i
        if "H" in tagged_by_bar.get(i, []):
            if i == break_bar_bear:
                minor_lh[i] = H[i]   # the break bar's own high doesn't seed the next candidate
            elif cand_hi is None or H[i] > cand_hi[1]:
                if cand_hi is not None: minor_lh[cand_hi[0]] = cand_hi[1]
                cand_hi = (i, H[i])
            else:
                minor_lh[i] = H[i]

    def do_down(i):
        nonlocal run_min_L, run_min_L_bar, standing_major_hl, standing_major_lh, cand_hi, cand_lo, bull_attempt, bear_attempt, break_bar_bull
        if standing_major_hl is not None and L[i] < standing_major_hl:
            breaks.append((i, "bull")); standing_major_hl = None; cand_lo = None; bull_attempt = True; break_bar_bull = i
        ok_to_confirm = (not bear_attempt) or ("L" in tagged_by_bar.get(i, []))
        if L[i] < run_min_L and cand_hi is not None and cand_hi[0] != i and ok_to_confirm:
            major_lh[cand_hi[0]] = cand_hi[1]; newext[cand_hi[0]] = i   # LH known at this NEW LOW
            if "L" in tagged_by_bar.get(i, []):
                major_ll[i] = L[i]  # confirming bar is itself the fresh trough
            else:
                major_ll[run_min_L_bar] = L[run_min_L_bar]
            standing_major_lh = cand_hi[1]; cand_hi = None; bear_attempt = False
        if L[i] < run_min_L: run_min_L = L[i]; run_min_L_bar = i
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

    # ==== OPEN-OF-DAY H/L seed propagation — the PRE-PHASE before the first pivot ====
    # b1 always seeds BOTH an H and an L. Each later bar vs the PRIOR bar (two-bar rule):
    #   higher-high only  -> H moves onto this bar (the L stays where it was)
    #   lower-low only    -> L moves onto this bar (the H stays where it was)
    #   outside bar       -> BOTH H and L carry forward onto this bar
    #   inside bar        -> neither moves (this bar gets no label)
    #   equal bar (H==,L==) -> a perfect INSIDE bar, ignored exactly like one
    # The label only continues on the side that breaks out. The open phase runs ONLY until
    # the first real swing pivot forms (tagged[0], e.g. b5 HH on 2/24, confirmed when b6
    # breaks below it); from that bar on, the regular engine below takes over. The carried-
    # forward open marks (H trail + the b1 L) are kept faded on the chart so the hand-off is
    # visible. (Starting simple: OB carries both, no tick-order decomposition yet.)
    first_piv_bar = tagged[0][0] if tagged else n-1
    open_H = [False]*n; open_L = [False]*n
    open_H[0] = True; open_L[0] = True
    for i in range(1, first_piv_bar+1):
        bt = H[i] > H[i-1]; bb = L[i] < L[i-1]
        if bt and bb:
            open_H[i] = True; open_L[i] = True
        elif bt:
            open_H[i] = True
        elif bb:
            open_L[i] = True
        # inside bar (and the equal bar, which is a perfect inside bar): neither

    # ==== CONFIRMATION — TWO parallel rules, chosen by the pivot's label ====
    # HH / LL are TREND-CONTINUATION pivots: KNOWN at the TURN — price ticks back the other
    #   way (a high fixed when a later bar ticks below it: b11->b12; the first pivot too: b5->b6).
    # HL / LH are PULLBACK pivots: KNOWN only when the trend RESUMES to a NEW EXTREME past the
    #   prior swing extreme (HL needs a new high, LH a new low): b8->b9, b15->b20, b35->b52.
    #   b16 is NOT a new high above b11, so b15 is not yet a HL at b16.
    # Keyed by (bar, side) so an OB bar that is major on both sides gets a correct number each.
    def turn_bar(p, typ):
        for j in range(p+1, n):
            if (typ == "H" and L[j] < L[j-1]) or (typ == "L" and H[j] > H[j-1]):
                return j
        return None
    confirm = {}   # (bar, "H"/"L") -> confirmation bar index
    for b in major_hh:                                   # HH -> turn down
        tb = turn_bar(b, "H")
        if tb is not None: confirm[(b, "H")] = tb
    for b in major_ll:                                   # LL -> turn up
        tb = turn_bar(b, "L")
        if tb is not None: confirm[(b, "L")] = tb
    for b in major_hl:                                   # HL -> new high (from the pass)
        if b in newext: confirm[(b, "L")] = newext[b]
    for b in major_lh:                                   # LH -> new low (from the pass)
        if b in newext: confirm[(b, "H")] = newext[b]
    fp_typ = tagged[0][1] if tagged else "H"             # first pivot -> turn
    tb = turn_bar(first_piv_bar, fp_typ)
    if tb is not None: confirm[(first_piv_bar, fp_typ)] = tb

    major_bars = set(major_hl) | set(major_lh) | set(major_hh) | set(major_ll) | {first_piv_bar}
    known_order = sorted(major_bars, key=lambda b: (min([v for (bb, s), v in confirm.items() if bb == b] or [b]), b))
    xmax = n - 1
    if crop_majors and len(known_order) >= crop_majors:
        nth = known_order[crop_majors-1]
        cvals = [v for (bb, s), v in confirm.items() if bb == nth] or [nth]
        xmax = min(n - 1, max(cvals) + 2)

    # ---- chart ----
    # scale label spacing to the VISIBLE range so cropped views aren't dwarfed by full-day range
    vhi = H[:xmax+1].max(); vlo = L[:xmax+1].min()
    off = 0.014 * max(vhi - vlo, 0.5)
    fig, ax = plt.subplots(figsize=(30, 12))

    # fixed vertical tiers (data units) for each side of a bar so labels never overlap:
    #   minor label nearest the bar, then the major circle, then bar number below the low.
    T_MINOR = off*1.0     # minor two-bar label, just beyond the bar
    T_MAJOR = off*4.2     # major circle, well clear of the minor label
    T_NUM_D = off*7.6     # bar number below a major-low stack (clears circle + confirm#)
    OPEN_C  = "#9a7d0a"   # neutral gold for first-leg single H/L

    # shade the OPEN pre-phase (b1 .. first pivot bar) + banner
    ax.axvspan(-0.5, first_piv_bar+0.5, color="#fff2cc", alpha=0.55, zorder=0)
    ax.text(first_piv_bar/2.0, vhi+off*6.0, "OPEN  (b1 seeds H/L → first pivot b%d)" % (first_piv_bar+1),
            ha="center", va="bottom", fontsize=10, fontweight="bold", color=OPEN_C, zorder=9)

    for i in range(n):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.plot([i, i], [L[i], H[i]], color=col, lw=1.4, zorder=2)
        ax.add_patch(plt.Rectangle((i-0.34, min(O[i], C[i])), 0.68, max(abs(C[i]-O[i]), .02), facecolor=col, edgecolor="black", lw=0.4, zorder=3))

    # yellow dot on each OUTSIDE bar marking which side broke the prior bar FIRST (from tick
    # order): dot on the high if it broke up first, on the low if it broke down first.
    for i, s in ob_side.items():
        if i > xmax: continue
        yy = H[i] + off*0.5 if s == "U" else L[i] - off*0.5
        ax.plot(i, yy, "o", ms=8, color="gold", mec="black", mew=0.7, zorder=6)

    def confirm_outside(bar, typ, ycirc, color):
        # the bar# at which this major pivot became KNOWN in real time, printed just outside
        # the circle (above a high-circle / below a low-circle) so it never crowds neighbours
        cb = confirm.get((bar, typ))
        if cb is not None:
            yy = ycirc + off*1.6 if typ == "H" else ycirc - off*1.6
            ax.text(bar, yy, str(cb+1), ha="center", va=("bottom" if typ == "H" else "top"),
                    fontsize=10, fontweight="bold", color=color, zorder=8)

    def major_circle(bar, typ, label, color):
        yc = (H[bar]+T_MAJOR) if typ == "H" else (L[bar]-T_MAJOR)
        ax.text(bar, yc, label, ha="center", va="center", fontsize=11, fontweight="bold", color=color, zorder=8,
                bbox=dict(boxstyle="circle,pad=0.3", fc="white", ec=color, lw=1.4))
        confirm_outside(bar, typ, yc, color)

    # open seed trail: single H/L carried up to (not incl.) the first pivot bar, kept faded
    for i in range(first_piv_bar):
        if open_H[i]:
            ax.text(i, H[i]+T_MINOR, "H", ha="center", va="bottom", fontsize=14, fontweight="bold", color="#1b5e20", alpha=0.8, zorder=6)
        if open_L[i]:
            ax.text(i, L[i]-T_MINOR, "L", ha="center", va="top", fontsize=14, fontweight="bold", color="#b71c1c", alpha=0.8, zorder=6)

    # engine pivots: EVERY pivot gets its minor two-bar label (nearest the bar); major pivots
    # ALSO get a circled major label further out + the real-time confirmation bar# beside it.
    # First-leg pivot is the exception: a single gold H/L (no minor, no double label).
    for (bar, typ, t) in tagged:
        if t not in ("HH", "HL", "LH", "LL") or bar > xmax: continue
        if bar == first_piv_bar:
            major_circle(bar, typ, typ, OPEN_C)   # single letter, gold, uses confirm (its turn bar)
            continue
        mc = "darkgreen" if t in ("HH", "HL") else "darkred"      # minor colour from the two-bar tag
        if typ == "H":
            ax.text(bar, H[bar]+T_MINOR, t.lower(), ha="center", va="bottom", fontsize=13, fontweight="normal", color=mc, alpha=0.6, zorder=7)
        else:
            ax.text(bar, L[bar]-T_MINOR, t.lower(), ha="center", va="top", fontsize=13, fontweight="normal", color=mc, alpha=0.6, zorder=7)
        if   typ == "L" and bar in major_hl: major_circle(bar, typ, "HL", "darkgreen")
        elif typ == "L" and bar in major_ll: major_circle(bar, typ, "LL", "darkred")
        elif typ == "H" and bar in major_hh: major_circle(bar, typ, "HH", "darkgreen")
        elif typ == "H" and bar in major_lh: major_circle(bar, typ, "LH", "darkred")

    # major reference extremes that are not themselves tagged swing pivots (tied highs/lows)
    tagged_bars = {b for (b, _, _) in tagged}
    for bar in major_hh:
        if bar <= xmax and bar not in tagged_bars: major_circle(bar, "H", "HH", "darkgreen")
    for bar in major_ll:
        if bar <= xmax and bar not in tagged_bars: major_circle(bar, "L", "LL", "darkred")

    for (bar, side) in breaks:
        if bar > xmax: continue
        ax.axvline(bar-0.5, color="black", lw=1.5, ls=(0, (2, 2)), zorder=4)
        ax.text(bar-0.5, vhi+off*3.6, "%s BREAK→NEUTRAL" % side.upper(), ha="center", va="bottom", fontsize=8, fontweight="bold", color="black", zorder=9)

    # bar numbers below each low, dropped far enough to clear whatever is stacked below it
    deep_low = set(major_hl) | set(major_ll)                      # major low -> below the circle
    if tagged and tagged[0][1] == "L": deep_low.add(first_piv_bar)
    mid_low = {b for (b, ty, _) in tagged if ty == "L"} | {i for i in range(first_piv_bar) if open_L[i]}
    num_ys = []
    for i in range(min(n, xmax+1)):
        d = T_NUM_D if i in deep_low else (off*2.3 if i in mid_low else off*1.2)
        y = L[i] - d; num_ys.append(y)
        ax.text(i, y, str(i+1), ha="center", va="top", fontsize=12, fontweight="normal", color="#333333", zorder=7)

    ax.set_ylim(min(num_ys)-off*1.5, vhi+off*8)
    if xmax < n - 1:
        ax.set_xlim(-0.7, xmax+0.9)
        ax.set_title("%s - OPEN → first %d major pivots (crop @ b%d) · minor label + major circle + confirm bar#" % (DAY, crop_majors, xmax+1), fontsize=11, fontweight="bold")
    else:
        ax.set_title("%s - swing pivots: minor label (near bar) + circled major + real-time confirmation bar# outside the circle" % DAY, fontsize=11, fontweight="bold")
    ax.set_xticks([]); ax.grid(alpha=0.25, lw=0.5)

    fig.tight_layout()
    if out is None:
        out = ROOT/"docs"/"living"/("regime_layer_%s.png" % DAY.replace("-", ""))
    fig.savefig(out, dpi=200); plt.close(fig)
    def _cf(b):
        vs = [v for (bb, s), v in confirm.items() if bb == b]
        return (min(vs)+1) if vs else None
    print("saved %s  | first_pivot=b%d(%s)  confirm(b#->known@)=%s" % (
        out, first_piv_bar+1, tagged[0][1] if tagged else "?",
        [(b+1, _cf(b)) for b in known_order[:6]]))
    return str(out)


def gallery(ndays=10, crop_majors=2, seed=None):
    """Pick N random valid days, render each cropped to the first `crop_majors` major
    pivots, and save PNGs into a gallery dir. Prints the saved paths (one per line)."""
    import random as _random
    _random.seed(seed)
    outdir = ROOT/"docs"/"living"/"open_gallery"; outdir.mkdir(parents=True, exist_ok=True)
    cand = ALL[:]; _random.shuffle(cand)
    done = []
    for dd in cand:
        if len(done) >= ndays: break
        outp = outdir/("open_%s.png" % dd.replace("-", ""))
        try:
            r = build(dd, out=outp, crop_majors=crop_majors)
        except Exception as e:
            print("skip %s (%s)" % (dd, e)); continue
        if r: done.append((dd, str(outp)))
    print("GALLERY_DONE %d days" % len(done))
    for dd, p in done: print("GALLERY %s %s" % (dd, p))
    return done


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "2022-02-24"
    if arg == "gallery":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        seed = int(sys.argv[3]) if len(sys.argv) > 3 else None
        gallery(n, crop_majors=2, seed=seed)
    else:
        build(arg)
