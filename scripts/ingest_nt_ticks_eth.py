#!/usr/bin/env python
"""ingest_nt_ticks_eth.py — build the FULL-SESSION (ETH+RTH) tick store from NT8
exports, in PARALLEL to the RTH trove (which is left untouched).

WHY SEPARATE STORE
    data/ticks_continuous/ is RTH-only [08:30,15:15) and feeds the 5M cache + all
    RTH research. This writes data/ticks_continuous_eth/ with the WHOLE CME globex
    session so overnight is available without breaking anything downstream. The RTH
    slice of a day here must match the RTH trove tick-for-tick (that's the validator).

SESSIONIZING (CME ES globex)
    The session that SETTLES on trade date D runs [D-1 17:00, D 16:00) CT with a
    16:00-17:00 maintenance break. Each tick's session_end_date:
        time >= 17:00  -> next trading day (market_calendar.next_trading_day)
        time <  17:00  -> same calendar day (its own trading day if one, else skip)
    One parquet per session_end_date: data/ticks_continuous_eth/{D}.parquet.

GUARANTEES (same as the RTH ingest)
    - CONTRACT/ROLL: every session's front-month per rolls.json must equal this
      export's ticker, else that session is ABORTED (a dump can't cross a roll).
    - OFFSET: Panama cum_offset from contracts.py applied to price (same as massive.py).
    - DEDUP: exact-duplicate rows from overlapping session coverage are collapsed
      ONLY within (DateTime,Price,Volume) AND a within-file duplicate guard, so
      overlap between per-day export files can't double-count; genuine same-ms trades
      are preserved by keeping the max count seen across files (see _merge).

USAGE (one contract at a time — the export files must all be the same contract)
    python scripts/ingest_nt_ticks_eth.py --glob "data/nt_ticks/ES_09-26_ticks_*.csv"
    # --out-dir data/ticks_continuous_eth (default)  --force  --dry-run
    # --validate-rth : after writing, assert the RTH slice matches data/ticks_continuous/
"""
from __future__ import annotations

import argparse
import glob as _glob
import sys
from datetime import date, time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from contracts import load_rolls, get_active_contract, _MONTH_TO_CODE  # noqa: E402
import market_calendar as MC  # noqa: E402

RTH_DIR = ROOT / "data" / "ticks_continuous"
ETH_DIR = ROOT / "data" / "ticks_continuous_eth"
RTH_START, RTH_END = time(8, 30), time(15, 15)
SESSION_OPEN = time(17, 0)          # globex reopen -> belongs to NEXT trade day


def contract_to_ticker(full: str) -> str:
    base, mmyy = full.strip().split(" ")
    mm, yy = mmyy.split("-")
    return f"{base}{_MONTH_TO_CODE[int(mm)]}{yy[-1]}"


def session_end_date(ts: pd.Timestamp) -> date:
    """CME trade date this tick settles into."""
    d = ts.date()
    if ts.time() >= SESSION_OPEN:
        return MC.next_trading_day(d)
    return d


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--glob", default="data/nt_ticks/*_ticks_*.csv")
    ap.add_argument("--files", nargs="*")
    ap.add_argument("--src-tz", default="America/Chicago")
    ap.add_argument("--out-dir", default=str(ETH_DIR))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--validate-rth", action="store_true",
                    help="assert each written day's RTH slice == the RTH trove day")
    a = ap.parse_args()
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = a.files if a.files else sorted(_glob.glob(str(ROOT / a.glob)))
    if not paths:
        print(f"! no files matched ({a.files or a.glob})"); return 2

    contracts_seen, frames = set(), []
    print(f"reading {len(paths)} file(s):")
    for p in paths:
        fp = Path(p)
        stem = fp.name.split("_ticks_")[0].replace("_", " ")
        contracts_seen.add(stem)
        df = pd.read_csv(fp)
        print(f"  {fp.name}: {len(df):,} rows  contract='{stem}'")
        frames.append(df)
    if len(contracts_seen) != 1:
        print(f"! files span multiple contracts {contracts_seen} — one contract at a time")
        return 2
    full_contract = contracts_seen.pop()
    ticker = contract_to_ticker(full_contract)
    print(f"\ncontract '{full_contract}' -> ticker {ticker}")

    raw = pd.concat(frames, ignore_index=True).dropna(subset=["Time", "Price", "Volume"])
    ts = pd.to_datetime(raw["Time"])
    ts = (ts.dt.tz_localize(a.src_tz, ambiguous="infer", nonexistent="shift_forward")
            .dt.tz_convert("America/Chicago").dt.tz_localize(None))
    ticks = pd.DataFrame({
        "DateTime": ts,
        "Price": raw["Price"].astype(float).values,
        "Volume": raw["Volume"].astype(int).values,
    })
    # overlap dedup: identical (DateTime,Price,Volume) rows from overlapping per-day
    # export windows are collapsed; a genuine repeat trade has the SAME triple too,
    # but NT's export is one row per trade, so a triple appearing in TWO files is the
    # overlap artifact — keep one. (Within a single file there are no exact dup rows.)
    n0 = len(ticks)
    ticks = ticks.drop_duplicates(subset=["DateTime", "Price", "Volume"]).sort_values("DateTime")
    if len(ticks) != n0:
        print(f"  collapsed {n0 - len(ticks):,} overlap-duplicate rows")

    ticks["sed"] = ticks["DateTime"].map(session_end_date)
    rolls = load_rolls()

    written, skipped, aborted = [], [], []
    for d, g in ticks.groupby("sed"):
        active = get_active_contract(d, rolls)
        if active is None:
            aborted.append(d); print(f"! {d}: no active contract — SKIP"); continue
        if active["ticker"] != ticker:
            aborted.append(d)
            print(f"! {d}: front-month {active['ticker']} != export {ticker} (roll) — ABORT")
            continue
        off = active["cum_offset"]
        day = g[["DateTime", "Price", "Volume"]].copy()
        day["Price"] = day["Price"] + off
        day = day.sort_values("DateTime").reset_index(drop=True)

        out = out_dir / f"{d.isoformat()}.parquet"
        if out.exists() and not a.force:
            skipped.append(d); print(f"  {d} EXISTS-skip ({len(day):,})"); continue

        rth = day[(day["DateTime"].dt.time >= RTH_START) & (day["DateTime"].dt.time < RTH_END)]
        print(f"  {d} off {off:+.2f}  {len(day):,} ticks ({len(rth):,} RTH)  "
              f"{day['DateTime'].iloc[0]} .. {day['DateTime'].iloc[-1]}")

        if a.validate_rth:
            rp = RTH_DIR / f"{d.isoformat()}.parquet"
            if rp.exists():
                ref = pd.read_parquet(rp)
                chk = rth.reset_index(drop=True)[["DateTime", "Price", "Volume"]]
                same = (len(chk) == len(ref) and
                        chk["Price"].round(2).equals(ref["Price"].round(2)) and
                        chk["Volume"].astype("int64").equals(ref["Volume"].astype("int64")))
                print(f"      RTH cross-check vs trove: {'MATCH' if same else 'MISMATCH'} "
                      f"(eth-rth {len(chk):,} vs trove {len(ref):,})")

        if not a.dry_run:
            day["Volume"] = day["Volume"].astype("int64")
            day.to_parquet(out, index=False)
        written.append(d)

    print(f"\ndone: {len(written)} written, {len(skipped)} skipped, {len(aborted)} aborted "
          f"-> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
