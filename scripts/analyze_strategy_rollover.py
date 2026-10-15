"""analyze_strategy_rollover.py -- full-period (2026-08-04 -> 2026-10-15) SPX 0DTE
desk review: which strategies made/lost money, are the GEX-wall trades (gx_bcs/gx_bps)
any good, is performance rolling over over time, and what simple filter rules would
have improved realized P&L. Realized (closed) trades only.

Read-only diagnostic. Does NOT change any live trading config -- the desk stays
advisory-only (no auto-skip/gate) per standing instruction; this is a "what if"
retro, not a live filter.

Saves dated CSVs to data/options_sim/. Run:
  .venv/Scripts/python.exe scripts/analyze_strategy_rollover.py
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog
import analyze_retro_filters as arf  # reuse load_gameplans() / leg_info()

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "options_sim"
TODAY = dt.date.today().strftime("%Y%m%d")


def families(df):
    s = df.strategy_id.astype(str)
    df = df.copy()
    df["timing"] = np.where(s.str.startswith("eod"), "EOD",
                    np.where(s.str.startswith("open"), "Open",
                    np.where(s.str.startswith("gx"), "GexWall", "other")))
    df["structure"] = np.where(s.str.contains("fly"), "iron-fly",
                       np.where(s.str.contains("ic"), "iron-condor",
                       np.where(s.str.contains("bps|bcs"), "vertical-wall", "other")))
    df["side"] = np.where(s.str.endswith("_c") | s.str.contains("bcs"), "call",
                  np.where(s.str.endswith("_p") | s.str.contains("bps"), "put", "both"))
    return df


def stats(g):
    p = g.pnl
    pf = round(p[p > 0].sum() / -p[p < 0].sum(), 2) if (p < 0).any() and (p > 0).any() else np.nan
    return pd.Series({
        "n": len(g), "win%": round(100 * (p > 0).mean()),
        "total": round(p.sum()), "avg": round(p.mean(), 1), "PF": pf,
        "avg_win": round(p[p > 0].mean(), 1) if (p > 0).any() else 0,
        "avg_loss": round(p[p < 0].mean(), 1) if (p < 0).any() else 0,
        "worst": round(p.min()), "best": round(p.max()),
    })


def show(df, by, title):
    if not len(df):
        print(f"\n=== {title} ===\n(no rows)")
        return pd.DataFrame()
    t = df.groupby(by, observed=True).apply(stats, include_groups=False).sort_values("total", ascending=False)
    print(f"\n=== {title} ===")
    print(t.to_string())
    return t


def load_all():
    d = tlog.load()
    d["pnl"] = pd.to_numeric(d["pnl"], errors="coerce")
    d["ed"] = pd.to_datetime(d["exit_dt"], errors="coerce")
    d = d[d.ed.notna() & d.pnl.notna() & (d.strategy_id != "incident_orphan")].copy()
    d["day"] = d.ed.dt.strftime("%Y-%m-%d")
    d["month"] = d.ed.dt.strftime("%Y-%m")
    d["week"] = d.ed.dt.strftime("%G-W%V")
    return families(d)


def main():
    d = load_all()
    lo, hi = d.ed.min().date(), d.ed.max().date()
    print(f"PERIOD: {lo} -> {hi}   ({d.day.nunique()} trading days, {len(d)} closed trades)")
    print(f"REALIZED TOTAL: ${d.pnl.sum():,.0f}   overall win rate {100*(d.pnl>0).mean():.0f}%\n")

    per_strat = show(d, "strategy_id", "BY STRATEGY (full period)")
    show(d, "structure", "BY STRUCTURE")
    show(d, "timing", "BY TIMING (EOD vs Open vs GexWall)")
    show(d, "side", "BY SIDE (call vs put)")
    show(d, "grade", "BY GRADE")

    # ---- monthly trend per strategy: is it really rolling over, or specific books? ----
    print("\n=== MONTHLY P&L BY STRATEGY (rollover check) ===")
    piv = d.pivot_table(index="strategy_id", columns="month", values="pnl", aggfunc="sum").round(0)
    piv["TOTAL"] = piv.sum(axis=1)
    piv = piv.sort_values("TOTAL", ascending=False)
    print(piv.to_string())

    print("\n=== MONTHLY P&L BY FAMILY (timing) ===")
    pivf = d.pivot_table(index="timing", columns="month", values="pnl", aggfunc="sum").round(0)
    pivf["TOTAL"] = pivf.sum(axis=1)
    print(pivf.to_string())

    # weekly cumulative equity (overall + GexWall vs the rest) to show the shape of the rollover
    print("\n=== WEEKLY P&L: overall vs GexWall vs iron-fly/condor book ===")
    wk = d.groupby(["week"]).pnl.sum().round(0)
    wk_gx = d[d.timing == "GexWall"].groupby("week").pnl.sum().round(0)
    wk_rest = d[d.timing != "GexWall"].groupby("week").pnl.sum().round(0)
    wkt = pd.DataFrame({"ALL": wk, "GexWall": wk_gx, "fly/condor book": wk_rest}).fillna(0)
    wkt["ALL_cum"] = wkt["ALL"].cumsum()
    wkt["GexWall_cum"] = wkt["GexWall"].cumsum()
    wkt["rest_cum"] = wkt["fly/condor book"].cumsum()
    print(wkt.to_string())

    # ---- GEX-wall trades deep dive ----
    gx = d[d.timing == "GexWall"]
    rest = d[d.timing != "GexWall"]
    print(f"\n=== GEX-WALL TRADES (gx_bcs / gx_bps) ===")
    print(f"n={len(gx)}  total ${gx.pnl.sum():,.0f}  win% {100*(gx.pnl>0).mean():.0f}%  "
          f"avg ${gx.pnl.mean():,.0f}  vs rest of book: n={len(rest)} total ${rest.pnl.sum():,.0f} "
          f"win% {100*(rest.pnl>0).mean():.0f}% avg ${rest.pnl.mean():,.0f}")
    show(gx, "strategy_id", "GEX-wall strategies individually")
    show(gx, "month", "GEX-wall by month")

    # ---- join gameplan (day_type / gamma regime) for regime-based filters ----
    gp = arf.load_gameplans()
    d["day_type"] = d.day.map(lambda x: gp.get(x, {}).get("day_type"))
    d["gamma"] = d.day.map(lambda x: gp.get(x, {}).get("gamma"))
    d["event_verdict"] = d.day.map(lambda x: gp.get(x, {}).get("event_verdict"))
    show(d[d.day_type.notna()], "day_type", "BY DAY TYPE (gameplan-joined)")
    show(d[d.gamma.notna()], "gamma", "BY GAMMA REGIME (gameplan-joined)")

    # ---- SIMPLE FILTER-RULE BACKTESTS (full period, read-only what-if) ----
    base = d.pnl.sum()

    def impact(mask, label):
        kept = d[~mask]
        return {"rule": label, "n_skipped": int(mask.sum()),
                "skipped_pnl": round(d[mask].pnl.sum()),
                "kept_pnl": round(kept.pnl.sum()),
                "delta_vs_base": round(kept.pnl.sum() - base)}

    worst3 = per_strat.sort_values("total").head(3).index.tolist()
    rules = [
        impact(d.strategy_id == per_strat.sort_values("total").index[0], f"drop worst single strategy ({per_strat.sort_values('total').index[0]})"),
        impact(d.strategy_id.isin(worst3), f"drop worst 3 strategies ({', '.join(worst3)})"),
        impact(d.timing == "GexWall", "drop ALL GexWall (gx_bcs+gx_bps)"),
        impact(d.timing == "EOD", "drop the EOD book"),
        impact(d.timing == "Open", "drop the Open book"),
        impact(d.side == "call", "drop the CALL side"),
        impact(d.side == "put", "drop the PUT side"),
        impact(d.grade == "D", "drop grade D"),
        impact(d.grade.isin(["C", "D"]), "drop grades C+D (keep A/B only)"),
        impact(pd.to_numeric(d["pop"], errors="coerce") < 0.5, "drop POP<0.50"),
        impact(pd.to_numeric(d["pop"], errors="coerce") < 0.6, "drop POP<0.60"),
        impact(d.day_type == "TREND", "drop TREND days (gameplan)"),
        impact(d.gamma == "NEGATIVE", "drop NEGATIVE-gamma days (gameplan)"),
        impact(d.dow.isin(["Mon"]), "drop Mondays"),
        impact(d.dow.isin(["Fri"]), "drop Fridays"),
        impact(d.month == "2026-10", "drop October entirely (hindsight, NOT a real rule -- shown for scale only)"),
    ]
    fdf = pd.DataFrame(rules).sort_values("delta_vs_base", ascending=False)
    print(f"\n=== FILTER-RULE BACKTESTS (base realized ${base:,.0f}, {len(d)} trades) ===")
    print(fdf.to_string(index=False))

    # stack the best 2 REAL (non-hindsight) rules found, to see if they compound
    top2 = fdf[~fdf.rule.str.contains("hindsight")].head(2)
    print(f"\ntop 2 non-hindsight rules by itself: see table above.")

    out1 = OUT / f"rollover_by_strategy_{TODAY}.csv"
    out2 = OUT / f"rollover_filters_{TODAY}.csv"
    out3 = OUT / f"rollover_monthly_{TODAY}.csv"
    per_strat.to_csv(out1)
    fdf.to_csv(out2, index=False)
    piv.to_csv(out3)
    print(f"\nwrote {out1}\nwrote {out2}\nwrote {out3}")


if __name__ == "__main__":
    main()
