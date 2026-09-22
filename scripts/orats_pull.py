"""ORATS historical chain puller (S75 rewrite) — partitioned, holiday-free, resumable.

1 request = 1 ticker-tradeDate (full chain). Quota 20,000 req/month, 1,000/min.
Endpoint: /datav2/hist/strikes (Delayed tier), OI+greeks back to 2007. Token in
scratchpad/orats_token.txt (gitignored).

⚠️ ORATS carries EQUITY / INDEX / ETF options only — NO futures options. So the
MenthorQ futures/commodity tickers can only be PROXIED (see INSTRUMENTS below):
NQ1!→NDX and RTY1!→RUT are illiquid indices (noisy, ~4/10 walls); CL1!→USO and
GC1!→GLD are ETF proxies at a different scale (weak — a "build-our-own" story, not
an MQ match). Clean reproduction = SPX + the 7 mega-cap equities.

DATE SOURCE per instrument:
  default            the session dates MenthorQ has for that instrument's mq_key
                     (data/menthorq/<key>_mq_levels_history.csv) — NO holidays,
                     matches the calibration overlap.
  --from / --to      business-day range instead (deep pre-MQ history back to 2007).
                     NOTE holidays in a bday range still cost an (empty) request.

STORAGE: data/orats/<ORATS_TICKER>/<TICKER>_<YEAR>.parquet — pruned to 16 cols,
downcast (float32/int32/int16), zstd. ~0.5 MB per SPX day (5.6x smaller than raw).
Per-year files → cheap appends (no whole-ticker rewrite as history grows).
Coverage tracked in data/orats/_coverage.json for instant resume.

Usage (does NOT run until invoked):
  # the clean calibration set (SPX + 7 equities), MQ-overlap dates:
  .venv/Scripts/python.exe scripts/orats_pull.py --set calibration-liquid
  # one instrument, smoke test:
  .venv/Scripts/python.exe scripts/orats_pull.py --instr SPX --limit 5
  # deep pre-MQ history for SPX back to 2007:
  .venv/Scripts/python.exe scripts/orats_pull.py --instr SPX --from 2007-01-03 --to 2021-09-24
  ...add --dry-run to preview the plan (dates + request/size estimate), no requests.
"""
import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "orats"
COVERAGE = OUT / "_coverage.json"
TOKEN_FILE = ROOT / "scratchpad" / "orats_token.txt"
MENTHORQ = ROOT / "data" / "menthorq"
BASE = "https://api.orats.io/datav2/hist/strikes"
QUOTA = 20_000

# canonical -> (orats_ticker, mq_date_key, kind, ~rows/day, note)
INSTRUMENTS = {
    "SPX":   ("SPX",   "SPX",   "index",       14600, "clean - SPX index options ARE the S&P basket"),
    "XSP":   ("XSP",   "XSP",   "index",        4000, "Mini-SPX (1/10 SPX) — small-size vehicle, data to 2007"),
    "VIX":   ("VIX",   "VIX",   "index",         400, "VIX options — vol/tail-hedge strategies, data to 2007"),
    "AAPL":  ("AAPL",  "AAPL",  "equity",       1800, "clean (validated)"),
    "AMZN":  ("AMZN",  "AMZN",  "equity",       2200, "clean"),
    "GOOGL": ("GOOGL", "GOOGL", "equity",       2000, "clean"),
    "META":  ("META",  "META",  "equity",       2400, "clean"),
    "MSFT":  ("MSFT",  "MSFT",  "equity",       2200, "clean"),
    "NVDA":  ("NVDA",  "NVDA",  "equity",       3000, "clean"),
    "TSLA":  ("TSLA",  "TSLA",  "equity",       3200, "clean"),
    # proxies — reproduce MenthorQ futures/commodity levels only approximately
    "NQ":    ("NDX",   "NQ1!",  "index-proxy",  7700, "NDX illiquid -> MQ NQ noisy (~4/10 walls)"),
    "RTY":   ("RUT",   "RTY1!", "index-proxy",  6000, "Russell index options thin — expect noise"),
    "ES":    ("SPX",   "ES1!",  "dup",         14600, "ES~=SPX - REDUNDANT with SPX, skip"),
    "CL":    ("USO",   "CL1!",  "etf-proxy",    3000, "USO != front crude; scale differs — weak"),
    "GC":    ("GLD",   "GC1!",  "etf-proxy",    3000, "GLD ~$300 vs GC ~$3000 (~10x scale) — weak"),
}
SETS = {
    "calibration-liquid": ["SPX", "AAPL", "AMZN", "GOOGL", "META", "MSFT", "NVDA", "TSLA"],
    "proxies": ["NQ", "RTY", "CL", "GC"],
    "all": [k for k in INSTRUMENTS if k != "ES"],
}
BYTES_PER_ROW = 489_062 / 14605  # measured: pruned+downcast+zstd SPX day

