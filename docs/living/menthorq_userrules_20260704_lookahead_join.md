# Level-universe & user-rule tests — 2026-07-04 18:28

**Trigger:** user-proposed rules after the S54 nulls: (1) never trade INTO a main
level; (2) trade the break-and-retest; (3) clusters of levels; (4) expand the level
universe to VA / IB / VWAP / prior-day H-L-C. All pre-registered with directions
before outcomes. Script: `scripts/menthorq_userrules.py`. 81 days, cached S54 sim.

## Verdicts

- **U4 (the anchor result): NO level family beats random at the 5M/6-bar scale** —
  not prior-day H/L/C, not VWAP, not VA, not IB, not any MenthorQ family. Every CI
  spans zero against 3,263 random-control touches (bounce ≈ 21–24% for everything).
  The 5M touch-bounce lens finds no S/R for ANYTHING in this window — so the earlier
  "MenthorQ levels are not S/R" null is not special to MenthorQ; either 81 days is
  too small for this effect size, or 5M-scale bouncing is not how any daily level
  expresses itself in 2026 ES. Visual level-respect at this scale is mostly
  base-rate + confirmation bias.
- **U1 "never trade into a main level": REFUTED (wrong direction)** — stacked trades
  INTO an MQ main level within 1R did BETTER (+0.262, n=48) than not-into (+0.124,
  n=156); "clear of all levels" (≥1R air) was the WORST bucket (+0.044, PF 0.88,
  net negative). Consistent with the round-1 headwind null. Skipping into-level
  trades would have cost money in this window.
- **U3 clusters: the user's best call — only registered-direction hit of the day.**
  Trading INTO a ≥3-level cluster (MQ+structural, 4-pt chain) within 1R: stacked
  +0.005 PF 0.76 (n=33) vs +0.186 ✅ PF 1.43 not-into; all-signals −0.100 PF 0.64
  vs +0.097 PF 1.34. Cluster touch test also leans right (bounce 26.5% vs 22.0%
  isolated, CI spans 0). Registered direction, consistent across both scopes,
  coherent mechanism (confluence). Still small n and 3 months → **top watch item;
  pre-registered re-test: "skip/downsize stacked trades with a ≥3-level cluster
  within 1R" at 6–12 months of MenthorQ data.**
- **U2 break-and-retest: UNTESTABLE at this event rate** — 16 qualifying trades
  all-scope, ZERO in the stacked subset (main levels rarely break+retest+signal
  aligns). Structural variant n=5 (meaningless). No conclusion either way.

## U4 — 6-bar touch test by level family (MQ vs market-structure)

| family | touches | bounce% | break% | drift pts | bounce diff vs ctrl (95% CI) |
|---|---|---|---|---|---|
| MQ main | 407 | 20.1% | 79.6% | -0.15 | [-5.0pp, +3.5pp] |
| MQ other (BL+GEX) | 1394 | 23.2% | 76.3% | -0.22 | [-0.4pp, +5.0pp] |
| Prior day H/L/C | 426 | 24.4% | 75.6% | -0.06 | [-0.8pp, +7.6pp] |
| Prior day VA (POC/VAH/VAL) | 374 | 21.7% | 78.3% | -1.93 | [-3.8pp, +5.0pp] |
| IB high/low (post-IB) | 315 | 21.3% | 78.1% | +0.74 | [-4.4pp, +4.9pp] |
| VWAP (developing) | 448 | 22.5% | 77.2% | +0.96 | [-2.5pp, +5.5pp] |
| random control | 3263 | 21.0% | 78.5% | +0.01 | — |

## U3a — cluster zones (≥3 of ANY level within 4-pt chain) vs isolated

175 cluster zones / 81 days.

| zone | touches | bounce% | break% | drift |
|---|---|---|---|---|
| CLUSTER ≥3 | 223 | 26.5% | 73.1% | -1.38 |
| isolated | 965 | 22.0% | 77.7% | +0.09 |

Bounce diff (cluster − isolated) 95% CI: [-2.2pp, +10.7pp]

