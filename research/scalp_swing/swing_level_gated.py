"""SWING (gated by STRUCTURAL LEVEL): IB breakout, WITH the level, held to close.

Gate = price vs a daily structural level, the 2E-book principle ('above prior-day
HVL -> long side'). Two level sources compared:
  sma20d : 20-day SMA of RTH daily closes, prior-day value (self-computed, causal).
  hvl    : prior-EOD HVL from data/regime/hvl_by_session.csv (MQ ES real 2024-07+,
           SPX-approx before -> HVL comparison only clean in the modern era).
Per S85 the two agree ~93% (kappa 0.85), so sma20d is the clean self-contained gate.

Rule: level L fixed for the day. At arm bar i (causal), side = +1 if Close>L else -1.
Arm an IB-breakout stop on that side (anticipate, don't chase). risk fixed pts,
target = rr*risk, hold to RTH close. min RR 2:1.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import engine_ticks as E
import strategies as S
TICK = 0.25


def sma20d_map(df5, win=20):
    dclose = df5.groupby("Date").Close.last()
    dates = list(dclose.index); c = dclose.values.astype(float)
    sma = pd.Series(c).rolling(win).mean().values
    # prior-day sma known at today's open
    return {d: (sma[i - 1] if i >= win else np.nan) for i, d in enumerate(dates)}


def hvl_map():
    h = pd.read_csv(ROOT / "data" / "regime" / "hvl_by_session.csv")
    return dict(zip(h["session_date"].astype(str), h["hvl"].astype(float)))


def make_level_ib(levels, ib_bars, risk_pts, rr=2.0, cutoff_bar=54,
                  min_dist=0.0, tag=""):
    def f(day):
        n = len(day); sig = S._empty(day)
        if n < ib_bars + 3:
            return sig
        d = day.Date.iloc[0]
        L = levels.get(d, np.nan)
        if not np.isfinite(L):
            return sig
        H, Lo, C = day.High.values, day.Low.values, day.Close.values
        hi = H[:ib_bars].max(); lo = Lo[:ib_bars].min()
        buf = TICK; hi_lvl = hi + buf; lo_lvl = lo - buf
        arm = ib_bars - 1                       # side decided at IB close (causal)
        if min_dist and abs(C[arm] - L) < min_dist:
            return sig
        s = 1 if C[arm] > L else -1
        ep = hi_lvl if s > 0 else lo_lvl
        if (s > 0 and C[arm] >= ep) or (s < 0 and C[arm] <= ep):
            return sig                          # already broken; anticipate only
        sp = ep - s * risk_pts; tp = ep + s * rr * risk_pts
        # single order: live from IB close until cutoff (engine fills first cross)
        expiry = min(n - 1, cutoff_bar) - arm
        sig.iloc[arm] = [s, ep, sp, tp, "stop", expiry]
        return sig
    f.__name__ = f"lvl_{tag}_ib{ib_bars}_r{risk_pts}_rr{rr}_md{min_dist}"
    return f


def scan(df5, levels, tag, rr, ib_list, risk_list, md_list):
    fns = [make_level_ib(levels, ib, r, rr=rr, min_dist=md, tag=tag)
           for ib in ib_list for r in risk_list for md in md_list]
    res = E.run_many(df5, fns, max_hold_minutes=None, min_rr=min(rr, 2.0))
    rows = []
    for f in fns:
        tr = res[f.__name__]
        if len(tr) == 0:
            continue
        tr["d"] = pd.to_datetime(tr["Date"])
        trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
        mt, mo = E.metrics(trn), E.metrics(oos)
        rows.append(dict(cfg=f.__name__, tr_n=mt["n"], tr_pnl=mt["pnl"], tr_pf=mt["pf"], tr_win=mt["win"],
                         tr_dd=mt["maxdd"], tr_ndd=mt["netdd"], oo_n=mo["n"], oo_pnl=mo["pnl"],
                         oo_pf=mo["pf"], oo_win=mo["win"], oo_dd=mo["maxdd"], oo_ndd=mo["netdd"]))
    return pd.DataFrame(rows).sort_values("tr_pnl", ascending=False)


if __name__ == "__main__":
    rr = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
    sma = sma20d_map(df5); hvl = hvl_map()
    ib_list = [6, 12, 18]; risk_list = [6, 8, 10, 12]; md_list = [0.0, 3.0]
    for tag, lv in [("sma20d", sma), ("hvl", hvl)]:
        R = scan(df5, lv, tag, rr, ib_list, risk_list, md_list)
        R.to_csv(ROOT / "research" / "scalp_swing" / f"scan_lvl_{tag}_rr{rr}.csv", index=False)
        print(f"\n===== LEVEL={tag}  RR={rr} =====")
        print(R.to_string(index=False))
    print("\nDONE_LVL")