# pruned schema — everything needed for GEX self-compute + option-P&L backtests
KEEP = ["ticker", "tradeDate", "expirDate", "dte", "strike",
        "callOpenInterest", "putOpenInterest", "gamma", "delta",
        "callMidIv", "putMidIv", "callValue", "putValue",
        "stockPrice", "spotPrice", "expiryTod"]
F32 = ["strike", "gamma", "delta", "callMidIv", "putMidIv",
       "callValue", "putValue", "stockPrice", "spotPrice"]
I32 = ["callOpenInterest", "putOpenInterest"]
DEDUP = ["tradeDate", "expirDate", "strike", "expiryTod"]


def optimize(df):
    """Prune to KEEP, downcast, categorize — the on-disk schema."""
    df = df[[c for c in KEEP if c in df.columns]].copy()
    for c in F32:
        if c in df:
            v = pd.to_numeric(df[c], errors="coerce")
            with np.errstate(over="ignore"):   # old ORATS data has garbage >f32 max
                v = v.astype("float32")
            df[c] = v.replace([np.inf, -np.inf], np.nan)  # unstorable -> null (corrupt)
    for c in I32:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int32")
    if "dte" in df:
        df["dte"] = pd.to_numeric(df["dte"], errors="coerce").fillna(-1).astype("int16")
    for c in ("ticker", "expiryTod"):
        if c in df:
            df[c] = df[c].astype("category")
    for c in ("tradeDate", "expirDate"):
        if c in df:
            df[c] = df[c].astype("string")
    return df


def mq_dates(key):
    f = MENTHORQ / f"{key}_mq_levels_history.csv"
    if not f.exists():
        raise SystemExit(f"no MenthorQ history for --mq-dates {key} ({f} missing)")
    m = pd.read_csv(f, usecols=lambda c: c in ("session_date", "eod_date"))
    col = "eod_date" if "eod_date" in m.columns else "session_date"
    return sorted(d for d in m[col].dropna().astype(str).unique() if d)


def bday_dates(start, end):
    return pd.bdate_range(start, end).strftime("%Y-%m-%d").tolist()


def load_coverage():
    if COVERAGE.exists():
        try:
            return json.loads(COVERAGE.read_text())
        except Exception:
            pass
    return {}


def save_coverage(cov):
    COVERAGE.parent.mkdir(parents=True, exist_ok=True)
    COVERAGE.write_text(json.dumps(cov, indent=1))


def have_dates(ticker):
    """Dates already on disk for a ticker (coverage cache, else scan parquet)."""
    cov = load_coverage().get(ticker)
    if cov:
        return set(cov)
    have = set()
    d = OUT / ticker
    if d.exists():
        for f in d.glob(f"{ticker}_*.parquet"):
            try:
                have |= set(pd.read_parquet(f, columns=["tradeDate"]).tradeDate.astype(str).unique())
            except Exception:
                pass
    return have


def write_year(ticker, year, new_df):
    """Merge new_df into the ticker-year parquet (dedup), write zstd."""
    d = OUT / ticker
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{ticker}_{year}.parquet"
    if f.exists():
        new_df = pd.concat([pd.read_parquet(f), new_df], ignore_index=True)
    new_df = optimize(new_df).drop_duplicates(subset=DEDUP)
    new_df.to_parquet(f, index=False, compression="zstd")
    return f, len(new_df)


def resolve_instruments(args):
    names = list(args.instr or [])
    if args.set:
        if args.set not in SETS:
            raise SystemExit(f"--set must be one of {list(SETS)}")
        names += SETS[args.set]
    seen, out = set(), []
    for n in names:
        if n not in INSTRUMENTS:
            raise SystemExit(f"unknown instrument {n}; known: {list(INSTRUMENTS)}")
        if INSTRUMENTS[n][0] in seen:      # dedup by orats ticker (ES->SPX etc.)
            print(f"  skip {n}: ORATS ticker {INSTRUMENTS[n][0]} already in plan")
            continue
        seen.add(INSTRUMENTS[n][0])
        out.append(n)
    return out


