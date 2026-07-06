"""
or12_baserate_tables.py — the FREE 80% of the OR12 signal as a reference card:
conditional base-rate tables over open-location bucket x IB-width tier
(+ formation-order direction check), with an era-stability audit.

All conditioning features are causal at 09:30 CT (bucket, gap) or 10:30 CT
(IB width vs ADR14, formation order). Outcomes are end-of-day. These are
simple counts — no kNN, no fitting — so the only overfit risk is cell size;
n and a 2021-23 vs 2024-26 era split are printed for every cell.

Outputs: stdout tables + docs/living/or12_baserate_tables_<date>.csv
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from or12_pattern_groups import build_features, BARS_PQ  # noqa: E402
from or12_outcome_agreement import day_outcome            # noqa: E402

OUT_CSV = ROOT / "docs" / "living" / f"or12_baserate_tables_{datetime.now():%Y%m%d}.csv"
ERA_SPLIT = pd.Timestamp("2024-01-01").date()


def main() -> None:
    bars = pd.read_parquet(BARS_PQ).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    outs = {d: o for d, g in bars.groupby(bars["DateTime"].dt.date)
            if (o := day_outcome(g))}
    out_df = pd.DataFrame.from_dict(outs, orient="index")

    dr = bars.groupby(bars["DateTime"].dt.date).agg(H=("High", "max"),
                                                    L=("Low", "min"))
    adr20 = (dr["H"] - dr["L"]).rolling(20, min_periods=10).mean().shift(1)

    df, _, _ = build_features()
    df = df[df.index.isin(out_df.index)].sort_index()
    out_df = out_df.loc[df.index]
    adr20 = adr20.reindex(df.index)

    t = pd.DataFrame(index=df.index)
    t["bucket"] = df["bucket"]
    # IB width tiers — full-sample terciles of IB range / ADR14 (report cuts)
    q1, q2 = df["ib_atr"].quantile([1/3, 2/3])
    t["ib_tier"] = pd.cut(df["ib_atr"], [-np.inf, q1, q2, np.inf],
                          labels=["narrow", "mid", "wide"])
    t["hi_first"] = df["ib_high_first"] > 0
    t["era"] = np.where(pd.Series(df.index).values < ERA_SPLIT,
                        "2021-23", "2024-26")

    is_trend = ((out_df["day_rng"] > 1.1 * adr20)
                & ((out_df["close_pos"] >= 0.75)
                   | (out_df["close_pos"] <= 0.25)))
    t["trend"] = is_trend.fillna(False).to_numpy()
    t["cls"] = out_df["class3"].to_numpy()
    t["ext_any"] = (np.maximum(out_df["ext_up"], out_df["ext_dn"]) > 0.5).to_numpy()
    t["both_brk"] = ((out_df["ext_up"] > 0) & (out_df["ext_dn"] > 0)).to_numpy()
    t["first_break"] = out_df["first_break"].to_numpy()
    t = t[adr20.notna().to_numpy()]

    print(f"n = {len(t)} days ({t.index.min()} - {t.index.max()})")
    print(f"IB width tier cuts (IBrange/ADR14): narrow < {q1:.3f} <= mid < "
          f"{q2:.3f} <= wide")
    print(f"Unconditional: trend {t.trend.mean():.0%}, ext>0.5IB "
          f"{t.ext_any.mean():.0%}, both-sides broken {t.both_brk.mean():.0%}\n")

    def cell_stats(g: pd.DataFrame) -> pd.Series:
        e1 = g[g.era == "2021-23"]; e2 = g[g.era == "2024-26"]
        return pd.Series({
            "n": len(g),
            "P_trend": g.trend.mean(),
            "P_ext": g.ext_any.mean(),
            "P_both": g.both_brk.mean(),
            "P_close_above": (g.cls == "above").mean(),
            "P_close_inside": (g.cls == "inside").mean(),
            "P_close_below": (g.cls == "below").mean(),
            "trend_2123": e1.trend.mean() if len(e1) > 20 else np.nan,
            "trend_2426": e2.trend.mean() if len(e2) > 20 else np.nan,
        })

    main_tbl = (t.groupby(["bucket", "ib_tier"], observed=True)
                .apply(cell_stats, include_groups=False))
    pct_cols = [c for c in main_tbl.columns if c != "n"]
    show = main_tbl.copy()
    show[pct_cols] = (show[pct_cols] * 100).round(1)
    show["n"] = show["n"].astype(int)
    print("== MAIN TABLE: bucket x IB-width tier ==")
    print(show.to_string(), "\n")

    # formation-order direction check (the documented ~2:1 claim)
    print("== FORMATION ORDER -> first IB break side (documented ES skew: "
          "high-first -> break DOWN ~45/24) ==")
    fo = (t.groupby("hi_first")["first_break"]
          .value_counts(normalize=True).unstack().fillna(0) * 100).round(1)
    fo["n"] = t.groupby("hi_first").size()
    print(fo.to_string(), "\n")

    # same check but conditional on bucket (does context change the skew?)
    fo_b = (t.groupby(["bucket", "hi_first"])["first_break"]
            .value_counts(normalize=True).unstack().fillna(0) * 100).round(1)
    fo_b["n"] = t.groupby(["bucket", "hi_first"]).size()
    print("== formation order x bucket ==")
    print(fo_b.to_string())

    main_tbl.to_csv(OUT_CSV)
    print(f"\nwritten: {OUT_CSV}")


if __name__ == "__main__":
    main()
