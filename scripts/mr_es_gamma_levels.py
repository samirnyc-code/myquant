"""ES gamma-level edge study (S73, user directive #1) — do ES 5M bars respect
MenthorQ's CR / PS / HVL levels, and is there a tradeable edge?

Data:
  data/menthorq/levels_history.csv  ES rows: date -> cr/ps/hvl (levels KNOWN at
      each session's open, computed from prior EOD -> causal to trade that day)
  data/bars/_continuous.parquet     ES 5M RTH bars (CT, OPEN-stamped)
Overlap ~229 sessions (2025-07 .. 2026-06).

STUDY A — touch & react (S66 asked this; got ~50% for MenthorQ's own hold-rate):
  A "touch" = a 5M bar whose range contains the level (first touch/day/level).
  After the touch, which happens first over the next LOOK bars:
    reject = price moves MOVE pts back to the origin side, or
    break  = price moves MOVE pts through the level.
  hold_rate = rejects / (rejects+breaks). >55% or <45% = exploitable asymmetry.

STUDY B — fade vs break expectancy (ES points, the tradeable test):
  FADE: at CR touch go short (at PS touch go long), stop MOVE beyond, target the
        opposite move. BREAK: opposite. Net ES points per trade, both directions.

STUDY C — HVL regime: is the session trend/So different above vs below HVL?

Run: .venv/Scripts/python.exe scripts/mr_es_gamma_levels.py
Optional: --move 4 --look 8 --tol 1.0   (pts; ES tick=0.25, $12.50/pt on MES... ES=$50/pt)
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    lv = lv[lv.symbol == "ES"].copy()
    lv["date"] = lv.date.astype(str)
    levels = {r.date: {"cr": r.cr, "ps": r.ps, "hvl": r.hvl} for r in lv.itertuples()}
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    return levels, b


def touch_react(day, lvl, side, MOVE, LOOK, TOL):
    """side: 'res' (approach from below) or 'sup' (from above). Returns list of
    ('reject'|'break', touch_time, entry_px)."""
    H, L, C, O = day.High.values, day.Low.values, day.Close.values, day.Open.values
    hm = day.hm.values
    out = []
    i = 0
    n = len(day)
    touched_bar = -99
    while i < n:
        if (L[i] - TOL) <= lvl <= (H[i] + TOL) and i - touched_bar > LOOK:
            touched_bar = i
            entry = lvl
            res = None
            for j in range(i + 1, min(n, i + 1 + LOOK)):
                if side == "res":
                    if L[j] <= lvl - MOVE:
                        res = "reject"; break
                    if H[j] >= lvl + MOVE:
                        res = "break"; break
                else:
                    if H[j] >= lvl + MOVE:
                        res = "reject"; break
                    if L[j] <= lvl - MOVE:
                        res = "break"; break
            if res:
                out.append((res, hm[i], entry))
        i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--move", type=float, default=4.0)
    ap.add_argument("--look", type=int, default=8)   # 8*5m = 40min window
    ap.add_argument("--tol", type=float, default=1.0)
    a = ap.parse_args()
    levels, bars = load()
    days = [d for d in sorted(set(bars.date)) if d in levels]
    print(f"ES level study — {len(days)} sessions with levels, "
          f"MOVE={a.move}pt LOOK={a.look}bars({a.look*5}m) TOL={a.tol}pt\n")

    stats = {"cr": {"reject": 0, "break": 0}, "ps": {"reject": 0, "break": 0}}
    by_hour = {}
    fade_pnl = {"cr": [], "ps": []}
    hvl_above_ret, hvl_below_ret = [], []

    for d in days:
        day = bars[bars.date == d].reset_index(drop=True)
        if len(day) < 10:
            continue
        cr, ps, hvl = levels[d]["cr"], levels[d]["ps"], levels[d]["hvl"]
        # STUDY A/B: resistance = CR, support = PS
        for lvl, key, side in [(cr, "cr", "res"), (ps, "ps", "sup")]:
            if not np.isfinite(lvl):
                continue
            for res, hm, entry in touch_react(day, lvl, side, a.move, a.look, a.tol):
                stats[key][res] += 1
                hh = hm[:2]
                by_hour.setdefault(hh, {"reject": 0, "break": 0})[res] += 1
                # fade trade: reject => +MOVE, break => -MOVE (ES points, before costs)
                fade_pnl[key].append(a.move if res == "reject" else -a.move)
        # STUDY C: HVL regime — session return sign vs open-side of HVL
        if np.isfinite(hvl):
            o, c = day.Open.iloc[0], day.Close.iloc[-1]
            ret = c - o
            (hvl_above_ret if o > hvl else hvl_below_ret).append(ret)

    print("=== STUDY A — touch & react hold-rates ===")
    for key in ("cr", "ps"):
        r, b = stats[key]["reject"], stats[key]["break"]
        tot = r + b
        hr = r / tot * 100 if tot else 0
        print(f"  {key.upper():3s}: {tot:4d} touches  reject {r:4d}  break {b:4d}  "
              f"HOLD-RATE {hr:5.1f}%  (fade edge {'YES' if abs(hr-50)>5 else 'weak'})")

    print("\n=== STUDY B — fade-the-level expectancy (ES pts, pre-cost) ===")
    for key in ("cr", "ps"):
        p = np.array(fade_pnl[key])
        if len(p):
            print(f"  fade {key.upper()}: n {len(p):4d}  E[pts] {p.mean():+.2f}  "
                  f"(break-trade E {-p.mean():+.2f})  total {p.sum():+.0f}pt")

    print("\n=== hold-rate by hour (CT) — CR+PS combined ===")
    for hh in sorted(by_hour):
        r, b = by_hour[hh]["reject"], by_hour[hh]["break"]
        t = r + b
        if t >= 8:
            print(f"  {hh}:00  n {t:3d}  hold {r/t*100:5.1f}%")

    print("\n=== STUDY C — HVL regime (session O->C return, ES pts) ===")
    for lbl, arr in [("open ABOVE hvl", hvl_above_ret), ("open BELOW hvl", hvl_below_ret)]:
        a_ = np.array(arr)
        if len(a_):
            print(f"  {lbl}: n {len(a_):3d}  mean {a_.mean():+.1f}  "
                  f"up-days {100*(a_>0).mean():.0f}%  |mean| {np.abs(a_).mean():.1f}")

    out = ROOT / "data" / "options_sim" / "es_levels_study.txt"
    print(f"\n(next: condition on aggregate GEX regime — directive #3)")


if __name__ == "__main__":
    main()
