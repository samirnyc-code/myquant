---
title: Defended Levels: Seeing Who is Holding the Price
url: https://www.mzpack.pro/defended-levels-seeing-who-is-holding-the-price/
date: 2026-07-06
topic: core-concepts
research_relevance: high
---
## Summary
Teaches how to identify who is defending a price level by combining footprint absorption zones (price axis) with mzBigTrade prints (time axis): "A level defended by a handful of small orders and a level defended by repeated 100-lot prints are not the same level." Gives three defense reads (big prints, icebergs, trades volume profile), a two-act defense mechanic (attack absorbed, then defender turns aggressive), two concrete mzBigTrade filter presets, and three timestamped case studies (a defended hold, an iceberg defense at a POC, and a broken level where iceberg defense failed with no initiative follow-through).

## Key concepts & definitions
- Defended level = absorption zone + identification of who executed there. "Absorption first; the prints tell you who, not whether."
- Three defense reads: (1) big prints — large trade clusters at S/R with price holding; (2) icebergs — hidden limit orders that refill while price stays static (Hard and Soft detection algorithms; live data or Market Replay only); (3) Trades Volume Profile — concentration map of filtered trades (set "Marker size relative to = Iceberg" for iceberg-defense mapping).
- Trade display format at iceberg defense: total / iceberg / DOM pressure / DOM support volumes.
- Defense unfolds in two acts: attack phase (aggressive size hits level, gets absorbed) then initiative phase (defending side turns aggressive, pushes price away).
- Critical distinction: "Size on the wrong side of absorption is the stop-run trap" — big prints penetrating a level indicate breakout, not defense.
- Defense scales conviction; it does not replace triggers. Hierarchy: context → level identification → absorption confirmation → grid confirmation.

## Rules / thresholds / settings
mzBigTrade Preset A (Intentional Size): Filters Type = Manual; Min volume = 20 lots; Volume is multiple of = 5; Aggression min ticks = 3.
mzBigTrade Preset B (Heavy Hands Only): Min volume = 50 lots; Trade marker = Box; extra filters off.
Common: Presentation Type = Default; Marker size relative to = Volume; Max trades in frame = 100; Trades Volume Profile: Show = on.
Entries: aggressive on close of the holding bar with stop beyond the level; conservative after 1-3 confirming bars.

## Order-flow signature described
Defended hold (case 1): 09:40:01 sell 86 lots at 7500.5-7500; 09:40:02 sell 71 lots at 7500.75-7500.25; cyan absorption fires (limit buyers eating); 09:40:03 buy 50 lots at 7500-7500.5; 09:40:05 buy 50 lots same prices → ~30-point rally; breakout buys of 647 and 503 lots at 7509.25-7511.
Iceberg defense (case 2, 6716 POC): 10:11:11 sell 95 lots at 6722.5-6722, format 95/34/32/0 (34 lots matched iceberg, 32 fresh bids added); 10:12:46 buy 6 lots at 6719.25, 6/0/-25/0 (25 lots of offers pulled); 10:12:58 sell 27 lots at 6719, 27/26/1/0 (iceberg eats 26 of 27).
Break (case 3, 6733 POC): buy 48 lots eaten 47/48 by sell iceberg; buy 32 lots eaten 31/32; but no initiative follows — buyers keep pressing and the level breaks. Absorption without the initiative phase is not enough.

## Relevance to our research
Directly maps to our defended-level and level-touch outcome studies: it operationalizes defense as absorption + large-print/iceberg identification + an initiative phase, and case 3 gives the key negative signature (absorption without follow-through initiative → break), a testable feature for our touch-outcome classifier.
