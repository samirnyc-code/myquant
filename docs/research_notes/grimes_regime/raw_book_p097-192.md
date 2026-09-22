# Raw extraction — Grimes book, PDF pages 97–192 (Ch.3 end, Ch.4 Ranges, Ch.5 Interfaces, Ch.6 Templates 1st half)
Extracted 2026-07-22 (S81). PDF page cites (book page = PDF − 16).

## TREND IDENTIFICATION & INTEGRITY (Ch.3 remainder)
- p97 — MA-slope trend flag: slope of a single MA (e.g. 50-SMA) as direction classifier. Failure mode: false signals cluster when the average is flat; fix = "undefined zone" around zero slope (explicit 3-state classifier: up / down / undefined) at the cost of later signals. MA length sets the evaluation horizon.
- p97 — Alternatives: DMI/ADX for trend strength (Raschke/Connors use ADX without DMI, direction from other tools); MACD histogram for trend-change warnings. All lag pure swing-structure reading.
- p98 — Three trend-integrity measures: (1) length of swings, (2) rate of trend (trendline slope), (3) character of trend legs.
- p99 — Swing-length rule: uptrend = upswings larger than downswings in BOTH price and time. Quantifiable: compare vertical (price) and horizontal (bars) extent of each pivot-to-pivot swing vs prior swings.
- p99 — Weakening: successively shorter upswings = trend running out of steam (equivalent to rounding top / double top / H&S — "all the same pattern").
- p100 — THE key structural signal: the FIRST downswing in an uptrend that is longer than the preceding upswing (in time OR price) = "single most important pattern in length of swing analysis"; lower low, change of character; sets up countertrend short on next bounce — or a complex consolidation.
- p103-104 — Parallel trend channel: standard trendline + clone at most extreme opposite pivot between anchors; must not cut prices between anchors. Price at upper channel = reduce/take-profit zone; consolidate-then-push THROUGH channel = trend accelerates.
- p105 — Two-bar line: line from day-before-yesterday's low to yesterday's high extended into today = intraday exhaustion/inflection (inverse for downtrend).
- p106-107 — Trendline-break fakeout timing: pullback trendline broken then recovered = entry catalyst; market should NOT spend much time outside the line — weekly ≤ ~2 days outside; daily ≤ a few hours; 1-min back inside in <30 seconds.
- p108 — Rate of trend: breaks often shift to a shallower slope (fan of trendlines), not reversal — naive trendline-break signals fail. Ever-steepening lines = acceleration; near-vertical lines break "easily and with impunity" but flag parabolic risk.
- p110 — Quantifiable leg-character features:
  - Swing 2–3× the average swing length after several same-direction swings = overextension/possible climax (explicit threshold).
  - Larger bars = conviction, but very large bars near the END of a leg = exhaustion.
  - Closes below midpoint in uptrend = lower-TF disagreement; closes AT the extreme high for multiple consecutive bars = exhaustion — "counterintuitive, but statistically verifiable."
  - Bars per leg ~redundant with slope. Gaps that don't fill / skipped levels = ease-of-movement conviction.

