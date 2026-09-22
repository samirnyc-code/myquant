import json, random, itertools
from bl_fp import load_levels, spot, SYMS, ES_BL, NQ_BL, all_dates
random.seed(1)
DATE='2026-07-17'

def levs(lv):
    return [(k,v) for k,v in lv.items() if v is not None]

def test_midpoints(BLs, lv, tol=0.05):
    vals=[v for k,v in levs(lv)]
    names=[k for k,v in levs(lv)]
    hits=[]
    for bi,bl in enumerate(BLs):
        for i in range(len(vals)):
            for j in range(i+1,len(vals)):
                mid=(vals[i]+vals[j])/2
                if abs(mid-bl)<tol:
                    hits.append((bi,bl,names[i],names[j],mid,bl-mid))
    return hits

def test_offset(BLs, lv, tol=0.05):
    # BL = level + fixed offset? find any exact-decimal match to a level for some BL
    vals=[(k,v) for k,v in levs(lv)]
    hits=[]
    for bi,bl in enumerate(BLs):
        for k,v in vals:
            d=bl-v
            hits.append((bi,round(d,2),k,v))
    return hits

def frac(x): return round(x-int(x),2)

if __name__=='__main__':
    for tname,BLs,tsym in [('ES',ES_BL,'ES1!'),('NQ',NQ_BL,'NQ1!')]:
        lv=load_levels(tsym,DATE)
        print(f"\n===== {tname} =====")
        print("BL sorted:", sorted(BLs))
        print("spot:", spot(lv), "1DMin", lv['1D Min'], "1DMax", lv['1D Max'])
        print("BL fracs:", sorted([frac(b) for b in BLs]))
        print("\n-- exact midpoints of own-level pairs (tol .05) --")
        for h in test_midpoints(BLs,lv):
            print("  bl",h[0]+1,"=",h[1]," = mid(",h[2],",",h[3],")=",round(h[4],2),"resid",round(h[5],3))
        print("\n-- BL - own_level offsets: look for repeated identical offsets --")
        offs={}
        for bi,d,k,v in test_offset(BLs,lv):
            offs.setdefault(d,[]).append((bi+1,k,v))
        rep={d:x for d,x in offs.items() if len(x)>=3 and abs(d)>0.01}
        for d in sorted(rep,key=lambda z:-len(rep[z]))[:8]:
            print(f"  offset {d}: {len(rep[d])} BLs -> {rep[d]}")

    # Cross-asset midpoint test with spot-ratio scaling, real vs null
    print("\n\n===== CROSS-ASSET midpoint (spot-scaled) exact hits: REAL vs NULL =====")
    for tname,BLs,tspot in [('ES',ES_BL,7494.75),('NQ',NQ_BL,28768.25)]:
        Ldict={s:load_levels(s,DATE) for s in SYMS}
        def count_mid_hits(levelsets):
            tot=0
            for bl in BLs:
                found=False
                for vals in levelsets:
                    for i in range(len(vals)):
                        for j in range(i+1,len(vals)):
                            if abs((vals[i]+vals[j])/2-bl)<0.05:
                                found=True;break
                        if found:break
                    if found:break
                tot+= found
            return tot
        real_sets=[]
        for s in SYMS:
            r=tspot/spot(Ldict[s])
            real_sets.append([v*r for k,v in levs(Ldict[s])])
        real=count_mid_hits(real_sets)
        nulls=[]
        for _ in range(100):
            sets=[]
            for s in SYMS:
                d=random.choice([x for x in all_dates(s) if x!=DATE])
                olv=load_levels(s,d)
                if not olv or not spot(olv): continue
                r=tspot/spot(olv)
                sets.append([v*r for k,v in levs(olv)])
            nulls.append(count_mid_hits(sets))
        import statistics
        p=sum(1 for n in nulls if n>=real)/len(nulls)
        print(f"{tname}: REAL exact-midpoint hits={real}/10 | NULL mean={statistics.mean(nulls):.2f} max={max(nulls)} p={p:.3f}")
