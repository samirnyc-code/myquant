# BL reverse-engineering — EXACT-ARITHMETIC DECIMAL FINGERPRINT angle

Date analyzed: 2026-07-17. Ground truth: ES1! and NQ1! bl_1..bl_10.
Scripts: scratchpad/bl_fp.py, bl_fp2.py, bl_fp3.py, bl_fp4.py, bl_fp5.py

## VERDICT: REFUTED
No exact-decimal fingerprint exists. Neither the correlated-equity universe nor
the ETF/index proxy universe (SPY, QQQ, NDX, SPX, IWM, DIA, SMH, XLK, GLD, ...)
reproduces ANY ES or NQ blind spot from `round_level * clean_ratio` to the 0.01
precision that would be a fingerprint. The "Blind Spots V2 = fixed-ratio proxy
copy" hypothesis (SPY×10.08, QQQ×41.26, SPX×1.005, NDX×1.006) is refuted: every
clean fixed ratio yields **0 exact hits**, and the best data-fitted ratio is
statistically indistinguishable from random points in the BL band.

## What was tested and the numbers

### 1. Clean fixed ratios -> exact reconstruction (V1 single-proxy copy)
For each proxy at its documented/spot ratio, count BLs equal to some level*r within 0.05:
- SPY ×10.0 and ×10.08  -> 0 exact hits (ES)
- SPX ×1.0 and ×1.005   -> 0 exact hits (ES) [×1.005 gives 2 within 0.5, not exact]
- DIA ×14.0             -> 0 exact hits (ES)
- QQQ ×41.26 and ×41.37 -> 0 exact hits (NQ)
- NDX ×1.0 and ×1.006   -> 0 exact hits (NQ)
Not a single BL is an exact fixed-ratio copy of a proxy level. V1 REFUTED.

### 2. Best data-FITTED single ratio vs random-BL null (the pool-density trap)
Scan every candidate ratio = BL/level; take the ratio reproducing the MOST
distinct BLs exactly (<0.05). Real BLs vs 300 sets of random BLs in the same band:
```
        REAL   NULL mean / max   p(null>=real)
ES SPY  2/10     1.80 / 3          0.79
ES SPX  2/10     1.82 / 3          0.79
ES IWM  2/10     1.71 / 3          0.70
ES GLD  2/10     1.76 / 3          0.76
NQ QQQ  2/10     1.37 / 3          0.37
NQ SMH  2/10     1.29 / 2          0.29
NQ NDX  1/10     1.36 / 2          1.00
```
Real reproduces at most 2/10; RANDOM points reproduce the same 1.3-1.8 (max 3).
Every p >= 0.29. The apparent 2/10 "exact" hits are pure coincidence: 10 BLs ×
~19 levels = ~190 candidate ratios per proxy, so 2 accidental sub-0.05 collisions
are expected. NO ratio is shared by 3+ BLs at a clean constant. REFUTED.

### 3. Implied-ratio clustering (the requested method)
Clusters that share a ratio across >=2 BLs DO appear, but (a) the shared ratio is
never a clean/spot constant (e.g. SPY r=9.838 not 10.08; QQQ r=42.10 not 41.26),
and (b) they are only 2-BL clusters = the same coincidence as #2. The best 3-BL
clusters (SPX r=1.0253; NDX r=1.0064) do not sit at the true basis ratio and do
not survive the null.

### 4. V2 overlap-centroid (BL = centroid of dense cross-proxy cluster)
Map all proxies into ES/NQ space by spot ratio; measure cross-proxy level density
at each BL vs random points:
- ES: density 8.80 vs null 7.37, p=0.167  (NOT significant)
- NQ: density 6.20 vs null 4.84, p=0.023  (marginally significant)
This is only the previously-established weak dense-pool enrichment (brief fact #2),
not a fingerprint. It cannot generate the exact 2-decimal values and fails on ES.

### 5. Own-asset structural ideas (midpoints / offsets / decimals)
- No BL is an exact midpoint of any pair of the instrument's own gamma levels.
- No repeated fixed additive offset (level ± k) links 3+ BLs.
- BL fractional parts (.32 .49 .74 .72 .74 .50 .19 .90 .29 .64 for ES) do not
  match spot (.75) or 1D Min/Max (.89/.61) fracs; not reproducible.
- Confirmed structural fact only: 5 BL below spot / 5 above (ES and NQ both).

## Why this is a clean refutation, not a data gap
The fingerprint claim is falsifiable and would be near-proof IF true: an exact
`round_level * fixed_ratio` copy leaves a 0.00 residual that random points cannot
fake. We looked with the proxy universe MQ itself uses, at the exact ratios MQ
documents, and found zero exact residuals and full null-indistinguishability.
Whatever computes bl_1..bl_10 either (a) uses inputs we do NOT own (per-strike OI
/ a proprietary vol model producing the odd decimals) or (b) applies a
many-input centroid/rounding that is not invertible from one day. Either way, an
exact formula from the gamma levels we hold is not recoverable.

## Recommendation
Stop pursuing an exact arithmetic reconstruction. The only non-null residual
signal anywhere is the weak NQ dense-pool enrichment (p=0.023, n=1 day) already
known. If BL history is needed, the realistic path is capturing live BL EOD daily
going forward, not deriving it. To upgrade this from REFUTED to fully closed,
capture 2-3 more ground-truth days and confirm the fixed-ratio exact-hit count
stays at null level.
