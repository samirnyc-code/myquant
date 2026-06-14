#!/usr/bin/env python3
"""
scripts/fetch_for_nt_flatfiles.py — Download Massive.io flat files and write NT8 import file.

Downloads daily gzip CSVs from Massive S3, filters for one ES contract ticker,
filters RTH, and writes an NT8-compatible tick import file (e.g. "ES_MAS 06-26.Last.txt").

Usage
-----
    1. Set TICKER, DATE_START, DATE_END in Config section below.
    2. python scripts/fetch_for_nt_flatfiles.py

    Files already in DOWNLOAD_DIR are reused — delete them to force re-download.

Output
------
    <DOWNLOAD_DIR>/<YYYY-MM-DD>.csv.gz     — raw daily flat files (kept for reuse)
    <OUTPUT_DIR>/ES_MAS MM-YY.Last.txt    — NT8 tick import file

NT8 import steps
----------------
    Tools > Historical Data Manager > Import tab
    File: select the .Last.txt file
    Timezone: Central Time (US & Canada)
"""

import gzip
import io
import os
from datetime import date, timedelta

import boto3
import pandas as pd
from botocore.config import Config

# ── Config ────────────────────────────────────────────────────────────────────
AWS_ACCESS_KEY_ID     = "d0e1191e-61c3-454b-adcb-5bea8e9e9c6a"
AWS_SECRET_ACCESS_KEY = "4aTW6AdSEwulL86_kJnNupQppKxSgwXw"
ENDPOINT_URL          = "https://files.massive.com"
BUCKET                = "flatfiles"
PREFIX                = "us_futures_cme/trades_v1"

TICKER     = "ESM6"
DATE_START = "2026-06-12"   # YYYY-MM-DD, inclusive
DATE_END   = "2026-06-13"   # YYYY-MM-DD, inclusive — expand to full contract once confirmed

NT_NAME    = "ES_MAS 06-26"
OUTPUT_DIR = r"C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\MAS_Import"
DOWNLOAD_DIR = os.path.join(OUTPUT_DIR, "flatfiles_cache")

# ─────────────────────────────────────────────────────────────────────────────


def make_s3():
    session = boto3.Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )
    return session.client(
        "s3",
        endpoint_url=ENDPOINT_URL,
        config=Config(signature_version="s3v4"),
    )


def date_range(start: str, end: str):
    d = date.fromisoformat(start)
    stop = date.fromisoformat(end)
    while d <= stop:
        yield d
        d += timedelta(days=1)


def s3_key(d: date) -> str:
    return f"{PREFIX}/{d.year}/{d.month:02d}/{d.isoformat()}.csv.gz"


def download_day(s3, d: date, download_dir: str) -> str | None:
    """Download one daily flat file; returns local path or None if file not found."""
    local_path = os.path.join(download_dir, f"{d.isoformat()}.csv.gz")
    if os.path.exists(local_path):
        print(f"  {d.isoformat()} — cached")
        return local_path

    key = s3_key(d)
    try:
        s3.download_file(BUCKET, key, local_path)
        print(f"  {d.isoformat()} — downloaded")
        return local_path
    except Exception as e:
        if "404" in str(e) or "NoSuchKey" in str(e):
            print(f"  {d.isoformat()} — not found (weekend/holiday), skipping")
            return None
        raise


def load_day(local_path: str, ticker: str, debug_first: bool = False) -> pd.DataFrame:
    """Read one gzip CSV, filter for ticker, return raw DataFrame."""
    with gzip.open(local_path, "rb") as f:
        raw = f.read()

    df = pd.read_csv(io.BytesIO(raw))

    if debug_first:
        print(f"  [DEBUG] columns: {list(df.columns)}")
        print(f"  [DEBUG] first row: {df.iloc[0].to_dict()}")
        print(f"  [DEBUG] total rows in file: {len(df):,}")

    df = df[df["ticker"] == ticker].copy()
    return df


def process_day(df: pd.DataFrame) -> pd.DataFrame:
    """Return all ticks with timestamps in CT. No RTH filter — NT's session template handles boundaries.
    Import into NT as 'Central Time (US & Canada)' so NT stores ticks at the correct CT time.
    """
    dt_ct = (
        pd.to_datetime(df["timestamp"], unit="ns", utc=True)
        .dt.tz_convert("America/Chicago")
        .dt.tz_localize(None)
    )
    return pd.DataFrame({
        "DateTime": dt_ct,
        "Price":    df["price"].astype(float).values,
        "Volume":   df["size"].astype(int).values,
    })


def write_nt_file(df: pd.DataFrame, output_path: str) -> None:
    """Write NT8 tick import file: yyyyMMdd HHmmss;price;volume per line."""
    dt_str    = df["DateTime"].dt.strftime("%Y%m%d %H%M%S")
    price_str = df["Price"].map("{:.2f}".format)
    size_str  = df["Volume"].astype(str)
    lines = (dt_str + ";" + price_str + ";" + size_str + "\n").tolist()
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"  wrote {len(df):,} ticks to {output_path}")


def main():
    print(f"Ticker:  {TICKER}  ({DATE_START} to {DATE_END})")
    print(f"NT name: {NT_NAME}")
    print(f"Output:  {OUTPUT_DIR}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    s3 = make_s3()

    print("\nDownloading flat files...")
    all_frames = []
    first_file = True

    for d in date_range(DATE_START, DATE_END):
        local_path = download_day(s3, d, DOWNLOAD_DIR)
        if local_path is None:
            continue
        day_df = load_day(local_path, TICKER, debug_first=first_file)
        first_file = False
        rth_df = process_day(day_df)
        print(f"    {d.isoformat()}: {len(day_df):,} raw ticks, {len(rth_df):,} RTH ticks")
        all_frames.append(rth_df)

    if not all_frames:
        print("No data found.")
        return

    result = pd.concat(all_frames, ignore_index=True)
    result.sort_values("DateTime", inplace=True, ignore_index=True)
    print(f"\nTotal RTH ticks: {len(result):,}")
    print(f"Date range:      {result['DateTime'].iloc[0]} to {result['DateTime'].iloc[-1]}")
    print(f"Price range:     {result['Price'].min():.2f} to {result['Price'].max():.2f}")

    nt_path = os.path.join(OUTPUT_DIR, f"{NT_NAME}.Last.txt")
    print(f"\nWriting NT import file...")
    write_nt_file(result, nt_path)

    print(f"\nDone. NT import file: {nt_path}")
    print("Next: Tools > Historical Data Manager > Import tab in NT8")
    print("      Format: NinjaTrader, Data Type: Last, Timezone: Central Time (US & Canada)")


if __name__ == "__main__":
    main()
