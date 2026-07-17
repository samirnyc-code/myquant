---
title: How to Create Custom Indicator Using MZpack API
url: https://www.mzpack.pro/how-to-create-custom-indicator-using-mzpack-api/
date: 2023-03-04
topic: platform-misc
research_relevance: low
---
## Summary
A brief announcement-style post noting that MZpack API users can build custom MZpack-based indicators. Technically, these are implemented as NinjaTrader strategies that behave like indicators: "you must enable your indicator-strategy from Strategies tab to get indicator work." Sample code ships with the MZpack Strategies package (MZpack_Pro_API_Samples.zip). The article itself contains no code, class/method names, step-by-step instructions, or parameters — it points to the User Guide and the samples for details.

## Key concepts & definitions
- MZpack API: lets users "create their own custom MZpack-based indicators."
- Indicator-strategy: custom tools are strategies enabled from the Strategies tab, not the Indicators section, even though they act like indicators.
- Resources: samples in the MZpack Strategies package; downloadable MZpack_Pro_API_Samples.zip; User Guide documentation.

## Rules / thresholds / settings
None given.

## Order-flow signature described
None given.

## Relevance to our research
General background; only relevant if we ever want programmatic access to MZpack's absorption/iceberg detections inside NT8 instead of our own reconstruction.
