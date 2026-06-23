> # 🚨 INVALID — LOOK-AHEAD BUG (see docs/living/handoff.md, S34)
> This study used ER/feature values that read the **entry bar** (one bar in the
> future), not the signal bar. Its numbers are **not trustworthy**. Re-run on the
> corrected `tag_signals` pipeline before citing anything here.

# ER granularity — finer ER gate (OOS-TESTED, pending in-app reproduction)

**Status (updated S26 night):** OOS-tested extensively — `ER_intra_2` (2-bar/10-min)
**dominates** `ER_intra_6` out-of-sample (15/15 vs 12/15 green folds at 0.30, worstFold
positive at every threshold ≥0.30). The "tautology" worry was resolved: signal-bar ER
is contemporaneous (known at bar-T close, trade enters later) = look-ahead-safe, an
entry-quality reading — NOT circular. Full results: `er10_oos_sweep_20260621.md`.
**Still NOT adopted** — looks too good to be true; reproduce in the live app first,
and treat the *lookback swap at 0.30* as the defensible change vs the *threshold raise*
(a second knob = multiple-testing). See the S26 handoff block for the full disposition.

---
_Original hypothesis brief (pre-OOS) preserved below for the record._

## Where it came from (S25 thread, ER-blend concern)
Investigating whether the deployed ER gate has a *cross-session blind spot*:
`ER_intra_6` is computed on the **continuous** RTH series and does NOT reset per
session, so for the first ~5 bars of a day the reading reaches back over the
17.5h overnight gap and blends yesterday's closing momentum with today's open.

Two in-sample observations (1R single-leg, corrected engine
`entry_slip=1/exit_slip=0`, commission $4.36, full history — NOT OOS):

1. **The ER gate is mildly counterproductive on the early bars.** Within
   `ER_intra_6 ≥ 0.30`, bars 1–5 = $90 exp / PF 1.19, *below* the same early
   bars **un-gated** ($111 / PF 1.24). On bars 6+ the gate works as expected
   ($87 / PF 1.29). So the gate is dropping good early trades and/or admitting
   bad ones exactly where the ER reading is cross-session-contaminated.

2. **A shorter ER window looks better on every cut (IN-SAMPLE).**
   | gate (≥0.30) | n | exp | PF | bars1-5 exp |
   |---|---|---|---|---|
   | none | 5444 | $47 | 1.14 | — |
   | ER_intra_6 (deployed) | 4439 | $87 | 1.28 | $90 |
   | ER_intra_4 | 5010 | $76 | 1.24 | $144 |
   | ER_intra_2 | 4380 | $107 | 1.36 | $156 |
   At ≥0.40: ER_intra_2 → $127 / PF 1.45. A 2-bar (10-min) window is pure-intraday
   by bar 3, so it *also* fixes observation #1's cross-session blend.

## ⚠️ Why this is NOT yet a decision
This is a **multiple-testing sweep** — spans {2,3,4,6} × thresholds {0.30,0.40},
crowning the winner on the full in-sample. The locked-filter rail (handoff S20:
"pre-commit a small number of hypothesis-driven buckets; don't keep survivors of
many tries") exists to stop exactly this. A finer ER is also more reactive →
more prone to fitting noise. Need a STRUCTURAL why + OOS confirmation first.

**Structural why (the hypothesis to defend):** a breakout's edge depends on the
*immediately preceding* efficiency, not the last 30 min spanning an overnight
gap. A 10–15 min window measures the pre-signal thrust more locally and avoids
blending two different sessions' regimes.

## Test plan (when we get to it)
1. **Pre-commit** the comparison: deployed `ER_intra_6≥0.30` vs ONE challenger
   (propose `ER_intra_3≥0.30`, 15-min — a middle ground, less noisy than 2-bar).
   Decide the threshold by structure, not by which maxes in-sample.
2. **OOS folds**, same harness as `scripts/confirm_balance_day.py` (is=252 /
   oos=63 signal-days): does the challenger beat the deployed gate in a majority
   of OOS folds, incl. 2022? Report per-fold lift + pooled.
3. **Early-bar slice** specifically: does the challenger fix the bars-1-5 deficit
   (obs #1) OOS, or was that an in-sample artifact?
4. Only if it survives 2–3: consider swapping. Otherwise keep `ER_intra_6`.

Infra note: `indicators.bar_kaufman_er(bars, spans=(...))` already computes any
span; `ER_intra_3` would just need adding to the spans tuple + the gate UI.

## Related (separate but adjacent) — already on the backlog
- S23 ER-timing item: `ER_intra_6` includes bar T's own close (the signal bar),
  so it partially selects FOR signal bars. Fix = use T−1's ER. The granularity
  question and the timing question should probably be tested together.
