# Wall-source P&L backtest — SPEC (for approval before running)

**Purpose.** Rank the 0DTE gamma-**wall sources** (gexlog / ThetaData-computed / MenthorQ,
plus a wall-free baseline) by trading the desk's ACTUAL `gx_bps`+`gx_bcs` strategy at each
source's walls and comparing forward P&L. Everything except the walls is held identical and
replicates the live sim's rules. **No rule may be silently changed** (the earlier pass changed
fills→mid, exits→hold-to-expiry, and dropped days — all wrong).

This spec is derived from the live code: `options_gameplan.py`, `options_trigger_daemon.py`
(exits `thesis_broken`, fills `place_combo`/`close_combo`), `market_calendar.py`.

---

## 1. Calendar (was the bug — now fixed)
Every date derived from `market_calendar.py` (rules-based, holidays + early closes).
`prev_trading_day` used for OI-record and prior-close spot. **No hardcoded/JSON holiday list.**
Early-close days (July 3 when 7/4 is a weekday, day-after-Thanksgiving, Christmas Eve): SPX
options close **12:15 CT** → time-stop and settlement move to 12:15 CT on those days.

## 2. Universe
All SPX 0DTE sessions in the overlap where the needed inputs exist. **No day is dropped for
convenience.** If a source cannot form a valid OTM condor on a day (e.g. MenthorQ's gamma wall
sits through spot — happens 47/77 days), that is a **recorded outcome for that source**, not a
skipped day: see §7. gexlog/TD/baseline always straddle spot, so they trade every day.

## 3. Entry
- **Time:** 08:30 CT (`ENTRY_AT`) on normal days. On **WAIT/event/blind** days the open- and
  gexlog-stream entries shift to **09:05 CT** (`options_gameplan.py` ~L246-265) — determined
  deterministically from that day's saved gexlog brief (`playbook_wait`, or missing/stale brief
  ⇒ assume WAIT). We replicate that flag from the saved raw brief.
- **Structure:** two verticals, `WING=25`, strikes rounded to 5 pt, **size = 1** (`execution.size`).
  - `gx_bps` Bull Put: short put @ putWall, long put @ putWall−25
  - `gx_bcs` Bear Call: short call @ callWall, long call @ callWall+25
- **Wall source per book:**
  - **gx** = gexlog published putWall/callWall (per-side gamma; the desk's live inputs)
  - **td** = ThetaData per-side walls (max call-γ above spot / max put-γ below), our calibration
  - **mq** = MenthorQ 0DTE ps0 (put) / gw0 (call)
  - **fx** = fixed-offset baseline: short strikes at spot ± OFFSET (default 35), no wall info

## 4. Fills (marketable touch — NOT mid)
Live daemon fills marketable (`place_combo` BUYs the bag at the ask; `marketable()` crosses).
Backtest convention, from TD NBBO at the entry timestamp:
- **Enter (sell the condor):** credit = short_bid − long_ask, each vertical (cross to fill).
- **Exit (buy it back):** debit = short_ask − long_bid (cross to fill).
- **Fees:** real IB **$1.63 / contract / execution**, charged on BOTH entry and exit, all legs
  (`options_trigger_daemon` S112). 4 legs entry + up-to-4 legs exit.
- **Sensitivity run:** also report mid-fill, to bound the fill assumption (S113: real fills were
  ~touch, median at touch, 86% ≤ mid — so touch is the honest/conservative primary).

## 5. Exits (intraday — whichever fires FIRST) — `thesis_broken`
Priced at the **then-current TD NBBO** (touch), not 4pm intrinsic:
1. **Level acceptance:** spot holds **beyond the short strike** (call: above; put: below) for
   **≥10 min** (`level_accept_mins`), wicks reset the clock → close the breached vertical.
2. **Regime invalidation:** spot crosses **HVL** against the trade since entry (PIN setups: entry
   positive-gamma → now negative-gamma) → close. *(HVL source per day = open question, §8.)*
3. **Time-stop 14:45 CT** (12:15 CT on early-close days) → close whatever's open, flat before the
   0DTE gamma cliff.
Each side (bps/bcs) exits independently on its own level-acceptance; regime/time-stop close both.

## 6. Data required from ThetaData (bigger pull than entry+settle)
- Entry NBBO per leg at the entry time (have the mechanism).
- **Intraday underlying path** (SPX index, ≤1-min) to detect level-acceptance timing + HVL crosses.
- Option NBBO **at each candidate exit timestamp** (breach-accept time, HVL-cross time, 14:45).
- Per-day **HVL** and **entry regime** (spot vs HVL at entry).
- Calendar via market_calendar (no pull).

## 7. MenthorQ handling (must be honest)
MQ 0DTE walls sit **through spot 47/77 days** — not a drop-in condor. Options, pick one:
- **(A)** Trade MQ only where its walls are OTM; report P&L **and** the coverage ("MQ produced a
  tradeable condor on N/77 days") so the wins aren't cherry-picked silently. *(recommended)*
- **(B)** Trade MQ mechanically even when ITM (directional) — reflects naive use, but mixes a
  different trade in. Report separately if at all.
Never report MQ's subset total next to gx/td full-sample totals without the coverage caveat.

## 8. Open questions (need your call before running)
1. **HVL source** for regime-invalidation: gexlog doesn't publish HVL in `levels`; the live plan
   gets it from — MenthorQ? gexlog `gex_flip`? Confirm the desk's actual source so we replicate it.
2. **Sizing:** keep size=1 (clean per-lot comparison) or replicate any EM-based sizing? (`execution.size=1` today, so 1 is faithful.)
3. **Intraday granularity:** 1-min SPX is enough for a 10-min acceptance rule; confirm TD index
   intraday is available at that resolution for 2026.
4. **Sample:** overlap is Apr-6→Jul-15 (3-way w/ MQ) or 05-13→09-04 (gx-vs-td, TD calib days).
   For a real ranking we want **multi-year incl. stress** — but MQ history caps at 07-15 and TD
   0DTE + our calibration must be extended. Decide sample now vs after a pilot.
5. **Realized cross-check:** where the live sim actually traded gx_bps/gx_bcs (Aug window), we can
   validate the backtest's gexlog column against the REAL fills/exits — a truth anchor. Do it?

## 9. Outputs
Per-day and aggregate, per wall source and per strategy (bps/bcs): P&L, win%, PF, avg credit,
avg/max loss, exit-reason mix (accept / regime / time-stop), MQ coverage. Deltas vs gexlog.
Self-contained HTML + CSV. Engine unit-verified on hand-traced days (winner, breach-exit,
time-stop) before any aggregate is reported.
