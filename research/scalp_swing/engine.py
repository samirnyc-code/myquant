"""Backtest engine for ES intraday (RTH), 5M bars.

Rules enforced (per user's spec):
  - 1 ES at a time; NO opposing/simultaneous trades (single position, no pyramiding).
  - min R/R 2:1 (engine asserts target_dist >= 2*risk on every order).
  - flat by RTH close (force-exit at the last bar of each day).
  - $30 round-trip cost per trade (POINT_VALUE=$50/pt, so 0.60 pt).

Fill model (search phase = PESSIMISTIC, no phantom fills):
  - entry: 'market' -> next bar open; 'stop' -> triggers intrabar at the stop
    price (fill = max(entry,open) long / min(entry,open) short = adverse);
    'limit' -> triggers intrabar at limit price.
  - management: on each bar after entry, if BOTH stop and target lie inside
    [Low,High], assume STOP hit first (worst case). Otherwise whichever is touched.
  - time exit: max_hold_bars or session end, filled at that bar's close.

A strategy is a function sig(day_df) -> DataFrame indexed like day_df with columns:
  side (+1 long / -1 short / 0 none), entry, stop, target, etype ('market'|'stop'|'limit'), expiry
Only ONE order is armed at a time (most recent non-zero side row); it stays live
for `expiry` bars or until a position is open.
"""
import numpy as np
import pandas as pd

POINT_VALUE = 50.0
COST_RT = 30.0          # $ round trip
TICK = 0.25


def run(df5, sig_fn, max_hold_bars=None, verbose=False):
    """df5 = full 5M dataframe (all days). sig_fn(day_df)->signals. Returns trades DataFrame."""
    trades = []
    for date, day in df5.groupby("Date", sort=True):
        day = day.reset_index(drop=True)
        sig = sig_fn(day)
        if sig is None or (sig["side"] != 0).sum() == 0:
            continue
        O, H, L, C = day.Open.values, day.High.values, day.Low.values, day.Close.values
        n = len(day)
        side = sig["side"].values
        entry_a = sig["entry"].values
        stop_a = sig["stop"].values
        tgt_a = sig["target"].values
        etype_a = sig["etype"].values
        expiry_a = sig["expiry"].values

        pos = 0            # 0 flat, +1/-1
        i = 0
        armed_bar = -1     # bar index where current order armed
        while i < n - 1:
            if pos == 0:
                # find most-recent armed order at or before bar i
                if side[i] != 0:
                    armed_bar = i
                if armed_bar < 0 or side[armed_bar] == 0:
                    i += 1; continue
                s = int(side[armed_bar]); ep = entry_a[armed_bar]
                sp = stop_a[armed_bar]; tp = tgt_a[armed_bar]
                et = etype_a[armed_bar]; exp = int(expiry_a[armed_bar])
                # R/R guard
                risk = abs(ep - sp); rew = abs(tp - ep)
                if risk <= 0 or rew < 2 * risk - 1e-9:
                    armed_bar = -1; i += 1; continue
                # try to fill entry on bars armed_bar+1 .. armed_bar+exp
                filled = False; fbar = None; fpx = None
                for j in range(armed_bar + 1, min(armed_bar + 1 + exp, n)):
                    if et == "market":
                        fpx = O[j]; fbar = j; filled = True; break
                    if et == "stop":
                        if s > 0 and H[j] >= ep:
                            fpx = max(ep, O[j]); fbar = j; filled = True; break
                        if s < 0 and L[j] <= ep:
                            fpx = min(ep, O[j]); fbar = j; filled = True; break
                    if et == "limit":
                        if s > 0 and L[j] <= ep:
                            fpx = min(ep, O[j]); fbar = j; filled = True; break
                        if s < 0 and H[j] >= ep:
                            fpx = max(ep, O[j]); fbar = j; filled = True; break
                if not filled:
                    armed_bar = -1; i += 1; continue
                # manage from fbar onward
                pos = s
                # recompute stop/target relative to actual fill? keep original absolute levels
                exit_px = None; exit_bar = None; reason = None
                hold_cap = n - 1 if max_hold_bars is None else min(fbar + max_hold_bars, n - 1)
                for k in range(fbar, n):
                    hi, lo, cl = H[k], L[k], C[k]
                    hit_stop = (lo <= sp) if s > 0 else (hi >= sp)
                    hit_tgt = (hi >= tp) if s > 0 else (lo <= tp)
                    if k == fbar:
                        # on entry bar, only count stop/target beyond the fill path (conservative: allow both)
                        pass
                    if hit_stop and hit_tgt:
                        exit_px = sp; exit_bar = k; reason = "stop(both)"; break
                    if hit_stop:
                        exit_px = sp; exit_bar = k; reason = "stop"; break
                    if hit_tgt:
                        exit_px = tp; exit_bar = k; reason = "target"; break
                    if k >= hold_cap:
                        exit_px = cl; exit_bar = k; reason = "time"; break
                if exit_px is None:
                    exit_px = C[n - 1]; exit_bar = n - 1; reason = "eod"
                pnl_pts = (exit_px - fpx) * s
                pnl = pnl_pts * POINT_VALUE - COST_RT
                trades.append(dict(Date=date, side=s, ebar=fbar, xbar=exit_bar,
                                   entry=fpx, stop=sp, target=tp, exitpx=exit_px,
                                   reason=reason, risk_pts=risk, pnl_pts=pnl_pts, pnl=pnl,
                                   etime=day.DateTime.values[fbar], xtime=day.DateTime.values[exit_bar]))
                pos = 0; armed_bar = -1
                i = exit_bar + 1
            else:
                i += 1
    return pd.DataFrame(trades)


def metrics(tr, label=""):
    if len(tr) == 0:
        return dict(label=label, n=0, pnl=0, pf=0, win=0, avgR=0, maxdd=0, netdd=0)
    tr = tr.copy()
    tr["year"] = pd.to_datetime(tr["Date"]).dt.year
    wins = tr[tr.pnl > 0].pnl.sum(); loss = -tr[tr.pnl < 0].pnl.sum()
    pf = wins / loss if loss > 0 else float("inf")
    eq = tr.pnl.cumsum()
    dd = (eq - eq.cummax()).min()
    R = (tr.pnl_pts * POINT_VALUE) / (tr.risk_pts * POINT_VALUE)
    daily = tr.groupby("Date").pnl.sum()
    sharpe = (daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0
    return dict(label=label, n=len(tr), pnl=round(tr.pnl.sum()),
                pf=round(pf, 2), win=round((tr.pnl > 0).mean() * 100, 1),
                avgR=round(R.mean(), 2), maxdd=round(dd), netdd=round(tr.pnl.sum() / abs(dd), 1) if dd < 0 else 0,
                sharpe=round(sharpe, 2))


def by_year(tr):
    if len(tr) == 0:
        return pd.DataFrame()
    tr = tr.copy(); tr["year"] = pd.to_datetime(tr["Date"]).dt.year
    g = tr.groupby("year").agg(n=("pnl", "size"), pnl=("pnl", "sum"),
                               win=("pnl", lambda x: round((x > 0).mean() * 100, 1)))
    g["pnl"] = g["pnl"].round()
    return g


def split_report(tr, name):
    tr = tr.copy(); tr["d"] = pd.to_datetime(tr["Date"])
    train = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]
    print(f"\n===== {name} =====")
    print("ALL  ", metrics(tr, "all"))
    print("TRAIN", metrics(train, "2021-23"))
    print("OOS  ", metrics(oos, "2024-26"))
    print(by_year(tr).to_string())
    return metrics(tr), metrics(train), metrics(oos)
