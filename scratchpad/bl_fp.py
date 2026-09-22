import json, itertools, random, os
from collections import defaultdict

BASE=r'C:\Users\Admin\myquant\data\menthorq'
SYMS=['ES1!','NQ1!','RTY1!','GC1!','CL1!','AAPL','MSFT','NVDA','AMZN','GOOGL','META','TSLA']

def load_levels(sym, date):
    fn=os.path.join(BASE,f'{sym}_mq_levels_history_raw.jsonl')
    with open(fn) as f:
        for line in f:
            d=json.loads(line)
            if d['item']['date']==date:
                lv={}
                for block in d['item']['levels']:
                    if block['level_type']=='gamma_levels':
                        for e in block['level_values']:
                            lv[e['name']]=e['value']
                return lv
    return None

def all_dates(sym):
    fn=os.path.join(BASE,f'{sym}_mq_levels_history_raw.jsonl')
    out=[]
    with open(fn) as f:
        for line in f:
            out.append(json.loads(line)['item']['date'])
    return out

ES_BL=[7579.32,7427.49,7566.74,7484.72,7835.74,7471.50,7246.19,7279.90,7603.29,7615.64]
NQ_BL=[29090.25,28504.10,29463.36,29228.17,28892.27,28327.97,29300.79,27936.18,29048.15,29489.09]

def spot(lv):
    if lv and '1D Min' in lv and '1D Max' in lv:
        return (lv['1D Min']+lv['1D Max'])/2.0
    return None

if __name__=='__main__':
    date='2026-07-17'
    L={s:load_levels(s,date) for s in SYMS}
    print("=== spots (1DMin+Max)/2 ===")
    for s in SYMS:
        print(f"{s:6} spot={spot(L[s])}  nlevels={len(L[s])}")
    print()
    print("ES own levels:", {k:v for k,v in L['ES1!'].items()})
    print()
    print("NQ own levels:", {k:v for k,v in L['NQ1!'].items()})
