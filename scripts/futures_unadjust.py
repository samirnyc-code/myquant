"""Generalized roll-adjustment repair (S73): any continuous futures parquet ->
unadjusted prices via Yahoo front-contract daily closes (per-day offset, median-
smoothed). Same method as es_unadjust.py, parameterized.

Run: .venv/Scripts/python.exe scripts/futures_unadjust.py NQ CL GC [YM]
Maps: NQ->_continuous_NQ.parquet/NQ=F, CL->CL=F, GC->GC=F, YM->YM=F, ES->ES=F.
Writes data/bars/_continuous_<SYM>_unadj.parquet + offsets_<SYM>.csv
"""
import datetime as dt
import json
import sys
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo("America/New_York")
FILES = {"ES": "_continuous.parquet", "NQ": "_continuous_NQ.parquet",
         "CL": "_continuous_CL.parquet", "GC": "_continuous_GC.parquet",
         "YM": "_continuous_YM.parquet"}


def yahoo_daily(tkr):
    req = urllib.request.Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{tkr}%3DF?range=2y&interval=1d",
        headers={"User-Agent": "Mozilla/5.0"})
    r = json.loads(urllib.request.urlopen(req, timeout=30).read())["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    return pd.DataFrame({
        "date": [dt.datetime.fromtimestamp(t, ET).date().isoformat() for t in r["timestamp"]],
        "actual_close": q["close"]}).dropna()


def repair(sym):
    src = ROOT / "data" / "bars" / FILES[sym]
    if not src.exists():
        print(f"{sym}: missing {src.name}")
        return
    b = pd.read_parquet(src)
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    y = yahoo_daily(sym)
    cont = b.groupby("date").Close.last().rename("cont_close").reset_index()
    m = cont.merge(y, on="date", how="inner")
    m["offset"] = (m.cont_close - m.actual_close)
    m["offset_s"] = m.offset.rolling(5, center=True, min_periods=1).median().round(4)
    m.to_csv(ROOT / "data" / "bars" / f"offsets_{sym}.csv", index=False)
    off = dict(zip(m.date, m.offset_s))
    b = b[b.date.isin(off)].copy()
    shift = b.date.map(off)
    for c in ("Open", "High", "Low", "Close"):
        b[c] = b[c] - shift
    out = ROOT / "data" / "bars" / f"_continuous_{sym}_unadj.parquet"
    b.drop(columns=["date"]).to_parquet(out, index=False)
    print(f"{sym}: offsets {m.offset_s.min():+.2f}..{m.offset_s.max():+.2f} over {len(m)}d "
          f"-> {out.name} ({len(b):,} bars)")


if __name__ == "__main__":
    for s in (sys.argv[1:] or ["NQ", "CL", "GC"]):
        repair(s.upper())
