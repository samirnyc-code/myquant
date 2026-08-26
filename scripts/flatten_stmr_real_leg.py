"""Flatten the live IB paper STMR leg AFTER the book was reconstructed to 8/25 (S106).

The book already records bps_stmr_REAL_20260819 as CLOSED on 2026-08-25 (reconstructed
at mid 14.35). But the physical IB paper position — short 7635P / long 7575P, exp
2026-09-02 — is still OPEN. This buys it to close so the account goes flat and matches
the book.

DELIBERATELY does NOT write to trades.parquet: the strategy PnL stays at the 8/25 rule
price (-$270.2). The actual close fill today is recorded ONLY to
data/options_sim/stmr_missed_exit_cost_20260825.csv as the operational cost of the miss
(actual cost vs the 14.35 book) — it is NOT part of today's or any strategy PnL.

Safety: verifies IB holds exactly short-1 7635P / long+1 7575P (exp 20260902) before
sending anything; aborts on any mismatch. Dry by default; pass --confirm to place.
Run (RTH only, 09:30-16:15 ET): .venv/Scripts/python.exe scripts/flatten_stmr_real_leg.py --confirm
"""
from __future__ import annotations
import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_sim_daemon as sd
import ib_conn
from ib_async import Option

EXPIRY = "20260902"
SHORT_K, LONG_K = 7635.0, 7575.0
BOOK_EXIT_COST = 14.35          # what the book recorded for the 8/25 exit
OUT_CSV = sd.OUT / "stmr_missed_exit_cost_20260825.csv"
CLIENT_ID = 80


def held(ib):
    """Return {(strike): position} for the two STMR legs currently in IB."""
    pos = {}
    for p in ib.positions():
        c = p.contract
        if (c.secType == "OPT" and getattr(c, "symbol", "") == "SPX"
                and getattr(c, "lastTradeDateOrContractMonth", "") == EXPIRY
                and float(c.strike) in (SHORT_K, LONG_K)):
            pos[float(c.strike)] = p.position
    return pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="actually place the buy-to-close")
    a = ap.parse_args()

    ib = ib_conn.connect(client_id=CLIENT_ID)
    try:
        pos = held(ib)
        print(f"IB holds (exp {EXPIRY}): {pos or 'nothing'}")
        if pos.get(SHORT_K) != -1 or pos.get(LONG_K) != 1:
            print(f"! ABORT: expected short-1 {SHORT_K:.0f}P / long+1 {LONG_K:.0f}P, got {pos}. "
                  "Nothing placed.")
            return 1

        so = ib.qualifyContracts(Option("SPX", EXPIRY, SHORT_K, "P", "SMART", tradingClass="SPXW"))[0]
        lo = ib.qualifyContracts(Option("SPX", EXPIRY, LONG_K, "P", "SMART", tradingClass="SPXW"))[0]
        ib.reqMarketDataType(1)
        st = ib.reqMktData(so, "", snapshot=False)
        lt = ib.reqMktData(lo, "", snapshot=False)
        ib.sleep(8)
        print(f"  {SHORT_K:.0f}P bid/ask {st.bid}/{st.ask}   {LONG_K:.0f}P bid/ask {lt.bid}/{lt.ask}")
        if not (st.ask == st.ask and lt.bid == lt.bid and st.ask > 0 and lt.bid > 0):
            print("! ABORT: incomplete quotes — nothing placed."); return 1

        est = round((st.ask or 0) - (lt.bid or 0), 2)  # what a buy-to-close pays now
        print(f"est buy-to-close cost now ~{est:.2f}  (book recorded 8/25 at {BOOK_EXIT_COST})")
        if not a.confirm:
            print("\nDRY — rerun with --confirm to place the buy-to-close.")
            return 0

        ex = sd.place_real_exit(ib, so, st, lo, lt, qty=1)
        ib.sleep(3)
        after = held(ib)
        flat = after.get(SHORT_K, 0) == 0 and after.get(LONG_K, 0) == 0
        actual = ex["cost"]
        delta = round((actual - BOOK_EXIT_COST) * 100, 2)   # operational cost of the miss ($)
        print(f"CLOSED real leg: paid {actual:.2f}  status {ex['close_status']}  IB flat: {flat} ({after})")
        print(f"operational miss cost (actual {actual} vs book {BOOK_EXIT_COST}) = ${delta:+,.2f} "
              "— recorded separately, NOT in strategy/today PnL")

        new = not OUT_CSV.exists()
        with open(OUT_CSV, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["closed_dt_et", "trade_id", "book_exit_cost", "actual_close_cost",
                            "operational_cost_usd", "ib_flat", "note"])
            w.writerow([sd.now_et().strftime("%Y-%m-%d %H:%M:%S"), "bps_stmr_REAL_20260819",
                        BOOK_EXIT_COST, actual, delta, flat,
                        "flatten of the 8/25-reconstructed STMR leg; operational only, not in strategy PnL"])
        print(f"wrote {OUT_CSV.name}")
        return 0 if flat else 1
    finally:
        ib.disconnect()


if __name__ == "__main__":
    sys.exit(main())
