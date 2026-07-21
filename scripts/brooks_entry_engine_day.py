"""Brooks entry engine — canonical version of everything locked this session.

LEGS:      strict 1t-break; IBs (vs immediate prior bar) ignored; OBs tick-resolved
           (cont-first = real reversal pivot; break-first = trap, leg continues).
STRUCTURE: LH exists only when price travels from that swing high DIRECTLY to a
           new LL (retro-labeled: highest swing high since previous swing low,
           assigned when the LL prints). HL mirrored. Only labeled swings carry
           sequential numbers, reset per regime.
REGIME:    NEUTRAL at open; both entry sides counted while neutral.
           ADOPTION: the FIRST ENTRY THAT TRIGGERS sets the regime (user rule),
           and adoption resets the counter (the defining entry keeps its mark).
           Fallback: first structure confirmation adopts if no entry has fired.
           FLIPS: bear->bull on a CLOSE above the confirmed LH; mirrored.
           On any regime change: opposing side state cleared, own count reset.
ENTRIES:   pullback bar = higher-high OR higher/equal low (micro-DB) [shorts;
           mirrored for longs]; its low = low-to-break; entry when a later bar
           ticks 1t below it -> count+1 (1ES/2ES/3ES=wedge). ORIGIN = swing base
           the pullback bounced from; count resets when origin is taken out.
           OBs: break-first fills the pending entry and re-arms off the OB
           (its low = next low-to-break, count continues).
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
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
import massive

DAY = "2026-06-09"
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


def ob_continue_first(i, up):
    s = tick_slice(i)
    if up:
        cont = np.nonzero(s > H[i-1])[0]; brk = np.nonzero(s < L[i-1])[0]
    else:
        cont = np.nonzero(s < L[i-1])[0]; brk = np.nonzero(s > H[i-1])[0]
    tc = cont[0] if len(cont) else np.inf
    tb = brk[0] if len(brk) else np.inf
    return tc < tb


# ---- 1. legs -> pivots -------------------------------------------------------
piv = []
d = 1 if H[1] >= H[0] else -1
ext_i = 0; pj = 0
ob_notes = []
for i in range(1, n):
    if H[i] < H[i-1] and L[i] > L[i-1]:
        continue                                    # IB: ignored
    if H[i] > H[i-1] and L[i] < L[i-1]:             # OB: tick-resolved
        up = (d == 1); cf = ob_continue_first(i, up)
        if up:
            if cf:
                if H[i] >= H[ext_i]: ext_i = i
                piv.append((ext_i, H[ext_i], "H")); d = -1; ext_i = i
            else:
                piv.append((ext_i, H[ext_i], "H")); piv.append((i, L[i], "L"))
                d = 1; ext_i = i
        else:
            if cf:
                if L[i] <= L[ext_i]: ext_i = i
                piv.append((ext_i, L[ext_i], "L")); d = 1; ext_i = i
            else:
                piv.append((ext_i, L[ext_i], "L")); piv.append((i, H[i], "H"))
                d = -1; ext_i = i
        ob_notes.append((i, "cont" if cf else "trap"))
        pj = i; continue
    if d == 1:
        if H[i] >= H[ext_i]: ext_i = i
        if L[i] < L[pj]:
            piv.append((ext_i, H[ext_i], "H")); d = -1; ext_i = i
    else:
        if L[i] <= L[ext_i]: ext_i = i
        if H[i] > H[pj]:
            piv.append((ext_i, L[ext_i], "L")); d = 1; ext_i = i
    pj = i
piv.append((ext_i, H[ext_i] if d == 1 else L[ext_i], "H" if d == 1 else "L"))

# ---- 2. structure labels (user's direct-travel rule) -------------------------
sw = [[idx, prc, typ, ""] for (idx, prc, typ) in piv]
events = []
refH = refL = None          # price of last LABELED (or seed) structural high / low
for k, (idx, prc, typ, _) in enumerate(sw):
    if typ == "L":
        if refL is None:
            refL = prc                      # seed: first swing low, unlabeled
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
            refH = prc                      # seed: first swing high, unlabeled
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
ev_by_bar = {}
for e in events:
    ev_by_bar.setdefault(e[0], []).append(e)

# ---- 3. ONE PASS: regime + both entry trackers --------------------------------
regime = 0
reg = np.zeros(n, dtype=int)
conf_LH = conf_HL = None
switches = []                       # (bar, tag, why_bar, why_price, why_txt)
sigS = {1: [], 2: [], 3: []}; ecS = 0; refS = None; refSbar = None; orgS = None
sigL = {1: [], 2: [], 3: []}; ecL = 0; refL = None; refLbar = None; orgL = None

def clear_S():
    global ecS, refS, refSbar, orgS
    ecS = 0; refS = None; refSbar = None; orgS = None

def clear_L():
    global ecL, refL, refLbar, orgL
    ecL = 0; refL = None; refLbar = None; orgL = None

for i in range(n):
    # structure confirmations known at this bar
    for (ebar, kind, lb, lp) in ev_by_bar.get(i, []):
        if kind == "LL":
            conf_LH = (lb, lp)
            if regime == 0:
                regime = -1; switches.append((i, "BEAR", lb, lp, "structure")); clear_L(); ecS = 0
        else:
            conf_HL = (lb, lp)
            if regime == 0:
                regime = 1; switches.append((i, "BULL", lb, lp, "structure")); clear_S(); ecL = 0

    if i >= 1:
        is_ob = H[i] > H[i-1] and L[i] < L[i-1]
        # ---- SHORT tracker (active in neutral + bear) ----
        if regime == 1:
            clear_S()
        else:
            if refS is not None and L[i] < refS - TICK/2:
                ecS += 1
                sigS[min(ecS, 3)].append(refSbar)
                if regime == 0:                      # FIRST TRIGGERED ENTRY -> adopt
                    regime = -1
                    switches.append((i, "BEAR", refSbar, refS, "first entry (1ES)"))
                    clear_L(); ecS = 0
                refS = None; refSbar = None
                if is_ob and H[i] > H[i-1]:
                    refS = L[i]; refSbar = i
                if orgS is not None and L[i] < orgS - TICK/2:
                    ecS = 0; orgS = None
            elif orgS is not None and L[i] < orgS - TICK/2:
                ecS = 0; orgS = None
            if regime <= 0:
                if is_ob:
                    if orgS is None: orgS = L[i]
                    refS = L[i]; refSbar = i
                elif H[i] > H[i-1] or L[i] >= L[i-1] - TICK/2:
                    if refS is None and orgS is None: orgS = L[i-1]
                    refS = L[i]; refSbar = i
        # ---- LONG tracker (active in neutral + bull) ----
        if regime == -1:
            clear_L()
        else:
            if refL is not None and H[i] > refL + TICK/2:
                ecL += 1
                sigL[min(ecL, 3)].append(refLbar)
                if regime == 0:
                    regime = 1
                    switches.append((i, "BULL", refLbar, refL, "first entry (1EL)"))
                    clear_S(); ecL = 0
                refL = None; refLbar = None
                if is_ob and L[i] < L[i-1]:
                    refL = H[i]; refLbar = i
                if orgL is not None and H[i] > orgL + TICK/2:
                    ecL = 0; orgL = None
            elif orgL is not None and H[i] > orgL + TICK/2:
                ecL = 0; orgL = None
            if regime >= 0:
                if is_ob:
                    if orgL is None: orgL = H[i]
                    refL = H[i]; refLbar = i
                elif L[i] < L[i-1] or H[i] <= H[i-1] + TICK/2:
                    if refL is None and orgL is None: orgL = H[i-1]
                    refL = H[i]; refLbar = i

    # regime flips on CLOSE through confirmed levels
    if regime == -1 and conf_LH is not None and C[i] > conf_LH[1]:
        regime = 1; switches.append((i, "BULL", conf_LH[0], conf_LH[1], "close>LH"))
        conf_LH = None; clear_S(); ecL = 0
    elif regime == 1 and conf_HL is not None and C[i] < conf_HL[1]:
        regime = -1; switches.append((i, "BEAR", conf_HL[0], conf_HL[1], "close<HL"))
        conf_HL = None; clear_L(); ecS = 0
    reg[i] = regime

print("switches:", [(s[0], s[1], f"{s[4]} @bar{s[2]} {s[3]:.2f}") for s in switches])
print("1ES:", sigS[1]); print("2ES:", sigS[2]); print("3ES-w:", sigS[3])
print("1EL:", sigL[1]); print("2EL:", sigL[2]); print("3EL-w:", sigL[3])

# ---- 4. chart -----------------------------------------------------------------
fig, ax = plt.subplots(figsize=(24, 12))
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
    if i > 0 and H[i] < H[i-1] and L[i] > L[i-1]:
        ax.text(i, H[i]+1, "IB", ha="center", fontsize=7, color="purple")
    if i > 0 and H[i] > H[i-1] and L[i] < L[i-1]:
        ax.text(i, H[i]+1, "OB", ha="center", fontsize=7, color="darkorange", fontweight="bold")
xs = [p[0] for p in piv]; ys = [p[1] for p in piv]
ax.plot(xs, ys, color="steelblue", lw=0.9, ls=":", marker="o", ms=3.5, alpha=0.55, zorder=6)
# per-label sequences (LH1, LH2... / LL1... / HH1... / HL1...), reset on regime change
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
    col = "green" if tag == "BULL" else "red"
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
for si, col, lbl in ([(x, "darkorange", "1ES") for x in sigS[1]] +
                     [(x, "red", "2ES") for x in sigS[2]] +
                     [(x, "purple", "3ES-w") for x in sigS[3]]):
    ax.annotate("", xy=(si, H[si] + off*0.45), xytext=(si, H[si] + off),
                arrowprops=dict(arrowstyle="-|>", color=col, lw=2.5))
    ax.text(si, H[si] + off*1.08, lbl, ha="center", fontsize=8, color=col, fontweight="bold")
for si, col, lbl in ([(x, "#4caf50", "1EL") for x in sigL[1]] +
                     [(x, "darkgreen", "2EL") for x in sigL[2]] +
                     [(x, "purple", "3EL-w") for x in sigL[3]]):
    ax.annotate("", xy=(si, L[si] - off*0.45), xytext=(si, L[si] - off),
                arrowprops=dict(arrowstyle="-|>", color=col, lw=2.5))
    ax.text(si, L[si] - off*1.08, lbl, ha="center", va="top", fontsize=8, color=col, fontweight="bold")
ax.set_xticks(range(0, n, 2)); ax.set_xticklabels([str(i) for i in range(0, n, 2)], fontsize=7)
ax.grid(alpha=0.25, lw=0.5)
ax.set_title(f"{DAY} — Brooks entry engine: first-triggered-entry regime adoption, "
             f"structure flips, 1ES/2ES/wedge both sides", fontsize=13, fontweight="bold")
fig.tight_layout(); fig.savefig(ROOT / "docs" / "living" / "legs_engine_20260609.png", dpi=110)
print("saved")