## ALL MC signals

| cut | n | ExpR ±CI | 95% interval | PF | net$ |
|---|---|---|---|---|---|
| baseline | 370 | +0.064 ±0.110 | [-0.046,+0.174] | 1.19 | $27,862 |
| U1 INTO MQ main (≤1R) [reg: worse] | 91 | +0.126 ±0.225 | [-0.099,+0.352] | 1.22 | $8,678 |
| U1 not into MQ main | 279 | +0.043 ±0.126 | [-0.083,+0.169] | 1.19 | $19,184 |
| U1 INTO structural (pdHLC/VA/IB, ≤1R) | 238 | +0.054 ±0.137 | [-0.083,+0.190] | 1.24 | $25,512 |
| U1 not into structural | 132 | +0.082 ±0.186 | [-0.104,+0.268] | 1.06 | $2,349 |
| U1 INTO any (MQ main ∪ struct) | 263 | +0.081 ±0.135 | [-0.054,+0.217] | 1.28 | $31,078 |
| U1 clear of all (≥1R air) | 107 | +0.020 ±0.186 | [-0.166,+0.206] | 0.90 | $-3,217 |
| U3b INTO cluster zone (≤1R) [reg: worse] | 63 | -0.100 ±0.237 | [-0.337,+0.137] | 0.64 | $-11,087 |
| U3b not into cluster | 307 | +0.097 ±0.123 | [-0.026,+0.220] | 1.34 | $38,949 |
| U2 break-retest MQ main [reg: better] | 16 | +0.079 ±0.466 | [-0.387,+0.545] | 1.93 | $2,743 |
| U2 rest (MQ) | 354 | +0.063 ±0.113 | [-0.050,+0.176] | 1.18 | $25,119 |
| U2 break-retest STRUCT (exploratory) | 38 | +0.012 ±0.294 | [-0.283,+0.306] | 1.17 | $1,547 |
| U2 rest (struct) | 332 | +0.070 ±0.118 | [-0.049,+0.188] | 1.20 | $26,315 |

## STACK v2 subset

| cut | n | ExpR ±CI | 95% interval | PF | net$ |
|---|---|---|---|---|---|
| baseline | 204 | +0.157 ±0.166 | [-0.009,+0.322] | 1.30 | $25,836 |
| U1 INTO MQ main (≤1R) [reg: worse] | 48 | +0.262 ±0.362 | [-0.100,+0.624] | 1.32 | $7,591 |
| U1 not into MQ main | 156 | +0.124 ±0.186 | [-0.062,+0.310] | 1.29 | $18,245 |
| U1 INTO structural (pdHLC/VA/IB, ≤1R) | 125 | +0.142 ±0.209 | [-0.067,+0.352] | 1.34 | $20,805 |
| U1 not into structural | 79 | +0.179 ±0.273 | [-0.093,+0.452] | 1.20 | $5,031 |
| U1 INTO any (MQ main ∪ struct) | 139 | +0.209 ±0.211 | [-0.001,+0.420] | 1.43 | $28,494 |
| U1 clear of all (≥1R air) | 65 | +0.044 ±0.260 | [-0.215,+0.304] | 0.88 | $-2,658 |
| U3b INTO cluster zone (≤1R) [reg: worse] | 33 | +0.005 ±0.386 | [-0.381,+0.391] | 0.76 | $-4,306 |
| U3b not into cluster | 171 | +0.186 ±0.183 ✅ | [+0.003,+0.369] | 1.43 | $30,142 |
| U2 break-retest MQ main [reg: better] | 0 | — | — | — | — |
| U2 rest (MQ) | 204 | +0.157 ±0.166 | [-0.009,+0.322] | 1.30 | $25,836 |
| U2 break-retest STRUCT (exploratory) | 5 | +0.553 ±0.483 ✅ | [+0.070,+1.036] | 39.37 | $2,566 |
| U2 rest (struct) | 199 | +0.147 ±0.169 | [-0.022,+0.316] | 1.27 | $23,270 |
