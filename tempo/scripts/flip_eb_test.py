"""flip_eb_test.py — EB (entry-bar) opposite-IBS rule on the climax flip (S117-tempo).

User hypothesis: after entry (close of the signal bar), if the NEXT bar (EB) is NOT a
climax bar but closes with OPPOSITE IBS (long trade + EB IBS<=0.45, short + >=0.55),
the entry is being rejected -> cut it short, or reverse.

Base config = current best cell: EB-Reversal (SAR on opposite climax pairs), IBS
direction, RR2 target, stop 1 tick beyond the 2-bar box, one position, conservative
both-in-bar -> stop, session end marked to close.

Arms:
  CONTROL   base, no EB rule (plus diagnostic: control outcomes of EB-flagged trades)
  SCRATCH   EB trigger -> exit at EB close
  REVERSE   EB trigger -> exit + reverse at EB close; new stop 1 tick beyond the
            extreme of {signal bar, EB}; RR2 target on the new risk
Trigger checked ONLY on the first bar after entry, after stop/target (conservative).

    python tempo/scripts/flip_eb_test.py
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
PT_USD = 50.0
FEE_RT = 4.50 / PT_USD


def bar_dir(h, l, c, i):
    rg = h[i] - l[i]
    if rg < TICK / 2:
        return 0
    ibs = (c[i] - l[i]) / rg
    return 1 if ibs >= 0.55 else (-1 if ibs <= 0.45 else 0)


def sim_day(g, mode):
    h = g["high"].to_numpy(); l = g["low"].to_numpy(); c = g["close"].to_numpy()
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
                trades.append({**pos, "res": "target", "pnl": RR * pos["rk"]}); pos = None
            elif i == pos["i"] + 1:
                # EB rule: first bar after entry, not climax, opposite IBS
                d = bar_dir(h, l, c, i)
                opp = (not cx[i]) and ((not sh and d == -1) or (sh and d == 1))
                pos["eb_opp"] = opp
                if opp and mode in ("SCRATCH", "REVERSE"):
                    sgn = -1 if sh else 1
                    trades.append({**pos, "res": "eb_exit", "pnl": (c[i] - pos["en"]) * sgn})
                    if mode == "REVERSE":
                        new_sh = not sh
                        hi2 = max(h[pos["i"]], h[i]); lo2 = min(l[pos["i"]], l[i])
                        en = c[i]
                        st = hi2 + TICK if new_sh else lo2 - TICK
                        rk = abs(en - st)
                        if rk >= TICK:
                            sg2 = -1 if new_sh else 1
                            pos = {"i": i, "short": new_sh, "en": en, "st": st, "rk": rk,
                                   "tg": en + sg2 * RR * rk, "eb_opp": False,
                                   "date": g["date"].iloc[0], "kind": "EBrev"}
                            continue
                    pos = None
        if pos is None or True:
            if not (cx[i] and cx[i - 1]):
                continue
            d1, d2 = bar_dir(h, l, c, i - 1), bar_dir(h, l, c, i)
            if d1 == 0 or d2 == 0 or d1 == d2:
                continue
            sig_short = d1 == 1
            if pos is not None:
                if sig_short != pos["short"]:
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
            pos = {"i": i, "short": sig_short, "en": en, "st": st, "rk": rk,
                   "tg": en + sgn * RR * rk, "eb_opp": False,
                   "date": g["date"].iloc[0], "kind": "flip"}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (c[n - 1] - pos["en"]) * sgn})
    return trades


def metrics(t):
    pnl = t["pnl"]
    eq = pnl.cumsum()
    dd = (eq - eq.cummax()).min()
    tgt = (t["res"] == "target").sum(); stp = (t["res"] == "stop").sum()
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"n": len(t), "win%": round(100 * tgt / max(1, tgt + stp), 1),
            "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "tot_pts": round(pnl.sum(), 1), "exp_$": round(pnl.mean() * PT_USD, 1),
            "exp_$net": round((pnl.mean() - FEE_RT) * PT_USD, 1),
            "maxDD_$": round(dd * PT_USD, 0)}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    all_dates = sorted(df["date"].unique())
    rows = []
    diag_lines = []
    for scope, dates in [("1yr", all_dates[-252:]), ("full", all_dates)]:
        sub = df[df["date"].isin(dates)]
        byday = {d: g.reset_index(drop=True) for d, g in sub.groupby("date")}
        for mode in ["CONTROL", "SCRATCH", "REVERSE"]:
            trades = []
            for d in sorted(byday):
                trades += sim_day(byday[d], mode)
            t = pd.DataFrame(trades)
            m = metrics(t); m["scope"] = scope; m["arm"] = mode
            rows.append(m)
            if mode == "CONTROL":
                fl = t[t["eb_opp"] == True]      # noqa: E712
                nf = t[t["eb_opp"] == False]     # noqa: E712
                diag_lines.append(
                    f"{scope} CONTROL diagnostic: EB-flagged n={len(fl)} "
                    f"avg {fl['pnl'].mean():+.3f} pt (win {(fl['res']=='target').mean():.1%}) | "
                    f"unflagged n={len(nf)} avg {nf['pnl'].mean():+.3f} pt "
                    f"(win {(nf['res']=='target').mean():.1%})")
    res = pd.DataFrame(rows)[["scope", "arm", "n", "win%", "PF", "tot_pts",
                              "exp_$", "exp_$net", "maxDD_$"]]
    res.to_csv(OUT / f"flip_eb_{today}.csv", index=False)
    print(res.to_string(index=False))
    print()
    print("\n".join(diag_lines))


if __name__ == "__main__":
    main()
