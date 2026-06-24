# BUG — multileg / 3-leg P&L is mis-scaled (over-counts net, inflates exp R)

**Found:** June 24, 2026 (Keystone/IB-edge exit-variant work)
**Severity:** HIGH — invalidates every multileg / 3-leg / scale-in / scale-out result
**Status:** NOT FIXED. Single-leg path is unaffected and verified correct.

## Symptom (controlled diagnostic on the gated IB-edge book, 1,395 trades)

| check | got | should be | ratio |
|---|---|---|---|
| `single 2R (1c)` net | $232,593 | — | — |
| `ML both legs @2R (2c)` net | **$762,678** | 2 × $232,593 = $465,186 | **3.28×** (must be 2.00×) |
| `ML scale-out 1R/2R (2c)` net | **$878,003** | single1R + single2R = $394,986 | **2.22×** (must be 1.00×) |

Two **identical** 1-contract legs exiting at 2R must equal exactly 2× the single-leg 2R
book. Instead net is 3.28×, and **PF inflates 1.38 → 2.24** on identical legs — i.e. the
**loss side is being under-counted** in the multileg path.

## Root cause (partial — needs a full pass through `_simulate_one_multileg`)

- `simulation_engine.py:670` — multileg returns `RiskDollar = risk_pts/ts * tv1` (**leg-1
  risk only**) while `NetPnL` sums **both legs** → **exp R inflated ~2×**. Always divide by
  the *active* risk (`tv_total` when E2 filled), not `tv1`.
- The `tv1/tv2 = tick_value * contracts_t1/contracts_t2` split (`sim_engine:1828-1829`) is
  correct, so the **net-$ over-count (~1.6× beyond the correct 2-contract value) is inside
  `_simulate_one_multileg`'s leg P&L / exit pricing** — most likely the stop leg (and/or the
  blended-entry exit) under-charging losses. The 3-leg path (`_simulate_one_3leg`) shares the
  same structure and is presumed equally affected.

## Impact

- **Every** multileg / 3-leg result (Bar Analysis, WFA, sweeps, the S31 ZLO/MC multileg work,
  any saved multileg run) is **unreliable until this is fixed.** Treat as guilty.
- **Single-leg is fine** — verified: single 1R = $162,393, single 2R = $232,593, matching all
  prior single-leg work. The Keystone setup is single-leg and is NOT affected by this bug.

## Repro

`.venv/Scripts/python.exe scripts/ib_edge_scalein.py` → `docs/living/ib_edge_scalein_<date>.md`
(the "Accounting check" section prints the ratios above).

## Fix checklist

1. In `_simulate_one_multileg`: make total `NetPnL` = sum of per-leg (ticks × per-leg tv),
   and ensure the **stop exit charges every still-open leg** at the stop (suspected leak).
2. Set `RiskDollar` to the **total** risk actually on at entry (E1 risk, plus E2 risk once the
   pullback fills) — not `tv1` alone (`:670`).
3. Mirror the fix in `_simulate_one_3leg`.
4. Re-validate: `ML both@2R (2c)` must equal exactly 2.00× `single 2R (1c)`;
   `ML scale-out 1R/2R` must equal `single1R + single2R`.
5. Re-run / re-trust any multileg conclusion only after the diagnostic passes.
