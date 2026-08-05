# Penny-exact CROSS-ASSET coverage: can each ES/NQ BL be reconstructed as
# source_level * fixed_ratio to the penny, across 200 days? Beats null?
import json, csv, statistics
import numpy as np
GAM=json.load(open('scratchpad/bl_basket_gamma.json'))
def load_bl(sym):
    out={}
    with open(f'data/menthorq/{sym}_mq_blindspots_history.csv') as f:
        for row in csv.DictReader(f):
            out[row['date']]=[float(row[f'bl_{i}']) for i in range(1,11) if row.get(f'bl_{i}') not in (None,'','nan')]
    return out
LEVELS=['Call Resistance','Put Support','HVL','Call Resistance 0DTE','Put Support 0DTE','HVL 0DTE','Gamma Wall 0DTE','1D Min','1D Max']+[f'GEX {i}' for i in range(1,11)]
def spot(sym,dt):
    v=GAM.get(sym,{}).get(dt,{})
    a,b=v.get('1D Min'),v.get('1D Max')
    return (a+b)/2 if a and b else None

def fixed_ratio(target,src,dates):
    rs=[spot(target,dt)/spot(src,dt) for dt in dates if spot(target,dt) and spot(src,dt)]
    return statistics.median(rs) if rs else None

def coverage(target, sources, tol_pts, tol_rel=None):
    tbl=load_bl(target)
    dates=sorted(tbl)
    ratios={s:fixed_ratio(target,s,dates) for s in sources}
    ratios={s:r for s,r in ratios.items() if r}
    # real coverage: fraction of (day,BL) reconstructable
    def cov(get_levels_for_day):
        cov_bl=0; tot_bl=0; day_cov=[]
        for dt in dates:
            bls=tbl[dt]; tot_bl+=len(bls)
            # candidate reconstructed points
            cand=[]
            for s in ratios:
                lv=get_levels_for_day(s,dt)
                if not lv: continue
                for L in LEVELS:
                    val=lv.get(L)
                    if val and val>0: cand.append(val*ratios[s])
            cand=np.array(cand)
            hit=0
            for b in bls:
                if len(cand)==0: continue
                tol=tol_rel*b if tol_rel else tol_pts
                if np.min(np.abs(cand-b))<=tol: hit+=1
            cov_bl+=hit; day_cov.append(hit/len(bls) if bls else 0)
        return cov_bl/tot_bl, statistics.mean(day_cov)
    real,_=cov(lambda s,dt: GAM.get(s,{}).get(dt))
    # null: use source levels from a shuffled different date
    import random; random.seed(1)
    shuf=dates[:]; 
    nullv=[]
    for _ in range(20):
        random.shuffle(shuf)
        m={dt:shuf[i] for i,dt in enumerate(dates)}
        nv,_=cov(lambda s,dt: GAM.get(s,{}).get(m[dt]))
        nullv.append(nv)
    return real, statistics.mean(nullv), statistics.pstdev(nullv), len(ratios)

# all basket sources
SRC=list(GAM.keys())
for tgt in ['ES1!','NQ1!']:
    for tol in [0.05,0.25,1.0]:
        r,nm,ns,nsrc=coverage(tgt,SRC,tol)
        z=(r-nm)/(ns or 1e-9)
        print(f'{tgt} tol={tol:5} nsrc={nsrc}  real_cov={r:.3f}  null={nm:.3f}+-{ns:.3f}  z={z:.1f}')
