"""Recompute live desk P&L under the GEX brief's own avoidance guidance, and
test whether the overnight-gap-vs-expected-move relationship is significant.

Part 1 — "what if we'd followed the brief's suggestion to sit out":
GexLog's own methodology page states the Go/Caution/Wait `signal` field
"reflect[s] regime context for premium-selling strategies" specifically — i.e.
it IS the brief's explicit suggestion for when to run (or not run) exactly the
kind of credit-selling structures our whole menu is built from (confirmed: all
10 of our setups book as 'vertical' credit spreads, structure field). This
recomputes our actual P&L under two simulated sit-out rules:
  (a) skip every trade on a "Wait" day
  (b) skip every trade on a "Wait" OR "Caution" day
against the real result, with no sit-out at all.

Sanity check included: the free-text narrative's "Income structures... are
misaligned" sentence does NOT reduce cleanly to the signal field (it appears
on 6 of 15 "Go" days too) -- the structured `signal` field is the cleaner,
already-intended proxy, not something inferred from prose.

Part 2 — overnight gap (open vs. prior close) vs. the expected-move band:
pulls today's actual SPX open from each evening report (not in the existing
flattened CSV) and the prior-close-anchored EM band from the same day's
morning report, then checks: (i) does a bigger gap-as-fraction-of-EM predict
an EM breach later that day, (ii) does it predict OUR day-level P&L, split by
anchor (eod vs open) -- the hypothesis being EOD-anchored strikes are set
BEFORE the gap is known (fully exposed to it) while Open-anchored strikes are
set AFTER the gap (the gap is priced in by construction).

Run: .venv/Scripts/python.exe scripts/gexlog_guidance_recalc_20261031.py
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "gexlog" / "raw"
OUT_DIR = ROOT / "data" / "options_log" / "_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)
EXCLUDE_DAYS = {"2026-08-04", "2026-08-05"}
MISALIGNED_RE = re.compile(r"misaligned|Income structures", re.I)


def g(d, *path, default=None):
    for k in path:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return default
    return d if d is not None else default


def load_brief_days():
    rows = {}
    for f in sorted(glob.glob(str(RAW / "*_morning.json"))):
        date = Path(f).stem[:10]
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        rows[date] = {
            "date": date,
            "signal": g(d, "guidance", "signal"),
            "guidance_message": g(d, "guidance", "message"),
            "regime": g(d, "forecast", "factors", "gamma", "value"),
            "forecast_type": g(d, "forecast", "type"),
            "prior_close": g(d, "levels", "current"),
            "expectedMove": g(d, "levels", "expectedMove"),
            "emLower": g(d, "levels", "emLower"),
            "emUpper": g(d, "levels", "emUpper"),
            "narrative_misaligned": bool(MISALIGNED_RE.search(g(d, "notes", default="") or "")),
        }
    for f in sorted(glob.glob(str(RAW / "*_evening.json"))):
        date = Path(f).stem[:10]
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        if date not in rows:
            continue
        rows[date].update({
            "spx_open": g(d, "market", "spx", "open"),
            "spx_close": g(d, "market", "spx", "price"),
            "spx_high": g(d, "market", "spx", "high"),
            "spx_low": g(d, "market", "spx", "low"),
            "e_session_type": g(d, "session_analysis", "session_type"),
            "e_forecast_accurate": g(d, "session_analysis", "forecast_accurate"),
            "e_em_hit": g(d, "session_analysis", "expected_move_hit"),
        })
    return pd.DataFrame(rows.values()).sort_values("date")


def load_trades():
    sys.path.insert(0, str(ROOT / "scripts"))
    import options_trade_log as tlog
    df = tlog.dedupe_duplicate_fires(tlog.dedupe_mirrors(tlog.load()))
    df = df[df["source"] == "auto_trigger"].copy()
    df["entry_dt"] = pd.to_datetime(df["entry_dt"])
    df["date"] = df["entry_dt"].dt.strftime("%Y-%m-%d")
    df = df[~df["date"].isin(EXCLUDE_DAYS)]
    df["pnl"] = df["pnl"].astype(float)
    DECOMP = {
        "eodic_p": ("eod", "ic", "put"), "eodic_c": ("eod", "ic", "call"),
        "eodfly_p": ("eod", "fly", "put"), "eodfly_c": ("eod", "fly", "call"),
        "openic_p": ("open", "ic", "put"), "openic_c": ("open", "ic", "call"),
        "openfly_p": ("open", "fly", "put"), "openfly_c": ("open", "fly", "call"),
        "gx_bps": ("gexlog", "wall", "put"), "gx_bcs": ("gexlog", "wall", "call"),
    }
    df["anchor"] = df["strategy_id"].map(lambda s: DECOMP.get(s, ("?", "?", "?"))[0])
    df["width"] = df["strategy_id"].map(lambda s: DECOMP.get(s, ("?", "?", "?"))[1])
    df["side"] = df["strategy_id"].map(lambda s: DECOMP.get(s, ("?", "?", "?"))[2])
    return df


def part1_signal_recalc(trades, brief):
    m = trades.merge(brief[["date", "signal"]], on="date", how="left")
    actual_total = m["pnl"].sum()
    skip_wait = m[m["signal"] != "Wait"]["pnl"].sum()
    skip_wait_caution = m[~m["signal"].isin(["Wait", "Caution"])]["pnl"].sum()
    n_wait_days = brief[brief.date.isin(trades.date.unique())]["signal"].eq("Wait").sum()
    n_caution_days = brief[brief.date.isin(trades.date.unique())]["signal"].eq("Caution").sum()
    n_go_days = brief[brief.date.isin(trades.date.unique())]["signal"].eq("Go").sum()

    by_anchor = []
    for anchor, g_ in m.groupby("anchor"):
        by_anchor.append({
            "anchor": anchor, "actual": round(g_["pnl"].sum(), 2),
            "skip_wait": round(g_[g_["signal"] != "Wait"]["pnl"].sum(), 2),
            "skip_wait_caution": round(g_[~g_["signal"].isin(["Wait", "Caution"])]["pnl"].sum(), 2),
        })
    by_strategy = []
    for sid, g_ in m.groupby("strategy_id"):
        by_strategy.append({
            "strategy_id": sid, "actual": round(g_["pnl"].sum(), 2),
            "skip_wait": round(g_[g_["signal"] != "Wait"]["pnl"].sum(), 2),
            "skip_wait_caution": round(g_[~g_["signal"].isin(["Wait", "Caution"])]["pnl"].sum(), 2),
            "n": len(g_),
        })
    return {
        "actual_total": round(actual_total, 2),
        "skip_wait_total": round(skip_wait, 2),
        "skip_wait_caution_total": round(skip_wait_caution, 2),
        "n_wait_days": int(n_wait_days), "n_caution_days": int(n_caution_days), "n_go_days": int(n_go_days),
        "by_anchor": pd.DataFrame(by_anchor),
        "by_strategy": pd.DataFrame(by_strategy).sort_values("actual"),
    }


def part2_gap_em(trades, brief):
    b = brief.copy()
    b["gap"] = b["spx_open"] - b["prior_close"]
    b["gap_frac_em"] = (b["gap"].abs() / b["expectedMove"]).round(3)
    b = b.dropna(subset=["gap_frac_em"])

    # bucket gap_frac_em into quartile-ish bins
    b["gap_bucket"] = pd.cut(b["gap_frac_em"], bins=[0, 0.15, 0.3, 0.5, 10],
                              labels=["<0.15 EM", "0.15-0.3 EM", "0.3-0.5 EM", ">0.5 EM"])
    em_hit_by_bucket = b.groupby("gap_bucket")["e_em_hit"].agg(["count", "mean"])

    day_pnl = trades.groupby(["date", "anchor"])["pnl"].sum().reset_index()
    day_pnl_wide = day_pnl.pivot(index="date", columns="anchor", values="pnl")
    merged = b.merge(day_pnl_wide, on="date", how="inner")

    corr = {}
    for anchor_col in ["eod", "open", "gexlog"]:
        if anchor_col in merged.columns:
            sub = merged.dropna(subset=[anchor_col, "gap_frac_em"])
            corr[anchor_col] = sub["gap_frac_em"].corr(sub[anchor_col]) if len(sub) > 3 else None

    pnl_by_bucket = merged.groupby("gap_bucket")[[c for c in ["eod", "open", "gexlog"] if c in merged.columns]].mean().round(2)
    n_by_bucket = merged.groupby("gap_bucket")[[c for c in ["eod", "open", "gexlog"] if c in merged.columns]].count()

    return {
        "em_hit_by_gap_bucket": em_hit_by_bucket, "corr_gap_frac_vs_anchor_pnl": corr,
        "mean_daily_pnl_by_bucket_and_anchor": pnl_by_bucket, "n_by_bucket": n_by_bucket,
        "merged": merged,
    }


def main():
    brief = load_brief_days()
    trades = load_trades()
    brief.to_csv(OUT_DIR / "gexlog_brief_days_full_20261031.csv", index=False)

    p1 = part1_signal_recalc(trades, brief)
    print("=== PART 1: P&L under the brief's own Go/Caution/Wait guidance ===")
    print(f"days in our window tagged: Go={p1['n_go_days']}  Caution={p1['n_caution_days']}  Wait={p1['n_wait_days']}")
    print(f"ACTUAL total P&L (no avoidance):            {p1['actual_total']:>10.2f}")
    print(f"IF we'd skipped all 'Wait' days:             {p1['skip_wait_total']:>10.2f}  (delta {p1['skip_wait_total']-p1['actual_total']:+.2f})")
    print(f"IF we'd skipped 'Wait' + 'Caution' days:     {p1['skip_wait_caution_total']:>10.2f}  (delta {p1['skip_wait_caution_total']-p1['actual_total']:+.2f})")
    print("\nby anchor (eod/open/gexlog):")
    print(p1["by_anchor"].to_string(index=False))
    print("\nby strategy:")
    print(p1["by_strategy"].to_string(index=False))

    p2 = part2_gap_em(trades, brief)
    print("\n\n=== PART 2: overnight gap (open vs prior close) as a fraction of the EM band ===")
    print("EM-hit rate by gap-size bucket (does a bigger gap predict breaching the EM later?):")
    print(p2["em_hit_by_gap_bucket"].to_string())
    print("\ncorrelation: |gap|/EM vs same-day P&L, by anchor family:")
    for k, v in p2["corr_gap_frac_vs_anchor_pnl"].items():
        print(f"  {k}: {v}")
    print("\nmean day-level P&L by gap bucket and anchor:")
    print(p2["mean_daily_pnl_by_bucket_and_anchor"].to_string())
    print("\nn per bucket/anchor:")
    print(p2["n_by_bucket"].to_string())

    p1["by_strategy"].to_csv(OUT_DIR / "gexlog_signal_recalc_by_strategy_20261031.csv", index=False)
    p1["by_anchor"].to_csv(OUT_DIR / "gexlog_signal_recalc_by_anchor_20261031.csv", index=False)
    p2["merged"].to_csv(OUT_DIR / "gexlog_gap_em_merged_20261031.csv", index=False)


if __name__ == "__main__":
    main()
