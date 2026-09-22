import json
d=json.load(open('scratchpad/bl_live_pull.json'))
bl={'ES':[7579.32,7427.49,7566.74,7484.72,7835.74,7471.50,7246.19,7279.90,7603.29,7615.64],
    'NQ':[29090.25,28504.10,29463.36,29228.17,28892.27,28327.97,29300.79,27936.18,29048.15,29489.09]}
spot={'ES':7494.75,'NQ':28768.25}

def surface(ps):
    strikes=ps['strikes']; c=ps['cells']
    si=c['strike_idx']; ng=c['net_gex']
    agg={}
    for i,g in zip(si,ng):
        agg[i]=agg.get(i,0.0)+(g or 0.0)
    pts=sorted((strikes[i],agg[i]) for i in agg)
    return pts

def zerocross(pts):
    zc=[]
    for a,b in zip(pts,pts[1:]):
        (x1,y1),(x2,y2)=a,b
        if y1==0: zc.append((x1,'exact'))
        if (y1<0<y2) or (y1>0>y2):
            xz=x1+(0-y1)*(x2-x1)/(y2-y1)
            zc.append((round(xz,2),'%+.0f->%+.0f'%(y1,y2)))
    return zc

for sym in ['ES','NQ']:
    ps=d['ps_%s'%sym]
    pts=surface(ps)
    zc=zerocross(pts)
    print('====',sym,'strikes',len(pts),'range',pts[0][0],'-',pts[-1][0],'spot',spot[sym])
    print('  #zerocrossings(aggregate):',len(zc))
    for z in zc: print('   zc',z)
    print('  BL sorted:',sorted(bl[sym]))
