import json, random
from bl_fp import ES_BL, NQ_BL

PROXY=json.load(open(r'C:\Users\Admin\myquant\scratchpad\bl_proxy_gamma_20260717.json'))
random.seed(7)

def proxy_levels(sym):
    d=PROXY[sym]
    skip={'ticker','timestamp','frequency'}
    return [(k,v) for k,v in d.items() if k not in skip and isinstance(v,(int,float))]

def proxy_spot(sym):
    d=PROXY[sym]; return (d['max_1d']+d['min_1d'])/2

# 1) IMPLIED-RATIO CLUSTERING: for each proxy, ratio=BL/level, cluster, find ratios hit by many BLs
def cluster(BLs, sym, relgap=3e-5):
    lv=proxy_levels(sym)
    ent=[]
    for bi,bl in enumerate(BLs):
        for name,val in lv:
            if val>0: ent.append((bl/val,bi,name,val,bl))
    ent.sort()
    clusters=[]; cur=[ent[0]]
    for e in ent[1:]:
        if abs(e[0]-cur[-1][0])/cur[-1][0]<relgap: cur.append(e)
        else: clusters.append(cur); cur=[e]
    clusters.append(cur)
    out=[]
    for c in clusters:
        bls=set(x[1] for x in c)
        if len(bls)>=2:
            out.append((sum(x[0] for x in c)/len(c),len(bls),c))
    out.sort(key=lambda z:-z[1])
    return out

# 2) FIXED-RATIO EXACT TEST: given proxy + ratio r, how many BLs hit some level*r within tol
def fixed_exact(BLs, sym, r, tol=0.05):
    lv=proxy_levels(sym)
    hits=[]
    for bi,bl in enumerate(BLs):
        for name,val in lv:
            if abs(val*r-bl)<tol:
                hits.append((bi+1,bl,name,val,val*r,bl-val*r))
    return hits

if __name__=='__main__':
    print("Proxy spots & clean ES/NQ ratios:")
    for s in PROXY:
        print(f"  {s:5} spot={proxy_spot(s):9.2f}  ES/={7494.75/proxy_spot(s):9.4f}  NQ/={28768.25/proxy_spot(s):9.4f}")

    for tname,BLs,proxies,cleanratios in [
        ('ES',ES_BL,['SPY','SPX','DIA'],{'SPY':[10.0,10.08],'SPX':[1.0,1.005],'DIA':[14.0]}),
        ('NQ',NQ_BL,['QQQ','NDX','SMH'],{'QQQ':[41.26,41.37],'NDX':[1.0,1.006],'SMH':[50.0]}),
    ]:
        print(f"\n{'='*70}\n{tname}  BL={sorted(BLs)}\n{'='*70}")
        for px in proxies:
            print(f"\n--- {px} implied-ratio clusters (>=2 BLs share ratio) ---")
            cl=cluster(BLs,px)
            for rmean,nbl,c in cl[:6]:
                bset=sorted(set(x[1]+1 for x in c))
                print(f"  r={rmean:.5f}  {nbl} BLs {bset}  ES/NQspot-ratio={7494.75/proxy_spot(px) if tname=='ES' else 28768.25/proxy_spot(px):.4f}")
                for x in c:
                    print(f"       bl{x[1]+1}={x[4]} / {x[3]}({x[2]}) = {x[0]:.5f}")
            # test clean fixed ratios
            for r in cleanratios.get(px,[]):
                h=fixed_exact(BLs,px,r,tol=0.05)
                h2=fixed_exact(BLs,px,r,tol=0.5)
                print(f"  fixed r={r}: exact(<.05)={len(h)} near(<.5)={len(h2)}")
                for x in h: print(f"       EXACT bl{x[0]}={x[1]} = {x[3]}({x[2]})*{r} = {x[4]:.2f} resid {x[5]:.3f}")
