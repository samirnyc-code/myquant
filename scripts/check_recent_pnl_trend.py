"""One-shot diagnostic (S128): user asked why the sim desk is 'losing every day
now' after doing well. Pull the actual equity curve (account.csv net_liq, EOD
per day) and the realized P&L columns from daily_summary.csv, over the full
history, to see where/when the trend actually turned.

Usage: .venv/Scripts/python.exe scripts/check_recent_pnl_trend.py
Saves: data/options_sim/pnl_trend_<today>.csv
"""
import csv
from collections import OrderedDict
from datetime import date
from pathlib import Path

SIM = Path(__file__).resolve().parents[1] / "data" / "options_sim"


def eod_netliq():
    by_day = OrderedDict()
    with open(SIM / "account.csv", newline="") as fh:
        for row in csv.DictReader(fh):
            d = row["ts_et"][:10]
            by_day[d] = float(row["net_liq"])  # last write per day wins
    return by_day


def main():
    eod = eod_netliq()
    days = list(eod.items())
    out_rows = []
    prev = None
    for d, nl in days:
        chg = (nl - prev) if prev is not None else None
        out_rows.append((d, nl, chg))
        prev = nl

    out = SIM / f"pnl_trend_{date.today():%Y%m%d}.csv"
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "eod_net_liq", "day_change"])
        w.writerows(out_rows)

    print(f"{len(out_rows)} trading days, {out}")
    print("date,eod_net_liq,day_change")
    for d, nl, chg in out_rows:
        print(f"{d},{nl:.2f},{'' if chg is None else f'{chg:+.2f}'}")


if __name__ == "__main__":
    main()
