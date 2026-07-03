# Fable 5 MC Research Findings — Edge Concentration Study
**Date:** 2026-07-04
**Agent:** Fable 5 autonomous research run
**Data:** 5,640 MC signals 2021–2026 (5,540 filled), tick-simulated with realistic execution: entry next-bar-open +1 tick slip, exit_slip=1, stop_offset=1, commission $4.36/RT, 1 contract.
**Method:** All ~1,240 tick days loaded once; every signal simulated once at 1R and 2R; every filter below is a subset of that single cached simulation (identical execution assumptions everywhere). All features computed at or before the signal bar's close (causal); IB-break state uses the close of the first post-IB breaking bar; prior-day features come from the completed prior session; time-of-day is the signal bar close (CT).

**Realistic baseline (this run):**

```
All MC @ 1R:  n=5540  +0.021R [-0.002,+0.044]  WR=51%  PF=1.10  $+184,296  yrs+5/6
   2021:$-11,385  2022:$+35,515  2023:$+3,121  2024:$+26,069  2025:$+92,666  2026:$+38,311
Longs  @ 1R:  n=2959  +0.035R [+0.004,+0.066]  WR=53%  PF=1.15  $+143,986  yrs+6/6  CI>0
All MC @ 2R:  n=5540  +0.038R [+0.010,+0.067]  WR=44%  PF=1.13  $+262,621  yrs+5/6  CI>0
```
Note: the brief's baseline ($253K @1R) was computed with more optimistic exits. With exit_slip=1 the unfiltered 1R baseline **straddles zero** — filtering is not optional, it is what makes this tradeable.

---

## 1. WHAT WORKED (CI lower bound > 0, year-stable)

### ★ THE RECOMMENDATION — "Stack v2": three exclusions, nothing else

**Rules (all causal):**
1. **No counter-IB-break trades** — skip a Long if the session's 60-min IB has already broken DOWN (and not up) by the signal bar's close; skip a Short if IB has broken UP only. (Signals before any break, after an aligned break, or after both sides broke are all kept.)
2. **No prior trend day** — skip the whole day if the prior session's range > 1.6×ADR (`prior_adr_ext`, the existing S25 flag). This supersedes prior-day Double-Distribution exclusion: all 312 prev-DD signals are a strict subset of the 700 adr_ext signals.
3. **Before 14:00 CT** — skip signals whose bar closes at/after 14:00 (extends the known 13:00-decay finding; 14:00+ is outright negative).

```
STACK v2 @ 1R:  n=2925  +0.091R [+0.058,+0.125]  WR=56%  PF=1.25  $+253,072  yrs 6/6 positive  CI>0
   2021:$+9,380  2022:$+68,010  2023:$+40,903  2024:$+7,917  2025:$+86,832  2026:$+40,030
STACK v2 @ 2R:  n=2925  +0.120R [+0.077,+0.163]  WR=48%  PF=1.28  $+319,334  yrs 6/6 positive  CI>0
   2021:$+25,642  2022:$+87,498  2023:$+45,028  2024:$+28,229  2025:$+102,182  2026:$+30,755
```

**Robustness (all @1R unless noted):**
- Sub-period (lookahead check): 2021–22 n=977 +0.092R [+0.034,+0.151] PF 1.22 $+77,390; 2023–26 n=1948 +0.090R [+0.050,+0.131] PF 1.26 $+175,682 — nearly identical, no uniformity artifact (2021 and 2024 are weak years, as in the baseline).
- Both directions independently CI>0: Longs n=1577 +0.081R [+0.035,+0.126] PF 1.23 $+117,637; Shorts n=1348 +0.103R [+0.054,+0.153] PF 1.27 $+135,435. This filter is the first thing found that makes **shorts** work.
- Every CC type independently CI>0 inside the stack @1R:
  - CC1 n=66 +0.253R [+0.032,+0.475] WR 65% PF 1.76 $+17,337 (6/6 yrs)
  - CC2 n=460 +0.125R [+0.039,+0.212] WR 58% PF 1.33 $+52,769 (5/6)
  - CC3 n=886 +0.068R [+0.005,+0.130] WR 54% PF 1.18 $+55,425 (4/6)
  - CC4 n=906 +0.073R [+0.014,+0.133] WR 56% PF 1.18 $+56,962 (5/6) — even CC4 is fine inside the stack
  - CC5 n=607 +0.108R [+0.038,+0.179] WR 57% PF 1.35 $+70,578 (6/6)
- Cutoff sensitivity is smooth, not knife-edge (v1 stack, DD variant): 13:00 cutoff +0.083R n=2601; 14:00 +0.080R n=3148; 15:00 +0.062R n=3681 — all CI>0.
- Per-year n: 317–657 (never thin). ~2.5 trades/day vs 4.5 unfiltered.
- **The excluded complement is significantly negative**: n=2392 −0.057R [−0.089,−0.026] WR 46% PF 0.91 $−65,979, positive in only 1/6 years (v1 complement). The stack keeps 57% of trades and captures 137% of baseline net.
- Each exclusion contributes marginally on its own (all @1R): no counter-break n=4118 +0.044R [+0.017,+0.070] PF 1.13 $+194,983 (6/6); tod<14:00 n=4352 +0.039R [+0.011,+0.066] PF 1.13 $+205,838 (5/6); no prev-DD n=5228 +0.028R [+0.004,+0.051] PF 1.12 $+211,281 (5/6).

**Why it makes sense (a priori stories, not post-hoc):** counter-IB-break = fighting the day's declared range extension (Dalton: other-timeframe conviction); prior trend day = poor follow-through context after a range blow-out (already the S25 "skip" flag); post-14:00 decay extends the locked 13:00-decay finding.

### Secondary CI>0 findings (all causal, all @1R with realistic slip)

