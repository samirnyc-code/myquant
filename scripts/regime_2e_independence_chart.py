"""Independence-test graphics: equity curves + train/test PF bars per config.
  python scripts/regime_2e_independence_chart.py
"""
from pathlib import Path
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
d = pd.read_csv(ROOT / "data" / "regime" / "validation_tick_20260724.csv")
d["is_tr"] = d.Date <= "2023-12-31"
ORDER = ["s0", "s0+gap", "s0+cxl6", "s0+both", "adr30_rt8"]
COLS = {"s0": "#8b8f96", "s0+gap": "#2a78d6", "s0+cxl6": "#eda100",
        "s0+both": "#1baf7a", "adr30_rt8": "#4a3aa7"}


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return gp / gl if gl > 0 else float("inf")


fig, (a1, a2) = plt.subplots(1, 2, figsize=(15, 6), dpi=115,
                             gridspec_kw=dict(width_ratios=[2, 1]))
for v in ORDER:
    x = d[d.variant == v].sort_values("Date")
    a1.plot(range(len(x)), x.net.cumsum().values, lw=1.8, color=COLS[v],
            label=f"{v}  ({x.net.sum():+,.0f}$, PF {pf(x.net):.2f})")
a1.axhline(0, color="#c3c2b7", lw=1); a1.legend(frameon=False, fontsize=9.5)
a1.set_title("Independence test — equity, net of all costs (1 ES)", fontweight="bold")
a1.grid(axis="y", color="#eceeed", lw=0.7)

import numpy as np
xs = np.arange(len(ORDER)); w = 0.35
tr_pf = [pf(d[(d.variant == v) & d.is_tr].net) for v in ORDER]
te_pf = [pf(d[(d.variant == v) & ~d.is_tr].net) for v in ORDER]
a2.bar(xs - w / 2, tr_pf, w, color="#2a78d6", label="train PF")
a2.bar(xs + w / 2, te_pf, w, color="#eb6834", label="test PF")
for i, (t_, e_) in enumerate(zip(tr_pf, te_pf)):
    a2.text(i - w / 2, t_ + 0.02, f"{t_:.2f}", ha="center", fontsize=9, fontweight="bold")
    a2.text(i + w / 2, e_ + 0.02, f"{e_:.2f}", ha="center", fontsize=9, fontweight="bold")
a2.axhline(1.0, color="#33454d", lw=1.2, ls="--")
a2.set_xticks(xs, ORDER, rotation=20)
a2.legend(frameon=False); a2.set_title("PF by half — the transfer test", fontweight="bold")
a2.grid(axis="y", color="#eceeed", lw=0.7)
for ax in (a1, a2):
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
fig.tight_layout()
p = ROOT / "docs" / "living" / "independence_test_20260724.png"
fig.savefig(p, facecolor="white")
print("saved", p)
