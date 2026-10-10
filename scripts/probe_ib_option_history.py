"""probe_ib_option_history.py — READ-ONLY probe: can IB give us historical BID_ASK bars
for an SPXW option that expired YESTERDAY? (ThetaData's at_time/quote endpoint now
requires a paid tier we don't have; checking whether IB's own reqHistoricalData can
substitute for the Oct-9 reconstruction, since IB is already our live NBBO source.)

Run:  .venv/Scripts/python.exe scripts/probe_ib_option_history.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ib_conn
from ib_async import Option


def main():
    ib = ib_conn.connect()
    try:
        c = Option("SPX", "20261009", 7765.0, "P", "SMART", tradingClass="SPXW", multiplier="100", currency="USD")
        qualified = ib.qualifyContracts(c)
        print(f"qualified: {qualified}")
        if not qualified:
            print("COULD NOT QUALIFY CONTRACT — trying CBOE exchange explicitly")
            c = Option("SPX", "20261009", 7765.0, "P", "CBOE", tradingClass="SPXW", multiplier="100", currency="USD")
            qualified = ib.qualifyContracts(c)
            print(f"qualified (CBOE): {qualified}")
        if not qualified:
            print("STILL no contract — cannot proceed")
            return
        c = qualified[0]
        bars = ib.reqHistoricalData(
            c, endDateTime="20261009-20:00:00",
            durationStr="1 D", barSizeSetting="1 min",
            whatToShow="BID_ASK", useRTH=True, formatDate=1)
        print(f"BID_ASK bars returned: {len(bars)}")
        for b in bars[:5]:
            print(" ", b)
        if len(bars) > 5:
            print(f"  ... and {len(bars)-5} more")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
