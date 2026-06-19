# Setup Decision Manual — from 5 raw setups to a validated bot rulebook

**Purpose:** a precise, repeatable sequence for turning the raw CC1–CC5 signals (5 years of tick + signal data) into an automated trading bot's configuration — some setups discarded, the survivors parameterized, a few possibly regime-gated.

**The pipeline is three separated stages — never mix them:**

> **Discovery → Validation → Portfolio Construction**

Keeping these apart is what eliminates accidental overfitting. Discovery *describes*; Validation *proves out-of-sample*; Portfolio *combines proven setups*.

**Golden rule:** optimize each setup *individually* with walk-forward analysis (WFA); use the Portfolio function only at the end for interaction and risk. Never choose parameters by eyeballing an in-sample sweep — that is curve-fitting.

**Test individually or portfolio?** → **Individually first** (Phases 1–4.5, one CC at a time). **Portfolio last** (Phase 5). The portfolio combines *already-locked* setups; it is not where parameters are chosen.

> Legend for tooling status on each step: **[have]** exists in the app · **[partial]** partly built · **[build]** to be built.

---

## Phase 0 — Sanity (Massive / Bar Analysis tabs)

- Confirm the 5yr ticks + signals are loaded and **CC1–CC5 appear as SignalType checkboxes**. **[have]**
  - *Why:* every later step filters by these. *Expect:* 5 selectable setups.
- Reconcile **one trade per setup against NinjaTrader** (`explain_trade.py`). **[have]**
  - *Why:* trust the engine before trusting its output. *Expect:* tick-exact match.

---

## Phase 1 — Per-setup raw edge (Bar Analysis, one CC at a time) — DISCOVERY

- Select **only CC1**, run the sim with neutral baseline params (e.g. single-leg ~1.0–1.5R, default stop). Repeat per CC. **[have]**
- Read: **trade count, expectancy ($/trade), PF, equity-curve shape, max DD**.
  - *Why:* a setup must show raw positive expectancy *before* any optimization — optimizing a non-edge just fits noise.
  - *Expect:* some CCs clearly positive, some flat/negative.
- **Discard rule:** drop/shelve any CC with negative raw expectancy or too few trades (~30/year floor, ~150 over 5yr).

---

## Phase 2 — Per-setup structure (descriptive only — don't filter yet) — DISCOVERY

- For each survivor read **Monthly Breakdown**, the **TOD/DOW table**, and the **Regime / Indicator Expectancy table** (ATR%ile, ADX%ile, VWAP-deviation, value-area location, ADX×ATR matrix). **[have]**
  - *Why:* confirm the edge is *stable and structural*, and note *which conditions* favor each setup (raw material for "when to use which").
  - *Expect:* a one-line profile per setup, e.g. "CC2: edge concentrated in high-ADX, weak in low-vol."
- **Watch trade counts (n):** thin buckets are noise. **Lock nothing here — this is a map, not a decision.**

---

## Phase 2.5 — Regime Stability across walk-forward segments — DISCOVERY  **[build]**

The danger in Phase 2: a finding like *"CC3 works great when ADX > 60th percentile"* may come **entirely from one year (e.g. 2025)**. Before you ever act on a regime, prove it *repeats*.

- For every promising regime bucket, split the 5yr history into walk-forward segments and recompute the bucket's expectancy per segment:

  | WF Segment | Expectancy |
  | ---------- | ---------- |
  | Segment 1  |            |
  | Segment 2  |            |
  | Segment 3  |            |
  | Segment 4  |            |

  - *Goal:* does the regime edge appear **repeatedly**, or did one giant year create it?
  - *Decision:* a regime that holds in **7 of 9 windows** is far more valuable than one that worked in **1 of 9**. Reject single-window edges.

---

## Phase 3 — Parameter selection via WFA (the core — WFA tab, per setup) — VALIDATION

- Run **WFA on CC1 alone** (IS 1yr / OOS 3mo). It sweeps params in-sample, picks by **PROM**, validates on untouched OOS, averages the top-N into a locked set. Repeat per surviving CC. **[have]**
- Read: **guardrails** (≥70% combos profitable, kurtosis ok, ≥30 IS trades); **Mean WFE**; **OOS PROM/PF/DD**; **IS-surface heatmap** (want a *plateau*, not a lone spike).

### Phase 3a — Walk-Forward Structure Robustness  **[partial — Window-Map heatmap]**

- Re-run each surviving CC under **multiple WF structures**, not just one:

  | IS  | OOS |
  | --- | --- |
  | 12m | 3m  |
  | 6m  | 3m  |
  | 6m  | 1m  |

  - *Objective:* **not** to optimize the WF structure — to confirm the edge **survives different validation structures**. A system that looks great under exactly one WF configuration is dangerous.
  - The **Window-Map heatmap** (`run_window_grid`) already sweeps IS×OOS pairs — use it here.

### Phase 3b — Expanded discard rules  **[partial — concentration metric to build]**

Reject a setup/parameter set if **any** of:

- **WFE < 50%**
- **OOS Profit % < 50%** (share of OOS windows that were profitable)
- **Parameter surface is a needle** (no plateau — spike-only optimum)
- **Top 10 trades > 25% of total profit** ← catches many fake edges  **[build]**

---

## Phase 3c — Profit Concentration & Time Under Water (per setup) — VALIDATION  **[build / partial]**

### Profit Concentration  **[build]**

- **Profit by year:**

  | Year | Profit |
  | ---- | ------ |
  | 2022 |        |
  | 2023 |        |
  | 2024 |        |
  | 2025 |        |
  | 2026 |        |

