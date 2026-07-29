import json, numpy as np
idx = json.load(open(r'c:\Users\Admin\myquant-regime\data\annotations\book_review\bo_setup_index.json'))
all_pnl=[]; seq_pnl=[]; maxconc=0; multi_days=0
for date in sorted(idx):
    day=sorted(idx[date], key=lambda t:t[0])
    for t in day: all_pnl.append(t[4])
    last_exit=-1
    for t in day:
        ft,exb=t[0],t[6]
        if ft>=last_exit: seq_pnl.append(t[4]); last_exit=exb
    ev=[]
    for t in day: ev+=[(t[0],1),(t[6]+1,-1)]
    ev.sort(); c=0; peak=0
    for _,d in ev:
        c+=d; peak=max(peak,c)
    maxconc=max(maxconc,peak)
    if peak>1: multi_days+=1
def metr(us):
    us=np.array(us); net=us.sum(); w=us[us>0]; l=us[us<=0]; pf=w.sum()/-l.sum() if l.sum()<0 else 9.99
    eq=np.cumsum(us); dd=float((np.maximum.accumulate(eq)-eq).max())
    return f"n={len(us)} net=${round(net):,} $/yr=${round(net/5.04):,} PF={round(pf,2)} win={round(100*len(w)/len(us))}% maxDD=${round(dd):,} net/DD={round(net/dd,2)}"
print("ALL (overlap allowed):", metr(all_pnl))
print("1-at-a-time (no overlap):", metr(seq_pnl))
print(f"max concurrent positions: {maxconc}   days with overlap: {multi_days}/{len(idx)}")
