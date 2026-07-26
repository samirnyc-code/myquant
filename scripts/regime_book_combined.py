"""TEST 3 — assemble the final book: 2E-above-HVL (core) + f2EL bear fade (sleeve). RevFT
excluded (below-HVL edge is directional down-drift, not signal; see regime_book_revft drift test).
One equity path, per-year, drawdown, Monte-Carlo, correlation, sizing. Proxy, 2021+, 1 ES.

  python scripts/regime_book_combined.py
Output: docs/living/book_combined_20260725.png + tables.
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
rng = np.random.default_rng(83)


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def maxdd(v):
    e = np.cumsum(v); return float((e - np.maximum.accumulate(e)).min())


def main():
    # 2E above HVL (core)
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
    core = d[(d.prior_hvl_es.notna()) & (d.entry_px > d.prior_hvl_es) & (d.yr >= 2021)][["Date", "net"]].copy(); core["book"] = "2E>HVL"

    # f2EL bear fade (sleeve) -- BEAR-gated from the fade sweep
    fd = pd.read_csv(WT / "data" / "regime" / "fade_full_hvl_20260725.csv")
    sleeve = fd[(fd.fade == "f2EL") & (fd.reg == "BEAR")][["Date", "net"]].copy(); sleeve["book"] = "f2EL"

    allt = pd.concat([core, sleeve])
    dayp = allt.groupby(["Date", "book"]).net.sum().unstack(fill_value=0)
    for c in ("2E>HVL", "f2EL"):
        if c not in dayp: dayp[c] = 0.0
    dayp["comb"] = dayp["2E>HVL"] + dayp["f2EL"]
    dayp = dayp.sort_index(); dayp["yr"] = pd.to_datetime(dayp.index).year

    print("=== FINAL BOOK (2021+, 1 ES, proxy) ===")
    for nm, col, n in (("2E>HVL core", "2E>HVL", len(core)), ("f2EL sleeve", "f2EL", len(sleeve)), ("COMBINED", "comb", None)):
        v = dayp[col].values; vt = v[v != 0] if col != "comb" else v
        print(f"  {nm:<14} trades~{n if n else len(core)+len(sleeve)}  net ${dayp[col].sum():+8,.0f} (${dayp[col].sum()/5.5:+,.0f}/yr)  "
              f"PF {pf(vt):.2f}  maxDD ${maxdd(v):+,.0f}  net/DD {dayp[col].sum()/-maxdd(v):.1f}")
    corr = dayp["2E>HVL"].corr(dayp["f2EL"])
    print(f"  daily-PnL corr(core, sleeve) = {corr:+.3f}")
    cv = dayp["comb"].values
    mc = np.array([maxdd(rng.permutation(cv)) for _ in range(4000)])
    print(f"  COMBINED MC maxDD: median ${np.median(mc):,.0f}  worst-5% ${np.percentile(mc,5):,.0f}  worst-1% ${np.percentile(mc,1):,.0f}")
    print("\n  combined by year:")
    for y in range(2021, 2027):
        yy = dayp[dayp.yr == y]; print(f"    {y}: core ${yy['2E>HVL'].sum():+7,.0f}  sleeve ${yy['f2EL'].sum():+6,.0f}  COMB ${yy['comb'].sum():+7,.0f}")
    dd1 = -np.percentile(mc, 1)
    print(f"\n  sizing: worst-1% ${dd1:,.0f} -> ${dd1/0.33:,.0f}/ES at 33% risk tolerance; net/yr ${dayp['comb'].sum()/5.5:+,.0f}")

    fig, ax = plt.subplots(figsize=(13, 6), dpi=115); x = np.arange(len(dayp))
    ax.plot(x, dayp["2E>HVL"].cumsum(), lw=1.5, color="#2a78d6", label=f"2E>HVL core: {dayp['2E>HVL'].sum():+,.0f}")
    ax.plot(x, dayp["f2EL"].cumsum(), lw=1.3, color="#e08a1e", label=f"f2EL sleeve: {dayp['f2EL'].sum():+,.0f}")
    ax.plot(x, dayp["comb"].cumsum(), lw=2.3, color="#111", label=f"COMBINED: {dayp['comb'].sum():+,.0f} (net/DD {dayp['comb'].sum()/-maxdd(cv):.1f})")
    ax.axhline(0, color="#8b8f96", lw=0.8); ax.grid(axis="y", color="#eceeed", lw=0.7); ax.legend(frameon=False)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
    ax.set_title("Final book: HVL-gated two-sided 2E + f2EL bear fade (2021-2026, 1 ES)", fontweight="bold")
    fig.tight_layout(); p = WT / "docs" / "living" / "book_combined_20260725.png"
    fig.savefig(p, facecolor="white"); print("\nsaved", p)


if __name__ == "__main__":
    main()
