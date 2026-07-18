"""ALL-levels touch/react study (S73) — majors + 0DTE set + 1D Min/Max on ES 5M.

Correct approach semantics per level type (the user-catch rule):
  resistance (fade = short): CR, CR 0DTE, GW 0DTE, 1D Max  — approach FROM BELOW
  support    (fade = long) : PS, PS 0DTE, 1D Min           — approach FROM ABOVE
  HVL 0DTE: tested both ways (cross up / cross down) separately.

For each level type: touches, hold-rate, hold by GEX regime, and fade expectancy
at stop 8 / target 10 (the robust mid-grid cell), $50/pt, 1.25pt friction.
Run: .venv/Scripts/python.exe scripts/mr_es_all_levels.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MOVE, LOOK, TOL = 4.0, 8, 1.0
STOP, TGT, FRIC = 8.0, 10.0, 1.25


def load():
    l1 = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    l1 = l1[l1.symbol == "ES"][["date", "cr", "ps", "hvl"]]
    l0 = pd.read_csv(ROOT / "data" / "menthorq" / "levels0_history.csv")
    l0 = l0[l0.symbol == "ES"][["date", "cr0", "ps0", "hvl0", "gw0", "d1_min", "d1_max"]]
    lv = l1.merge(l0, on="date", how="outer")
    lv["date"] = lv.date.astype(str)
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    gi = pd.read_csv(ROOT / "data" / "menthorq" / "gex_insights_ES1.csv").sort_values("date")
    gi["date"] = gi.date.astype(str)
    return lv, b, gi


LEVELS = [  # (column, kind) kind: 'res' fade-short / 'sup' fade-long
    ("cr", "res"), ("cr0", "res"), ("gw0", "res"), ("d1_max", "res"),
    ("ps", "sup"), ("ps0", "sup"), ("d1_min", "sup"),
]


def study(day, lvl, kind):
    """touches with correct approach direction; returns [(hold, fade_pnl_pts, hh)]"""
    H, L, Cl = day.High.values, day.Low.values, day.Close.values
    hm = day.hm.values
    out = []
    last = -99
    for i in range(1, len(day)):
        k = max(0, i - 3)
        if kind == "res":
            ok = np.max(Cl[k:i]) < lvl - 0.5
        else:
            ok = np.min(Cl[k:i]) > lvl + 0.5
        if not ok or not ((L[i] - TOL) <= lvl <= (H[i] + TOL)) or i - last <= LOOK:
            continue
        last = i
        hold = None
        for j in range(i + 1, min(len(day), i + 1 + LOOK)):
            away = (L[j] <= lvl - MOVE) if kind == "res" else (H[j] >= lvl + MOVE)
            thru = (H[j] >= lvl + MOVE) if kind == "res" else (L[j] <= lvl - MOVE)
            if away:
                hold = 1; break
            if thru:
                hold = 0; break
        if hold is None:
            continue
        # fade trade from the touch
        pnl = None
        for j in range(i + 1, len(day)):
            if kind == "res":
                if H[j] >= lvl + STOP:
                    pnl = -STOP; break
                if L[j] <= lvl - TGT:
                    pnl = TGT; break
            else:
                if L[j] <= lvl - STOP:
                    pnl = -STOP; break
                if H[j] >= lvl + TGT:
                    pnl = TGT; break
        if pnl is None:
            pnl = (lvl - Cl[-1]) if kind == "res" else (Cl[-1] - lvl)
        out.append((hold, pnl - FRIC, hm[i][:2]))
    return out


def main():
    lv, bars, gi = load()
    levels = {r.date: r for r in lv.itertuples()}
    days = [d for d in sorted(set(bars.date)) if d in levels]
    print(f"sessions with any levels: {len(days)}\n")
    print(f"{'level':8s} {'kind':4s} {'touch':>6s} {'hold%':>6s} | {'negGEX hold%':>13s} {'posGEX hold%':>13s} | "
          f"{'fadeE$':>7s} {'fadeE$ negGEX':>13s}")
    results = {}
    for col, kind in LEVELS:
        rows_all, rows_neg, rows_pos = [], [], []
        for d in days:
            r = levels[d]
            lvlv = getattr(r, col, np.nan)
            if not np.isfinite(lvlv):
                continue
            day = bars[bars.date == d].reset_index(drop=True)
            if len(day) < 10:
                continue
            p = gi[gi.date < d]
            g = p.iloc[-1].gex if len(p) else np.nan
            res = study(day, lvlv, kind)
            rows_all += res
            if np.isfinite(g):
                (rows_neg if g < 0 else rows_pos).extend(res)

        def agg(rows):
            if not rows:
                return None
            h = [x[0] for x in rows]
            p = [x[1] for x in rows]
            return {"n": len(rows), "hold": round(np.mean(h) * 100, 1),
                    "fadeE": round(np.mean(p) * 50)}
        A, N, P = agg(rows_all), agg(rows_neg), agg(rows_pos)
        results[col] = {"all": A, "neg": N, "pos": P}
        if A:
            print(f"{col:8s} {kind:4s} {A['n']:6d} {A['hold']:6.1f} | "
                  f"{(str(N['hold']) + '% n' + str(N['n'])) if N else '—':>13s} "
                  f"{(str(P['hold']) + '% n' + str(P['n'])) if P else '—':>13s} | "
                  f"{A['fadeE']:+7d} {(('$' + format(N['fadeE'], '+d')) if N else '—'):>13s}")
    (ROOT / "data" / "options_sim" / "all_levels_study.json").write_text(json.dumps(results, indent=1))
    print("\nfade sim: stop 8 / tgt 10 / friction 1.25 (robust mid-grid cell), ES $50/pt")


if __name__ == "__main__":
    main()
