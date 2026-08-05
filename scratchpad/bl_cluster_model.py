"""BL V2 overlap-clustering model — full basket, 200 days (S75V).

Hypothesis (MQ's own words): BL = ranges from highly correlated assets with strong
OVERLAPS; BL1 = most overlap. Test: are ES bl_1..bl_10 the top-10 overlap CLUSTERS
of the whole basket's gamma levels mapped into ES space?

Method: per day, map every basket asset's levels into target space by spot-ratio,
pool them, greedily cluster at tolerance TOL, score each cluster by #distinct assets,
take top-10 clusters -> predicted BL. Compare to actual BL (median matched dist) vs null.
Grid over {basket subset, level set, TOL}, config picked on TRAIN (first 140d),
reported OUT-OF-SAMPLE (last 60d). Ordering claim + NQ consistency.
"""
import json, csv, math, statistics as st, random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MQ = ROOT / "data" / "menthorq"
BASKET = json.load(open(ROOT / "scratchpad" / "bl_basket_gamma.json"))

STRUCT = ["Call Resistance", "Put Support", "HVL",
          "Call Resistance 0DTE", "Put Support 0DTE", "HVL 0DTE", "Gamma Wall 0DTE"]
GEX = [f"GEX {i}" for i in range(1, 11)]
LEVELSETS = {"structural": STRUCT, "+GEX": STRUCT + GEX, "all": STRUCT + GEX + ["1D Min", "1D Max"]}

IDX = ["SPX", "SPY", "QQQ", "NDX", "IWM", "RUT", "DIA"]
SECT = ["XLK", "SMH", "XLF", "XLE", "XLV", "XLY", "XLI", "XLP", "XLU", "XLB", "XLC", "XLRE"]
MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOG", "META", "TSLA"]
MACRO = ["VIX", "IBIT", "GLD", "USO", "TLT", "HYG", "GC1!", "CL1!"]
BASKETS = {
    "idx": IDX,
    "+sectors": IDX + SECT,
    "+mag7": IDX + SECT + MAG7,
    "all": IDX + SECT + MAG7 + MACRO,
}


def load_bl(sym):
    rows = {}
    p = MQ / f"{sym}_mq_blindspots_history.csv"
    with open(p, newline="") as f:
        for r in csv.DictReader(f):
            vals = [float(r[f"bl_{i}"]) for i in range(1, 11) if r.get(f"bl_{i}")]
            if len(vals) == 10:
                rows[r["date"]] = vals  # keep MQ column order (bl_1..bl_10)
    return rows


def spot(sym, date):
    g = BASKET.get(sym, {}).get(date)
    if not g:
        return None
    lo, hi = g.get("1D Min"), g.get("1D Max")
    if lo and hi:
        return (lo + hi) / 2
    return None


def mapped_pool(subset, levelnames, target_sym, tgt_spot, date, include_target=False):
    """Return list of (value_in_target_space, asset) for all assets in subset."""
    pool = []
    for s in subset:
        if s == target_sym and not include_target:
            continue
        sp = spot(s, date)
        if not sp:
            continue
        r = tgt_spot / sp
        g = BASKET[s][date]
        for k in levelnames:
            v = g.get(k)
            if v is not None and v > 0:
                pool.append((v * r, s))
    return pool


def cluster(pool, tol):
    """Greedy fixed-width clustering on values. Return list of (centroid, n_assets, n_pts)."""
    if not pool:
        return []
    pool = sorted(pool)  # by value
    clusters = []
    start = pool[0][0]
    cur = [pool[0]]
    for val, asset in pool[1:]:
        if val - start <= tol:
            cur.append((val, asset))
        else:
            clusters.append(cur)
            cur = [(val, asset)]
            start = val
    clusters.append(cur)
    out = []
    for c in clusters:
        cent = sum(v for v, _ in c) / len(c)
        nass = len({a for _, a in c})
        out.append((cent, nass, len(c)))
    return out


def predict(pool, tol, k=10):
    cl = cluster(pool, tol)
    # rank by distinct assets desc, then total pts desc
    cl.sort(key=lambda x: (x[1], x[2]), reverse=True)
    return cl[:k]  # list of (centroid, n_assets, n_pts)


def med_matched(actual, pred_centroids):
    """median nearest distance from each actual BL to nearest predicted centroid."""
    if not pred_centroids:
        return float("nan")
    return st.median(min(abs(a - c) for c in pred_centroids) for a in actual)


def run_config(target_sym, subset, levelnames, tol, dates, bl, seed=0):
    """Return per-day (real, null) matched distances."""
    rng = random.Random(seed)
    reals, nulls = [], []
    for date in dates:
        tgt_spot = spot(target_sym, date)
        if not tgt_spot:
            continue
        acts = bl.get(date)
        if not acts:
            continue
        pool = mapped_pool(subset, levelnames, target_sym, tgt_spot, date)
        if len(pool) < 15:
            continue
        pred = predict(pool, tol)
        cents = [c for c, _, _ in pred]
        real = med_matched(acts, cents)
        lo, hi = min(acts), max(acts)
        ndraw = []
        for _ in range(50):
            pts = [rng.uniform(lo, hi) for _ in range(10)]
            ndraw.append(med_matched(pts, cents))
        nulls.append(st.mean(ndraw))
        reals.append(real)
    return reals, nulls


def summ(reals, nulls):
    n = len(reals)
    if n == 0:
        return None
    diffs = [r - nu for r, nu in zip(reals, nulls)]
    md = st.mean(diffs)
    sd = st.pstdev(diffs) or 1e-9
    t = md / (sd / math.sqrt(n))
    wins = sum(1 for d in diffs if d < 0)
    return dict(n=n, real=st.mean(reals), null=st.mean(nulls),
                ratio=st.mean(reals) / st.mean(nulls), t=t, winpct=100 * wins / n)


