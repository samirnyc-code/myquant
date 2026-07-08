"""Zoom the 2026-06-09 bottom reversal and show the TWO ways to count HH/HL
that define the bull flip, so we can pick one.

Scheme A (swing pivots + running break): HH1 = first higher swing-HIGH pivot,
          HH2 = first bar to break HH1's high; HL from swing-LOW pivots.
Scheme B (every new higher high): every bar making a new high-since-low = HH.
Both need 2 HH + 2 HL to flip.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(r"c:\Users\Admin\myquant")
b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
g = b[b["Date"] == "2026-06-09"].sort_values("DateTime").reset_index(drop=True)
O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])

LO, HI = 36, 50
LOWBAR = 38                                    # reversal low

# ----- Scheme A: swing pivots (from engine) + running break -------------------
# swing pivots in window: b39 H, b41 L, b43 H, b44 L
A = [(LOWBAR, "L", L[LOWBAR], "LOW", "black"),
     (41, "L", L[41], "HL1", "darkred"),
     (43, "H", H[43], "HH1", "darkgreen"),
     (44, "H", H[44], "HH2", "green"),
     (44, "L", L[44], "HL2", "red")]
FLIP_A = 44

# ----- Scheme B: every bar making a new high-since-low = HH -------------------
B = [(LOWBAR, "L", L[LOWBAR], "LOW", "black")]
run_hi = H[LOWBAR]; k = 0
for i in range(LOWBAR + 1, HI + 1):
    if H[i] > run_hi:
        k += 1; run_hi = H[i]
        B.append((i, "H", H[i], f"HH{k}", "green"))
# higher-low swing pivots
B += [(41, "L", L[41], "HL1", "darkred"), (44, "L", L[44], "HL2", "red")]
FLIP_B = 44


def candles(ax):
    for i in range(LO, HI + 1):
        col = "#26a69a" if C[i] >= O[i] else "#ef5350"
        ax.plot([i, i], [L[i], H[i]], color=col, lw=1.6, zorder=2)
        ax.add_patch(plt.Rectangle((i-0.34, min(O[i], C[i])), 0.68,
                     max(abs(C[i]-O[i]), .02), facecolor=col, edgecolor="black", lw=0.5, zorder=3))
    ax.set_xticks(range(LO, HI + 1)); ax.set_xticklabels(range(LO, HI + 1), fontsize=8)
    ax.set_xlim(LO - 0.7, HI + 0.7); ax.grid(alpha=0.25)


def annotate(ax, marks, flip):
    for (i, side, prc, lbl, c) in marks:
        dy = 3 if side == "H" else -3
        va = "bottom" if side == "H" else "top"
        ax.plot([i], [prc], marker="_", ms=18, mec=c, mew=2.5)
        ax.text(i, prc + dy, lbl, ha="center", va=va, fontsize=9, color=c, fontweight="bold")
    ax.axvline(flip, color="blue", lw=2, ls="--", alpha=0.7)
    ax.text(flip, ax.get_ylim()[1], f" FLIP → BULL @ b{flip}", color="blue",
            fontsize=11, fontweight="bold", va="top")


fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 13), sharex=True)
candles(ax1); annotate(ax1, A, FLIP_A)
ax1.set_title("SCHEME A — swing pivots + running break:  HH1=b43 (first higher swing-high), "
              "HH2=b44 (first break of it);  HL1=b41, HL2=b44  →  2HH+2HL at b44",
              fontsize=12, fontweight="bold")
candles(ax2); annotate(ax2, B, FLIP_B)
nHH = sum(1 for m in B if m[3].startswith("HH"))
ax2.set_title(f"SCHEME B — every new higher-high bar counts ({nHH} HHs: b41,b42,b43,b44…):  "
              f"2 HHs reached early, but only 2 HLs by b44  →  still flips at b44 (HL is the bottleneck)",
              fontsize=12, fontweight="bold")
fig.suptitle("2026-06-09 bottom reversal — two ways to count HH/HL for the bull flip",
             fontsize=14, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.97])
out = ROOT / "docs" / "living" / "reversal_count_demo.png"
fig.savefig(out, dpi=130)
print("saved", out)
print("Scheme A HHs/HLs:", [(m[0], m[3]) for m in A if m[3] != "LOW"])
print("Scheme B HHs/HLs:", [(m[0], m[3]) for m in B if m[3] != "LOW"])
