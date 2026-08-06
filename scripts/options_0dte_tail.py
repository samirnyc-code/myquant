"""options_0dte_tail.py — Cycle 4: crash-tail risk + IC/BPS portfolio.

The gap filter skips UP-gaps, but crashes are DOWN moves the strategy trades INTO
(short put side). This quantifies the real tail: worst days, consecutive-loss streaks,
the defined-risk cap, a synthetic crash shock, and whether IC+BPS diversify.
Uses the open-anchored, skip-up-gap, hold-to-expiry book (1-EM / 25-wide).

Run: .venv/Scripts/python.exe scripts/options_0dte_tail.py
Out: console + data/options_0dte/tail.txt
"""
from __future__ import annotations
from pathlib import Path
import io
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "options_0dte"
OUT = io.StringIO()


def p(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.write(s + "\n")


def worst_streak(x):
    """largest cumulative peak-to-trough in $ and the max consecutive losing run."""
    cum = np.cumsum(x); dd = (np.maximum.accumulate(cum) - cum).max()
    run = mx = 0
    for v in x:
        run = run + 1 if v < 0 else 0
        mx = max(mx, run)
    return dd, mx


def main():
    t = pd.read_csv(D / "trades_all.csv", parse_dates=["date"])
    t = t[(t.anchor == "open") & (t.gap_pct <= 0.2)].sort_values("date")
    ic = t[t.strat == "ic"]; bps = t[t.strat == "bps"]

    p("=== CRASH TAIL (open, skip up-gaps, hold-to-expiry, 1-EM/25-wide) ===\n")
    for name, g in [("IC", ic), ("BPS", bps)]:
        x = g.pnl_mid.to_numpy()
        dd, run = worst_streak(x)
        worst = g.nsmallest(5, "pnl_mid")[["date", "gap_pct", "close", "pnl_mid"]]
        p(f"{name}: n={len(x)}  worst day ${x.min():.0f}  (defined-risk cap ~-$2300/contract)")
        p(f"     maxDD ${dd:.0f}  longest losing streak {run} trades")
        p(f"     5 worst days:")
        for _, r in worst.iterrows():
            p(f"       {r['date'].date()}  gap {r['gap_pct']:+.2f}%  close {r['close']:.0f}  ${r['pnl_mid']:.0f}")
        # are the worst days DOWN moves? (crashes the filter does NOT stop)
        downmoves = (g[g.pnl_mid < -1000]["close"] < g[g.pnl_mid < -1000]["open"]).mean() * 100
        p(f"     of the big-loss days (<-$1000), {downmoves:.0f}% were DOWN days "
          f"-> the gap filter (up-gaps) does NOT protect the crash tail.\n")

    # synthetic crash: every trade this book takes on a -X% close = max loss on put side
    p("=== SYNTHETIC CRASH (what a -5% day does to 1 contract) ===")
    p("  defined-risk: put spread caps at width-credit ~ -$2,300; call side expires -> keep call credit.")
    p("  IC on a crash day ~ -$2,300 + call credit(~$80) = ~-$2,220/contract.")
    p("  A 3-day crash streak ~ -$6,700/contract; 5-day ~ -$11,000/contract (~55% of a $20k acct).")
    p("  KEY: crashes are down-gaps, which PASS the up-gap filter -> full exposure. Not hedged.\n")

    # portfolio: do IC and BPS diversify?
    m = ic.set_index("date")["pnl_mid"].rename("IC").to_frame().join(
        bps.set_index("date")["pnl_mid"].rename("BPS"), how="inner")
    corr = m["IC"].corr(m["BPS"])
    combo = (m["IC"] + m["BPS"])
    def sh(x): return x.mean()/x.std()*np.sqrt(252)
    ddc, _ = worst_streak(combo.to_numpy())
    p("=== IC + BPS PORTFOLIO (both, same days) ===")
    p(f"  correlation IC vs BPS: {corr:.2f}  (high = same bet, low = diversifying)")
    p(f"  IC alone  Sharpe {sh(m['IC']):.2f}  | BPS alone Sharpe {sh(m['BPS']):.2f}  "
      f"| IC+BPS Sharpe {sh(combo):.2f}  maxDD ${ddc:.0f}")
    p("  (both are short-vol / short the same down-tail -> expect high corr, little diversification)")

    (D / "tail.txt").write_text(OUT.getvalue())
    p(f"\nsaved {D/'tail.txt'}")


if __name__ == "__main__":
    main()
