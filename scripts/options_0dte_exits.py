"""options_0dte_exits.py — intraday exit sweep for the 0DTE IC + BPS book.

Adds real intraday management on top of the hold-to-expiry baseline, using the
full-session cbbo-1m path. Sweeps:
  profit targets : capture X% of the entry credit (close when spread decays to (1-X)*credit)
  stops          : close when it costs stop_mult * credit to buy back (loss cap)
  time stop      : force-close at 15:45 ET (= 14:45 CT, the desk rule)
Exits pay a closing commission (2 legs/spread); expiring winners don't. Mid fills.

For each (date, structure=IC/BPS, open anchor) we build the minute path of the spread's
mid value ONCE, then evaluate every config cheaply via first-threshold-crossing.

Out: data/options_0dte/exit_sweep.csv (config x structure metrics)
     data/options_0dte/exit_trades_best.csv (per-trade for the best config, for slicing)
Run: .venv/Scripts/python.exe scripts/options_0dte_exits.py
"""
from __future__ import annotations
import glob
import math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "data" / "databento" / "0dte_parsed"
SPX = ROOT / "data" / "spx_daily_ohlc.csv"
VIX = ROOT / "data" / "vix_daily_full.csv"
OUT = ROOT / "data" / "options_0dte"

SQRT252 = math.sqrt(252)
WIDTH = 25
COMM_LEG = 1.30
MULT = 100
PROFIT_TARGETS = [None, 0.50, 0.75]
STOPS = [None, 1.5, 2.0, 2.5, 3.0]
TIME_STOPS = [None, "15:45"]


def load_daily():
    spx = pd.read_csv(SPX, parse_dates=["Date"]).set_index("Date")
    vix = pd.read_csv(VIX, parse_dates=["Date"]).set_index("Date")["vix"]
    d = spx.join(vix, how="inner")
    d["prior_close"] = d["Close"].shift(1)
    d["prior_vix"] = d["vix"].shift(1)
    return d


def metrics(x):
    x = np.asarray(x, float)
    if len(x) == 0:
        return dict(n=0, mean=0, total=0, sharpe=0, pf=0, maxdd=0, win=0)
    cum = np.cumsum(x); dd = (np.maximum.accumulate(cum) - cum).max()
    w = x[x > 0].sum(); l = -x[x < 0].sum()
    return dict(n=len(x), mean=round(x.mean(), 1), total=round(x.sum(), 0),
                sharpe=round(x.mean()/x.std()*np.sqrt(252), 2) if x.std() else 0,
                pf=round(w/l, 2) if l else np.inf, maxdd=round(dd, 0),
                win=round((x > 0).mean()*100, 1))


def build_paths(day, legs, tgrid):
    """Return (mid_value[], cross_close[], cross_credit_at). All aligned to tgrid.
    mid_value   = sum(short_mid - long_mid)          -> the mark we watch/trigger on
    cross_close = sum(short_ask - long_bid)          -> worst-case cost to CLOSE
    cross_open  = sum(short_bid - long_ask)          -> worst-case credit to OPEN"""
    day = day.copy()
    def leg_series(k, right, col):
        s = day[(day["strike"] == k) & (day["right"] == right)].set_index("ts")[col]
        return s[~s.index.duplicated()].reindex(tgrid, method="ffill").to_numpy()
    mid = np.zeros(len(tgrid)); cclose = np.zeros(len(tgrid)); copen = np.zeros(len(tgrid))
    for right, ks, kl in legs:
        sb, sa = leg_series(ks, right, "bid"), leg_series(ks, right, "ask")
        lb, la = leg_series(kl, right, "bid"), leg_series(kl, right, "ask")
        mid = mid + ((sb + sa) / 2 - (lb + la) / 2)
        cclose = cclose + (sa - lb)
        copen = copen + (sb - la)
    return mid, cclose, copen


def eval_config(mid, cclose, copen, intrinsic, entry_i, pt, stop, tstop_i, legs_n):
    """Return (pnl_mid, pnl_cross) for one exit config. Trigger on the mid mark."""
    enter_comm = COMM_LEG * 2 * legs_n
    exit_comm = COMM_LEG * 2 * legs_n
    cr_mid = mid[entry_i]; cr_cross = copen[entry_i]
    end_i = tstop_i if tstop_i is not None else len(mid) - 1
    ei = None
    for i in range(entry_i + 1, end_i + 1):
        v = mid[i]
        if v != v:
            continue
        if pt is not None and v <= (1 - pt) * cr_mid:
            ei = i; break
        if stop is not None and v >= stop * cr_mid:
            ei = i; break
    if ei is not None:                              # early close
        pnl_mid = (cr_mid - mid[ei]) * MULT - (enter_comm + exit_comm)
        xc = cclose[ei]; xc = mid[ei] if xc != xc else xc
        pnl_cross = (cr_cross - xc) * MULT - (enter_comm + exit_comm)
    elif tstop_i is not None:                       # time-stop close
        vm = mid[tstop_i]; vm = intrinsic if vm != vm else vm
        vc = cclose[tstop_i]; vc = intrinsic if vc != vc else vc
        pnl_mid = (cr_mid - vm) * MULT - (enter_comm + exit_comm)
        pnl_cross = (cr_cross - vc) * MULT - (enter_comm + exit_comm)
    else:                                           # hold to expiry (settle intrinsic, no exit comm)
        pnl_mid = (cr_mid - intrinsic) * MULT - enter_comm
        pnl_cross = (cr_cross - intrinsic) * MULT - enter_comm
    return pnl_mid, pnl_cross


