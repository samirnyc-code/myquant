# S75Q — Pre-registration: do MenthorQ gamma levels help the Brooks method?

Written **before** any result was inspected. Committed so the analysis cannot be
retro-fitted to whatever came out. Dated 2026-07-18.

## Background — what already failed

The aggregate/regime axis is dead (S75Q part 1, see `scripts/gex_vs_vol_baseline.py`):

- Net vs Total GEX: our existing net formula reproduces MQ's CR/PS at 81%/79%
  exact. Total GEX scores 17%/20%. **No code change warranted.**
- Four Options-Matrix regimes: quadrant `+GEX/-DEX` has n=2 over five years; the
  bearish claim for `-GEX/-DEX` is false (mean return **+0.097%**, 50.6% up-days);
  the vol claim is real but **subsumed by VIX** (adding GEX to a VIX baseline moved
  OOS R² 0.4490 → 0.4416, i.e. slightly worse).

This round tests the **spatial** axis instead: do the published *levels* mark
prices where behaviour differs? That is the axis Brooks trades on.

## Primary hypothesis (ONE — everything else is exploratory)

**H1.** Price approaching **CR** (call resistance) from below is rejected more
often than it is at a matched control strike the same distance away.

- **Rejection** = after first touch of level `L` from below, price reaches
  `L - R` before it reaches `L + R`, within `N` bars.
- `R = 10` ES points, `N = 24` bars (2h of 5-min bars). Fixed in advance.
- Under the null, rejection rate ≈ 50% and equals the control rate.
- **Decision rule:** H1 is supported only if CR rejection exceeds control by
  ≥ 3 percentage points with a session-clustered bootstrap 95% CI excluding zero.
  Anything smaller is noise regardless of p-value.

## Exploratory (reported, but NOT decision-grade)

- **E1** PS (put support) rejection when approached from above.
- **E2** HVL as day-type divider: range/trend conditional on open above vs below.
- **E3** Do session highs/lows cluster near GEX 1–4 more than near random strikes?

These carry a multiple-comparisons burden (~14 levels × several definitions).
A positive E-result is a *hypothesis for a future round*, never a green light.

## Controls — non-negotiable

1. **Matched random strikes.** Every level stat is paired with control strikes on
   the same 25-pt grid, same session, matched on distance-from-open. If CR works
   but so does a random strike at equal distance, we measured mean reversion, not
   gamma.
2. **No lookahead.** MQ rows whose `eod_date == session_date` are ambiguous about
   whether they encode that day's close, so levels for session *d* are taken from
   the row of the **prior** session, and the SPX→ES basis is likewise the prior
   session's. Costs a little precision, removes all doubt.
3. **VIX confound check.** Any positive result gets re-run within VIX terciles.
   The regime test died to exactly this confound; assume this one will too until
   shown otherwise.
4. **No Brooks regime engine.** Per standing rule, the broken always-in/regime
   engine and its sim outputs are not used. Breakouts are defined structurally
   from bars only.
5. **Not a backtest.** These are reaction base rates. No fills, no P&L, no costs
   are claimed. Per the phantom-fill rule, nothing here becomes a strategy claim
   without chart-audited trades.

## Expected outcome

Most likely negative, like part 1. The honest prior: gamma walls are widely
watched, and widely-watched levels tend to be arbitraged into noise. A null
result is a publishable result here — it closes the question.
