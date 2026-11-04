"""Audit: why did the Analytics tab's "ideal account size" line jump, and does
the EOD drawdown chart agree with other drawdown numbers on the dashboard?

Reproduces options_dashboard.py's client-side buildDaily()/analytics_payload()
logic in Python against the real trades.parquet, day by day, so the jump can
be pinned to an exact date/cause instead of eyeballed off a chart. Also pulls
shadow_stop_log.csv's "trough" (intraday DD) for the same window to compare
against the EOD (close-to-close) drawdown the Analytics chart plots -- these
are two different metrics by design (see options_dashboard.py buildDaily()
comment: "DD is END-OF-DAY ... not intraday"), so a mismatch between them is
expected, not a bug -- this just makes the actual numbers visible side by side.

Usage: .venv/Scripts/python.exe scripts/analytics_capital_dd_audit_20261103.py
Writes data/options_sim/_analysis/capital_dd_audit_<ts>.csv
"""
import csv
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
import options_dashboard as dash   # reuse the REAL display filter (_shown): EXCLUDE_DAYS +
                                     # dedupe_mirrors + dedupe_duplicate_fires -- a raw
                                     # trades.parquet read (no filter) does NOT match what
                                     # the dashboard actually shows.
import options_trade_log as tlog

LOG = ROOT / "data" / "options_log" / "trades.parquet"
SHADOW = ROOT / "data" / "options_sim" / "shadow_stop_log.csv"
OUT = ROOT / "data" / "options_sim" / "_analysis"
OUT.mkdir(parents=True, exist_ok=True)
IDEAL_BUFFER = 0.25


def build_daily(trades):
    rows = []
    for _, r in trades.iterrows():
        is_open = pd.isna(r.exit_dt)
        pnl = None if is_open else (float(r.pnl) if pd.notna(r.pnl) else None)
        if pnl is None:
            continue   # mirrors T.filter(t=>t.pnl!=null) in buildDaily()
        coll = float(r.collateral) if pd.notna(r.collateral) else 0.0
        entry = str(r.entry_dt) if pd.notna(r.entry_dt) else ""
        exitd = str(r.exit_dt) if pd.notna(r.exit_dt) else ""
        bucket_date = exitd[:10] if (not is_open and exitd) else entry[:10]
        rows.append({"trade_id": r.trade_id, "strategy": r.strategy_id,
                      "date": bucket_date, "entry_day": entry[:10], "pnl": pnl, "coll": coll})
    df = pd.DataFrame(rows)
    by_day = df.groupby("date")["pnl"].sum().sort_index()
    days = by_day.index.tolist()
    last_day = days[-1] if days else None

    cum, peak = 0.0, 0.0
    day_recs = {}
    for d in days:
        cum += by_day[d]
        peak = max(peak, cum)
        day_recs[d] = {"d": d, "pnl": round(by_day[d], 2), "cum": round(cum, 2), "dd": round(cum - peak, 2)}

    coll_by = {d: 0.0 for d in days}
    for _, t in df.iterrows():
        c = t["coll"]
        if not c:
            continue
        e = t["entry_day"] or t["date"]
        x = last_day if False else (t["date"] or e)   # no "open" trades reach here (pnl filter above)
        for d in days:
            if e <= d <= x:
                coll_by[d] += c

    mc, mdd = 0.0, 0.0
    for d in days:
        day_recs[d]["coll"] = round(coll_by[d], 2)
        mc = max(mc, coll_by[d])
        day_recs[d]["maxColl"] = round(mc, 2)
        mdd = max(mdd, -day_recs[d]["dd"])
        day_recs[d]["base"] = round(mc + mdd, 2)
        day_recs[d]["ideal"] = round((mc + mdd) * (1 + IDEAL_BUFFER), 2)
    return [day_recs[d] for d in days]


def main():
    raw = tlog.load()
    shown = dash._shown(raw)   # same filter the live dashboard applies before anything else
    trades = pd.concat([shown, dash._recon_df()], ignore_index=True)   # + reconstructed desk-down days, same as gp_trades_all
    print(f"raw trades: {len(raw)}  after _shown(): {len(shown)}  + recon days: {len(trades) - len(shown)}  "
          f"= {len(trades)} total (this matches analytics_payload's actual input)\n")
    daily = build_daily(trades)

    print(f"{'date':<12}{'pnl':>10}{'cum':>10}{'dd (EOD)':>10}{'coll':>10}{'maxColl':>10}{'ideal':>12}")
    prev_ideal = None
    for d in daily:
        marker = ""
        if prev_ideal is not None and d["ideal"] != prev_ideal:
            marker = "  <<< ideal changed"
        print(f"{d['d']:<12}{d['pnl']:>10.0f}{d['cum']:>10.0f}{d['dd']:>10.0f}"
              f"{d['coll']:>10.0f}{d['maxColl']:>10.0f}{d['ideal']:>12.0f}{marker}")
        prev_ideal = d["ideal"]

    # cross-check against shadow_stop_log.csv's intraday trough for the same days
    if SHADOW.exists():
        shadow_rows = {r["date"]: r for r in csv.DictReader(SHADOW.open())}
        print("\n--- EOD dd (Analytics chart) vs intraday trough (Shadow Daily Stop panel) ---")
        print(f"{'date':<12}{'EOD dd':>10}{'intraday trough':>18}")
        for d in daily[-15:]:
            sr = shadow_rows.get(d["d"])
            trough = sr["trough"] if sr else "—"
            print(f"{d['d']:<12}{d['dd']:>10.0f}{trough:>18}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_f = OUT / f"capital_dd_audit_{ts}.csv"
    pd.DataFrame(daily).to_csv(out_f, index=False)
    print(f"\nwrote {out_f}")


if __name__ == "__main__":
    main()
