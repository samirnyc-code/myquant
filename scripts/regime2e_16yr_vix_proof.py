"""16-YEAR 2E book P&L per year vs VIX / ADR — does the edge live in high vol?

Data (already on disk):
  - oos_pertrade_full_20260725.csv : every filled 2E 2010-2026 on the Databento
    1-min pseudo-tick PROXY (NOT real ticks; real ticks only exist 2021+). Same
    emitter behind the audited book. Columns incl. mae_pts / eod_move so any stop
    can be re-derived: net(S) = -S if mae>=S else eod_move.
  - _db_es_5m_rth.parquet          : 5-min RTH bars -> SMA20_D gate, ADR10, gap,
    per-year ADR.
  - vix_daily.csv                  : per-year mean VIX close.

Book gates applied EXACTLY as regime_2e_book_metrics.py: with_trend, fill hour
09-13, entry_px > prior-day SMA20 of session closes, skip day-after-trend-day,
gap <= 0.54%. Stop = 0.30 x ADR10 (8t floor). Costs: net at $17.50/trade.

  python scripts/regime2e_16yr_vix_proof.py
Output: reports/regime2e/16yr_vix_proof.csv + stdout table.
"""
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COST = 17.5; FLOOR = 8 * TICK
REPO = Path(__file__).resolve().parent.parent
WT = Path(r"C:\Users\Admin\myquant-regime")
DATA = REPO / "data"
OUT = REPO / "reports" / "regime2e"


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl else float("inf")


def main():
    d = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    d = d[d.with_trend & d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    # stop = 0.30 x ADR10 (per-trade adr col already = prior ADR10), 8t floor
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    d["pnl"] = np.where(d.mae_pts.values >= S, -S, d.eod_move.values) * PT

    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet")
    b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    g = b.groupby("Date").agg(C=("Close", "last"), H=("High", "max"), L=("Low", "min")).reset_index().sort_values("Date")
    g["rng"] = g.H - g.L
    g["sma20"] = g.C.rolling(20).mean().shift(1)
    g["adr10"] = g.rng.rolling(10).mean().shift(1)
    g["skip_after"] = ((g.H - g.L) > 1.6 * g["adr10"]).shift(1).fillna(False).astype(bool)
    d = d.merge(g[["Date", "sma20", "skip_after"]], on="Date", how="left").dropna(subset=["sma20"])
    book = d[(d.entry_px > d.sma20) & (~d.skip_after)].copy()
    book["pnl_net"] = book.pnl - COST

    # per-year VIX + ADR context
    vix = pd.read_csv(DATA / "vix_daily.csv"); vix["yr"] = pd.to_datetime(vix.date).dt.year
    vy = vix.groupby("yr").close.mean()
    g["yr"] = pd.to_datetime(g.Date).dt.year
    ay = g.groupby("yr").rng.mean()

    rows = []
    for y, x in book.groupby("yr"):
        v = x.pnl_net.values
        rows.append(dict(yr=int(y), n=len(v), net=v.sum(), pf=pf(v),
                         win=100 * (v > 0).mean(), exp=v.mean(),
                         vix=vy.get(y, np.nan), adr=ay.get(y, np.nan)))
    r = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    r.to_csv(OUT / "16yr_vix_proof.csv", index=False)

    print("16-YEAR 2E BOOK (Databento 1-min PROXY, net $17.50/tr) vs VIX / ADR\n")
    print(f"{'yr':>4} {'n':>4} {'net$':>9} {'PF':>5} {'win%':>5} {'exp$':>6} {'VIX':>6} {'ADRpt':>6}")
    for _, x in r.iterrows():
        print(f"{int(x.yr):>4} {int(x.n):>4} {x.net:>+9,.0f} {x.pf:>5.2f} {x.win:>5.0f} "
              f"{x.exp:>+6.0f} {x.vix:>6.1f} {x.adr:>6.1f}")

    lo_tr = book[book.yr.between(2013, 2017)].pnl_net.values
    hi_tr = book[book.yr >= 2021].pnl_net.values
    lo = r[r.yr.between(2013, 2017)]; hi = r[r.yr >= 2021]
    print("\n--- ERA CONTRAST ---")
    print(f"2013-2017 (low vol): net ${lo_tr.sum():+,.0f} over {len(lo_tr)} tr, "
          f"exp ${lo_tr.mean():+.0f}/tr, PF {pf(lo_tr):.2f}, "
          f"mean VIX {lo.vix.mean():.1f}, mean ADR {lo.adr.mean():.1f}pt")
    print(f"2021-2026 (high vol): net ${hi_tr.sum():+,.0f} over {len(hi_tr)} tr, "
          f"exp ${hi_tr.mean():+.0f}/tr, PF {pf(hi_tr):.2f}, "
          f"mean VIX {hi.vix.mean():.1f}, mean ADR {hi.adr.mean():.1f}pt")
    # correlation across years: yearly expectancy vs VIX and vs ADR
    print(f"\ncorr(yearly exp$/tr, VIX) = {r.exp.corr(r.vix):+.2f}   "
          f"corr(yearly exp$/tr, ADR) = {r.exp.corr(r.adr):+.2f}   (n={len(r)} years)")
    print(f"\nfull 16yr: net ${r.net.sum():+,.0f}  n={int(r.n.sum())}  PF {pf(book.pnl_net.values):.2f}  "
          f"exp ${book.pnl_net.mean():+.0f}/tr")
    print(f"csv: {OUT / '16yr_vix_proof.csv'}")


if __name__ == "__main__":
    main()