- **Best-year contribution** = Best Year Profit ÷ Total Profit.
  - If one year is **70–80%** of all profit, you likely have a **regime-dependency** problem, not a stable edge.

### Time Under Water  **[partial — Max TUW exists]**

- Measure **average recovery time** and **longest recovery time** (not just DD depth).
  - *Why:* many setups have *acceptable DD* but *unacceptable recovery time*. Max Time Underwater already exists in the WFA results; add **average** recovery. **[build: avg]**

---

## Phase 4 — Regime conditioning *(optional, only if justified)* — still VALIDATION

Strengthen the discipline: **for every proposed filter, document this BEFORE testing** (prevents indicator-fishing):

1. **Observation** — e.g. "Losing trades cluster in low ADX."
2. **Hypothesis** — e.g. "Setup requires directional participation."
3. **Market rationale** — e.g. "Signal captures continuation; needs trend to follow through."

Only then test. Lock the condition on a **design slice**, then **re-run WFA with the condition on**.

- Accept the gate **only if**: higher expectancy, **similar trade count**, similar OOS robustness, and improvement **across multiple windows**. A filter that boosts results while cutting ~70% of trades is *suspect* until independently validated.
  - *Expect:* maybe 1–2 setups gain a gate (e.g. "CC3 only when ADX%ile > 60"); most won't.

---

## Phase 4.5 — Monte Carlo (OOS trades only) — VALIDATION  **[build]**

Historical drawdown is almost always optimistic. Before sizing capital, stress it.

- For each setup, on its **OOS trades only**, generate **5,000–10,000 reshuffles/bootstraps** and report:
  - **95% DD**, **99% DD**
  - **Recovery Factor** distribution
  - **Probability of a losing year**
  - *Why:* this is what you size capital against — not the single realized path. The per-fold OOS trade logs are already persisted, so the data is ready.

---

## Phase 5 — Portfolio assembly (Portfolio tab) — PORTFOLIO CONSTRUCTION

- Load survivors **with their locked params**; build the combined equity curve. **[have]**
- Read: **combined DD vs sum-of-individual DD, total expectancy.**

### Regime Overlap — beyond simple correlation  **[build]**

Two setups can look diversified yet **fire simultaneously**. Track:

| CC Pair    | Correlation |
| ---------- | ----------- |
| CC1 vs CC2 |             |
| CC1 vs CC3 |             |

and — more important than correlation —

- **Concurrent Exposure %** — how often are both setups active at the same time?
  - *Why:* simultaneous firing concentrates risk even when return correlation looks low.

- **Decide here:** max concurrent positions, max daily loss, per-setup sizing.

---

## Phase 6 — Acceptance Report Card (the objective gate)  **[build]**

For each surviving setup, fill one row. This is your **objective acceptance checklist** — accept/size/reject from the numbers, not a feeling.

| Metric                      | Value |
| --------------------------- | ----- |
| Raw Expectancy              |       |
| OOS Expectancy              |       |
| WFE                         |       |
| OOS Profit %                |       |
| Robustness (windows passed) |       |
| Monte Carlo DD95            |       |
| Profit Concentration        |       |
| Regime Dependency           |       |
| Time Under Water            |       |

---

## Phase 7 — Bot rulebook (the deliverable)

- Per surviving setup: **SignalType, locked params** (T1 / T2 / PB / stop / contracts), any **regime gate**, session/DoW constraints.
- Global: **max concurrent, max daily loss, position sizing** (prefer **regime-based sizing** over hard trade removal).
  - *Why:* every line traces back to OOS-validated evidence.

---

## End state

2–4 surviving setups, each with a WFA-locked parameter set that survived multiple WF structures and Monte Carlo, maybe 1–2 with a validated regime/session gate, combined and risk-bounded in the portfolio. **That is your bot's configuration.**

---

### Discipline reminders (taped to the monitor)

- **Discovery → Validation → Portfolio.** Never mix the stages.
- One hypothesis at a time; document Observation → Hypothesis → Rationale **before** testing.
- Describe → hypothesize → lock on a design slice → validate OOS across **multiple windows**. Never read the OOS curve and design backward from it.
- **Regime tables find where edge exists — they are not filters and not optimization.** "High ADX bucket = profitable" must NOT become `ADX > 63.7` in the strategy. That is how edges die. Treat regime study as a *diagnostic*, not a signal generator.
- Prefer **position sizing** by regime over **removing** trades; removal that guts trade count is suspect.
- An edge that lives in **one window / one year / ten trades** is not an edge.
- Historical DD is optimistic — size against **Monte Carlo DD95/DD99**, not the realized path.

---

### Tooling status summary

| Capability | Status |
| --- | --- |
| Per-setup sim, sweeps, equity/DD | have |
| TOD/DOW + Regime/Indicator expectancy tables | have (today) |
| WFA: IS sweep → PROM → OOS, guardrails, IS-surface heatmap | have |
| WF-structure robustness (IS×OOS Window-Map heatmap) | have (`run_window_grid`) |
| Max Time Underwater, Windsorized WFE | have (S18) |
| Regime stability across WF segments | **build** |
| Top-10-trade profit concentration; profit-by-year | **build** |
| Average recovery time | **build** (max already exists) |
| Monte Carlo on OOS trades (DD95/99, recovery, P(losing year)) | **build** |
| Portfolio regime overlap + concurrent-exposure % | **build** |
| Acceptance report card (auto-aggregated) | **build** |
