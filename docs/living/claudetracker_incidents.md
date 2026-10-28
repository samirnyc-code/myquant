# ClaudeTracker incident log

Running history of ClaudeTrackerV2 (the NT8 strategy that journals every trade
to `trade-playbook`) losing, mangling, or misattributing a trade. Kept
separate from `docs/living/handoff.md`'s chronological session log so the
*pattern* across incidents is visible at a glance without digging through
unrelated sessions. Add a new entry every time this happens — don't let it
live only in a session's handoff block.

See `nt8/strategies/ClaudeTrackerV2.cs` for the current code; recovery
scripts referenced below live in the private `trade-playbook` repo
(`Desktop\trade-playbook\scripts\`).

---

## 2026-10-23 — architecture change: AddOn port built to fix the whole "disables itself" class

Every "disable" seen across these incidents (10-16's screenshot cross-thread crash, the
2026-10-22 `OnBarUpdate` exception) shares one root cause: it's a **Strategy**, and NT8
itself force-disables a Strategy on certain uncaught exceptions in its callbacks (confirmed
in the Output log both times: "Disabling NinjaScript strategy"). User asked directly
whether this class of bug could be eliminated rather than chased fix-by-fix.

Built `nt8/addons/ClaudeTrackerAddOn.cs` — same trade-tracking logic, ported onto NT8's
`AddOnBase` instead of `Strategy`. An AddOn has no Strategies-tab enable/disable state at
all, so there is nothing for NT8 to auto-disable. Also a natural singleton (one AddOn
instance per NT8 process, no "two chart instances on the same instrument" scenario), which
deleted the entire ownership-arbitration subsystem the Strategy version needed.

Ported from the Strategy's current stable baseline (post `4460db47` revert), not the riskier
reload-resume rewrite that caused the 10-22 incident — and separately re-applied the
entry-merge-window fix (EntryOrderId/EntryMergeWindowMs, fixes multi-lot market orders
getting mislabeled ADD_ON) that was reverted alongside it despite being explicitly flagged
as not implicated.

**Screenshots are NOT dropped** — an earlier pass of this file punted on them (no-op stub) on
an unverified risk assessment; corrected same day after the user pushed back. Verified the
real API against `NinjaTrader.Gui.dll` via reflection instead of guessing:
`Chart.ActiveChartControl.Instrument` finds the right open chart, `Chart.Dispatcher` is that
window's own UI thread, `Chart.GetScreenshot(ShareScreenshotType)` is the same call the
Strategy version used. Two-hop dispatcher pattern (`Application.Current.Dispatcher` to find
the window, then THAT window's own `Dispatcher` to screenshot it) avoids the exact
wrong-thread crash the Strategy version hit on 2026-10-16. Real remaining limitation: no open
chart showing the tracked instrument = no screenshot that cycle (logged, not fatal) — the
manual "+ Add screenshot" upload in the Journal app covers that case.

**Deliberately dropped:** bar/session-bar tracking (MAE/MFE now runs off live tick prices via
a MarketData subscription instead — an AddOn has no bars, but ticks are at least as accurate).

**What this does NOT fix:** state lost on an NT8 recompile. ALL NinjaScript — Strategies,
Indicators, AddOns — gets torn down and reinstantiated on F5; switching base class doesn't
change that. `ReconcileOpenPosition()` (the simple Position-reconcile fallback, not the
reverted TryResumeOpenTrade rewrite) is ported as-is and has the same limitation it always
had: a trade open across a reload keeps trading but loses its original entry time/stop
history.

**Status: compile-checked clean, NOT deployed, NOT F5'd, NOT run live.** Recommend running
it side by side with the existing Strategy for at least one full session, comparing output
files, before retiring the Strategy — not swapping in blind, per the 10-22 lesson.

**First live test, same day (2026-10-23), both trackers running side by side:** ES SIM101
test trade, one entry/one exit. Results: the AddOn tracked the fill, risk, and close
correctly (PnL=-50.00) with zero disabling. **ClaudeTrackerV2 (the Strategy) did NOT close
the trade** — but not from a code bug: the NT8 log shows `Chart Trader close position`
disabled TWO strategies in the same instant (`BreakoutBoysLiteV3` and `ClaudeTrackerV2`),
half a second before the actual exit fill landed — this is NT8's own platform behavior
(manually closing a position via Chart Trader disables strategies on that instrument), not
anything specific to this file. Live confirmation that the Strategy is vulnerable to a
disable trigger beyond the ones already in this log (uncaught exceptions) — simply clicking
"Close Position" can do it too — and that the AddOn is immune to the whole class.

Also found: AddOn screenshots didn't fire (`"no open chart showing ES 12-26 — skipped"`,
both entry and exit) — the chart-window lookup only checked each window's
`ActiveChartControl` (the currently-focused tab); the ES chart was apparently open in a
non-active tab. Fixed same day: falls back to scanning every tab via
`Chart.MainTabControl.Items` → `ChartTab.ChartControl.Instrument`, switching to a background
match briefly (restored after capture) if the active tab doesn't have it.

---

## 2026-10-22 — the reload-fix itself broke live trading within hours of deploy

**Symptom:** Thomas deployed the SAME-DAY reload fix (below), closed a trade, and
`ClaudeTrackerV2` immediately disabled itself. Reproducible, every close.

**Root cause:** `OnBarUpdate` now called the new `TryResumeOpenTrade()` on every tick
while flat — but `OnBarUpdate` has NO try/catch around it, unlike
`OnAccountOrderUpdate`/`OnAccountExecutionUpdate`, which both wrap their entire body.
Any exception inside the new replay logic (most likely racing the Events.csv write
`CloseTrade` had just done a moment earlier, or a transient `Position` read that
hadn't settled to Flat yet right after the closing fill) propagated straight out of
`OnBarUpdate` uncaught, and NT8 disables a strategy on an uncaught `OnBarUpdate`
exception.

**Fix (same day):** the `OnBarUpdate` call site now explicitly catches and is
throttled to once per 5s instead of every tick (less I/O, smaller race window);
`TryResumeOpenTrade` itself also got a top-level try/catch
(`TryResumeOpenTradeInner` holds the real logic) so no call site — including any
future one with no caller-side protection — can ever take the strategy down again.
Compiled clean, deployed to Samir's own Custom folder, committed `edd650a`.

**Lesson for next time:** a reload-safety fix is itself new, more complex code
running on a hot path (every tick) — it needs the SAME defensive wrapping as the
rest of this file, not just the thing it's protecting against. Should have wrapped
`OnBarUpdate`'s new call from the start instead of only the three already-protected
call sites.

## 2026-10-15 — stuck-open trades + one dropped entirely

**Symptom:** 2 of Samir's trades stuck `OPEN` in the journal forever; a 3rd
trade (10:42 entry) never appeared at all.

**Root cause:** The strategy reloaded (recompile/reconnect) mid-trade, right
after `InitialStop` locked but before the final exit fill landed.
`activeTrade`/`activeStudy` were plain in-memory fields with no persistence —
the reload wiped them. `HandleExitExecution`'s `if (activeTrade == null)
return;` guard then silently ate the next closing fill: no error, no trace,
nothing written anywhere.

**Fix at the time:** `ReconcileOpenPosition()` added — checks the broker's
live `Position` at `State.Realtime` and on ownership-takeover between chart
instances, synthesizes a stub "RECOVERED" trade from `Position.AveragePrice`/
`Quantity` if one is found open with nothing tracking it. Buys correctness
(the trade will eventually close) over completeness (original entry time and
stop history before the reload are lost).

**Recovery:** `recover_20261015_trades.py` — manually reconstructed all 3
trades from Samir's pasted NT8 execution history + whatever `EntryStudy.csv`
data survived. Posted directly to `/api/ingest/trade`.

---

## 2026-10-16 — one real trade chopped into 3 fictional ones

**Symptom:** A single real trade (08:47 entry, Target1 partial, Stop2 exit)
appeared as 3 separate trades in the journal, all exited
`ForceClosed_HealthCheck` with `WeightedAvgExitPrice=0.00`.

**Root cause:** A health-check force-close path (added after the 10-15
incident, since removed — see `RunHealthCheck`'s current comment) fired on a
single stale `Position` read 5 seconds after a genuine entry, then misread
the real subsequent Target1/Stop2 fills as brand-new entries.

**Fix at the time:** The drift-check/auto-close logic in `RunHealthCheck` was
removed entirely (not just the auto-close action) — user call, after it
proved it could fire on a perfectly healthy trade. `RunHealthCheck` is now
ONLY a heartbeat (`ClaudeTracker_Health.json`) + the raw execution-log
snapshot — no comparison, no reconciliation, no alerting.

**Recovery:** `recover_20261016_chopped_trade.py` — merged the 3 fictional
trades back into 1 real one (reusing the first fake trade's `TradeID` so its
real ENTRY/TARGET1 screenshots stayed attached), reattached the 2 real
mid-trade screenshots that had been captured under the wrong labels, deleted
the 2 fake trade records.

---

## 2026-10-21 — Thomas: entire trading day never tracked (6 trades)

**Symptom:** Zero trades in the journal for Thomas's `ES DEC26` account all
day, despite 6 real round-trips (+$975 gross) in his own NT8 execution log.

**Root cause:** Never directly confirmed (no NT8 Output log available for
his machine) — ClaudeTrackerV2 simply never started tracking that day on his
install. Distinct from the other incidents: not a mid-trade loss, a total
miss from the first fill.

**Recovery:** `recover_20261021_thomas_trades.py` — reconstructed all 6
trades from his pasted raw `ExecutionLog_2026-10-21.csv`. Timestamps
required converting from Europe/Berlin (his PC's clock) to UTC, not
America/Chicago like Samir's exports — cross-checked against Samir's own
same-morning trades (price levels lined up once converted) to confirm the
timezone before posting. No stop/risk data existed anywhere, so those fields
were left `null`, not guessed.

---

## 2026-10-21/22 — Samir: a breakeven stop-exit became a phantom new trade

**Symptom:** A 10:03 LONG stuck `OPEN` forever. A fictional `SHORT` trade
appeared at 10:12:59 (the LONG's own exit time), also stuck `OPEN` forever —
and the NEXT real trade (10:20 SHORT, -$150) never appeared at all; its
fills got silently absorbed as a fake "ADD_ON" to the phantom.

**Root cause — the general case, not just this instance:** `HandleExecution`
trusted `activeTrade == null` as proof the account is flat
(`positionBefore = activeTrade != null ? activeTrade.CurrentQty : 0`), with
NO check against the broker's actual `Position`. `ReconcileOpenPosition()`
only ran at `State.Realtime` and ownership-takeover — anywhere else
`activeTrade` went null (most likely: NT8's `Account.Positions` snapshot
lagging the matching `Execution` event during a reconnect, a known class of
race), the very next real fill got misread as a brand-new trade instead of
the close it actually was.

**Recovery:** `recover_20261021_samir_reload_trades.py` — closed the real
LONG at its true breakeven exit ($0, stop/risk data pulled from its own
surviving `EntryStudy.csv`), split out the real SHORT (-$150) with its 4 real
screenshots reattached (identified by matching file mtimes to the real fill
times, not the phantom's), deleted the phantom.

**Real fix (this time, not just a recovery script) — 2026-10-22:**
1. `Events.csv` is now written on **every** fill, not just at `CloseTrade()`
   — previously only `EntryStudy.csv` was durable mid-trade, which is
   exactly why the 10-21 forensics could recover stop data but not the close.
2. `TryResumeOpenTrade()` replaces the Position-only stub as the primary
   recovery path: on reload it replays this trade's own `Events.csv` +
   `EntryStudy.csv` rows to resume the **identical `TradeID`** with full
   history intact, instead of a stub "RECOVERED" trade with history wiped.
   Falls back to the old Position-only stub only when there's truly nothing
   on disk to replay.
3. The resume check now also runs inline inside `HandleExecution` (before
   trusting `activeTrade == null` as flat) and every `OnBarUpdate` tick, not
   only at the two old checkpoints — closes the race window to at most one
   tick instead of "until the next reload."
4. If the replayed quantity doesn't match the broker's real position (fills
   genuinely happened during the gap with no record of them), the gap is
   never silently trusted either way — reconciled to the broker's truth with
   a flagged `GAP_RECONCILE` row for manual review, not hidden.
5. New companion indicator `ClaudeTrackerWatchdog.cs` — a strategy can't
   alert on its own death, so this is a separate script that reads the same
   heartbeat file on an independent wall-clock timer and draws a large
   on-chart red banner + sound alert the moment the heartbeat goes stale or
   the file disappears (and a distinct amber banner if a `GAP_RECONCILE`
   ever fires).

Commits: `nt8/strategies/ClaudeTrackerV2.cs`, `nt8/indicators/ClaudeTrackerWatchdog.cs`
in this repo. **Not yet deployed live** — needs copying to the NT8 Custom
folder + F5 when flat (see `nt8/README.md`); compile-checked clean
individually via `scripts/nt8_compile_check.ps1` but not yet run live.

---

## Pattern across all 4 incidents

Every single one is the same shape: `activeTrade` (plain in-memory state)
went out of sync with the broker's real position, and nothing caught it
before the next fill got misattributed. The 2026-10-22 fix targets that
general shape directly (durable per-fill ledger + continuous broker-aligned
resume), not just the specific trigger — but it has not yet been proven live
through an actual reload. Add the next incident here regardless of whether
it's a "new" failure mode or this fix just didn't cover some case.

---

## 2026-10-27 — AddOn's assumed-singleton immunity was wrong: settleTimer reentrancy caused duplicate trade records, same day NT8 crashed mid-trade

User reported a SIM ES 12-26 LONG showing as **two** Journal cards for what
was one 2-lot entry/stop-out (-$610 each) — one card had screenshots, one
didn't. Same session, separately, NT8 crashed while the user was in a trade
(SIM, no real-money exposure; position was already flat per the log by the
time of the crash, confirmed before advising a restart).

**First investigated and ruled out:** the screenshot-targeting mechanism
itself (`ClaudeTrackerChartRegistry` + `ClaudeTrackerChartTag.cs`, built
2026-10-23) — log evidence showed it had been silently falling back to
ambiguous title-matching on 100% of screenshots since 10-24 (zero
`"(tagged chart)"` lines in any log from 10-24 through 10-27, despite
working all of 10-23). Root cause there: `Register()` only fires once at
`State.DataLoaded`, which can land before `ChartControl` is populated
after an overnight session rollover — one missed registration, stuck for
days with no retry and no warning logged. Fixed: `ClaudeTrackerChartTag`
now re-registers every bar (self-healing); `ClaudeTrackerAddOn` now logs a
`Warning` on every fallback and lists every candidate window when more
than one chart shares a title, instead of only logging on a zero-match.
This explained *which chart* got screenshotted wrong, but not why there
were two trade records in the first place.

**Real root cause, found in the actual trade's log:** `ClaudeTrackerAddOn`'s
header comment claims it's "a natural singleton (one AddOn instance per
NT8 process)," immune to the class of duplicate-instance bug documented in
Part 6.5 above. That's false in the way that matters: `TryResolveInstrument()`
/ `TryResolveAccount()` are driven by `settleTimer`, a `System.Timers.Timer`
(1s interval) — which is **reentrant**. Confirmed directly in the
crash-restart log: one `"loaded for Sim101..."` line (SetDefaults ran once,
genuinely one instance) but **four** `"instrument resolved"` and **four**
`"account resolved"` lines, all within the same millisecond — a burst of
queued Elapsed ticks (startup contention: dozens of vendor DLLs + workspace
restoring at the same moment) racing through the unguarded
`if (x != null) return` check before the first tick's assignment was
visible to the others. `TryResolveAccount` subscribing
`Account.ExecutionUpdate += OnAccountExecutionUpdate` more than once meant
every real fill fired the handler once per duplicate subscription — each
firing independently incremented `dailyTradeCounter` and wrote its own
trade record (`_T1_ADDON` / `_T2_ADDON` from one fill), and independently
called `RequestScreenshot`, so each hit the tagged-chart-registry race
differently (one got `"(tagged chart)"`, one got the fallback) — which is
also why the two cards differed on screenshots specifically.

**Fix:** wrapped both resolve methods in a double-checked `lock` on the
existing (previously underused) `subLock` field, making check-then-set
atomic. `[myquant] fdc7b27`. This likely also explains the old unsolved
Part 6.5 question ("why two instances could simultaneously hold ownership
was never root-caused") — same reentrancy class, different host (the
Strategy had an analogous poll-and-resolve pattern that was never
instrumented closely enough to catch the race in the act).

**Not yet deployed live** — copied to the Custom folder but user was
mid-trade/just-crashed when this was found; needs F5 when flat, same as
the chart-tag fix above (`[myquant] a745daa`). Both fixes are in the same
session, deploy together.

---

## 2026-10-28 — the 10-27 chart-tag fix wasn't enough (OnBarClose too slow); AND a separate bug silently drops a partial exit's P&L from the journal forever

The 10-27 deploy (`a745daa`/`fdc7b27`) never got F5'd before the next trade — confirmed
by `NinjaTrader.Custom.dll`'s own mtime (2026-10-27 14:23, after both fixes were
written). So it should have been live. It wasn't effective anyway, for a second,
independent reason.

**Screenshot-wrong-chart recurred.** Log for tonight's 02:02 ES 12-26 LONG:
`tagged-chart registry has no entry for "ES 12-26"` — identical failure to 10-24. The
10-27 fix made `ClaudeTrackerChartTag` re-register every bar close (`Calculate.OnBarClose`)
instead of only once at `State.DataLoaded`. That self-heal is useless on a 2000-tick ES
chart during low-volume ETH hours: if the one-shot `DataLoaded` registration missed (the
original failure mode), a 2000-tick bar can take far longer to close than the gap to the
next real trade, so the "self-heal" never got a chance to run even once before the
screenshot fired. Fixed: `Calculate` switched to `OnEachTick` so the re-registration
retries on every tick instead of every bar close; added registration attempts at
`State.Historical`/`State.Realtime` too, not just `DataLoaded`; added a one-time `Print`
on first successful registration (there was previously zero log output on success, only
on failure — no way to confirm the self-heal had worked without this incident forcing a
code read).

**Separately: `ClaudeTrackerAddOn` reloaded mid-trade at 02:08:37** — all three AddOns
(`ClaudeTrackerAddOn`, `L1TapeRecorderAddOn`, `TickExportAddOn`) show `"loaded"` in the
log within the same second, which only happens on an NT8-wide recompile (F5). Not
triggered by this session's `.cs` file copy to the Custom folder — NT8 doesn't watch that
folder; only an explicit F5/Compile reloads NinjaScript. Cause of the F5 itself unconfirmed
— user was mid-trade at the time.

That reload wiped `ClaudeTrackerAddOn`'s in-memory `activeTrade` for the still-open
position, and `ReconcileOpenPosition()` did exactly what it's designed to do: recovered a
new `..._RECOVERED_T1_ADDON` trade record for the 1 contract still open, same entry price
(7759.50) as the original — this is the "duplicate trade at the same entry price" the user
saw, and it's not a phantom trade, it's the same real position split across two TradeIDs
because the tracking process restarted underneath it.

**The real finding is worse than the duplicate.** Cross-checked against NT8's own
execution log (ground truth): the real trade was entry 2 @ 7759.50, Target1 filled 1 @
7762.50 at 02:05:40 (+$150), Target2 filled 1 @ 7764.50 at 02:10:28 (+$250) — true total
+$400. The Target1 fill happened *while `ClaudeTrackerAddOn` was still running normally*,
3 minutes before the reload, and it was never written to `Events.csv`/`TradeSummary.csv`
at all — `CloseTrade()` was the only place those files got written, and it only runs when
the position goes fully flat. `activeTrade.EventRows` accumulated every event (including
the profitable Target1 exit) purely in memory until then. The 02:08:37 reload destroyed
that in-memory list before the trade ever closed under its original TradeID, so the $150
leg has no file anywhere in the journal — not a duplicate, a permanent loss, recoverable
only by reading NT8's raw platform log by hand (which is how this was reconstructed).
`journal_uploader.py`'s own header comment (`trade-playbook/scripts/journal_uploader.py:11`)
already documented `Events.csv` as "fill-by-fill event log (full rewrite each fill)" — the
uploader was built assuming incremental writes the AddOn never actually did.

**Fix:** added `FlushEventsIncremental()` — rewrites the per-trade `Events.csv` whole
(cheap, idempotent) and appends only not-yet-flushed rows to the master `Events_MASTER.csv`
(tracked via new `EventRowsFlushedCount` field) — called after every OPEN/SCALE_IN/ADD_ON/
SCALE_OUT/EXIT event is added, not just at `CloseTrade()`. `TradeSummary.csv` deliberately
stays write-on-close only — `journal_uploader.py` uses its existence as the "trade is done"
signal, so an interim one would read as a premature close. `[myquant]` pending commit.

**Not yet F5'd** — both fixes (chart-tag + incremental events) compile-checked clean and
copied to the Custom folder; trade closed flat by 02:10:28 so no live position is at risk,
but no F5 has happened this session. Next: F5 when convenient, then watch the next trade
for a `"[ClaudeTrackerChartTag] registered"` Print (confirms the tag fix) and verify
`Events.csv` in the trade folder already has rows mid-trade, before any exit (confirms the
flush fix).

**Third finding, same session, user asked directly whether Initial/Actual Risk would now
record correctly:** `InitialStopLockSeconds = 5` is a settle window, and the window only
*starts* on the stop's first subsequent price change, not at the moment the stop was first
placed — so tonight's stop sitting at 7756.50 for 4 minutes before trailing to breakeven at
7759.50 (after Target1 filled) locked `InitialStop` at 7759.50, reading 0.00pt risk instead
of the real 3.00pt. Initially read this as a bug and shipped a fix moving the window start
to the moment of placement. **Reverted immediately** — user clarified the window starting
on the first *move*, not placement, is deliberate: it's the mechanism for correcting a
just-placed stop to the intended price within 5 seconds of moving it, and starting the
window at placement instead would cut that correction window short whenever the correction
itself takes a few seconds to make. `HandleStopUpdate` is back to the pre-session logic
(window starts on first move). **Do not change this without asking again** — see memory
`claudetracker-initialstop-window-intentional`.
