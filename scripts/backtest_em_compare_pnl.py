"""Run the desk's ACTUAL August iron-condor trades under 3 expected-move methods,
side by side, to isolate how the EM choice changes P&L.

For each of the desk's real IC verticals (put/call spread it actually fired), keep
side + width(25) + entry time, but recompute the short strike from each EM:

  A  straddle  : EM = TD ATM 0DTE straddle mid at the open        (convention-free)
  B  vix252    : EM = prior_close x VIX/100 x sqrt(1/252)         (== gexlog == desk)
  C  vix365    : EM = prior_close x VIX/100 x sqrt(1/365)         (TD's IV convention)

  short = round5(center -/+ EM)   [center: eod=prior_close, open=SPX open print]
  long  = short -/+ 25

Entry credit = TD marketable touch at the desk's actual entry time (short@bid-long@ask).
Exit = settlement: SPX final close -> vertical intrinsic capped at width (56/58 Aug
trades expired, so settlement is faithful). P&L = (credit - settle)*100 - 2*FEE.

Method B is the control: its total should reproduce the desk's real booked P&L.
"""
import csv
import datetime as dt
import json
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_calendar as MC
from td_shadow_reprice import nbbo_at, ct_to_et
from backtest_ic_strikes import index_ohlc
from td_gexlog_em_compare import straddle_mid

FEEDS = {}


def load_feed(d):
    """desk intraday underlying (CT timestamps) for date d (YYYY-MM-DD); cached."""
    if d in FEEDS:
        return FEEDS[d]
    p = ROOT / f"data/options_sim/underlying_{d.replace('-','')}.csv"
    FEEDS[d] = pd.read_csv(p) if p.exists() else None
    return FEEDS[d]


def detect_stop(feed, short_k, right, hold_min=10):
    """Desk level-acceptance: underlying holds beyond the short strike for >=10
    continuous min. Returns the CT trigger time 'HH:MM:SS' or None (-> settle)."""
    if feed is None or not len(feed):
        return None
    beyond = (feed["und"] >= short_k) if right == "C" else (feed["und"] <= short_k)
    run_start = None
    for t, b in zip(feed["ts_et"].tolist(), beyond.tolist()):
        try:
            tt = dt.datetime.strptime(t, "%H:%M:%S")
        except ValueError:
            continue
        if b:
            if run_start is None:
                run_start = tt
            elif (tt - run_start).total_seconds() >= hold_min * 60:
                return t
        else:
            run_start = None
    return None


def price_close(day_c, short_k, long_k, right, et):
    """marketable-touch DEBIT to close: buy short@ask - sell long@bid. None if unquoted."""
    sq = nbbo_at(day_c, short_k, right, day_c, et)
    lq = nbbo_at(day_c, long_k, right, day_c, et)
    if sq is None or lq is None:
        return None
    return round(sq[1] - lq[0], 2)                      # short ask - long bid

ROOT = Path(__file__).resolve().parents[1]
FEE = 1.63
VIX = {r["date"]: float(r["close"]) for r in csv.DictReader(open(ROOT / "data/vix_daily.csv"))}
S252 = math.sqrt(1 / 252.0)
S365 = math.sqrt(1 / 365.0)


def round5(x):
    return round(x / 5.0) * 5.0


def price_entry(day_c, short_k, long_k, right, et):
    """marketable-touch credit: short@bid - long@ask. None if either leg unquoted."""
    sq = nbbo_at(day_c, short_k, right, day_c, et)
    lq = nbbo_at(day_c, long_k, right, day_c, et)
    if sq is None or lq is None:
        return None
    return round(sq[0] - lq[1], 2)                      # short bid - long ask


def settle_vertical(short_k, long_k, right, final_close):
    w = abs(short_k - long_k)
    if right == "P":
        itm = max(0.0, short_k - final_close)
    else:
        itm = max(0.0, final_close - short_k)
    return min(w, itm)


