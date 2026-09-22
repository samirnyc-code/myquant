"""Build a CURRENT ES 5m dataset for the fib tool by extending the base history
(_db_es_5m_rth, ends ~07-24) with fresh NT8 tick exports (data/nt_ticks/*.csv,
Time,Price,Volume). Writes eminiaddict/data/es_5m_current.parquet, which fib_tool.py
prefers if present. Re-run after dropping a new tick file (e.g. the 07-31 session).

Usage: python build_current_bars.py
"""
import glob
import os
import pathlib
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = ROOT / "data" / "bars" / "_db_es_5m_rth.parquet"
TICKS = ROOT / "data" / "nt_ticks"
OUT = ROOT / "eminiaddict" / "data" / "es_5m_current.parquet"


def ticks_to_5m():
    frames = []
    for f in sorted(glob.glob(str(TICKS / "ES_*ticks*.csv"))):
        try:
            t = pd.read_csv(f, parse_dates=["Time"])
        except Exception as e:
            print(f"  skip {os.path.basename(f)}: {e}"); continue
        if not {"Time", "Price", "Volume"} <= set(t.columns):
            continue
        frames.append(t[["Time", "Price", "Volume"]])
    if not frames:
        return None
    tk = pd.concat(frames).dropna().sort_values("Time")
    tk = tk.drop_duplicates(subset=["Time", "Price", "Volume"])
    b = (tk.set_index("Time").resample("5min")
         .agg(Open=("Price", "first"), High=("Price", "max"),
              Low=("Price", "min"), Close=("Price", "last"), Volume=("Volume", "sum"))
         .dropna().reset_index().rename(columns={"Time": "DateTime"}))
    return b


def main():
    base = pd.read_parquet(BASE)[["DateTime", "Open", "High", "Low", "Close", "Volume"]]
    base_end = base["DateTime"].max()
    print(f"base: {len(base)} bars .. {base_end}")
    tb = ticks_to_5m()
    if tb is None or tb.empty:
        print("no tick bars found; writing base only")
        merged = base
    else:
        print(f"tick 5m: {len(tb)} bars {tb.DateTime.min()} .. {tb.DateTime.max()}")
        newer = tb[tb["DateTime"] > base_end]                 # only extend beyond base
        print(f"appending {len(newer)} bars after {base_end}")
        merged = (pd.concat([base, newer]).drop_duplicates(subset=["DateTime"])
                  .sort_values("DateTime").reset_index(drop=True))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    merged.to_parquet(OUT, index=False)
    print(f"wrote {OUT}  ({len(merged)} bars, ends {merged.DateTime.max()})")


if __name__ == "__main__":
    main()
