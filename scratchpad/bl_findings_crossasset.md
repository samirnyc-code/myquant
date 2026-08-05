# BL reverse-engineering — cross-asset structural mapping (dual-instrument, adversarial)

Angle: rigorous cross-asset structural mapping on BOTH ES and NQ ground truth (2026-07-17).
Method: permutation nulls (5000×), self/cross decomposition, spot-anchored null, V2 overlap-
clustering, fixed-ratio calibration, beta-map, outer-BL tests. n = 10 BLs per instrument, ONE day.

## VERDICT: INCONCLUSIVE, leaning WEAK-REAL for the SET, REFUTED for the strong V2 mechanism

- The structural nearest-match enrichment (established finding #2) **SURVIVES on both ES and NQ**,
  but only as a weak POOL/SET property (~2–3× enrichment, p≈0.01/0.004), not a clean per-asset or
  cluster-rank mechanism. One day, 10 points, many configs looked at → suggestive, not proven.
- The **stronger V2 "overlap-clustering ranked by #distinct assets" mechanism is NOT supported**
  by this data (unstable, underpowered, inconsistent across instruments).
- Beta-map and "outer BLs = 1D range" are **cleanly REFUTED**.

---

## 1. Structural nearest-match, spot-ratio, permutation null (the finding #2 claim)

Pool = correlated FUTURES+STOCKS universe (ES,NQ,RTY,GC,CL,AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA),
levels mapped into target by spot-ratio (asset_spot = (1D Min+1D Max)/2). p = frac(null median-err ≤ real).

| pool | ES real/null (ratio) p | NQ real/null (ratio) p |
|---|---|---|
| CR/PS | 28.7/30.3 (1.05×) p=0.46 | 131/146 (1.11×) p=0.41 |
| +HVL | 10.8/11.2 (1.04×) p=0.47 | 15.8/39.1 (2.47×) p=0.026 |
| **+GammaWall {CR,PS,HVL,GW}** | **2.15/6.46 (3.0×) p=0.011** | **6.85/25.2 (3.68×) p=0.004** |
| +0DTE | 2.15/4.27 (2.0×) p=0.053 | 6.85/16.4 (2.4×) p=0.029 |
| +GEX1-3 | 1.59/2.64 (1.7×) p=0.13 | 3.33/8.26 (2.5×) p=0.026 |
| ALL (228) | 1.22/1.34 (1.1×) p=0.41 | 2.12/4.77 (2.25×) p=0.043 |

**Best pool = {Call Resistance, Put Support, HVL, Gamma Wall 0DTE}** — the ONLY pool that beats
p<0.05 on BOTH instruments. Gamma Wall 0DTE is the load-bearing level: without it (+HVL) the ES
signal vanishes (p=0.47). CR/PS alone is pure noise. The "ALL" dense pool is the density artifact
(finding #1) on ES.

## 2. Adversarial decomposition (self / cross / null)

- **Spot-anchored null** (random points drawn at BL-like distances from spot, controls for BLs
  clustering near spot where the pool is densest): +GammaWall still ES p=0.0066, NQ p=0.0048.
  The near-spot-density confound does NOT explain it.
- **Cross-only (exclude the instrument's own gamma levels)**: +GammaWall ES p=0.040, NQ p=0.040 —
  **still beats 0.05 on both.** The signal is not merely the instrument matching its own levels.
  (Self-only alone: ES p=0.089, NQ p=0.065 — self helps but is not the whole story.)
- **ALL pool cross-only collapses on ES (p=0.32)** — confirming the ALL result is self-GEX + density.

So: the {CR,PS,HVL,GW} structural enrichment is real, weak, survives the honest nulls on both.

## 3. Contributing-asset consistency — FAILS

If specific correlated assets systematically defined BLs, ES and NQ should draw from overlapping
asset sets. They do NOT:
- +GammaWall cross-only contributors: ES = {NQ1!,RTY1!,NVDA,META,MSFT,CL1!}, NQ = {ES1!,RTY1!,
  TSLA,MSFT,AAPL,AMZN,GC1!}. Shared = {RTY1!, MSFT}. **Real Jaccard = 0.18 vs chance mean 0.39,
  p(chance ≥ real) = 0.97.** Overlap is WORSE than chance.
- Interpretation: the aggregate set is enriched near BLs, but *which* asset supplies each match is
  essentially arbitrary/coincidental — a hallmark of a density/coincidence explanation, not a
  clean per-asset mechanism. This is the single most damaging result against the cross-asset story.

## 4. Mapping form: spot-ratio vs beta — beta REFUTED

Return-beta computed from ~2yr of historical spot-midpoints in the JSONL (no live API). Dollar-beta
offset map: level→ tgt + β·(tgt/asset_spot)·(level−asset_spot).

| | spot-ratio | beta-map |
|---|---|---|
| ES +GammaWall | real=2.15 p=0.009 | real=5.78 p=0.095 |
| NQ +GammaWall | real=6.85 p=0.006 | real=41.4 p=0.55 |

Beta-map is **much worse**. Spot-ratio (≈ fixed ratio for a single day) is the correct mapping;
a return-beta correction destroys the alignment (betas span 0.24 GC → 2.28 TSLA). Confirms finding #3.

## 5. V2 overlap-clustering model (coordinator hypothesis) — NOT SUPPORTED here

Tested: convert equity-complex levels (incl. new ETF proxies SPY/QQQ/NDX/IWM/SPX/DIA/SMH/XLK) into
target space, grid-density of DISTINCT assets, top-10 peaks ranked by asset-count as BL1..10.

- **Peak-match vs null is tolerance-unstable.** No single (levelset, tol) beats null on BOTH:
  ES likes STRUCT+GEX @tol6 (p=0.002) but NQ hates GEX (p=0.85–0.95); NQ likes STRUCT @tol4/10
  (p≈0.014) but ES STRUCT is null (p=0.21). This flip-flop across 16 configs = tolerance-mining.
- **BL-rank vs overlap-count (the core V2 claim BL1=most overlap):** Spearman rho is negative in
  all 4 configs (−0.18, −0.41, −0.44, −0.48 — correct direction!) but **none significant**
  (p=0.62, 0.24, 0.20, 0.17). Underpowered at n=10; a weak hint at best, not confirmation.
- **Adding the ETF proxies to the structural nearest-match does NOT help.** cross+ETF STRUCT:
  ES real=2.38 p=0.083 (drops below significance), NQ real=5.92 p=0.025. ETF-only: ES p=0.12,
  NQ p=0.31. The ETF proxies lower the null (density) as much as they lower real error.

## 6. Fixed-ratio calibration & outer-BL tests

- **Calibration**: fitting a per-proxy ratio to minimize distance-to-BL shifts SPY/SPX/QQQ/NDX/
  SMH/XLK ratios a consistent −2.4 to −3.0% below spot-ratio and cuts residuals (SPY 62→18,
  SPX 39→9, IWM 22→6.5). Intriguing consistent basis-like shift, BUT this is fit TO the BLs (free
  ratio param) with no out-of-sample check → overfit-prone, not evidence. SMH/XLK/NDX never fit
  (residuals 79–197pt) at any ratio.
- **Outer BLs are NOT the 1D expected-move range**: SPX 1D range maps to [7428,7561] (≈ ES own
  1D range [7426,7564] — good ratio check), but ES outer BLs are 7246 / 7835, well OUTSIDE it.
  Range hypothesis REFUTED.
- **Outer HIGH BL is closely matched by a high-beta name** (ES 7835.74 ← high-beta err=1.38;
  NQ 29489.09 ← XLK err=1.68), better than equity-core. Suggestive of "outer BLs from high-beta
  proxies" but it's nearest-match (density), not null-tested — do not over-read.

---

## Bottom line for the coordinator

- **Does cross-asset structural mapping survive on both ES and NQ? Weakly yes for the {CR,PS,HVL,
  Gamma Wall 0DTE} structural SET via spot-ratio** (ES p≈0.011, NQ p≈0.004; cross-only p≈0.04 both;
  survives spot-anchored null). Gamma Wall 0DTE is essential.
- **Best pool**: {CR, PS, HVL, Gamma Wall 0DTE}. **Best map**: spot-ratio (≈ fixed ratio for 1 day);
  beta-map refuted.
- **BUT the strong V2 mechanism is not supported by this day's data**: clustering is tolerance-
  unstable, BL1=most-overlap rank correlation is NS (right sign, underpowered), ETF proxies don't
  help, and — most damning — the contributing-asset set overlap between ES and NQ is WORSE than
  chance (Jaccard 0.18 vs 0.39, p=0.97). That argues the aggregate enrichment is a set/density
  property with arbitrary per-match attribution, not a clean "these assets overlap here" mechanism.
- **Refuted cleanly**: beta-map; outer-BL = 1D range.
- **Hard limitation**: one day, 10 points/instrument, many configurations examined. The +GammaWall
  result earns credibility only because finding #2 pre-registered it and it replicates independently
  on ES and NQ — but p≈0.01–0.04 here is FRAGILE. A second ground-truth day is the only thing that
  can move this from INCONCLUSIVE to CONFIRMED/REFUTED.
