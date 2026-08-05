import json, csv, statistics, random
import numpy as np
GAM=json.load(open('scratchpad/bl_basket_gamma.json'))
def load_bl(sym):
    out={}
    with open(f'data/menthorq/{sym}_mq_blindspots_history.csv') as f:
        for row in csv.DictReader(f):
            out[row['date']]=[float(row[f'bl_{i}']) for i in range(1,11) if row.get(f'bl_{i}') not in (None,'','nan')]
    return out
def spot(sym,dt):
    v=GAM.get(sym,{}).get(dt,{}); a,b=v.get('1D Min'),v.get('1D Max')
    return (a+b)/2 if a and b else None
PAIRS=[('Call Resistance','Put Support'),('1D Min','1D Max'),('Gamma Wall 0DTE','HVL'),
       ('Call Resistance 0DTE','Put Support 0DTE'),('Call Resistance','HVL'),('Put Support','HVL')]
def midtest(target,tol=0.10):
    tbl=load_bl(target); dates=sorted(tbl)
    ratios={}
    for s in GAM:
        rs=[spot(target,dt)/spot(s,dt) for dt in dates if spot(target,dt) and spot(s,dt)]
        if rs: ratios[s]=statistics.median(rs)
    def cov(mapfn):
        hit=tot=0
        for dt in dates:
            bls=tbl[dt]; cand=[]
            for s,r in ratios.items():
                lv=GAM.get(s,{}).get(mapfn(dt),{})
                for a,b in PAIRS:
                    if lv.get(a) and lv.get(b): cand.append((lv[a]+lv[b])/2*r)
            cand=np.array(cand)
            for x in bls:
                tot+=1
                if len(cand) and np.min(np.abs(cand-x))<=tol: hit+=1
        return hit/tot
    real=cov(lambda d:d)
    random.seed(5); nl=[]
    for _ in range(25):
        sh=dates[:]; random.shuffle(sh); m={d:sh[i] for i,d in enumerate(dates)}
        nl.append(cov(lambda d:m[d]))
    nm,ns=statistics.mean(nl),statistics.pstdev(nl) or 1e-9
    print(f'  {target} structural-midpoints (cross-asset, {len(ratios)} assets x {len(PAIRS)} pairs): real={real:.3f} null={nm:.3f}+-{ns:.3f} z={(real-nm)/ns:.1f}')
print('=== C) HYPOTHESIS 2: BL = midpoint of structural level pair, penny-exact ===')
for t in ['ES1!','NQ1!']: midtest(t)
