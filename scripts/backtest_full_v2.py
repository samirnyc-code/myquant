"""FULL-HISTORY v2 backtest, 2022-05-16 -> 2026-09-04 — the DESK-FAITHFUL engine
(S115), all 8 streams in one run, vix252 EM (the desk formula) only.

Fixes vs the S114 engine (backtest_full_em_2022 / _fly_2022):
  1. entry gate: credit<=0 -> broken skip; credit<0.10 -> thin_credit skip
     (options_gameplan MIN_CREDIT_ABS) — the old engine traded everything,
     including negative-credit crossed quotes
  2. WAIT-day anchors: open* streams run under TWO policies per day —
       nowait  : entry 09:33 ET every day (08:30 CT + 3min fire lag)
       calwait : 10:08 ET on FOMC/CPI/NFP days (data/econ_calendar_2022_2026.csv,
                 sources: federalreserve.gov + bls.gov per-year schedules),
                 09:33 ET otherwise
     (No gameplan files exist pre-2026-08, so the calendar approximates the
     brief's WAIT rule; Aug-2026 check: brief also waited on blind/other days
     and did NOT wait on POS-gamma NFP 08-07 — treat the two policies as a band.)
  3. 14:45 CT time-stop modeled as the desk behaves: quotable close (debit>0.10)
     at 15:45 ET, else ride to settlement
  4. eod entry = 09:31 ET (desk 08:30 CT + lag), strikes premarket-fixed:
     eodic round5(prior_close -/+ EM), eodfly round5(prior_close);
     open strikes struck from parity-SPX at the actual fire minute:
     openic round5(S -/+ EM), openfly round5(S)

Exits otherwise identical to the validated engine: level-acceptance stop
(parity feed, 10 min) -> TD touch close; settlement = intrinsic vs daily close;
fees $1.63/contract/exec. Checkpointed per day to backtest_full/rows_v2.csv
(both policies' rows written together; non-event days emit the open rows once
per policy with identical values but are computed once).

Run: python scripts/backtest_full_v2.py [--start 2022-05-16] [--end 2026-09-04]
     [--workers 4]   (Theta terminal required; 4 concurrent = tier limit)
"""
import argparse
import csv
import datetime as dt
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_calendar as MC
from backtest_full_em_2022 import (FEE, OUT, parity_feed, touch, detect_stop,
                                   settle_vertical, yahoo_spx)

ROOT = Path(__file__).resolve().parents[1]
ROWS = OUT / "rows_v2.csv"
S252 = math.sqrt(1 / 252.0)
MIN_CREDIT = 0.10
EOD_ET = "09:31:00"
OPEN_ET, WAIT_ET = "09:33:00", "10:08:00"
TIME_STOP_ET = "15:45:00"
FIELDS = ["date", "policy", "strat", "event", "center", "em", "short_k",
          "long_k", "credit", "entry_et", "exit_kind", "exit_val", "pnl", "note"]


def round5(x):
    return round(x / 5.0) * 5.0


def spot_at(feed, et):
    if feed is None:
        return None
    f = feed[feed["t"] >= et].head(1)
    return None if not len(f) else float(f.iloc[0]["S"])


def run_trade(dc, strat, short_k, long_k, right, entry_et, feed, close_px):
    rec = dict(strat=strat, short_k=short_k, long_k=long_k, entry_et=entry_et,
               credit=None, exit_kind="", exit_val=None, pnl=None, note="")
    cr = touch(dc, short_k, long_k, right, entry_et)
    rec["credit"] = cr
    if cr is None:
        rec["exit_kind"], rec["note"] = "SKIP", "no entry quote"
        return rec
    if cr <= 0:
        rec["exit_kind"], rec["note"] = "SKIP", "gate: broken"
        return rec
    if cr < MIN_CREDIT:
        rec["exit_kind"], rec["note"] = "SKIP", "gate: thin_credit"
        return rec
    stop_t = detect_stop(feed, short_k, right, entry_et)
    if stop_t:
        debit = touch(dc, short_k, long_k, right, stop_t, closing=True)
        if debit is not None:
            rec.update(exit_kind="stop", exit_val=debit,
                       pnl=round((cr - debit) * 100 - 4 * FEE, 2))
            return rec
        rec["note"] = "stop unquotable -> settle"
    else:
        debit = touch(dc, short_k, long_k, right, TIME_STOP_ET, closing=True)
        if debit is not None and debit > 0.10:
            rec.update(exit_kind="time", exit_val=debit,
                       pnl=round((cr - debit) * 100 - 4 * FEE, 2))
            return rec
    sv = settle_vertical(short_k, long_k, right, close_px)
    rec.update(exit_kind=rec["exit_kind"] or "settle", exit_val=sv,
               pnl=round((cr - sv) * 100 - 2 * FEE, 2))
    return rec


