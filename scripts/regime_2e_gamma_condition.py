"""GAMMA-REGIME CONDITIONING — does dealer gamma (MenthorQ 19yr backfill) condition the 2E edge
better/more-stably than VIX? Mechanistic thesis: NEGATIVE-gamma days -> dealers hedge WITH the
move -> intraday trend/follow-through -> second-entry continuation works. POSITIVE-gamma ->
dealers dampen -> chop/pin -> 2E fails. Gamma is causal (computed from prior-day EOD chains,
known pre-open).

Long with-trend book, 0.30xADR, 09-13, no gap. Merge mq_regime_daily_2007_2026_v2 (net_total_gex,
regime) by date. Report edge by gamma sign/bucket, per 4-year block (block-robust = real).

Reads oos_pertrade_full_20260725.csv + C:/Users/Admin/myquant/data/regime/mq_regime_daily_2007_2026_v2.csv

  python scripts/regime_2e_gamma_condition.py
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
CSV = WT / "data" / "regime" / "oos_pertrade_full_20260725.csv"
MQ = DATA / "regime" / "mq_regime_daily_2007_2026_v2.csv"
BLOCKS = [(2010, 2013), (2014, 2017), (2018, 2021), (2022, 2026)]


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def blockrow(name, m):
    row = f"{name:<24}"; ok = True
    for (y0, y1) in BLOCKS:
        b = m[(m.yr >= y0) & (m.yr <= y1)]
        mr = b.Rn.mean() if len(b) else float('nan')
        row += f"{mr:>+8.3f}" if len(b) else f"{'-':>8}"
        if not (len(b) and mr > 0):
            ok = False
    print(row + f"   PF {pf(m.net):.2f} n={len(m)} {'ROBUST' if ok else ''}")


def main():
    d = pd.read_csv(CSV); d = d[d.with_trend & (d.dir == "L")].copy()
    d = d[d.fill_hour.astype(int).isin({9, 10, 11, 12, 13})]
    S = np.maximum(np.round(0.30 * d.adr.values / TICK) * TICK, FLOOR)
    move = np.where(d.mae_pts.values >= S, -S, d.eod_move.values)
    d["net"] = move * PT - COMM - SLIP; d["Rn"] = d.net / (S * PT)

    mq = pd.read_csv(MQ).sort_values("date").reset_index(drop=True)
    mq["date"] = mq["date"].astype(str)
    # CAUSAL: net_total_gex[D] is same-day EOD (look-ahead). Shift to PRIOR session = known at D open.
    mq["gex_causal"] = mq["net_total_gex"].shift(1)
    mq["greg_causal"] = mq["regime"].shift(1)
    mq = mq.rename(columns={"date": "Date", "regime": "gregime"})
    d = d.merge(mq[["Date", "net_total_gex", "gex_causal", "gregime", "greg_causal", "spot"]], on="Date", how="left")
    print(f"gamma coverage on long-book trades: {d.net_total_gex.notna().mean()*100:.0f}% "
          f"({d.net_total_gex.notna().sum()}/{len(d)})")
    dg = d[d.net_total_gex.notna()].copy()
    # normalize gex by spot^2 scale roughly -> use sign + within-history percentile (causal expanding)
    dg = dg.sort_values("Date")
    print("\nregime label values:", dg.gregime.value_counts().to_dict())

    print("\n========== long-2E edge by GAMMA SIGN, per 4yr block ==========")
    print(f"{'gate':<24}{'2010-13':>8}{'2014-17':>8}{'2018-21':>8}{'2022-26':>8}")
    blockrow("ALL (gamma-covered)", dg)
    blockrow("NEG gamma (gex<0)", dg[dg.net_total_gex < 0])
    blockrow("POS gamma (gex>0)", dg[dg.net_total_gex >= 0])

    print("\n========== by MQ regime label ==========")
    for r in dg.gregime.dropna().unique():
        blockrow(f"gregime={r}", dg[dg.gregime == r])

    print("\n========== NEG vs POS gamma, aggregate + by era ==========")
    for nm, sub in (("NEG gamma", dg[dg.net_total_gex < 0]), ("POS gamma", dg[dg.net_total_gex >= 0])):
        old = sub[sub.yr <= 2019]; mod = sub[sub.yr >= 2020]
        print(f"  {nm:<10} FULL meanR {sub.Rn.mean():+.3f} PF {pf(sub.net):.2f} n={len(sub):4d} | "
              f"OLD {old.Rn.mean():+.3f}/{pf(old.net)} (n{len(old)}) | MOD {mod.Rn.mean():+.3f}/{pf(mod.net)} (n{len(mod)})")

    print("\n########## CAUSALITY TEST: same-day (LEAKY) vs prior-session (CAUSAL) gamma ##########")
    dc = d[d.gex_causal.notna()].copy()
    print(f"{'gate':<28}{'2010-13':>8}{'2014-17':>8}{'2018-21':>8}{'2022-26':>8}")
    blockrow("POS same-day gex (LEAKY)", dc[dc.net_total_gex >= 0])
    blockrow("POS prior-day gex (CAUSAL)", dc[dc.gex_causal >= 0])
    blockrow("NEG prior-day gex (CAUSAL)", dc[dc.gex_causal < 0])
    pc = dc[dc.gex_causal >= 0]; nc = dc[dc.gex_causal < 0]
    print(f"\n  CAUSAL POS: meanR {pc.Rn.mean():+.3f} PF {pf(pc.net):.2f} n={len(pc)}  | "
          f"CAUSAL NEG: meanR {nc.Rn.mean():+.3f} PF {pf(nc.net):.2f} n={len(nc)}")
    # how often does the sign flip day-to-day (persistence)?
    flip = (np.sign(dc.net_total_gex) != np.sign(dc.gex_causal)).mean()
    print(f"  gamma-sign flips same-day vs prior-day on {flip*100:.1f}% of trades (persistence check)")


if __name__ == "__main__":
    main()
