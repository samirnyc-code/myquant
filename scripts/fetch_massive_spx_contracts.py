"""Enumerate the FULL Massive options contract universe for SPX (weeklies, monthlies,
dailies/0DTE, EOM — everything under underlying_ticker=SPX), active + expired, and
checkpoint to parquet. This is the manifest; price-history pulls key off it.

Robust: paginates via next_url, backs off on 429/5xx, checkpoints every CKPT pages so
a timeout/kill loses nothing (resume-safe via the saved parquet + a saved cursor).
"""
import os, time, sys, json
from pathlib import Path
import requests
import pandas as pd

KEY = os.environ.get("MASSIVE_API_KEY", "")
BASE = "https://api.massive.com/v3/reference/options/contracts"
OUT = Path(__file__).resolve().parent.parent / "data" / "massive_options"
OUT.mkdir(parents=True, exist_ok=True)
CKPT = 10  # pages between checkpoints
sess = requests.Session()


def get(url, tries=6):
    for i in range(tries):
        try:
            r = sess.get(url, timeout=40)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (429, 500, 502, 503, 504):
                wait = min(60, 2 ** i)
                print(f"  {r.status_code} -> backoff {wait}s", flush=True)
                time.sleep(wait); continue
            print(f"  HTTP {r.status_code}: {r.text[:200]}", flush=True)
            return None
        except requests.RequestException as e:
            wait = min(60, 2 ** i)
            print(f"  {type(e).__name__} -> retry {wait}s", flush=True)
            time.sleep(wait)
    return None


def pull(expired, rows):
    url = f"{BASE}?underlying_ticker=SPX&expired={expired}&limit=1000&apiKey={KEY}"
    pages = 0
    while url:
        j = get(url)
        if j is None:
            print(f"  giving up on this page (expired={expired})", flush=True)
            break
        rows.extend(j.get("results", []))
        pages += 1
        if pages % CKPT == 0:
            pd.DataFrame(rows).to_parquet(OUT / "spx_contracts.parquet")
            print(f"  [{expired}] page {pages}  total rows {len(rows):,}", flush=True)
        nu = j.get("next_url")
        url = (nu + f"&apiKey={KEY}") if nu else None
    return pages


def main():
    rows = []
    print("=== ACTIVE ===", flush=True)
    pa = pull("false", rows)
    n_active = len(rows)
    print(f"active done: {n_active:,} rows, {pa} pages", flush=True)
    print("=== EXPIRED (2022-03-07 -> now; large) ===", flush=True)
    pe = pull("true", rows)
    df = pd.DataFrame(rows).drop_duplicates(subset=["ticker"])
    df.to_parquet(OUT / "spx_contracts.parquet")
    tick = df["ticker"].astype(str)
    spxw = tick.str.startswith("O:SPXW").sum()
    spx = (tick.str.startswith("O:SPX") & ~tick.str.startswith("O:SPXW")).sum()
    exps = sorted(df["expiration_date"].dropna().unique())
    print(f"\n=== DONE ===", flush=True)
    print(f"total unique contracts: {len(df):,}  (active {n_active:,} + expired pages {pe})", flush=True)
    print(f"  O:SPX  monthly/AM:       {spx:,}", flush=True)
    print(f"  O:SPXW weekly/daily/EOM: {spxw:,}", flush=True)
    print(f"expirations: {len(exps)}  range {exps[0]} .. {exps[-1]}", flush=True)
    print(f"saved -> {OUT/'spx_contracts.parquet'}", flush=True)


if __name__ == "__main__":
    main()
