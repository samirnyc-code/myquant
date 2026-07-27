"""Tick-accurate backtest engine for ES intraday RTH.

Signals are computed on 5M bars; EVERY fill (entry, stop, target) is resolved on
the raw trade-tick stream in true chronological order -> no phantom fills, no
same-bar ambiguity. This is the correct engine for tight-stop scalping.

Rules: 1 position at a time, no opposing trades, min R/R 2:1 (asserted),
flat by RTH close (force-exit at last tick), $30 round-trip cost.

Fill semantics on ticks:
  entry 'stop'  long: first tick price >= entry   (fill = that tick px, can gap = adverse)
  entry 'stop'  short: first tick price <= entry
  entry 'market': first tick at/after arm-bar end
  entry 'limit' long: first tick <= entry ; short: first tick >= entry
  exit  long: first tick where px<=stop (stop) OR px>=target (target); earliest in TIME wins
  exit  short: mirror
  time exit: max_hold_minutes after entry, else session end -> fill at last tick in window
"""
import functools
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant")
TICKDIR = ROOT / "data" / "ticks_continuous"
POINT_VALUE = 50.0
COST_RT = 30.0


@functools.lru_cache(maxsize=8)
def _load_ticks(date):
    t = pd.read_parquet(TICKDIR / f"{date}.parquet", columns=["DateTime", "Price"])
    t = t.sort_values("DateTime")
    return t["DateTime"].values.astype("datetime64[ns]"), t["Price"].values.astype(float)


def _first_idx(cond, start):
    """first index >= start where cond True, else -1. cond is full-length bool array."""
    sub = cond[start:]
    w = np.argmax(sub)
    if sub.size == 0 or not sub[w]:
        return -1
    return start + w


def run(df5, sig_fn, max_hold_minutes=None):
    trades = []
    FIVE = np.timedelta64(5, "m")
    for date, day in df5.groupby("Date", sort=True):
        day = day.reset_index(drop=True)
        sig = sig_fn(day)
        if sig is None or (sig["side"] != 0).sum() == 0:
            continue
        try:
            tt, tp = _load_ticks(date)
        except FileNotFoundError:
            continue
        if len(tt) == 0:
            continue
        bt = day.DateTime.values.astype("datetime64[ns]")
        n = len(day)
        sess_end = tt[-1]
        side_a = sig["side"].values; entry_a = sig["entry"].values
        stop_a = sig["stop"].values; tgt_a = sig["target"].values
        etype_a = sig["etype"].values; exp_a = sig["expiry"].values

        # ordered list of armed orders
        orders = [(i, int(side_a[i]), entry_a[i], stop_a[i], tgt_a[i], etype_a[i], int(exp_a[i]))
                  for i in range(n) if side_a[i] != 0]
        ptr_time = tt[0]
        for (ab, s, ep, sp, tpx, et, exp) in orders:
            arm_end = bt[ab] + FIVE
            if arm_end < ptr_time:
                continue
            risk = abs(ep - sp); rew = abs(tpx - ep)
            if risk <= 0 or rew < 2 * risk - 1e-9:
                continue
            win_end = bt[min(ab + exp, n - 1)] + FIVE
            e0 = np.searchsorted(tt, arm_end, side="left")
            e1 = np.searchsorted(tt, win_end, side="right")
            if e0 >= e1:
                continue
            # entry trigger
            if et == "market":
                efill = e0
            elif et == "stop":
                cond = (tp >= ep) if s > 0 else (tp <= ep)
                efill = _first_idx(cond[:e1], e0)
            else:  # limit
                cond = (tp <= ep) if s > 0 else (tp >= ep)
                efill = _first_idx(cond[:e1], e0)
            if efill < 0 or efill >= e1:
                continue
            fpx = tp[efill]; ftime = tt[efill]
            # exit window
            if max_hold_minutes is not None:
                hard = ftime + np.timedelta64(int(max_hold_minutes), "m")
                hard = min(hard, sess_end)
            else:
                hard = sess_end
            x1 = np.searchsorted(tt, hard, side="right")
            x1 = min(max(x1, efill + 1), len(tt))
            stop_cond = (tp <= sp) if s > 0 else (tp >= sp)
            tgt_cond = (tp >= tpx) if s > 0 else (tp <= tpx)
            si = _first_idx(stop_cond[:x1], efill + 1)
            ti = _first_idx(tgt_cond[:x1], efill + 1)
            cand = [(si, sp, "stop"), (ti, tpx, "target")]
            cand = [c for c in cand if c[0] >= 0]
            if cand:
                xi, xpx_lvl, reason = min(cand, key=lambda c: c[0])
                xpx = tp[xi]; xtime = tt[xi]
            else:
                xi = x1 - 1; xpx = tp[xi]; xtime = tt[xi]
                reason = "time" if max_hold_minutes is not None else "eod"
            pnl_pts = (xpx - fpx) * s
            pnl = pnl_pts * POINT_VALUE - COST_RT
            trades.append(dict(Date=date, side=s, etype=et, entry=round(fpx, 2), stop=sp,
                               target=tpx, exitpx=round(xpx, 2), reason=reason,
                               risk_pts=round(risk, 2), pnl_pts=round(pnl_pts, 2), pnl=round(pnl, 2),
                               etime=ftime, xtime=xtime))
            ptr_time = xtime  # no overlapping / opposing trades
    return pd.DataFrame(trades)


