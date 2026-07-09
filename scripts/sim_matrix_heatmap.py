"""Heatmap of the stop x target sweep (avgR, PF annotated) for key filter sets."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(r"c:\Users\Admin\myquant")
df = pd.read_parquet(ROOT / "docs" / "living" / "brooks_sim_matrix.parquet")
STOPS = ["SB", "A1", "A1.5", "A2"]
TGTS = ["BE1", "BE2", "1R", "2R", "3R", "t8", "EOD"]

SETS = [
    ("IB+OB all-day", df.setup.isin(["IB", "OB"])),
    ("IB+OB morning", df.setup.isin(["IB", "OB"]) & (df.frac < 0.33)),
    ("IB+OB morning + SB-IBS>=60", df.setup.isin(["IB", "OB"]) & (df.frac < 0.33) & (df.sbibs >= 60)),
]

fig, axes = plt.subplots(1, 3, figsize=(22, 7))
for ax, (title, mask) in zip(axes, SETS):
    sub = df[mask]
    Rm = np.full((len(STOPS), len(TGTS)), np.nan)
    ann = np.empty((len(STOPS), len(TGTS)), dtype=object)
    for si, sn in enumerate(STOPS):
        for ti, tn in enumerate(TGTS):
            c = sub[(sub.stop == sn) & (sub.target == tn)]
            if len(c):
                Rm[si, ti] = c.R.mean()
                gp = c.net[c.net > 0].sum(); gl = -c.net[c.net < 0].sum()
                pf = gp / gl if gl else 9
                ann[si, ti] = f"{c.R.mean():+.2f}\nPF{pf:.2f}\n${c.net.sum()/1000:+.0f}k"
            else:
                ann[si, ti] = ""
    vmax = np.nanmax(np.abs(Rm))
    im = ax.imshow(Rm, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(TGTS))); ax.set_xticklabels(TGTS)
    ax.set_yticks(range(len(STOPS))); ax.set_yticklabels(STOPS)
    ax.set_xlabel("target"); ax.set_ylabel("stop")
    ax.set_title(f"{title}\n(n={len(sub)//(len(STOPS)*len(TGTS))})", fontsize=11, fontweight="bold")
    for si in range(len(STOPS)):
        for ti in range(len(TGTS)):
            ax.text(ti, si, ann[si, ti], ha="center", va="center", fontsize=7.5)
fig.suptitle("Brooks IB/OB — stop x target sweep (color = avg R; label = avgR / PF / net) — 1yr, $5 RT, 1 ES",
             fontsize=13, fontweight="bold")
fig.tight_layout(rect=[0, 0, 1, 0.95])
out = ROOT / "docs" / "living" / "sim_matrix_heatmap.png"
fig.savefig(out, dpi=120); print("saved", out)
