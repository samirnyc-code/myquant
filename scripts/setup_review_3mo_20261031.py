"""Preliminary 3-month setup review (S-2026-10-31) — PRELIMINARY ONLY.

User directive: no rule changes from this. Decisions wait until 3 more months
of data or end of year, whichever is later. This is the first pass of ongoing
monitoring, not a recommendation to act on now.

Scope: the live paper desk's auto-executed 0DTE trades, 2026-08-06 ->
2026-10-30 (2026-08-04/05 excluded as known error days, same as the dashboard).
Looks for any setup whose forward record is consistently bad (not one-day-
driven, not noise), and separately joins the daily GEX briefing
(data/gexlog/gexlog_daily.csv) to check whether regime/signal/day-type
explains the pattern.

Decomposition of the 10 setups (parsed from strategy_id, confirmed against
data/options_sim/gameplan_*.json structure definitions):
  anchor: eod (prior EOD close reference) | open (today's open reference)
  width:  ic (EM-based condor, wider)      | fly (ATM-based, tighter)
  side:   p (put side / bull put)          | c (call side / bear call)
  gx_bps/gx_bcs: separate family, strikes anchored to GexLog's put/call wall.

Run: .venv/Scripts/python.exe scripts/setup_review_3mo_20261031.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "options_log" / "_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)
EXCLUDE_DAYS = {"2026-08-04", "2026-08-05"}

DECOMP = {
    "eodic_p":   dict(anchor="eod",  width="ic",  side="put"),
    "eodic_c":   dict(anchor="eod",  width="ic",  side="call"),
    "eodfly_p":  dict(anchor="eod",  width="fly", side="put"),
    "eodfly_c":  dict(anchor="eod",  width="fly", side="call"),
    "openic_p":  dict(anchor="open", width="ic",  side="put"),
    "openic_c":  dict(anchor="open", width="ic",  side="call"),
    "openfly_p": dict(anchor="open", width="fly", side="put"),
    "openfly_c": dict(anchor="open", width="fly", side="call"),
    "gx_bps":    dict(anchor="gexlog", width="wall", side="put"),
    "gx_bcs":    dict(anchor="gexlog", width="wall", side="call"),
}


def load_trades():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import options_trade_log as tlog
    df = tlog.dedupe_duplicate_fires(tlog.dedupe_mirrors(tlog.load()))
    df = df[df["source"] == "auto_trigger"].copy()
    df["entry_dt"] = pd.to_datetime(df["entry_dt"])
    df["date"] = df["entry_dt"].dt.strftime("%Y-%m-%d")
    df = df[~df["date"].isin(EXCLUDE_DAYS)]
    df["pnl"] = df["pnl"].astype(float)
    df["month"] = df["entry_dt"].dt.strftime("%Y-%m")
    df["anchor"] = df["strategy_id"].map(lambda s: DECOMP.get(s, {}).get("anchor", "?"))
    df["width"] = df["strategy_id"].map(lambda s: DECOMP.get(s, {}).get("width", "?"))
    df["side"] = df["strategy_id"].map(lambda s: DECOMP.get(s, {}).get("side", "?"))
    return df


def load_gexlog():
    g = pd.read_csv(ROOT / "data" / "gexlog" / "gexlog_daily.csv")
    return g[["date", "regime", "signal", "day_type_label", "e_session_type",
              "risk_level", "net_gex", "confidence", "regime_streak", "vix"]]


def structural_breakeven(row):
    """Breakeven win rate implied by the structure's own risk/reward, treating
    outcomes as binary full-win/full-loss (a simplification -- real P&L is a
    distribution, not binary, but this gives a consistent, comparable bar)."""
    mg, ml = row.get("max_gain"), row.get("max_loss")
    if pd.isna(mg) or pd.isna(ml) or (mg + ml) == 0:
        return None
    return ml / (mg + ml)


def per_strategy_table(df):
    rows = []
    for sid, g in df.groupby("strategy_id"):
        n = len(g)
        total = g["pnl"].sum()
        exp = total / n if n else None
        win_rate = (g["pnl"] >= 0).mean() * 100
        w = g.loc[g["pnl"] > 0, "pnl"].sum()
        l = -g.loc[g["pnl"] < 0, "pnl"].sum()
        pf = (w / l) if l else None
        be = g.apply(structural_breakeven, axis=1).dropna()
        be_rate = be.mean() * 100 if len(be) else None
        worst = g.loc[g["pnl"].idxmin()]
        total_ex_worst = total - worst["pnl"]
        rows.append({
            "strategy_id": sid, "anchor": g["anchor"].iloc[0], "width": g["width"].iloc[0],
            "side": g["side"].iloc[0], "n": n, "total_pnl": round(total, 2),
            "expectancy": round(exp, 2), "win_rate_pct": round(win_rate, 1),
            "structural_breakeven_pct": round(be_rate, 1) if be_rate else None,
            "profit_factor": round(pf, 3) if pf else None,
            "worst_day": worst["date"], "worst_day_pnl": round(worst["pnl"], 2),
            "total_pnl_ex_worst_day": round(total_ex_worst, 2),
        })
    return pd.DataFrame(rows).sort_values("expectancy")


def monthly_table(df):
    piv = df.pivot_table(index="strategy_id", columns="month", values="pnl", aggfunc="sum", fill_value=0)
    piv["n_months_negative"] = (piv < 0).sum(axis=1)
    return piv.round(2)


def gex_breakdown(df, gex):
    merged = df.merge(gex, on="date", how="left")
    out = {}
    for dim in ["regime", "signal", "e_session_type", "risk_level"]:
        t = merged.groupby(["strategy_id", dim])["pnl"].agg(["count", "sum", "mean"]).round(2)
        t.columns = ["n", "total_pnl", "expectancy"]
        out[dim] = t.reset_index()
    return out, merged


def comovement(df):
    """For each strategy, its 5 worst days; then measure overlap within the
    put-selling family and the call-selling family separately (fly/ic share
    an anchor+direction thesis, gx_b* is a third, GEX-specific family)."""
    worst5 = {sid: set(g.nsmallest(5, "pnl")["date"]) for sid, g in df.groupby("strategy_id")}
    put_family = ["eodic_p", "openic_p", "eodfly_p", "openfly_p", "gx_bps"]
    call_family = ["eodic_c", "openic_c", "eodfly_c", "openfly_c", "gx_bcs"]

    def overlap_report(fam):
        from collections import Counter
        c = Counter()
        for sid in fam:
            if sid in worst5:
                c.update(worst5[sid])
        return sorted(c.items(), key=lambda x: -x[1])

    return {"put_side_worst5_overlap": overlap_report(put_family),
            "call_side_worst5_overlap": overlap_report(call_family)}


def pair_comparison(df):
    pairs = [("eodic_p", "eodic_c"), ("eodfly_p", "eodfly_c"),
             ("openic_p", "openic_c"), ("openfly_p", "openfly_c"),
             ("gx_bps", "gx_bcs")]
    rows = []
    for a, b in pairs:
        ga, gb = df[df.strategy_id == a], df[df.strategy_id == b]
        rows.append({
            "pair": f"{a} vs {b}",
            f"{a}_total": round(ga["pnl"].sum(), 2), f"{a}_n": len(ga),
            f"{b}_total": round(gb["pnl"].sum(), 2), f"{b}_n": len(gb),
            "gap": round(ga["pnl"].sum() - gb["pnl"].sum(), 2),
        })
    return pd.DataFrame(rows)


def anchor_width_rollup(df):
    return df.groupby(["anchor", "width"])["pnl"].agg(["count", "sum", "mean"]).round(2).reset_index()


def main():
    df = load_trades()
    gex = load_gexlog()

    strat = per_strategy_table(df)
    monthly = monthly_table(df)
    gex_cuts, merged = gex_breakdown(df, gex)
    co = comovement(df)
    pairs = pair_comparison(df)
    rollup = anchor_width_rollup(df)

    df.to_csv(OUT_DIR / "setup_review_3mo_trades_20261031.csv", index=False)
    merged.to_csv(OUT_DIR / "setup_review_3mo_trades_gexjoined_20261031.csv", index=False)
    strat.to_csv(OUT_DIR / "setup_review_3mo_per_strategy_20261031.csv", index=False)
    monthly.to_csv(OUT_DIR / "setup_review_3mo_monthly_20261031.csv")
    pairs.to_csv(OUT_DIR / "setup_review_3mo_pairs_20261031.csv", index=False)
    rollup.to_csv(OUT_DIR / "setup_review_3mo_anchor_width_20261031.csv", index=False)
    for dim, t in gex_cuts.items():
        t.to_csv(OUT_DIR / f"setup_review_3mo_gex_{dim}_20261031.csv", index=False)

    print(f"window: {df['date'].min()} -> {df['date'].max()}, {df['date'].nunique()} days, {len(df)} trades\n")
    print("=== PER-STRATEGY (sorted worst expectancy first) ===")
    print(strat.to_string(index=False))
    print("\n=== MONTHLY P&L BY STRATEGY ===")
    print(monthly.to_string())
    print("\n=== ANCHOR x WIDTH ROLLUP ===")
    print(rollup.to_string(index=False))
    print("\n=== SYMMETRIC PAIR (put vs call side) ===")
    print(pairs.to_string(index=False))
    print("\n=== WORST-DAY CO-MOVEMENT ===")
    print("put-side family worst-5-day overlap (date: how many strategies had it in their worst 5):")
    for d, c in co["put_side_worst5_overlap"][:8]:
        print(f"  {d}: {c}")
    print("call-side family worst-5-day overlap:")
    for d, c in co["call_side_worst5_overlap"][:8]:
        print(f"  {d}: {c}")
    print("\n=== GEX CONTEXT CUTS ===")
    for dim, t in gex_cuts.items():
        print(f"--- by {dim} ---")
        print(t.to_string(index=False))
        print()


if __name__ == "__main__":
    main()
