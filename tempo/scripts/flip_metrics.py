"""flip_metrics.py — full metric table for the climax-flip setups (S117-tempo).

Setups (user naming): BASIC = flip, one position, signals-while-busy skipped.
EB-REVERSAL = variant 1: opposite signal while in trade exits at that bar's close
and reverses. Both with IBS direction (bull>=0.55 / bear<=0.45, middle = no signal),
stop 1 tick beyond the 2-bar box, both-in-bar -> stop, open at session end marked
to last close. RR grid: target = 1R / 2R / 3R / 4R.

Metrics per cell: n, share target/stop/rev, win rate (targets / (targets+stops)),
PF (gross wins / gross losses, all trades incl rev+open marks), total pts,
expectancy pts & $ per trade (ES $50/pt, gross; net line assumes $4.50 RT),
avg stop distance (pts), max drawdown of the trade-sequence equity (pts, $).

    python tempo/scripts/flip_metrics.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
PT_USD = 50.0
FEE_RT = 4.50 / PT_USD          # $4.50 round turn in pts


def bar_dir(o, h, l, c, i):
    rg = h[i] - l[i]
    if rg < TICK / 2:
        return 0
    ibs = (c[i] - l[i]) / rg
    return 1 if ibs >= 0.55 else (-1 if ibs <= 0.45 else 0)


def sim_day(g, rr, sar):
    h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); c = g["close"].to_numpy()
    cx = g["climax"].to_numpy()
    n = len(g)
    trades = []
    pos = None
    for i in range(1, n):
        if pos is not None:
            sh = pos["short"]
            hs = h[i] >= pos["st"] if sh else l[i] <= pos["st"]
            ht = l[i] <= pos["tg"] if sh else h[i] >= pos["tg"]
            if hs:
                trades.append({**pos, "res": "stop", "pnl": -pos["rk"]}); pos = None
            elif ht:
                trades.append({**pos, "res": "target", "pnl": rr * pos["rk"]}); pos = None
        if not (cx[i] and cx[i - 1]):
            continue
        d1, d2 = bar_dir(o, h, l, c, i - 1), bar_dir(o, h, l, c, i)
        if d1 == 0 or d2 == 0 or d1 == d2:
            continue
        sig_short = d1 == 1
        if pos is not None:
            if sar and sig_short != pos["short"]:
                sgn = -1 if pos["short"] else 1
                trades.append({**pos, "res": "rev", "pnl": (c[i] - pos["en"]) * sgn})
                pos = None
            else:
                continue
        hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        en = c[i]
        st = hi2 + TICK if sig_short else lo2 - TICK
        rk = abs(en - st)
        if rk < TICK:
            continue
        sgn = -1 if sig_short else 1
        pos = {"date": g["date"].iloc[0], "short": sig_short, "en": en, "st": st,
               "rk": rk, "tg": en + sgn * rr * rk}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (c[n - 1] - pos["en"]) * sgn})
    return trades


def metrics(t: pd.DataFrame) -> dict:
    pnl = t["pnl"]
    eq = pnl.cumsum()
    dd = (eq - eq.cummax()).min()
    tgt = (t["res"] == "target").sum(); stp = (t["res"] == "stop").sum()
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {
        "n": len(t),
        "tgt%": round(100 * tgt / len(t), 1), "stop%": round(100 * stp / len(t), 1),
        "rev%": round(100 * (t["res"] == "rev").mean(), 1),
        "win%": round(100 * tgt / max(1, tgt + stp), 1),
        "PF": round(gp / gl, 2) if gl > 0 else np.inf,
        "tot_pts": round(pnl.sum(), 1),
        "exp_pts": round(pnl.mean(), 3),
        "exp_$": round(pnl.mean() * PT_USD, 1),
        "exp_$net": round((pnl.mean() - FEE_RT) * PT_USD, 1),
        "avg_stop": round(t["rk"].mean(), 2),
        "maxDD_pts": round(dd, 1),
        "maxDD_$": round(dd * PT_USD, 0),
    }


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    all_dates = sorted(df["date"].unique())
    rows = []
    for scope, dates in [("1yr", all_dates[-252:]), ("full", all_dates)]:
        sub = df[df["date"].isin(dates)]
        byday = {d: g.reset_index(drop=True) for d, g in sub.groupby("date")}
        for sar in [False, True]:
            for rr in [1, 2, 3, 4]:
                trades = []
                for d in sorted(byday):
                    trades += sim_day(byday[d], rr, sar)
                t = pd.DataFrame(trades)
                m = metrics(t)
                m["scope"] = scope
                m["setup"] = "EB-Reversal" if sar else "Basic"
                m["RR"] = rr
                rows.append(m)
    res = pd.DataFrame(rows)[["scope", "setup", "RR", "n", "win%", "tgt%", "stop%", "rev%",
                              "PF", "tot_pts", "exp_pts", "exp_$", "exp_$net",
                              "avg_stop", "maxDD_pts", "maxDD_$"]]
    res.to_csv(OUT / f"flip_metrics_{today}.csv", index=False)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
