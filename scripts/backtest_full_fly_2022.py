"""FULL fly-stream backtest 2022-05-16 -> present: the desk's 4 ATM verticals
(eodfly_p/c centered on prior close @09:31 ET, openfly_p/c on the open @10:05 ET),
short strike = round5(center), 25-wide, no EM/wall inputs needed.

Engine identical to backtest_full_em_2022 (entries TD touch, level-acceptance stop
on parity feed >=10min from entry, TD touch stop exits, settlement else) — the
configuration validated against the desk's real August fly book in
backtest_fly_control.py (79/79 stop decisions vs rule, corr 0.965, D -$108/75).

Checkpointed to data/options_sim/backtest_full/fly_rows.csv.
"""
import argparse
import csv
import datetime as dt
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_calendar as MC
from backtest_full_em_2022 import (ENTRY_ET, FEE, OUT, parity_feed, round5,
                                   settle_vertical, touch, detect_stop, yahoo_spx)

ROOT = Path(__file__).resolve().parents[1]
ROWS = OUT / "fly_rows.csv"
FIELDS = ["date", "strat", "center", "short_k", "long_k", "credit",
          "exit_kind", "exit_val", "pnl", "note"]


def run_day(d, spx):
    dc = d.replace("-", "")
    dd = dt.datetime.strptime(d, "%Y-%m-%d").date()
    prior = MC.prev_trading_day(dd).strftime("%Y-%m-%d")
    if d not in spx.index or prior not in spx.index:
        return [dict(date=d, strat="", note="no spx daily")]
    pc, o_o, close = spx.loc[prior, "close"], spx.loc[d, "open"], spx.loc[d, "close"]
    feed, _ = parity_feed(dc, round5(o_o))

    def spot_at(et):
        """spot at the entry moment from the parity feed (the desk's 'ATM' is ATM
        AT ENTRY, verified vs desk strikes Aug-2026; open-print was 30pts off on
        drift days). Fallback: the open print."""
        if feed is not None and len(feed):
            w = feed[feed["t"] >= et]
            if len(w):
                return float(w["S"].iloc[0])
        return o_o

    rows = []
    for base, ekey in (("eodfly", "eod"), ("openfly", "open")):
        et = ENTRY_ET[ekey]
        # centering verified vs desk strikes (Aug-2026): eodfly ATM = PRIOR CLOSE
        # (set in the premarket gameplan, 100% match); openfly ATM = spot at the
        # trigger-fire moment (~1 min after schedule).
        center = pc if ekey == "eod" else spot_at("10:05:00")
        k = round5(center)
        for right, suff in (("P", "_p"), ("C", "_c")):
            short_k = k
            long_k = short_k - 25 if right == "P" else short_k + 25
            cr = touch(dc, short_k, long_k, right, et)
            rec = dict(date=d, strat=base + suff, center=round(center, 2),
                       short_k=short_k, long_k=long_k, credit=cr,
                       exit_kind="", exit_val=None, pnl=None, note="")
            if cr is None:
                rec["note"] = "no entry quote"
                rows.append(rec)
                continue
            if cr <= 0:
                # the DESK's own rule: stand down on zero/negative credit
                # (seen live 2026-08-19 eodic_p "STOOD DOWN ... zero/negative credit")
                rec["note"] = "stood down (credit<=0)"
                rec["credit"] = cr
                rows.append(rec)
                continue
            stop_t = detect_stop(feed, short_k, right, et)
            if stop_t:
                debit = touch(dc, short_k, long_k, right, stop_t, closing=True)
                if debit is not None:
                    debit = min(debit, 25.0)          # never pay >width to close
                    rec["exit_kind"], rec["exit_val"], nfee = "stop", debit, 4
                else:
                    rec["exit_kind"] = "settle*"
                    rec["exit_val"], nfee = settle_vertical(short_k, long_k, right, close), 2
            else:
                rec["exit_kind"] = "settle"
                rec["exit_val"], nfee = settle_vertical(short_k, long_k, right, close), 2
            rec["pnl"] = round((cr - rec["exit_val"]) * 100 - nfee * FEE, 2)
            rows.append(rec)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2022-05-16")
    ap.add_argument("--end", default=None)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    end = a.end or (dt.date.today() - dt.timedelta(days=1)).strftime("%Y-%m-%d")

    spx = yahoo_spx()
    done = set()
    if ROWS.exists():
        done = set(pd.read_csv(ROWS, usecols=["date"])["date"].unique())
    days = []
    d = dt.datetime.strptime(a.start, "%Y-%m-%d").date()
    e = dt.datetime.strptime(end, "%Y-%m-%d").date()
    while d <= e:
        ds = d.strftime("%Y-%m-%d")
        if MC.is_trading_day(d) and ds not in done:
            days.append(ds)
        d += dt.timedelta(days=1)
    print(f"fly days to run: {len(days)} (done: {len(done)})", flush=True)

    new_file = not ROWS.exists()
    fh = open(ROWS, "a", newline="", encoding="utf-8")
    w = csv.DictWriter(fh, fieldnames=FIELDS)
    if new_file:
        w.writeheader()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        for i, rows in enumerate(ex.map(lambda dy: run_day(dy, spx), days)):
            for r in rows:
                w.writerow({k: r.get(k) for k in FIELDS})
            fh.flush()
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(days)}", flush=True)
    fh.close()
    print("DONE ->", ROWS, flush=True)


if __name__ == "__main__":
    main()
