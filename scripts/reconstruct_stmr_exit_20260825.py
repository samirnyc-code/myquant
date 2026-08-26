"""Reconstruct the MISSED STMR exit of 2026-08-25 (S106).

The STMR rule said exit on 2026-08-25 (15:59 spot 7679 > SMA5 7671 -> buy the BPS
back). The all-day daemon died before the decision that day (late gateway), so the
exit never fired and both bps_stmr rows sat open. This backdates the exit into the
book to the 8/25 fill window, at the best recorded price we have.

PRICE: the only 8/25 close-window data recorded for the 9/2 7635P/7575P spread is the
marks-watch MID mark. Fill window is 16:00-16:15 ET; nearest sample 16:05:02 = 14.35.
A real buy-to-close pays the ask side, so 14.35 (mid) is ~0.15-0.30 OPTIMISTIC — the
fill_model is tagged 'reconstructed_1600_mark' so this is never mistaken for a real NBBO
fill (backtest-fill-realism rule).

  sim  bps_stmr_2026-08-19    : pure book entry -> clean backdated close.
  real bps_stmr_REAL_20260819: the LIVE IB paper position (short 7635P/long 7575P) is
                               still open. This books it closed as-of 8/25 for the
                               record; the physical IB leg must be flattened separately
                               (a real order) or reconcile_real will flag divergence.

Reversible: backs up trades.parquet first. Prints before/after PnL.
Run: .venv/Scripts/python.exe scripts/reconstruct_stmr_exit_20260825.py [--apply]
     (default is a DRY preview; --apply writes the book.)
"""
from __future__ import annotations
import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_trade_log as tlog

EXIT_DT = "2026-08-25"
EXIT_COST = 14.35          # 16:05:02 ET mid mark (nearest to the 16:00 fill window)
FEE = 1.30                 # per-contract; 4 legs round-trip on the close
FEES_TOTAL = 4 * FEE
ROWS = [
    ("bps_stmr_2026-08-19",    "reconstructed_1600_mark",
     "STMR exit 8/25 (spot>SMA5); reconstructed — daemon missed the fire (S106)"),
    ("bps_stmr_REAL_20260819", "reconstructed_1600_mark",
     "STMR exit 8/25 (spot>SMA5); reconstructed — LIVE IB leg still open, flatten separately (S106)"),
]


def preview(df):
    print(f"{'trade_id':<26}{'credit':>8}{'exit_cost':>10}{'fees':>7}{'-> PnL':>10}")
    out = {}
    for tid, _, _ in ROWS:
        r = df[df.trade_id == tid]
        if r.empty:
            print(f"{tid:<26}  NOT FOUND"); continue
        credit = float(r.credit.iloc[0])
        pnl = (credit - EXIT_COST) * 100 - FEES_TOTAL
        out[tid] = pnl
        cur = r.exit_dt.iloc[0]
        state = "OPEN" if (cur is None or str(cur) in ("NaT", "nan", "")) else f"already exited {cur}"
        print(f"{tid:<26}{credit:>8.2f}{EXIT_COST:>10.2f}{FEES_TOTAL:>7.2f}{pnl:>10.1f}   ({state})")
    print(f"{'':<26}{'':>8}{'':>10}{'COMBINED':>7}{sum(out.values()):>10.1f}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the book (default: dry preview)")
    a = ap.parse_args()

    df = tlog.load()
    print("=== BEFORE (would-be 8/25 exit PnL) ===")
    preview(df)

    if not a.apply:
        print("\nDRY preview only — rerun with --apply to write.")
        return

    src = Path(tlog.LOG)
    bak = Path(str(src) + ".bak_reconstruct_20260825")
    shutil.copy2(src, bak)
    print(f"\nbacked up book -> {bak.name}")

    for tid, fm, reason in ROWS:
        r = tlog.update_exit(tid, EXIT_DT, EXIT_COST, FEES_TOTAL,
                             fill_model=fm, close_reason=reason)
        print(f"CLOSED {tid}: exit_dt {r['exit_dt']}  exit_cost {r['exit_cost']}  pnl ${r['pnl']:+,.1f}")

    print("\n=== AFTER (written) ===")
    preview(tlog.load())


if __name__ == "__main__":
    main()
