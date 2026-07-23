# Brooks second-entry rules — mined from the codex (S83, 2026-07-23)

Source: `docs/living/brooks_final.json` (91 setups, 78 tiered rules, 1,390 teachings).
Mined for the S83 regime × 2E study. Full extract lived in session scratchpad
(`mine_codex.py` / `mined.txt`); this file is the durable record.

## Codex's own backtest flags (context)
- H2/L2 with-trend M2B: TESTED, ROBUST (+0.217R, PF 1.32, 5/6 yrs)
- Breakout Pullback: TESTED, WEAK (+0.123R, PF 1.18)
- Second-entry REVERSAL (fading extension): TESTED, FAILED (PF 0.32, 0/6 yrs)
⚠️ These flags predate the S71 "do not resurrect" verdict on `brooks_bt_*` numbers
(detector mislabeling) — treat as directional hints, not results.

## Top-12 computable filters (ranked by Brooks' emphasis)
1. Attempt-index == 2 — take the second attempt, never the third; after strong
   momentum the FIRST reversal attempt is banned outright.
2. Trend-direction validity — H-counts only in bull/range, L-counts only in
   bear/range; opposite counts are traps (fade material, not entries).
3. Prior-strength gate — "a high 2 alone is not a setup": the H1 leg must have
   broken a minor trendline / contain >=1 strong with-trend body.
4. EMA-touch M2B/M2S — two-legged pullback tags the 20-EMA at the signal bar.
5. Countertrend precondition — no reversal-side 2E without a prior trendline/
   channel break that reached the EMA.
6. Post-climax lockout — after a >=2x-ATR climax bar late in a trend, suppress
   H1/H2 for ~10 bars (two-legged correction expected first).
7. Momentum gate on fades — 4+ consecutive trend bars => first reversal attempt
   banned, second allowed.
8. Signal-bar quality — with-trend body >=50-60% of range, close near extreme;
   doji => require attempt 2 or veto.
9. Overlap/barbwire veto — >=3 overlapping bars + doji near flat EMA => no stop
   entries; count-based signals void in tight ranges (last-15-bar range < 0.3 ADR).
10. Range-extreme polarity — on range days, H2 near the top is a SHORT fade,
    L2 near the bottom a LONG fade (opposite of trend-day handling).
11. Better-price trap veto — a 2E filling at a BETTER price than the 1E is
    suspect ("most good second entries are at the same price or worse").
12. Failed-L2/H2 trap reversal — a count-signal that triggers and fails within
    2 bars => enter opposite at the trapped stops.

## Selected doctrine (the load-bearing quotes, paraphrased)
- "A second entry is almost always more likely to be profitable than a first."
- H2/L2 valid ONLY with the trend or in a range; H2 in a bear is a trap.
- Steep-trend countertrend ban: no countertrend even on an H2/L2 without a prior
  significant trendline break or channel overshoot.
- ~80% of days are non-trend days whose best trades are second-entry reversals
  at NEW swing extremes (range polarity).
- Double-bottom variant (two pullback lows ~equal) is a particularly reliable H2.
- H2 buys valid even at the high of the day in a bull.
- If a good 2E fails, you're misreading the market — no third entry (wedge/H3
  in a tight channel is the one exception, and H3 > H2 there).
- Post-climax: expect H1 AND H2 to fail; wait ~10 bars / two-legged correction.
- In barbwire (3+ overlapping bars + doji, flat EMA): only failed-breakout
  second entries; never buy the high / sell the low of it.
- Institutions defend 2E stops: probes often stop 1 tick shy of the signal-bar
  stop level (why sigbar+1t stops mostly survive).

## Full mined list
68 distinct rules were extracted with per-rule computable proxies; the complete
list is reproduced in the S83 handoff session materials. NOT-computable residue:
subjective doubt, felt urgency, emotional capacity to reverse. Everything else
has an OHLC/tick proxy.
