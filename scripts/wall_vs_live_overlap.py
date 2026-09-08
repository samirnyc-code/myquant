"""wall_vs_live_overlap.py — backtest (desk-stop gexlog wall condor) vs the LIVE
calendar's realized gx_bps/gx_bcs, on the OVERLAPPING days only.

The backtest (wall_pnl_stops.py, gx source) MODELS the desk rule (10-min acceptance
+ 14:45 stop, mid-fill) on gexlog walls. The live book ACTUALLY trades gx_bps/gx_bcs
at gexlog walls with the SAME rule and REAL IB fills. So on shared days this validates
the model. Live realized = sum of that day's closed gx_bps + gx_bcs pnl (trades.parquet).

Calendar basis note: the dashboard calendar excludes the 08-04/08-05 error days -> we
show totals BOTH with and without them.

Read-only. Writes a dated CSV.
  .venv/Scripts/python.exe scripts/wall_vs_live_overlap.py
"""
from __future__ import annotations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BT = ROOT / "data" / "options_sim" / "wall_pnl_stops.csv"
TRADES = ROOT / "data" / "options_log" / "trades.parquet"
OUT = ROOT / "data" / "options_sim"
EXCLUDE = {"2026-08-04", "2026-08-05"}     # calendar error days


def main() -> int:
    bt = pd.read_csv(BT)
    bt = bt[bt["source"] == "gx"][["date", "settle_pnl", "stopped_pnl"]].copy()

    t = pd.read_parquet(TRADES)
    t = t[t["strategy_id"].isin(["gx_bps", "gx_bcs"]) & t["exit_dt"].notna()].copy()
    t["date"] = t["entry_dt"].astype(str).str[:10]
    live = t.groupby("date").agg(live_gx=("pnl", lambda s: pd.to_numeric(s, errors="coerce").sum()),
                                 n_legs=("pnl", "size")).reset_index()

    m = bt.merge(live, on="date", how="inner").sort_values("date").reset_index(drop=True)
    if not len(m):
        print("no overlapping days"); return 1

    print(f"Overlapping days: {len(m)}  ({m.date.min()} -> {m.date.max()})\n")
    print(f"{'date':12}{'bt_settle':>11}{'bt_stopped':>12}{'live_gx':>11}{'stop-live':>11}  note")
    for _, r in m.iterrows():
        note = "cal-excluded (error day)" if r.date in EXCLUDE else ""
        print(f"{r.date:12}{r.settle_pnl:>11.0f}{r.stopped_pnl:>12.0f}{r.live_gx:>11.0f}"
              f"{r.stopped_pnl - r.live_gx:>11.0f}  {note}")

    def tot(df, col):
        return float(df[col].sum())
    for label, df in [("ALL overlap", m), ("calendar basis (excl 08-04/05)", m[~m.date.isin(EXCLUDE)])]:
        print(f"\n== {label}  (n={len(df)}) ==")
        print(f"  backtest settle (hold) : {tot(df,'settle_pnl'):>10,.0f}")
        print(f"  backtest desk-stop     : {tot(df,'stopped_pnl'):>10,.0f}")
        print(f"  LIVE gx realized       : {tot(df,'live_gx'):>10,.0f}")
        print(f"  desk-stop - live       : {tot(df,'stopped_pnl')-tot(df,'live_gx'):>10,.0f}")
        if len(df) > 2:
            c = df["stopped_pnl"].corr(df["live_gx"])
            print(f"  per-day corr(stop,live): {c:>10.2f}")

    outp = OUT / f"wall_vs_live_overlap_{m.date.max().replace('-','')}.csv"
    m.to_csv(outp, index=False)
    print(f"\nsaved -> {outp.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
