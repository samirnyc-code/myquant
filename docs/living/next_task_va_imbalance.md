# Next task — VA-imbalance side-by-side WFA run

*Read `PROJECT_CHARTER.md` then `handoff.md` first (the S22 research-findings block at
the top is the live context). Then do this.*

**Goal:** test one locked, structural hypothesis — *breakouts work in imbalance, not
balance* — by dropping every signal **inside** the prior session value area (keep only
`below VAL` + `above VAH`), and compare it **side-by-side** against the existing baseline.

## Why it's legit (discipline check — keep it honest)
Auction-market rationale: the value area is where ~70% of volume traded = balance/
acceptance. A breakout firing *inside* the VA fights rotation and tends to revert; a
breakout *outside* the VA is in imbalance/rejection with room to continue. Decided a
priori, structural, open-ended (keep the tails, drop the middle), one filter. The reason
must be the imbalance theory — NOT "the inside-VA bucket was red in the table."

## Baseline (already persisted — do NOT rerun, just load it)
`run_id = pin10_all_sl` — ALL CC setups, single-leg, **target pinned 1.0R**, 12m IS / 3m
OOS, slip 0.5/0.5, $3 r/t commission, 1 ES contract, stop_offset 1.
(Net $194,776 · 4,129 OOS trades · 96% target-driven · MAR95 4.0.)

## Filtered run to create (identical config + the VA filter)
- Signals: `saved_signals/ba_signals_mc.parquet` (all setups).
- VA filter via `regime_filter` (mirror the `wfa.py` regime-filter block):
  ```python
  tagged, bcols = regime_filter.tag_and_bucket(sig, bars)
  mask  = regime_filter.filter_mask(tagged, bcols, {"session_va": ["below", "above"]})
  kept  = set(tagged.loc[mask, "_rf_id"].tolist())
  sig2  = sig.copy(); sig2["_rf_id"] = np.arange(len(sig2))
  sig_filtered = sig2[sig2["_rf_id"].isin(kept)].drop(columns="_rf_id").copy()
  ```
  This keeps imbalance (`below`+`above`), drops `inside`.
- Bars: `data/bars/_continuous.parquet` (drop `Contract`, group by `DateTime.dt.date`).
  Ticks: `massive.load_continuous_ticks(d)` per signal-day.
- `base_params = dict(entry_slip=0.5, exit_slip=0.5, stop_offset=1, tick_value=12.5,
  contracts=1, contracts_t1=1, contracts_t2=1, commission=3.0, ratchet_r=0.0,
  pb_round="nearest")`
- Run: `wfa.run_wfa("pin10_all_va_sl", "ALL", sig_filtered, tbd, bbd, base_params,
  "singleleg", is_days=252, oos_days=63, n_param_sets=1, pin_t1=1.0)`
  — pin keeps R fixed; do NOT re-optimize R alongside the filter.
- The dtype fix + `eri_30` alignment are in (commit `8635c18`), so `tag_and_bucket`
  works headless.

## Side-by-side comparison to print
Load both runs from `results_store`; reuse the S22 deep-analysis pattern (per-setup
decomposition, target-vs-EOD split, year/fold concentration, Monte-Carlo DD95,
longest-underwater).

| Metric | Baseline `pin10_all_sl` | VA-filtered `pin10_all_va_sl` |
|---|---|---|
| OOS trades (and **% dropped**) | | |
| Net $ · **Expectancy $/trade** | | |
| Target game $ vs EOD $ | | |
| Win% · Median trade | | |
| % OOS windows green | | |
| Best-year share % | | |
| MAR vs Monte-Carlo DD95 (MAR95) | | |
| Longest underwater (days) | | |
| Median WFE % · Mean PROM | | |

## Acceptance test (the verdict criterion — be strict)
A WIN only if it raises **expectancy** at a **similar trade count** with **similar-or-
better OOS robustness across windows** — NOT if PF rises merely because it cut a large
fraction of trades. Flag **% dropped** prominently; if it guts trades below ~30/OOS
bucket, reject regardless of PF. Judge on OOS only; the filter is locked (no re-tuning
against the result).

## Notes
- No in-app side-by-side tool yet — do this headless. Building an in-app "Compare two
  runs" view (overlay equity + metrics diff) is a logged next-build, not required here.
- Any saved WFA run can be analysed headless straight from `data/wfa_store` — no
  screenshots needed; just the run_id.
