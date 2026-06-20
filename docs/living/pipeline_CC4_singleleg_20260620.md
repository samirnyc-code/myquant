# Pipeline Report — CC4 (singleleg, regime filter OFF)
*Generated 2026-06-20 13:48 · headless · same engine as the app · human-pre-specified config, no auto-tuning (PROJECT_CHARTER §4).*

## Phase 0 — Sanity
- **1680 CC4 signals** over 2021-06-16 → 2026-06-16 (~5.0 yr), 946 signal-days.
- Tick data present for **930/946** days.
- Avg **336 signals/yr** (above the ~30/yr discard floor).

## Phase 1 — Raw edge (baseline 1.0R target, NO optimisation)
- Trades **1643** · Net **$50,046** · Expectancy **$30.5/trade** (0.030 R) · PF **1.10** · Win% **51.7** · Max DD **$-27,500** · PnL/DD **1.82**.
- Raw expectancy is **POSITIVE** — clears the Phase-1 gate (an edge must exist before optimisation; optimising a non-edge just fits noise).

## Phase 2 — Structure: profit by year & concentration
| Year | Net PnL |
|---|---|
| 2021 | $-5,766 |
| 2022 | $19,028 |
| 2023 | $-10,882 |
| 2024 | $10,418 |
| 2025 | $30,560 |
| 2026 | $6,686 |

- **Best-year share:** 61% of total profit (ok).
- **Top-10-trade share of gross profit:** 5% (ok).

## Phase 3 — Walk-Forward Analysis (unpinned, 12m IS / 3m OOS)
- **11 folds** · Total OOS PnL **$41,294** · Median WFE **55%** · % OOS profitable **82%** · Median fold PF **1.10** · Mean PROM **-0.81** · Worst-fold DD **$-15,488**.
- Baseline window **PASSES** the rails.

## Phase 3a — Walk-forward STRUCTURE robustness
Same setup + params under 6 IS/OOS architectures. Robustness score = independent fixed tests survived (0–7).

| Architecture | Tests | Folds | OOS PnL | Med PF | Med WFE% | %green | PROM |
|---|---|---|---|---|---|---|---|
| IS 3m/OOS 1m | 3/7 | 42 | $57,514 | 1.09 | 39 | 55 | -0.77 |
| IS 6m/OOS 1m | 3/7 | 39 | $32,034 | 1.14 | 17 | 56 | -0.82 |
| IS 6m/OOS 3m | 5/7 | 13 | $29,572 | 1.07 | 72 | 77 | -0.95 |
| IS 12m/OOS 3m | 5/7 | 11 | $41,294 | 1.10 | 55 | 82 | -0.81 |
| IS 12m/OOS 1m | 4/7 | 33 | $36,757 | 1.20 | 13 | 58 | -0.84 |
| IS 24m/OOS 6m | 4/7 | 3 | $29,959 | 1.15 | 209 | 100 | -0.44 |

- **2/6 architectures score ≥5/7.** Robust edges survive *most* structures, not one cherry-picked window.

## Phase 4.5 — Monte Carlo (baseline OOS trades, 5,000 bootstraps)
- **DD95 $-50,260** · **DD99 $-65,243** (size capital against THIS, not the single realised path).
- Terminal OOS PnL: median **$41,094** (95% CI $-26,719 … $111,596); **P(OOS loss) = 11.5%**.

## Verdict — Acceptance report card
| Gate | Result |
|---|---|
| Raw edge positive | ✅ |
| Baseline WFA passes rails | ✅ |
| Survives ≥half of structures | ❌ |
| Monte Carlo P(loss) < 35% | ✅ |

### **CONDITIONAL — promising but not clean**  (3/4 gates)
One gate failed; investigate it specifically before risking capital.

*Rails fixed in advance; this report executes a pre-specified config and never tuned a parameter or filter to these results.*