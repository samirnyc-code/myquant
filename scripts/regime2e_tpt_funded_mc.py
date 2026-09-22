"""TPT PRO funded account: blow-up odds + annual P&L under the INTRADAY trailing DD.

Unlike regime2e_funded_mc.py (Apex), which bootstraps DAILY REALIZED returns and
therefore ignores intraday unrealized swings, this bootstraps whole TRADES *with
their intraday price segments* and replays the TPT intraday floor tick-by-tick
inside each trade (peak realized+unrealized, floor locks at START). That is the
model that actually liquidates a Regime2E book on TPT, so this is the honest odds.

Moving-block bootstrap over the 294-trade record (block=15 trades preserves
streaks). Horizon = one year of trades (~56). Reports:
  P(blow before the floor LOCKS at start)  — the ramp-up danger zone
  P(blow within 1 yr)
  median / 10th / 90th one-year realized $, P(down year)

Plans (TPT Rule 3): 25K T$1,500 / 50K $2,000 / 75K $2,500 / 100K $3,000 / 150K $4,500.

  python scripts/regime2e_tpt_funded_mc.py
"""
import sys
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from regime2e_apex_intraday import extract_trades, PT               # noqa: E402

PLANS = [("25K", 1500.0), ("50K", 2000.0), ("75K", 2500.0),
         ("100K", 3000.0), ("150K", 4500.0)]
RNG = np.random.default_rng(7)
NPATH = 4000; BLOCK = 15


def trades_per_year(trades):
    yrs = {t["date"][:4] for t in trades}
    return max(1, round(len(trades) / len(yrs)))


def precompute(trades, size):
    """Per-trade, at unit-$ (×size done here): for the intraday floor recursion we
    only need, given the equity peak coming IN to the trade (P), whether the trade
    blows and the peak/realized going OUT. Within a trade the equity path is
    eq = R + u_path. runpk = max(Pglobal, R + cummax(u)). floor = min(runpk-T, 0).
    Blow iff min(eq - floor) <= 0. Because runpk is non-decreasing and eq<=runpk,
    the tightest point is the max drawdown-from-peak combined with eq<=0.
    We precompute per trade: cummax(u) profile summary via:
      umax    = max cumulative unrealized in trade (raises the global peak)
      worst   = max over ticks of (running_peak_within - eq) i.e. deepest give-back
                measured against the peak *including prior global peak* — but prior
                peak is only known at runtime, so we store the raw u path stats
                needed: the per-tick (cummax(u) - u) [give-back vs in-trade peak]
                and u itself.
    To stay O(1) per trade at runtime we store:
      gb   = max_t (cummax(u)_t - u_t)      # deepest drop from the in-trade running peak
      umin = min_t u_t                      # deepest raw unrealized
      umax = max_t cumsum peak = max u      # highest unrealized (for global peak update)
      uend = pnl$ (realized delta)
    Runtime blow test (given incoming global peak P, incoming realized R):
      pk_in = max(P, R)                                  # start-of-trade global peak
      # drop vs global peak that also incorporates in-trade new highs:
      dd_max = max(pk_in - (R + umin), gb)               # worst peak-to-trough
      eq_min = R + umin
      blow if dd_max >= T and eq_min <= 0   (cushion<=0 under lock-at-start)
    """
    P = PT * size
    arr = []
    for t in trades:
        u = t["sgn"] * (t["seg"] - t["entry"]) * P
        cmax = np.maximum.accumulate(u)
        gb = float((cmax - u).max())
        arr.append((gb, float(u.min()), float(u.max()), t["pts"] * P, t["date"][:4]))
    return arr


def replay_fast(seq, T):
    realized = 0.0; peak = 0.0; locked_at = None
    for i, (gb, umin, umax, pnl, _) in enumerate(seq):
        pk_in = max(peak, realized)
        eq_min = realized + umin
        dd_max = max(pk_in - eq_min, gb)
        if dd_max >= T and eq_min <= 0.0:        # cushion<=0, lock-at-start
            return True, locked_at, realized
        peak = max(pk_in, realized + umax)
        if locked_at is None and peak >= T:
            locked_at = i
        realized += pnl
    return False, locked_at, realized


def boot_indices(n, length):
    out = []
    while len(out) < length:
        st = int(RNG.integers(0, n - BLOCK))
        out.extend(range(st, min(st + BLOCK, n)))
    return out[:length]


def mc(pre, size, T, horizon):
    n = len(pre)
    blow_pre = 0; blow_yr = 0; annual = np.empty(NPATH)
    for k in range(NPATH):
        seq = [pre[j] for j in boot_indices(n, horizon)]
        blew, locked_at, final = replay_fast(seq, T)
        annual[k] = final
        if blew:
            blow_yr += 1
            if locked_at is None:
                blow_pre += 1
    return dict(blow_pre=blow_pre / NPATH, blow_yr=blow_yr / NPATH,
                med=np.median(annual), p10=np.percentile(annual, 10),
                p90=np.percentile(annual, 90), pneg=(annual < 0).mean())


def main():
    trades = extract_trades()
    tpy = trades_per_year(trades)
    print(f"TPT PRO — intraday-unrealized floor, TRADE block-bootstrap "
          f"({len(trades)} trades, ~{tpy}/yr, block={BLOCK}, {NPATH:,} paths)")
    print("COST=$17.50/RT (=Apex run; TPT real ES comm $4.50 -> live slightly better)\n")
    print(f"  {'plan':>5} {'size':>4} | {'med yr$':>9} {'10th':>8} {'90th':>8} {'P(down)':>8} |"
          f" {'P(blow<lock)':>12} {'P(blow<1yr)':>11}")
    pre_by_size = {s: precompute(trades, s) for s in (1, 2, 3)}
    for name, T in PLANS:
        for size in (1, 2, 3):
            r = mc(pre_by_size[size], size, T, tpy)
            print(f"  {name:>5} {size:>4} | ${r['med']:>+7,.0f} ${r['p10']:>+6,.0f} ${r['p90']:>+6,.0f} "
                  f"{100*r['pneg']:>6.0f}% | {100*r['blow_pre']:>11.1f}% {100*r['blow_yr']:>10.1f}%")
        print()


if __name__ == "__main__":
    main()
