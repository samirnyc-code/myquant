"""options_0dte_struct.py — Cycle 3: structural sweep of strike distance x wing width.

Is fixed 25pt / 1-EM optimal? Sweeps short-strike distance {0.75,1.0,1.25 x EM} and
wing width {10,25,50pt} for IC & BPS, open-anchored, skip up-gaps>+0.2%, hold-to-expiry.
Reports mid AND worst-case cross, Sharpe, maxDD, and year-by-year — fast (entry+settle,
no intraday path). Fills: sell short @ bid (cross) / mid; buy long @ ask (cross) / mid.

Out: data/options_0dte/struct_sweep.csv + console
Run: .venv/Scripts/python.exe scripts/options_0dte_struct.py
"""
from __future__ import annotations
import glob
import math
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PARSED = ROOT / "data" / "databento" / "0dte_parsed"
SPX = ROOT / "data" / "spx_daily_ohlc.csv"
VIX = ROOT / "data" / "vix_daily_full.csv"
OUT = ROOT / "data" / "options_0dte"
SQRT252 = math.sqrt(252)
COMM_LEG = 1.30
MULT = 100
DISTS = [0.75, 1.0, 1.25]          # short strike = center +/- dist*EM
WIDTHS = [10, 25, 50]
GAP_MAX = 0.2                      # skip up-gaps > +0.2%


def load_daily():
    spx = pd.read_csv(SPX, parse_dates=["Date"]).set_index("Date")
    vix = pd.read_csv(VIX, parse_dates=["Date"]).set_index("Date")["vix"]
    d = spx.join(vix, how="inner")
    d["prior_close"] = d["Close"].shift(1); d["prior_vix"] = d["vix"].shift(1)
    return d


def metrics(df, col):
    x = df[col].to_numpy(float)
    if len(x) == 0:
        return {}
    c = np.cumsum(np.sort(x)[::-1] * 0 + x)  # keep order below instead
    return {}


def summ(g):
    x = g["pnl_mid"].to_numpy(float)
    cx = g["pnl_cross"].to_numpy(float)
    def sh(a): return round(a.mean()/a.std()*np.sqrt(252), 2) if a.std() else 0
    cum = np.cumsum(x); dd = (np.maximum.accumulate(cum)-cum).max()
    yr = g.groupby("yr")["pnl_mid"].mean().round(0).astype(int).to_dict()
    return dict(n=len(x), mid=round(x.mean(), 1), cross=round(cx.mean(), 1),
                sharpe_mid=sh(x), sharpe_cross=sh(cx), maxdd=round(dd, 0),
                yrs=str({int(k): v for k, v in yr.items()}))


def main():
    daily = load_daily()
    files = sorted(glob.glob(str(PARSED / "*.parquet")))
    rows = []
    for f in files:
        date = pd.Timestamp(Path(f).stem)
        if date not in daily.index:
            continue
        r = daily.loc[date]; pc, pv, op, cl = r["prior_close"], r["prior_vix"], r["Open"], r["Close"]
        if any(pd.isna(x) for x in (pc, pv, op, cl)):
            continue
        gap = (op - pc)/pc*100
        if gap > GAP_MAX:                      # skip up-gaps
            continue
        day = pd.read_parquet(f)
        day["ts"] = pd.to_datetime(day["ts"], utc=True)
        et = pd.Timestamp(f"{date.date()} 09:30", tz="America/New_York").tz_convert("UTC")
        sub = day[day["ts"] >= et]
        if sub.empty:
            continue
        snapq = day[day["ts"] == sub["ts"].iloc[0]]
        q = {(r2.strike, r2.right): (r2.bid, r2.ask) for r2 in snapq.itertuples()}
        strikes = sorted({k for k, _ in q})
        if len(strikes) < 10:
            continue
        em = pc*(pv/100)/SQRT252
        snap = lambda t: min(strikes, key=lambda s: abs(s-t))

        def spread(right, ks, kl):
            s = q.get((ks, right)); l = q.get((kl, right))
            if not s or not l:
                return None
            bs, as_, bl, al = s[0], s[1], l[0], l[1]
            if any(v != v for v in (bs, as_, bl, al)) or bs <= 0:
                return None
            return (bs-al, (bs+as_)/2-(bl+al)/2)     # cross, mid
        def loss(right, ks, w):
            return min(max((ks-cl) if right == "P" else (cl-ks), 0.0), w)

        for dist in DISTS:
            for w in WIDTHS:
                lo = snap(op - dist*em); hi = snap(op + dist*em)
                for strat, legs in {"bps": [("P", lo)], "ic": [("P", lo), ("C", hi)]}.items():
                    cr_c = cr_m = 0.0; ok = True; ls = 0.0
                    for right, ks in legs:
                        kl = snap(ks - w) if right == "P" else snap(ks + w)
                        sp = spread(right, ks, kl)
                        if sp is None:
                            ok = False; break
                        cr_c += sp[0]; cr_m += sp[1]; ls += loss(right, ks, w)
                    if not ok or cr_m <= 0:
                        continue
                    comm = COMM_LEG*2*len(legs)/MULT
                    rows.append({"date": str(date.date()), "yr": date.year, "strat": strat,
                                 "dist": dist, "width": w,
                                 "pnl_mid": (cr_m-ls-comm)*MULT, "pnl_cross": (cr_c-ls-comm)*MULT})
    df = pd.DataFrame(rows)
    df.to_parquet(OUT / "struct_trades.parquet", compression="zstd")
    res = []
    for (strat, dist, w), g in df.groupby(["strat", "dist", "width"]):
        res.append({"strat": strat, "dist": dist, "width": w, **summ(g)})
    R = pd.DataFrame(res)
    R.to_csv(OUT / "struct_sweep.csv", index=False)
    for s in ["ic", "bps"]:
        print(f"\n===== {s.upper()} structural sweep (skip up-gaps, hold-to-expiry) =====")
        sub = R[R.strat == s].sort_values("sharpe_cross", ascending=False)
        print(sub[["dist", "width", "n", "mid", "cross", "sharpe_mid", "sharpe_cross", "maxdd", "yrs"]].to_string(index=False))
    print(f"\nsaved {OUT/'struct_sweep.csv'}")


if __name__ == "__main__":
    main()
