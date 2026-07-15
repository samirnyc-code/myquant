"""Diagnose paper OPRA entitlement: one ATM SPXW put, realtime then delayed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ib_conn
from ib_async import Index, Option

ib = ib_conn.connect()
msgs = []
ib.errorEvent += lambda reqId, code, msg, *a: msgs.append(f"  [{code}] {msg[:150]}")

spx = Index("SPX", "CBOE", "USD")
ib.qualifyContracts(spx)
ib.reqMarketDataType(4)
t = ib.reqMktData(spx, "", snapshot=False)
ib.sleep(4)
ib.cancelMktData(spx)
spot = t.last if t.last == t.last else t.close
chains = ib.reqSecDefOptParams("SPX", "", "IND", spx.conId)
chain = next(c for c in chains if c.tradingClass == "SPXW" and c.exchange == "SMART")
expiry = sorted(chain.expirations)[3]
k = min(chain.strikes, key=lambda s: abs(s - spot))
opt = ib.qualifyContracts(Option("SPX", expiry, k, "P", "SMART", tradingClass="SPXW"))[0]
print(f"contract: SPXW {expiry} {k}P conId={opt.conId}")

for mdt, name in ((1, "REALTIME"), (3, "DELAYED")):
    msgs.clear()
    ib.reqMarketDataType(mdt)
    q = ib.reqMktData(opt, "", snapshot=False)
    ib.sleep(8)
    g = q.modelGreeks
    print(f"\n{name}: bid={q.bid} ask={q.ask} last={q.last} "
          f"undPrice={getattr(g, 'undPrice', None) if g else None} mdt_received={q.marketDataType}")
    for m in msgs:
        print(m)
    ib.cancelMktData(opt)
    ib.sleep(1)
ib.disconnect()