def run_day(d, spx, vix, events):
    dc = d.replace("-", "")
    dd = dt.datetime.strptime(d, "%Y-%m-%d").date()
    prior = MC.prev_trading_day(dd).strftime("%Y-%m-%d")
    if d not in spx.index or prior not in spx.index:
        return [dict(date=d, policy="", strat="", note="no spx daily")]
    pc, o_o, close = (float(spx.loc[prior, "close"]), float(spx.loc[d, "open"]),
                      float(spx.loc[d, "close"]))
    v = vix.get(prior)
    if v is None:
        return [dict(date=d, policy="", strat="", note="no vix")]
    em = pc * v / 100.0 * S252
    ev = events.get(d, "")
    feed, _ = parity_feed(dc, round5(o_o))
    rows = []

    def emit(rec, policy, center):
        rec.update(date=d, policy=policy, event=ev,
                   center=round(center, 2), em=round(em, 1))
        rows.append(rec)

    # eod streams (policy-independent, premarket strikes)
    for strat, short_k, right in (
            ("eodic_p", round5(pc - em), "P"), ("eodic_c", round5(pc + em), "C"),
            ("eodfly_p", round5(pc), "P"), ("eodfly_c", round5(pc), "C")):
        long_k = short_k - 25 if right == "P" else short_k + 25
        emit(run_trade(dc, strat, short_k, long_k, right, EOD_ET, feed, close),
             "eod", pc)

    # open streams under both policies (identical on non-event days: compute once)
    policies = [("nowait", OPEN_ET)]
    policies.append(("calwait", WAIT_ET if ev else OPEN_ET))
    cache = {}
    for pol, et in policies:
        if et in cache:
            for rec, center in cache[et]:
                emit(dict(rec), pol, center)
            continue
        S = spot_at(feed, et)
        done = []
        if S is None:
            done.append((dict(strat="open*", short_k=None, long_k=None,
                              entry_et=et, credit=None, exit_kind="SKIP",
                              exit_val=None, pnl=None, note="no parity spot"), 0.0))
        else:
            for strat, short_k, right in (
                    ("openic_p", round5(S - em), "P"), ("openic_c", round5(S + em), "C"),
                    ("openfly_p", round5(S), "P"), ("openfly_c", round5(S), "C")):
                long_k = short_k - 25 if right == "P" else short_k + 25
                done.append((run_trade(dc, strat, short_k, long_k, right, et,
                                       feed, close), S))
        cache[et] = done
        for rec, center in done:
            emit(dict(rec), pol, center)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-05-16")
    ap.add_argument("--end", default="2026-09-04")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    spx = yahoo_spx()
    vix = {r["date"]: float(r["close"])
           for r in csv.DictReader(open(ROOT / "data/vix_daily.csv"))}
    events = {r["date"]: r["event"]
              for r in csv.DictReader(open(ROOT / "data/econ_calendar_2022_2026.csv"))}

    done = set()
    if ROWS.exists():
        done = set(pd.read_csv(ROWS, usecols=["date"])["date"].unique())
    days = []
    d = dt.datetime.strptime(a.start, "%Y-%m-%d").date()
    e = dt.datetime.strptime(a.end, "%Y-%m-%d").date()
    while d <= e:
        ds = d.strftime("%Y-%m-%d")
        if MC.is_trading_day(d) and ds not in done:
            days.append(ds)
        d += dt.timedelta(days=1)
    print(f"days to run: {len(days)} (done: {len(done)})", flush=True)

    new_file = not ROWS.exists()
    fh = open(ROWS, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file:
        w.writeheader()
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, rows in enumerate(ex.map(lambda dy: run_day(dy, spx, vix, events), days)):
            for r in rows:
                w.writerow({k: r.get(k) for k in FIELDS})
            fh.flush()
            if (i + 1) % 25 == 0:
                print(f"  {i+1}/{len(days)} ({rows[0].get('date', '?')})", flush=True)
    fh.close()
    print("DONE ->", ROWS, flush=True)


if __name__ == "__main__":
    main()
