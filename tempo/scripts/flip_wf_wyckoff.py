"""flip_wf_wyckoff.py — does the full walk-forward ADOPT the Wyckoff effort filter?

Extends flip_walkforward_v2.py by ONE axis: wyckoff in {off, on}.
  wyckoff on = skip any climax-flip entry (Basic or SAR-reversal) whose reversal
  bar traded MORE volume than the trap bar (sb_vol_rel = vol[SB]/vol[trap] > 1.0).
  The 1.0 boundary is the Wyckoff-theoretic Terminal-Shakeout line (Spring #1),
  NOT a fitted value -> zero extra fitting added to the walk-forward.

Applied IN-SIM so it composes correctly with SAR (a filtered reversal still CLOSES
the old position; it just doesn't open the new one).

Grid = ibs x sar x {noEB,scr,belim} x RR{1,2,3} x skipH8b x wyckoff{off,on} = 144.
IS = everything through 2022, expanding; OOS years 2023-26. Selection on TRAIN only
(by total gross points, and by PF>=100 trades) -> report OOS, and how often the WF
picks wyckoff=on.

    python tempo/scripts/flip_wf_wyckoff.py
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
WYCK_CUT = 1.0     # Wyckoff boundary: SB volume > trap volume => Terminal Shakeout


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
                     "vol": g["vol"].to_numpy(dtype=float),
                     "hr": pd.to_datetime(g["start"]).dt.hour.to_numpy(), "n": len(g)})
    return days


def sim_day(day, ibs, sar, ebm, rr, skiph8b, wyck):
    h, l, c, cx = day["h"], day["l"], day["c"], day["cx"]
    vol = day["vol"]
    dd = day["d_ibs"] if ibs else day["d_co"]
    d_eb = day["d_ibs"]; hr = day["hr"]; n = day["n"]
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
                else:
                    pos = [sh, en, st, None, rk, ei, kd, True]
        if not (cx[i] and cx[i - 1]):
            continue
        d1, d2 = dd[i - 1], dd[i]
        if d1 == 0 or d2 == 0 or d1 == d2:
            continue
        sig_short = d1 == 1
        kind = "B"
        # Wyckoff effort filter: reversal bar volume vs trap bar volume
        wyck_skip = wyck and (vol[i - 1] > 0) and (vol[i] / vol[i - 1] > WYCK_CUT)
        if pos is not None:
            if sar and sig_short != pos[0]:
                sh, en, st, tg, rk, ei, kd, bl = pos
                out.append(((c[i] - en) * (-1 if sh else 1), kd, "rev"))
                pos = None; kind = "R"
            else:
                continue
        if wyck_skip:               # close-only on SAR; never open a filtered entry
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
            "tot_pts": round(pnl.sum(), 1), "$/trade": round(pnl.mean() * PT_USD, 1),
            "maxDD_$": round(dd * PT_USD, 0)}


def cname(cfg):
    ibs, sar, ebm, rr, sk, wy = cfg
    return (("IBS+" if ibs else "co+") + ("SAR+" if sar else "noSAR+")
            + {"none": "noEB", "scr": "EBscr", "belim": "EBbe"}[ebm]
            + f"+RR{rr}" + ("+skipH8b" if sk else "") + ("+WYCK" if wy else ""))


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    days = prep_days(df)
    years = sorted({d["year"] for d in days})
    grid = list(itertools.product([True, False], [True, False],
                                  ["none", "scr", "belim"], [1, 2, 3],
                                  [True, False], [False, True]))
    print(f"{len(grid)} configs x {len(days)} days ...")

    peryear = {}
    for cfg in grid:
        yp = {y: [] for y in years}
        for day in days:
            yp[day["year"]] += sim_day(day, *cfg)
        peryear[cfg] = yp

    rows = []
    wf = {"pts": [], "pf": []}
    picks = {"pts": [], "pf": []}
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
            picks[tag].append((Y, cname(cfg), cfg[5]))
            rows.append({"select": tag, "test_year": Y, "picked": cname(cfg),
                         "wyck_on": cfg[5], **metrics(oos)})
    res = pd.DataFrame(rows)
    res.to_csv(OUT / f"flip_wf_wyckoff_years_{today}.csv", index=False)
    print("\n=== per-year OOS picks (IS through 2022, expanding) ===")
    print(res.to_string(index=False))

    print("\n=== concatenated OOS 2023-26 ===")
    comp = []
    for tag in ("pts", "pf"):
        comp.append({"row": f"WF select-by-{tag} (144-grid, wyck available)",
                     "wyck_picked": sum(1 for _, _, w in picks[tag] if w),
                     **metrics(wf[tag])})
    # forced comparisons: best NON-wyckoff vs same config +wyckoff, WF-stable
    stable = (True, False, "none", 2, True)     # IBS+noSAR+noEB+RR2+skipH8b (S119 WF pick)
    for wy, lab in ((False, "WF-stable base (no wyck)"), (True, "WF-stable + WYCK")):
        cfg = stable + (wy,)
        oos = [x for y in years if y >= 2023 for x in peryear[cfg][y]]
        comp.append({"row": lab, "wyck_picked": int(wy), **metrics(oos)})
    cres = pd.DataFrame(comp)
    cres.to_csv(OUT / f"flip_wf_wyckoff_summary_{today}.csv", index=False)
    print(cres.to_string(index=False))

    # per-year equity for the WF-stable base vs +wyck (for charts)
    eq_rows = []
    for wy, lab in ((False, "base"), (True, "wyck")):
        cfg = stable + (wy,)
        for y in years:
            eq_rows.append({"config": lab, "year": y, **metrics(peryear[cfg][y])})
    pd.DataFrame(eq_rows).to_csv(OUT / f"flip_wf_wyckoff_peryear_{today}.csv", index=False)
    print("\nsaved years/summary/peryear CSVs ->", OUT)


if __name__ == "__main__":
    main()
