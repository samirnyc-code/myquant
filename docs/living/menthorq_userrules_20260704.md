# Level-universe & user-rule tests — 2026-07-04 19:10

80 days; volume data: True

## U4 — 6-bar touch test by level family (MQ vs market-structure)

| family | touches | bounce% | break% | drift pts | bounce diff vs ctrl (95% CI) |
|---|---|---|---|---|---|
| MQ main | 351 | 24.8% | 75.2% | -2.25 | [-2.5pp, +6.8pp] |
| MQ other (BL+GEX) | 1321 | 24.1% | 75.5% | -0.19 | [-1.2pp, +4.1pp] |
| Prior day H/L/C | 417 | 24.2% | 75.8% | -0.25 | [-2.6pp, +5.8pp] |
| Prior day VA (POC/VAH/VAL) | 371 | 21.8% | 78.2% | -2.22 | [-5.1pp, +3.7pp] |
| IB high/low (post-IB) | 301 | 21.9% | 77.4% | +0.65 | [-5.7pp, +4.4pp] |
| VWAP (developing) | 439 | 22.8% | 77.0% | +0.83 | [-3.7pp, +4.3pp] |
| random control | 3413 | 22.7% | 77.0% | +0.01 | — |

## U3a — cluster zones (≥3 of ANY level within 4-pt chain) vs isolated

175 cluster zones / 80 days.

| zone | touches | bounce% | break% | drift |
|---|---|---|---|---|
| CLUSTER ≥3 | 196 | 22.4% | 77.0% | -2.27 |
| isolated | 983 | 24.3% | 75.7% | -1.02 |

Bounce diff (cluster − isolated) 95% CI: [-8.1pp, +5.1pp]

## ALL MC signals

| cut | n | ExpR ±CI | 95% interval | PF | net$ |
|---|---|---|---|---|---|
| baseline | 369 | +0.066 ±0.110 | [-0.044,+0.177] | 1.21 | $29,629 |
| U1 INTO MQ main (≤1R) [reg: worse] | 81 | +0.237 ±0.236 ✅ | [+0.001,+0.473] | 2.01 | $29,684 |
| U1 not into MQ main | 288 | +0.018 ±0.124 | [-0.106,+0.143] | 1.00 | $-56 |
| U1 INTO structural (pdHLC/VA/IB, ≤1R) | 235 | +0.048 ±0.138 | [-0.090,+0.186] | 1.22 | $22,588 |
| U1 not into structural | 134 | +0.098 ±0.183 | [-0.085,+0.282] | 1.19 | $7,041 |
| U1 INTO any (MQ main ∪ struct) | 257 | +0.072 ±0.134 | [-0.063,+0.206] | 1.27 | $29,467 |
| U1 clear of all (≥1R air) | 112 | +0.055 ±0.192 | [-0.137,+0.247] | 1.00 | $162 |
| U3b INTO cluster zone (≤1R) [reg: worse] | 78 | +0.077 ±0.225 | [-0.149,+0.302] | 1.21 | $7,472 |
| U3b not into cluster | 291 | +0.064 ±0.126 | [-0.062,+0.190] | 1.21 | $22,156 |
| U2 break-retest MQ main [reg: better] | 6 | +0.132 ±0.517 | [-0.385,+0.649] | 9.86 | $2,736 |
| U2 rest (MQ) | 363 | +0.065 ±0.112 | [-0.046,+0.177] | 1.19 | $26,892 |
| U2 break-retest STRUCT (exploratory) | 38 | +0.012 ±0.294 | [-0.283,+0.306] | 1.17 | $1,547 |
| U2 rest (struct) | 331 | +0.073 ±0.118 | [-0.045,+0.191] | 1.21 | $28,082 |

## STACK v2 subset

| cut | n | ExpR ±CI | 95% interval | PF | net$ |
|---|---|---|---|---|---|
| baseline | 203 | +0.162 ±0.166 | [-0.004,+0.329] | 1.32 | $27,602 |
| U1 INTO MQ main (≤1R) [reg: worse] | 43 | +0.519 ±0.379 ✅ | [+0.141,+0.898] | 2.75 | $28,388 |
| U1 not into MQ main | 160 | +0.067 ±0.182 | [-0.116,+0.249] | 0.99 | $-785 |
| U1 INTO structural (pdHLC/VA/IB, ≤1R) | 125 | +0.142 ±0.209 | [-0.067,+0.352] | 1.34 | $20,805 |
| U1 not into structural | 78 | +0.194 ±0.274 | [-0.080,+0.469] | 1.29 | $6,797 |
| U1 INTO any (MQ main ∪ struct) | 135 | +0.186 ±0.208 | [-0.022,+0.394] | 1.41 | $26,099 |
| U1 clear of all (≥1R air) | 68 | +0.115 ±0.276 | [-0.161,+0.391] | 1.07 | $1,504 |
| U3b INTO cluster zone (≤1R) [reg: worse] | 42 | +0.283 ±0.318 | [-0.035,+0.601] | 1.65 | $11,567 |
| U3b not into cluster | 161 | +0.131 ±0.192 | [-0.061,+0.323] | 1.24 | $16,036 |
| U2 break-retest MQ main [reg: better] | 2 | +0.306 ±0.634 | [-0.328,+0.940] | 101.31 | $1,691 |
| U2 rest (MQ) | 201 | +0.161 ±0.168 | [-0.007,+0.329] | 1.30 | $25,911 |
| U2 break-retest STRUCT (exploratory) | 5 | +0.553 ±0.483 ✅ | [+0.070,+1.036] | 39.37 | $2,566 |
| U2 rest (struct) | 198 | +0.153 ±0.170 | [-0.017,+0.322] | 1.29 | $25,037 |
