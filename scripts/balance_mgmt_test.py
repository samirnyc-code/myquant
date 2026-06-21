"""balance_mgmt_test.py — targets & BE-ratchet: balance vs non-balance.

ER>=0.30, single-leg. Four configs, split by balance state:
  base    target 1.0R, no ratchet            (reference)
  notgt   target 100R  (never hits)          -> UNCENSORED MFE: how far do they run?
  rb05    target 1.0R + stop->BE after +0.5R
  rb075   target 1.0R + stop->BE after +0.75R
Answers: (1) do balance trades run further -> bigger target? (uncensored MFE)
         (2) do balance trades come back to E1 less -> can we ratchet to BE cheaply?
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np, pandas as pd

_ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(_ROOT))
import massive, regime_filter as rf                                  # noqa: E402
from simulation_engine import simulate_trades                       # noqa: E402
from scripts.regime_overlay_phaseB import (BASE, CHOP_MIN, tag_states,  # noqa: E402
                                           _SIGNALS, _BARS, _SESS)


def grp(f, m, col="NetPnL"):
    g = f[m]; pnl = g[col].to_numpy()
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    return dict(n=len(g), exp=pnl.mean(), win=(pnl > 0).mean()*100,
                pf=(gw/gl if gl else float("inf")))


def main():
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    sess = pd.read_parquet(_SESS)
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    tagged, _ = rf.tag_and_bucket(sig, bars)
    er = tagged["ER_intra_6"].astype(float).fillna(0)
    sigf = sig[er >= CHOP_MIN].reset_index(drop=True).copy()
    st = tag_states(sigf, bars, sess)
    sigf = pd.concat([sigf, st], axis=1)
    sigf["bal"] = (sigf["open_loc"] == "inside") & (sigf["disc"] == "rotation")
    tk = {d: massive.load_continuous_ticks(d) for d in sorted(sigf["Date"].unique())}
    tk = {d: t for d, t in tk.items() if not t.empty}

    def run(**ov):
        p = {**BASE, **ov}
        r = simulate_trades(signals=sigf, ticks_by_date=tk, bars_by_date=bbd, **p)
        r = r[r["Filled"] == True].copy()
        r["bal"] = sigf.loc[r.index, "bal"].values
        return r

    base  = run()
    notgt = run(target_r=100.0)
    rb05  = run(ratchet_r=0.5, ratchet_dest="BE")
    rb075 = run(ratchet_r=0.75, ratchet_dest="BE")

    print("\n=== UNCENSORED MFE (target removed) — how far trades actually run ===")
    print(f"{'grp':<12}{'n':>5}{'MFE med':>9}{'p75':>7}{'p90':>7}{'%>=1.5R':>9}{'%>=2R':>8}")
    for lab, m in [("balance", notgt['bal']), ("non-balance", ~notgt['bal'])]:
        g = notgt[m]; mfe = g["MFE_R"].clip(lower=0)
        print(f"{lab:<12}{len(g):>5}{mfe.median():>9.2f}{mfe.quantile(.75):>7.2f}"
              f"{mfe.quantile(.90):>7.2f}{(mfe>=1.5).mean()*100:>8.0f}%{(mfe>=2).mean()*100:>7.0f}%")

    print("\n=== TARGET / RATCHET configs (net exp, win%, PF) — side by side ===")
    print(f"{'config':<10}{'balance exp/win/PF':>26}   {'non-bal exp/win/PF':>26}")
    for lab, r in [("base 1R", base), ("ratchet.5", rb05), ("ratchet.75", rb075)]:
        b = grp(r, r['bal']); nb = grp(r, ~r['bal'])
        print(f"{lab:<10}  ${b['exp']:>5.0f} / {b['win']:>3.0f}% / {b['pf']:.2f}"
              f"      ${nb['exp']:>5.0f} / {nb['win']:>3.0f}% / {nb['pf']:.2f}")

    # came-back-to-E1 proxy: with ratchet .5, BE-stopped = gross ~0 among trades that
    # reached +0.5R. Compare the BE-stop rate balance vs non-balance.
    print("\n=== 'came back to E1 after +0.5R' (BE-stop rate under ratchet .5) ===")
    reached = base["MFE_R"] >= 0.5
    for lab, m in [("balance", rb05['bal']), ("non-balance", ~rb05['bal'])]:
        sub = rb05[m & reached.reindex(rb05.index).fillna(False)]
        be = (sub["GrossPnLPts"].abs() < 0.13)   # ~half-tick of entry = BE stop
        denom = len(sub)
        print(f"{lab:<12} reached+0.5R n={denom:>4}   BE-stopped {be.sum():>4} ({be.mean()*100:>3.0f}%)")


if __name__ == "__main__":
    main()
