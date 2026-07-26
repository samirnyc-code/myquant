"""SMA-LENGTH SWEEP for the gate — is 20 best, or is the edge robust across lengths (=not fit)?
Gate the two-sided 2E book on entry_px > SMA_N (and EMA_N) of daily closes, prior-day/causal,
for N in {10,20,30,50,100,200}. Report 2021+ (the tradeable era) and full-16yr, plus the
below-gate PF (should stay weak). Robust across lengths => real regime effect, not curve-fit.

  python scripts/regime_2e_sma_sweep.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def main():
    d = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    d = d[d.with_trend & d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    d["net"] = np.where(d.mae_pts.values >= S, -S, d.eod_move.values) * PT - COMM - SLIP

    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    dc = b.groupby("Date")["Close"].last().reset_index().sort_values("Date")
    for N in (10, 20, 30, 50, 100, 200):
        dc[f"sma{N}"] = dc["Close"].rolling(N).mean().shift(1)
        dc[f"ema{N}"] = dc["Close"].ewm(span=N, adjust=False).mean().shift(1)
    d = d.merge(dc, on="Date", how="left")

    def stats(mask, yrmin):
        x = d[mask & (d.yr >= yrmin)]
        return len(x), pf(x.net), x.net.sum()

    print(f"{'gate':<10}{'2021+ n':>8}{'PF':>6}{'net':>10}   {'16yr n':>7}{'PF':>6}{'net':>10}   {'below-gate 21+ PF':>18}")
    for kind in ("sma", "ema"):
        for N in (10, 20, 30, 50, 100, 200):
            col = f"{kind}{N}"
            dd = d.dropna(subset=[col])
            above = dd.entry_px > dd[col]
            # recompute on the non-NaN subset
            def st(sub):
                return len(sub), pf(sub.net), sub.net.sum()
            a21 = dd[above & (dd.yr >= 2021)]; a16 = dd[above]
            b21 = dd[~above & (dd.yr >= 2021)]
            print(f"{col:<10}{len(a21):>8}{pf(a21.net):>6.2f}{a21.net.sum():>+10,.0f}   "
                  f"{len(a16):>7}{pf(a16.net):>6.2f}{a16.net.sum():>+10,.0f}   {pf(b21.net):>18.2f}")
        print()


if __name__ == "__main__":
    main()
