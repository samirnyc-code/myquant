import json
import numpy as np

def series(sym):
    d={}
    with open(f'data/menthorq/{sym}_mq_levels_history_raw.jsonl') as fh:
        for line in fh:
            it=json.loads(line)['item']
            lv=None
            for l in it['levels']:
                if l['level_type']=='gamma_levels':
                    lv={v['name']:v['value'] for v in l['level_values']}
            if lv and lv.get('1D Min') and lv.get('1D Max'):
                d[it['date']]=(lv['1D Min']+lv['1D Max'])/2   # last wins
    dts=sorted(d)
    return dts, np.array([d[x] for x in dts])

def rsi(x, n=14):
    d=np.diff(x[-(n+1):]); up=np.where(d>0,d,0); dn=np.where(d<0,-d,0)
    au=up.mean(); ad=dn.mean()
    return 100.0 if ad==0 else 100-100/(1+au/ad)

for sym in ('ES1!','NQ1!'):
    dts,m=series(sym); px=m[-1]
    print('='*60); print(sym,'uniq days',len(m),'last',dts[-1],'mid',round(px,2))
    for n in (5,10,20):
        print(f'  {n}d ret={ (px/m[-1-n]-1)*100:+.2f}%  dist_{n}dMA={px-m[-n:].mean():+.1f}pt ({(px/m[-n:].mean()-1)*100:+.2f}%)')
    print(f'  RSI14={rsi(m):.1f}   last6 mids {[round(v,1) for v in m[-6:]]}')
