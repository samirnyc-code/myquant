"""build_2000t_features.py — Stage 0b of the tempo/market-state study (S116).

Builds 2000-tick bars + core tempo features for EVERY day in data/ticks_continuous/
(Panama-adjusted ES trade ticks, CT-naive, RTH [08:30,15:15)).

Per bar: start, end, duration_s, ticks, vol, OHLC, range, disp (|C-O|),
eff (disp/range), tempo (ticks/sec), avg_trade_size (vol/ticks).
Bars never span days (tick count resets each session, matching NT8 charts).
The last bar of a day is kept with its true tick count (< 2000) — analysis
filters on ticks == SIZE.

Checkpointed: one parquet per day in tempo/outputs/bars_2000t/; existing days
are skipped. Final concat -> tempo/outputs/bars_2000t_all.parquet.

    python tempo/scripts/build_2000t_features.py [--size 2000] [--force]
"""
from __future__ import annotations
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TROVE = ROOT / "data" / "ticks_continuous"
OUTDIR = ROOT / "tempo" / "outputs" / "bars_2000t"
ALL = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"


def day_bars(df: pd.DataFrame, size: int, date: str) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    grp = df.index // size
    g = df.groupby(grp)
    b = pd.DataFrame({
        "start": g["DateTime"].first(),
        "end": g["DateTime"].last(),
        "open": g["Price"].first(),
        "high": g["Price"].max(),
        "low": g["Price"].min(),
        "close": g["Price"].last(),
        "vol": g["Volume"].sum(),
        "ticks": g["Price"].size(),
    }).reset_index(drop=True)
    b.insert(0, "date", date)
    b.insert(1, "bar", np.arange(len(b)))
    dur = (b["end"] - b["start"]).dt.total_seconds().clip(lower=1e-3)
    b["duration_s"] = dur
    b["range"] = b["high"] - b["low"]
    b["disp"] = (b["close"] - b["open"]).abs()
    b["eff"] = np.where(b["range"] > 0, b["disp"] / b["range"], 0.0)
    b["tempo"] = b["ticks"] / dur
    b["avg_trade_size"] = b["vol"] / b["ticks"]
    b["session_min"] = (b["start"] - b["start"].dt.normalize()
                        - pd.Timedelta(hours=8, minutes=30)).dt.total_seconds() / 60.0
    return b


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--size", type=int, default=2000)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    files = sorted(TROVE.glob("*.parquet"))
    done = skipped = 0
    for f in files:
        out = OUTDIR / f"{f.stem}.parquet"
        if out.exists() and not a.force:
            skipped += 1
            continue
        b = day_bars(pd.read_parquet(f), a.size, f.stem)
        b.to_parquet(out, index=False)
        done += 1
        if done % 100 == 0:
            print(f"  {done} days built ({f.stem})", flush=True)

    parts = [pd.read_parquet(p) for p in sorted(OUTDIR.glob("*.parquet"))]
    allb = pd.concat(parts, ignore_index=True)
    allb.to_parquet(ALL, index=False)
    full = allb[allb["ticks"] == a.size]
    print(f"built {done} new / skipped {skipped} existing days")
    print(f"total: {len(allb):,} bars over {allb['date'].nunique():,} days "
          f"({allb['date'].min()} .. {allb['date'].max()})")
    print(f"full {a.size}-tick bars: {len(full):,} ({len(full)/len(allb):.1%})")
    print(f"bars/day: median {allb.groupby('date').size().median():.0f}")
    print(f"duration_s (full bars): p10 {full['duration_s'].quantile(.1):.1f}  "
          f"median {full['duration_s'].median():.1f}  p90 {full['duration_s'].quantile(.9):.1f}  "
          f"p99 {full['duration_s'].quantile(.99):.1f}")
    print(f"saved -> {ALL.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
