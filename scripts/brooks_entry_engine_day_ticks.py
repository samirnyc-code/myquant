"""Brooks entry engine (full labels) with a SETTING:  IGNORE_IB.

IGNORE_IB = True  -> inside bars are collapsed out of the series entirely. Every
                     bar's "prior bar" becomes the last NON-IB bar, so OB
                     detection, leg breaks and entry arming all reference the bar
                     BEFORE the inside bar. IBs never arm or trigger.
IGNORE_IB = False -> original behaviour (prior bar = immediate i-1).

Default day = 2026-06-09; pass a date as argv[1], or run with no arg for a random
day. Chart adds the OB first-break tag (H1st / L1st) as before.
"""
import sys, os
from pathlib import Path
from datetime import date
import random
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25
IGNORE_IB = True                      # legs/structure ignore IBs; entries arm off the bar BEFORE the IB
ALLOW_LOOSE = True                    # True: loose IB/OB (one equal-tick side) count as IB/OB
REGIME_END_MODE = 1                   # end a regime -> NEUTRAL when the confirmed LH/HL is broken:
#                                       1 = 1-tick break (intrabar) | 2 = 1 close beyond | 3 = 2 closes beyond
REGIME_END_MODE = int(os.environ.get("END_MODE", REGIME_END_MODE))
FLIP_BAR_NOT_OB = True                # True: a regime-end (flip) bar may NOT be an outside bar
STRUCTURE_ONLY = bool(int(os.environ.get("STRUCT_ONLY", "0")))  # hide entries; show only structure+regime
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT))
import massive

b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
all_days = sorted(b["Date"].unique())

if len(sys.argv) > 1:
    DAY = sys.argv[1] if sys.argv[1] != "rand" else None
else:
    DAY = "2026-06-09"

if DAY is not None:
    g = b[b["Date"] == DAY].sort_values("DateTime").reset_index(drop=True)
    tk = massive.load_continuous_ticks(date.fromisoformat(DAY)).sort_values("DateTime")
else:
    random.seed()
    cand = [dd for dd in all_days if 20 < (b["Date"] == dd).sum() < 200]
    tk = None
    while cand:
        DAY = random.choice(cand); cand.remove(DAY)
        g = b[b["Date"] == DAY].sort_values("DateTime").reset_index(drop=True)
        try:
            tk = massive.load_continuous_ticks(date.fromisoformat(DAY)).sort_values("DateTime")
        except Exception:
            tk = None
        if tk is not None and len(tk) > 100:
            break
    print("RANDOM DAY:", DAY)

O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
n = len(g)
tP = tk["Price"].values
tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1

# ---- BO+FT machinery: IBS (close location) + ABR(10) --------------------------
rng = (H - L).astype(float)
IBS = np.where(rng > 0, (C - L) / np.maximum(rng, 1e-9) * 100.0, 50.0)
ABR10 = np.array([rng[max(0, i-10):i].mean() if i > 0 else rng[0] for i in range(n)])


def boft_up(i):
    """BO+FT up completing at bar i (i-1 = breakout bar, i = follow-through):
    two strong directional IBS bars, breakout bar breaks the prior high,
    >=1 of the two bars has above-average range (ABR10)."""
    if i < 2: return False
    bo, ft = i-1, i
    return (H[bo] > H[bo-1] and IBS[bo] >= 69 and IBS[ft] >= 69
            and (rng[bo] > ABR10[bo] or rng[ft] > ABR10[ft]))


def boft_dn(i):
    if i < 2: return False
    bo, ft = i-1, i
    return (L[bo] < L[bo-1] and IBS[bo] <= 31 and IBS[ft] <= 31
            and (rng[bo] > ABR10[bo] or rng[ft] > ABR10[ft]))

# ---- bar classification vs a reference bar p (honours ALLOW_LOOSE) -----------
#   strict IB : inside both sides           strict OB : breaks both sides
#   loose  IB : one side ==tick, other in   loose  OB : one side ==tick, other out
#   both sides ==tick -> IB (rule: "it's an IB")
def btype(i, p):
    eqH = H[i] == H[p]; eqL = L[i] == L[p]
    inH = H[i] < H[p];  inL = L[i] > L[p]
    outH = H[i] > H[p]; outL = L[i] < L[p]
    if inH and inL:            return "IB"
    if outH and outL:          return "OB"
    if eqH and eqL:            return "IB"          # both equal -> IB
    if ALLOW_LOOSE:
        if (eqH and inL) or (eqL and inH):   return "IB"   # loose IB (mDT / mDB)
        if (eqH and outL) or (eqL and outH): return "OB"   # loose OB (mDT / mDB)
    return "N"

