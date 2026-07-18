import pandas as pd, numpy as np
df = pd.read_parquet('scratchpad/orats_SPX_2026-07-15.parquet')
for c in ['strike','gamma','callOpenInterest','putOpenInterest','dte']:
    df[c]=pd.to_numeric(df[c],errors='coerce')
SPOT=7572.40
g=df[df.dte>1].copy(); g['net']=g.gamma*(g.callOpenInterest-g.putOpenInterest)*100*SPOT
p=(g.groupby('strike')['net'].sum()/1e6).sort_index()
MQ=[7475,7500,7550,7575,7580,7620,7625,7645,7650,7675]

def score(name, strikes):
    s=sorted(int(x) for x in strikes)
    sh=sorted(set(s)&set(MQ))
    print(f'{name:34} {len(sh)}/10  mine={s}\n{"":34} MQ-only={sorted(set(MQ)-set(s))} MY-only={sorted(set(s)-set(MQ))}')

# variant A: local maxima of |GEX| on $5 grid (peak >= both neighbors), top10 by |GEX|, window +/-120
def local_peaks(prof):
    v=prof.values; k=prof.index.values; out=[]
    for i in range(1,len(v)-1):
        if abs(v[i])>=abs(v[i-1]) and abs(v[i])>=abs(v[i+1]):
            out.append((k[i],v[i]))
    return out
win=p[np.abs(p.index-SPOT)<=120]
peaks=local_peaks(win)
A=sorted(peaks,key=lambda t:-abs(t[1]))
A=[k for k,_ in A if k!=7600][:10]
score('A local-peak, top10 |GEX|, w=120', A)

# variant B: coarsen to $25 bins (sum), top10
b=g.copy(); b['bin']=(b.strike/25).round()*25
pb=(b.groupby('bin')['net'].sum()/1e6)
pbw=pb[np.abs(pb.index-SPOT)<=140]
B=[k for k in pbw.reindex(pbw.abs().sort_values(ascending=False).index).index if k!=7600][:10]
score('B $25-bin sum, top10', B)

# variant C: local-peak but balance sides: top5 calls(>spot)+top5 puts(<spot) by |GEX|
above=[t for t in peaks if t[0]>SPOT and t[0]!=7600]
below=[t for t in peaks if t[0]<SPOT]
C=[k for k,_ in sorted(above,key=lambda t:-abs(t[1]))[:5]]+[k for k,_ in sorted(below,key=lambda t:-abs(t[1]))[:5]]
score('C peak, top5 above + top5 below', C)

# variant D: local peak, min-spacing 15 greedy by |GEX|
cand=sorted(local_peaks(p[np.abs(p.index-SPOT)<=140]),key=lambda t:-abs(t[1]))
sel=[]
for k,v in cand:
    if k==7600: continue
    if all(abs(k-s)>=15 for s in sel): sel.append(k)
    if len(sel)==10: break
score('D peak, min-spacing 15, top10', sel)
print('\nMQ set:', MQ)
