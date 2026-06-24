# RevFT Trade-Location — VWAP deviation + value area (2026-06-24)

## ⛔ VERDICT — NEGATIVE, AND THE RESPONSIVE-FADE PREMISE IS FALSIFIED (read first)
- **No location subset clears the ~$15/trade cost hurdle with a CI excluding zero.** In R
  terms, every cell on the board is ≤0.
- **VWAP stretch runs the WRONG way vs the hypothesis.** Pre-registered "deeper favorable
  stretch → better fade" is backwards: least-stretched/continuation-side (`S<-1`) is the
  least-bad (−$14), deep favorable stretch (`S 2.0–3.0`) is catastrophic (−$197, −0.57R,
  22% win). Fading INTO a VWAP extension gets run over.
- **The pre-registered responsive cell (`S>1 AND V>0`) loses every year** (full sample
  −$40/trade, −0.120R, PF 0.81). Clean falsification.
- **The only positive-$ pockets are a wide-stop R-illusion** (long·VA-above +$14 but
  −0.021R; chase·VA-above +$28 but +0.020R, CI ±45 straddles 0). Positive in $, ~zero in
  R — they "win" only via bigger R-denominators. Judge in R, not $. The green tilt is
  toward price ABOVE prior value / continuation longs — the ANTI-responsive direction.
- **Conclusion:** dynamic location (VWAP/VA) joins static location (reversal_at_extreme)
  as dead. RevFT's problem is directional, not locational. Only untested lever left is a
  selectivity gate at wider R (`fade_revft` follow-up). Recommend stopping the location hunt.

**Question:** is there a SUBSET of RevFT defined by where the signal sits vs the developing-session VWAP and the prior-day value area that clears the ~$15/trade cost hurdle? Descriptive only — pinned 1.0R single-leg, real tick engine, look-ahead-safe features (S34 `tag_signals`).

- Signal set: `ba_signals_revft.parquet` · 6328 signals · filled: 6133 · with VWAP_dev: 6003 · with prior-VA dist: 5957

- **S** = directional VWAP stretch (σ): `-VWAP_dev` long / `+VWAP_dev` short. >0 = stretched on the mean-reversion-favorable side (long below VWAP / short above); <0 = fading on the continuation side (chasing).

- **V** = directional prior-day VA position (ADR): beyond the responsive-fade edge (long below prior VAL / short above prior VAH) is >0.

- **Verdict rule:** MONOTONIC gradient across a real sample (check ±95%CI). One lucky thin bucket ≠ edge.

- **NB (S37):** RevFT @1:1 is a firm net loser overall — selectivity hunt, not a validation.


**Baseline (ALL filled):** | ALL | 6133 | $-183,540 | $-30 | ±15 | -0.084 | 0.88 | 46.1% |


# A — VWAP deviation (directional stretch S)

### Both directions

| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| ALL | 6133 | $-183,540 | $-30 | ±15 | -0.084 | 0.88 | 46.1% |
| < -1.0 (chase) | 1368 | $-18,489 | $-14 | ±34 | -0.052 | 0.95 | 47.6% |
| -1.0..-0.25 | 998 | $-52,651 | $-53 | ±38 | -0.093 | 0.80 | 45.3% |
| -0.25..0.25 (at VWAP) | 675 | $-12,418 | $-18 | ±44 | -0.055 | 0.93 | 47.7% |
| 0.25..1.0 | 1358 | $-49,821 | $-37 | ±28 | -0.107 | 0.85 | 45.1% |
| 1.0..2.0 | 1550 | $-39,846 | $-26 | ±24 | -0.087 | 0.88 | 46.3% |
| 2.0..3.0 | 54 | $-10,648 | $-197 | ±89 | -0.566 | 0.28 | 22.2% |
| > 3.0 (deep stretch) | 0 | — | — | — | — | — | — |

### Long only (fade up — favorable BELOW VWAP)

| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| ALL | 3114 | $-71,915 | $-23 | ±20 | -0.075 | 0.91 | 46.7% |
| < -1.0 (chase) | 763 | $6,123 | $+8 | ±41 | -0.023 | 1.04 | 48.8% |
| -1.0..-0.25 | 523 | $-24,230 | $-46 | ±46 | -0.098 | 0.81 | 44.7% |
| -0.25..0.25 (at VWAP) | 352 | $-7,397 | $-21 | ±59 | -0.063 | 0.92 | 47.2% |
| 0.25..1.0 | 703 | $-39,253 | $-56 | ±44 | -0.126 | 0.80 | 44.4% |
| 1.0..2.0 | 692 | $-9,717 | $-14 | ±41 | -0.066 | 0.94 | 48.0% |
| 2.0..3.0 | 15 | $-3,090 | $-206 | ±212 | -0.479 | 0.35 | 26.7% |
| > 3.0 (deep stretch) | 0 | — | — | — | — | — | — |

