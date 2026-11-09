# HighVolumePivot

For: Thomas
Date: 2026-11-09
Version: v1.1
Platform: NinjaTrader 8 (NinjaScript indicator)
File in repo: `nt8/indicators/HighVolumePivot.cs`
Source: NT8 port of the MQL5 "High-Volume Pivot" indicator (mql5.com/en/articles/24820)

## Premise

Most volume spikes aren't meaningful — they're just noise relative to how much volume
normally trades at that time of day. This indicator flags pivot highs and lows that
formed on volume that was abnormally high *relative to recent history*, not relative to
a fixed number. It compares each bar's trailing volume against a rolling 95th-percentile
reference, separately for regular trading hours (RTH) and overnight/electronic hours
(ETH), since the two have structurally different volume levels and blending them would
skew the threshold.

Visualization only — no entries, exits, or position management.

## What it does

1. **Pivot detection** — a bar is a pivot high/low if it's the most extreme high/low
   among a configurable number of bars to its left and right (confirmed a few bars
   after it forms, not in real time).
2. **Volume filter** — the pivot is only drawn if its trailing volume score clears a
   minimum threshold (see "The volume score" below). Most pivots on the chart fail this
   filter and are never drawn at all.
3. **Marker** — a dot (regular pivot) or diamond (outlier pivot, see below) at the pivot
   price.
4. **Volume label** — text showing the pivot bar's volume and/or its volume score.
5. **ATR rings** — concentric ellipses around the pivot, scaled by ATR(500), with the
   ring count driven by how high the volume score is. Purely visual/stylistic from the
   original MQL5 indicator.
6. **Reaction level** — a horizontal line projected forward from the pivot price. It
   stays solid while the level is "live," then switches to dotted once price breaks
   through it (see "Level break logic" below).

## The volume score (core concept)

```text
volume score = 5 x (trailing volume sum / 95th-percentile reference)
```

- **Trailing volume sum** = sum of `Volume` over the last `2 x Left Bars` bars, ending
  at the current bar.
- **95th-percentile reference** = the 95th percentile (nearest-rank) of that trailing
  sum across the last 1000 bars — tracked as **two separate rolling histories**, one
  fed only by RTH bars and one only by ETH bars (see "RTH/ETH session" below). Each
  bar's score is compared against whichever reference matches its own session.

A score of exactly 5.0 means today's trailing volume sum equals the historical
95th-percentile level for that session.

- A pivot is **drawn at all** only when `score > Filter Volume`.
- A pivot is marked an **outlier** (diamond marker, bold magenta label by default) when
  `score >= Filter Volume x Outlier Multiplier`. With the default settings
  (2.0 x 2.5 = 5.0), outlier means the volume genuinely reached the historical
  95th-percentile level, not just the minimum confirmation bar.

## RTH/ETH session

RTH and ETH volume regimes are different enough that mixing them into one rolling
reference would skew the threshold for whichever regime is less represented in the
trailing window. Each bar is classified RTH or ETH by its exchange-time clock position,
and each regime gets its own independent 1000-bar percentile history.

- Bar time is converted from NinjaTrader's display timezone into the configured
  exchange timezone (`Timezone Id`, default "Central Standard Time" = Chicago) before
  the RTH window is applied — this is DST-safe: .NET's `TimeZoneInfo` handles the
  CST/CDT (winter/summer) switch automatically, so the window stays correct at both
  boundary bars and year-round.
- Default window: RTH 08:30–15:15 Chicago time (CME ES's standard RTH session).

## Level break logic

The original/simple behavior (price closing once beyond the level) can get fooled by a
double-top/double-bottom: price briefly pokes through, then reverses, and the level
gets marked "broken" even though nothing really changed. `Break Mode` offers three ways
to confirm a break:

| Mode | Confirms when | Resets if |
| --- | --- | --- |
| `SingleClose` (default) | First close beyond the level | — (instant, original behavior) |
| `NClosesBeyond` | N *consecutive* closes beyond the level | Any single close back on the original side |
| `AtrDistance` | Price closes at least N x ATR(500) beyond the level | Any single close back on the original side |

`SingleClose` is the default so existing charts don't change behavior until `Break
Mode` is switched deliberately. `AtrDistance` is the timeframe-agnostic option — it's
measured in price/volatility terms, not bar count, so it behaves consistently whether
the chart is tick bars, a daily chart, or anything in between.

## Settings reference

### Parameters

| Setting | Default | What it does |
| --- | --- | --- |
| Left Bars | 15 | Bars to the left checked for the local-extreme pivot test; also sets the trailing volume window (2 x Left Bars). |
| Right Bars | 15 | Bars to the right checked for the local-extreme test, and the confirmation delay — a pivot only appears this many bars after it actually formed. |
| Display Bars | 300 | Pivots older than this many bars back are no longer drawn or tracked. |
| Filter Volume | 2.0 | Minimum volume score required to draw a pivot at all. |
| Show Pivot Dots | On | Toggles the regular (non-outlier) dot marker. |
| Show Rings | On | Toggles the ATR-scaled rings — when off, they are not drawn AND not calculated at all. |
| Ring Step | 1.0 | One ring is drawn per this much volume score above the filter threshold. |
| Show Levels | On | Toggles the reaction-level line. |
| Show Volume Label | On | Toggles the per-pivot text label. |
| Multiplier Only | Off | When on, the label shows only the volume score (e.g. "5.3x") instead of volume + score. |
| Outlier Multiplier | 2.5 | Outlier threshold = Filter Volume x this value. Default (2.0 x 2.5 = 5.0) means outlier = volume at the historical 95th percentile. |
| Show Outlier Markers | On | Toggles the outlier diamond marker. |
| Upper Color (Pivot High) | Orange | Marker/ring/level color for pivot highs. |
| Lower Color (Pivot Low) | Teal | Marker/ring/level color for pivot lows. |
| Label Color | Blue | Text color for non-outlier volume labels. |
| Outlier Color | Magenta | Marker, level-line, and label color for outlier pivots. |

### RTH/ETH Session

| Setting | Default | What it does |
| --- | --- | --- |
| RTH Start (HHmm) | 830 | Exchange-time RTH open (08:30). |
| RTH End (HHmm) | 1515 | Exchange-time RTH close (15:15). |
| Timezone Id (Windows) | Central Standard Time | Windows timezone id the RTH window is defined in; auto-handles CST/CDT. |

### Level Break

| Setting | Default | What it does |
| --- | --- | --- |
| Break Mode | SingleClose | SingleClose / NClosesBeyond / AtrDistance — see "Level break logic" above. |
| Closes Required | 2 | `NClosesBeyond` mode only: consecutive closes beyond the level required to confirm. |
| Break ATR Multiple | 0.25 | `AtrDistance` mode only: price must close this many x ATR(500) beyond the level to confirm. |

## Notes

- Core volume-score formula, percentile method, and ring geometry were checked
  line-by-line against the original MQL5 source article.
- `Left Bars`, `Right Bars`, `Step`, and the `Filter Volume` default (2.0) match the
  original indicator's defaults.
- The "real volume vs. tick volume" toggle present in the MT5 original was removed in
  this port — NinjaTrader's `Volume` series is already real traded volume for futures
  feeds that report it (including ES), so there's no separate series to switch to the
  way MT5 needs for feeds that only report tick volume.