## TRADING RANGES (Ch.4)
- p113, 129 — Core: trends = persistent imbalance, more predictable. Ranges = equilibrium, ~random walk; direction, timing, and exit of the range all unpredictable → NO-TRADE inside ranges; only edges tradable.
- p114–117 — Random-levels experiment: randomly drawn lines reproduce all classic S/R behavior. Most S/R indistinguishable from random; only obvious widely-watched levels (higher-TF pivots, multi-tested levels, spike extremes, prior day's H/L) have nonrandom effect (p118).
- p118 — EV proof: buying near support with 10:1 R/R in a random walk → win rate ~9%, EV = 0.
- p125 — Level-holds signature = price REJECTION: immediate sharp movement away. A market trending slowly down into support shows no rejection and "often presages a significant break." Spike into level > grind into level.
- p126–127 — Multiple-test rule: each test WEAKENS a level. Should hold on 1–3 tests then leave with conviction; ≥3 returns → probability shifts toward break. Market going quiet/dull at the level = harbinger of failure.
- p127 — Micro tool: 2–3 period MA on the lower timeframe to read rejection vs consolidation at levels.
- p123 — Springs/upthrusts: stop-runs; core accumulation/distribution tells. Volume confirmation: Grimes could NOT substantiate volume as adding value around these patterns.
- p129–131 — Range default prior = CONTINUATION of the preceding trend ("innocent until proven guilty"). Unreadable trading-TF range often = simple higher-TF pullback. Reversal-range bias needs HTF overextension + momentum divergence + terminating formations.
- p132–136 — Range taxonomy (parallel / converging / expanding):
  - Parallel box: violations short-lived; a break may just EXPAND the range. Sloping parallel range against HTF trend = the most common pullback pattern (complex pullback); springs at its lows in uptrends.
  - Tight consolidation hugging one edge of range (< ~25% of range height, p140) = pressure building, classic breakout precursor.
  - Triangles: compression → breakout mode; never fade the first breakout. Ascending triangle (higher lows into flat resistance) = the one variant with real bullish edge.
  - Sharp spike + equal opposite spike → expect triangle/consolidation, suboptimal trading (p135, 156–157).
  - Expanding ranges: they "expend stored energy" and usually resolve into random low-vol ranges, NOT strong moves — avoid (p136).

## TREND↔RANGE INTERFACES (Ch.5) — transition taxonomy
- p137 — Complete transition set: (1) breakout range→trend; (2) trend termination→range; (3) trend reversal; + 2 failure modes: failed breakout, failed trend termination.
- p138, 162 — Base rate: "the majority of breakout trades fail"; "Breakout failures are far more common than successful breakouts."
- p140–141 — Pre-breakout accumulation signatures: (a) higher lows into resistance; (b) tight range near edge of larger range, typically <25% of large-range height; (c) springs/upthrusts inside the pre-breakout range.
- p141–142 — At-breakout: good breakout = volatile, visible event; bar ranges expand. Quant spec: instantaneous volatility = ratio of current bar's range to a window of previous bars. Quiet "polite" push through the level = bad. Slippage should be adverse (positive slippage = impending failure). Immediate satisfaction required; slow grind back = "no breakout at all."
- p143–144 — Post-breakout: first pullback is THE decision point — "if the breakout is going to fail, it is going to fail at this first pullback." Pullback violating the level is NOT itself failure; shakeout below the level often catalyzes the real move.
- p146 — Failure-test quantification: failed breakout = brief excursion, immediate reversal; rule of thumb no more than 2–3 bars outside the level, then strong reversing momentum; close back inside the level critical. Consolidation near the level after re-entry = more typical of eventual continuation through it (p147).
- p148–149 — Breakout pullbacks rarely fail by going flat — flat consolidation outside the level is CONSTRUCTIVE; they fail via sharp momentum out the wrong side; that failure-pullback is a high-quality trade against the breakout.
- p150–151 — Trend→range: "trends fail when pullbacks fail." Preconditions: momentum divergence (necessary warning, not sufficient), extremely high volatility (climax), >3 trend legs same direction — pullback-failure probability rises with each leg. Three failure forms: pullback→range at the pullback level; failure test at prior trend extreme; failure-pullback whose countertrend thrust exhausts ≈ at the measured-move objective, defining the new range extreme (p151–152).
- p152 — Most trend terminations lead to ranges, not reversals; ranges holding near the trend extreme = more likely HTF continuation. Strong momentum beyond prior trend extreme = undeniable continuation.
- p153–157 — Trend reversal (rare), two setups: (1) Parabolic climax: long trend + acceleration; signature = multiple "free bars" entirely outside Keltner channels (p154); after climax expect sharp countertrend → consolidation → second countertrend leg; judge the with-old-trend bounces — smaller in price AND time than new-trend legs = change confirmed (p156). Sharp move + sharp opposite move ⇒ triangle, avoid (p157). (2) Last gasp = upthrust above a recognized top after sufficient consolidation, stops elected, no follow-through, price back below prior high → very reliable termination (p157–158).
- p158–159 — Trend change without warning: rare, catalyst-driven; absence of pattern is itself informative.
- p159 — Change of character operationalized: first downswing bigger than preceding upswing after many swings = flag; monitor next few swings for confirmation.
- p160 — Failed reversals power continuation via trapped countertrend traders; complex pullback's second leg commonly mistaken for reversal.
- p161–162 — Axioms: two forces (mean reversion, range expansion) express as alternation of trends and ranges; four trades, each valid only in its regime phase — "If you apply the wrong trade to current market conditions, you will lose." Absent contrary info, any range = continuation pattern.

## Ch.6 TEMPLATES (regime-relevant quant specs)
- p166–169 — Failure Test (spring/upthrust; Sperandeo 2B): trade beyond clear level, reversal on SAME or FOLLOWING bar with close back inside; enter on that close; hard stop just beyond excursion extreme; must be immediately profitable within 1–3 bars; consolidation near the level after entry = failing (2–3 days above = precursor to loss); stop-out then re-break back inside = obligatory re-entry (size both entries so summed risk ≈ one normal trade).
- p170–171 — Pullback regime filter: market MUST be trending; setup leg at least as strong as prior legs; no momentum divergence. Market character: intraday index products rarely extend beyond 3 legs (ES-relevant); bigger markets trend better.
- p171, 173 — Good pullback: reduced activity (smaller bar ranges), no strong countertrend momentum; lighter volume common but NOT the distinguishing feature. Avoid buying ≥3 tests of pullback support (lower highs into support = failure setup).
- p172, 174, 180 — Entries: trendline/channel undercut-and-recover (washout = lower-TF climax); or limit at sloping support. Stops: farther + random jitter beyond obvious levels; tight stops similar EV, worse costs.
- p175–176 — Targets: previous pivot of setup leg (conservative); measured move CD ≈ AB from C (zone, volatility-grounded); or risk multiples reconciled against structure.
- p181–185 — Complex pullback: two countertrend legs (ABCD); legs tend equal, second-leg terminus via AB=CD (market respects MMO "even more strongly in pullbacks", p184); stop below the whole complex structure valid; after a climax no simple-pullback entries but a complex consolidation can rehabilitate the trend (p183); ≥3-leg pullbacks uncommon/unreliable (p185).
- p186–189 — The Anti (regime-transition detector): (1) termination precondition (momentum loss on successive thrusts, HTF overextension, double top/bottom, failure test); (2) change-of-character impulse — countertrend swing larger than previous countertrend swings, NEW momentum extreme on the indicator (Raschke original: stochastic fast line sloping against slow after slow rolls over, p189); (3) enter first pullback after that impulse. Stop beyond trend extreme. First countertrend thrust commonly exhausts at MMO; if MMO holds and structure looks like complex consolidation → original trend likely resumes. Countertrend trades: take 33–66% off at first target.
- p190–192 — Breakout base: significant levels only (multi-tested, clean, visible); pre-breakout penetrations expend energy (short/small failure tests OK); gap through level = strength ("gap and go"); base = tight range pinned at the edge, or successively higher highs into resistance.

## Most directly codable items
MA-slope with undefined zone (p97); swing length/time comparison + first-larger-countertrend-swing flag (p99–100, 159); >3 legs → failure probability rises (p150); 2–3× average swing = climax (p110); consecutive closes at bar-extreme = exhaustion (p110); range = random-walk no-trade state, edges only (p129); ≥3 level tests → break bias (p126); tight sub-range <25% of range height at edge → breakout bias (p140); breakout validity = current-bar-range/rolling-window ratio expansion (p141) + ≤2–3 bars outside on failure test (p146) + close back inside; free bars outside Keltner = parabolic climax (p154); Anti = new momentum extreme then first pullback (p186–189); MMO (AB=CD) as transition/exhaustion projection (p175, 184, 187).
