"""Comparison metrics for the 2E x regime-tracker study.

Evaluates every arm on ONE universe with identical metrics + fill model, per period,
with a train/test split. Reproduces the committed phase-machine book as a validation
baseline (must land near PF 1.39 / +$82.7k / ~630 tr for 2021+).

  python scripts/regime2e_tracker_metrics.py
Reads:  data/regime/tracker_2e_<stamp>.csv, data/regime/tracker_choch_<stamp>.csv,
        data/bars/_db_es_5m_rth.parquet  (daily SMA20 / gap / skip-after-trend gates)
"""
from pathlib import Path
import numpy as np, pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
DATA = Path(r"C:/Users/Admin/myquant/data")
STAMP = "20260924"


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl else float('inf')


def mdd(x):
    e = x.sort_values("Date").net.cumsum().values
    return float((e - np.maximum.accumulate(e)).min()) if len(e) else 0.0


def daily_sharpe(x):
    daily = x.groupby("Date").net.sum()
    return daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else 0.0


def row(name, x, yrs):
    v = x.net.values
    if not len(v):
        return dict(setup=name, n=0)
    w = v[v > 0]; l = v[v < 0]
    return dict(setup=name, n=len(v), net=v.sum(), per_yr=v.sum() / yrs, pf=pf(v),
                win=100 * (v > 0).mean(), payoff=(abs(w.mean() / l.mean()) if len(l) and len(w) else np.nan),
                expect=v.mean(), mdd=mdd(x), sharpe=daily_sharpe(x), tpy=len(v) / yrs)


def daily_gates():
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet")
    b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    g = b.groupby("Date").agg(O=("Open", "first"), C=("Close", "last"),
                              H=("High", "max"), L=("Low", "min")).reset_index().sort_values("Date")
    g["sma20"] = g.C.rolling(20).mean().shift(1)
    g["adr10"] = (g.H - g.L).rolling(10).mean().shift(1)
    g["skip_after"] = ((g.H - g.L) > 1.6 * g["adr10"]).shift(1).fillna(False).astype(bool)
    g["gap"] = ((g.O - g.C.shift(1)) / g.C.shift(1) * 100).abs()
    return g[["Date", "sma20", "skip_after", "gap"]]


def fmt(rows, title):
    print(f"\n### {title}")
    hdr = f"{'setup':<34}{'n':>5}{'net$':>10}{'$/yr':>9}{'PF':>6}{'win%':>6}{'pay':>6}{'exp$':>7}{'maxDD$':>9}{'Shrp':>6}{'t/yr':>6}"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        if not r.get("n"):
            print(f"{r['setup']:<34}{0:>5}   (no trades)"); continue
        print(f"{r['setup']:<34}{r['n']:>5}{r['net']:>10,.0f}{r['per_yr']:>9,.0f}{r['pf']:>6.2f}"
              f"{r['win']:>6.1f}{r['payoff']:>6.2f}{r['expect']:>7.0f}{r['mdd']:>9,.0f}{r['sharpe']:>6.2f}{r['tpy']:>6.1f}")


def side_split(x, la, lb, ka, kb):
    def one(s):
        return f"{s} n={len(s):d} PF {pf(s.net):.2f} ${s.net.sum():+,.0f}" if len(s) else f"{s} n=0"
    a = x[x.dir == ka]; b = x[x.dir == kb]
    return f"    {la} n={len(a)} PF {pf(a.net):.2f} ${a.net.sum():+,.0f}   {lb} n={len(b)} PF {pf(b.net):.2f} ${b.net.sum():+,.0f}"


def main():
    gates = daily_gates()
    d = pd.read_csv(DATA / "regime" / f"tracker_2e_{STAMP}.csv").merge(gates, on="Date", how="left")
    c = pd.read_csv(DATA / "regime" / f"tracker_choch_{STAMP}.csv").merge(gates[["Date", "gap"]], on="Date", how="left")
    d["h"] = d.fill_hour.astype(int)
    hr = d.h.isin({9, 10, 11, 12, 13})
    aboveS = d.entry_px > d.sma20
    noskip = ~d.skip_after

    # ---- 2E arms (each a boolean mask on d) ----
    arms2e = {
        "raw 2E (all, no gate)":                     hr,
        "committed: PM-WT + SMA20 + skip [BASE]":     hr & d.with_trend_pm & aboveS & noskip,
        "tracker-WT (Bull->L / Bear->S)":             hr & d.with_trend_trk,
        "tracker-WT + SMA20 + skip":                  hr & d.with_trend_trk & aboveS & noskip,
        "tracker-WT & PM-WT (both agree)":            hr & d.with_trend_trk & d.with_trend_pm,
        "tracker-WT + SMA20 (no skip filter)":        hr & d.with_trend_trk & aboveS,
        "tracker-WT, fresh trend (age<=6)":           hr & d.with_trend_trk & (d.trend_age <= 6),
        "tracker Range-only (either side)":           hr & (d.regime_trk == "Range"),
    }
    for era, ymin, yrs in (("2021+ (tradeable era)", 2021, 5.5), ("full 16yr", 2010, 16.5)):
        rows = [row(name, d[m & (d.yr >= ymin)], yrs) for name, m in arms2e.items()]
        fmt(rows, f"2E FAMILY — {era}")

    # side splits + train/test for the two headline tracker arms
    print("\n### 2E side split + train/test (2021+ era)")
    for name, m in (("committed [BASE]", d.with_trend_pm & aboveS & noskip & hr),
                    ("tracker-WT+SMA20+skip", d.with_trend_trk & aboveS & noskip & hr)):
        x = d[m & (d.yr >= 2021)]
        print(f"  {name}:")
        print(side_split(x, "2EL", "2ES", "L", "S"))
        tr = x[x.yr <= 2023]; te = x[x.yr >= 2024]
        print(f"    train'21-23 n={len(tr)} PF {pf(tr.net):.2f} ${tr.net.sum():+,.0f}   test'24-26 n={len(te)} PF {pf(te.net):.2f} ${te.net.sum():+,.0f}")

    # ---- ChoCh arms ----
    c["h"] = c.fill_hour.astype(int); chr_ = c.h.isin({9, 10, 11, 12, 13})
    armsC = {
        "FADE first ChoCh of day":         chr_ & (c["mode"] == "fade") & c.is_first_of_day,
        "FADE any ChoCh (first-of-trend)":  chr_ & (c["mode"] == "fade"),
        "WITH first ChoCh of day":          chr_ & (c["mode"] == "with") & c.is_first_of_day,
        "WITH any ChoCh":                   chr_ & (c["mode"] == "with"),
        "FADE first ChoCh, gap<=0.54":      chr_ & (c["mode"] == "fade") & c.is_first_of_day & (c.gap <= 0.54),
    }
    for era, ymin, yrs in (("2021+ (tradeable era)", 2021, 5.5), ("full 16yr", 2010, 16.5)):
        rows = [row(name, c[m & (c.yr >= ymin)], yrs) for name, m in armsC.items()]
        fmt(rows, f"ChoCh FAMILY — {era}")

    print("\n### ChoCh train/test (2021+): FADE first ChoCh of day")
    x = c[(c["mode"] == "fade") & c.is_first_of_day & c.h.isin({9, 10, 11, 12, 13}) & (c.yr >= 2021)]
    tr = x[x.yr <= 2023]; te = x[x.yr >= 2024]
    print(f"    train'21-23 n={len(tr)} PF {pf(tr.net):.2f} ${tr.net.sum():+,.0f}   test'24-26 n={len(te)} PF {pf(te.net):.2f} ${te.net.sum():+,.0f}")


if __name__ == "__main__":
    main()
