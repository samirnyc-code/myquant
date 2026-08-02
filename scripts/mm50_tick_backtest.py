#!/usr/bin/env python
"""mm50_tick_backtest.py — S92-EA: the DEFINITIVE test. Re-score every 50% MM signal on the
actual TICK TAPE (not 15M OHLC), full sample, all swing settings. Answers whether any edge
survives tick reality after the June N=1 audit showed the 15M engine over-counts targets.

Per signal: from leg-confirmation time, replay ticks -> did the 50% limit fill before the
61.8% broke? then first-touch stop vs 123% target, exact order. Reports tick-accurate
win/expectancy/PF/per-year for each N, side by side with the (optimistic) 15M numbers.

Usage: python scripts/mm50_tick_backtest.py
"""
from __future__ import annotations

from pathlib import Path
import glob as _glob
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MASTER_DIR = ROOT / "data" / "nt_internals" / "master"
TICKS = ROOT / "data" / "ticks_continuous"
sys.path.insert(0, str(ROOT / "scripts"))
from halsey_mm50_engine import build_15m  # noqa: E402
from mm50_tick_verify import tick_outcome  # noqa: E402


def st(R, label):
    R = np.asarray(R, float)
    R = R[~np.isnan(R)]
    if not len(R):
        return f"{label}: n=0"
    w = R[R > 0].sum(); l = -R[R < 0].sum()
    pf = w / l if l else np.inf
    return (f"{label}: n={len(R):5d}  win={100*(R>0).mean():4.1f}%  exp={R.mean():+.3f}R  "
            f"PF={pf:4.2f}")


def main():
    g = build_15m(); dt = g["dt"]
    tr = pd.read_csv(sorted(_glob.glob(str(MASTER_DIR / "mm50_trades_*.csv")))[-1])
    tr["conf_t"] = dt.iloc[tr["conf"].astype(int).values].values
    tr["cday"] = pd.to_datetime(tr["conf_t"]).dt.date
    tr["year"] = pd.to_datetime(tr["conf_t"]).dt.year

    tick_R = np.full(len(tr), np.nan)
    tick_why = np.array(["?"] * len(tr), dtype=object)
    days = sorted(tr["cday"].unique())
    print(f"replaying {len(tr):,} signals over {len(days)} trading days on the tick tape...")
    for di, day in enumerate(days):
        fp = TICKS / f"{day.isoformat()}.parquet"
        if not fp.exists():
            continue
        tk = pd.read_parquet(fp)
        px = tk["Price"].to_numpy(); ts = tk["DateTime"].to_numpy()
        sub = tr[tr["cday"] == day]
        for i, t in sub.iterrows():
            why, R, ft, xt = tick_outcome(px, ts, pd.Timestamp(t["conf_t"]), int(t["side"]),
                                          t["e50"], t["stop"], t["tgt"])
            tick_why[i] = why if why is not None else "no_fill"
            tick_R[i] = R if R is not None else 0.0   # no-fill = trade not taken
        if (di + 1) % 200 == 0:
            print(f"  ...{di+1}/{len(days)} days")
    tr["tick_R"] = tick_R; tr["tick_why"] = tick_why

    # net-of-costs: 1-tick slippage on stop exits (worse) + $5 RT commission, expressed in R
    COMM = 5.0; SLIP_TK = 1.0; ES_PT = 50.0
    risk_dollar = tr["risk_pts"] * ES_PT
    slip_R = (SLIP_TK * 0.25 * ES_PT) / risk_dollar         # 1 tick as a fraction of risk
    comm_R = COMM / risk_dollar
    tr["net_R"] = tr["tick_R"] - comm_R
    tr.loc[tr["tick_why"] == "stop", "net_R"] -= slip_R[tr["tick_why"] == "stop"]

    miss = tr["tick_R"].isna().sum()
    print(f"\n(missing tick file for {miss} of {len(tr)} signals — excluded from tick stats)")
    print("=== 15M (optimistic) vs TICK-ACCURATE vs NET (comm $5 + 1tk stop slip) ===")
    for N in sorted(tr["N"].unique()):
        d = tr[tr["N"] == N].dropna(subset=["tick_R"])
        yr15 = d.groupby("year")["R"].mean(); yrtk = d.groupby("year")["tick_R"].mean()
        yrnet = d.groupby("year")["net_R"].mean()
        print(f"\nN={N}:")
        print(f"  {st(d['R'], '15M ')}   years+={(yr15>0).sum()}/{len(yr15)}")
        print(f"  {st(d['tick_R'], 'TICK')}   years+={(yrtk>0).sum()}/{len(yrtk)}   "
              f"| target-flips: {((d['why']=='target') & (d['tick_why']!='target')).sum()}"
              f" of {(d['why']=='target').sum()} 15M targets")
        print(f"  {st(d['net_R'], 'NET ')}   years+={(yrnet>0).sum()}/{len(yrnet)}   "
              f"| median risk {d['risk_pts'].median()*4:.0f}tk (${d['risk_pts'].median()*ES_PT:.0f})")

    out = MASTER_DIR / "mm50_tickaccurate.csv"
    tr.to_csv(out, index=False)
    print(f"\nwrote {out.relative_to(ROOT)}")
    print("\nVERDICT basis: compare TICK exp/PF to 15M. If TICK collapses to <=0, the 50% MM as "
          "modeled is NOT tradeable — the 15M target counts were phantom (intrabar path).")


if __name__ == "__main__":
    main()
