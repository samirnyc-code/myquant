#!/usr/bin/env python3
"""
scripts/fetch_for_nt.py — Fetch Massive.io ES tick data and write NT8 import files.

Fetches all trades for one ES contract, caches to parquet, and writes an
NT8-compatible import file (e.g. "ES_MAS 06-26.Last.txt").

Usage
-----
    1. Set API_KEY, TICKER, DATE_START, DATE_END in the Config section below.
    2. python scripts/fetch_for_nt.py

    To re-fetch (ignore cache): delete  <OUTPUT_DIR>/cache/<TICKER>.parquet

Output
------
    <OUTPUT_DIR>/ES_MAS MM-YY.Last.txt    — NT8 tick import file
    <OUTPUT_DIR>/cache/<TICKER>.parquet   — local cache (skip API on re-run)

NT8 import steps (after running this script)
--------------------------------------------
    Tools > Historical Data Manager > Import tab
    File: select the .Last.txt file above
    Timezone: Central Time (US & Canada)
"""

import os
import requests
import pandas as pd

# ── Config ───────────────────────────────────────────────────────────────────
API_KEY    = "YOUR_API_KEY_HERE"   # TODO: fill in when key arrives Monday
TICKER     = "ESM6"                # Massive.io ticker (confirm exact format with API)
DATE_START = "2026-03-17"          # session_end_date inclusive, YYYY-MM-DD
DATE_END   = "2026-06-20"          # session_end_date inclusive, YYYY-MM-DD
OUTPUT_DIR = r"C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\MAS_Import"

BASE_URL   = "https://api.massive.com"  # confirmed from AAPL test
PAGE_LIMIT = 49_999
# ─────────────────────────────────────────────────────────────────────────────

_MONTH_TO_NUM = {"H": 3, "M": 6, "U": 9, "Z": 12}


def _auth_params() -> dict:
    # Auth confirmed from AAPL test: apiKey as query param, not a header.
    return {"apiKey": API_KEY}


def get_contract_info(ticker: str) -> dict:
    """Return contract record from Contracts API (first_trade_date, last_trade_date, etc.).
    TODO: confirm futures endpoint path (/futures/v1/ vs /v2/) with live key.
    """
    resp = requests.get(
        f"{BASE_URL}/futures/v1/contracts",
        params={"ticker.any_of": ticker, **_auth_params()},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"No contract found for ticker '{ticker}'")
    return results[0]


def ticker_to_nt_name(ticker: str, first_trade_date: str) -> str:
    """
    Convert Massive ticker + contract start date → NT8 instrument contract name.
    'ESM6' + '2026-03-17' → 'ES_MAS 06-26'
    Uses first_trade_date for unambiguous year (avoids single-digit year guessing).
    """
    month_code = ticker[2]                   # 'M'
    month_num  = _MONTH_TO_NUM[month_code]   # 6
    year       = int(first_trade_date[:4])   # 2026
    return f"ES_MAS {month_num:02d}-{year % 100:02d}"


def fetch_all_trades(ticker: str, date_start: str, date_end: str) -> pd.DataFrame:
    """
    Paginate Trades API and return DataFrame with columns:
        timestamp_ns (int64), price (float64), size (int64)

    Filters: correction == 0 only (cancelled/corrected trades excluded).
    """
    url    = f"{BASE_URL}/futures/v1/trades/{ticker}"
    # TODO: confirm futures trades endpoint path (/futures/v1/ vs /v2/) with live key.
    # TODO: confirm date filter param names (session_end_date.gte vs timestamp.gte).
    params = {
        "session_end_date.gte": date_start,
        "session_end_date.lte": date_end,
        "limit":                PAGE_LIMIT,
        "sort":                 "asc",  # confirmed from AAPL test
        **_auth_params(),
    }

    rows = []
    page = 0
    while url:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        body = resp.json()

        for t in body.get("results", []):
            if t.get("correction", 0) != 0:
                continue
            rows.append((int(t["timestamp"]), float(t["price"]), int(t["size"])))

        url    = body.get("next_url")   # None on last page
        params = {}                     # next_url already encodes all params
        page  += 1
        print(f"  page {page:3d}: {len(rows):>10,} ticks so far")

    df = pd.DataFrame(rows, columns=["timestamp_ns", "price", "size"])
    df.sort_values("timestamp_ns", inplace=True, ignore_index=True)
    return df


def write_nt_file(df: pd.DataFrame, output_path: str) -> None:
    """
    Write NT8 import file: one tick per line, format yyyyMMdd HHmmss;price;volume
    Timestamps converted from nanosecond UTC → Central Time (CT).
    """
    dt_ct    = pd.to_datetime(df["timestamp_ns"], unit="ns", utc=True).dt.tz_convert("America/Chicago")
    dt_str   = dt_ct.dt.strftime("%Y%m%d %H%M%S")
    price_str = df["price"].map("{:.2f}".format)
    size_str  = df["size"].astype(str)

    lines = (dt_str + ";" + price_str + ";" + size_str + "\n").tolist()
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"  wrote {len(df):,} ticks → {output_path}")


def main():
    print(f"Fetching {TICKER}  {DATE_START} → {DATE_END}")
    print(f"Output:  {OUTPUT_DIR}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cache_dir = os.path.join(OUTPUT_DIR, "cache")
    os.makedirs(cache_dir, exist_ok=True)

    # ── Contract metadata ────────────────────────────────────────────────────
    print("\nLooking up contract...")
    contract = get_contract_info(TICKER)
    nt_name  = ticker_to_nt_name(TICKER, contract["first_trade_date"])
    print(f"  {TICKER}: {contract['first_trade_date']} – {contract['last_trade_date']}")
    print(f"  NT name: {nt_name}")

    # ── Fetch or load cache ──────────────────────────────────────────────────
    cache_path = os.path.join(cache_dir, f"{TICKER}.parquet")
    if os.path.exists(cache_path):
        print(f"\nLoading from cache: {cache_path}")
        df = pd.read_parquet(cache_path)
        print(f"  {len(df):,} ticks loaded")
    else:
        print("\nFetching from API (this may take a while for large date ranges)...")
        df = fetch_all_trades(TICKER, DATE_START, DATE_END)
        df.to_parquet(cache_path, index=False, compression="snappy")
        print(f"  cached → {cache_path}")

    # ── Write NT import file ─────────────────────────────────────────────────
    print(f"\nWriting NT import file...")
    nt_path = os.path.join(OUTPUT_DIR, f"{nt_name}.Last.txt")
    write_nt_file(df, nt_path)

    print("\nDone.")
    print(f"NT import file: {nt_path}")
    print("Next: Tools > Historical Data Manager > Import tab in NT8")
    print("      Timezone: Central Time (US & Canada)")


if __name__ == "__main__":
    main()
