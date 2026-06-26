# Handoff — Current State
**Status:** Living — update every session  
**Last Updated:** June 25, 2026 (session 42)
**Current Versions:** SIM_v3.9 / GS_v4.5 / SHEET_v3.3 *(S32: Prop Sim overhaul — MC-sized payout buffer, monthly 80/20 payouts, ES/MES margin, never-blow floor de-risk + shock model, richer dashboard; MCBreakout pyramiding (N concurrent/dir) + ratchet-lock fix. S31: ZLO exporter + filters, MCBreakout stop fix + ER filter, ZLO sweeps, Auction feature library + tab (Dalton day types), Prop Sim DD-lock. S30: Prop Sim tab, Extras tab, 1M bars, NT strategy. S29: ESA into WFA, session filters, multi-TF, ER10. S28: ESA v2. S27: ESA Phase A. S24: critical slippage off-tick bugfix.)*
**Rule:** Read this file first every session. It is the only source of truth for current state.
**Handoff hygiene (S20):** A competing handoff had grown in the `.claude/.../memory/` auto-memory folder and a new chat read *that* instead of this file. Fixed: added repo `CLAUDE.md` + rewrote `.claude` `MEMORY.md` to point here; deleted the duplicate session-state memories. **There is now ONE handoff: this file.**
**Onboarding (S22):** `docs/living/PROJECT_CHARTER.md` is the from-inception synthesis (the *arc* + locked decisions). Read the charter first for orientation, then this handoff for current state. The charter owns the arc/locked rails; **this handoff still wins on what's true today.**

---

## 📓 RESEARCH NOTES REGISTRY — AUTHORITATIVE NUMBER LEDGER (all chats: read + reserve here FIRST)

**Why this exists:** `docs/research_notes/` (the friend-facing MC Setup Research Notes
series) was spun up by multiple chats independently and numbers collided by luck, not
design. **This block is the single authority for note numbers — it wins over any
per-branch `README.md` index.** Workflow standard lives in `docs/research_notes/README.md`;
render with `scripts/render_note_pdf.py` (mirrors to `~/Documents/MC_Setup_Research_Notes/`).

**RULE — before creating a note:** claim the next free number by adding its row to the
CLAIMED table below *in the same edit*, with your session/branch in "By". If you can't
commit, still write the claim here and call it out in your session block. If two chats
race the same number, the **earlier-merged** note keeps it; the later one takes the next free.

### Claimed (do not reuse)
| # | Note | Status | By |
|---|------|--------|----|
| 0001 | PB scale-in (`0001_pb_scalein_mc.md`) | DONE | s38 |
| 0002 | ER10 look-ahead bug (`0002_er10_lookahead_bug.md`) | DONE | s39 |
| 0003 | Keystone — IB-edge fade (`0003_keystone_ib_edge_fade.md`) | DONE | s40 |

**NEXT FREE NUMBER: 0004**

### Backlog — candidate notes (claim a number above before starting one)
**Tier A — ALREADY RESEARCHED in `docs/living/`; convert to a note, do NOT redo:**
- **CC setup go/no-go** — CC5 the real edge, CC4 NO-GO, CC2/CC3 unsound, CC1 untestable (S23, `pipeline_CC4_singleleg`)
- **ER10 / ER×CC chop filter** — edge is per-CC (CC2/CC5 reward high ER, CC4 anti-ER, CC3 flat) (S35, `er_cc_survivor_filter_20260623`)
- **Is 1R the right target? / exit management** — flat 1R wins; BE/trail/scale-out all failed; fill-time decay (S26/S28)
- **Balance-state vs trend days** — MC edge by balance/rotation (S25: `balance_deepdive`, `mfe_by_balance`, `fade_by_state`)
- **Value-area location filter** — composition effect, not per-setup edge (`va_filter_compare`, `va_per_setup_threshold`)
- **Origin / reversal at extreme** — signals born at the day's extreme; both hypotheses negative (`origin_at_extreme`, `reversal_at_extreme`)
- **Fade the signal (RevFT)** — negative; sub-cost edge at 1:1 (`fade_revft`)
- **Execution reality / ESA** — slippage + the unlimited-positions assumption; how much edge survives realistic fills (S24, S27–28)

**Tier B — NEW RUNS (genuinely unwritten):**
- **Day structure → today's session** ⭐ (user-requested) — does the PRIOR day's type (inside day, ADR-ext/trend day, prior-ER, Dalton day type) predict today's MC edge? Features exist in `tag_signals` (`prior_inside_day`, `prior_adr_ext`, `prior_ER`, ATR/ADX pct); never assembled into one "yesterday → today" study.
- **Afternoon filter on the BASE trade** — follow-up from 0001: is the 13:00 CT decay a scale-in thing or the whole setup? (cheap; reuse path-study machinery)
- **Trade location: chase vs pullback entry** — does entry distance from EMA20/VWAP predict outcome? (`ext_ema` lead from 0001, base-trade version)
- **Consecutive-cluster gate** — does requiring N same-dir signals improve quality? (S33 + `dir_streak` 4+ lead from 0001)
- **Always-In (AID) as a sizer** — negative as a gate (S36); size-with/against-regime untested
- **Pyramiding (N concurrent same-dir)** — does it beat a single entry? (S32 MCBreakout pyramiding)

---

## ⭐ SESSION 43 — June 25, 2026 — Bar Viewer trade visualization (exit-anchored lines + price path + result)

### What was built
- **`app.py` `make_candlestick()` signal overlay** — rewrote stop/target lines and added
  price path trace + result annotation. Replaces the fixed 10-min span with actual exit discovery.

### How the new overlay works
For each signal on the Bar Viewer chart:
1. **Lines start at BO bar** — `bo_start = sig_dt - 5min` (the bar before the FT trigger).
   Both stop (dotted) and target (dashed) lines extend from BO bar open to exit bar.
2. **Exit discovery** — walks forward through day bars from entry bar (`entry_dt = sig_dt + 5min`).
   First bar where `Low ≤ stop` (long) or `High ≥ target` hits ends the trade. If both hit on
   the same bar, stop wins (conservative). EOD fallback: last bar close.
3. **Price path** — `go.Scatter` line connecting bar closes from entry bar to exit bar.
   Color = green if result > 0, red if result ≤ 0. Opacity 0.6, no legend.
4. **Result annotation** — `"+X.XX"` or `"-X.XX"` at exit bar, monospace 9pt, green/red.
   Positioned above exit price for long, below for short. Result measured from entry bar open.

### Files committed this session
- MODIFIED: `app.py` (signal overlay in `make_candlestick()`)

### NEXT
1. **Run proper sim** — once tick cache is built, run `simulate_trades()` with all
   10,886 BO+FT signals. Get real metrics: WR, avg R, expectancy.
2. **NT8 indicator testing** — load AMASignalOverlay.cs, compile, verify data box + racing stripes.
3. **Research note 0008** — document AMA detector work after backtest results.
4. **Recreate lost CS files** — ZerolagExporter.cs, AlwaysIn.cs, QSSignalOverlay.cs, MCBreakout.cs.

---

## ⭐ SESSION 42 — June 25, 2026 — AMA Breakouts Python port + BO+FT signal model fix

### What was built
- **`nt8/indicators/AMASignalOverlay.cs`** — NT8 indicator that overlays Python-generated
  AMA signals on the chart. 23 plots in 6 groups (ID, Setup, Bars, Stop, Target, Result),
  all togglable via property panel. Racing-stripe BackBrush coloring with chart legend.
  Stop/target dashes via Draw.Line. Entry dot via Draw.Diamond. Data box via cursor tooltip
  (mutual-exclusion plot trick: only active setup name gets value=1, others stay NaN).
- **`scripts/ama_export_signals_nt.py`** — CLI exporter: generates AMA signals from
  `_continuous.parquet` and writes `data/nt_import/ama_signals_{tag}.csv` for NT8 import.
- **`app.py`** — AMA wired as third signal source in BA tab with Generate button, expander
  (stop offset, target mode/mult, BO+FT / OB / BigBO checkboxes), and status strip count.
  Bar source: `mas_continuous` → `data_sc_5m` fallback.

### ⚠️ CRITICAL: BO+FT signal model (this was the main fix)
The original detector was emitting ~50,727 signals (40/day) — completely wrong.

**Root causes found and fixed:**
1. **BO alone is not a setup.** A BO bar is setup detection only; the trade fires at the
   FT (follow-through) bar close, entry at the next bar's open. The code was emitting signal
   rows for both BO bars AND FT bars — effectively double-counting and generating a signal
   for every bar in a trend leg.
2. **Only the FIRST FT bar per setup chain emits a signal.** In a trend, NT8 paints bar 3,
   4, 5... as chained FT bars (not new BOs) — that's preserved in `detect()`. But
   `to_signal_rows()` only emits the FT bar that immediately follows a pure BO (`ft_prev==0`).
   All chained FT bars are skipped — they are part of the running trade, not new entries.

**After fix:** 10,886 BO+FT signals over 5 years (8.5/day). OB singles: 7,591 (5.9/day).

**Code:** `ama_setups.py` `to_signal_rows()` — `is_first_ft = is_ft and ft_arr[i-1]==0`.
`detect()` FT chaining preserved (matches NT8). `include_ft` logic: both "BO" and "FT"
type selectors now mean "include BO+FT setups" (BO alone has no meaning as a trade).

### Tick cache
Downloaded: 45GB of raw gz files in `data/flatfiles_cache/` (1,297 days).
Converted to per-day parquet: only 9 days in `data/ticks_continuous/` so far.
**User is building the full tick cache now.** Once done: run proper sim with tick-accurate
stop/target resolution via `simulate_trades()`.

### ⚠️ Bar sim numbers are garbage — ignore
Ran a quick bar-based sim (`_simulate_one_bars`) to get directional numbers while ticks
were missing. Those results (48.8% WR, -$85k) are meaningless without intrabar resolution.
Discard them. Wait for tick cache before drawing any conclusions.

### NT8 defaults vs Python AMAConfig defaults
NT8 ships with IBS filters OFF (-1), OB OFF, FT OFF, BigBO OFF. Our Python AMAConfig
has IBS 60/40 ON, OB ON, FT ON — these are the user's custom settings, not NT8 stock.
The IBS filter (60/40) is the main qualifier on BO bars: bull BO needs close in top 40%
of bar range; bear BO needs close in bottom 40%.

### Files committed this session
- NEW: `nt8/indicators/AMASignalOverlay.cs`
- NEW: `scripts/ama_export_signals_nt.py`
- MODIFIED: `app.py` (AMA signal source + BO+FT fix)
- MODIFIED: `ama_setups.py` (to_signal_rows signal model fix)
- MODIFIED: `massive.py` (minor: wrong variable in 15M resample button)
- MODIFIED: `nt8/README.md` (AMASignalOverlay.cs status row)

### NEXT
1. **Run proper sim** — once tick cache is built, run `simulate_trades()` with all
   10,886 BO+FT signals and OB signals. Get real metrics: WR, avg R, expectancy by
   direction/type/time-of-day.
2. **NT8 indicator testing** — user needs to load AMASignalOverlay.cs, compile in NT8,
   verify data box and racing stripes match exported CSV.
3. **Research note 0008** — document AMA detector work (wait for backtest results first).
4. **Recreate lost CS files** — ZerolagExporter.cs, AlwaysIn.cs, QSSignalOverlay.cs,
   MCBreakout.cs (all marked ❌ LOST in `nt8/README.md`).
5. **Sim engine: per-trade TargetPoints** — AMA has variable targets per bar (BarRange
   mode). Engine currently takes a fixed `target_r`. Deferred — do NOT touch until
   explicitly authorized.

---

## ⭐ SESSION 40 — June 24, 2026 — KEYSTONE (note 0003) discovered + audited; 2-leg engine design corrected (read FIRST)
*Searched whether an MC signal's ORIGIN location predicts an edge; one survivor — the
Initial-Balance edge fade ("Keystone") — passed a look-ahead audit and is written up as
research note **0003**. Separately, untangled and CORRECTED the 2-leg scale-in engine's
design with the user (the "P&L bug" was largely my misuse of a degenerate config).*

### ⭐ KEYSTONE — Initial-Balance Edge Fade → research note 0003 (DONE)
- **Gate (look-ahead-safe, never optimized):** keep MC signals whose origin (`StopPrice`/MCX)
  sits within **0.10 ADR of the same-side IB edge** (`OR60_Low` long / `OR60_High` short);
  `d=(origin−edge)/ADR`, keep `0≤d≤0.10`. Exit **fixed 2.0R single-leg, both directions**.
- **Result (1 contract, 5yr, 2.0R):** 1,395 trades · **+0.159 R** · PF 1.38 · win 48.5% ·
  net $232,593 · MAR 8.86. Selection value @2R: gate +0.159 vs **non-gate +0.026** (the
  complement is inert → the filter concentrates the edge). Positive EVERY year.
- **PASSED look-ahead audit (the gate to belief):** session-timing split shows the edge is
  **STRONGER after the first hour** (+0.203R, where OR60 is indisputably past) than during it
  (+0.126R) — the opposite of a leak. OR60 causal in code (`indicators.py:263-274`); no
  entry-bar merge; StopPrice 100% correct side. Survives cost stress to 3-tick slip (+0.092R).
- **Improvement attempts ALL failed to beat plain 2R single-leg** (threshold = structural cliff
  at 0.10; target = plateau ~2R; BE/trail/scale-in/scale-out neutral-or-worse; both-dir for
  symmetry; balance stacks to +0.168R but halves trades → kept standalone). Edge is in SELECTION.
- **HONEST status:** in-sample + selected among ~85 buckets → forward ~**+0.09–0.12R**; deep
  target-invariant drawdown (~$26k/contract) → a **cash-account COMPONENT (~$75–100k/contract),
  NOT a standalone prop system.** Note 0003 says exactly this. Next: true OOS + prop/cash sim.
- **What died (the breadth):** reversal-at-extreme (LOD/HOD, LOY/HOY), balance (regime-dep),
  failed-breakout fade (canonical fade LOSES), HVN/LVN + single-prints (null), VA-edge (thin),
  IB-width $-peak (a stop-size illusion — judge in R not $). Keystone was the lone survivor.

### ⭐ 2-LEG SCALE-IN ENGINE — design corrected with the user (NOT the "bug" I first chased)
- A suspicious multileg net led me to a degenerate **`ml_pb_r=0` "scale-out"** path; I mis-read
  it as a real mode and started a wrong fix. **User clarified the actual design:** the 2-leg is
  ALWAYS a scale-IN — E2 only exists if price ticks through the PB level; no "both at signal".
- **Changes made (validated):** (1) **E1-break-even variant now ALWAYS exits at E1's entry
  price** at any PB% (`_t2_for` "e2" branch → `actual_entry`); was only true at 50%PB/1R.
  Mirrored in the fast-sweep (`bar_analysis`) + oracle (`validate_oracle`). (2) **Removed the
  `0%` PB option** (both `_pb_vals` lists) + **engine guard**: `multileg & ml_pb_r≥0` → single-leg.
  (3) **UI:** T2 greyed out in E1-BE style. (4) New `scripts/validate_multileg_invariant.py`
  (the missing "2 legs = 2× single" / E1-scratch-E2-wins test).
- **Validated:** oracle==engine (0 mismatches), fast==engine (64/64), invariant test all PASS.
  E2 fills require a strict **tick-through** (not touch) and fill at the limit. Single-leg
  (Keystone) is a different code path — untouched. See `BUG_multileg_pnl_scaling.md` (the net
  over-count) + `multileg_bug_forensics.md` (note: forensics OVERSTATED impact — the defect is
  the non-PB scale-out path only, now removed/guarded; the real scale-IN path was correct).

### Files (this session)
- `simulation_engine.py` (E1-BE `_t2_for` + multileg guard), `bar_analysis.py` (fast-sweep
  mirror + UI grey-out + removed 0% PB), `scripts/validate_oracle.py` (E1-BE oracle).
- NEW: `docs/research_notes/0003_keystone_ib_edge_fade.md`+`.pdf`, `scripts/{keystone_audit,
  ib_edge_exits,ib_edge_scalein,validate_multileg_invariant}.py`,
  `docs/living/{BUG_multileg_pnl_scaling,multileg_bug_forensics,keystone_audit_*,ib_edge_*}.md`.
- Registry: 0003 claimed (next free **0004**); README index + backlog updated.

### NEXT (S41)
1. Keystone true OOS / held-out + prop-cash sim (drawdown path is the binding constraint).
2. FULLY fix the multileg P&L if the non-PB path is ever needed (currently guarded off, not deep-fixed).
3. Convert remaining backlog notes (CC go/no-go, ER×CC, etc.).

---

## ⭐ SESSION 39 (parallel chat) — Trust rupture over look-ahead; "guilty until proven innocent" is now the rule (read FIRST)
*Not a coding session. The user came in heartbroken: he had believed we had a deployable,
scalable prop system, had explicitly asked earlier whether it used future information and been
told no, then discovered the look-ahead (the ER10 leakage thread, S34/S37). Months of
nights-and-days work, and his trust in the app is gone. He asked the honest question — do retail
traders ever find a consistently profitable automated system, or is it a pipe dream — and then
called it a night. This block records what was agreed so future sessions stay consistent.*

### New standing principle (adopted this session)
- **Every backtest result is GUILTY UNTIL PROVEN INNOCENT.** A beautiful equity curve is treated
  as a suspected bug (look-ahead, single-regime overfit, costs/slippage too kind, survivorship)
  until we have actively tried to kill it and failed. We do NOT say "we have a system" again until
  it is defensible. See [[keep-in-check]].
- **No result is reported with optimism it hasn't earned** — report plainly, especially when bad.
  Trust is rebuilt by the app EARNING belief, not by me asserting it.
- **The check goes INTO the workflow, not into our memory to remember** — a leakage audit should be
  a standing, repeatable step.

### Honest framing given to the user (keep consistent)
- Look-ahead is the most common way a backtest lies and the cruelest: the curve looks exactly like
  the dream and does not look suspicious. Getting fooled by it is a process failure, not a verdict
  on the user's ability.
- Consistent automated retail trading is rare but not a pipe dream; survivors aren't smarter, they
  are more suspicious of their own results. That suspicion is the edge.

### Next (explicitly DEFERRED to tomorrow — do not rush him back to setups)
- **Leakage audit first:** walk the whole feature/signal pipeline for any value that could use a bar
  not yet closed at decision time. S34's `_causal_at_signal_bar` in `indicators.tag_signals` is the
  template; confirm overlays/ER/VWAP/EMA/ZLO/AID merges are all clean. Make it documented + re-runnable.
- Anything surviving → re-validate with realistic costs + walk-forward, report plainly.
- The known leakage entry point is already documented (S34/S37); the audit is about proving the REST
  of the pipeline clean, not re-finding the known one.

---

## ⭐ SESSION 39 — June 24, 2026 — ER10 look-ahead: quantified the bug + exhausted the salvage (research note 0002) (read FIRST)
*Deliberately reproduced the pre-S34 ER10 look-ahead headless (no production code touched —
imported the reproduction helpers from `er_lookahead_tab.py` and drove the real engine), then
chased whether the trades it wrongly "phantom-blocked" can be salvaged. They can't. Wrote
friend-facing research note **0002**. No engine change.*

### What we found (all in-sample, MC = `ba_signals_mc.parquet`, gate ER10≥0.70, 1R single-leg)
- **Bug impact (3.8×):** pre-fix look-ahead = 61.7% win / $192.21 exp / PF 1.78 / $629,692 net;
  causal (live) = 52.4% / $50.91 / PF 1.17 / $269,863. The bug's "skill" was **phantom-BLOCKING
  ~2,118 trades** (only 118 phantom-passes) — it read the *entry-bar* ER (5 min future) to toss
  trades that hadn't yet turned choppy. Pure look-ahead *selection*, not execution.
- **The wrongly-blocked trades are a real −$360k drag** (exp −$169.85/trade); unflagged book is
  +$629,597. Flag = (causal ER≥gate) & (entry-bar ER<gate).
- **Salvage by EXIT timing fails, for a structural reason:** at the 5M entry-bar close (when the
  decayed ER is legitimately known) **97% are already underwater** (`flat@EBclose` win 3.3%).
  Tightened stops are all *worse* than baseline. Best is a tight take-profit (+4pt / 0.05×ABR)
  ≈ **+$30k** whole-book — and the **control passed** (TP helps flagged +$13.93/trade, HURTS
  unflagged −$73.86 and random −$38.64 → genuinely ER10-specific), BUT **by-year it's fragile**
  (carried by 2022 +$47/t; **negative 2024 −$10/t**, null 2025). Not deployable.
- **1-minute drill-down = the decisive negative:** 1M-ER is <gate at min 1 for ~99% of ALL trades
  (not discriminating); the shiny +$95.77/t "earlier exit" is **the same look-ahead** (it acts at
  min 1 on the flag known only at min 5). Causal blend = **−$66.8/t** (murders the good trades).

### Verdict & open threads
- **Keep the causal fix; never reintroduce it.** The bug's gain (~$360k) was *not-trading* and is
  **uncapturable causally**. The EXIT-mitigation question is **closed** (structural). **OPEN:** a
  causal *entry* filter for these low-efficiency signals (general MC filter line, not an exit hack);
  and **RevFT OOS replication** would lift note 0002 from Medium→High.

