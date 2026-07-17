---
title: Mirror Levels: Trading Order-Flow Polarity Flips on the Footprint
url: https://www.mzpack.pro/mirror-levels-trading-order-flow-polarity-flips-on-the-footprin/
date: 2026-06-25
topic: core-concepts
research_relevance: high
---
## Summary
Defines a Mirror Level: broken resistance becoming support at the same price, confirmed when a fresh Support zone (buy imbalances) prints on top of an old Resistance zone with no gap. Validation is layered: absorption is the primary filter ("what actually separates a mirror from a breakout"), COT flip (COT High collapsing, COT Low positive and sustained, Delta % expanding often above 30%) confirms direction and holding, and zone volume is only a conviction gradient. Four numeric case studies show two valid mirrors (including a "silent delta" bar) and two false mirrors (one-bar flip and stop run), each with exact grid values.

## Key concepts & definitions
- Mirror Level: "broken resistance becomes support" at the same price. Three sequential elements: Context (sharp directional move creating sell-imbalance Resistance zones), Return (price bases and comes back), Flip (fresh Support zone prints at the same price, "no gap between them").
- Absorption: "a diagonal imbalance with level rejection: aggressive market orders hit the level, limit orders eat them, and price bounces instead of pushing through." If absorption doesn't fire, "that is a breakout or a stop run, not a mirror, no matter how large the delta or the zone volume looks."
- COT High (negative): "after the high was made, net selling followed... Resistance in numbers." COT Low (positive): "after the low was made, net buying followed... Support in numbers."
- Genuine flip: COT High collapses toward zero; COT Low turns positive and stays there across more than one bar; Delta picks a side and holds across consecutive bars; Delta % expands well past single-digit chop, often above 30%.
- Stop-run caution: COT Low "should be a meaningful share of delta, not almost all of it" — nearly all delta made off the low in one burst with a Vol/sec spike = stop run through the level.
- Silent delta case: a bar with zero delta, zero Delta %, flat COT can still be a valid mirror if absorption fired and the bar sits on the level; "balanced delta on a short, high-Vol/sec bar is itself an absorption signature."
- Zone volume = conviction gradient, not a hard line; a thin zone that holds with absorption and a sustained flip is still valid.
- Shorts: invert every sign (prior move up, old Support flipping to Resistance).

## Rules / thresholds / settings
- Delta % on genuine flips "often above 30%" (gradient, not hard threshold).
- Entries — aggressive: on the close of the flip bar, given absorption fired and positive COT Low on that bar. Conservative: wait the next 1-3 bars; COT Low stays positive, COT High not negative.
- Stop: "below the zone, or at most below the low of the bar that made it."
- mzFootprint Statistics Grid: show COT High, COT Low, Delta, Delta %, Volume, Volume per second.
- Zones: enable S/R zones; configure "consecutive levels", "volume filter", and "ended by" for the instrument; keep Absorption enabled. (No default values given.)

## Order-flow signature described
Case 1 (valid, silent delta): Volume 846, Delta 0, Delta % 0, COT High 0, COT Low -13, Vol/sec 101 (elevated), bar ~8 seconds; level held, price ran up.
Case 2 (valid, thin zone): zone 88 contracts; subsequent bars Delta 188/84/169/138, Delta % 33.8/16.5/42.8/21.6, COT Low 150/71/153/148/131; held.
Case 3 (false, one-bar flip): Volume 215, Delta +97, Delta % 45.1, COT High 0, COT Low +98, zone 33 contracts; next bar Volume 646, Delta +8, Delta % 1.2, COT High -82; no absorption; failed.
Case 4 (false, stop run): Volume 1.9K, Delta +962, Delta % 49.5, COT Low +709 (~three-quarters of delta), zone ~1,000 lots (thick), Vol/sec 392.8 vs neighbors ~145; no absorption; price broke through.
Principle: "Absorption-first rejects both before you enter; the grid and zone volume only explain how each one baited you."

## Relevance to our research
High-value for absorption-at-extremes and level-flip studies: it gives concrete false-positive signatures we can encode — delta concentrated off the extreme (>~70% of bar delta) with a Vol/sec spike = stop run, not defense — and validates that high-volume/zero-delta no-progress bars (effort vs. result) are themselves absorption evidence.
