import json, csv, random, sys
import numpy as np
from clust import cluster_days
random.seed(42); np.random.seed(42)
GAM = json.load(open('scratchpad/bl_basket_gamma.json'))
def load_bl(sym):
    out={}
    try:
        with open(f'data/menthorq/{sym}_mq_blindspots_history.csv') as f:
            for row in csv.DictReader(f):
                vals=[float(row[f'bl_{i}']) for i in range(1,11) if row.get(f'bl_{i}') not in (None,'','nan')]
                out[row['date']]=vals
    except FileNotFoundError: pass
    return out
TARGETS=['ES1!','NQ1!','SPY','QQQ','SPX','NDX','IWM','RUT','RTY1!','YM1!','AAPL','MSFT','NVDA','AMZN','GOOG','META','TSLA','CL1!','GC1!']
BL={s:load_bl(s) for s in TARGETS}
LEVELS=['Call Resistance','Put Support','HVL','Call Resistance 0DTE','Put Support 0DTE','HVL 0DTE','Gamma Wall 0DTE','1D Min','1D Max']+[f'GEX {i}' for i in range(1,11)]

def scan(target, rel=0.0001, nulls=20):
    tbl=BL.get(target,{})
    results=[]
    for A in GAM:
        for L in LEVELS:
            dts=[];lvs=[];blss=[]
            for dt,bls in tbl.items():
                lv=GAM.get(A,{}).get(dt,{}).get(L)
                if lv and lv>0 and bls:
                    dts.append(dt);lvs.append(lv);blss.append(bls)
            nd=len(dts)
            if nd<40: continue
            didx={dt:k for k,dt in enumerate(dts)}
            rdates=[];rrat=[]
            for k,(lv,bls) in enumerate(zip(lvs,blss)):
                for b in bls: rdates.append(k); rrat.append(b/lv)
            rdates=np.array(rdates); rrat=np.array(rrat,dtype=float)
            real,rr=cluster_days(rdates,rrat,rel)
            lvarr=np.array(lvs)
            blss_np=[np.array(b,dtype=float) for b in blss]
            nullsc=[]
            for _ in range(nulls):
                perm=np.random.permutation(nd)
                nd_=[];nr_=[]
                for k in range(nd):
                    lv=lvarr[perm[k]]
                    for b in blss[k]: nd_.append(k); nr_.append(b/lv)
                nc,_=cluster_days(np.array(nd_),np.array(nr_,dtype=float),rel)
                nullsc.append(nc)
            nm=float(np.mean(nullsc)); ns=float(np.std(nullsc)) or 1e-9
            z=(real-nm)/ns
            results.append((A,L,nd,real,round(rr,5),round(nm,1),int(np.max(nullsc)),round(z,2)))
    results.sort(key=lambda x:-x[7])
    return results
tgts=sys.argv[1:] or ['ES1!','NQ1!']
for tgt in tgts:
    print('='*74); print('TARGET',tgt,'ndays',len(BL[tgt]))
    res=scan(tgt)
    print(f'{"src":6} {"level":18} {"nd":3} {"real":4} {"ratio":11} {"nullmu":6} {"nmax":4} {"z":6}')
    for r in res[:15]: print(f'{r[0]:6} {r[1]:18} {r[2]:3} {r[3]:4} {str(r[4]):11} {r[5]:6} {r[6]:4} {r[7]:6}')
