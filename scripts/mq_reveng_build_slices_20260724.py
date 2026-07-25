"""mq_reveng_build_slices_20260724.py — shared intermediate for the MQ level
reverse-engineering agents: per (tradeDate, expirDate, strike) chain slice for every
date in the MQ overlap, so spec-search variants are cheap reweightings.

Output: data/regime/mq_reveng/chain_slices_overlap.parquet
        data/regime/mq_reveng/mq_truth.csv  (per-overlap-day MQ levels + spot)
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "regime" / "mq_reveng"
OUT.mkdir(parents=True, exist_ok=True)

mq = pd.read_csv(ROOT / "data" / "menthorq" / "SPX_mq_levels_history.csv")
mq["eod_date"] = pd.to_datetime(mq["eod_date"]).dt.date
mq = mq.drop_duplicates("eod_date", keep="last")
dates = set(mq["eod_date"])

COLS = ["tradeDate", "expirDate", "dte", "strike",
        "callOpenInterest", "putOpenInterest", "gamma", "delta", "spotPrice"]
parts = []
for p in sorted((ROOT / "data" / "orats" / "SPX").glob("SPX_*.parquet")):
    year = int(p.stem.split("_")[1])
    if year < 2021:
        continue
    df = pd.read_parquet(p, columns=COLS)
    df["tradeDate"] = pd.to_datetime(df["tradeDate"]).dt.date
    df = df[df["tradeDate"].isin(dates)]
    parts.append(df)
    print(f"{p.name}: kept {len(df):,} rows")

sl = pd.concat(parts, ignore_index=True)
sl.to_parquet(OUT / "chain_slices_overlap.parquet", index=False)
truth = mq[mq["eod_date"].isin(set(sl["tradeDate"]))]
truth.to_csv(OUT / "mq_truth.csv", index=False)
print(f"slices: {len(sl):,} rows, {sl['tradeDate'].nunique()} days -> {OUT}")
print(f"truth: {len(truth)} days, cols={list(truth.columns)}")