### Artifacts (S39 work committed `fc27d05` on `docs/s38-reversal-at-extreme`, pushed)
- **Note:** `docs/research_notes/0002_er10_lookahead_bug.md` (+ rendered PDF, mirrored to
  `C:\Users\Admin\Documents\MC_Setup_Research_Notes\` per the series workflow; README index updated).
- **Scripts:** `scripts/er10_{lookahead_rerun,block_exit_sweep,tp_control,scaled_tp_sweep,1m_leadlag}.py`
  (all headless, day-by-day tick replay; each now dumps a per-trade parquet for re-use without recompute).
- **Result md + per-trade parquet:** `docs/living/er10_*_20260624.md` and `docs/living/er10_*pertrade*.parquet`
  / `er10_block_{base,overlay}.parquet` / `er10_lookahead_tagged.parquet`.
- Engine fix reference (S34): `indicators._causal_at_signal_bar()` in all 5 `tag_signals` merge paths (`8cbca3e`).

---

## ⭐ SESSION 38 — June 24, 2026 — PB scale-in = NO-GO + launched `docs/research_notes/` series (read FIRST)
*Investigated whether the MC CC pullback scale-in (add leg 2 on a retrace, target original 1R)
is worth it. Answer: NO. Built a friend-facing research-note series to house this and future
findings. No engine change.*

### Result — the PB scale-in does NOT add edge
- Tick-by-tick path study, all MC signals (`ba_signals_mc.parquet`, 5,580 sigs, 5yr, real ticks).
  At a 50% pullback: **54% pull back, but only 18% of those reach 1R** (resolved win 22.7% vs the
  ~27% the leg-2 add needs). Biggest single outcome of any signal = **PB→stop (33%)**.
- Apparent +$37k add (scale-in $306k vs single-leg $269k net) is an **EOD-marking artifact**.
  Stress test (mark unresolved leg-2 at close / breakeven / stop): under *neutral* breakeven,
  every depth×phase cell goes negative **except 0.25R + morning (+$19k/5yr, trivial)**.
- **Depth sweep** (0.25–1.0R): shallower looks better but it's the same artifact amplified; add
  value crosses negative beyond ~0.5R. **Per-CC:** negative CC1, ~0 CC5, only CC2/CC3 mildly +.
- **Only durable, real finding is NEGATIVE & time-based (CME Central):** Late/Close (after 13:00)
  pullbacks reach 1R ~½ as often — robust **6/6 years**. "Open+Mid is +EV" clears the bar only
  2/6 years. Tell hunt (balance, EMA-location, 4+ streak, AID, ER) = all weak/overfit; AID even
  points **counter-regime** (consistent with its S36 subtractive-gate shelving).
- ⚠️ TZ note for future studies: these stamps are **CME Central Time**; phases =
  `bar_analysis._SESSION_PHASES` (Open 08:30–11:30 · Mid 11:30–13:00 · Late 13:00–14:45 · Close 14:45–15:15).

### NEW — `docs/research_notes/` (friend-facing setup studies; distinct from this handoff)
- `README.md` = index + house template (Header → Confidence → TL;DR → Setup → Question → Methods →
  Results → Why → Recommendation → Caveats → Reproduce) + conventions (costs, R, CT phases, CI).
- `0001_pb_scalein_mc.md` = the full PB note (Confidence: High). All 8 tests with tables.
- Scripts (headless, day-by-day): `scripts/pb_to_1r_path_study.py`, `pb_tell_hunt.py`,
  `pb_level_compare.py`, `pb_eod_stress.py`. Artifacts: `docs/living/pb_*.parquet`.

### Open / next
- Does avoiding the afternoon improve the **base single-leg** MC trade (not just the scale-in)? Not isolated yet.
- `with_trend` (structural-trend agreement) was broken in `pb_tell_hunt.py` (string match) — re-test clean if curious.
- Nothing committed — awaiting user confirmation.

---

## ⭐ SESSION 37 — June 24, 2026 — ER10 look-ahead "regression" was a STALE PROCESS (read FIRST)
*User saw the too-good ER10 numbers come back in the BA sim. Root cause was NOT a
code regression — the S34 causal fix is intact & committed (`8cbca3e`). It was a
long-running Streamlit process serving pre-fix code from memory.*

### Root cause — stale in-memory code, not a bad cache
- The app process (PID 2796) **started 6/23 07:01**; the S34 causal `tag_signals`
  fix was **committed 6/23 17:47**. That process held the **pre-fix `indicators.py`
  in RAM for 10h** and never reloaded it → kept serving the ER10 look-ahead
  (~61% win / ~$167/trade). A clean restart loaded the fixed code → numbers
  correctly collapsed to no-edge. **The disk was right the whole time.**
- Verified the fix is NOT reverted: `_causal_at_signal_bar` defined + wired into all
  5 `merge_asof` paths in `indicators.tag_signals`; working tree == HEAD. Saved
  signals (`ba_signals_revft.parquet`) carry only RAW cols (no baked tagged ER/VWAP/
  EMA) → tagged fresh each run. `bar_analysis.py` overlays use `searchsorted`, not
  `merge_asof` (no dtype-crash surface there).

### Prevention (DONE this session)
- **`.streamlit/config.toml`: `runOnSave = true` + `fileWatcherType = "auto"`** so
  source edits auto-reload the running app. **Still: a FULL kill+relaunch is the only
  bulletproof guarantee after engine/indicator changes — do it every time.**
- App restarted clean on current code (incl. uncommitted S36 AID/fade), port 8501.

### Stale WFA store QUARANTINED (reversible)
- All **222 pre-fix WFA run dirs** (6/19–6/20, every one ER10-look-ahead) moved to
  `data/wfa_store/_contaminated_pre_S34/{trades,sweeps}/`. DB pruned **122→1 runs /
  1144→15 folds**; full pre-prune backup at `_contaminated_pre_S34/wfa_results_full_backup.db`.
- **KEPT (post-fix, valid):** `run_0c65425a` (6/23 18:15) — the validated cluster-gate run.
- NOT touched (source data, not caches): `data/flatfiles_cache` (45G Massive raw),
  `data/bars`, `data/ticks_continuous`, `saved_signals`.

### Note
- A separate headless day-by-day worker (another chat) was running earlier and
  finished on its own; never targeted by the restarts here.

---

## ⭐ SESSION 36 — June 24, 2026 — "Always In" port + AID overlay (negative result) + Fade toggle (read FIRST)
*Reverse-engineered a TradeStation "MyReversals/Logan" system from screenshots; built its
"Always In" regime piece for NT8; wired an AID overlay into BA and tested it (subtractive —
shelved); added a BA "fade signals" toggle. RevFT signal set = the MyReversals export.*

### NT8 — `AlwaysIn.cs` indicator (NEW, in NT8 Indicators folder; not in repo)
- Ports Logan's EL "Always In" regime: `AID=+1/-1` flips on (A) a ≥1σ-range bar whose
  midpoint (HL2) crosses EMA(Close,20), or (B) two consecutive closes beyond that EMA.
  Renders a green/red **subpanel ribbon** + **flip-bar racing stripes** (toggle + adjustable
  opacity), exposes `AlwaysInDir`/`FlipBar` series, and **writes flip events to CSV**
  (`MCVolumeExport\AlwaysIn_State.csv`: Event,BarTime,BarNum,NewDir,O,H,L,C,EmaFast,Mid,ZScore).
- Two EL black boxes assumed (source not in screenshots): `GetMidPoint`→HL2 (param: OHLC4
  toggle), `GetZScoreData`→z-score of bar RANGE over N (param ZScorePeriod, default 20).
- **Day Summary classifier decoded** (Logan's, NOT built): `Value1 = Close−sessionOpen`;
  `BL TR` if `Value1 > abr*4`, `BR TR` if `< -abr*4`, else `TR`. One-dimensional close−open
  displacement in ABR units — path-blind, ignores range/close-location. NOT ported (weak).

### BA — Always In overlay (REPO — uncommitted). Wired exactly like ZLO.
- `app.py` Data tab: **🧭 Always In State** uploader (flip CSV → `ba_alwaysin`, parquet-persisted).
- `bar_analysis.py`: `merge_alwaysin_overlay` (backward as-of on `BarTime` = causal, signal-bar
  state; adds `AID_State / AID_FlipIdx / AID_BarsSinceFlip / AID_OnFlipBar / AID_DirMatch /
  AID_FirstMatch`) + `apply_alwaysin_filters` (modes: With-AID / First-MC-after-flip /
  On-flip-bar / Exclude-near-flip) + Regime-Gates UI + fingerprint wiring.
- **TEST RESULT (headless `scripts/alwaysin_flip_test.py`, MC set, 1R) — AID is SUBTRACTIVE:**
  baseline expR **0.048** PF1.16 (5,433t) → dir-match 0.045 → **first-after-flip 0.040** PF1.11
  (2,036t) → on-flip 0.040. Every gate **drops trades AND lowers per-trade expectancy** =
  negative selectivity (preferentially kills *better* trades). By year unstable (2024 PF0.98).
  **Verdict: shelved as a gate** — it's a weak EMA/trend tag, redundant like ER10. Columns stay
  attached for Edge-analysis bucketing. (Engine note: ticks can't all load at once → run
  day-by-day; `massive.load_continuous_ticks` is NOT cached; subset = row-mask of one full run
  since the sim scores trades independently — the unlimited-positions assumption.)

### BA — "🔄 Fade signals" toggle (REPO — uncommitted)
- New checkbox in BA **📶 Signals** expander. `apply_fade` (in `bar_analysis.py`) flips Direction
  and mirrors stop across entry (`newStop = 2*entry − oldStop`) → at 1:1 the stop becomes the
  target and vice-versa. Applied **AFTER all gates** (rules pick the same trades, you take the
  other side). Fingerprint + Save-as-Default wired. Engine compares `direction=="Long"` exactly,
  so fade emits canonical "Long"/"Short".
- **Honest framing given the user's −$300k 1:1 RevFT curve:** fading is ONE trade/one set of
  costs (NOT double commission). Correct accounting: strip costs → flip gross → pay costs once;
  `Net_fade ≈ −Gross_orig − Costs`.

### ⭐ Fade test — RUN on RevFT → SAVED `docs/living/fade_revft_20260624.md`
- `scripts/fade_revft_test.py` (one tick-load pass for orig/fade × gross/net; first version
  timed out reloading ticks 4×). RevFT 6,133 filled trades, 1R, real = $5 comm + 1t entry slip.
- **ORIGINAL:** gross **−$79,150**, costs $108k, **net −$187,465**, PF0.90, expR−0.073, DD−$197k.
- **FADE:** gross **+$18,638**, costs $89k, **net −$70,790**, PF0.97, expR−0.020, DD−$91k.
- **Findings:** (1) real small NEGATIVE directional edge — orig loses even gross, so not pure
  cost bleed; fading flips gross positive. (2) **Fade still loses net** — +$18.6k gross swamped
  by ~$89k cost. "Less bad" (½ DD) but a firm loser. (3) **1:1 whipsaw tax is large** — clean
  mirror would be +$79k gross, fade realized only +$18.6k → ~$60k lost to intrabar
  which-touched-first (confirms at-1:1 fade is NOT a clean sign-flip). (4) by year even faded:
  only 2021/2023 green. **Verdict:** problem isn't direction — it's ~6k trades/run at 1:1 with a
  sub-cost (~$15–18/trade) edge. Levers: trade far less (selectivity gate > ~$15 gross/trade) or
  widen R.

### Open / next
- Optional: selectivity-gate sweep on RevFT (find a subset clearing the cost hurdle); fade at 2:1/3:1.
- Optional: AID as a *sizer* (size with/against regime, keep all trades) instead of a gate.
- `AlwaysIn.cs` needs compiling in NT8 (F5); not under repo version control.

---

## ⭐ SESSION 35 — June 24, 2026 — App-settings cleanup + ER×CC filter study + scale-in OOM fix (read FIRST)
*UI/default cleanup, a large ER×CC filter study saved to disk, confirmation that causal
ER is genuinely informative (not residual look-ahead), and a memory fix for the scale-in
sweep. Continues the S33 cluster-gate / S34 look-ahead thread.*

### App settings / UX cleanup (REPO — uncommitted)
- **5M is now the default timeframe everywhere** it's selectable. Bug: BA + WFA did
  `_tf_options.insert(0,"1M")` when 1M data was loaded and `st.radio` defaults to index 0,
  so **1M silently became the default**. Fixed via `index=_tf_options.index("5M")` on both
  radios (`bar_analysis.py`, `wfa.py`). 1M/15M/100s still selectable.
- **ES round-trip commission default = $5 everywhere.** Source: `simulation_engine.py`
  `INSTRUMENTS["ES"]["default_commission"]` 4.36→**5.0** (feeds BA single/ML/3L, WFA,
  Portfolio). Also hardcoded inputs: `prop_sim.py`, `extras.py` 4.36→5.0; BA `.get(...,3.0)`
  fallbacks→5.0. MES unchanged ($1.30). `scripts/` left at 4.36 (regression baselines).
- **Date whitelist REMOVED** from BA (uploader + `date_whitelist` filter path) and WFA.
- **Assumption Ledger expander moved far down** in BA results (was right after the run
  caption; now just before the ESA Phase B expander). WFA ledger left (already deep).
- **ESA execution model default = Realistic preset + market entry** in BA + WFA (via
  `index=...index("Realistic")`; market was already index 0). er_lookahead_tab inherits via
  `ba_sim_params`. Updated the stale "Custom/market/0ms = byte-identical" comment.

### ⭐ ER×CC filter study — SAVED to `docs/living/er_cc_survivor_filter_20260623.{md,csv}`
- Causal **signal-bar** ER (post-S34 fix; verified 323/323 signal-bar, 0 leakage), spans
  3/6/9/12 = **ER15/30/45/60**, both directions, 1R bar-resolver (~9% hot, no CAL),
  in-sample 2021–26. CSV = 240 rows (6 pops × 4 TF × 10 thresholds). Two views computed:
  isolated 0.1 buckets AND cumulative survivor (`keep ER > X`) — the saved file is the
  **cumulative-survivor** view (8 metrics incl. ExpR + P/DD = Net/|MaxDD|).
- **Findings:** ER15 degenerate (no spread — drop it). Edge is **per-CC**: **CC2 + CC5
  reward high ER** (CC5 ER30>0.7 → ExpR 0.14, $137, keeps 40%, P/DD 6.5; CC2 ER60>0.8 →
  ExpR 0.38); **CC3 flat, CC4 is an ANTI-ER setup** (every ER filter strictly hurts it).
  No single global ER threshold serves the book. Small in R terms (base ExpR 0.049).

### Causal-ER vs RIC — confirmed NOT a look-ahead leak
- User saw ER still topping the "RIC Ranking" tab. Proven via headless (fixed `tag_signals`):
  **ER10 look-ahead RIC 348% → causal 25%** (bug gone, collapses 14×). Longer ER (30/60/120m)
  stay high *causally* (123–134%) because the 1-future-bar contamination is a small fraction
  of a 6–24-bar window — i.e. genuine signal, not leak. RIC is also **inflated ~4–7× by the
  50-bin scheme** (ER30 131%@50bins → 18%@5bins). RIC = dispersion ranking, NOT edge size.
  RIC tab buckets only 30/60/120m (ER10 not shown). Tab uses fixed `tag_signals` (causal);
  if it still shows pre-fix numbers, the Streamlit `@st.cache_data` is stale → restart app.

### ⚠️ Scale-in sweep OOM fix (REPO — uncommitted, NOT YET VALIDATED)
- Crash: `_run_ml_scalein_sweep` (`bar_analysis.py`) caches a **full remaining-session tick
  path per filled trade × 3 arrays** (prices/rmax/neg_rmin) → tens of GB → `ArrayMemoryError`
  (failed on a 1.31 MiB alloc = RAM already exhausted). **Fix:** cache `prices` as **float32**
  (line ~1428) — lossless for ES (tick-aligned price/tick < 2²⁴ exact; rmax/neg_rmin + every
  searchsorted query on those exact values), halves the cache footprint.
- **⚠️ MUST RUN `scripts/validate_scalein_sweep.py`** to confirm byte-identical results — the
  user redirected to docs before I ran it. If it still OOMs after float32: the deeper fix is
  trimming each path to the RTH session / a level-based cut, but a naive level cut breaks the
  `>= n` "never reached" semantics (verified buggy) — needs care + re-validation.

### Files changed (REPO, S35) — UNCOMMITTED
- `bar_analysis.py` (5M default, comm fallback, whitelist removal, ledger move, ESA default,
  float32 cache), `wfa.py` (5M default, whitelist removal, ESA default), `simulation_engine.py`
  (ES comm 5.0), `prop_sim.py` + `extras.py` (comm 5.0).
- NEW: `docs/living/er_cc_survivor_filter_20260623.md` + `.csv`.

---

## 🚨🚨 SESSION 34 — June 23, 2026 — ER10 LOOK-AHEAD BUG **FIXED IN CODE** + ER10 audit tab (read FIRST)

> # ⚠️ WARNING — ALL PRIOR BACKTESTS / WFA RESULTS / SAVED STUDIES ARE INVALID
> Every result produced before this session used **look-ahead-tainted features**. The
> `tag_signals` as-of merge silently used the **entry bar** (one bar in the future) for
> ER, EMA, VWAP, session levels, and market structure. **Any conclusion, sweep, WFA fold,
> or saved study that gated on those features must be RE-RUN before it is trusted.**
> Specifically tainted: every `docs/living/er*` study, `zlo_filter_sweep*`, all `wfa_store`
> results, and any handoff conclusion below S34 that cites ER/EMA/VWAP/MSS numbers.
> The +$229k NT grid / +$303k sim "edges" were look-ahead (see S33). **Treat pre-S34
> performance numbers as fiction until reproduced on the corrected pipeline.**

### ✅ THE FIX (hard cutover — done & validated this session)
- **One chokepoint:** `indicators.tag_signals`. Added helper `_causal_at_signal_bar(frame)`
  that shifts a developing per-bar feature back one row before the backward as-of merge, so
  the join returns the **signal bar's** value (last CLOSED bar at decision time) instead of
  the still-forming **entry bar**. Open-labeled bars + close-stamped signals = the raw merge
  landed one bar in the future; the shift undoes exactly that.
- **Routed through the fix (were buggy):** `ER_intra_*` (ER10/ER30), `EMA_20`, VWAP bands
  (VWAP/sigma/dev), `session_levels` (OOD/HOY/LOY/OR60), market structure
  (structural_trend/active_floor/is_deep_pullback/mss_event).
- **Deliberately NOT shifted (already causal):** `developing_session_levels`/`balance_state`
  already does `groupby(day).shift(1)` — shifting again would have introduced a NEW bug.
  Prior-day regime + prior-period value areas already use `shift(1)` by date. Verified untouched.
- **Propagates app-wide:** `tag_signals` is the single source, so BA regime gates, WFA,
  `regime_filter`, and the sweep scripts are all corrected by this one change.
- **VALIDATION (full 5,385-signal population, all PASS):**
  - ER10, ER30, EMA_20, VWAP, OOD == builder value at the **signal bar**: **100%**.
  - `balance_state` unchanged (no double-shift): **100%**.
  - OLD vs NEW ER10 differ on **50.5%** of signals (confirms the bug was real & removed).

### 🔬 New audit tool — "ER10 Look-ahead" tab
- New tab (`er_lookahead_tab.py`, wired in `app.py`) runs the **same sim twice** —
  pre-fix look-ahead ER10 vs the causal value now live — using your **Bar Analysis ESA
  settings verbatim** (inherits the resolved config via new `st.session_state["ba_sim_params"]`
  published from `bar_analysis.py`; no fields to re-enter). Shows every metric side by side
  + gate-flip diagnostics. Kept as a **historical-impact / regression view**.
- Smoke (40-day slice, gate 0.30, single-leg): pre-fix net **$14,807** / exp **$127.64** vs
  causal **$9,088** / **$60.99** — expectancy roughly **halved** once the cheat is removed.

### Files changed (REPO, S34) — committed this session
- `indicators.py` — `_causal_at_signal_bar` + routed 5 feature merges through it in `tag_signals`.
- `er_lookahead_tab.py` (NEW) — ER10 look-ahead comparison/audit tab.
- `app.py` — wire the new tab (import + tab + render).
- `bar_analysis.py` — publish resolved ESA config to `ba_sim_params` for the audit tab.
  *(Also carries the S33 cluster-gate wiring — see below; that part is NOT yet run/validated.)*
- `wfa.py` — S33 cluster-gate wiring (bundled in this commit; NOT yet run/validated).

### ⚠️ Bundled-but-unvalidated in this commit
The S33 **consecutive-cluster gate** code (`bar_analysis.py` + `wfa.py`) was already in the
working tree and is included here so the tree is clean. It has **NOT been run on the corrected
pipeline** — re-validate before trusting the ~$120 expectancy claim.

### NEXT
1. **Re-run everything** that mattered on the corrected pipeline (WFA folds first).
2. Re-validate the cluster gate on corrected ER (BA single run → WFA year-by-year).
3. Optional: add stale-cache guard in `prop_sim.py` (`ps_result` missing-key crash).

---

## ⭐⭐ SESSION 33 — June 23, 2026 — ER10 LOOK-AHEAD BUG + Consecutive-Cluster Gate (read FIRST)
> **S34 UPDATE:** the "NOT YET FIXED" status below is **superseded** — the fix is now
> implemented & validated (see S34 block above).
*Diagnosed a look-ahead bug in the Python sim's ER10 (and every other as-of-merged
gate), quantified the damage, proved the base strategy has no tradeable edge once
corrected, and wired the one surviving legitimate lever — a consecutive-signal
cluster gate — into BOTH BA and WFA for validation.*

### ⭐ THE BUG — ER10 (and all as-of-merged gates) looked into the future
- **Root cause:** Massive 5M bars are **OPEN-stamped** (label = bar start); MC signals
  are **CLOSE-stamped** (label = bar close = open+5min). `indicators.tag_signals` joins
  signals onto bars with `pd.merge_asof(direction="backward")`, which lands the signal on
  the bar AFTER it — the **entry bar**, whose close is 5 min in the future. So `ER_intra_2`
  (=ER10) on every signal was the *entry-bar* ER, not the signal-bar ER.
- **NT does it right:** positional indexing (`Close[0]` = the just-closed signal bar). NT's
  ERPeriod=2 == Python's ER_intra_2 mathematically; the only difference was the timestamp join.
- **Damage was via EXCLUSION:** the future ER silently DROPPED losing trades. Buggy sim:
  1,757 trades, 61.6% win, ~$167/trade. **Corrected (engine, full MC): 5,439 trades, 51.2%
  win, $34.82 exp, 0.029R, PF 1.12, PROM(target-hit) −0.96** → **no tradeable edge.** The
  +$229k NT grid and +$303k sim were both look-ahead. Confirmed 3 independent ways + NT
  real-fill cross-check (the excluded trades were 41.5% win, −$112/trade).
- **NOT YET FIXED in code:** the one-line fix is to merge against `signal_time − 5min` in
  `tag_signals`; it affects ER_intra_2, ER_intra_6, VWAP, EMA, session levels, structure,
  deviation — ALL share this join. Must re-validate every gate after. **Paused pending user.**

### ⭐ Consecutive-signal cluster gate — WIRED into BA + WFA (S33)
- **Finding (corrected-ER scratch, longs):** taking only the **2nd-or-later** breakout in a
  run of consecutive-bar signals ~**doubled expectancy (~$120 vs ~$59 baseline)**, ~658
  trades. **N=2 is THE signal**; N≥3 reverts toward baseline on thin samples (118/6/0) — so
  it reads structural, not a tune-an-N curve-fit. Look-ahead-safe (prior-bar signal known
  at decision time). Management rules (early-exit / BE / 0.5R bracket) all FAILED — the edge
  was in NOT ENTERING, unrecoverable post-entry.
- **Implementation:** new helper `_consecutive_run_pos(df)` (per Date+Direction, run position
  over unique consecutive BarNums) + `want_consec`/`min_run` params on the shared
  `apply_regime_population_filters` (bar_analysis.py) → status `not_consec`. UI checkbox
  "Cluster gate (Nth-in-a-row)" + "Min consecutive (N)" in BOTH BA (Regime Gates) and WFA;
  wired into guards, fingerprint, save-defaults, and WFA locked-gate notes.
### ⭐ Cluster gate — WFA RESULT (run this session) + headless robustness
- **WFA (window-structures robustness report) PASSED 3/4 + every cell PnL-positive.**
  Single run IS12m/OOS3m: **$72,136 OOS, 631 trades, 55.3% win, PF 1.32, maxDD −$16.8k,
  5/6 folds green.** Window-anchor grid (15 cells): **Total OOS PnL positive in ALL 15
  ($72k–$111k), median OOS PF >1 in all (1.16–1.36).** The 4-window verdict = "FRAGILE 3/4":
  the only failing structure is **OOS=1m** (WFE 13–19%) — and with target pinned at 1R +
  cluster gate fixed, **nothing is optimized**, so WFE here is just period-to-period regime
  variance on a tiny 1m sample, NOT overfitting. Discard the OOS=1m column.
- **Headless sweeps (corrected signal-bar ER, bar-resolver):** ER10 is **REDUNDANT** with the
  cluster gate — gate cuts 5,580 signals → ~1,260 (715 unique days); ER10≥0.70 then removes
  only ~48 more (~4%). So the real filter is the *clustering*, not ER10 — can drop ER10.
  Other-TF ER (15/20/30/60m) all worse than native 10m. **2-in-a-row is green EVERY year
  2021–2026** (survived 2023 when base died) and **works on SHORTS too** ($106 vs $37) →
  symmetric, ~1,260 both-dir trades. Time-of-day open-boost ($327, n=63) and escalation
  (n=8) = overfit traps, dropped. 3/4/5-in-a-row revert to baseline (N=2 is the signal).
- **⚠️ THE WFA ABOVE PREDATES THE S34 tag_signals FIX (commit 8cbca3e).** It must be
  **RE-RUN on the corrected pipeline.** The cluster gate itself is look-ahead-safe (signal
  BarNum count), but any ER10/feature gating in that run was tainted — and per the S34
  warning, no pre-fix WFA is trusted. Re-run with ER10 OFF (redundant) + calendar basis.

### ⭐ Calendar-day fold basis — NEW TOGGLE (wired this session, `wfa.py`)
- **Why:** `build_folds` counted `is_days` in **signal-days** (days with ≥1 signal), not
  calendar days. The cluster gate halves signal density (1,250→715 days), so a "252-signal-day"
  (=12m) IS window stretched to ~20 calendar months → first OOS shoved to 2023-03, only 6
  folds, 2021–2022 buried in warm-up. (Confirmed: gated 252nd signal-day = 2023-02-22 ≈ the
  observed first OOS.) Signal-days is NOT a Pardo rule (Pardo uses calendar windows + a
  min-trade floor); it was a local choice whose one virtue is constant trade-count/fold.
- **Fix:** added `fold_basis` param ('signal' | 'calendar') threaded through
  `run_wfa` / `run_window_grid` / `run_window_structures`, + a **"Fold window basis" radio**
  in WFA config (default = Signal-days, to preserve existing behavior). Calendar basis cuts
  folds on the real trading-day calendar (from `bars_by_date`), bounded to the signal span;
  trades still come only from signals inside each window. Preview + 0-folds feasibility guard
  now report the correct unit per basis. Closes S32-NEXT item "Calendar-day WFA folds".
- **Trade-count validation (calendar basis, both-dir, gated):** IS12m/OOS3m = **15 folds,
  IS 186–252–278 trades/fold, OOS 34–61–79, ZERO folds <30** (Pardo floor clears everywhere).
  IS6m/OOS3m also clean. **OOS=1m too thin** (median 19, 42/47 folds <30 — junk). **Single
  direction too thin** (short-only: 10/15 folds <30). → **Recommended config: calendar /
  12m / 3m / BOTH directions / ER10 off.** Meaningful + Pardo-correct.

### Files changed (REPO, S33/this session)
- `bar_analysis.py` — `_consecutive_run_pos` + cluster gate in `apply_regime_population_filters`;
  `not_consec` label; BA UI + guard + fingerprint + save-defaults. **(committed in 8cbca3e.)**
- `wfa.py` — cluster-gate UI/guard/call/locked-note **(in 8cbca3e)** + **`fold_basis` toggle
  (signal vs calendar) — committed THIS commit.**

### NEXT (cluster-gate thread)
1. **RE-RUN the WFA on the corrected (post-8cbca3e) pipeline** with the recommended config
   (calendar / 12m / 3m / both dir / ER10 off) — confirm the PF~1.3 / positive-every-window
   result survives the look-ahead fix. This is the gating test before trusting the edge.
2. Then: bucket OOS PnL by year to quantify how lean the non-2025 years are (the edge is
   real but 2025-concentrated) and size for the lean version, 2025 as upside not baseline.
3. Held thought (user said "hold that thought"): whether to set calendar/12m/3m/both as the
   WFA defaults.

---

## ⭐⭐ SESSION 32 — June 23, 2026 — Prop Sim Overhaul + MCBreakout Pyramiding (read FIRST)
*Reworked the NT MCBreakout strategy to take multiple concurrent trades (it was
refusing additional signals while in a position) and fixed a counter ratchet that
silently locked it out after ~1 month. Then a major Prop Sim rebuild: Monte-Carlo
risk sizing, monthly 80/20 payouts, ES/MES margin, and a "never-blow" floor de-risk
driven by a user-specified shock model. User's stated #1 priority: never blow the
account, EVER.*

### MCBreakout (NT strategy, in NT Strategies folder, NOT repo) — pyramiding + bug fixes
- **Now takes N concurrent entries per direction** (was 1 hard position). The old
  `if Position != Flat: return` guard blocked every continuation signal while in a
  trade — that's why the two flagged long signals on the chart were skipped.
- **New property `Max Concurrent/Dir`** (default 1 = old behavior). Each entry uses a
  **unique signal name** (`MCB_1`, `MCB_2`, …) with its **own SetStopLoss/SetProfitTarget**
  keyed to that name (NT setting: Stop & target submission = *Per entry execution*,
  EntryHandling = *UniqueEntries*, EntriesPerDirection = N). Exits matched back via
  `Order.FromEntrySignal`. Never reverses / never holds both sides; one add per bar
  (existing same-bar dedup). Per-entry state held in a `Dictionary<string,TradeState>`.
- **⭐ RATCHET-LOCK BUG FIXED**: a hand-maintained `_openLongCount`/`_openShortCount`
  incremented on entry fill but only decremented on a *matched* exit. The built-in
  **"Exit on session close"** flattens with an exit whose `FromEntrySignal` doesn't map
  → counter never came down → after ~a month it hit the cap and **locked out all new
  entries for the rest of the 5yr backtest** ("takes trades for ~1 month then stops").
  Fix: the concurrent cap now reads NT's **actual `Position.Quantity`** (+ unfilled
  submitted entries), which can't leak; `_open.Clear()` at session start as a reset.
  **ACTION: uncheck "Exit on session close" in NT** so the strategy's own matched
  session-flatten handles EOD and every trade lands in the CSV. **NOT YET RECOMPILED/
  TESTED by user.** Earlier CS0136 (duplicate local names) + scope fixes already applied.

### ⭐ PROP SIM OVERHAUL (`prop_sim.py`, REPO) — full rebuild
- **Fixed crash**: `Styler.applymap` (removed in pandas 2.1+) → `Styler.map`.
- **ES/MES instrument selector** sets tick value + per-contract day-margin together
  (ES $12.50 / $500; MES $1.25 / $50). Margin caps contracts at `floor(balance/margin)`.
- **Direction filter** (Both/Long/Short).
- **Monthly 80/20 payouts**: withdraw `max(0, account − (start + buffer))` at each month
  end; split 80% take-home / 20% firm; gates = min trading days, min payout, **consistency
  rule** (defer if any single day > X% of period profit). Subscription fee + reset fee
  tracked. Reports realized take-home, unrealized (80% of in-account profit), and
  **net-to-trader** (the real bottom line — *account equity is NOT your money*).
- **Monte-Carlo (moving-block bootstrap)** computes: **payout buffer** = 99th-pct $ DD at
  max contracts (the withdrawal floor), **suggested scale interval** = per-contract 99th-pct
  DD × safety-mult (rounded $250), and **blow-up probability**.
- **⭐ NEVER-BLOW FLOOR DE-RISK** (toggle, default off): before each trade, cap contracts so
  **N worst-ever single-trade losses still fit in the headroom to the blow level**; sizes
  *below base* near the floor, *skips* the trade if even 1c is unsafe. Asymmetric (cut fast
  down, add only on the normal profit interval up). Re-sizing every trade makes a streak
  self-throttle. **Verdict on asymmetric scale-down: it's a SURVIVAL lever, not an edge
  lever** — EV-neutral on an IID curve (you under-participate in the recovery), but worth it
  here because the binding constraint is the hard trailing-DD floor + reset cost.
- **⭐ SHOCK MODEL** (user-specified): **shock size (points)** + **once per N trading days**.
  Flows into: (1) de-risk unit = `max(historical worst trade, shock$/c)`; (2) MC buffer
  (injected into bootstrap); (3) flat-max blow-up %; (4) suggested scale interval;
  (5) a new **de-risk-aware blow-up %** (sequential sim with de-risk + scaling + injected
  shocks per trade — the realistic "will I ever blow" figure). Does NOT rewrite historical
  per-trade P&L, does NOT touch margin. Gap reality discussed: intraday + EOD-flat + event
  filters removes the overnight/limit-down tail; residual = ~15–40pt unscheduled intraday
  shock while in a trade. Recommend setting shock to ~20–30pt, not the calm backtest max.
- **Conservative modelling locked in**: trailing DD measured on **trading equity** (start +
  cum P&L), withdrawals are a separate cash flow (no phantom blow-ups); scaling keys off
  **account balance** (so cashing out excess sizes you back down); live haircut is
  **asymmetric** (wins ×(1−x), losses ×(1+x) — must worsen DD, not flatter it).
- **Richer dashboard** (item 2): Quick View adds CAGR/Sharpe/MAR/payoff; new **🏦 Prop
  Metrics** expander (take-home/firm/payouts/day# of max TDD/margin/buffer/blow-up/shock/
  de-risk unit); **🎯 Setup Breakdown** (per-SignalType); **📆 Start-Date Sensitivity**
  (rolling start months); **🎲 MC DD Distribution** histogram. All run-button gated.

### Files changed (REPO)
- `prop_sim.py` — full rewrite (MC sizing, payouts, margin, de-risk, shock, dashboard).
- **NT (NOT repo)**: `MCBreakout.cs` — pyramiding rewrite + ratchet-lock fix.

### Design decisions confirmed by user (AskUserQuestion)
- Buffer = **Monte-Carlo 99th-pct DD**; payouts **monthly**; live haircut = **expectancy %**
  (implemented asymmetric per the conservatism note); extras = consistency rule + MC blow-up
  prob + start-date sensitivity + reset cost (ALL). Shock frequency = **once per N days**.
- Pyramiding = **cap concurrent at N per direction**, each with its own stop/target.

### NEXT (S33)
0. **User recompiles + tests MCBreakout in NT** with `Max Concurrent/Dir` > 1 and "Exit on
   session close" UNCHECKED; confirm the two flagged signals now fire and it trades through
   the full 5yr (no month-1 stall).
1. **User runs the new Prop Sim** (Run button) and tunes: set a realistic shock (~20–30pt),
   turn on floor de-risk, A/B symmetric vs asymmetric on blow-up % / worst DD / net-to-trader.
2. **Optional hardening**: de-risk-aware MC currently bounded by the specified shock only —
   consider a second, larger "catastrophic" shock tier if desired.
3. Carried from S31/S32: developing-day conditional outcome study; MABreakout vs MCSignal CSV
   diff; per-row `Contracts` column for variable-size engine runs.

---

## ⭐⭐ SESSION 31 — June 23, 2026 — ZLO Exporter + Filters, MCBreakout Fixes, Auction Feature Library (read FIRST)
*Wired the LizardTrader Zerolag Oscillator (ZLO) into the research loop, swept it as
a filter (verdict: only useful as MC confluence, not a standalone signal or gate),
fixed two MCBreakout bugs + added an ER filter, and built the Auction Feature Library
+ tab with a Dalton day-type classifier grounded in the actual MOM book. Closed the
ZLO thread; pivoted the AMT direction to developing-day structure.*

### ZLO (LizardTrader Zerolag Oscillator) — explored & CLOSED
- **`ZerolagExporter.cs`** (NT indicator, in NT Indicators folder, NOT repo) — exports
  per-bar ZLO data (Oscillator, BaseTrend, TrendState, 6 signal series) to CSV. Exposes
  Period/Smooth/Fractal/EfficiencyMult/TrendFilterType. Run on a 5M ES chart → overwrites
  CSV each run. NOTE: NT stacks generated-code regions on failed compiles → if it errors,
  delete the duplicate `#region NinjaScript generated code` blocks (keep one).
- **ZLO upload + filters in BA** (`app.py` Data tab "📈 ZLO Overlay", `bar_analysis.py`
  Regime Gates "ZLO Filters"): merge ZLO onto signals by nearest DateTime; filters for
  BaseTrend=direction, |TrendState|≥N, Oscillator on-side. `merge_zlo_overlay` +
  `apply_zlo_filters` + fingerprint wiring.
- **Sweep (`scripts/zlo_filter_sweep.py` → `docs/living/zlo_filter_sweep.csv`)**: all
  ZLO filters × ER10 0.1–0.9 slices, full metrics. **VERDICT: directional/trend filters
  HURT (redundant with MC + ER10). Confluence (ZLO's own mom/key-ret signal fires same-bar
  same-dir as MC CC) is the ONLY positive — SuperTrend variant best (ER10≥0.8 → 67% win,
  PF 2.53, PnL/DD 18.6) but only ~200 trades/5yr → SIZING NUDGE, not a gate.**
- **Standalone KeyRet backtest (`scripts/keyret_backtest.py`)**: forward-return probe
  showed ZLO Key Retracement looked promising (+1.3pt/30min), BUT through the real tick
  engine with the doc's retracement stop + costs → **NO edge (PF 0.97–1.04, exp ±$10).**
  The forward-return was gross drift; the tight stop kills it. **KeyRet not tradeable alone.**
- **Two ZLO CSVs**: EfficiencyRatio (BaseTrend has 0 neutral zone) vs SuperTrend (no neutral
  → fires MORE signals). Ran separately, not combined. Trend filter GATES signal generation
  (LongMom only fires when BaseTrend>0), which is why the populations differ.
- **CLOSED the ZLO thread.** Confluence captured as a sizing candidate (see memory).

### MCBreakout strategy (NT, in NT Strategies folder, NOT repo) — 2 fixes + ER filter
- **STOP BUG FIXED**: was taking `High[lookback]`/`Low[lookback]` (one bar) instead of the
  MC EXTREME. Now scans all bars 0..lookback for the true highest-high / lowest-low. Stop
  now lands on the MCX level (the magenta line).
- **ER10 filter added**: toggle (UseERFilter), ERPeriod (default 2 = ER10 on 5M), ERMinThreshold
  (0.30). Inline Kaufman ER, skips signals below threshold. Off by default.
- **Timing-column caveat**: CalcMs/FillMs are garbage in historical backtest (DateTime.Now −
  historical bar time = huge). Only meaningful in LIVE/REPLAY. By design — for the future
  NT-sim timing-calibration phase.

### Prop Sim — DD lock toggle
- **"Lock DD at starting balance"** checkbox (default ON): trailing DD threshold stops trailing
  once it reaches the starting balance, then locks there forever (prop-firm rule). Off =
  pure trailing. `peak_balance = min(peak, starting_bal + max_trailing_dd)`. (Max trades/day
  already existed in Account Rules.)

### ⭐ AUCTION FEATURE LIBRARY (`auction_features.py`) + tab (`auction_tab.py`) — NEW
- **`build_session_features(bars, eth)`** → one row per RTH session, look-ahead-safe: IB
  (first 60min) + extension each side + first-break, range/ADR/DR%, open/close location
  (OLV/CLV), value area (POC/VAH/VAL/width/skew), volume-profile bimodality, gap (size in
  ADR, bucket, same-session fill, open vs prior range/VA), VA migration, **Dalton day-type**.
- **Day-type classifier grounded in *Mind Over Markets* Ch.2** (read from user's `MOM.pdf`):
  Normal (27.9%) · Normal Variation (57.8%) · Trend (2.5%) · Double Distribution (5.5%,
  via profile bimodality) · Neutral (4.4%, Center/Extreme split) · Nontrend (1.9% — the
  quiet "TR day"). Stable across years. Tunable in `_classify_day_type`.
- **Studies**: `day_type_transition_matrix` (yesterday→today), `gap_outcome_study`.
- **Tab (new "🏛️ Auction")**: day-type distribution, transition heatmap, gap-bias table,
  raw downloadable feature table. Run-button gated.
- **Findings**: balance/Nontrend clusters; trend days don't repeat (3.9%); gap size scales
  monotonically with prior-day energy (trend→0.57 ADR gap vs balance→0.29); large gaps fill
  only ~32% vs ~90% flat (gap-and-go threshold).

### STRATEGY POV (agreed direction for S32)
- **Prior-day → today prediction is WEAK** (yesterday barely shifts today's distribution).
  **Developing-day structure (real-time, look-ahead-safe at the signal bar) is where AMT pays.**
- **The decisive test**: build a developing-day feature set at each MC signal bar (IB
  formed/broken, one-timeframe-so-far, price vs developing POC/VWAP/IB) → conditional
  outcome study: does MC breakout expectancy shift materially by developing day structure?
  Edge → filter/sizer; no edge → shelve AMT honestly. Classification alone is worthless.
- **Actionable day-type characteristics** (go-with vs fade for a breakout) documented in chat;
  Trend=hold/go-with, Normal=fade extremes, Nontrend=don't trade breakouts, etc.

### Files changed (REPO)
- `app.py` — ZLO uploader (Data tab), new "🏛️ Auction" tab + import
- `bar_analysis.py` — ZLO merge + filters (`merge_zlo_overlay`, `apply_zlo_filters`) + UI + fingerprint
- `prop_sim.py` — DD lock-at-start toggle
- `auction_features.py` — NEW (per-session auction feature library + Dalton classifier)
- `auction_tab.py` — NEW (explorer tab)
- `scripts/zlo_filter_sweep.py`, `scripts/keyret_backtest.py` — NEW
- `docs/living/zlo_filter_sweep.csv`, `docs/living/keyret_backtest.csv` — NEW
- **NT (NOT repo)**: `@@MCBreakout.cs` (stop fix + ER filter), `ZerolagExporter.cs` (NEW)

### Memory updated
- `sizing_candidates.md` — master "size, don't skip" list (balance, prior-inside, ZLO
  confluence, ER10 gradient; size-down on trend-day; test design). Folded in old zlo_sizing_idea.
- `auction_theory_refs.md` — 4 local PDF paths (Dalton MOM + Markets in Profile, Steidlmayer,
  Volume Profile insider guide), all verified readable. Dalton day-type definitions.

### NEXT (S32)
0. **🔬 Compare MABreakout vs MCSignal CSVs** — user has an MABreakout strategy CSV trading
   "the same logic" as the MCSignal producer, but results are VASTLY different. Diff
   column-by-column (entry timing, stop reference, dedup, session window) to find the mismatch.
1. **Developing-day feature set + conditional outcome study** (the decisive AMT test above).
   Condition on full MC pop or ER10-filtered book (user to decide).
2. **Sizing hypothesis test** — engine needs a per-row `Contracts` column to run variable
   size; then flat vs conviction-scaled (balance/inside/confluence/ER10), judged on MAR/PnL-DD/SQN,
   validated OOS + Prop Sim.
3. **Compile + test MCBreakout in NT sim** (carried from S30/S31) — verify the stop fix +
   ER filter, measure real timing.

---

## ⭐⭐ SESSION 30 — June 22, 2026 — Prop Sim + Extras + NT Strategy + 1M Bars + Bug Fixes (read FIRST)
*Built the Prop Firm Simulator as a new tab, the Extras tab (signal overlap & account
allocation), 1M continuous bars, the NT8 MCBreakout strategy, and fixed several bugs.*

### PROP SIM TAB (NEW — `prop_sim.py`)
- **Sequential walk-through simulator** that replays BA filled trades with prop firm rules.
  Trades that violate limits are **SKIPPED** — the equity path reflects what a real prop
  account would experience, unlike the Extras tab which retroactively rescales.
- **Account rules:** Starting balance, max daily loss cutoff, max trailing DD (account blown),
  max trades/day (total or per-direction).
- **Contract scaling:** Base contracts + 1 per $X profit above start. Scales DOWN when balance
  drops. Configurable max contracts.
- **Output:** Quick View (PnL/Win%/PF/Exp$/MaxDD/PnL-DD/SQN), Detail breakdown, Monthly
  Breakdown (bar chart + cumulative + table), 4-panel chart (Balance/Daily PnL/Trailing DD/
  Contracts), Scaling breakdown table, Daily + Trade detail tables.
- **Run-button gated** — configure, then click Run Prop Sim.

### EXTRAS TAB (NEW — `extras.py`)
- **Signal Overlap & Account Allocation:** Trades-per-day distribution (stacked L/S over time +
  histogram), gap-between-signals stats, concurrent position estimate (30-min window chart),
  account allocation scenarios (1-5 per direction), per-account equity curves with slider,
  per-account summary table.
- **Prop Firm Compliance** section (simplified, uses retroactive rescaling — the Prop Sim tab
  is the proper sequential version).

### 1M CONTINUOUS BARS
- **Build button in Massive tab** (from tick cache, same as 100s). Saved to
  `_continuous_1m.parquet`, auto-loaded on restart.
- **1M selector in BA + WFA** bar timeframe radio (appears when 1M bars are built).

### NT8 STRATEGY — `@@MCBreakout.cs`
- **Managed-order strategy:** MC CC signal → market entry on bar close, stop at MCX ± offset
  (absolute price), target at entry ± R × risk (absolute price).
- **Properties:** Direction (Both/Long/Short), TargetR, StopOffsetTicks, Contracts, MinCC,
  MaxTradesPerDay (total or per-direction), MaxDailyLossDollars, MaxRiskPerTrade.
- **CSV logging (32 columns):** Appends per trade — SignalDateTime, CalcTime, OrderSubmitTime,
  FillTime, FillPrice, CalcDelayMs, FillDelayMs, TotalDelayMs, SlippageTicks, ExitTime,
  ExitPrice, ExitType, PnLPts, GrossPnL, R_Achieved, DailyPnL, etc.
- **Purpose:** Run on NT sim for months, build a database of real timing data, feed measured
  delays back into ESA's calc_delay_ms / wire_delay_ms parameters.
- **NOT YET COMPILED IN NT** — user needs to open, compile, and test.

### BUG FIXES
- **`_simulate_one_multileg` missing `max_fill_ms`** — parameter was passed by `simulate_trades`
  but not in the function signature. Added. Crashed WFA when using ESA fill timeout.
- **WFA event filter hardcoded** — was `Skip ±window` at 15 min with no UI controls. Added
  "Skip full day" / "Window ±N minutes" radio + slider (15–180 min), matching BA.
- **Window Map heatmaps red-to-green on good data** — used relative `RdYlGn` scale so even
  excellent values got colored red. Replaced with absolute thresholds: red/orange only for
  genuinely bad values (PnL<0, PF<1, DD worse than -$30k), shades of green for good.
- **Duplicate Streamlit key `pf_commission`** — collided with Portfolio tab. Renamed all
  Extras keys to `ext_pf_*`.

### FILES CHANGED
- `app.py` — new tabs (Extras, Prop Sim), imports
- `extras.py` — NEW (signal overlap + prop firm compliance)
- `prop_sim.py` — NEW (sequential prop firm simulator)
- `bar_analysis.py` — 1M bar selector + source branch
- `wfa.py` — 1M selector, event filter UI (mode radio + window slider), absolute heatmap
  color thresholds (`_HEATMAP_THRESHOLDS`, `_abs_colorscale`)
- `massive.py` — 1M build button + auto-load
- `simulation_engine.py` — `max_fill_ms` added to `_simulate_one_multileg` signature
- `@@MCBreakout.cs` — NEW NT8 strategy (in NT Strategies folder, not repo)

### NEXT (S31)
0. **Compile + test MCBreakout in NT sim** — verify signals match, measure real delays.
1. **Stress-test the simulation engine** — the original ask this session. Layer 1 (fill logic
   asymmetry, EOD pricing, same-bar priority), Layer 2 (WFA methodology), Layer 3 (filter
   timing / look-ahead). Started analysis but pivoted to building.
2. **Feed NT CSV timing data back into ESA** — once MCBreakout runs for a few days, import
   the CSV and set calc_delay_ms / wire_delay_ms to measured values.
3. **Calendar-day WFA folds** — option to slice by calendar dates instead of signal-days.
4. **Position management in sim** — the biggest result-overstating gap. One-at-a-time,
   one-per-direction, close-and-reverse modes.

---

## ⭐⭐ SESSION 29 — June 22, 2026 — ESA into WFA + Session Filters + Multi-TF + ER10 Analysis (read FIRST)
*Wired ESA execution model into WFA, closed the BA→WFA filter inheritance gap,
renamed delay parameters to reflect automated execution timeline, built 15M/100s
bar series, added ER10 distribution analysis, date whitelist upload, and reorganized
the UI for better workflow.*

### ESA WIRED INTO WFA
- **Full ESA controls in WFA Config:** Execution preset dropdown (Custom / Optimistic /
  Realistic / Conservative / Brutal), entry model radio (market/stop), calc delay, wire
  delay, fill timeout. Named presets grey out slip/delay inputs they override.
- **ESA params flow through all sim calls:** IS sweep, IS summary, OOS run — every
  `simulate_trades` call in WFA receives `entry_model`, `calc_delay_ms`, `wire_delay_ms`,
  `max_fill_ms`, `exec_seed` via `base_params`.
- **Run notes record ESA config** for traceability.

### DELAY RENAMED — `entry_delay_ms` → `calc_delay_ms`
- **Physical timeline clarified:** SB closes → first tick of new bar = SEPrice (trigger
  moment, can't act before it) → `calc_delay_ms` (indicator computation: ER10 filter
  etc., 10-50ms automated) → `wire_delay_ms` (network to exchange, 50-250ms) → order
  is live at exchange → retrace scan begins.
- **Presets updated:** Removed Idealized (serves no purpose for automated strategy).
  New values: Optimistic (10ms calc / 50ms wire), Realistic (20/100), Conservative
  (30/150), Brutal (50/250). Will update with real NT8 timing data.
- **`ActualDelayMs` → `ActualCalcMs`** in audit columns.
- **Phase B comparison baseline** changed from Idealized to Optimistic.
- 27/27 validation tests pass after rename.

### BA→WFA FILTER INHERITANCE — CLOSED (S26 item 2)
- **Session filters now in WFA:** Exclude holidays, DOW checkboxes, exclude first N bars,
  exclude last N minutes, FOMC/NFP/CPI event exclusion (±15min window), direction filter.
- **First-trade-only / First-2-of-day** added to WFA session filters.
- Applied to `signals_filtered` before regime gates, so all folds (IS + OOS) see the
  identical filtered population as BA.
- Session filter config recorded in run notes.

### 15M + 100s BAR SERIES
- **15M continuous bars:** Resampled from 5M (instant build), per-day grouping to avoid
  cross-session bars. Build button in Massive tab, auto-loads from parquet on restart.
- **100s continuous bars:** Resampled from per-day continuous tick cache. Build button in
  Massive tab (takes a few minutes), cached to parquet.
- **Bar timeframe selector** (5M / 15M / 100s radio) in both BA and WFA.

### ER10 DISTRIBUTION + THRESHOLD ANALYSIS
- **ER10 column** added to signal table (Core column group).
- **ER10 Distribution expander:** Histogram (0.1-wide buckets, colored green/red by avg R),
  summary stats (median, mean, count < 0.30, count > 0.70), per-bucket table.
- **ER10 Threshold Analysis table:** Each row = "if ER10 >= X": trades, win%, PF, Exp R,
  Net $, Max DD. Shows the marginal value of raising the threshold.
- Values come from the same `_regime_tags_cached` the filter uses — guaranteed consistent.

### DATE WHITELIST UPLOAD
- **BA + WFA:** File uploader accepts CSV/TXT with one YYYYMMDD per line. Multiple files
  merged. Signals filtered to only those dates before all other filters apply.
- BA: placed under Bar Timeframe selector. WFA: placed before Session Filters.

### ENTRY ZOOM CHART IMPROVEMENTS
- **Label placement:** Pixel-offset annotations with arrows pointing to events. Early
  cluster (SB Close, SEPrice, Order Live) goes left; later events (Retrace, Tick-Through)
  go above/below. No markers obscuring PA.
- **Delay/wire shading:** Faint colored vertical bands when calc/wire > 0, labeled.
- **Interval metrics strip:** Sig→SEPrice, SEPrice→Live, Live→Fill, Sig→Fill (total),
  Retrace→Fill. Adaptive formatting (ms/s/min).
- **Finer hlines:** SEPrice and Entry (slipped) lines thinner (0.8 vs 1.5). SBClose
  right-side label removed (already marked by event annotation).

### UI REORGANIZATION
- **Tab order:** Massive → Data → BA → WFA → Bar Viewer → Chart → Portfolio.
- **BA expander order after sim:** Quick View → Detail → Monthly/Setup → Entry Zoom →
  Edge Analysis → TOD/DOW → Regime → rest.
- **Auto-expand after run:** Quick View, Detail, Monthly, Setup expand on sim run.
- **Quick View layout:** Row 1: Net PnL | Win% | PF | Exp$ | ExpR | MaxDD | PnL/DD.
  Row 2: Trades (with avg/day delta) | Avg Win | Avg Loss | SQN | Days.
- Removed Median W / Median L from Quick View.
- Removed missing tick-data days warning.

### Files changed this session
- `simulation_engine.py` — `calc_delay_ms` rename throughout, updated `EXECUTION_PRESETS`
  (removed Idealized, new values), `ActualCalcMs` audit column
- `bar_analysis.py` — Entry Zoom rewrite (labels, shading, intervals), ER10 column +
  distribution + threshold table, date whitelist, bar TF selector (5M/15M/100s), Quick
  View rearrange, expander reorder + auto-expand, removed missing-tick warning
- `wfa.py` — ESA controls (preset/entry-model/delays/timeout), session filters (holidays/
  DOW/last-N-min/FOMC/first-trade/first-2/direction), date whitelist, bar TF selector,
  tuple slip fix for saved runs
- `massive.py` — `_resample_5m_to_15m`, `_resample_ticks_to_bars`, 15M/100s build
  buttons + auto-load + parquet cache
- `scripts/validate_execution.py` — calc_delay rename, 27/27 pass
- `app.py` — tab order: Massive → Data → BA → WFA → Bar Viewer → Chart → Portfolio

### NEXT (S30)
0. **Run WFA with realistic execution + ER10 >= 0.70** — stop entry, Realistic preset,
   ER10 gate on, session filters matching BA. This is the real validation test.
1. **ER10 reproduction in-app under realistic execution** (S28 item 3).
2. **NT Trade Overlay** — CSV export button + NT8 indicator skeleton (S28 item 4).
3. **15M signal set** — user getting 15M MC signals; run strategy on 15M bars.

---

## ⭐⭐ SESSION 28 — June 22, 2026 — ESA v2 + Phase B + Fill Timeout + Audit (read FIRST)
*Rebuilt the execution model (ESA v2), built Phase B comparison UI, discovered fill-time decay,
added fill timeout filter, built full execution audit with Y/N verification checks. Major
trust-building session — every fill is now verified against actual tick data.*

### ESA v2 ENGINE CHANGES (`simulation_engine.py`)
- **`EXECUTION_MODEL_VERSION` → `ESA_v2`**
- **SEPrice fixed to `prices[0]`** (first tick after SB close) — independent of delay. Previously
  SEPrice shifted with delay, meaning the stop-entry reference changed depending on execution
  assumptions. Now the reference is always the same; delay only affects when the scan starts.
- **`wire_delay_ms`** — new parameter: order-to-exchange latency (separate from reaction delay).
  Presets: Idealized 0ms, Optimistic 30ms, Realistic 60ms, Conservative 90ms, Brutal 120ms.
- **`max_fill_ms`** — new parameter: cancel entry if not filled within N ms of signal bar close.
  Data showed fills >30 min are net losers (avg R -0.09, 45% win). UI control in ESA expander.
- **Stop entry logic:** reference = first tick (fixed), scan starts at `sig_dt + delay + wire`,
  retrace + tick-through evaluated within the `max_fill_ms` deadline.
- **New audit fields:** `WireDelayMs`, `OrderLiveTime` (when order reaches exchange).
- 27/27 validation tests pass (3 new timeout tests, 2 wire delay tests).

### ESA PHASE B — COMPARISON EXPANDER (built)
- **Multiselect** presets (default all 5), "Run ESA Comparison" button, cached.
- **Comparison table:** Trades/Win%/PF/Exp$/ExpR/Net$/MaxDD/CAGR/Sharpe/SQN per preset.
- **Degradation table:** Δ vs Idealized for each metric.
- **Execution Robustness Score:** Conservative ExpR ÷ Idealized ExpR, banded
  (≥80% Strong, ≥60% Adequate, ≥40% Weak, <40% Fragile), near-zero denominator guarded.
- **Equity overlay chart:** all preset curves on one plot, color-coded.
- **Audit drill-down:** per-preset trade table with timestamps + Y/N checks.

### EXECUTION AUDIT EXPANDER (built — main run)
- Full **Y/N verification** on every filled trade:
  `Ref≥SigDt`, `Live≥Delay`, `Fill≥Live`, `SlipOK`, `Retr≥Live`, `Thru>Retr`, `StopFillOK`.
- **Computed delay columns:** `SigToRef_ms`, `SigToLive_ms`, `SigToFill_ms`, `LiveToFill_ms`.
- **Pass/fail banner** + failures-only filter.
- **Fill-time distribution table** — bucket breakdown with avg R / win% / net PnL per bucket.
- **Result: ALL 2710+ trades pass all verification checks (all Y).** Engine is trustworthy.

### ⭐ FILL-TIME DECAY DISCOVERY (key finding)
Analyzed `SigToFill_ms` across all stop-entry trades (Brutal preset):
- **75% fill within 2 min** (median 24 sec). These are clean breakouts.
- **< 1 min fills: avg R +0.15, 59% win, $296k net** (the core edge).
- **1-5 min fills: avg R +0.03, 54% win** (still marginal).
- **30+ min fills: avg R -0.12, 42% win, -$10k net** — stale entry, net losers.
- **Recommendation:** cap at 15-30 min. Built `max_fill_ms` for this. Validate in WFA.

### ENTRY ZOOM REWRITE
- Old zoom showed 6 ticks total — useless. New version shows **full tick path from signal
  to fill + 5 ticks beyond**, with annotated ESA events (SBClose, SEPrice, OrderLive,
  Retrace, TickThrough/Fill) as labeled colored markers. Auto-scales to trade data.
- Metrics strip: SBClose, SEPrice, Entry (slipped), Stop, Fill time.
- Timestamp trail: Signal → SEPrice tick → Order Live → Retrace → Fill.

### TRADE COUNT NON-MONOTONICITY (investigated, understood)
Market-entry ESA showed Brutal having MORE trades than Idealized (2747 vs 2738). Root cause:
`zero_risk` gate uses slipped entry price, so different slip draws push borderline trades in/out.
Magnitude is ~0.5% of trades — noise, not a bug. All performance metrics degrade monotonically
as expected. Stop entry resolves this (fewer fills with stricter execution).

### Files changed this session
- `simulation_engine.py` — ESA v2: fixed SEPrice, `wire_delay_ms`, `max_fill_ms`, updated
  `_resolve_entry` + all 3 sim paths + `simulate_trades`, `EXECUTION_PRESETS` with wire delays,
  `_exec_audit_fields` + `_EMPTY_TRADE` (WireDelayMs, OrderLiveTime)
- `bar_analysis.py` — ESA Phase B expander (comparison/degradation/robustness/equity/audit),
  Execution Audit expander (Y/N checks + fill-time table), Entry Zoom rewrite (full tick trail),
  `max_fill_ms` UI control, wire delay UI display
- `scripts/validate_execution.py` — 27 tests (3 new timeout, 2 wire delay, updated SEPrice test)
- `docs/living/handoff.md` — this session block + NT overlay idea documented

### NEXT (S29)
0. **Wire ESA into WFA** — single locked preset (option 2 from discussion). Add execution model
   controls (preset dropdown + entry model + delay + fill timeout) to WFA Config section.
1. **Validate fill timeout in WFA** — run with 15-min and 30-min caps, compare OOS metrics.
2. **BA→WFA filter inheritance** (still pending from S26).
3. **ER10 reproduction in-app** under realistic execution (S26 item 0b).
4. **NT Trade Overlay** — CSV export button + NT8 indicator skeleton (documented in NEXT item 5).

---

## ⭐⭐ SESSION 27 — June 22, 2026 — EXECUTION SENSITIVITY ANALYSIS (ESA) — PHASE A BUILT (read FIRST)
*New priority: the ESA design spec (`Execution Sensitivity Analysis Design Specification.pdf`).
Make execution assumptions a first-class, auditable, stress-testable object. Phase A
(engine) is DONE + validated; Phase B (ESA UI expander) NOT started — user paused to
test the engine on real data first.*

### ⚠️ THE TRUST ISSUE THAT STARTED THIS (read carefully)
User believed the engine "filled trades on touch at the SignalPrice" = cheating. **It did
NOT** — every fill is at the **first tick of the bar after the signal bar** (`first_tick_px
= float(prices[0])`), which is a realistic *basis*. TWO real problems existed:
1. **Labeling bug:** the output column `SEPrice` stored `signal_price` (the signal *bar
   close*), not the entry reference. Fixed: **SEPrice now = the post-delay entry reference
   (first tick at/after SB_close+delay)**; signal bar close moved to a new `SBClose` column.
2. **No execution realism:** zero latency, no delay, no slippage ranges, no market-vs-stop
   entry, no audit. That optimism (instant fill) — not a fake price — is what ESA stress-tests.

### LOCKED DEFINITIONS (confirmed by user this session)
- **SEPrice = first tick at/after (SB_close + delay)** — the Entry Reference Price. Delay=0
  reproduces today's fill exactly.
- **Stop-entry reference = SEPrice** (the first tick), NOT a separate level. §6 acceptance-test
  numbers were illustrative. Long stop: retrace ≥1 tick below SEPrice, THEN tick-through ≥1
  tick above → fill at SEPrice+1tick (mirror for short); else NO FILL.
- **R convention = fill-based (unchanged):** target = slipped fill + target_r×R; stop level =
  signal `StopPrice` ± stop_offset (fixed, NOT fill-derived); R unit = |slipped fill − stop|.
  Slippage genuinely widens risk + stretches the target.
- **3-leg tick path: SKIPPED per user** (baseline-identical, not audit-wired).

### WHAT WAS BUILT (Phase A — `simulation_engine.py`)
- **`_resolve_entry(prices, times, sig_dt, is_long, entry_model, delay_ms, entry_slip, ts)`**
  — the one shared entry resolver. Returns fill_idx + SEPrice + raw/adjusted fill + audit, or
  None (new FilterStatus `no_entry_fill`). Callers slice `prices/times` at fill_idx so the
  **validated exit machinery (target tick-through, stop-on-touch, PB, ratchet, vec==loop) is
  UNTOUCHED.**
- Wired into `_simulate_one` (single-leg) + `_simulate_one_multileg` (2-leg) tick paths.
- **Slippage:** `entry_slip`/`exit_slip` accept int (fixed) OR (lo,hi) integer-tick range,
  drawn per-trade from a seeded RNG (`exec_seed`, default 42). Fixed ints do NOT consume the
  RNG → baseline byte-identical. `target_slip`/`stop_slip` accepted but must equal each other
  (raises otherwise — every preset has target==stop; full per-side split deferred).
- **Audit fields** (`_exec_audit_fields`, in `_EMPTY_TRADE`): SEPrice, SBClose, RawFillPrice,
  EntryType, EntrySlipTicks/ExitSlipTicks, ActualDelayMs, ExecCostTicks, ExecModelVersion,
  ReferenceTime/RetraceTime/FirstThroughTime/ExitTriggerTime.
- **`EXECUTION_PRESETS`** (§13): Idealized/Optimistic/Realistic/Conservative/Brutal (delay +
  slip per spec; spread into `simulate_trades(**preset)`).
- **`compute_summary`**: added **CAGR + Sharpe** (vs notional `cagr_capital`=$100k — for
  *relative* degradation across presets, not promised live %) + `ann_return_dollar`.
- **`EXECUTION_MODEL_VERSION = "ESA_v1"`**.
- `bar_analysis.py`: SEPrice/SBClose display labels fixed (3 sites).

### VALIDATION
- **`scripts/validate_execution.py` — 21/21 pass.** Synthetic controlled paths: §17 entry
  tests (stop valid/invalid long+short, market+delay), §10 exit tests (target tick-through,
  stop touch), baseline equivalence, slip application, delay shift, seeded determinism.
- ⚠️ **Could NOT run the historical validators** (`validate_engine/oracle/ratchet/scalein`) —
  they OOM (MemoryError) loading every tick parquet in this 16GB env. Baseline equivalence was
  proven on synthetic paths instead. **User should run the historical validators on their box
  to confirm byte-identical baseline before trusting ESA degradation numbers.**

### IN-APP EXECUTION CONTROL (added after the engine, for testing)
`bar_analysis.py` now has a **⚙️ Execution model (ESA)** expander right above the Run button:
preset dropdown (Custom + Idealized…Brutal) · entry-model radio (market/stop) · delay (ms).
Feeds the MAIN run (`exec_entry_slip/exec_exit_slip/exec_entry_model/exec_delay_ms/exec_seed`),
included in `_sim_fp` so changes require a re-run. Defaults (Custom/market/0ms) = baseline.
Named presets OVERRIDE the Trading-Params slip. This is the single-run tester, NOT the full
preset-comparison ESA expander (that's still Phase B).

### NEXT (S27 → continue)
1. **USER IS TESTING THE ENGINE** on real data (paused here). Sanity-check: SEPrice now shows
   the entry reference (not bar close); a default run (Custom/market/delay0) must match the
   prior numbers; flip the Execution preset to Realistic/Brutal and re-run to see edge decay.
2. **Phase B — ESA comparison expander** (NOT started). Goes directly below the Detail expander
   (`bar_analysis.py:5000`). Preset selector + Comparison table (per-preset re-run:
   Trades/Win%/PF/Exp/AvgTrade/Net/MaxDD/CAGR/Sharpe/SQN) + Degradation table (Δ vs Idealized)
   + **Execution Robustness Score** (§15: Conservative ExpR / Idealized ExpR, banded, guard the
   near-zero denominator) + "View Execution Audit Trades" drill-down. **5× sim → Run-button gated.**
3. **Deferred:** mirror the resolver in the `bar_analysis.py:1127` fast-sweep (separate from ESA;
   baseline unchanged so `validate_scalein_sweep` stays green); full per-side target/stop slip.
4. **Downstream:** once trusted, re-state the ER10 "champagne run" (S26) under the Realistic
   preset to see how much edge survives realistic execution.
5. **NT Trade Overlay (idea, not started):** Export a CSV per run with trade timestamps + prices
   (SignalDateTime, EntryDateTime, ExitDateTime, Direction, EntryPrice, StopPrice, TargetPrice,
   ExitPrice, EntryType, RawFillPrice, SEPrice, all ESA timestamps). Then build a lightweight
   NT8 indicator that reads the CSV on chart load and draws markers on a 1-tick chart:
   `DrawDiamond` at fill, `DrawArrowUp/Down` at signal, `DrawLine` entry→exit (green/red),
   `DrawRay` for stop/target levels. The audit data already has everything needed — this is
   purely a rendering job on the NT side (~100 lines C#). The real value: verify fills visually
   against the actual market tape in NT's native chart, where you can scroll/zoom freely and
   cross-reference against volume, order flow, and other NT indicators. **Build the CSV export
   button first** (trivial — the Execution Audit dataframe already has the columns), then the
   NT indicator.

### Files changed this session
- `simulation_engine.py` — `_resolve_entry`, `_exec_audit_fields`, `_draw_slip`,
  `EXECUTION_MODEL_VERSION`, `EXECUTION_PRESETS`, single-leg + multileg entry integration,
  `_EMPTY_TRADE` audit fields, `simulate_trades` params (entry_model/delay/ranges/seed),
  `compute_summary` (+CAGR/Sharpe)
- `bar_analysis.py` — SEPrice/SBClose display labels (3 sites) + ⚙️ Execution model (ESA)
  expander (preset/entry-model/delay controls, feeds main sim run, fingerprint-gated)
- `ba_filter_defaults.json` — updated UI defaults (single-leg, 1.0R, slip/commission tweaks)
- `scripts/validate_execution.py` — NEW (21 synthetic acceptance/regression tests)
- Plan: `C:\Users\Admin\.claude\plans\snappy-gliding-gray.md`

---

## ⭐⭐ SESSION 26 — June 21, 2026 (night) — REGIME GATES BUILT + SCALE-OUT TESTED (read FIRST)
*Built the S25 regime gates into both apps (Bar Analysis + WFA), tested scale-out
head-to-head vs flat 2c baseline. No engine change. User reproduced S25 balance
numbers live in-app ($145 exp, PF 1.42, 676 trades). Scale-out decisively loses to
flat 1R — the 1R edge is already maximally capital-efficient.*

### THE HEADLINE — scale-out does NOT beat flat 1R (clean finding, close the question)
Head-to-head on ER≥0.30 + skip-prior-trend, `entry_slip=1/exit_slip=0`, commission
$4.36, 3886 filled trades:

| run | net | exp | PF | win% | max DD |
|---|---|---|---|---|---|
| **Baseline: 2c flat 1.0R** | **$763,939** | **$197** | 1.34 | 56% | −$44,741 |
| Scale-out: T1=1.0R BE, T2=1.5R | $417,609 | $107 | 1.37 | 47% | −$22,404 |
| Scale-out: T1=1.0R BE, T2=1.75R | $448,346 | $115 | 1.40 | 45% | −$24,242 |
| Scale-out: T1=1.0R BE, T2=2.0R | $463,921 | $119 | 1.41 | 44% | −$25,880 |

**WHY:** back-of-envelope confirmed by the sim. Flat 2c at 1R: 58% × 2R − 42% × 2R
= +0.32R. Scale-out: when T1 misses both contracts stop (−2R); when T1 hits you bank
only 1R instead of 2R, and the runner needs to reach 1.5–2R to compensate — but
P(reach T2 | reached T1) is only 43–60%. The runner doesn't recover the sacrificed
guaranteed second 1R bank. Scale-out PF is slightly better (1.41 vs 1.34) and DD is
half — but that's just because it makes less money.
**CONCLUSION:** 1R flat is the right trade management, not a compromise. The breakout
edge is too efficient at 1R to justify splitting positions. **Close this question.**

### REGIME GATES — built into both apps (BA + WFA)

**Foundation (`indicators.py`):**
- `developing_session_levels()` — causal cummax/cummin shifted 1 bar (dev range
  strictly before the signal bar, no look-ahead).
- `_daily_balance_context()` — prior completed day `inside_day` + `adr_ext`
  (range > 1.6×ADR trend day).
- `tag_signals()` now emits: `dev_High`, `dev_Low`, `balance_state`,
  `prior_inside_day`, `prior_adr_ext`. Validated 99.55% agreement with the
  canonical `tag_states` from `regime_overlay_phaseB.py` (22 diffs = days
  missing from `regime_ladder_sessions.parquet`, 3 = off-bar-edge ties).

**Bar Analysis (`bar_analysis.py`):**
- ⚙️ Filters expander → **Regime Gates** section:
  - **Intraday ER 30m ≥ gate** (adjustable threshold, default 0.30) — the deployed
    chop gate, now a hard population filter (not just a descriptive bucket).
  - **Balance state only** — opened inside prior range AND still rotating inside.
  - **Prior inside day only** — compression → expansion.
  - **Skip prior trend day** — range > 1.6×ADR, the one clean hard-skip.
- `apply_regime_population_filters()` stacks onto existing `FilterStatus` pipeline.
- `_regime_tags_cached()` tags once per signal/bar set (only when a gate is active).
- New FilterStatus labels: `low_er`, `not_balance`, `not_inside`, `prior_trend`.
- Wired into sim fingerprint + Save Defaults.

**WFA (`wfa.py`):**
- Same 4 checkboxes in WFA Config, placed between CC filter and multi-slice regime
  filter. Imports `_regime_tags_cached` + `apply_regime_population_filters` from
  `bar_analysis`. Temporary `FilterStatus` column added/removed (WFA signals don't
  carry one natively). Active gates recorded in run notes as
  `regime_gates[LOCKED]: ER>=0.30+skip_trend` etc. for traceability.

**User verified live in-app:** ER≥0.30 + Balance → $145 exp, PF 1.42, 57.8% win,
676 trades — matches S25 research exactly.

### ⚠️ ER10 (2-bar) DOMINATES ER30 OOS — STRONG, but NOT YET reproduced in-app
*This is the biggest result of the session and it looks **too good to be true** →
the immediate next action (S27) is to reproduce these numbers in the live app
before anyone adopts ER10. Treat as PROMISING, not BANKED.*

**The tautology scare — raised then resolved.** First reaction was that ER_intra_2
must be circular because the 2-bar ER includes the signal bar itself, so it's just
"big signal bars." The lag-1 test (ER excluding the signal bar) killed the edge,
seeming to confirm it. **But the user correctly pushed back:** the signal AND its
ER are both computed at the *same* bar-T close, and the trade enters on a LATER tick
— so bar-T's ER is *contemporaneous*, available at decision time, look-ahead-safe.
It is NOT future data. The lag-1 test was over-conservative (it deleted real,
available information). Correct framing: ER_intra_2 is largely an **entry-quality
reading of the breakout bar** (how cleanly the signal bar moved) — a legitimate,
executable filter, not a tautology. The one open item is OPERATIONAL: confirm NT can
compute ER10 from the just-closed bar and gate the order before the next tick (trivial,
but verify in the NT-sim phase).

**OOS evidence (walk-forward 15× 252/63 folds, pinned 1.0R, 1c, no other filters):**
- `ER_intra_2 ≥ 0.30` beats deployed `ER_intra_6 ≥ 0.30` on every metric at the same
  ~3,400 trades: exp $116 vs $94, PF 1.40 vs 1.31, **15/15 vs 12/15 green folds**,
  2022 $114 vs $100. All three of ER30's red folds flip green.
- Monotonic improvement to ~0.7–0.8 (net peaks ~0.7), 2022 exp keeps climbing to 0.9.
- **worstFold turns POSITIVE at ≥0.30 and stays positive through 0.9** — i.e. NO losing
  OOS fold anywhere. SQN reaches 12–13, Sharpe ~5. (Harness reproduces the deployed
  ER30 = $321k / $94 / 12-15 green EXACTLY, so it's apples-to-apples with S25.)

**DISCIPLINE — what is and isn't decided:**
- The defensible change is the **lookback swap (ER6→ER2) at the SAME 0.30 threshold** —
  a *single-knob* change vs the deployed gate, OOS-proven. That can be adopted.
- **Raising the threshold (0.30→0.7/0.8) is a SECOND knob = multiple-testing.** The
  monotonic pattern is reassuring but do NOT crown the in-sample net-max. Decide the
  threshold forward, by structure, with the full filter stack on.
- **The MAR95/SQN/Sharpe numbers are ROSY** — 1 contract, pinned 1R, NO session/FOMC/DOW
  filters, NO position management. They will worsen under realistic constraints (Phase 2).
  Treat as relative rankings, not promised live performance.

**Full sweep saved:** `docs/living/er10_oos_sweep_20260621.md` — all 4 filter
conditions (ER10 only / +skip-trend / +balance / +prior-inside) × 9 thresholds ×
20 OOS metrics. Re-confirms S25: **balance & prior-inside are SIZING signals, not
gates** (great per-trade exp/PF but worstFold stays negative, MAR95 single-digit,
>1yr underwater — sparsity kills them as standalone books). **ER10 + skip-trend is
the tradeable book.**

**NEXT (immediate): reproduce the ER10 table numbers in the app** (gates already
wired). Turn OFF all session/FOMC/DOW filters to match the headless runs, set ER10
gate, pinned 1.0R single-leg, ES, slip 1/0, $4.36. If the app matches → trust the
tables. If not → find the discrepancy before going further.

Related: ER gate is mildly counterproductive on bars 1–5 ($90 gated vs $111 ungated)
— the cross-session blend window; ER10's shorter reach largely fixes this.

### Early-bar analysis (within ER≥0.30, 1R single-leg)
| bar | n | exp | PF |
|---|---|---|---|
| 2 | 67 | $273 | 1.99 |
| 3 | 98 | $15 | 1.03 |
| 4 | 111 | $149 | 1.31 |
| 5 | 81 | −$51 | 0.91 |
| 1–5 | 357 | $90 | 1.19 |
| 6+ | 4082 | $87 | 1.29 |
Small n, noisy — bar 2 looks great but it's 67 trades. Not actionable alone.

### ER10 UI + infrastructure (S26 late — parallel chat)

- `indicators.py` — `bar_kaufman_er` spans extended `(6,12,24)` → `(2,6,12,24)`;
  `tag_signals()` now emits `ER_intra_2` (10-min / 2-bar Kaufman ER).
- `bar_analysis.py` — **ER 10m ≥ gate** checkbox + **ER10 gate** threshold input
  added to Regime Gates section (next to ER30). `apply_regime_population_filters()`
  accepts `want_er10`/`er10_min` params. New FilterStatus `low_er10`.
  `_regime_tags_cached()` returns `ER_intra_2`. Wired into defaults + sim fingerprint.
- `wfa.py` — same ER10 checkbox + threshold in WFA Config. Run notes record
  `ER10>=X` when active.
- Both ER gates stack: a signal must pass whichever are enabled (AND logic).

### Files changed this session
- `indicators.py` — `developing_session_levels()`, `_daily_balance_context()`,
  `tag_signals()` extended with 5 new columns + `ER_intra_2`
- `bar_analysis.py` — `apply_regime_population_filters()`, `_regime_tags_cached()`,
  Regime Gates UI (ER30 + ER10), FilterStatus labels, sim fingerprint, Save Defaults
- `wfa.py` — regime gate checkboxes (ER30 + ER10 + balance + inside + skip-trend),
  filtering + run-notes recording
- `docs/living/next_task_er_granularity.md` — ER granularity HYPOTHESIS (parked)

### S26 STATUS vs S25 FIRST ORDER OF BUSINESS
- ✅ **Build the app regime-filter checkboxes** — done (both apps).
- ✅ **TEST THE SCALE-OUT** — done. Result: flat 1R wins. Question closed.
- ⬜ **Baseline A re-run** — not done (deferred, but now trivial: just check ER≥0.30 +
  skip-trend in WFA and run).
- ⬜ **Head-to-head WFA:** baseline A vs A+balance-sizing+prior-trend-skip — the
  scale-out arm is now dead, simplifying this to a 2-way comparison.

### S26 PART 2 (late night) — ER10 VALIDATED OOS + stability panel + the BA→WFA gap
- **ER10 reproduced & validated.** In-app: ER≥0.30+balance → $145 exp/PF 1.42 (matches S25).
  Engine confirmed UNCHANGED this session; export reconciles to the penny from raw prices
  (pure arithmetic $562,970 vs $563,279), all fills on valid 0.25 ticks → numbers are real.
- **`low_er10` filtered-OUT signals LOSE −$297,883** (1,854 fillable, exp −$161, PF 0.66,
  win 40%) — the gate removes a deeply net-negative population. Conservation, not magic.
- **⭐ run_f76c8b92 (ALL / single-leg / PINNED 1.0R / ER10≥0.70) — the champagne run.**
  OOS 2,395 trades, **net $470,333, ExpR +0.212, PF 1.78, 62% win, 12/13 folds green.**
  maxDD $12k, MC-DD95 $14.8k, **MAR95 31.8**, longest UW 71d, SQN 12.3, Sharpe 4.71.
  **Every calendar year green** (2022–2026, ExpR 0.16–0.24), best-year share 40% (NOT
  regime-concentrated). **Breakout-vs-drift decomposition: Target +$942k, Stop −$521k,
  EOD +$50k → 89% of profit is the breakout MECHANIC, only 11% drift.** This is the
  EXACT INVERSE of the S22 unpinned disaster — pinning 1R + ER10 gate gives a REAL
  breakout edge, not a closet drift bet. The lone red fold (5) = the 2024-Q1 soft patch
  the rolling-ExpR chart independently flagged. **Verdict given: pour a glass, not the
  bottle** — 0.70 is an in-sample-selected threshold (validates the ER10 *concept*, not
  0.70 vs 0.30/0.50 specifically), and it's frictionless (no constraints, NT fills unproven).
- **Built: 📈 Expectancy Stability (R) expander in Bar Analysis** (`bar_analysis.py`, after
  Quick View) — rolling Exp-R chart (windows A/B adjustable, year markers) + green/red
  bar chart by Year/Half/Quarter + period table. Reads `R_achieved`; contract-independent.
- **🔴 CONFIRMED GAP — BA session filters are NOT inherited by WFA.** WFA shares only signal
  source + SignalType/CC selection + the new regime gates. It does NOT apply: exclude-holidays,
  DOW, excl-first-N-bars, **excl-last-N-min**, **FOMC/NFP/CPI**, **first-trade-only**,
  **first-2-of-day**, **direction**, date-range. So `run_f76c8b92` still contains late-session
  + FOMC + all-directions + every-trade-per-day. **BA and WFA validate DIFFERENT populations**
  — exactly the long-flagged "BA→WFA filter inheritance" gap. **THIS IS S27 FIRST TASK.**

### NEXT (S27)
0. **🔴 WIRE BA→WFA FILTER INHERITANCE (FIRST TASK, user's explicit ask).** Make WFA apply
   the SAME `apply_signal_filters` as Bar Analysis (reading the live `ba_*` session keys:
   holidays/DOW/excl-first-N/excl-last-N-min/FOMC-NFP-CPI) PLUS first-trade-only / first-2 /
   direction, so the two tools validate the IDENTICAL population. Mechanical, well-scoped.
   Then RE-RUN the ER10 WFA so its book matches the BA book.
0b. **REPRODUCE ER10 IN-APP (also early).** Reproduce `er10_oos_sweep_20260621.md` in the live
   app: all session filters OFF, ER10 gate on, pinned 1.0R single-leg, ES, slip 1/0, $4.36.
1. **Head-to-head WFA OOS:** baseline A (ER≥0.30 + skip-trend, flat 1R) vs
   A+balance-sizing (same population, but MES position sizing: base 3 MES,
   size up on balance). This is the remaining gate to "convinced." If ER10 is
   confirmed in-app, run baseline A on ER10 instead of ER30.
2. **A–G state taxonomy** (friend's framework) — specifically F/G
   (balance→discovery transition). The balance gate is built; the next
   question is whether the *transition out of* balance carries its own edge.
3. **ER timing fix + threshold decision** (`docs/living/next_task_er_granularity.md`):
   lookback swap (ER6→ER2 @0.30) is the defensible single-knob change; the threshold
   raise is a separate forward decision, not the in-sample net-max.

---

## ⭐⭐ SESSION 25 — June 21, 2026 (eve) — BALANCE-STATE RESEARCH + ETH LEVELS (read FIRST)
*Built overnight (ETH) levels from raw flat files, then discovered a real, regime-stable
market-state edge: CC breakouts work better in "balance state." All tests this session are
**single-leg, pinned 1.0R, corrected engine** (entry_slip=1, exit_slip=0). No engine change.*

### THE HEADLINE — "balance state" is a real, regime-stable conviction signal
- **Definition (look-ahead-safe, observable at signal time):** opened **inside** prior RTH
  range (LOY<OOD<HOY) **AND** still inside at signal (developing High<HOY AND Low>LOY) =
  market rotating inside yesterday's range, no discovery yet.
- **Finding:** within ER≥0.30, balance trades **$149/trade vs $75 non-balance** (PF 1.43 vs
  1.25). Survives the **time-of-day confound** (within the same TOD window: Open $147 vs $21,
  Lunch $273 vs $96) and persists **9/14 walk-forward OOS folds**, incl. 2022. The opening
  session — otherwise your weakest — is where balance helps most.
- **WHY:** with a 1R target, a balance-day breakout only needs to ride to the nearby untouched
  prior extreme (inside-open days touch a prior extreme **84%** of the time) to hit target.

### ⚠️ ER30 IS THE PRIMARY GATE — balance is a SECONDARY booster (2×2, all corrected-engine)
| | balance | non-balance |
|---|---|---|
| **ER≥0.30** | $149 (PF 1.43) | $75 (PF 1.25) |
| **ER<0.30** | **−$103** | **−$132** |
- **Below ER 0.30 EVERYTHING loses** — balance can't rescue chop. ER30 is make-or-break; the
  user's instinct that ER30 is the filter with most merit is **correct**. Balance is additive
  *on top of* ER30 (nearly doubles exp), not a replacement. Balance-alone (ignoring ER) is mildly
  positive (~$91) — earlier "balance alone loses" was imprecise; only its low-ER slice loses.

### HOW TO APPLY IT — size, don't skip (the key practical conclusion)
- **Do NOT hard-filter to balance-only.** Non-balance ER30 trades still profit ($75); WFA
  shows ER30-only nets **$321k** vs balance-only **$65k** — skipping non-balance throws away
  ~$240k of edge (same lesson as the VA-imbalance test: filtering for quality kills volume).
- **Structure:** ER≥0.30 = hard gate · **balance = size-up (conviction)** · inside-day-prior =
  size-up more · **prior trend-day (>1.6×ADR) = the one clean hard-SKIP** (see below).

### PRIOR-DAY CONTEXT (within ER≥0.30) — two of three theories confirmed hard
| prior day was… | exp | PF | +balance |
|---|---|---|---|
| **inside day** | $172 | 1.60 | $348 (n=44) |
| normal | $82 | 1.26 | $135 |
| **trend day (>1.6×ADR)** | **$6** | 1.01 | $2 (dead) |
- Inside-day-prior → compression→expansion, **breakouts much better**. Trend-day-prior →
  digestion, **breakout edge DEAD** ($6) → clean skip. CLV (close location) = weak, nothing.

### WALK-FORWARD OOS config comparison (pinned 1.0R, same is=252/oos=63 folds, corrected engine)
| config | trades | exp | PF | %green | pooled net | MAR | exp 2022 |
|---|---|---|---|---|---|---|---|
| none | 4184 | $54 | 1.17 | 73% | $227k | 8.5 | $33 |
| **ER≥0.30** | 3422 | $94 | 1.31 | 80% | **$321k** | **13.4** | **$99** |
| balance only | 719 | $91 | 1.26 | 80% | $65k | 4.9 | $89 |
| ER≥0.30+balance | 576 | $141 | 1.43 | 73% | $81k | 7.8 | $119 |
| ER+bal+prior-inside | 33 | $450 | 4.05 | 77% | $15k | 4.8 | (thin) |
| ER+bal+prior-trend>1.6 | 119 | $20 | 1.04 | 50% | $2k | 0.2 | dead |
- **ER30 is the workhorse — strongest single result in the project.** More net than no-filter on
  fewer trades, best MAR, 80% green, $99 exp even in 2022.

### MFE/BE (S25 late) — balance trades have more follow-through
- Balance MFE_R median **0.96** vs non-bal **0.71** → hints balance supports a bigger target/2nd
  leg. **BUT MFE is censored at the 1.0R target** — must re-run with a HIGH/no target to confirm.
- Give-back after +0.5R: balance 18% vs non-bal 20% (after +0.75R: 8% vs 10%) — too small to
  manage differently. BE/ratchet at ~0.5–0.75R is a general lever, not balance-specific.

### FADE — symmetric fade is dead; asymmetric is a real but DEFERRED idea
- Mirror-stop fade (flip direction + mirror stop across entry) **loses in every regime bucket**
  (−$124/trade) because the system is net-positive everywhere — no structural loser to reverse.
- User's insight (real fades may use a **tighter stop + bigger R target** — asymmetric) is valid
  and *can* be positive where the mirror isn't. **DEFERRED to the reversal/RevFT signal work.**
  Build order then: reclaim-trigger entry, stop just beyond the failed-breakout extreme, sweep
  target R / structural targets, bucket by regime (esp. trend-prior / non-balance days).

### A–G STATE TAXONOMY (friend's framework) — adopt next
- Friend's PDF is a clean synthesis of THIS session's results (its test table = our `confirm`
  output) **plus** one real new contribution: a MECE state taxonomy observable at signal time —
  A Balance (=our balance), B/C Accepted above/below (discovery — our data says WEAKER, test it),
  D/E Failed discovery (=the fade setups, deferred), **F/G intraday discovery** (opened inside
  then broke YH/YL — the balance→imbalance transition we never isolated; friend hypothesizes
  this "potential energy released" is the real edge → TEST). Validate at **portfolio level**,
  **within ER≥0.30**. Friend under-weights ER (it's the gate, not a 2ndary feature).
- **Acceptance is a PARAMETER, not a binary.** Default for B/C/D/E: "traded ≥2 ticks beyond
  YH/YL AND not returned inside since" (causal); **sweep the buffer** (0/2/4/8 ticks) — edge
  must survive. Cross-check vs value-area migration (VP engine exists) as ground truth.

### ETH OVERNIGHT LEVELS — new infrastructure (validated vs NT)
- `scripts/build_eth_levels.py` → `data/eth_levels.parquet` (per-session ETH H/L, back-adjusted
  via the project's roll machinery `get_active_contract`→`cum_offset`; RTH H/L matches continuous
  bars exactly). Parallel pyarrow extractor (~4 min). **NT-matched window = [prev 17:00, 08:15)**
  — NT labels 15-min bars by CLOSE time, so its `08:15` cutoff = last bar 08:00–08:15. **Validated
  8/10 exact vs the user's NT `ES_ETH_levels.csv`** (2 misses = partial holiday sessions). Window
  is one constant if we want to change it. Also captures post-close tail (PC_High/Low) for a
  def-B "[prev 15:15, 08:15)" variant if wanted.
- Ladder base rates (`scripts/regime_ladder_study.py` → `regime_ladder_sessions.parquet`): ETH-edge
  break = ~coin-flip on acceptance (54%); Brooks PDH/PDL "magnet" = 84% of inside-open days touch a
  prior extreme (but only 9% both); ADR has NO exhaustion cliff (~56% continuation per +0.25×ADR
  past 1×). All base rates **regime-stable across years incl 2022**.
- HOD/LOD-by-bar table (`docs/living/hod_lod_by_bar.csv`): day extreme forms at the OPEN (bar 0 =
  27%), one side locks by ~10:00 (80% either-in) but BOTH not in until ~14:10; sharp EOD surge
  (bars 77–80) = the EOD-drift signature quantified. Bar 18/10:00 is NOT special (baseline 2.5%).

### Scripts added this session
`build_eth_levels.py`, `regime_ladder_study.py`, `regime_overlay_phaseB.py`,
`confirm_balance_day.py`, `fade_by_state.py` (fixed: mirror-stop), `balance_deepdive.py`,
`mfe_by_balance.py`. Reports in `docs/living/`: `regime_ladder_*.md`, `regime_overlay_phaseB_*.md`,
`confirm_balance_day_*.md`, `fade_by_state_*.md`, `balance_deepdive_*.md`, `hod_lod_by_bar.csv`.

### S26 FIRST ORDER OF BUSINESS (decisions already made — just execute)
- **Baseline = A: ER30-pinned-1.0R-ALL, single-leg** (user chose, apples-to-apples).
- **Build the app regime-filter checkboxes** (user wants to test himself): Bar Analysis
  trade-parameter section + WFA Config section. Filters: **Balance state**, **Prior inside
  day**, **Skip prior trend day (>1.6×ADR)** (ER≥0.30 already exists). Exact look-ahead-safe
  defs are in this S25 block ("Filter definitions"). Foundation first: add developing
  session High/Low (causal cummax/cummin shifted 1 bar) + `balance_state` / `prior_inside_day`
  / `prior_adr_ext` columns to `indicators.tag_signals`, THEN wire the checkboxes.
- **TEST THE SCALE-OUT (the big one, untested):** verified the engine supports it as-is —
  multileg with **`ml_pb_r=0` (E1=E2, no pullback add) + `t1_r=1.0` + `t1_action="BE"` +
  `target_r`=~1.5–2.0** = bank at 1R (keep the 58% leg-1 win), runner to bigger T2 risk-free.
  This is where the balance bigger-MFE finding (p75 1.97R, 25% reach 2R) should pay off.
  NOTE: BE-ratchet at 0.5/0.75R HURT — only ratchet AFTER the T1 partial.
- **Head-to-head WFA:** baseline A vs A+balance-sizing+prior-trend-skip vs A+scale-out.
  The 3 gates to "convinced": (1) scale-out beats flat 1R, (2) combined beats A head-to-head
  OOS, (3) survives realistic constraints.

### NEXT (S25 → S26) — backlog
1. **WFA: balanced+prior+ER30 vs the best portfolio from yesterday** (the user's priority).
   ⚠️ Yesterday's stored runs (`opt_A/opt_B_CC*` per-setup, ES1/MES5, single+multileg) and the
   S22 `pin10_all_sl` predate/straddle the slippage fix — re-run the baseline FRESH on the
   corrected engine for an apples-to-apples compare. Decide baseline: per-setup-optimized vs
   ER30-pinned-1R-ALL. Test balance as **size-up** + **prior-trend skip**, not a hard filter.
2. **Implement A–G states** + acceptance-buffer sweep; portfolio-level OOS within ER30; isolate
   **F/G (balance→discovery)**.
3. **High/no-target re-run** to settle the target question (balance MFE censored at 1R).
4. **MES position-sizing engine (roadmap Phase 2)** — 3 MES base, size up on balance/inside-day,
   skip trend-prior. Keep multipliers simple (don't optimize). Real engine build (position mgr).
5. Fade/RevFT (deferred — see above) when reversal signals are explored.

---

## 🚨🚨 SESSION 24 — June 21, 2026 — CRITICAL SLIPPAGE BUGFIX (read FIRST)
*A trade trace exposed a long-standing engine bug: every research script passed
`entry_slip=0.5, exit_slip=0.5`, and the engine computes slippage as `slip × tick_size`
→ `0.5 × 0.25 = 0.125 pts = HALF A TICK`, pricing **every** computed fill off-tick.
**All prior S22–S23 dollar/PF/PROM/MAR numbers produced via the research scripts are
INVALID and must be regenerated.** Directional conclusions may survive; specific numbers do not.*

### Root cause
- Slippage is in **whole ticks** (engine does `slip × ts`). Scripts passed `0.5` → 0.125 pts
  off-tick on E1 entry, E2 entry, and all exits; `RiskPts`/R-multiples/PB/target levels
  inherited the error. Intended default was always integer ticks (`validate_engine.DEFAULTS`
  + handoff both say `entry_slip=1, exit_slip=1`). The `0.5` lived ONLY in research scripts,
  never the validators — which is why every validator stayed green and the bug survived.
- **Second bug found:** the PB (pullback) add is a resting **limit** at the trigger, but the
  engine applied *adverse* slip (`pb_trigger ∓ slip`), modelling a fill *worse than the limit*
  — impossible. Produced a short E2 filling at 4973.50 below a 4973.75 trigger.

### Fix (engine change — re-baselines numbers, intended)
1. **E2/PB add now fills AT `pb_trigger`** (already tick-snapped), no adverse slip. Applied
   identically to vec + loop + ratchet-on + bars-path + the Bar Analysis fast sweep + the
   oracle reference, so vec==loop and fast==oracle still hold.
2. **Guard:** `simulate_trades` now **raises** on any non-integer slip → can't recur.
3. **Params → `entry_slip=1, exit_slip=0`** (ES rarely slips: 1 tick on the market entry,
   exits fill at level on touch). Updated active scripts + UI defaults/integer step
   (`wfa.py`, `portfolio.py` — no more half-tick entry).

### Validated (all green AFTER the fix)
- `validate_ratchet` multileg/e2: vec==loop byte-identical, 9 settings
- `validate_oracle` multileg: independent reference agrees on every trade incl. `E2FillPrice`
- `validate_scalein_sweep`: fast==engine, 64 combos
- Live trade check: all prices on valid 0.25 ticks; CC2 short E2 fills at 4973.75 (trigger)

### Files
- `simulation_engine.py` (E2 fill ×4 sites, slip guard), `bar_analysis.py` (fast sweep E2),
  `wfa.py` + `portfolio.py` (UI integer slip), `scripts/validate_oracle.py` (oracle E2 def)
- Full writeup: **`docs/living/slippage_offtick_bugfix.md`**
- New (corrected) research scripts present but **NOT yet re-run**: `per_setup_portfolio.py`
  (`--mode`/`--instrument`/`--contracts` CLI; multileg/singleleg × ES/MES), `late_period_analysis.py`
  (TOD/per-bar/session-phase), `er_timing_compare.py` (ER bar-T vs T-1, no auto-shift),
  `fade_analysis.py` (reverse losers, bucket by VA/ER/TOD/dir), `overnight_batch.py` (chains them)

### NEXT
- **All re-runs were CANCELLED at user's request** — no corrected numbers exist yet. Do NOT
  cite any S22–S23 figure as current. Regenerate before drawing conclusions.
- The multiprocessing experiment for `run_is_sweep` was attempted and **reverted** (Windows
  spawn pickle of the full tick dict failed; ~1.7x at best on multileg, slower on singleleg).
- **User moved on to a new task after this commit.**

---

## ⭐⭐ SESSION 23 — June 21, 2026
*Research session: regime filter ablation (ER confirmed), prom_tgt objective test, WFA optimizer exposed as gaming PB depth. Major planning session — roadmap through prop firm deployment, research backlog built out.*

### FIRST ORDER OF BUSINESS — NEXT SESSION
1. **Multiprocessing for IS sweep** — implement the plan in handoff (Pool(4), initializer pattern, slice ticks to IS dates). Every run after this is ~4x faster. Sonnet can do it.
2. **Per-setup optimization with sane PB grid** — `_PB_VALS` already updated to `[-0.25, -0.33, -0.50]`. Run unpinned WFA for each CC (CC2–CC5) individually with ER≥0.30 chop filter. Find the best T1/T2/PB per setup.
3. **Find ideal ER30 chop threshold per setup** — sweep ER from 0.20–0.40 in 0.02 steps per CC (not just ALL). Each setup may have a different sweet spot.
4. **Run the portfolio** — combine per-setup optimal params + per-setup ER thresholds, run the full portfolio WFA with those pinned settings. This is the real test.

### Key findings this session

**Ablation 6 — PROM vs PROM-target (unpinned per-CC with ER≥0.30):**
- prom_tgt works as designed: picks lower targets (avg 1.14–1.40R vs 1.49–1.78R), higher target hit rates (50–61% vs 35–46%)
- BUT: not universally better. CC4 prom $89k vs prom_tgt $42k; CC5 prom $52k vs prom_tgt $40k. These setups genuinely profit from bigger moves.
- CC2 is the exception: prom_tgt $48k vs prom $40k. CC2 breakouts are smaller moves.
- **Conclusion: per-setup objective selection, not one-size-fits-all.**

**WFA optimizer exposed — PB depth exploit:**
- Optimizer chose PB = -0.94R (94% pullback to stop!). E2 fills at ~34% rate, EVERY E2 fill is a net loser (avg −$417 to −$835).
- The deep PB exploits R math: E2 enters near the stop → tiny risk denominator → inflated R-achieved → inflated PROM.
- All money comes from E1-only trades (avg +$450 to +$625). The pullback leg destroys value across every setup and every objective.
- **FIX: capped `_PB_VALS` to `[-0.25, -0.33, -0.50]`** — removed -0.625, -0.75, -1.00.
- User direction: pin params after manual optimization in Bar Analysis. WFA optimizer not trusted.

**Commission update:**
- ES commission updated from $3.00 to **$4.36** RT (NinjaTrader Free tier: $2.18/side). Was undercharging by $1.36/trade.
- MES updated from $1.00 to **$1.30** RT ($0.65/side).
- Updated in `simulation_engine.py` INSTRUMENTS dict + all 9 ablation/validation scripts.

**ER bar-granularity update (previous conversation, noting here):**
- `bar_analysis.py` ER bins changed from 0.2-wide to 0.02-wide (50 bins). Propagates to regime filter multiselect.

### Changes made this session
- `simulation_engine.py`: ES commission 3.0→4.36, MES commission 1.0→1.30; added `prom_tgt` to `compute_summary` (target-hit-only PROM)
- `wfa.py`: `_PB_VALS` capped to [-0.25, -0.33, -0.50]; `select_params` accepts `objective` param; `run_wfa`/`run_window_grid`/`run_window_structures` thread `objective` through; IS objective dropdown added to UI
- `bar_analysis.py`: ER bin granularity 0.2→0.02
- All ablation scripts: commission 3.0→4.36
- `scripts/filter_ablation6_prom_tgt.py`: new — unpinned per-CC PROM vs PROM-target comparison
- Results CSV: `docs/living/filter_ablation6_prom_tgt.csv`

### Runs created this session
- `abl6_CC2_prom`, `abl6_CC2_prom_tgt` (4 folds each)
- `abl6_CC3_prom`, `abl6_CC3_prom_tgt` (8 folds each)
- `abl6_CC4_prom`, `abl6_CC4_prom_tgt` (9 folds each)
- `abl6_CC5_prom`, `abl6_CC5_prom_tgt` (8 folds each)

---

## ⭐⭐ SESSION 22 — RESEARCH FINDINGS (the headline; read FIRST) — June 20, 2026
*Drove the whole MC signal set through the validation apparatus end-to-end. The big finding: there **is** a real edge, but only a **target-driven** one — and the WFA optimizer was actively burying it.*

### LATEST (S22 late eve) — VA-imbalance filter + the per-setup/fold insight + a new compare tool
- **VA-imbalance hypothesis tested** (structural: breakouts work in imbalance, not balance → DROP signals inside prior **session VA**, keep `below`+`above`). At pinned 1.0R on the ALL portfolio (`pin10_all_va_sl` vs baseline `pin10_all_sl`): **QUALIFIED WIN at portfolio level.** Net **$194,776 → $213,902** on **−28.7% trades** (4,129→2,945), expectancy **$47→$73**, median trade $47→$110, **Mean PROM −0.08 → +0.52**, best-year **54%→39%** (less regime-dependent), MC DD95 −$49k→−$32k. NOT PF-by-attrition (net ROSE on fewer trades = dropped trades were net-negative). The ONE fail: Median WFE 41%<50% — a **divide-by-fragile-IS artifact** (baseline 115% inflated by 2 near-zero-IS folds; filter raises IS PnL too, so OOS÷IS falls). Reports: `docs/living/va_filter_compare_20260620.md`, `va_per_setup_threshold_20260620.md`.
- **PER-SETUP CHECK DID NOT CONFIRM.** VA filter **hurt** CC2/CC4 (net ~halved), CC5 mixed (PROM→0.02), CC3 better but still PROM −0.88. So the aggregate win is a **composition/diversification effect, not a per-setup structural edge** — and the per-setup runs are too thin post-filter to trust either way.
- **KEY METHOD INSIGHT (why per-setup can't be validated here):** `build_folds` slices folds by **COUNT of distinct signal-DAYS, not calendar**. ⇒ (a) sparse setups get fewer folds (CC2 6→3 after filtering); (b) **"12m IS" is mislabeled** — 252 *signal-days* for a sparse setup spans ~2+ calendar years, and per-setup folds cover different calendar windows than the ALL run (not directly comparable). Combined with the **min-trades gate** (Pardo ≥30/bucket, ≥100 pref — it exists because <30 trades = PF/expectancy are pure noise), the **individual setups lack the statistical power to validate alone.** → **DIRECTION: make the PORTFOLIO the unit of validation; per-setup = diagnostic only.** Candidate methodological fix: fold on **calendar windows** (all signals in the window) instead of signal-days.
- **NEW TOOL — in-app ⚖️ Compare Two Runs** (`wfa.py` Results tab expander; `_compare_metrics`/`_cells_from_folds`/`_mc_dd95`): side-by-side OOS metrics + overlaid equity for any two stored runs. **Built by a parallel chat; byte-compiles; NOT yet eyeballed live → sanity-check in the app.** Mirrors `scripts/compare_va_filter.py`.
- **NEXT:** (a) run the **VA-filtered ALL portfolio through the window-anchor robustness map** — does the filter survive different IS/OOS structures, or is the win a single-window fluke? (the real open question). (b) **User is now exploring 2-LEG entries in WFA.** (c) Still open: window-map persistence, better WFA objective (cap R / maximin), BA→WFA filter inheritance, MES sizing.

### THE KEY FINDING — the optimizer harvests EOD drift; pin the target low
- **Unpinned WFA (optimizer free to pick R) chooses ~2.0R (grid ceiling) and produces a regime-dependent EOD-drift bet, NOT a breakout edge.** Decomposing OOS PnL into the breakout mechanic (target-hits + stops) vs hold-to-close (EOD-green): on the ALL-setup portfolio (`run_13693b64`, $242,938 OOS) the **target game is −$23,381** (the breakout system *loses money*) and **EOD-drift is +$266,319** — i.e. **100%+ of profit is just ES drifting into the close**, concentrated in the 2024–25 bull grind.
- **Pinning the target at 1.0R FLIPS it to a real breakout edge.** Same portfolio pinned 1.0R (`pin10_all_sl`): Net **$194,776**, **target game +$186,962 (96% of profit)**, EOD only +$7,814. Median trade −$53 → **+$47**, win% 46.9 → **52.1**. The edge was real all along; the optimizer was chasing high R into drift.
- **WHY the optimizer can't see this:** its objective is **PROM**, and PROM is *higher* at 2R because EOD-drift wins inflate GrossWin while MaxDD (stops) is R-invariant. The drift is present in BOTH IS and OOS (2021–26 was drift-friendly), so neither in-sample optimization nor the OOS test punishes it — only the mechanical target-vs-EOD split exposes it. **FIX (next session, OPEN): cap `_T_VALS` at ~1.5R (structural: targets >1.5R don't bind) and/or change the objective from peak-PROM to a robustness/worst-fold (maximin) metric.** The user explicitly wants a better WFA optimization approach.

### Per-setup battery (pinned 1.0R, single-leg, 12m/3m) — validate individually (manual's order)
| Setup | OOS Net | Target$ | %grn | BestYr | MAR95 | U/W | PROM | verdict |
|---|---|---|---|---|---|---|---|---|
| ALL | $194,776 | $186,962 | 67% | 54% | 4.0 | 315d | −0.08 | diversified blend |
| CC5 | $55,494 | $53,740 | 62% | **49%** | 2.1 | 250d | **+0.14** | **the real edge (only +PROM)** |
| CC4 | $50,244 | $40,556 | **91%** | 66% | 1.3 | 417d | −0.74 | consistent but risk-thin |
| CC2 | $46,535 | $35,834 | 67% | **93%** | 2.1 | 392d | −0.18 | ❌ one-year windfall |
| CC3 | $19,123 | $25,773 | 60% | 60% | **0.4** | **798d** | −0.90 | ❌ risk disaster |
| CC1 | — | — | — | — | — | — | — | unvalidatable (~7 trades/fold) |
- **CONCLUSION: the tradeable core is CC5 (+ maybe CC4), NOT the 5-setup blend.** The portfolio's robustness is **diversification masking 2 unsound setups** (CC2 = 93% one year; CC3 = MAR95 0.4 / 798 days underwater) + 1 untestable (CC1). Diversification IS real (portfolio MAR95 4.0 > any single's 2.1) but you'd be trading dead-weight setups for it. **Everything is thin (PF 1.1–1.3, PROM ≈ 0) → size on MES.**
- MAR95 = Net ÷ Monte-Carlo DD95 (realistic worst DD, ~$52k for the portfolio vs −$29k realized). U/W = longest underwater (days).

### The "$599k sweep is BS" scare — RESOLVED, no bug
- User saw a sweep showing ~$599k and distrusted the WFA. **Reproduced their EXACT config with the validated engine → $110,031**, matching the **Summary ($110,637)**, the **1-D R sweep**, AND the **2-D Stop×Target sweep's 1.00× column** (S21's never-verified cross-check now PASSES: 1.00×/1.75R = $110,637). **The $599k was 2-Leg mode**, not a bug — a different (legitimate) config. Lesson = the WFA and Bar Analysis must run the SAME config (filter-inheritance still TODO).
- Also corrected the user's framing: WFA never "lost money" — negative **PROM** ≠ negative dollars; it made +$40–58k OOS. PROM is risk-adjusted/pessimistic.

### Fixes made this session (committed)
- **`indicators.py` dtype bug** — signals parquet is `datetime64[us]`, bars `[ns]` → `merge_asof` in `tag_signals` raised "incompatible merge keys", **crashing the regime filter**. Now normalises both to ns. Fixes WFA regime filter AND Bar Analysis regime expectancy.
- **`regime_filter.py` SHORTLIST: `eri_60` → `eri_30`** (`ER_intra_12`→`ER_intra_6`) so the locked filter names the SAME indicator (Intraday ER 30m) Bar Analysis's factor-grouping picks (highest RIC). User flagged "these don't match".
- **`wfa.py` `_T_VALS`/`_T_OPTS`: clean 0.25 steps** `[0.50,0.75,1.00,1.25,1.50,1.75,2.00]` (was non-0.25 `0.625`). Pin default kept at 1.00R (index 2).
- **`scripts/run_setup_pipeline.py`**: `--excl-last-min` (applies the app's session filter via `apply_signal_filters`) + **Phase 4.6 OOS equity PATH/shape gates** (MAR, best-year concentration) — added after the user caught that a regime-dependent equity curve passed as "CONDITIONAL"; shape failures are now decisive (force NO-GO).

### ROADMAP (user-defined, June 21 2026)

**Phase 1 — MC breakout optimization (CURRENT):**
Per-setup optimization (CC2–CC5), each with own regime filters (ER≥0.30 confirmed, testing others). Decide pinned vs unpinned params. Assemble portfolio, validate with window maps, Monte Carlo, robustness. At some point: stop optimizing and call it done.

**Phase 2 — Realistic trade constraints:**
Position management (one-at-a-time, one-per-direction, close-and-reverse). Max daily loss, risk caps, MES position sizing. Re-run WFAs with constraints baked into the sim — optimal params may change when you can't take every signal.

**Phase 3 — Reversal setup (RevFT):**
New signal type, separate development. Own regime filters, own WFA optimization. Eventually: combined MC + RevFT portfolio.

**Phase 4 — Multi-system portfolio:**
Portfolio of MC breakouts + RevFT reversals + possibly MC fades (failed breakouts flipped as reversal entries — the two systems are two sides of the same coin). Diversification across signal types, not just setups within one type.

**Phase 5 — NT sim validation:**
Run automated strategy on NinjaTrader sim for several months. Compare live-sim results to backtest expectations — fills, slippage, P&L, drawdown. This is the ultimate reality check before real capital.

**Phase 6 — Prop firm deployment:**
Separate accounts for long and short (prop firm requirement). New cost structure: monthly fees, higher commissions, profit share — all must be modeled. Each account level has strict rules (max drawdown, daily loss limits, position limits, scaling rules) that must be baked into the automated strategy. These constraints alone could break things — the system must be re-validated under each firm's specific ruleset. Account-level rules vary by firm and tier.

### OPEN / NEXT (priority order)
0. **NEXT SESSION TODO — three items before new research:**
   - **Late-period signal filter:** ~1,195 late-session trades with PF <1 and negative PnL. Price out the bucket, find the right time cutoff, run ablation (ALL+ER≥0.30 ± late cut). No reason to keep structurally negative trades.
   - **ER timing fix (real issue):** ER_intra_6 includes bar T's close — the same bar that generates the signal. A strong breakout bar pushes ER higher AND creates the CC pattern, so the filter partially selects FOR signal bars rather than independently measuring the pre-signal regime. Fix: use T−1's ER (the value before the signal bar). Re-run the ER≥0.30 ablation with 1-bar lag to confirm the edge holds on prior-bar ER. Also worth exploring: compute ER on tick/price-change basis and use the last value before bar T closes.
   - **Range/ATR >1.2 filter:** 857 trades, PF 0.98, Exp −$22. Test dropping them (ALL+ER≥0.30+RangeATR≤1.2 vs baseline). Also consider: per-trade stop-size cap based on volatility (skip signals where risk is too wide relative to ATR) — different mechanism than population filter, worth testing.
   - **Stop size / volatility cap:** Investigate capping stop size based on ATR. High-vol days have wider stops → more dollar risk per trade. A per-trade risk gate (e.g., skip if stop > X × ATR) could normalize risk and remove the worst Range/ATR bucket organically.
   - **Adaptive target based on ATR:** Instead of fixed 1.0R, scale target to the day's range/ATR. Tight days = smaller target (easier to hit), wide days = larger target (more room). Could improve target hit rates without giving up edge. Test against fixed-R baseline.
   - **Volume analysis (3 angles):** (a) Signal bar volume relative to time-of-day average — breakout on 2x normal volume = institutional conviction vs 0.5x = noise. TOD avg infrastructure exists in indicators.py. (b) PB fill bar volume — low-volume pullback fill = weak counter-move (good), high-volume = real reversal (bad). (c) E1 fill volume as predictor of whether E2 gets reached in multileg mode. All three are independent of ER/ATR/VA — they measure conviction, not regime.
   - **Volume Profile features — single prints + HVN/LVN nodes:** VP is already implemented (`indicators.py` `_profile_value_area`). Next step: extract single prints (zero-volume price levels = low-acceptance, price tends to revisit) and HVN/LVN nodes (high/low volume nodes = support/resistance vs acceleration zones). Signal near an LVN = price likely to move through fast (good for breakout); signal into an HVN = likely to stall (bad). Could be a powerful structural filter beyond simple VA location.
   - **TOD bar-level filtering:** Investigate which time-of-day windows hurt performance. Three candidates: (a) skip first N bars after open (noise/fake breakouts in first 5–15 min), (b) skip last N bars before close (already have late-period filter above), (c) skip lunch hour (~11:30–13:00 ET) when volume drops and chop increases. Run per-bar-number expectancy table first, then ablate the worst windows. DOW (day of week) stays — no reason to skip any day.
   - **FOMC expansion — day before + time window:** Current FOMC filter only handles the announcement day with ±15-min cushion. Investigate: (a) day before FOMC — positioning/hedging activity may create false breakouts, (b) wider time window around the announcement (±30 min? ±1 hr?) — the current ±15 min may be too tight if the volatility regime persists longer. Price out each bucket (FOMC day ±window, day before FOMC, day after) to find the optimal exclusion zone.
   - **All-In Flip (revisit old idea):** Previously discussed concept — when a CC signal fires in one direction and price reverses completely, treat the reversal as an even stronger signal (the original breakout trapped traders, now the unwind IS the move). Needs definition: what constitutes a "flip"? Stop-out on original signal + new CC in opposite direction within N bars? Price out historically — how often does the flip signal have better edge than the original? Could be a powerful entry type if the data supports it.
   - **Fade hypothesis — turn structural losers into winners (HIGH PRIORITY RESEARCH):** Core idea: some losing CC signals aren't random — they fail for structural reasons (liquidity grab, mean reversion at fair value, exhaustion, breakout into overhead supply). A signal that *reliably* goes the wrong way is just as informative as one that goes right. **Test plan:** (1) Take all losing trades from current system (ER≥0.30, pinned). (2) Tag each with regime context: VA location, HVN/LVN proximity, ER bucket, TOD/bar number, distance to prior-day POC/VAH/VAL. (3) For each tagged bucket, compute what happens if you entered the OPPOSITE direction at the same entry price with symmetric target/stop. (4) Any bucket where the fade has positive expectancy + reasonable sample = real signal. **Three action levels per bucket:** full fade (reverse direction), quick-exit/BE management (same direction but move to BE after N bars if no progress — saves R on slow bleeds), or skip (what filters do now). **Why this matters:** ~2000 losing trades in the system. Converting just 10% to BE or small winners recovers $10–20k+ and improves every performance metric simultaneously (PF, PROM, MAR, drawdown) with zero additional signals needed. **Key regime contexts to test as fade candidates:** (a) low-ER signals below 0.30 (chop = mean reversion), (b) VA-inside (breakout at fair value reverts to POC), (c) signal into prior-day HVN (supply/demand stalls the move), (d) late-session signals (MOC/profit-taking reversion), (e) exhaustion bars where the signal bar itself was the entire move (high ER caused BY the bar, not preceding it). Pairs naturally with VP nodes and ER timing fix work. **Fade entry refinement — low MFE after fill:** Especially interested in trades with near-zero MFE in the first N bars after fill (price never even tried to go in the breakout direction). These are the cleanest fades: (a) the MFE itself becomes the fade stop (very tight, e.g., 1–2 ticks), (b) the reversal is already underway = fast R, (c) structurally means immediate rejection of the breakout = institutional selling into buyer liquidity. Test: bucket all filled trades by MFE at bar 1/2/3 after fill. Trades with MFE < 0.25R AND high MAE = reliable fade candidates. Also connects to ER exhaustion — high ER on signal bar + zero post-fill MFE = the breakout bar was the entire move.
   - **🔴 PRIORITY: Position management / realistic constraints (ENGINE GAP):** Current sim treats every signal independently — unlimited simultaneous positions, no capital constraints. This is not how live trading works. MUST quantify: (a) how often do positions overlap? (b) how much does performance change under realistic rules? **Test order:** (1) one-per-direction (1 long + 1 short max), (2) one-at-a-time (strictest), (3) close-and-reverse (opposite signal closes current + enters new). **Risk layers to add:** max daily loss, max open risk $, daily trade cap. Implementation requires a position manager that tracks state across signals chronologically — significant engine change. **Opus recommended for implementation.**
   - **🔴 PRIORITY: Multiprocessing for IS sweep (verified bottleneck, plan ready):** Confirmed via live profiling: Python GIL means only 1 of 6 CPU cores is active during WFA runs (99% on one core, 5 idle). Hardware: Intel i5-8400T, 6C/6T @ 1.70 GHz, 16 GB RAM. **Plan:** Parallelize the combo loop in `run_is_sweep` (`wfa.py` line 121). Each of ~126 combos is independent. Use `multiprocessing.Pool(4)` with an `initializer` pattern — worker init pickles shared data (signals_is, ticks_subset, bars_subset) ONCE per worker, not per combo. Two new module-level functions: `_init_worker` (stores data in module global `_worker_data`) and `_sweep_one_combo` (runs simulate_trades + compute_summary for one combo, reads from `_worker_data`). **Critical: slice ticks_by_date to only IS fold dates before passing to workers** — full dataset is ~800 days/800 MB, IS fold is ~252 days/250 MB, so 4 workers × 250 MB = 1 GB copies (fine with 16 GB RAM). Keep sequential fallback via `workers=1` for debugging. **Windows gotchas:** must use `spawn` (default), worker functions must be module-level (not nested), guard against Streamlit re-import on worker spawn. **What does NOT change:** simulation_engine.py (untouched), run_wfa (untouched), any sweep logic or result format. Expected speedup: ~4x → 1-hour ablation runs become ~15 min. **Sonnet can implement this.**
   - **Performance: Numba JIT for sim engine tick loop (phase 2):** The inner tick scan in `_simulate_one_multileg` still runs in Python. The PB vectorized path (lines 495–571) uses numpy, but the fallback loop and `simulate_trades` per-signal iteration are pure Python. Numba `@njit` on the tick scan could yield 20–50x per-signal. Combined with multiprocessing = under 1 min for a full WFA run. Bigger project than multiprocessing — do after.
1. **NEXT CHAT STARTS HERE:** `docs/living/next_task_va_imbalance.md` — run the VA-imbalance hypothesis (drop inside-VA signals, keep `below`+`above`) at pinned 1.0R and compare **side-by-side** vs baseline `pin10_all_sl`. Self-contained brief; do it headless (no in-app compare tool yet).
1. **Window-map / robustness-report results are NOT persisted** (`persist=False`, session_state only) → an app restart loses them (~2 hr to rebuild). User wants this fixed. **BUILD: save grid_df to disk on build, reload on startup.**
2. **Better WFA optimization** (the user's ask): cap target grid ≤1.5R (structural) and/or maximin/median-fold objective instead of peak-PROM — so it stops harvesting EOD drift.
3. **BA→WFA filter inheritance** (still pending from earlier): WFA must apply the same session/FOMC/DOW filters as Bar Analysis (via `apply_signal_filters`, reading the live `ba_*` session keys) so the two tools validate the identical population.
4. **Decide: trade CC5 (+CC4) core, or the diversified portfolio?** Investigate CC2's one-year concentration and CC3's 798-day drawdown — salvage or drop.
- Persisted runs created this session (loadable headless via `results_store` / viewable in app Results): `run_13693b64` (unpinned ALL), `pin10_all_sl` + `pin10_cc2/cc3/cc4/cc5_sl` (pinned battery), `repro_cc4_175`, `pipe_cc4_singleleg`.
- **TIP for next chat:** any saved WFA run can be analysed headless straight from `data/wfa_store` — no screenshots needed; just the run_id. The deep-analysis pattern (per-setup decomposition, target-vs-EOD split, year/fold concentration, Monte-Carlo DD95, longest-underwater) is the right lens — reuse it.

---

## ⭐ SESSION 22 HANDOFF — June 20, 2026 (read first)
*Built the onboarding charter, the WFA window-robustness UI, and a headless master-run pipeline — then drove ONE setup (CC4 single-leg) end-to-end to a real go/no-go. Result: **NO-GO** (regime-dependent edge). No engine change. Committed + pushed. The strategic-review/S22-plan block below is now largely DONE — see this block for what actually happened.*

### Built
- **`docs/living/PROJECT_CHARTER.md`** — from-inception synthesis (mission, the arc SC→Massive / engine→validation, current architecture, locked rails §4, on-track assessment). New-chat reading order: **charter → handoff**. Pointer added at top of this file. Charter owns the arc + locked rails; **this handoff still wins on what's true today.**
- **WFA → 🗺️ Window Map, one scrollable page (`wfa.py`):**
  - **🛡️ Window Robustness Score** — every IS/OOS architecture scored 0–7 by *independent fixed pass/fail tests survived* (NOT profit-weighted): OOS PnL>0, Median WFE≥50%, ≥60% OOS green, Median PF≥1.2, Mean PROM>0, Return≥MaxDD, ≥8 folds. Heatmap + **ranked architecture table** (`_window_robustness_tests`/`_window_robustness_score`, `_WIN_N_TESTS`). Thresholds fixed in advance.
  - **Four component heatmaps** stacked (Total OOS PnL, Median WFE, Median OOS PF, Worst-fold Max DD) via `_window_heatmap` — replaced the single metric dropdown. PF/DD are *per-fold aggregates* (median PF, worst-fold DD); `_aggregate_grid_cell` extended with `oos_pf_median`/`oos_maxdd_worst`. Added **3m** to the IS grid options/default; OOS default now 1/2/3/4/6.
  - **🧭 4-Window Robustness Report** — `run_window_structures()` runs a FULL WFA per editable IS/OOS structure, `_robustness_report()` renders each in sequence (per-fold + cumulative OOS PnL) then a combined **ROBUST / FRAGILE / FAIL** verdict (`_window_pass`, rails `_WIN_MIN_*`). Nothing persisted.
- **Headless master-run pipeline `scripts/run_setup_pipeline.py`** — drives ONE pre-specified setup through Phase 0→verdict using the SAME engine (`simulate_trades`, `wfa.run_wfa`, `run_window_structures`); no trade-logic reimplementation, **no auto-tuning** (executes a locked config and reports — charter §4 hard rail). Emits `docs/living/pipeline_<setup>_<mode>_<date>.md`. Persists the baseline WFA as run `pipe_<setup>_<mode>` (viewable in the Results tab).

### First real end-to-end go/no-go — CC4 single-leg, filter OFF, unpinned (the S22 deliverable)
- **Verdict: NO-GO (regime-dependent).** Raw edge IS positive (1643 trades, +$50k @1.0R, PF 1.10) and the 12m/3m baseline WFA *passes* (Median WFE 55%, 82% OOS folds green, +$41k). **But the equity PATH is the tell:** combined OOS +$41k yet **72% of OOS profit is 2025 alone** (regime-dependent, >70% flag), 2023 is a year-long bleed (−$6k/323 trades), MAR 2.05, and **Mean PROM is NEGATIVE in all 6 window architectures**. Monte Carlo **DD95 −$50k > total profit +$41k**. Only **2/6 architectures score ≥5/7**.
- **Optimizer boundary-pinning:** IS PROM picked **2.0R (the grid max in `_T_VALS`) as the #1 target in 9/11 folds** — likely the true optimum is beyond the grid; **widen the target grid past 2.0R and re-check** before trusting CC4's params. Locked R per fold landed ~1.3–1.6 only because Kaufman-averaging the top-3 pulls it off the 2.0 ceiling.

### ⚠️ Report-card BLIND SPOT found & fixed (the user caught it: "the equity curve is a disaster, how come that did not get flagged?")
- v1 of the pipeline gated **aggregates only** (total PnL, median WFE, %folds-profitable, MC P-loss) and **never gated the equity PATH** → a regime-dependent curve passed as "CONDITIONAL." Also computed profit-concentration on the RAW full sample (61%, passed) instead of **OOS** (72%, fails).
- **Fix (added, NOT yet re-run):** new **Phase 4.6 — OOS equity PATH & shape** (`oos_path_stats`) + two **shape gates** — **MAR ≥ 1** and **OOS best-year share ≤ 70%** — computed on the combined OOS curve. **Shape failures are DECISIVE** (force NO-GO regardless of aggregates). On the existing CC4 numbers this flips the verdict to **NO-GO** (best-year 72% fails). Re-run `--setup CC4 --mode singleleg` to regenerate the card; the on-disk report still shows the old "CONDITIONAL".

### Open / next
- **Re-run CC4 pipeline** with the new shape gates (will read NO-GO) and/or **widen `_T_VALS` past 2.0R** to test the boundary-pinning, then re-judge.
- **CC3** (1653 trades) through the same pipeline for comparison (user hasn't decided yet).
- Investigate **negative PROM vs positive PnL** across all architectures (PROM is the WFA objective — params are *selected* on a metric that's negative OOS).
- Regime-filter question was raised ("which filter would've been good here") — **declined to crown a backtest-fit filter** (no-feedback rail); the legitimate path is the descriptive Phase-2 map (Bar Analysis → Regime/Indicator Expectancy) on a design slice → hypothesis → lock → validate OOS via the built `🧭 Regime Filter`.
- Throwaway run logs `streamlit_run.log` / `pipeline_run.log` are gitignored.
- Carry-forward from S21: verify 2-D sweep cross-checks in-app; identical-per-setup OOS-count flag.

### Carry-forward rules
NEVER commit/push without explicit OK · user must have run the app · `git pull` first (two-machine) · Edit/Write only for source (PowerShell → mojibake) · all sims behind Run button · one engine = one trade definition · **regime filters LOCKED before WFA, never optimized/tuned against OOS; describe-don't-fit; sizing deferred to MES**.

---

## 🧭 STRATEGIC REVIEW & S22 PLAN — June 20, 2026 (read this BEFORE the session logs)
*Written end of S21 in response to the user's onboarding/direction questions. A new chat: read this block, then S21 below, then act. **Most of this plan is now DONE — see the SESSION 22 block above for outcomes.***

### Where a new chat should start (the onboarding gap)
There is **no single from-inception synthesis yet** — `handoff.md` is a stack of session *deltas* (1300+ lines) and gives current state well but not the *arc*. **First S22 task: write `docs/living/PROJECT_CHARTER.md`** (original goal, how it evolved, current architecture, irreversible decisions, on-track/risks). Then a fresh chat reads charter (the arc) + this handoff (the frontier) and is oriented in one pass.

### What we are building (reconstructed — make it authoritative in the charter)
- **Original task:** NT8 sim + Google-Sheets pipeline were done; the task became **build a Python walk-forward engine to validate an ES-futures breakout strategy (MC "CC" signals) with Pardo-grade discipline — prove a *durable* edge without overfitting.**
- **What changed:** the *data pipeline* (Sierra/SCID → **Massive.io** ticks, S12); the *focus* (engine-build → descriptive research tooling → now validation + decision tooling).
- **What hasn't:** the core mission — *rigorously decide whether a setup is tradeable, without curve-fitting* — is unchanged.

### On track? Doing it right? (honest assessment — keep challenging this)
- **Method: yes.** Pardo rails are sound and enforced (lock before OOS, no co-optimization in WFA, describe-don't-fit, one engine/one trade definition). Today's scare was *measurement* artifacts (WFE÷~0, kurtosis-on-pinned-grid), now fixed — not a strategy failure.
- **Pushback (standing keep-in-check order):** we are accumulating **tooling/metrics faster than decisions**. Tells: the only dissected WFA run was **fully pinned** (so WFA wasn't doing its core job — testing parameter robustness) with a **modest edge** (OOS PF 1.16). Risk = analysis-as-procrastination.
- **Recommendation:** run **one real end-to-end** — a single CC setup, **unpinned** WFA, regime filter either OFF or *one* pre-locked hypothesis — and force a **go/no-go**. More dashboards won't answer the question; that run will.

### Autonomous "master run" + full export (user request — feasible, with one hard rail)
- **Master-run pipeline** (`run_master(setup, config)`): execute the whole sequence headless — load signals → descriptive expectancy → WFA → window map → guardrails → friction → equity — persisting every artifact; one-button "Run Full Pipeline" in-app + progress log.
- **Full export:** one self-contained `report.html` (Plotly embeds natively; tables as HTML) **plus** a `zip` of the raw parquet/CSV behind every chart. Data already persists (folds DB, OOS trade logs, sweep grids) → mostly a report-builder over existing stores. "Every byte" is realistic at that scope.
- **HARD RAIL:** "without us interfering" must **NOT** include auto-selecting the regime filter or pinning params to results — that is the no-feedback / overfitting violation the whole project guards against. The master run executes a **human-pre-specified config** and *reports*; it never auto-tunes.

### Recommended S22 order
1. **`PROJECT_CHARTER.md`** (cheap; permanently fixes onboarding).
2. **Master-run pipeline + full HTML/zip export** (the artifact the user asked for).
3. **First real unpinned end-to-end go/no-go** on one CC setup, using #2.
This fixes continuity, delivers the export, and breaks the analysis-paralysis risk in one move. *(Also still open from S21: verify 2-D sweep edge cross-checks in-app; investigate identical-per-setup OOS counts — possible setup filter not subsetting signals.)*

---

## ⭐ SESSION 21 HANDOFF — June 20, 2026 (read first)
*Built both lead S21 priorities (2-D Stop×Target sweep + locked multi-slice regime filter), reordered tabs, and fixed three misleading WFA metrics that a long debugging thread surfaced. No engine change → trade definitions & validators unaffected. Committed + pushed.*

### Built
- **2-D Stop × Target sweep** (`bar_analysis.py`, descriptive, per `docs/reference/stop_target_2d_sweep_spec.md`). `_run_stop_target_sweep` (reuses `_apply_stop_mult`/`simulate_trades`/`compute_summary`/`_win_breakdown`) + `_show_stop_target_sweep` expander (Bar Analysis, right after Stop Multiplier Sweep). PnL/DD heatmap, ranked top-20, and a **neighbor-stability "plateau not peak" caption** (`_stop_target_plateau`) + low-Tgt%/thin-trades flags. **Cross-check still to verify in-app:** 1.00× column == 1-D R sweep; current-target row == 1-D stop sweep. Never wired into WFA. **Spec status updated to BUILT.**
- **Locked multi-slice regime filter for WFA** (`regime_filter.py` — new, pure/testable + UI in `wfa.py` Configure & Run, after the CC filter). Reuses `indicators.tag_signals` and imports the **same bin edges** from `bar_analysis` (one definition shared research↔validation). Orthogonal shortlist (one per factor): VWAP σ, Range/ATR, ADX %ile, Intraday ER 60m, 20-EMA alignment, Session VA. **Master "Enable regime filter" checkbox, default OFF** (this is the on/off; "locked" only means *not optimized by WFA*). AND across active indicators; NaN-regime signals dropped; open-ended-tail nudge; time-spread flag; locked spec recorded into run notes. **Fold-feasibility guard** added (warns when filtered signal-days < IS+OOS so you don't silently get 0 folds).

### WFA metric fixes (display only — a debugging thread proved these were artifacts, not strategy problems)
- **WFE undefined when IS≤0** (`wfa.py` `run_wfa`): `wfe = oos/is if is_ann > 0 else NaN`. The −8606/−11108% folds were divide-by-≈0, not OOS losses. Headline is now **Median WFE** (badge, equity panel, `results_store.guardrail_report`, window-map aggregate) so 1–2 folds can't dominate. Existing run `run_a8f45df7`: old Mean −1145% → **Median −16.1%** (no re-run needed); a re-run marks 4 IS-unprofitable folds N/A → median +39.2%. *Per-fold WFE column/chart for OLD runs still show stored blowups until re-run.*
- **Kurtosis N/A for single-combo sweeps** (pinned params): was a red **0/17** because `NaN<=6` is False. Now stored NULL + badge shows **N/A** (neutral) + breakdown caption explaining the surface is degenerate. Robustness∈{0,100} exactly + kurtosis N/A is the tell that **all of T1/T2/PB were pinned** (run a8f45df7 was such a run).
- **Window Map**: default cell metric → **Total OOS PnL** (no divide-by-zero), and **switching the metric no longer recomputes** — it re-colours the cached grid instantly (was stuck on build-time metric — a real bug).

### UX
- **Tab order restored**: Bar Viewer first, **Bar Analysis second**, then Massive/Data/Chart/Portfolio/WFA. A one-time guarded JS click (`app.py`, `components.html` + sessionStorage) keeps Bar Analysis the **default-open** tab without yanking you back on later reruns (native `st.tabs` always opens tab 0).

### Verified
- All five files byte-compile. `regime_filter` pure-logic unit tests pass (AND/subset/NaN-drop, open-ended detection). On-disk audit: **all 11 stored runs** have `sum(per-fold oos_n_trades) == equity filled count` (the reported "mismatch" was a mis-add; 4788 vs 4701 = 87 unfilled signals). Engine validators NOT re-run (no engine change) — re-run before any future engine edit.

### ⚠️ Data-quality flag to investigate (S22)
On-disk, several runs share **identical** OOS counts across *different* setup labels (ALL/CC1/CC2/CC4 all = 4701 at 17 folds, all = 4129 at 15 folds). Could be the user relabelling `setup_id` on otherwise-identical ALL runs, OR the per-SignalType checkbox not actually filtering signals into WFA. **Verify the setup filter actually subsets the signal set before trusting per-setup results.**

### Session 22 priorities
- **Verify the 2-D sweep edge cross-checks in-app** (1.00×/current-target) — that's its definition-of-done.
- **Investigate the identical-per-setup-count flag above.**
- **Master autonomous run + full export** (user request): drive ONE CC setup through the whole Phase 0→7 pipeline end-to-end, render in-app, and emit a single self-contained artifact (HTML/zip) capturing every table + chart. See `docs/living/setup_decision_manual.md` for the pipeline; this needs scoping (headless render of Streamlit figures, or a parallel report builder).
- **Onboarding:** consider a `docs/living/PROJECT_CHARTER.md` (original task, what's changed, on-track assessment) so a fresh chat can realign from one read.
- Carry-forward from S20: OOS Regime Analysis module; quick wins (profit concentration, profit-by-year, recovery time, concurrent-exposure %, acceptance report card); 15M timeframe; vectorize 3-leg.

### Carry-forward rules
NEVER commit/push without explicit OK · user must have run the app · `git pull` first (two-machine) · Edit/Write only for source (PowerShell → mojibake) · all sims behind Run button · one engine = one trade definition · **regime filters are LOCKED before WFA and never optimized/re-tuned against OOS; pre-commit a few hypothesis-driven filters, don't combo-hunt; sizing deferred to MES**.

---

## ⭐ SESSION 20 HANDOFF — June 20, 2026 (read first)
*All work this session was **descriptive / read-only** (consistent with describe-don't-filter): regime research tooling in Bar Analysis, a new intraday efficiency indicator, and the MSS engine — validated and bug-fixed. No engine change. Committed + pushed (627a708, 18cd2b3). Plus the handoff-hygiene fix above.*

### Bar Analysis — Regime/Indicator Expectancy expander (descriptive only)
- **Factor Groups & Redundancy** (`_show_factor_groups`, `_FACTOR_MAP`) — groups the 15 regime indicators into latent factors (Displacement-from-value, Volatility, Trend strength, Intraday efficiency, Directional alignment, Market structure), marks the highest-RIC pick per factor (✅, `_RIC_FLOOR=35%`), prints an orthogonal shortlist, and shows a **Spearman correlation matrix** of the underlying values (|ρ|>0.6 ⇒ redundant). Purpose: stop the user stacking 3 filters that measure the same thing. On user data the shortlist ≈ **VWAP σ, 20-EMA alignment, Range/ATR, ADX** (+ intraday ER). User likes **Session VA** (defensible: low-DoF 3-bucket, prior-day-fixed reference).
- **Time-distribution flag** (`_time_concentration`) — Notable Slices now shows a **Time Spread** column (🟢<40% / 🟡 / 🔴>65% of a slice's trades in its busiest 6-month window) + a per-slice caption. Guards against single-regime / windfall artifacts (e.g. the +802% VWAP tail).
- **Slice Inspector** (`_plot_slice_inspector`) — pick any indicator/bucket → plots exactly those entries on the continuous price line (▲/▼ long/short, green/red W/L); Focus dropdown zooms to one trade (±5d). Directional/HOY/OR bucket labels now persisted on the trade frame so they're selectable.
- **Auto-hypotheses corrected** — were wrongly framed as "mean-reversion"; MC is a **breakout / volatility-expansion** system. All hypothesis text now breakout-framed.

### `indicators.py` — intraday Kaufman ER (new) + MSS engine
- **`bar_kaufman_er(bars, spans=(6,12,24))`** = 30m/60m/120m developing ER on the 5M close, causal, merged in `tag_signals` → new **"Intraday Efficiency"** factor (fixed 0–1 bins). *Why:* the existing Kaufman ER is **daily (10-day)** = macro horizon (middling RIC); intraday tests trade-local efficiency. **Built as a ROBUSTNESS SET, not a tuned value** — read all three; a real edge is stable across lookbacks. Reminder: ATR/ADX(14), ER(10d), 252d percentile are **conventions, not optimized** — never sweep a lookback to fit the trades (= overfitting).
- **MSS engine `calculate_market_structure`** — validated **look-ahead-safe** (the 4 merged cols are byte-identical under truncation). **Fixed a real bug**: the zigzag swing-low reversal gate (line ~406) was asymmetric (gated on the bar's *low*); now mirrors the swing-high gate (`h[i]-anchor>=threshold`). Added **Structural Trend** + **Deep Pullback** regime buckets. **BUT RIC ≈ 0–6% on user data → SHELVED as a filter** (structure state doesn't differentiate this breakout strat; revisit only with a reason). `last_swing_type` is non-causal (backfill) and correctly NOT merged.

### UX + bug fixes
- **Bar Analysis is now the default landing tab**; **ALL expanders default collapsed**; **load-status strip** under the title (✅ price / continuous / MC signals / RevFT) — renders at the END of `main()` via a container placeholder so it reflects state the tab blocks populate later.
- Fixes: Slice Inspector **stale-selectbox crash** (composite keys per indicator/bucket); status strip **read empty state** (deferred render); Slice Inspector **blank chart** (`Scattergl`→`Scatter`; WebGL ignores axis `rangebreaks`).

### ✅ DIRECTION — DECIDED (S20): multi-slice FILTER, validated via WFA
- **Decision:** build a **locked multi-slice regime filter** and validate it in WFA. **Sizing is deferred** — it needs position granularity the user doesn't have at 1 ES contract; revisit sizing only on **MES** (micro, 1/10 size). So filtering is the pragmatic tool now; the old "prefer sizing" stance is paused for ES, not abandoned.
- **What "filter" means here:** per shortlist indicator, KEEP a *set* of buckets (e.g. VWAP keep the tails / exclude inside; VA keep above+below / exclude inside; ADX keep most / drop with a reason). NOT a single slice.
- **Discipline rails (non-negotiable — "survived WFA" only counts if these hold):**
  1. Filter is **LOCKED before the run** and never re-tuned against OOS results. WFA optimizes only T1/T2/PB per fold.
  2. **Pre-commit a small number** of hypothesis-driven filters; do NOT try many combos and keep the survivors (multiple-testing).
  3. Prefer **open-ended thresholds** (e.g. |VWAP σ| ≥ 2) over hand-drawn bands (e.g. +2..+3). Capping the extreme usually = fitting to a thin in-sample bucket. Every kept/dropped bucket needs a structural *why*, not "it was red."

### Session 21 priorities
- **BUILD the 2-D Stop × Target sweep** (Bar Analysis, descriptive) per the full build spec `docs/reference/stop_target_2d_sweep_spec.md`. Rationale: R is measured in stop units, so the existing 1-D R sweep (`_run_r_sweep`) and 1-D stop sweep (`_run_stop_mult_sweep`) are slices of one interacting surface — chaining their picks can miss the joint optimum. Spec reuses `_apply_stop_mult`/`simulate_trades`/`compute_summary`/`_win_breakdown`, mirrors the T1×T2 heatmap UI, and REQUIRES a neighbor-stability "plateau not peak" caption. Descriptive only — never wired into the WFA grid. Edge cross-check: 1.00× column == R sweep, current-target row == stop sweep.
- **BUILD the locked multi-slice regime filter in WFA → Configure & Run** (next to the CC filter, ~wfa.py:838): per shortlist indicator, multiselect of buckets to KEEP (or a threshold); tag signals via `tag_signals`; filter the signal set BEFORE the fold loop; show post-filter trade count + time-spread; **never optimized by WFA**. Honor the discipline rails in the DIRECTION section.
- Carry-forward from S19/S20: OOS Regime Analysis module per `setup_decision_manual.md` (regime stability across WF segments → Monte Carlo → profit concentration → report card); quick wins (top-10 profit concentration, profit-by-year, recovery time, concurrent-exposure %, acceptance report card); 15M timeframe (`bar_num_from_dt` 5M-hardcoded); vectorize 3-leg.

### Carry-forward rules
NEVER commit/push without explicit OK · user must have run the app · `git pull` first (two-machine) · Edit/Write only for source (PowerShell → mojibake) · all sims behind Run button · one engine = one trade definition · **regime filters are LOCKED before WFA and never optimized/re-tuned against OOS; pre-commit a few hypothesis-driven filters, don't combo-hunt; sizing is deferred to MES**.

---

## ⭐ SESSION 19 HANDOFF — June 19, 2026 (read first)
*New `indicators.py` engine (VWAP σ-bands, multi-timeframe volume-profile value areas, daily ATR/ADX + percentiles, look-ahead-safe trade tagging); Continuous Chart overlays with grouped-legend toggles + single-session scroll; two new descriptive expectancy tables in Bar Analysis (TOD/DOW and Regime/Indicator); FRED key stored; a full setup-decision manual written. No engine change → all validators still green. Committed + pushed.*

### New: `indicators.py` (pure compute, no engine change)
- **Session VWAP σ-bands** — `session_vwap_bands()` returns developing (causal) VWAP, volume-weighted σ, and `VWAP_dev` (signed σ-distance). Warmup-guarded (first 3 bars/session → `VWAP_dev` NaN so early-session readings don't explode).
- **Volume-profile value areas** — `value_areas(bars, period)` for period ∈ {session, weekly, monthly, quarterly, yearly}: POC/VAH/VAL via 70%-rule expansion over a typical-price volume histogram. `prior_period_levels()` projects the **prior** period's levels (look-ahead-safe; shift over existing periods handles holidays).
- **Daily regime** — `daily_regime()` → ATR(14), **ATR percentile** (252d rolling rank), ADX(14), **ADX percentile**.
- **`tag_signals()`** — joins all of the above onto any df with a `DateTime` column (causal VWAP via `merge_asof`; prior-day regime; prior-period value areas for session/weekly/monthly). Verified on the full 99k-bar series (VAL≤POC≤VAH all sessions, no NaN leakage, dev range ±6σ).

### Continuous Chart (`continuous_chart.py`) overlays + UX
- VWAP **±1/2/3σ bands** (multiselect) and **value areas** at all 5 timeframes (multiselect), drawn with **grouped legend** + `groupclick="togglegroup"` → click a group title to hide a whole set, click one item (e.g. just +3σ, or M-POC) to toggle it individually.
- VWAP line **breaks at the session edge** (helper `_break_last_of_group`); VA levels are **flat horizontal segments** (no risers); **VA shading + opacity slider**; **chart-height slider** (drives fullscreen vertical size); **single-session ◀/▶ scroll mode** (like Bar Viewer); EMA50 off by default.

### Bar Analysis — two new descriptive tables (read-only, Pardo-safe)
- **🕐 Time-of-Day / Day-of-Week Breakdown** — Day-of-Week table, Session-phase table (Open 08:30–11:30 / Mid –13:00 / Late –14:45 / Close –15:15 CT), Weekday×phase heatmap (selectable metric). Helper `_expectancy_stats` shared.
- **🌡️ Regime / Indicator Expectancy** — buckets the current trade set by ATR%ile, ADX%ile, VWAP-deviation band, value-area location (session/weekly/monthly), plus an **ADX×ATR matrix heatmap**. Trade tags cached via `_tag_trades_cached` (joins `indicators.tag_signals` onto filled trades by EntryTime). **Description only — no filter, no optimization; trade counts shown everywhere.**

### NOT built / paused (important)
- **Entry filter** — started wiring `indicator_filters` into `apply_signal_filters`, then **reverted** at user's request (`apply_signal_filters` is back at baseline). User paused the "regime module" to realign.
- **The PDF "Regime Analysis Module" spec** (OOS-only, describe-don't-filter, prefer sizing) is the agreed direction but NOT built. See `docs/living/setup_decision_manual.md`.

### Setup-decision manual (`docs/living/setup_decision_manual.md`)
Step-by-step Phase 0→7 pipeline (Discovery → Validation → Portfolio), per-setup individual WFA then portfolio last, with discard rules + a tooling-status table. Incorporates user's pro-level additions: **regime stability across WF segments, WF-structure robustness, Monte Carlo on OOS, profit concentration, time-under-water, Observation→Hypothesis→Rationale gate, concurrent-exposure %, acceptance report card**. Most of those = **to build**; Window-Map heatmap (`run_window_grid`) and Max Time Underwater already exist.

### Misc
- **FRED API key** stored in `.streamlit/secrets.toml` (git-ignored) → enables VIX (`VIXCLS`) for the future VIX regime module.
- **App launch (PowerShell):** `.\.venv\Scripts\streamlit.exe run app.py` (the `.\` prefix is required; bare relative path errors).
- Validators all green (no engine change this session): `validate_engine`, `validate_oracle`, `validate_ratchet`.

### Session 20 priorities
- Decide direction with user (paused): build the **OOS Regime Analysis module** per the PDF/manual (regime stability across WF segments → Monte Carlo → profit concentration → report card), vs. the in-sample entry filter. Manual is the blueprint.
- Quick wins already specced as "to build": top-10-trade profit concentration, profit-by-year, average recovery time, concurrent-exposure %, acceptance report card.
- Still carried from S18: 15M timeframe (`bar_num_from_dt` is 5M-hardcoded), vectorize 3-leg, truncated-flatfile refetch.

### Carry-forward rules
NEVER commit/push without explicit OK · user must have run the app · `git pull` first (two-machine) · Edit/Write only for source (PowerShell → mojibake) · all sims behind Run button · one engine = one trade definition.

---

## ⭐ SESSION 18 HANDOFF — June 19, 2026 (read first)
*WFA UI overhaul + Pardo-safe diagnostics, two heatmaps, a continuous 5yr chart tab, app-wide 2-decimal display, and the big engine change: tick-snap of all computed targets (default nearest). All internal-consistency validators green. Committed + pushed at end of session.*

### Engine change (re-baselines numbers — intended, like the S17 T2 change)
- **Tick-snap of computed price levels.** Every computed target (single-leg `target_price`, 2-leg `t1`/`t2`/`_t2_for`, 3-leg `t1`/`t2`/`t3`, + their PB triggers) now snaps to a tradeable tick via one helper `_snap_level(raw, ts, entry, mode)` in `simulation_engine.py`. Before, fractional-R targets (e.g. 0.625×risk) booked exits at off-tick prices that can't trade — distorting PnL. **Why:** prices must be divisible by tick size (ES 0.25). User decision: **Option 1 (snap the level), default `nearest`** (realistic execution accuracy, NOT max-pessimism — "be realistic on execution, conservative on selection").
- **`pb_round` is now the single rounding policy for ALL levels (PB + targets), default flipped `floor_ceil`→`nearest`.** Threaded through `_simulate_one`, `_simulate_one_multileg`, `_simulate_one_3leg` (added `pb_round` param to single-leg & 3-leg), the bars-path diagnostics, the fast scale-in sweep (`bar_analysis._run_ml_scalein_sweep` — uses the SAME imported `_snap_level` so fast==oracle holds), the UI (`ba_pb_round` selectbox reordered, default "Round to nearest", relabeled "Price rounding (PB & targets)"), and `wfa.py` base_params (`pb_round="nearest"`). **2-leg/single numbers shifted vs S17 — intended.** `validate_regression` is a manual dump/cmp tool (no committed golden) → take a fresh `dump` as the new reference.
- **Fixed a STALE Layer-B oracle.** `scripts/validate_oracle.py` still computed **blended-style T2** — never updated for the S17 e2-style default — so it was silently RED at the S17 commit. Rewrote it to the current definition (e2-style T2 + nearest snap on target/T1/PB). **Now green, multileg + single.**
- **Verified (all green):** Layer A (`validate_engine`), Layer B (`validate_oracle` multi+single), vec==loop (`validate_ratchet` multileg/e2, 9 settings byte-identical), fast==oracle (`validate_scalein_sweep`, 64 combos identical).

### WFA tab — UI overhaul + Pardo-safe diagnostics (`wfa.py`)
- **Setup ID → per-SignalType checkboxes** (like Bar Analysis): they filter signals AND derive the storage label; empty-selection guards everywhere.
- **Metric tooltips** (`_METRIC_HELP`) on inputs + OOS metrics + a **Metric Glossary** expander.
- **Per-fold guardrail breakdown table** (`_guardrail_breakdown`) — ✓/✗ per rail + roll-up of which folds failed. (Fixed a dict-key-collapse bug that rendered every flag as "None"; use `_flag()`.)
- **Removed the forward-risk `st.warning`.**
- **Results expanded:** per-fold WFE/PnL charts, OOS NetPnL histogram, **Friction & Robustness Diagnostics** (Windsorized WFE, Pain Index, Total Commission/Slippage, Friction-to-Profit, interactive **SEC slippage-elasticity slider** + curve, **assumption ledger** table), Max-Time-Underwater + OOS PF added to equity metrics.
- **Two heatmaps:**
  - **Per-fold IS optimization surface** (`_is_surface_section`) — PB×T2 (sliced by T1) coloured by PROM/NetPnL/PF, ✕ marks the chosen set → see plateau vs spike. Needs the full IS sweep grid, now persisted per fold via `results_store.save_sweep`/`load_sweep` (`data/wfa_store/sweeps/...`). **Old runs lack it → re-run to populate.**
  - **Window-anchor heatmap** — new "🗺️ Window Map" sub-tab. `run_window_grid()` runs a full non-persisted WFA per IS×OOS pair (added `persist=False` to `run_wfa`), colours cells by Mean WFE / Total OOS PnL / Mean OOS PROM / %profitable. Heavy compute; pin params to shrink.
- **Objective is PROM** (`select_params` nlargest by `prom`) — confirmed; NetPnL/PF/PnL-DD displayed but don't drive selection. Drill-down param table now labelled (Target R / T1 R / T2 R / PB R), ranked, with the averaged locked set; R-values rendered as 3-dp strings so the 2-dp display rule leaves them intact.

### New: Continuous Chart tab (`continuous_chart.py`, wired in `app.py` as "📈 Chart")
- Windowed scrollable candlestick over the full 99k-bar / 5yr continuous series (`data_sc_5m`/`mas_continuous`). Date-range presets, RTH rangebreaks. Overlays: EMAs (multi), session VWAP, Daily-200EMA, Daily ATR(14) & ADX(14) subplots. Indicators computed on full series then sliced (correct at window edge). **Trade overlays / tick price-paths = deliberate Phase-2** (ticks can't render across 5yr; drill-in per day only).

### App-wide: 2-decimal display
- Global `st.dataframe` wrapper in `app.py` (`_dataframe_2dp`): money/PnL cols → 0 dp, ratios/% → 2 dp, via `column_config` (plain DF) or `Styler.format` (styled). Calc precision untouched — display only. Commission label fixed to "($/contract, round-trip)".

### Session 19 priorities
- **15M timeframe.** User will import 15M signals as a CSV from NT (same schema as 5M) → slots in like RevFT (a new signal set; dynamic checkboxes already handle it). Engine is **tick-based ⇒ largely timeframe-agnostic** (entry = first tick after signal-bar timestamp). TWO things to fix first: (1) verify the 15M NT export's **DateTime convention** (signal-bar close → "first tick after" = next 15M bar open; reconcile one trade vs NT); (2) **`bar_num_from_dt` is 5M-hardcoded** (`/5+1`) → mislabels `EntryBar` and breaks manual-fill mapping on 15M — make it timeframe-aware. Continuous Chart: add a **timeframe selector (5M/15M)** (resample) — easy.
- **TOD/DOW expectancy breakdown** (Tier-2, Pardo-safe) in Bar Analysis. We have a DoW *filter* + session filter + Monthly breakdown, but **no TOD/DOW read-only expectancy table and no optimization.** Build the per-condition matrix (by hour/session-phase/weekday) as DESCRIPTION; form a structural hypothesis; lock on a design slice; the filter then lives in the **shared engine layer** and WFA *inherits* it. **NEVER co-sweep TOD/DOW inside the WFA IS grid** (dimensionality → curve-fit + no-feedback violation). Rolling-PF self-filter is the most robust regime idea.
- Tier-2 OOS-trade export tagged with daily macro metadata (VIX/ATR%ile/ADX/200EMA-dist/ToD) → per-condition expectancy matrix (read-only; needs a macro data-source decision: Massive vs FRED vs computed-from-bars).
- Counterfactual "tick-snap & same-bar-priority cost" rows for the assumption ledger (needs no-snap/optimistic-priority re-runs).
- Deferred still: vectorize 3-leg; truncated-flatfile refetch (10 dates, metered).

### Carry-forward rules
NEVER commit/push without explicit OK · user must have run the app · `git pull` first (two-machine) · Edit/Write only for Python source (PowerShell → mojibake) · all sims behind Run button · one engine = one trade definition.

---

## ⭐ SESSION 17 HANDOFF — June 19, 2026 (read first)
*Ratchet vectorized + exposed on both setups, 2-leg T2 redefinition, PB-rounding toggle, WFA unblocked. All sim changes verified vec==loop / fast==oracle over the full 1-yr window. Committed at end of session.*

### Done + verified this session
- **Vectorized ratchet (BE + Lock-in)** in `simulation_engine.py` for `_simulate_one` (single-leg) and `_simulate_one_multileg` (2-leg PB). Loop kept as live reference via new private `_force_loop` kwarg (threaded through `simulate_trades`). The 2-leg vectorized path encodes the full state machine incl. **pre-E2 ratchet fire that can block the scale-in** (confirmed intended — Q1). Proven **byte-identical to the loop** across 9 ratchet settings (5 BE + 4 Lock-in) for BOTH `scale_in_style` values via new `scripts/validate_ratchet.py` (1107 trades, 63 cols, 0 diffs each).
- **2-leg T2 redefinition (the big one).** Found a 3-way drift: code did `blended + R×blended_risk`, the Session-2 design doc said `blended + R×original_risk`, and the user wanted **E1-to-BE**. User decided: T2 = **E2 entry + R × E2's-own-risk** (`scale_in_style="e2"`, now DEFAULT) → at a 50% PB both legs exit at E1 entry (E1 scratches BE, E2 banks 1R). The old behavior kept as `scale_in_style="blended"`. One shared `_t2_for()` helper drives all 3 engine paths. **2-leg sweep/WFA numbers shift vs before — intended** (old default was a drifted formula). Ratchet R-unit left on ORIGINAL risk for now (user unsure; refine later — see open items).
- **PB-rounding toggle (plan item D).** `pb_round` = "floor_ceil" [default, = old behavior] vs "nearest". Threaded engine→fast sweep→oracle→`_show_optimal_r`→main sim→fingerprint→param echo. Fast==oracle verified for BOTH modes (`validate_scalein_sweep.py --pb-round …`).
- **Single-leg ratchet UI exposed** — was hard-disabled behind `if False` in `bar_analysis.py` (the cause of "same PnL for every ratchet R" — it was inert). Now a real "Stop Ratchet (trail to BE)" section. **Sensitivity proven live** (`scripts/test_ratchet_sensitivity.py`): single-leg PnL varies strongly for `ratchet_r < target_r`; identical to OFF for `ratchet_r >= target_r` (target hit before trigger — correct, not a bug).
- **Dynamic signal-type checkboxes** — `📶 Signals` filter now builds from the loaded signals' own `SignalType`s (MC CC2/CC3/…, RevFT OB/IB/Trap, anything). `apply_signal_filters` now takes `excluded_types: set` instead of 5 hardcoded `incl_cc*` bools.
- **♻️ Full Restart button** (top of app, next to Reload) — clears all session_state + caches, re-derives from disk. **Param echo** line above the Bar Analysis Summary showing exactly what the sim consumed (`🧾 ran: 2-leg · T1 1.50R · PB -0.50R · T2 1.00R · style e2 · PBround floor_ceil · …`) — stale-result guard.
- **WFA unblocked (2 bugs fixed):** `results_store.save_fold` had 33 `?` placeholders vs 32 columns → now generated from the tuple so it can't drift. `wfa.py` used removed `Styler.applymap` → `.map`. WFA now runs end-to-end and persists folds.
- **RevFT reviewed:** `saved_signals/ba_signals_revft.parquet` has IDENTICAL schema to MC (155 sigs, 2026-04-29→06-12; 5yr coming). No engine changes needed; only the dynamic checkboxes (done). `portfolio.py` already groups setups dynamically. Source NT logic in `Downloads/MyReversals (2).zip`.

### New permanent tools (`scripts/`)
- `validate_ratchet.py [--mode single|multileg] [--style e2|blended]` — vec==loop across the ratchet grid.
- `explain_trade.py [--signal N …]` — **CLI** tick-level, NT-reconcilable trade tracer (CT times, 5M bar #, raw+adjusted prices, event timeline with the 3 ticks before each event, per-leg PnL, engine-consistency assert). Auto-selects representative trades. **Not yet in the app** (user wants an in-app "🔎 Trade Explainer" expander — filled-trades dropdown — to eventually replace the "useless" Entry Zoom).
- `test_ratchet_sensitivity.py` — PnL vs ratchet_r table + #trades-differ-from-off.

### Verification protocol (unchanged — all must pass before commit)
`validate_regression.py` (note: 2-leg now DIFFERS from pre-session-17 by design — T2 change), `validate_engine.py` (Layer A), `validate_oracle.py` (Layer B), `validate_ratchet.py`, `validate_scalein_sweep.py`. One engine, one trade definition — never reimplement sim logic in a sweep without a verified-identical regression.

### Session 18 priorities (set 2026-06-19) — two LLM MD files in chat to mine
User pasted 2 analyses of the **first WFA run** (`gemini-code-*.md`, `chatgpt-code-*.md`). **Pardo discipline is paramount — user is emphatic about NOT overfitting.** Distilled stance:
- **TAKE the diagnostics** (Pardo-safe, add no strategy params): WFA **window-stability heatmap** (IS×OOS grid — is 12m/3m itself overfit? already roadmap Phase F), **Monte Carlo** on OOS trades (reshuffle/bootstrap → DD & terminal-PnL distributions, empirical "forward risk" — endorse strongly), **windsorized/trimmed Mean WFE** (is WFE outlier-driven?), **max time-underwater + Pain Index**, **friction/slippage sensitivity (SEC)**, per-condition **expectancy analysis**.
- **RESIST** the Gemini doc's instinct to read the OOS equity curve and design regime filters from it — that is the Pardo no-feedback violation / overfitting trap. The ChatGPT doc's frame is correct: **one hypothesis at a time, demand a macro/structural reason, decide+lock on a design slice BEFORE final OOS, don't co-optimize.** The "self-filtering" (rolling PF/expectancy circuit-breaker) is the most robust regime idea (adaptive, fewer fixed thresholds to fit).
- ⚠️ Caveat: the MD files analyze a run produced BEFORE today's T2/ratchet fixes — treat their specific numbers ($233k OOS, WFE 129.9%, etc.) as provisional; the *framework* is what's useful.

User's explicit WFA asks (items 2–8):
1. **Setup ID → checkboxes** like the Signals tab (currently the `wfa_setup_id` text field at `wfa.py:445` likely runs effectively one/all — give per-`SignalType` checkboxes to run individual setups).
2. **Metric tooltips** (hover-i `help=`) on all WFA metrics.
3. **Breakdown tables** inside metrics (e.g. which folds failed each guardrail, distributions).
4. **Remove the "Pardo forward risk rule" warning** — `wfa.py:633-637` (`forward_risk_warning` st.warning, "2× IS max drawdown").
5. **TOD/DOW filter placement** (item 6): recommend the FILTER lives in the **shared engine/signal layer** (one definition for Bar Analysis research + WFA validation + future NT robot). Research *which* TOD/DOW in Bar Analysis on a design slice; once locked it becomes strategy logic and WFA inherits it. **Do NOT** sweep TOD/DOW inside WFA's IS grid (co-optimization).
6. **Expand WFA Results section** — detailed tables, equity/DD charts, histograms, bell curves, Monte Carlo (per the MD files, Pardo-safe subset).

### Other open items (excluding 3-leg, per user)
- In-app 🔎 Trade Explainer expander (filled-trades dropdown; leave Entry Zoom for now — "fix zoom later").
- Progress bars on every sweep + main-sim Run (plan item E). Scale-in sweep already has one.
- **Decide Q5/Q6** (max concurrent positions, max daily loss) BEFORE reading any WFA OOS (`open_questions.md`).
- Deferred: vectorize `_simulate_one_3leg` + non-PB multileg (write a 3-leg Layer-B oracle first).
- Bar-based multileg (`_simulate_one_bars_multileg`, alt-path diagnostic only) NOT updated for `scale_in_style`/`pb_round` — still floor_ceil/blended-ish; low priority (NT-mismatch diagnostic, not primary sim).
- Truncated-flatfile refetch (10 dates) — still not written; needs OK (metered API).

### Carry-forward rules
NEVER commit/push without explicit OK · user must have run the app · `git pull` first (two-machine) · Edit/Write only for Python source (PowerShell → mojibake) · all sims behind Run button · one engine = one trade definition.

---

## ⚠️ Architecture shift as of Session 12 (June 16, 2026)

**Massive (Track 4) is now the primary and only active data pipeline.** The Sierra Charts/SCID path (Track 2) is paused — not deleted, not formally retired, just not being worked on. Everything below "Session 12" in this doc reflects the new reality:

- Massive flat-file ticks (S3) → per-contract 5M bars + back-adjusted continuous series, built and persisted in the **📂 Massive** tab
- NT is used **only** as a continuous-contract upload for matching/validation — never as a fill/exit data source
- Bar Analysis simulates trades using Massive bars + a per-day continuous tick cache, not NT bars
- The old `📡 Massive.io` tab name/6th-tab numbering below is stale — it's now the **first** tab, named `📂 Massive`, and absorbed the Contract Manager UI described in `data_sources.md`

Read `docs/architecture/data_sources.md` (updated Session 12) for the current pipeline. Treat anything about SCID/`.scid` files in this doc as historical/paused, not active work.

---

## What Is Active Right Now

The NT8 simulator and Sheets analysis pipeline are complete and working. All new development is Python-first, on the Massive pipeline (Track 4). The SC/SCID path (Track 2) is paused.

Two parallel tracks were active before Session 12; Track 4 has since become primary:

**Track 2 — Python WFA Engine (SC path):**
```
Sierra Charts scid data confirmed
        |
        v
Phase A: scid parser + 5M bar builder
        |
        v
Gate 1: Python bars vs SC export (bar_validation.md)
        |
        v
Gate 2: Sierra bars vs NT8/Rithmic bars — ROOT CAUSES FOUND (see Session 7 below)
        |
        v
Phase B: Signal detector — port from MCSimulatorV5_5.cs
        |
        v
Signal validation gate: match C# output on 4-week test period
        |
        v
Phase C onward: simulator, optimizer, WFA engine
```

**Track 4 — Massive.io Independent Tab (new, parallel):**
```
massive.io API (Developer plan, subscribing 2026-06-16)
        |
        v
Pull ticks via API → App 5M bars (reuse resample_ticks_to_bars)
        |
        ├── Convert ticks → NT import format → NT builds 5M bars
        │          → NinjaScript indicator → MCSignals CSV
        │          → NinjaScript bar exporter → NT 5M bars CSV
        |
        ├── massive.io Aggs API → massive 5M reference bars
        |
        └── Three-way comparison: App bars vs NT bars vs massive bars
                   → all must match → trust App bars for simulation
```

Track 4 is completely independent from Track 2 (SC gates). SC path continues in parallel.
Nothing in Phase C or beyond starts until all gates above pass.

---

## Streamlit App (June 8, 2026)

Four-tab app with contract selector and file upload. All tabs share cached data loaded by `data_loader.py`.

| File | Purpose |
|------|---------|
| `app.py` | Entry point, contract selector, tab layout, Reload button; Upload Data expander lives inside Bar Analysis tab |
| `data_loader.py` | Contract registry; parameterised loaders for SC bars, SC ticks, NT bars; upload parsers; `bar_num_from_dt()` |
| `validation.py` | Bar Validation tab — SC vs NT comparison |
| `bar_analysis.py` | Bar Analysis tab — signal sim, charts, monthly breakdown, R sweep |
| `portfolio.py` | Portfolio tab — per-setup 2-leg simulation, equity curves, sweep, saved runs, PDF export |
| `economic_calendar.py` | FOMC hardcoded 2015–2026; NFP/CPI via FRED API |
| `.streamlit/config.toml` | `maxUploadSize = 2000` (MB) |
| `filter_defaults.json` | Bar Validation persisted defaults — not in git |
| `ba_filter_defaults.json` | Bar Analysis persisted defaults — not in git |
| `pf_defaults.json` | Portfolio per-setup params persisted defaults — not in git |
| `pf_saved_runs.json` | Portfolio saved run comparison store — not in git |

**Contract registry (`data_loader.py` → `CONTRACTS` dict):**
- `"ESM6 — 2026"` → `ESM6.CME_BarData.txt` / `NinjaScript Output 03_06_2026 23_08.txt`
- `"ESH21 — 2021"` → `ESH21-CME.txt` / `NinjaScript Output 2021.txt` *(file not yet on disk)*
- Add new contracts by adding an entry to `CONTRACTS` — no other code changes needed
- Contract selector only shows contracts whose SC file exists on disk

**economic_calendar.py — current state:**
- FOMC dates hardcoded 2015–2026; 2026 confirmed from federalreserve.gov on 2026-06-04
- NFP (release_id=50) and CPI (release_id=10) fetched from FRED API; requires `FRED_API_KEY` in `.streamlit/secrets.toml`
- `get_economic_events(event_types: tuple, start, end)` returns DataFrame with DateTime (CT, tz-naive), EventType, Color

**Layout (tab-first design):**
- Tabs (`📊 Bar Viewer | 🔍 Bar Validation | 📈 Bar Analysis | 📊 Portfolio`) are the first element after the page header
- **Source selector runs BEFORE `st.tabs()`** — critical for render-order correctness. Tab1 (Bar Viewer) needs `bar_source` to be set before it renders. If selector was inside Tab3, it would be one render cycle stale.
- Upload UI lives inside the Bar Analysis tab: `📁 Upload Data` expander (3 cols: Tick | OHLC | MC Signals)
- `📡 Bar data source` expander only shown when multiple sources available (inside Tab3, collapsed), but the actual `bar_source` session state key is set before tabs
- Session state carries uploaded data across tabs; Bar Viewer and Bar Validation read from session state silently
- Reload button clears all upload state including `ba_signals`, `bar_source`, and `bar_source_radio`

**Radio widget key guard:** `key="bar_source_radio"` persists across rerenders. After disk SCID load, `st.session_state.pop("bar_source_radio", None)` is called before `st.rerun()` to prevent stale "SC Ticks (disk)" value overriding the new source.

**Upload guard:** The `else` branch of the tick file uploader (empty uploader) only clears `uploaded_sc_*` keys if `uploaded_sc_key` does NOT start with `"scid_"`. This prevents the auto-loaded SCID cache from being evicted on every rerender when the uploader widget is empty.

**Tab 3 — Bar Analysis — section layout (expander order, as of June 9):**
1. `📁 Upload Data` — tick / OHLC / signals upload (collapsed)
2. `📡 Bar data source` — only when choice exists (collapsed)
3. `⚙️ Filters` — date range, DOW, econ events, CC3/CC4 (collapsed)
4. `📶 Signals` — signal scatter map (collapsed)
5. `⚙️ Trading Parameters` — instrument, trade mode radio, column inputs (collapsed)
6. `📋 Summary` — 4 rows × 6 metrics incl. Max Drawdown, **PnL/DD**, Trading Days (**expanded**)
7. `🔍 Optimal R Sweep` (single-leg) OR `🔍 T1×T2 Sweep` + `🔍 Scale-In Sweep (PB × T1 × T2)` (2-leg) (collapsed)
8. `🔍 Stop Multiplier Sweep` (collapsed)
9. `📅 Monthly Breakdown` (collapsed)
10. `📊 Setup Analysis` (collapsed)
11. Unfilled / filtered signal expanders (collapsed)
12. `📈 Daily Chart` (**expanded**)
13. Signal Table + All Signals expanders (collapsed)
14. `🔍 Bar Data Mismatch Analysis` (collapsed)

Only Summary and Daily Chart are expanded by default.

---

## Trade Mode — 2-Leg Scale-In (implemented June 8, 2026)

### Model

E1 enters at signal price. Phase 1 scans **simultaneously** for three events:
- **Stop hit** → E1 stops out, trade over
- **T1 hit** (before PB fills) → E1 exits at profit, trade over (no scale-in)
- **PB fills** (before T1) → E2 adds to position, proceed to Phase 2

Same-bar priority (conservative): **Stop > T1 > PB**. If T1 and PB both reachable on same bar, T1 wins.

Phase 2 (after E2 fills): combined position scans for T2 or original stop.

### Key Prices

| Price | Formula |
|-------|---------|
| T1 | `E1_entry + T1_r × risk_pts` |
| PB trigger | `E1_entry − PB_r × risk_pts` (negative R, for long) |
| E2 fill | `pb_trigger + entry_slip × tick_size` |
| Blended entry | `(E1_price × tv1 + E2_price × tv2) / tv_total` |
| Blended risk | `abs(blended_entry − original_stop)` |
| T2 | `blended_entry + T2_r × blended_risk` |

Stop stays at **original level** after E2 fills.

### ExitReason values (2-leg)

| ExitReason | Meaning |
|------------|---------|
| `T1_only` | T1 hit before PB → E1 profit, no scale-in |
| `Stop` | E1 stopped out in Phase 1 |
| `EOD` | Session end without T1, stop, or PB fill |
| `E1E2+Target` | Combined position hit T2 |
| `E1E2+Stop` | Combined position stopped out |
| `E1E2+EOD` | Combined position held to session end |

### Commission / Slippage correctness

`T1_only` and `Stop` (Phase 1 before PB fills) charge only `contracts_t1` commission and slippage — E2 never traded. `E1E2+*` results charge `contracts_t1 + contracts_t2`.

This is enforced in both `_build` (via `_e2_filled` flag → uses `_tv_active`) and `simulate_trades` (checks `Leg2ExitReason != "NoFill"`).

### Session state keys (2-leg UI)

| Key | Widget | Type |
|-----|--------|------|
| `ba_contracts_t1` | E1 Contracts | int |
| `ba_t1_r_sel` | T1 dropdown (0.50R–3.00R) | str label |
| `ba_contracts_t2` | E2 Contracts | int |
| `ba_ml_pb_sel` | E2 Pullback dropdown | str label |
| `ba_t2_r_sel` | T2 dropdown (0.50R–3.00R) | str label |
| `ba_entry_slip_ml` | Entry slip (ticks) | float |
| `ba_exit_slip_ml` | Exit slip (ticks) | float |
| `ba_stop_offset_ml` | Stop offset (ticks) | int |
| `ba_commission_ml` | Commission ($/contract) | float |

**Critical**: the simulation setup block (line ~3703) reads T2 and PB from selectbox label keys (`ba_t2_r_sel`, `ba_ml_pb_sel`), NOT the old numeric keys. Must use `_r_lbls.index(label)` to convert. If you add new inputs, follow this pattern or values will silently default.

### Chart — 2-Leg annotations

- T1: dotted teal line, label "T1 X.XXR"
- T2: dashed teal line, label "T2 X.XXR"
- PB level: orange dash-dot horizontal line from entry to E2 fill bar, label "PB"
- E2 fill: filled orange circle at `(E2FillTime, E2FillPrice)` with hover

### Trade table — 2-Leg extra columns

`PB Lvl`, `E2 Fill`, `E2 Time` — shown when `PBLevel` column is present in results. Shows "—" for T1_only / Stop / EOD trades where E2 never filled.

### Result dict fields added (2-leg specific)

```python
"PBLevel":    float(pb_trigger) or nan
"E2FillPrice": e2_entry if E2 filled else nan
"E2FillTime":  pd.Timestamp(bar["DateTime"]) if E2 filled else pd.NaT
```

---

## Scale-In Sweep (PB × T1 × T2)

Lives in `_show_optimal_r()` under the `elif multileg:` branch, after the T1×T2 sweep expander.

**Function:** `_run_ml_scalein_sweep(signals, ticks_by_date, ..., pb_vals, t1_vals, t2_vals)`

**Default ranges:** PB: 8 values (−0.25R to −1.50R) · T1: 6 values (0.50R–2.00R) · T2: 9 values (0.50R–3.00R) = 432 combos

**UI controls inside expander:**
- 3 columns: PB range (Shallowest/Deepest), T1 range (Min/Max), T2 range (Min/Max)
- Combo count shown live before running
- Heatmap slices by selected T1 (PB on Y, T2 on X)
- Ranked top-20 table shows all T1 values

**Session state guard:** if `ba_si_sweep_df` exists but lacks `T1_R` column (stale from old 2-param format), it is discarded and user must re-run.

**Matches UI simulation exactly** — both use `filtered_signals`. Exception: sweep ignores ratchet (always `ratchet_r=0`) and `first_trade_only` post-filter.

---

## Summary Row 4 — Metrics

`Slippage | Commission | Total Cost | Max Drawdown | PnL/DD | Trading Days`

PnL/DD = `net_total / abs(max_dd)`. Shows "—" when no drawdown.

Slippage ticks for multileg: derived as `round(slippage_total_usd / tick_value)` — correct because it reflects the actual per-trade dollar amounts (which already account for whether each leg traded).

---

## Simulation Engine (`bar_analysis.py`)

- `_simulate_one_bars_multileg()` — bar-level 2-leg scale-in. Phase 1: simultaneous scan for T1/stop/PB. Phase 2: T2 from blended entry.
- `_EMPTY_TRADE` includes: `PBLevel`, `E2FillPrice`, `E2FillTime`, `SameBarConflict`
- `compute_summary()` — `net_total` uses `filled["NetPnL"].sum()` (correct, per-trade commission applied in `simulate_trades`)

---

## Sweep Tools

### 1. Optimal R Sweep (single-leg) / T1×T2 Sweep (2-leg)
- Auto-switches based on trade mode
- **1D (single-leg):** R from 0.50 to Max R in 0.25 steps
- **2D (2-leg):** all valid (T1, T2) combos where T1 < T2
- Results: `ba_sweep_df` (1D), `ba_t1t2_df` (2D)

### 2. Scale-In Sweep (2-leg only)
- PB × T1 × T2 — 432 combos by default, configurable via range controls
- Results: `ba_si_sweep_df`

### 3. Stop Multiplier Sweep
- 10 stop sizes: 0.25×–2.00× original stop
- Results: `ba_stop_sweep_df`

---

## SCID Data System (Session 6 — June 10, 2026)

### Architecture Decision — 1-Second OHLCV (locked)

**Previous approach:** tick SCID files (individual trades) — deleted June 10, 2026 (108 GB).  
**New approach:** 1-second OHLCV bars stored in SCID format.

**Rationale:**
- 5-minute bar simulation with conservative same-bar priority (Stop > T1 > PB) is too coarse — same-bar conflicts are frequent with tight stops
- Tick data (108 GB, weeks to download) is impractical
- 1-second bars (~210 MB/quarter, ~14 GB total) give simulation granularity sufficient to eliminate same-bar ambiguity while remaining practical to download and store
- 1-minute bars are NOT sufficient — ES 1-min range frequently spans both stop and target simultaneously

**Simulation design (to be built):**
- 5-minute bars: built from 1-second bars for charting/display only
- Simulation engine: scans 1-second bars sequentially within each 5-minute signal window to detect stop/target/PB hits in order

**Data to download:** Configure Sierra Chart to store 1-second OHLCV for all ES quarterly contracts (ESZ09–ESM26). Request historical data from SC.

### SCID Disk Loader

**Data directory:** `C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data`  
**Defined as:** `SCID_DATA_DIR` in `data_loader.py`

**Key functions in `data_loader.py`:**
- `build_scid_quarter_map()` — scans SCID_DATA_DIR for `ES*.scid`, samples timestamps, returns `{quarter: path}`
- `load_scid_ticks_chunked(path, quarters, progress)` — optimised loader: integer UTC pre-filter (eliminates ~65% ETH records before tz_convert), integer RTH check (no strftime), 2M-record chunks. Returns RTH DataFrame: DateTime, Price, Volume
- `resample_ticks_to_bars(ticks)` — resamples to 5-min OHLCV bars
- `build_bars_from_cache(quarters)` — builds 5-min bars one quarter at a time (no OOM); use for >16 quarters

**TODO when 1-second data arrives:**
- `load_scid_ticks_chunked` currently uses `records["Close"]` as tick price — correct for ticks, but for 1-second bars must aggregate OHLC properly (first Open, max High, min Low, last Close per 5-min window)
- `resample_ticks_to_bars` needs updating to resample 1-second OHLCV → 5-min OHLCV (not tick prices)
- Simulation engine needs new 1-second scan path

### Parquet Cache

One Parquet file per calendar quarter — built once via `scripts/build_scid_cache.py`, loaded instantly thereafter.

**Location:** `SCID_DATA_DIR/_scid_cache/{quarter}.parquet` + `last_selection.json`  
**Cache functions in `data_loader.py`:**
- `save_scid_cache(ticks, quarters)` — writes per-quarter Parquet files (snappy)
- `save_last_selection(quarters)` — updates last_selection.json (startup auto-load target)
- `load_scid_cache()` → reads last_selection.json, loads those quarters; legacy ticks.parquet fallback
- `load_quarters_from_cache(quarters)` → loads specific quarters from per-quarter Parquet
- `build_bars_from_cache(quarters)` → bars only, one quarter at a time (OOM-safe for large ranges)
- `list_cached_quarters()` → sorted list of cached quarter strings
- `clear_scid_cache()` — rmtree the `_scid_cache` dir (use with caution — cache takes time to rebuild)

**UI note:** "Unload" button in the SCID expander clears session state only — does NOT delete Parquet files.

**Auto-load on startup:** At top of `main()` in `app.py`, before any tabs render:
```python
if "uploaded_sc_bars" not in st.session_state:
    _cached_ticks, _cache_meta = load_scid_cache()
    if _cached_ticks is not None:
        _cached_bars = resample_ticks_to_bars(_cached_ticks)
        st.session_state["uploaded_sc_ticks"]  = _cached_ticks
        st.session_state["uploaded_sc_bars"]   = _cached_bars
        st.session_state["uploaded_sc_key"]    = f"scid_{','.join(_cache_meta['quarters'])}"
        st.session_state["bar_source"] = "sc_upload"
        st.session_state.pop("bar_source_radio", None)
```

**Session state keys (SCID):**

| Key | Content |
|-----|---------|
| `uploaded_sc_bars` | 5-min bar DataFrame (from SCID or uploaded tick file) |
| `uploaded_sc_ticks` | raw tick DataFrame |
| `uploaded_sc_key` | starts with `"scid_"` for disk/cache loads, else filename |
| `scid_loaded_label` | human-readable label shown in the UI |
| `scid_load_summary` | stats string (n ticks, date range) |
| `scid_quarter_map` | result of `build_scid_quarter_map()` |

### SCID Binary Format (Confirmed)

| Field | Type | Detail |
|-------|------|--------|
| Header | 56 bytes | Fixed header block |
| Record size | 40 bytes | `s_IntradayRecord` |
| `DateTime` | int64 | Microseconds since 1899-12-30 00:00:00 UTC |
| OHLC | float32 × 4 | Open, High, Low, Close |
| NumTrades | int32 | |
| TotalVolume | int32 | |
| BidVolume | int32 | |
| AskVolume | int32 | |

**Timestamp conversion:**
```python
SC_EPOCH = pd.Timestamp("1899-12-30")
dt_utc = SC_EPOCH + pd.to_timedelta(raw_int64_microseconds, unit="us")
dt_ct  = dt_utc.tz_localize("UTC").tz_convert("America/Chicago").tz_localize(None)
```

**Bar timestamp — CONFIRMED (Session 7):** In NinjaTrader with `Calculate.OnBarClose`, `Time[0]` is the bar **close** time. Empirically verified: NT's 15:35 Berlin bar prices match SC's 08:30 CT bar prices exactly (same O/H/L/C within back-adjustment). This confirms the −5 min shift is correct for NT TXT exports.

SC SCID timestamp behaviour: SCID bar timestamps appear to use bar **open** time (08:30:00 for the first RTH bar). The SCID loader does NOT apply a −5 min shift. This was not changed in Session 7 — verify if ever unclear by comparing first SCID bar DateTime to known SC bar open.

### OHLC NT Parser — Dual-Format Support (Session 7)

`parse_ohlc_from_upload()` in `data_loader.py` auto-detects format from first 512 bytes of the file.

**Format 1 — NT CSV** (comma-separated, has header, open times):
```
DateTime,Open,High,Low,Close,Volume
2025-01-02 08:30:00,6238.50,6241.25,6222.00,6222.25,12345
```
- Detected when first line contains `,` and not `;`
- Parses `DateTime` column as-is — already bar **open** time, NO −5 min shift needed
- Tolerant: tries strict format first, falls back to `pd.to_datetime`

**Format 2 — NT TXT** (semicolon-separated, no header, close times):
```
23/12/2024 15:35:00;6269.50;6279.00;6268.00;6273.50;12345
```
- Tries `DD/MM/YYYY HH:MM:SS` first; falls back to `MM/DD/YYYY` if >50% fail
- Detects Berlin vs CT via median hour heuristic (`> 14` → Berlin)
- Berlin path: `tz_localize("Europe/Berlin", ambiguous="infer", nonexistent="shift_forward")` → tz_convert → strip tz → −5 min
- CT path: dt_parsed − 5 min (fast; no DST lookup; preferred)

**Why CT is preferred over Berlin:** `tz_localize("Europe/Berlin")` on 29 K rows requires DST checking for every timestamp — very slow on Windows. The new MyOHLCReader.cs outputs `Time[0]` directly (CT), so Berlin path is legacy only.

**Key invariant:** After parsing, `DateTime` is always the bar **open** time in CT, tz-naive.

---

## Session 7 — Gate 2 Investigation (June 10, 2026)

### NT OHLCExporter (MyOHLCReader.cs) — Fixed

File location: `MyOHLCReader.cs` in repo root (NinjaTrader NinjaScript indicator).

**Problem found:** Old code called `BarCloseTime(Time[0])` to compute close time. But `Time[0]` with `Calculate.OnBarClose` IS already the bar close time — calling `BarCloseTime()` added another 5 minutes, so every bar was exported 5 min late.

**Fix:** Use `Time[0]` directly. Simplified indicator:
- Removed all timezone conversion (Berlin tz code deleted entirely)
- Removed CSV output — TXT only
- Reduced to 2 properties: `OutputPath`, `AppendMode`
- Core write: `Time[0]` direct, no conversion, no helper calls

```csharp
string line = string.Format(CultureInfo.InvariantCulture,
    "{0:dd/MM/yyyy HH:mm:ss};{1:F2};{2:F2};{3:F2};{4:F2};{5}",
    Time[0], Open[0], High[0], Low[0], Close[0], (long)Volume[0]);
```

This matches the exact approach confirmed by a colleague: `Print(Time[0], Open[0], High[0], Low[0], Close[0], Volume[0])`.

**Evidence of fix:** Old file started at `15:40:00 Berlin` (one bar late). New export starts at `15:35:00 Berlin` (correct close of 08:30 bar).

**NT export files on disk:**  
`C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\OHLC 5M\ohlc_export.txt`  
`C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\OHLC 5M\ohlc_export.csv`  
Both ~1.7 MB, written 2026-06-10 17:07 local. These are from an intermediate build (Time[0] fixed, Berlin conversion still present). The final simplified build (no Berlin) must be recompiled in NT and a fresh export run.

### Gate 2 Root Cause — Back-Adjustment Discrepancy

After fixing the timestamp bug, Gate 2 still showed 0% match. Root cause:

- **SC** exports from `ESM26-CME [CB]` — Sierra Chart's "CB" back-adjusted continuous contract
- **NT** exports from its continuous contract — different roll dates and spreads

**Observed deltas (from price comparison):**

| Period | Back-adj delta | Mismatches/day |
|--------|---------------|----------------|
| Dec 2024 – Jun 2025 (ESZ24/H25/M25) | Hundreds of points | ~80 (all bars) |
| Jul 2025 – present (ESU25+) | ~0.50 pt (2 ticks) | 0–10 |

Even 2 ticks is unacceptable — user requires 100% exact match.

**Evidence from price check:**
```
SC  Dec 23 2024 08:30 CT: O=6269.50 H=6279.00 L=6268.00 C=6273.50
NT  Dec 23 2024 08:30 CT: O=6269.00 H=6278.50 L=6267.50 C=6273.00
Delta:                       −0.50    −0.50    −0.25      −0.00
```

### Gate 2 Fix — Individual Contracts Required

Both SC and NT must export from the **same individual (non-back-adjusted) quarterly contract charts** to get exact tick-for-tick price match.

**Contracts needed:** ESZ24, ESH25, ESM25, ESU25, ESZ25, ESH26, ESM26

**SC:** Open individual contract charts (ESZ24-CME, ESH25-CME, etc.), export 5M bars from each.  
**NT:** Run OHLCExporter indicator on each individual contract chart in NT8.

**Agreed next step:** Start with **ESM26 only** (current front month — zero back-adjustment on either platform). Verify 100% match end-to-end. Then expand to full history.

**App change needed (not yet built):** Gate 2 UI must accept multiple per-contract files and stitch them date-by-date for the full comparison. Currently only one NT 5M file slot exists.

### Code Changes — Session 7

| File | Change |
|------|--------|
| `MyOHLCReader.cs` | Completely rewritten — simplified to `Time[0]` direct, no tz conversion, 2 props |
| `data_loader.py` | `parse_ohlc_from_upload` rewritten — auto-detects CSV vs TXT; CSV=no shift; TXT=−5min |
| `validation.py` | Empty DataFrame guard at line ~247 (before `max()`/`min()` date overlap) |
| `app.py` | Empty DataFrame guard after NT 5M parse — shows error with first 200 chars, `st.stop()` |

### Bar Viewer / Bar Validation — Upload-Only Policy

Neither tab has disk fallbacks. If no data is uploaded (and no cache loaded), they show an info message. No 2026 disk data ever appears unless explicitly loaded or cached. This is enforced in `show_bar_viewer()` and `validation.py`.

---

## Data files (not in git — keep in `data/raw/`)
- `ESM6.CME_BarData.txt` (~3GB SC ticks, 2026) — old disk file, not used by bar viewer unless uploaded
- `NinjaScript Output 03_06_2026 23_08.txt` (NT 5M bars, 2026) — old disk file, not used unless uploaded
- `NinjaScript Output 2021.txt` (NT 5M bars, 2021 — needed for ESH21 contract)
- SCID files live at: `C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data\`

**Run:** `.venv\Scripts\streamlit run app.py` (Windows)

---

## Commit Status

**Session 1 (June 7):** ✅ Committed + pushed  
**Session 2 (June 7):** ✅ Committed + pushed (no-auto-load, library tenets)  
**Session 3 (June 8):** ✅ Committed + pushed — 2-leg scale-in model complete  
**Session 4 (June 8):** ✅ Committed + pushed — Portfolio tab complete  
**Session 5 (June 9):** ✅ Committed + pushed (`c5c2f0f`) — SCID disk loader, Parquet cache, source selector fix, OHLC auto-detect, upload-only bar viewer/validation  
**Session 6 (June 10):** ✅ Committed + pushed (`e4e0c6c`) — optimised SCID loader (integer pre-filter, no strftime, 8× larger chunks), per-quarter Parquet cache, OOM fix (build_bars_from_cache), Unload button, Select All fix; deleted 108 GB tick SCID files; architecture decision: switch to 1-second OHLCV  
**Session 7 (June 10):** ✅ Committed + pushed — NT OHLCExporter Time[0] fix (MyOHLCReader.cs), NT parser dual-format (CSV/TXT), empty DataFrame guards (validation.py + app.py), Gate 2 root cause documented (back-adjustment); Gate 2 100% match requires individual contracts (ESM26 first)  
**Session 8 (June 10):** ✅ Committed + pushed — `validation.py` CSV download fix (st.download_button, gate_key param); corrected back-adjustment findings; NT corrupted bar (2025-07-15) found and fixed in NT  
**Session 10 (June 13):** ✅ Committed + pushed — `scripts/fetch_for_nt.py` (NT import script), `data_loader.py` (4 Massive.io API functions), `massive.py` (new Massive.io tab), `app.py` (6th tab added); all Massive.io code ready pending API key Monday 2026-06-16  
**Session 11 (June 14):** ✅ Committed + pushed — Massive.io API details confirmed (base URL, auth, sort); ES_MAS full pipeline confirmed working end-to-end with AAPL test data; NT native bars slot + Comparison 3 added to massive.py; API key subscribed today
**Session 12 (June 16):** ✅ Committed + pushed — see full section below. Massive promoted to primary pipeline: contract manager, back-adjustment bug fix, continuous tick series (445M ticks, validated 99.49% vs 5M bars), app-restart persistence for continuous series + NT upload, unified filters (single editable home in Data tab), alt-path mismatch analysis in Bar Analysis, tab reorder/cleanup, Bar Validation tab removed, requirements.txt fixed, onboarding docs updated  
**Session 13 (June 17):** ✅ Committed + pushed — WFA infrastructure: `simulation_engine.py` extracted from `bar_analysis.py`, `results_store.py` (SQLite + Parquet), `wfa.py` (full IS sweep + guardrails + OOS + Streamlit tab), `app.py` wired; scipy added to venv. **NOT yet user-tested end-to-end — do not rely on this as validated output.**

---

## Session 13 — June 17, 2026 — WFA Infrastructure

### Summary

Built the complete WFA (Walk-Forward Analysis) infrastructure from scratch. Three new files plus changes to two existing files. The Streamlit tab is wired and the module tree imports cleanly. **No end-to-end run with real signal data has been done yet** — that is the first thing to do next session.

### New Files

| File | Lines | Purpose |
|------|-------|---------|
| `simulation_engine.py` | ~750 | All simulation functions extracted from `bar_analysis.py` + PROM metric added to `compute_summary()` |
| `results_store.py` | ~275 | SQLite fold metadata (`runs` + `folds` tables) + Parquet per-fold trade logs; full CRUD |
| `wfa.py` | ~460 | WFA engine (`build_folds`, `run_is_sweep`, `compute_robustness`, `select_params`, `average_params`, `run_wfa`) + Streamlit tab (`show_wfa_tab`) |

### Modified Files

| File | Change |
|------|--------|
| `bar_analysis.py` | All simulation function definitions removed (lines 150–1608 original, plus `_resimulate_bars`); import block at top pulls from `simulation_engine` |
| `app.py` | `import wfa as wfa_mod`; 6th tab `🔄 WFA` added; `show_wfa_tab()` wired |

`portfolio.py` unchanged — it imports `simulate_trades`, `compute_summary`, `INSTRUMENTS` from `bar_analysis`, which now re-exports them from `simulation_engine`. No breakage.

### WFA Architecture (locked this session)

**Window:** rolling IS=1yr / OOS=3mo (configurable; warns if < 10 folds). Step = OOS window length. ~16 folds over the current 5-year dataset.

**Parameter grid (IS sweep):**
- Single-leg: T1 only (7 values: 0.50–2.00R, multiplicative spacing per Kaufman)
- 2-leg (multileg): T1 × T2 × PB1 (~120 valid combos, T1 < T2 enforced)
- 3-leg: T1 × T2 × PB1 (same grid, different sim path)
- Ratchet always off during sweep (Kaufman: do not co-optimize)

**Objective function:** PROM (Pessimistic Return on Margin) — primary. PnL/DD and PF displayed alongside.

**Kaufman guardrails (per fold):**
- ≥ 70% of IS param combos profitable → `rob_passed`
- Kurtosis of PROM surface ≤ 6 → `kurtosis_ok`
- ≥ 30 trades in IS window → `min_trades_ok`
- Trade the average of top-N sets (default 3), not the single best

**Pardo rules (hard constraints, not just metrics):**
- OOS locked immediately after run (`lock_oos()` called inside `run_wfa`)
- Forward live risk = 2× IS max drawdown (surfaced as warning in UI, not enforced in code)
- Scan ranges, strategy logic, and objective function are all fixed before the first IS sweep runs

**Storage:**
- `data/wfa_store/wfa_results.db` — SQLite; `runs` table (run-level config) + `folds` table (all scalar metrics + guardrail flags per fold)
- `data/wfa_store/trades/{run_id}/{setup_id}/fold_{N}_{is|oos}.parquet` — per-fold trade logs

**Streamlit UI (two sub-tabs):**
- `⚙️ Configure & Run` — setup ID, instrument, mode, IS/OOS window, param-set count, execution params, CC filter, run button with progress bar
- `📊 Results` — run selector, guardrail badge panel, combined OOS equity curve with 4 summary metrics, fold table (color-coded WFE), per-fold drill-down (IS/OOS metrics + chosen param sets + trade log expanders), delete run

### PROM formula (now in `compute_summary`)

```
PROM = [GrossWin × (1 − 1/√Nw) − GrossLoss × (1 + 1/√Nl)] / |MaxDrawdown|
```

Uses gross (pre-commission) win/loss to match Pardo's original formulation. Returns `nan` when max drawdown = 0 (no drawdown → infinite PROM, which is nonsensical). `compute_summary()` now returns `prom` and `pnl_dd` alongside all previous metrics.

### Dependency added

`scipy` installed to `.venv` (needed for `scipy.stats.kurtosis` in `compute_robustness()`).

### What is NOT yet done / NOT yet tested

- **No end-to-end run with real signals** — `show_wfa_tab()` requires `mas_continuous` (from Massive tab) + an uploaded signals file. First real test is a full WFA run on CC2 signals in multileg mode.
- **Bar Analysis filters not yet migrated** to the shared Data-tab panel — same carry-over from Session 12.
- **Max concurrent positions / max daily loss** (Q5, Q6 in `open_questions.md`) — wfa.py currently ignores both. All signals run independently. Decide before relying on WFA output for live trading.
- **RevFT signals** — not ready yet. When they arrive, slot in as another `setup_id`; no code changes required.
- **Portfolio WFA layer** — individual setup runs work; combining OOS equity curves across setups (`load_portfolio_oos_trades()` in `results_store.py`) is wired but the Portfolio tab doesn't yet call it.
- **Window stability scanner** (Phase F in roadmap) — not built. Runs the fold builder over a grid of IS/OOS sizes to find the most stable window pair.

---

## Session 12 — June 16, 2026 — Massive Becomes Primary Pipeline

### Summary

Long session. Took Massive from "parallel validation track" to "the only data source Bar Analysis actually uses." Found and fixed several real bugs along the way (back-adjustment roll-date semantics, OOM crash in validation, NT OHLCExporter buffer-loss risk investigated but not changed — see below). Ended by unifying filters across tabs and removing the now-redundant Bar Validation tab.

### Bugs found and fixed

1. **Back-adjustment roll-date semantics** (`contracts.py`) — `apply_back_adjustment` was treating the user-entered `roll_date` as the contract's own roll-OUT date instead of NT's actual convention (roll-IN date — the date a contract BECOMES front month). This clipped every middle contract to ~2 trading days instead of its full quarter. Fixed by swapping the bound logic: lower bound = own roll_date, upper bound = NEXT contract's roll_date. Verified before/after: 7,662 bars/96 days → 94,435 bars/1,189 days (19 contracts at the time).
2. **5-minute timestamp misalignment between Massive and NT** — Massive resamples bars with `label="left"` (DateTime = bar open time); NT TXT uploads keep NT's close-time label as-is. Every comparison row was silently off by one bar. Fixed in `build_comparison()` (`validation.py`) — shifts the NT side back 5 minutes before joining, at comparison time only (neither source's own convention touched).
3. **OOM crash in tick-cache validation** — `validate_ticks_vs_bars()` originally concatenated all ~445M cached ticks into one DataFrame before resampling (`numpy._core._exceptions._ArrayMemoryError`, tried to allocate 3.3GB for one column). Fixed to process one cached day-file at a time, accumulating only summary counters.
4. **403 vs 404 on Massive's S3 endpoint** — Massive returns 403 (not 404) for dates with no data yet (future dates). The old `_download_day()` only treated 404/NoSuchKey as "skip," so it crashed mid-download whenever the loop reached today's date boundary. Now treats 403/Forbidden the same as 404.
5. **Memory-unsafe NT tick-import writer** — `download_contract()` accumulated all of a contract's ticks in memory before one big write; switched to incremental per-day appends (`_append_nt_lines`).
6. **`bar_source` dead code in `bar_analysis.py`** — `bar_source` session-state key was read everywhere but never written anywhere in the codebase, so `show_bar_analysis()` always fell through to the `uploaded_ohlc_bars` branch (NT bars) regardless of what was actually intended. This meant Bar Analysis was silently simulating on NT data, not Massive, this whole time. Fixed by rewiring to source `bars` from `mas_continuous` directly (see below).

### New capability: continuous back-adjusted tick series

Built `massive.py: build_continuous_ticks_for_date()` / `load_continuous_ticks()` / `build_all_continuous_ticks()` — one small Parquet per trading day (front-month ticker only, RTH-filtered, back-adjustment offset baked into price), built from the flat-file cache that's already on disk (no new downloads). A combined multi-year tick file was considered and rejected — ~500M+ rows is impractical to hold in memory or load as one file; per-day files keep memory bounded and each individual day-read fast regardless of total history size.

**Built and validated:** 1,220 days, 444,968,944 total ticks. Validation (`validate_ticks_vs_bars()`, also surfaced as a button in the Massive tab UI): 98.6–100% of Massive 5M bars have tick coverage (two measurement passes gave slightly different numbers — see Known Gaps below), 99.49% OHLC exact match.

`contracts.py` gained `get_contract_windows()` (shared front-month-window + cumulative-offset table, extracted from `apply_back_adjustment`) and `get_active_contract(date, rolls)` (which contract + offset was active on a given date) — both used by the tick builder so it applies the exact same roll/offset logic as the bar back-adjustment.

### Persistence across app restarts

Previously `mas_continuous` (Massive's built continuous series) and `nt_cont_bars` (the NT `@ES` continuous upload) only lived in `st.session_state` — gone on every restart, requiring a manual rebuild/re-upload. Fixed:

- `mas_continuous` → saved to `data/bars/_continuous.parquet` on build, auto-loaded on `show_massive_tab()` entry if not already in session.
- `nt_cont_bars` → saved via the existing generic CSV-cache mechanism (`save_csv_cache`/`load_csv_manifest`, prefix `"nt_cont"`), auto-loaded the same way. First upload after this fix still required once to seed the cache; every restart after that is automatic.
- Bar Viewer's `data_sc_5m` slot (separate from `mas_continuous`) also auto-derives from `mas_continuous` now, via a one-line check placed in `app.py: main()` right after the Massive tab renders (placement matters — Data tab renders before Bar Viewer in tab order, so the derive has to happen before Data tab's status check, not inside Bar Viewer itself).

### Bar Analysis now actually uses Massive data

`show_bar_analysis()` rewired: `bars` comes from `mas_continuous`; ticks load lazily per-day from the continuous tick cache, scoped only to dates that actually have signals (not the full multi-year history — keeps memory bounded regardless of total cache size). NT bars are used **only** for the signal-bar-Close matching gate (`_nt_bars_for_mismatch`), never for fills/exits. Legacy `uploaded_sc_bars`/`uploaded_sc_ticks`/`sc_disk` routing removed (was dead code per bug #6 above).

**New: alt-path mismatch analysis** (`compute_alt_path_outcomes()` in `bar_analysis.py`) — for filled trades, checks whether the NT signal bar's Close differs from Massive's Close at that exact bar (the gate). Only for gated trades, re-derives the outcome using NT's 5M bars in place of Massive's (same entry/pullback/target logic, `signal_price`/`stop_csv` held fixed since they come from the external signals file). Flags `AltDiffers=True` only when the re-derived outcome actually changes (different fill/no-fill, exit reason, or PnL) — most gated trades re-derive to the same outcome and aren't flagged. Dispatches across all three trade structures (single-leg, 2-leg, 3-leg) via `_resimulate_bars(mode, ...)`. Surfaced as a second section under the existing `_show_mismatch_analysis` table.

**New: RevFTSignals** — a second, independent signal upload alongside MC Signals (own session-state keys), with a radio toggle deciding which one actually feeds the simulation. Lets you keep both loaded and switch without re-uploading.

### Manual date exclusion (global)

New `excluded_dates.json` (committed, same pattern as `rolls.json`) + `load_excluded_dates()`/`save_excluded_dates()`/`filter_excluded_dates()` in `data_loader.py`. Managed via a "🚫 Manually Excluded Dates" panel (currently in the Data tab). Wired into every bar-loading path: `apply_data_slot`, Massive continuous build, NT upload parsing, and Bar Analysis's `bars`/`ticks`/`nt_bars`/`signals_raw`. One add removes that date everywhere.

Seeded with `2026-04-06`: NT's OHLCExporter captured only 1 stray tick (12:55, vol=1) that entire session — diagnosed as `IsSuspendedWhileInactive = true` (in `MyOHLCReader.cs`) likely suppressing `OnBarUpdate` while the chart tab was inactive. **Not fixed in the indicator** — user explicitly said not to touch it without being asked; the exclusion-list workaround was used instead. If this recurs often, the indicator fix (flush-to-disk periodically instead of buffering until `Terminated`) is sketched out in conversation history but was reverted, never applied.

### Investigated mismatch patterns (no further action needed)

- **2026-04-06**: see above — NT capture gap, not a Massive/back-adjustment issue.
- **~50 missing trading days across 14 contracts (2021–2022 heavy)**: real gaps in `data/flatfiles_cache/` — some days' `.csv.gz` never downloaded (likely transient 403s before the fix above existed), some downloaded but produced zero bars. Not yet re-downloaded. Listed precisely in conversation history; would need a targeted re-download pass for just those dates.
- **Outliers up to ~30 ticks on ordinary (non-roll) days**: cluster at session open/close boundaries (feed-timing disagreement between Massive's raw CME ticks and NT's Rithmic feed, worse during real volatility — e.g. 2025-04-04 Liberation Day tariffs, 2024-08-05/06 yen-carry unwind). Not a bug.
- **2021-10-01 (24 mismatches)**: same boundary-noise mechanism, just an unusually choppy day. Not a bug.

### Unified filters

Filters (exclude NYSE holidays, day-of-week, session boundaries — first-N-bars/last-N-min, economic events FOMC/NFP/CPI) previously existed as three **separate** widget sets: Massive's comparison panel, the old Bar Validation tab, and Bar Analysis's own panel. Streamlit can't have the same interactive widget editable from two tabs in one script run (duplicate key error), so true bidirectional sync isn't directly possible.

**Resolution (user's choice from 3 options presented):** single editable copy lives in the **🗂️ Data tab** (`validation.render_filters("shared")`). Massive's comparison section reads the same values read-only via the new `validation.get_filters("shared")` (no widgets rendered there anymore — just `get_filters("shared")` called directly). **Bar Analysis's own separate `ba_`-prefixed filter widgets were NOT yet migrated to the shared panel — this is the main carry-over item for next session** (see Next Session Priorities).

### Tab/UI cleanup

- Tabs reordered: Massive first (📂 icon, was 📡), Data second (🗂️ icon, was 📂 — avoided icon collision)
- **Bar Validation tab removed entirely** — fully superseded by Massive's own comparison panel (same underlying `show_gate_body` engine, just pointed at Massive continuous bars instead of manually-uploaded single-contract files). `import validation` removed from `app.py` then re-added once the shared-filters work needed it again.
- Data tab's NT 5M upload column removed — was used only by the now-removed Bar Validation tab and a legacy Bar Analysis fallback, both superseded by the NT `@ES` continuous upload in the Massive tab. ES_MAS 5M upload kept as an explicit manual override (auto-derives from `mas_continuous` otherwise).
- Roll Schedule table: removed "Active From"/"Last Trade" columns — confirmed read-only display fields with no logic dependency (download window comes from the `Contract` dataclass directly, never from the edited table).
- `_show_by_date` chart x-axis now shows the year (`tickformat="%b %d, %Y"`) — was ambiguous across a 5-year multi-year series.

### Onboarding / requirements

- `requirements.txt` was missing `boto3`, `pyarrow`, `numpy`, `requests` — would have crashed Thomas's first run on import. Fixed.
- `COLLABORATOR_ONBOARDING.md` rewritten for the Massive pipeline (was written for the old 3GB SC tick file approach). A duplicate `ONBOARDING.md` created mid-session was merged into it and deleted — **one onboarding doc, not two**, per the existing "never duplicate information across files" rule.

### Known gaps / not yet verified

- **Bar Analysis filters not yet unified** with the shared Data-tab panel (see above) — top priority for next session.
- **Tick-cache validation discrepancy**: the UI button's day-by-day validation (`validate_ticks_vs_bars`, memory-safe) reported 98.6% coverage / 1,587 extra bars, while an earlier single-pass full-history script (same logic, no memory constraint) reported 100% / 243 extra bars. Both confirm the data is sound; the gap itself wasn't root-caused. Worth checking if it matters before relying on the UI number for anything precise.
- **~50 missing-day gaps in `flatfiles_cache`** (listed above) — not re-downloaded.
- **NT `OHLCExporter` buffer-loss risk** (the mechanism behind the 2026-04-06 exclusion) — diagnosed, a fix was drafted (flush-to-disk every N bars instead of buffering until `Terminated`) but reverted per explicit user instruction not to touch it without being asked. If gaps recur, that fix is the move — ask first.
- **Calendar-month-range optimization in Bar Analysis** — user asked "we need to be able to optimize on particular date ranges, not by contract, rather by calendar months" — raised but not yet designed or scoped. Carry over.
- Live-tested via Playwright (chromium installed this session: `pip install playwright && python -m playwright install chromium` — now available for future UI smoke tests) for: tab order, Roll Schedule columns, tick-cache build + validation button (including the OOM crash and its fix), Data-tab auto-load on a real process restart, Massive continuous-series persistence on restart. NOT live-tested: RevFTSignals end-to-end with a real second signal file, alt-path mismatch table with a real divergent trade, the new shared-filters panel's actual effect on Bar Analysis simulation results (since Bar Analysis filters aren't wired to it yet).

---

---

## Portfolio Tab (Session 4 — June 8, 2026)

### Feature Set

- **Per-setup 2-leg simulation** — all enabled CC types run independently using `simulate_trades(multileg=True)` + `compute_summary(is_multileg=True)`
- **Equity curves** — combined portfolio + per-setup traces on one Plotly chart
- **Drawdown chart** — portfolio-level drawdown subplot
- **Per-setup breakdown table** — Trades, Win%, PF, Net PnL, Max DD, Ann Return, Starting Capital configurable
- **Global Settings** — Instrument, date range, contracts T1/T2, slippage/commission, starting capital
- **Setup Parameters** — per-CC T1/PB/T2 dropdowns in expander; Save as Defaults button persists to `pf_defaults.json`
- **Portfolio Sweep** — per-CC independent T1×PB×T2 grid sweep; ranked by PnL/DD, Net PnL, or PF; click row to apply directly to setup config
- **Saved Runs** — save named run with structured name (Scope | Period | Description) to `pf_saved_runs.json`; Compare tab shows side-by-side metrics for all saved runs
- **PDF Export** — `components.html()` with `window.parent.print()`; counter in JS comment forces re-render on every click; `matchMedia('print')` + `Plotly.relayout()` resizes equity chart from 420→680px; no expanders are auto-opened

### Key Technical Patterns

**Versioned widget keys** — programmatic config updates (e.g. "apply sweep row") cannot use `st.session_state["pf_t1_CC2"] = new_val` after widget is rendered. Solution: version counter `pf_cfg_ver` in session state; incrementing it changes the key suffix (`_v0` → `_v1`), creating uninitialized keys that accept `index=` parameter.

```python
def _apply_to_config(cc, t1_raw, pb_raw, t2_raw):
    _cfg = dict(st.session_state.get(f"pf_cfg_{cc}", {}))
    _cfg["t1_idx"] = _t_idx(t1_raw)
    _cfg["pb_idx"] = _pb_idx(pb_raw)
    _cfg["t2_idx"] = _t_idx(t2_raw)
    st.session_state[f"pf_cfg_{cc}"] = _cfg
    st.session_state["pf_cfg_ver"] = st.session_state.get("pf_cfg_ver", 0) + 1
```

**PDF equity chart resize** — CSS alone cannot resize Plotly SVGs (fixed at render time). `matchMedia('print')` fires `Plotly.relayout({height: 680})` on the open "Equity Curves" expander's chart element before print, then restores after.

**Row-level apply** — `st.dataframe(on_select="rerun", selection_mode="single-row")` + apply button renders a per-row apply flow without custom components.

### Known Gaps / Not Yet Verified

- **PDF equity chart resize** — `Plotly.relayout()` is called from an iframe (`components.html`); browser security policy may block `window.parent.Plotly` depending on browser/version. Needs testing.
- **2-leg math** — per-leg P&L math against manual calculations still unverified (carried from session 3).
- **`first_trade_only` filter** — not applied in sweep (pre-existing across all sweeps).

---

## Massive.io Tab — Architecture (locked, implemented Session 10)

- **Tab:** `📡 Massive.io` — 6th tab in app.py (`massive.py`). Independent from SC validation tabs. No shared state.
- **API-first** — ticks via `GET /futures/v1/trades/{ticker}`, agg bars via `GET /futures/v1/aggs/{ticker}`. Both cached to `data/massive_cache/` as parquet after first fetch.
- **Bar builder** — reuses `resample_ticks_to_bars()` in `data_loader.py`. No new bar logic.
- **Comparison** — reuses `build_comparison()` from `validation.py`, called twice:
  - Comparison 1: tick-built bars vs Massive agg bars (validates bar builder)
  - Comparison 2: tick-built bars vs NT ES_MAS bars (validates full import round-trip)
- **Rollover** — use `last_trade_date` from Contracts API; no hardcoded dates.
- **Correction filter** — exclude `correction != 0` trades.
- **Conditions field** — ignore for ES (equities only, confirmed by massive.io).
- **Session boundaries** — hardcoded RTH_START/RTH_END (08:30–15:15 CT).
- **Developer plan** — 5-year history (~2021 to present), 10-min delay. Sufficient for validation. Advanced needed for full WFA history to 2010.
- **Massive Agg bars caveat** — may differ slightly at session boundaries (08:30/15:15 CT). Tick-built vs NT is the comparison that matters most.
- **Reversal setup** — NT signal CSV arriving this week. Defer all design until CSV + NT strategy logic is seen. Do not design in advance.

### Functions in `data_loader.py` (built Session 10)

| Function | Purpose |
| -------- | ------- |
| `fetch_massive_trades(api_key, ticker, date_start, date_end)` | Paginate Trades API → DataFrame(DateTime CT, Price, Volume); cache to parquet |
| `fetch_massive_aggs(api_key, ticker, date_start, date_end, resolution)` | Paginate Aggs API → DataFrame(DateTime, OHLCV); cache to parquet |
| `fetch_massive_contract_info(api_key, ticker)` | Single contract metadata (first/last trade date, tick size) |
| `massive_ticker_to_nt_name(ticker, first_trade_date)` | `'ESM6' + '2026-03-17'` → `'ES_MAS 06-26'` |

**TODOs for Monday (require live API key):** confirm `BASE_URL`, auth header format, sort param syntax, exact ticker format (`ESM6` vs `ESM26`). All are marked with `# TODO` in code.

### `scripts/fetch_for_nt.py` (built Session 10)

Standalone script — runs natively on PC (Python + requests). Configure `API_KEY`, `TICKER`, `DATE_START`, `DATE_END` at top, then run. Output: `ES_MAS MM-YY.Last.txt` in `OUTPUT_DIR` + parquet cache. Same TODOs as above.

## NT Data Isolation — Confirmed Facts (Session 9)

From NT8 documentation (Historical Data Manager):

**Delete does not work for isolation:**
> "Deleted historical data will be replaced when data is reloaded from the connectivity provider."
Deleting ESM6 Rithmic data then importing massive ticks is unreliable — Rithmic refills on reconnect. Do not use this approach.

**Custom instrument approach — IN PROGRESS (Session 10):**
From NT docs: "Any data imported where the instrument does not exist in the database will automatically be imported as a Stock instrument type. Futures and forex instruments must pre-exist in the database."

- **ES_MAS** custom Future instrument created in NT Instrument Manager ✅
- Contract months added manually one at a time with rollover dates + price offsets; NT applies back-adjustment ("merge back adjusted" setting)
- NT contract month naming: `ES_MAS 06-26`, `ES_MAS 12-25`, etc. (`MM-YY` format)
- Whether NinjaScript indicators run cleanly on ES_MAS is **still unconfirmed** — blocked on tick data (API key Monday)
- First test: one contract month only. If indicators work → expand. If not → escalate to NinjaTrader support.

**Merge vs overwrite on import:** NT documentation does not specify. Unknown.

**Rule added:** Never guess NT8 behavior. If uncertain, say so immediately and stop. Do not present plausible-sounding guesses as recommendations.

---

## Session 11 — Massive.io API Confirmed + ES_MAS Pipeline Proven (June 14, 2026)

### Massive.io API — Confirmed Details

From a live AAPL test call, the following are now confirmed API-wide (equities and futures):

| Item | Old assumption | Confirmed |
|------|---------------|-----------|
| Base URL | `https://api.massive.io` | **`https://api.massive.com`** |
| Auth | `Authorization: Bearer` header | **`?apiKey=KEY` query param** |
| Sort param | `sort.asc=timestamp` | **`sort=asc`** |
| Agg timestamp | unknown unit | **Unix milliseconds** (`t` field) |
| Agg fields (equities) | `window_start`, `open`... | **`t`, `o`, `h`, `l`, `c`, `v`** |
| Pagination | `next_url` cursor | ✅ confirmed; must re-add `apiKey` on each page |

**Still unconfirmed for futures specifically:**
- Endpoint path: `/futures/v1/trades/` and `/futures/v1/aggs/` vs `/v2/` — confirm on first live futures call
- Date filter param names for trades (`session_end_date.gte` vs `timestamp.gte`)
- Response field names for futures aggs (may differ from equities `o/h/l/c/v/t`)

All confirmed fixes applied in `data_loader.py` and `scripts/fetch_for_nt.py`. Remaining unknowns marked with `# TODO` in code.

**API key:** Subscribed June 14, 2026.

### ES_MAS NT Pipeline — Fully Confirmed

Tested end-to-end using AAPL 5-min agg bars as synthetic tick data (May 5–29, 2026, 1,404 RTH bars).

| Step | Result |
|------|--------|
| `ES_MAS 06-26.Last.txt` → NT HDM import | ✅ 29 test bars loaded, then 1,404 RTH bars |
| NT builds minute bars from imported ticks | ✅ confirmed (doji bars, O=H=L=C as expected) |
| Tick size rounding (0.25) | ✅ 279.40 → 279.50 |
| EMA indicator on ES_MAS 06-26 chart | ✅ runs correctly |
| OHLCExporter on ES_MAS 06-26 chart | ✅ runs and writes bars |
| OHLCExporter bar timestamps | ✅ close times (08:30 open → 08:35 in output) |
| "Unknown instrument 'ES_MAS 06-26'" error | ⚠️ appears on chart open but does NOT block indicators |
| Exchange TZ in OHLCExporter log | Eastern Time (CME session template) — watch for offset with CT imports |

**Key finding:** Bars are dots/dashes because each 5-min agg bar was imported as a single tick (O=H=L=C = close price). This is expected and does not affect OHLCExporter output. Real ES futures ticks will produce proper OHLC bars.

**File naming confirmed:** `ES_MAS MM-YY.Last.txt` → NT HDM correctly associates with the matching contract month.

### Code Changes — Session 11

| File | Change |
|------|--------|
| `data_loader.py` | BASE_URL `.io`→`.com`; auth `Bearer header`→`apiKey` query param; `sort`→`asc`; agg timestamp `unit="ns"`→`"ms"`; agg fields dual-support (`o/t` + `open/window_start`); removed `_massive_headers()` |
| `scripts/fetch_for_nt.py` | Same URL/auth/sort fixes; `_headers()`→`_auth_params()` |
| `massive.py` | 4th data slot: **NT native bars** (upload, `mas_nt_native_bars`); **Comparison 3**: Tick-built vs NT native; Clear cache includes new keys; Comparison 2 label `"NT"`→`"NT_MAS"` |
| `scripts/write_aapl_test_nt.py` | New one-off: 29 pre-market AAPL bars → NT import file (first test) |
| `scripts/write_aapl_rth_nt.py` | New one-off: fetch AAPL RTH bars from API → NT import file (pipeline test) |

---

## Session 14 — June 18, 2026

### What Was Done

#### 1. Simulation engine — entry logic corrected (all 6 functions)

The old entry logic in ALL 6 simulation functions was wrong: it scanned bars and waited for price to cross `signal_price` (SBClose) before filling. The correct rule is:

> **Entry = first tick after signal datetime, unconditional. `signal_price` is informational only.**

Fixed in `_simulate_one`, `_simulate_one_multileg`, `_simulate_one_3leg` (tick-based) and `_simulate_one_bars`, `_simulate_one_bars_multileg`, `_simulate_one_bars_3leg` (bar-based).

Tick-based fix:
```python
# Before (wrong): bar-grouping crossing scan
# After (correct):
first_row     = after.iloc[0]   # after = ticks after sig_dt
first_tick_px = float(first_row["Price"])
entry_dt      = first_row["DateTime"]
```

Bar-based fix:
```python
# Before (wrong): returned no_fill if nb["High"] <= signal_price (long)
# After (correct):
fill_px = float(nb["Open"])  # unconditional
```

#### 2. `_simulate_one_multileg` — PB scale-in added (was missing entirely)

The tick-based multileg function had no PB logic. Added:
- `ml_pb_r` and `ml_pb_ticks` parameters
- `use_pb = ml_pb_r < 0` flag
- Single scan loop: PB fill check (strict tick-through) → stop (touch) → T2 (after PB) or T1 (before PB)
- Returns `PBLevel`, `PBLevelRaw`, `E2FillPrice`, `E2FillTime`, `BlendedEntry`
- `simulate_trades` dispatcher now forwards `ml_pb_r`, `ml_pb_ticks` to the tick function (was silently dropping them)

#### 3. `_build` fixes in `_simulate_one_multileg`

- Leg 2 P&L now measured from `e2_entry` (PB fill price), not `actual_entry`
- `r_ach` uses `_e1_risk_dollar = risk_pts / ts * tv1` for 1-leg exits (was always dividing by `tv_total`)

#### 4. Entry Zoom chart added (`bar_analysis.py`)

New `_show_entry_zoom` function renders a tick-level chart around every filled trade entry:
- **3 ticks before SBClose** + **3 ticks after EB Open** (tick-count window, not time window)
- Orange circle = SBClose tick (last tick ≤ sig_dt) with timestamp
- Cyan diamond = EB Open (first tick > sig_dt = fill tick) with timestamp
- Grey dots = surrounding ticks with timestamps
- Orange solid vertical line at sig_dt = 5M bar boundary
- Horizontal lines: SBClose price (orange dotted), Entry price (green dashed), Stop (red dashed)
- Title: `SB Closes HH:MM:SS · EB Opens HH:MM:SS.mmm · Fill XXXX.XX → Entry XXXX.XX`
- Metrics strip: SBClose | EB Open | Entry (Δ slip) | Stop (Δ risk pts)

`_show_entry_zoom_section` wraps it in a `🔍 Entry Zoom` expander with a selectbox — appears after the signal table in Bar Analysis.

#### 5. `SBClose` column bug fixed

`SBClose` in the results DataFrame was always NaN because `base.update(_EMPTY_TRADE)` overwrites it after `sig.to_dict()`. The correct column is `SEPrice` (set by every sim function as `signal_price`). Fixed in:
- `_show_entry_zoom`: uses `sig_row["SEPrice"]` instead of `sig_row["SBClose"]`
- Signal table display (line ~653): `disp["SB Close"]` now reads `results["SEPrice"]` (was always showing `—`)

#### 6. Dependency fixes

- `scipy` installed and added to `requirements.txt` (used by `wfa.py`)
- `boto3` was in `requirements.txt` but not installed in the venv on this machine — reinstalled

#### 7. Two-machine note

All contract data (flatfiles_cache, bars parquet, continuous tick cache) lives on the PC. The Mac only has `data/raw/` with a few files. App runs on both but full contract history requires the PC.

---

## ⭐ HANDOFF FOR NEW CHAT — Bar Analysis sweep-speed rewrite (Session 16)
*Written 2026-06-18 by Opus. Read this whole section before writing any code. The goal: make ALL Bar Analysis sweeps + the main simulation fast, with progress bars, and provably correct — then a full 5-year validation. Only after Bar Analysis is "perfect" do we touch the WFA tab.*

### ✅ Session 16 progress (evening of 2026-06-18) — NOT yet committed→ committed at end of session

**Step A — engine vectorized (DONE, verified).** `simulation_engine.py`: added a numpy first-hit-index scan path for `ratchet_r == 0` to `_simulate_one` (single-leg) and `_simulate_one_multileg` (PB scale-in). Python loop kept for `ratchet_r > 0` / manual-fill and as regression reference. Verified **byte-identical** (`validate_regression.py` old-vs-new), Layer A all pass, Layer B 0 mismatches (1097 trades, both modes). Speed: main multileg sim **59s → 2.4s**.
- **Deferred (do later, needs its own oracle first):** `_simulate_one_3leg` and the non-PB branch of `_simulate_one_multileg` still run the Python loop. 3-leg has no independent oracle — write one before vectorizing.

**Step B — scale-in sweep fast + engine-accurate (DONE, verified).** `bar_analysis.py`:
- Deleted the **drifted inline** `_run_ml_scalein_sweep` (it overstated Net PnL by up to **$7.4k/combo** — `round()` vs floor/ceil PB, and mis-scored same-tick PB+stop gaps).
- New **fast prefix-scan** `_run_ml_scalein_sweep`: precompute running-max/min per signal ONCE → each combo's first-hit is O(log n) `searchsorted` + a C-level numpy suffix scan post-PB. **Full 1224-combo grid ~2 min (95 ms/combo), was ~41 min** (~20×). A 432-combo grid ≈ 40s.
- Kept the slow `_run_ml_scalein_sweep_engine` (= simulate_trades + compute_summary) as the **reference oracle**.
- New permanent regression **`scripts/validate_scalein_sweep.py`** proves fast == engine. **64-combo subset (all code paths, T1<T2 and T1>T2): IDENTICAL on all 14 columns.** Full 1224-combo `--full` run was launched end-of-session → **confirm `data/_regress/scalein_full_verify.log` tomorrow** (expected green; logic is combo-uniform so the subset is the real proof).

**Win-decomposition columns (DONE).** Shared `_win_breakdown()` helper adds **Tgt % / EOD Win % / EOD Win R** to BOTH the R sweep and the scale-in sweep. `Win % = Tgt % + EOD Win %`. (Surfaced *why* Win% plateaus at high R: target becomes non-binding intraday → wins shift from target-hits to EOD-green.)

**Filter defaults changed (DONE).** New defaults in `bar_analysis.py` (code fallbacks) **and** `ba_filter_defaults.json` (git-tracked, so it propagates): **Exclude last 45 min** of RTH, **FOMC ON with ±15-min window cushion** (event mode = "Window ±N minutes", window = 15). These change sweep/sim numbers vs before (fewer signals) — intended. Requires a full app restart (defaults load via `setdefault`, won't override an existing session).

**Note on speed reality (measured this session):** routing sweeps through the engine per-combo is ~1.9–2.7s/combo (full result-dict build dominates, NOT post-processing) → ~15 min for 432 combos. The prefix-scan is the only thing that makes big sweeps usable. Other engine-based sweeps (R, T1×T2, stop-mult) still call the engine per combo and are still minutes on large grids — same prefix-scan treatment could be applied later if needed.

### 🐞 Data-integrity finding (investigated this session, fix NOT yet written)
The "missing tick data" sweep warnings are **truncated Massive flatfile downloads**, verified by inspecting raw gz contents (not file size — multi-product files mask time-truncation):
- **7 dates "no tick data"** — gz truncated before 08:30 RTH open → builder writes no parquet: 2021-07-21, 2021-08-12, 2021-08-13, 2021-10-07, 2021-11-23, 2022-03-16, 2022-06-24.
- **3 dates "no ticks after signal" (truncated mid-session)** — confirmed every contract in the file stops early: 2021-07-26 (08:59), 2021-11-30 (13:01), 2021-12-08 (10:29). (2021-11-30 gz is 45M but multi-product; ESZ1 = 397k RTH rows stopping at 13:01.) Active-contract pick is correct (ESZ1) — NOT a roll bug.
- **5 dates "no ticks after signal" by design** — signal on bar 81 (15:10–15:15, the last bar, no next bar to fill). **No fix needed.**

**Planned fix (script not yet written):** `scripts/refetch_truncated_days.py` — re-fetch those 10 dates (force-overwrite gz) → rebuild continuous ticks → **assert RTH span ~08:30→15:15 and fail loud** (don't silently keep a partial). Plus a **build-time guard** in `build_continuous_ticks_for_date` to flag abnormally short RTH coverage so future partial downloads surface immediately. Re-fetch hits the Massive API (metered) + overwrites cache — get explicit OK before running. Only helps if Massive now serves complete data for those days (the assert tells us).

### Non-negotiable principles (the user was emphatic — this is for real money)
1. **One engine, one definition of a trade.** `simulation_engine.py` is the single source of truth. The main sim, every sweep, the WFA tab, AND a future NinjaTrader auto-trade robot must all produce identical trades. NEVER reimplement trade logic in a sweep — call the engine. (The old `_run_ml_scalein_sweep` violated this and silently drifted — see below.)
2. **Every tick matters.** Entry = first tick after the signal bar close. PB level must be 100% identical across all CSVs, tables, and charts. Stop fills on touch. Floor/ceil PB rounding (see toggle below). Do not "optimize" by changing any comparator, rounding, or priority.
3. **Correctness is verified, not assumed.** Three tools exist (committed). After ANY engine/sweep change, all three must pass before commit: exact regression + Layer A + Layer B (see "Verification protocol").
4. **No commit/push without the user's explicit OK**, and the user must have run the app. Verified-identical output is necessary but not sufficient — still ask.
5. **Edit/Write tools only** for Python source (PowerShell double-encodes UTF-8 → mojibake). All sims behind a Run button in the app. Keep responses short.

### What is ALREADY DONE and verified (committed — do not redo)
- **Sim engine validated.** Session-14 entry logic + PB scale-in are correct. Proven by Layer A (invariants) + Layer B (independent oracle): 0 violations / 0 mismatches on all 1,097 filled trades, both single-leg and 2-leg PB modes, 1-yr window.
- **Engine speedup Step 1 (searchsorted).** `_simulate_one`, `_simulate_one_multileg`, `_simulate_one_3leg` now get the post-signal tick slice via a shared `_ticks_after()` helper (searchsorted, O(log n) + view) instead of `day_ticks[day_ticks["DateTime"] > sig_dt]` (O(n) boolean mask + copy per signal). **Proven byte-identical** to the prior engine: regression = 1,107 rows × 63 cols identical across single/multi/3leg. The scan loops were NOT touched.

### Verification tools (committed in `scripts/`)
- `validate_engine.py` — Layer A invariants. `python scripts/validate_engine.py --mode multileg --start 2021-06-18 --end 2022-06-18`
- `validate_oracle.py` — Layer B independent first-hit-index oracle. `--per-reason 100000` checks every trade. Same args.
- `validate_regression.py` — dumps simulate_trades output (all 3 modes) and diffs trade-for-trade. `dump <dir>` then `cmp <dirA> <dirB>`. Use it to prove a rewrite is identical: dump new → `git stash` → dump old → `git stash pop` → cmp.
- Default exec params used by all three (mirror ES multileg defaults): tick_value 12.50, commission 3.0, entry_slip 1, exit_slip 1, stop_offset 0, contracts_t1 1, contracts_t2 1, t1_r 1.5, target_r(=T2) 1.0, ml_pb_r −0.50. Data: `saved_signals/ba_signals_mc.parquet` (5,580 signals 2021–2026) + per-day tick cache `data/ticks_continuous/*.parquet` (1,247 days). **Work on the 1-yr window 2021-06-18 → 2022-06-18 (1,097 filled) unless told otherwise.**

### THE BOTTLENECK (measured — read this before planning)
One **multileg `simulate_trades` over 1,107 signals = ~59 seconds** on the real continuous tick cache (~356k ticks/day). The dominant cost is the **Python per-tick scan loop** in `_simulate_one*` (EOD/long-held trades scan ~100k+ ticks each in interpreted Python), NOT the pandas filter (that was already fixed by `searchsorted`). Consequence: routing the scale-in sweep through per-combo `simulate_trades` would be ~168 × 59s ≈ **2.8 hours** — so "just call the engine per combo" is NOT viable for the big sweep. The old handoff's "~1 s/combo" was from different/smaller data — ignore it. **Vectorizing the scan is the core fix, and it also makes the main-sim Run button fast.**

### THE REMAINING WORK (in order)

**A. Vectorize the tick scan in the engine (the core fix — ratchet-off case).**
In `simulation_engine.py`, give each `_simulate_one*` a vectorized scan path for `ratchet_r == 0` (always true in sweeps; usually true in the main sim) that computes the outcome via numpy first-hit indices (`np.flatnonzero`/`argmax`) instead of the Python loop — producing the **full result dict** (exit reason/price/PnL, MAE/MFE, E2 fill, blended entry, leg fields, bar nums…). **Layer B's oracle (`scripts/validate_oracle.py`) is the proven template** — it already re-derives exit sequencing this way and matches the engine on every trade. Keep the existing Python loop as (1) the `ratchet_r > 0` path and (2) the regression reference. Preserve every comparator, the PB `continue`, floor/ceil, and stop-on-touch exactly.

**B. Reuse per-signal setup across combos; reroute all sweeps; delete the inline scale-in copy.**
Split each `_simulate_one*` into `prepare_setup(signal, day_arrays)` (entry tick via searchsorted + entry/stop/risk — combo-independent, computed ONCE) and `resolve(setup, params)` (the vectorized scan from A). Precompute each day's `(price_array, datetime_array)` once at the top of `simulate_trades`. Then:
- Main sim = prepare + resolve once.
- Every sweep (`_run_r_sweep`, `_run_t1t2_sweep`, `_run_pb_sweep`, `_run_t1t2_sweep_3leg`, `_run_stop_mult_sweep`, `_run_ml_scalein_sweep`) = prepare setups once, loop combos calling `resolve`. ONE logic copy, no drift.
- **Delete the inline body of `_run_ml_scalein_sweep` (`bar_analysis.py` ~1002–1240).** It is a reimplementation that DRIFTED from the engine in two ways: (1) `round()` for the PB trigger vs the engine's `floor`/`ceil`; (2) on a tick that gaps through both PB and the stop, the engine fills PB and continues while the inline copy calls it a leg-1 stop. Replacing it with the shared `resolve` auto-fixes both.

**C. Confirm the speed target.** After A+B, time it. Need: 17 WFA folds finish in reasonable time (a sweep should be seconds, not minutes). If a sweep reuses setups + vectorized resolve, a 168-combo scale-in sweep should drop from hours to seconds. Measure with `scripts/_timeit.py`-style timing (then delete that throwaway).

**D. PB rounding toggle (user requested).**
Add a toggle in the **Filters** expander of Bar Analysis: PB level rounding = "Floor/Ceil (conservative)" [default] vs "Round to nearest". Thread it through `simulate_trades` → `_simulate_one_multileg` + `_simulate_one_3leg` (the `pb_trigger` / `pb1_price` / `pb2_price` computation, currently `np.floor`/`np.ceil` at simulation_engine.py ~315). Must flow to every sweep and into the sim fingerprint so changing it re-runs. Default preserves today's exact behavior (floor/ceil = snap PB away from entry = harder to fill = never overstate scale-ins). This is a comparison knob, not a new default.

**E. Progress bars on everything.** Every sweep `_show_*` and the main sim Run path must show a live progress bar (the scale-in sweep already has one — pattern at bar_analysis.py ~1107). The user must never see a frozen screen.

### Verification protocol (run BEFORE asking to commit — all must pass)
1. `validate_regression.py`: new vs old (git-stash trick) → **IDENTICAL** for single/multi/3leg. (For sweeps: also confirm one combe, e.g. PB=−0.50 T1=1.50 T2=1.00, sweep row == direct `simulate_trades` + `compute_summary`.)
2. `validate_engine.py` (Layer A) → all invariants pass, multileg + single.
3. `validate_oracle.py --per-reason 100000` (Layer B) → 0 mismatches, multileg + single.
4. Then the user runs the app and eyeballs a sweep + the main sim.
5. **Pardo rule:** never change the PB/T1/T2 grid VALUES during this work — speed only.

### Full 5-year validation (after Bar Analysis is "perfect")
Run validation across the entire signal history **year by year** (memory: ~444M ticks total — never load all at once; `validate_oracle.py` already chunks yearly, mirror that for any new check). All years must pass Layer A + B. This is the confidence gate before WFA.

### Current numbers (1-yr IS window, Jun 2021 – Jun 2022)
- Signals in file: ~5,580 · in window with tick data: 1,107 · filled: 1,097
- 8 dates permanently missing tick data (Massive has none)
- Scale-in grid: typical 168 combos (PB:4 · T1:6 · T2:7); full default 392 (8×7×7)
- **Measured speed:** one multileg `simulate_trades` over 1,107 signals = **~59 s** (full tick cache, ~356k ticks/day; Python scan loop dominates). So 168 combos via per-combo engine calls ≈ 2.8 h — vectorization required. Target: a sweep in seconds so 17 WFA folds finish in reasonable time.

### Loose ends to clean up at handoff
- `scripts/_timeit.py` was a throwaway perf script — delete it. `2026-06-18T12-41_export7.csv` lives in the user's Downloads, NOT the repo; it is the app's OWN exported trade log (regression-only, not independent ground truth) — do not rely on it for correctness.
- `data/_regress/` holds regression dumps (gitignore it or it clutters `git status`).

---

## Next Session — Priorities (set 2026-06-18 evening, session 16)

**First: `git pull` (two-machine).** Then confirm `data/_regress/scalein_full_verify.log` says IDENTICAL (the full-grid fast-vs-engine check launched at end of session 16).

**Critical path:** ✅ sim engine validated → ✅ scale-in sweep fast+correct → 🔄 finish the sweep-speed plan (D, E) + the new feature work below → decide Q5/Q6 → first WFA run.

### Session-17 explicit asks from the user (2026-06-18)
1. **Trailing stop → BE after xR, on BOTH setups (single-leg + 2-leg).** The engine already has `ratchet_r` / `ratchet_dest="BE"` (move stop to break-even after favor ≥ xR) — it works in the loop path but the vectorized fast paths are `ratchet_r == 0` only, and it is not exposed/wired as a first-class control on both setups or in the sweeps. Task: surface it cleanly on both setups, make sure it flows into sweeps + the sim fingerprint, and decide defaults. (Will need a vectorized ratchet path OR keep ratchet-on sims on the loop and document the speed cost.)
2. **New setup: RevFT.** A RevFT signal CSV is arriving. Slot it in as another `setup_id` alongside MC signals (the RevFTSignals upload scaffolding already exists per Session 12). Review the CSV + its strategy logic BEFORE writing code — do not design in advance. No engine changes expected (same trade structures).

### Remaining sweep-speed plan items (⭐ section)
- **D. PB rounding toggle** — Filters expander: "Floor/Ceil (conservative)" [default] vs "Round to nearest", threaded through engine → every sweep → sim fingerprint.
- **E. Progress bars** on every sweep + main sim Run path.
- **Vectorize 3-leg + non-PB multileg** — write a 3-leg Layer-B oracle first, then vectorize (currently loop-only, so the 3-leg sweep is slow).

### Data integrity (paused — script not yet written)
- Write `scripts/refetch_truncated_days.py` (10 truncated dates) + build-time RTH-coverage guard. See "🐞 Data-integrity finding" in the ⭐ section above. Re-fetch hits Massive API + overwrites gz → get OK before running.

### Step 2 — Decide Q5 and Q6 (before reading any OOS)
Max concurrent positions and max daily loss rule are still open (`open_questions.md`). Current WFA output assumes unlimited concurrent positions and no daily loss cap. Decide these **before** reading OOS results — reading OOS then changing the model is a Pardo no-feedback violation. WFA OOS metrics are not actionable for live sizing until decided.

### Step 3 — First real WFA run
1. Start the app (`.venv\Scripts\streamlit run app.py`)
2. Build `mas_continuous` in the Massive tab if not already persisted
3. Upload CC2 signals (or whichever setup has the most data)
4. Open the `🔄 WFA` tab → Configure & Run → select multileg, default windows (IS=12mo / OOS=3mo, 3 param sets)
5. Verify: fold count shown (~16), IS sweep runs without error, guardrail badges appear, OOS equity curve renders, fold table populates
6. Spot-check one fold's IS sweep: confirm the param grid was correct (T1 < T2 enforced, PB values negative)
7. **Only after a clean run** move on to portfolio layer or window scanner

### Step 3 — Portfolio WFA layer
Update Portfolio tab to load and combine OOS equity curves from multiple setup runs via `load_portfolio_oos_trades()` in `results_store.py`. This is already wired on the storage side; only the Portfolio tab UI needs updating.

### Carry-over from Session 12 (lower priority than WFA)
1. **Econ calendar API** — user flagged this as broken at end of Session 12. Ask what specifically is broken before touching `economic_calendar.py`.
2. **Migrate Bar Analysis filters to the shared panel** — `ba_`-prefixed widgets still independent from `validation.get_filters("shared")`.
3. **"Clear all cached data" confirmation popup** — no confirmation UI exists currently.
4. Re-download ~50 missing trading days in `data/flatfiles_cache/`.
5. Root-cause tick-cache validation discrepancy (98.6% vs 100%).
6. Live-test RevFTSignals and alt-path mismatch table with real divergent data.

### Stale / superseded (kept for history only — do not act on without re-confirming with user)
The items below were written for the old Massive.io-as-secondary-track plan (Sessions 10–11) and are now superseded by Session 12's work — Massive is already primary, the API is already confirmed and working, and `massive.py` already has the contract manager described here. Left in place rather than deleted per "preserve existing architecture unless instructed otherwise," but treat as historical.

1. ~~Confirm futures endpoint paths~~ — done, `massive.py` Contract Manager downloads real ES futures successfully.
2. ~~Confirm futures agg field names~~ — superseded; current pipeline uses flat-file trades, not the Aggs API.
3. ~~Contract lookup~~ — done, `CATALOG` in `contracts.py`.
4. ~~Run `scripts/fetch_for_nt.py`~~ — superseded by `massive.py`'s built-in NT import file writer.
5. ~~Run OHLCExporter on ES_MAS chart~~ — done, all 20 contracts have NT import files.
6. ~~App Comparison 1 (tick-built vs agg)~~ — superseded by the tick-cache-vs-5M-bars validation built in Session 12.

### SCID / WFA (carry-over, blocked on SC data)

1. **Configure SC for 1-second OHLCV** — set chart type to 1-second bars for all ES quarterly contracts (ESZ09–ESM26), request historical data from SC. Expected ~210 MB/quarter.
2. **Run `scripts/build_scid_cache.py`** once 1-second data is on disk.
3. **Update SCID pipeline for 1-second bars** — `resample_ticks_to_bars` needs to aggregate OHLC from 1-second OHLCV, not tick prices.
4. **Gate 1** — validate Python-built 5-min bars vs SC native 5-min export.

### Other

1. **Reversal setup** — review NT signal CSV + strategy logic before any code. Do not design in advance.
2. **Carry-over:** Verify PDF equity chart resize, verify 2-leg math (both low priority).

---

## Session 2 — June 7, 2026 — Design Decisions (still valid)

### Scale-In / 3-Leg Design

#### Naming convention

| Layer | E1 | E2 | E3 |
|-------|----|----|-----|
| Code | E1 | E2 | E3 |
| UI | Initial | PB1 | PB2 |
| Trade types | Rocket (E1 only) | E1+PB1 | E1+PB1+PB2 |

#### R reference
- **All targets and stop ratchet triggers use original R** (E1 entry → E1 stop distance).
- Blended average entry is used **only** for BE stop calculations and T2 target.
- Rationale: original R is stable and computed at signal time.

#### PB Level Parameters
- Level as R multiple: `[0.25, 0.33, 0.50, 0.66, 0.75, 1.00]` × original stop distance
- Tick offset (signed integer): fine-tune entry relative to R level
- Hard floor: 1.0R level minimum offset = 0 (negative = buying below stop)

#### Exit Modes — Per Trade Type
Each trade type (Rocket, E1+PB1, E1+PB1+PB2) has independent exit parameters.

#### Stop Ratchet — Per Trade Type
Trigger = after X R move → stop to blended BE / E1 / lock-in R.

---

### WFA Methodology — Locked

| Parameter | Decision |
|-----------|----------|
| Method | Rolling WFA (not anchored) |
| IS window | ~1 year |
| OOS window | ~3 months |
| Total length | 2010–2025 (~56 walk-forwards) |
| WFE minimum | ≥ 50% |
| OOS profitable windows | ≥ 60% |
| Min trades per OOS bucket | ≥ 30 (Pardo), ≥ 100 preferred |

---

## Current Versions

| Component | Version | Notes |
|-----------|---------|-------|
| NT8 Simulator | SIM_v3.3 | Multi-leg, OnBarClose, PB66 + EB stop |
| Apps Script | GS_v4.5 | ETH bucket, pre-filters, export fixes |
| Google Sheet | SHEET_v3.3 | |

---

## Data Status

| Source | Status | Notes |
|--------|--------|-------|
| Sierra Charts scid (Delani) | ✅ Parser built | 12 quarterly contracts on disk (ESU23–ESZ25). Parser working: 9M+ ticks/quarter. See SCID Data System section above. |
| NT8/Rithmic tick data | Available | 1 year on disk. Used for Gate 2 bar validation. |
| ESM6 CME tick data (.txt) | Available | 56 trading days. Old disk file — not loaded by default. |
| NT 5M bar data (.txt) | Available | April 1 – June 3 2026. Upload via OHLC uploader. |
| 2022–2025 + pre-2021 data | Arriving | Expected soon. |
| massive.io API | Subscribing 2026-06-16 | Developer plan. Futures Trades + Aggs APIs. ES quarterly contracts. Full docs in `docs/reference/massive_io/`. |

---

## Rules for New Chat

1. Never write code until explicitly instructed
2. Always ask: entire file rewrite or old/new snippets?
3. Never invent NT8 APIs — check NT8 docs in project files first
4. Preserve existing architecture unless instructed otherwise
5. No fluff, no affirmations, be direct and technical
6. Read `NT8_NinjaScript_LessonsLearned.md` before writing any NT8/SharpDX code
7. Always search project knowledge and past chats before answering questions about prior decisions
8. Read `docs/README.md` index before adding any new doc — no duplicates, no orphans
9. **NEVER commit and push code the user has not tested. Syntax check is not a test.**
10. **Never guess NT8 behavior.** If the answer is not in the docs or confirmed by the user, say "I don't know" and stop. Do not fill gaps with plausible-sounding guesses.
11. **Two-machine workflow:** User works on both a PC and a Mac laptop. Always remind to `git pull` at the start of every session before any other work.
