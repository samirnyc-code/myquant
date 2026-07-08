"""Find & display real examples of STRICT vs LOOSE inside/outside bars.

Classification of bar i vs the immediately prior bar i-1 (exact tick):
  strict IB      : H[i]<H[i-1] and L[i]>L[i-1]                 (no equal extreme)
  loose IB (mDT) : H[i]==H[i-1] and L[i]>L[i-1]               (equal HIGH)
  loose IB (mDB) : L[i]==L[i-1] and H[i]<H[i-1]               (equal LOW)
  strict OB      : H[i]>H[i-1] and L[i]<L[i-1]                 (breaks both)
  loose OB (mDT) : H[i]==H[i-1] and L[i]<L[i-1]               (equal HIGH, low breaks out)
  loose OB (mDB) : L[i]==L[i-1] and H[i]>H[i-1]               (equal LOW,  high breaks out)
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

CATS = ["strict IB", "loose IB (mDT)", "loose IB (mDB)",
        "strict OB", "loose OB (mDT)", "loose OB (mDB)"]
found = {c: [] for c in CATS}
NEED = 3
MINRNG = 1.0                                   # prior-bar range filter (pts) so bars are visible

for day, g in b.groupby("Date"):
    g = g.sort_values("DateTime").reset_index(drop=True)
    H, L = g["High"].values, g["Low"].values
    n = len(g)
    for i in range(2, n - 1):
        if (H[i-1] - L[i-1]) < MINRNG:
            continue
        eqH = H[i] == H[i-1]; eqL = L[i] == L[i-1]
        inH = H[i] < H[i-1];  inL = L[i] > L[i-1]
        outH = H[i] > H[i-1]; outL = L[i] < L[i-1]
        cat = None
        if inH and inL:                cat = "strict IB"
        elif eqH and inL:              cat = "loose IB (mDT)"
        elif eqL and inH:              cat = "loose IB (mDB)"
        elif outH and outL:            cat = "strict OB"
        elif eqH and outL:             cat = "loose OB (mDT)"
        elif eqL and outH:             cat = "loose OB (mDB)"
        if cat and len(found[cat]) < NEED:
            found[cat].append((day, i))
    if all(len(found[c]) >= NEED for c in CATS):
        break

for c in CATS:
    print(c, "->", found[c])


def draw(ax, day, i):
    g = b[b["Date"] == day].sort_values("DateTime").reset_index(drop=True)
    O, H, L, C = (g[x].values for x in ["Open", "High", "Low", "Close"])
    lo, hi = i - 2, i + 2
    for j in range(lo, hi + 1):
        if j < 0 or j >= len(g):
            continue
        col = "#26a69a" if C[j] >= O[j] else "#ef5350"
        hl = (j in (i - 1, i))
        ax.plot([j, j], [L[j], H[j]], color=col, lw=2.2 if hl else 1.2, zorder=3)
        ax.add_patch(plt.Rectangle((j - 0.34, min(O[j], C[j])), 0.68,
                                   max(abs(C[j] - O[j]), .02), facecolor=col,
                                   edgecolor="black" if not hl else "blue",
                                   lw=1.6 if hl else 0.4, zorder=4))
    # mark the reference bar (i-1) and the classified bar (i)
    ax.text(i-1, H[i-1] + (H[i]-L[i])*0.10, "prior", ha="center", fontsize=7, color="dimgray")
    ax.text(i, H[i] + (H[i]-L[i])*0.10, f"bar", ha="center", fontsize=7, color="blue", fontweight="bold")
    # equal-tick level for loose cases
    if H[i] == H[i-1]:
        ax.axhline(H[i], color="darkgreen", ls=":", lw=1.2)
        ax.text(hi+0.2, H[i], " =H (mDT)", va="center", fontsize=7, color="darkgreen")
    if L[i] == L[i-1]:
        ax.axhline(L[i], color="darkred", ls=":", lw=1.2)
        ax.text(hi+0.2, L[i], " =L (mDB)", va="center", fontsize=7, color="darkred")
    ax.set_xlim(lo - 0.7, hi + 1.6)
    ax.set_xticks([]); ax.set_yticks([])


# ---- one big HI-RES slide per category ---------------------------------------
slug = {"strict IB": "strictIB", "loose IB (mDT)": "looseIB_mDT",
        "loose IB (mDB)": "looseIB_mDB", "strict OB": "strictOB",
        "loose OB (mDT)": "looseOB_mDT", "loose OB (mDB)": "looseOB_mDB"}
outdir = ROOT / "docs" / "living" / "ib_ob_examples"
outdir.mkdir(exist_ok=True)
saved = []
from matplotlib.backends.backend_pdf import PdfPages
pdf_path = ROOT / "docs" / "living" / "ib_ob_examples.pdf"
pdf = PdfPages(pdf_path)
for c in CATS:
    fig, axes = plt.subplots(1, NEED, figsize=(20, 8))
    if NEED == 1:
        axes = [axes]
    for k in range(NEED):
        ax = axes[k]
        if k < len(found[c]):
            day, i = found[c][k]
            draw(ax, day, i)
            ax.set_title(f"{day}   bar {i}", fontsize=13)
        else:
            ax.axis("off")
    fig.suptitle(f"{c.upper()}  —  real ES examples "
                 f"(blue = prior bar + classified bar; dotted = equal-tick extreme)",
                 fontsize=16, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = outdir / f"{slug[c]}.png"
    fig.savefig(out, dpi=160)
    pdf.savefig(fig)                     # add as a page to the bundled PDF
    plt.close(fig)
    saved.append(out)
    print("saved", out)
pdf.close()
print("saved bundle", pdf_path)
print("\nALL:", "\n".join(str(s) for s in saved))
