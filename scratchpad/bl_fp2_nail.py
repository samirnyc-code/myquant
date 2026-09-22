import json, csv, statistics, random
import numpy as np
GAM=json.load(open('scratchpad/bl_basket_gamma.json'))
def load_bl(sym):
    out={}
    with open(f'data/menthorq/{sym}_mq_blindspots_history.csv') as f:
        for row in csv.DictReader(f):
            out[row['date']]=[float(row[f'bl_{i}']) for i in range(1,11) if row.get(f'bl_{i}') not in (None,'','nan')]
    return out
LEVELS=['Call Resistance','Put Support','HVL','Call Resistance 0DTE','Put Support 0DTE','HVL 0DTE','Gamma Wall 0DTE','1D Min','1D Max']+[f'GEX {i}' for i in range(1,11)]

# ---- A) documented clean fixed ratios, penny-exact hit vs null ----
print('=== A) DOCUMENTED CLEAN RATIOS: penny-exact coverage vs null ===')
def clean_test(target,src,ratio,tol=0.10):
    tbl=load_bl(target); dates=sorted(tbl)
    def cov(mapfn):
        hit=tot=0
        for dt in dates:
            bls=tbl[dt]; lv=GAM.get(src,{}).get(mapfn(dt),{})
            cand=np.array([lv[L]*ratio for L in LEVELS if lv.get(L)])
            for b in bls:
                tot+=1
                if len(cand) and np.min(np.abs(cand-b))<=tol: hit+=1
        return hit/tot
    real=cov(lambda d:d)
    random.seed(3); nulls=[]
    for _ in range(30):
        sh=dates[:]; random.shuffle(sh); m={d:sh[i] for i,d in enumerate(dates)}
        nulls.append(cov(lambda d:m[d]))
    nm,ns=statistics.mean(nulls),statistics.pstdev(nulls) or 1e-9
    print(f'  {target} = {src} x {ratio:<7}: real_cov={real:.3f} null={nm:.3f}+-{ns:.3f} z={(real-nm)/ns:.1f}')
for t,s,r in [('ES1!','SPY',10.08),('ES1!','SPX',1.005),('ES1!','SPY',10.0),('NQ1!','QQQ',41.26),('NQ1!','NDX',1.005),('NQ1!','QQQ',41.34)]:
    clean_test(t,s,r)

# ---- B) odd-decimal signature: are BL fractional parts continuous or quantized? ----
print('\n=== B) FRACTIONAL-PART (cents) distribution of BL ===')
for tgt in ['ES1!','NQ1!','SPY','QQQ']:
    tbl=load_bl(tgt); allb=[b for v in tbl.values() for b in v]
    frac=np.array([round(b%1,4) for b in allb])
    cents=np.round(frac*100).astype(int)
    # how many distinct cent values, and % that are .00/.25/.50/.75 (quantized) vs arbitrary
    u=len(set(cents.tolist()))
    quant=np.mean(np.isin(cents,[0,25,50,75]))
    round25=np.mean(cents%25==0)
    print(f'  {tgt}: n={len(allb)} distinctCents={u}/100 pct@(.00/.25/.50/.75)={quant:.3f} pct@multiple-of-.25={round25:.3f}')
# reference: a round-level x clean-ratio would concentrate cents; continuous source -> ~uniform 100 values, quant~0.04
