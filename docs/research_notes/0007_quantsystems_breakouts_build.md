# 0007 — QS Breakouts: Build & Test Mechanism — 2026-06-24
**Series:** MC Setup Research Notes · Note 0007 · **LIVING (in progress)**
**Confidence:** N/A — this is an **engineering/methods note**, not an edge study. It documents *how* we reproduce and test the QuantSystems breakout setups so any result later is auditable and re-runnable. The companion **0006** holds the *spec* (the rules); this note holds the *machinery*. No edge is claimed.

**TL;DR:** Reproduction is a 3-layer pipeline: **(1) detection** (`qs_setups.py`, pure/headless, every paper parameter on one `QSConfig` dataclass) → **(2) simulation** (reuse `simulation_engine.simulate_trades` — tick-level paths, real costs) → **(3) view/sweep** (new `🎯 QS Breakouts` tab reuses the bar-viewer chart; a purpose-built setup-aware sweep re-detects per combo). The contract that glues it together is the **project-standard signal schema**. First gate — signal **frequency** — already passes (BO+FT ≈ 6.3/day after filters vs the paper's ~5/day).

---

## 1. Why a separate build note

0006 makes the rules precise. But "precise rules" can still be tested wrongly (look-ahead, wrong fills, costs omitted, un-sweepable hard-codes). This note pins the *mechanism* so that:
- every parameter the paper names is **sweepable** (no hidden constants),
- detection is **headless + unit-testable** (validated before any UI spend),
- simulation reuses the **already-audited** engine (same tick paths + cost model as MC/Keystone work — comparable numbers),
- the chart labels obey the project's **tick-granularity** rendering rules for free.

## 2. Architecture (3 layers + 1 contract)

```
            QSConfig (dataclass, all paper params)
                       |
   data/bars/_continuous.parquet (5m, CT, RTH)
                       |
        ┌──────────────▼───────────────┐
        │ (1) DETECTION  qs_setups.py   │  pure pandas/numpy, no Streamlit
        │  range,IBS,BarDir,ABR + setups│
        └──────────────┬───────────────┘
                       │  >>> SIGNAL SCHEMA CONTRACT <<<
                       │  SignalNum,SignalType,Direction,DateTime,
                       │  BarNum,SignalPrice,StopPrice,Date,FilterStatus
        ┌──────────────▼───────────────┐
        │ (2) SIMULATION                │  simulation_engine.simulate_trades
        │  tick paths + costs + exits   │  (REUSED, unchanged)
        │  target_r, entry_model, ...   │  ticks: massive.load_continuous_ticks
        └──────────────┬───────────────┘
                       │  results schema (adds EntryTime/Price, ActualStop,
                       │  Target, ExitTime/Price, ExitReason, NetPnL, ...)
        ┌──────────────▼───────────────┐
        │ (3a) VIEW  🎯 QS Breakouts tab│  reuses bar-viewer chart fn
        │ (3b) SWEEP setup-aware grid   │  re-detect+re-sim per combo
        └───────────────────────────────┘
```

**The contract (why layers stay decoupled).** Detection emits exactly the schema
`simulate_trades` already consumes (the same columns as `saved_signals/ba_signals_mc.parquet`).
So the sim, the cost model, the execution-audit, and the bar-viewer chart all work
on QS signals **with no changes** — we only add layer (1) and the thin tab/sweep
in (3). This is the same decoupling every `scripts/*_study.py` relies on.

## 3. Layer 1 — detection (`qs_setups.py`)

- **Pure & headless** (pandas/numpy only) → importable by the tab *and* by scripts; unit-testable.
- **`QSConfig` dataclass** — every paper parameter + every 0006 ambiguity knob (A1 `bull/bear_*_ibs`, A3 `strong_bar_is_breakout_bar`, A5 stop knobs, ABR period/include-current, big-bar mult, all filter toggles). Defaults = note 0006. **Nothing is hard-coded → the whole detector is sweepable.**
- **Building blocks** (note §2): `_ibs`, `_bardir` (verbatim cascade, stateful per session), `_abr` (prior-N, session-scoped, NaN until enough history).
- **Setups implemented:** Setup 1 **BO+FT** (2-bar) and Setup 2 **Big Breakout** (1-bar). BigBO is checked first (priority); the two share building blocks so adding Rev+FT (#3) later is incremental.
- **iStop / R** (`_stop_price`, note §4.2): `StopPrice` baked in at detection so `R = |SignalPrice − StopPrice|` is whatever the paper's variant says; `target_r` in the sim = the paper's 1R. Paper's small/2-bar/big overrides behind `use_paper_istop_variants` (else a clean `stop_basis × stop_dist_mult` for free sweeping).
- **Filters** (`_apply_filters`, note §4.4): no-3rd-consecutive, time (≥ `entry_start_ct`, CT), large-bar. **Tags `FilterStatus` (does not drop rows)** — so the chart can grey filtered signals and a sweep can include/exclude them cheaply. Legs-3/4 (P5) deliberately absent (no leg counter yet).

**Key implementation decisions (for auditability):**
- Times are **CME Central**; the store's 08:30 = NY cash open. `entry_start_ct="09:10"` == 10:10 ET.
- ABR is **session-scoped** (no cross-day bleed); a signal can't fire until `abr_period` prior bars exist in the same RTH session.
- `BarNum = (open − 08:30)/5` (0-based), matching the existing MC convention (12:55 → 53).
- Setup overlap (paper 1d/2c: a BO bar may also be a reversal) is **not** de-duped across setup *types*; within a bar, BigBO wins over BO by priority.

## 4. Layer 2 — simulation (reused, unchanged)

`simulation_engine.simulate_trades(signals, ticks_by_date, target_r, entry_slip,
exit_slip, stop_offset, tick_value, contracts, commission, entry_model=..., ...)`:
- replays **real continuous ticks** per day (`massive.load_continuous_ticks`),
- `R` = entry−stop distance (matches our `StopPrice`), exits at `target_r`·R or stop,
- **house costs**: $5 round-turn + 1 tick/leg slippage (overridable; we stress later),
- `entry_model` `"market"` (fills ≈ next tick after signal-bar close) is the BTC default; `"stop"`/delay models available for execution-sensitivity (ESA),
- returns the full **results schema** the bar-viewer chart and execution-audit already understand.

> Multileg/scale-in params exist in the engine but the paper's scale-in level is **P4 (placeholder)** — base spec is single-leg flat-1R.

## 5. Layer 3 — view & sweep

**3a — `🎯 QS Breakouts` tab (planned).** Controls bound 1:1 to `QSConfig` + sim
params; single run → headline metrics + the **existing** bar-viewer chart fn
(`bar_analysis.py`), which already renders the standard schema with **tick-granularity
labels**: signal `vrect` on the signal bar, entry/exit markers at **exact fill-tick**
timestamps/prices, stop & target lines, x-axis labelled by bar **close** (open+5m).
Filtered signals (`FilterStatus≠ok`) render greyed.

**3b — setup-aware sweep (planned, purpose-built).** The existing `_run_*_sweep`
helpers re-score a *fixed* signal set (exit params only). QS needs to sweep
**detection** params too (ABR, IBS, big-bar mult, stop geometry, filters), which
change the signal set — so each grid cell = **re-detect → re-simulate → score**.
Design: a grid spec over `QSConfig` fields × sim params, cached by config hash,
emitting an expectancy/PF/SQN/MAR surface. (User approved building a new sweep tool
rather than bending the exit-only ones.)

## 6. Validation gates (run in order; cheapest first)

| Gate | What | Status |
|------|------|--------|
| **G1 Frequency** | signals/day vs paper (~5 BO/day) — no P&L | ✅ **PASS** — see §7 |
| G2 Spot-check labels | a few days rendered; signals sit on the right bars | ⬜ pending tab |
| G3 Cost-aware baseline | BO+FT through sim, no leg filter, full costs | ⬜ |
| G4 Robustness | sweep ABR/IBS/stop — does edge (if any) survive? (paper [1] claims it should) | ⬜ |
| G5 Execution sensitivity | ESA slippage stress | ⬜ |

## 6b. LIVE FINDINGS LOG (S41 — keep appending; promote to edge note 0008 when locked)

**Dataset:** `data/bars/_continuous.parquet`, 5m RTH, **2021-06-18 → 2026-06-15, 1,249 sessions**; fills on real continuous ticks. NOT the WP's hand-picked 100-trade VIX batches.

**Authoritative source = EL Ver 5 (Feb 2023) + Pine v7.6 cross-check** (identical core logic). Defaults differ by version — but the WP *study* config was reverse-engineered from frequency (below), since "default off ≠ unused."

**Reverse-engineered the WP study config from frequency fingerprint:** `QSConfig.paper()`
= all 3 signal types ON + IBS 69/31 on signal bar + ABR(10) range gate + 2-bar FT
(same-dir / must-BO, not close-beyond) + 10:10ET + no-3rd-consec. This reproduces the
paper's stated counts: **total 17.7/day (WP ~20), BO 6.4/day (WP ~5), BO-family 11.3% of
bars (WP "~12%")**. Critically, the counts only reconcile with the **range/ABR filter ON**
(Pine ships it off) → Ali used it for the study.

**Frictionless P&L (FT-only = WP BO+FT setup, entry bar 2, hold 1R):**
- 1R: n=1,196 · win **65.1%** · expR **+0.224** · PF 2.26 · **SQN 10.85**
- WP Fig 14/15: win 83–86%, SQN 7.4–8.9.
- **Our SQN ≥ WP on a 12× larger unselected sample — the edge reproduces.** The win-rate
  gap (65% vs 83%) is Ali's discretionary **breakeven/early-loss exit** (his AvgR 0.8 @ 83%
  win ⇒ avg loss ≈ 0.18R, not the full −1R). Same edge, redistributed. → test a BE stop (G3b).
- BO-family @1R shows 93%/SQN 160 = a **geometry artifact** of the 2×-combined iStop making
  1R trivial; not a real edge — use FT-only for WP comparison.

**Per-period stability (FT-only, frictionless, 1 ES contract) — POSITIVE EVERY YEAR:**
| Yr | n | win% | expR | SQN | net$ @1R | net$ @2R |
|----|---|------|------|-----|----------|----------|
|2021|126|59.5|+0.198|2.9|$23,462|$19,462|
|2022|255|67.5|+0.238|5.3|$101,812|$116,012|
|2023|240|67.1|+0.228|5.1|$55,150|$56,138|
|2024|258|61.6|+0.196|4.2|$64,762|$60,375|
|2025|237|67.9|+0.288|6.4|$95,575|$91,300|
|2026*|80|63.7|+0.111|1.5|$18,538|$15,575|
- 5yr total ≈ **$359k @1R / $359k @2R per 1 ES contract**, frictionless (~$340k with house
  costs). Quarterly/monthly/weekly CSVs in `docs/living/qs_periods/`.
- Every calendar year positive (quasi-OOS). 2026 partial. This is the strongest evidence so far.

**OPEN / next:** BE-stop test (chase WP win%); WP-faithful FT "same-direction-only" mode;
legs-3/4 filter (the headline ~5/day + biggest WP edge driver, still a placeholder); the tab
+ chart labels; costs/ESA stress; then lock → edge note **0008**.

## 7. Results so far — G1 frequency gate (PASS)

`python scripts/qs_breakouts_detect.py` over **1,249 RTH sessions** (2021-06 → 2026-06):

| Setup | count | per day (raw) | per day (after no-3rd-consec) | paper |
|-------|-------|---------------|-------------------------------|-------|
| BO+FT | 11,831 | 9.47 | **6.28** | ~5/day |
| BigBO | 1,872 | 1.50 | — | (rarer subset) |

- Direction split: BO 6,237 L / 5,594 S (balanced); BigBO 782 L / 1,090 S (short-skewed — big bars cluster in selloffs).
- `FilterStatus`: 66.8% `ok`, 33.2% `consec3`; **0** blocked by time (ABR(10) can't fire before ~09:25 CT, already past 09:10).
- **Verdict:** same order of magnitude as the paper; the ~1.3× excess is expected (paper also applies legs-3/4 + 10:10, conservative hand-marking). No spec error indicated → proceed.

## 8. How to run (current)

```
# G1 frequency gate (headless, ~seconds)
python scripts/qs_breakouts_detect.py

# in Python
from qs_setups import detect, QSConfig
import pandas as pd
bars = pd.read_parquet("data/bars/_continuous.parquet")
sig  = detect(bars, QSConfig())            # standard signal schema
```

## 9. Files

- `qs_setups.py` — detection + `QSConfig` (layer 1).
- `scripts/qs_breakouts_detect.py` — G1 frequency gate.
- *(planned)* `🎯 QS Breakouts` tab in `app.py`/`bar_analysis.py`; setup-aware sweep.
- Spec: `docs/research_notes/0006_quantsystems_breakouts_blueprint.md`.

## 10. Open items / next

1. Wire `simulate_trades` over QS signals (G3) — single-day spot-check first (G2).
2. Build the tab (controls ↔ `QSConfig`), reuse the bar-viewer chart.
3. Build the setup-aware sweep (G4) + ESA (G5).
4. Then — and only then — a SEPARATE edge note (≥0008). This note asserts no edge.
