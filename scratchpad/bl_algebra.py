import csv, os, statistics as st, random, itertools, math
random.seed(7)
DIR='data/menthorq'
SYMS=['ES1!','NQ1!','RTY1!','YM1!','SPX','NDX','RUT','SPY','QQQ','IWM',
      'AAPL','MSFT','NVDA','AMZN','GOOG','META','TSLA','CL1!','GC1!']

def load(s):
    p=os.path.join(DIR,s+'_mq_blindspots_history.csv')
    if not os.path.exists(p): return {}
    d={}
    for r in csv.DictReader(open(p)):
        try:
            v=[float(r['bl_'+str(i)]) for i in range(1,11)]
        except (ValueError,KeyError):
            continue
        d[r['date']]=v
    return d

DATA={s:load(s) for s in SYMS}
# common dates sorted
alldates=sorted(set.intersection(*[set(DATA[s]) for s in ['ES1!','SPX','SPY','QQQ','NQ1!']]))
print("common ES/SPX/SPY/QQQ/NQ dates:",len(alldates), alldates[0], alldates[-1])
N=len(alldates); split=int(N*0.7)
TRAIN=alldates[:split]; TEST=alldates[split:]
print("train",len(TRAIN),"test",len(TEST))

def med(x): return st.median(x)

# ---------- TEST A: element-wise same-order fixed ratio (per pair) ----------
# For a target T and source S, per day: ratio_i = T_i/S_i (native order).
# If T is S scaled elementwise same order -> CV(ratio) ~ 0.
# metric: median over days of (stdev(ratio_i)/mean(ratio_i)).
def elementwise_cv(T,S,dates):
    cvs=[]
    for dt in dates:
        if dt not in T or dt not in S: continue
        r=[T[dt][i]/S[dt][i] for i in range(10) if S[dt][i]!=0]
        if len(r)<10: continue
        m=st.mean(r)
        cvs.append(st.pstdev(r)/m if m else 1)
    return med(cvs) if cvs else None, len(cvs)

print("\n=== TEST A: element-wise same-order ratio consistency (target=ES1!) ===")
print("(low CV => ES BL is that instrument's BL x single per-day ratio, SAME index order)")
resA=[]
for s in SYMS:
    if s=='ES1!': continue
    cv,n=elementwise_cv(DATA['ES1!'],DATA[s],alldates)
    if cv is not None: resA.append((cv,s,n))
for cv,s,n in sorted(resA):
    print(f"  {s:6s} CV={cv:.2e}  n={n}")

# ---------- TEST B: matched-set distance (sorted) with best fixed ratio, OOS ----------
# Fit ratio r (and offset) on TRAIN by minimizing median matched abs dist between sorted sets;
# apply to TEST. Compare to NULL (source from a different random day).
def sortset(v): return sorted(v)
def matched_dist(T,Sconv):
    # both length10 sorted; mean abs elementwise after sort
    a=sorted(T); b=sorted(Sconv)
    return st.mean([abs(a[i]-b[i]) for i in range(10)])

def fit_ratio(T,S,dates):
    # ratio that best maps S sorted onto T sorted, elementwise, least squares through origin
    num=den=0
    for dt in dates:
        if dt not in T or dt not in S: continue
        a=sorted(T[dt]); b=sorted(S[dt])
        for i in range(10):
            num+=a[i]*b[i]; den+=b[i]*b[i]
    return num/den if den else 0

def eval_pair(target,source,scale='ratio'):
    r=fit_ratio(DATA[target],DATA[source],TRAIN)
    real=[]; null=[]
    tdates=[d for d in TEST if d in DATA[target] and d in DATA[source]]
    for dt in tdates:
        conv=[x*r for x in DATA[source][dt]]
        real.append(matched_dist(DATA[target][dt],conv))
    # null: source from a shuffled different day
    for dt in tdates:
        od=random.choice([d for d in tdates if d!=dt])
        conv=[x*r for x in DATA[source][od]]
        null.append(matched_dist(DATA[target][dt],conv))
    # normalize by ES price scale
    return r, med(real), med(null), len(tdates)

