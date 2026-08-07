"""
Chart the yearly + rolling ABR of ES 2000-tick RTH bars.

Reads the dated per-day file from abr_tick2000.py and renders one PNG:
- top: yearly ABR (mean bar + median marker)
- bottom: 20-day rolling ABR with faint daily values

Output: abr_tick2000_chart_<stamp>.png
"""
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime

OUT_DIR = Path(__file__).parent
DAILY = OUT_DIR / "abr_tick2000_daily_20260807_191750.csv"

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e6e5e1"
BLUE = "#2a78d6"     # series 1
ORANGE = "#eb6834"   # series 2

d = pd.read_csv(DAILY, parse_dates=["date"])
yearly = d.groupby("year").agg(abr=("abr_pts", lambda s: (s * d.loc[s.index, "bars"]).sum()
                                    / d.loc[s.index, "bars"].sum()),
                               med=("med_range", "median")).reset_index()
d = d.sort_values("date")
d["roll20"] = d["abr_pts"].rolling(20).mean()

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7.5), dpi=150,
                               gridspec_kw={"height_ratios": [1, 1.3], "hspace": 0.38})
fig.patch.set_facecolor(SURFACE)

for ax in (ax1, ax2):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)

# --- top: yearly ---
x = range(len(yearly))
ax1.bar(x, yearly["abr"], width=0.55, color=BLUE, label="Mean bar range", zorder=3)
ax1.scatter(x, yearly["med"], color=ORANGE, marker="D", s=42, zorder=4,
            label="Median (of daily medians)")
for xi, v in zip(x, yearly["abr"]):
    ax1.text(xi, v + 0.09, f"{v:.2f}", ha="center", fontsize=9, color=INK)
ax1.set_xticks(list(x), yearly["year"].astype(str))
ax1.set_ylim(0, yearly["abr"].max() * 1.22)
ax1.set_ylabel("points", color=INK2, fontsize=9)
ax1.set_title("ES 2000-tick RTH bars — average bar range by year",
              color=INK, fontsize=12, loc="left", pad=10)
ax1.legend(frameon=False, fontsize=9, labelcolor=INK2, loc="upper left",
           bbox_to_anchor=(0.0, 1.02), ncols=2)

# --- bottom: rolling daily ---
ax2.plot(d["date"], d["abr_pts"], color=BLUE, alpha=0.18, linewidth=0.8)
ax2.plot(d["date"], d["roll20"], color=BLUE, linewidth=2)
ax2.set_ylabel("points", color=INK2, fontsize=9)
ax2.set_title("Daily ABR (faint) and 20-day rolling mean",
              color=INK, fontsize=11, loc="left", pad=8)
for y in range(2022, 2027):
    ax2.axvline(pd.Timestamp(f"{y}-01-01"), color=GRID, linewidth=0.8, zorder=1)
last = d.dropna(subset=["roll20"]).iloc[-1]
ax2.annotate(f'{last["roll20"]:.2f}', (last["date"], last["roll20"]),
             xytext=(8, 0), textcoords="offset points", fontsize=9,
             color=INK, va="center")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
out = OUT_DIR / f"abr_tick2000_chart_{stamp}.png"
fig.savefig(out, bbox_inches="tight", facecolor=SURFACE)
print(out)
