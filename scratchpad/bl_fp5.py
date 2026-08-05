import json, random
from bl_fp import ES_BL, NQ_BL
PROXY=json.load(open(r'C:\Users\Admin\myquant\scratchpad\bl_proxy_gamma_20260717.json'))
random.seed(11)

def proxy_levels(sym):
    d=PROXY[sym]; skip={'ticker','timestamp','frequency'}
    return [v for k,v in d.items() if k not in skip and isinstance(v,(int,float)) and v>0]

def best_ratio_hits(BLs, levels, tol=0.05):
    """Scan candidate ratios = every BL/level; for each, count DISTINCT BLs hitting some level*r within tol.
    Return (max_distinct_bls, best_r)."""
    cands=set()
    for bl in BLs:
        for v in levels:
            cands.add(bl/v)
    best=0; bestr=None
    for r in cands:
        hit=set()
        for bi,bl in enumerate(BLs):
            for v in levels:
                if abs(v*r-bl)<tol:
                    hit.add(bi); break
        if len(hit)>best: best=len(hit); bestr=r
    return best,bestr

def rand_bls(BLs):
    lo,hi=min(BLs),max(BLs)
    return [round(random.uniform(lo,hi),2) for _ in BLs]

if __name__=='__main__':
    for tname,BLs,proxies in [('ES',ES_BL,['SPY','SPX','DIA','IWM','GLD']),
                              ('NQ',NQ_BL,['QQQ','NDX','SMH','XLK','DIA'])]:
        print(f"\n===== {tname}: best-single-ratio EXACT(<.05) BL reproduction, REAL vs NULL =====")
        for px in proxies:
            lv=proxy_levels(px)
            real,rr=best_ratio_hits(BLs,lv)
            nulls=[best_ratio_hits(rand_bls(BLs),lv)[0] for _ in range(300)]
            p=sum(1 for n in nulls if n>=real)/len(nulls)
            import statistics
            print(f"  {px:5} REAL={real}/10 @r={rr:.4f} | NULL mean={statistics.mean(nulls):.2f} max={max(nulls)} p(null>=real)={p:.3f}")

    # Also: pooled cluster-centroid (V2) test — combine SEVERAL proxies into ES space via spot ratio,
    # then for each BL count nearby mapped levels ("overlap"); is BL a centroid of a dense cluster?
    print("\n===== V2 overlap-centroid: are BLs at LOCAL MAXIMA of cross-proxy level density? REAL vs NULL =====")
    def spot(sym): d=PROXY[sym]; return (d['max_1d']+d['min_1d'])/2
    for tname,BLs,tspot,proxies in [
        ('ES',ES_BL,7494.75,['SPY','SPX','DIA','IWM','QQQ','NDX','GLD','SMH','XLK']),
        ('NQ',NQ_BL,28768.25,['QQQ','NDX','SMH','XLK','SPY','SPX','IWM'])]:
        mapped=[]
        for px in proxies:
            r=tspot/spot(px)
            mapped+=[v*r for v in proxy_levels(px)]
        mapped.sort()
        def density(x,bw): return sum(1 for m in mapped if abs(m-x)<bw)
        bw = (max(BLs)-min(BLs))/40
        real=[density(bl,bw) for bl in BLs]
        import statistics
        realmean=statistics.mean(real)
        nulls=[statistics.mean([density(x,bw) for x in rand_bls(BLs)]) for _ in range(300)]
        p=sum(1 for n in nulls if n>=realmean)/len(nulls)
        print(f"  {tname}: mean cross-proxy density@BL REAL={realmean:.2f} | NULL mean={statistics.mean(nulls):.2f} p(null>=real)={p:.3f} (bw={bw:.1f})")
