# PROJECT CHARTER — myquant

**Purpose of this file:** the single from-inception synthesis. `handoff.md` is a
stack of session *deltas* (the frontier); this charter is the *arc* (where we
started, how it evolved, what is locked, and whether we're on track). A fresh
chat reads **this file for orientation, then `handoff.md` for current state**,
and is oriented in one pass.

**Status:** Living — revise when the mission, architecture, or a locked decision
changes (not every session). Created Session 22 (June 20, 2026).
**Source-of-truth rule is unchanged:** `docs/living/handoff.md` remains the
authoritative record of *current* state. If this charter and the handoff
conflict on *what is true today*, the handoff wins. The charter owns the *arc*
and the *locked decisions*.

---

## 1. The Mission (unchanged since inception)

**Rigorously decide whether an ES-futures breakout setup is tradeable, without
curve-fitting.**

The strategy under test is a set of MarketCharacter ("MC", a.k.a. "CC") breakout
/ volatility-expansion signals on ES futures, plus a second setup, RevFT
(reversal). The deliverable is not a strategy — it is a **validation and
decision apparatus**: a walk-forward engine with Pardo-grade discipline that can
prove (or reject) a *durable* edge and force an honest go/no-go. This is for
real money, so correctness is verified, not assumed.

What "without curve-fitting" means in practice is encoded in the locked
decisions (§4). The recurring failure mode this project guards against is the
**no-feedback violation**: reading OOS results and then redesigning the model to
fit them.

---

## 2. How We Got Here (the arc)

The starting point was a working NinjaTrader 8 (NT8) simulator and a Google
Sheets analysis pipeline (both complete; SIM_v3.4 / GS_v4.5 / SHEET_v3.3). The
task then became: **build a Python walk-forward engine to validate the ES
breakout strategy** — independent of NT, with Pardo discipline.

Three things evolved; one thing did not.

**The data pipeline changed (twice).**
- Originally **Sierra Charts `.scid`** (1-second OHLCV) was the planned source,
  with a two-gate validation plan (Gate 1: Python bars vs SC export; Gate 2: SC
  bars vs NT/Rithmic). Gate 2 surfaced a back-adjustment discrepancy whose root
  cause was found (individual contracts required, not the continuous series).
- **Session 12 (June 16) was the pivot: Massive.io flat-file ticks became the
  primary and only active pipeline.** The SC/SCID path is *paused, not deleted*.
  NT is now used **only** as a continuous-contract upload for matching/
  validation — never as a fill/exit data source.

**The focus changed (engine → research tooling → validation/decision tooling).**
The engine was built and validated first; then a lot of *descriptive* research
tooling accreted (regime/indicator expectancy, factor grouping, sweeps, slice
inspector); the current and correct emphasis is back on **validation + a forced
decision**.

**The mission did not change.** Decide tradeability without overfitting.

### Rough timeline (sessions)
- **S2** — design decisions still in force: scale-in/3-leg naming, R reference,
  WFA methodology locked (rolling, IS≈1yr / OOS≈3mo).
- **S6–S7** — SCID 1-second OHLCV architecture; Gate 2 root-cause work.
- **S9–S11** — Massive.io API confirmed; ES_MAS NT pipeline proven.
- **S12** — **Massive becomes primary.** Continuous back-adjusted tick series.
- **S13** — **WFA infrastructure built** (`simulation_engine.py`,
  `results_store.py`, `wfa.py`); one engine extracted; PROM added.
- **S14–S16** — engine **vectorized** and proven byte-identical; sweeps made
  fast + provably engine-accurate; 3-layer verification harness established.
- **S17** — ratchet vectorized; 2-leg T2 redefinition (`scale_in_style="e2"`);
  PB-rounding toggle; dynamic signal-type checkboxes; WFA unblocked.
- **S18** — tick-snap of computed targets (engine re-baseline); WFA UI overhaul +
  Pardo-safe diagnostics + two heatmaps; Continuous Chart tab.
- **S19–S20** — `indicators.py` (VWAP σ-bands, value areas, daily regime,
  intraday ER, MSS); descriptive expectancy tables; **direction decided: a
  LOCKED multi-slice regime filter validated via WFA** (sizing deferred to MES).
- **S21** — 2-D Stop×Target sweep; the locked regime filter built into WFA;
  three misleading WFA metrics fixed (they were measurement artifacts, not
  strategy failures).
- **S22** — this charter; then master-run pipeline + full export; then the first
  real unpinned end-to-end go/no-go.

---

## 3. Current Architecture (one-pass map)

**Data flow:** Massive.io flat-file ticks (S3) → per-contract 5M bars +
back-adjusted **continuous tick series** (built/persisted in the `📂 Massive`
tab) → simulation over a per-day continuous tick cache. NT is validation-only.

**One engine, one definition of a trade.** `simulation_engine.py` is the single
source of truth. The main sim, every sweep, the WFA tab, and any future NT
auto-trade robot must produce *identical* trades. Trade logic is never
reimplemented in a sweep — sweeps call the engine (a drifted inline scale-in
sweep that violated this was deleted in S16).

**Key modules:**

| File | Role |
|------|------|
| `app.py` | Entry point, tab layout, contract selector, startup cache auto-load |
| `data_loader.py` | Contract registry, loaders, `bar_num_from_dt()` (⚠ 5M-hardcoded) |
| `simulation_engine.py` | **The engine** — single/2-leg/3-leg sim, `compute_summary` (PROM), tick-snap, vectorized scan paths |
| `bar_analysis.py` | Bar Analysis tab — descriptive research, all sweeps (R, T1×T2, scale-in, stop-mult, 2-D Stop×Target) |
| `indicators.py` | Pure compute — VWAP σ-bands, value areas, daily ATR/ADX + percentiles, intraday ER, `tag_signals` (look-ahead-safe), MSS |
| `regime_filter.py` | Locked multi-slice regime filter (pure/testable) used by WFA |
| `wfa.py` | WFA engine (`build_folds`, `run_is_sweep`, `select_params`, `run_wfa`) + tab |
| `results_store.py` | SQLite fold/run metadata + Parquet per-fold trade logs |
| `continuous_chart.py` | Continuous 5yr candlestick + overlays |
| `portfolio.py` | Per-setup 2-leg sim, equity curves, saved runs |
| `massive.py` | Massive contract manager + tick/continuous pipeline |

**Tab order (S21):** Bar Viewer · **Bar Analysis** (default-open) · Massive ·
Data/Validation · Chart · Portfolio · WFA.

**Storage:** `data/wfa_store/wfa_results.db` (runs + folds), per-fold trade
parquet, persisted IS sweep grids (`sweeps/`). Continuous tick cache:
`data/ticks_continuous/*.parquet` (~1,247 days).

**Verification harness (run before any commit touching the engine):**
`validate_engine.py` (Layer A invariants), `validate_oracle.py` (Layer B
independent first-hit oracle), `validate_regression.py` (byte-for-byte vs prior),
`validate_ratchet.py` (vec==loop), `validate_scalein_sweep.py` (fast==oracle).

**Two-machine workflow:** user works on a PC and a Mac. Full contract data lives
on the PC. **`git pull` at the start of every session.**

---

## 4. Locked / Irreversible Decisions (the rails)

These are decided. Do not re-litigate without an explicit, reasoned request from
the user.

**Methodology (Pardo, locked S2/S13):**
- Rolling (not anchored) WFA. IS≈1yr / OOS≈3mo, step = OOS length, ~16 folds.
- Objective = **PROM** (Pessimistic Return on Margin). PnL/DD and PF are
  displayed but do not drive selection.
- Guardrails per fold: ≥70% IS combos profitable, kurtosis of PROM surface ≤6,
  ≥30 IS trades; trade the **average of top-N sets** (default 3), not the single
  best.
- Acceptance targets: WFE ≥ 50%, ≥60% OOS-profitable windows, ≥30 trades/OOS
  bucket (≥100 preferred).
- **OOS is locked immediately after a run** (`lock_oos()` inside `run_wfa`).
- Scan ranges, strategy logic, and objective are fixed **before** the first IS
  sweep.

**The no-feedback discipline (the heart of the project):**
- **Regime filters are LOCKED before WFA and never optimized/re-tuned against
  OOS.** WFA optimizes only T1/T2/PB per fold — never the filter, never TOD/DOW.
- Pre-commit a *small number* of hypothesis-driven filters; do **not**
  combo-hunt and keep the survivors (multiple-testing trap).
- Prefer open-ended thresholds (e.g. |VWAP σ| ≥ 2) over hand-drawn bands; every
  kept/dropped bucket needs a structural *why*, not "it was red."
- Lookbacks (ATR/ADX 14, ER 10d, 252d percentile) are **conventions, not
  optimized** — never sweep a lookback to fit the trades.
- Describe-don't-fit: descriptive tooling reports; it never selects parameters.

**Engine / trade definition (locked through S18):**
- One engine, one trade definition (§3).
- Entry = first tick after the signal bar close; stop fills on touch; same-bar
  priority Stop > T1 > PB.
- 2-leg T2 = E2 entry + R × E2's-own-risk (`scale_in_style="e2"`, default).
- Computed price levels **tick-snap** to tradeable ticks (`pb_round="nearest"`
  default) — realistic on execution, conservative on selection.

**Scope decisions:**
- **Sizing is deferred to MES** (micro). At 1 ES contract there isn't position
  granularity to size; the pragmatic tool now is filtering. The old "prefer
  sizing over filtering" stance is *paused for ES, not abandoned*.
- Massive is the only active data pipeline; SC/SCID paused; NT validation-only.
- Q5 (max concurrent positions) and Q6 (max daily loss) are **still open** and
  must be decided **before** any OOS result is used for live sizing.

**Working rules (carry-forward, every session):**
NEVER commit/push without explicit OK · the user must have run the app first
(syntax check ≠ a test) · `git pull` first · Edit/Write only for source
(PowerShell mangles UTF-8 → mojibake) · all sims behind a Run button.

---

## 5. On Track? (honest assessment — keep challenging this)

**Method: yes.** The Pardo rails are sound and actually enforced (lock before
OOS, no co-optimization in WFA, describe-don't-fit, one engine / one trade
definition). The engine is validated to a high bar (Layer A + Layer B, byte-
identical vec==loop, fast==oracle). The S21 "scare" was *measurement* artifacts
(WFE÷≈0, kurtosis on a pinned grid) — now fixed — not a strategy failure.

**The standing pushback (keep-in-check order):** we are accumulating
**tooling/metrics faster than decisions.** Tells:
- The only dissected WFA run was **fully pinned** — so WFA wasn't doing its core
  job (testing parameter robustness) — with a **modest edge** (OOS PF 1.16).
- Identical OOS counts across different setup labels on disk (S21 flag) — the
  per-setup filter may not actually be subsetting signals. **Verify before
  trusting per-setup results.**

The risk is **analysis-as-procrastination**: more dashboards will not answer the
tradeability question.

**The corrective (S22):** run **one real end-to-end** — a single CC setup,
**unpinned** WFA, regime filter either OFF or *one* pre-locked hypothesis — and
force a **go/no-go**. The master-run pipeline + full export is the vehicle for
that one run.

**Hard rail on the "autonomous master run":** "without us interfering" must
**NOT** include auto-selecting the regime filter or pinning params to results —
that is the exact no-feedback violation the project guards against. The master
run executes a **human-pre-specified config** and *reports*; it never auto-tunes.

---

## 6. Open Frontier (see `handoff.md` for live detail)

- Verify the 2-D Stop×Target sweep edge cross-checks in-app (1.00× column == 1-D
  R sweep; current-target row == 1-D stop sweep) — its definition-of-done.
- Investigate the identical-per-setup OOS-count flag (filter subsetting bug?).
- Build the **master-run pipeline + single self-contained HTML/zip export**.
- The **first real unpinned end-to-end go/no-go** on one CC setup.
- Decide Q5/Q6 before reading OOS for sizing.
- Carry-forward: OOS Regime Analysis module, quick-win metrics, 15M timeframe
  (`bar_num_from_dt` is 5M-hardcoded), vectorize 3-leg, refetch 10 truncated
  Massive days.
