"""xsp_fee_model.py — what XSP fees look like as you trade a few minis (1..N per leg),
and the catch: per unit of EXPOSURE, XSP is far more expensive than SPX because you need
10x the contracts. Published-schedule estimate; confirm exact via check_fees_ib.py (whatIf).

Model (per contract, 1-lot combo so the $1.00 order minimum doesn't bite):
  IB base commission  ~$0.65   (fixed tier; tiered can be lower + passthrough)
  Cboe XSP index fee   $0.00 for 1-9 contracts/leg, $0.07 for >=10/leg
  regulatory (ORF/OCC) ~$0.05
  SPX per contract    ~$1.30   (IB $0.65 + full Cboe SPX index fee + regulatory)

    python scripts/xsp_fee_model.py [--spx-gross 75]
"""
from __future__ import annotations
import argparse

IB = 0.65
REG = 0.05
SPX_CT = 1.30            # SPX all-in per contract (desk model / schedule)
XSP_IDX = lambda n: 0.00 if n <= 9 else 0.07   # per-leg Cboe XSP index fee


def xsp_ct(n_per_leg):
    return IB + XSP_IDX(n_per_leg) + REG


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spx-gross", type=float, default=75.0,
                    help="avg SPX gross P&L per spread ($), to show the fee % drag")
    a = ap.parse_args()
    print("XSP fee as you trade N minis per leg  (2-leg spread; published-schedule estimate)")
    print(f"{'N/leg':>6} {'exposure':>9} {'idx fee':>8} {'XSP $/spread':>13} {'SPXeq $/spread':>15} "
          f"{'XSP/SPXeq':>10} {'fee % of gross':>15}")
    for n in (1, 2, 3, 5, 7, 9, 10, 20):
        idx = XSP_IDX(n)
        xsp_spread = 2 * n * xsp_ct(n)                 # 2 legs x N contracts
        spx_equiv = (n / 10.0) * 2 * SPX_CT            # same exposure in SPX
        ratio = xsp_spread / spx_equiv if spx_equiv else float("inf")
        gross = (n / 10.0) * a.spx_gross               # XSP gross scales with exposure
        feepct = 100 * xsp_spread / gross if gross else 0
        exp = f"{n/10:.1f} SPX"
        print(f"{n:>6} {exp:>9} {('$'+format(idx,'.2f')):>8} {('$'+format(xsp_spread,'.2f')):>13} "
              f"{('$'+format(spx_equiv,'.2f')):>15} {ratio:>9.1f}x {feepct:>13.1f}%")
    print()
    print("reads:")
    print("  * 1-9 minis/leg: index fee $0 — stay <=9/leg to keep it waived (>=10 adds $0.07/ct).")
    print("  * fee % of gross is ~CONSTANT across 1-9 — trading more minis does NOT dilute it")
    print("    (fee and P&L both scale with size).")
    print("  * per unit of EXPOSURE, XSP costs ~5x the SPX fee (10x the contracts at ~half the")
    print("    per-contract rate). The mini's edge is SMALL SIZE / small account, NOT fee efficiency.")
    print("  * so: a few minis is fine for a small account; scaling minis to replace an SPX lot is")
    print("    fee-expensive — at ~1 SPX-equivalent (10 minis) you also trip the index fee.")


if __name__ == "__main__":
    main()
