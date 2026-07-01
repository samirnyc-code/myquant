# RevFT continuation gate — pre-registered confirmatory test (2026-06-24)

## ⛔ VERDICT — GATE FAILS; RevFT CLOSED (read first)
- **Full sample never clears zero in R.** Continuation gate climbs −0.072R (1R) →
  −0.034R (2R) → −0.016R (3R) — asymptotes at BREAK-EVEN, never positive-significant.
- **Directional finding holds & is robust:** continuation (≈break-even) beats the
  REVERSION complement (firmly red, interval excludes 0 negative at every R) by ~0.07–
  0.09R. RevFT is a CONTINUATION signal, not mean-reversion. But that only avoids the
  loss; it does not make money.
- **Year-by-year kills the gate:** @3R the only positive-significant year is **2022**
  (+0.185R, +$45,650). 2024 +0.081 (∋0), 2021/2023 ∋0, **2025 −0.150 and 2026 −0.203
  both negative-significant.** The whole break-even is carried by 2022 — a single
  trending regime. Strip it → loser. Classic one-regime artifact.
- **Conclusion:** RevFT location is dead on every axis (extremes, VWAP-dev, value area);
  the mean-reversion premise is falsified; the continuation inversion is real as a
  direction but NOT tradeable (break-even, regime-dependent, recently negative). **Retire
  RevFT.** Pre-registration + year-by-year is what prevented a false positive here.

**Pre-registered gate** (fixed before this run, from the 0.5σ slice study): `continuation = (Long & VWAP_dev > +0.5σ) OR (Short & VWAP_dev < -0.5σ)` — RevFT fired WITH the move, on the far side of developing VWAP. Thesis: with-trend, edge grows with target → judged in R at 1R/2R/3R.

- **REVERSION** = the mean-reversion complement (should stay red). **NEUTRAL** = `|dev| ≤ 0.5` (inert). **BASELINE** = all filled.

- A group is a *finding* only if its R 95%-interval EXCLUDES zero AND it holds year-by-year. `(∋0)` flags an interval that still contains zero.

- **Honesty:** the +0.5σ threshold was chosen in-sample on this same 5yr set. This is selectivity confirmation, NOT out-of-sample. A pass earns a true OOS run.


# Target 1R

| group | n | net $ | exp $ | exp R | ±R CI | R-95% interval | PF | win% |
|---|---|---|---|---|---|---|---|---|
| BASELINE (all) | 6133 | $-183,540 | $-30 | -0.084 | ±0.024 | [-0.108, -0.061] | 0.88 | 46.1% |
| CONTINUATION gate | 2066 | $-51,333 | $-25 | -0.072 | ±0.041 | [-0.113, -0.031] | 0.91 | 46.5% |
|   · long leg (dev>+0.5) | 1148 | $-15,193 | $-13 | -0.052 | ±0.054 | [-0.106, +0.003]  (∋0) | 0.94 | 47.3% |
|   · short leg (dev<-0.5) | 918 | $-36,140 | $-39 | -0.097 | ±0.061 | [-0.158, -0.036] | 0.87 | 45.5% |
| REVERSION complement | 2586 | $-81,000 | $-31 | -0.099 | ±0.037 | [-0.135, -0.062] | 0.86 | 45.7% |
| NEUTRAL (|dev|<=0.5) | 1351 | $-51,540 | $-38 | -0.081 | ±0.051 | [-0.132, -0.031] | 0.85 | 46.1% |


# Target 2R

| group | n | net $ | exp $ | exp R | ±R CI | R-95% interval | PF | win% |
|---|---|---|---|---|---|---|---|---|
| BASELINE (all) | 6133 | $-147,052 | $-24 | -0.084 | ±0.031 | [-0.115, -0.053] | 0.92 | 34.8% |
| CONTINUATION gate | 2066 | $6,205 | $+3 | -0.034 | ±0.054 | [-0.088, +0.021]  (∋0) | 1.01 | 36.4% |
|   · long leg (dev>+0.5) | 1148 | $-6,968 | $-6 | -0.033 | ±0.072 | [-0.105, +0.038]  (∋0) | 0.98 | 36.4% |
|   · short leg (dev<-0.5) | 918 | $13,173 | $+14 | -0.034 | ±0.083 | [-0.117, +0.049]  (∋0) | 1.04 | 36.3% |
| REVERSION complement | 2586 | $-87,075 | $-34 | -0.108 | ±0.048 | [-0.156, -0.060] | 0.87 | 34.1% |
| NEUTRAL (|dev|<=0.5) | 1351 | $-56,853 | $-42 | -0.113 | ±0.066 | [-0.179, -0.048] | 0.86 | 33.6% |


