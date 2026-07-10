"""
SPX OI/gamma PROFILE diagnostic — reverse-engineer MenthorQ levels.
Pulls BOTH classes (SPXW weeklies/dailies + SPX monthlies, AM-settled),
wide band, 25pt resolution. Dumps per-strike call/put OI and gamma so we can
see whether MenthorQ's Put Support 7300 is a raw-OI wall we were missing.

Target (MenthorQ $SPX, struck 7/9 EOD, shown 7/10): CR 7550 | PS 7300 | HVL 7485
"""
import time, math
from collections import defaultdict
from ib_async import IB, Index, Option

HOST, PORT, CID = "127.0.0.1", 4001, 22
LO, HI = 0.92, 1.05          # spot -8% / +5%
STEP = 25                    # 25pt scan (OI walls sit on 25/50/100 grid)
N_WEEKLY = 10                # nearest SPXW expiries
N_MONTHLY = 6                # nearest SPX (AM monthly) expiries
THROTTLE = 0.04
MQ = dict(CR=7550, PS=7300, HVL=7485)

ib = IB(); ib.connect(HOST, PORT, clientId=CID, timeout=15); ib.reqMarketDataType(3)
spx = Index("SPX", "CBOE", "USD"); ib.qualifyContracts(spx)
t = ib.reqMktData(spx, "", snapshot=False); ib.sleep(3)
spot = t.last if t.last == t.last else t.close
print(f"SPX spot = {spot:.2f}")

params = ib.reqSecDefOptParams(spx.symbol, "", spx.secType, spx.conId)
def chainfor(tc):
    return next((c for c in params if c.tradingClass == tc and c.exchange == "SMART"), None)
cw, cm = chainfor("SPXW"), chainfor("SPX")

exps = []
for e in sorted(cw.expirations)[:N_WEEKLY]:  exps.append(("SPXW", e))
for e in sorted(cm.expirations)[:N_MONTHLY]: exps.append(("SPX", e))
grid = [k for k in sorted(set(cw.strikes) | set(cm.strikes))
        if LO*spot <= k <= HI*spot and k % STEP == 0]
print(f"expiries: {[e for _,e in exps]}")
print(f"{len(grid)} strikes {grid[0]:.0f}-{grid[-1]:.0f} x {len(exps)} exp "
      f"= ~{len(grid)*len(exps)*2} contracts\n")

agg = defaultdict(lambda: [0.,0.,0.,0.])   # strike -> [cOI,cGamma_sum,pOI,pGamma_sum]
for tc, exp in exps:
    cons = [Option("SPX", exp, k, r, "SMART", tradingClass=tc) for k in grid for r in ("C","P")]
    q = [c for c in ib.qualifyContracts(*cons) if c and getattr(c,"conId",None)]
    tks = [(c, ib.reqMktData(c, "100,101,104,106", snapshot=False)) for c in q
           for _ in [time.sleep(THROTTLE)]]
    ib.sleep(6)
    for c, tk in tks:
        g = getattr(tk.modelGreeks,"gamma",None) if tk.modelGreeks else None
        g = g if (g is not None and g==g) else 0.
        oi = tk.callOpenInterest if c.right=="C" else tk.putOpenInterest
        oi = oi if oi==oi else 0.
        a = agg[c.strike]
        if c.right=="C": a[0]+=oi; a[1]+=g*oi
        else:            a[2]+=oi; a[3]+=g*oi
    for c in q: ib.cancelMktData(c)
    print(f"  pulled {tc} {exp}")

ib.disconnect()

rows = []
for k in sorted(agg):
    coi,cgn,poi,pgn = agg[k]
    rows.append(dict(k=k, coi=coi, poi=poi,
                     cgex= cgn*100*spot*spot*1e-9,
                     pgex=-pgn*100*spot*spot*1e-9,
                     tgam=(cgn+pgn)))
def top(key, cond, n=8, rev=True):
    return sorted([r for r in rows if cond(r["k"])], key=lambda r:abs(r[key]), reverse=rev)[:n]

print("\n===== RAW OI WALLS =====")
print(" PUT OI below spot:", [(int(r['k']),int(r['poi'])) for r in top('poi',lambda k:k<spot)])
print(" CALL OI above spot:",[(int(r['k']),int(r['coi'])) for r in top('coi',lambda k:k>spot)])
print("\n===== GAMMA-NOTIONAL WALLS =====")
print(" put |GEX| below:", [(int(r['k']),round(r['pgex'],1)) for r in top('pgex',lambda k:k<spot)])
print(" call GEX above :", [(int(r['k']),round(r['cgex'],1)) for r in top('cgex',lambda k:k>spot)])

# candidates
PS_oi  = top('poi', lambda k:k<spot,1)[0]['k']
CR_oi  = top('coi', lambda k:k>spot,1)[0]['k']
PS_g   = top('pgex',lambda k:k<spot,1)[0]['k']
CR_g   = top('cgex',lambda k:k>spot,1)[0]['k']
HVL_g  = sorted(rows, key=lambda r:r['tgam'], reverse=True)[0]['k']   # max total gamma

print("\n================ CANDIDATE LEVELS vs MenthorQ ================")
print(f"                MenthorQ   OI-based   Gamma-based")
print(f"  Call Resist :   {MQ['CR']}       {int(CR_oi)}       {int(CR_g)}")
print(f"  Put Support :   {MQ['PS']}       {int(PS_oi)}       {int(PS_g)}")
print(f"  HVL(maxTgam):   {MQ['HVL']}                  {int(HVL_g)}")

# save profile
import csv
p = r"c:\Users\Admin\myquant\scratchpad\spx_oi_profile.csv"
with open(p,"w",newline="") as f:
    w=csv.writer(f); w.writerow(["strike","call_oi","put_oi","call_gex","put_gex","tot_gamma"])
    for r in rows: w.writerow([r['k'],int(r['coi']),int(r['poi']),
                               round(r['cgex'],2),round(r['pgex'],2),round(r['tgam'],6)])
print(f"\nprofile -> {p}")