# ---- IB collapse: is_ib[i] + prev[i] (effective prior bar) --------------------
is_ib = np.zeros(n, dtype=bool)
prev = np.zeros(n, dtype=int)
if IGNORE_IB:
    _ref = 0
    for i in range(1, n):
        if btype(i, _ref) == "IB":
            is_ib[i] = True; prev[i] = _ref            # inside the reference bar
        else:
            prev[i] = _ref; _ref = i
else:
    for i in range(1, n):
        prev[i] = i - 1
        is_ib[i] = btype(i, i-1) == "IB"

# ---- ii / ioi breakout-mode detection ----------------------------------------
#   ii : two inside bars in a row  -> entry ref = the bar BEFORE the ii (mother)
#   ioi: inside, outside, inside   -> entry ref = the OB inside the ioi (middle)
def _ib(j): return 1 <= j and btype(j, j-1) == "IB"
def _ob(j): return 1 <= j and btype(j, j-1) == "OB"

bo = {}                               # completion_bar -> (kind, ref_bar, [outline bars]) — labels only
for i in range(2, n):
    if _ib(i) and _ib(i-1):
        bo[i] = ("ii", i-2, [i-1, i])
for i in range(3, n):
    if _ib(i) and _ob(i-1) and _ib(i-2):
        bo[i] = ("ioi", i-1, [i-2, i-1, i])       # ioi wins over ii on the same bar
print("ii/ioi patterns (completion_bar -> kind, ref_bar, bars):", bo)


def tick_slice(i):
    a = np.searchsorted(tbar, i, "left"); z = np.searchsorted(tbar, i, "right")
    return tP[a:z]


def ob_continue_first(i, up):
    p = prev[i]; s = tick_slice(i)
    if up:
        cont = np.nonzero(s > H[p])[0]; brk = np.nonzero(s < L[p])[0]
    else:
        cont = np.nonzero(s < L[p])[0]; brk = np.nonzero(s > H[p])[0]
    tc = cont[0] if len(cont) else np.inf
    tb = brk[0] if len(brk) else np.inf
    return tc < tb


def first_break(i):
    p = prev[i]; s = tick_slice(i)
    up = np.nonzero(s > H[p])[0]; dn = np.nonzero(s < L[p])[0]
    tu = up[0] if len(up) else np.inf
    td = dn[0] if len(dn) else np.inf
    return "H" if tu < td else "L"


# ---- 1. legs -> pivots -------------------------------------------------------
piv = []
d = 1 if H[1] >= H[0] else -1
ext_i = 0; pj = 0
for i in range(1, n):
    if is_ib[i]:
        continue                                    # IB: ignored
    p = prev[i]
    if btype(i, p) == "OB":                         # OB (vs effective prior; incl. loose)
        up = (d == 1); cf = ob_continue_first(i, up)
        if up:
            if cf:
                if H[i] >= H[ext_i]: ext_i = i
                piv.append((ext_i, H[ext_i], "H", i)); d = -1; ext_i = i
            else:
                piv.append((ext_i, H[ext_i], "H", i)); piv.append((i, L[i], "L", i))
                d = 1; ext_i = i
        else:
            if cf:
                if L[i] <= L[ext_i]: ext_i = i
                piv.append((ext_i, L[ext_i], "L", i)); d = 1; ext_i = i
            else:
                piv.append((ext_i, L[ext_i], "L", i)); piv.append((i, H[i], "H", i))
                d = -1; ext_i = i
        pj = i; continue
    if d == 1:
        if H[i] >= H[ext_i]: ext_i = i
        if L[i] < L[pj]:
            piv.append((ext_i, H[ext_i], "H", i)); d = -1; ext_i = i
    else:
        if L[i] <= L[ext_i]: ext_i = i
        if H[i] > H[pj]:
            piv.append((ext_i, L[ext_i], "L", i)); d = 1; ext_i = i
    pj = i
