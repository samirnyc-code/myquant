# BL reverse-engineering — ORDERING + NON-GAMMA SOURCES (angle: decode index / test per-strike, Q-score, IV)

Date of ground truth: 2026-07-17. ES spot 7494.75, NQ spot 28768.25 (=1D Min/Max midpoint).
Data: scratchpad/bl_live_pull.json (live per_strike/matrix/metrics/vol, one MQ session, 7/17).

## TL;DR
No non-gamma source I tested explains BL better than null on BOTH instruments. The index
ordering is NOT a distance rank and is NOT reconstructable from one day. The only durable NEW
fact is negative: the "5 below / 5 above" balance is an ES coincidence — NQ is 7 above / 3 below.

## 1. Index-ordering decode  → INCONCLUSIVE (mostly negative)
Tabulated bl_1..bl_10 with signed distance, |distance| rank, side:

ES (spot 7494.75), above=5 below=5:
  idx : signed_d  | |d|-rank | side
  bl_1 +84.57  rank5 above   bl_2 -67.26 rank3 below   bl_3 +71.99 rank4 above
  bl_4 -10.03  rank1 below   bl_5 +340.99 rank10 above  bl_6 -23.25 rank2 below
  bl_7 -248.56 rank9 below   bl_8 -214.85 rank8 below   bl_9 +108.54 rank6 above
  bl_10 +120.89 rank7 above
NQ (spot 28768.25), above=7 below=3:
  bl_1 +322 rank4 ab  bl_2 -264 rank2 bl  bl_3 +695 rank8 ab  bl_4 +460 rank6 ab
  bl_5 +124 rank1 ab  bl_6 -440 rank5 bl  bl_7 +533 rank7 ab  bl_8 -832 rank10 bl
  bl_9 +280 rank3 ab  bl_10 +721 rank9 ab

- bl_1 is NOT the nearest (rank5 ES, rank4 NQ) and NOT the strongest/outermost. Index ≠ distance
  rank: the (index → |d|-rank) map is non-monotonic and different between ES and NQ. So the index
  is an internal MenthorQ ordering (probably a "blindness/void score" rank), not decodable from a
  single day. Need multi-day capture to regress it.
- **5/5 split is ES-ONLY. NQ is 7 above / 3 below.** The brief's "structural balance" (item 5) is a
  coincidence, not a rule. → the balance claim is **REFUTED** as a general property.
- Odd-index → above spot: ES 4/5 (only bl_7 below), NQ 5/5. Combined **9/10** — the single
  strongest ordering regularity. Even-index → below: ES 4/5, NQ 3/5 → combined 7/10, weaker.
  Pair hypothesis (odd=upper / even=lower of a bracketing pair) holds 3/5 pairs on each. First pair
  (bl_1,bl_2) brackets spot on both (mid 7503 vs 7494; 28797 vs 28768). Suggestive, one day, weak.

## 2. Per-strike net-GEX surface (zero-crossings / sign-flips)  → REFUTED / no signal
Aggregated net_gex per strike across all 31 expirations; found zero-crossings by linear interp.
- Aggregate surface is noisy: 37 crossings (ES) / 122 (NQ), mostly "exact" zeros at empty far
  strikes = dense pool, meaningless.
- Restricting to true sign-flips inside the BL band: ES only **3** flips (real median err 97.65 pt,
  nowhere near BLs, p(null≤real)=0.167); NQ 25 flips (real 21.61 vs null 72.46, p=0.093).
  Neither significant; ES pool of 3 can't produce 10 BLs. **The gamma-flip / zero-GEX hypothesis
  (blind spot = dealer long/short-gamma flip point) does NOT hold.**

## 3. Q-score / metrics  → REFUTED as a source
mq.metrics('ES1!') returns per-day dict of exactly 4 SCALAR scores:
{momentum, seasonality, volatility, option} (values ~1-5). **No level-like / price fields at all.**
Cannot be a source of price levels.

## 4. IV-implied band for the outermost BLs  → REFUTED (no consistent mechanism)
ES iv_0dte=0.103 iv_1m=0.144 iv_3m=0.150 ; NQ iv_0dte=0.185 iv_1m=0.258 iv_3m=0.243.
- ES BL band: low -3.32%, high +4.55% (ASYMMETRIC). Closest IV match = 1-month 1σ (±4.17%,
  band 7182..7807) but ES high BL 7835.74 sits BEYOND the 1σ high, and the band is asymmetric while
  IV band is symmetric.
- NQ BL band: low -2.89%, high +2.51%. This is between 0dte 1σ (±1.17%) and 1w 1σ (±3.64%) — a
  DIFFERENT (and narrower) horizon than ES. NQ's own 1-month 1σ is ±7.45%, far wider than its BLs.
- Different instruments imply different IV horizons/multiples → not one mechanism. Also BLs are
  spread THROUGHOUT the band, not clustered at the edges as an expected-move band would predict.
  matrix.implied_expected_move is None for every expiration. **IV band does not explain BL.**

## 5. Bonus: OI local-minima ("blind" = low-liquidity strike)  → REFUTED (inconsistent)
Nearest-OI-minimum test vs 2000 random-in-band nulls:
- ES: real median err 1.72 vs null 3.15, p=0.058 — marginal, but pool=54 (dense).
- NQ: real 6.45 vs null 5.25, **p=0.710 (worse than random)**. Fails. Not a cross-instrument source.

## Best finding
All my tested non-gamma sources fail the both-instruments null. The most useful takeaways are
negative and sharpen the search: (a) BL index is an internal score-rank, not distance — needs
multi-day capture to decode, not one-day geometry; (b) the 5/5 balance is not real (NQ 7/3);
(c) per-strike GEX zero-crossings, Q-score, IV-band, and OI-minima are all ruled out. This
re-centers the live hypothesis on the earlier structural-gamma-level pool (Call Res / Put Sup /
HVL / Gamma Wall mapped by ratio, ~2x null enrichment) as the only thing beating null so far.

## Per-hypothesis verdict
- Index = nearest/strongest/distance-rank: **REFUTED**
- 5-below/5-above structural balance: **REFUTED** (ES-only; NQ 7/3)
- Odd-index→above-spot regularity: **INCONCLUSIVE** (9/10, one day)
- BL = per-strike net-GEX zero-crossings / gamma-flip: **REFUTED**
- BL from Q-score/metrics: **REFUTED** (no level fields exist)
- Outer BL = IV-implied expected-move band: **REFUTED**
- BL = OI local minima: **REFUTED** (inconsistent across ES/NQ)

## Lead for whoever continues
The .xx decimals must come from a computed (interpolated or %-based) source, not round strikes.
1D Min/Max are the only 2-decimal gamma fields (ES 7425.89/7563.61); bl_2=7427.49 sits ~1.6 above
1D Min and bl_3=7566.74 ~3.1 above 1D Max — a coincidence-grade lead, not a fit. Real decode almost
certainly requires capturing BL daily for N days and regressing index/value against the same-day
gamma + per-strike + IV features. One day cannot separate these.
