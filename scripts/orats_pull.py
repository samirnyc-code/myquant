"""ORATS historical chain puller (S73) — READY FOR PURCHASE DAY.

Verified 2026-07-15: the $99/mo "Delayed" Data API tier includes /datav2/hist/strikes
back to 2007 with callOpenInterest/putOpenInterest. Quota 20,000 requests/month,
1 request = one ticker-tradeDate (rate limit 1,000/min).

Budget plan (fits ONE $99 month): 14 tickers x 2021-01-04..today ≈ 19.4k requests.
For 2007+ depth use the $599 one-time bulk FTP instead (all symbols).

Usage (after subscribing, put the API token in scratchpad/orats_token.txt — gitignored):
  .venv/Scripts/python.exe scripts/orats_pull.py --from 2021-01-04
Writes one parquet per ticker: data/orats/chains_<TICKER>.parquet (append/dedup safe,
resumable — reruns skip already-pulled dates). Tracks request count vs quota.
"""
import datetime as dt
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "orats"
TOKEN_FILE = ROOT / "scratchpad" / "orats_token.txt"
TICKERS = ["SPX", "SPY", "QQQ", "NDX", "GLD", "DIA", "USO",
           "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
BASE = "https://api.orats.io/datav2/hist/strikes"
KEEP = ["ticker", "tradeDate", "expirDate", "dte", "strike",
        "callVolume", "callOpenInterest", "callBidPrice", "callAskPrice",
        "putVolume", "putOpenInterest", "putBidPrice", "putAskPrice",
        "callMidIv", "putMidIv", "delta", "gamma", "theta", "vega",
        "stockPrice", "spotPrice"]


def trading_days(start):
    import numpy as np
    days = pd.bdate_range(start, dt.date.today()).strftime("%Y-%m-%d").tolist()
    return days


def main():
    if not TOKEN_FILE.exists():
        raise SystemExit(f"Put your ORATS API token in {TOKEN_FILE} first.")
    token = TOKEN_FILE.read_text().strip()
    start = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else "2021-01-04"
    OUT.mkdir(parents=True, exist_ok=True)
    days = trading_days(start)
    total_req = 0
    for tkr in TICKERS:
        f = OUT / f"chains_{tkr}.parquet"
        have = set()
        if f.exists():
            have = set(pd.read_parquet(f, columns=["tradeDate"]).tradeDate.unique())
        todo = [d for d in days if d not in have]
        print(f"{tkr}: {len(todo)} days to pull ({len(have)} already on disk)")
        buf = []
        for i, d in enumerate(todo):
            r = requests.get(BASE, params={"token": token, "ticker": tkr, "tradeDate": d},
                             timeout=60)
            total_req += 1
            if r.status_code == 200:
                data = r.json().get("data", [])
                if data:
                    df = pd.DataFrame(data)
                    buf.append(df[[c for c in KEEP if c in df.columns]])
            elif r.status_code == 429:
                print("  rate limited — sleeping 65s")
                time.sleep(65)
            elif r.status_code in (401, 403):
                raise SystemExit(f"auth error: {r.text[:200]}")
            # holidays return empty -> fine
            if i % 100 == 99:
                print(f"  ...{i + 1}/{len(todo)} ({total_req} total requests)", flush=True)
                time.sleep(1)
        if buf:
            new = pd.concat(buf, ignore_index=True)
            if f.exists():
                new = pd.concat([pd.read_parquet(f), new], ignore_index=True)
                new = new.drop_duplicates(subset=["tradeDate", "expirDate", "strike"])
            new.to_parquet(f, index=False)
            print(f"  wrote {f.name}: {len(new):,} rows")
    print(f"\nDONE — {total_req} requests used this run (quota 20k/month)")


if __name__ == "__main__":
    main()
