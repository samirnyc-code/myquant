# NT8 Simulator Architecture
**Status:** Architecture — Stable  
**Last Updated:** June 2, 2026  
**Source of truth for:** NT8 sim, CSV schema, Sheets pipeline, MCChartMarker

---

## Current Versions

| Component | Version | Notes |
|-----------|---------|-------|
| NT8 Simulator | SIM_v3.3 | Multi-leg, OnBarClose, PB66 + EB stop |
| Apps Script | GS_v4.5 | ETH bucket, pre-filters, export fixes |
| Google Sheet | SHEET_v3.3 | |

---

## Version Naming Convention

```
SIM_v[major].[minor]    — NinjaScript simulator (.cs file)
GS_v[major].[minor]     — Google Apps Script (.gs file)
SHEET_v[major].[minor]  — Google Sheets file (named in version history)
```

- Increment minor for bug fixes, new properties, small changes
- Increment major for schema changes, new setup type, architectural changes
- Always increment SIM version when CSV schema changes
- Apps Script is NOT saved in Sheet version history — back up `.gs` manually
- Never rename a bound script file — creates a second unbound script

---

## Files

| File | Location |
|------|----------|
| `MCSimulatorV5_5.cs` | NT8 strategy, runs sim, exports CSV |
| `MainCodeV4.5.gs` | Google Apps Script, all Sheets logic |
| `NT8_NinjaScript_LessonsLearned.md` | NT8/SharpDX coding lessons |
| `MultiYear_MASTER_Architecture.md` | Planned multi-year MASTER tab architecture |

---

## Pipeline Architecture

```
NT8 sim (MCSimulatorV5_5.cs)
        |
        v
MCSimulator*.csv → G:\My Drive\MCVolumeExport\
        |
        v
Sheets: RAW_IMPORT → buildMaster → MASTER tab
        |
        v
ANALYSIS / FILTER_OPTIMIZER / SAVED_RUNS
```

---

## Tab Structure

| Tab | Purpose |
|-----|---------|
| `SETTINGS` | Constants, version tracking, last import info |
| `RAW_IMPORT` | Raw CSV data, never modified by script |
| `MASTER` | Processed data with derived columns |
| `COLUMN_MAP` | Column definitions for SIM and DERIVED columns |
| `ANALYSIS` | Filters + metrics + breakdowns |
| `SAVED_RUNS` | Transposed comparison of saved runs |
| `VERSION_REGISTRY` | Run history log |
| `FILTER_OPTIMIZER` | Combinatorial filter sweep |
| `OPTIMIZER_INDEX` | Saved optimizer run registry |

---

## CSV Schema (SIM_v3.3)

- One row per leg (not per position). Position has up to 5 legs (P1-P5)
- PositionID format: `yyyyMMdd_HHmmss_N`
- Date format: `yyyy-MM-dd`, Time format: `HH:mm:ss`
- 313 columns total

**Key position-level columns:**
`PositionID, SignalDate, SignalTime, Direction, CCCount, IsBTCSignal, StopDistPts, PositionNetPnlD, PositionMFE_R, PositionMAE_R, PositionExitR, PositionTotalRisk, FreeMaxR, FreeMAE_BeforeFreeMax`

**Key leg-level columns:**
`PNumber, EntryLevel, Contracts, StopMode, Filled, EntryPrice, StopPrice, EBStopPrice, ExitType, ExitPrice, GrossPnlD, NetPnlD, LegPnlR`

**R-level columns:** 0.5R through 20.0R × Hit/Time/Bar (both actual and free-running)

---

## MASTER Derived Columns

| Column | Derivation |
|--------|------------|
| Date | SignalDate string yyyy-MM-dd |
| DOW | Mon/Tue/Wed/Thu/Fri/Sat/Sun from SignalDate |
| Time of Day | TOD bucket from SignalTime |
| First Trade Of Day | Y/N — first position per date |

---