def main():
    df = pd.read_parquet(ROOT / "data/options_log/trades.parquet")
    ic = df[df["strategy_id"].astype(str).str.contains("ic", na=False) & df["pnl"].notna()].copy()
    ic["date"] = ic["entry_dt"].astype(str).str[:10]
    ic = ic[(ic["date"] >= "2026-08-01") & (ic["date"] <= "2026-08-31")].copy()

    # per-day inputs (cache TD pulls)
    daycache = {}
    def day_inputs(d):
        if d in daycache:
            return daycache[d]
        dd = dt.datetime.strptime(d, "%Y-%m-%d").date()
        prior = MC.prev_trading_day(dd)
        _, pc = index_ohlc(prior.strftime("%Y%m%d"))       # prior close
        o_o, o_c = index_ohlc(d.replace("-", ""))          # open, final close
        vix = VIX.get(prior.strftime("%Y-%m-%d"))
        strad, _ = straddle_mid(d.replace("-", ""), o_o) if o_o else (None, None)
        em = {}
        if pc and vix:
            em["vix252"] = pc * vix / 100.0 * S252
            em["vix365"] = pc * vix / 100.0 * S365
        if strad:
            em["straddle"] = strad
        daycache[d] = dict(prior_close=pc, open=o_o, close=o_c, vix=vix, em=em)
        return daycache[d]

    METHODS = ["straddle", "vix252", "vix365"]
    recs = []
    for _, t in ic.iterrows():
        d = t["date"]
        di = day_inputs(d)
        if di["close"] is None or not di["em"]:
            continue
        sid = str(t["strategy_id"])
        right = "P" if sid.endswith("_p") else "C"
        center = di["prior_close"] if sid.startswith("eod") else di["open"]
        if center is None:
            continue
        ect = str(t["entry_dt"]).split(" ")[-1]
        et = ect + ":00" if ect.count(":") == 1 else ect
        # CT->ET +1h, and dodge the 09:30 stale-open seed
        h, m = int(et[:2]) + 1, et[3:5]
        et_et = f"{h:02d}:{m}:00"
        if et_et <= "09:30:30":
            et_et = "09:31:00"

        rec = dict(date=d, strat=sid, right=right, center=round(center, 1),
                   desk_pnl=round(float(t["pnl"]), 2))
        for meth in METHODS:
            emv = di["em"].get(meth)
            if emv is None:
                rec[meth] = None
                continue
            short_k = round5(center - emv) if right == "P" else round5(center + emv)
            long_k = short_k - 25 if right == "P" else short_k + 25
            dc = d.replace("-", "")
            cr = price_entry(dc, short_k, long_k, right, et_et)
            if cr is None:
                rec[meth] = None
                continue
            # exit: desk level-acceptance stop (>=10min beyond short) else settlement
            stop_ct = detect_stop(load_feed(d), short_k, right)
            exit_kind = "settle"
            if stop_ct:
                xet = ct_to_et(stop_ct)
                debit = price_close(dc, short_k, long_k, right, xet)
                if debit is not None:
                    exit_val, nfee, exit_kind = debit, 4, "stop"
                else:
                    exit_val, nfee = settle_vertical(short_k, long_k, right, di["close"]), 2
            else:
                exit_val, nfee = settle_vertical(short_k, long_k, right, di["close"]), 2
            pnl = round((cr - exit_val) * 100 - nfee * FEE, 2)
            rec[meth] = pnl
            rec[f"{meth}_k"] = short_k
            rec[f"{meth}_cr"] = cr
            rec[f"{meth}_exit"] = exit_kind
        recs.append(rec)

    out = pd.DataFrame(recs)
    out.to_csv(ROOT / "data/options_sim/backtest_em_compare_pnl.csv", index=False)

    n = len(out)
    print(f"August IC verticals re-run under 3 EM methods (n={n})\n")
    print(f"{'method':12}{'total P&L':>12}{'win%':>8}{'avg cr':>9}{'stops':>8}{'priced':>9}")
    for meth in METHODS:
        s = out[meth].dropna()
        wins = (s > 0).sum()
        avgcr = out[f"{meth}_cr"].dropna().mean() if f"{meth}_cr" in out else float("nan")
        stops = (out[f"{meth}_exit"] == "stop").sum() if f"{meth}_exit" in out else 0
        print(f"{meth:12}{s.sum():>12,.2f}{100*wins/len(s):>7.0f}%{avgcr:>9.2f}{stops:>6}/{len(s):<3}{len(s):>6}")
    print(f"\n{'desk actual (booked)':22}{out['desk_pnl'].sum():>12,.2f}   <- control: method B (vix252) should be close\n")

    # per-strategy breakdown
    print(f"{'strat':10}{'desk':>10}{'straddle':>10}{'vix252':>10}{'vix365':>10}")
    for sid in ["eodic_p", "eodic_c", "openic_p", "openic_c"]:
        g = out[out["strat"] == sid]
        if not len(g):
            continue
        print(f"{sid:10}{g['desk_pnl'].sum():>10,.0f}{g['straddle'].sum():>10,.0f}"
              f"{g['vix252'].sum():>10,.0f}{g['vix365'].sum():>10,.0f}")
    print(f"-> data/options_sim/backtest_em_compare_pnl.csv")


if __name__ == "__main__":
    main()
