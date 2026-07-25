"""VOL-REGIME HISTORY — is the 2010-2017 low-vol era structurally behind us, or will it return?
Quantifies VIX + ES intraday-range regimes by year and flags the structural-change timeline
(0DTE, retail options, rate regime). Frames how much to worry about the strategy's vol-dependence.

Reads data/vix_daily.csv (1990-2026) + _db_es_5m_rth.parquet (ES intraday range).

  python scripts/regime_2e_vol_history.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")


def main():
    v = pd.read_csv(DATA / "vix_daily.csv"); v["date"] = pd.to_datetime(v["date"]); v["yr"] = v.date.dt.year
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["DateTime"] = pd.to_datetime(b["DateTime"])
    b["Date"] = b["DateTime"].dt.date.astype(str)
    day = b.groupby("Date").agg(H=("High", "max"), L=("Low", "min"), C=("Close", "last"))
    day["rng_pct"] = (day.H - day.L) / day.C * 100
    day["yr"] = pd.to_datetime(day.index).year

    print("========== VIX + ES intraday-range regime by year ==========")
    print(f"{'yr':>4}{'VIXmean':>8}{'VIXmed':>7}{'%d<15':>7}{'%d<13':>7}{'%d>25':>7}   "
          f"{'ES rng%med':>10}{'%d<0.7%':>8}")
    for yr in range(2007, 2027):
        vv = v[v.yr == yr]["close"]
        dd = day[day.yr == yr]["rng_pct"]
        if not len(vv):
            continue
        lowrng = 100 * (dd < 0.7).mean() if len(dd) else float('nan')
        rngmed = dd.median() if len(dd) else float('nan')
        print(f"{yr:>4}{vv.mean():>8.1f}{vv.median():>7.1f}{100*(vv<15).mean():>7.0f}"
              f"{100*(vv<13).mean():>7.0f}{100*(vv>25).mean():>7.0f}   {rngmed:>10.2f}{lowrng:>8.0f}")

    print("\n========== era summary ==========")
    eras = [("2007-2009 GFC", 2007, 2009), ("2010-2017 QE/ZIRP grind", 2010, 2017),
            ("2018-2019 transition", 2018, 2019), ("2020 COVID", 2020, 2020),
            ("2021-2026 rate/0DTE era", 2021, 2026)]
    for nm, y0, y1 in eras:
        vv = v[(v.yr >= y0) & (v.yr <= y1)]["close"]
        dd = day[(day.yr >= y0) & (day.yr <= y1)]["rng_pct"]
        print(f"{nm:<28} VIX mean {vv.mean():4.1f} med {vv.median():4.1f}  %VIX<15 {100*(vv<15).mean():3.0f}%  "
              f"ES rng% med {dd.median():.2f}  %low-range(<0.7) {100*(dd<0.7).mean():3.0f}%")

    print("\n========== structural-change timeline (context, not backtest) ==========")
    for yr, ev in [(2005, "VIX weeklys; algo/HFT ramp"), (2010, "Flash Crash; HFT dominant; Reg-driven fragmentation"),
                   (2013, "SPX Wed weeklys"), (2016, "SPX Mon/Wed weeklys — more expiries"),
                   (2020, "COVID; retail-options boom (Robinhood); 0DTE retail begins"),
                   (2022, "SPX Tue/Thu -> DAILY 0DTE expiries; 0DTE ~40-50% of SPX vol by 2023"),
                   (2022, "Fed hiking cycle ends ZIRP; QT; macro-vol regime up"),
                   (2023, "0DTE dominant; AI/LLM-driven flow narrative begins")]:
        print(f"  {yr}: {ev}")


if __name__ == "__main__":
    main()
