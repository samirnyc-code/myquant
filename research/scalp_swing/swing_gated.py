"""SWING A/C: multi-day-trend-aligned IB breakout, held to RTH close.

Gate (the edge): trade the initial-balance breakout ONLY in the direction of the
higher-timeframe DAILY trend (EMA-fast vs EMA-slow of prior RTH closes, causal ==
uses days strictly BEFORE today). This is the 'with-trend' principle from the 2E
book, implemented via a daily-EMA regime rather than the phase machine.

Optional secondary gates: VWAP agreement, expansion, cutoff time.
Held to RTH close (max_hold=None). RR configurable (2:1 default, 1.5:1 variant).
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import engine_ticks as E
import strategies as S
TICK = 0.25


def daily_bias(df5, ema_fast=5, ema_slow=20):
    """Return {date: +1/-1/0} trend sign known at today's open (prior closes only)."""
    dclose = df5.groupby("Date").Close.last()
    dates = list(dclose.index)
    c = dclose.values.astype(float)
    ef = S._ema(c, ema_fast); es = S._ema(c, ema_slow)
    bias = {}
    for i, d in enumerate(dates):
        if i < ema_slow:
            bias[d] = 0
        else:
            # use PRIOR day's ema (shift by 1 -> causal at today's open)
            bias[d] = 1 if ef[i - 1] > es[i - 1] else -1
    return bias


def make_trend_ib(bias, ib_bars, risk_pts, rr=2.0, need_vwap=False,
                  need_expand=0.0, cutoff_bar=54, tag=""):
    def f(day):
        n = len(day); sig = S._empty(day)
        if n < ib_bars + 3:
            return sig
        d = day.Date.iloc[0]
        b = bias.get(d, 0)
        if b == 0:
            return sig
        H, L, C = day.High.values, day.Low.values, day.Close.values
        hi = H[:ib_bars].max(); lo = L[:ib_bars].min()
        or_avg = np.mean(H[:ib_bars] - L[:ib_bars])
        vw = S._vwap(day)
        buf = TICK
        hi_lvl = hi + buf; lo_lvl = lo - buf
        thi = min(n - 1, cutoff_bar)
        for i in range(ib_bars - 1, thi):
            s = b  # with-trend only
            ep = hi_lvl if s > 0 else lo_lvl
            if (s > 0 and C[i] >= ep) or (s < 0 and C[i] <= ep):
                continue  # level already passed; anticipate not chase
            if need_expand and (H[i] - L[i]) < need_expand * max(or_avg, 0.25):
                continue
            if need_vwap and ((s > 0 and C[i] < vw[i]) or (s < 0 and C[i] > vw[i])):
                continue
            sp = ep - s * risk_pts; tp = ep + s * rr * risk_pts
            sig.loc[i, ["side", "entry", "stop", "target", "etype", "expiry"]] = [s, ep, sp, tp, "stop", 2]
        return sig
    f.__name__ = f"tib_ib{ib_bars}_r{risk_pts}_rr{rr}_v{int(need_vwap)}_x{need_expand}_{tag}"
    return f


if __name__ == "__main__":
    df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
    rr = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
    bias = daily_bias(df5, 5, 20)
    fns = []
    for ib in [6, 12, 18]:
        for risk in [6, 8, 10, 12]:
            for vw in [False, True]:
                fns.append(make_trend_ib(bias, ib, risk, rr=rr, need_vwap=vw, cutoff_bar=54))
    print(f"trend-IB swing, RR={rr}, {len(fns)} configs ...")
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
    R = pd.DataFrame(rows).sort_values("tr_pnl", ascending=False)
    R.to_csv(ROOT / "research" / "scalp_swing" / f"scan_tib_rr{rr}.csv", index=False)
    print(R.to_string(index=False))
