---
title: Interpretations for Some of mzBigTrade Indicator Order Flow Patterns
url: https://www.mzpack.pro/interpretations-for-some-of-mzbigtrade-indicator-order-flow-patterns/
date: 2020-11-25
topic: core-concepts
research_relevance: high
---
## Summary
A visual glossary of mzBigTrade order-flow patterns and how to read them. It defines the indicator's triangle markers (DOM support/resistance/liquidity pulling, aggressive trades) and walks through four annotated chart patterns: selling absorbed by DOM support + icebergs (long setup), aggressive buying into DOM resistance at a top, liquidity pulling combined with aggressive buying at local highs (avoid), and a huge aggressive sell trade read as a stop-loss trigger / selling culmination. General rule: ignore small DOM events (small triangles).

## Key concepts & definitions
- DOM Pressure: solid colored triangles.
- DOM Support: green triangles.
- DOM Resistance: red triangles.
- DOM Liquidity Pulling: grey dotted triangles (limit liquidity being pulled).
- Aggressive Trades: dotted-contour triangles; may involve slippage.

## Rules / thresholds / settings
No numerical parameters or thresholds given. Qualitative rules:
- Pattern A: "Selling. But with DOM support and Iceberg orders" — use these trade clusters as long targets/zones.
- Pattern B: "Aggressive (dotted contour) buy trades (with slippage) with DOM resistance at the top" — buying into resistance at a top.
- Pattern C: "DOM liquidity pulling (grey dotted triangle) but with aggressive buy trades — avoid this on local highs."
- Pattern D: "Huge Aggressive sell trade — stop loss trigger, selling culmination."
- "Ignore small amounts of DOM events (small triangles)."

## Order-flow signature described
Long signature: cluster of sell market orders met by green DOM-support triangles and iceberg markers (passive buyers defending). Fade/avoid signature at highs: aggressive slippage buying while red DOM resistance sits above, or while grey dotted triangles show liquidity being pulled (no real passive support behind the move). Exhaustion signature: one outsized aggressive sell print at a low = stops being run, selling culmination.

## Relevance to our research
Maps almost one-to-one onto our signature taxonomy: Pattern A is defended-level absorption with iceberg refill; Pattern B/C are effort-vs-result failure at extremes (aggression into resistance or into pulled liquidity); Pattern D is the capitulation/stop-run print we can use as a level-touch outcome marker. The "ignore small events" rule supports size-filtering our detectors.
