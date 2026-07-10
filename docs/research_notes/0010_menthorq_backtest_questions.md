# 0010 — MenthorQ backtest panel: decomposition, vendor questions, tracking plan

*2026-07-10. Companion to [0009_menthorq_gamma_mc.md](0009_menthorq_gamma_mc.md). Tracker files live in [`gamma_tracker/`](../../gamma_tracker/).*

## Context

MenthorQ's ES gamma-level "Backtest" panel shows a per-level **Regime Hold Rate** with a positive-outcome count, plus sub-stats under "Broke During Day" and "Broke At Close". Only *today's* backtest is visible — no history. Panel on 2026-07-10:

| Level | Hold rate |
|---|---|
| 1D Max (7602.02) | 89.1% |
| Call Res. 0DTE | 72.9% |
| Call Res. | 89.8% |
| Put Support | 98.6% |
| Put Sup. 0DTE | 87.2% |
| 1D Min (7482.54) | 91.3% |

1D Max detail: 89.07%, "348 positive outcomes over the past 3 years". Broke During Day: comeback rate 43%, avg move +22.01, worst +108.70. Broke At Close: 10.9%, median +19.74, avg +23.29, worst +86.53.

## Decomposition

From hold rate `H`, positive count `P`, broke-at-close `Bc`, comeback rate `Cr`:

```
N (total days)  = P / H                     = 348 / 0.8907 ≈ 391
closed beyond   = N × Bc                    = 391 × 0.109  ≈ 43
comeback days   = closed_beyond × Cr/(1−Cr) = 43 × 0.43/0.57 ≈ 32
broke intraday  = comeback + closed_beyond  = 75
never reached   = N − broke_intraday        = 316
```

| Outcome | Days | % of regime days |
|---|---:|---:|
| Never reached | 316 | 80.8% |
| Broke intraday, closed back inside | 32 | 8.2% |
| Closed beyond | 43 | 11.0% |
| **Total** | **391** | 100% |

Self-check: never-reached + comeback = 316 + 32 = **348** = displayed positive outcomes ✓.

**Key takeaway:** the headline 89% "hold" mixes days the level was never touched (~81%) with days it was touched but recovered (~8%). Assumptions to confirm: "comeback rate" = comebacks ÷ intraday-breaks; "broke" = any intraday pierce.

## Questions for Fabio

### A. Definitions
1. "Broke during the day" — any intraday touch, a one-tick pierce, or a minimum distance beyond?
2. Comeback rate 43% — denominator = days that broke intraday, or all regime days?
3. Broke at close 10.9% — share of all regime days, or only of intraday-break days?
4. "348 positive outcomes" — does that include never-reached days, or only reached-and-held?

### B. Sample / denominator
5. 348 at 89.07% implies ≈391 qualifying days — is that the denominator?
6. How many days did price never reach the level (est. ~316, ≈81%)? Is never-reached tracked?
7. Is the 3-year window rolling? Does the positive-outcome count change day to day?

### C. Regime
8. How is regime defined — gamma positioning only, or also vol, trend, dealer positioning, HVL…?
9. How many historical days qualify as today's regime before the level-specific filter?
10. Can subscribers see which regime today is classified as?

### D. Timing / updates
11. When are stats generated — after prior close or pre-open?
12. Do they update intraday as levels move (Live tier)? How often?
13. Do 20-min-delayed subscribers see delayed stats?

### E. Bias / validation
14. Is regime classified with only pre-open information? (look-ahead)
15. Out-of-sample, or in-sample fit over the 3 years?

### F. Transparency
16. Why is only today's backtest visible? Can history be exposed?
17. Could the outcome count link to dated occurrences (date / regime / level / result)?

**First message: lead with A1, A2, B5, C8, D11–12, F16.**

## Comebacks if he deflects

- **"Proprietary."** — Not asking for the formula, just the inputs and the denominator. That's methodology, not IP; every legitimate backtest states its universe and counting rule.
- **"Too technical."** — Then one number: how many total historical days is today's 89% computed from? A percentage without a sample size isn't interpretable.
- **"You don't need that."** — I size positions on these probabilities. Whether 89% comes from 40 days or 400 — and whether it's conditional on the level being reached — materially changes the bet.
- **"Technical issues / no history."** — Then a CSV export of the dated occurrences behind one level? Or confirm I can log them myself daily.
- **Stonewall.** — No problem; I'll keep my own daily record and check calibration over a few months.

## Tracking plan

Daily logging via [`gamma_tracker/`](../../gamma_tracker/) (CSV template + SQLite schema with a `v_decomposition` view). Record the positive-outcome count **every day** — drift (348 → 351 → 349) reveals whether the window is rolling and whether the regime filter changes daily.
