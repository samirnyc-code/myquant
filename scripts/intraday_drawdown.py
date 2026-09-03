"""intraday_drawdown.py — worst intraday MTM drawdown of the SPX 0DTE desk.

Reconstructs each day's intraday equity curve = realized(closed by t) + sum(open-position
unreal_pnl at t) from marks.csv + trades.parquet, then reports per day: the deepest underwater
point (trough) and the biggest peak-to-trough drop. Read-only. Saves data/options_sim/intraday_dd.csv.
Run: .venv/Scripts/python.exe scripts/intraday_drawdown.py
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog

SIM = Path(__file__).resolve().parents[1] / "data" / "options_sim"


def main():
    m = pd.read_csv(SIM / "marks.csv")
    m["ts"] = pd.to_datetime(m.ts_et, errors="coerce")
    m["day"] = m.ts.dt.strftime("%Y-%m-%d")
    m["unreal_pnl"] = pd.to_numeric(m.unreal_pnl, errors="coerce")

    tr = tlog.load()
    tr["pnl"] = pd.to_numeric(tr.pnl, errors="coerce")
    tr["xdt"] = pd.to_datetime(tr.exit_dt, errors="coerce")
    tr["eday"] = pd.to_datetime(tr.entry_dt, errors="coerce").dt.strftime("%Y-%m-%d")

    rows = []
    for day, mg in m.groupby("day"):
        dt_trades = tr[(tr.eday == day) & tr.pnl.notna()]
        # equity at each mark timestamp = open unreal (that ts) + realized already booked by ts
        curve = []
        for ts, g in mg.groupby("ts"):
            open_mtm = g.unreal_pnl.sum()
            realized = dt_trades[dt_trades.xdt <= ts].pnl.sum()
            curve.append((ts, open_mtm + realized))
        if not curve:
            continue
        eq = pd.Series([v for _, v in curve])
        trough = eq.min()                      # deepest underwater point of the day
        peak2trough = (eq.cummax() - eq).max() # largest peak-to-trough drop
        rows.append({"day": day, "n_marks": len(curve), "intraday_trough": round(trough),
                     "peak_to_trough_dd": round(peak2trough), "day_close_mtm": round(eq.iloc[-1])})
    r = pd.DataFrame(rows).sort_values("intraday_trough")
    print("=== WORST intraday troughs (deepest underwater point in the day) ===")
    print(r.head(8).to_string(index=False))
    print("\n=== BIGGEST peak-to-trough drawdowns ===")
    print(r.sort_values("peak_to_trough_dd", ascending=False).head(8).to_string(index=False))
    print(f"\nWORST single intraday trough: ${r.intraday_trough.min():,.0f} on {r.loc[r.intraday_trough.idxmin(),'day']}")
    print(f"BIGGEST peak-to-trough DD:    ${r.peak_to_trough_dd.max():,.0f} on {r.loc[r.peak_to_trough_dd.idxmax(),'day']}")
    r.to_csv(SIM / "intraday_dd.csv", index=False)


if __name__ == "__main__":
    main()
