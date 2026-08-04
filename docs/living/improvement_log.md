# Premium Desk — Improvement Log

**Status:** Living. THE place all improvement ideas land and get tracked to a fate.
Sources: nightly evening-report reads (`evening_reads/`), morning-brief words,
incidents, user ideas, P&L analysis. Protocol (handoff S94): every session reads
the latest evening narrative → adds ideas here → user signs off → implement →
measure in the sim → record the verdict. **No idea dies in a chat log.**

Statuses: `proposed` → `approved` → `implemented` → `measuring (n=X)` → `KEEP / REJECT / PARKED`

| # | Idea | Source | Added | Status | Fate / evidence |
|---|---|---|---|---|---|
| 1 | Pre-event entries: skip or size-down the EOD set on WAIT days (we sent full notional pre-JOLTs; EOD was worst stream −$805) | 08-03 evening read ("do not carry full notional into the print") | 08-04 | **measuring** | timing + `playbook_wait` recorded per trade; decide after ~10 WAIT days |
| 2 | Pivot-wing condor variant: wings at S2/S1/R1/R2 instead of EM±wings | 08-03 evening read (their suggested structure) | 08-04 | **approved-pending** | pivots now captured daily (`gexlog.pivots`); build as 6th stream when sample design ready |
| 3 | Playbook-scenario resolution tagging → later test "trade the primary scenario" as a stream | 08-03/08-04 playbook (primary hit on 08-04) | 08-04 | **implemented (capture)** | `gexlog.playbook` stored daily; evening pass to tag which trigger resolved — tagging TBD |
| 4 | Wall/flip PROXIMITY as entry-quality tag ("at the wall ≠ above it with cushion") | 08-04 morning notes (flip 5.5pt away) | 08-04 | **implemented (capture)** | `flip_proximity`, `borderline_regime` recorded; use as filter only after data |
| 5 | All-or-none condor rule (cancel surviving wing if the other stands down) | 08-04 user question | 08-04 | **rejected (for now)** | day-1 partial (call-wing-only) was BETTER than full condor would've been; per-leg P&L design favors independent wings; revisit if partials bleed |
| 6 | Sim daemon rc=1 (08-03) — recheck | 08-04 incident | 08-04 | **open** | reran 08-04 without visible error; watch tomorrow's 14:28 run |
| 7 | Day-type normalizer: map "HIGH VOLATILITY" forecast (currently → unknown) | 08-04 brief | 08-04 | **proposed** | small; decide bucket (own class vs TREND-adjacent) |
| 8 | Trigger-daemon task fired 08:33 not 08:29 (Windows trigger boundary, wrapper can only delay) | 08-04 incident | 08-04 | **implemented** | trigger moved to 07:33 CT + wrapper 08:29; verify 08-05 open |
| 9 | Chain recorder crashed silently at 08:25 (pythonw, no stderr) | 08-04 incident | 08-04 | **measuring** | relaunched with logging; root-cause from tomorrow's log if it recurs |
| 10 | Evening task registered after its start boundary → never fired day 1 | 08-05 incident | 08-05 | **implemented** | manual retry-loop caught 08-04; task fires correctly from 08-05 |
| 11 | VIX-regime band scaling (widen band VIX>25) — validated in the 1,183-session backtest, not yet live | gexlog repo backtest | 08-04 | **parked** | VIX ~16 now; wire `band_k(vix)` into the gameplan when VIX regime shifts or after base sample accrues |
| 12 | Rich-credit vs thin-credit asymmetry: day-1 flies (fat credits) beat far condors (thin credits) on the trend day | 08-04 P&L | 08-04 | **measuring** | hypothesis: min-credit floor higher than $0.10, or credit-scaled sizing; needs ≥20 days |

## How to add a row
One line per idea, always with a source and a date. When acted on, update status
in place and put the evidence (numbers, commit, file) in the fate column. Weekly:
sweep `proposed` rows → approve/reject with the user.
