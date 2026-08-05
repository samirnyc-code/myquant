import json
import numpy as np

def series(sym):
    dates=[]; mid=[]
    with open(f'data/menthorq/{sym}_mq_levels_history_raw.jsonl') as fh:
        for line in fh:
            it=json.loads(line)['item']
            lv=None
            for l in it['levels']:
                if l['level_type']=='gamma_levels':
                    lv={v['name']:v['value'] for v in l['level_values']}
            if lv and lv.get('1D Min') and lv.get('1D Max'):
                dates.append(it['date']); mid.append((lv['1D Min']+lv['1D Max'])/2)
    return dates, np.array(mid)

def rsi(x, n=14):
    d=np.diff(x); up=np.where(d>0,d,0); dn=np.where(d<0,-d,0)
    au=up[-n:].mean(); ad=dn[-n:].mean()
    if ad==0: return 100.0
    return 100-100/(1+au/ad)

for sym in ('ES1!','NQ1!'):
    dts,m=series(sym)
    print('='*60)
    print(sym, 'days=',len(m), 'last date', dts[-1], 'last mid', round(m[-1],2))
    px=m[-1]
    for n in (5,10,20):
        ret=(px/m[-1-n]-1)*100
        mean=m[-1-n:].mean()
        print(f'  {n}d return={ret:+.2f}%  dist_from_{n}d_mean={px-mean:+.1f}pt ({(px/mean-1)*100:+.2f}%)')
    print(f'  RSI14={rsi(m):.1f}')
    # normalized momentum sign
    print(f'  last 5 mids: {[round(v,1) for v in m[-5:]]}')
