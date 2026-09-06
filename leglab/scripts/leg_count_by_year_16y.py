"""
ES leg count by year over the full 16-year sample (2010-2026).
Bars = mean legs_closed/day (Tim's definition). 2010 & 2026 are partial years
(flagged). Overlays the full-sample mean line and Tim's ~15 reference band.
Reads leg_count_es.py per-day CSV.
"""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUTDIR = ROOT / "leglab" / "outputs"
RUN = "20260906"
df = pd.read_csv(OUTDIR / f"leg_count_es_5m_{RUN}.csv")

yr = df.groupby("year").agg(
    legs_mean=("legs_closed", "mean"),
    legs_median=("legs_closed", "median"),
    days=("legs_closed", "size"),
).round(2)
yr.to_csv(OUTDIR / f"leg_count_by_year_16y_{RUN}.csv")
print(yr.to_string())

partial = {2010, 2026}
overall = df["legs_closed"].mean()

fig, ax = plt.subplots(figsize=(13, 6))
colors = ["#9db8d6" if y in partial else "#2b5fa8" for y in yr.index]
bars = ax.bar(yr.index.astype(str), yr["legs_mean"], color=colors)
ax.bar_label(bars, fmt="%.1f", padding=2, fontsize=9)

ax.axhline(overall, color="#e08a2b", lw=1.6, ls="--",
           label=f"16y mean = {overall:.1f}")
ax.set_ylabel("Average legs per day (legs_closed, 0.15x ADR)")
ax.set_title("ES — average legs per day by year, 2010-2026 (light bars = partial year)")
ax.set_ylim(0, 19)
ax.grid(axis="y", alpha=0.3)
ax.legend()
fig.tight_layout()
png = OUTDIR / f"leg_count_by_year_16y_{RUN}.png"
fig.savefig(png, dpi=130)
print(f"\npng -> {png}")
print(f"16y mean legs/day = {overall:.2f}")
