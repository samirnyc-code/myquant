"""Trace the account equity path + rerun from later start dates (no tick reprocess).

Loads the saved flip-mode trades (regime2e_flip_scale_sim.py output), then:
  - traces the 1 ES EOD equity curve around the Nov-2021 blow: running peak (hwm),
    trailing floor = min(hwm,4500)-4500, and where/why it first violates.
  - reruns the $4,500-EOD-trailing-freeze-at-BE account for several ACCOUNT-OPEN
    dates (you can't choose your start in reality, but this tests period-luck).

  python scripts/regime2e_flip_account_analysis.py [flip_trades_csv]
"""
import sys
from glob import glob
from pathlib import Path
import numpy as np
import pandas as pd

DD = 4500.0; SUB = 200.0
REPO = Path(__file__).resolve().parent.parent
OUTDIR = REPO / "reports" / "regime2e"


def daily_series(df, mult, cost):
    d = df.copy()
    d["net_pts"] = d["pts"] - cost / mult
    return d.groupby("date")["net_pts"].sum() * mult      # $ per day at 1 contract


def sim(daily, base, step, start=None):
    """STATIC DD: floor is fixed at start - $4,500 (EOD), does NOT trail the peak.
    Blown only if EOD equity (relative to start=0) ever <= -4,500."""
    if start:
        daily = daily[daily.index >= start]
    eq = peak = 0.0; maxdd = 0.0; size = base; blown = None
    min_eq = 0.0                                   # deepest EOD equity below start
    sub_paid = 0.0; pm = None; rows = []
    for d, pnl1 in daily.items():
        m = d[:7]
        if m != pm:
            sub_paid += SUB; pm = m
        size = min(15, base + int(max(eq, 0) // step)) if step else base
        eq += pnl1 * size
        floor = -DD                                # STATIC, below start
        peak = max(peak, eq); maxdd = min(maxdd, eq - peak)
        min_eq = min(min_eq, eq)
        rows.append((d, eq, peak, floor, size))
        if blown is None and eq <= floor:
            blown = d
    return dict(final=eq, take=eq - sub_paid, sub=sub_paid, maxdd=maxdd,
                min_eq=min_eq, blown=blown, end_size=size, rows=rows)


def main():
    csvs = sorted(glob(str(OUTDIR / "flip_trades_*.csv")))
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(csvs[-1])
    df = pd.read_csv(path); df["date"] = df["date"].astype(str)
    print(f"loaded {len(df)} flip trades from {path.name}\n")

    es = daily_series(df, 50.0, 17.5)
    mes = daily_series(df, 5.0, 6.25)

    # --- STATIC DD: the survival question is simply how deep EOD equity ever goes
    #     below the STARTING balance (floor = -$4,500, fixed). ---
    print("STATIC DD model: floor = start - $4,500 (fixed, EOD). Blow only if EOD")
    print("equity ever closes >= $4,500 below where you started.\n")
    r = sim(es, 1, 0)
    cur = pd.DataFrame(r["rows"], columns=["date", "eq", "peak", "floor", "size"])
    trough_dt = cur.loc[cur["eq"].idxmin(), "date"]
    print(f"1 ES: deepest EOD equity below start = ${r['min_eq']:+,.0f} (on {trough_dt}) "
          f"vs floor -$4,500 -> {'BLOWN' if r['blown'] else 'SURVIVES'}"
          + (f" ({r['blown']})" if r["blown"] else f", margin ${r['min_eq']+DD:,.0f}"))
    print("  1 ES EOD equity at each year-end + intra-year trough:")
    cur["yr"] = cur["date"].str[:4]
    for y, x in cur.groupby("yr"):
        print(f"    {y}: year-end ${x['eq'].iloc[-1]:+8,.0f}   lowest-EOD ${x['eq'].min():+8,.0f} "
              f"({x.loc[x['eq'].idxmin(),'date']})")

    print("\nRERUN FROM LATER ACCOUNT-OPEN DATES (static $4,500 floor each start):")
    for label, start in [("2021-06 (full)", None), ("2022-06-18", "2022-06-18"),
                         ("2023-01-01", "2023-01-01"), ("2024-01-01", "2024-01-01")]:
        print(f"  --- open {label} ---")
        for inst, ser in (("ES ", es), ("MES", mes)):
            for base, step in ((1, 0), (1, 20000)):
                rr = sim(ser, base, step, start)
                st = f"BLOWN {rr['blown']}" if rr["blown"] else f"SURVIVES (deepest ${rr['min_eq']:+,.0f})"
                tag = f"{base}c fixed" if not step else f"1c +1/$20k(end {rr['end_size']}c)"
                print(f"    {inst} {tag:22}: acct ${rr['final']:+8,.0f}  take ${rr['take']:+8,.0f}  -> {st}")

    # --- November seasonality: real effect or coincidence? ---
    print("\nNOVEMBER CHECK — calendar-month P&L across ALL years (1 ES, $/pt=50):")
    df["mo"] = df["date"].str[5:7]
    mo = df.assign(pnl=(df["pts"] - 17.5 / 50.0) * 50.0).groupby("mo")["pnl"].agg(["sum", "count"])
    for m, x in mo.iterrows():
        bar = "#" * int(abs(x["sum"]) / 400)
        print(f"    {m}: ${x['sum']:+7,.0f}  (n={int(x['count'])})  {bar}")
    novs = df[df["mo"] == "11"].assign(yr=df["date"].str[:4], pnl=(df["pts"] - 0.35) * 50.0)
    print("  November by year:  " + "  ".join(
        f"{y}:${g['pnl'].sum():+,.0f}(n{len(g)})" for y, g in novs.groupby("yr")))


if __name__ == "__main__":
    main()
