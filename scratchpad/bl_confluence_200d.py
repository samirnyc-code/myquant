"""Blind Spots structural cross-asset confluence — 200-day powered test (S75V).

The single-day squeeze found: real BLs sit closer to the pooled cross-asset STRUCTURAL
gamma levels {Call Resistance, Put Support, HVL, Gamma Wall 0DTE} than random, ES p=0.011.
n=1 day. Now we have ~200 days of BL. Re-run per session, aggregate for real power.

Real  = median nearest-distance of the 10 BLs to the mapped structural pool (that session).
Null  = same, for 10 uniform-random points in the BL band (many draws), that session.
Verdict = paired real-vs-null across all sessions.
"""
import glob, json, statistics as st
from pathlib import Path
import csv

ROOT = Path(__file__).resolve().parents[1]
MQ = ROOT / "data" / "menthorq"
STRUCT = ["Call Resistance", "Put Support", "HVL", "Gamma Wall 0DTE"]
# gamma-history universe correlated to ES (we hold gamma jsonl for these)
UNI = ["ES1!", "NQ1!", "RTY1!", "GC1!", "CL1!", "AAPL", "MSFT", "NVDA",
       "AMZN", "GOOGL", "META", "TSLA", "SPX"]


def load_gamma_by_date(sym):
    f = MQ / f"{sym}_mq_levels_history_raw.jsonl"
    if not f.exists():
        return {}
    out = {}
    for line in open(f, encoding="utf-8"):
        try:
            d = json.loads(line)
        except Exception:
            continue
        it = d.get("item", {})
        dt = it.get("date")
        for lv in it.get("levels", []):
            if lv.get("level_type") == "gamma_levels":
                out[dt] = {v["name"]: v["value"] for v in lv.get("level_values", [])}
    return out


GAMMA = {s: load_gamma_by_date(s) for s in UNI}


def es_bl():
    rows = {}
    with open(MQ / "ES1!_mq_blindspots_history.csv", newline="") as f:
        for r in csv.DictReader(f):
            vals = [float(r[f"bl_{i}"]) for i in range(1, 11) if r.get(f"bl_{i}")]
            if len(vals) == 10:
                rows[r["date"]] = sorted(vals)
    return rows


def struct_pool(date, es_spot):
    pool = []
    for s in UNI:
        g = GAMMA[s].get(date)
        if not g or "1D Min" not in g or "1D Max" not in g:
            continue
        sp = (g["1D Min"] + g["1D Max"]) / 2
        if not sp:
            continue
        r = es_spot / sp
        for k in STRUCT:
            if g.get(k) is not None:
                pool.append(g[k] * r)
    return pool


def med_nn(pts, pool):
    return st.median(min(abs(p - c) for c in pool) for p in pts)


def main():
    BL = es_bl()
    # ES spot per date from ES1! gamma 1D mid
    reals, nulls, wins = [], [], 0
    used = 0
    for date, bls in sorted(BL.items()):
        g = GAMMA["ES1!"].get(date)
        if not g or "1D Min" not in g:
            continue
        es_spot = (g["1D Min"] + g["1D Max"]) / 2
        pool = struct_pool(date, es_spot)
        if len(pool) < 8:
            continue
        band = (min(bls), max(bls)); w = band[1] - band[0]
        real = med_nn(bls, pool)
        # 200 quasi-random null draws of 10 pts each
        ndraw = []
        for k in range(200):
            pts = [band[0] + w * (((k * 10 + j) * 0.61803398875) % 1) for j in range(10)]
            ndraw.append(med_nn(pts, pool))
        null = st.median(ndraw)
        reals.append(real); nulls.append(null)
        used += 1
        if real < null:
            wins += 1
    n = used
    mr, mn = st.mean(reals), st.mean(nulls)
    # paired sign test p (one-sided): P(wins >= observed | p=0.5) via normal approx
    import math
    z = (wins - n * 0.5) / math.sqrt(n * 0.25)
    print(f"ES Blind Spots structural cross-asset confluence — {n} sessions")
    print(f"  mean median-NN distance:  REAL {mr:.2f} pt   NULL {mn:.2f} pt   ratio {mr/mn:.2f}")
    print(f"  sessions where REAL < NULL: {wins}/{n} = {100*wins/n:.1f}%   (z={z:+.1f})")
    print(f"  => {'CONFIRMED: BLs cluster near cross-asset structural levels' if z>2 else 'not significant'}")
    # effect size
    diffs = [a - b for a, b in zip(reals, nulls)]
    md = st.mean(diffs); sd = st.pstdev(diffs) or 1e-9
    print(f"  paired diff (real-null): {md:+.2f} pt/session (sd {sd:.2f}, t~{md/(sd/math.sqrt(n)):+.1f})")


if __name__ == "__main__":
    main()
