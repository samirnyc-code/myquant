# Raw extraction — Grimes, The Art & Science of Technical Analysis, PDF pages 1–96
Source: Wiley 2012 book PDF (480 pp). Extracted 2026-07-22 (S81) for the regime-engine build.
Page cites = PDF page numbers (book page ≈ PDF page − 16).

## Core premise / no-trade baseline
- p.19-20, 30: Markets are usually near-efficient; most price movement is random. Edge exists only in identifiable moments when markets are "less random than usual." Implication: a regime engine's DEFAULT state should be no-trade/random; trade states are exceptions.
- p.30: Two-force model — motive vs resistive force. Normal state = equilibrium (random walk, no edge, avoid). Trend = motive force overcomes resistive; occurs after a "failure of liquidity on one side" producing an impulse/momentum move. Two resolutions of any impulse: (a) resistive force reasserts → back to balance (possibly at new level), or (b) feedback loop → trend.
- p.23: The only edge source = buying/selling imbalance; patterns are its footprint.

## Chart/timeframe mechanics (quantified)
- p.27: Related timeframes should differ by factor of 3–5x.
- p.27-28: Vertical distances (stops, targets, volatility) scale with sqrt of timeframe ratio — e.g., $0.25 stop on 5-min → $0.25 × sqrt(30/5) ≈ $0.61 on 30-min.
- p.27: Log scale when chart shows >100% price change or >2 years of data.

## Market structure primitives (pivots/swings)
- p.31-33: First-order pivot high = bar with higher high than the bar before and after (inverted for lows). Second-order pivot high = first-order pivot high flanked by lower first-order pivot highs. Third-order = same recursion; third-order pivots "usually mark major inflections." Second/third-order pivots need not alternate high/low — rules must handle 3 same-type pivots in a row (p.33). Post-hoc/context tool, not predictive at right edge (p.34).
- p.34-35: Swing-length rules (core regime classifier):
  - Buyers stronger → upswings longer than downswings in BOTH price and time.
  - Sellers in control → downswings longer.
  - Equilibrium → no clear pattern to swings.
  - S/R = rough AREAS (not lines) beyond which pivots fail to penetrate.
- p.35-37: Uptrend = higher pivot highs + higher pivot lows; trading range = random, no swing pattern; sharp moves within ranges are "more or less unpredictable"; break of HH/HL = warning only, not tradable alone; best breakouts preceded by higher lows pressing into resistance (ascending pressure).

## Bar-level / intrabar signals
- p.39: Close near bar high → buyers in control that period; close mid-bar (long shadows) → no conviction. Several consecutive closes on absolute highs = statistically short-term EXHAUSTION, slight reversal expected — don't enter with-trend after this.
- p.39: Large bars with open/close at opposite ends = lower-TF trend inside; small bars with open/close near center = lower-TF trading range.
- p.42: Directional moves emerge from contracted volatility. Even where baseline is mean reversion (short-term equities), slight continuation edge out of volatility compression. Inside bar = high ≤ prior high AND low ≥ prior low; multiple inside bars = lower-TF triangle = compression; trading INSIDE it is a losing proposition, but it sets up strong breakouts.