piv.append((ext_i, H[ext_i] if d == 1 else L[ext_i], "H" if d == 1 else "L", n-1))
piv_at_conf = {}
for (pb, prc, typ, cb) in piv:
    piv_at_conf.setdefault(cb, []).append((pb, prc, typ))

# ---- 2. structure labels -----------------------------------------------------
sw = [[idx, prc, typ, ""] for (idx, prc, typ, cb) in piv]
events = []
refH = refL = None
for k, (idx, prc, typ, _) in enumerate(sw):
    if typ == "L":
        if refL is None:
            refL = prc
        elif prc < refL:
            sw[k][3] = "LL"; refL = prc
            lows = [j for j, s in enumerate(sw[:k]) if s[2] == "L"]
            j0 = lows[-1] if lows else -1
            seg = [s for s in sw[j0+1:k] if s[2] == "H"]
            if seg:
                lh = max(seg, key=lambda s: s[1])
                if not lh[3] and (refH is None or lh[1] < refH):
                    lh[3] = "LH"; refH = lh[1]
                    events.append((idx, "LL", lh[0], lh[1]))
    else:
        if refH is None:
            refH = prc
        elif prc > refH:
            sw[k][3] = "HH"; refH = prc
            highs = [j for j, s in enumerate(sw[:k]) if s[2] == "H"]
            j0 = highs[-1] if highs else -1
            seg = [s for s in sw[j0+1:k] if s[2] == "L"]
            if seg:
                hl = min(seg, key=lambda s: s[1])
                if not hl[3] and (refL is None or hl[1] > refL):
                    hl[3] = "HL"; refL = hl[1]
                    events.append((idx, "HH", hl[0], hl[1]))
sw = [tuple(s) for s in sw]
if os.environ.get("DBG"):
    lo, hi = (int(x) for x in os.environ["DBG"].split(","))
    print("PIVOTS/LABELS in range:",
          [(idx, round(prc, 2), typ, lbl or "-") for (idx, prc, typ, lbl) in sw if lo <= idx <= hi])
ev_by_bar = {}
for e in events:
    ev_by_bar.setdefault(e[0], []).append(e)

# ---- 3. ONE PASS: regime + both entry trackers -------------------------------
regime = 0
reg = np.zeros(n, dtype=int)
conf_LH = conf_HL = None
end_cnt = 0                           # closes-beyond counter for REGIME_END_MODE 3
opened = False                        # first regime set by the OPEN (first entry / structure)
# --- arm -> confirm FLIP state (only after a regime has ended into neutral) ---
armed_bull = armed_bear = False; arm_bar = None
last_sh = last_sl = None
rev_sh = rev_sh_bar = rev_ref_lo = None
rev_sl = rev_sl_bar = rev_ref_hi = None
switches = []
sigS = {1: [], 2: [], 3: []}; ecS = 0; refS = None; refSbar = None; orgS = None
sigL = {1: [], 2: [], 3: []}; ecL = 0; refL = None; refLbar = None; orgL = None
ent_dbgS = []; ent_dbgL = []
bo_kind_bar = {}                       # ref_bar -> "ii"/"ioi" (for labeling the entry)

def clear_S():
    global ecS, refS, refSbar, orgS
    ecS = 0; refS = None; refSbar = None; orgS = None

def clear_L():
    global ecL, refL, refLbar, orgL
    ecL = 0; refL = None; refLbar = None; orgL = None

