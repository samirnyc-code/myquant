"""
SPX call-resistance / put-support / HVL from live IB OI x gamma.
Calibration target (MenthorQ $SPX, 2026-07-09):
    Call Resistance 7550 | Put Support 7300 | HVL 7485
    CR-0DTE 7550 | PS-0DTE 7450 | GammaWall-0DTE 7550
Read-only. Delayed feed OK (OI is prior-day anyway).
"""
import sys, math, time
from collections import defaultdict
from ib_async import IB, Index, Option

HOST, PORT, CID = "127.0.0.1", 4001, 21
BAND_LO, BAND_HI = 0.95, 1.03          # spot -5% / +3%
NEAR_DTE = 14                          # "standard" aggregate window
THROTTLE = 0.04                        # s between mkt-data requests

MQ = dict(CR=7550, PS=7300, HVL=7485, CR0=7550, PS0=7450, GW0=7550)

ib = IB()
ib.connect(HOST, PORT, clientId=CID, timeout=15)
ib.reqMarketDataType(3)                # delayed

spx = Index("SPX", "CBOE", "USD"); ib.qualifyContracts(spx)
t = ib.reqMktData(spx, "", snapshot=False); ib.sleep(3)
spot = t.last if t.last == t.last else t.close
print(f"SPX spot = {spot:.2f}\n")

params = ib.reqSecDefOptParams(spx.symbol, "", spx.secType, spx.conId)
chain = next(c for c in params if c.tradingClass == "SPXW" and c.exchange == "SMART")
today = min(chain.expirations)                       # nearest expiry = 0DTE
exps  = sorted(chain.expirations)
# near-term set: expiries within NEAR_DTE calendar days of the nearest
def dte(e): return (int(e) - int(today))             # crude yyyymmdd delta as proxy
near = [e for e in exps if dte(e) <= (NEAR_DTE*1.0 + 5)][:8]   # cap at 8 expiries
strikes = sorted(k for k in chain.strikes if BAND_LO*spot <= k <= BAND_HI*spot)
print(f"0DTE expiry {today} | near-term set {near}")
print(f"{len(strikes)} strikes {strikes[0]:.0f}-{strikes[-1]:.0f} | "
      f"~{len(strikes)*len(near)*2} contracts to pull\n")

def pull(expiry, strikes):
    """return {strike: (callOI, callGamma, putOI, putGamma)}"""
    out = {}
    # qualify all C+P for this expiry at once
    cons = []
    for k in strikes:
        for r in ("C", "P"):
            cons.append(Option("SPX", expiry, k, r, "SMART", tradingClass="SPXW"))
    q = ib.qualifyContracts(*cons)
    q = [c for c in q if c and getattr(c, "conId", None)]
    tickers = {}
    for c in q:
        tk = ib.reqMktData(c, "100,101,104,106", snapshot=False)
        tickers[c.conId] = (c, tk)
        time.sleep(THROTTLE)
    ib.sleep(6)                         # let greeks/OI populate
    for c, tk in tickers.values():
        g = getattr(tk.modelGreeks, "gamma", None) if tk.modelGreeks else None
        oi = tk.callOpenInterest if c.right == "C" else tk.putOpenInterest
        oi = oi if oi == oi else 0.0
        g = g if (g is not None and g == g) else 0.0
        cur = out.get(c.strike, [0,0,0,0])
        if c.right == "C": cur[0], cur[1] = oi, g
        else:              cur[2], cur[3] = oi, g
        out[c.strike] = cur
    for c in q: ib.cancelMktData(c)
    return out

def walls(agg, spot, label):
    # agg: {strike:[cOI,cG,pOI,pG]}  -> notional = OI*gamma*100*spot^2*1e-9 (units cancel for argmax)
    rows = []
    for k,(coi,cg,poi,pg) in sorted(agg.items()):
        cgex =  coi*cg*100*spot*spot*1e-9
        pgex = -poi*pg*100*spot*spot*1e-9     # dealer short puts -> negative
        rows.append((k, cgex, pgex, cgex+pgex, coi, poi))
    calls_above = [(k,cg) for k,cg,pg,net,coi,poi in rows if k>spot]
    puts_below  = [(k,-pg) for k,cg,pg,net,coi,poi in rows if k<spot]  # magnitude
    CR = max(calls_above, key=lambda x:x[1])[0] if calls_above else None
    PS = max(puts_below,  key=lambda x:x[1])[0] if puts_below  else None
    # HVL: net-GEX zero crossing (flip)
    HVL = None
    for i in range(1,len(rows)):
        if rows[i-1][3] <= 0 < rows[i][3] or rows[i-1][3] >= 0 > rows[i][3]:
            HVL = rows[i][0]; break
    # top |net GEX| strikes
    top = sorted(rows, key=lambda r:abs(r[3]), reverse=True)[:10]
    print(f"\n=== {label} ===")
    print(f"  Call Resistance : {CR}")
    print(f"  Put Support     : {PS}")
    print(f"  HVL (gamma flip): {HVL}")
    print(f"  top |GEX| strikes: {[int(r[0]) for r in top]}")
    return CR, PS, HVL, rows

# ---- 0DTE ----
d0 = pull(today, strikes)
CR0,PS0,HVL0,_ = walls(d0, spot, f"0DTE ({today})")

# ---- near-term aggregate ----
agg = defaultdict(lambda:[0,0,0,0])
for e in near:
    d = pull(e, strikes)
    for k,v in d.items():
        a = agg[k]; a[0]+=v[0]; a[1]+=v[1]; a[2]+=v[2]; a[3]+=v[3]
CRn,PSn,HVLn,_ = walls(agg, spot, f"NEAR-TERM aggregate ({len(near)} exp <= ~{NEAR_DTE}DTE)")

print("\n================ COMPARISON vs MenthorQ 2026-07-09 ================")
print(f"                 MenthorQ   IB-0DTE   IB-near")
print(f"  Call Resist :    {MQ['CR']}      {CR0}      {CRn}")
print(f"  Put Support :    {MQ['PS']}      {PS0}      {PSn}")
print(f"  HVL         :    {MQ['HVL']}      {HVL0}      {HVLn}")
ib.disconnect()
