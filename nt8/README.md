# NinjaTrader 8 — NinjaScript Files

All NT8 NinjaScript code (.cs) lives here. **Every file written or modified must be
committed to this folder — no exceptions.** The prior pattern of leaving CS files only
on the NT8 machine caused permanent loss of several indicators and strategies.

## Structure

```
nt8/
  indicators/          ← NT8 Indicators (compiled as indicators in NT8)
  strategies/          ← NT8 Strategies
  addons/              ← NT8 AddOns (no enable step, run automatically on NT8 startup)
  third_party/         ← Unmodified third-party code (reference only; do not modify)
```

## Files

### indicators/

**NT8-side grouping (2026-10-18):** on the deployed NT8 machine (not in this repo's flat
layout), `SessionSRLevelsV9.cs`, `SessionSRLevelsV10.cs`, `BidAskVolumeRatio.cs`,
`BidAskVolumeDelta.cs`, `BidAskVolumeSplit.cs`, `RegimeTracker.cs`, `RegimeTrackerV2.cs`,
`RegimeTrackerBox.cs`, `RegimeTrackerPanel.cs`, `Regime2ESetups.cs`, `RegimePhaseMachine.cs`,
`DtDbScanner.cs`, `DtDbScannerV2.cs`, and `DtDbScannerV3.cs` were moved into a
`Custom\Indicators\!Samir's Indis\` subfolder
(the `!` forces it to sort first in NT8's Indicators dialog) so they group together at
the top of the indicator list, separate from everything else in `Custom\Indicators\`.
Subfolder location is NT8 UI organization only — NT8 compiles the whole `Custom\` tree
recursively regardless of nesting, so this has no effect on compilation. `SessionSRLevelsV10.cs`
deliberately does NOT redeclare the shared `LevelLineStyle` enum and requires
`SessionSRLevelsV9.cs` to stay present somewhere under `Custom\` (both now live together
in this same subfolder, so that constraint still holds).

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
| `DtDbScannerV3.cs` | DtDbScannerV2 (Hide/Show-synced drawings) with re-weighted quality score: 15% symmetry, 20% depth, 15% time symmetry, **50% trend context** (V1/V2: 35/25/15/25). User decision 2026-10-02. 2026-10-08: chart label drops the tick interval and sits 10t (was 6t) off price; swing ties resolved like NT8 built-in Swing (earlier of two equal highs/lows is the pivot); DT/DB pairing looks back through all earlier pivots within MaxBarsBetween (not just the previous one). Pre-look-back rollback copy: `indicators/rollback/DtDbScannerV3_2026-10-08_pre-lookback.cs.bak`. User compiled (F5) OK 2026-10-08. 2026-10-12: optional ABR sizing (peak tolerance + min valley depth = multiple x avg High-Low of last N bars, default 8); neckline-break marker = text-glyph triangle with size setting (default 30, DB SeaGreen); black width-4 line joins the two tops/bottoms; neckline width 2; "Delete invalidated DT/DB" setting (watches every drawn structure, not just the pending one). Rollback point for this batch: commit 7fc55360. User compiled (F5) OK 2026-10-12. 2026-10-15: "Show DT/DB label" setting (hide the DT/DB + score text). Later 2026-10-15: "5. Lines" settings (DT/DB leg color, leg style/width; peak-line color/style/width; defaults = previous look); alert echo prints removed; tick-chart warning only with debug prints. Defaults = user 15-min ES settings. 2026-10-15 later: triangle color settings; "Show last N DT/DB" (DT+DB together, 0 = all); neckline extends to the bar that closes beyond it; neckline = highest High / lowest Low of ANY bar between the two troughs/peaks (no swing pivot needed) + outside-bar special case (trough-1 bar own High counts if it closed up, trough-2 if down; mirrored for DT). Rollback point before this batch: 5489ee1f. Not yet F5-confirmed | ✅ current |
| `SessionSRLevelsV9.cs` | RTH + ETH session S/R levels + current-day H/L + 8 custom levels + **1D expected-move bands (two methods: VIX-formula AND gexlog brief, side-by-side for comparison)**. ETH levels computed from a hidden 1-min ETH-hours data series (work on RTH-only + daily charts); ETH H/L lock at the RTH open (overnight range). **OoD/OoW/OoM opens come from a hidden 1-min RTH-hours series** (it resets at 08:30 so bar[0] opens exactly on the RTH open — fixes wrong opens on tick/volume charts whose "first RTH bar" straddles 08:30 with a pre-open Open); keyed by date so live + historical both read the right value; the primary chart supplies only the start-bar anchor. **"Settlement" level = PRIOR trading day's Daily ETH close** (Fri shows Thu), read straight from a hidden Daily ETH series (`BarsPeriodType.Day`, ETH template) via `SettlementBefore(day)`; own property group + Historical checkbox. Series indices resolved dynamically (`_ethBip/_rthBip/_ethDayBip`). Start bars resolved per period from the primary chart (session-open on intraday, calendar-date walk on daily). Chart Trader buttons: RTH/ETH/LABELS/PRICE. Manual OoM price+month override; custom-level calendar start dates; extend-right offset; OoD RTH caps at its RTH session end. EM reads `data/vix_daily.csv` + `data/gexlog/raw/{date}_morning.json` (throttled, self-updating). **HISTORICAL LEVELS (Model A, confined per-day segments):** "22 Historical" properties section with a show-historically checkbox per level (RTH HOY/LOY/COY/OoD/OoW/OoM, ETH H/L, 1D Max/Min VIX+GEX); each prior day draws its levels confined to its own trading day, starting at the session-break line, dimmed, labels centered above (highs/opens) / below (lows). HOY/LOY/COY = the PRIOR session's H/L/C; ETH H/L + 1D bands = THAT session's own values; historical 1D bands use a VIX date→close map off the CSV + per-date gexlog briefs (cached). ⚠️ **NT8 duplicate-generated-region bug: this file is kept REGION-LESS in the repo — NT8 generates & owns its single region on first compile. Never paste a `#region NinjaScript generated code` block back in** (that's what caused the whole V1→V9 rename saga; see handoff). Renamed V1→V9 over the session; V9 is canonical. | ⚠ F5 verified rendering; EM comparison in progress |
| `SessionSRLevelsV10.cs` | V9 + optional developing session Point-of-Control/Value-Area (`ShowDevPocVa`, OFF by default). Live per-tick price/volume binning (`OnMarketData`, real-time only, no historical backfill) drives today's developing POC/VAH/VAL via the same greedy value-area expansion validated in `scripts/volume_profile.py`, recomputed once per bar close; final values logged to `data/vp_levels/session_vp_live_log.csv` on session close; prior sessions' VA renders as a box (`VpHistSessions`, default 1) off V9's existing `_rthHist` day-boundary tracking — builds up one day at a time from when first enabled live, never backfilled. Forked from V9 rather than replacing it — deliberately does NOT redeclare `LevelLineStyle` (reuses V9's); **V9.cs must stay deployed alongside it** or this fails to compile (CS0101 if both ever redeclare it, missing-type if V9 is removed). Not yet added to this table until now (2026-10-18) — see NT8-side grouping note above. | ⚠ F5 status not verified this session |
| `PriorWeekOHLCV4.cs` | Prior-week O/H/L/C — custom SharpDX render (per-print-bar start anchoring, extend-right offset, centered labels, PWO LABELS Chart Trader button, own `PWOLineStyle` enum so no cross-file dependency). Works on intraday + Daily. Also kept REGION-LESS (same NT8 bug). Renamed V1→V4; V4 is canonical. | ⚠ untested (F5 pending) |
| `CVDDivergenceOscillator.cs` | Standalone NT8 port of TradingView's TradingFinder "Cumulative Volume Delta Divergence Periodic EMA" — bar-proxy CVD (rolling-sum Periodic or EMA mode) + fixed-lookback fractal regular divergence (trend-EMA filtered). Deliberately kept separate from `CumulativeDelta.cs`'s own tick-level live-zigzag divergence feature so the two can be compared. Omits Pine's Forex/Crypto multi-broker "Ultra Data" volume sum (no NT8 equivalent on a single CME feed) — see file header for full list of documented deviations from the Pine source. Compile-checked clean 2026-10-18 | ✅ current, F5 pending |
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
| `BreakoutBoysLiteV1.cs` | Leaner rebuild (S136, extended S139-S141) — no ATM, no properties-dialog dependence. **Three entry mechanisms, generalized under `BBEntryKind {StopGated, StopUngated, Lmt}`:** SE LONG/SHORT (gated stop-limit), SE LONG/SHORT 2nd (ungated stop-limit), and new **LMT LONG/LMT SHORT** — a plain limit resting on the OPPOSITE side of the SB (`Low - OFFSET` for long, `High + OFFSET` for short), no IBS gate: a pullback/fade entry, not a breakout, betting price retraces into the SB's range rather than continuing out of it. Same staleness-guard pattern as the stop entries (reject + popup if the level is already marketable at the last price). Shares the same stop-loss calc (`ComputeStopLossPx`, factored out once three entry paths needed it), R-multiple target, and bars-alive expiration as the stop entries. **Also added same session:** if the protective SEstop is dragged to a new price before it fills, `OnOrderUpdate` recomputes + `ChangeOrder`s the target to keep the same R-multiple off the real entry; new **BARS** sub-button controls how many bars an unfilled entry stays working before auto-cancel (previously an implicit 1-bar NT8 default — `isLiveUntilCancelled=true` + `ExpireStaleEntry()` now own it explicitly). **LMT split into two pairs** (`BBEntryKind` now `{StopGated, StopUngated, LmtPullback, LmtRetest}`): LMT L BB / LMT S SA (unchanged — near side of the SB, same-bar pullback) and new **LMT L ▲ / LMT S ▼** (far side instead — SB High+OFFSET long / SB Low-OFFSET short) for a retest entry off an older broken level, typically via PICK SB on a bar price has since moved past. Initially pushed back on this as "the same as SE 2nd" / impossible as a plain limit — correct that a limit can't rest on the marketable side of *current* price, but wrong to assume the SB is always close to current price: with an older picked bar, "above the SB" can easily sit below where price trades now, making it a legitimate resting limit, not a stop. Same price-formula pair as the pullback variant, just swapped (High+OFFSET for longs instead of Low-OFFSET), and the staleness guard formula is unchanged (`isLong ? limitPx <= lastPx : limitPx >= lastPx`) — it naturally rejects the retest variant on the default (just-closed) SB, which is correct since retests need an older level. **Pick marker fix:** was always a below-bar up-arrow regardless of side, reading as "buy here" even when the pick was for a short — `DrawPickMarker(barIdx, isLong)` now draws below/up for longs, above/down for shorts; drawn long-style by default at pick time (side not known yet) and flipped in `ArmSE` once a side button is actually clicked. **Follow-up bug (same report, still showing up for shorts):** re-calling `Draw.ArrowUp` with the same tag as an existing `Draw.ArrowDown` (or vice versa) does NOT swap the underlying drawing-tool type — it just repositions the original object, so the arrow kept its original direction regardless of which Draw method got called later. Fixed by `RemoveDrawObject` before every redraw so the correct tool type actually gets recreated. Also: marker set to `ChartMarkerSize.Small` (was default/unset, i.e. larger) and forced to the same blue (`ColorPick`) on both directions per request; pick-time default direction now checks `_pendingShort` first (for the arm-before-pick order) instead of always assuming long. SE LONG/SHORT: arm intrabar, on the SB close gate on IBS = (Close-Low)/(High-Low) (momentum semantics: long needs IBS >= threshold, short needs IBS <= 1-threshold), then rest a genuine **STOP-LIMIT** entry: stop TRIGGER at the SB's own High (long)/Low (short), LIMIT cap N ticks past the trigger (bounds slippage once it fires) — fails the gate, or the trigger is already stale/through the last price, -> no order + a `MessageBox` popup explaining why. **Root-cause history (S137/S138):** v1 used a plain `EnterLongLimit`/`EnterShortLimit` resting above/below market, which is immediately marketable and fired instantly with no requirement that price ever trade back through the level — functionally not a stop entry at all; user caught it from a trade that filled with multiple points of "slippage" and a bar-stop that was already invalid by fill time. Fixed by switching to `EnterLongStopLimit`/`EnterShortStopLimit` and adding a staleness guard (trigger must still be on the correct side of `Close[0]`, `>=`/`<=` not strict so a bar that closed exactly at its own extreme still passes). That rewrite initially passed the args as (stop, limit) and threw "Limit price can't be greater than stop price" on first live test — reflected `NinjaTrader.Core.dll`'s `StrategyBase` to confirm the real signature is `(quantity, limitPrice, stopPrice, signalName)`, limit first; fixed. Also initially put the OFFSET on the wrong leg — applied it only to the limit cushion, leaving the trigger at the raw unoffset SB extreme — which the user caught from a fill landing exactly at the SB High instead of High+offset; fixed by moving OFFSET back onto the trigger (`SB extreme +/- OFFSET`, matching the original dashboard's stop-market convention) and giving the limit a small fixed (non-user-exposed) cushion (`StopLimitCushionTicks = 2`) purely to bound slippage once triggered. **Two more additions same session:** (1) if the protective SEstop order gets manually dragged to a new price on the chart before it fills, `OnOrderUpdate` detects the price change (vs the last value this code set) and recomputes + `ChangeOrder`s SEtgt to keep the same R-multiple off the real entry and the new stop. (2) new **BARS** sub-button (default 1) — NT8's managed default auto-cancels an unfilled entry at the next bar close; entries now submit with `isLiveUntilCancelled=true` (also discovered by reflection: `EnterXStopLimit`'s 6-arg overload is `(barsInProgressIndex, isLiveUntilCancelled, quantity, limitPrice, stopPrice, signalName)`) and a new `ExpireStaleEntry()` called every bar owns the cancel instead, honoring however many bars the user sets. SE LONG/SHORT 2nd: identical entry, skips the IBS gate (failed-second-entry re-attempts). Default SB = the bar you armed in; **PICK SB** button (toggle, then click a bar) overrides it with any manually-selected bar — order still only submits at the next bar close (OnBarClose-only strategy), same one-bar lag as the old dashboard's pick mode. Picked bar is marked with a blue arrow on the chart (`Draw.ArrowUp`, fixed tag — moves/clears itself) for visual confirmation. Stop-loss: BarStop (SB opposite extreme, inside-bar walk-left) or LastSwing, both + tick offset. Target: R-multiple of the REAL fill's risk (recomputed in `OnExecutionUpdate` off the actual fill price, not the pre-fill intended entry). STP mode / TGT R / limit-cap OFFSET / IBS threshold are all mini sub-buttons (left-click down, right-click up) on the Chart Trader panel — Cancel + Flatten All round it out. Compile-checked clean (paired with BreakoutBoysDashboardV1.cs — distinct enum name `BBLiteStopMode` to avoid a namespace collision). **2026-10-14: the "entry blocked" MessageBox was a MODAL dialog on NT's UI thread → froze the whole platform; replaced with non-blocking `Draw.TextFixed`.** | ⚠ untested (F5 pending) |
| `BreakoutBoysLiteV2.cs` | V1 + **tab-aware Chart Trader panel** (2026-10-14): a chart WINDOW shares ONE Chart Trader across its tabs, so the old per-instance buttons were dead on the 2nd tab. Now ONE shared button set per window (static `_ctByGrid`), routed to whichever chart the mouse last entered (`ChartControl.MouseEnter`); colors re-sync on entry; shared PICK flag (per-instance `_pickArmed` broke across tabs); panel compacted so the BARS row isn't clipped. Entry logic unchanged from V1. **V1 left untouched = rollback.** | ⚠ Sim F5 pending |
| `BreakoutBoysLiteV3.cs` | V2 + **reworked entry engine** (2026-10-14, user-designed). **BUY/SELL** (one per side): level L = SB extreme ± OFS; order TYPE auto-chosen at placement by last price vs L — not reached → stop-limit at L (breakout), already past → limit at L (pullback); **never blocked** (`PlaceAutoEntry`). **IBS = on/off toggle** (shows "IBS 50") + `[IBS −][IBS +]` mini-buttons (±5), gates BUY/SELL only. **No SB picked** → SB = forming bar, placed at its close; **SB picked** → placed IMMEDIATELY, queued + submitted in **`OnMarketData`** (managed `Enter()` from the button/`TriggerCustomEvent` thread silently no-ops). Stop-side guard (stale LastSwing fallback to SB BarStop). **SB marker stays while working + FOREVER on fill** (trade mark); removed only on cancel/disarm/expire/flatten of an unfilled order. Removed SE-2nd + LMT-retest; LMT L BB/S SA unchanged. Reuses V1's enums (keep V1). **V1/V2 untouched = rollback.** | ⚠ NEEDS Sim F5 + test |
| `WedgeScalper.cs` | MyWedge signal-bar scalper (stop entry 1t beyond SB, +4t scalp, runner BE→trail). Superseded by V2. | ✅ current |
| `WedgeScalperV2.cs` | WedgeScalper renamed + S107 fixes (single sized entry, all-manual exits, immediate stop on fill via OnExecutionUpdate, no re-scalp, entry auto-expire, hard safety net, qty=0 disables a lot). Has dated change-log header. | ✅ current |
| `MCBreakout.cs` | MC breakout strategy (pyramiding + ratchet-lock, S32) | ❌ LOST — not committed |

