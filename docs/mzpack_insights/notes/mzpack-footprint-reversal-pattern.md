---
title: MZpack Footprint Reversal Pattern
url: https://www.mzpack.pro/mzpack-footprint-reversal-pattern/
date: 2021-03-31
topic: footprint
research_relevance: high
---
## Summary
Defines a concrete footprint-based reversal setup (shown as a sell signal, with a mirrored buy variant) using the mzFootprint indicator on Range bars in NinjaTrader 8. The sell pattern is built from four in-bar conditions: a down-bar, a sell imbalance zone near the top of the bar, three merged POCs in the middle or upper half of the bar, and (optionally) sell delta rate at the top. The article stresses that the imbalance percentage and imbalance volume filter must be tuned per instrument, but gives no specific numbers.

## Key concepts & definitions
- Footprint Reversal Pattern: an order-flow reversal setup read from a single footprint bar's internal structure.
- Imbalance zone: a cluster of price levels with diagonal bid/ask imbalance (sell imbalance = aggressive selling dominant); its location within the bar matters (near the top for the sell signal).
- Merged POCs: three points of control merged/clustered together — POC clustering in the middle or higher half of the bar.
- Delta Rate: a per-level/per-zone delta intensity measure; "Sell Delta Rate at the top" is listed as an optional condition (article itself marks it "optional?").

## Rules / thresholds / settings
Sell signal conditions (exact, from article):
1. Down-bar
2. Sell Imbalance zone is near the top of the bar
3. Three merged POCs at the middle or higher half of the bar
4. Sell Delta Rate at the top (optional?)
Tunable per instrument (no values given): Imbalance percentage (%), Imbalance volume filter.
Requirements: mzFootprint, Range bar chart type, NinjaTrader 8, MZpack 3.16.2+.

## Order-flow signature described
A down range-bar whose footprint shows aggressive selling concentrated at the TOP of the bar (sell imbalance zone + sell delta rate up high) while volume acceptance (three merged POCs) sits mid-bar or higher — i.e., sellers were aggressive early/high but price built its volume structure above the low, implying the selling effort at the highs did not translate into acceptance lower.

## Relevance to our research
High relevance to effort-vs-result/absorption at extremes: the imbalance-at-one-end + POC-cluster-location logic is a codifiable bar-level signature we can implement in our reconstructed ES footprints and test at MQ level touches; the merged-POC condition also connects to our POC-retest work.
