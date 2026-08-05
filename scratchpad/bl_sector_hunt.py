"""Sector-ETF hypothesis for MenthorQ Blind Spots (S75V).

Do ES (and NQ) Blind Spots sit on the gamma levels -- or the OVERLAP of gamma levels --
of SECTOR ETFs? Train first 140 sessions, TEST held-out last 60. REAL vs NULL, z/p.
"""
import json, csv, math, statistics as st
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MQ = ROOT / "data" / "menthorq"
BASKET = json.load(open(ROOT / "scratchpad" / "bl_basket_gamma.json"))

SECTORS = ["XLK","SMH","XLF","XLE","XLV","XLY","XLI","XLP","XLU","XLB","XLC","XLRE"]
BROAD   = ["SPY","QQQ"]
STRUCT  = ["Call Resistance","Put Support","HVL","Gamma Wall 0DTE"]
NONLEVEL = {"1D Min","1D Max"}
RNG = np.random.default_rng(42)
NDRAW = 400

def bl_rows(sym):
    out = {}
    f = MQ / f"{sym}_mq_blindspots_history.csv"
    with open(f, newline="") as fh:
        for r in csv.DictReader(fh):
            vals = [float(r[f"bl_{i}"]) for i in range(1,11) if r.get(f"bl_{i}")]
            if len(vals) == 10:
                # keep BOTH internal order (for index tests) and sorted
                out[r["date"]] = vals
    return out

def spot(sym, date):
    g = BASKET.get(sym, {}).get(date)
    if not g or "1D Min" not in g or "1D Max" not in g:
        return None
    return (g["1D Min"] + g["1D Max"]) / 2.0

def mapped_levels(sym, date, tgt_spot, which):
    """Return sym's gamma levels mapped into target (ES/NQ) price space by spot ratio."""
    g = BASKET.get(sym, {}).get(date)
    sp = spot(sym, date)
    if not g or not sp:
        return []
    r = tgt_spot / sp
    if which == "struct":
        names = STRUCT
    else:  # all levels except the 1D range bounds
        names = [k for k in g if k not in NONLEVEL]
    return [g[k]*r for k in names if g.get(k) is not None and g[k]==g[k]]

def med_nn(pts, pool):
    if len(pool)==0: return float("nan")
    pool = np.asarray(pool); pts=np.asarray(pts,dtype=float)
    d = np.abs(pts[:,None]-pool[None,:]).min(axis=1)
    return float(np.median(d))

def null_mednn(band, pool, k=NDRAW):
    lo,hi = band; w = hi-lo
    pool = np.asarray(pool)
    pts = lo + w*RNG.random((k,10))                     # (k,10)
    d = np.abs(pts[:,:,None]-pool[None,None,:]).min(axis=2)  # (k,10)
    meds = np.median(d,axis=1)
    return float(meds.mean()), float(meds.std() or 1e-9)

def agg(reals, nulls):
    """paired real-vs-null: win rate z (sign test) + paired t + per-session z."""
    reals=np.array(reals); nulls=np.array(nulls)
    m=~np.isnan(reals)&~np.isnan(nulls); reals=reals[m]; nulls=nulls[m]
    n=len(reals)
    if n<5: return None
    wins=int(np.sum(reals<nulls))
    zsign=(wins-n*0.5)/math.sqrt(n*0.25)
    diffs=reals-nulls
    t=diffs.mean()/(diffs.std(ddof=1)/math.sqrt(n)) if diffs.std()>0 else 0
    return dict(n=n, real=float(reals.mean()), null=float(nulls.mean()),
                ratio=float(reals.mean()/nulls.mean()), wins=wins, winrate=100*wins/n,
                z=zsign, t=t, meddiff=float(np.median(diffs)))

def split(dates):
    d=sorted(dates); return d[:140], d[140:]

