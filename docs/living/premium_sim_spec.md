# Premium-desk sim spec — the minute-data experiment battery

**Status:** waiting on data. Turnkey plan for the moment we have **1-minute 0DTE
SPXW option data (ideally 2022-05 → present)**. Until then nothing here can be
honestly tested — 0DTE intraday behaviour cannot be inferred from EOD or from the
7-DTE proxy (the S-gexlog lesson). This doc is the build order so the data drop is
plug-and-play.

## Why we can't test these now
- The desk is a **forward paper record** (started 08-04). n≈4 days — far too small.
- Every experiment below is an **intraday-path** question (when to exit, how wide,
  where to center, manage-at-50%). None are answerable from daily bars.
- 0DTE SPXW didn't exist before 2023; a "2-yr" pull realistically starts ~2023 for
  true 0DTE, earlier only for 1-DTE. Record the actual first date on arrival.

## Data contract (what the pull must contain)
Per SPXW expiry = trade date, 1-min bars for the strikes we touch:
`ts, expiry, strike, right, bid, ask, mid, (underlying_spot)`.
- Strike coverage: at least spot ±1.5% (matches the live chain recorder window) so
  every centering/wing variant below can be priced without extrapolation.
- Underlying 1-min spot aligned to the same clock (for centering + exit triggers).
- Cross-check the first week against our own live `chain_YYYYMMDD.csv` recordings to
  confirm the vendor's mids agree with what we booked (fill-realism gate — the S73
  phantom-fill rule: treat any too-good PF as a bug until proven).

## Replay engine (build once, reused by all 8)
`scripts/premium_replay.py` — deterministic, no look-ahead:
1. For a trade date: load the day's 1-min chain + spot.
2. Reconstruct the gameplan strikes from that day's real brief fields (EOD center,
   Open center at 08:30, walls, EM) — reuse `options_gameplan.build_triggers` logic.
3. Enter at the modeled time; mark P&L each minute from the vendor mids (same
   `fill_model`/slippage as the live daemon so paper and sim are comparable).
4. Apply the exit rule under test; book the result with full per-leg detail.
5. Emit one tidy row per (date, structure, center, variant) → a dated CSV, plus a
   per-trade minute P&L path for the grade-bucketing work.
**Guardrails:** honor the live exit primitives (short-strike acceptance = spot holds
beyond the short ≥10 min; 14:45 time-stop) as the *baseline* arm so every variant is
measured against what we actually trade today.

## The 8 experiments (each = one variant arm vs the live baseline)
Ordered by expected value / independence. Each reports: PF, avg/day, Sharpe, win%,
tail (worst day), split by gamma regime + event_day (so results compose with #20).

| # | Question | Variant arm | Baseline | Decision metric |
|---|---|---|---|---|
| 15 | Exit mode | (a) wings-independent (b) both-together (c) hold-to-expiry | live: independent + accept/time-stop | PF & tail per mode; the +686 vs ~+100 vs −570 fly anecdote needs n |
| 22 | Manage at 50% max profit | close leg at 50% of credit captured | hold to accept/time-stop | avg/day & Sharpe; their recurring rule vs our hold |
| 14 | Event wing width | wings 35/50pt on event days | fixed 25pt | tail reduction per $ of credit given up (pairs with #20 NEG-gamma cell) |
| 28 | Directional fly center | shift ATM fly center by k·(open−prevclose) or toward nearer wall | symmetric ATM | fly-call drawdown on drift days (08-07 both losers were fly calls) |
| 23 | RSI-extreme skew | short call tighter than short put when RSI>70/80 | symmetric | credit & win% on extended tapes |
| 24 | Gap-into-wall fade | pre-position bear-call at Call Wall on gap-up-into-wall days | none | hit-rate of the ~20 archive gap-fade days |
| 12 | Credit-scaled sizing | size ∝ credit (fat-credit flies vs thin far condors) | flat size 1 | risk-adjusted return; the day-1 fat-credit-beats-thin observation |
|  2 | Pivot-wing condor | wings at S2/S1/R1/R2 instead of EM±wings | EM-band condor | containment vs EM-band variant, split by regime |

## Grade-bucketing (the labeling payoff)
Once the replay produces per-trade minute paths across ~2 yrs:
- Compute the live grade ladder (rich+cushion=A … near-free=D) **at entry** for each
  historical trade, then measure realized P&L **by grade bucket**.
- If grades A/B materially out-earn C/D out-of-sample, the ladder becomes a real
  entry filter (today it's `F`/unconditional). Validate on a walk-forward split, not
  in-sample — a high in-sample separation is the overfit trap to reject.

## Compose with the live forward record
Every arm above must also be scored on the growing forward paper record, not just
the historical replay — the archive tells us the past regime, the forward tells us
whether it survives contact. Cross-check: a variant that wins in replay but loses
forward is not shipped.

## Cross-refs
- Improvement-log items: 2, 12, 14, 15, 22, 23, 24, 28 (bucket B).
- #20 gamma-gate (VALIDATED 08-08) is the split axis for every table here.
- Fill-realism rule: `backtest_fill_realism` memory (audit trades on charts before
  believing any PF).
