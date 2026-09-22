import numpy as np
def cluster_days(dates_int, ratios, rel=0.0001):
    order=np.argsort(ratios); r=ratios[order]; dd=dates_int[order]
    n=len(r); best=0; bestr=0.0
    from collections import defaultdict
    cnt=defaultdict(int); distinct=0; j=0
    for i in range(n):
        if j<i:
            j=i; cnt.clear(); distinct=0
        while j<n and r[j] <= r[i]*(1+rel):
            if cnt[dd[j]]==0: distinct+=1
            cnt[dd[j]]+=1; j+=1
        if distinct>best: best=distinct; bestr=r[(i+j)//2 if (i+j)//2<n else n-1]
        # remove i
        cnt[dd[i]]-=1
        if cnt[dd[i]]==0: distinct-=1
    return best,float(bestr)
