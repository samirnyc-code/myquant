"""
ABR (average bar range, high-low) of ES 2000-tick RTH bars, by year.

Bars built exactly as in the S95 sims: 2000 ticks per bar, per-day RTH chart
from data/ticks_continuous (RTH-only files, 08:30-15:15), partial last bar
of each day dropped.

Output (dated): abr_tick2000_<stamp>.csv + printed table.
"""
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime

TICK_DIR = Path(r"c:\Users\Admin\myquant\data\ticks_continuous")
OUT_DIR = Path(__file__).parent
BAR = 2000
T = 0.25


def main():
    rows = []
    files = sorted(TICK_DIR.glob("*.parquet"))
    for i, f in enumerate(files):
        prices = pd.read_parquet(f, columns=["Price"])["Price"].to_numpy()
        nbars = len(prices) // BAR
        if nbars == 0:
            continue
        grid = prices[: nbars * BAR].reshape(nbars, BAR)
        rng = grid.max(axis=1) - grid.min(axis=1)
        rows.append({"date": f.stem, "year": f.stem[:4], "bars": nbars,
                     "sum_range": rng.sum(), "med_range": np.median(rng)})
        if (i + 1) % 300 == 0:
            print(f"{i+1}/{len(files)} days...", flush=True)

    d = pd.DataFrame(rows)
    out = []
    for y, g in d.groupby("year"):
        abr = g["sum_range"].sum() / g["bars"].sum()
        out.append({
            "year": y,
            "days": len(g),
            "bars": int(g["bars"].sum()),
            "bars_per_day": round(g["bars"].mean(), 1),
            "abr_pts": round(abr, 2),
            "abr_ticks": round(abr / T, 1),
            "med_daily_median_pts": round(g["med_range"].median(), 2),
        })
    abr_all = d["sum_range"].sum() / d["bars"].sum()
    out.append({"year": "ALL", "days": len(d), "bars": int(d["bars"].sum()),
                "bars_per_day": round(d["bars"].mean(), 1),
                "abr_pts": round(abr_all, 2), "abr_ticks": round(abr_all / T, 1),
                "med_daily_median_pts": round(d["med_range"].median(), 2)})
    res = pd.DataFrame(out)
    print(res.to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    res.to_csv(OUT_DIR / f"abr_tick2000_{stamp}.csv", index=False)
    d.drop(columns="sum_range").assign(
        abr_pts=(d["sum_range"] / d["bars"]).round(2)
    ).to_csv(OUT_DIR / f"abr_tick2000_daily_{stamp}.csv", index=False)
    print(f"saved: abr_tick2000_{stamp}.csv (+ per-day file)")


if __name__ == "__main__":
    main()
