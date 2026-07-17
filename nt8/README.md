# NinjaTrader 8 — NinjaScript Files

All NT8 NinjaScript code (.cs) lives here. **Every file written or modified must be
committed to this folder — no exceptions.** The prior pattern of leaving CS files only
on the NT8 machine caused permanent loss of several indicators and strategies.

## Structure

```
nt8/
  indicators/          ← NT8 Indicators (compiled as indicators in NT8)
  strategies/          ← NT8 Strategies and AddOns
  third_party/         ← Unmodified third-party code (reference only; do not modify)
```

## Files

### indicators/

| File | Purpose | Status |
|------|---------|--------|
| `MyOHLCReader.cs` | Exports 5M OHLCV bars to CSV for Python pipeline | ✅ current |
| `ETHLevelsExporter.cs` | Exports ETH session levels | ✅ current |
| `PAI_BarStrength_V1_NoLegs.cs` | PAI bar strength indicator | ✅ current |
| `MyChartReader.cs` | Chart reading utility | ✅ current |
| `AMASignalOverlay.cs` | Overlays Python-generated AMA Breakouts signals on chart (S42) | ✅ current |
| `MyStochasticsColorwithSignal.cs` | Stochastic %K/%D with OB/OS zone + filtered reversal-bar coloring (source indicator) | ✅ current |
| `MyStochasticExporter.cs` | Exports per-bar %K/%D + zone/reversal signals to CSV for BA stochastic overlay (S50) | ✅ current |
| `FootprintExporter.cs` | Reconstructs bid/ask footprint + delta from ticks (Tick Replay) to CSV — free order-flow, no MzPack. Fallback/validation vs a paid MzPack `StrategyFootprintIndicator` extractor (S75) | ✅ current |
| `ZerolagExporter.cs` | Exports ZLO state to CSV for BA overlay (S31) | ❌ LOST — not committed |
| `AlwaysIn.cs` | Exports AlwaysIn regime state to CSV (S36) | ❌ LOST — not committed |
| `QSSignalOverlay.cs` | Overlays Python-generated QS signals on chart (S41) | ❌ LOST — not committed |

### strategies/

| File | Purpose | Status |
|------|---------|--------|
| `ClaudeTracker.cs` | Trade lifecycle tracker — logs every fill/stop/target event | ✅ current |
| `TradeLifecycle.cs` | Trade lifecycle utilities | ✅ current |
| `MCStrategyDashboardV3.cs` | MC strategy dashboard | ✅ current |
| `MCBreakout.cs` | MC breakout strategy (pyramiding + ratchet-lock, S32) | ❌ LOST — not committed |

### third_party/

| File | Purpose |
|------|---------|
| `AMABreakoutsPB6.cs` | Ali Moin-Afshari's AMA Breakouts PB Ver 6 (source reference for Python port) |
| `AmaBreakouts6.11/` | Full Ver 6.11 package (includes @SMA, @StdDev dependencies) |

## ❌ Lost files

Three indicator/strategy files were written and compiled in NT8 but never committed.
They need to be recreated:

1. **`ZerolagExporter.cs`** (S31) — exports `MCVolumeExport/ZLO_State.csv` with columns
   `BarTime, BaseTrend, TrendState, Oscillator`. Wired into BA overlay.

2. **`AlwaysIn.cs`** (S36) — exports `MCVolumeExport/AlwaysIn_State.csv` with columns
   `Event, BarTime, BarNum, NewDir, O, H, L, C, EmaFast, Mid, ZScore`.

3. **`QSSignalOverlay.cs`** (S41) — reads `qs_signals_{tag}.csv` from the NT8 user
   directory, overlays Python-generated QS breakout signals on the chart. Format:
   `DateTime(yyyyMMdd HHmmss), Dir(L/S), Type, Status, Price, Stop, BarNum`.

4. **`MCBreakout.cs`** (S32) — MC breakout strategy with pyramiding (N concurrent/dir)
   and ratchet-lock fix. Was in NT8 Indicators folder.

## Workflow rule

1. Write or modify a CS file → save it in `nt8/indicators/` or `nt8/strategies/`
2. Copy to NT8 machine for compilation (or develop directly in the NT8 editor and copy back)
3. Commit immediately — never leave a CS file only on the NT8 machine

## Naming convention for signal overlay indicators

Python-generated signal overlays follow the pattern `{Source}SignalOverlay.cs`:
- `QSSignalOverlay.cs` — QS breakout signals
- `AMASignalOverlay.cs` — AMA breakout signals (to be built)
