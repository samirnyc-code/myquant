# Build spec — 2-D Stop × Target sweep (single-leg)

**Audience:** the LLM building the research engine.
**Status:** ✅ BUILT (Session 21) — `_run_stop_target_sweep` + `_show_stop_target_sweep` in
`bar_analysis.py`, wired after the Stop Multiplier Sweep. Descriptive tool (Pardo-safe), NOT a
WFA input. *Remaining: verify the edge cross-checks in §1 in-app (1.00× col == R sweep;
current-target row == stop sweep).*
**File to edit:** `bar_analysis.py`. **Tab:** Bar Analysis → new expander next to the
existing "🔍 Optimal R Sweep" and "🔍 Stop Multiplier Sweep".

Read `docs/living/handoff.md` first. Honor the carry-forward rules: no commit
without explicit OK, all sims behind a Run button, Edit/Write for source only.

---

## 1. Why this exists (read before coding)

We already have two **1-D** sweeps:

- **Optimal R Sweep** (`_run_r_sweep`) — holds the stop at baseline (1.00×), sweeps
  `target_r` (the reward target in R). Produces the first screenshot table.
- **Stop Multiplier Sweep** (`_run_stop_mult_sweep` + `_apply_stop_mult`) — holds
  `target_r` fixed, scales the stop distance by a multiplier. Produces the second.

The catch that makes a 2-D sweep necessary: **R is defined as a multiple of the
stop distance.** So when the stop sweep changes the stop, it *also* moves the
absolute target (target distance = `stop_mult × baseline_stop × target_r`). The
two parameters are **not independent in price terms** — they interact. Picking the
best stop at a fixed target, then the best target at a fixed stop, can land off the
true joint optimum. The 2-D sweep crosses both axes so we read the real surface.

**Built-in cross-check (use it to validate):**
- The column at `stop_mult = 1.00×` must reproduce the 1-D **R sweep** exactly.
- The row at the current `target_r` must reproduce the 1-D **stop sweep** exactly.
If either edge disagrees with the existing 1-D function, the grid wiring is wrong.

---

## 2. Compute function

Add next to `_run_t1t2_sweep` (it is the closest existing 2-D template — copy its
structure). Reuse the existing helpers; **do not** reimplement simulation.

```python
def _run_stop_target_sweep(
    signals: pd.DataFrame, ticks_by_date: dict,
    entry_slip: float, exit_slip: float, stop_offset: int,
    tick_value: float, contracts: int, commission: float,
    bars_by_date: dict | None = None,
    multileg: bool = False, t1_r: float = 1.0,
    t1_action: str = "exit", contracts_t1: int = 1, contracts_t2: int = 1,
    stop_mults: list | None = None,
    target_rs:  list | None = None,
    first_trade_only: bool = False, first_2_filled_only: bool = False,
    progress_cb=None,
) -> pd.DataFrame:
    """2-D grid sweep over (stop_mult × target_r), single-leg by default.

    Reuses _apply_stop_mult (stop scaling), simulate_trades + _apply_day_trade_filters
    + compute_summary (exact engine path), and _win_breakdown (Tgt%/EOD decomposition).
    """
    if stop_mults is None:
        stop_mults = _STOP_MULTS
    if target_rs is None:
        target_rs = [round(r * 0.25, 2) for r in range(2, 21)]   # 0.50 – 5.00

    rows = []
    total = len(stop_mults) * len(target_rs)
    i = 0
    for mult in stop_mults:
        sigs = _apply_stop_mult(signals, mult)          # scale stop ONCE per column
        for tr in target_rs:
            i += 1
            if progress_cb:
                progress_cb(i / total, f"Stop {mult:.2f}× · T {tr:.2f}R ({i}/{total})")
            res = simulate_trades(
                sigs, ticks_by_date, tr,
                entry_slip, exit_slip, stop_offset,
                tick_value, contracts, commission,
                bars_by_date=bars_by_date,
                multileg=multileg, t1_r=t1_r, t1_action=t1_action,
                contracts_t1=contracts_t1, contracts_t2=contracts_t2,
            )
            res = _apply_day_trade_filters(res, first_trade_only, first_2_filled_only)
            s = compute_summary(res, commission, contracts=contracts, is_multileg=multileg,
                                t1_action=t1_action,
                                contracts_t1=contracts_t1, contracts_t2=contracts_t2)
            if not s or s["n_trades"] == 0:
                continue
            _dd_abs = abs(s["max_dd"]) if s["max_dd"] != 0 else None
            tgt_pct, eodw_pct, eodw_r = _win_breakdown(res)
            rows.append({
                "Stop Mult": f"{mult:.2f}×",
                "R":         tr,
                "Win %":     round(s["win_pct"], 1),
                "Tgt %":     tgt_pct,
                "EOD Win %": eodw_pct,
                "PF":        round(s["pf"], 2) if s["pf"] < 99 else 99.9,
                "Net PnL":   round(s["net_total"], 0),
                "DD $":      round(_dd_abs, 0) if _dd_abs else 0.0,
                "PnL/DD":    round(s["net_total"] / _dd_abs, 2) if _dd_abs else 0.0,
                "Exp $":     round(s["exp_dollar"], 0),
                "Trades":    int(s["n_trades"]),
            })
    return pd.DataFrame(rows)
```