for i in range(n):
    es_fired = el_fired = False                        # did a short/long entry trigger this bar
    for (ebar, kind, lb, lp) in ev_by_bar.get(i, []):
        if kind == "LL":
            conf_LH = (lb, lp)
            if regime == 0 and not opened:                # OPEN only (structure fallback)
                regime = -1; opened = True; switches.append((i, "BEAR", lb, lp, "structure")); clear_L(); ecS = 0
        else:
            conf_HL = (lb, lp)
            if regime == 0 and not opened:
                regime = 1; opened = True; switches.append((i, "BULL", lb, lp, "structure")); clear_S(); ecL = 0

    # track swing pivots causally; after arming, capture the post-arm reversal swing
    for (pb, prc, typ) in piv_at_conf.get(i, []):
        if typ == "H":
            if armed_bull and arm_bar is not None and pb > arm_bar and rev_sh is None:
                rev_sh = prc; rev_sh_bar = pb; rev_ref_lo = last_sl
            last_sh = prc
        else:
            if armed_bear and arm_bar is not None and pb > arm_bar and rev_sl is None:
                rev_sl = prc; rev_sl_bar = pb; rev_ref_hi = last_sh
            last_sl = prc

    # ---- INSIDE-BAR TRIANGLE arming: reference = the bar BEFORE the IB --------
    #   prev[i] = last non-IB bar, so single-IB -> mother, ii -> bar before pair,
    #   ioi -> the outside bar. Regime-directional (rule 1). IB itself can't
    #   trigger (its extreme is inside the reference); a later non-IB bar breaks it.
    if i >= 1 and is_ib[i]:
        p = prev[i]
        tag = bo[i][0] if i in bo else "ib"
        if regime <= 0:
            if orgS is None: orgS = L[p]
            refS = L[p]; refSbar = p; bo_kind_bar[p] = tag
        if regime >= 0:
            if orgL is None: orgL = H[p]
            refL = H[p]; refLbar = p; bo_kind_bar[p] = tag

    if i >= 1 and not is_ib[i]:                       # triggers/arming on non-IB bars
        p = prev[i]
        is_ob = btype(i, p) == "OB"
        # ---- SHORT tracker (active in neutral + bear) ----
        if regime == 1:
            clear_S()
        else:
            if refS is not None and L[i] < refS - TICK/2:
                ecS += 1; es_fired = True
                sigS[min(ecS, 3)].append(refSbar)
                ent_dbgS.append((f"{min(ecS,3)}ES", refSbar, L[refSbar], i, refS - TICK))
                if regime == 0 and not opened:                          # OPEN only
                    regime = -1; opened = True
                    switches.append((i, "BEAR", refSbar, refS, "first entry (1ES)"))
                    clear_L(); ecS = 0
                refS = None; refSbar = None
                if is_ob and H[i] > H[p]:
                    refS = L[i]; refSbar = i
                if orgS is not None and L[i] < orgS - TICK/2:
                    ecS = 0; orgS = None
            elif orgS is not None and L[i] < orgS - TICK/2:
                ecS = 0; orgS = None
            if regime <= 0:
                if is_ob:
                    if orgS is None: orgS = L[i]
                    refS = L[i]; refSbar = i
                elif H[i] > H[p] or L[i] >= L[p] - TICK/2:
                    if refS is None and orgS is None: orgS = L[p]
                    refS = L[i]; refSbar = i
        # ---- LONG tracker (active in neutral + bull) ----
        if regime == -1:
            clear_L()
        else:
            if refL is not None and H[i] > refL + TICK/2:
                ecL += 1; el_fired = True
                sigL[min(ecL, 3)].append(refLbar)
                ent_dbgL.append((f"{min(ecL,3)}EL", refLbar, H[refLbar], i, refL + TICK))
                if regime == 0 and not opened:                          # OPEN only
                    regime = 1; opened = True
                    switches.append((i, "BULL", refLbar, refL, "first entry (1EL)"))
                    clear_S(); ecL = 0
                refL = None; refLbar = None
                if is_ob and L[i] < L[p]:
                    refL = H[i]; refLbar = i
                if orgL is not None and H[i] > orgL + TICK/2:
                    ecL = 0; orgL = None
            elif orgL is not None and H[i] > orgL + TICK/2:
                ecL = 0; orgL = None
            if regime >= 0:
                if is_ob:
                    if orgL is None: orgL = H[i]
                    refL = H[i]; refLbar = i
                elif L[i] < L[p] or H[i] <= H[p] + TICK/2:
                    if refL is None and orgL is None: orgL = H[p]
                    refL = H[i]; refLbar = i

    # ---- END OF REGIME -> NEUTRAL (does NOT flip to opposite) ----------------
    _txt = {1: "1t break", 2: "close beyond", 3: "2 closes"}[REGIME_END_MODE]
    flip_ok = not (FLIP_BAR_NOT_OB and i >= 1 and btype(i, prev[i]) == "OB")
    if regime == -1 and conf_LH is not None:
        lvl = conf_LH[1]
        if REGIME_END_MODE == 1:   broke = H[i] > lvl
        elif REGIME_END_MODE == 2: broke = C[i] > lvl
        else:
            end_cnt = end_cnt + 1 if C[i] > lvl else 0; broke = end_cnt >= 2
        if broke and flip_ok:
            switches.append((i, "NEUTRAL", conf_LH[0], lvl, f"bear end - {_txt}>LH"))
            regime = 0; conf_LH = None; end_cnt = 0; clear_S(); clear_L()
            armed_bull = True; armed_bear = False; arm_bar = i
            rev_sh = rev_sh_bar = rev_ref_lo = None
    elif regime == 1 and conf_HL is not None:
        lvl = conf_HL[1]
        if REGIME_END_MODE == 1:   broke = L[i] < lvl
        elif REGIME_END_MODE == 2: broke = C[i] < lvl
        else:
            end_cnt = end_cnt + 1 if C[i] < lvl else 0; broke = end_cnt >= 2
        if broke and flip_ok:
            switches.append((i, "NEUTRAL", conf_HL[0], lvl, f"bull end - {_txt}<HL"))
            regime = 0; conf_HL = None; end_cnt = 0; clear_S(); clear_L()
            armed_bear = True; armed_bull = False; arm_bar = i
            rev_sl = rev_sl_bar = rev_ref_hi = None

    # ---- FAILED-FLIP REVERT: counter-direction entry while armed -> original --
    if armed_bull and es_fired:                        # tried bull, a 1ES fired -> back to BEAR
        regime = -1; armed_bull = False; rev_sh = rev_sh_bar = rev_ref_lo = None
        switches.append((i, "BEAR", i, L[i], "revert: failed flip (1ES)"))
    elif armed_bear and el_fired:                       # tried bear, a 1EL fired -> back to BULL
        regime = 1; armed_bear = False; rev_sl = rev_sl_bar = rev_ref_hi = None
        switches.append((i, "BULL", i, H[i], "revert: failed flip (1EL)"))

    # ---- FLIP via BO+FT (runaway, no pullback needed) ------------------------
    if armed_bull and boft_up(i):
        regime = 1; armed_bull = False; rev_sh = rev_sh_bar = rev_ref_lo = None
        switches.append((i, "BULL", i-1, H[i-1], "flip BO+FT")); clear_S(); ecL = 0
    elif armed_bear and boft_dn(i):
        regime = -1; armed_bear = False; rev_sl = rev_sl_bar = rev_ref_hi = None
        switches.append((i, "BEAR", i-1, L[i-1], "flip BO+FT")); clear_L(); ecS = 0

    # ---- FLIP via pullback: post-arm swing high broken + higher-low ----------
    if armed_bull and rev_sh is not None and rev_ref_lo is not None:
        if H[i] > rev_sh and L[rev_sh_bar:i+1].min() > rev_ref_lo:
            regime = 1; armed_bull = False
            switches.append((i, "BULL", rev_sh_bar, rev_sh, "flip HL+breakHH"))
            clear_S(); ecL = 0
    elif armed_bear and rev_sl is not None and rev_ref_hi is not None:
        if L[i] < rev_sl and H[rev_sl_bar:i+1].max() < rev_ref_hi:
            regime = -1; armed_bear = False
            switches.append((i, "BEAR", rev_sl_bar, rev_sl, "flip LH+breakLL"))
            clear_L(); ecS = 0
    reg[i] = regime

