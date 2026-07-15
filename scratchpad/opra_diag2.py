"""Test 2 live-spot candidates on paper: (a) modelGreeks after long wait,
(b) put-call parity from 0DTE ATM call+put NBBO."""
import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ib_conn
from ib_async import Index, Option

ib = ib_conn.connect()
spx = Index("SPX", "CBOE", "USD")
ib.qualifyContracts(spx)
ib.reqMarketDataType(4)
t = ib.reqMktData(spx, "", snapshot=False)
ib.sleep(4)
ib.cancelMktData(spx)
spot = t.last if t.last == t.last else t.close
print(f"delayed spot ~ {spot}")
chains = ib.reqSecDefOptParams("SPX", "", "IND", spx.conId)
chain = next(c for c in chains if c.tradingClass == "SPXW" and c.exchange == "SMART")
today = dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")
exp0 = min(e for e in chain.expirations if e >= today)
ks = sorted(chain.strikes, key=lambda s: abs(s - spot))[:3]
print(f"0DTE expiry {exp0}, strikes {ks}")

ib.reqMarketDataType(1)
pairs = {}
for k in ks:
    for r in "CP":
        c = ib.qualifyContracts(Option("SPX", exp0, k, r, "SMART", tradingClass="SPXW"))[0]
        pairs[(k, r)] = ib.reqMktData(c, "", snapshot=False)
ib.sleep(15)

for k in ks:
    cq, pq = pairs[(k, "C")], pairs[(k, "P")]
    ok = all(x == x and x > 0 for x in (cq.bid, cq.ask, pq.bid, pq.ask))
    if ok:
        s = (cq.bid + cq.ask) / 2 - (pq.bid + pq.ask) / 2 + k
        print(f"K={k}: C {cq.bid}/{cq.ask}  P {pq.bid}/{pq.ask}  parity spot = {s:.2f}")
    else:
        print(f"K={k}: incomplete quotes C {cq.bid}/{cq.ask} P {pq.bid}/{pq.ask}")
    g = pq.modelGreeks
    print(f"      put modelGreeks after 15s: {'undPrice=' + str(g.undPrice) + ' delta=' + str(g.delta) if g else 'None'}")
ib.disconnect()
