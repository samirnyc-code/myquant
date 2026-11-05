# Fixes for Thomas — 2026-11-05 (complete, single doc — supersedes any earlier version of this file)

**Written:** 2026-11-05 (Samir's machine)
**For:** whichever Claude Code session Thomas opens on his own machine to apply this.
**Two unrelated issues, both covered below:**
- **Issue A — Screenshot / chart-tag reliability** (`myquant` repo, `ClaudeTrackerAddOn.cs`
  + friends). Thomas has git access here (`tdeutschmann-byte`).
- **Issue B — CVD/DT-DB indicator family** (`CVDRealDivergence.cs`,
  `CVDDivergenceOscillator.cs`, `DtDbScannerV3.cs`, `DtDbCvdPivotRegistry.cs`,
  `BidAskSharedEnums.cs` — all also in `myquant`, same git access).

**New convention starting this session, apply going forward too:** every file below now
has ALL of its per-machine-editable values (file paths, account names, etc.) collected in
ONE clearly marked block at the TOP of the file, instead of scattered through the body.
Look for `==================== PER-MACHINE CONFIG ... ====================` banners.

There is no `trade-playbook` repo content in this version of the doc — that was a
separate, already-resolved issue (trade journal upload gap) from earlier the same day;
if you need that, check git history for this file or ask Samir.

---

## Issue A: Screenshot / chart-tag reliability

**Symptom reported:** screenshots only landed roughly half the time, AND — more
specifically — Thomas observed screenshots recording correctly even when the
"ClaudeTracker Chart Tag" indicator wasn't running at all. That second symptom is the
real smoking gun (see A2 below).

### A1. Wrong tab captured

`CaptureFromChartControl()` calls `targetChart.GetScreenshot(...)` on the chart
**window**, which renders whatever **tab** is currently selected — not specifically the
tagged `ChartControl`. If Thomas is looking at a different tab (another instrument/
timeframe) in the same chart window when a trade event fires, the old code captured
whatever was on screen instead of the right chart, or got a blank render, instead of
failing loudly.

**Fix:** before capturing, the code finds the tagged chart's own tab in its window's tab
collection, force-selects it, captures, then restores whatever tab was previously showing.

### A2. Stale registry entry — the bigger bug, explains the exact symptom reported

`ClaudeTrackerChartRegistry` is a pure write-back cache: `Get()` returns whatever's
cached, **forever**, with no expiry and no liveness check. The only cleanup path
(`Unregister()`) fires from the tag indicator's own `State.Terminated` — already known
unreliable (a 2026-10-28 comment in the file documents an NT8-wide reload or a closed
chart window not always tearing the indicator down cleanly). Net effect: if the tag was
ever on a chart that later closed (or the indicator got removed) without a clean
`State.Terminated`, the registry kept silently pointing at that dead/stale chart forever
— exactly "recorded fine with the indicator not even running": it was capturing from an
old leftover chart, never re-verified.

**Fix:** `CaptureFromChartControl()` now re-checks, on the matched chart's own UI thread,
that `ClaudeTracker Chart Tag` is genuinely still present on its indicator list right now.
If not, it unregisters the stale entry and re-triggers a fresh live-scan instead of
silently capturing from the wrong/dead chart. Watch for this new log line — if it ever
appears, it's direct proof this exact bug just fired and self-healed:
```
Screenshot: <tagged chart|live scan> was STALE -- "ClaudeTracker Chart Tag" is no longer
on this ChartControl (removed, or its window closed without a clean unregister) --
clearing the cached entry and re-scanning from scratch
```

### Steps

1. `git pull` in Thomas's `myquant` clone — confirm you land on commit `d1e97c6d` or
   later (and ideally the follow-up path-consolidation commit right after it — check
   `git log --oneline -5 -- nt8/addons/ClaudeTrackerAddOn.cs`).
2. Open `nt8/addons/ClaudeTrackerAddOn.cs` — the per-machine config is now ONE block near
   the top of the class (`AccountName`, `SymbolName`, `TraderTag`, `ExportRootFolder`), all
   4 lines together, clearly banner-commented. **Before copying over his deployed file**,
   note Thomas's current 4 values (they're in his existing deployed copy at
   `<Documents>\NinjaTrader 8\bin\Custom\AddOns\ClaudeTrackerAddOn.cs`, previously split
   across two different places in the file — that scatter is exactly what's fixed now).
   Copy the new repo file in, then set those same 4 values in the new top config block.
   Byte-diff after to confirm only his 4 values differ from the repo version.
3. **Tell Thomas to F5 when flat** (no open position) — needs a human in the NT8 UI.
4. This only helps if Thomas has already dropped "ClaudeTracker Chart Tag" on his one real
   execution chart (original setup, `docs/living/thomas_claudetracker_addon_setup.md` step
   6). If he hasn't, screenshots still fall back to ambiguous window-title matching
   regardless of these fixes.
5. Verify: fire a Sim test trade, confirm `Screenshot saved (tagged chart): ...` in his
   log (not a bare `Screenshot saved:` with no "(tagged chart)" suffix), and open the PNG
   to confirm it's actually the right chart.

---

## Issue B: CVD / DT-DB indicator family

Five files, built over several prior sessions, not yet actually sent to Thomas. Honesty
up front: **not everything below is equally confirmed working** — Samir's own testing
left some items unconfirmed (diagnostic log files that were supposed to prove a fix
landed were never found on a check this session — see the per-component notes).
Don't present any of this to Thomas as "definitely working," only as "this is the current
state, here's what's confirmed vs. not."

### What each file is

| File | What it is | Status |
|---|---|---|
| `CVDRealDivergence.cs` | Standalone. CVD fractal-pivot divergence using REAL tick-classified delta (live `OnMarketData` + historical backfill from `data/bid_ask/bid_ask_vol_buckets.csv`). Separate from the OHLC-proxy version below — different indicator, same algorithm. | Built 2026-10-28. One descriptive comparison study run (`scripts/cvd_divergence_proxy_vs_real_study.py`) — real method fires fewer signals, skewed bearish; **not validated beyond that one pass**. |
| `CVDDivergenceOscillator.cs` | The original OHLC-bar-proxy version of the same divergence algorithm, now with an optional link to DT/DB's own confirmed pivots (`OnlyShowAtDtDb`). | Thomas previously said he only wants this "OHLC version." Needs `DtDbCvdPivotRegistry.cs` to compile at all, even if the toggle is off. Defaults-sync commit `9cda0755` (matching Samir's live "Save As Default" values) — **not confirmed F5'd/reflected in the Properties panel as of this doc.** |
| `DtDbScannerV3.cs` | Double-top/bottom structure scanner, gained 3 new CVD-related toggles this cycle (`FilterToDivergenceOnly`, `ShowCvdDivergenceLine`, `ShowHiddenCvdDivergence`) — DT/DB detection/scoring itself untouched. | Hidden-divergence bug found+fixed, but the diagnostic log meant to confirm it (`data/_dtdb_hidden_div_diag.log`) **does not exist on Samir's machine as of this check — fix is NOT yet confirmed working with real data.** Needs `BidAskSharedEnums.cs` + `DtDbCvdPivotRegistry.cs` to compile. |
| `DtDbCvdPivotRegistry.cs` | Shared in-process registry linking DT/DB's confirmed pivots to `CVDDivergenceOscillator.cs` (same pattern as `ClaudeTrackerChartRegistry.cs`). | Required by both files above if `OnlyShowAtDtDb`/the CVD toggles are ever turned on. No file-path config, nothing to edit. |
| `BidAskSharedEnums.cs` | Shared `CvdCumulativeMode` enum. | Required by `DtDbScannerV3.cs`. No config. |