## Wyckoff cycle (pp. 47–55)
- p.48: Four phases: Accumulation (sideways, smart money buys), Markup (uptrend), Distribution (sideways, smart money sells), Markdown (downtrend).
- p.49: Accumulation signature: sideways range, intermediate-term MA FLAT, price chops both sides of the MA — looks like equilibrium. Breakout-chasing at range edges is exactly the losing behavior in this state.
- p.50: Spring (failure test): probe below range support that immediately finds buyers. Quantified: long lower shadows below support with few/no closes below it; excursion below support lasts less than ~1/4 of the bar's period (daily: at most a few hours below; hourly: <15 min). Standalone long-lower-shadow candles have NO predictive power; only in accumulation context do springs tilt odds up.
- p.53: Distribution vs accumulation discriminators: price rebids more slowly after drops below support; price spends more time hugging the bottom of the range; pressure against the TOP of range is more common in accumulation; false breakout above range with long upper shadow = upthrust (inverse of spring). Distribution ends when price drops below support and fails to bounce.
- p.54-55: Markdown: downtrends begin from optimism/complacency, not fear; bounces fall short of prior highs; final panic marks the bottom. Volatility reliably expands on declines; bear rallies are sharp/vicious vs orderly bull pullbacks — up/down NOT mirror images.
- p.55-56: Failure modes: sequence isn't always acc→up→dist (can be acc→up→acc); mid-trend sideways ranges are ambiguous in real time; stops under accumulation ranges are wrong (you want to buy flushes).
- p.55: Fractality bounded by liquidity — liquid instruments fractal down to ~15-second charts; illiquid degenerate into noise below daily.

## The Four Trades taxonomy (pp. 56–61) — regime→strategy mapping
- Trend continuation: high probability ("verifiable statistical edge for trend continuation"); appropriate in markup/markdown; failures usually small unless crowded in overextended trends.
- Trend termination: low probability, high reward/risk; win = trend STOPS (not reverses); true reversals rare. Biggest blowups = fading trends and adding.
- S/R holding: lowest reward/risk; support "usually does not hold cleanly" — dropouts below support strengthen it (shakeouts). Exception: failed breakouts = very high probability (p.60).
- S/R breaking (breakouts): "most breakouts fail" (p.60); breakout zones are high-volatility/low-liquidity; realized losses can be multiples of intended risk; best breakouts pre-set by higher lows into resistance / large-scale imbalance.

## Trend structure (Ch. 3, pp. 65–96)
- p.66-67: Fundamental pattern on ALL timeframes: impulse → retracement → impulse (ABCD); each leg decomposes into the same pattern one TF down.
- p.68 (indicator spec): modified Keltner channels at 2.25 × ATR around a 20-period EMA + modified MACD (Ch.7/App.B). Concepts transfer to Bollinger/percent bands, ROC/CCI/standard MACD/stochastic.
- p.68-70: New-trend detection out of a range: sharp momentum move penetrating the channel + MACD fast line at new high/low vs recent history ("new momentum high"). Indicator is redundant confirmation of visible structure.
- p.69-70: Trend-health rule: as long as each with-trend leg's momentum is roughly consistent with prior legs, buy the next pullback. Trend-break rule: sharp CONTRAtrend momentum on a pullback (big countertrend bars, MACD new extreme against trend) = trend broken until further notice.
- p.70: Three most important continuation signals: new momentum highs/lows; subsequent legs making similar impulse moves; ABSENCE of strong countertrend momentum on pullbacks.
- p.70-76 Climax/exhaustion (trend-termination signature):
  - Extremely strong impulse = more likely climax than strength — the central ambiguity of TA (p.70).
  - Buying climax markers (p.71-72): accelerated trend rate (parabolic); large range bars pulling away from the MA; many "free bars" (entire bar outside the Keltner channel — low above upper band); volume spikes 4–5x average near the extreme; many bars closing at/near their highs (inverse for selling climax).
  - Checklist (p.76): usually after ≥2 trend legs same direction; acceleration; relatively infrequent; at significant new high/low (unusual mid-range); CONFIRMED only by subsequent sharp contratrend momentum — absent that, trend may just be very strong.
  - Usage: not a standalone countertrend entry; it's a do-not-enter-pullbacks / lighten-up signal (p.72-73). Climax lows often retested and broken later (p.74-75).
  - Climax detection out of a RANGE is unreliable — volatility contraction skews range-expansion measures; strong range breakouts usually continue even if apparently climactic; only score climaxes after extended trends (p.73).