print("\n=== TEST B: OOS matched-set median abs distance, ES1! target, fixed ratio from TRAIN ===")
print(f"{'source':7s} {'ratio':>10s} {'REAL':>8s} {'NULL':>8s}  real/null")
rowsB=[]
for s in SYMS:
    if s=='ES1!': continue
    try:
        r,real,null,n=eval_pair('ES1!',s)
        rowsB.append((real,s,r,null,n))
    except Exception as e:
        pass
for real,s,r,null,n in sorted(rowsB):
    print(f"{s:7s} {r:10.4f} {real:8.2f} {null:8.2f}  {real/null:6.3f}  n={n}")

# ---------- TEST C: element-wise (native order) OOS residual, best pair ----------
# For the winner(s), use PER-DAY ratio (exact) vs FIXED ratio (OOS) elementwise native order.
def elementwise_resid(target,source,dates,fixed=None):
    res=[]
    for dt in dates:
        if dt not in DATA[target] or dt not in DATA[source]: continue
        T=DATA[target][dt]; S=DATA[source][dt]
        if fixed is None:
            r=sum(T[i]*S[i] for i in range(10))/sum(S[i]*S[i] for i in range(10))
        else:
            r=fixed
        res.extend([abs(T[i]-S[i]*r) for i in range(10)])
    return med(res),len(res)

print("\n=== TEST C: ELEMENT-WISE native-order residual (ES1! target) ===")
for s in ['SPX','SPY','NDX','QQQ','NQ1!','RUT','IWM','YM1!','GC1!','CL1!']:
    # per-day exact ratio
    pd,_=elementwise_resid('ES1!',s,alldates,fixed=None)
    # fixed ratio fit on train, eval on test
    rfix=fit_ratio(DATA['ES1!'],DATA[s],TRAIN)  # note: sorted-fit; recompute elementwise fit
    # elementwise fixed ratio (native order) fit on train
    num=den=0
    for dt in TRAIN:
        if dt in DATA['ES1!'] and dt in DATA[s]:
            for i in range(10):
                num+=DATA['ES1!'][dt][i]*DATA[s][dt][i]; den+=DATA[s][dt][i]**2
    rfe=num/den if den else 0
    fx,_=elementwise_resid('ES1!',s,TEST,fixed=rfe)
    print(f"  ES vs {s:6s}: per-day-ratio resid={pd:8.3f} | fixed-ratio(OOS) resid={fx:8.3f}  r={rfe:.5f}")

# ---------- TEST D: is the ordering identical? (permutation check) ----------
print("\n=== TEST D: index-order preservation ES vs SPX / SPY (per-day ratio, native order) ===")
for s in ['SPX','SPY']:
    exact_days=0; tot=0
    for dt in alldates:
        if dt in DATA['ES1!'] and dt in DATA[s]:
            tot+=1
            r=DATA['ES1!'][dt][0]/DATA[s][dt][0]
            if all(abs(DATA['ES1!'][dt][i]-DATA[s][dt][i]*r)<0.5 for i in range(10)):
                exact_days+=1
    print(f"  ES==SPX-scaled(native order) within 0.5pt using bl_1 ratio: {s} {exact_days}/{tot} days")

# ---------- TEST E: NQ family (QQQ/NDX) same structure? ----------
print("\n=== TEST E: NQ1! target element-wise CV vs sources ===")
resE=[]
for s in SYMS:
    if s=='NQ1!': continue
    cv,n=elementwise_cv(DATA['NQ1!'],DATA[s],alldates)
    if cv is not None: resE.append((cv,s,n))
for cv,s,n in sorted(resE)[:6]:
    print(f"  {s:6s} CV={cv:.2e} n={n}")

# ---------- TEST F: reverse direction & ratio drift ----------
print("\n=== TEST F: ES/SPX per-day ratio drift over 200d ===")
ratios=[]
for dt in alldates:
    if dt in DATA['ES1!'] and dt in DATA['SPX']:
        ratios.append((dt,DATA['ES1!'][dt][0]/DATA['SPX'][dt][0]))
print("  first",ratios[0][1].__round__(6),"last",ratios[-1][1].__round__(6),
      "min",round(min(r for _,r in ratios),6),"max",round(max(r for _,r in ratios),6))
