"""Pull historical 5-min stock bars from IB (S73). Free, deep, no roll issues.
Writes data/bars/stocks/<SYM>_5m_ib.parquet (idempotent merge).
Run: .venv/Scripts/python.exe scripts/ib_stock_bars.py AAPL [--months 13]
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
from ib_async import Stock

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "bars" / "stocks"
SYMS = [a for a in sys.argv[1:] if not a.startswith("--")] or ["AAPL"]
MONTHS = int(sys.argv[sys.argv.index("--months") + 1]) if "--months" in sys.argv else 13
BAR = sys.argv[sys.argv.index("--bar") + 1] if "--bar" in sys.argv else "5m"
# 1-min bars: IB caps duration per request lower -> pull in 5-day chunks
BAR_SETTING = {"5m": "5 mins", "1m": "1 min"}[BAR]
CHUNK = {"5m": "1 M", "1m": "5 D"}[BAR]
N_CHUNKS = {"5m": MONTHS, "1m": MONTHS * 5}[BAR]  # ~5 chunks (weeks) per month


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ib = ib_conn.connect()
    try:
        for sym in SYMS:
            c = Stock(sym, "SMART", "USD")
            ib.qualifyContracts(c)
            frames = []
            end = dt.datetime.now()
            for _ in range(N_CHUNKS):
                bars = ib.reqHistoricalData(
                    c, endDateTime=end.strftime("%Y%m%d %H:%M:%S US/Eastern"),
                    durationStr=CHUNK, barSizeSetting=BAR_SETTING,
                    whatToShow="TRADES", useRTH=True, formatDate=1)
                if not bars:
                    break
                df = pd.DataFrame([{"DateTime": b.date, "Open": b.open, "High": b.high,
                                    "Low": b.low, "Close": b.close, "Volume": b.volume}
                                   for b in bars])
                frames.append(df)
                end = pd.to_datetime(df.DateTime.min()).to_pydatetime() - dt.timedelta(minutes=5)
                print(f"  {sym}: +{len(df)} bars back to {df.DateTime.min()}", flush=True)
                ib.sleep(11)   # pacing: stay under 60 req / 10 min comfortably
            if frames:
                allb = pd.concat(frames, ignore_index=True)
                # IB returns tz-aware datetimes (mixed DST offsets) -> normalize to naive ET
                allb["DateTime"] = (pd.to_datetime(allb.DateTime, utc=True)
                                    .dt.tz_convert("US/Eastern").dt.tz_localize(None))
                allb = allb.drop_duplicates(subset=["DateTime"]).sort_values("DateTime")
                f = OUT / f"{sym}_{BAR}_ib.parquet"
                if f.exists():
                    allb = pd.concat([pd.read_parquet(f), allb]).drop_duplicates(
                        subset=["DateTime"]).sort_values("DateTime")
                allb.to_parquet(f, index=False)
                print(f"{sym}: {len(allb):,} bars total  "
                      f"{allb.DateTime.min()} .. {allb.DateTime.max()}")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
