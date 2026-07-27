"""SHORT-GATE test (Samir, 2026-07-27): the book gates BOTH 2EL and 2ES on entry > SMA20
(positive gamma). Should 2ES instead be gated BELOW SMA20 (short in negative gamma)? This
splits the with-trend book by side x SMA20-side and compares book variants. Causal SMA20,
0.30xADR stop, 09-13, EOD. NOTHING changed in the live book.

  python scripts/regime_2e_short_gate.py
Output: stdout table + data/regime/short_gate_compare_YYYYMMDD.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum(); return round(gp / gl, 2) if gl else 0.0


def row(name, x, yrs):
    v = x.net.values
    if not len(v):
        print(f"  {name:<26} (none)"); return
    print(f"  {name:<26} n={len(v):4d}  PF {pf(v):4.2f}  net ${v.sum():+8,.0f}  (${v.sum()/yrs:+7,.0f}/yr)  win {100*(v>0).mean():3.0f}%")


def main():
    d = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
    d = d[d.with_trend & d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})].copy()
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    d["net"] = np.where(d.mae_pts.values >= S, -S, d.eod_move.values) * PT - COMM - SLIP

    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["Date"] = pd.to_datetime(b["DateTime"]).dt.date.astype(str)
    g = b.groupby("Date").agg(C=("Close", "last"), H=("High", "max"), L=("Low", "min")).reset_index().sort_values("Date")
    g["sma20"] = g.C.rolling(20).mean().shift(1)
    g["adr10"] = (g.H - g.L).rolling(10).mean().shift(1)
    g["rng"] = g.H - g.L
    g["skip_after"] = (g["rng"] > 1.6 * g["adr10"]).shift(1).fillna(False)
    d = d.merge(g[["Date", "sma20", "skip_after"]], on="Date", how="left").dropna(subset=["sma20"])
    d["above"] = d.entry_px > d.sma20
    L = d.dir == "L"; Sh = d.dir == "S"; td = ~d.skip_after

    for lbl, ymin in (("2021+", 2021), ("16yr", 2010)):
        yrs = 5.5 if ymin == 2021 else 16.5
        dd = d[d.yr >= ymin]
        print(f"\n===== {lbl} =====")
        print("--- by side x SMA20-side (with-trend, no skip-TD) ---")
        row("2EL above SMA20", dd[L & dd.above], yrs)
        row("2EL below SMA20", dd[L & ~dd.above], yrs)
        row("2ES above SMA20", dd[Sh & dd.above], yrs)
        row("2ES below SMA20", dd[Sh & ~dd.above], yrs)
        print("--- book variants (+ skip-after-trend-day) ---")
        cur = dd[td & ((L & dd.above) | (Sh & dd.above))]
        alt = dd[td & ((L & dd.above) | (Sh & ~dd.above))]
        lo = dd[td & (L & dd.above)]
        both = dd[td & ((L & dd.above) | Sh)]
        row("CURRENT  L>sma & S>sma", cur, yrs)
        row("ALT      L>sma & S<sma", alt, yrs)
        row("longs-only L>sma", lo, yrs)
        row("S ungated (any side)", both, yrs)

    d.to_csv(WT / "data" / "regime" / "short_gate_compare_20260727.csv", index=False)
    print("\nsaved data/regime/short_gate_compare_20260727.csv")


if __name__ == "__main__":
    main()
