"""IB history depth: AAPL 1-min + ES CONTFUT verification (unadjusted or not?)."""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\Admin\myquant\scripts")
import ib_conn
from ib_async import ContFuture, Stock

ib = ib_conn.connect()
try:
    # ---------- AAPL 1-min depth ----------
    aapl = Stock("AAPL", "SMART", "USD")
    ib.qualifyContracts(aapl)
    try:
        head = ib.reqHeadTimeStamp(aapl, whatToShow="TRADES", useRTH=True, formatDate=1)
        print(f"AAPL headTimestamp (earliest data): {head}")
    except Exception as e:
        print(f"AAPL headTimestamp ERR: {str(e)[:100]}")
    for yb in (1, 3, 5, 8, 10, 15):
        end = dt.datetime.now() - dt.timedelta(days=int(yb * 365.25))
        try:
            bars = ib.reqHistoricalData(aapl, endDateTime=end.strftime("%Y%m%d %H:%M:%S US/Eastern"),
                                        durationStr="1 D", barSizeSetting="1 min",
                                        whatToShow="TRADES", useRTH=True, formatDate=1)
            print(f"  AAPL -{yb:2d}y: {len(bars):4d} bars" +
                  (f"  {bars[0].date} .. {bars[-1].date} close {bars[-1].close}" if bars else "  EMPTY"))
        except Exception as e:
            print(f"  AAPL -{yb:2d}y: ERR {str(e)[:80]}")
        ib.sleep(3)

    # ---------- ES CONTFUT: adjusted or actual? ----------
    es = ContFuture("ES", "CME")
    ib.qualifyContracts(es)
    print(f"\nES CONTFUT conId {es.conId} localSymbol {es.localSymbol}")
    # Known actual reference closes (from Yahoo ES=F, actual front-contract):
    # 2025-07-11 close ~6296 actual; back-adjusted continuous had ~+225 offset then.
    for yb, ref in ((1, "expect ~6290s if ACTUAL, ~6520s if back-adjusted"),
                    (3, "check plausibility vs 2023 ES ~4500s"),
                    (5, "2021 ES ~4300s")):
        end = dt.datetime.now() - dt.timedelta(days=int(yb * 365.25))
        try:
            bars = ib.reqHistoricalData(es, endDateTime=end.strftime("%Y%m%d %H:%M:%S US/Eastern"),
                                        durationStr="1 D", barSizeSetting="1 min",
                                        whatToShow="TRADES", useRTH=False, formatDate=1)
            print(f"  ES -{yb}y: {len(bars):4d} bars" +
                  (f"  last {bars[-1].date} close {bars[-1].close}  [{ref}]" if bars else "  EMPTY"))
        except Exception as e:
            print(f"  ES -{yb}y: ERR {str(e)[:80]}")
        ib.sleep(3)
finally:
    ib.disconnect()
