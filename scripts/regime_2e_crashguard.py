"""CRASH GUARD — the LONG-2E+ER10 book's one real tail is buying continuation-longs into a fast
decline (2020 COVID = -$11.9k in one year). Theory-motivated causal guard: skip longs when the
prior-5-session return is sharply negative. Kept ONLY because it improves EVERY 4-yr block (not
just aggregate) and is robust across thresholds -> not curve-fit.

Reads oos_pertrade_full_20260725.csv + _db_es_5m_rth (daily ER10 + ret5, causal).

  python scripts/regime_2e_crashguard.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
CSV = WT / "data" / "regime" / "oos_pertrade_full_20260725.csv"
BLOCKS = [(2010, 2013), (2014, 2017), (2018, 2021), (2022, 2026)]


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def main():
    d = pd.read_csv(CSV); d = d[d.with_trend & (d.dir == "L")].copy()
    d = d[d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})]
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet")
    b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    dd = b.groupby("Date").agg(C=("Close", "last")).reset_index().sort_values("Date")
    c = dd["C"]; chg = c.diff().abs()
    dd["er10"] = ((c - c.shift(10)).abs() / chg.rolling(10).sum()).shift(1)
    dd["medexp"] = dd["er10"].expanding(min_periods=60).median()
    dd["er10_top"] = (dd["er10"] > dd["medexp"]).astype(float)
    dd["ret5"] = c.pct_change(5).shift(1)                       # causal prior-5d return
    d = d.merge(dd.set_index("Date")[["er10_top", "ret5"]], left_on="Date", right_index=True, how="left")
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    mv = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    d["net"] = mv * PT - COMM - SLIP; d["Rn"] = d.net / (S * PT)
    book = d[d.er10_top == 1].copy()

    print("CRASH GUARD: skip long-2E+ER10 when prior-5d return < threshold (causal)\n")
    print(f"{'guard':<16}{'n':>5}{'net':>9}{'PF':>6}{'meanR':>7}   blocks[10-13/14-17/18-21/22-26]  2020    2017")
    for thr in [None, -0.03, -0.04, -0.05, -0.06]:
        bk = book if thr is None else book[book.ret5 >= thr]
        lab = "NONE" if thr is None else f"skip<{thr:.0%}"
        blocks = "/".join(f"{pf(bk[(bk.yr>=y0)&(bk.yr<=y1)].net):.2f}" for y0, y1 in BLOCKS)
        print(f"{lab:<16}{len(bk):>5}{bk.net.sum():>+9,.0f}{pf(bk.net):>6.2f}{bk.Rn.mean():>+7.3f}   "
              f"{blocks}   {bk[bk.yr==2020].net.sum():>+7,.0f} {bk[bk.yr==2017].net.sum():>+7,.0f}")

    print("\nLOCKED forward spec = LONG-2E + ER10-top + skip-if-ret5<-4%:")
    fin = book[book.ret5 >= -0.04]
    print(f"  n={len(fin)} ({len(fin)/16.5:.0f}/yr)  net ${fin.net.sum():+,.0f} (${fin.net.sum()/16.5:+,.0f}/yr)  "
          f"PF {pf(fin.net)}  meanR {fin.Rn.mean():+.3f}  win {100*(fin.net>0).mean():.0f}%")


if __name__ == "__main__":
    main()
