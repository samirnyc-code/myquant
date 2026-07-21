"""How deep can IB serve AAPL 1-minute bars? Probe progressively older windows."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ib_conn
from ib_async import Stock

ib = ib_conn.connect()
try:
    aapl = Stock("AAPL", "SMART", "USD")
    ib.qualifyContracts(aapl)
    print(f"AAPL conId {aapl.conId}")

    # 1) headTimestamp = IB's own answer for earliest available data
    head = ib.reqHeadTimeStamp(aapl, whatToShow="TRADES", useRTH=True)
    print(f"headTimestamp (earliest TRADES data): {head}")

    # 2) actually fetch 1-min bars at several depths (1 day each, RTH)
    for years_back in (1, 3, 5, 8, 10, 15):
        end = dt.datetime.now() - dt.timedelta(days=int(years_back * 365.25))
        end_str = end.strftime("%Y%m%d %H:%M:%S US/Eastern")
        try:
            bars = ib.reqHistoricalData(aapl, endDateTime=end_str, durationStr="1 D",
                                        barSizeSetting="1 min", whatToShow="TRADES",
                                        useRTH=True, formatDate=1, timeout=30)
            if bars:
                print(f"  -{years_back:2d}y: {len(bars):4d} 1-min bars  "
                      f"{bars[0].date} .. {bars[-1].date}  close {bars[-1].close}")
            else:
                print(f"  -{years_back:2d}y: EMPTY")
        except Exception as e:
            print(f"  -{years_back:2d}y: ERR {str(e)[:80]}")
        ib.sleep(2)
finally:
    ib.disconnect()
