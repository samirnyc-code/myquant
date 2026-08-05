import json, random
from collections import defaultdict
from bl_fp import load_levels, spot, SYMS, ES_BL, NQ_BL, all_dates

DATE='2026-07-17'
random.seed(42)

def get_levels_list(lv, include_derived=True):
    """Return list of (name,value) for an asset's gamma block."""
    out=[(k,v) for k,v in lv.items() if v is not None]
    return out

def implied_ratio_cluster(BLs, asset_levels, tol_ratio_frac=1e-4):
    """For each (BL, level) compute implied ratio. Cluster ratios; find clusters
    hit by >=2 distinct BLs. Return list of (ratio, [(bl_idx,level_name,resid)])."""
    entries=[]
    for bi,bl in enumerate(BLs):
        for name,val in asset_levels:
            if val<=0: continue
            r=bl/val
            entries.append((r,bi,name,val))
    entries.sort()
    # cluster by relative gap
    clusters=[]
    cur=[entries[0]]
    for e in entries[1:]:
        if abs(e[0]-cur[-1][0])/cur[-1][0] < tol_ratio_frac:
            cur.append(e)
        else:
            clusters.append(cur); cur=[e]
    clusters.append(cur)
    results=[]
    for c in clusters:
        bls=set(x[1] for x in c)
        if len(bls)>=2:
            rmean=sum(x[0] for x in c)/len(c)
            results.append((rmean,len(bls),c))
    results.sort(key=lambda x:-x[1])
    return results

def best_ratio_map(BLs, asset_levels, r):
    """Given fixed ratio r, map levels to target scale, find nearest for each BL."""
    mapped=[(name,val*r) for name,val in asset_levels]
    res=[]
    for bl in BLs:
        best=min(mapped,key=lambda m:abs(m[1]-bl))
        res.append((bl,best[0],best[1],bl-best[1]))
    return res

def run(target_name, BLs, target_spot):
    print(f"\n{'='*70}\n{target_name}: implied-ratio clustering per asset\n{'='*70}")
    L={s:load_levels(s,DATE) for s in SYMS}
    findings=[]
    for s in SYMS:
        lv=L[s]
        levels=get_levels_list(lv)
        rspot = target_spot/spot(lv) if spot(lv) else None
        clusters=implied_ratio_cluster(BLs, levels, tol_ratio_frac=5e-5)
        # exact-ish resid within cluster: how tight
        for rmean,nbl,c in clusters[:3]:
            resids=[]
            # for this ratio, compute nearest-level residual for ALL BLs
            m=best_ratio_map(BLs,levels,rmean)
            nexact=sum(1 for x in m if abs(x[3])<0.05)
            nnear=sum(1 for x in m if abs(x[3])<0.5)
            spot_close = (abs(rmean-rspot)/rspot<0.02) if rspot else False
            findings.append((s,rmean,nbl,nexact,nnear,rspot,spot_close,m))
    findings.sort(key=lambda x:(-x[3],-x[4]))
    print(f"{'asset':6} {'ratio':>10} {'#BLshareR':>9} {'#exact<.05':>10} {'#near<.5':>8} {'rspot':>9} {'spotmatch'}")
    for s,rmean,nbl,nexact,nnear,rspot,sc,m in findings[:15]:
        print(f"{s:6} {rmean:10.5f} {nbl:9d} {nexact:10d} {nnear:8d} {rspot:9.4f} {sc}")
    return findings,L

def null_test(target_name, BLs, target_spot, L, n_null=200):
    """Null: for each asset, use r=spot ratio, map levels, count exact/near matches.
    Compare real day vs random OTHER days for same asset."""
    print(f"\n--- NULL TEST ({target_name}): exact/near matches, real 7/17 vs random other days, r=spot ratio ---")
    for s in SYMS:
        lv=L[s]; rspot=target_spot/spot(lv)
        levels=get_levels_list(lv)
        m=best_ratio_map(BLs,levels,rspot)
        real_exact=sum(1 for x in m if abs(x[3])<0.05)
        real_near=sum(1 for x in m if abs(x[3])<0.5)
        real_medabs=sorted(abs(x[3]) for x in m)[len(m)//2]
        # null: other days
        dates=all_dates(s)
        others=[d for d in dates if d!=DATE]
        ne=[]; nn=[]; nmed=[]
        for _ in range(n_null):
            d=random.choice(others)
            olv=load_levels(s,d)
            if not olv or not spot(olv): continue
            ol=get_levels_list(olv)
            # scale that day's levels into target using THAT day's spot ratio (fair)
            rr=target_spot/spot(olv)
            mm=best_ratio_map(BLs,ol,rr)
            ne.append(sum(1 for x in mm if abs(x[3])<0.05))
            nn.append(sum(1 for x in mm if abs(x[3])<0.5))
            nmed.append(sorted(abs(x[3]) for x in mm)[len(mm)//2])
        avg=lambda a:sum(a)/len(a) if a else float('nan')
        p_exact=sum(1 for x in ne if x>=real_exact)/len(ne) if ne else float('nan')
        p_med=sum(1 for x in nmed if x<=real_medabs)/len(nmed) if nmed else float('nan')
        print(f"{s:6} rspot={rspot:8.4f} | REAL exact={real_exact} near={real_near} med={real_medabs:.2f} "
              f"|| NULL exact~{avg(ne):.2f} near~{avg(nn):.2f} med~{avg(nmed):.2f} "
              f"| p(exact>=real)={p_exact:.3f} p(med<=real)={p_med:.3f}")

if __name__=='__main__':
    fES,L=run('ES',ES_BL,7494.75)
    null_test('ES',ES_BL,7494.75,L)
    fNQ,L2=run('NQ',NQ_BL,28768.25)
    null_test('NQ',NQ_BL,28768.25,L2)
