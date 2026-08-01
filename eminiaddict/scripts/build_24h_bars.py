"""Build 24-HOUR (ETH/globex) ES 5m bars from the newest RawTickExporter CSV, for the
Halsey-style charts (his 15m chart is 24H, not RTH). Kept SEPARATE from the RTH
ticks_continuous pipeline — writes eminiaddict/data/es_5m_24h.parquet (gitignored).

5m bars are OPEN-labeled here (pipeline convention); the 15m display close-labels
(NT convention) at render time. Usage: python build_24h_bars.py [days_back]
"""
import glob
import os
import pathlib
import sys
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "eminiaddict" / "data" / "es_5m_24h.parquet"
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 20


def main():
    csv = max(glob.glob(str(ROOT / "data" / "nt_ticks" / "ES_09-26_ticks_*.csv")),
              key=os.path.getmtime)
    print("source:", os.path.basename(csv))
    cutoff = None
    parts = []
    # chunked read (file is tens of millions of rows)
    for ch in pd.read_csv(csv, usecols=["Time", "Price", "Volume"], parse_dates=["Time"],
                          chunksize=2_000_000):
        if cutoff is None:
            cutoff = ch["Time"].max()  # provisional; fixed after first read below
        parts.append(ch)
    df = pd.concat(parts, ignore_index=True)
    df = df.dropna().sort_values("Time")
    hi = df["Time"].max()
    df = df[df["Time"] >= hi - pd.Timedelta(days=DAYS)]
    print(f"{len(df):,} ticks  {df.Time.min()} .. {df.Time.max()} (last {DAYS}d, 24H)")
    b = (df.set_index("Time").resample("5min", closed="left", label="left")  # OPEN-labeled 5m
         .agg(Open=("Price", "first"), High=("Price", "max"), Low=("Price", "min"),
              Close=("Price", "last"), Volume=("Volume", "sum")).dropna().reset_index()
         .rename(columns={"Time": "DateTime"}))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    b.to_parquet(OUT, index=False)
    print(f"wrote {OUT}  ({len(b)} 5m bars, {b.DateTime.min()} .. {b.DateTime.max()})")


if __name__ == "__main__":
    main()
