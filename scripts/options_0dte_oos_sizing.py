"""options_0dte_oos_sizing.py — OOS test + down-gap variant + account sizing + minis.

Answers the follow-ups on the open-anchored, up-gap-filtered 0DTE book:
  1. TRUE OOS — pick the gap threshold on IS (2023-2024) by Sharpe, LOCK it, apply
     untouched to OOS (2025-2026). The honest test of whether the edge is real.
  2. down-gaps-only vs skip-up-gaps — trade count / per-trade / total / Sharpe trade-off.
  3. account size + max drawdown (dollars) for 1-contract trading.
  4. mini options (XSP, 1/10 SPX): the fixed per-contract commission vs 1/10 premium.
  5. fees: $1.30/leg already in pnl (this script works from net pnl and adds back to gross).

Run: .venv/Scripts/python.exe scripts/options_0dte_oos_sizing.py
Out: console + data/options_0dte/oos_sizing.txt
"""
from __future__ import annotations
from pathlib import Path
import io
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "options_0dte"
COMM_LEG = 1.30
LEGS = {"ic": 4, "bps": 2, "bcs": 2, "ifly": 4}
OUT = io.StringIO()


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s); OUT.write(s + "\n")


def metrics(x):
    x = np.asarray(x, float)
    if len(x) == 0:
        return dict(n=0, mean=np.nan, total=np.nan, sharpe=np.nan, pf=np.nan, maxdd=np.nan, win=np.nan)
    cum = np.cumsum(x); dd = (np.maximum.accumulate(cum) - cum).max()
    w = x[x > 0].sum(); l = -x[x < 0].sum()
    return dict(n=len(x), mean=round(x.mean(), 1), total=round(x.sum(), 0),
                sharpe=round(x.mean() / x.std() * np.sqrt(252), 2) if x.std() else 0,
                pf=round(w / l, 2) if l else np.inf, maxdd=round(dd, 0),
                win=round((x > 0).mean() * 100, 1))