**Rules to follow exactly:**
- Call `_apply_stop_mult(signals, mult)` **once per stop column**, then loop targets
  inside — never re-scale per target (the stop is target-independent).
- Use `simulate_trades` (the engine), NOT a fast/vectorized re-implementation. Stop
  scaling changes signal geometry; there is no precompute shortcut here, and we
  want byte-identical-to-engine numbers since this can inform a config choice.
- Keep `target_rs` start at 0.50R (index `range(2, …)`, i.e. `2×0.25`) to match the
  1-D R sweep's lower bound and its cross-check.
- `Trades` column is added so the user can see thin cells (overfitting risk).

---

## 3. UI (new expander)

Copy the layout of the T1×T2 expander (`bar_analysis.py` ~1791–1851). Place the new
expander immediately after the Stop Multiplier Sweep expander.

```python
def _show_stop_target_sweep(signals, ticks_by_date, entry_slip, exit_slip, stop_offset,
                            tick_value, contracts, commission, bars_by_date=None,
                            multileg=False, t1_r=1.0, t1_action="exit",
                            contracts_t1=1, contracts_t2=1,
                            first_trade_only=False, first_2_filled_only=False):
    _METRIC_COLS = ["Win %", "PF", "Net PnL", "DD $", "PnL/DD", "Exp $"]
    _THRESHOLDS  = {"PF": 1.0, "Net PnL": 0, "PnL/DD": 0, "Exp $": 0}
    with st.expander("🔍 2-D Stop × Target Sweep", expanded=False):
        st.caption(
            "Crosses stop size (× baseline stop) with target R. Because R is measured "
            "in stop units, these two interact — the joint optimum can differ from "
            "chaining the two 1-D sweeps. Read the surface for a stable PLATEAU, not a "
            "lone peak. Descriptive only: this never feeds the WFA optimizer."
        )
```

**Controls (3 columns of range pickers):**
- **Stop range** — two `select_slider`s over `_STOP_MULTS` (default 0.50× … 1.25×;
  the screenshots show the action lives ≤1.25× — wider stops blow up DD). Slice
  `_STOP_MULTS` between min/max like the existing stop sweep does.
- **Target range** — `Min R` / `Max R` `number_input`s, `step=0.25`, `min=0.50`,
  default 0.50 … 3.00. Build `target_rs = [round(r*0.25,2) for r in range(...)]`.