### Per-machine config now at the top of `CVDRealDivergence.cs`

Only this one file in the CVD family had a buried path — now fixed:
```
BucketLogPath = @"C:\Users\Admin\myquant\data\bid_ask\bid_ask_vol_buckets.csv"
```
This is ONLY used for historical backfill (reconstructing past bars' real delta from the
L1 tape) — produced by `scripts/backfill_bid_ask_log.py` in the myquant repo, a **Python
pipeline** that has to be running on whichever machine wants that backfill. If Thomas
doesn't run that pipeline, leave this pointed at a nonexistent path — the indicator still
works **live** (today forward), it just won't backfill past-day divergences. Not a
blocker to deploying it, just a feature that needs its own data pipeline to be useful.
The other 4 files in this family have no file-path config at all — nothing to edit in
them.

### Deploy locations — the `.My` dual-copy trap applies here

`CVDDivergenceOscillator.cs` and `DtDbScannerV3.cs` both declare
`namespace NinjaTrader.NinjaScript.Indicators.My` — NT8 auto-mirrors `.My`-namespaced
indicators into `Custom\Indicators\My\`, and **that mirrored copy, not the top-level one,
is what NT8 actually keeps compiling from** after the first time it does this (see
`nt8/README.md`'s "`.My`-namespaced indicators auto-duplicate" section for the full
story — this already cost a full F5 failure once). **Before deploying either file, check
whether `Custom\Indicators\My\<name>.cs` already exists on Thomas's machine** — if it
does, deploy there and delete any top-level orphan, don't leave both copies present.
`CVDRealDivergence.cs`, `DtDbCvdPivotRegistry.cs`, and `BidAskSharedEnums.cs` are all
plain-namespaced — deploy those at the top level of `Custom\Indicators\`, no `.My` trap.

### What to actually send Thomas

Per his own stated preference ("only interested in OHLC version atm"), the default is:
- **`CVDDivergenceOscillator.cs` + `DtDbCvdPivotRegistry.cs`** (2 files) — but flag the
  unconfirmed defaults-sync status above before he trusts the properties it loads with.

If he wants the DT/DB CVD toggles too: add **`DtDbScannerV3.cs` + `BidAskSharedEnums.cs`**
(3 more files on top, `DtDbCvdPivotRegistry.cs` already covers the shared dependency) —
but flag the unconfirmed hidden-divergence fix first.

If he ever wants the real-tick-data version instead of/alongside the OHLC one: just
**`CVDRealDivergence.cs`**, standalone, nothing else needed — this is the file with the
config block now fixed.

### Steps

1. `git pull`, confirm the CVD-family commits are present (`git log --oneline -3 -- nt8/indicators/CVDRealDivergence.cs` should show the 2026-11-05 path-consolidation commit on top).
2. Pick the file set per "What to actually send Thomas" above, confirm with Thomas first
   if unsure which he wants.
3. Copy to the correct Custom folder per the `.My` trap note above — check for an
   existing `Custom\Indicators\My\` copy first.
4. F5 when flat.
5. Before telling Thomas anything is "fixed," check the relevant diagnostic log
   (`data/_dtdb_hidden_div_diag.log` or `data/_cvd_pivot_connector_diag.log` if he's using
   `DtDbScannerV3.cs`'s hidden-div/pivot-connector features) for real fresh entries — don't
   assume either fix works just because it compiled.

---

## If something looks wrong

Same standing instruction as the original setup doc: report back the exact log lines
rather than guessing at a fix blind.