def main():
    bl_es = load_bl("ES1!")
    dates = sorted(set(bl_es) & set(BASKET["ES1!"]))
    print(f"ES BL sessions available: {len(dates)}  ({dates[0]}..{dates[-1]})")
    tr, te = dates[:140], dates[140:]
    print(f"train={len(tr)} test={len(te)}\n")

    TOLS = [3, 5, 7, 9, 12, 15, 20]
    print("=== GRID SEARCH (ES) — ranked by TRAIN real matched dist ===")
    print(f"{'basket':10}{'levelset':12}{'TOL':>4}  {'tr_real':>8}{'tr_null':>8}{'tr_ratio':>9}{'tr_t':>7}")
    results = []
    for bname, subset in BASKETS.items():
        for lname, lv in LEVELSETS.items():
            for tol in TOLS:
                r, nu = run_config("ES1!", subset, lv, tol, tr, bl_es)
                s = summ(r, nu)
                if s:
                    results.append((bname, lname, tol, s))
    results.sort(key=lambda x: x[3]["real"])
    for bname, lname, tol, s in results[:12]:
        print(f"{bname:10}{lname:12}{tol:>4}  {s['real']:>8.2f}{s['null']:>8.2f}"
              f"{s['ratio']:>9.3f}{s['t']:>7.1f}")

    best = results[0]
    bname, lname, tol, _ = best
    print(f"\nBEST config (min train real dist): basket={bname} levels={lname} TOL={tol}")

    # also pick best by ratio (most beats-null) among configs with decent absolute dist
    byratio = sorted(results, key=lambda x: x[3]["ratio"])[0]
    print(f"BEST by ratio: basket={byratio[0]} levels={byratio[1]} TOL={byratio[2]} "
          f"ratio={byratio[3]['ratio']:.3f}")

    print("\n=== OUT-OF-SAMPLE (ES, last 60d) for BEST config ===")
    r, nu = run_config("ES1!", BASKETS[bname], LEVELSETS[lname], tol, te, bl_es)
    s = summ(r, nu)
    print(f"  n={s['n']}  REAL {s['real']:.2f}pt  NULL {s['null']:.2f}pt  ratio {s['ratio']:.3f}"
          f"  t={s['t']:+.1f}  win%={s['winpct']:.1f}")

    print("\n=== NQ consistency (SAME config, NQ space, OOS 60d) ===")
    bl_nq = load_bl("NQ1!")
    r, nu = run_config("NQ1!", BASKETS[bname], LEVELSETS[lname], tol, te, bl_nq)
    s = summ(r, nu)
    if s:
        print(f"  n={s['n']}  REAL {s['real']:.2f}pt  NULL {s['null']:.2f}pt  ratio {s['ratio']:.3f}"
              f"  t={s['t']:+.1f}  win%={s['winpct']:.1f}")
        # NQ full 200d too
        rf, nuf = run_config("NQ1!", BASKETS[bname], LEVELSETS[lname], tol, dates, bl_nq)
        sf = summ(rf, nuf)
        print(f"  NQ full {sf['n']}d: REAL {sf['real']:.2f} NULL {sf['null']:.2f} "
              f"ratio {sf['ratio']:.3f} t={sf['t']:+.1f} win%={sf['winpct']:.1f}")

    print("\n=== ORDERING CLAIM (BL1=most overlap) — 200d Spearman ===")
    ordering_test("ES1!", bl_es, dates, BASKETS[bname], LEVELSETS[lname], tol)
    ordering_test("NQ1!", bl_nq, dates, BASKETS[bname], LEVELSETS[lname], tol)


def spearman(x, y):
    n = len(x)
    if n < 3:
        return float("nan")
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = rank(x), rank(y)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else float("nan")


def ordering_test(target_sym, bl, dates, subset, levelnames, tol):
    """For each day: match each actual BL (in MQ column order 1..10) to nearest predicted
    cluster; record that cluster's distinct-asset overlap count. Spearman(bl_index, overlap)."""
    rhos = []
    for date in dates:
        tgt_spot = spot(target_sym, date)
        if not tgt_spot:
            continue
        acts = bl.get(date)
        if not acts:
            continue
        pool = mapped_pool(subset, levelnames, target_sym, tgt_spot, date)
        if len(pool) < 15:
            continue
        pred = predict(pool, tol)  # ordered top-10 (centroid, nass, npts)
        if len(pred) < 8:
            continue
        idx, ov = [], []
        for i, a in enumerate(acts):  # i=0 -> bl_1
            # nearest predicted cluster
            best = min(pred, key=lambda c: abs(a - c[0]))
            idx.append(i + 1)
            ov.append(best[1])  # distinct-asset count
        rho = spearman(idx, ov)
        if not math.isnan(rho):
            rhos.append(rho)
    if not rhos:
        print(f"  {target_sym}: no data")
        return
    n = len(rhos)
    mr = st.mean(rhos)
    sd = st.pstdev(rhos) or 1e-9
    se = sd / math.sqrt(n)
    t = mr / se
    # expect NEGATIVE (bl_1 low index -> high overlap)
    print(f"  {target_sym}: mean Spearman(bl_index, overlap)={mr:+.3f}  "
          f"95%CI[{mr-1.96*se:+.3f},{mr+1.96*se:+.3f}]  t={t:+.1f}  n={n}days  "
          f"(<0 supports BL1=most overlap)")


if __name__ == "__main__":
    main()
