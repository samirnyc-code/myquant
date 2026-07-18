"""Pull 5m bars from MenthorQ's candles API for the stock panel (S73).
~6 months of history available (floor ~2026-01-08). No roll adjustment needed
for equities — prices are the actual prices the levels are struck on.

Writes data/bars/stocks/<TICKER>_5m.parquet (idempotent merge).
Run: .venv/Scripts/python.exe scripts/mq_candles_pull.py [--symbols AAPL,MSFT,...]
"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_api import MQ, GW

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "bars" / "stocks"
SYMS = (sys.argv[sys.argv.index("--symbols") + 1].split(",") if "--symbols" in sys.argv
        else ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    mq = MQ()
    now_ms = int(dt.datetime.now().timestamp() * 1000)
    frm_ms = now_ms - 220 * 24 * 3600 * 1000   # ask past the ~6mo floor
    for sym in SYMS:
        r = mq.s.get(f"{GW}/tickers/{sym}/candles",
                     headers={"authorization": mq.token},
                     params={"interval": "5m", "from": frm_ms, "to": now_ms,
                             "countBack": 50000}, timeout=120)
        if r.status_code != 200:
            print(f"{sym}: HTTP {r.status_code} {r.text[:100]}")
            continue
        c = r.json()
        if not c:
            print(f"{sym}: empty")
            continue
        df = pd.DataFrame(c)
        df["DateTime"] = pd.to_datetime(df.t, unit="ms")
        df = df.rename(columns={"o": "Open", "h": "High", "l": "Low",
                                "c": "Close", "v": "Volume"})
        df = df[["DateTime", "Open", "High", "Low", "Close", "Volume"]]
        f = OUT / f"{sym}_5m.parquet"
        if f.exists():
            old = pd.read_parquet(f)
            df = pd.concat([old, df]).drop_duplicates(subset=["DateTime"]).sort_values("DateTime")
        df.to_parquet(f, index=False)
        print(f"{sym}: {len(df):,} bars  {df.DateTime.min():%Y-%m-%d} .. {df.DateTime.max():%Y-%m-%d}")


if __name__ == "__main__":
    main()
