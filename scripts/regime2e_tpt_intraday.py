"""Regime2E funded-account survival under TAKE PROFIT TRADER's **PRO** drawdown model.

Source (scraped, verbatim, reports/tpt_scrape/):
  - PRO Account Rules #5 + "How to Keep Track Of Your Drawdown": the PRO (funded)
    account uses an INTRADAY trailing drawdown on PEAK BALANCE including realized
    AND unrealized gains. It trails up in real time and STOPS at the STARTING
    balance (locks at start, NOT start+$100 like Apex). Liquidated the instant
    equity (realized+unrealized) touches the minimum-account-balance floor.
  - Rule 3 table: DD amount per size — 25K $1,500 / 50K $2,000 / 75K $2,500 /
    100K $3,000 / 150K $4,500. Max contracts 3/6/9/12/15. PRO DD = passed-test DD.

Difference vs Apex legacy funded (regime2e_apex_intraday.py):
  - floor locks at start ($0 P&L), not start+$100.
  - Smaller DDs and TPT tops out at 150K ($4,500) — Apex went to 300K ($7,500),
    so TPT's biggest account gives LESS cushion than Apex 250K/300K.

Same one-per-day book, same real trove ticks, same COST as the Apex run so the
two are directly comparable. (TPT's real ES commission is $4.50/RT; COST here
bundles commission+slippage at the Apex-comparable $17.50 — see note in output.)

  python scripts/regime2e_tpt_intraday.py
"""
import sys
from pathlib import Path
import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from regime2e_apex_intraday import extract_trades, PT               # noqa: E402

# (name, drawdown threshold, max contracts) — TPT Rule 3 table
PLANS = [("25K", 1500.0, 3), ("50K", 2000.0, 6), ("75K", 2500.0, 9),
         ("100K", 3000.0, 12), ("150K", 4500.0, 15)]


def evaluate(trades, size, T):
    """Intraday trailing on peak (realized+unrealized), floor locks at START ($0 P&L)."""
    realized = 0.0; peak = 0.0; blown = None
    min_cush = 1e12; yearly = {}
    for t in trades:
        if blown is not None:
            break
        u = t["sgn"] * (t["seg"] - t["entry"]) * PT * size
        eq = realized + u
        runpk = np.maximum(peak, np.maximum.accumulate(eq))
        floor = np.minimum(runpk - T, 0.0)          # trails up, locks at start (0)
        cush = eq - floor
        mc = float(cush.min())
        min_cush = min(min_cush, mc)
        if mc <= 0 and blown is None:
            blown = t["date"]
        peak = float(runpk[-1])
        realized += t["pts"] * PT * size
        yearly[t["date"][:4]] = yearly.get(t["date"][:4], 0.0) + t["pts"] * PT * size
    return dict(blown=blown, min_cush=min_cush, final=realized, yearly=yearly)


def main():
    trades = extract_trades()
    print(f"TAKE PROFIT TRADER **PRO** intraday trailing DD (peak realized+unrealized, "
          f"locks at START) — one_per_day, {len(trades)} trades, real ticks")
    print("NOTE: COST=$17.50/RT (commission+slippage, = Apex run). TPT actual ES "
          "commission is $4.50/RT, so live results run slightly better.\n")
    print(f"{'plan':>5} {'cap':>4} {'size':>4} | {'blew?':>18} {'deepest cushion':>16} {'net/5yr(1c)':>12}")
    for name, T, cap in PLANS:
        for size in (1, 2, 3):
            r = evaluate(trades, size, T)
            st = f"BLOWN {r['blown']}" if r["blown"] else "survives 5yr"
            print(f"{name:>5} {cap:>4} {size:>4} | {st:>18} ${r['min_cush']:>+13,.0f} ${r['final']:>+11,.0f}")
        print()
    r = evaluate(trades, 1, 4500.0)
    print("150K @ 1 ES per-year (until blow):")
    print("  " + "  ".join(f"{y}:${v:+,.0f}" for y, v in sorted(r["yearly"].items())))


if __name__ == "__main__":
    main()
