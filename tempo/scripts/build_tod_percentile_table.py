"""build_tod_percentile_table.py — calibration table for the NT8 TempoSpeedometer (S116-tempo).

From the full 5-year 2000t bar history, builds per-15-min-session-bucket percentile
grids for the three gauge metrics so the indicator can say "fast FOR THIS TIME OF DAY":

  metric   tempo  = ticks/sec        (full 2000-tick bars only)
           range  = high-low, points
           eff    = |close-open| / (high-low)

Buckets: session minute // 15 -> 0..26 (RTH 08:30-15:15 CT = 405 min). A bucket=-1
row holds the ALL-session grid (fallback / eff, which is nearly tod-flat).
Grid: percentiles 1..99. Output CSV (long): metric,bucket,p01..p99 — read by
nt8/TempoSpeedometer.cs at Configure.

    python tempo/scripts/build_tod_percentile_table.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ALL = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"
OUT = ROOT / "tempo" / "outputs" / "tod_percentiles.csv"
SIZE = 2000
BUCKET_MIN = 15
PCTS = list(range(1, 100))


def main():
    df = pd.read_parquet(ALL)
    df = df[df["ticks"] == SIZE].copy()
    df["bucket"] = (df["session_min"] // BUCKET_MIN).astype(int)
    df = df[(df["bucket"] >= 0) & (df["bucket"] <= 26)]
    print(f"bars: {len(df):,}  days: {df['date'].nunique():,}  buckets: {df['bucket'].nunique()}")

    rows = []
    for metric in ["tempo", "range", "eff"]:
        for bucket, g in [(-1, df)] + list(df.groupby("bucket")):
            q = np.percentile(g[metric].to_numpy(), PCTS)
            row = {"metric": metric, "bucket": int(bucket), "n": len(g)}
            row.update({f"p{p:02d}": round(float(v), 6) for p, v in zip(PCTS, q)})
            rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False)

    t = out[(out["metric"] == "tempo") & (out["bucket"] >= 0)].set_index("bucket")
    print("\ntempo median (p50) by bucket, ticks/sec — the intraday U:")
    for b in t.index:
        bar = "#" * int(t.loc[b, "p50"] * 1.5)
        t0 = (dt.datetime(2000, 1, 1, 8, 30) + dt.timedelta(minutes=15 * int(b))).strftime("%H:%M")
        print(f"  {t0}  p50={t.loc[b, 'p50']:6.1f}  p95={t.loc[b, 'p95']:7.1f}  {bar}")
    print(f"\nsaved -> {OUT.relative_to(ROOT)}  ({len(out)} rows: 3 metrics x 28 buckets)")


if __name__ == "__main__":
    main()
