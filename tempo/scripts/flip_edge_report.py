"""flip_edge_report.py — plain-language edge report on the climax-flip trades (S119-tempo).

Input: tempo/outputs/flip_bucket_trades_2026-09-12.csv (the frozen RR2-control trades
with all entry-time features, from flip_bucket_study.py). No re-simulation: skipping a
trade in reality would change the SAR chain slightly; these are per-trade tilts.

Tables (all 1 ES, gross pts and $ @ $50/pt):
  T1 baseline by year
  T2 time of day (hour buckets)
  T3 fresh-extreme vs in-range flips (newsess / beyond_pd)
  T4 SB flush depth (sb_poke_abr terciles, train edges)
  T5 SB tempo heat (tpct2 above/below train median)
  T6 side (long vs short)
  T7 combined skip rule (drop hour-8 AND fresh-session-extreme flips) by year vs baseline

    python tempo/scripts/flip_edge_report.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tempo" / "outputs" / "flip_bucket_trades_2026-09-12.csv"
OUT = ROOT / "tempo" / "outputs"
PT_USD = 50.0


def stats(t, label):
    pnl = t["pnl"]
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"group": label, "n": len(t),
            "win%": round(100 * (pnl > 0).mean(), 1) if len(t) else np.nan,
            "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "tot_pts": round(pnl.sum(), 1),
            "$/trade": round(pnl.mean() * PT_USD, 1) if len(t) else np.nan}


def show(title, rows):
    print(f"\n=== {title} ===")
    print(pd.DataFrame(rows).to_string(index=False))


def main():
    today = dt.date.today().isoformat()
    t = pd.read_csv(SRC)
    tr = t[t["year"] <= 2024]; te = t[t["year"] >= 2025]

    r1 = [stats(g, y) for y, g in t.groupby("year")] + [stats(t, "ALL")]
    show("T1 baseline (current best config, all trades)", r1)

    r2 = [stats(g, f"{h}:xx") for h, g in t.groupby("hour_ct")]
    show("T2 time of day (bar-timestamp hour, full 5.2yr)", r2)
    r2b = [stats(tr[tr["hour_ct"] == 8], "hour 8, 2021-24"),
           stats(te[te["hour_ct"] == 8], "hour 8, 2025-26"),
           stats(tr[tr["hour_ct"] != 8], "rest, 2021-24"),
           stats(te[te["hour_ct"] != 8], "rest, 2025-26")]
    show("T2b first-hour split, both halves", r2b)

    r3 = []
    for col, yes, no in [("newsess", "bar1 = NEW session extreme", "inside session range"),
                         ("beyond_pd", "entry beyond prior-day H/L", "inside prior-day range")]:
        r3 += [stats(tr[tr[col]], f"{yes}, 21-24"), stats(te[te[col]], f"{yes}, 25-26"),
               stats(tr[~tr[col]], f"{no}, 21-24"), stats(te[~te[col]], f"{no}, 25-26")]
    show("T3 fresh-extreme vs in-range flips", r3)

    e = tr["sb_poke_abr"].quantile([1 / 3, 2 / 3]).to_numpy()
    lab = [f"shallow (<{e[0]:.2f} ABR)", "middle", f"deep (>{e[1]:.2f} ABR)"]
    r4 = []
    for name, sub in (("21-24", tr), ("25-26", te)):
        b = pd.cut(sub["sb_poke_abr"], [-np.inf, *e, np.inf], labels=lab)
        r4 += [stats(sub[b == v], f"{v}, {name}") for v in lab]
    show("T4 SB flush depth beyond bar1's extreme (terciles, train edges)", r4)

    med = tr["tpct2"].median()
    r5 = [stats(tr[tr["tpct2"] > med], f"SB tempo > p{med:.1f}, 21-24"),
          stats(te[te["tpct2"] > med], "same, 25-26"),
          stats(tr[tr["tpct2"] <= med], "SB tempo below, 21-24"),
          stats(te[te["tpct2"] <= med], "same, 25-26")]
    show("T5 SB tempo heat (above/below train median of tpct2)", r5)

    r6 = [stats(g, f"{s}, 21-24") for s, g in tr.groupby("side")] + \
         [stats(g, f"{s}, 25-26") for s, g in te.groupby("side")]
    show("T6 side", r6)

    keep = (t["hour_ct"] != 8) & (~t["newsess"])
    r7 = []
    for y, g in t.groupby("year"):
        k = g[keep.loc[g.index]]
        r7.append({"year": y, "base_n": len(g), "base_pts": round(g["pnl"].sum(), 1),
                   "base_$/tr": round(g["pnl"].mean() * PT_USD, 1),
                   "filt_n": len(k), "filt_pts": round(k["pnl"].sum(), 1),
                   "filt_$/tr": round(k["pnl"].mean() * PT_USD, 1) if len(k) else np.nan})
    kall = t[keep]
    r7.append({"year": "ALL", "base_n": len(t), "base_pts": round(t["pnl"].sum(), 1),
               "base_$/tr": round(t["pnl"].mean() * PT_USD, 1),
               "filt_n": len(kall), "filt_pts": round(kall["pnl"].sum(), 1),
               "filt_$/tr": round(kall["pnl"].mean() * PT_USD, 1)})
    show("T7 combined skip rule: drop hour-8 AND new-session-extreme flips", r7)
    dropped = t[~keep]
    print(f"\ndropped trades: n={len(dropped)}  total {dropped['pnl'].sum():+.1f} pts "
          f"({dropped['pnl'].sum() * PT_USD:+,.0f} $)  avg ${dropped['pnl'].mean() * PT_USD:+.1f}/trade")

    for name, rows in [("t1_base", r1), ("t2_tod", r2), ("t3_extreme", r3),
                       ("t4_poke", r4), ("t5_heat", r5), ("t6_side", r6), ("t7_combo", r7)]:
        pd.DataFrame(rows).to_csv(OUT / f"flip_edge_{name}_{today}.csv", index=False)


if __name__ == "__main__":
    main()
