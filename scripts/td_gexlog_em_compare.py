"""Can a TD-derivable expected-move REPRODUCE gexlog's published EM?

gexlog generates premarket (~06:20 ET) and publishes `expectedMove` at reference
spot `current`. If no TD formula reproduces it, the historical backtest cannot
emulate gexlog's levels.

For each August 0DTE day we put gexlog's EM next to:
  A. TD ATM straddle mid at the open (09:31 ET)  -> TD's convention-free EM
  B. current x VIX/100 x sqrt(1/252)             -> desk's own formula
  C. current x VIX/100 x sqrt(1/365)             -> TD's calendar convention
and we also BACK OUT the annualized IV gexlog implicitly used, under both
conventions, to see if it equals VIX (=> gexlog is VIX-based) or something else
(=> gexlog uses a different IV, e.g. VIX1D / 0DTE ATM IV).

Report: per-day EM candidates + residuals, median |error| per candidate, and the
implied-IV-vs-VIX check.
"""
import csv
import datetime as dt
import glob
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_calendar as MC
from td_shadow_reprice import nbbo_at
from backtest_ic_strikes import index_ohlc

ROOT = Path(__file__).resolve().parents[1]
VIX = {r["date"]: float(r["close"]) for r in csv.DictReader(open(ROOT / "data/vix_daily.csv"))}
S252 = math.sqrt(1 / 252.0)
S365 = math.sqrt(1 / 365.0)
OPEN_ET = "09:31:00"


def round5(x):
    return round(x / 5.0) * 5.0


def straddle_mid(day, spot):
    """ATM 0DTE straddle mid (call_mid + put_mid) at the open; None if unquoted."""
    k = round5(spot)
    cq = nbbo_at(day, k, "C", day, OPEN_ET)
    pq = nbbo_at(day, k, "P", day, OPEN_ET)
    if cq is None or pq is None:
        return None, k
    cmid = (cq[0] + cq[1]) / 2.0
    pmid = (pq[0] + pq[1]) / 2.0
    return round(cmid + pmid, 2), k


def main():
    rows = []
    for f in sorted(glob.glob(str(ROOT / "data/options_sim/gameplan_202608*.json"))):
        g = json.load(open(f))
        gx = g.get("gexlog", {}) or {}
        em, cur = gx.get("expectedMove"), gx.get("current")
        if not em or not cur:
            continue
        d = os.path.basename(f)[9:17]                       # YYYYMMDD
        dd = dt.datetime.strptime(d, "%Y%m%d").date()
        prior = MC.prev_trading_day(dd).strftime("%Y-%m-%d")
        vix = VIX.get(prior)
        o_o, _ = index_ohlc(d)                              # today's open (for the straddle strike)
        strad, k = straddle_mid(d, o_o) if o_o else (None, None)

        a = strad                                           # A: TD straddle
        b = cur * vix / 100.0 * S252 if vix else None       # B: VIX x sqrt(1/252)
        c = cur * vix / 100.0 * S365 if vix else None       # C: VIX x sqrt(1/365)
        iv_impl_252 = (em / cur) / S252 * 100               # gexlog's implied annualized IV, 252 conv
        iv_impl_365 = (em / cur) / S365 * 100               # ... 365 conv
        rows.append(dict(date=d, gex_em=em, cur=cur, vix=vix, open=o_o, atm_k=k,
                         straddle=a, vix252=round(b, 1) if b else None,
                         vix365=round(c, 1) if c else None,
                         iv252=round(iv_impl_252, 1), iv365=round(iv_impl_365, 1)))

    # print
    print(f"{'date':10}{'gexEM':>7}{'strad':>7}{'vix252':>8}{'vix365':>8}"
          f"{'|A|':>6}{'|B|':>6}{'|C|':>6}   {'VIX':>5}{'iv252':>7}{'iv365':>7}")
    errA, errB, errC = [], [], []
    for r in rows:
        eA = abs(r["straddle"] - r["gex_em"]) if r["straddle"] is not None else None
        eB = abs(r["vix252"] - r["gex_em"]) if r["vix252"] is not None else None
        eC = abs(r["vix365"] - r["gex_em"]) if r["vix365"] is not None else None
        if eA is not None: errA.append(eA)
        if eB is not None: errB.append(eB)
        if eC is not None: errC.append(eC)
        print(f"{r['date']:10}{r['gex_em']:>7.0f}{str(r['straddle']):>7}{str(r['vix252']):>8}"
              f"{str(r['vix365']):>8}{('%.0f'%eA) if eA is not None else '-':>6}"
              f"{('%.0f'%eB) if eB is not None else '-':>6}{('%.0f'%eC) if eC is not None else '-':>6}"
              f"   {str(r['vix']):>5}{r['iv252']:>7}{r['iv365']:>7}")

    med = lambda xs: sorted(xs)[len(xs)//2] if xs else None
    print(f"\nmedian |error| vs gexlog EM (pts):")
    print(f"  A  TD ATM straddle       : {med(errA):.1f}   (n={len(errA)})")
    print(f"  B  VIX x sqrt(1/252)      : {med(errB):.1f}   (n={len(errB)})")
    print(f"  C  VIX x sqrt(1/365)      : {med(errC):.1f}   (n={len(errC)})")
    vixvals = [r["vix"] for r in rows if r["vix"]]
    print(f"\nIV check: gexlog's implied annualized IV vs actual VIX (prior close):")
    print(f"  mean VIX(prior)        = {sum(vixvals)/len(vixvals):.1f}")
    print(f"  mean gexlog iv (252)   = {sum(r['iv252'] for r in rows)/len(rows):.1f}")
    print(f"  mean gexlog iv (365)   = {sum(r['iv365'] for r in rows)/len(rows):.1f}")

    import pandas as pd
    pd.DataFrame(rows).to_csv(ROOT / "data/options_sim/td_gexlog_em_compare.csv", index=False)
    print("-> data/options_sim/td_gexlog_em_compare.csv")


if __name__ == "__main__":
    main()