# ============ SETUP: target = ES (and NQ) ============
def run_target(TGT, log):
    BL = bl_rows(TGT)
    dates = [d for d in BL if spot(TGT,d)]
    tr, te = split(dates)
    log.append(f"\n{'='*70}\nTARGET = {TGT}   (train {len(tr)} sessions, TEST {len(te)} sessions)\n{'='*70}")

    def target_spot(d): return spot(TGT,d)

    # ---------- TEST A: single-sector enrichment ----------
    log.append("\n[TEST A] Single-sector enrichment (median nearest-dist of 10 BL vs null)")
    log.append(f"{'sector':7s} {'set':7s} | {'in-sample':^30s} | {'OUT-OF-SAMPLE (last 60)':^30s}")
    log.append(f"{'':7s} {'':7s} | real  null  ratio  win%  z     | real  null  ratio  win%  z")
    Arank=[]
    for which in ["struct","all"]:
        for sec in SECTORS:
            res={}
            for tag,ds in [("tr",tr),("te",te)]:
                R,N=[],[]
                for d in ds:
                    ts=target_spot(d); bls=BL[d]
                    pool=mapped_levels(sec,d,ts,which)
                    if len(pool)<2: continue
                    band=(min(bls),max(bls))
                    R.append(med_nn(bls,pool))
                    N.append(null_mednn(band,pool)[0])
                res[tag]=agg(R,N)
            a,b=res.get("tr"),res.get("te")
            if a and b:
                if which=="struct": Arank.append((sec,a,b))
                log.append(f"{sec:7s} {which:7s} | {a['real']:5.1f} {a['null']:5.1f} {a['ratio']:5.2f} {a['winrate']:4.0f} {a['z']:+5.1f} | {b['real']:5.1f} {b['null']:5.1f} {b['ratio']:5.2f} {b['winrate']:4.0f} {b['z']:+5.1f}")
    # rank
    Arank.sort(key=lambda x:x[2]['ratio'])
    log.append("\n  Sector ranking by OUT-OF-SAMPLE ratio (struct set, lower=BL closer than null):")
    for sec,a,b in Arank:
        flag = "**" if (b['ratio']<1 and b['z']>1.6) else "  "
        log.append(f"   {flag} {sec:6s} OOS ratio {b['ratio']:.2f} z {b['z']:+.1f} winrate {b['winrate']:.0f}%  (IS ratio {a['ratio']:.2f} z {a['z']:+.1f})")

    # ---------- TEST B: sector OVERLAP ----------
    log.append("\n[TEST B] Sector OVERLAP: do BL land where MULTIPLE sectors agree?")
    # For each BL, count distinct sectors with a mapped STRUCT level within TOL.
    def overlap_analysis(ds, tol_frac):
        # correlation of overlap-count with bl internal index; real vs null overlap
        real_ov, null_ov = [], []
        idx_ov = []  # (internal_index 1..10, overlap_count)
        for d in ds:
            ts=target_spot(d); bls_int=BL[d]  # internal order
            tol = tol_frac*ts
            # per-sector mapped struct levels
            secpools={sec:mapped_levels(sec,d,ts,"struct") for sec in SECTORS}
            secpools={k:v for k,v in secpools.items() if v}
            if len(secpools)<6: continue
            band=(min(bls_int),max(bls_int))
            def ov_count(p):
                return sum(1 for v in secpools.values() if min(abs(np.array(v)-p))<=tol)
            # real
            ovs=[ov_count(p) for p in bls_int]
            real_ov.append(np.mean(ovs))
            for i,p in enumerate(bls_int):
                idx_ov.append((i+1, ov_count(p)))
            # null: random pts
            lo,hi=band
            nulldraw=[]
            for _ in range(50):
                pts=lo+(hi-lo)*RNG.random(10)
                nulldraw.append(np.mean([ov_count(p) for p in pts]))
            null_ov.append(np.mean(nulldraw))
        return np.array(real_ov), np.array(null_ov), idx_ov
    for tag,ds in [("in-sample",tr),("OUT-OF-SAMPLE",te)]:
        ro,no,idxov=overlap_analysis(ds,0.001)  # tol=0.1% of spot (~7 ES pts)
        if len(ro)<5: continue
        diff=ro-no
        z=diff.mean()/(diff.std(ddof=1)/math.sqrt(len(diff)))
        # spearman-ish: corr of index vs overlap count
        idxov=np.array(idxov)
        if len(idxov)>10:
            # rank corr
            from scipy.stats import spearmanr
            rho,pv=spearmanr(idxov[:,0], idxov[:,1])
        else:
            rho,pv=float('nan'),float('nan')
        log.append(f"  {tag:14s}: mean sectors-overlapping-a-BL REAL {ro.mean():.2f} vs NULL {no.mean():.2f}  (z={z:+.1f}, n={len(ro)})")
        log.append(f"  {tag:14s}: corr(bl_internal_index, overlap_count) rho={rho:+.3f} p={pv:.3g}  (neg => BL1 has most overlap)")

    # ---------- TEST C: do sectors ADD anything beyond SPY/QQQ? ----------
    log.append("\n[TEST C] Sectors beyond SPY/QQQ: nearest-dist of BL, {SPY,QQQ} vs {SPY,QQQ+sectors}")
    for which in ["struct","all"]:
        for tag,ds in [("in-sample",tr),("OUT-OF-SAMPLE",te)]:
            base_R, both_R, nullR = [], [], []
            for d in ds:
                ts=target_spot(d); bls=BL[d]
                basepool=[]
                for s in BROAD: basepool+=mapped_levels(s,d,ts,which)
                secpool=[]
                for s in SECTORS: secpool+=mapped_levels(s,d,ts,which)
                if len(basepool)<2 or len(secpool)<2: continue
                bothpool=basepool+secpool
                band=(min(bls),max(bls))
                base_R.append(med_nn(bls,basepool))
                both_R.append(med_nn(bls,bothpool))
                nullR.append(null_mednn(band,bothpool)[0])
            base_R=np.array(base_R); both_R=np.array(both_R); nullR=np.array(nullR)
            if len(base_R)<5: continue
            # Does adding sectors improve? paired base vs both
            d1=base_R-both_R  # positive => both is closer (improvement)
            zimp=d1.mean()/(d1.std(ddof=1)/math.sqrt(len(d1))) if d1.std()>0 else 0
            # NOTE bothpool always >= denser so will trivially be closer; report vs DENSITY-matched null too
            log.append(f"  {which:6s} {tag:14s}: SPYQQQ med-NN {base_R.mean():5.1f} | +sectors {both_R.mean():5.1f} | null(dense) {nullR.mean():5.1f}")
            log.append(f"  {which:6s} {tag:14s}: adding sectors improves by {(base_R.mean()-both_R.mean()):+.2f} pt (paired z={zimp:+.1f})  [caveat: denser pool trivially closer]")

    # ---------- TEST C-fair: density-matched. Sectors-only vs same-count SPY/QQQ-jittered null ----------
    log.append("\n[TEST C-fair] Density-matched: are sector levels closer than the SAME NUMBER of random levels?")
    for tag,ds in [("in-sample",tr),("OUT-OF-SAMPLE",te)]:
        secR, nullR = [], []
        for d in ds:
            ts=target_spot(d); bls=BL[d]
            secpool=[]
            for s in SECTORS: secpool+=mapped_levels(s,d,ts,"struct")
            if len(secpool)<8: continue
            band=(min(bls),max(bls)); n=len(secpool)
            secR.append(med_nn(bls,secpool))
            # null: n random levels in an extended band (spot +/- band)
            lo,hi=band
            draws=[]
            for _ in range(100):
                fake=lo+(hi-lo)*RNG.random(n)
                draws.append(med_nn(bls,fake))
            nullR.append(np.mean(draws))
        r=agg(secR,nullR)
        if r:
            log.append(f"  {tag:14s}: sector-struct pool med-NN REAL {r['real']:.1f} vs same-count NULL {r['null']:.1f} ratio {r['ratio']:.2f} win {r['winrate']:.0f}% z {r['z']:+.1f} t {r['t']:+.1f}")

    # ---------- TEST C2 (cleanest): base=SPY+QQQ; adding REAL sector levels vs adding SAME COUNT random ----------
    log.append("\n[TEST C2] Cleanest control: add REAL sector levels to SPY+QQQ vs add the SAME # of RANDOM levels")
    for which in ["struct","all"]:
        for tag,ds in [("in-sample",tr),("OUT-OF-SAMPLE",te)]:
            realR, randR = [], []
            for d in ds:
                ts=target_spot(d); bls=BL[d]
                base=[]
                for s in BROAD: base+=mapped_levels(s,d,ts,which)
                sec=[]
                for s in SECTORS: sec+=mapped_levels(s,d,ts,which)
                if len(base)<2 or len(sec)<2: continue
                band=(min(bls),max(bls)); lo,hi=band; K=len(sec)
                realR.append(med_nn(bls, base+sec))
                # add K random levels drawn across band, avg over draws
                dd=[med_nn(bls, base+list(lo+(hi-lo)*RNG.random(K))) for _ in range(60)]
                randR.append(np.mean(dd))
            r=agg(realR,randR)
            if r:
                verdict="sectors ADD signal" if (r['ratio']<1 and r['z']>2) else "NO gain over random"
                log.append(f"  {which:6s} {tag:14s}: base+REALsectors {r['real']:.2f} vs base+RANDOM {r['null']:.2f}  ratio {r['ratio']:.2f} win {r['winrate']:.0f}% z {r['z']:+.1f}  => {verdict}")

    # ---------- TEST D (gold-standard null): DAY-SHUFFLE. Same pool structure, WRONG day. ----------
    # Preserves each pool's clustering/density exactly; only breaks today's alignment.
    log.append("\n[TEST D] Day-shuffle null (preserves clustering): match BL to TODAY's vs OTHER-day's pool")
    def raw_pool(symlist, d, which):
        """raw sector levels + their spot, for re-mapping to another day."""
        out=[]
        for s in symlist:
            g=BASKET.get(s,{}).get(d); sp=spot(s,d)
            if not g or not sp: continue
            names=STRUCT if which=="struct" else [k for k in g if k not in NONLEVEL]
            for k in names:
                if g.get(k) is not None and g[k]==g[k]:
                    out.append((g[k]/sp))   # store as ratio-to-own-spot (dimensionless)
        return out   # multiply by target_spot(today) to map into target space
    for label,symlist in [("SECTORS",SECTORS),("SPY+QQQ",BROAD)]:
        for which in ["struct"]:
            for tag,ds in [("in-sample",tr),("OUT-OF-SAMPLE",te)]:
                ds=list(ds)
                realR, shufR = [], []
                raws={d:raw_pool(symlist,d,which) for d in ds}
                for i,d in enumerate(ds):
                    ts=target_spot(d); bls=BL[d]
                    if len(raws[d])<2: continue
                    real_pool=[x*ts for x in raws[d]]
                    realR.append(med_nn(bls, real_pool))
                    # 20 other-day draws
                    dd=[]
                    for _ in range(20):
                        od=ds[RNG.integers(len(ds))]
                        if od==d or len(raws[od])<2: continue
                        dd.append(med_nn(bls, [x*ts for x in raws[od]]))
                    if dd: shufR.append(np.mean(dd))
                    else: realR.pop()
                r=agg(realR,shufR)
                if r:
                    verdict="REAL day-alignment" if (r['ratio']<1 and r['z']>2) else "no day-specific alignment"
                    log.append(f"  {label:8s} {which:6s} {tag:14s}: today {r['real']:.2f} vs other-day {r['null']:.2f} ratio {r['ratio']:.2f} win {r['winrate']:.0f}% z {r['z']:+.1f} t {r['t']:+.1f} => {verdict}")
    return

def main():
    log=[]
    for TGT in ["ES1!","NQ1!"]:
        run_target(TGT, log)
    txt="\n".join(log)
    print(txt)
    (ROOT/"scratchpad"/"bl_sector_raw_out.txt").write_text(txt)

if __name__=="__main__":
    main()
