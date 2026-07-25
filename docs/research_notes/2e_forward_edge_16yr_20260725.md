# The 2E Edge, Taken Apart: A 16-Year Out-of-Sample Reckoning

**Author:** quant desk · **Date:** 2026-07-25 · **Branch:** `regime/indep`
**Mandate:** take apart everything at our disposal and find an edge we can trade forward.

---

## TL;DR (the honest verdict)

- The flagship "REGIME-2E" book (**+$93.7k / PF 1.44, green every year**) is **materially inflated
  by regime-fit and hindsight.** It was validated only on 2021–26 — a single favorable regime.
- A **clean-room walk-forward from 2010** (re-optimizing gap/stop/window/side each year, zero 2021
  priors) delivers **PF 1.10, +$16k** over 2012–26. The ~0.11 PF vs the frozen 1.21 is the
  **curve-fit premium.**
- **BUT a real, causal, non-curve-fit edge does exist** underneath: **LONG-only second-entry, filtered
  to trend-efficient days (ER10-top).** It is **net-positive in all four 4-year blocks 2010–2026**
  (PF 1.28–1.46), robust to parameters, and long-bias is independently confirmed by the WFA (long
  picked 14/15 years).
- **Honest scale:** **PF 1.32, meanR +0.155, ~$2,553/yr per ES**, realized maxDD −$13.9k, crash-
  vulnerable (2020 −$11.9k). ~2.7%/yr on ~$96k/ES capital. **Real but modest and low-frequency
  (32 trades/yr).** Not a standalone money machine on one instrument.
- **Everything else we hoped for is dead or fake:** the short side is regime-dependent; **gamma-
  regime conditioning is LOOK-AHEAD** (dies causally); VIX conditioning is 2024-driven; a mean-
  reversion complement does not exist (choppy days have no edge either way).

---

## Data & method

- **16 years of ES**: Databento `ohlcv-1m` 2010-06→2026-07 ($0.48 pull), panama front-month
  (`databento_build_continuous_1m.py`), seam-checked corr **0.99987** vs our NT series on the
  2021–26 overlap. Bar geometry matches NT 5M to **0.0000 pt median**.
- **Tick-proxy** (1-min → pseudo-ticks) validated on 2021–26: **99.89% regime-label agreement**,
  book PF 1.35 vs real-tick 1.45 (mildly pessimistic = safe). Caveat: proxy unvalidated below
  ADR 25 (no low-vol days exist in 2021–26 to test against).
- Every result reported **in scale-free R** and **per 4-year block** (block-robust = real, not a
  vol-scaling or single-era artifact). Costs $5 RT + 1t slip. Look-ahead audited throughout.

## The reckoning, step by step

1. **Frozen book, true OOS.** On 2010–2020 (never seen) the frozen three-book is **PF 0.96,
   −$6.4k**; on 2021+ **PF 1.38, +$90.4k**. The "explosion at 2021" is ~4× exaggerated by dollar-
   vol scaling (ES ADR tripled) — in R the ratio is 3:1, not 14:1 — but a real edge-shift remains.
2. **The short side is the killer.** Pre-2021 longs PF 1.03 (breakeven), shorts PF 0.91 (−$8.6k).
   With-trend shorts need a real downtrend; the 2010–20 secular bull starved them.
3. **Costs + curve-fit, not just regime.** Gross pre-2021 is PF 1.07 (small but positive); costs
   sink it. Clean-room WFA = PF 1.10 (the honest edge) vs frozen 1.21 (hindsight premium).
4. **The real edge = LONG + ER10-top.** Net-positive every 4-yr block; PF 1.32 full. ER10 filter
   audited **causal** (prior-day trend efficiency, expanding-median threshold — NOT the S83
   intraday-entry-bar look-ahead bug).

## Dead ends (recorded so we don't re-run them)

| Idea | Result | Why it failed |
|---|---|---|
| With-trend shorts | regime-dependent (0.91 pre / 1.34 post) | need sustained downtrends |
| **Gamma-regime conditioning** | **LOOK-AHEAD** — POS 1.66 → 1.27 causal (≈ NEG 1.20) | MQ gamma[D] uses D's own EOD chain; same-day sign proxies the outcome |
| VIX-level conditioning | 2024-driven, not stable | modern low-VIX edge is ~all 2024 |
| Mean-reversion / fade complement | dead (PF 0.87–0.94 everywhere) | choppy days have no edge either direction |
| Vol-regime day-filter on the book | no improvement (uw% stuck 86–90%) | paying days not identifiable ex-ante |

## Structural / forward context

- The dead 2010–2017 era was **extreme low vol (VIX med 10.8–15.3, ES range 0.35–0.67%) AND
  pre-0DTE.** Daily 0DTE (2022+) and the retail-options boom (2020+) are structural and sticky.
- The edge does **not** require high VIX (2024 was low-VIX and strong). A full return to the
  2010–17 dead regime needs both a VIX collapse *and* 0DTE disappearing — unlikely.
- **The edge is a modest long-biased intraday-continuation edge, best in orderly conditions.**

## Forward recommendation

1. **Do NOT trade the +$93.7k/1.44 frozen book as if durable.** Trade the **LONG-2E + ER10** spec,
   sized honestly (~$96k/ES, expect ~2.7%/yr, −$14k DD, crash-year tail).
2. **To make it a real book, SCALE it multi-instrument** (NQ/RTY/YM/CL) — same long-continuation
   logic, ~4–5× the trades and diversification. (NQ transfer is being tested in the parallel
   cross-instrument work; the frozen symmetric book partial-failed on NQ, but the *long-only*
   version should be re-tested.)
3. **Crash guard:** the one real tail is long-continuation in a fast bear (2020). A causal
   "not in a confirmed fast downtrend" gate is theory-motivated and worth testing (carefully,
   to avoid curve-fit).

## Reproduce

`regime_2e_oos_databento.py` · `_diagnostics` · `_pertrade` (+`--full`) · `_analysis` · `_wfa` ·
`_wfa_cleanroom` · `_reconcile` · `_fixed_configs` · `_long_hunt` · `_era_vs_vol` ·
`_gamma_condition` · `_reversion` · `_forward_spec` · `_vol_history`. Charts in `docs/living/`.