loose_ib = [i for i in range(1, n) if is_ib[i] and not (H[i] < H[prev[i]] and L[i] > L[prev[i]])]
loose_ob = [i for i in range(1, n) if btype(i, prev[i]) == "OB"
            and not (H[i] > H[prev[i]] and L[i] < L[prev[i]])]
print(f"IGNORE_IB = {IGNORE_IB}   ALLOW_LOOSE = {ALLOW_LOOSE}   day = {DAY}   #IB = {int(is_ib.sum())}")
print(f"loose IB bars: {loose_ib}   loose OB bars: {loose_ob}")
print("switches:", [(s[0], s[1], f"{s[4]} @bar{s[2]} {s[3]:.2f}") for s in switches])
print("1ES:", sigS[1]); print("2ES:", sigS[2]); print("3ES-w:", sigS[3])
print("1EL:", sigL[1]); print("2EL:", sigL[2]); print("3EL-w:", sigL[3])
print("\nSHORT arm->trigger  (tag, arm_bar, arm_low, trigger_bar, entry_px) [BO]:")
for r in ent_dbgS:
    print("  ", r, "  BO:", bo_kind_bar.get(r[1], ""))
print("LONG arm->trigger [BO]:")
for r in ent_dbgL:
    print("  ", r, "  BO:", bo_kind_bar.get(r[1], ""))

