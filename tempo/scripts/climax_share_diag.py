"""climax_share_diag.py — why is the chart full of climax bars? (S116-tempo)

Scores EVERY historical 2000t bar against the shipped TOD grid (tod_percentiles.csv,
pooled 2021-2026) exactly like the NT8 indicator does, then reports the share of
bars >= p95 / p80 BY YEAR. If the calibration were stationary, every year would
show ~5% / ~20%. A drifting share = the pooled grid mis-calibrates recent data
and the table must be built from a trailing window instead.

    python tempo/scripts/climax_share_diag.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"
TOD = ROOT / "tempo" / "outputs" / "tod_percentiles.csv"
OUT = ROOT / "tempo" / "outputs"


def main():
    tod = pd.read_csv(TOD)
    grids = {int(r["bucket"]): r[[f"p{p:02d}" for p in range(1, 100)]].to_numpy(float)
             for _, r in tod[tod["metric"] == "tempo"].iterrows()}

    df = pd.read_parquet(BARS)
    df = df[df["ticks"] == 2000].copy()
    df["bucket"] = (df["session_min"] // 15).astype(int).clip(0, 26)
    pct = np.empty(len(df))
    for b, g in df.groupby("bucket"):
        pct[df.index.get_indexer(g.index)] = np.searchsorted(grids[int(b)], g["tempo"].to_numpy()) + 1
    df["tpct"] = np.clip(pct, 1, 99)
    df["year"] = df["date"].str[:4]

    res = df.groupby("year").agg(
        n=("tpct", "size"),
        share_ge95=("tpct", lambda s: (s >= 95).mean()),
        share_ge80=("tpct", lambda s: (s >= 80).mean()),
        median_pct=("tpct", "median"),
        median_tps=("tempo", "median"),
    ).round(3)
    # last 60 sessions, daily share
    last = df[df["date"].isin(sorted(df["date"].unique())[-60:])]
    daily = last.groupby("date")["tpct"].apply(lambda s: (s >= 95).mean())
    today = dt.date.today().isoformat()
    res.to_csv(OUT / f"climax_share_diag_{today}.csv")
    print(res.to_string())
    print(f"\nlast 60 sessions: daily share>=p95 median {daily.median():.1%}  "
          f"min {daily.min():.1%}  max {daily.max():.1%}")
    print(f"most recent 5 days: {[(d, round(v,3)) for d, v in daily.tail(5).items()]}")


if __name__ == "__main__":
    main()
