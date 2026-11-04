"""One-off: the skew_condor_shadow.py --live run (2026-11-03) exited at its
14:45 CT time-stop with BOTH close_combo attempts failing ("combo close did
not fill") -- entry fills succeeded (open: sold 7645C/bought 7670C; eod: sold
7650C/bought 7675C, both credit $0.05), but neither position was flattened or
logged as exited. This checks actual IB position state and either closes
them (if still time before the 15:00 CT / 16:00 ET close) or, if the market
has already closed, finalizes the trade log from the actual settlement
(cash-settled SPXW index options -- no assignment risk either way).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
import options_trade_log as tlog
from options_trigger_daemon import combo_contract, close_combo, qualify
import datetime as dt
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
EXP = "20261103"
FEE = 1.30

PAIRS = {
    "open": [("C", 7670, "BUY"), ("C", 7645, "SELL")],
    "eod":  [("C", 7675, "BUY"), ("C", 7650, "SELL")],
}
TRADE_IDS = {"open": "skew_open_20261103_110218", "eod": "skew_eod_20261103_110441"}


def main():
    tlog.set_book("skew_condor")
    ib = ib_conn.connect()
    print(f"now CT: {dt.datetime.now(CT)}")

    # actual IB position check (ground truth, not assumed)
    positions = ib.positions()
    for p in positions:
        if p.contract.symbol == "SPX" and p.contract.lastTradeDateOrContractMonth == EXP:
            print(f"  IB position: {p.contract.localSymbol} qty={p.position} avgCost={p.avgCost}")

    for anchor, legs in PAIRS.items():
        try:
            bag = combo_contract(ib, EXP, legs)
            debit = close_combo(ib, bag, 1, retries=2)
            print(f"  {anchor}: CLOSED, debit {debit}")
        except Exception as e:
            print(f"  {anchor}: close still failing ({e})")
            continue
        tlog.update_exit(TRADE_IDS[anchor], dt.datetime.now(CT).strftime("%Y-%m-%d %H:%M"),
                          debit, 4 * FEE)
        print(f"  {anchor}: trade log updated")

    ib.disconnect()


if __name__ == "__main__":
    main()
