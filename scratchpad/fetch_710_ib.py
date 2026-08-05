# Pull ES Sep'26 1-min bars for 2026-07-10 RTH from IB Gateway (paper, delayed ok)
# -> approximate prior-session VP for the 7/13 trading chart.
import sys
sys.path.insert(0, r"c:\Users\Admin\myquant\scripts")
sys.path.insert(0, r"c:\Users\Admin\myquant")
from ib_conn import connect
from ib_async import Future
import pandas as pd

ib = connect(client_id=87, market_data_type=3)
c = Future("ES", exchange="CME", lastTradeDateOrContractMonth="202609", currency="USD")
ib.qualifyContracts(c)
print("contract:", c.localSymbol, c.conId)

bars = ib.reqHistoricalData(
    c, endDateTime="20260710 16:10:00 US/Central", durationStr="1 D",
    barSizeSetting="1 min", whatToShow="TRADES", useRTH=False, formatDate=1)
df = pd.DataFrame([{ "t": b.date, "o": b.open, "h": b.high, "l": b.low,
                     "c": b.close, "v": b.volume } for b in bars])
print(len(df), "bars")
if len(df):
    df.to_csv(r"c:\Users\Admin\myquant\scratchpad\es_1min_20260710_ib.csv", index=False)
    print(df.head(2)); print(df.tail(2))
ib.disconnect()