# Target 3R

| group | n | net $ | exp $ | exp R | ±R CI | R-95% interval | PF | win% |
|---|---|---|---|---|---|---|---|---|
| BASELINE (all) | 6133 | $-118,290 | $-19 | -0.067 | ±0.036 | [-0.103, -0.031] | 0.94 | 31.7% |
| CONTINUATION gate | 2066 | $10,405 | $+5 | -0.016 | ±0.062 | [-0.078, +0.046]  (∋0) | 1.02 | 33.5% |
|   · long leg (dev>+0.5) | 1148 | $3,745 | $+3 | +0.003 | ±0.082 | [-0.079, +0.085]  (∋0) | 1.01 | 34.2% |
|   · short leg (dev<-0.5) | 918 | $6,660 | $+7 | -0.039 | ±0.094 | [-0.133, +0.055]  (∋0) | 1.02 | 32.6% |
| REVERSION complement | 2586 | $-89,537 | $-35 | -0.104 | ±0.055 | [-0.159, -0.048] | 0.87 | 30.5% |
| NEUTRAL (|dev|<=0.5) | 1351 | $-31,003 | $-23 | -0.074 | ±0.076 | [-0.151, +0.002]  (∋0) | 0.93 | 31.2% |


# Year-by-year — CONTINUATION gate


### 1R

| group | n | net $ | exp $ | exp R | ±R CI | R-95% interval | PF | win% |
|---|---|---|---|---|---|---|---|---|
| 2021 | 217 | $-13,121 | $-60 | -0.207 | ±0.122 | [-0.329, -0.084] | 0.67 | 41.0% |
| 2022 | 430 | $1,925 | $+4 | +0.008 | ±0.091 | [-0.083, +0.098]  (∋0) | 1.01 | 49.5% |
| 2023 | 393 | $-9,663 | $-25 | -0.069 | ±0.094 | [-0.163, +0.024]  (∋0) | 0.89 | 47.1% |
| 2024 | 425 | $-9,491 | $-22 | -0.062 | ±0.089 | [-0.150, +0.027]  (∋0) | 0.90 | 47.1% |
| 2025 | 417 | $-11,681 | $-28 | -0.069 | ±0.090 | [-0.160, +0.021]  (∋0) | 0.91 | 46.5% |
| 2026 | 184 | $-9,302 | $-51 | -0.134 | ±0.137 | [-0.271, +0.004]  (∋0) | 0.86 | 43.5% |


### 2R

| group | n | net $ | exp $ | exp R | ±R CI | R-95% interval | PF | win% |
|---|---|---|---|---|---|---|---|---|
| 2021 | 217 | $-6,834 | $-31 | -0.128 | ±0.161 | [-0.289, +0.033]  (∋0) | 0.84 | 34.6% |
| 2022 | 430 | $32,513 | $+76 | +0.106 | ±0.126 | [-0.020, +0.233]  (∋0) | 1.22 | 39.3% |
| 2023 | 393 | $-5,613 | $-14 | -0.064 | ±0.124 | [-0.187, +0.060]  (∋0) | 0.94 | 36.4% |
| 2024 | 425 | $6,297 | $+15 | +0.028 | ±0.121 | [-0.093, +0.149]  (∋0) | 1.06 | 38.4% |
| 2025 | 417 | $-7,643 | $-18 | -0.122 | ±0.115 | [-0.237, -0.007] | 0.95 | 33.6% |
| 2026 | 184 | $-12,515 | $-68 | -0.127 | ±0.175 | [-0.302, +0.048]  (∋0) | 0.83 | 33.2% |


### 3R

| group | n | net $ | exp $ | exp R | ±R CI | R-95% interval | PF | win% |
|---|---|---|---|---|---|---|---|---|
| 2021 | 217 | $-9,259 | $-43 | -0.149 | ±0.176 | [-0.325, +0.027]  (∋0) | 0.79 | 31.3% |
| 2022 | 430 | $45,650 | $+106 | +0.185 | ±0.151 | [+0.035, +0.336] | 1.30 | 36.5% |
| 2023 | 393 | $-6,038 | $-15 | -0.037 | ±0.140 | [-0.177, +0.103]  (∋0) | 0.94 | 34.1% |
| 2024 | 425 | $16,609 | $+39 | +0.081 | ±0.143 | [-0.062, +0.225]  (∋0) | 1.15 | 35.3% |
| 2025 | 417 | $-16,756 | $-40 | -0.150 | ±0.125 | [-0.274, -0.025] | 0.89 | 31.4% |
| 2026 | 184 | $-19,802 | $-108 | -0.203 | ±0.186 | [-0.389, -0.017] | 0.75 | 28.3% |