| Filter | n | E[R] | CI | WR | PF | Net | Years+ |
|---|---|---|---|---|---|---|---|
| **balance_state & stack v1** (size-up tier) | 627 | +0.159R | [+0.085,+0.232] | 60% | 1.36 | $+87,441 | 5/6 |
| **mss_event, tod<14** | 184 | +0.169R | [+0.040,+0.298] | 58% | 1.54 | $+37,860 | 6/6 |
| **stack v1 & 12:00–13:00 CT** | 530 | +0.143R | [+0.065,+0.220] | 58% | 1.42 | $+58,989 | 5/6 |
| **Long below weekly VA, tod<14** | 539 | +0.108R | [+0.031,+0.186] | 57% | 1.41 | $+98,000 | 6/6 |
| **Long above daily VA, tod<14** | 1160 | +0.074R | [+0.022,+0.126] | 56% | 1.25 | $+87,592 | 6/6 |
| 12:00–13:00 CT window (all signals) | 850 | +0.098R | [+0.036,+0.159] | 56% | 1.31 | $+75,106 | 6/6 |
| with-IB-break aligned (L/up, S/dn) | 1953 | +0.048R | [+0.009,+0.086] | 53% | 1.11 | $+65,960 | 5/6 |
| balance_state=True (standalone) | 933 | +0.078R | [+0.019,+0.137] | 55% | 1.21 | $+71,870 | 5/6 |
| prior_inside_day (standalone) | 575 | +0.080R | [+0.010,+0.150] | 55% | 1.41 | $+71,306 | 5/6 |
| Long below monthly VA | 623 | +0.085R | [+0.017,+0.152] | 55% | 1.40 | $+103,984 | 6/6 |
| Long above IB high (after IB) | 1116 | +0.065R | [+0.015,+0.115] | 54% | 1.22 | $+66,059 | 6/6 |
| Short when open above prior VA | 924 | +0.064R | [+0.008,+0.119] | 52% | 1.27 | $+77,921 | 5/6 |
| prev session VA migrated up (any dir) | 2273 | +0.052R | [+0.016,+0.088] | 53% | 1.20 | $+129,327 | 6/6 |
| prev day type = Normal | 1456 | +0.057R | [+0.013,+0.102] | 53% | 1.22 | $+95,052 | 5/6 |
| Long below VWAP | 534 | +0.071R | [+0.001,+0.141] | 57% | 1.31 | $+41,434 | 5/6 |

Detail on notable ones:
- **12:00–13:00 CT** is a genuine midday sweet spot, not a bin artifact: 11:30–12:30 +0.066R CI>0, 12:00–12:30 +0.077R, 12:30–13:00 +0.120R CI>0, then decays 13:00–13:30 (+0.031R) and goes negative after 14:00. 12–13 works for both directions (L +0.074R, S +0.124R CI>0) and 6/6 years overall ($4,053 / $21,507 / $15,347 / $13,300 / $18,536 / $2,364).
- **Long below weekly VA** — Dalton "price below value seeking value": vaW_pos gradient for longs is <−0.5 → +0.093R CI>0; [−0.5,0) → +0.100R CI>0; ≥1 (above weekly VA) → +0.005R dead. Interaction: L below wVA **and** below daily VA +0.132R [+0.038,+0.225] PF 1.63 n=325 (6/6 yrs, $70,733). Longs above weekly VA (n=1345) have zero edge — weekly value location is the strongest single long/no-long discriminator found.
- **balance_state & stack** is the best "size-up" tier: n=627 +0.159R PF 1.36, and at 2R +0.216R [+0.117,+0.315] PF 1.41 $+116,291 (6/6 yrs). Balance days (opened and still rotating inside prior range) reward MC breakout attempts — consistent with the "size, don't skip" balance candidate in the sizing backlog.
- **mss_event** (market-structure shift at the signal bar) is small-n but strikingly consistent: 6/6 years, both directions positive, +0.137R all-day / +0.169R before 14:00.

---

## 2. WHAT WAS FLAT (no exploitable lift, tested and closed)

- **Stochastic** (re-confirmed on realistic sim): K<20 +0.002R; K>80 +0.024R; K-aligned-with-trade +0.017R — nothing.
- **Intraday ER (ER_intra_6/12) quartiles**: all within ±0.03R of baseline, non-monotonic. High intraday ER does NOT improve MC signals; if anything low-ER longs were mildly better (+0.045R, ns).
- **Structural trend alignment**: aligned +0.022R vs counter +0.018R — structural_trend adds nothing directionally (unlike IB break, which does).
- **VWAP_dev quintiles (unsigned)**: mid quintile mildly negative, extremes mildly positive; only weakly informative. `vwap_dev_dir > 1.5σ` (extended in trade direction) is CI>0 (+0.034R [+0.000,+0.068], n=2600, 6/6 yrs) but the lift is small; deeper thresholds are non-monotonic → not recommended standalone.
- **Relative volume**: only Q3 [1.04,1.26) CI>0, Q4 flat — non-monotonic, treated as noise.
- **Stop size**: brief's tight-stop hypothesis is REFUTED — smallest stops are the worst (stop/ATR<0.10: −0.043R, PF 0.86); the largest-stop quartile is the only CI>0 bin (+0.051R). Wide stops = volatile bar = more room to the 1R target; do not filter for tight stops.
- **Gap direction / gap-fade vs gap-with**: both ~+0.02–0.03R, year-unstable (huge 2022/2025 flips). Gap-up days +0.034R CI>0 but mostly a long-regime proxy.
- **VA-migration alignment with trade direction**: aligned +0.018R vs counter +0.031R — the migration level matters (up-migration good for everything), the alignment doesn't.
- **POC distance** (at-POC vs far-from-POC): flat both ways.
- **Consecutive same-direction clusters**: samedir_n_day=3 pops CI>0 (+0.058R) but n≥4 collapses to +0.006R — non-monotonic, not a real dose-response; treated as noise. sig_n_day≥4 (late-day over-signaling) is dead (+0.000R), but that's mostly the time-of-day effect.
- **EMA-20 side, dev-range position, room-to-session-extreme**: single CI>0 bins, non-monotonic → noise.

## 3. WHAT WAS NEGATIVE (avoid / exclusion rules)

| Condition | n | E[R] | CI | WR | PF | Net | Years+ |
|---|---|---|---|---|---|---|---|
| Signals at/after 14:00 CT | 1188 | −0.047R | [−0.083,−0.010] | 45% | 0.92 | $−21,542 | 3/6 |
| Counter-IB-break (L after dn-break / S after up-break) | 1422 | −0.046R | [−0.090,−0.002] | 48% | 0.97 | $−10,687 | 3/6 |
| Short after IB up-break | 655 | −0.080R | [−0.145,−0.016] | 45% | 0.89 | $−20,293 | 2/6 |
| Prior day trend day (adr_ext, range>1.6×ADR) | 700 | −0.069R | [−0.133,−0.005] | 47% | 0.93 | $−25,414 | 2/6 |
| Prior day = Double Distribution (subset of above) | 312 | −0.096R | [−0.191,−0.000] | 46% | 0.82 | $−26,985 | 3/6 |
| Short above VWAP | 532 | −0.081R | [−0.155,−0.006] | 46% | 0.84 | $−23,357 | 3/6 |
| Stack-v1 complement (union of the 3 exclusions) | 2392 | −0.057R | [−0.089,−0.026] | 46% | 0.91 | $−65,979 | 1/6 |
| CC3 Shorts (baseline population) | 754 | −0.055R | [−0.119,+0.009] | 47% | 0.88 | $−36,062 | 1/6 |

