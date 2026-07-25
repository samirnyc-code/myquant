# REGIME-2E  ·  system config & frozen parameters
**Designation:** REGIME-2E (Regime-gated Second-Entry, ES) · **Version v1.0-rc1**
(release *candidate* — NOT live-validated; graduation to v1.0 requires the 10 stress
tests below + NT8 signal-diff + a forward MES period). Frozen 2026-07-25 (S83).
Branch `regime/indep`, worktree `myquant-regime`. All numbers: ES 5-min RTH ticks
2021-06→2026-07, strict fills, net of $5 RT + 1-tick exit slip, 1 ES.

## The three books (one system)
| book | side | regime | entry | stop |
|---|---|---|---|---|
| 2EL | long | BULL | S61 2nd entry, retest 6t limit | 0.30×ADR10 (wide) |
| 2ES | short | BEAR | S61 2nd entry, retest 6t limit | 0.30×ADR10 (wide) |
| f2EL | short | BEAR | failed counter-trend 2EL, stop-entry at SBlow−1t | 4pt (tight) |
f2ES-long fade = DEAD (0.71), NOT in the system. Fade must gate to the OPPOSITE
trend only (never NEUTRAL).

## FROZEN PARAMETERS (do not change without a new version)
- Instrument/chart: ES front-month volume-continuous, **5-min TIME bars, RTH**, day-scoped.
- Regime: tick-driven phase machine v4, **wick break** (not close). Day opens NEUTRAL.
- Signal: S61 second entry only (2EL/2ES; origin-reset count; increment #2). No 1st/3rd.
- Direction gate: with-trend, **evaluated at the trigger tick**. Regime flips ignored.
- Day filter: **skip day if |RTH open − prior RTH close| / prior close > 0.54%**
  (fixed constant = train-2021-23 75th-pctile of |gap|; re-derive as trailing pctile in a WFA).
- Entry (WT): **limit 6 ticks back** from the S61 trigger; fill requires trade-through +1t;
  cancel unfilled after **6 bars (30 min)**.
- Entry (fade): stop-entry at **signal-bar-low − 1 tick**, must fail within **K=2 bars**
  of the 2EL trigger; 1t slip.
- Window: fills **09:00–13:59 machine-tz** (session open +30 to +330 min). ⚠️ map to
  exchange time before live — never assert CT.
- Stop (WT): **0.30 × ADR10** (prior-10-day avg RTH range), nearest tick, **floor 8 ticks**
  (~15.75pt median), never moved. Intraday-adaptive stop tested — does NOT beat this OOS.
- Stop (fade): **fixed 4 pt (16 ticks)**, never moved. (Fade dies on the wide stop.)
  **Swept 2026-07-25 (`regime_2e_fade_stop_sweep.py`, FADE-S 105 tr):** 4pt is the PF-max (1.35)
  and the ONLY stop with test>train (1.28→1.42) — every higher-net stop (10/12pt, EOD make ~2× $)
  degrades OOS. **Vol-scaling (k×ADR) tested and REJECTED** — 0.15×ADR overfits (tr 1.53/te 1.12);
  the fade's invalidation is *structural* (~small buffer past the failed-breakout bar), not vol-dependent
  (4pt ≈ 7% of ADR). Caveat: 4pt is a *sharp* peak (3pt 1.05 / 5pt 1.12) on a thin 13%-win book — trust
  "small fixed ~4pt structural stop", not the exact 4.00 value.
- Exit: **NO target. Hold to session close (EOD flat), or the stop.** Regime flips do NOT
  exit. Every target / trail / % give-back tested — all lose. (2R "target" would seem to work
  because 75% reach 2R MFE, but only 30% reach it BEFORE the stop → real 2R target PF 0.74.)
- Concurrency: same-direction adds ≤3; never opposing; opposite qualifying FILL = reverse
  (P3) — happens ~2.4×/yr (rare). 518/930 days trade 0; active days 1–3 (max 5).
- Costs modeled: $5 RT + 1t exit slip; entry slip 0 by limit (robust at 2t slip).

## PERFORMANCE (backtest, 1 ES, three books = 2EL+2ES+f2EL)
- 5-yr net **+$93,722**, 678 trades (~133/yr), win 45% (WT) / 13% (fade).
- WT PF 1.45 (train 1.51/test 1.42); fade 1.35–1.36; combined **PF 1.44**.
- Green every calendar year; every ADR-vol quintile green.
- Max realized DD **−$9,502**; worst-start (≈Sep-2023) −$9,502; MC-shuffle worst-1% −$24k.
  **HONEST DD = block-bootstrap (5-trade blocks, preserves losing clusters): worst-5% −$27.6k,
  worst-1% −$35.4k** (stress #6). The MC shuffle understated it by breaking up streaks — size off −$35k.
- **Account sizing:** on the honest −$35.4k, DD ÷ 33% → **~$105k per 1 ES** (the earlier $70–75k used the
  optimistic MC number). Return ≈ **~18% CAGR fixed-contract** (the earlier "~26%" was simple, not CAGR).
  $20k fits **1 MES**, not 1 ES.
- MES viability marginal after $5 RT commission — negotiate cheaper micros or run ES.

## STRESS TEST #5 RESULT — engine invariance (DONE, PASS)
Full three-book on the NEW 2nd-PC immediate-flip engine vs OLD (same everything else):
- OLD: n=678, +$93,722, **PF 1.44**, maxDD −$9,502, MC-1% −$23.5k.
- NEW: n=773, +$102,298, **PF 1.43**, maxDD −$14,288, MC-1% −$25.3k.
- Both halves green, green every year. Fade survives (1.31 vs 1.35). **Edge is ROBUST to the
  engine** — new engine is higher-capacity (+95 trades, +$8.6k) at ~identical PF, but DEEPER
  drawdown (−$14.3k vs −$9.5k realized). Caveat: pt_new is a verbatim lift, not yet
  reference-day-diffed. Use the deeper NEW-engine DD for sizing if adopting the new engine.

## PROP / MES SIZING (EOD-trail, corrected 2026-07-25)
The prop DD is an **EOD (end-of-day closed) trail**, NOT intraday — so the flat-by-close
system is judged only on daily closed equity (my earlier intraday-unrealized objection was WRONG).
EOD-trail DD, three-book MES @ **$3 RT**, vs a **$4,500** trailing limit:
| contracts | realized | MC-5% | MC-1% | net/yr | fits $4,500? |
|---|---|---|---|---|---|
| **1 MES** | −$1,158 | −$2,778 | −$3,340 | +$1,517 | **YES (even worst-1% clears)** |
| 2 MES | −$2,316 | −$5,422 | −$6,616 | +$3,034 | NO (bad-1-in-20 blows it) |
| 3 MES | −$3,473 | −$8,363 | −$9,829 | +$4,552 | NO |
**Verdict: 1 MES is prop-safe on a $4,500 EOD-trail (even the 1-in-100 stress stays under).**
2 MES is NOT — a plausible ~1-in-20 sequence trips the limit. Prop route = 1 MES only; scale
contracts only on a bigger account. (MES @ $3 RT holds PF ~1.35; at $5 RT it sags.)
On the honest block-bootstrap DD, 1 MES worst-1% = −$3,545 (−35.4k/10) — still clears $4,500. 1 MES holds.

## KNOWN RISKS (on the record)
- **Tail-concentrated:** top 20 of 630 WT trades = all the profit; top 2 ≈ 24%. NOT flukes —
  90% of top-20 on trend-expansion days (day-range >1.3×ADR), spread across all 6 years.
  But ⇒ high variance, low statistical confidence, regime-dependent (a multi-year chop era is
  the kryptonite; 2023 = weakest at 1.10–1.23). **Automation is the strategy** — any process
  that can clip runners eats the edge.
- ~20 *effective* observations over 5 yrs; PF CI straddles 1.0.
- NT-derived tick series had ~20 bad closes 2021-23; Databento is the clean cross-check (untested here).
- Second-PC engine (immediate-flip) changes state on 48% of days but PF ~identical (1.44 vs 1.45) —
  edge robust to engine; port not yet reference-day-diffed.

## RETRACTED / DEAD (do not resurrect)
Fixed targets (all) · regime-flip exits (0.72/0.20) · 1st entries (OOS-dead) · close-confirm &
sticky regimes · 1m/15m/30m/60m & 6500-vol bars (5m is peak) · ETH/overnight · BE-move / scale-out /
stop-tighten (fill fantasy) · EMA-touch M2B · f2ES-long fade · chase entries · 2:1 target on fade ·
intraday-adaptive vol stop (no OOS gain) · % give-back trails (clip the tail).

## KEY FILES (branch regime/indep)
Strategy `nt8/strategies/RegimeSecondEntry.cs` · indicator `nt8/indicators/RegimePhaseMachine.cs`
(cockpit + HVL) · engine `scratchpad/regime_phase_machine.py` · sims `scripts/regime_2e_*.py`,
`regime_2e_two_sleeves.py` (three-book), `regime_engine_ab.py` · report
`docs/artifacts/regime_2e_summary.html` · fade gallery `docs/living/fade_gallery/index.html`.
Stress/gamma scripts: `regime_2e_walkforward.py`, `regime_2e_stress_battery.py`,
`regime_2e_gamma_hvl.py`, `regime_2e_0dte_expansion.py`, `regime_2e_vix_stationarity.py`,
`regime_2e_vol_invertedU.py`, `regime_2e_regime_tracker.py`.

---

## STRESS RESULTS (run 2026-07-25) — 6 of 10 executed, all survive
Base reconciles to +$93,722 / PF 1.44 / maxDD −$9,502 in the battery (trust check passed).
- **#1 Walk-forward (PASS):** 14/18 OOS quarters green (78%), median +$2,484, worst qtr −$5,208;
  re-derived gap threshold mean 0.531% (0.54 well-centered). Edge is temporally stable.
- **#2 Cost stress (PASS):** $10 RT + 2t both sides → PF 1.44→**1.28**, +$64.9k, maxDD −$13.1k.
- **#3 Pessimistic fills (QUARANTINED):** the tick-reimplementation base = +$83.3k ≠ frozen +$93.7k,
  so its absolute numbers are untrusted. #2 (reconciled) already covers cost/slip. Do not cite #3.
- **#5 Engine invariance (PASS):** see above.
- **#6 Drought/bootstrap (PASS, sobering):** block-boot maxDD worst-1% −$35.4k (the honest sizing #);
  longest flat stretch median 143 trades, worst-1% 493 (~44 months).
- **#7 Param neighborhood (PASS):** broad plateau PF 1.35–1.53 across stop{0.20,0.30,0.40}×gap{0.45,0.54,0.60};
  0.30×ADR is the ridge. 0.45 gap scores higher (1.53) but we keep the derived 0.54 (no optimum-shopping).
- **#8 Jackknife (PASS):** drop any single year → rest PF 1.35–1.50 (no year carries it); tail: top-20 = 99% of net.
- Not runnable here: #4 Databento cross-check, #9 NT8 live-fills, #10 out-of-period/cross-instrument.

## REGIME RISK & CIRCUIT-BREAKER (2026-07-25)
**Diagnosis:** the vol→edge map is **non-stationary — a real structural break at 2022→2023.**
2021-22 (macro-vol / **79% negative-gamma** in 2022): elevated vol traded BEST (2022 = +$33.8k, best year).
2023-26 (calm, positive-gamma-dominant, 4 straight yrs): calm vol (VIX<17) best, elevated degrades.
No VIX transform (level, %ile, vs-SMA, Δ) is stationary; the "inverted-U in vol" was refuted OOS
(mid-only 2024-26 = PF 0.83). **Consequence: keep the system UNCONDITIONAL — that is what makes it
robust across both regimes. Do NOT bolt on a vol/gamma-tuned knob (it breaks across the next break).**

**"Back to 2022" is NOT itself a de-risk trigger — 2022 was the best year.** The real threat is an
*unseen* regime where the 2E trend edge dies. We cannot detect that fast: normal droughts run 143
(median) to 493 (worst-1%, ~44 mo) trades, and rolling-40 PF is <1.0 25% of the time as noise — a dead
edge and a routine drought look identical for ~a year. So act on early warning, not on proof.

**Tracker (`regime_2e_regime_tracker.py`, daily-updatable), 3 layers:**
- **WATCH** (lead, ~12-wk lag measured on 2022): 50d-median VIX > ~22 sustained ≥15d **OR** 20d
  negative-gamma share > 60%. → strip any regime-tuned knobs, revert to pure base, tighten monitoring.
- **DE-RISK** (objective, regime-agnostic): live DD breaches block-boot **worst-5% (−$27.6k / 1-ES)** → **half size**.
- **HALT:** live DD breaches **worst-1% (−$35.4k)** OR trailing ~500-trade net stays negative → pause + re-audit.
In-sample worst DD was −$9,502, so the breaker levels (3-4× beyond) won't fire on noise.

## GAMMA / LEVELS — INVESTIGATED, NOT INCORPORATED (2026-07-25)
Full gamma/MQ-levels sweep. **Verdict: nothing clears the bar to trade. Kept as understanding, not knobs.**
- **HVL-proximity** (near-HVL PF 1.81 vs far, tr 1.65/te 1.90, full 5yr): OOS-stable AND now **passes
  orthogonality vs the gap filter** (corr −0.09; near>far inside both gap halves & 2/3 gap terciles; HVL PF-spread
  +0.71 > gap's +0.25 — HVL is the stronger stratifier). **Graduated to candidate SIZE-LEAN.** NOT a hard gate:
  far-HVL is the trend tail (beats near in gap-high → hard-gating kills 2022). Rule shape: **size UP near-HVL, DOWN far-HVL (2:1)**.
  **DD/tail gate PASSED 2026-07-25 (`regime_2e_hvl_sizelean_risk.py`):** same-avg-capital 2:1 lean →
  net +25%, PF 1.44→1.56, maxDD unchanged, boot worst-1% *shallower* (−33.1k), top-20 100→94%. The
  **skip-dead variant is REJECTED** (deepens boot-1% to −36.4k, maxDD −15.6k). **HVL 2:1 lean has now
  cleared all gates → v1.1 SIZING-RULE candidate.** Caveats: (a) does NOT fix tail dependence (top-20 still
  ~94%); (b) benefit realizable only where you can size UP near-HVL — **NOT on the 1-MES prop floor**
  (there you can only size down far, which cuts return). Tests: `regime_2e_hvl_orthogonality.py`,
  `regime_2e_hvl_sizelean_risk.py`.
- **Gamma regime label (pos/neg):** train/test PFs **invert** (tr 2.07/te 0.91) → dead.
- **0DTE (cr0/ps0/hvl0, d1-envelope):** only 2024-07→2026-07 coverage; d1-envelope 0.72-corr w/ VIX
  (redundant); intraday level features basis-contaminated (panama drift +244pt); best nugget (low-VIX×wide-0DTE
  PF 6.17) is 39 trades = 100%+ of profit, inverts 2025 → too fragile. Levels are **ES1! scale** (no SPX conv);
  join by `session_date`, dedup last-per-session.
- **VIX-conditional / inverted-U sizing:** non-stationary / refuted OOS (above). Dead.

---

## THE 10 STRESS TESTS — designed to BREAK it (survive all ⇒ real)
1. **Rolling walk-forward** (1yr IS / 3mo OOS, ~16 windows): re-derive the gap threshold as a
   trailing percentile each window, params otherwise fixed; +single-knob stop-multiple sensitivity.
   *Breaks it if:* OOS quarters are mostly red or the re-derived threshold swings wildly.
2. **Cost stress:** double commission ($10 RT) + 2-tick slip on BOTH entry and exit.
   *Breaks it if:* PF drops below ~1.1 (the edge was just eating thin costs).
3. **Pessimistic fills:** require retest to trade 3+ ticks through; randomly fail X% of limit
   fills (queue-position model). *Breaks it if:* the surviving trades lose the edge (adverse selection).
4. **Independent data cross-check:** re-run on **Databento** ES ticks (clean vendor) vs the
   NT-derived series. *Breaks it if:* the edge doesn't replicate on clean independent data.
5. **Regime-engine invariance:** run on the 2nd-PC immediate-flip engine AND future variants;
   diff signals. *Breaks it if:* a legitimate regime definition kills the edge (it's fit to one machine).
6. **Regime-drought / block bootstrap:** block-bootstrap returns and simulate a multi-year
   low-vol/no-trend-day regime. *Breaks it if:* a plausible chop era produces an un-survivable flat stretch.
7. **Joint parameter neighborhood:** perturb ALL knobs ±1 step simultaneously (stop mult, retest
   depth, gap threshold, window bounds, fade K/stop). *Breaks it if:* it's a fragile peak, not a plateau.
8. **Leave-one-year-out + tail jackknife:** drop each calendar year in turn, and remove the top-N
   winners. *Breaks it if:* any single year or handful of trades carries the whole edge.
9. **NT8 live-fills reconciliation:** signal-diff the C# port vs the research engine trade-for-trade,
   then a forward MES period logging ACTUAL fills vs modeled. *Breaks it if:* real fills ≠ model.
10. **Out-of-period / cross-instrument:** test on ES 2010–2020 (Databento) and on NQ/MES.
    *Breaks it if:* the edge doesn't exist outside the exact 2021–26 ES window (it was period-specific).
