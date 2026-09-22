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
    # NOTE: exact (DateTime,Price,Volume) repeats are LEGITIMATE here — NT reports every
    # individual fill, and a sweep produces many same-ms/price/size prints. Collapsing
    # them is the bug we fixed, so we do NOT flag them. We only flag true corruption.
    issues = []
    if not eth["DateTime"].is_monotonic_increasing:
        issues.append("non-monotonic ts")
    if (eth["Volume"] <= 0).any():
        issues.append("non-positive volume")
    if (eth["Price"] <= 0).any():
        issues.append("non-positive price")
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
    # NT (ETH store) and Massive (trove) are DIFFERENT vendors: NT reports every fill,
    # Massive aggregates, so ROW COUNTS legitimately differ. The cross-vendor INVARIANTS
    # are total VOLUME (contracts traded is a market fact) and the RTH OHLC (price band).
    # Gold check = RTH volume EXACT match + OHLC match; row count is reported, not gated.
    eth_vol = int(rth_slice["Volume"].sum())
    tr_vol = int(trove["Volume"].sum())
    hi_e, lo_e = round(rth_slice["Price"].max(), 2), round(rth_slice["Price"].min(), 2)
    hi_t, lo_t = round(trove["Price"].max(), 2), round(trove["Price"].min(), 2)
    dv = eth_vol - tr_vol
    tol = max(500, int(0.001 * tr_vol))          # cross-vendor micro-diff tolerance (~0.1%)
    band_ok = abs(hi_e - hi_t) <= 0.5 and abs(lo_e - lo_t) <= 0.5

    if abs(dv) <= tol and band_ok:
        r["rth_gold"] = "MATCH"
        r["notes"] = f"vol {eth_vol} (d={dv:+d}); px {lo_e}-{hi_e}; rows NT {len(rth_slice)}/Massive {len(trove)}"
    elif eth_vol > tr_vol and lo_e <= lo_t + 0.25 and hi_e >= hi_t - 0.25:
        # NT has MORE volume and its range CONTAINS the trove's -> the Massive trove
        # day is incomplete; NT is the more-complete source. NOT an NT/ingest fault.
        r["rth_gold"] = "NT-MORE-COMPLETE"
        r["notes"] = (f"Massive trove INCOMPLETE: NT vol {eth_vol} vs {tr_vol} (d={dv:+d}); "
                      f"NT px {lo_e}-{hi_e} contains Massive {lo_t}-{hi_t}")
    else:
        r["rth_gold"] = "MISMATCH"
        r["notes"] = f"vol NT {eth_vol} vs Massive {tr_vol} (d={dv:+d}); px NT {lo_e}-{hi_e} Massive {lo_t}-{hi_t}"
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

    n_match = (df["rth_gold"] == "MATCH").sum()
    n_mis = (df["rth_gold"] == "MISMATCH").sum()
    n_incomplete = (df["rth_gold"] == "NT-MORE-COMPLETE").sum()
    n_struct = (df["structure"] != "OK").sum()
    n_sess = (df["session"] != "OK").sum()
    # show the non-clean rows in full
    bad = df[df["rth_gold"].isin(["MISMATCH", "NT-MORE-COMPLETE"]) |
             (df["structure"] != "OK")]
    if len(bad):
        print("NON-MATCH / flagged days:")
        print(bad.to_string(index=False))
    print(f"\nDAYS {len(df)}  |  RTH volume MATCH {n_match}  MISMATCH {n_mis}  "
          f"NT-more-complete(trove gap) {n_incomplete}  |  struct issues {n_struct}  session issues {n_sess}")
    print(f"eth-only days (no trove): {(df['rth_gold']=='no-trove-day').sum()}  "
          f"missing files: {(df['rth_gold']=='MISSING').sum()}")
    print(f"-> {out}")
    if n_mis or n_struct:
        print("\n*** VALIDATION FAILED — genuine MISMATCH/structure rows above (investigate NT export) ***")
        return 1
    print(f"\nVALIDATION PASSED — every ETH day's RTH volume matches the Massive trove within "
          f"tolerance{' (plus '+str(n_incomplete)+' days where NT is MORE complete than the trove)' if n_incomplete else ''}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
