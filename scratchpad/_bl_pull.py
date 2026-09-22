import sys, json
sys.path.insert(0,'scripts')
from mq_api import MQ
mq=MQ()
out={}
def tryget(k,fn):
    try:
        out[k]=fn(); print('OK',k, 'type',type(out[k]).__name__)
    except Exception as e:
        out[k]='ERR:%r'%e; print('ERR',k,e)
tryget('ps_ES',lambda:mq.per_strike('ES1!'))
tryget('ps_NQ',lambda:mq.per_strike('NQ1!'))
tryget('mx_ES',lambda:mq.matrix('ES1!'))
tryget('mx_NQ',lambda:mq.matrix('NQ1!'))
tryget('met_ES',lambda:mq.metrics('ES1!'))
tryget('vi_ES',lambda:mq.vol_insights('ES1!'))
tryget('vi_NQ',lambda:mq.vol_insights('NQ1!'))
json.dump(out,open('scratchpad/bl_live_pull.json','w'))
print('saved')
