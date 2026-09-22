"""Join the GexLog morning-brief fields we do NOT trade on to the v2 backtest's
per-stream day P&L, and ask: would any ignored field have mattered?

Why this design:
- The extraction the question implies ("reread every report") is ALREADY done:
  data/gexlog/gexlog_daily.csv flattens every archived morning brief (+ the
  evening self-grade) 2026-04-06..present. This script only JOINS.
- No sim rerun needed: data/options_sim/backtest_full/rows_v2.csv already holds
  per-day per-stream P&L (desk-faithful v2 engine) covering the same dates.
- ADVISORY-ONLY by hard rule (premium desk never blocks trades): output is a
  fact table "P&L by bucket", not a gate. n≈100 days -> single-field splits
  only, n shown everywhere, no field combinations (overfitting guard).
- Morning-knowable fields are reported separately from hindsight (evening
  e_*) fields, which are sanity checks only.

Outputs (dated):
  data/options_sim/gexlog_field_join_<YYYYMMDD>.csv       joined day table
  data/options_sim/gexlog_field_join_stats_<YYYYMMDD>.txt bucket tables
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"c:\Users\Admin\myquant")
OUT = ROOT / "data" / "options_sim"
STAMP = dt.date.today().strftime("%Y%m%d")

FAMS = ["eod_ic", "eod_fly", "open_ic", "open_fly"]


def fam(strat: str) -> str:
    return {"eodic": "eod_ic", "eodfly": "eod_fly",
            "openic": "open_ic", "openfly": "open_fly"}[strat.split("_")[0]]


def load_bt() -> pd.DataFrame:
    """rows_v2 -> one row per day with per-family and total P&L.

    Policy selection: eod streams live under policy 'eod' (premarket-fixed,
    WAIT-independent); open streams under 'nowait'/'calwait' — we take the
    NOWAIT baseline (calendar-WAIT is a separate S115 thread).
    """
    r = pd.read_csv(OUT / "backtest_full" / "rows_v2.csv")
    r = r[r["date"] >= "2026-04-06"].copy()
    r = r[(r["policy"] == "eod") | (r["policy"] == "nowait")]
    r["pnl"] = pd.to_numeric(r["pnl"], errors="coerce")
    r["fam"] = [fam(s) for s in r["strat"]]
    day = r.pivot_table(index="date", columns="fam", values="pnl", aggfunc="sum")
    day = day.reindex(columns=FAMS)
    day["total"] = day.sum(axis=1)
    return day.reset_index()


def _norm_sig(s):
    s = str(s or "").upper()
    return ("GO" if s.startswith("GO") else "CAUTION" if s.startswith("CAUT")
            else "WAIT" if s.startswith("WAIT") else "?")


def _norm_ft(s):
    s = str(s or "").lower()
    if "volatil" in s:
        return "HIVOL"
    if "trend" in s:
        return "TREND"
    if "range" in s:
        return "RANGE"
    if "chop" in s or "mixed" in s or "balance" in s:
        return "CHOP"
    return "?"


def load_gex() -> pd.DataFrame:
    g = pd.read_csv(ROOT / "data" / "gexlog" / "gexlog_daily.csv")
    for c in ["confidence", "current", "es", "expectedMove", "net_gex", "vix",
              "putWall", "callWall", "emLower", "emUpper", "regime_streak",
              "e_spx_change", "e_vix_change"]:
        g[c] = pd.to_numeric(g[c], errors="coerce")
    g["signal_b"] = g["signal"].map(_norm_sig)
    g["ftype_b"] = g["forecast_type"].map(_norm_ft)
    g["regime_b"] = g["regime"].astype(str).str[:3]           # POS / NEG
    g["flip_present"] = np.where(pd.to_numeric(g["gex_flip"], errors="coerce").notna(),
                                 "flip-in-chain", "no-flip")
    g["netgex_sign"] = np.where(g["net_gex"] >= 0, "netgex+", "netgex-")
    g["netgex_mag"] = pd.qcut(g["net_gex"].abs(), 3, labels=["|gex| lo", "|gex| mid", "|gex| hi"])
    g["streak_b"] = pd.cut(g["regime_streak"], [0, 1, 3, 99],
                           labels=["day1", "day2-3", "day4+"])
    g["conf_b"] = pd.cut(g["confidence"], [0, 59, 69, 100],
                         labels=["conf<60", "conf60-69", "conf70+"])
    g["em_pct"] = g["expectedMove"] / g["current"] * 100
    g["empct_b"] = pd.qcut(g["em_pct"], 3, labels=["EM% lo", "EM% mid", "EM% hi"])
    g["gap_pct"] = (g["es"] - g["current"]) / g["current"] * 100
    g["gap_b"] = pd.cut(g["gap_pct"].abs(), [-0.001, 0.2, 0.5, 99],
                        labels=["|gap|<.2", "|gap|.2-.5", "|gap|>.5"])
    # walls tighter than the EM band = gexlog seeing pinning risk inside range
    g["walls_in_em"] = np.where(
        (g["putWall"] >= g["emLower"]) & (g["callWall"] <= g["emUpper"]),
        "walls-inside-EM", "walls-at/past-EM")
    # hindsight (evening) — sanity only, NOT morning-knowable
    g["h_accurate"] = g["e_forecast_accurate"].astype(str)
    g["h_session"] = g["e_session_type"].astype(str).str.split().str[0]
    return g


MORNING_FIELDS = [
    ("signal_b", "guidance signal (GO/CAUTION/WAIT)"),
    ("ftype_b", "forecast day-type"),
    ("regime_b", "gamma regime (POS/NEG)"),
    ("flip_present", "GEX flip level in chain?"),
    ("netgex_sign", "net GEX sign"),
    ("netgex_mag", "|net GEX| tercile"),
    ("streak_b", "regime streak age"),
    ("conf_b", "forecast confidence"),
    ("risk_level", "risk level"),
    ("empct_b", "EM width %% of spot tercile"),
    ("gap_b", "overnight gap magnitude"),
    ("walls_in_em", "walls inside EM band?"),
]
HINDSIGHT_FIELDS = [
    ("h_accurate", "evening self-grade: forecast accurate (HINDSIGHT)"),
    ("h_session", "realized session type (HINDSIGHT)"),
]


def bucket_table(df: pd.DataFrame, col: str) -> pd.DataFrame:
    rows = []
    for key, grp in df.groupby(col, observed=True, dropna=False):
        d = {"bucket": str(key), "n": len(grp),
             "total": grp["total"].sum(), "avg/day": grp["total"].mean(),
             "win%": 100 * (grp["total"] > 0).mean(),
             "worst": grp["total"].min()}
        for f in FAMS:
            d[f] = grp[f].sum()
        rows.append(d)
    t = pd.DataFrame(rows).sort_values("avg/day", ascending=False)
    return t


def main():
    bt = load_bt()
    gx = load_gex()
    j = bt.merge(gx, on="date", how="inner")
    n_bt, n_gx = len(bt), len(gx)

    L = [f"GEXLOG IGNORED-FIELDS JOIN — v2 backtest day P&L (eod policy + nowait opens) "
         f"x morning brief fields",
         f"bt days {n_bt} ({bt['date'].min()}..{bt['date'].max()}) · "
         f"gexlog days {n_gx} ({gx['date'].min()}..{gx['date'].max()}) · joined {len(j)}",
         f"ADVISORY-ONLY fact table. Single-field splits, no combos. n<10 buckets = noise.",
         ""]
    base = (f"BASELINE all joined days: total {j['total'].sum():+,.0f}  "
            f"avg/day {j['total'].mean():+,.0f}  win% {100*(j['total']>0).mean():.0f}  "
            f"per family: " + "  ".join(f"{f} {j[f].sum():+,.0f}" for f in FAMS))
    L += [base, ""]

    for fields, hdr in [(MORNING_FIELDS, "=== MORNING-KNOWABLE FIELDS ==="),
                        (HINDSIGHT_FIELDS, "=== HINDSIGHT (sanity only — NOT tradeable) ===")]:
        L.append(hdr)
        for col, label in fields:
            t = bucket_table(j, col)
            L.append(f"\n--- {label} [{col}] ---")
            L.append(t.to_string(index=False,
                                 float_format=lambda x: f"{x:+,.0f}"))
        L.append("")

    # live-book overlay (tiny n, Aug 4 ->) on the same buckets, total P&L only
    ds = pd.read_csv(OUT / "daily_summary.csv")
    ds["pnl_total"] = pd.to_numeric(ds["pnl_total"], errors="coerce")
    lv = ds[["date", "pnl_total"]].merge(gx, on="date", how="inner")
    L.append(f"=== LIVE BOOK overlay (n={len(lv)} days, {lv['date'].min()}..{lv['date'].max()} — "
             f"tiny sample, direction check only) ===")
    for col in ["signal_b", "ftype_b", "regime_b", "flip_present"]:
        t = (lv.groupby(col, observed=True)["pnl_total"]
               .agg(n="count", total="sum", avg="mean").reset_index()
               .sort_values("avg", ascending=False))
        L.append(f"\n--- {col} ---")
        L.append(t.to_string(index=False, float_format=lambda x: f"{x:+,.0f}"))

    txt = "\n".join(L)
    print(txt)
    (OUT / f"gexlog_field_join_stats_{STAMP}.txt").write_text(txt, encoding="utf-8")
    j.to_csv(OUT / f"gexlog_field_join_{STAMP}.csv", index=False)
    print(f"\nsaved: gexlog_field_join_{STAMP}.csv + gexlog_field_join_stats_{STAMP}.txt")


if __name__ == "__main__":
    main()
