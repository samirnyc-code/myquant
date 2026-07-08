"""Scheme A regime engine — label the whole day by LOCAL structure.

STRUCTURE (relative labels vs the previous SAME-TYPE swing pivot):
  swing high > prev high  -> HH        swing high < prev high -> LH
  swing low  > prev low   -> HL        swing low  < prev low  -> LL
FLIP (neutral -> trend):
  BULL when 2 higher-lows AND 2 higher-highs since the anchor low
        (HH #2 counts the first BAR that breaks HH#1's high -> "running break")
  BEAR mirror: 2 lower-highs AND 2 lower-lows.
END (trend -> neutral), REGIME_END_MODE = 1 (1-tick break):
  BULL ends when price trades 1t below the last confirmed higher-low (HL).
  BEAR ends when price trades 1t above the last confirmed lower-high (LH).
Legs: strict 1t-break, inside bars ignored, outside bars tick-resolved.
"""
import sys
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25
END_MODE = 1
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT))
import massive

DAY = sys.argv[1] if len(sys.argv) > 1 else "2026-06-09"
b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
g = b[b["Date"] == DAY].sort_values("DateTime").reset_index(drop=True)
O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
n = len(g)
tk = massive.load_continuous_ticks(date.fromisoformat(DAY)).sort_values("DateTime")
tP = tk["Price"].values
tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1


def tick_slice(i):
    a = np.searchsorted(tbar, i, "left"); z = np.searchsorted(tbar, i, "right")
    return tP[a:z]


def ob_cont_first(i, up):
    s = tick_slice(i)
    if up: cont = np.nonzero(s > H[i-1])[0]; brk = np.nonzero(s < L[i-1])[0]
    else:  cont = np.nonzero(s < L[i-1])[0]; brk = np.nonzero(s > H[i-1])[0]
    tc = cont[0] if len(cont) else np.inf; tb = brk[0] if len(brk) else np.inf
    return tc < tb


# ---- 1. legs -> pivots (record confirmation bar) -----------------------------
piv = []                                # (pivot_bar, price, 'H'/'L', conf_bar)
d = 1 if H[1] >= H[0] else -1
ext_i = 0; pj = 0
for i in range(1, n):
    if H[i] < H[i-1] and L[i] > L[i-1]:
        continue
    if H[i] > H[i-1] and L[i] < L[i-1]:
        up = (d == 1); cf = ob_cont_first(i, up)
        if up:
            if cf:
                if H[i] >= H[ext_i]: ext_i = i
                piv.append((ext_i, H[ext_i], "H", i)); d = -1; ext_i = i
            else:
                piv.append((ext_i, H[ext_i], "H", i)); piv.append((i, L[i], "L", i)); d = 1; ext_i = i
        else:
            if cf:
                if L[i] <= L[ext_i]: ext_i = i
                piv.append((ext_i, L[ext_i], "L", i)); d = 1; ext_i = i
            else:
                piv.append((ext_i, L[ext_i], "L", i)); piv.append((i, H[i], "H", i)); d = -1; ext_i = i
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

# ---- 2. DIRECT-TRAVEL labels (engine rule: HH/HL/LL/LH vs last LABELED extreme)
sw = [[pb, prc, typ, ""] for (pb, prc, typ, cb) in piv]
refH = refL = None
for k, (idx, prc, typ, _) in enumerate(sw):
    if typ == "L":
        if refL is None:
            refL = prc
        elif prc < refL:
            sw[k][3] = "LL"; refL = prc
            lows = [j for j, s in enumerate(sw[:k]) if s[2] == "L"]; j0 = lows[-1] if lows else -1
            seg = [s for s in sw[j0+1:k] if s[2] == "H"]
            if seg:
                lh = max(seg, key=lambda s: s[1])
                if not lh[3] and (refH is None or lh[1] < refH):
                    lh[3] = "LH"; refH = lh[1]
    else:
        if refH is None:
            refH = prc
        elif prc > refH:
            sw[k][3] = "HH"; refH = prc
            highs = [j for j, s in enumerate(sw[:k]) if s[2] == "H"]; j0 = highs[-1] if highs else -1
            seg = [s for s in sw[j0+1:k] if s[2] == "L"]
            if seg:
                hl = min(seg, key=lambda s: s[1])
                if not hl[3] and (refL is None or hl[1] > refL):
                    hl[3] = "HL"; refL = hl[1]
labels = {(pb, typ): (prc, lab) for (pb, prc, typ, lab) in sw if lab}
lab_at = {}
for (pb, prc, typ, lab) in sw:
    if lab:
        lab_at.setdefault(pb, []).append((typ, prc, lab))

# ---- 3. regime state machine ------------------------------------------------
# OPEN: first regime set simply on the first structure label (handled separately).
# FLIP (only after open): regime level (last LH / HL) broken -> NEUTRAL (armed);
#   then bear->bull needs a higher-low AND a break of the swing high; mirror for bull->bear.
piv_at_conf = {}
for (pb, prc, typ, cb) in piv:
    piv_at_conf.setdefault(cb, []).append((pb, prc, typ))

