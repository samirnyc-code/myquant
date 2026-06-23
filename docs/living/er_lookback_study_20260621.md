> # 🚨 INVALID — LOOK-AHEAD BUG (see docs/living/handoff.md, S34)
> This study used ER/feature values that read the **entry bar** (one bar in the
> future), not the signal bar. Its numbers are **not trustworthy**. Re-run on the
> corrected `tag_signals` pipeline before citing anything here.

# ER Lookback Study (2026-06-21)


## 1. Early-bar performance (current ER30 cross-session)

Bars 1-5 (first 25 min) use prior-session ER values — cross-session contamination.


### All signals (no ER filter)

| slice | n | net | exp | PF | win% |
|---|---|---|---|---|---|
| ALL | 5444 | $258,314 | $47 | 1.14 | 52.1% |
| bars 1-5 | 353 | $43,786 | $124 | 1.28 | 57.2% |
| bars 6+ | 5091 | $214,528 | $42 | 1.13 | 51.8% |


### With ER30 >= 0.30 gate

| slice | n | net | exp | PF | win% |
|---|---|---|---|---|---|
| ER30 all | 4439 | $385,558 | $87 | 1.28 | 54.9% |
| ER30 bars 1-5 | 276 | $36,322 | $132 | 1.30 | 56.5% |
| ER30 bars 6+ | 4163 | $349,237 | $84 | 1.28 | 54.7% |


### Per-bar expectancy (bars 1-12, no ER filter)

| slice | n | net | exp | PF | win% |
|---|---|---|---|---|---|
| bar 1 | 0 | — | — | — | — |
| bar 2 | 0 | — | — | — | — |
| bar 3 | 83 | $18,788 | $226 | 1.72 | 62.7% |
| bar 4 | 118 | $5,948 | $50 | 1.11 | 53.4% |
| bar 5 | 152 | $19,050 | $125 | 1.26 | 57.2% |
| bar 6 | 123 | $9,126 | $74 | 1.14 | 53.7% |
| bar 7 | 75 | $16,160 | $215 | 1.43 | 56.0% |
| bar 8 | 77 | $24,414 | $317 | 1.81 | 62.3% |
| bar 9 | 101 | $-4,665 | $-46 | 0.92 | 46.5% |
| bar 10 | 43 | $-4,575 | $-106 | 0.80 | 48.8% |
| bar 11 | 69 | $-7,901 | $-115 | 0.79 | 46.4% |
| bar 12 | 54 | $-6,635 | $-123 | 0.78 | 46.3% |


### Per-bar expectancy (bars 1-12, ER30 cross >= 0.30)

| slice | n | net | exp | PF | win% |
|---|---|---|---|---|---|
| bar 1 | 0 | — | — | — | — |
| bar 2 | 0 | — | — | — | — |
| bar 3 | 67 | $18,320 | $273 | 1.99 | 61.2% |
| bar 4 | 98 | $1,423 | $15 | 1.03 | 51.0% |
| bar 5 | 111 | $16,579 | $149 | 1.31 | 58.6% |
| bar 6 | 81 | $-4,153 | $-51 | 0.91 | 51.9% |
| bar 7 | 63 | $13,788 | $219 | 1.43 | 57.1% |
| bar 8 | 64 | $20,558 | $321 | 1.79 | 62.5% |
| bar 9 | 87 | $408 | $5 | 1.01 | 48.3% |
| bar 10 | 37 | $-4,336 | $-117 | 0.79 | 48.6% |
| bar 11 | 58 | $-5,640 | $-97 | 0.82 | 48.3% |
| bar 12 | 44 | $-5,379 | $-122 | 0.78 | 47.7% |


## 2. ER >= 0.30 gate: cross-session vs session-reset, by lookback

Session-reset: NaN (and therefore DROPPED) for bars with < N same-session bars.


| lookback | variant | passed | dropped | n_filled | net | exp | PF | win% |
|---|---|---|---|---|---|---|---|---|
| 5min | cross | 5263 | 181 | 5263 | $251,303 | $48 | 1.14 | 52.3% |
| 5min | reset | 5263 | 181 | 5263 | $251,303 | $48 | 1.14 | 52.3% |
| 10min | cross | 4380 | 1064 | 4380 | $468,903 | $107 | 1.36 | 55.8% |
| 10min | reset | 4380 | 1064 | 4380 | $468,903 | $107 | 1.36 | 55.8% |
| 15min | cross | 4818 | 626 | 4818 | $450,844 | $94 | 1.31 | 55.1% |
| 15min | reset | 4751 | 693 | 4751 | $426,386 | $90 | 1.29 | 54.9% |
| 30min | cross | 4439 | 1005 | 4439 | $385,558 | $87 | 1.28 | 54.9% |
| 30min | reset | 4083 | 1361 | 4083 | $361,773 | $89 | 1.30 | 54.9% |


## 3. Early bars: cross vs session-reset (30min / 6-bar lookback)

Session-reset drops bars 1-5 entirely (NaN). Cross keeps them with stale ER.


