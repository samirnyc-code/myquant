import json
d=json.load(open('scratchpad/bl_live_pull.json'))
def peek(o,depth=0,maxlist=2):
    ind='  '*depth
    if isinstance(o,dict):
        for k,v in list(o.items())[:30]:
            if isinstance(v,(dict,list)):
                print(ind+str(k)+':',type(v).__name__,'len',len(v))
                peek(v,depth+1,maxlist)
            else:
                print(ind+str(k)+'=',repr(v)[:80])
    elif isinstance(o,list):
        print(ind+'[list len %d] sample:'%len(o))
        for e in o[:maxlist]:
            peek(e,depth+1,maxlist)
for k in ['ps_ES','mx_ES','met_ES','vi_ES']:
    print('\n########',k,'########')
    peek(d[k])
