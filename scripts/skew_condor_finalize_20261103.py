"""Finalize the two skew-condor trades left open since 2026-11-03 14:45 CT
(both close_combo attempts failed -- no bid on far-OTM 0DTE calls that late).

Settlement value is NOT guessed/modeled: both skew legs share EXACT strikes
with real desk trades that settled normally --
  skew "open" (short 7645C/long 7670C) == real eodic_c (auto_20261103_083231)
  skew "eod"  (short 7650C/long 7675C) == real gx_bcs   (auto_20261103_090906)
Both real trades: exit_cost=0.0, close_reason="expired" (confirmed worthless
at cash settlement). Using that same verified exit_cost for the skew legs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog

FEE = 1.30
EXIT_DT = "2026-11-03 16:00"   # same timestamp format/value as the real trades at these strikes

EXITS = {
    "skew_open_20261103_110218": 0.0,   # == real eodic_c (7645C/7670C), confirmed expired worthless
    "skew_eod_20261103_110441": 0.0,    # == real gx_bcs   (7650C/7675C), confirmed expired worthless
}


def main():
    tlog.set_book("skew_condor")
    for tid, exit_cost in EXITS.items():
        r = tlog.update_exit(tid, EXIT_DT, exit_cost, 4 * FEE, close_reason="expired")
        print(f"{tid}: credit {r['credit']} -> exit_cost {r['exit_cost']}, pnl {r['pnl']:.2f}")


if __name__ == "__main__":
    main()
