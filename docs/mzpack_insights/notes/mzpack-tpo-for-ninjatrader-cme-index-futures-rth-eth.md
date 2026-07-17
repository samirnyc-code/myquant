---
title: MZpack TPO for NinjaTrader – CME Index Futures RTH – ETH
url: https://www.mzpack.pro/mzpack-tpo-for-ninjatrader-cme-index-futures-rth-eth/
date: 2019-08-21
topic: volume-profile-tpo
research_relevance: low
---
## Summary
A configuration guide for splitting CME index futures into separate RTH and ETH sessions for TPO/volume-profile analysis in NinjaTrader 8 with mzVolumeProfile. The method: install a provided Trading Hours template into the NT8 templates folder, set the system time zone to UTC-6, restart NinjaTrader, and open the pre-installed workspace "MZpack – TPO – CME Index Futures RTH – ETH". The key indicator setting is Chart Profile mode = Session so profiles reset per defined session.

## Key concepts & definitions
- RTH / ETH: Regular vs Electronic (overnight) trading hours, treated as separate sessions so each builds its own TPO/volume profile.
- Chart Profile mode = Session: mzVolumeProfile setting that builds one profile per trading-hours session.

## Rules / thresholds / settings
- MZpack 3.14.6 (mzVolumeProfile) or later required.
- Time zone: UTC-6.
- mzVolumeProfile "Common – Chart Profile mode" = "Session".
- Steps: install Trading Hours template file → set UTC-6 → restart NT8 → open workspace.
No trading thresholds given.

## Order-flow signature described
None — configuration-only article.

## Relevance to our research
General background; only reinforces that session VP references (VPOC/VAH/VAL) for ES should be computed on an RTH/ETH session split, which our session-profile code already respects.
