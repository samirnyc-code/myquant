"""Validate the discriminator features on ALL CR touches (S73) — not just the
18 fade trades. If CR-height (vs HVL, vs open) and QScore-option genuinely govern
hold vs break, they must show up across ~160 touches with real n.

Hold definition: after touch, 4pt retrace before 4pt break (LOOK 8 bars) — same
as the v2 study. Buckets report hold-rate + n.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MOVE, LOOK, TOL, CUTOFF = 4.0, 8, 1.0, "23:59"


def load():
    lv = pd.read_csv(ROOT / "data" / "menthorq" / "levels_history.csv")
    lv = lv[lv.symbol == "ES"].copy(); lv["date"] = lv.date.astype(str)
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"]); b["date"] = b.DateTime.dt.strftime("%H").radd("")  # placeholder
    b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous_unadj.parquet")
    b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["date"] = b.DateTime.dt.strftime("%Y-%m-%d")
    b["hm"] = b.DateTime.dt.strftime("%H:%M")
    gi = pd.read_csv(ROOT / "data" / "menthorq" / "gex_insights_ES1.csv").sort_values("date")
    gi["date"] = gi.date.astype(str)
    qs = pd.read_csv(ROOT / "data" / "menthorq" / "qscore_ES1.csv")
    qs["date"] = qs.date.astype(str)
    qsm = {r.date: r for r in qs.itertuples()}
    return lv, b, gi, qsm


def touches_with_features(lv, bars, gi, qsm):
    levels = {r.date: r for r in lv.itertuples()}
    rows = []
    prev_close = None
    for d in sorted(set(bars.date)):
        day = bars[bars.date == d].reset_index(drop=True)
        pc = prev_close
        prev_close = day.Close.values[-1] if len(day) else prev_close
        if d not in levels or len(day) < 10 or not np.isfinite(levels[d].cr):
            continue
        cr, hvl = levels[d].cr, levels[d].hvl
        p = gi[gi.date < d]
        gex = p.iloc[-1].gex if len(p) else np.nan
        q = qsm.get(d)
        H, L, O = day.High.values, day.Low.values, day.Open.values
        hm = day.hm.values
        Cl = day.Close.values
        last = -99
        for i in range(len(day)):
            # APPROACH FROM BELOW required (user catch): the prior 3 bars must have
            # been trading under the level — price rallying UP into resistance.
            if i < 1:
                continue
            k = max(0, i - 3)
            from_below = np.max(Cl[k:i]) < cr - 0.5
            if from_below and (L[i] - TOL) <= cr <= (H[i] + TOL) and i - last > LOOK:
                last = i
                res = None
                for j in range(i + 1, min(len(day), i + 1 + LOOK)):
                    if L[j] <= cr - MOVE:
                        res = 1; break     # hold/reject
                    if H[j] >= cr + MOVE:
                        res = 0; break     # break
                if res is None:
                    continue
                rows.append({
                    "date": d, "hold": res, "hour": hm[i][:2],
                    "gex_neg": int(gex < 0) if np.isfinite(gex) else np.nan,
                    "cr_minus_hvl": cr - hvl if np.isfinite(hvl) else np.nan,
                    "cr_minus_open": cr - O[0],
                    "gap": (O[0] - pc) if pc else np.nan,
                    "q_option": getattr(q, "option", np.nan) if q else np.nan,
                    "q_momentum": getattr(q, "momentum", np.nan) if q else np.nan,
                })
    return pd.DataFrame(rows)


def bucket_report(df, col, edges, labels):
    print(f"\n  hold-rate by {col}:")
    df = df.dropna(subset=[col])
    df["_b"] = pd.cut(df[col], edges, labels=labels)
    for b, g in df.groupby("_b", observed=True):
        if len(g) >= 8:
            print(f"    {str(b):12s} n {len(g):4d}  hold {g.hold.mean() * 100:5.1f}%")


def main():
    lv, bars, gi, qsm = load()
    df = touches_with_features(lv, bars, gi, qsm)
    print(f"ALL CR touches with outcome: {len(df)}  (base hold {df.hold.mean() * 100:.1f}%)")
    bucket_report(df, "cr_minus_hvl", [-1e9, 50, 100, 150, 1e9],
                  ["<50", "50-100", "100-150", ">150"])
    bucket_report(df, "cr_minus_open", [-1e9, 0, 15, 35, 1e9],
                  ["below open", "0-15", "15-35", ">35"])
    bucket_report(df, "gap", [-1e9, -5, 5, 1e9], ["gap dn", "flat", "gap up"])
    bucket_report(df, "q_option", [-0.1, 1.5, 2.5, 5.1], ["low 0-1", "mid 2", "high 3-5"])
    bucket_report(df, "q_momentum", [-0.1, 2.5, 5.1], ["low", "high"])
    # the money cross: neg-GEX x cr_minus_hvl
    print("\n  CROSS: gex_neg x cr_minus_hvl>100:")
    d2 = df.dropna(subset=["gex_neg", "cr_minus_hvl"])
    for gn in (1, 0):
        for far in (1, 0):
            g = d2[(d2.gex_neg == gn) & ((d2.cr_minus_hvl > 100).astype(int) == far)]
            if len(g) >= 6:
                print(f"    negGEX={gn} far={far}: n {len(g):4d}  hold {g.hold.mean() * 100:5.1f}%")
    df.to_csv(ROOT / "data" / "options_sim" / "cr_touches_features.csv", index=False)


if __name__ == "__main__":
    main()
