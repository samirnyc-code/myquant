import json, os
import numpy as np

SYMS=['ES1!','NQ1!','RTY1!','GC1!','CL1!','AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA']
STRUCT={'Call Resistance','Put Support','HVL','Gamma Wall 0DTE','Call Resistance 0DTE','Put Support 0DTE','HVL 0DTE'}
STRUCT_CORE={'Call Resistance','Put Support','HVL','Gamma Wall 0DTE'}

BL={
 'ES1!':[7579.32,7427.49,7566.74,7484.72,7835.74,7471.50,7246.19,7279.90,7603.29,7615.64],
 'NQ1!':[29090.25,28504.10,29463.36,29228.17,28892.27,28327.97,29300.79,27936.18,29048.15,29489.09],
}
SPOT={'ES1!':7494.75,'NQ1!':28768.25}

def load_last(sym):
    last=None
    with open(f'data/menthorq/{sym}_mq_levels_history_raw.jsonl') as fh:
        for line in fh: last=line
    return json.loads(last)['item']

def levels_of(item):
    for l in item['levels']:
        if l['level_type']=='gamma_levels':
            return {v['name']:v['value'] for v in l['level_values']}
    return {}

data={s:levels_of(load_last(s)) for s in SYMS}
def assetspot(lv):
    return (lv['1D Min']+lv['1D Max'])/2

# Build structural pool mapped into target
def pool_for(target, core_only=True):
    tspot=SPOT[target]
    names=STRUCT_CORE if core_only else STRUCT
    pool=[]
    for s in SYMS:
        lv=data[s]; asp=assetspot(lv)
        r=tspot/asp
        for name in names:
            if name in lv and lv[name] is not None:
                pool.append((lv[name]*r, s, name))
    return pool

def residuals(target, core_only=True):
    pool=pool_for(target,core_only)
    vals=np.array([p[0] for p in pool])
    res=[]
    for bl in BL[target]:
        i=int(np.argmin(np.abs(vals-bl)))
        res.append((bl, vals[i], bl-vals[i], pool[i][1], pool[i][2]))
    return res

for core in (True,False):
    print('='*70)
    print('CORE ONLY' if core else 'ALL STRUCT (incl 0DTE variants)')
    for t in ('ES1!','NQ1!'):
        print(f'--- {t} spot={SPOT[t]} ---')
        rs=residuals(t,core)
        for k,(bl,m,d,src,nm) in enumerate(rs,1):
            side='below' if bl<SPOT[t] else 'above'
            print(f'bl_{k:<2} {bl:>10.2f} match={m:>10.2f} resid={d:>8.2f} dist_spot={bl-SPOT[t]:>8.1f} {side:5} <- {src} {nm}')
        ds=[abs(r[2]) for r in rs]
        print(f'  median|resid|={np.median(ds):.2f} mean={np.mean(ds):.2f}')