def main():
    t = pd.read_csv(D / "trades_all.csv", parse_dates=["date"])
    t["yr"] = t.date.dt.year
    o = t[t.anchor == "open"].copy()

    # ---------- 1. TRUE OOS ----------
    p("=" * 70)
    p("1. TRUE OUT-OF-SAMPLE  (threshold picked on 2023-2024, locked, applied to 2025-2026)")
    p("=" * 70)
    thr_grid = [1.0, 0.5, 0.3, 0.2, 0.1, 0.0, -0.1, -0.2]
    for strat in ["ic", "bps"]:
        s = o[o.strat == strat]
        IS = s[s.yr <= 2024]; OOS = s[s.yr >= 2025]
        # pick threshold maximising IS Sharpe
        best = max(thr_grid, key=lambda th: metrics(IS[IS.gap_pct <= th].pnl_mid)["sharpe"])
        mi = metrics(IS[IS.gap_pct <= best].pnl_mid)
        mo = metrics(OOS[OOS.gap_pct <= best].pnl_mid)
        moc = metrics(OOS[OOS.gap_pct <= best].pnl_cross)
        p(f"\n{strat.upper()}  locked threshold gap<= {best} (chosen on IS by Sharpe)")
        p(f"  IS  2023-24: n={mi['n']:4} mean=${mi['mean']:6} sharpe={mi['sharpe']:5} pf={mi['pf']} total=${mi['total']:.0f}")
        p(f"  OOS 2025-26: n={mo['n']:4} mean=${mo['mean']:6} sharpe={mo['sharpe']:5} pf={mo['pf']} total=${mo['total']:.0f}  <-- untouched")
        p(f"  OOS cross-fill (worst case): mean=${moc['mean']} total=${moc['total']:.0f} sharpe={moc['sharpe']}")

    # ---------- 2. down-gaps only vs skip-up ----------
    p("\n" + "=" * 70)
    p("2. VARIANT: down-gaps only vs skip-up-gaps  (open IC, full period, mid)")
    p("=" * 70)
    ic = o[o.strat == "ic"]
    for name, mask in [("all days           ", ic.gap_pct <= 99),
                       ("skip up>+0.2%       ", ic.gap_pct <= 0.2),
                       ("flat+down only <=0  ", ic.gap_pct <= 0.0),
                       ("DOWN gaps only <=-0.2", ic.gap_pct <= -0.2)]:
        m = metrics(ic[mask].pnl_mid)
        p(f"  {name}: n={m['n']:4} ({m['n']/len(ic)*100:4.0f}% of days) mean=${m['mean']:6} "
          f"total=${m['total']:7.0f} sharpe={m['sharpe']:5} maxDD=${m['maxdd']:.0f}")
    p("  -> fewer, more-selective days = higher per-trade + Sharpe, but LESS total $ and more variance.")

    # ---------- 3. account size + maxDD ----------
    p("\n" + "=" * 70)
    p("3. ACCOUNT SIZE + MAX DRAWDOWN  (open IC, skip up>+0.2%, 1 contract)")
    p("=" * 70)
    f = ic[ic.gap_pct <= 0.2]
    m = metrics(f.pnl_mid)
    avg_credit = f.credit_mid.mean()
    max_risk = (25 - avg_credit) * 100          # defined-risk margin per condor
    worst_trade = f.pnl_mid.min()
    p(f"  per-contract: avg credit ${avg_credit*100:.0f}, max risk/margin ~${max_risk:.0f}, "
      f"worst single trade ${worst_trade:.0f}")
    p(f"  equity maxDD (1 contract): ${m['maxdd']:.0f}")
    p(f"  suggested account (margin + 2x maxDD buffer): ${max_risk + 2*m['maxdd']:.0f}")
    p(f"  annual: ~{m['n']/ (f.yr.nunique()):.0f} trades/yr x ${m['mean']} = "
      f"~${m['mean']*m['n']/f.yr.nunique():.0f}/yr per contract (mid, pre-tax)")

    # ---------- 4. minis (XSP) ----------
    p("\n" + "=" * 70)
    p("4. MINI OPTIONS (XSP = 1/10 SPX): fixed commission vs 1/10 premium")
    p("=" * 70)
    p(f"  fee model: ${COMM_LEG}/contract/leg, IC = {LEGS['ic']} legs = ${COMM_LEG*LEGS['ic']:.2f}/contract.")
    gross = f.pnl_mid + COMM_LEG * LEGS["ic"]     # add back the SPX commission -> gross edge
    g_mean = gross.mean()
    p(f"  SPX  1 contract: gross ${g_mean:.1f} - fee ${COMM_LEG*LEGS['ic']:.2f} = NET ${g_mean-COMM_LEG*LEGS['ic']:.1f}/trade")
    xsp_1 = g_mean / 10 - COMM_LEG * LEGS["ic"]   # 1 XSP contract: 1/10 gross, SAME fee
    p(f"  XSP  1 contract: gross ${g_mean/10:.1f} - fee ${COMM_LEG*LEGS['ic']:.2f} = NET ${xsp_1:.1f}/trade")
    xsp_10 = g_mean - 10 * COMM_LEG * LEGS["ic"]  # 10 XSP = same exposure as 1 SPX, 10x fees
    p(f"  XSP 10 contracts (= 1 SPX notional): gross ${g_mean:.1f} - fee ${10*COMM_LEG*LEGS['ic']:.2f} = NET ${xsp_10:.1f}/trade")
    p("  -> minis carry the SAME per-contract fee on 1/10 the premium: the edge is")
    p(f"     mostly eaten. Break-even needs gross > ${COMM_LEG*LEGS['ic']:.2f}/XSP-contract "
      f"(here only ${g_mean/10:.1f}).")

    (D / "oos_sizing.txt").write_text(OUT.getvalue())
    p(f"\nsaved {D/'oos_sizing.txt'}")


if __name__ == "__main__":
    main()
