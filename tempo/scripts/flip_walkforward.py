"""flip_walkforward.py — honest walk-forward of the climax-flip config (S119-tempo).

Answers: would the setup have made money if every rule choice had been made ONLY on
data available at the time? No hindsight, no full-history tuning.

Candidate grid = every axis explored in S117-S119 (48 configs):
  ibs      IBS direction bands 0.55/0.45 (middle = no signal)  vs  close>=open
  sar      opposite flip signal while in trade -> exit + reverse  vs  skip signal
  eb       EB scratch: first bar after entry non-climax w/ opposite IBS -> exit @ close
  rr       fixed target 1R / 2R / 3R
  skiph8b  skip BASIC (from flat) entries in the 8:xx hour; SAR entries unaffected
Shared mechanics (frozen): stop 1 tick beyond the 2-bar box, one position,
conservative both-in-bar -> stop, session end marked to close.

Walk-forward: for each test year Y in 2022..2026, pick the config with the best
TRAIN metric on ALL years < Y (expanding window), trade year Y with it, concatenate.
Selection metrics reported separately: (a) total gross points, (b) PF (min 100
train trades). The whole 21-26 result of the CURRENT hand-picked config is shown
for comparison — that one is in-sample by construction.

    python tempo/scripts/flip_walkforward.py
"""
from __future__ import annotations
import datetime as dt
import itertools
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
PT_USD = 50.0


def prep_days(df):
    days = []
    for d, g in df.groupby("date"):
        g = g.reset_index(drop=True)
        h = g["high"].to_numpy(); l = g["low"].to_numpy()
        o = g["open"].to_numpy(); c = g["close"].to_numpy()
        rg = h - l
        ibs = np.where(rg > TICK / 2, (c - l) / np.where(rg == 0, 1, rg), 0.5)
        d_ibs = np.where(ibs >= 0.55, 1, np.where(ibs <= 0.45, -1, 0))
        d_co = np.where(c >= o, 1, -1)
        hr = pd.to_datetime(g["start"]).dt.hour.to_numpy()
        days.append({"date": d, "year": int(d[:4]), "h": h, "l": l, "c": c,
                     "cx": g["climax"].to_numpy(), "d_ibs": d_ibs, "d_co": d_co,
                     "hr": hr, "n": len(g)})
    return days


def sim_day(day, ibs, sar, eb, rr, skiph8b):
    h, l, c, cx = day["h"], day["l"], day["c"], day["cx"]
    dd = day["d_ibs"] if ibs else day["d_co"]
    d_eb = day["d_ibs"]                     # EB rule always uses IBS bands
    hr = day["hr"]; n = day["n"]
    pnls = []
    pos = None
    for i in range(1, n):
        if pos is not None:
            sh, en, st, tg, rk, ei = pos
            sgn = -1 if sh else 1
            if (h[i] >= st) if sh else (l[i] <= st):
                pnls.append(-rk); pos = None
            elif (l[i] <= tg) if sh else (h[i] >= tg):
                pnls.append(rr * rk); pos = None
            elif eb and i == ei + 1 and (not cx[i]) and \
                    ((not sh and d_eb[i] == -1) or (sh and d_eb[i] == 1)):
                pnls.append((c[i] - en) * sgn); pos = None
        if not (cx[i] and cx[i - 1]):
            continue
        d1, d2 = dd[i - 1], dd[i]
        if d1 == 0 or d2 == 0 or d1 == d2:
            continue
        sig_short = d1 == 1
        from_sar = False
        if pos is not None:
            if sar and sig_short != pos[0]:
                sh, en, st, tg, rk, ei = pos
                sgn = -1 if sh else 1
                pnls.append((c[i] - en) * sgn); pos = None
                from_sar = True
            else:
                continue
        if skiph8b and not from_sar and hr[i] == 8:
            continue
        hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        en = c[i]
        st = hi2 + TICK if sig_short else lo2 - TICK
        rk = abs(en - st)
        if rk < TICK:
            continue
        sgn = -1 if sig_short else 1
        pos = (sig_short, en, st, en + sgn * rr * rk, rk, i)
    if pos is not None:
        sh, en, st, tg, rk, ei = pos
        pnls.append((c[n - 1] - en) * (-1 if sh else 1))
    return pnls


def metrics(pnl):
    pnl = np.asarray(pnl)
    if len(pnl) == 0:
        return {"n": 0, "PF": np.nan, "tot_pts": 0.0, "$/trade": np.nan, "maxDD_$": 0.0}
    eq = pnl.cumsum()
    dd = (eq - np.maximum.accumulate(eq)).min()
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"n": len(pnl), "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "tot_pts": round(pnl.sum(), 1),
            "$/trade": round(pnl.mean() * PT_USD, 1),
            "maxDD_$": round(dd * PT_USD, 0)}


def cname(cfg):
    ibs, sar, eb, rr, sk = cfg
    return (("IBS+" if ibs else "co+") + ("SAR+" if sar else "noSAR+")
            + ("EB+" if eb else "noEB+") + f"RR{rr}" + ("+skipH8b" if sk else ""))


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    days = prep_days(df)
    years = sorted({d["year"] for d in days})
    grid = list(itertools.product([True, False], [True, False], [True, False],
                                  [1, 2, 3], [True, False]))
    print(f"{len(grid)} configs x {len(days)} days ...")

    # per config: pnl list per year
    peryear = {}
    for cfg in grid:
        yp = {y: [] for y in years}
        for day in days:
            yp[day["year"]] += sim_day(day, *cfg)
        peryear[cfg] = yp

    rows = []
    wf = {"pts": [], "pf": []}
    for Y in [y for y in years if y > years[0]]:
        trainy = [y for y in years if y < Y]
        scored = []
        for cfg, yp in peryear.items():
            tr = [p for y in trainy for p in yp[y]]
            tot = float(np.sum(tr)) if tr else -1e9
            gp = sum(p for p in tr if p > 0); gl = -sum(p for p in tr if p < 0)
            pf = (gp / gl) if gl > 0 else -1e9
            scored.append((cfg, tot, pf if len(tr) >= 100 else -1e9))
        best_pts = max(scored, key=lambda x: x[1])[0]
        best_pf = max(scored, key=lambda x: x[2])[0]
        for tag, cfg in (("pts", best_pts), ("pf", best_pf)):
            oos = peryear[cfg][Y]
            wf[tag] += oos
            m = metrics(oos)
            rows.append({"select": tag, "test_year": Y, "picked": cname(cfg), **m})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / f"flip_walkforward_{today}.csv", index=False)
    print("\n=== per-year OOS: config picked on ALL prior years, traded next year ===")
    print(res.to_string(index=False))

    print("\n=== concatenated WALK-FORWARD out-of-sample (2022-2026) ===")
    cur = (True, True, True, 2, False)
    span = [p for y in years if y > years[0] for p in peryear[cur][y]]
    comp = [{"row": "WF (select by tot pts)", **metrics(wf["pts"])},
            {"row": "WF (select by PF)", **metrics(wf["pf"])},
            {"row": "current config 22-26 (IN-SAMPLE by construction)", **metrics(span)},
            {"row": "current config full 21-26 (in-sample)",
             **metrics([p for y in years for p in peryear[cur][y]])}]
    cres = pd.DataFrame(comp)
    cres.to_csv(OUT / f"flip_walkforward_summary_{today}.csv", index=False)
    print(cres.to_string(index=False))


if __name__ == "__main__":
    main()
