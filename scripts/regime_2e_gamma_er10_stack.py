"""GAMMA x ER10 STACK — both prior-session NEG-gamma and prior-day trend-efficiency (ER10-top)
independently and causally condition the long-2E edge (PF 1.30 / 1.32 vs base 1.23). Do they
STACK? Test base / each / AND / OR, per 4-year block, on the long book. + crash guard.

All causal. Reads oos_pertrade_full + mq_regime_daily + _db_es_5m_rth.

  python scripts/regime_2e_gamma_er10_stack.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
CSV = WT / "data" / "regime" / "oos_pertrade_full_20260725.csv"
MQ = DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv"
BLOCKS = [(2010, 2013), (2014, 2017), (2018, 2021), (2022, 2026)]


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def brow(name, m):
    row = f"{name:<30}"; ok = True
    for (y0, y1) in BLOCKS:
        b = m[(m.yr >= y0) & (m.yr <= y1)]
        mr = b.Rn.mean() if len(b) else float('nan')
        row += f"{mr:>+8.3f}" if len(b) else f"{'-':>8}"
        if not (len(b) and mr > 0):
            ok = False
    print(row + f"  PF {pf(m.net):.2f} n={len(m)} $/yr {m.net.sum()/16.5:+,.0f} {'ROBUST' if ok else ''}")


def main():
    d = pd.read_csv(CSV); d = d[d.with_trend & (d.dir == "L")].copy()
    d = d[d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})]
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    mv = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    d["net"] = mv * PT - COMM - SLIP; d["Rn"] = d.net / (S * PT)

    # prior-session gamma label (causal)
    mq = pd.read_csv(MQ).sort_values("date").reset_index(drop=True); mq["date"] = mq["date"].astype(str)
    mq["greg_prev"] = mq["regime"].shift(1)
    d = d.merge(mq[["date", "greg_prev"]].rename(columns={"date": "Date"}), on="Date", how="left")

    # ER10 causal + ret5 crash guard
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet")
    b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    dd = b.groupby("Date").agg(C=("Close", "last")).reset_index().sort_values("Date")
    c = dd["C"]; chg = c.diff().abs()
    dd["er10"] = ((c - c.shift(10)).abs() / chg.rolling(10).sum()).shift(1)
    dd["er10_top"] = (dd["er10"] > dd["er10"].expanding(min_periods=60).median()).astype(float)
    dd["ret5"] = c.pct_change(5).shift(1)
    d = d.merge(dd.set_index("Date")[["er10_top", "ret5"]], left_on="Date", right_index=True, how="left")

    neg = d.greg_prev == "negative_gamma"; eff = d.er10_top == 1; guard = d.ret5 >= -0.04
    print(f"{'gate':<30}{'2010-13':>8}{'2014-17':>8}{'2018-21':>8}{'2022-26':>8}")
    brow("BASE long", d)
    brow("ER10-top", d[eff])
    brow("prior NEG-gamma", d[neg])
    brow("ER10-top AND NEG-gamma", d[eff & neg])
    brow("ER10-top OR NEG-gamma", d[eff | neg])
    print("-- with crash guard (ret5>=-4%) --")
    brow("ER10-top + guard", d[eff & guard])
    brow("(ER10 OR NEGgamma) + guard", d[(eff | neg) & guard])
    brow("(ER10 AND NEGgamma) + guard", d[eff & neg & guard])

    print("\n== full stats of the best candidates ==")
    for nm, msk in (("ER10+guard", eff & guard),
                    ("ER10-or-NEGgamma+guard", (eff | neg) & guard),
                    ("ER10-and-NEGgamma+guard", eff & neg & guard)):
        x = d[msk]; v = x.net.values; e = np.cumsum(np.sort(v))  # rough
        dd_ = (np.cumsum(x.sort_values("Date").net.values) -
               np.maximum.accumulate(np.cumsum(x.sort_values("Date").net.values))).min()
        print(f"  {nm:<26} n={len(x):4d} ({len(x)/16.5:.0f}/yr)  net ${v.sum():+,.0f} (${v.sum()/16.5:+,.0f}/yr)  "
              f"PF {pf(v)}  meanR {x.Rn.mean():+.3f}  win {100*(v>0).mean():.0f}%  maxDD ${dd_:,.0f}  net/DD {v.sum()/-dd_:.1f}")


if __name__ == "__main__":
    main()
