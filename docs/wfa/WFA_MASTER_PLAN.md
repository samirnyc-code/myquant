# WFA Master Plan
*Captured from June 7, 2026 session — do not lose this*

---

## 1. The Big Picture

Build a **Walk-Forward Analysis (WFA)** framework for myquant that:
- Uses 15 years of 5M OHLC bar data + MCSignals (2010–2025) in CSV
- Slices IS/OOS periods cleanly inside the app (upload once, never again)
- Runs rolling WFA: 1yr IS / 3mo OOS, re-optimize every 3 months
- Saves all IS and OOS run results for review
- Follows Kaufman/Pardo guardrails strictly — many alerts and warnings built in
- Is **maximally modular** — each piece independently testable and replaceable

---

## 2. Guiding Principles (from the Books)

These are non-negotiable guardrails to build INTO the app:

### Kaufman Guide — Robustness Rules
- **≥70% of all parameter combinations must be profitable** → if below, show red alert, block WFA run
- **Kurtosis ≤ 6** on the optimization surface → warn if higher (over-fit signal)
- **Parameter spacing must be multiplicative** (×1.25 or ×1.5 per step), not linear → enforce in sweep UI
- **Trade the average, not the peak** → auto-calculate and display the ≥3 equally-weighted parameter set average; block single-best-pick
- **No feedback rule** → once OOS data is used, the result is FINAL, locked. No re-run on same OOS period ever. Enforce with a database flag or hash.
- **Forward risk = 2× the IS risk estimate** → always display expected live risk = 2× backtest risk; never let user misread IS results as live expectation
- **IR > 3.0 = flag as likely error** → alert if IS Information Ratio exceeds 3.0 (look-ahead bias check)
- **Price shock filter** → trades where daily range ≥ 2.5× 20-bar avg range should be flagged; forward expectation on these is only ~50%
- **Minimum sample** → 400 trades for 5% sample error; warn if fewer than 100, block if fewer than 30
- **Volatility filter** → annualized vol >45–50% → skip short-term entries; app should optionally enforce this

### Pardo / General
- **No post-hoc tuning** → parameters chosen in IS cannot be modified after seeing OOS
- **Re-optimization is calendar-driven, NOT performance-driven** → every 3 months regardless of live performance
- **The sweep is for robustness ONLY** → never pick the single best parameter to trade; never use to validate the strategy

---

## 3. Data Architecture (settled decisions)

### What We Have / Will Have
| Data Type | Format | Period |
|-----------|--------|--------|
| 5M OHLC bar data | CSV files | 2010–2025 (~15 years) |
| MCSignals (entry/stop signals) | CSV files | 2010–2025 |
| Indicator data (future) | TBD CSV | 2010–2025 |
| Indicators: EMA(20), VWAP ± deviations, VAH/VAL, Prev Day HLC, Prev Week/Month/Quarter HLC | TBD | TBD |

### Upload Strategy
- Upload ONCE at session start (or point to disk path)
- App slices into IS/OOS periods in memory — no re-upload per run
- Data slice = `df[date_from:date_to]` — trivial with a DatetimeIndex

### File Structure (proposed)
```
data/
  raw/
    ohlc_5m_2010_2025.csv          ← single big file or yearly chunks
    mc_signals_2010_2025.csv
  processed/                        ← pre-merged, index-sorted, cached
    merged_2010_2025.parquet        ← optional: pre-process once for speed
```

---

## 4. WFA Methodology

### Rolling Window Parameters
| Parameter | Value |
|-----------|-------|
| IS window | 1 year (252 trading days) |
| OOS window | 3 months (~63 trading days) |
| Step size | 3 months (OOS length = step) |
| Total folds | ~56 folds across 15 years |
| Re-optimize | Every 3 months (calendar, not performance driven) |
| Anchored vs Rolling | **Rolling** (IS window slides, does not expand) |

### Per-Fold Flow
```
Fold N:
  1. Slice IS period (1yr)
  2. Run parameter sweep on IS data
     → check robustness: ≥70% profitable, kurtosis ≤6
     → select ≥3 param sets (trade the average, not the peak)
  3. Lock parameters → mark OOS period as "used" (no-feedback flag)
  4. Run OOS simulation with locked params
  5. Save IS + OOS results to results store
  6. Advance by 3 months → next fold
```