- p.79-81 Three pushes: three drives to new high/low after an extended trend, roughly symmetrical in time/price; spacing between the three highs compressed vs earlier trend (new highs every ~15 bars → pushes ~5 bars apart); best examples: third push breaks the trendline across pushes 1–2. Reaction: tighten stops/reduce with-trend exposure; next pullback has elevated failure probability.
- p.76-78 Pullbacks: countertrend move on lighter volume ("traditional volume relationships not as reliable as believed"); alternate simple vs complex (Elliott alternation) — 5 trend legs typically = 2 simple + 2 complex pullbacks, almost never 4 simple. Complex pullback = two-legged (a full lower-TF trend structure); on higher TF revealed by several down-closes separated by ONE up-close bar (p.41-42). Second leg often terminates at the measured-move objective of the first leg (p.78).
- p.78-79 Measured move: CD ≈ AB added from C; rough guideline; profit target or entry locator for complex-pullback leg 2.
- p.81-87 Winning-pullback filters:
  - Higher-TF alignment: TTF pullback trade against the HTF trend = much lower probability (p.81-82).
  - Must follow significant momentum: only after impulse moves large vs prior swings; quantifiable as MACD at significant new high/low vs recent history (p.82-83).
  - NOT after a momentum divergence (price new high, indicator doesn't) — skip the next pullback (p.83-84).
  - Location in trend: rising suspicion with each leg; legs 4–5+ increasingly generate divergences then roll over; up to ~10 legs possible (rare) (p.84-85).
  - Retracement %: expect termination ~50% of setup leg, practical band 25–75%, large error margins (p.85).
  - Trends too strong to pull back: stair-step tight ranges or price sliding along the upper Keltner band; very strong imbalance, hard to enter, prone to sudden countertrend spikes (p.85-86).
  - Good pullbacks = lower volatility/activity than trend legs, smaller lower-TF ranges, symmetric/clean geometry; erratic pullbacks = less tradable regime (p.85-87).
- p.87-93 Pullback failure modes (3): (1) no momentum out → flat range at pullback level → edge gone, exit (p.88); (2) sharp countertrend momentum breaks the "wrong side" — can mark long-term trend inflection via trapped traders (p.89-90); failed-breakdown at pullback bottom that immediately reverses = outstanding with-trend entry (trapped shorts) (p.91); (3) new leg fails around the prior pivot extreme — marginal-new-high-then-fail is the most treacherous (most trapped traders, sharpest countertrend momentum) (p.92-93). Prior swing high/low = first conservative profit target for any pullback trade (p.92).

## Dow Theory trend states & transitions (pp. 93–96)
- p.94: Uptrend = higher highs AND higher lows (both required — HH without HL means buyers not in control); downtrend = LL AND LH.
- p.95: THREE trend states: up, down, UNCERTAIN — the engine must have an explicit uncertain/ambiguous state; forcing every market into up/down is wrong.
- p.95: Trend change type 1: fail to make new high → status UNCERTAIN (not downtrend); confirmation only when price trades through the last pivot low (LH + LL both present). Markets commonly fail a new high, consolidate, then resume — the failure alone is only a warning.
- p.95-96: Trend change type 2: swing off the high directly takes out the prior pivot low (HH + LL = broken pattern; often traps trend traders → attractive countertrend setups). Confirmation needs two more steps: next rally falls short of prior high AND next decline takes out the prior low. Inverted for down→up.
- p.96: Known failure of naive Dow rules: a complex (two-legged) consolidation triggers a false "trend change" at exactly the spot to buy — any HH/HL state machine must special-case two-legged pullbacks or it flips regime at the worst point.

## One-line regime-engine takeaways
- Default = random/no-trade.
- Trend entry = channel-penetrating impulse + new momentum extreme out of compression.
- Trend health = consistent leg momentum + no countertrend momentum spikes + no divergences.
- Trend exhaustion = climax (free bars/parabolic/4–5x volume) or three pushes or divergence, confirmed only by subsequent contratrend momentum.
- Transition = Dow uncertain state, with the complex-pullback special case.
- Range subtype (accumulation vs distribution) discriminated by spring-vs-upthrust behavior and where price hugs the range.
