import json
import numpy as np

SYMS=['ES1!','NQ1!','RTY1!','GC1!','CL1!','AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA']
STRUCT_CORE={'Call Resistance','Put Support','HVL','Gamma Wall 0DTE'}
BL={'ES1!':[7579.32,7427.49,7566.74,7484.72,7835.74,7471.50,7246.19,7279.90,7603.29,7615.64],
    'NQ1!':[29090.25,28504.10,29463.36,29228.17,28892.27,28327.97,29300.79,27936.18,29048.15,29489.09]}
SPOT={'ES1!':7494.75,'NQ1!':28768.25}
# momentum proxy (5d return %, down on 7/17 for both)
MOM5={'ES1!':-1.72,'NQ1!':-4.32}

def levels_of(sym):
    last=None
    with open(f'data/menthorq/{sym}_mq_levels_history_raw.jsonl') as fh:
        for line in fh: last=line
    it=json.loads(last)['item']
    for l in it['levels']:
        if l['level_type']=='gamma_levels':
            return {v['name']:v['value'] for v in l['level_values']}
data={s:levels_of(s) for s in SYMS}
aspot=lambda lv:(lv['1D Min']+lv['1D Max'])/2

def pool(target):
    r0=SPOT[target]; P=[]
    for s in SYMS:
        lv=data[s]; r=r0/aspot(lv)
        for n in STRUCT_CORE:
            if lv.get(n) is not None: P.append(lv[n]*r)
    return np.array(P)

def linfit(x,y):
    x=np.asarray(x,float); y=np.asarray(y,float)
    A=np.vstack([x,np.ones_like(x)]).T
    b,a=np.linalg.lstsq(A,y,rcond=None)[0]
    yh=b*x+a; ss=((y-yh)**2).sum(); st=((y-y.mean())**2).sum()
    return b,a,(1-ss/st if st>0 else 0)

for t in ('ES1!','NQ1!'):
    P=pool(t); res=[]; dsp=[]
    for bl in BL[t]:
        m=P[np.argmin(np.abs(P-bl))]; res.append(bl-m); dsp.append(bl-SPOT[t])
    res=np.array(res); dsp=np.array(dsp)
    above=(dsp>0).sum(); below=(dsp<0).sum()
    print('='*60); print(f'{t}  mom5d={MOM5[t]:+.2f}% (DOWN)   BL sides: {above} above / {below} below')
    print(f'  mean signed resid={res.mean():+.2f}  median|res|={np.median(np.abs(res)):.2f}')
    print(f'  BL extension: max above=+{dsp.max():.0f}  max below={dsp.min():.0f}  mean pos={dsp.mean():+.0f}')
    b,a,r2=linfit(dsp,res)
    print(f'  fit resid ~ dist_spot:  slope={b:+.4f} intcpt={a:+.2f} R2={r2:.3f}')
    b2,a2,r22=linfit(np.abs(dsp),res)
    print(f'  fit resid ~ |dist_spot|: slope={b2:+.5f} intcpt={a2:+.2f} R2={r22:.3f}')
    print(f'  resid values: {[round(float(v),1) for v in res]}')
