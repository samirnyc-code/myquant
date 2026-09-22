"""Graph: our 2E equity vs Apex's TRAILING EOD drawdown floor, entire 5-yr record.

Apex EOD trailing floor (relative to start = 0):
  peak = running max of end-of-day equity
  while peak < T + 100 : floor = peak - T           (trails your best EOD)
  once peak >= T + 100 : floor LOCKS at +100 forever (Safety Net reached)
  BLOW if EOD equity <= floor.
'Cushion' = equity - floor = how far you are from blowing at each day's close.

  python scripts/regime2e_apex_ddchart.py
Output: reports/regime2e/apex_dd_chart.png
"""
from glob import glob
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MULT = 50.0; COST = 17.5
OUTDIR = Path(__file__).resolve().parent.parent / "reports" / "regime2e"
THRESH = [(5000, "150K"), (6500, "250K"), (7500, "300K")]


def series(daily):
    eq = daily.cumsum().values
    return eq


def floor_and_cushion(eq, T):
    peak = np.maximum.accumulate(eq)
    locked = peak >= (T + 100)
    # once locked at index k, floor stays +100 from then on
    first_lock = np.argmax(locked) if locked.any() else -1
    floor = peak - T
    if first_lock >= 0:
        floor[first_lock:] = 100.0
    cushion = eq - floor
    return floor, cushion, first_lock


def main():
    path = Path(sorted(glob(str(OUTDIR / "mode_sweep_*.csv")))[-1])
    df = pd.read_csv(path); df["date"] = df["date"].astype(str)
    fig, ax = plt.subplots(2, 2, figsize=(15, 9))
    fig.suptitle("REGIME-2E equity vs Apex trailing EOD drawdown floor — full 5yr, 1 ES net",
                 fontsize=14, weight="bold")

    for row, mode in enumerate(["one_per_day", "flip"]):
        g = df[df["mode"] == mode].assign(net=(df["pts"] - COST / MULT) * MULT)
        daily = g.groupby("date")["net"].sum()
        x = pd.to_datetime(daily.index)
        eq = series(daily)

        # left: equity + floor + cushion shade (150K threshold)
        T = 5000
        floor, cushion, lk = floor_and_cushion(eq, T)
        a = ax[row, 0]
        a.plot(x, eq, color="#2e7d32", lw=1.4, label="EOD equity (profit vs start)")
        a.plot(x, floor, color="#c62828", lw=1.2, ls="--", label="trailing DD floor (150K, $5k)")
        a.fill_between(x, floor, eq, where=(eq >= floor), color="#2e7d32", alpha=0.08)
        a.axhline(0, color="#888", lw=0.6)
        if lk >= 0:
            a.axvline(x[lk], color="#1565c0", lw=1, ls=":")
            a.annotate("floor LOCKS at +$100\n(banked $5.1k)", (x[lk], 100),
                       fontsize=8, color="#1565c0", xytext=(10, 20), textcoords="offset points")
        mn = np.argmin(cushion)
        a.annotate(f"closest to floor: ${cushion[mn]:,.0f}", (x[mn], eq[mn]),
                   fontsize=8, color="#c62828", xytext=(10, -25), textcoords="offset points")
        a.set_title(f"{mode}: equity vs $5k trailing floor"); a.set_ylabel("$ vs start"); a.legend(fontsize=8)

        # right: cushion (eq - floor) for all 3 thresholds; 0 = blow
        a2 = ax[row, 1]
        for T, name in THRESH:
            _, cu, _ = floor_and_cushion(eq, T)
            a2.plot(x, cu, lw=1.2, label=f"{name} (${T/1000:.1f}k)  min ${cu.min():,.0f}")
        a2.axhline(0, color="#c62828", lw=1.5, ls="--", label="0 = ACCOUNT BLOWN")
        a2.set_title(f"{mode}: cushion to floor (higher = safer)"); a2.set_ylabel("$ above floor"); a2.legend(fontsize=8)

    for a in ax.flat:
        a.tick_params(labelsize=8)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = OUTDIR / "apex_dd_chart.png"
    fig.savefig(out, dpi=110)
    print(f"chart: {out}")
    # print the min-cushion table
    print("\nminimum cushion to floor (lower = closer to blowing) over 5yr:")
    for mode in ["one_per_day", "flip"]:
        g = df[df["mode"] == mode].assign(net=(df["pts"] - COST / MULT) * MULT)
        eq = g.groupby("date")["net"].sum().cumsum().values
        row = "  " + mode.ljust(12)
        for T, name in THRESH:
            _, cu, _ = floor_and_cushion(eq, T)
            row += f"  {name}: ${cu.min():+,.0f}"
        print(row)


if __name__ == "__main__":
    main()
