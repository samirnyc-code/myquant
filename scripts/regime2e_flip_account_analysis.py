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
    if start:
        daily = daily[daily.index >= start]
    eq = hwm = peak = 0.0; maxdd = 0.0; size = base; blown = None
    sub_paid = 0.0; pm = None; rows = []
    for d, pnl1 in daily.items():
        m = d[:7]
        if m != pm:
            sub_paid += SUB; pm = m
        size = min(15, base + int(max(eq, 0) // step)) if step else base
        eq += pnl1 * size
        hwm = max(hwm, eq)
        floor = min(hwm, DD) - DD
        peak = max(peak, eq); maxdd = min(maxdd, eq - peak)
        rows.append((d, eq, hwm, floor, size))
        if blown is None and eq <= floor:
            blown = d
    return dict(final=eq, take=eq - sub_paid, sub=sub_paid, maxdd=maxdd,
                blown=blown, end_size=size, rows=rows)


def main():
    csvs = sorted(glob(str(OUTDIR / "flip_trades_*.csv")))
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(csvs[-1])
    df = pd.read_csv(path); df["date"] = df["date"].astype(str)
    print(f"loaded {len(df)} flip trades from {path.name}\n")

    es = daily_series(df, 50.0, 17.5)

    # --- trace the 1 ES blow ---
    r = sim(es, 1, 0)
    cur = pd.DataFrame(r["rows"], columns=["date", "eq", "hwm", "floor", "size"])
    cur["yr"] = cur.date.str[:7]
    print("1 ES — EOD equity by MONTH-END through the first blow:")
    monthly = cur.groupby("yr").tail(1)
    for _, x in monthly[monthly["yr"] <= "2021-12"].iterrows():
        flag = "  <-- BLOWN" if r["blown"] and x["date"] == r["blown"] else ""
        print(f"  {x['date']}: eq ${x['eq']:+8,.0f}  peak ${x['hwm']:+8,.0f}  floor ${x['floor']:+8,.0f}{flag}")
    if r["blown"]:
        b = cur[cur["date"] == r["blown"]].iloc[0]
        pre = cur[cur["date"] < r["blown"]]
        peak_before = pre["eq"].max(); peak_dt = pre.loc[pre["eq"].idxmax(), "date"]
        print(f"\n  peak BEFORE blow: ${peak_before:+,.0f} on {peak_dt}")
        print(f"  blow day {r['blown']}: eq ${b['eq']:+,.0f}, floor ${b['floor']:+,.0f} "
              f"(hwm ${b['hwm']:+,.0f}; floor still trailing if hwm < +$4,500)")
        print(f"  drawdown peak->blow = ${b['eq'] - peak_before:+,.0f}")
        seg = cur[(cur["date"] >= peak_dt) & (cur["date"] <= r["blown"])]
        print(f"  that decline spanned {len(seg)} trading days ({peak_dt} -> {r['blown']})")

    # --- rerun from later account-open dates, ES and MES ---
    print("\n\nRERUN FROM LATER ACCOUNT-OPEN DATES (fresh $4,500 DD each start):")
    mes = daily_series(df, 5.0, 6.25)
    for label, start in [("2021-06 (full)", None), ("2022-06-18", "2022-06-18"),
                         ("2023-01-01", "2023-01-01"), ("2024-01-01", "2024-01-01")]:
        print(f"\n  --- open {label} ---")
        for inst, ser in (("ES ", es), ("MES", mes)):
            for base, step in ((1, 0), (1, 20000)):
                rr = sim(ser, base, step, start)
                st = f"BLOWN {rr['blown']}" if rr["blown"] else "SURVIVES"
                tag = f"{base}c fixed" if not step else f"1c +1/$20k(end {rr['end_size']}c)"
                print(f"    {inst} {tag:22}: acct ${rr['final']:+8,.0f}  take ${rr['take']:+8,.0f}  "
                      f"maxDD ${rr['maxdd']:+8,.0f} -> {st}")


if __name__ == "__main__":
    main()
