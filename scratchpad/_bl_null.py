import json,random,statistics
random.seed(1)
d=json.load(open('scratchpad/bl_live_pull.json'))
bl={'ES':[7579.32,7427.49,7566.74,7484.72,7835.74,7471.50,7246.19,7279.90,7603.29,7615.64],
    'NQ':[29090.25,28504.10,29463.36,29228.17,28892.27,28327.97,29300.79,27936.18,29048.15,29489.09]}
spot={'ES':7494.75,'NQ':28768.25}

def surface(ps):
    strikes=ps['strikes']; c=ps['cells']
    agg={}
    for i,g in zip(c['strike_idx'],c['net_gex']): agg[i]=agg.get(i,0.0)+(g or 0.0)
    oi={}
    for i,cc,pp in zip(c['strike_idx'],c['oi_call'],c['oi_put']): oi[i]=oi.get(i,0.0)+(cc or 0)+(pp or 0)
    pts=sorted((strikes[i],agg[i],oi.get(i,0)) for i in agg)
    return pts

def interp_zc(pts):
    zc=[]
    for (x1,y1,_),(x2,y2,_) in zip(pts,pts[1:]):
        if (y1<0<y2) or (y1>0>y2):
            zc.append(x1+(0-y1)*(x2-x1)/(y2-y1))
    return zc

def nearest_med(targets,pool):
    return statistics.median(min(abs(t-p) for p in pool) for t in targets)

for sym in ['ES','NQ']:
    pts=surface(d['ps_%s'%sym]); sp=spot[sym]
    lo,hi=min(bl[sym])-50,max(bl[sym])+50
    # candidate pools restricted to band
    zc=[z for z in interp_zc(pts) if lo<=z<=hi]
    band_pts=[(x,g,oi) for (x,g,oi) in pts if lo<=x<=hi]
    # OI local minima
    oimin=[]
    for i in range(1,len(band_pts)-1):
        if band_pts[i][2]<=band_pts[i-1][2] and band_pts[i][2]<=band_pts[i+1][2]:
            oimin.append(band_pts[i][0])
    print('====',sym,'band',round(lo),round(hi),' #zc_signflip_in_band',len(zc),' #OImin',len(oimin))
    for label,pool in [('signflip_zc',zc),('OI_minima',oimin)]:
        if not pool: 
            print('  ',label,'empty'); continue
        real=nearest_med(bl[sym],pool)
        nulls=[nearest_med([random.uniform(min(bl[sym]),max(bl[sym])) for _ in range(10)],pool) for _ in range(2000)]
        p=sum(1 for n in nulls if n<=real)/len(nulls)
        print('   %-12s real_median_err=%6.2f  null_median=%6.2f  p(null<=real)=%.3f  poolsize=%d'%(
            label,real,statistics.median(nulls),p,len(pool)))
