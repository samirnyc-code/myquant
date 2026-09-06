"""
Side-by-side: OUR ES leg counts vs Tim's published per-year chart.

Tim's chart "ES -- average legs per day, by year" (0.15x threshold), the four
full years in his 2021-08..2026 window. Values read directly off es_legs_by_year.png:
    2022=14.7, 2023=15.4, 2024=15.2, 2025=14.8   (MEAN legs/day, counted-at-reversal)

Our comparable metric = legs_closed MEAN (a leg is counted when it closes on a
threshold reversal — this is what matches Tim's ~15, not legs_total).

Reads the per-day CSV produced by leg_count_es.py.
Outputs:
    data/research/leg_count_vs_tim_<RUN>.csv
    data/research/leg_count_vs_tim_<RUN>.png   (grouped bar chart)
"""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUTDIR = ROOT / "leglab" / "outputs"
RUN = "20260906"
CSV_IN = OUTDIR / f"leg_count_es_5m_{RUN}.csv"

TIM = {2022: 14.7, 2023: 15.4, 2024: 15.2, 2025: 14.8}  # from es_legs_by_year.png


def main():
    df = pd.read_csv(CSV_IN)
    yr = df.groupby("year")["legs_closed"].mean().round(2)

    rows = []
    for y in sorted(TIM):
        ours = float(yr.get(y, float("nan")))
        rows.append({
            "year": y,
            "tim_avg": TIM[y],
            "ours_avg": round(ours, 2),
            "delta": round(ours - TIM[y], 2),
            "pct_err": round(100 * (ours - TIM[y]) / TIM[y], 1),
        })
    comp = pd.DataFrame(rows)

    print("ES average legs/day (0.15x ADR) — OURS vs TIM")
    print(comp.to_string(index=False))
    print(f"\nmean |delta| = {comp['delta'].abs().mean():.2f} legs   "
          f"mean |pct_err| = {comp['pct_err'].abs().mean():.1f}%")

    csv_out = OUTDIR / f"leg_count_vs_tim_{RUN}.csv"
    comp.to_csv(csv_out, index=False)
    print(f"csv -> {csv_out}")

    # grouped bar chart
    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = range(len(comp))
    w = 0.38
    b1 = ax.bar([i - w / 2 for i in x], comp["tim_avg"], w, label="Tim (published)", color="#2b5fa8")
    b2 = ax.bar([i + w / 2 for i in x], comp["ours_avg"], w, label="Ours (Databento 5M)", color="#e08a2b")
    ax.bar_label(b1, fmt="%.1f", padding=2, fontsize=10)
    ax.bar_label(b2, fmt="%.1f", padding=2, fontsize=10)
    ax.set_xticks(list(x))
    ax.set_xticklabels(comp["year"])
    ax.set_ylabel("Average legs per day (0.15x ADR)")
    ax.set_title("ES leg count by year — Ours vs Tim (zentradingtech)")
    ax.set_ylim(0, 18)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    png_out = OUTDIR / f"leg_count_vs_tim_{RUN}.png"
    fig.savefig(png_out, dpi=130)
    print(f"png -> {png_out}")


if __name__ == "__main__":
    main()
