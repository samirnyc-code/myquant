---
title: Optimizing VolumeProfile and TPO Charts in MZpack
url: https://www.mzpack.pro/optimizing-volumeprofile-and-tpo-charts-in-mzpack/
date: 2020-10-28
topic: volume-profile-tpo
research_relevance: low
---
## Summary
A performance-tuning guide for running volume profile and TPO charts in NinjaTrader 8 without saturating CPU. NT8 processes only one CPU thread per instrument, so the article's workaround is a dual-data-series chart: a tick-replay series (5 days) for tick-accurate indicators (mzFootprint, mzBigTrade, mzVolumeDelta) and a non-tick-replay series (30 days) running mzVolumeProfile at "Minute" profile accuracy, which needs far fewer resources and loads much faster. Target result is roughly 1% CPU load.

## Key concepts & definitions
- NT8 threading constraint: "only one CPU thread per instrument" regardless of cores.
- Profile accuracy = Minute: builds volume/TPO profiles from minute data; "doesn't require tick replay mode, requires much fewer CPU resources, and has significantly less loading time." TPO works with Minute accuracy "even for very short periods like session."
- Dual data series pattern: heavy tick-replay series for footprint/order-flow, light minute-accuracy series for profiles; second series is sent to the same panel as the first.

## Rules / thresholds / settings
- Data series 1: Tick Replay ON, 5 days to load.
- Data series 2: Tick Replay OFF, 30 days to load ("we recommend using equal time periods for both data series").
- mzVolumeProfile: input = second series, Profile accuracy = Minute; example config: Weekly periodical profiles + Monthly profile as stacked VP.
- mzFootprint (and optionally mzBigTrade, mzVolumeDelta): on the tick-replay series.
- CPU load target: ~1%.

## Order-flow signature described
None — purely a platform/performance configuration article.

## Relevance to our research
General background. Mildly relevant confirmation that minute-resolution data is adequate for session VP/TPO (VPOC/VAH/VAL) construction while tick data is only needed for footprint-level signatures — matching our own pipeline split.
