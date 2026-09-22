"""flip_trap_mgmt.py — trap-quality filters + profit-management ladder (S117-tempo).

Base config (matches live chart): climax flip, IBS direction, SAR on opposite climax
pair, EB opposite-IBS scratch, stop 1 tick beyond box, one position, conservative
both-in-bar -> stop, session-end mark to close.

=== ARM A: MANAGEMENT (mechanics only, no filter) ===
  RR2          target 2R (control = current best)
  BE1@1R_T2    once 1R touched, stop -> entry +1 tick (armed from NEXT bar); target 2R
  BE1@1R_T3    same protection, target 3R
  TRAIL@1R     once 1R touched: stop -> BE+1t AND bar-trail (stop ratchets to prior
               bar extreme -/+ 1 tick each close); NO target (runner)
  TRAIL@2R     BE+1t at 1R; bar-trail activates at 2R; NO target (runner)
All threshold/trail updates apply from the NEXT bar (no intrabar lookahead).

=== ARM B: TRAP-QUALITY FILTERS (on RR2 control trades; train 2021-24 / test 2025-26) ===
  F1 trap-extreme   pre-SB climax bar made a NEW 20-bar extreme (trapped breakout)
  F2 engulf         SB range engulfs the pre-SB bar (h2>=h1 and l2<=l1)
  F3 full-roundtrip SB closes beyond the pre-SB bar's OPEN
  F4 level-poke     pre-SB bar poked beyond PDH (shorts) / PDL (longs)
Filters recorded at entry on every control trade; no re-simulation needed.

    python tempo/scripts/flip_trap_mgmt.py
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
LV = ROOT / "tempo" / "outputs" / "levels_by_day.json"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
PT_USD = 50.0
FEE_RT = 4.50 / PT_USD
NEXT = 20


def bar_dir(h, l, c, i):
    rg = h[i] - l[i]
    if rg < TICK / 2:
        return 0
    ibs = (c[i] - l[i]) / rg
    return 1 if ibs >= 0.55 else (-1 if ibs <= 0.45 else 0)


def sim_day(g, mode, lv):
    h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); c = g["close"].to_numpy()
    cx = g["climax"].to_numpy()
    n = len(g)
    trades = []
    pos = None
    for i in range(1, n):
        if pos is not None:
            sh = pos["short"]; sgn = -1 if sh else 1
            hs = h[i] >= pos["stop"] if sh else l[i] <= pos["stop"]
            if hs:
                pnl = (pos["stop"] - pos["en"]) * sgn
                res = "stop" if abs(pos["stop"] - pos["st0"]) < TICK / 2 else \
                      ("be" if abs(pos["stop"] - (pos["en"] + sgn * TICK)) < TICK / 2 else "trail")
                trades.append({**pos, "res": res, "pnl": pnl}); pos = None
            else:
                if pos["tg"] is not None and (l[i] <= pos["tg"] if sh else h[i] >= pos["tg"]):
                    trades.append({**pos, "res": "target", "pnl": (pos["tg"] - pos["en"]) * sgn})
                    pos = None
                else:
                    # EB scratch (first bar after entry)
                    if pos is not None and i == pos["i"] + 1:
                        d = bar_dir(h, l, c, i)
                        if (not cx[i]) and ((not sh and d == -1) or (sh and d == 1)):
                            trades.append({**pos, "res": "eb_scr", "pnl": (c[i] - pos["en"]) * sgn})
                            pos = None
                    if pos is not None:
                        # threshold upgrades, applied from NEXT bar
                        if not pos["hit1"] and (l[i] <= pos["r1"] if sh else h[i] >= pos["r1"]):
                            pos["hit1"] = True
                            if mode != "RR2":
                                pos["stop"] = pos["en"] + (TICK if not sh else -TICK)   # BE +1 tick in favor
                        if not pos["hit2"] and (l[i] <= pos["r2"] if sh else h[i] >= pos["r2"]):
                            pos["hit2"] = True
                        trail_on = (mode == "TRAIL@1R" and pos["hit1"]) or (mode == "TRAIL@2R" and pos["hit2"])
                        if trail_on:
                            cand = (h[i] + TICK) if sh else (l[i] - TICK)
                            if (sh and cand < pos["stop"]) or (not sh and cand > pos["stop"]):
                                pos["stop"] = cand
        if not (cx[i] and cx[i - 1]):
            continue
        d1, d2 = bar_dir(h, l, c, i - 1), bar_dir(h, l, c, i)
        if d1 == 0 or d2 == 0 or d1 == d2:
            continue
        sig_short = d1 == 1
        if pos is not None:
            if sig_short != pos["short"]:
                sgn = -1 if pos["short"] else 1
                trades.append({**pos, "res": "rev", "pnl": (c[i] - pos["en"]) * sgn}); pos = None
            else:
                continue
        hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        en = c[i]
        st = hi2 + TICK if sig_short else lo2 - TICK
        rk = abs(en - st)
        if rk < TICK:
            continue
        sgn = -1 if sig_short else 1
        j0 = max(0, i - 1 - NEXT)
        if i - 1 > j0:
            f1 = (h[i - 1] > h[j0:i - 1].max()) if sig_short else (l[i - 1] < l[j0:i - 1].min())
        else:
            f1 = False
        f2 = h[i] >= h[i - 1] and l[i] <= l[i - 1]
        f3 = c[i] < o[i - 1] if sig_short else c[i] > o[i - 1]
        f4 = False
        if lv and "hoy" in lv:
            f4 = (h[i - 1] > lv["hoy"]) if sig_short else (l[i - 1] < lv["loy"])
        tgt = None if mode.startswith("TRAIL") else en + sgn * (3 if mode.endswith("T3") else 2) * rk
        pos = {"i": i, "short": sig_short, "en": en, "st0": st, "stop": st, "rk": rk,
               "tg": tgt, "r1": en + sgn * rk, "r2": en + sgn * 2 * rk,
               "hit1": False, "hit2": False, "date": g["date"].iloc[0],
               "f1": f1, "f2": f2, "f3": f3, "f4": f4}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (c[n - 1] - pos["en"]) * sgn})
    return trades


def metrics(t):
    pnl = t["pnl"]
    eq = pnl.cumsum()
    dd = (eq - eq.cummax()).min()
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"n": len(t), "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "tot_pts": round(pnl.sum(), 1),
            "exp_$": round(pnl.mean() * PT_USD, 1),
            "exp_$net": round((pnl.mean() - FEE_RT) * PT_USD, 1),
            "avg_win": round(pnl[pnl > 0].mean(), 2) if (pnl > 0).any() else 0,
            "avg_loss": round(pnl[pnl < 0].mean(), 2) if (pnl < 0).any() else 0,
            "maxDD_$": round(dd * PT_USD, 0)}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    levels = json.loads(LV.read_text(encoding="utf-8")) if LV.exists() else {}
    all_dates = sorted(df["date"].unique())
    byday = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}

    rows = []
    ctrl_trades = None
    for mode in ["RR2", "BE1@1R_T2", "BE1@1R_T3", "TRAIL@1R", "TRAIL@2R"]:
        for scope, dates in [("1yr", all_dates[-252:]), ("full", all_dates)]:
            trades = []
            for d in sorted(dates):
                if d in byday:
                    trades += sim_day(byday[d], mode, levels.get(d))
            t = pd.DataFrame(trades)
            m = metrics(t); m["mode"] = mode; m["scope"] = scope
            rows.append(m)
            if mode == "RR2" and scope == "full":
                ctrl_trades = t
    res = pd.DataFrame(rows)[["mode", "scope", "n", "PF", "tot_pts", "exp_$",
                              "exp_$net", "avg_win", "avg_loss", "maxDD_$"]]
    res.to_csv(OUT / f"flip_mgmt_{today}.csv", index=False)
    print("=== ARM A: management (base incl. SAR + EB-scratch) ===")
    print(res.to_string(index=False))

    print("\n=== ARM B: trap-quality filters on RR2 control (train 21-24 / test 25-26) ===")
    ct = ctrl_trades.copy()
    ct["year"] = ct["date"].str[:4].astype(int)
    ct.to_csv(OUT / f"flip_trap_trades_{today}.csv", index=False)
    tr = ct[ct["year"] <= 2024]; te = ct[ct["year"] >= 2025]
    for name, col in [("F1 trap-extreme", "f1"), ("F2 engulf", "f2"),
                      ("F3 full-roundtrip", "f3"), ("F4 level-poke", "f4")]:
        a, b = tr[tr[col] == True], te[te[col] == True]        # noqa: E712
        an, bn = tr[tr[col] == False], te[te[col] == False]    # noqa: E712
        print(f"  {name:<18} train n={len(a):>4} avg {a['pnl'].mean():+.3f} "
              f"(rest {an['pnl'].mean():+.3f}) | test n={len(b):>4} avg {b['pnl'].mean():+.3f} "
              f"(rest {bn['pnl'].mean():+.3f})")


if __name__ == "__main__":
    main()
