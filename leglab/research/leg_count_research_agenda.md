# Leg-Count Research Agenda (ES 5M RTH)

Source inspiration: Tim @ zentradingtech.com "leg counting" series.
Our data: `data/bars/_db_es_5m_rth.parquet` (2010-06 → 2026-07, 4,137 RTH days).
Baseline reproduced (S111): mean legs_closed/day ≈ 15.5, matches Tim's per-year
chart within 1.2% (see `scripts/leg_count_es.py`, `scripts/leg_count_compare_tim.py`).

Leg definition (confirmed): intrabar HL reversal off the running extreme by
≥ 0.15 × ADR, ADR = mean of prior 8 RTH daily ranges, per-day reset.
`legs_closed` = counted at reversal (Tim's "15"); `legs_total = legs_closed + 1`.

## Findings so far
- 16y mean 15.5 legs/day, band 14.7–16.6, NO secular drift (structural constant).
- Down days > up days: ext_down ~20 vs ext_up ~14 legs (`legs_closed`).
- Asymmetry is PARTLY volatility (down days bigger range/ADR vs a lagging
  threshold) but a **+2.89 leg residual survives matching on range/ADR**
  (`scripts/leg_count_vol_control.py`) — a real directional effect. Leading
  candidate: negative dealer gamma / short-covering two-sidedness on selloffs.
  VWAP is a poor candidate (symmetric mechanism). GEX test deferred.

## Tim's own open questions (from the 2026-09-06 post)
- Unexplained down(18)/up(12) leg asymmetry (we partly cracked it).
- "Does leg count in the first 2-3 hours predict rest-of-day?" — he calls this
  "the actual tradeable version of this question."
- Day-type classification (trend/range/channel) UNSOLVED — he feeds legs + an
  "RLS ratio" into it but has no finished method.

## The 10 ideas

### A. Prediction / day-typing
1. **Early-leg trend/range classifier.** First 60-90 min leg count → predict
   rest-of-day range expansion, close location, trend efficiency. (Tim's Q.)
2. **Leg-count filter for the 0DTE options desk.** Low early-leg count = trend
   day → skip/size-down the with-trend wall. Fixes the no-gap/trend-filter hole
   that cost −$1,811 on 9/3. Highest P&L value.
3. **Solve the day-type taxonomy.** legs + leg-size dispersion + close-location
   + RLS → trend/range/channel buckets, % per bucket, predictive test.

### B. Leg geometry
4. **Intraday leg-size curve.** leg length(pts)/duration(bars) by order 1..N and
   by time-of-day → feeds adaptive targets (#10).
5. **Leg-to-leg ratios.** leg_n/leg_{n-1}: expanding = accel/continuation,
   contracting = exhaustion/reversal. Ties to "second leg gets a second leg."
6. **Breakout-of-structure vs inside legs.** Tag each leg BOS vs inside; count
   consecutive inside legs before a break; P(next leg breaks | k inside).
   Confirm BOS legs with our free footprint/absorption data. Balance→breakout engine.

### C. Combine with our systems
7. **Leg index as a conditioner on the 2E book (678 ES trades).** Tag entry leg
   index / legs-so-far; test early vs late-day 2E performance.
8. **Gamma-conditioned leg regime.** Does the +2.89 down-day residual sit on
   negative-GEX days? neg-gamma → fade legs; pos-gamma → join. (ORATS, deferred.)
9. **Leg pace as a vol clock.** minutes-to-leg-5/8 → gate WedgeScalperV2 off on
   whipsaw days (it churns ~90 no-edge trades on those).
10. **Leg-structure-aware stops/targets.** target ≈ median leg (≈0.15×ADR),
    stop ≈ ½-leg; backtest wedge signal-bar-close entry (PF 1.04-1.16) leg-scaled
    vs fixed ticks.

## Adjacent Tim setups to backtest on ES 5M RTH (standalone + combine w/ legs)
- 18-bar range swing method; open-on-high/low & shaved opens; CSC / consecutive
  opening bars; measured-move-of-yesterday's-range; big-ES-days-what-follows;
  streaks above/below MA; always-in / swing-point breaks.
- Cross-tests: do shaved-open days run fewer legs? do big-ES-days precede
  low-leg trend follow-through?

## Additions from the full-site crawl (see zentradingtech_digest.md)
- **RLS now defined** = travel above open vs below open (open-relative ratio). Enables
  idea #3: build the real day-type taxonomy from legs + RLS + swing-breaks (1 break=range,
  2=flip) + close-location. He admits his own version is unsolved — open contribution.
- **Fractal legs / second-leg**: idea #5 gains his 3 counting methods (spike-break,
  inside-bar, combo) and the "failed 2nd leg = reliable reversal" claim to quantify.
- **New cross-setup ideas (leg count as a trend-day confirmer):**
  11. Do **shaved-open / big-ES-day / two-same-color-opening-bar** days run FEWER legs?
      If yes, leg count corroborates his existing trend-day signals → stronger day filter.
  12. Tag each leg with **Always-In state** (his mechanical def: 2 same-color bars, both
      one side of MA, IBS>65/<35, one bar>ABR). Do BOS legs (#6) align with AI flips?
  13. **18-bar range × leg count**: small 18-bar range + low early legs = compression before
      trend expansion (join); large range + high legs = day done (fade). Direct fusion of
      his 18-bar work with #1.
- **Match methodology exactly**: his GitHub (github.com/Zen-Tim/zen-trading-tech-public)
  has Pine source + some ES CSVs + research reports — pull to align ABR/ADR/RLS definitions.

## Findings log
- **#1 early-leg classifier (DONE, leg_early_classifier.py).** Early leg count does
  NOT predict trend-ness (efficiency Spearman −0.03) — the intuitive hypothesis
  FAILS. Sole exception: exactly 1 leg in the first 90 min (3% of days, n=134) =
  67% trend days vs ~46% base. What early legs DO predict is rest-of-day
  VOLATILITY (rest_range/ADR Spearman +0.40; +0.26 partial after controlling for
  morning range — an independent signal, not just a range proxy).
  Implications: day-typing (#3) needs RLS + structure, not early leg count;
  for the options desk (#2) early legs = expected-range forecaster, not a trend gate
  (except the 1-leg morning). Engine now emits full per-leg geometry → unlocks #4-6.

- **#4/#5 leg geometry (DONE, leg_geometry.py).** Leg size ~constant ~0.32 ADR all
  day; duration is a U (2.5 bars open/close, 6.7 lunch) = velocity smile. Strong
  leg-size mean-reversion (after big leg next larger 14%; after small 81%). Big
  first leg -> bigger RANGE day (Spearman +0.18) not trend (eff +0.00).
- **#3 day-type taxonomy (DONE, leg_day_typing.py).** 4 types (Trend-Up 24% /
  Channel 28% / Range 31% / Trend-Down 16%). Tim's fewer-legs=trend holds for UP
  trends (12.6 legs) but Trend-Down = 19.2 legs (reconfirms down-day whip). Day-type
  does NOT persist (transition matrix ~= base rate). Volatility DOES cluster
  (P big|big 58.5% vs 41.5%). Weak bear-reversal after Trend-Down (55% up next day).
- **#2 options-desk filter (BLOCKED, not tested).** Desk daily P&L = only 24 days
  (8/4-9/4 2026) -> statistically unusable (overfitting). Desk ALREADY classifies
  day-type/high-vol/gap/gamma; both big losers (8/4 -1334 HIVOL, 9/3 -1407 TREND)
  were self-flagged and traded through -> issue is ACTION/sizing, not detection.
  Also our 5M bars end 2026-07-24 (no overlap with desk window). Real path =
  synthetic 0DTE wall-selling backtest over the 16y leg history + gamma (ORATS),
  NOT a 24-day fit.
- **#6 leg structure BOS vs inside (DONE, leg_structure.py) — FIRST directional
  signal.** 36% of legs break structure. State persists: P(next same-dir leg BOS)
  = 48% after BOS vs 14% after inside (base 27%, 3.4x, no lookahead). Balance does
  NOT coil into breakout — P(next BOS) falls monotonically with consecutive inside
  legs (39%->3%); ranges beget ranges. BOS legs bigger (0.38 vs 0.28 ADR). CAVEAT:
  2 & 3 partly mechanical (proximity to extreme); needs a costed tradeable test to
  confirm real edge beyond "near the high makes new highs."
- **#6 STRESS-TEST (DONE, leg_structure_stresstest.py).** Raw BOS-persistence is
  ~85% MECHANICAL: gap-to-beat 0.34 ADR after BOS vs 0.72 after inside. But a
  +5.4pp edge survives within every gap-to-beat quintile -> a small REAL regime-
  persistence edge. Earns a costed backtest (next).
- **Big-ES-days (DONE, big_es_days.py) — Tim's 85% REFUTED on 16y.** Continuation
  falls below base as K rises (0.333 at 3.3x vs 0.495 base); next-day drift is
  AGAINST the big move (-11.7 pts at 3.3x); big days extend LESS than random. ES
  MEAN-REVERTS after big days (big-up reverse hardest, -19.8 pts, n=17). Tim's
  n=14 (2021-25 bull) = small-sample/recency. Possible FADE lead (big-up -> short).
  Caveat: outcome = daily close/extreme, not his intraday 50%-pullback rule.
- **THESIS (from #1/#4/#3):** leg-based metrics forecast VOLATILITY
  (clustering + persistence), not direction/day-type-sequence. Build vol-timing,
  not trend-prediction, on legs.

## Status
- Baseline + asymmetry diagnostics: DONE, committed (branch leglab).
- Full-site digest: DONE (research/zentradingtech_digest.md); 2nd-pass crawl running.
- Reusable engine (leg_engine.py) validated == baseline (median 15, diff 0.0).
- Idea #1 DONE. Next candidates: #4/#5 leg geometry (engine ready), #3 day-type
  taxonomy (RLS-based), #11 leg count as trend-day confirmer on his other setups.
