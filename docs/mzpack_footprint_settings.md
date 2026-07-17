# mzFootprint — recommended settings, all 108 parameters (ES)

Companion to `mzpack_footprint_params.md` (the raw reflection dump). Purpose: the
level-touch / absorption research chart (ES, 14-Range or our volume bars, Ticks per
level 1). Every parameter below, grouped as in the properties window.

**Source legend** — how much to trust each value:
- **[A]** article-backed: published by MZpack for ES (POC Retest / Defended Levels /
  Mirror Levels, 2026).
- **[C]** convention: standard footprint practice, no MZpack-published number.
- **[V]** visual/taste: cosmetic only, any value is "correct".
- **[R]** our research rule: chosen to protect the study (e.g. keep vendor signals
  off so they can't bias the eye).

Calibration rule (theirs, verbatim): *if a known-good bar doesn't flag, lower
Filter first, then Absorption %.* If half the chart flags, raise Filter first.

## Absorption (the primary gate)

| Parameter | Set to | Src | Why |
|---|---|---|---|
| ShowAbsorption | ✔ true | A | the whole point |
| AbsorptionParams (slots #1–#5) | only **#2 Show ✔**; #1/#3/#4/#5 off | R | one calibrated tier; multi-tier later |
| AbsorptionPercentage (#2) | **100** | A | = 2:1 diagonal minimum |
| AbsorptionDepth (#2) | **8** | A | 8 ticks = 2 ES pts diagonal window |
| AbsorptionFilter (#2) | **80** | A | min contracts on absorbing side |
| ShowAbsorptionSRZones | ✔ true | A | absorption prints → persistent defended-level zones |
| AbsorptionSRZonesConsecutiveLevels | 2 | A | their default in the panel |
| AbsorptionSRZonesVolumeFilter | 0 | A | raise only if zones spam |
| AbsorptionSRZonesBreakOnSession | false | R | naked/prior-day zones matter (7/10 evidence) |
| AbsorptionSRZoneEnding | Break (default) | C | zone dies when traded through |
| AbsorptionSRZoneApproaching | 0 | R | no approach alerts |
| AbsorptionSRZoneAlert / OnBarClose / UseAbsorptionAlert / AbsorptionAlert | false / false / false / (empty) | R | no sounds; we read, not react |
| AbsorptionMinWidthPx | 0 | V | draw at any zoom |
| ShowOnlyAbsorption | false | V | keep full footprint visible |

## Imbalance (secondary confirmation)

| Parameter | Set to | Src | Why |
|---|---|---|---|
| ShowImbalance | ✔ true | C | core diagonal read |
| ImbalancePercentage | **200** | C | = 3:1 diagonal, the classic footprint convention (100=2:1, 300=4:1); no MZpack ES number published |
| ImbalanceFilter | **40** | C | min contracts per imbalance cell (~half the absorption filter; single-cell vs zone) |
| ImbalanceHighlightValues | ✔ true | V | bold the imbalanced cells |
| ImbalanceMarker / MarkerType / MarkerPosition | defaults | V | cosmetic |
| ImbalanceMarkerMinWidthPx | 0 | V | |
| ShowImbalanceSRZones | ✔ true | C | stacked imbalances → S/R zones (Mirror Levels uses these as the old zone being flipped) |
| ImbalanceSRZonesConsecutiveLevels | 2 | C | 2 stacked levels form a zone |
| ImbalanceSRZonesVolumeFilter | 0 | C | raise if spammy |
| ImbalanceSRZonesBreakOnSession | false | R | zones persist across sessions |
| ImbalanceSRZoneEnding | Break (default) | C | |
| ImbalanceSRZoneApproaching | 0 | R | |
| ImbalanceSRZoneAlert / OnBarClose / UseImbalanceAlert / ImbalanceAlert | all off | R | |
| ShowOnlyImbalance | false | V | |

## Statistics grid (the COT-flip confirmation layer)

| Parameter | Set to | Src | Why |
|---|---|---|---|
| StatisticGridShow | ✔ true | A | required for the confirmation reads |
| StatisticGridShowCOTHigh | ✔ true | A | resistance-in-numbers |
| StatisticGridShowCOTLow | ✔ true | A | support-in-numbers |
| StatisticGridShowDelta | ✔ true | A | |
| StatisticGridShowDeltaPercent | ✔ true | A | flip strength ("often >30%") |
| StatisticGridShowVolume | ✔ true | A | |
| StatisticGridShowDeltaRate | ✔ true | C | stop-run vs absorption separator (Delta Rate article) |
| StatisticGridShowDeltaCumulative | ✔ true | C | in-chart session CVD — matches our CVD work |
| StatisticGridShowMinDelta | false | V | grid width; delta+delta% suffice |
| StatisticGridShowBuyVolume / ShowSellVolume | false | V | redundant with delta+volume |
| StatisticGridShowTrades | false | V | |
| StatisticGridShowAbsoluteDeltaAverage | false | V | |
| StatisticGridShowArr | (driven by the toggles above) | — | |
| StatisticGridPredictedValuesShow / GaugeShow | false | R | intra-bar prediction invites impulse reads |
| StatisticGridInFront | ✔ true | V | readable over bars |
| StatisticGridAutoscaleValues | ✔ true | V | |
| StatisticGridCellScale | default | V | |
| StatisticGridValuesX1000 | ✔ true | V | "1.2K" style |
| StatisticGridValuesDivider | default (1) | V | |

## Bar statistics / in-bar display

| Parameter | Set to | Src | Why |
|---|---|---|---|
| ShowBarDelta | ✔ true | C | |
| ShowBarDeltaPercent | ✔ true | C | |
| ShowBarVolume | ✔ true | C | |
| ShowBarCOT | ✔ true | A | COT High/Low per bar — the Mirror-Levels read |
| ShowBarMinMaxDelta | ✔ true | C | in-bar delta excursion (effort trace) |
| ShowBarPOC | ✔ true | A | needed for the Footprint Reversal pattern |
| ShowBarPOCCount | **3** | A | "three merged POCs" is that pattern's condition |
| ShowBarVA | false | V | session VA is the one that matters; in-bar VA is clutter |
| BarVAPercentage | 70 | A | (inactive while ShowBarVA=false) |
| ShowBarMarker | default | V | |
| ShowBarRatioNumbers | false | V | ratio numbers duplicate imbalance highlighting |
| BarRatioNumbersBoundsHigh / Low | defaults | V | inactive |
| ShowBarAbsoluteDeltaAverage | false | V | |
| BarStatisticValuesX1000 | ✔ true | V | |
| BarStatisticValuesDivider | default (1) | V | |
| ShowUnfinishedAuction | false | R | separate concept; off until we test it |
| UnfinishedAuctionMinWidthPx | 0 | V | |

## Session profile / POC / VA

| Parameter | Set to | Src | Why |
|---|---|---|---|
| ShowSessionPOC | ✔ true | A | the level family we test |
| ShowSessionVA | ✔ true | A | VAH/VAL |
| SessionVAPercentage | **70** | A | standard VA |
| SessionPOCIsDeveloping | ✔ true | C | developing VPOC = our session-VP layer |
| SessionVAIsDeveloping | ✔ true | C | |
| SessionDailyProfileMode | **RTH_ETH** | A | their ES recommendation (POC Retest) |
| POCMinWidthPx | 0 | V | |

## Delta rate / divergence signals

| Parameter | Set to | Src | Why |
|---|---|---|---|
| DeltaRateOfChangeType | Milliseconds | C | time-window delta velocity |
| DeltaRateOfChangeValue | **1000** (ms) | C | 1-second burst window; no published number |
| DeltaRateOfChangeShowInBar | ✔ true | C | shows max |ΔD| + its price interval |
| DeltaDivergenceSignal_Enable | **false** | R | we pre-registered ONE divergence definition — the vendor's stays OFF so it can't bias the eye |
| DeltaDivergenceSignal_DeltaThreshold / VolumeThreshold | n/a (disabled) | R | |
| DeltaDivergenceSignal_Alert / Sound | false / (empty) | R | |

## Structure / filters / scaling

| Parameter | Set to | Src | Why |
|---|---|---|---|
| TicksPerLevel | **1** | A | no aggregation — all thresholds above assume it |
| TradeFilterMin | 0 | C | raw tape into the footprint; size-filtering happens in analysis, not display |
| TradeFilterMax | 0 | C | 0 = no cap |
| DisplayValueFilter | 0 | V | show all cell values |
| BidAskRelativeScaling | ✔ true | V | cell shading proportional within bar |
| AutoscaleValues | ✔ true | V | |
| OuterMargin | default | V | |

## Not in this list but REQUIRED (indicator-level / global)

- Calculation mode = **BidAsk** (futures) — [A]
- Orderflow settings → **Reconstruct tape: timestamps only** = on — [A] (historical/live consistency)
- Chart Data Series → **Tick Replay ✔** — [A] (else historical bars have no footprint)
- NT8 Tools→Options→Market data → Show Tick Replay ✔ · Enable market recording for playback ✔ (done 7/17)

## Honesty box

Only ~20 of the 108 have a published MZpack ES value [A]. ~25 are convention [C] —
defensible starting points, not truth; the two that actually change what flags are
**ImbalancePercentage (200)** and **ImbalanceFilter (40)** — calibrate them on known
bars exactly like the absorption pair. Everything tagged [V] is cosmetic. Everything
tagged [R] is deliberately OFF to keep vendor signals from contaminating the
pre-registered-hypothesis workflow.
