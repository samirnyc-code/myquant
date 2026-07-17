---
title: Tape Iceberg Detection: Finding Refilling Icebergs on Historical Charts
url: https://www.mzpack.pro/tape-iceberg-detection-finding-refilling-icebergs-on-historical-charts/
date: 2026-07-16
topic: core-concepts
research_relevance: high
---
## Summary
Explains how MZpack detects icebergs from the tape (trade prints) on historical charts, rather than from live DOM behavior. The signature is a "clip" — a run of identical-size fills at one price inside a single reconstructed trade — with each additional identical clip counting as a "refill" of the hidden reserve. Gives a hidden-volume floor formula, two sensitivity thresholds, and trade logic for defended vs. defeated icebergs. Contrasts with the Hard/Soft DOM-based algorithms in mzBigTrade, which need live or Market Replay data but catch randomized icebergs that tape detection misses.

## Key concepts & definitions
- Iceberg order: large order with only a small visible "tip" in the book; hidden reserve auto-replenishes the tip at the same price and size when consumed.
- Clip: "a run of identical-size fills at one price" — consecutive fills of exactly the same contract quantity at a single price level.
- Refill: each additional identical clip beyond the first (hidden reserve replenishing).
- Worked example: a 503-lot buy swept eight price levels with 176 total fills; within it, "five consecutive fills of exactly 57 contracts at 7510,5"; notated *5 x 57 @7510,5 (+7)* where +7 is a partially consumed final refill.
- Fingerprinting: "clip size itself is a fingerprint: machines often reuse the same display quantity all day" — same size elsewhere suggests the same player.
- Detection is a floor measurement: unexecuted reserve is invisible — "the iceberg was at least this big."

## Rules / thresholds / settings
- Hidden volume formula: (refills − 1) x clip size. Example: (5 − 1) x 57 = 228 contracts estimated hidden liquidity, plus partial remainder of 7.
- "Iceberg: tape min clip" — minimum fill size that qualifies as a clip (filters small-lot noise). No default value given.
- "Iceberg: tape min refills" — number of consecutive identical fills required to confirm an iceberg vs. coincidence. No default value given.
- Enable via "Iceberg: tape" in the Filters group (works on historical charts).
- Integrates with mzBigTrade: "Iceberg: min volume" filter, "Marker size relative to = Iceberg", iceberg map in Trades Volume Profile, pop-up info.
- Hard/Soft DOM-based algorithms require live or Market Replay data only.

## Order-flow signature described
Multiple identical-sized prints at one price within a single reconstructed trade (sweep). Defended level: price attacks the iceberg and is rejected — level likely matters on retest, especially if untested for a while. Defeated iceberg: reserve exhausted, level often flips roles and the winning side presses. Conviction: clusters of detections at one price across the session = repeated reloading by the same participant.

Limitations: algorithms randomizing display quantity leave no clip pattern; an iceberg consumed slowly by many small independent trades produces no run; thresholds filter but do not eliminate coincidence on very active instruments.

## Relevance to our research
Directly informs our iceberg/refill detection: the clip/refill signature is computable from our reconstructed NT8 tick footprint (same-size consecutive fills at one price within a sweep), and the (refills − 1) x clip-size floor gives a quantitative hidden-liquidity estimate for defended-level and level-touch outcome studies.
