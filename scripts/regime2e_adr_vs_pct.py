"""Is the 2E edge driven by POINT-range (price-level, will persist at 8000) or by
%-volatility (regime, can collapse)? Tests Samir's claim directly.

Key facts the test separates:
  - $ P&L and ADR-in-points scale MECHANICALLY with price level (P&L = pts x $50;
    at 8000 a 1% day is ~80pt vs ~18pt at 1800). So dollar figures WILL stay large.
  - PF and win rate are SCALE-INVARIANT ratios: multiplying every trade's points
    by a constant does NOT change PF. So if 2013-17 PF was < 1 because of low
    %-vol (not low price), higher price alone will NOT fix it.
  - BUT entry/stop mechanics are FIXED in ticks (6t retest, 8t stop floor) = a
    fixed POINT amount. At low price that's a larger %-move, so the mechanics are
    relatively coarser when price is low -> a genuine price-level interaction.

Per year: ADR points, ADR as % of price, mean price, PF, expectancy. Then
correlate yearly PF (scale-invariant) against ADR% vs ADR-points to see which
one the EDGE (not the dollar size) actually tracks.

  python scripts/regime2e_adr_vs_pct.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COST = 17.5; FLOOR = 8 * TICK
REPO = Path(__file__).resolve().parent.parent
WT = Path(r"C:\Users\Admin\myquant-regime")


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl else float("inf")


def main():
    d = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    d = d[d.with_trend & d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    d["pnl"] = np.where(d.mae_pts.values >= S, -S, d.eod_move.values) * PT - COST

    b = pd.read_parquet(REPO / "data" / "bars" / "_db_es_5m_rth.parquet")
    b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    g = b.groupby("Date").agg(C=("Close", "last"), H=("High", "max"), L=("Low", "min")).reset_index().sort_values("Date")
    g["rng"] = g.H - g.L
    g["sma20"] = g.C.rolling(20).mean().shift(1)
    g["adr10"] = g.rng.rolling(10).mean().shift(1)
    g["skip_after"] = ((g.H - g.L) > 1.6 * g["adr10"]).shift(1).fillna(False).astype(bool)
    d = d.merge(g[["Date", "sma20", "skip_after"]], on="Date", how="left").dropna(subset=["sma20"])
    book = d[(d.entry_px > d.sma20) & (~d.skip_after)].copy()

    g["yr"] = pd.to_datetime(g.Date).dt.year
    g["adr_pct"] = g.rng / g.C * 100
    ctx = g.groupby("yr").agg(price=("C", "mean"), adr_pt=("rng", "mean"), adr_pct=("adr_pct", "mean"))

    rows = []
    for y, x in book.groupby("yr"):
        v = x.pnl.values
        rows.append(dict(yr=int(y), n=len(v), net=v.sum(), pf=pf(v), exp=v.mean(),
                         price=ctx.loc[y, "price"], adr_pt=ctx.loc[y, "adr_pt"],
                         adr_pct=ctx.loc[y, "adr_pct"]))
    r = pd.DataFrame(rows)

    print(f"{'yr':>4} {'price':>6} {'ADRpt':>6} {'ADR%':>5} | {'n':>4} {'net$':>8} {'PF':>5} {'exp$':>6}")
    for _, x in r.iterrows():
        print(f"{int(x.yr):>4} {x.price:>6.0f} {x.adr_pt:>6.1f} {x.adr_pct:>5.2f} | "
              f"{int(x.n):>4} {x.net:>+8,.0f} {x.pf:>5.2f} {x.exp:>+6.0f}")

    print("\n-- which does the SCALE-INVARIANT edge (PF) track? --")
    print(f"corr(yearly PF, ADR%)     = {r.pf.corr(r.adr_pct):+.2f}")
    print(f"corr(yearly PF, ADRpt)    = {r.pf.corr(r.adr_pt):+.2f}")
    print(f"corr(yearly PF, price)    = {r.pf.corr(r.price):+.2f}")
    print(f"corr(ADRpt, price)        = {r.adr_pt.corr(r.price):+.2f}   (are point-range & price confounded?)")
    print(f"corr(ADR%, price)         = {r.adr_pct.corr(r.price):+.2f}")
    lo = r[r.yr.between(2013, 2017)]; hi = r[r.yr >= 2021]
    print(f"\n2013-17: price {lo.price.mean():.0f}  ADR {lo.adr_pt.mean():.1f}pt / {lo.adr_pct.mean():.2f}%  PF {lo.pf.mean():.2f}")
    print(f"2021-26: price {hi.price.mean():.0f}  ADR {hi.adr_pt.mean():.1f}pt / {hi.adr_pct.mean():.2f}%  PF {hi.pf.mean():.2f}")
    print("\nread: if PF tracks ADR% (not ADRpt/price), the edge is a %-VOL effect and")
    print("high price alone won't sustain it. If PF tracks price/ADRpt, Samir is right.")


if __name__ == "__main__":
    main()
