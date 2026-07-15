"""Repair roll-adjustment misalignment (S73 night — CRITICAL FIX).

data/bars/_continuous.parquet is BACK-ADJUSTED: older bars are shifted by
cumulative roll gaps (+263pts at 2025-07 vs actual). MenthorQ levels are struck
in actual front-contract prices, so every bar-vs-level study needs UNADJUSTED bars.

Method: Yahoo ES=F daily history = actual (unadjusted) front-contract closes.
Per-session offset = continuous 15:59 close - actual close (constant intraday,
steps at rolls). Writes data/bars/_continuous_unadj.parquet (5M, price-repaired)
and data/bars/es_offsets.csv for audit.

Run: .venv/Scripts/python.exe scripts/es_unadjust.py
"""
import datetime as dt
import json
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")


def yahoo_es_daily():
    req = urllib.request.Request(
        "https://query1.finance.yahoo.com/v8/finance/chart/ES%3DF?range=10y&interval=1d",
        headers={"User-Agent": "Mozilla/5.0"})
    r = json.loads(urllib.request.urlopen(req, timeout=30).read())["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    return pd.DataFrame({
        "date": [dt.datetime.fromtimestamp(t, ET).date().isoformat() for t in r["timestamp"]],
        "actual_close": q["close"]}).dropna()


def main():
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    y = yahoo_es_daily()
    # continuous session close (last bar of RTH session, CT 15:10 last)
    cont_close = b.groupby("date").Close.last().rename("cont_close").reset_index()
    m = cont_close.merge(y, on="date", how="inner")
    m["offset"] = (m.cont_close - m.actual_close).round(2)
    # offset should be a step function (constant between rolls) — smooth single-day
    # noise (yahoo close timing vs 15:10 bar) with a rolling median
    m["offset_s"] = m.offset.rolling(5, center=True, min_periods=1).median().round(2)
    m[["date", "cont_close", "actual_close", "offset", "offset_s"]].to_csv(
        ROOT / "data" / "bars" / "es_offsets.csv", index=False)
    off = dict(zip(m.date, m.offset_s))
    b = b[b.date.isin(off)].copy()
    shift = b.date.map(off)
    for c in ("Open", "High", "Low", "Close"):
        b[c] = b[c] - shift
    out = ROOT / "data" / "bars" / "_continuous_unadj.parquet"
    b.drop(columns=["date"]).to_parquet(out, index=False)
    print(f"offsets: {m.offset_s.min():+.1f} .. {m.offset_s.max():+.1f} over {len(m)} sessions")
    print(f"sample: {m.iloc[0].date} {m.iloc[0].offset_s:+.1f} | "
          f"{m.iloc[len(m)//2].date} {m.iloc[len(m)//2].offset_s:+.1f} | "
          f"{m.iloc[-1].date} {m.iloc[-1].offset_s:+.1f}")
    print(f"wrote {out} ({len(b):,} bars, price-repaired)")


if __name__ == "__main__":
    main()
