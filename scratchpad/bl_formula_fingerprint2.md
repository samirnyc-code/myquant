# BL formula hunt — angle: EXACT-DECIMAL RECONSTRUCTION (200-day panel)

**Verdict: REFUTED.** Exact (penny-level) reconstruction of MenthorQ Blind Spots from
the *published gamma-level* inputs (Call/Put/HVL/Gamma-Wall/0DTE/GEX/1D-Min-Max, whole
38-ticker basket incl. sector ETFs) is **impossible**. Across 200 sessions, no
asset/level × fixed-ratio, no structural midpoint, and no documented clean ratio
reproduces BL to the penny above chance density. The BL fractional parts are the smoking
gun: they are **continuous**, so BL cannot be `round_level × clean_ratio`. The only real,
repeatable signal is the already-established *confluence* effect (BL sit near the asset
family's own gamma zones), which is a proximity statistic, not a generating formula.

Targets analyzed: ES1!, NQ1! (primary), plus SPY, QQQ, SPX, NDX. 200 sessions
2025-09-30..2026-07-17. Every test carries a NULL (source levels drawn from a shuffled
different date) and a z-score. Scripts: `scratchpad/bl_fp2_hunt.py` (implied-ratio
recurrence), `bl_fp2_cover.py` (pooled coverage), `bl_fp2_nail.py` (clean ratios +
decimal signature), `bl_fp2_mid.py` (midpoints).

---

## Test 1 — Implied-ratio recurrence (hypothesis 1 & 3)
For each (target BL, source asset, level type) collect implied ratio = BL/level over all
days/all 10 BL; find the tightest 0.01%-wide ratio window and count DISTINCT days in it;
null = shuffle level-dates. A true fixed-ratio formula → one ratio recurs on ~all days.

**Result — every top hit is same-instrument / same-family at ratio ≈ 1.0**, i.e. the
confluence effect, NOT a cross-asset conversion:

| target | best source·level | ratio | days in 0.01% window | null µ (max) | z |
|---|---|---|---|---|---|
| ES1! | ES1! Gamma Wall 0DTE | 0.99995 | 25/200 | 7.6 (9) | 26 |
| ES1! | ES1! Call Resistance | 0.99992 | 21/200 | 8.0 (11) | 11 |
| ES1! | SPY GEX/HVL (best cross) | 10.02–10.19 | 13/200 | 7.0 (8) | ~10 |
| NQ1! | NQ1! Gamma Wall 0DTE | 0.99993 | 19/200 | 6.5 (8) | 21 |
| NQ1! | QQQ GEX 3 (best cross) | 41.47 | 13/200 | 6.2 (7) | 13 |
| SPY | SPY Gamma Wall 0DTE | 1.00004 | 38/200 | 8.0 (10) | 39 |
| QQQ | QQQ 1D Max | 0.99981 | 26/200 | 6.3 (7) | 34 |

Reading: the strongest relationship anywhere is SPY's own Gamma Wall 0DTE, and it accounts
for **only 38/200 days = 19%**, and only within a **0.01% (~0.7pt) window — never to the
penny**. Cross-asset conversions (SPY→ES, QQQ→NQ) are weak (13/200) and land on *ad-hoc*
ratios (10.02, 41.47), not the documented 10.08 / 41.26. No fixed cross-asset ratio recurs
across many days. The apparent SPY↔SPX (0.0997) / QQQ↔NDX (0.02434) hits are the trivial
same-underlying cross-listing, not information.

## Test 2 — Pooled penny-exact coverage (upper bound on any level-based formula)
Pool ALL 37 basket assets × 19 levels × their fixed spot-ratio; ask what fraction of
(day, BL) is reconstructable within a tolerance. Null = shuffled source dates.

| target | tol=0.05pt | tol=0.25pt | tol=1.0pt |
|---|---|---|---|
| ES1! real / null | **0.070 / 0.041** | 0.280 / 0.175 | 0.711 / 0.495 |
| NQ1! real / null | **0.019 / 0.010** | 0.076 / 0.042 | 0.265 / 0.161 |

At the penny (0.05pt), even pooling ~700 candidate points/day, real coverage is 7% (ES) /
2% (NQ), barely over the ~4% / 1% you get by chance from candidate density. The loose-tol
"coverage" (49% null at ±1pt) is pure density, not signal. **No exact formula lives here.**

## Test 3 — Documented clean ratios, penny-exact (hypothesis 3)
| formula | penny coverage (real) | null | z |
|---|---|---|---|
| ES = SPY × 10.08 | 0.008 | 0.002 | 5.5 |
| ES = SPY × 10.0 | 0.013 | 0.004 | 6.3 |
| ES = SPX × 1.005 | 0.006 | 0.004 | 2.3 |
| NQ = QQQ × 41.26 | 0.004 | 0.001 | 4.1 |
| NQ = NDX × 1.005 | 0.002 | 0.001 | 2.9 |

z is "significant" but the **absolute magnitude is ~1%** — about one BL every 10 days. If
MQ literally applied SPY×10.08, coverage would be large. It is not. **Refuted.**

## Test 4 — Odd-decimal signature (hypothesis 4) — THE SMOKING GUN
Distribution of BL fractional cents (n≈2000 per instrument):

| target | distinct cent values | % on .00/.25/.50/.75 | % on any multiple of .25 |
|---|---|---|---|
| ES1! | 100/100 | 0.044 | 0.044 |
| NQ1! | 100/100 | 0.037 | 0.037 |
| SPY | 100/100 | 0.036 | 0.036 |
| QQQ | 100/100 | 0.035 | 0.035 |

BL cents are **uniform across all 100 values**; the quarter-mark share (3.5–4.4%) equals
the 4% chance rate. A `round_level × clean_ratio` generator (or a midpoint of round levels)
would **concentrate** cents on a few quantized values. It does not. Therefore BL are
computed from a **continuous** quantity (spot / per-strike interpolation / continuous price
ranges), which is exactly the input we do NOT have historically. This independently proves
Test 1–3's refutation and confirms established finding #1 across the full 200-day panel.

## Test 5 — Structural midpoints (hypothesis 2)
BL = (L1+L2)/2 for {CR,PS},{1DMin,1DMax},{GW,HVL},{CR0,PS0},{CR,HVL},{PS,HVL}, cross-asset,
spot-ratio mapped, penny tol:

| target | real | null | z |
|---|---|---|---|
| ES1! | 0.042 | 0.028 | 4.2 |
| NQ1! | 0.008 | 0.006 | 1.2 |

4% / 0.8% penny coverage ≈ null. **Refuted.**

## Out-of-sample (rule #5)
No candidate reached in-sample exactness, so there is no formula to hold out. The single
real relationship (self/family confluence, ratio≈1, ~0.7pt proximity) is a structural
property that trivially persists on any date subset — but it is proximity, not identity,
and reconstructs at most 19% of one BL slot, never all ten, never to the penny.

## Bottom line
- **REFUTED:** exact-decimal reconstruction of BL from published gamma levels (any asset,
  any level type, any fixed or free ratio, midpoints included) — impossible; penny coverage
  never exceeds ~7% pooled and the decimal signature is continuous.
- **CONFIRMED (already established, re-verified on 200 days):** BL track the asset family's
  own structural gamma zones (confluence) at ~0.5–0.7pt proximity on 15–19% of days,
  z=20–39 vs null. This is the real but non-exact mechanism.
- **Implication for the project:** the true BL inputs are continuous (per-strike surface /
  correlated-asset price *ranges*), not the round level cache. Cracking BL to the penny
  would require the historical per-strike surface, which we do not have. Recommend closing
  the "exact reconstruction from published levels" line and treating BL operationally as a
  confluence indicator.
