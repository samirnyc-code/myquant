"""HVL PORTFOLIO — pair the two regime-complementary books using the HVL as the switch:
  ABOVE prior-day HVL (positive gamma) -> 2E with-trend continuation.
  BELOW prior-day HVL (negative gamma) -> RevFT reversal.
They fire in opposite gamma regimes, so combining should smooth the equity. Modern era (2021+).

Sources:
  2E:    oos_pertrade_full (with_trend, entry above prior-HVL), net 0.30xADR EOD.
  RevFT: revft_regime_full (mq==negative_gamma), net EOD hold (neod).
  (RevFT gamma tag inherited from the parallel session's build -- assumed causal, VERIFY.)

  python scripts/regime_hvl_portfolio.py
Output: docs/living/hvl_portfolio_20260725.png + tables.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def maxdd(v):
    e = np.cumsum(v); return float((e - np.maximum.accumulate(e)).min())


def main():
    # ---- 2E above HVL (positive gamma) ----
    d = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    d = d[d.fill_hour.astype(int).isin({9, 10, 11, 12, 13}) & d.with_trend].copy()
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    mv = np.where(d.mae_pts.values >= S, -S, d.eod_move.values); d["net"] = mv * PT - COMM - SLIP
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    esc = b.groupby("Date").agg(es_close=("Close", "last"))
    mq = pd.read_csv(DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv"); mq["date"] = mq["date"].astype(str)
    dd = mq[["date", "spot", "hvl"]].rename(columns={"date": "Date", "spot": "spx"}).set_index("Date").join(esc, how="inner").sort_index()
    dd["prior_hvl_es"] = (dd.hvl + (dd.es_close - dd.spx)).shift(1)
    d = d.merge(dd[["prior_hvl_es"]], left_on="Date", right_index=True, how="left")
    e2 = d[(d.prior_hvl_es.notna()) & (d.entry_px > d.prior_hvl_es) & (d.yr >= 2021)].copy()
    e2["book"] = "2E>HVL"

    # ---- RevFT below HVL (negative gamma) ----
    rv = pd.read_parquet(DATA / "regime" / "revft_regime_full_20260725.parquet")
    rv = rv[(rv.mq == "negative_gamma") & (rv.year >= 2021)].copy()
    rv["net"] = rv["neod"]; rv["book"] = "RevFT<HVL"
    rv["Date"] = rv["Date"].astype(str)

    two = e2[["Date", "net", "book"]]; rev = rv[["Date", "net", "book"]]
    for nm, x in (("2E >HVL (pos gamma)", two), ("RevFT <HVL (neg gamma)", rev)):
        v = x.net.values
        print(f"{nm:<24} n={len(v):4d}  net ${v.sum():+8,.0f}  PF {pf(v):.2f}  maxDD ${maxdd(x.sort_values('Date').net.values):+,.0f}")

    # daily PnL for each + combined
    d2 = two.groupby("Date").net.sum(); dr = rev.groupby("Date").net.sum()
    j = pd.concat([d2.rename("E2"), dr.rename("RV")], axis=1).fillna(0).sort_index()
    j["comb"] = j.E2 + j.RV
    corr = j.E2.corr(j.RV)
    print(f"\ndaily-PnL corr (2E>HVL vs RevFT<HVL) = {corr:+.3f}")
    print(f"days 2E-only {((j.E2!=0)&(j.RV==0)).sum()}  RevFT-only {((j.E2==0)&(j.RV!=0)).sum()}  both {((j.E2!=0)&(j.RV!=0)).sum()}")

    def line(nm, s):
        v = s.values; print(f"  {nm:<20} net ${v.sum():+8,.0f}  PF {pf(v):.2f}  maxDD ${maxdd(v):+,.0f}  net/DD {v.sum()/-maxdd(v):.1f}")
    print("\ncombined daily book:")
    line("2E>HVL alone", j.E2[j.E2 != 0]); line("RevFT<HVL alone", j.RV[j.RV != 0]); line("COMBINED", j.comb)

    print("\ncombined by year:")
    j["yr"] = pd.to_datetime(j.index).year
    for y in range(2021, 2027):
        yy = j[j.yr == y]
        print(f"  {y}: 2E ${yy.E2.sum():+7,.0f} (PF {pf(yy.E2[yy.E2!=0]):.2f})  RevFT ${yy.RV.sum():+7,.0f} (PF {pf(yy.RV[yy.RV!=0]):.2f})  COMB ${yy.comb.sum():+7,.0f}")

    fig, ax = plt.subplots(figsize=(13, 6), dpi=115)
    idx = np.arange(len(j))
    ax.plot(idx, j.E2.cumsum(), lw=1.4, color="#2a78d6", label=f"2E >HVL (pos gamma): {j.E2.sum():+,.0f}")
    ax.plot(idx, j.RV.cumsum(), lw=1.4, color="#e08a1e", label=f"RevFT <HVL (neg gamma): {j.RV.sum():+,.0f}")
    ax.plot(idx, j.comb.cumsum(), lw=2.2, color="#111", label=f"COMBINED: {j.comb.sum():+,.0f}  (corr {corr:+.2f})")
    ax.axhline(0, color="#8b8f96", lw=0.8); ax.grid(axis="y", color="#eceeed", lw=0.7); ax.legend(frameon=False)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title("HVL regime-switch portfolio: 2E above HVL + RevFT below HVL (2021-2026)", fontweight="bold")
    fig.tight_layout(); p = WT / "docs" / "living" / "hvl_portfolio_20260725.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
