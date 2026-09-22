# TD fill-report v2 + EOD backstop — greenlit spec (2026-09-08)

ThetaData reviewed the Aug IB-vs-TD fill report and gave 8 improvements. User greenlit
**Tier 1 + Tier 2** (below); **Tier 3 shelved** until the fill comparison is locked.
TD's headline: the fills hold up — 5.8% haircut is normal for a marketable engine, sim
isn't flattering itself.

These belong in the **EOD backstop** (authoritative IB-vs-TD comparison from TD tick
history at the desk's real fill timestamps), NOT the live shadow pings (which stay a
quick monitor). Applies to the retrospective Aug 187-trade report AND each live-shadow day.

## Tier 1 — fill-grading accuracy (DO)
1. **Tick-window grading.** IB exec time is to the second; 0DTE NBBO updates ~150–300×/sec,
   so `at_time` grades a fill against 1 of ~300 possible quotes → the 43 below-zero + 11
   through-book outliers are a timestamp artifact. FIX: per fill, pull the whole second
   `history/quote?interval=tick&start_time=HH:MM:SS.000&end_time=HH:MM:SS.999`, grade against
   the best/worst touch in that second — a BUY is achievable if ≥ lowest ask in the second,
   a SELL if ≤ highest bid. Keep `at_time` for the freshness check.
2. **Package grading.** Condors/flies are combo orders; IB allocates per-leg prices from the
   package, so per-leg is an artifact. FIX: grade the NET package vs the package NBBO built
   from the legs at the same instant. For print confirmation of a package use same-millisecond
   condition **130/131/134** prints across the strikes (legs of a complex trade print together);
   keep single-leg conditions **0/18** for single-leg fills.
3. **Settlement — biggest lever** (115/187 trades settle). The 16:00:00 print ≠ official close;
   the index updates ~4 min into the closing auction and SPXW settles on the official close.
   Sep-4: 16:00:00 = 7717.85 vs final 7718.60; ≥0.5pt on 14/22 days, max 2.35 (Aug 20) — flips a
   0DTE wing ITM/OTM. FIX: use the FINAL close. **CONFIRMED source: `/v3/index/history/eod`
   `close` = 7718.60, last_trade 16:04:34 (post-auction final).** No need for TD's 22-close list.
4. **Aug-25 gap.** TD's SPX/SPXW quote record is missing 09:25:00–09:41:49 ET that morning;
   trades intact. Any SPXW fill in that window grades against the stale 09:25 quote — use the
   trade prints there / exclude. Likely our one stale exclusion.

## Tier 2 — method adoptions (DO, low effort)
- **Exit engine (level-acceptance):** evaluate the premise on **1-minute rows**
  (`history/quote interval=1m` for the legs; `strike_range` pulls a band in one call), using
  the `underlying_price` on the IV rows for SPX on the same minute grid. When the premise
  breaks, take the touch on the row X minutes later as the exit; save the tick pull for grading
  the fill afterward. This is the clean way to build the wall-source-sim exits AND solves the
  intraday-underlying problem.
- **Expected move:** match TD's IV convention — **calendar time, √365** (their IV is solved on
  hours-to-expiry/8760, min 1h): move = S × IV × √(hours_left/8760), or √(1/365) for a full day.
  252 does NOT match their IV. Convention-free 0DTE alt = ATM straddle mid at entry. (Matches the
  MenthorQ 1D-min/max √365 finding.)
- **GEX base formula** confirmed = Σ gamma×OI×100×spot²×0.01, calls +, puts −; call wall = max +,
  put wall = max −, flip = running-total zero-cross. (Matches what we derived.)

## Tier 3 — SHELVED (until fill comparison locked); documented so it's not lost
**0DTE walls from trade-flow, not OI.** OI is stamped ~06:30 ET reflecting the PRIOR close, so
for a same-day expiry it never sees the positioning built DURING the session — which is what
forms the 0DTE walls. Method: `trade_quote` gives every print with the NBBO in effect → print
at ask = buy, at bid = sell → build NET positioning per strike through the day → apply our own
Black-Scholes gamma off TD's IV. Implication: our OI-based gexlog replication has a real ceiling
for 0DTE; trade-flow is the upgrade for the July modeling. Heavier pull + methodology change =
its own scoped study.

## Build order (when executing)
Settlement (#3) → tick-window (#1) → package grading (#2) → Aug-25 handling (#4) →
1-min exit method (Tier 2) → √365 EM. Verify on hand-traced fills before any aggregate.
See [[td-vs-gexlog-wall-sim-comparison]] and the fill-validation note
docs/options_0dte/thetadata_fill_validation.md.