def plan_dates(name, args):
    otkr, mqkey, kind, rpd, note = INSTRUMENTS[name]
    if args.frm:
        dates = bday_dates(args.frm, args.to or dt.date.today().isoformat())
    else:
        dates = mq_dates(mqkey)
    return otkr, kind, rpd, note, dates


def main():
    ap = argparse.ArgumentParser(description="ORATS historical chain puller")
    ap.add_argument("--instr", nargs="+", help=f"instrument(s): {list(INSTRUMENTS)}")
    ap.add_argument("--set", help=f"named set: {list(SETS)}")
    ap.add_argument("--from", dest="frm", help="bday range start (deep pre-MQ history)")
    ap.add_argument("--to", dest="to", help="bday range end YYYY-MM-DD")
    ap.add_argument("--limit", type=int, help="smoke test: only first N missing dates")
    ap.add_argument("--dry-run", action="store_true", help="print plan + estimates, no requests")
    args = ap.parse_args()
    if not (args.instr or args.set):
        raise SystemExit("need --instr NAME... or --set NAME")

    names = resolve_instruments(args)
    if not TOKEN_FILE.exists() and not args.dry_run:
        raise SystemExit(f"Put your ORATS API token in {TOKEN_FILE} first.")
    token = TOKEN_FILE.read_text().strip() if TOKEN_FILE.exists() else ""

    cov = load_coverage()
    total_req = 0
    grand_req = grand_bytes = 0
    for name in names:
        otkr, kind, rpd, note, dates = plan_dates(name, args)
        have = have_dates(otkr)
        todo = [d for d in dates if d not in have]
        if args.limit:
            todo = todo[:args.limit]
        est_bytes = len(todo) * rpd * BYTES_PER_ROW
        grand_req += len(todo)
        grand_bytes += est_bytes
        print(f"\n{name} -> ORATS {otkr} [{kind}]  {note}")
        print(f"  {len(todo)} dates to pull ({len(have)} on disk, {len(dates)} in plan)"
              f"  ~{est_bytes/1e6:.0f} MB, {len(todo)} req ({len(todo)/QUOTA*100:.1f}% quota)")
        if args.dry_run:
            print(f"  first: {todo[:3]}  last: {todo[-3:] if todo else []}")
            continue
        by_year, got = {}, set()

        def flush():
            """Write buffered years to disk + checkpoint coverage (crash-safe)."""
            for yr, frames in by_year.items():
                f, n = write_year(otkr, yr, pd.concat(frames, ignore_index=True))
                print(f"  wrote {f.relative_to(ROOT)} ({n:,} rows)")
            by_year.clear()
            cov[otkr] = sorted(set(cov.get(otkr, [])) | have | got)
            save_coverage(cov)

        for i, d in enumerate(todo):
            try:
                r = requests.get(BASE, params={"token": token, "ticker": otkr,
                                               "tradeDate": d}, timeout=90)
            except requests.RequestException as e:
                print(f"  {d}: network error {e} — retry in 10s")
                time.sleep(10)
                continue
            total_req += 1
            if r.status_code == 429:
                print("  rate limited — sleeping 65s")
                time.sleep(65)
                continue
            if r.status_code in (401, 403):
                raise SystemExit(f"auth error: {r.text[:200]}")
            if r.status_code != 200:
                print(f"  {d}: HTTP {r.status_code} {r.text[:120]}")
                continue
            data = r.json().get("data", [])
            got.add(d)  # a real (even if empty) response = covered
            if data:
                by_year.setdefault(d[:4], []).append(optimize(pd.DataFrame(data)))
            if (i + 1) % 100 == 0:
                print(f"  ...{i + 1}/{len(todo)} ({total_req} req, "
                      f"~{total_req/QUOTA*100:.1f}% quota) — checkpoint", flush=True)
                flush()          # crash-safe: persist + checkpoint every 100 dates
                time.sleep(1)
        flush()                  # final partial batch
        print(f"  coverage: {len(cov[otkr])} dates on disk")
    if args.dry_run:
        print(f"\nPLAN TOTAL - {grand_req} requests ({grand_req/QUOTA*100:.1f}% of "
              f"{QUOTA:,}/mo), ~{grand_bytes/1e9:.2f} GB on disk")
    else:
        print(f"\nDONE - {total_req} requests this run "
              f"(~{total_req/QUOTA*100:.1f}% of {QUOTA:,}/mo quota)")


if __name__ == "__main__":
    main()