### When to Re-Optimize
- **Always at the calendar interval** (every 3 months)
- **Never** because live performance is bad (that's feedback)
- **Exception**: if the strategy has a catastrophic draw where position sizing would require suspension, can pause — but params stay locked until next calendar date

---

## 5. Indicators and Trade Location Filtering

### The "Trade Location" Problem
Not all signals are equal. A long signal at LOY (Low of Yesterday) is fundamentally different from one that trades directly into HOY. This is the **trade location** concept.

### Proposed Indicators (for filtering, not optimization)
| Indicator | Use Case |
|-----------|----------|
| EMA(20) | Trend filter — skip counter-trend signals |
| VWAP + deviations | Mean-reversion context |
| VAH / VAL (Value Area) | Market profile context |
| Prev Day H/L/C | Key reference levels |
| Prev Week / Month / Quarter H/L/C | Larger structure levels |

### Where Does Filtering Live?

**Open question — 3 possible architectures:**

**Option A: Pre-WFA filter tab**
- Separate tab in app: "Signal Filter" or "Pre-WFA"
- User marks which signals to include/exclude based on indicator context
- Filtered signal list is then fed into WFA
- Pro: clean separation, indicator context is explicit
- Con: manual — user must tag signals

**Option B: Inside WFA as a parameter**
- Indicator filters become WFA parameters (IS-optimized)
- Pro: quantified, systematic
- Con: adds optimization dimensions → risks over-fitting → Kaufman says add rules only if they lift ALL cells of the optimization surface

**Option C: Inside current Bar Analysis tab**
- Filter toggle per signal type / location
- Pro: already exists (CC3/CC4 filters, day-of-week, event filters)
- Con: mixing single-day analysis with WFA context

**Recommendation**: Start with Option A (pre-WFA filter). Keep indicator context as a BINARY filter (include/exclude), not an optimized parameter. Kaufman rule: a new rule is only valid if it lifts the average of ALL parameter combinations, not just the best.

---

## 6. Results Storage and Display

### What to Save per Fold
```
fold_results = {
  "fold_id":        int,
  "is_start":       date,
  "is_end":         date,
  "oos_start":      date,
  "oos_end":        date,
  "params_used":    dict,          # the ≥3 param sets and their weights
  "is_summary":     dict,          # full compute_summary output for IS
  "oos_summary":    dict,          # full compute_summary output for OOS
  "is_trades":      DataFrame,     # full trade log for IS
  "oos_trades":     DataFrame,     # full trade log for OOS
  "is_win_pct":     float,
  "oos_win_pct":    float,
  "is_net_pnl":     float,
  "oos_net_pnl":    float,
  "is_ir":          float,
  "oos_ir":         float,
  "ir_decay":       float,         # oos_ir / is_ir — should be ~0.5
  "robustness_pct": float,         # % of param combos profitable
  "kurtosis":       float,
  "no_feedback_locked": bool,      # OOS data used and locked
}
```

### Key Displays
1. **Fold summary table** — one row per fold: IS PnL, OOS PnL, IS win%, OOS win%, IR decay
2. **Equity curve** — IS + OOS stitched together across all folds (the "real" equity curve)
3. **IR decay chart** — IS IR vs OOS IR per fold (should trend ~0.5 ratio)
4. **Robustness heatmap** — per fold: was the ≥70% threshold met?
5. **Parameter stability chart** — how much do optimal params shift fold-to-fold?
6. **Combined OOS only equity** — the forward curve (what would have happened in live)

---

## 7. Modularity Design — Proposed Script Structure

### Option A: Single expanded app.py (not recommended)
Everything in one file — hard to debug, hard to test independently.

### Option B: Separate WFA script with shared simulation engine (recommended)
```
myquant/
  app.py                    ← main Streamlit entry point
  bar_analysis.py           ← existing analysis tab (already exists)
  wfa.py                    ← new: WFA tab / page (to build)
  simulation_engine.py      ← NEW: extract simulate_trades + helpers here
                               Both bar_analysis and wfa import from this
  data_loader.py            ← already exists
  signal_filters.py         ← already exists (apply_signal_filters)
  results_store.py          ← NEW: save/load fold results to disk (parquet/json)
  indicator_engine.py       ← NEW (future): compute indicator columns from bars
  config.py                 ← NEW: constants, instrument defs, WFA params
```

### Why This Matters
- `simulation_engine.py` is the core. Both Bar Analysis and WFA call the same `simulate_trades()` — no code duplication, no divergence.
- `results_store.py` handles persistence — WFA results saved to disk between sessions.
- `wfa.py` is the new tab — imports engine, calls it per fold, stores results.
- **Modular = each piece testable independently** (critical for 15-year datasets where bugs are expensive).

---

## 8. 3-Leg Trade Structure (BUILT in bar_analysis.py — June 7, 2026)

### Design (locked)
| Leg | Entry | When |
|-----|-------|------|
| E1 | Signal price (stop entry) | Always — initial entry |
| E2 | PB1 level (limit order) | If price pulls back to PB1 after E1 fills |
| E3 | PB2 level (limit order) | If price pulls back to PB2 after E2 fills |

### Trade Types (by what actually fills)
- **Rocket** — only E1 fills (never pulls back to PB1)
- **E1+PB1** — E1 and E2 fill
- **E1+PB1+PB2** — all three fill

### Key Formula Decisions
- **Original R** = E1 entry − E1 stop (stable, computed at signal time, never changes)
- **PB level formula (long)**: `PB1 = E1_entry − pb1_r × original_R + pb1_ticks × tick_size`
  - `pb1_r` = R-distance back (0.25, 0.50, 0.75, 1.00, etc.)
  - `pb1_ticks` = fine-tune offset (+= shallower, −= deeper)
  - Hard floor: PB must be strictly above actual stop
- **T1 / T2** always based on E1 entry + original R (stable reference)
- **Blended entry** = weighted average of all fills — used ONLY for BE stop calculation

### Stop Ratchet (all modes)
- Trigger: price moves `ratchet_trigger_r × original_R` from blended entry
- Destination options: BE (blended entry) | E1 entry | Lock-in R (entry + lock_r × R)
- Fires ONCE — stop stays at new level
- Sweeps always run WITHOUT ratchet (keep robustness analysis clean)
- Ratchet is a live-trading safeguard, not an optimization parameter

### Sweeps Available
| Sweep | 1-Leg | 2-Leg | 3-Leg |
|-------|-------|-------|-------|
| Optimal R (1D) | ✓ | — | — |
| T1×T2 (2D heatmap) | — | ✓ | — |
| PB1×PB2 (2D heatmap) | — | — | ✓ |
| Stop Mult (all modes) | ✓ | ✓ | ✓ |

---

## 9. Open Questions to Answer Before Building WFA

These MUST be decided before writing a line of WFA code:

### Q1: Single file vs multi-file?
Leaning toward multi-file (separate `simulation_engine.py`, `wfa.py`, `results_store.py`). User preference?

### Q2: Results storage format?
- **Parquet** — fast, binary, column-oriented (best for large trade logs)
- **SQLite** — queryable, single file, human-inspectable
- **JSON + CSV** — human-readable but slow for 15 years
Recommendation: **SQLite for fold metadata + Parquet for trade logs**

### Q3: Indicator data — when and how?
- Upload alongside OHLC? Or compute on-the-fly from OHLC?
- VWAP and session-level stats (VAH/VAL) need intraday bars → computable from 5M bars
- Daily/Weekly/Monthly reference prices need daily OHLC → separate upload or derive from 5M
- Decision: compute from 5M bars where possible, upload daily separately

### Q4: Signal filter timing — pre-WFA or in-WFA?
- Does indicator filtering happen BEFORE the WFA fold slicing (fixed filter), or IS it a parameter tested in the IS sweep?
- **Recommendation**: Fixed pre-filter, not an IS parameter (avoids extra optimization dimension)

### Q5: Parameter space for WFA sweep — what and how many dimensions?
- Current params: T1 (R), T2 (R), PB1 (R), PB2 (R), Stop mult
- Kaufman: multiplicative spacing, not linear
- How many dimensions to sweep simultaneously? More dims = more combos = slower
- **Recommendation**: Max 2–3 dimensions per sweep; hold others fixed

### Q6: Multi-param set trading — how to average?
- Kaufman says trade ≥3 equally-weighted param sets
- In practice: does each param set get allocated equal capital, or do we run the simulation with the average of the param values?
- **Recommendation**: Average the parameter VALUES (not the capital) → single simulation with blended params

### Q7: What triggers a "failed" WFA fold?
- OOS drawdown > X%? → pause live trading flag?
- OOS win rate < 40%?
- IR decay > 75%?
- Need explicit criteria before building

### Q8: How to handle the regime/market structure question?
- ES has lower Efficiency Ratio than NQ → fade-the-breakout (pullback) favored
- But regime changes — sometimes trending, sometimes ranging
- Does the WFA automatically detect this? Or is it a manual override?
- This is a future problem — leave for phase 2

---

## 10. Implementation Roadmap

### Phase 0 — Complete (or very close)
- [x] Bar Analysis tab with single-leg, 2-leg, 3-leg trade simulation
- [x] Stop ratchet for all trade modes
- [x] PB1×PB2 sweep (3-leg)
- [x] T1×T2 sweep (2-leg), Stop mult sweep (all modes)
- [x] Monthly breakdown, unfilled signals, per-day chart
- [x] Library tenets from Kaufman Guide Ch.4/8/10/11/15

### Phase 1 — Before WFA build starts (next week)
- [ ] User uploads sample data (OHLC 5M + MCSignals) → we verify format
- [ ] Decide on file architecture (single vs multi-file)
- [ ] Decide on results storage format
- [ ] Answer the 8 open questions above
- [ ] Write a short spec doc: WFA parameter space, fold methodology, output format
- [ ] Test 3-leg trade simulation in the running Streamlit app (untested as of June 7)
- [ ] Test no-auto-load changes (app.py, validation.py) — untested as of June 7

### Phase 2 — WFA Core Build
- [ ] `simulation_engine.py` — extract `simulate_trades()` and all helpers from `bar_analysis.py`
- [ ] `results_store.py` — save/load fold results
- [ ] `wfa.py` — WFA tab: data slicing, fold loop, robustness checks, results display
- [ ] Fold summary table + combined OOS equity curve
- [ ] Robustness guardrails (≥70% threshold, kurtosis check, IR >3.0 flag)
- [ ] No-feedback enforcement (lock OOS after first use)

### Phase 3 — Indicator Integration
- [ ] `indicator_engine.py` — compute VWAP, VAH/VAL, EMA(20) from 5M bars
- [ ] Pre-WFA signal filter tab — indicator-based include/exclude
- [ ] Daily reference prices (prev day/week/month H/L/C)

### Phase 4 — Trade Location Analysis
- [ ] Signal tagging by market context (at LOY, at HOY, in middle of range, etc.)
- [ ] Statistical analysis of performance by location
- [ ] Feed into pre-filter decisions

---

## 11. Kaufman Rules Checklist — Build Into UI

Every WFA run should produce these warnings/alerts automatically:

```
[ ] ≥70% of IS parameter combos profitable?          → BLOCK if failed
[ ] Kurtosis ≤ 6 on optimization surface?            → WARN if failed
[ ] Minimum 100 trades in IS period?                 → WARN if <100, BLOCK if <30
[ ] Trading ≥3 parameter sets (not just the best)?   → ENFORCE (no single-best option)
[ ] IS Information Ratio ≤ 3.0?                      → ALERT if exceeded
[ ] No OOS data used more than once?                 → ENFORCE via lock flag
[ ] Forward risk displayed as 2× IS risk?            → ALWAYS show this, can't turn off
[ ] Price shock days identified and flagged?          → SHOW in trade log
[ ] Volatility filter applied when vol >45%?         → OFFER toggle, recommend ON
[ ] Parameter spacing is multiplicative?             → ENFORCE in sweep UI
```

---

## 12. What Makes This Different from a Typical Backtest

1. **No curve fitting** — parameters chosen in IS, tested in OOS, results accepted as-is
2. **No cherry-picking** — trade the average of ≥3 param sets, not the single best
3. **No data snooping** — once OOS is seen, it's locked forever
4. **Regime awareness** — ES ≠ NQ in ER terms; what works here is a pullback/fade approach, confirmed by Kaufman's ER analysis
5. **Live expectation calibrated** — always show "expect 2× IS risk in live"; always show IR will likely halve IS→OOS→live
6. **Built-in humility** — the app should make it HARD to over-optimize, not easy

---

*Created June 7, 2026 from session where: (1) Kaufman Guide chapters 4/8/10/11/15 were read and added to library_tenets.md, (2) 3-leg trade simulation was fully built in bar_analysis.py, (3) WFA architecture was discussed at high level.*

*Next session: user uploads sample data → verify format → answer open questions → begin phase 1.*