### addons/

AddOns run automatically the instant NT8 starts — no Strategies-grid enable step, survive
restarts. Deployed copy's enable/disable state lives in the filename extension in the Custom
folder (`Foo.cs` = compiled/active, `Foo.cs.disabled` = not compiled); the repo copy here is
always named `.cs` regardless of deployed state — this table is the source of truth for status.

| File | Purpose | Status |
|------|---------|--------|
| `TickExportAddOn.cs` | On-demand tick export bridge — watches `data/nt_ticks/_request.json`; what `tick_pipeline.py` and manual backfills ask NT8 for historical ticks through | ✅ current |
| `L1TapeRecorderAddOn.cs` | L1 tape + best-bid/ask recorder (replaced the old L2/footprint pipeline — footprint is reconstructable offline from the L1 tape, see `FootprintExporter.cs` above) | ⛔ retired 2026-10-14 (user decision) — deployed copy renamed `.cs.disabled`, supporting tasks `MyQuant L1 Recorder Watchdog`/`MyQuant L1 Rollover` disabled. Historical `data/l1_tape/*` files untouched; no new ones accumulate. |
| `MarketDepthRecorderAddOn.cs` | Experimental L2 market-depth recorder (S75V, 2026-07-21) — shadow-test parallel to the old `MarketDepthRecorder.cs` strategy, writes to `data/depth/addon_test/` (never fed the live pipeline) | ⛔ retired 2026-10-14 — was a zombie well before this: hardcoded `SymbolName = "ES 09-26"` (never updated past that contract's expiry) meant it spent months endlessly reconnecting to a dead contract (log: `depth SILENT 90s ... forcing resubscribe` every ~90s) for zero real data. Deployed copy renamed `.cs.disabled`. |

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
