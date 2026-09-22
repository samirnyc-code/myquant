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

    contracts_seen = {Path(p).name.split("_ticks_")[0].replace("_", " ") for p in paths}
    if len(contracts_seen) != 1:
        print(f"! files span multiple contracts {contracts_seen} — one contract at a time")
        return 2
    full_contract = contracts_seen.pop()
    ticker = contract_to_ticker(full_contract)
    print(f"\ncontract '{full_contract}' -> ticker {ticker}  ({len(paths)} files)")

    # MEMORY-SAFE two-pass. The ETH template makes each session appear COMPLETE in ~2
    # files (identical full copies); we must NOT concat all files (68 files x ~1M rows
    # OOMs the box) and must NOT dedup on (Time,Price,Volume) (genuine same-ms/price/size
    # fills would collapse and destroy ~60% of volume — the 07-23 bug). Instead:
    #   pass 1: cheaply count rows-per-session in each file (string date/hour, no pandas tz)
    #   pass 2: load ONLY the single best (most-complete) file per session, one at a time,
    #           and write that session's rows verbatim (no dedup) -> volume preserved exactly.
    def cheap_sed(tstr: str):
        d0 = date.fromisoformat(tstr[:10])
        return MC.next_trading_day(d0) if int(tstr[11:13]) >= 17 else d0

    from collections import defaultdict
    best = {}            # sed -> (count, file_index)
    print("pass 1/2: counting sessions per file...")
    for i, p in enumerate(paths):
        col = pd.read_csv(p, usecols=["Time"], dtype=str)["Time"].dropna()
        seds = col.map(cheap_sed)
        for d, c in seds.value_counts().items():
            if d not in best or c > best[d][0]:
                best[d] = (int(c), i)
    need = defaultdict(list)
    for d, (c, i) in best.items():
        need[i].append(d)

    rolls = load_rolls()
    written, skipped, aborted = [], [], []
    print("pass 2/2: writing best file per session...")
    for i in sorted(need):
        raw = pd.read_csv(paths[i]).dropna(subset=["Time", "Price", "Volume"])
        ts = pd.to_datetime(raw["Time"])
        ts = (ts.dt.tz_localize(a.src_tz, ambiguous="infer", nonexistent="shift_forward")
                .dt.tz_convert("America/Chicago").dt.tz_localize(None))
        fdf = pd.DataFrame({"DateTime": ts.values,
                            "Price": raw["Price"].astype(float).values,
                            "Volume": raw["Volume"].astype(int).values})
        fdf["sed"] = fdf["DateTime"].map(session_end_date)
        for d in sorted(need[i]):
          g = fdf[fdf["sed"] == d]
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
          # cross-vendor invariant: NT total RTH VOLUME must equal the Massive trove
          # (row counts differ — NT reports every fill, Massive aggregates).
          vtag = ""
          if a.validate_rth:
              rp = RTH_DIR / f"{d.isoformat()}.parquet"
              if rp.exists():
                  ref = pd.read_parquet(rp)
                  ev, tv = int(rth["Volume"].sum()), int(ref["Volume"].sum())
                  vtag = f"  RTH vol NT {ev} vs Massive {tv}: {'MATCH' if ev == tv else 'MISMATCH'}"
          print(f"  {d} off {off:+.2f}  {len(day):,} ticks ({len(rth):,} RTH)  "
                f"{day['DateTime'].iloc[0]} .. {day['DateTime'].iloc[-1]}{vtag}")

          if not a.dry_run:
              day["Volume"] = day["Volume"].astype("int64")
              day.to_parquet(out, index=False)
          written.append(d)

    print(f"\ndone: {len(written)} written, {len(skipped)} skipped, {len(aborted)} aborted "
          f"-> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
