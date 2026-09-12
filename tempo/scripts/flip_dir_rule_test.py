"""flip_dir_rule_test.py — user rule: bar1 = color only, IBS on the SB only (S119).

User correction (2026-09-12): in the climax flip, only the SECOND bar's IBS matters;
the first climax bar just needs the correct COLOR (close vs open). The deployed rule
applies IBS bands (0.55/0.45, middle = dead) to BOTH bars.

Direction-rule variants (signal = adjacent climax pair, opposite direction):
  IBS2   both bars via IBS bands (deployed rule)
  COL1   bar1 via color (close>=open bull), SB via IBS bands  <- USER RULE
  COL2   both bars via color (original S117 base rule)

Part 1: head-to-head per year + IS 21-22 / OOS 23-26, in the stable WF family
        (RR2 + skip-hour-8-Basic + noEB), SAR off and on.
Part 2: walk-forward (protocol = flip_walkforward_v2: IS through 2022, expanding,
        select by prior-years PF/pts) with dir as a free 3-state axis:
        3 dir x 2 sar x 3 eb x 3 rr x 2 skip = 108 configs. Does a blind selector
        pick the user rule, and does OOS improve?

    python tempo/scripts/flip_dir_rule_test.py
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
        days.append({"date": d, "year": int(d[:4]), "h": h, "l": l, "c": c,
                     "cx": g["climax"].to_numpy(),
                     "d_ibs": np.where(ibs >= 0.55, 1, np.where(ibs <= 0.45, -1, 0)),
                     "d_co": np.where(c >= o, 1, -1),
                     "hr": pd.to_datetime(g["start"]).dt.hour.to_numpy(), "n": len(g)})
    return days


def sim_day(day, dirmode, sar, ebm, rr, skiph8b):
    """dirmode: IBS2 | COL1 | COL2. returns list of (pnl, kind, res)."""
    h, l, c, cx = day["h"], day["l"], day["c"], day["cx"]
    di, dc = day["d_ibs"], day["d_co"]
    d1v = dc if dirmode in ("COL1", "COL2") else di      # first bar of the pair
    d2v = dc if dirmode == "COL2" else di                # SB
    d_eb = di
    hr = day["hr"]; n = day["n"]
    out = []
    pos = None
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
        d1, d2 = d1v[i - 1], d2v[i]
        if d1 == 0 or d2 == 0 or d1 != -d2:
            continue
        sig_short = d1 == 1
        kind = "B"
        if pos is not None:
            if sar and sig_short != pos[0]:
                sh, en = pos[0], pos[1]
                out.append(((c[i] - en) * (-1 if sh else 1), pos[6], "rev"))
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
        out.append(((c[n - 1] - pos[1]) * (-1 if pos[0] else 1), pos[6], "open"))
    return out


def metrics(pnls):
    p = np.asarray(pnls, dtype=float)
    if len(p) == 0:
        return {"n": 0, "PF": np.nan, "tot_pts": 0.0, "$/trade": np.nan, "maxDD_$": 0.0}
    eq = p.cumsum()
    dd = (eq - np.maximum.accumulate(eq)).min()
    gp = p[p > 0].sum(); gl = -p[p < 0].sum()
    return {"n": len(p), "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "tot_pts": round(p.sum(), 1), "$/trade": round(p.mean() * PT_USD, 1),
            "maxDD_$": round(dd * PT_USD, 0)}


def cname(cfg):
    dm, sar, ebm, rr, sk = cfg
    return (dm + ("+SAR" if sar else "") + {"none": "", "scr": "+EBscr", "belim": "+EBbe"}[ebm]
            + f"+RR{rr}" + ("+skipH8b" if sk else ""))


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    days = prep_days(df)
    years = sorted({d["year"] for d in days})

    # Part 1: head-to-head in the stable family
    print("=== P1 head-to-head (RR2 + skipH8b + noEB), per year ===")
    fam = [(dm, sar) for dm in ("IBS2", "COL1", "COL2") for sar in (False, True)]
    pnls = {}
    for dm, sar in fam:
        yp = {y: [] for y in years}
        for day in days:
            yp[day["year"]] += [x[0] for x in sim_day(day, dm, sar, "none", 2, True)]
        pnls[(dm, sar)] = yp
    r1 = []
    for dm, sar in fam:
        name = dm + ("+SAR" if sar else "")
        for label, ys in [("IS 21-22", [y for y in years if y <= 2022]),
                          ("OOS 23-26", [y for y in years if y >= 2023])]:
            r1.append({"rule": name, "period": label,
                       **metrics([p for y in ys for p in pnls[(dm, sar)][y]])})
    t1 = pd.DataFrame(r1)
    print(t1.to_string(index=False))
    r1y = []
    for dm, sar in fam:
        rec = {"rule": dm + ("+SAR" if sar else "")}
        for y in years:
            rec[str(y)] = round(float(np.sum(pnls[(dm, sar)][y])), 0)
        r1y.append(rec)
    t1y = pd.DataFrame(r1y)
    print("\nper-year total pts:")
    print(t1y.to_string(index=False))

    # Part 2: walk-forward with dir axis free
    grid = list(itertools.product(["IBS2", "COL1", "COL2"], [True, False],
                                  ["none", "scr", "belim"], [1, 2, 3], [True, False]))
    print(f"\n=== P2 walk-forward, {len(grid)} configs, IS through 2022 ===")
    peryear = {}
    for cfg in grid:
        yp = {y: [] for y in years}
        for day in days:
            yp[day["year"]] += [x[0] for x in sim_day(day, *cfg)]
        peryear[cfg] = yp
    rows = []
    wf = {"pts": [], "pf": []}
    for Y in [y for y in years if y >= 2023]:
        trainy = [y for y in years if y < Y]
        scored = []
        for cfg, yp in peryear.items():
            tr = [p for y in trainy for p in yp[y]]
            tot = float(np.sum(tr)) if tr else -1e9
            gp = sum(p for p in tr if p > 0); gl = -sum(p for p in tr if p < 0)
            pf = (gp / gl) if gl > 0 and len(tr) >= 100 else -1e9
            scored.append((cfg, tot, pf))
        for tag, key in (("pts", 1), ("pf", 2)):
            cfg = max(scored, key=lambda x: x[key])[0]
            oos = peryear[cfg][Y]
            wf[tag] += oos
            rows.append({"select": tag, "test_year": Y, "picked": cname(cfg),
                         **metrics(oos)})
    t2 = pd.DataFrame(rows)
    print(t2.to_string(index=False))
    print("\nconcatenated OOS 23-26:")
    t3 = pd.DataFrame([{"row": f"WF select-by-{tag}", **metrics(wf[tag])} for tag in ("pts", "pf")])
    print(t3.to_string(index=False))

    t1.to_csv(OUT / f"flip_dirrule_h2h_{today}.csv", index=False)
    t1y.to_csv(OUT / f"flip_dirrule_h2h_yearly_{today}.csv", index=False)
    t2.to_csv(OUT / f"flip_dirrule_wf_years_{today}.csv", index=False)
    t3.to_csv(OUT / f"flip_dirrule_wf_summary_{today}.csv", index=False)


if __name__ == "__main__":
    main()