def _sim_day(date, day, tt, tp, sig, max_hold_minutes):
    """Simulate one day given preloaded ticks + a signal frame. Returns list of trade dicts."""
    out = []
    FIVE = np.timedelta64(5, "m")
    bt = day.DateTime.values.astype("datetime64[ns]")
    n = len(day); sess_end = tt[-1]
    side_a = sig["side"].values; entry_a = sig["entry"].values
    stop_a = sig["stop"].values; tgt_a = sig["target"].values
    etype_a = sig["etype"].values; exp_a = sig["expiry"].values
    orders = [(i, int(side_a[i]), entry_a[i], stop_a[i], tgt_a[i], etype_a[i], int(exp_a[i]))
              for i in range(n) if side_a[i] != 0]
    ptr_time = tt[0]
    for (ab, s, ep, sp, tpx, et, exp) in orders:
        arm_end = bt[ab] + FIVE
        if arm_end < ptr_time:
            continue
        risk = abs(ep - sp); rew = abs(tpx - ep)
        if risk <= 0 or rew < 2 * risk - 1e-9:
            continue
        win_end = bt[min(ab + exp, n - 1)] + FIVE
        e0 = np.searchsorted(tt, arm_end, side="left")
        e1 = np.searchsorted(tt, win_end, side="right")
        if e0 >= e1:
            continue
        if et == "market":
            efill = e0
        elif et == "stop":
            cond = (tp >= ep) if s > 0 else (tp <= ep)
            efill = _first_idx(cond[:e1], e0)
        else:
            cond = (tp <= ep) if s > 0 else (tp >= ep)
            efill = _first_idx(cond[:e1], e0)
        if efill < 0 or efill >= e1:
            continue
        fpx = tp[efill]; ftime = tt[efill]
        if max_hold_minutes is not None:
            hard = min(ftime + np.timedelta64(int(max_hold_minutes), "m"), sess_end)
        else:
            hard = sess_end
        x1 = min(max(np.searchsorted(tt, hard, side="right"), efill + 1), len(tt))
        stop_cond = (tp <= sp) if s > 0 else (tp >= sp)
        tgt_cond = (tp >= tpx) if s > 0 else (tp <= tpx)
        si = _first_idx(stop_cond[:x1], efill + 1)
        ti = _first_idx(tgt_cond[:x1], efill + 1)
        cand = [c for c in [(si, "stop"), (ti, "target")] if c[0] >= 0]
        if cand:
            xi, reason = min(cand, key=lambda c: c[0])
        else:
            xi = x1 - 1; reason = "time" if max_hold_minutes is not None else "eod"
        xpx = tp[xi]; xtime = tt[xi]
        pnl_pts = (xpx - fpx) * s
        out.append(dict(Date=date, side=s, etype=et, entry=round(fpx, 2), stop=sp, target=tpx,
                        exitpx=round(xpx, 2), reason=reason, risk_pts=round(risk, 2),
                        pnl_pts=round(pnl_pts, 2), pnl=round(pnl_pts * POINT_VALUE - COST_RT, 2),
                        etime=ftime, xtime=xtime))
        ptr_time = xtime
    return out


def run_many(df5, sig_fns, max_hold_minutes=None):
    """Loop days ONCE, load ticks once/day, evaluate every sig_fn. Returns {name: trades_df}."""
    acc = {getattr(f, "__name__", f"s{i}"): [] for i, f in enumerate(sig_fns)}
    names = list(acc.keys())
    for date, day in df5.groupby("Date", sort=True):
        day = day.reset_index(drop=True)
        try:
            tt, tp = _load_ticks(date)
        except FileNotFoundError:
            continue
        if len(tt) == 0:
            continue
        for nm, f in zip(names, sig_fns):
            sig = f(day)
            if sig is None or (sig["side"] != 0).sum() == 0:
                continue
            acc[nm].extend(_sim_day(date, day, tt, tp, sig, max_hold_minutes))
    return {nm: pd.DataFrame(rows) for nm, rows in acc.items()}


# ---- metrics (shared) ----
def metrics(tr, label=""):
    if len(tr) == 0:
        return dict(label=label, n=0, pnl=0, pf=0, win=0, avgR=0, maxdd=0, netdd=0, sharpe=0)
    wins = tr[tr.pnl > 0].pnl.sum(); loss = -tr[tr.pnl < 0].pnl.sum()
    pf = wins / loss if loss > 0 else float("inf")
    eq = tr.pnl.cumsum(); dd = (eq - eq.cummax()).min()
    R = tr.pnl / (tr.risk_pts * POINT_VALUE)
    daily = tr.groupby("Date").pnl.sum()
    sharpe = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0
    return dict(label=label, n=len(tr), pnl=round(tr.pnl.sum()), pf=round(pf, 2),
                win=round((tr.pnl > 0).mean() * 100, 1), avgR=round(R.mean(), 2),
                maxdd=round(dd), netdd=round(tr.pnl.sum() / abs(dd), 1) if dd < 0 else 0,
                sharpe=round(sharpe, 2))


def by_year(tr):
    if len(tr) == 0:
        return pd.DataFrame()
    tr = tr.copy(); tr["year"] = pd.to_datetime(tr["Date"]).dt.year
    g = tr.groupby("year").agg(n=("pnl", "size"), pnl=("pnl", "sum"),
                               pf=("pnl", lambda x: round(x[x > 0].sum() / max(1e-9, -x[x < 0].sum()), 2)),
                               win=("pnl", lambda x: round((x > 0).mean() * 100, 1)))
    g["pnl"] = g["pnl"].round()
    return g
