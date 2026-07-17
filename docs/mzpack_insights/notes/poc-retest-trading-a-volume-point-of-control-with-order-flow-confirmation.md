---
title: POC Retest: trading a volume Point of Control with order-flow confirmation
url: https://www.mzpack.pro/poc-retest-trading-a-volume-point-of-control-with-order-flow-confirmation/
date: 2026-07-01
topic: volume-profile-tpo
research_relevance: high
---
## Summary
A full playbook for trading retests of a prior profile's untested (naked) POC with footprint confirmation. Structure is Level (naked POC from mzVolumeProfile) → Return (price reverts to it) → Decision (footprint says hold or break). Validation hierarchy: absorption is the primary gate; COT flip (COT Low/High, Delta %) is secondary directional confirmation; POC prominence and defending zone volume are tertiary conviction gradients. Includes aggressive/conservative entry rules, a "reclaim" failed-breakdown pattern, a context gate, and exact mzVolumeProfile/mzFootprint settings with calibration guidance.

## Key concepts & definitions
- POC: "the price where the most volume traded inside a profile" — the market's fair-value anchor.
- Naked POC: a POC price not revisited since formation; stronger magnetic pull ("unfinished business").
- Absorption: "a diagonal imbalance with level rejection: aggressive market orders hit the POC, limit orders eat them, and price bounces." Absorption fires = defended = bounce candidate; no absorption = level is spent.
- COT flip (long/support retest): COT Low turns positive and sustains across multiple bars; COT High collapses toward zero; Delta % expands well past single-digit noise. Invert all signs for a short.
- "The defence holding for more than one bar is confirmation, not a precondition."
- Conviction gradients (not gates): POC prominence in its profile (sharp single peak > flat/double distribution); zone-volume gradient of the footprint defending the retest.
- Reclaim (failed breakdown): price breaks below POC into an absorption zone beneath, floor holds, next bar closes back above the POC — confirmation rests on the close location.
- Context gate: cleaner when price returns to the POC from outside the value area after a directional move, not while chopping inside value.

## Rules / thresholds / settings
mzVolumeProfile: Profile mode = RTH_ETH or Session (Daily for Forex); POC mode = Naked (Extended also viable); VA % = 70; Profile Statistics: POC on.
mzFootprint: Absorption = enabled (primary filter); Absorption % = 100 (imbalance side minimum 2:1 ratio); Depth = 8 levels (8 ticks = 2 pts ES at Ticks per level = 1); Filter = 80 (minimum contracts on absorbing side); Ticks per level = 1 (no aggregation); Grid display: COT High, COT Low, Delta, Delta %, Volume, Volume/sec.
Entries — aggressive: close of the bar holding the POC with absorption fired AND positive COT Low on that bar; stop just beyond the POC (below it for a long). Conservative: wait 1-3 bars; COT Low stays positive, COT High doesn't turn negative; enter on close of confirming bar.
Calibration: "If a known good bar does not flag, lower Filter first, then Absorption %."
Template: poc-retest-ES-14-Range-v1.xml (ES 14 Range chart).

## Order-flow signature described
At a holding POC: aggressive sells hit the level, diagonal imbalance with the limit side eating them (absorption fires), price rejects; COT Low positive and sustained, COT High near zero, Delta % expanding past single digits. Spent POC: price trades straight through with no absorption. Reclaim: break below, absorption floor holds beneath, close back above the POC.

## Relevance to our research
This is the most directly transferable article for our MQ/VP level-touch outcome study: concrete, numeric absorption gate (Absorption % 100 = 2:1 diagonal, Filter 80 contracts, depth 8 ticks on ES) plus a COT-flip confirmation layer we can approximate with our reconstructed footprint and CVD around POC/VAH/VAL touches.
