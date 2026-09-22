"""flip_stop_entry_test.py — entry method: SB close vs stop-entry beyond SB / box (S119).

User request: side-by-side test of entry variants, everything else frozen to the
CURRENT DEPLOYED chart rules (2026-09-12): both bars climax; bar1 = color, no doji;
SB = IBS band 0.55/0.45 AND body >= 4 ticks; SAR on opposite signal; EB opposite-IBS
scratch (first bar after entry fill); RR2 target; protective stop 1 tick beyond the
2-bar box; one position; conservative both-in-bar -> stop; session end -> close.
(No hour-8 skip — the chart doesn't have one.)

Entry variants:
  CLOSE   enter at SB close (deployed behavior)
  SE_SB   stop entry 1t beyond the SB extreme in trade direction; fill requires a
          tick THROUGH the SE price (long: high >= SE + 1t), fill AT the SE price
  SE_BOX  same, but SE 1t beyond the BOX extreme (i.e. beyond bar1's extreme too)
Pending-order handling (SE variants): cancelled if the protective-stop level is hit
BEFORE the entry triggers (setup invalidated); replaced by any newer signal; expires
at session end. Bar that crosses SE and stop together = filled-then-stopped
(conservative). Risk/target computed off the ACTUAL fill price.

    python tempo/scripts/flip_stop_entry_test.py
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
RR = 2
MINBODY = 4 * TICK
PT_USD = 50.0


def ibs_dir(h, l, c, i):
    rg = h[i] - l[i]
    if rg < TICK / 2:
        return 0
    x = (c[i] - l[i]) / rg
    return 1 if x >= 0.55 else (-1 if x <= 0.45 else 0)


def signal(h, l, o, c, cx, i):
    """deployed chart rules; returns 0 none / 1 short / 2 long"""
    if not (cx[i] and cx[i - 1]):
        return 0
    if abs(c[i - 1] - o[i - 1]) < TICK / 2:            # bar1 doji = no color
        return 0
    if abs(c[i] - o[i]) < MINBODY - TICK / 2:          # SB body >= 4t
        return 0
    d1 = 1 if c[i - 1] >= o[i - 1] else -1
    d2 = ibs_dir(h, l, c, i)
    if d2 == 0 or d1 == d2:
        return 0
    return 1 if d1 == 1 else 2


def sim_day(g, variant):
    h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); c = g["close"].to_numpy()
    cx = g["climax"].to_numpy()
    n = len(g)
    trades = []
    nsig = 0
    pos = None          # dict short en st tg rk fill_i
    pend = None         # dict short se psl
    for i in range(1, n):
        # manage open position
        if pos is not None:
            sh = pos["short"]; sgn = -1 if sh else 1
            if (h[i] >= pos["st"]) if sh else (l[i] <= pos["st"]):
                trades.append({**pos, "res": "stop", "pnl": -pos["rk"]}); pos = None
            elif (l[i] <= pos["tg"]) if sh else (h[i] >= pos["tg"]):
                trades.append({**pos, "res": "target", "pnl": RR * pos["rk"]}); pos = None
            elif i == pos["fill_i"] + 1:
                d = ibs_dir(h, l, c, i)
                if (not cx[i]) and ((not sh and d == -1) or (sh and d == 1)):
                    trades.append({**pos, "res": "eb_scr", "pnl": (c[i] - pos["en"]) * sgn})
                    pos = None
        # manage pending stop-entry
        if pend is not None:
            sh = pend["short"]
            inval = (h[i] >= pend["psl"]) if sh else (l[i] <= pend["psl"])
            trig = (l[i] <= pend["se"] - TICK) if sh else (h[i] >= pend["se"] + TICK)
            if trig:
                en = pend["se"]
                st = pend["psl"]
                rk = abs(en - st)
                sgn = -1 if sh else 1
                pos = {"short": sh, "en": en, "st": st, "rk": rk,
                       "tg": en + sgn * RR * rk, "fill_i": i, "date": g["date"].iloc[0]}
                pend = None
                if inval:                              # crossed both -> filled then stopped
                    trades.append({**pos, "res": "stop", "pnl": -rk}); pos = None
                elif (l[i] <= pos["tg"]) if sh else (h[i] >= pos["tg"]):
                    trades.append({**pos, "res": "target", "pnl": RR * rk}); pos = None
            elif inval:
                pend = None
        # new signal
        s = signal(h, l, o, c, cx, i)
        if s == 0:
            continue
        nsig += 1
        sig_short = s == 1
        if pos is not None:
            if sig_short != pos["short"]:
                sgn = -1 if pos["short"] else 1
                trades.append({**pos, "res": "rev", "pnl": (c[i] - pos["en"]) * sgn})
                pos = None
            else:
                continue
        hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        if variant == "CLOSE":
            en = c[i]
            st = hi2 + TICK if sig_short else lo2 - TICK
            rk = abs(en - st)
            if rk < TICK:
                continue
            sgn = -1 if sig_short else 1
            pos = {"short": sig_short, "en": en, "st": st, "rk": rk,
                   "tg": en + sgn * RR * rk, "fill_i": i, "date": g["date"].iloc[0]}
        else:
            ext = (l[i] if sig_short else h[i]) if variant == "SE_SB" else \
                  (lo2 if sig_short else hi2)
            se = ext - TICK if sig_short else ext + TICK
            psl = hi2 + TICK if sig_short else lo2 - TICK
            if abs(se - psl) < TICK:
                continue
            pend = {"short": sig_short, "se": se, "psl": psl}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (c[n - 1] - pos["en"]) * sgn})
    return trades, nsig


def stats(t, nsig, label):
    if len(t) == 0:
        return {"variant": label, "signals": nsig, "fills": 0}
    pnl = t["pnl"]
    eq = pnl.cumsum()
    dd = (eq - eq.cummax()).min()
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"variant": label, "signals": nsig, "fills": len(t),
            "fill%": round(100 * len(t) / nsig, 0) if np.isfinite(nsig) else np.nan,
            "win%": round(100 * (pnl > 0).mean(), 1),
            "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "avg_risk_pts": round(t["rk"].mean(), 2),
            "tot_pts": round(pnl.sum(), 1),
            "$/trade": round(pnl.mean() * PT_USD, 1),
            "maxDD_$": round(dd * PT_USD, 0)}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    byday = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}
    rows = []
    for variant in ["CLOSE", "SE_SB", "SE_BOX"]:
        trades, nsig = [], 0
        for d in sorted(byday):
            tr, ns = sim_day(byday[d], variant)
            trades += tr; nsig += ns
        t = pd.DataFrame(trades)
        t["year"] = t["date"].str[:4].astype(int)
        for label, sub in [("21-22", t[t["year"] <= 2022]),
                           ("23-26", t[t["year"] >= 2023]), ("full", t)]:
            rows.append({"period": label, **stats(sub, nsig if label == "full" else np.nan, variant)})
        t.to_csv(OUT / f"flip_se_trades_{variant}_{today}.csv", index=False)
    res = pd.DataFrame(rows).sort_values(["period", "variant"])
    res.to_csv(OUT / f"flip_stop_entry_{today}.csv", index=False)
    print(res.to_string(index=False))


if __name__ == "__main__":
    main()
