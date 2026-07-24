"""Underwater explainer graphic: equity vs its own high-water mark (adr.30 book).
  python scripts/regime_2e_underwater_explain.py
"""
from pathlib import Path
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
d = pd.read_csv(ROOT / "data" / "regime" / "volstops_20260724.csv")
x = d[(d["stop"] == "adr.30") & (d.target == "eod")].sort_values("Date").reset_index(drop=True)
x["net"] = x.net - 12.5
eq = x.net.cumsum(); hwm = eq.cummax()
dates = pd.to_datetime(x.Date)

fig, ax = plt.subplots(figsize=(13, 6.5), dpi=115)
ax.plot(dates, eq, lw=1.8, color="#2a78d6", label="equity (always ABOVE zero here)")
ax.plot(dates, hwm, lw=1.4, ls="--", color="#1baf7a", label="high-water mark (best equity so far)")
ax.fill_between(dates, eq, hwm, where=(hwm - eq) > 1e-9, color="#e34948", alpha=0.25,
                label="UNDERWATER = below your own best, not below zero")
ax.axhline(0, color="#33454d", lw=1.2)
ax.text(dates.iloc[10], 500, "zero line", fontsize=10, color="#33454d")
i_pk = eq[eq.cummax() == eq[x.Date <= "2023-03-03"].max()].index[0]
seg = eq[(x.Date >= "2023-03-03") & (x.Date <= "2024-12-18")]
i_tr = seg.idxmin()
ax.annotate(f"peak +${eq[i_pk]:,.0f}\n2023-03-03", (dates[i_pk], eq[i_pk]),
            xytext=(dates[i_pk], eq[i_pk] + 9000), ha="center", fontsize=10,
            fontweight="bold", arrowprops=dict(arrowstyle="->"))
ax.annotate(f"trough +${eq[i_tr]:,.0f}\n(still > 0, but ${hwm[i_tr]-eq[i_tr]:,.0f}\nbelow the peak)",
            (dates[i_tr], eq[i_tr]), xytext=(dates[i_tr], eq[i_tr] - 14000), ha="center",
            fontsize=10, fontweight="bold", arrowprops=dict(arrowstyle="->"))
ax.set_title("Underwater = distance below your OWN best equity (high-water mark) — "
             "656 days without a new high, all of it above zero", fontweight="bold", fontsize=12)
ax.legend(frameon=False, loc="upper left")
ax.grid(axis="y", color="#eceeed", lw=0.7)
for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
fig.tight_layout()
p = ROOT / "docs" / "living" / "underwater_explained_20260724.png"
fig.savefig(p, facecolor="white")
print("saved", p)
