# Raw extraction — Grimes Course Workbook, PDF pages 307–408 (Modules 7–9: breakouts, plans, failures; psychology skipped)
Extracted 2026-07-22 (S81). PDF page cites. Pages 374–408 nearly pure psychology — near-nothing regime-relevant.

## Epistemic frame
- p.307-309 — Cone of uncertainty: baseline forecast = future prices ≈ current prices (options-pricing null); edges are small statistical tilts on top → a regime engine should output probability tilts, not point forecasts. Tools must be "simple and robust."
- p.341 — "Market action is mostly random, and most markets do not offer any tactical edge at most times — trading opportunities are fleeting." → default no-edge/no-trade state.
- p.372 — Correlated-input warning: overbought/oversold indicators, sentiment, ratios, bands "all measure the same thing, in a different way." Three oversold signals = one signal. Do NOT vote-count correlated features in a classifier.

## Market cycle / regime taxonomy
- p.317 (Module 7 intro) — implicit 4-state cycle: (1) trending while moving, (2) trend possibly ending (termination), (3) ranging within ranges, (4) breaking out of ranges into new trend legs. The regime state machine: trend → termination → range → breakout → new trend.
- p.310-312 — Strategy = big-picture classification first: "swing analysis, some looks at momentum and volatility, and perhaps a quick heuristic glance" — "is this going up, down, or sideways?" Get direction right and entry details barely matter.
- p.403-404 — Empirical regime-frequency claim: for a trend-pressing daytrading style, "maybe 1 in 5 trading days really rewards this style" — ~20% of sessions trend days, ~80% chop (anecdotal but concrete prior).

## Continuation vs reversal statistics
- p.369-370 — Big moves continue: after "a very large move out of all proportion to its recent history," another large same-direction move is far more likely than reversal (cites Mandelbrot). Extreme range expansion = continuation state, NOT mean-reversion state. Example extreme: 5× ATR nearly instantly — still dangerous to fade.
- p.370-373 — Reversal bias is the classic trader error; any trend shows multiple fake "head and shoulders."

## Trend termination / transition signature (the key transition rule)
- p.373 — Required two-step sequence before classifying trend-end: (1) a clear trend-break signal from the named set — exhaustion, climax, three pushes, failure test, price rejection — then (2) "change of character": new momentum in the opposite direction, setting up a pullback in the possibly-new trend. "In the absence of that sequence... the best bet is to not try to fade the trend." Directly codable: transition state requires break-event + counter-trend momentum impulse; otherwise remain in trend state.
- p.315 — Parabolic/overextended context strengthens reversal signals: failure test after a parabolic run ("free bars") is much stronger than after a single thrust. Retest of highs after a parabolic move = ideal bull-trap location; "never pay a breakout here."
- p.349 — Climax termination: trades grinding favorably day after day are often positioned into a climax; "When these moves end, they often end dramatically."

## Failure test (quantified spec)
- p.313 — His first-tested pattern, "clear and strong statistical tendency": brief probe above resistance (below support) → immediate failure and sharp reversal. Entry: short at yesterday's close or at that level or higher; stop above yesterday's high.
- p.314-315 — Mechanism = stop runs: "markets move to levels where orders are clustered... run stops"; why so many breakouts fail; why markets "predictably reverse from highs and lows of the day."
- p.316-317 — Quality filter at range-bottom: strong version first flushes decisively through the level ("say 10 handles or more" on the S&P) electing stops, then reverses sharply to close on the highs. A bounce that didn't clear the level/elect stops = weak signal.
- p.313 — Counter-case: "continued consolidation and pressure against resistance is very constructive for the bulls" — pressing without rejection = continuation.

## Followthrough rules (regime-confirmation, quantified)
- p.317 — After a bullish reversal signal: "If this is a strong buy, we should see very quick followthrough... within a week or two" (daily). Negative rule: "going flat and dull near current prices would likely be a consolidation pointing lower." Absence of followthrough within N bars = downgrade/flip.
- p.317 — HTF override: strong intact HTF uptrend → favor upside even while expecting a short-term flush.

## Multiple-timeframe logic
- p.340-344 — Canonical conflict: daily uptrend inside weekly downtrend (daily "uptrend" may be a weekly pullback). Three plan options: skip counter-HTF trades / take with tighter stops & faster profits / ignore HTF. A weak daily failure test gains significance when the weekly presses multi-year support — HTF context can UPGRADE LTF signals.
- p.329-330 — Filters to test: no pullback trades if HTF shows a trend-termination pattern; trigger pullback entries via LTF failure tests.

## Volatility / stops / execution (quantified)
- p.345 — Use ATR, not HV, for stops (HV is close-based, blind to highs/lows; stops execute intrabar). "Stops placed less than 1 ATR are probably too close."
- p.312, 347 — Stop options: 3–5 ATR (wide) or low of X previous bars ± fudge; his practice: initial stops 2–4 ATR.
- p.312 — Breakout entry: buy break of previous bar's high, rolling down bar by bar; volatility fudge factor 2–5 points on S&P futures above the level; or hold-above-level-for-X-minutes time filter.
- p.318 — Breakout regime: spreads widen; volatility extreme and hidden within single bars; many news-driven.
- p.348-349 — Exit style must match regime: trend trades → trail (e.g., yesterday's low); countertrend → quick predefined targets. Tested: chart-based targets NOT more effective than target = 1× initial risk; exception: intraday highs/lows of the day DO deserve respect.
- p.346-347 — Gap losses ~4.5× initial risk happen → 1–2% per-trade risk. p.351 — If an add fails, exit more than the added amount.

## Asset-class note
- p.313-314 — Short-term mean reversion muted in currencies, as is longer-term momentum, vs equities/commodities — regime parameters are asset-class-specific.

Not present in this range: Keltner settings, MA/MACD params, trend-day checklists (earlier modules).
