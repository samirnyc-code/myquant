"""Stop/target sweep + monthly distribution for the 1D-Max fade (S73 night).
Entry: first touch of 1D Max (approach from below, any time RTH, any regime).
Short at the level; grid of stops/targets; mark-to-close if neither hits."""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FRIC = 1.25
STOPS = [3, 4, 5, 6, 8, 10]
TGTS = [6, 8, 10, 12, 15, 20]


def entries():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels0_history.csv")
    lv = lv[lv.symbol == "ES"].copy(); lv["date"] = lv.date.astype(str)
    levels = {r.date: r.d1_max for r in lv.itertuples() if np.isfinite(r.d1_max)}
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    out = []
    for d in sorted(set(b.date)):
        if d not in levels:
            continue
        day = b[b.date == d].reset_index(drop=True)
        if len(day) < 10:
            continue
        lvl = levels[d]
        H, L, Cl = day.High.values, day.Low.values, day.Close.values
        for i in range(1, len(day)):
            k = max(0, i - 3)
            if np.max(Cl[k:i]) < lvl - 0.5 and (L[i] - 1.0) <= lvl <= (H[i] + 1.0):
                out.append((d, day, lvl, i))
                break
    return out


def pnl_for(day, lvl, ti, stop, tgt):
    H, L, Cl = day.High.values, day.Low.values, day.Close.values
    for j in range(ti + 1, len(day)):
        if H[j] >= lvl + stop:
            return -stop - FRIC
        if L[j] <= lvl - tgt:
            return tgt - FRIC
    return (lvl - Cl[-1]) - FRIC


def main():
    ents = entries()
    print(f"1D-Max fade entries (from below, any regime): {len(ents)}")
    dates = [d for d, *_ in ents]
    months = pd.Series([d[:7] for d in dates]).value_counts().sort_index()
    print("per month:", dict(months), "\n")
    print("E[$/trade] (win%):")
    print("stop\\tgt " + "".join(f"{t:>14d}" for t in TGTS))
    pos = 0
    best = None
    for s in STOPS:
        row = []
        for t in TGTS:
            p = np.array([pnl_for(day, lvl, ti, s, t) for _, day, lvl, ti in ents])
            e = p.mean() * 50
            pos += e > 0
            row.append(f"{e:+7.0f} ({(p > 0).mean() * 100:3.0f}%)")
            if s == 8 and t == 10:
                eq = np.cumsum(p * 50)
                dd = (eq - np.maximum.accumulate(eq)).min()
                best = (len(p), (p > 0).mean() * 100, e, p.sum() * 50, dd)
        print(f"{s:>7}  " + " ".join(f"{c:>13s}" for c in row))
    print(f"\npositive cells: {pos}/{len(STOPS) * len(TGTS)}")
    n, w, e, tot, dd = best
    print(f"\nreference cell stop8/tgt10: n{n} win {w:.0f}% E ${e:+.0f} total ${tot:+,.0f} maxDD ${dd:+,.0f}")
    # OOS split: first 8 months vs last 4
    cut = sorted(dates)[int(len(dates) * 0.66)]
    a = [pnl_for(day, lvl, ti, 8, 10) for d, day, lvl, ti in ents if d <= cut]
    bpart = [pnl_for(day, lvl, ti, 8, 10) for d, day, lvl, ti in ents if d > cut]
    for lbl, arr in [("in-sample (first 2/3)", a), ("out-of-sample (last 1/3)", bpart)]:
        p = np.array(arr)
        print(f"{lbl}: n{len(p)} win {(p > 0).mean() * 100:.0f}% E ${p.mean() * 50:+.0f} total ${p.sum() * 50:+,.0f}")


if __name__ == "__main__":
    main()
