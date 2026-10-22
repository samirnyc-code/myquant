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