reg = np.zeros(n, dtype=int); regime = 0
opened = False
switches = []                           # (bar, tag, why)
level_lines = []                        # (level_bar, break_bar, price, side) broken LH/HL line
last_sh = last_sl = None                # last swing-high / swing-low pivot price
last_LH = last_HL = None                # most recent labeled LH / HL (= the regime level)
last_LH_bar = last_HL_bar = None
armed_bull = armed_bear = False; arm_bar = None
# the post-arm reversal swing to break + its reference pullback extreme
rev_sh = rev_sh_bar = rev_ref_lo = None
rev_sl = rev_sl_bar = rev_ref_hi = None

for i in range(n):
    for (typ, prc, lab) in lab_at.get(i, []):
        if lab == "LH": last_LH = prc; last_LH_bar = i
        elif lab == "HL": last_HL = prc; last_HL_bar = i
        if not opened and regime == 0:                    # OPEN — left alone
            if lab == "LL":
                regime = -1; opened = True; switches.append((i, "BEAR", "open"))
            elif lab == "HH":
                regime = 1; opened = True; switches.append((i, "BULL", "open"))
    for (pb, prc, typ) in piv_at_conf.get(i, []):
        if typ == "H":
            # first swing HIGH to form after arming = the high to break; its prior swing low = ref
            if armed_bull and arm_bar is not None and pb > arm_bar and rev_sh is None:
                rev_sh = prc; rev_sh_bar = pb; rev_ref_lo = last_sl
            last_sh = prc
        else:
            if armed_bear and arm_bar is not None and pb > arm_bar and rev_sl is None:
                rev_sl = prc; rev_sl_bar = pb; rev_ref_hi = last_sh
            last_sl = prc

    # ARM: regime price level broken (1t) -> NEUTRAL; draw a line from that LH/HL to here
    if regime == -1 and last_LH is not None and H[i] > last_LH:
        regime = 0; armed_bull = True; armed_bear = False; arm_bar = i
        rev_sh = rev_sh_bar = rev_ref_lo = None
        switches.append((i, "NEUTRAL", "bear end")); level_lines.append((last_LH_bar, i, last_LH, "bear"))
    elif regime == 1 and last_HL is not None and L[i] < last_HL:
        regime = 0; armed_bear = True; armed_bull = False; arm_bar = i
        rev_sl = rev_sl_bar = rev_ref_hi = None
        switches.append((i, "NEUTRAL", "bull end")); level_lines.append((last_HL_bar, i, last_HL, "bull"))

    # FLIP bear->bull: post-arm swing high (=> a pullback happened) broken, pullback low is a higher low
    if armed_bull and rev_sh is not None and rev_ref_lo is not None:
        if H[i] > rev_sh and L[rev_sh_bar:i+1].min() > rev_ref_lo:
            regime = 1; armed_bull = False; switches.append((i, "BULL", "flip"))
    elif armed_bear and rev_sl is not None and rev_ref_hi is not None:
        if L[i] < rev_sl and H[rev_sl_bar:i+1].max() < rev_ref_hi:
            regime = -1; armed_bear = False; switches.append((i, "BEAR", "flip"))
    reg[i] = regime

print("switches:", switches)

# ---- 4. chart ----------------------------------------------------------------
fig, ax = plt.subplots(figsize=(26, 12))
i0 = 0
for i in range(1, n + 1):
    if i == n or reg[i] != reg[i0]:
        colr = "#ffe5e5" if reg[i0] == -1 else ("#e3f4e3" if reg[i0] == 1 else "#f0f0f0")
        ax.axvspan(i0 - 0.5, i - 0.5, color=colr, alpha=0.6, zorder=0)
        i0 = i
for i in range(n):
    col = "#26a69a" if C[i] >= O[i] else "#ef5350"
    ax.plot([i, i], [L[i], H[i]], color=col, lw=1.3, zorder=2)
    ax.add_patch(plt.Rectangle((i-0.34, min(O[i], C[i])), 0.68, max(abs(C[i]-O[i]), .02),
                               facecolor=col, edgecolor="black", lw=0.4, zorder=3))
xs = [p[0] for p in piv]; ys = [p[1] for p in piv]
ax.plot(xs, ys, color="steelblue", lw=0.9, ls=":", marker="o", ms=3, alpha=0.5, zorder=5)
seq = {"HH": 0, "HL": 0, "LH": 0, "LL": 0}
for (pb, typ), (prc, lab) in sorted(labels.items(), key=lambda kv: kv[0][0]):
    if not lab: continue
    seq[lab] += 1
    dy = 2.2 if typ == "H" else -2.2
    ax.text(pb, prc + dy, f"{lab}{seq[lab]}", ha="center", va="bottom" if typ == "H" else "top",
            fontsize=8, fontweight="bold",
            color="darkgreen" if lab in ("HH", "HL") else "darkred", zorder=7)
# the broken LH/HL: dashed line from the level's pivot bar to where price breaks it
for (b0, b1, lvl, side) in level_lines:
    c = "red" if side == "bear" else "green"
    ax.plot([b0, b1], [lvl, lvl], color=c, ls="--", lw=1.6, zorder=6)
ax.set_xticks(range(0, n, 2)); ax.set_xticklabels(range(0, n, 2), fontsize=7)
ax.grid(alpha=0.25)
ax.set_title(f"{DAY} — Scheme A flips (dashed line = broken LH/HL); shading = regime",
             fontsize=13, fontweight="bold")
fig.tight_layout()
out = ROOT / "docs" / "living" / f"schemeA_{DAY.replace('-','')}.png"
fig.savefig(out, dpi=115); print("saved", out)
