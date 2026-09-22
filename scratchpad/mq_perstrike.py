import sys, json
sys.path.insert(0,"scripts")
from mq_api import MQ
mq = MQ()
ps = mq.per_strike("SPX","eod")
json.dump(ps, open("scratchpad/mq_perstrike.json","w"), indent=2, default=str)
print("keys:", list(ps.keys()) if isinstance(ps,dict) else type(ps))
# find the per-strike arrays
def find_strikes(d, path=""):
    if isinstance(d,dict):
        for k,v in d.items(): find_strikes(v, path+"."+k)
    elif isinstance(d,list) and d and isinstance(d[0],dict) and any("strike" in str(kk).lower() for kk in d[0]):
        print(f"\nARRAY at {path}: {len(d)} rows, sample keys={list(d[0].keys())}")
        strikes=[r.get('strike') for r in d if r.get('strike')]
        if strikes: print(f"  strike range {min(strikes)} .. {max(strikes)}")
find_strikes(ps)
