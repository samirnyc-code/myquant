"""flip_eb_belimit.py — the EB-flagged trades: scratch vs ride vs BE-limit (S119-tempo).

User: EB-scratch is 'setup 3' — what do JUST those trades come out to, vs not
scratching them, and vs a new variant: when the EB (first bar after entry, non-climax)
closes with the WRONG IBS, work a LIMIT at breakeven (entry price) instead of
scratching at the EB close.

Base config frozen: climax flip + IBS direction (0.55/0.45) + SAR + RR2 target,
stop 1 tick beyond box, one position, conservative both-in-bar -> stop, session
end marked to close.

Arms (differ ONLY in what happens on an EB wrong-IBS flag):
  RIDE        nothing (control) — flagged trades run to stop/target/SAR/eod
  SCRATCH     exit at EB close (current deployed rule)
  BE_TOUCH    from the bar after the EB, resting limit at ENTRY replaces the target;
              fills when price TOUCHES entry (long: high>=entry). Stop stays.
              Same-bar stop+BE -> STOP (conservative). SAR stays active.
  BE_THRU     same but fill requires trading THROUGH entry by 1 tick (conservative fill)
Note: after a flag the 2R target is unreachable before the BE limit (entry is between
price and target), so replacing the target loses nothing.

Periods: IS 2021-22 / OOS 2023-26 (user-set split), plus full.
Tables: T1 flagged trades only per arm; T2 whole system per arm; T3 current config
per setup (Basic / EB Reversal / the scratched trades).

    python tempo/scripts/flip_eb_belimit.py
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
    pos = None            # dict: short en st tg rk i kind flagged belim
    for i in range(1, n):
        if pos is not None:
            sh = pos["short"]; sgn = -1 if sh else 1
            if (h[i] >= pos["st"]) if sh else (l[i] <= pos["st"]):
                trades.append({**pos, "res": "stop", "pnl": -pos["rk"]}); pos = None
            elif pos["belim"] and ((l[i] <= pos["en"] - (TICK if mode == "BE_THRU" else 0))
                                   if sh else
                                   (h[i] >= pos["en"] + (TICK if mode == "BE_THRU" else 0))):
                trades.append({**pos, "res": "be_fill", "pnl": 0.0}); pos = None
            elif pos["tg"] is not None and ((l[i] <= pos["tg"]) if sh else (h[i] >= pos["tg"])):
                trades.append({**pos, "res": "target", "pnl": RR * pos["rk"]}); pos = None
            elif i == pos["i"] + 1:
                d = bar_dir(h, l, c, i)
                if (not cx[i]) and ((not sh and d == -1) or (sh and d == 1)):
                    pos["flagged"] = True
                    if mode == "SCRATCH":
                        trades.append({**pos, "res": "eb_scr", "pnl": (c[i] - pos["en"]) * sgn})
                        pos = None
                    elif mode in ("BE_TOUCH", "BE_THRU"):
                        pos["belim"] = True; pos["tg"] = None
        if not (cx[i] and cx[i - 1]):
            continue
        d1, d2 = bar_dir(h, l, c, i - 1), bar_dir(h, l, c, i)
        if d1 == 0 or d2 == 0 or d1 == d2:
            continue
        sig_short = d1 == 1
        kind = "Basic"
        if pos is not None:
            if sig_short != pos["short"]:
                sgn = -1 if pos["short"] else 1
                trades.append({**pos, "res": "rev", "pnl": (c[i] - pos["en"]) * sgn})
                pos = None; kind = "EBrev"
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
               "tg": en + sgn * RR * rk, "kind": kind, "flagged": False,
               "belim": False, "date": g["date"].iloc[0]}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (c[n - 1] - pos["en"]) * sgn})
    return trades


def stats(t, label):
    if len(t) == 0:
        return {"group": label, "n": 0}
    pnl = t["pnl"]
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"group": label, "n": len(t),
            "win%": round(100 * (pnl > 0).mean(), 1),
            "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "tot_pts": round(pnl.sum(), 1),
            "$/trade": round(pnl.mean() * PT_USD, 1)}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    byday = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}

    arms = {}
    for mode in ["RIDE", "SCRATCH", "BE_TOUCH", "BE_THRU"]:
        trades = []
        for d in sorted(byday):
            trades += sim_day(byday[d], mode)
        t = pd.DataFrame(trades)
        t["year"] = t["date"].str[:4].astype(int)
        arms[mode] = t

    pers = [("IS 21-22", lambda t: t[t["year"] <= 2022]),
            ("OOS 23-26", lambda t: t[t["year"] >= 2023]),
            ("full", lambda t: t)]

    print("=== T1 the EB-FLAGGED trades only (what 'setup 3' comes out to) ===")
    r1 = []
    for pname, sel in pers:
        for mode, t in arms.items():
            f = sel(t[t["flagged"]])
            r1.append(stats(f, f"{mode:<9} {pname}"))
    print(pd.DataFrame(r1).to_string(index=False))
    rc = arms["RIDE"]
    fl = rc[rc["flagged"]]
    print("\nflagged-under-RIDE outcome mix (full): "
          + ", ".join(f"{k} {v}" for k, v in fl["res"].value_counts().items()))
    bt = arms["BE_TOUCH"]; bfl = bt[bt["flagged"]]
    print("BE_TOUCH flagged outcome mix (full):   "
          + ", ".join(f"{k} {v}" for k, v in bfl["res"].value_counts().items()))

    print("\n=== T2 WHOLE system per arm ===")
    r2 = []
    for pname, sel in pers:
        for mode, t in arms.items():
            r2.append(stats(sel(t), f"{mode:<9} {pname}"))
    print(pd.DataFrame(r2).to_string(index=False))

    print("\n=== T3 current config (SCRATCH) by setup ===")
    ts = arms["SCRATCH"]
    r3 = []
    for pname, sel in pers:
        s = sel(ts)
        r3 += [stats(s[s["kind"] == "Basic"], f"Basic      {pname}"),
               stats(s[s["kind"] == "EBrev"], f"EB Reversal {pname}"),
               stats(s[s["res"] == "eb_scr"], f"scratched  {pname}")]
    print(pd.DataFrame(r3).to_string(index=False))

    for name, rows in [("t1_flagged", r1), ("t2_system", r2), ("t3_setup", r3)]:
        pd.DataFrame(rows).to_csv(OUT / f"flip_eb_belimit_{name}_{today}.csv", index=False)
    arms["BE_TOUCH"].to_csv(OUT / f"flip_eb_belimit_trades_{today}.csv", index=False)


if __name__ == "__main__":
    main()
