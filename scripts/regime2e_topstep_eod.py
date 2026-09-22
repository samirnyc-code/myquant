"""Regime2E under TOPSTEP's funded (Express Funded / XFA) drawdown model.

Source (scraped/verified, reports/ + WebFetch of topstep.com/express-funded-account-rules):
  - XFA is SIMULATED. Maximum Loss Limit (trailing DD) = $2,000 (50K) / $3,000
    (100K) / $4,500 (150K). It is END-OF-DAY trailing: "based on your highest
    end-of-day balance," ratchets up only at the close, never decreases. Account
    permanently closed if balance drops to/through the MLL. Locks once it reaches
    the starting balance (like TPT). Combine targets: 3k/6k/9k. Pos 5/10/15 minis.
  - Payout: 5 winning days of $150+, max payout $2k/$3k/$5k, 90/10 (100% of first
    $10k), min payout $125. LFA (Live Funded) has no caps + daily after 30 win days.

KEY vs Apex-legacy / TPT-PRO: the floor ratchets on END-OF-DAY balances only, NOT
on intraday peak unrealized. For a held-to-EOD book that is far more survivable.
Modeled seg-aware: within a day the floor is fixed (set by prior EODs); liquidation
still triggers if intraday equity (realized+unrealized) touches that floor.

  python scripts/regime2e_topstep_eod.py
"""
import sys
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from regime2e_apex_intraday import extract_trades, PT               # noqa: E402

PLANS = [("50K", 2000.0, 6), ("100K", 3000.0, 12), ("150K", 4500.0, 15)]
RNG = np.random.default_rng(7)
NPATH = 10000; BLOCK = 15


def replay(seq, size, T):
    """EOD-trailing floor: fixed within a day (from prior EODs), ratchets at close.
    one-per-day book => one trade per 'day'. Returns (blew, locked_i, final)."""
    realized = 0.0; peak_eod = 0.0; locked_i = None
    for i, t in enumerate(seq):
        floor = min(peak_eod - T, 0.0)               # set by prior EOD balances
        u = t["sgn"] * (t["seg"] - t["entry"]) * PT * size
        eq_low = realized + float(u.min())           # worst intraday equity today
        if eq_low <= floor:
            return True, locked_i, realized
        realized += t["pts"] * PT * size             # EOD balance (flat at close)
        peak_eod = max(peak_eod, realized)
        if locked_i is None and peak_eod >= T:
            locked_i = i
    return False, locked_i, realized


def boot_indices(n, length):
    out = []
    while len(out) < length:
        st = int(RNG.integers(0, n - BLOCK))
        out.extend(range(st, min(st + BLOCK, n)))
    return out[:length]


def main():
    trades = extract_trades()
    yrs = len({t["date"][:4] for t in trades})
    tpy = max(1, round(len(trades) / yrs))
    print(f"TOPSTEP XFA — EOD trailing DD (floor ratchets at close, locks at start) — "
          f"one_per_day, {len(trades)} trades, real ticks")
    print("COST=$17.50/RT (=Apex/TPT runs). TPT/Topstep ES comm differ; kept equal for compare.\n")

    # --- single deterministic 5-yr path ---
    print("Sequential 5-yr path:")
    print(f"  {'plan':>5} {'size':>4} | {'blew?':>18} {'net/5yr':>10}")
    for name, T, cap in PLANS:
        for size in (1, 2, 3):
            blew, _, final = replay(trades, size, T)
            st = "survives 5yr" if not blew else "BLOWN"
            # find blow date if blown
            if blew:
                r2, real = 0.0, 0.0; pe = 0.0; bd = None
                for t in trades:
                    fl = min(pe - T, 0.0)
                    u = t["sgn"] * (t["seg"] - t["entry"]) * PT * size
                    if real + float(u.min()) <= fl:
                        bd = t["date"]; break
                    real += t["pts"] * PT * size; pe = max(pe, real)
                st = f"BLOWN {bd}"
            print(f"  {name:>5} {size:>4} | {st:>18} ${final:>+9,.0f}")
        print()

    # --- block-bootstrap MC: blow odds + annual $ ---
    print(f"Block-bootstrap MC (~{tpy} trades/yr, block={BLOCK}, {NPATH:,} paths):")
    print(f"  {'plan':>5} {'size':>4} | {'med yr$':>9} {'10th':>8} {'90th':>8} {'P(down)':>8} |"
          f" {'P(blow<lock)':>12} {'P(blow<1yr)':>11}")
    n = len(trades)
    for name, T, cap in PLANS:
        for size in (1, 2, 3):
            blow_pre = blow_yr = 0; annual = np.empty(NPATH)
            for k in range(NPATH):
                seq = [trades[j] for j in boot_indices(n, tpy)]
                blew, locked_i, final = replay(seq, size, T)
                annual[k] = final
                if blew:
                    blow_yr += 1
                    if locked_i is None:
                        blow_pre += 1
            print(f"  {name:>5} {size:>4} | ${np.median(annual):>+7,.0f} "
                  f"${np.percentile(annual,10):>+6,.0f} ${np.percentile(annual,90):>+6,.0f} "
                  f"{100*(annual<0).mean():>6.0f}% | {100*blow_pre/NPATH:>11.1f}% "
                  f"{100*blow_yr/NPATH:>10.1f}%")
        print()


if __name__ == "__main__":
    main()