- Show a combo count caption: `len(stop_mults) * len(target_rs)` + the signal count
  (mirror the scale-in expander's `_si_sig_count` logic for the filter-aware count).
  **Warn if combos > ~200** (each combo is a full engine sim; this is the slow path).

**Run button** — `key="ba_run_st_sweep"`. Wrap in `st.spinner` + a `st.progress`
bar driven by `progress_cb` (same pattern as `_show_stop_sweep`). Persist the result
to `st.session_state["ba_st_sweep_df"]` so reruns don't recompute.

**Outputs (after a result exists):**

1. **Heatmap** — metric `selectbox` (`["PnL/DD", "Net PnL", "PF", "Exp $", "Win %"]`;
   default **PnL/DD** — this is the risk-adjusted surface we actually choose on).
   Pivot `index="Stop Mult"`, `columns="R"`, `values=metric`; `colorscale="RdYlGn"`;
   `xaxis_title="Target (R)"`, `yaxis_title="Stop Mult"`. Copy the T1×T2 heatmap
   block verbatim and swap the axis fields.
2. **Ranked table** — top 20 by the chosen metric, `_apply_best_green` for per-column
   best, `reset_index(+1)`. Use the same `_fmt` map as the other sweeps plus
   `"R": "{:.2f}"`, `"Tgt %": "{:.1f}"`, `"EOD Win %": "{:.1f}"`, `"Trades": "{:.0f}"`.
3. **Plateau caption (REQUIRED, this is the anti-overfit guardrail):** after ranking,
   compute the best cell by `PnL/DD`, then report how many of its **8 grid neighbors**
   are within 10% of it. Print e.g. `"Best PnL/DD 7.6 at 0.75×/1.50R — 6/8 neighbors
   within 10% (stable plateau)"` vs `"… 1/8 neighbors within 10% (isolated peak —
   treat as overfit)"`. This is the single most important output: it tells the user
   whether the winner is a robust region or a curve-fit spike.

Wire the call into the Bar Analysis render flow right after `_show_stop_sweep(...)`,
passing the same args it receives (note: this function does **not** take `target_r` —
target is an axis here, not a fixed input).

---

## 4. Discipline rails (non-negotiable — per handoff + keep_in_check)

- **Descriptive only.** This tool informs a *manual, locked* config decision. It must
  **never** be wired into the WFA IS optimization grid. Co-sweeping stop×target inside
  WFA folds = dimensionality blowup + curve-fit + the no-feedback violation. WFA still
  optimizes only T1/T2/PB per fold against PROM.
- **Choose plateaus, not peaks.** The neighbor-stability caption exists for this. A
  cell that beats its neighbors by a wide margin is almost always in-sample luck.
- **Watch `Trades` and `Tgt %`.** A high-R / wide-stop cell whose `Tgt %` has collapsed
  (target rarely hit; profit is mostly EOD closes) is not really a "stop/target" config
  — flag it. Thin `Trades` cells are unreliable regardless of metric.
- **Validate before trusting** — confirm the chosen cell holds out-of-sample / across
  WFA folds, not just on this aggregate surface.
- Numbers must be **engine-exact**: this uses `simulate_trades` directly, so the 1.00×
  column == 1-D R sweep and the current-target row == 1-D stop sweep. Verify both edges
  match before considering the feature done.

---

## 5. Definition of done

- [ ] `_run_stop_target_sweep` added; reuses `_apply_stop_mult`, `simulate_trades`,
      `_apply_day_trade_filters`, `compute_summary`, `_win_breakdown`.
- [ ] `_show_stop_target_sweep` expander added after the stop-sweep expander, behind a
      Run button, with progress bar + session-state caching.
- [ ] Heatmap (default PnL/DD) + ranked top-20 + neighbor-stability plateau caption.
- [ ] Combo-count + signal-count caption; warning when combos > ~200.
- [ ] Edge cross-check verified: 1.00× column == R sweep; current-target row == stop sweep.
- [ ] No path from this tool into `wfa.py`. App runs; user has clicked Run. No commit
      until the user OKs it.
```
