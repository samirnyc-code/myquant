# Setup-Grading ML Pipeline — Plan (S75V, agreed 2026-07-20)

**Status:** planned, approved. Not yet built. This is the durable spec from the
planning conversation — read before starting the build.

## Goal
Learn the function Samir's discretion computes — the thing that looks at a mechanical
setup (H1/H2/L1/L2, later reversals/MTR/W1P/breakout+FT) and says "that one" vs "not" —
and turn it into a **grader**: an indicator that scores each mechanical setup by fit to the
A+ profile, instead of trading every mechanical instance blind.

Core premise (Samir's own words): *there is no edge in mechanically trading every H1/H2;
the only filter known to work is discretion.* This project tests whether that discretion
has measurable edge, extracts its common denominators, and — only if the edge is real —
builds the grader.

## THE FALSIFICATION GATE (non-negotiable, comes first)
Before any ML: does A+ discretion actually beat the mechanical baseline?
- Grade setups, auto-record forward outcome for ALL of them (A+ AND passed-on).
- Compare expectancy: Samir-A+ vs every-mechanical-instance.
- **If A+ expectancy does not beat mechanical → stop.** Save months.
- Checkpoint after the first ~150 random days, not after all 1270.

## Methodology (the honesty guarantees)
1. **Mechanical pre-marking kills selection bias.** Claude places all H1/H2/L1/L2 by
   Brooks rules; Samir only GRADES + COMMENTS. He cannot invent winners or skip losers.
2. **Blind grading, batch-locked.** Forward reveal stays LOCKED across the whole batch
   until every mark is graded — no outcome leaks in during the primary pass. `reveal_idx`
   already enforces no-lookahead in mark_setups.py (client + server, auditable).
3. **Batch-blind, not per-chart-blind.** Grade ~20-40 charts fully blind before revealing
   any, so discretion stays STATIONARY (doesn't drift as outcomes are seen). Random day
   order for the same reason.
4. **Two-tier commentary, hard-separated:**
   - `blind_grade` + `blind_comment` + `blind_time` → the training label. Sacred.
   - `eod_grade` + `eod_comment` → hindsight pass after reveal, TAGGED, never a label.
   - The gap between blind and eod grade measures how much outcomes sway him.
5. **Outcome is auto-computed, never graded.** Store the forward PATH (next N bars H/L,
   MAE/MFE) — assumption-free, so any stop/target/exit can be computed later without
   re-labeling.
6. **Consistency check:** silently re-serve ~1 in 20 already-graded charts. Same grade =
   stable discretion. Establishes the noise floor before trusting labels.

## Data (checked 2026-07-20)
- **1270 ES trading days, 2021-06-18 → 2026-07-09**, tick granularity. The universe.
- 5M bars + footprint rebuilt from ticks on demand (footprint validated exact vs MzPack).
- **Gamma levels only back to 2024-07 (~526 days / 40% of universe).** Older 3yr = price
  action + footprint + structural levels only. Blind spots ~9 months. **L2/market depth
  NOT available historically — forward-only, a separate exercise.**

## Chart display vs feature backend (the key design)
**Display (what he sees while grading) — kept PURE:** EMA20 + prior-day H/L/C only.
Absolute price on the y-axis (accepted — round numbers matter; era-leak tolerated since
mechanical marks already kill selection bias). NO dates on charts.

**Backend (computed for every mark, whether displayed or not):** distance-to-nearest for
gamma levels, blind spots, IB, PDH/L/C, weekly OHLC, monthly OHLC, VWAP, overnight H/L,
prior settlement, developing POC/VA, prior swing H/L, round numbers, measured moves.
Rationale: **you cannot "discover" a level matters if you baked it into the label.** Keep
the label price-action-pure; let levels EARN their place via the backend.

Order-flow features (from ticks, historically available): signal-bar delta, absorption on
the pullback low, CVD divergence, POC location vs entry, volume-profile shape. (DOM
pulling/stacking/icebergs are L2 → forward-only dataset.)

Pullback-quality features (the real Brooks signal): leg count, one- vs two-legged,
bull/bear bar counts inside the pullback, ii/iii, EMA hold vs overshoot, prior trend-leg
strength, distance from EMA, time of day, ATR/vol state, intended-stop implied R:R.

**The "why" descriptions are the feature-discovery engine:** Claude reads all A+/trap
comments, clusters recurring concepts ("strong prior leg", "shallow pullback holding the
20", "absorption on the low", "at the wall with room"), each becomes a candidate feature
we then compute mechanically. Validation loop: if features from his WORDS match features
the MODEL finds discriminating, the edge is real, not noise.

## Build — reuse mark_setups.py (extend, don't rebuild)
Already solved there: forward-reveal with auditable no-lookahead (`reveal_idx`), 5M bars
from ticks (verified), per-session volume profile POC/VAH/VAL, grade+note+setup+direction
fields.

**⭐ FOUNDATION ALREADY EXISTS (found 2026-07-20):** `scripts/brooks_bt_h2.py` +
`brooks_bt_core.py` already provide:
- `detect_h2_l2()` — Brooks two-legged A-B-C H2/L2 detector, signal-bar/entry/stop,
  **REGIME-FREE (EMA20 only, no Brooks engine)** — so it sidesteps the broken engine AND
  does not depend on the engine rebuild happening this week on a separate branch.
- `fill_trade()` — forward-outcome across 1R/2R/4R/EOD/BE2R/TR1 = the auto-outcome field.
- per-year base rates net of $5 MES = the mechanical baseline the FALSIFICATION GATE
  compares against.
The engine rebuild is orthogonal: when it lands it becomes an OPTIONAL backend context
feature, never a dependency of the label or detector.

Deltas to build (foundation now mostly reuse, not new):
1. **Wrap `detect_h2_l2` to place marks on the grading charts** + reuse `fill_trade` for the
   outcome field. Sanity-check its marks against Samir's eye on ~5 days before trusting.
2. Batch queue over 1270 days, batch-blind lock, random order, prior-day left-context.
3. Grade taxonomy A+/A/B/skip/trap + structured comment + decision-time capture.
4. Auto-outcome (forward path capture).
5. EOD hindsight pass, tagged.
6. No-dates render, save-after-each-chart (atomic append), resume.
7. Feature backend — offline from ticks, never blocks the grading UI.
8. Progress dashboard tab.

## Analysis (separate page, after labeling)
Descriptive statistics FIRST (A+ feature distributions vs trap) — denominators often jump
out with zero modeling. Then a small INTERPRETABLE model (logistic / shallow tree), few
features, heavy regularization, walk-forward. Output is UNDERSTANDING, not a black box.
Anything found = a hypothesis to forward-test on unseen days, never a conclusion.
Overfitting is the top risk (n≈100 A+ per setup); leakage (causal features only) is second.

## Progress dashboard (this tab = progress/metrics only)
% done · # graded · days done/remaining · avg time/chart · avg time/mark · grade
distribution · consistency score · projected hours-to-finish at current pace · coverage
heatmap by year/regime. Save after every chart so nothing is lost; resume from last.

## Setup types (one all the way through first)
Pilot: **H2/L2 second entries** — frequent (fast labeling), clean mechanical definition,
huge discretionary spread between great and awful. Then H1/L1, MTR, W1P, breakout+FT.

## Sequencing
Build tool for all 5yr → grade first ~150 random days → **edge gate** → grind rest only
if the gate passes.