# ---- 4. chart -----------------------------------------------------------------
fig, ax = plt.subplots(figsize=(26, 12))
i0 = 0
for i in range(1, n + 1):
    if i == n or reg[i] != reg[i0]:
        colr = "#ffe5e5" if reg[i0] == -1 else ("#e3f4e3" if reg[i0] == 1 else "#f0f0f0")
        ax.axvspan(i0 - 0.5, i - 0.5, color=colr, alpha=0.6, zorder=0)
        i0 = i
ob_fb = []
for i in range(n):
    col = "#26a69a" if C[i] >= O[i] else "#ef5350"
    ax.plot([i, i], [L[i], H[i]], color=col, lw=1.3, zorder=2)
    ax.add_patch(plt.Rectangle((i-0.34, min(O[i], C[i])), 0.68, max(abs(C[i]-O[i]), .02),
                               facecolor=col, edgecolor="black", lw=0.4, zorder=3))
    if STRUCTURE_ONLY:
        pass
    elif is_ib[i]:
        p = prev[i]; strict = (H[i] < H[p] and L[i] > L[p])
        ax.text(i, H[i]+1, "IB" if strict else "ibℓ", ha="center", fontsize=7, color="purple")
    elif i > 0 and btype(i, prev[i]) == "OB":
        p = prev[i]; strict = (H[i] > H[p] and L[i] < L[p])
        ax.text(i, H[i]+1, "OB" if strict else "obℓ", ha="center", fontsize=7,
                color="darkorange", fontweight="bold")
        side = first_break(i); ob_fb.append((i, side))
xs = [p[0] for p in piv]; ys = [p[1] for p in piv]
ax.plot(xs, ys, color="steelblue", lw=0.9, ls=":", marker="o", ms=3.5, alpha=0.55, zorder=6)
lab_seq = {"LH": 0, "LL": 0, "HH": 0, "HL": 0}
prev_r = None
for (idx, prc, typ, lbl) in sw:
    if not lbl:
        continue
    r = reg[idx]
    if r != prev_r:
        lab_seq = {"LH": 0, "LL": 0, "HH": 0, "HL": 0}
        prev_r = r
    lab_seq[lbl] += 1
    dy = 2.2 if typ == "H" else -2.2
    ax.text(idx, prc + dy, f"{lbl}{lab_seq[lbl]}", ha="center",
            va="bottom" if typ == "H" else "top", fontsize=8, fontweight="bold",
            color="darkgreen" if lbl in ("HH", "HL") else "darkred", zorder=7)
off2 = 0.06 * (H.max() - L.min())
for (si, tag, lb, lp, why) in switches:
    col = {"BULL": "green", "BEAR": "red", "NEUTRAL": "gray"}[tag]
    ax.plot([lb, si], [lp, lp], color=col, lw=1.8, ls="-.", zorder=6)
    ax.text((lb+si)/2, lp + 1.2, f"{why} {lp:.2f}", ha="center", fontsize=8,
            color=col, fontweight="bold")
    y0 = L[si] - off2 if tag == "BULL" else H[si] + off2
    y1 = L[si] - off2*0.35 if tag == "BULL" else H[si] + off2*0.35
    ax.annotate("", xy=(si, y1), xytext=(si, y0),
                arrowprops=dict(arrowstyle="-|>", color=col, lw=3))
    ax.text(si, y0 + (-off2*0.15 if tag == "BULL" else off2*0.15),
            f"REGIME→{tag}", ha="center", va="top" if tag == "BULL" else "bottom",
            fontsize=9, fontweight="bold", color=col)
off = 0.10 * (H.max() - L.min())
for si, col, lbl in ([] if STRUCTURE_ONLY else
                     ([(x, "darkorange", "1ES") for x in sigS[1]] +
                      [(x, "red", "2ES") for x in sigS[2]] +
                      [(x, "purple", "3ES-w") for x in sigS[3]])):
    ax.annotate("", xy=(si, H[si] + off*0.45), xytext=(si, H[si] + off),
                arrowprops=dict(arrowstyle="-|>", color=col, lw=2.5))
    ax.text(si, H[si] + off*1.08, lbl, ha="center", fontsize=8, color=col, fontweight="bold")
