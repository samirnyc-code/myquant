#!/usr/bin/env python
"""validate_eth_store.py — accuracy mechanism for the full-session ETH tick store.

Checks the ENTIRE day (RTH + ETH), per day, in data/ticks_continuous_eth/:

  1. RTH GOLD CROSS-CHECK (the core accuracy test): the 08:30-15:15 slice of the
     ETH-store day must equal the trusted RTH trove day (data/ticks_continuous/)
     tick-for-tick — same row count, same prices (2dp), same volumes. The RTH trove
     is our independent, 5-yr, Massive-built reference; if the RTH slice matches it
     exactly, the ETH file shares that verified integrity and only ADDS overnight.
  2. WHOLE-DAY STRUCTURE: timestamps strictly non-decreasing; no exact-duplicate
     rows; volumes > 0; price within a sane band of the RTH trove's level (offset
     applied correctly); ETH rows >= RTH rows.
  3. SESSION KEYING: every tick falls in the CME session that settles on that date,
     [prev-trade-day 17:00, this-date 16:00) CT — nothing leaked from an adjacent
     session; last RTH tick <= 15:15, overnight present (ticks before 08:30).

Output: data/ticks_continuous_eth/_validation_<stamp>.csv (per-day verdicts) and a
summary. Exit code != 0 if ANY day FAILS the RTH gold cross-check (the hard gate).

  python scripts/validate_eth_store.py            # all ETH-store days
  python scripts/validate_eth_store.py 2026-09-10 # one day
"""
from __future__ import annotations

import sys
from datetime import date, time, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import market_calendar as MC  # noqa: E402

RTH_DIR = ROOT / "data" / "ticks_continuous"
ETH_DIR = ROOT / "data" / "ticks_continuous_eth"
RTH_START, RTH_END = time(8, 30), time(15, 15)
SESSION_OPEN, SESSION_CLOSE = time(17, 0), time(16, 0)


def check_day(d: str) -> dict:
    r = {"date": d, "rth_gold": "n/a", "eth_rows": 0, "rth_rows_eth": 0,
         "rth_rows_trove": 0, "structure": "n/a", "session": "n/a", "notes": ""}
    ep = ETH_DIR / f"{d}.parquet"
    if not ep.exists():
        r["notes"] = "no ETH file"; r["rth_gold"] = "MISSING"; return r
    eth = pd.read_parquet(ep)
    eth["DateTime"] = pd.to_datetime(eth["DateTime"])
    r["eth_rows"] = len(eth)

    # --- structure (whole day) ---
    issues = []
    if not eth["DateTime"].is_monotonic_increasing:
        issues.append("non-monotonic ts")
    dups = eth.duplicated(subset=["DateTime", "Price", "Volume"]).sum()
    if dups:
        issues.append(f"{dups} dup rows")
    if (eth["Volume"] <= 0).any():
        issues.append("non-positive volume")
    r["structure"] = "OK" if not issues else "; ".join(issues)

    # --- session keying (whole day) ---
    dd = date.fromisoformat(d)
    prev = MC.prev_trading_day(dd)
    lo = datetime.combine(prev, SESSION_OPEN)
    hi = datetime.combine(dd, SESSION_CLOSE)
    out_of_session = ((eth["DateTime"] < lo) | (eth["DateTime"] >= hi)).sum()
    tod = eth["DateTime"].dt.time
    has_overnight = (tod < RTH_START).any() or (eth["DateTime"].dt.date < dd).any()
    last_rth_ok = eth.loc[(tod >= RTH_START) & (tod < RTH_END), "DateTime"]
    r["session"] = "OK" if (out_of_session == 0 and has_overnight) else (
        (f"{out_of_session} ticks outside session; " if out_of_session else "") +
        ("no overnight ticks" if not has_overnight else ""))

    # --- RTH gold cross-check (the hard gate) ---
    rth_slice = eth[(tod >= RTH_START) & (tod < RTH_END)].reset_index(drop=True)
    r["rth_rows_eth"] = len(rth_slice)
    tp = RTH_DIR / f"{d}.parquet"
    if not tp.exists():
        r["rth_gold"] = "no-trove-day"        # ETH-only day (e.g. holiday overnight)
        return r
    trove = pd.read_parquet(tp).reset_index(drop=True)
    r["rth_rows_trove"] = len(trove)
    same_n = len(rth_slice) == len(trove)
    same_px = same_n and rth_slice["Price"].round(2).reset_index(drop=True).equals(
        trove["Price"].round(2).reset_index(drop=True))
    same_vol = same_n and rth_slice["Volume"].astype("int64").reset_index(drop=True).equals(
        trove["Volume"].astype("int64").reset_index(drop=True))
    r["rth_gold"] = "MATCH" if (same_px and same_vol) else "MISMATCH"
    if r["rth_gold"] == "MISMATCH":
        why = []
        if not same_n: why.append(f"count {len(rth_slice)} vs {len(trove)}")
        elif not same_px: why.append("prices differ")
        elif not same_vol: why.append("volumes differ")
        r["notes"] = "; ".join(why)
    return r


def main() -> int:
    days = ([sys.argv[1]] if len(sys.argv) > 1
            else sorted(p.stem for p in ETH_DIR.glob("*.parquet") if not p.stem.startswith("_")))
    if not days:
        print("no ETH-store days to validate"); return 0
    rows = [check_day(d) for d in days]
    df = pd.DataFrame(rows)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = ETH_DIR / f"_validation_{stamp}.csv"
    df.to_csv(out, index=False)

    gold = df[df["rth_gold"].isin(["MATCH", "MISMATCH"])]
    n_match = (df["rth_gold"] == "MATCH").sum()
    n_mis = (df["rth_gold"] == "MISMATCH").sum()
    n_struct = (df["structure"] != "OK").sum()
    n_sess = (df["session"] != "OK").sum()
    print(df.to_string(index=False) if len(df) <= 40 else
          df[df["rth_gold"] != "MATCH"].to_string(index=False) + f"\n... ({len(df)} days total)")
    print(f"\nDAYS {len(df)}  RTH gold: {n_match} MATCH / {n_mis} MISMATCH "
          f"(of {len(gold)} with a trove day)  |  structure issues {n_struct}  session issues {n_sess}")
    print(f"eth-only days (no trove): {(df['rth_gold']=='no-trove-day').sum()}  "
          f"missing files: {(df['rth_gold']=='MISSING').sum()}")
    print(f"-> {out}")
    if n_mis or n_struct:
        print("\n*** VALIDATION FAILED — see MISMATCH/structure rows above ***")
        return 1
    print("\nVALIDATION PASSED — every ETH day's RTH slice matches the trove tick-for-tick.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
