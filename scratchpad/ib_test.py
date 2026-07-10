"""
IB Gateway connection test — SPX index + one option (greeks + Open Interest).
Read-only. Pulls nothing else. Tells us if this account can see SPX option data.
"""
from ib_async import IB, Index, Option
import time

HOST, PORT, CID = "127.0.0.1", 4001, 17   # 4001 = live Gateway

ib = IB()
print(f"Connecting to {HOST}:{PORT} ...")
ib.connect(HOST, PORT, clientId=CID, timeout=15)
print("CONNECTED. Server:", ib.client.serverVersion())

# allow delayed data as fallback (3 = delayed, 4 = delayed-frozen)
ib.reqMarketDataType(3)

# --- SPX spot ---
spx = Index("SPX", "CBOE", "USD")
ib.qualifyContracts(spx)
t = ib.reqMktData(spx, "", snapshot=False)
ib.sleep(3)
spot = t.last if t.last == t.last else (t.close if t.close == t.close else None)
print(f"\nSPX spot: last={t.last}  close={t.close}  -> using {spot}")

if not spot:
    print("!! No SPX price came back — likely no CBOE index subscription.")
    ib.disconnect(); raise SystemExit

# --- pick a near-ATM option that ACTUALLY EXISTS ---
chains = ib.reqSecDefOptParams(spx.symbol, "", spx.secType, spx.conId)
print("\nchains found:", [(c.exchange, c.tradingClass, len(c.expirations)) for c in chains])
chain = next((c for c in chains if c.tradingClass == "SPXW"), chains[0])

expiries = sorted(chain.expirations)[2:6]              # a few near expiries to try
strikes  = sorted(chain.strikes, key=lambda k: abs(k - spot))[:8]  # 8 nearest-ATM

opt = None
for exp in expiries:
    for k in strikes:
        for tc in ("SPXW", "SPX"):
            c = Option("SPX", exp, k, "P", "SMART", tradingClass=tc)
            q = ib.qualifyContracts(c)
            if q and q[0].conId:
                opt = q[0]; break
        if opt: break
    if opt: break

if not opt:
    print("!! Could not qualify ANY SPX option contract."); ib.disconnect(); raise SystemExit
print(f"\nTesting option: SPX {opt.lastTradeDateOrContractMonth} "
      f"{opt.tradingClass} P {opt.strike:.0f}  (conId {opt.conId})")

# genericTick 100,101 = option volume + OPEN INTEREST; 106 = impl vol
ot = ib.reqMktData(opt, "100,101,104,106", snapshot=False)
ib.sleep(5)

print("\n--- OPTION DATA ---")
print(f"  bid/ask      : {ot.bid} / {ot.ask}")
print(f"  IV (modelGk) : {getattr(ot.modelGreeks,'impliedVol',None) if ot.modelGreeks else None}")
print(f"  gamma        : {getattr(ot.modelGreeks,'gamma',None) if ot.modelGreeks else None}")
print(f"  delta        : {getattr(ot.modelGreeks,'delta',None) if ot.modelGreeks else None}")
print(f"  PUT open int : {ot.putOpenInterest}")
print(f"  volume       : {ot.volume}")

ok_oi = ot.putOpenInterest == ot.putOpenInterest and ot.putOpenInterest > 0
ok_gk = ot.modelGreeks is not None and getattr(ot.modelGreeks, "gamma", None)
print("\n=== VERDICT ===")
print("  Open Interest :", "YES" if ok_oi else "NO - need OPRA/subscription")
print("  Greeks/gamma  :", "YES" if ok_gk else "NO - need option data subscription")
print("  -> walls buildable:", "YES" if (ok_oi and ok_gk) else "NOT YET")

ib.disconnect()
