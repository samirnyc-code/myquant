# MentorQ gamma-level tracker

Since MentorQ shows only *today's* backtest, this builds your own longitudinal
record so you can (a) recover the numbers they don't display and (b) check
whether their probabilities are actually calibrated.

## Files
- `daily_log_template.csv` — one row per level per day. Copy it to `daily_log.csv` and fill in.
- `schema.sql` — SQLite table + a `v_decomposition` view that back-outs the never-reached split.

## Daily routine
**Before RTH** — from the Backtest panel, record for each level: price,
hold rate, positive-outcomes count, broke-at-close %, comeback rate, and the
avg/worst move numbers. Log the *positive-outcomes count every day* — if it
drifts (348 → 351 → 349) you learn whether the 3-year window is rolling and
whether the regime filter changes day to day.

**After the cash close** — fill session high/low/close and, per level:
touched? broke intraday? max excursion beyond? closed beyond? held?

## The decomposition (what the panel lets you compute)
From four panel numbers — hold rate `H`, positive count `P`, broke-at-close
`Bc`, comeback rate `Cr`:

    total days     N  = P / H
    closed beyond     = N * Bc
    comeback days     = (N * Bc) * Cr/(1 - Cr)
    broke intraday    = comeback + closed_beyond
    never reached     = N - broke_intraday

Self-check: `never_reached + comeback` must equal `P` (positive outcomes).

Worked example — 1D Max on 2026-07-10 (H=0.8907, P=348, Bc=0.109, Cr=0.43):

| Outcome | Days | % |
|---|---|---|
| Never reached | 316 | 80.8% |
| Comeback (broke, closed inside) | 32 | 8.2% |
| Closed beyond | 43 | 11.0% |
| **Total** | **391** | 100% |

316 + 32 = 348 ✓

## Two definitions to confirm with the vendor
1. What does **"broke"** mean — any intraday touch, a 1-tick pierce, or a min distance?
2. Is **comeback rate's** denominator *intraday breaks* (assumed here) or *all days*?

Both change the decomposition, so note the answers — or just infer them once
you have a few weeks of your own logged outcomes to compare against.
