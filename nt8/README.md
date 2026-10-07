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
| `FootprintExporter.cs` | Reconstructed bid/ask footprint + delta from ticks (Tick Replay) to CSV | ❌ REMOVED (S120) — superseded by L1TapeRecorderAddOn (footprint reconstructable from the L1 tape offline); restore from git if a live CSV export is needed again. `MzFootprintExtractor.cs` removed with it. |
| `WedgeExporter.cs` | Hosts black-box `MyWedge` and exports every signal bar (`WedgeBLSB`/`WedgeBRSB` > 0; BL=long, BR=short) to CSV over full history — feeds the 2000t stop/target (MAE/MFE) study. Compiled OK S107 | ✅ current |
| `DtDbScanner.cs` | Double Top / Double Bottom structure scanner for tick charts; auto-reads chart's tick interval, detects/scores DT/DB setups, alerts on form + neckline confirm. Manual execution. Pulled from external repo `samirnyc-code/nt8-dtdb-scanner` (S125); fixed two expression-bodied methods (`=>`) NT8's compiler rejected | ✅ current |
| `SessionSRLevelsV6.cs` | RTH + ETH session S/R levels — HOY/LOY/COY (prior-session H/L/C) + OoD/OoW/OoM (open of day/week/month), 12 independently stylable levels, 2 Chart Trader toggle buttons (RTH/ETH). Session timing read from NT8's own CME Trading Hours templates (SessionIterator + `TradingHours.Get("CME US Index Futures RTH")`) so half-days/holidays are correct without reimplementing the calendar. Needs F5 half-day check — not yet verified live. | ⚠ untested (F5 pending) |
| `PriorWeekOHLCV3.cs` | Prior-week O/H/L/C as HLine plots + on-chart labels (OoLW/HoLW/LoLW/CoLW). Originally NT8 stock, previously hand-edited by the 2nd-PC collaborator ("TDEU" comments); allowed Daily bars via loosened guard, then V2 replaced the native HLine AddPlot rendering (drew edge-to-edge into empty future space) with a custom SharpDX ray-to-current-bar+1 render, same pattern as SessionSRLevelsV5 (centered labels, per-level color/opacity/style/thickness, optional price in label). Needs F5 check. | ⚠ untested (F5 pending) |
| `ZerolagExporter.cs` | Exports ZLO state to CSV for BA overlay (S31) | ❌ LOST — not committed |
| `AlwaysIn.cs` | Exports AlwaysIn regime state to CSV (S36) | ❌ LOST — not committed |
| `QSSignalOverlay.cs` | Overlays Python-generated QS signals on chart (S41) | ❌ LOST — not committed |

### strategies/

| File | Purpose | Status |
|------|---------|--------|
| `ClaudeTracker.cs` | Trade lifecycle tracker — logs every fill/stop/target event | ✅ current — re-synced from Custom folder 2026-10-01, had drifted from what's actually deployed |
| `ClaudeTrackerV2.cs` | ClaudeTracker + per-trade subfolder output (`EnsureTradeFolder`) — this is the version actually producing real output on disk. Feeds the Trade Playbook journal via `scripts/journal_uploader.py` (separate repo). Was UNCOMMITTED until 2026-10-01 (found only in the NT8 Custom folder) — no account/Sim-vs-Live tagging yet, see trade-playbook's `docs/journal-plan.md`. | ✅ current |
| `TradeLifecycle.cs` | Trade lifecycle utilities | ✅ current |
| `MCStrategyDashboardV3.cs` | MC strategy dashboard | ✅ current |
| `BreakoutBoysDashboardV1.cs` | Custom on-chart button panel for manual entries — SEL/SES stop-entry buttons, Cancel, Flat, Long/Short master toggles, stop-mode switch; submits via an ATM template (currently "Scalp & Run 2C BE 5t") for stop/target management. Order names use the PB33/PB50/PB66/BO/BBSA convention that ClaudeTrackerV2 special-cases. This is the actual panel used to enter trades — not a native NT8 ATM. | ✅ current |
| `WedgeScalper.cs` | MyWedge signal-bar scalper (stop entry 1t beyond SB, +4t scalp, runner BE→trail). Superseded by V2. | ✅ current |
| `WedgeScalperV2.cs` | WedgeScalper renamed + S107 fixes (single sized entry, all-manual exits, immediate stop on fill via OnExecutionUpdate, no re-scalp, entry auto-expire, hard safety net, qty=0 disables a lot). Has dated change-log header. | ✅ current |
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
