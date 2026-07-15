"""Full validation gauntlet for EVERY level's first-touch fade (S73 follow-up to
note 0016 — user push: 'they all look positive, prove which survive').

For each level (correct fade direction, first from-below/above touch per day,
any regime): 6x6 stop/target sweep, % positive cells, reference-cell stats,
chronological 2/3-1/3 OOS split, monthly spread. Repaired bars only.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
FRIC = 1.25
STOPS = [3, 4, 5, 6, 8, 10]
TGTS = [6, 8, 10, 12, 15, 20]
LEVELS = [("cr", "res"), ("cr0", "res"), ("d1_max", "res"),
          ("ps", "sup"), ("ps0", "sup"), ("d1_min", "sup")]


def load():
    l1 = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    l1 = l1[l1.symbol == "ES"][["date", "cr", "ps", "hvl"]]
    l0 = pd.read_csv(ROOT / "data" / "menthorq" / "levels0_history.csv")
    l0 = l0[l0.symbol == "ES"][["date", "cr0", "ps0", "d1_min", "d1_max"]]
    lv = l1.merge(l0, on="date", how="outer")
    lv["date"] = lv.date.astype(str)
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    return lv, b


def entries_for(lv, bars, col, kind):
    levels = {r.date: getattr(r, col) for r in lv.itertuples()
              if np.isfinite(getattr(r, col, np.nan))}
    out = []
    for d in sorted(set(bars.date)):
        if d not in levels:
            continue
        day = bars[bars.date == d].reset_index(drop=True)
        if len(day) < 10:
            continue
        lvl = levels[d]
        H, L, Cl = day.High.values, day.Low.values, day.Close.values
        for i in range(1, len(day)):
            k = max(0, i - 3)
            ok = (np.max(Cl[k:i]) < lvl - 0.5) if kind == "res" else (np.min(Cl[k:i]) > lvl + 0.5)
            if ok and (L[i] - 1.0) <= lvl <= (H[i] + 1.0):
                out.append((d, day, lvl, i))
                break
    return out


def pnl_for(day, lvl, ti, stop, tgt, kind):
    H, L, Cl = day.High.values, day.Low.values, day.Close.values
    for j in range(ti + 1, len(day)):
        if kind == "res":
            if H[j] >= lvl + stop:
                return -stop - FRIC
            if L[j] <= lvl - tgt:
                return tgt - FRIC
        else:
            if L[j] <= lvl - stop:
                return -stop - FRIC
            if H[j] >= lvl + tgt:
                return tgt - FRIC
    raw = (lvl - Cl[-1]) if kind == "res" else (Cl[-1] - lvl)
    return raw - FRIC


def main():
    lv, bars = load()
    print(f"{'level':8s} {'dir':4s} {'n':>4s} {'mo.spread':>10s} {'cells+':>7s} "
          f"{'ref E$':>7s} {'ref win':>8s} {'ref tot':>9s} {'maxDD':>8s} {'IS E$':>7s} {'OOS E$':>7s}  verdict")
    for col, kind in LEVELS:
        ents = entries_for(lv, bars, col, kind)
        if len(ents) < 8:
            print(f"{col:8s} {kind:4s} {len(ents):4d}  — too few entries")
            continue
        months = len({d[:7] for d, *_ in ents})
        pos = 0
        for s in STOPS:
            for t in TGTS:
                p = np.array([pnl_for(day, lvl, ti, s, t, kind) for _, day, lvl, ti in ents])
                pos += p.mean() > 0
        p_ref = np.array([pnl_for(day, lvl, ti, 8, 10, kind) for _, day, lvl, ti in ents])
        eq = np.cumsum(p_ref * 50)
        dd = (eq - np.maximum.accumulate(eq)).min()
        dates = [d for d, *_ in ents]
        cut = sorted(dates)[int(len(dates) * 0.66)]
        is_p = np.array([pnl_for(day, lvl, ti, 8, 10, kind) for d, day, lvl, ti in ents if d <= cut])
        oos_p = np.array([pnl_for(day, lvl, ti, 8, 10, kind) for d, day, lvl, ti in ents if d > cut])
        cells_pct = pos / 36 * 100
        verdict = ("SURVIVES" if cells_pct >= 85 and oos_p.mean() > 0 else
                   "fragile" if cells_pct >= 60 else "REJECT")
        print(f"{col:8s} {kind:4s} {len(ents):4d} {months:6d}/12 {pos:4d}/36 "
              f"{p_ref.mean() * 50:+7.0f} {(p_ref > 0).mean() * 100:7.0f}% {p_ref.sum() * 50:+9,.0f} "
              f"{dd:+8,.0f} {is_p.mean() * 50:+7.0f} {oos_p.mean() * 50:+7.0f}  {verdict}")
    print("\nref cell = stop 8 / tgt 10; OOS = last 1/3 chronological; friction 1.25pt; $50/pt")


if __name__ == "__main__":
    main()
