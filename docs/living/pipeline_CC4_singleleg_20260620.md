# Pipeline Report — CC4 (singleleg, regime filter OFF, excl last 45min)
*Generated 2026-06-20 14:42 · headless · same engine as the app · human-pre-specified config, no auto-tuning (PROJECT_CHARTER §4).*

## Phase 0 — Sanity
- **1451 CC4 signals** over 2021-06-16 → 2026-06-16 (~5.0 yr), 888 signal-days.
- Tick data present for **872/888** days.
- Avg **290 signals/yr** (above the ~30/yr discard floor).

## Phase 1 — Raw edge (baseline 1.0R target, NO optimisation)
- Trades **1424** · Net **$54,153** · Expectancy **$38.0/trade** (0.034 R) · PF **1.11** · Win% **52.7** · Max DD **$-26,020** · PnL/DD **2.08**.
- Raw expectancy is **POSITIVE** — clears the Phase-1 gate (an edge must exist before optimisation; optimising a non-edge just fits noise).

## Phase 2 — Structure: profit by year & concentration
| Year | Net PnL |
|---|---|
| 2021 | $-6,422 |
| 2022 | $18,154 |
| 2023 | $-8,644 |
| 2024 | $7,417 |
| 2025 | $34,120 |
| 2026 | $9,528 |

- **Best-year share:** 63% of total profit (ok).
- **Top-10-trade share of gross profit:** 5% (ok).

## Phase 3 — Walk-Forward Analysis (unpinned, 12m IS / 3m OOS)
- **10 folds** · Total OOS PnL **$40,254** · Median WFE **69%** · % OOS profitable **60%** · Median fold PF **1.11** · Mean PROM **-0.58** · Worst-fold DD **$-19,368**.
- Baseline window **PASSES** the rails.

## Phase 3a — Walk-forward STRUCTURE robustness
Same setup + params under 6 IS/OOS architectures. Robustness score = independent fixed tests survived (0–7).

| Architecture | Tests | Folds | OOS PnL | Med PF | Med WFE% | %green | PROM |
|---|---|---|---|---|---|---|---|
| IS 3m/OOS 1m | 3/7 | 39 | $49,221 | 1.05 | -24 | 56 | -0.83 |
| IS 6m/OOS 1m | 3/7 | 36 | $50,286 | 1.05 | 48 | 58 | -0.82 |
| IS 6m/OOS 3m | 4/7 | 12 | $47,062 | 1.13 | 69 | 58 | -0.63 |
| IS 12m/OOS 3m | 5/7 | 10 | $40,254 | 1.11 | 69 | 60 | -0.58 |
| IS 12m/OOS 1m | 4/7 | 30 | $30,604 | 1.05 | 20 | 60 | -0.82 |
| IS 24m/OOS 6m | 4/7 | 3 | $44,676 | 1.16 | 245 | 100 | -0.18 |

- **1/6 architectures score ≥5/7.** Robust edges survive *most* structures, not one cherry-picked window.

## Phase 4.5 — Monte Carlo (baseline OOS trades, 5,000 bootstraps)
- **DD95 $-47,656** · **DD99 $-61,682** (size capital against THIS, not the single realised path).
- Terminal OOS PnL: median **$40,285** (95% CI $-24,734 … $106,194); **P(OOS loss) = 11.4%**.

## Phase 4.6 — OOS equity PATH & shape
- Combined OOS: Net **$40,254** · Max DD **$-22,870** · **MAR 1.76** (net ÷ |max DD|) · early trough **$-10,899** · longest underwater **525 days**.
- **Best-year share: 82% of OOS profit** (⚠️ regime-dependent (>70%)).

| Year | OOS Net |
|---|---|
| 2022 | $2,678 |
| 2023 | $-3,418 |
| 2024 | $6,392 |
| 2025 | $33,032 |
| 2026 | $1,570 |

*A positive total with one year >70% of profit and a max DD near the total profit is a regime-dependent curve, not a durable edge — the shape gates below catch this.*

## Verdict — Acceptance report card
| Gate | Type | Result |
|---|---|---|
| Raw edge positive | core | ✅ |
| Baseline WFA passes rails | core | ✅ |
| Survives ≥half of structures | core | ❌ |
| Monte Carlo P(loss) < 35% | core | ✅ |
| OOS max-DD survivable (MAR ≥ 1) | shape | ✅ |
| OOS profit not 1-year (≤70%) | shape | ❌ |

### **NO-GO — does not clear the rails**  (4/6 gates · 1 core / 1 shape failed)
Shelve this configuration. A shape gate failed — the OOS profit is regime-dependent and/or the drawdown rivals the total profit, so the positive aggregate is not a durable edge. Do not trade it as-is.

*Rails fixed in advance; this report executes a pre-specified config and never tuned a parameter or filter to these results.*