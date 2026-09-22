# Raw extraction — Grimes Course Workbook, PDF pages 103–204 (Modules 2 end, 3 "Market Structure & Price Action", 4 intro)
Extracted 2026-07-22 (S81). PDF page cites. Pages 115–174 are mostly image-only exercise charts.

## Trend structure and trend-health
- p.109: Fundamental trend template: "trending markets move in alternating rounds of with-trend strength, interspersed with pullbacks or pauses against the trend that then break into further trend legs." A complete trading program can be built on this alone.
- p.109-111: Trend-integrity test = character of the move OUT of each pullback/consolidation. Healthy: breakouts from with-trend consolidations quickly go to new highs, don't pause much, new legs consolidate at higher levels. Regime-change signature: "the attempted moves up failed pretty quickly" — repeated failed breakouts from bullish consolidations = "character has changed, maybe the market is entering a new regime." Quantifiable: bars-to-new-high after consolidation break; whether new leg holds above prior consolidation.
- p.190-191: Swing-leg asymmetry: "the with-trend legs need to be stronger than the countertrend pullbacks" — leg length/slope/velocity ratio with-trend vs counter-trend as a trend-health feature. Core discrimination problem: "good" strength vs "overheated" overextension; all proposed solutions "work at times and fail at others"; typical failure = exiting trends too early.

## Climax / exhaustion criteria
- p.192: Buying climax bar spec: bar range 3+ times the average range of recent bars, when it (a) comes at a new trend extreme and (b) obviously breaks the trend's established rhythm. Long upper shadow adds evidence. Violations of trend pattern matter in BOTH directions.
- p.192-193: Post-climax playbook: tighten stops dramatically (even under last 1–3 days' lows); do NOT enter with-trend after the spike; avoid buying pullbacks/breakouts. "A buying climax often indicates the 'last willing buyer' has bought, and the market will often collapse into the vacuum."
- p.193: If a strong selloff follows a buying climax, the next bounce is often a high-probability short. Climax typically caps the trend "at least for several weeks"; alternative path = pause/absorb then resume.

## "Slide along the bands" regime (low-volatility grind trend)
- p.176-179: Distinct trend sub-regime: price presses into one band and STAYS, trending without normal pullbacks. Identification: price hugs one band while volatility (stdev of returns) craters and volume dries up. Rare but powerful; "can go much further than anyone thinks possible"; looks dull. Termination: "they tend to end in one way: with sharp, volatile counter-trend pops." Management: tight stops, tighten every 2–3 bars at new extremes; don't enter via retracements.

## Two Forces Model (the regime taxonomy itself)
- p.185-186: Price action = interaction of mean reversion (large moves tend to be reversed) and momentum (large moves lead to further same-direction moves).
  - Forces balanced (usual) → ~random walk, "market in equilibrium... the types of markets we try to actively avoid" → NO-TRADE regime definition.
  - Momentum dominant → trend regime. Mean reversion dominant → range regime (fade large moves).
- p.186: Timeframe- and asset-class-dependent; tools don't transfer without recalibration. The whole technical question: identify in advance when one force is likely stronger.

## Wyckoff cycle & four-trade classification
- p.181-185: Accumulation → mark-up → distribution → markdown. Four trade categories mapped to phases:
  1. Trend continuation (p.182): pullbacks, with-trend breakouts. "The most reliable profits are taken consistently at or just beyond the previous highs."
  2. Trend termination (p.182-183): "true trend reversals are exceedingly rare"; the common win = market simply stops trending. Fading trends + adding = source of the most dramatic blowouts.
  3. S/R holding (p.183-184): "Support, even when it holds, usually does not hold cleanly. The dropouts below support actually contribute to the strength of that support."
  4. S/R breaking (p.184-185): the transition event into a trend phase. "Most breakouts fail." Best breakouts pre-set by "the market holds higher lows into the resistance level before the actual breakout."
- p.182: "Trades from certain categories are more appropriate at certain points in the market structure" — the job includes NOT trading most of the time.

## Volatility regime facts
- p.111-113: Volatility clustering: "large price changes are much more likely to be followed by more large changes." ARCH/GARCH/EGARCH; shocks decay like waves from a stone in a pond. After a shock, best bet = more volatility; "it is unusual for a market to become volatile and then to immediately go dead again." Caveat: clustering is NON-directional. Illustration: daily changes > |2.0 stdev| cluster in time.

## Regime-change detection ("Hey, that's different") checklist (p.187-188)
Concrete trigger list:
- Largest volatility-adjusted move (sigma spike) over a lookback (example: largest up move in ~a year).
- Obvious move that breaks a chart pattern.
- Counter-to-expected breakout (must be obvious).
- "Sudden, sharp reversal like a single day that reverses the previous week's movement."
- "Quiet market goes into an extended period of volatility, or vice versa."
Must be anchored in effects that really exist, else analyzing noise.

## Trendline rules (objective spec)
- p.162: Valid trendline: (1) captures the swing low before the high of the trend (uptrend); (2) attaches as far back as possible; (3) cuts NO prices between the two attachment points (may cut after — that's a break).
- p.175: Research protocol: draw bar-by-bar (not hindsight), then score what happens at engagement.

## Range/transition notes from exercise annotations
- p.114-115: transitions/interfaces named "the most complex" technical areas — most opportunity AND risk lives there.
- p.125: range support should be defined as the low of the swing BEFORE the range began, even when active support appears considerably higher (structural boundary = pre-range swing extreme).
- p.116: ranges expand progressively until eventual breakout.

## Meta-rules / performance-as-regime-sensor
- p.190: "A great tool at the wrong time is the wrong tool." Rolling win-ratio of last ~20 trades (1/0 coded, MA) as early-warning regime detector; 5–6 consecutive losses = abnormal → conditions not favoring the play.
- p.189: Trend/range alternation measurable (FFT/Kalman for price cycles); cycles "shift and abort without warning" — useful as a first filter, hard to trade pure.

## Epistemic caveats
- p.107-108: patterns give only "a slight tilt in the probabilities."
- p.201-204: Quant method template: precise conditions → every occurrence → tabulate outcomes vs baseline of all other data; edge must be statistically verifiable and OOS-tested; edges decay.

Hard numbers in this span: climax bar ≥ 3× average recent range (p.192); >|2.0σ| daily-move clustering (p.111); stop-tighten every 2–3 bars in slide-along-bands trends (p.179); post-climax stops under last 1–3 days' lows (p.192); 20-trade rolling win ratio / 5–6 consecutive losses (p.190). No Keltner/MACD numeric settings in this span.