CC3 Shorts note: inside stack v1 they recover to +0.014R (ns) — most of their damage is counter-break/afternoon trades, so a separate CC3-short exclusion is optional, not required.

## 4. SINGLE BEST RECOMMENDATION

**Trade all MC signals (all CC types, both directions) with three skip rules: (1) skip counter-IB-break signals, (2) skip days after a >1.6×ADR prior trend day, (3) stop taking signals at 14:00 CT.**

At 1R: n=2,925 (~2.4/day), +0.091R [+0.058,+0.125], WR 56%, PF 1.25, $+253,072 over 5.5 years on 1 contract — vs the realistic unfiltered baseline of +0.021R (CI straddling 0) and $184K on 5,540 trades. Fewer trades, more money, positive every single year, significant in both halves of the sample, in both directions, and in all five CC types. It also clears the success bar at 2R (+0.120R [+0.077,+0.163], $319K), though 1R remains the house-locked target.

Optional overlay consistent with the "size, don't skip" doctrine: **size up on balance days** (balance_state=True inside the stack: +0.159R, PF 1.36, n=627, and +0.216R at 2R) and on **longs below the weekly value area** (+0.133R inside the stack, n=309).

## 5. OPEN HYPOTHESES (formed, not fully tested)

1. **Sizing tiers instead of binary skip**: stack + {balance_state, L-below-wVA, 12:00–13:00, mss_event} all sit at +0.13–0.17R with CI>0 — a 2x-size tier on any of these overlaps needs a portfolio-level test (overlapping concurrent risk not modeled here).
2. **Why 12:00–13:00?** Hypothesis: lunch balance resolves into afternoon range extension, and MC channels that persist through lunch carry real institutional flow. Could be tested by conditioning the midday window on IB-extension state.
3. **LVN proximity** (Tier 2 #12): not built — needs a volume-at-price profile engine per session; POC-distance proxy was flat, but true LVN gaps might not be.
4. **ETH/overnight context**: overnight inventory (ONH/ONL, overnight VWAP) is absent from the bar file (RTH-only bars); the gap features only partially capture it.
5. **Counter-break signals as fades**: the counter-break set is −0.046R at 1R as trend trades; whether they profit as opposite-direction entries was not tested (would need re-simulation with flipped direction/stops).
6. **2R target for the stack**: the stack's 2R expectancy (+0.120R) exceeds its 1R (+0.091R) with the same n — the "1R is locked" decision was made on the unfiltered population and might deserve a re-examination on the stacked subset (EOD exits are 505/2925 — midday entries have time to develop).

## Reproduction

Scripts in the session scratchpad (`build_cache.py` = feature build + one-shot tick sim at 1R/2R; `alib.py` = stats; `t1_scan.py`, `t1b_scan.py`, `t1c_scan.py`, `t2_dig.py`, `final_val.py` = the scans above). Features: `indicators.tag_signals` + `auction_features.build_session_features` (prior-session shifted via next-session-date mapping, not calendar +1day) + custom causal columns (IB-break timestamps from bar closes, tod, stop/ATR, VA-position scalars, cluster counts, 20-day relative cum-volume). Execution: entry_slip=1, exit_slip=1, stop_offset=1, commission=$4.36, 1 contract, tick-based fills.

---

# Round 2 — Sizing, Exits, Fades, RevFT, Bar Tells
**Date:** 2026-07-04. Base = Stack v2 (no counter-IB-break, no prior trend day >1.6×ADR, before 14:00 CT), n=2,925. Same realistic execution (entry_slip=1, exit_slip=1, stop_offset=1, $4.36 commission). All sims tick-based; sizing/management tests computed per-signal off the cached tick sims (PnL scales exactly with contracts).

## Test 1 — Edge-score sizing vs binary skips: SIZING WINS

Size-up features (each independently CI>0 in Round 1): `balance_state`, Long-below-weekly-VA, `mss_event`. Inside the stack the tier gradient is real:
```
tier base (score=0):  n=2091  +0.057R [+0.017,+0.096]  WR=54%  PF=1.14  $+98,196
tier +1  (score=1):   n= 750  +0.176R [+0.110,+0.242]  WR=60%  PF=1.57  $+141,830
tier +2  (score>=2):  n=  84  +0.186R [-0.015,+0.386]  WR=61%  PF=1.30  $+13,046   (thin)
```
Portfolio comparison @1R (E/ctr = contract-weighted R expectancy; maxDD on daily equity):
```
FLAT 1x stack:            2925 ctr  +0.091R/ctr  PF=1.25  $+253,072  maxDD $-20,519  net/DD 12.3
TIERED 1/2 (2x if any):   3759 ctr  +0.110R/ctr  PF=1.31  $+407,948  maxDD $-32,770  net/DD 12.5
  2021:$+20,473 2022:$+112,661 2023:$+56,308 2024:$+8,608 2025:$+128,877 2026:$+81,022
FLAT 1.29x (risk-match):  3759 ctr  +0.091R/ctr  PF=1.25  $+325,230  maxDD $-26,369  net/DD 12.3
TIERED 1/2/3:             3843 ctr  +0.112R/ctr  PF=1.31  $+420,995  maxDD $-39,895  net/DD 10.6
```
**Verdict:** 1/2 tiering beats a risk-matched flat scale by +$83K (+25%) at equal average contracts with slightly better net/DD. The 1/2/3 version adds little and concentrates DD (score≥2 is only 84 trades) — use 1/2.

## Test 2 — Fade the poison: DEAD

Counter-IB-break signals flipped (opposite direction, stop mirrored at same distance), realistic costs:
```
FADE @1R:  n=1422  -0.054R [-0.098,-0.010]  WR=47%  PF=0.83  $-77,425  maxDD $-103,205  yrs+2/6  CI<0
FADE @2R:  n=1422  -0.045R [-0.099,+0.008]  WR=41%  PF=0.84  $-75,800  yrs+1/6
```
The complement's −0.057R does not survive being traded from the other side: 2× slippage + commission (~0.09R round trip at median stop) eats the mirror edge. Do not fade; just skip.

## Test 3 — Exit re-examination on the stacked subset: 1R IS NOT OPTIMAL HERE

Full grid on the same 2,925 stack signals (fixed-R targets; ratchet = move stop to BE once +1R is touched):
```
target 0.5R:   +0.019R [-0.006,+0.043]  WR=68%  PF=1.09  $+72,859   maxDD $-29,248  net/DD  2.5
target 0.75R:  +0.053R [+0.024,+0.083]  WR=61%  PF=1.18  $+162,984  maxDD $-24,619  net/DD  6.6
target 1.0R:   +0.091R [+0.058,+0.125]  WR=56%  PF=1.25  $+253,072  maxDD $-20,519  net/DD 12.3
target 1.25R:  +0.103R [+0.066,+0.139]  WR=52%  PF=1.26  $+277,172  maxDD $-21,586  net/DD 12.8
target 1.5R:   +0.102R [+0.062,+0.141]  WR=50%  PF=1.25  $+275,435  maxDD $-24,363  net/DD 11.3
target 2.0R:   +0.120R [+0.077,+0.163]  WR=48%  PF=1.28  $+319,334  maxDD $-28,426  net/DD 11.2
target 2.5R:   +0.117R [+0.072,+0.162]  WR=46%  PF=1.27  $+313,547  maxDD $-29,176  net/DD 10.7
target 3.0R:   +0.130R [+0.083,+0.177]  WR=46%  PF=1.29  $+341,960  maxDD $-28,163  net/DD 12.1
target 4.0R:   +0.132R [+0.084,+0.181]  WR=46%  PF=1.30  $+354,872  maxDD $-28,869  net/DD 12.3
2R + BE@1R:    +0.127R [+0.086,+0.167]  WR=42%  PF=1.31  $+314,772  maxDD $-22,967  net/DD 13.7
3R + BE@1R:    +0.135R [+0.090,+0.179]  WR=40%  PF=1.33  $+332,910  maxDD $-23,307  net/DD 14.3  <- best
  2021:$+32,355 2022:$+94,885 2023:$+55,453 2024:$+29,742 2025:$+78,619 2026:$+41,855  (6/6)
```
ATR-scaled targets (k×prior_ATR, quantized to the grid) are uniformly worse than fixed-R (best k=0.6: +0.115R, $279K, net/DD 10.1) — the stop distance already encodes the right scale.

**Verdict:** the locked "1R is right" conclusion was a property of the unfiltered population. Inside Stack v2, expectancy rises monotonically with target and **3R with break-even ratchet after +1R dominates**: +32% more net than 1R, higher PF, best net/DD (14.3), positive 6/6 years (weakest year 2024 +$29.7K vs 1R's +$7.9K). The BE ratchet brings wide-target DD back near 1R levels. Worth re-opening the locked decision *for the stacked subset only*.

## Test 4 — RevFT × MC interaction: MILD CORROBORATION, NOT A RULE

RevFT file verified: exactly 6,442 signals parsed from the specified SEP26 export. Context: RevFT signals traded standalone @1R are strongly negative (n=6,169, −0.116R [−0.140,−0.092], PF 0.84, $−238,159, 0/6 years).

- **4a (causal outcome test — RevFT trade must have RESOLVED via tick-sim exit time before the MC signal):** MC in the same direction as a RevFT winner resolved within the last 120 min, inside stack: n=715, +0.173R [+0.108,+0.239], WR 60%, PF 1.43, $+90,770, 6/6 years (2021:$+12,469 2022:$+4,547 2023:$+22,746 2024:$+30,869 2025:$+17,005 2026:$+3,135). BUT after a same-direction RevFT *loser*: +0.061R (ns, n=204) — and after an *opposite* RevFT winner: +0.114R CI>0 (n=251). Outcome and direction barely discriminate; most of the lift is "a reversal attempt just resolved nearby", overlapping with the mss/balance context.
- **4b (same-direction RevFT signal within N bars, no outcome needed):** inside stack, N=12: n=1,023, +0.120R [+0.064,+0.176], PF 1.32, $+100,002 — but 2025 +$5.6K / 2026 −$11.1K vs no-RevFT control +0.057R. Year-unstable lift.
- **4c (conflict skip):** NOT supported — opposite-direction RevFT within 12 bars inside stack is +0.139R CI>0 (n=435). Standalone (ALL, N=3/6) it is negative but small-n/straddling. Do not skip on conflict.

**Verdict:** usable at most as a minor sizing feature (4a win-same-120m); not a filter.

## Test 5 — Distance from session extreme: STRONGEST NEW SIZING FEATURE

Pullback depth = distance from the developing session extreme in the trade direction (Long: dev_High − price; Short: price − dev_Low), normalized by 20-day avg 5M bar range (abr) or prior ATR. Inside the stack the gradient is clean and 6/6-year stable at the top:
```
pull_abr STACK [<0.16):      n=690  +0.094R [+0.025,+0.163]  PF=1.17  $+41,642   (at the extreme)
pull_abr STACK [0.16,0.36):  n=690  +0.076R [+0.007,+0.145]  PF=1.16  $+40,929
pull_abr STACK [0.36,0.86):  n=690  +0.097R [+0.028,+0.167]  PF=1.26  $+67,429
pull_abr STACK [>=0.86):     n=690  +0.163R [+0.096,+0.230]  WR=60%  PF=1.62  $+120,129  6/6yrs  <- deep pullback
```
(ADR normalization identical: top quartile ≥0.08×prior_ATR → +0.163R PF 1.63.) On ALL signals the pattern is weaker and the deepest quartile flips negative (−0.018R) — the stack context is what makes deep pullbacks safe to enter.
Travel from the opposite extreme (early-vs-late in move), inside stack: monotone decreasing — early-in-move best: trav_abr <3.31 → +0.164R [+0.093,+0.235] PF 1.46 (6/6); >7.19 → +0.071R. Confirms the user hypothesis: **best MC trades are early in the day's directional travel AND pulled back ≥ ~1 avg bar range from the session extreme**. Unfiltered, the effect washes out — these are size modifiers inside the stack, not standalone filters.

## Test 6 — Bar-close tells

**6a (signal bar character, causal filter):** Signal bar closing AGAINST the signal direction (close vs open): ALL −0.063R (n=381) vs WITH +0.027R; inside stack AGAINST −0.003R (n=237) vs WITH +0.099R. A small, coherent extra skip (~8% of stack trades, ~zero-EV ones). Close-location: mid-bar closes (0.33–0.67 of range toward trade direction) outperform closes AT the extreme inside the stack (+0.177R [+0.111,+0.242] PF 1.55 vs +0.077R [+0.036,+0.118]) — closing pinned at the bar extreme looks like short-term exhaustion. Body/range and bar-range/abr: flat. Optional refinement, kept out of the headline config to avoid over-stacking.

**6b (entry-bar close as tell):** hugely *prognostic* but mostly *unactionable*. Among stack trades still open at the entry bar close (2,894/2,925), final outcome by entry-bar close vs entry (fraction of stop distance):
```
x1 < -0.5:       n=  52  -0.652R  WR=19%  PF=0.24   |   x1 [0,0.25):   n=980  +0.240R  WR=64%  PF=1.79
x1 [-0.5,-0.25): n= 298  -0.245R  WR=38%  PF=0.58   |   x1 [0.25,0.5): n=257  +0.410R  WR=73%  PF=2.24
x1 [-0.25,0):    n=1097  +0.002R  WR=51%  PF=1.01   |   x1 >= 0.5:     n= 61  +0.816R  WR=93%  PF=11.2
```
But bail rules (exit at market on entry-bar close if against by >X of stop distance, 1-tick slip) do NOT beat holding inside the stack @1R: X=0 → $+84,922 (destroys value; the big [-0.25,0) bucket is neutral, not negative); X=0.25 → $+222,410; X=0.5 → $+249,785 vs hold $+253,072. By the time the bar closes >50% against, most of the loss is sunk — the stop is already doing its job.

**6c (bail at the NEXT bar close, >50% against):** the only management variant that (modestly) beats holding: stack @1R n=2925, bailed=124, **+0.096R [+0.063,+0.129], PF 1.27, $+267,884, maxDD $−20,081** vs hold $+253,072 / PF 1.25 / maxDD $−20,519; improves or matches every year (2021 $+9,005 / 2022 $+71,485 / 2023 $+42,215 / 2024 $+11,167 / 2025 $+90,182 / 2026 $+43,830). On ALL signals it helps more ($+217,596 vs $+184,296 baseline). Small edge, real but second-order. (Tested at 1R; not yet re-tested under the 3R+BE exit.)

## Round 2 combined recommendation

**Stack v2 + 3R target with BE-after-1R + 1/2 tier sizing** (2 contracts when any of: balance_state, Long-below-weekly-VA, mss_event, pullback ≥0.86×avg-bar-range; else 1):
```
                                       contracts  E/ctr     PF    net        maxDD     net/DD
3R+BE flat 1x                          2925       +0.135R   1.33  $+332,910  $-23,307  14.3
3R+BE tiered 1/2 (bal/bwva/mss)        3759       +0.160R   1.41  $+542,836  $-36,480  14.9
3R+BE tiered 1/2 (+pull>=0.86abr)      4262       +0.162R   1.42  $+609,118  $-38,809  15.7  <- best
  2021:$+61,418 2022:$+162,015 2023:$+83,758 2024:$+59,248 2025:$+149,122 2026:$+93,557  (6/6)
3R+BE flat 1.29x (risk-match ref)      3773       +0.135R   1.33  $+429,453  $-30,066  14.3
```
Sizing tiers: 1,588 base / 1,337 doubled. Every year ≥ $+59K. The tiered book beats the risk-matched flat book on every metric (E/ctr, PF, net, net/DD). Caveats: maxDD measured on daily closes; concurrent-position overlap not modeled (simultaneous 2-lot trades possible); tier features were selected on the same sample they are sized on — the tier *weights* (not the stack itself) deserve out-of-sample confirmation on 2026H2 data.

**Round 2 open items:** re-test the 6c bail rule under the 3R+BE exit; validate tier weights out-of-sample; portfolio-level margin/overlap check for the 2-lot tier.

---

# Round 3 — Validation & Hardening of the Combined Config
**Date:** 2026-07-04. Config under test: Stack v2 + 3R target with BE-after-1R + 1/2 tiering (2x when any of balance_state / Long-below-weekly-VA / mss_event / pullback ≥0.86×abr). Same realistic execution. All numbers from the cached per-signal tick sims.

## Test 1 — Walk-forward (expanding train, annual test 2023→2026): SURVIVES

Each window re-selects (a) tier features on train years (@1R, keep if lift > +0.02R and n≥40) and (b) the exit from {1R, 1.5R, 2R, 3R, 2R+BE, 3R+BE} by train net/DD; frozen choices applied to the test year.

**Selection stability:** the exit choice is perfectly stable — **3R+BE wins every window** (and the train net/DD ordering is monotone: BE variants > plain wide > 1R in all four windows). Features: `bal` and `pull` selected 4/4 windows, `mss` 3/4, `bwva` 2/4 — the two features that matter most are always in.

```
window->2023: feats=[bal,pull]           exit=3R+BE
window->2024: feats=[bal,bwva,mss,pull]  exit=3R+BE
window->2025: feats=[bal,mss,pull]       exit=3R+BE
window->2026: feats=[bal,bwva,mss,pull]  exit=3R+BE

WF-OOS 2023-26 tiered:  n=1948 ctr=2793  +0.139R [+0.085,+0.192]  WR=38%  PF=1.39  $+367,473  maxDD $-35,554  net/DD 10.3
   2023:$+70,215  2024:$+59,248  2025:$+144,453  2026:$+93,557   (4/4 years positive, CI>0)
WF-OOS 2023-26 flat 1x: n=1948           +0.116R [+0.063,+0.169]  WR=38%  PF=1.31  $+205,669  maxDD $-23,307
IS-selected config, same years (ref):    +0.140R [+0.087,+0.194]  PF=1.40  $+385,685  maxDD $-37,742  net/DD 10.2
```
**OOS degradation vs in-sample selection: −4.7% net (identical E[R], PF, net/DD).** The tier/exit selection process is not the source of the edge — the walk-forward result is statistically indistinguishable from the in-sample pick. (The stack rules themselves were frozen from Round 1 throughout.)

## Test 2 — Portfolio overlap & position caps: THE $609K NEEDS ~6 CONTRACTS OF HEADROOM

3R+BE trades live much longer than 1R; overlap is heavy. Uncapped concurrency (tiered book): **max 18 contracts, p95-at-entries 7, p99 10, mean 2.9**. Margin peak: ~$216K on ES ($12K/ctr) — or **~$21.6K trading the same book in MES** (10×1/10 lots).

Cap rule: process signals chronologically; take min(size, remaining capacity), skip if none free.
```
uncapped: 4262 ctr  +0.162R/ctr  PF=1.42  $+609,118  maxDD $-38,809  net/DD 15.7
cap=6:    4051 ctr  +0.158R/ctr  PF=1.40  $+563,463  maxDD $-38,300  net/DD 14.7   (92% of net kept; skipped 131)
cap=4:    3632 ctr  +0.136R/ctr  PF=1.34  $+433,989  maxDD $-38,767  net/DD 11.2   (71%; skipped 389)
cap=3:    3162 ctr  +0.118R/ctr  PF=1.28  $+323,289  maxDD $-40,939  net/DD  7.9   (53%; skipped 530)
cap=2:    2518 ctr  +0.114R/ctr  PF=1.24  $+225,697  maxDD $-42,636  net/DD  5.3   (37%; skipped 1102)
```
All caps stay CI>0 and 6/6-years positive, but net/DD degrades under tight caps because the cap preferentially drops clustered trades (which are disproportionately the good midday runs). **Realistic answer: no, the full $609K does not survive a 2–4 contract cap — plan for ~6 contracts of headroom (ES margin ~$72K, or MES ~$7.2K) to keep >90% of it.**

Daily realized P&L (999 trading days): uncapped worst day **$−14,251**, p5 $−4,530, median $−117, best $+41,372. Cap=3: worst $−9,097, p5 $−3,815, best $+18,574. For prop-firm daily-loss limits, cap=3 in MES units implies worst day ≈ −$910.

## Test 3 — 6c bail under 3R+BE: STILL ADDS (no interaction with BE@1R)

Bail = exit at market on the close of the bar after the entry bar if >50% of stop distance against (fires early, long before the BE ratchet is relevant — no conflict).
```
3R+BE flat, no bail:   +0.135R [+0.090,+0.179]  WR=40%  PF=1.33  $+332,910  maxDD $-23,307  net/DD 14.3
3R+BE flat + 6c bail:  +0.137R [+0.093,+0.180]  WR=39%  PF=1.34  $+341,885  maxDD $-22,729  net/DD 15.0  (bailed 124)
   2021:$+31,492  2022:$+95,660  2023:$+57,465  2024:$+33,317  2025:$+78,294  2026:$+45,655   (>= no-bail in 4/6 yrs, ~equal rest)
TIERED + 6c bail:      +0.164R [+0.120,+0.208]  WR=39%  PF=1.44  $+622,830  maxDD $-38,372  net/DD 16.2  <- new best book
   2021:$+59,930  2022:$+165,127  2023:$+87,983  2024:$+64,323  2025:$+145,597  2026:$+99,869
```

## Test 4 — 2026 holdout (Jan–Jul 2026, closest to live-forward)

```
2026 flat 1x:  n=317  +0.144R [+0.016,+0.273]  WR=39%  PF=1.32  $+41,855  maxDD $-19,519
2026 tiered:   n=317  +0.180R [+0.053,+0.308]  WR=39%  PF=1.53  $+93,557  maxDD $-26,897
monthly (tiered): Jan -$15,105 / Feb +$63,210 / Mar +$16,150 / Apr +$39,992 / May -$14,723 / Jun +$4,656 / Jul -$623
```
CI>0 on the year even standalone. Note the texture: two losing months and a January drawdown before payoff — the intra-year maxDD (−$27K) is large relative to a single year's net; this is a lumpy, trend-capture book, consistent with 40% WR at 3R.

## Round 3 bottom line

The combined config survives walk-forward (−4.7% OOS degradation, exit choice unanimous, core tier features stable), survives realistic position caps with CI>0 (though tight caps cost 30–60% of net — budget ~6 contracts of headroom or trade MES), still benefits from the 6c bail (new best: **+0.164R/ctr, PF 1.44, $+622,830, maxDD $−38,372, net/DD 16.2**), and its 2026 holdout year is independently CI>0 (+0.180R, PF 1.53, $+93,557). Remaining honest caveats: the stack rules themselves were discovered on this full sample (only the tiering/exit passed true OOS re-selection); concurrency cap simulation assumes skip-if-full rather than queueing; margin figures are approximate.

---

# Round 4 — Deployment: CC Mix, EOD Reality, MES Prop Constraints
**Date:** 2026-07-04. Best book = Stack v2 + 3R/BE@1R + 6c bail + 1/2 tiering (bal/bwva/mss/pull≥0.86abr). Reference: n=2,925, 4,262 ctr, +0.164R [+0.120,+0.208], PF 1.44, $+622,830, maxDD $−38,372.

## Test 1 — CC-type breakdown inside the best book: KEEP ALL FIVE

Per type (tier-weighted):
```
CC1: n=  66 ctr= 114  +0.342R [+0.035,+0.649]  WR=44%  PF=2.11  $+41,303   maxDD $-10,044  yrs 5/6
CC2: n= 460 ctr= 704  +0.234R [+0.114,+0.354]  WR=38%  PF=1.63  $+147,668  maxDD $-25,453  yrs 4/6
CC3: n= 886 ctr=1274  +0.138R [+0.057,+0.219]  WR=36%  PF=1.37  $+154,745  maxDD $-21,601  yrs 6/6
CC4: n= 906 ctr=1304  +0.139R [+0.061,+0.217]  WR=40%  PF=1.31  $+143,040  maxDD $-19,103  yrs 6/6
CC5: n= 607 ctr= 866  +0.159R [+0.072,+0.247]  WR=43%  PF=1.49  $+136,074  maxDD $-16,517  yrs 6/6
```
Every type is independently CI>0 inside the config — including CC4 (historically problematic), which is positive all 6 years here. Leave-one-out:
```
drop CC1: $+581,527  net/DD 17.1   drop CC4: $+479,791  net/DD 19.9  PF 1.50
drop CC2: $+475,162  net/DD 12.4   drop CC5: $+486,756  net/DD 12.7
drop CC3: $+468,085  net/DD 17.1
```
Dropping CC4 (or CC3) improves aggregate net/DD (the 2021–22 DD windows are CC3/CC4-heavy) but costs ~$143K (23%) of net, and the "improvement" is a single-DD-window artifact rather than a per-year pattern — CC4 is 6/6 years positive with PF 1.31. **Verdict: keep all five in the standard book; dropping CC4 is a legitimate option only for DD-constrained accounts (see Test 3), not an edge statement.**

## Test 2 — EOD mechanics: VERIFIED REALISTIC; 15:00 flat is equivalent

Engine mechanics (verified in `simulation_engine.py` exit path): if neither target nor stop is hit, the trade exits at the **last tick of the RTH session** (~15:14:59 CT) at last-tick price with 1-tick exit slip. Tick data is RTH-only (08:30–15:15 CT), so trades cannot span days — there are no overnight holds and no artificial EOD prices. Nothing to fix.

Exit mix of the best book: Target 7.4% (+$703,514 tiered), Stop 49.4% (−$1,207,335), **EOD 38.9% (+$1,228,616)**, Bail 4.2% (−$101,965). This book's profits are mostly *winners ridden to the close* — the 3R target functions as a cap on the best runs, and the BE ratchet + stop absorb the rest. 40.4% of trades are still open at 15:00 CT.

Explicit "flat by 15:00 CT" variant (exit open trades at the 15:00 bar close −1 tick; excludes 61 early-close-day trades with no 14:55 bar):
```
flat @15:00:      n=2864  +0.171R [+0.127,+0.216]  PF=1.45  $+626,692  maxDD $-38,072  net/DD 16.5  6/6
session close:    n=2925  +0.164R [+0.120,+0.208]  PF=1.44  $+622,830  maxDD $-38,372  net/DD 16.2  6/6
```
Statistically identical (15:00 marginally better) — the last 15 minutes carry no edge. Use whichever is operationally easier.

## Test 3 — MES + prop account with $4,500 trailing max drawdown: ONLY 1x SURVIVES

Assumptions: MES $1.25/tick ($5/pt), commission **$1.40/RT per MES lot**, same 1-tick slippage (per-lot P&L = ES gross/10 − $1.40). Trailing DD off the equity high-water mark, never locks. Base test on closed-trade equity; stricter variant adds each trade's MAE dip (per-trade approximation, concurrent overlap not compounded).

**(a) Historical survival sweep (tiered book, lots = tier × N):**
```
N=1: SURVIVES (closed and intraday-approx)  — min remaining room $639 (!)
N=2: breaches 2022-03-03    N=3: 2021-12-01    N=4: 2021-10-14    N=5/6: Oct/Aug 2021
```
Only **N=1 (1 MES base / 2 MES on tier trades)** survives the full 5.5 years, and it once came within $639 of the limit. This constraint binds hard.

**(b) Detail + day-resample bootstrap (2,000×252-day paths, day granularity, trailing $4,500):**
```
config            hist    boot-breach/1yr  med-annual   worst-day  worst-month
tiered  N=1       OK      ~25%             $+14,542     $-1,431    $-2,527
tiered cap=3 N=1  OK      ~13%             $+8,084      $-914      $-2,068
tiered cap=2 N=1  OK      ~6-8%            $+5,529      $-846      $-1,824
flat 1x N=1       OK      ~7-9%            $+7,746      $-715      $-1,339
  flat 1x N=1 annual: 2021:$+2,841 2022:$+8,933 2023:$+5,200 2024:$+2,854 2025:$+7,281 2026:$+4,260
Any N>=2, any variant: 60-100% 1-yr breach probability.
```
**(c) Smartest scheme under <10% breach:** drop the 2x tier — **flat 1 MES per signal** gives the highest median annual (~$7.7K) at ~7–9% one-year breach probability; tiered-cap=2 is the alternative (~$5.5K, ~6–8%). The sizing edge cannot be expressed inside a $4,500 trailing budget: the full tiered book at N=1 makes ~$14.5K/yr median but breaches ~25% of resampled years. Realistic guidance: run flat 1 MES in the prop eval; express the tier sizing only in a non-trailing (or funded/withdrawn-buffer) account. Caveats: bootstrap at day granularity understates intra-day trailing breaches slightly; iid day resampling ignores volatility clustering; the historical N=1 min-room of $639 says the true margin of safety is thin.

## FINAL FROZEN RULE SET (implementable spec)

```
INSTRUMENT / DATA
  ES (or MES) 5-minute RTH bars 08:30-15:15 CT; MC signal export (CC1-CC5, both directions).
  Signal DateTime = signal bar close. All features evaluated at or before that close.

FILTERS (skip signal unless ALL pass)
  F1  IB-break alignment: IB = high/low of first 12 RTH bars (08:30-09:30 CT).
      After 09:30, track first post-IB bar whose High > IB_High (up-break) / Low < IB_Low
      (down-break); a break "exists" from that bar's CLOSE onward.
      SKIP Long  if (down-break exists) and (no up-break yet).
      SKIP Short if (up-break exists)  and (no down-break yet).
      (Signals with no break yet, aligned break, or both sides broken: TAKE.)
  F2  Prior trend day: SKIP the entire session if prior session's range > 1.6 x its ADR
      (existing S25 prior_adr_ext flag, ADR(14)).
  F3  Time: SKIP signals whose bar closes at or after 14:00 CT.

ENTRY
  Market on next bar open after signal bar close (assume 1 tick slippage).
  Initial stop = signal StopPrice +/- 1 tick offset (engine stop_offset=1).
  R = |entry - stop|.

EXIT
  Target = entry + 3R (Long; mirror Short).
  Break-even ratchet: when price touches entry +1R, move stop to entry.
  Bail rule: at the CLOSE of the bar AFTER the entry bar, if the trade is still open
  and close is beyond 50% of stop distance against entry -> exit at market.
  Flatten at session close (15:00 CT flat is equivalent; never hold overnight).

SIZING (tier)
  2 units if ANY of:
    T1 balance_state = True (opened inside prior day range and still rotating inside it)
    T2 Long AND SignalPrice < prior WEEKLY Value Area Low (vaW_pos < 0)
    T3 mss_event = True (market-structure shift at signal bar)
    T4 pullback from developing session extreme in trade direction
       (Long: devHigh - price; Short: price - devLow) >= 0.86 x avg 5M bar range
       (trailing 20-session mean of bar High-Low)
  else 1 unit.

CAPACITY / ACCOUNT
  Full book: plan ~6 ES-equivalent units of concurrency headroom (p95=7 units;
  margin peak ~$216K ES / ~$21.6K MES). Position caps of 2-4 units keep the edge
  CI>0 but cost 30-60% of net.
  Prop account with $4,500 trailing DD: trade FLAT 1 MES per signal (no 2x tier),
  expect ~$5-9K/yr, ~7-9% annual breach risk; do not run N>=2.

EXPECTED PERFORMANCE (2021-2026 backtest, realistic slippage/commission, 1 ES/unit)
  n=2,925 trades (~2.4/day), 4,262 unit-trades tiered.
  +0.164R/unit [+0.120,+0.208], WR 39% (3R book), PF 1.44, $+622,830,
  maxDD $-38,372 (daily closes), positive all 6 years, walk-forward degradation -4.7%.
```

---

# Round 5 — Prop-Account Operating Structure
**Date:** 2026-07-04. Base book = frozen spec with flat-by-15:00 exits everywhere (n=2,925; flat 1 ES: +0.154R [+0.111,+0.198], WR 40%, PF 1.39, $+382,372, maxDD $−23,004, 6/6 years — the 15:00 flat adds ~$40K vs session-close on the 1-lot book). MES = $5/pt, $1.40/RT; ES = $50/pt, $4.36/RT. Breach probabilities are day-resample bootstrap, 252-day horizon, trailing $4,500 unless stated; both trailing rules modeled: **continuous trail** and **freeze-at-breakeven** (floor stops rising once it reaches the starting balance — the common prop rule). Structural note stated up front: with a continuous trail, cushion above the floor is mathematically capped at the DD budget, so a cushion gate > $4,500 is unreachable; only under freeze-at-BE does cushion grow without bound.

## Test 1 — Cushion-gated tier (start flat 1 MES, enable 2x tier at cushion ≥ C, drop back below)

```
trail rule        C        boot-breach   med-annual   hist(5.5y)
continuous     $1,500        17.1%       $+15,161      OK
continuous     $2,500        11.5%       $+14,454      OK
continuous     $3,500         8.7%       $+13,601      OK
continuous     $4,499         5.7%       $+10,851      OK  (tier only at fresh HWM)
freeze@BE      $1,500         7.6%       $+15,421      OK
freeze@BE      $2,500         5.7%       $+15,519      OK
freeze@BE      $3,500         5.0%       $+15,004      OK
freeze@BE      $4,499         2.4%       $+13,914      OK
freeze@BE      $6,000         4.1%       $+10,804      OK   (larger C just delays the tier)
never tier (flat 1 MES):      5.4%       $+8,868       OK
```
The cushion gate works: it captures most of the tier's extra P&L (median ~$14–15.5K vs $8.9K flat) while cutting breach risk versus an always-on tier (~25% from Round 4). **Recommended C = $4,500** — i.e., only trade 2-lots when the full drawdown buffer is intact (at/above HWM under a continuous trail; ≥ floor+$4.5K under freeze). Under freeze-at-BE that's 2.4% breach / $13.9K median; under a continuous trail 5.7% / $10.9K. If the firm's trail freezes at breakeven (ask!), C=$2,500–3,500 is defensible (~5%, ~$15K).

## Test 2 — ES in a prop account: NO

```
budget       freeze@BE breach   continuous breach   historical 5.5y
$4,500            66.8%             100.0%             BREACH
$7,500            56.0%             100.0%             BREACH
$10,000           47.8%              99.7%             BREACH
$15,000           34.7%              89.8%             BREACH
$20,000           24.1%              66.1%             BREACH
```
Flat 1 ES breaches historically at every tested budget and never gets near 10% bootstrap breach — extrapolating, <10% would need a ~$30K+ trailing budget (no standard prop product), and <5% more still. Median annual would be ~$95K if it survived, but it doesn't. **ES has no place in a $4.5–20K trailing account; trade MES.**

## Test 3 — Concurrency and the no-hedge rule

Book overlap facts (flat 1 lot): **54% of entries occur while another trade is already open** (concurrency max 10, p95 4); **6.9% of entries would create a simultaneous LONG+SHORT** — the prop-prohibited hedge state. So a compliance rule is mandatory, not cosmetic.

```
regime                    n     E[R]                  PF    net(1 ES eq)  maxDD     MES $4.5K breach(frz/cont)  med-annual MES
UNCONSTRAINED          2925  +0.154 [+0.111,+0.198]  1.39  $+382,372    $-23,004      3.2% / 5.8%               $+8,716
a) one-at-a-time       1420  +0.121 [+0.057,+0.186]  1.25  $+131,109    $-17,200      0.3% / 0.2%               $+2,965
b) net-dir cap=2       2146  +0.132 [+0.080,+0.183]  1.32  $+245,743    $-24,339      2.0% / 2.9%               $+5,645
b) net-dir cap=3       2497  +0.140 [+0.092,+0.187]  1.36  $+308,738    $-21,700      3.7% / 5.2%               $+6,992
c) A: Longs 1@t         778  +0.126 [+0.041,+0.210]  1.32  $+84,208     $-9,485       0.0% / 0.0%               $+2,871
c) B: Shorts 1@t        734  +0.134 [+0.041,+0.227]  1.23  $+64,750     $-14,840      0.5% / 0.3%               $+2,454
c) A+B combined        1512  +0.130 [+0.067,+0.192]  1.27  $+148,958    $-15,509      (two separate accounts)
```
- One-at-a-time keeps only **34%** of the net — too destructive.
- **Net-direction stacking, cap 3** keeps **81%** of the net, stays 6/6-years positive, removes all hedge states, and its breach risk is modest (3.7–5.2%). Cap 2 keeps 64%.
- The two-account long/short split keeps 39% combined — LESS than net-dir cap=3 in one account, with two eval fees and two DD budgets. Per-account breach is near zero, but each account only earns ~$2.4–3.0K/yr median. **Not worth it.** (Longs-only account is the steadier of the two if someone wants a single ultra-safe account.)

Combined recommended structure (net-dir cap=3 + cushion-gated tier, simulated jointly):
```
C=$4,500: freeze@BE breach 2.7%, med-annual $+10,452, hist OK ($+46,609/5.5y)  | continuous: 5.5%, $+8,958
C=$3,500: freeze@BE breach 4.5%, med-annual $+11,625, hist OK ($+51,129/5.5y)  | continuous: 7.1%, $+10,944
```

## Test 4 — Max risk snapshot (frozen-spec book)

- Per-trade initial risk: **median 15.75 pts** ($788 ES / $79 MES), p90 31.5 pts ($1,575 / $158), **max 97.75 pts ($4,888 ES / $489 MES)**.
- Worst realized single-trade loss (incl. slippage): **ES $−3,154 / MES $−316**.
- Flat-1-ES book: worst day $−7,126, worst week $−13,993. One-at-a-time: worst day $−4,796, worst week $−7,880; max open risk = single trade ($3,875 max).
- Max instantaneous open risk (sum of initial stop distances, unconstrained): **ES $15,000 / MES $1,500** (conservative — risk collapses to ~0 on any position whose BE ratchet has fired).
- Operational note: the max stop (97.75 pts, $489 MES) is ~11% of the whole DD budget on one trade; a per-trade risk cap (e.g., skip signals with stop > ~40 pts) was NOT part of the frozen spec and was not re-tested — flagged as an open refinement rather than added ad hoc.

## RECOMMENDED PROP OPERATING RULES (user's account)

```
1. Instrument: MES only. Never ES under a trailing budget < ~$30K.
2. Signals/entries/exits: frozen spec (Round 4) with FLAT BY 15:00 CT.
3. Compliance/concurrency: NET-DIRECTION ONLY — while any trade is open, take new
   signals only in the SAME direction, max 3 concurrent units; skip opposite-direction
   signals until flat. (Never long and short simultaneously.)
4. Sizing: start 1 MES per signal. Enable the 2x tier (Round 4 tier features) ONLY when
   closed-equity cushion above the current trailing floor >= $4,500; drop back to 1 MES
   whenever cushion < $4,500. If the firm freezes the trail at breakeven, $3,500 is an
   acceptable more-aggressive gate.
5. Expectations: ~$9-12K/yr median (MES), worst day ~-$700, worst week ~-$1,400 (MES),
   annual breach probability ~3-6% (freeze rule ~3%, continuous ~6%).
6. Two-account long/short split: not recommended (keeps less edge than net-dir cap=3
   in one account at double the fees).
```
