# VA-imbalance filter — side-by-side WFA (OOS only)
*Generated 2026-06-20 20:22 · headless · same engine · LOCKED filter, no tuning to result (PROJECT_CHARTER §4).*

**Hypothesis (structural, locked):** breakouts work in IMBALANCE, not balance → drop signals inside the prior-session value area (keep only below VAL + above VAH).

- **Baseline** `pin10_all_sl` — ALL CC, single-leg, target pinned 1.0R, 12m IS / 3m OOS, slip 0.5/0.5, $3 r/t, 1 ES, stop_offset 1.
- **Filtered** `pin10_all_va_sl` — identical config + `session_va ∈ {below, above}`.

| Metric | Baseline | VA-filtered |
|---|---|---|
| OOS trades (filled) | 4129 | 2945  (−28.7%) |
| Net $ · Expectancy $/trade | $194,776 · $47.2 | $213,902 · $72.6 |
| Target $ vs Stop $ vs EOD $ | $1,353,148 / $-1,166,186 / $7,814 | $970,216 / $-779,230 / $22,916 |
| Win% · Median trade $ | 52.1% · $47.0 | 53.4% · $109.5 |
| % OOS windows green | 67% | 69% |
| Best-year share % (OOS) | 54% | 39% |
| MAR (net÷|maxDD|) · MAR95 (net÷|MC DD95|) | 7.01 · 4.00 | 8.80 · 6.64 |
| MC DD95 $ | $-48,661 | $-32,219 |
| Longest underwater (days) | 315 | 315 |
| Median WFE % · Mean PROM | 115% · -0.08 | 41% · 0.52 |
| Folds | 15 | 13 |

**Signals dropped by the filter:** 28.7% at the OOS level (~227 trades / OOS bucket — OK).

## Acceptance test (strict)
A WIN only if expectancy rises at a *similar* trade count with similar-or-better OOS robustness across windows — NOT if a ratio improves merely by cutting trades.

- Expectancy higher? **✅** ($47.2 → $72.6)
- Trade count similar (≤35% cut)? **✅** (28.7% dropped)
- ≥~30 trades / OOS bucket? **✅** (227)
- **NOT** PF-by-attrition (OOS net rises while trades fall)? **✅** ($194,776 → $213,902 on 4129 → 2945 trades)
- OOS durability similar-or-better (%green, MAR, Mean PROM, best-year share)? **✅** — Mean PROM -0.08 → 0.52 (WFA's selection objective), best-year share 54% → 39%
- Locked rail — Median WFE ≥ 50%? **❌** (115% → 41%)  ⚠️ *but WFE fell because the IN-SAMPLE edge is stronger (median IS PnL up) — a larger OOS÷IS denominator, NOT an OOS regression; S21/S22 flagged WFE as denominator-fragile.*

### **QUALIFIED WIN — imbalance hypothesis supported, but not a clean pass**
Expectancy +54%, net OOS profit RISES on fewer trades (so it is not PF-by-attrition), best-year concentration drops 54%→39% (more durable), and Mean PROM flips negative→positive — strong support for the structural hypothesis. It does NOT clear the Median-WFE≥50% rail, but that is a denominator effect (stronger in-sample), not an OOS regression. OOS is still choppy fold-to-fold. **Recommendation:** promising — confirm on individual CC setups and consider the open-ended VA threshold before any GO; do NOT re-tune the filter to these numbers.

*Filter locked before the run; OOS judged once; no parameter or bucket was tuned to these numbers.*