### Short only (fade down — favorable ABOVE VWAP)

| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| ALL | 3019 | $-111,625 | $-37 | ±21 | -0.094 | 0.85 | 45.6% |
| < -1.0 (chase) | 605 | $-24,613 | $-41 | ±57 | -0.090 | 0.87 | 46.1% |
| -1.0..-0.25 | 475 | $-28,421 | $-60 | ±62 | -0.088 | 0.79 | 45.9% |
| -0.25..0.25 (at VWAP) | 323 | $-5,021 | $-16 | ±65 | -0.047 | 0.94 | 48.3% |
| 0.25..1.0 | 655 | $-10,568 | $-16 | ±35 | -0.087 | 0.92 | 45.8% |
| 1.0..2.0 | 858 | $-30,128 | $-35 | ±29 | -0.104 | 0.81 | 45.0% |
| 2.0..3.0 | 39 | $-7,558 | $-194 | ±95 | -0.600 | 0.24 | 20.5% |
| > 3.0 (deep stretch) | 0 | — | — | — | — | — | — |


# B — Prior-day value area

## B1 — categorical location (signal price vs prior VAH/VAL)

### Both directions

| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| ALL | 6133 | $-183,540 | $-30 | ±15 | -0.084 | 0.88 | 46.1% |
| above | 2287 | $-21,059 | $-9 | ±20 | -0.067 | 0.95 | 46.9% |
| inside | 1897 | $-65,333 | $-34 | ±27 | -0.093 | 0.87 | 46.0% |
| below | 1949 | $-97,148 | $-50 | ±30 | -0.096 | 0.83 | 45.4% |

### Long only

| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| ALL | 3114 | $-71,915 | $-23 | ±20 | -0.075 | 0.91 | 46.7% |
| above | 1072 | $14,939 | $+14 | ±31 | -0.021 | 1.07 | 49.3% |
| inside | 996 | $-45,268 | $-45 | ±38 | -0.110 | 0.83 | 44.9% |
| below | 1046 | $-41,586 | $-40 | ±37 | -0.097 | 0.86 | 45.7% |

### Short only

| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| ALL | 3019 | $-111,625 | $-37 | ±21 | -0.094 | 0.85 | 45.6% |
| above | 1215 | $-35,997 | $-30 | ±25 | -0.108 | 0.84 | 44.8% |
| inside | 901 | $-20,066 | $-22 | ±39 | -0.075 | 0.91 | 47.2% |
| below | 903 | $-55,562 | $-62 | ±47 | -0.095 | 0.80 | 45.1% |

## B2 — directional distance V beyond the responsive-fade edge (ADR)

### Both directions

| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| ALL | 6133 | $-183,540 | $-30 | ±15 | -0.084 | 0.88 | 46.1% |
| < -0.15 (far side) | 1454 | $-32,339 | $-22 | ±33 | -0.057 | 0.91 | 47.2% |
| -0.15..0.0 | 521 | $-8,284 | $-16 | ±46 | -0.049 | 0.93 | 47.6% |
| 0.0..0.15 | 2252 | $-66,944 | $-30 | ±24 | -0.081 | 0.88 | 46.4% |
| 0.15..0.30 | 407 | $-11,762 | $-29 | ±48 | -0.107 | 0.87 | 45.2% |
| 0.30..0.60 | 671 | $-22,563 | $-34 | ±41 | -0.087 | 0.85 | 45.6% |
| > 0.60 (deep beyond edge) | 652 | $-29,130 | $-45 | ±43 | -0.134 | 0.82 | 44.2% |

### Long only

| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| ALL | 3114 | $-71,915 | $-23 | ±20 | -0.075 | 0.91 | 46.7% |
| < -0.15 (far side) | 790 | $15,968 | $+20 | ±36 | -0.005 | 1.10 | 50.3% |
| -0.15..0.0 | 282 | $-1,030 | $-4 | ±60 | -0.067 | 0.98 | 46.5% |
| 0.0..0.15 | 1142 | $-49,392 | $-43 | ±35 | -0.094 | 0.84 | 45.6% |
| 0.15..0.30 | 181 | $-10,277 | $-57 | ±85 | -0.110 | 0.80 | 45.3% |
| 0.30..0.60 | 294 | $-6,519 | $-22 | ±70 | -0.083 | 0.92 | 45.6% |
| > 0.60 (deep beyond edge) | 318 | $-14,749 | $-46 | ±74 | -0.121 | 0.85 | 45.3% |

### Short only

| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| ALL | 3019 | $-111,625 | $-37 | ±21 | -0.094 | 0.85 | 45.6% |
| < -0.15 (far side) | 664 | $-48,308 | $-73 | ±58 | -0.120 | 0.78 | 43.7% |
| -0.15..0.0 | 239 | $-7,255 | $-30 | ±71 | -0.027 | 0.88 | 49.0% |
| 0.0..0.15 | 1110 | $-17,552 | $-16 | ±34 | -0.067 | 0.93 | 47.1% |
| 0.15..0.30 | 226 | $-1,485 | $-7 | ±54 | -0.105 | 0.96 | 45.1% |
| 0.30..0.60 | 377 | $-16,044 | $-43 | ±47 | -0.091 | 0.78 | 45.6% |
| > 0.60 (deep beyond edge) | 334 | $-14,381 | $-43 | ±46 | -0.147 | 0.78 | 43.1% |


# C — 2-D cross: VWAP stretch S × prior-day VA location

_Rows = S bands; within each, split by prior-day VA location._

| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| S < -1.0 (chase) · VA above | 538 | $15,054 | $+28 | ±45 | +0.020 | 1.14 | 51.1% |
| S < -1.0 (chase) · VA inside | 412 | $-9,759 | $-24 | ±69 | -0.071 | 0.92 | 46.6% |
| S < -1.0 (chase) · VA below | 418 | $-23,785 | $-57 | ±68 | -0.127 | 0.83 | 44.0% |
| S -1.0..-0.25 · VA above | 338 | $-2,036 | $-6 | ±49 | -0.043 | 0.97 | 47.6% |
| S -1.0..-0.25 · VA inside | 342 | $-15,916 | $-47 | ±66 | -0.079 | 0.83 | 46.5% |
| S -1.0..-0.25 · VA below | 318 | $-34,699 | $-109 | ±80 | -0.162 | 0.66 | 41.5% |
| S -0.25..0.25 (at VWAP) · VA above | 213 | $-3,129 | $-15 | ±60 | -0.070 | 0.93 | 46.5% |
| S -0.25..0.25 (at VWAP) · VA inside | 234 | $-3,195 | $-14 | ±70 | -0.071 | 0.94 | 47.0% |
| S -0.25..0.25 (at VWAP) · VA below | 228 | $-6,094 | $-27 | ±92 | -0.026 | 0.91 | 49.6% |
| S 0.25..1.0 · VA above | 474 | $-10,429 | $-22 | ±39 | -0.115 | 0.89 | 44.5% |
| S 0.25..1.0 · VA inside | 446 | $-29,445 | $-66 | ±49 | -0.153 | 0.74 | 43.0% |
| S 0.25..1.0 · VA below | 438 | $-9,947 | $-23 | ±58 | -0.053 | 0.92 | 47.7% |
| S 1.0..2.0 · VA above | 652 | $-26,693 | $-41 | ±33 | -0.105 | 0.78 | 45.2% |
| S 1.0..2.0 · VA inside | 400 | $-5,344 | $-13 | ±48 | -0.076 | 0.94 | 47.5% |
| S 1.0..2.0 · VA below | 498 | $-7,809 | $-16 | ±48 | -0.072 | 0.94 | 46.8% |
| S 2.0..3.0 · VA above | 28 | $-4,147 | $-148 | ±102 | -0.590 | 0.31 | 21.4% |
| S 2.0..3.0 · VA inside | 11 | $-3,223 | $-293 | ±257 | -0.648 | 0.23 | 18.2% |
| S 2.0..3.0 · VA below | 15 | $-3,278 | $-219 | ±184 | -0.461 | 0.28 | 26.7% |
| S > 3.0 (deep stretch) · VA above | 0 | — | — | — | — | — | — |
| S > 3.0 (deep stretch) · VA inside | 0 | — | — | — | — | — | — |
| S > 3.0 (deep stretch) · VA below | 0 | — | — | — | — | — | — |


# Year-by-year — a-priori responsive cell (S > 1.0 AND V > 0)

_Defined BEFORE seeing the cross above: a stretched VWAP fade that is also beyond the prior-day value edge. Stability check, not a tuned cell._

| year | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| 2021 | 85 | $-4,496 | $-53 | ±63 | -0.224 | 0.66 | 40.0% |
| 2022 | 233 | $-12,766 | $-55 | ±61 | -0.096 | 0.77 | 46.4% |
| 2023 | 189 | $-6,212 | $-33 | ±44 | -0.142 | 0.79 | 43.4% |
| 2024 | 192 | $-6,700 | $-35 | ±57 | -0.090 | 0.81 | 45.8% |
| 2025 | 184 | $-4,690 | $-25 | ±91 | -0.111 | 0.89 | 44.6% |
| 2026 | 107 | $-4,604 | $-43 | ±99 | -0.123 | 0.82 | 44.9% |

**Full-sample cell:** | S>1 & V>0 | 990 | $-39,466 | $-40 | ±29 | -0.120 | 0.81 | 44.6% |
