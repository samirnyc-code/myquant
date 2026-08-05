import sys, datetime as dt; sys.path.insert(0,"scripts")
import ib_conn
from ib_async import Option
ib=ib_conn.connect(client_id=10)
print(f"CONNECTED clientId=10  isConnected={ib.isConnected()}  -> API Client should be GREEN, single 'Client 10' tab")
ib.reqMarketDataType(1)
c=ib.qualifyContracts(Option("SPX","20260804",7600,"P","SMART",tradingClass="SPXW"))[0]
t=ib.reqMktData(c,"",snapshot=False); ib.sleep(6)
print(f"live quote check 7600P: type={t.marketDataType} bid={t.bid} ask={t.ask}")
for i in range(20):   # ~10 min heartbeat, holds the connection green
    ib.sleep(30)
    print(f"  [{dt.datetime.now():%H:%M:%S}] holding connection (heartbeat {i+1}/20)  connected={ib.isConnected()}")
ib.disconnect(); print("released")
