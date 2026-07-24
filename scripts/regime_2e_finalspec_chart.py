"""Final-spec graphics: equity w/ train-test split, yearly net + PF, net shares.
  python scripts/regime_2e_finalspec_chart.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
gc_ = pd.read_csv(ROOT / "data" / "regime" / "gapday_cancel_20260724.csv")
s3 = gc_[(gc_.scope == "NRM") & (gc_.variant == "cxl999")].sort_values("Date").reset_index(drop=True)
s3["yr"] = s3.Date.str[:4]
split_i = int((s3.Date <= "2023-12-31").sum())


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return gp / gl if gl > 0 else float("inf")


fig, axes = plt.subplots(2, 2, figsize=(15, 9), dpi=115)
ax = axes[0][0]
eq = s3.net.cumsum()
ax.plot(range(split_i), eq[:split_i], lw=2, color="#2a78d6",
        label=f"train n=283  +$40,772  PF 1.44")
ax.plot(range(split_i - 1, len(eq)), eq[split_i - 1:], lw=2, color="#eb6834",
        label=f"test n=347  +$41,940  PF 1.36")
ax.axvline(split_i, ls="--", color="#8b8f96")
ax.text(split_i + 3, eq.min(), "2024-01", fontsize=9, color="#8b8f96")
ax.axhline(0, color="#c3c2b7", lw=1)
ax.legend(frameon=False)
ax.set_title("COMMITTED SPEC equity — adr.30 × 6t × gap-filter × EOD (net of all costs)",
             fontweight="bold", fontsize=11)

ax = axes[0][1]
yn = s3.groupby("yr").net.sum()
cols = ["#1f7a3d" if v >= 0 else "#b23a2e" for v in yn.values]
ax.bar(yn.index, yn.values, color=cols, width=0.6)
for i, v in enumerate(yn.values):
    ax.text(i, v + 500, f"{v/1000:+.1f}k\n{yn.values[i]/yn.sum()*100:.0f}%",
            ha="center", fontsize=9, fontweight="bold")
ax.axhline(0, color="#c3c2b7", lw=1)
ax.set_title("Net by year + share of lifetime net (2022 = 37%)", fontweight="bold", fontsize=11)

ax = axes[1][0]
ypf = s3.groupby("yr").net.apply(pf)
ax.plot(ypf.index, ypf.values, "o-", lw=2, color="#4a3aa7")
for i, v in enumerate(ypf.values):
    ax.text(i, v + 0.03, f"{v:.2f}", ha="center", fontsize=10, fontweight="bold")
ax.axhline(1.0, ls="--", color="#33454d")
ax.set_ylim(0.8, 2.0)
ax.set_title("PF by year — green every year, best in trending 2022", fontweight="bold", fontsize=11)

ax = axes[1][1]
ex22 = s3[s3.yr != "2022"]
bars = [("lifetime", s3.net.sum(), pf(s3.net)), ("ex-2022", ex22.net.sum(), pf(ex22.net)),
        ("test half", s3.iloc[split_i:].net.sum(), pf(s3.iloc[split_i:].net)),
        ("2t slip", (s3.net - 12.5).sum(), pf(s3.net - 12.5))]
xs = np.arange(len(bars))
ax.bar(xs, [b[1] for b in bars], color="#9ec5f4", width=0.55)
for i, (lab, v, p_) in enumerate(bars):
    ax.text(i, v + 800, f"{v/1000:+.1f}k\nPF {p_:.2f}", ha="center", fontsize=10, fontweight="bold")
ax.set_xticks(xs, [b[0] for b in bars])
ax.set_title("Robustness views of the same book", fontweight="bold", fontsize=11)
for a_ in axes.flat:
    a_.grid(axis="y", color="#eceeed", lw=0.6)
    for s_ in ("top", "right"): a_.spines[s_].set_visible(False)
fig.tight_layout()
p = ROOT / "docs" / "living" / "finalspec_20260724.png"
fig.savefig(p, facecolor="white")
print("saved", p)
