"""flip_walkforward_v2.py — walk-forward, user spec: IS through 2022, per-setup (S119).

Changes vs v1: first in-sample block = ALL data through end-2022 (2021-06..2022-12),
first OOS year 2023, expanding window after; EB axis is now 3-state (none / scratch /
BE-limit-touch per flip_eb_belimit.py); OOS trades broken down by setup:
Basic (from flat) / EB Reversal (SAR entry) / scratched (res=eb_scr subset).

Grid: ibs x sar x {noEB, scratch, belim} x RR{1,2,3} x skipH8basic = 72 configs.
Shared mechanics frozen as always (stop 1t beyond box, one position, conservative
both-in-bar -> stop, session end -> close). Selection metrics: total gross points,
and PF (min 100 train trades) — reported separately.

    python tempo/scripts/flip_walkforward_v2.py
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
        days.append({"date": d, "year": int(d[:4]), "h": h, "l": l, "c": c,
                     "cx": g["climax"].to_numpy(), "d_ibs": d_ibs,
                     "d_co": np.where(c >= o, 1, -1),
                     "hr": pd.to_datetime(g["start"]).dt.hour.to_numpy(), "n": len(g)})
    return days


def sim_day(day, ibs, sar, ebm, rr, skiph8b):
    """returns list of (pnl, kind, res); kind: B=Basic, R=EBrev"""
    h, l, c, cx = day["h"], day["l"], day["c"], day["cx"]
    dd = day["d_ibs"] if ibs else day["d_co"]
    d_eb = day["d_ibs"]
    hr = day["hr"]; n = day["n"]
    out = []
    pos = None      # [short, en, st, tg, rk, i, kind, belim]
    for i in range(1, n):
        if pos is not None:
            sh, en, st, tg, rk, ei, kd, bl = pos
            sgn = -1 if sh else 1
            if (h[i] >= st) if sh else (l[i] <= st):
                out.append((-rk, kd, "stop")); pos = None
            elif bl and ((l[i] <= en) if sh else (h[i] >= en)):
                out.append((0.0, kd, "be_fill")); pos = None
            elif tg is not None and ((l[i] <= tg) if sh else (h[i] >= tg)):
                out.append((rr * rk, kd, "target")); pos = None
            elif ebm != "none" and i == ei + 1 and (not cx[i]) and \
                    ((not sh and d_eb[i] == -1) or (sh and d_eb[i] == 1)):
                if ebm == "scr":
                    out.append(((c[i] - en) * sgn, kd, "eb_scr")); pos = None
                else:                               # belim
                    pos = [sh, en, st, None, rk, ei, kd, True]
        if not (cx[i] and cx[i - 1]):
            continue
        d1, d2 = dd[i - 1], dd[i]
        if d1 == 0 or d2 == 0 or d1 == d2:
            continue
        sig_short = d1 == 1
        kind = "B"
        if pos is not None:
            if sar and sig_short != pos[0]:
                sh, en, st, tg, rk, ei, kd, bl = pos
                out.append(((c[i] - en) * (-1 if sh else 1), kd, "rev"))
                pos = None; kind = "R"
            else:
                continue
        if skiph8b and kind == "B" and hr[i] == 8:
            continue
        hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        en = c[i]
        st = hi2 + TICK if sig_short else lo2 - TICK
        rk = abs(en - st)
        if rk < TICK:
            continue
        sgn = -1 if sig_short else 1
        pos = [sig_short, en, st, en + sgn * rr * rk, rk, i, kind, False]
    if pos is not None:
        sh, en = pos[0], pos[1]
        out.append(((c[n - 1] - en) * (-1 if sh else 1), pos[6], "open"))
    return out


def metrics(tr):
    pnl = np.array([x[0] for x in tr])
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
    ibs, sar, ebm, rr, sk = cfg
    return (("IBS+" if ibs else "co+") + ("SAR+" if sar else "noSAR+")
            + {"none": "noEB", "scr": "EBscr", "belim": "EBbe"}[ebm]
            + f"+RR{rr}" + ("+skipH8b" if sk else ""))


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    days = prep_days(df)
    years = sorted({d["year"] for d in days})
    grid = list(itertools.product([True, False], [True, False],
                                  ["none", "scr", "belim"], [1, 2, 3], [True, False]))
    print(f"{len(grid)} configs x {len(days)} days ...")

    peryear = {}
    for cfg in grid:
        yp = {y: [] for y in years}
        for day in days:
            yp[day["year"]] += sim_day(day, *cfg)
        peryear[cfg] = yp

    rows = []
    wf = {"pts": [], "pf": []}
    for Y in [y for y in years if y >= 2023]:
        trainy = [y for y in years if y < Y]
        scored = []
        for cfg, yp in peryear.items():
            tr = [x for y in trainy for x in yp[y]]
            pnl = [x[0] for x in tr]
            tot = float(np.sum(pnl)) if pnl else -1e9
            gp = sum(p for p in pnl if p > 0); gl = -sum(p for p in pnl if p < 0)
            pf = (gp / gl) if gl > 0 and len(pnl) >= 100 else -1e9
            scored.append((cfg, tot, pf))
        best_pts = max(scored, key=lambda x: x[1])[0]
        best_pf = max(scored, key=lambda x: x[2])[0]
        for tag, cfg in (("pts", best_pts), ("pf", best_pf)):
            oos = peryear[cfg][Y]
            wf[tag] += oos
            rows.append({"select": tag, "test_year": Y, "picked": cname(cfg),
                         **metrics(oos)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / f"flip_wf2_years_{today}.csv", index=False)
    print("\n=== per-year OOS (IS = everything through 2022, expanding) ===")
    print(res.to_string(index=False))

    print("\n=== concatenated OOS 2023-26 ===")
    comp = []
    for tag in ("pts", "pf"):
        comp.append({"row": f"WF select-by-{tag}", **metrics(wf[tag])})
    cur = (True, True, "scr", 2, False)
    oos_cur = [x for y in years if y >= 2023 for x in peryear[cur][y]]
    comp.append({"row": "current config 23-26 (in-sample-flavored)", **metrics(oos_cur)})
    cres = pd.DataFrame(comp)
    cres.to_csv(OUT / f"flip_wf2_summary_{today}.csv", index=False)
    print(cres.to_string(index=False))

    print("\n=== WF OOS trades by SETUP ===")
    srows = []
    for tag in ("pts", "pf"):
        tr = wf[tag]
        srows += [{"select": tag, "setup": "Basic",
                   **metrics([x for x in tr if x[1] == "B" and x[2] != "eb_scr"])},
                  {"select": tag, "setup": "EB Reversal",
                   **metrics([x for x in tr if x[1] == "R" and x[2] != "eb_scr"])},
                  {"select": tag, "setup": "scratched/BE (setup 3)",
                   **metrics([x for x in tr if x[2] in ("eb_scr", "be_fill")])}]
    sres = pd.DataFrame(srows)
    sres.to_csv(OUT / f"flip_wf2_setups_{today}.csv", index=False)
    print(sres.to_string(index=False))


if __name__ == "__main__":
    main()
