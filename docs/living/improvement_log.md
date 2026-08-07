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
| 13 | Capture VIX-up-with-rally "protection bid" flag (their emphasis 2 days running; our 1990-study says not bearish — record, don't trade) | 08-04/05 evening reads | 08-05 | **measuring** | `vix_change` in daily_summary; intraday VIX path not yet captured |
| 14 | Wing width responsive to event days ("if holding, use wider wings" — we are fixed 25pt) | 08-05 evening guidance | 08-06 | **proposed** | needs the minute-data sims to price wider wings honestly |
| 15 | Wing-independent vs both-together vs hold-to-expiry exits | 08-05 user question + fly evidence (+686 vs ~+100 vs −570) | 08-06 | **proposed (sim question)** | replay all three exit modes over the 2-yr minute data |
| 16 | Combo (BAG) atomic orders — orphan cure | 08-05 incident (−$730) | 08-06 | **implemented (combo-first + fallback)** | RTH-only, so first live proof = 08-06 open; fallback = old path |
| 17 | Premarket-data days (08:30 ET cluster) clear BEFORE our bell — WAIT shift unnecessary on those days; distinguish premarket vs intraday catalysts in the wait rule | 08-05 evening (Productivity 08:30 ET) | 08-06 | **proposed** | wait rule currently keys on playbook text only |
| 18 | Anchor condor/fly SHORTS at Call/Put Wall (not EM band) in POSITIVE gamma — walls confirmed to-the-handle 40+ days | archive read | 08-07 | **proposed (high)** | our gexlog stream does this; make it the primary positive-gamma anchor, test wall vs EM containment split by regime |
| 19 | FADE their forecast label: HIGH-VOL-in-positive-gamma & CHOP-with-catalyst are self-defeating (CHOP 0/26) — stop weighting day_type; weight signal+band | archive read (28% acc) | 08-07 | **proposed (high)** | drop forecast_type from any gating; keep as recorded field only |
| 20 | Negative-gamma SCHEDULED-EVENT days: reduce size / widen wings / stand aside — EM breaks concentrate here | archive read (EM-hit False cluster) | 08-07 | **proposed (high)** | needs regime (pos/neg) from brief + event calendar; both captured |
| 21 | Negative gamma + HIGH sector dispersion → range holds (condor-friendly, contra their advice) | archive read (~6 days) | 08-07 | **proposed** | capture sector dispersion from market_context; test as a condor-GO filter |
| 22 | Manage at 50% of max profit (recurring their rule) — we hold to acceptance/time-stop | archive read | 08-07 | **proposed (sim question)** | replay 50%-TP vs current exit on the 2-yr minute data + forward |
| 23 | Skew short call TIGHTER than short put at RSI>80 (their asymmetric-skew instruction) — we run symmetric | archive read | 08-07 | **proposed** | rsi_14 captured; add a skew variant stream |
| 24 | Gap-into-Call-Wall fades at open in positive gamma — pre-position bear-call | archive read (~20 days) | 08-07 | **proposed** | gap_note + walls captured; test |
| 25 | Enter income POST-print (IV crush) not into it — already partly done via WAIT; formalize as the edge, not just risk-avoidance | archive read | 08-07 | **measuring** | WAIT-day entries; measure post-print vs at-open |
| 26 | Their signal MOST trustworthy on neg-gamma scheduled-event days — use as a stand-down/directional trigger | archive read | 08-07 | **proposed** | inverse of #20; same inputs |
| 27 | Regime (pos/neg gamma) + sector dispersion + RSI not yet captured per day for these tests | archive read | 08-07 | **implemented (capture)** | add gamma regime, dispersion, rsi to daily_summary from the brief |

## How to add a row
One line per idea, always with a source and a date. When acted on, update status
in place and put the evidence (numbers, commit, file) in the fate column. Weekly:
sweep `proposed` rows → approve/reject with the user.