## TOD Buckets (current)

| Internal value | Display | Time range |
|----------------|---------|------------|
| `Early_830_1100` | Early | 08:30 – 11:00 |
| `Lunch_1100_1300` | Lunch | 11:00 – 13:00 |
| `Late_1300_1515` | Late | 13:00 – 15:15 |
| `ETH_1515_830` | ETH Full | 15:15 – 08:30 |

Boundary logic (minutes from midnight):
- Early: 510 ≤ mins < 660
- Lunch: 660 ≤ mins < 780
- Late: 780 ≤ mins < 915
- ETH Full: everything else

**Note:** Sim must be constrained to RTH via NT8 trading hours template. ETH Full bucket exists because sim accidentally ran on ETH in a prior session.

**Planned:** 13 × 30-min buckets (08:30–15:15) — deferred until Python migration.

---

## FILTER OPTIMIZER

**Config block (rows 2-4, cols B-I):**
- Stop Dist Min/Max, Step Size
- Min Trade Count (n), Top N
- Min Net PnL, Min PF, Min Exp R
- CC Max Excl, DOW Max Excl, TOD Max Excl (all default to 0)
- First Trade Only (col G row 3)

**Pre-filter block (cols K-W, rows 1-7):**
- DOW checkboxes K4:O4
- TOD checkboxes K7:N7
- CC checkboxes Q4:U4
- Direction checkboxes V4:W4

**Sweep dimensions:** DOW × TOD × Direction × CC × Stop pairs

**Output:** row 10 onward, 18 columns, sorted Net PnL desc

---

## Export to NT8

**Files exported to `G:\My Drive\MCVolumeExport\`:**
- `optimizer_signals_ES_5M_YYYY-MM-DD_YYYY-MM-DD_N.csv`
- `optimizer_config_ES_5M_YYYY-MM-DD_YYYY-MM-DD_N.json`

**Workflow:** Run Optimizer → mark rows with X in col A → Export to NT8 → THEN Save Optimizer Tab
**Critical:** Export before saving — saveOptimizerTab shows alert warning.

---

## MCChartMarker Indicator (V1.0)

**File:** `MCChartMarker.cs`
**Purpose:** Paints background bands on chart bars matching optimizer signal times

**Properties per slot (5 slots):**
- `SlotN Enabled` — bool toggle
- `SlotN File` — full Windows path to signal CSV (no quotes)
- `SlotN Color` — color picker
- `Band Opacity (%)` — default 30

**Signal matching:** `HashSet<DateTime>` keyed on SignalDate + SignalTime, matched against `ChartBars.GetTimeByBarIdx()` on bar close

**Known issues:**
- File loaded at `State.DataLoaded` only — changing file path requires removing and re-adding indicator
- Path must not include surrounding quotes

**Planned:** Custom vertical panel showing all 5 slots with full metrics from config JSON

---

## ANALYSIS Tab

**Filters:** Direction, CC Count (1-5), DOW (Mon-Fri), TOD (4 buckets), Stop Dist Min/Max
**Results panel:** cols H-I, 23 metrics
**Breakdowns:** TOD, DOW, Monthly, TOD Matrix, Exit Target Matrix (Actual + Free Run)

**Known issue:** `saveRun` still uses old TOD labels `['Early','Mid','Late','End']` — update to `['Early','Lunch','Late','ETH Full']`

---

## NT8 Signal Logic (locked — do not change without explicit instruction)

- `Calculate = OnBarClose`
- Signal: first bar where `MC_Bull_Strong[1] > 0 && MC_Bull_Strong[2] == 0`
- CC type via indicator properties (Show3CC, Show4CC etc.)
- Session exit via `SessionIterator.ActualSessionEnd`
- Entry: `Close[1] + EntryOffsetTicks * TickSize`
- Stop: `MCLow - StopOffsetTicks * TickSize`
- Multiple simultaneous positions allowed (one per MC signal)
