"""ABR (average bar range, high-low) of ES 2000-tick bars, 08:30-14:30 CT, by year.

Same 2000-tick bars as the S95 sims, but ticks are restricted to the 08:30-14:30
CT window (Mack's core session / ~2:30 cutoff) before bars are built. Partial last
bar of the window dropped. Output (dated): abr_tick2000_830_1430_<stamp>.csv + table.
"""
from datetime import datetime, time
from pathlib import Path

import numpy as np
import pandas as pd

TICK_DIR = Path(r"c:\Users\Admin\myquant\data\ticks_continuous")
OUT_DIR = Path(__file__).parent
BAR = 2000
CUTOFF = time(14, 30)


def main():
    rows = []
    files = sorted(TICK_DIR.glob("*.parquet"))
    for i, f in enumerate(files):
        df = pd.read_parquet(f, columns=["DateTime", "Price"])
        df = df[df["DateTime"].dt.time < CUTOFF]
        prices = df["Price"].to_numpy()
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
    for y, g in list(d.groupby("year")) + [("ALL", d)]:
        abr = g["sum_range"].sum() / g["bars"].sum()
        out.append({"year": y, "days": len(g), "bars": int(g["bars"].sum()),
                    "bars_per_day": round(g["bars"].sum() / len(g), 1),
                    "abr_pts": round(abr, 2), "abr_ticks": round(abr / 0.25, 1),
                    "med_daily_median_pts": round(g["med_range"].median(), 2)})
    res = pd.DataFrame(out)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    res.to_csv(OUT_DIR / f"abr_tick2000_830_1430_{stamp}.csv", index=False)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
