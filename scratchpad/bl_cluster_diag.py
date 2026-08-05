"""Diagnostics: does OVERLAP-ranking add value beyond 'gamma levels exist',
and are predicted centroids degenerate? Uses best config idx/all/TOL=20."""
import statistics as st, random, math
from bl_cluster_model import (load_bl, spot, mapped_pool, cluster, predict,
                              med_matched, BASKETS, LEVELSETS, BASKET, summ)

TARGET, SUB, LV, TOL = "ES1!", BASKETS["idx"], LEVELSETS["all"], 20
bl = load_bl(TARGET)
dates = sorted(set(bl) & set(BASKET[TARGET]))
rng = random.Random(1)

# A) top-10-by-overlap vs 10 RANDOM clusters vs 10 clusters by SIZE(pts) only
real_ov, real_rand, real_big, nulls = [], [], [], []
spread_pred, spread_bl = [], []
for date in dates:
    sp = spot(TARGET, date); acts = bl.get(date)
    if not sp or not acts: continue
    pool = mapped_pool(SUB, LV, TARGET, sp, date)
    if len(pool) < 15: continue
    cl = cluster(pool, TOL)
    if len(cl) < 10: continue
    ov = sorted(cl, key=lambda x: (x[1], x[2]), reverse=True)[:10]
    big = sorted(cl, key=lambda x: (x[2], x[1]), reverse=True)[:10]
    rc = rng.sample(cl, 10)
    real_ov.append(med_matched(acts, [c[0] for c in ov]))
    real_big.append(med_matched(acts, [c[0] for c in big]))
    real_rand.append(med_matched(acts, [c[0] for c in rc]))
    lo, hi = min(acts), max(acts)
    nd = [med_matched([rng.uniform(lo, hi) for _ in range(10)], [c[0] for c in ov]) for _ in range(50)]
    nulls.append(st.mean(nd))
    spread_pred.append(max(c[0] for c in ov) - min(c[0] for c in ov))
    spread_bl.append(hi - lo)

n = len(real_ov)
print(f"n={n} sessions  (ES, idx/all/TOL20)")
print(f"  top-10 by OVERLAP   : {st.mean(real_ov):.2f}pt")
print(f"  top-10 by SIZE(pts) : {st.mean(real_big):.2f}pt")
print(f"  10 RANDOM clusters  : {st.mean(real_rand):.2f}pt")
print(f"  NULL (rand pts)     : {st.mean(nulls):.2f}pt")
# paired: overlap vs random-cluster
d1 = [a-b for a,b in zip(real_ov, real_rand)]
t1 = st.mean(d1)/(st.pstdev(d1)/math.sqrt(n))
print(f"  overlap vs random-cluster: diff {st.mean(d1):+.2f}pt  t={t1:+.1f}  "
      f"({'overlap better' if t1<-2 else 'NO edge from overlap ranking' if abs(t1)<2 else 'random better'})")
print(f"  predicted-centroid span: {st.mean(spread_pred):.0f}pt   BL band span: {st.mean(spread_bl):.0f}pt")
print(f"  n clusters/day avg: coverage of band = {100*st.mean([min(a,b)/b for a,b in zip(spread_pred,spread_bl)]):.0f}%")

# B) how many predicted centroids land within X pt of SOME actual BL (hit rate)
for THR in (3, 5, 10):
    hits = []
    for date in dates:
        sp = spot(TARGET, date); acts = bl.get(date)
        if not sp or not acts: continue
        pool = mapped_pool(SUB, LV, TARGET, sp, date)
        if len(pool) < 15: continue
        pred = [c[0] for c in predict(pool, TOL)]
        if len(pred) < 10: continue
        h = sum(1 for c in pred if min(abs(c-a) for a in acts) <= THR)
        hits.append(h)
    print(f"  pred centroids within {THR:>2}pt of an actual BL: {st.mean(hits):.1f}/10")
