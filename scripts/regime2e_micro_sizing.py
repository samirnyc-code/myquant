"""Regime2E with MES (micro) fractional sizing on TPT-PRO and Topstep-XFA funded.

Both firms permit MES ($5/pt = 0.1x ES). Micros let you size BELOW 1 ES, which is
the lever that matters: 1 ES sits at the edge of the small $4,500 max DD, so
fractional sizing is how you buy down the pre-lock blow risk. size=0.5 == 5 MES.

Sweeps size in ES-equivalents across the two funded DD models, reusing the exact
replay logic from the per-firm scripts:
  - TPT PRO   : intraday trailing on peak realized+unrealized (regime2e_tpt_funded_mc)
  - Topstep   : EOD trailing on highest end-of-day balance   (regime2e_topstep_eod)

COST scales with size (baked into pts at 1 ES); micro commission is a touch lower
than the linear scale, so live is marginally better than shown.

  python scripts/regime2e_micro_sizing.py
"""
import sys
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from regime2e_apex_intraday import extract_trades, PT               # noqa: E402
from regime2e_tpt_funded_mc import precompute, replay_fast, boot_indices, BLOCK  # noqa: E402

RNG = np.random.default_rng(11)
NPATH = 4000
SIZES = [0.2, 0.3, 0.5, 0.7, 1.0]          # ES-equivalents (2,3,5,7,10 MES)
# funded DD by account (same for TPT PRO and Topstep XFA)
ACCTS = [("50K", 2000.0), ("100K", 3000.0), ("150K", 4500.0)]


def eod_replay(seq, T):
    """Topstep EOD floor (ratchets at close, locks at start)."""
    realized = 0.0; peak_eod = 0.0; locked = None
    for i, (gb, umin, umax, pnl, _) in enumerate(seq):
        floor = min(peak_eod - T, 0.0)
        if realized + umin <= floor:
            return True, locked, realized
        realized += pnl
        peak_eod = max(peak_eod, realized)
        if locked is None and peak_eod >= T:
            locked = i
    return False, locked, realized


def sweep(trades, model):
    tpy = max(1, round(len(trades) / len({t["date"][:4] for t in trades})))
    replay = replay_fast if model == "TPT-intraday" else eod_replay
    print(f"\n{'='*70}\n{model} — MES fractional sizing, {NPATH:,} paths, ~{tpy}/yr\n{'='*70}")
    print(f"  {'acct':>5} {'ES':>4} {'MES':>4} | {'med yr$':>9} {'P(down)':>8} {'P(blow<1yr)':>11}")
    for name, T in ACCTS:
        for s in SIZES:
            pre = precompute(trades, s)     # scales pnl/umin/umax/gb by PT*s
            blow = 0; annual = np.empty(NPATH)
            for k in range(NPATH):
                seq = [pre[j] for j in boot_indices(len(pre), tpy)]
                blew, _, final = replay(seq, T)
                annual[k] = final
                blow += blew
            print(f"  {name:>5} {s:>4.1f} {int(s*10):>4} | ${np.median(annual):>+7,.0f} "
                  f"{100*(annual<0).mean():>6.0f}% {100*blow/NPATH:>10.1f}%")
        print()


def main():
    trades = extract_trades()
    print(f"Regime2E MES sizing — {len(trades)} trades, real ticks. "
          f"size=1.0 ES == 10 MES; COST scales with size.")
    sweep(trades, "Topstep-EOD")
    sweep(trades, "TPT-intraday")


if __name__ == "__main__":
    main()
