"""Reconcile the dashboard's Analytics tab (scripts/options_dashboard.py) against
the 2026-10-30 duplicate-fire incident.

The Analytics tab's stats are NOT per-day for 10-30 alone — "Max drawdown" is the
worst day-level trough across the ENTIRE equity curve (all history), built by
bucketing every trade's P&L on its realized date (bucket_date =
analytics_payload()'s own rule: exit date if closed, else entry date — see
options_dashboard.py:748), summing to a daily P&L, then a running
cum/peak/dd=cum-peak series (buildDaily(), options_dashboard.py:1581-1599). Since
all 27 of 10-30's rows (10 intended + 17 duplicate-fire copies) are real rows in
trades.parquet, they are ALL already flowing into that curve today — the dashboard
is not reading a stale number, it's reading the bug-inflated one.

This script replicates BOTH JS functions in Python exactly (statAll +
buildDaily) over the FULL trade history, once as-is (what the tab shows right
now) and once with 10-30's 17 duplicate rows removed (single-run baseline), and
reports where they diverge — specifically whether 10-30 is actually the account's
worst drawdown day (if not, fixing the duplicates doesn't move the Max DD tile at
all, it only moves Total P&L / win rate / etc).

Run: .venv/Scripts/python.exe scripts/analytics_tab_reconcile_20261030.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "options_log" / "_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)
BUG_DATE = "2026-10-30"


def load_all_trades() -> pd.DataFrame:
    df = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
    df["entry_dt"] = pd.to_datetime(df["entry_dt"])
    df["exit_dt"] = pd.to_datetime(df["exit_dt"])
    return df


def bucket_date(row) -> str:
    """Mirrors analytics_payload(), options_dashboard.py:748."""
    is_open = pd.isna(row["exit_dt"])
    if not is_open:
        return row["exit_dt"].strftime("%Y-%m-%d")
    return row["entry_dt"].strftime("%Y-%m-%d")


def stat_all(df: pd.DataFrame) -> dict:
    """Mirrors statAll(), options_dashboard.py:1555-1563 — flat over ALL closed
    trades (not day-bucketed): n, total, win rate, profit factor, expectancy,
    avg ROI. Also computes the trade-level (not daily) dd as the JS does when
    there's no daily series, though we always have one here."""
    closed = df[df["pnl"].notna()].copy()
    p = closed["pnl"].values
    w = p[p >= 0]
    l = p[p < 0]
    tot = p.sum()
    pf = (w.sum() / -l.sum()) if len(l) else None
    roi = closed.apply(lambda r: (r["pnl"] / r["collateral"] * 100)
                        if pd.notna(r["collateral"]) and r["collateral"] else None, axis=1)
    roi = roi.dropna()
    avgroi = roi.mean() if len(roi) else None
    return {
        "n": len(p), "total_pnl": round(tot, 2),
        "win_rate_pct": round(len(w) / len(p) * 100, 1) if len(p) else None,
        "profit_factor": round(pf, 3) if pf is not None else None,
        "expectancy": round(tot / len(p), 2) if len(p) else None,
        "avg_roi_pct": round(avgroi, 2) if avgroi is not None else None,
    }


def build_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Mirrors buildDaily(), options_dashboard.py:1581-1599 — day-level P&L,
    cumulative equity, running peak, drawdown = cum - peak."""
    closed = df[df["pnl"].notna()].copy()
    closed["bucket"] = closed.apply(bucket_date, axis=1)
    daily = closed.groupby("bucket")["pnl"].sum().sort_index().reset_index()
    daily.columns = ["date", "pnl"]
    cum = 0.0
    peak = 0.0
    cums, peaks, dds = [], [], []
    for pnl in daily["pnl"]:
        cum += pnl
        peak = max(peak, cum)
        dds.append(cum - peak)
        cums.append(cum)
        peaks.append(peak)
    daily["cum"] = cums
    daily["peak"] = peaks
    daily["dd"] = dds
    return daily


def main():
    df = load_all_trades()

    # ---- AS-IS: exactly what the Analytics tab shows right now ----
    stats_actual = stat_all(df)
    daily_actual = build_daily(df)
    maxdd_actual_row = daily_actual.loc[daily_actual["dd"].idxmin()]
    stats_actual["max_drawdown"] = round(daily_actual["dd"].min(), 2)

    # ---- BASELINE: drop the 17 duplicate-fire rows on 10-30, keep only the
    # first fire of each strategy_id that day (what should have happened) ----
    day_mask = df["entry_dt"].dt.strftime("%Y-%m-%d") == BUG_DATE
    day = df[day_mask].sort_values("entry_dt")
    wave = day.groupby("strategy_id").cumcount()
    dup_ids = day[wave > 0]["trade_id"]
    df_baseline = df[~df["trade_id"].isin(dup_ids)].copy()

    stats_baseline = stat_all(df_baseline)
    daily_baseline = build_daily(df_baseline)
    stats_baseline["max_drawdown"] = round(daily_baseline["dd"].min(), 2)
    maxdd_baseline_row = daily_baseline.loc[daily_baseline["dd"].idxmin()]

    out = []
    out.append("# Analytics tab reconciliation — 2026-10-30 duplicate-fire\n")
    out.append("## Account-wide stats, AS CURRENTLY SHOWN on the Analytics tab (actual, bug-inflated 10-30 row set)\n")
    for k, v in stats_actual.items():
        out.append(f"- {k}: {v}")
    out.append(f"- max_drawdown occurs on: {maxdd_actual_row['date']} (day pnl {maxdd_actual_row['pnl']:.2f}, "
                f"cum {maxdd_actual_row['cum']:.2f}, peak {maxdd_actual_row['peak']:.2f})")
    out.append("\n## Account-wide stats, BASELINE (10-30 duplicate-fire rows removed, single run only)\n")
    for k, v in stats_baseline.items():
        out.append(f"- {k}: {v}")
    out.append(f"- max_drawdown occurs on: {maxdd_baseline_row['date']} (day pnl {maxdd_baseline_row['pnl']:.2f}, "
                f"cum {maxdd_baseline_row['cum']:.2f}, peak {maxdd_baseline_row['peak']:.2f})")
    out.append("\n## Delta (actual - baseline)\n")
    for k in stats_actual:
        if isinstance(stats_actual[k], (int, float)) and isinstance(stats_baseline.get(k), (int, float)):
            out.append(f"- {k}: {round(stats_actual[k] - stats_baseline[k], 3)}")
    out.append(f"\n## Is 10-30 actually the account's worst drawdown day?\n")
    out.append(f"- As-is: {'YES' if maxdd_actual_row['date'] == BUG_DATE else 'NO — worse day exists: ' + maxdd_actual_row['date']}")
    out.append(f"- Baseline: {'YES' if maxdd_baseline_row['date'] == BUG_DATE else 'NO — worse day exists: ' + maxdd_baseline_row['date']}")

    report_path = OUT_DIR / "analytics_tab_reconcile_20261030.md"
    report_path.write_text("\n".join(out), encoding="utf-8")
    daily_actual.to_csv(OUT_DIR / "daily_equity_curve_actual_20261030.csv", index=False)
    daily_baseline.to_csv(OUT_DIR / "daily_equity_curve_baseline_20261030.csv", index=False)

    print("\n".join(out))
    print(f"\nwrote {report_path}")


if __name__ == "__main__":
    main()
