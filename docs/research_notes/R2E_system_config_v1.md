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
- Max realized DD **−$9,502**; worst-start (≈Sep-2023) −$9,502; MC worst-5% −$20k, worst-1% −$24k.
- **Account sizing:** stress DD ÷ 25–33% → **$70–75k per 1 ES (~26%/yr)**; $20k fits **1 MES**,
  not 1 ES (−$9.5k realized DD = 47% of $20k; stress case = ruin on 1 ES).
- MES viability marginal after $5 RT commission — negotiate cheaper micros or run ES.

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