def main():
    daily = load_daily()
    files = sorted(glob.glob(str(PARSED / "*.parquet")))
    structs = {"bps": [("P", "lo", "loW")], "bcs": [("C", "hi", "hiW")],
               "ic": [("P", "lo", "loW"), ("C", "hi", "hiW")]}
    keys = [(pt, st, ts) for pt in PROFIT_TARGETS for st in STOPS for ts in TIME_STOPS]
    acc = {s: {k: [] for k in keys} for s in structs}
    best_rows = []

    for f in files:
        date = pd.Timestamp(Path(f).stem)
        if date not in daily.index:
            continue
        r = daily.loc[date]
        pc, pv, op, cl = r["prior_close"], r["prior_vix"], r["Open"], r["Close"]
        if any(pd.isna(x) for x in (pc, pv, op, cl)):
            continue
        day = pd.read_parquet(f)
        day["ts"] = pd.to_datetime(day["ts"], utc=True)
        strikes = sorted(day["strike"].unique())
        if len(strikes) < 10:
            continue
        # minute grid over RTH
        tgrid = pd.DatetimeIndex(sorted(day["ts"].unique()))
        et = pd.Timestamp(f"{date.date()} 09:30", tz="America/New_York").tz_convert("UTC")
        ets = tgrid[tgrid >= et]
        if len(ets) == 0:
            continue
        entry_ts = ets[0]; entry_i = tgrid.get_loc(entry_ts)
        ts1545 = pd.Timestamp(f"{date.date()} 15:45", tz="America/New_York").tz_convert("UTC")
        tstop_idx = int(np.searchsorted(tgrid.values, np.datetime64(ts1545))) if ts1545 <= tgrid[-1] else len(tgrid)-1
        em = pc * (pv/100) / SQRT252
        gap = (op - pc) / pc * 100
        snap = lambda t: min(strikes, key=lambda s: abs(s - t))
        lo, hi = snap(op - em), snap(op + em)
        K = {"lo": lo, "loW": snap(lo - WIDTH), "hi": hi, "hiW": snap(hi + WIDTH)}

        for sname, tmpl in structs.items():
            legs = [(rt, K[a], K[b]) for rt, a, b in tmpl]
            mid, cclose, copen = build_paths(day, legs, tgrid)
            credit = mid[entry_i]
            if credit != credit or credit <= 0:
                continue
            intrinsic = sum(min(max((ks - cl) if rt == "P" else (cl - ks), 0.0), WIDTH)
                            for rt, ks, kl in legs)
            for (pt, st, tsr) in keys:
                tsi = tstop_idx if tsr else None
                pm, pcx = eval_config(mid, cclose, copen, intrinsic, entry_i, pt, st, tsi, len(legs))
                acc[sname][(pt, st, tsr)].append(pm)
                best_rows.append({"date": str(date.date()), "yr": date.year, "strat": sname,
                                  "gap_pct": round(gap, 3), "profit_target": pt, "stop": st,
                                  "time_stop": tsr, "pnl_mid": round(pm, 2), "pnl_cross": round(pcx, 2)})

    rows = []
    for s in structs:
        for k in keys:
            m = metrics(acc[s][k])
            pt, st, ts = k
            rows.append({"strat": s, "profit_target": pt, "stop": st, "time_stop": ts, **m})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "exit_sweep.csv", index=False)
    pd.DataFrame(best_rows).to_parquet(OUT / "exit_trades.parquet", compression="zstd")

    # print top configs per structure by Sharpe (min 100 trades)
    for s in structs:
        sub = res[(res.strat == s) & (res.n > 100)].sort_values("sharpe", ascending=False)
        print(f"\n===== {s.upper()} — top exit configs by Sharpe =====")
        print(sub.head(10).to_string(index=False))
        base = res[(res.strat == s) & (res.profit_target.isna()) & (res.stop.isna()) & (res.time_stop.isna())]
        print("baseline (hold-to-expiry):", base[["mean", "total", "sharpe", "pf", "maxdd", "win"]].to_string(index=False))
    print(f"\nsaved {OUT/'exit_sweep.csv'}")


if __name__ == "__main__":
    main()