for si, col, lbl in ([] if STRUCTURE_ONLY else
                     ([(x, "#4caf50", "1EL") for x in sigL[1]] +
                      [(x, "darkgreen", "2EL") for x in sigL[2]] +
                      [(x, "purple", "3EL-w") for x in sigL[3]])):
    ax.annotate("", xy=(si, L[si] - off*0.45), xytext=(si, L[si] - off),
                arrowprops=dict(arrowstyle="-|>", color=col, lw=2.5))
    ax.text(si, L[si] - off*1.08, lbl, ha="center", va="top", fontsize=8, color=col, fontweight="bold")
for (i, side) in ([] if STRUCTURE_ONLY else ob_fb):
    if side == "H":
        ax.annotate("", xy=(i, H[i]+off*0.30), xytext=(i, H[i]+off*0.62),
                    arrowprops=dict(arrowstyle="-|>", color="green", lw=2.6), zorder=9)
        ax.text(i, H[i]+off*0.66, "H1st", ha="center", va="bottom",
                fontsize=7.5, color="green", fontweight="bold", zorder=9)
    else:
        ax.annotate("", xy=(i, L[i]-off*0.30), xytext=(i, L[i]-off*0.62),
                    arrowprops=dict(arrowstyle="-|>", color="red", lw=2.6), zorder=9)
        ax.text(i, L[i]-off*0.66, "L1st", ha="center", va="top",
                fontsize=7.5, color="red", fontweight="bold", zorder=9)

# ---- TRIANGLE boxes: reference bar (mother / OB) through the inside bar[s] ----
#   single IB -> tan box (no text); ii -> gold+label; ioi -> blue+label.
i = 1
while (not STRUCTURE_ONLY) and i < n:
    if is_ib[i]:
        rs = i
        while i < n and is_ib[i]:
            i += 1
        re_ = i - 1
        ref = prev[rs]
        if _ob(ref):
            kind, ec = "ioi", "royalblue"
        elif re_ - rs + 1 >= 2:
            kind, ec = "ii", "goldenrod"
        else:
            kind, ec = "ib", "tan"
        bars = list(range(ref, re_ + 1))
        x0 = min(bars) - 0.46; x1 = max(bars) + 0.46
        ylo = min(L[bb] for bb in bars); yhi = max(H[bb] for bb in bars)
        ax.add_patch(plt.Rectangle((x0, ylo - 0.5), x1 - x0, (yhi - ylo) + 1.0, fill=False,
                                   edgecolor=ec, lw=2.0, zorder=8))
        if kind != "ib":
            ax.text((x0 + x1) / 2, yhi + 0.8, kind, ha="center", va="bottom",
                    fontsize=8.5, color=ec, fontweight="bold", zorder=9)
    else:
        i += 1

print("OB first-break:", ob_fb)
ax.set_xticks(range(0, n, 2)); ax.set_xticklabels([str(i) for i in range(0, n, 2)], fontsize=7)
ax.grid(alpha=0.25, lw=0.5)
if STRUCTURE_ONLY:
    _md = {1: "1t break", 2: "1 close beyond", 3: "2 closes beyond"}[REGIME_END_MODE]
    ax.set_title(f"{DAY} — STRUCTURE + REGIME only — end mode {REGIME_END_MODE} ({_md}); "
                 f"gray = neutral transition, flip = first new HH/LL after neutral",
                 fontsize=13, fontweight="bold")
else:
    ax.set_title(f"{DAY} — Brooks entry engine — inside-bar TRIANGLE entries "
                 f"(arm off bar before IB); ii=gold box, ioi=blue box", fontsize=13, fontweight="bold")
fig.tight_layout()
_suffix = f"structmode{REGIME_END_MODE}" if STRUCTURE_ONLY else f"endmode{REGIME_END_MODE}"
out = ROOT / "docs" / "living" / f"legs_engine_{DAY.replace('-','')}_{_suffix}.png"
fig.savefig(out, dpi=115)
print("saved", out)