| slice | n | net | exp | PF | win% |
|---|---|---|---|---|---|
| cross ER30, bars 1-5 | 276 | $36,322 | $132 | 1.30 | 56.5% |
| cross ER30, bars 6+ | 4163 | $349,237 | $84 | 1.28 | 54.7% |
| reset ER30, bars 6+ | 4073 | $357,054 | $88 | 1.29 | 54.8% |

(Session-reset has no bars 1-5 by definition for span=6.)


## 4. Shorter lookbacks — session-reset keeps more early bars

With span=1 (5min), session-reset only drops bar 1. Span=2 drops bars 1-2, etc.


| lookback | variant | bars 1-5 passed | bars 1-5 exp | bars 6+ passed | bars 6+ exp | total net |
|---|---|---|---|---|---|---|
| 5min | cross | 344 | $115 | 4919 | $43 | $251,303 |
| 5min | reset | 344 | $115 | 4919 | $43 | $251,303 |
| 10min | cross | 298 | $175 | 4082 | $102 | $468,903 |
| 10min | reset | 298 | $175 | 4082 | $102 | $468,903 |
| 15min | cross | 305 | $202 | 4513 | $86 | $450,844 |
| 15min | reset | 238 | $156 | 4513 | $86 | $426,386 |
| 30min | cross | 276 | $132 | 4163 | $84 | $385,558 |
| 30min | reset | 10 | $472 | 4073 | $88 | $361,773 |


## 5. Threshold sensitivity by lookback (cross-session)

Does 0.30 remain the right threshold for shorter lookbacks?


| threshold | 5min exp (n) | 10min exp (n) | 15min exp (n) | 30min exp (n) |
|---|---|---|---|---|
| 0.20 | $48 (5263) | $91 (4751) | $75 (5044) | $72 (4849) |
| 0.25 | $48 (5263) | $98 (4561) | $85 (4940) | $79 (4637) |
| 0.30 | $48 (5263) | $107 (4380) | $94 (4818) | $87 (4439) |
| 0.35 | $48 (5263) | $118 (4183) | $100 (4683) | $93 (4200) |
| 0.40 | $48 (5263) | $127 (4050) | $110 (4563) | $102 (3923) |
| 0.50 | $48 (5263) | $152 (3788) | $127 (4255) | $110 (3365) |


## 6. Yearly breakdown — top candidates

Checking regime stability across years for each lookback at ER >= 0.30.



### 5min cross-session ER >= 0.30

| slice | n | net | exp | PF | win% |
|---|---|---|---|---|---|
| 2021 | 545 | $-1,314 | $-2 | 0.99 | 48.8% |
| 2022 | 1152 | $51,052 | $44 | 1.11 | 53.6% |
| 2023 | 1029 | $12,014 | $12 | 1.04 | 49.7% |
| 2024 | 948 | $37,179 | $39 | 1.13 | 52.5% |
| 2025 | 1090 | $106,285 | $98 | 1.25 | 53.8% |
| 2026 | 499 | $46,087 | $92 | 1.26 | 54.7% |
| ALL | 5263 | $251,303 | $48 | 1.14 | 52.3% |


### 10min cross-session ER >= 0.30

| slice | n | net | exp | PF | win% |
|---|---|---|---|---|---|
| 2021 | 440 | $9,544 | $22 | 1.10 | 51.6% |
| 2022 | 940 | $106,989 | $114 | 1.32 | 56.8% |
| 2023 | 880 | $56,351 | $64 | 1.28 | 53.5% |
| 2024 | 795 | $63,934 | $80 | 1.29 | 55.5% |
| 2025 | 916 | $158,731 | $173 | 1.50 | 58.0% |
| 2026 | 409 | $73,354 | $179 | 1.59 | 59.2% |
| ALL | 4380 | $468,903 | $107 | 1.36 | 55.8% |


### 15min cross-session ER >= 0.30

| slice | n | net | exp | PF | win% |
|---|---|---|---|---|---|
| 2021 | 494 | $12,859 | $26 | 1.12 | 51.4% |
| 2022 | 1042 | $94,957 | $91 | 1.24 | 56.0% |
| 2023 | 949 | $56,050 | $59 | 1.25 | 53.2% |
| 2024 | 864 | $65,508 | $76 | 1.27 | 55.1% |
| 2025 | 1010 | $159,396 | $158 | 1.44 | 57.0% |
| 2026 | 459 | $62,074 | $135 | 1.41 | 56.9% |
| ALL | 4818 | $450,844 | $94 | 1.31 | 55.1% |


### 30min cross-session ER >= 0.30

| slice | n | net | exp | PF | win% |
|---|---|---|---|---|---|
| 2021 | 451 | $6,796 | $15 | 1.06 | 51.2% |
| 2022 | 980 | $98,140 | $100 | 1.27 | 55.7% |
| 2023 | 872 | $54,298 | $62 | 1.26 | 53.9% |
| 2024 | 799 | $64,004 | $80 | 1.29 | 54.9% |
| 2025 | 930 | $108,470 | $117 | 1.31 | 55.4% |
| 2026 | 407 | $53,850 | $132 | 1.39 | 57.5% |
| ALL | 4439 | $385,558 | $87 | 1.28 | 54.9% |
