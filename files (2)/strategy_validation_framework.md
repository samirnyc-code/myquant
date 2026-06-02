# Strategy Validation Framework
**Project:** MyQuant — MC Signal Python Simulator  
**Status:** Living Document  
**Last Updated:** June 1, 2026  
**Guiding Principle:** Every analytical decision is grounded in established literature. Nothing is decided by opinion.

---

## 0. Foundational Texts

These texts form the intellectual backbone of every test we run. When a threshold or methodology is used, it is traced back to one of these sources.

| Text | Author | Primary Contribution |
|------|--------|---------------------|
| *The Evaluation and Optimization of Trading Strategies* | Robert Pardo | Walk-forward analysis — the definitive methodology |
| *Trading Systems and Methods* (5th ed.) | Perry Kaufman | Broadest coverage of system metrics and robustness testing |
| *Trade Your Way to Financial Freedom* | Van Tharp | Expectancy, SQN — useful frameworks, thresholds are author opinion |
| *Evidence-Based Technical Analysis* | David Aronson | Rigorous statistical hypothesis testing applied to TA |
| *Quantitative Trading* | Ernest Chan | Practical Sharpe-based framework, implementation focus |
| *Algorithmic Trading* | Ernest Chan | Extensions of Chan Vol 1, more rigorous treatment |
| *Advances in Financial Machine Learning* | Marcos Lopez de Prado | Most rigorous modern framework — multiple testing, Deflated Sharpe, CPCV |

**Note on disagreement between sources:** These texts do not always agree. Where they conflict, we document the disagreement and apply the more conservative standard. We never select the standard that makes our results look better.

---

## 1. Core Philosophy

### 1.1 The Multiple Testing Problem
*(Lopez de Prado, Chapter 11)*

Every time a result is observed and a rule is adjusted, a statistical test is consumed. With enough tests, any dataset will yield a strategy that looks profitable by pure chance.

**Our discipline:**
- All setup logic (1cc–5cc) was defined BEFORE backtesting
- All filters must have a prior theoretical justification BEFORE application
- Every variation tested is logged — no silent discarding of negative results
- Final reported results include ALL tests run, not just survivors

### 1.2 The Hypothesis Framework

Each MC setup (1cc, 2cc, 3cc, 4cc, 5cc) is treated as an **independent hypothesis**:

> *"Setup Xcc produces positive expectancy in ES futures across a 15-year out-of-sample period, after transaction costs, that is statistically unlikely to be due to chance."*

Each setup is tested independently. Results are reported for all five. Setups are excluded only if they **fail their own independent test** — not because they drag down a combined result.

**This is hypothesis rejection, not data mining. The distinction is critical.**

### 1.3 The Filter Discipline
*(Aronson, Chapter 6; Lopez de Prado, Chapter 11)*

Filters applied based on observed results are multiple tests. They are only defensible if:

1. A prior theoretical reason exists BEFORE the filter is applied
2. The reason is documented before results are examined
3. Full unfiltered results are always reported alongside filtered results

**Current filter candidates and their status:**

| Filter | Prior Reason | Status |
|--------|-------------|--------|
| Exclude Wednesdays | FOMC, oil inventory, mid-week positioning — needs verification | Candidate — requires causal analysis first |
| Exclude 1330–1515 ET | Pre-close chop, low institutional participation | Candidate — structural rationale exists |
| Exclude 2cc | TBD — must be proven by independent test failure | Report results first |
| Exclude 5cc | TBD — must be proven by independent test failure | Report results first |
| Exclude 1cc | Low sample size — statistical power concern | Valid methodological reason |

**Rule:** No filter is applied until causal analysis is documented. The Wednesday filter specifically must distinguish between all Wednesdays vs. FOMC Wednesdays before any exclusion is made.

---

## 2. The Testing Stack

Tests are run in this order. Each layer builds on the previous. Do not skip layers.

### Layer 1: Does Any Edge Exist?
*Run before anything else. If this fails, stop.*

| Test | What It Measures | Pass Threshold | Source |
|------|-----------------|----------------|--------|
| **Expectancy $** | Average $ profit per trade | > $0 after commissions | Van Tharp |
| **Expectancy R** | Average profit in units of risk | > 0R | Van Tharp |
| **Profit Factor** | Gross profit / Gross loss | > 1.3 | Kaufman |
| **Win Rate** | % winning trades | Meaningless alone — must combine with W/L ratio | — |
| **Avg Win / Avg Loss ratio** | Payoff ratio | Depends on win rate — see expectancy | — |
| **Sample Size** | Number of trades | Minimum 200 per setup | Aronson |
| **Binomial Test** | Is win rate statistically above 50%? | p < 0.05 | Aronson, Ch 6 |
| **t-test on returns** | Are mean returns significantly > 0? | p < 0.05 | Aronson |

### Layer 2: Is It Consistent?
*If Layer 1 passes, run this.*

| Test | What It Measures | Pass Threshold | Source |
|------|-----------------|----------------|--------|
| **Year-by-year breakdown** | Annual expectancy for each of 15 years | No single year carries >40% of total profit | Kaufman |
| **SQN (System Quality Number)** | Expectancy / StdDev of R × √trades | >1.6 below average, >2.0 average, >2.5 good | Van Tharp* |
| **Profit Factor by year** | Annual PF | Majority of years >1.0 | Kaufman |
| **Z-score of runs** | Are wins/losses randomly distributed? | |Z| < 1.96 (not clustered) | Aronson |

*Van Tharp SQN thresholds are his own framework, not peer-reviewed. Treat as directional, not definitive.

### Layer 3: Is It Robust? (Walk-Forward)
*(Pardo — the definitive reference for this section)*

**Walk-forward tests are the primary robustness test.**

#### 3.1 Walk-Forward Methodology
*(Pardo, Chapter 8)*

- **In-sample (IS):** Period used to define/confirm rules
- **Out-of-sample (OOS):** Period never seen during rule definition
- **OOS must be defined before IS is examined**

#### 3.2 Walk-Forward Configurations

We run multiple window sizes simultaneously. No single window is definitive.

| Configuration | IS Period | OOS Period | Windows over 15 years |
|--------------|-----------|------------|----------------------|
| Anchored 10/5 | 10 years | 5 years | 1 (years 1-10 → test 11-15) |
| Rolling 5/1 | 5 years | 1 year | 10 windows |
| Rolling 3/1 | 3 years | 1 year | 12 windows |
| Rolling 2/0.5 | 2 years | 6 months | 25 windows |
| Rolling 1/0.25 | 1 year | 3 months | ~48 windows |

#### 3.3 Walk-Forward Interpretation
*(Pardo, Chapter 9)*

| Metric | What It Measures | Threshold |
|--------|-----------------|-----------|
| **OOS Profit Factor** | PF on never-seen data | >1.0 minimum, >1.2 target |
| **Walk-Forward Efficiency (WFE)** | OOS Sharpe / IS Sharpe | >0.5 (Pardo's standard) |
| **% Profitable OOS Windows** | Consistency across windows | >60% minimum |
| **OOS Expectancy $** | $ per trade on OOS data | Must remain positive |

**Key principle (Pardo):** Not every OOS window needs to be profitable. Losing windows in flat/hostile market regimes are expected. A catastrophic failure (large negative expectancy) in multiple consecutive windows is a red flag.

#### 3.4 Walk-Forward Visualization

For each window configuration, we produce:
- **Equity curve** — OOS windows stitched together (no IS data)
- **Rolling OOS expectancy chart** — expectancy per window over time
- **Window heatmap** — each window colored by OOS profit factor (red/yellow/green)
- **Regime overlay** — VIX levels overlaid on window performance

### Layer 4: Monte Carlo Analysis
*(Chan, Chapter 3; Lopez de Prado, Chapter 10)*

Monte Carlo answers: *"Given our actual trade results, what is the distribution of possible outcomes?"*

#### 4.1 Trade Sequence Shuffling
- Take actual trade results (R-multiples)
- Randomly reshuffle sequence 10,000 times
- For each shuffle, calculate: final equity, max drawdown, Sharpe
- Report 5th, 25th, 50th, 75th, 95th percentile outcomes

**What we're testing:** Is our actual equity curve meaningfully better than random sequencing of the same trades? If not, our entry/exit timing adds no value.

#### 4.2 Trade Result Sampling (Bootstrap)
- Randomly sample WITH replacement from actual trades
- Simulate 10,000 alternative 15-year histories
- Report distribution of outcomes

**What we're testing:** Sensitivity to which specific trades occurred. A fragile strategy's outcome varies wildly across simulations.

#### 4.3 Monte Carlo Outputs

| Output | What It Means |
|--------|--------------|
| **95th percentile max drawdown** | Worst realistic drawdown — size your account to survive this |
| **5th percentile final equity** | Worst realistic outcome — is it still above breakeven? |
| **Probability of ruin** | % of simulations ending below starting capital |
| **Median outcome** | What you should realistically expect |

#### 4.4 Visualization
- Equity curve fan chart (5th/25th/50th/75th/95th percentile bands)
- Drawdown distribution histogram
- Probability of ruin at each account level

### Layer 5: Slippage & Commission Sensitivity

| Test | Description |
|------|-------------|
| **Base case** | 1 tick entry slippage, $5 round trip commission |
| **+1 tick entry** | Entry slippage doubled |
| **+1 tick target** | Target requires 1 additional tick through |
| **+1 tick stop** | Stop triggered 1 tick earlier |
| **Full stress** | All three combined |

**Pass:** Edge survives full stress test with positive expectancy.  
**Yellow:** Edge survives base case only — marginal strategy.  
**Fail:** Edge disappears with any slippage — do not trade.

### Layer 6: Lopez de Prado Stress Tests
*(Lopez de Prado, Chapters 11-14)*

These are reported for transparency. We may not pass all of them. That is disclosed, not hidden.

| Test | Description | Our Expected Result |
|------|-------------|-------------------|
| **Deflated Sharpe Ratio** | Sharpe adjusted for number of tests run | Will be lower than raw Sharpe — report honestly |
| **Probability of Backtest Overfitting** | Mathematical probability our results are curve-fitted | Report the number — do not hide it |
| **Multiple testing adjustment** | Bonferroni or BHY correction on p-values | Applied to all significance tests |

---

## 3. Per-Setup Reporting Structure

Each of the 5 setups (1cc–5cc) gets an identical independent report:

```
Setup: Xcc
─────────────────────────────────────────
SECTION 1: Basic Statistics
  Total trades, Win rate, Avg Win, Avg Loss
  Expectancy $, Expectancy R
  Profit Factor, SQN
  Sample size adequacy (binomial test)

SECTION 2: Consistency
  Year-by-year table (15 rows)
  Best year / Worst year
  % of years profitable
  Z-score of runs

SECTION 3: Walk-Forward (all 5 configurations)
  OOS equity curve per configuration
  WFE per configuration
  % profitable OOS windows
  Window heatmap

SECTION 4: Monte Carlo
  Equity fan chart
  95th percentile max drawdown
  Probability of ruin

SECTION 5: Slippage Sensitivity
  Results table: base / +1 entry / +1 target / full stress

SECTION 6: Lopez de Prado
  Deflated Sharpe Ratio
  Tests run count
  Adjusted p-value

SECTION 7: Verdict
  PASS / CONDITIONAL / FAIL
  Reason stated explicitly
  Filters applied (if any) with prior justification documented
```

---

## 4. Multi-Timeframe Analysis (5M / 15M / 60M)

### 4.1 Signal Confluence
When a signal fires on 60M, it also fires on 15M and 5M by definition.

**Hypothesis:** Higher timeframe confluence produces higher expectancy per trade.

**Test:** Tag every 5M signal with its timeframe confluence level:
- 5M only
- 5M + 15M
- 5M + 15M + 60M

Run Layer 1–4 independently for each confluence level. Report all three.

**Do not assume confluence is better before testing.**

### 4.2 MES Scaling
ES trade results are directly translatable to MES at 1/10th the dollar value. No separate backtest needed — scale the $ results. Commission impact is proportionally higher on MES ($1.40 vs $5.00 per RT on ES) — model this explicitly.

---

## 5. Risk Parameters (Open Design Questions)

These must be resolved before simulation is built. Each option changes results materially.

| Question | Options | Decision |
|----------|---------|----------|
| New signal while in trade (same direction) | Ignore / Scale in / Reset | **UNDECIDED** |
| Max concurrent positions | 1 / 2 / unlimited | **UNDECIDED** |
| Max daily loss | Hard stop $ / No limit | **UNDECIDED** |
| Max open risk | % of account / Fixed $ | **UNDECIDED** |
| Long account + Short account | Separate NT8 accounts | **DECIDED: Yes** |
| Opposite signal while in trade | Hold both / Close and reverse | **DECIDED: Hold both (separate accounts)** |

---

## 6. Reporting Dashboard Design

All results are displayed in a single interactive dashboard. Priority order on screen:

**Above the fold (always visible):**
- Setup name + Verdict (PASS/CONDITIONAL/FAIL)
- Expectancy $ and R
- Profit Factor
- OOS Equity Curve (stitched walk-forward)
- Monte Carlo fan chart

**Expandable sections:**
- Year-by-year table
- Walk-forward window heatmap
- Slippage sensitivity table
- Lopez de Prado metrics
- Raw trade log

---

## 7. What "Good" Looks Like

Based on Pardo, Kaufman, and Chan — not opinion:

| Metric | Minimum | Target | Source |
|--------|---------|--------|--------|
| Profit Factor (OOS) | 1.2 | 1.5+ | Kaufman |
| WFE | 0.5 | 0.7+ | Pardo |
| % Profitable OOS Windows | 60% | 75%+ | Pardo |
| SQN | 1.6 | 2.5+ | Van Tharp* |
| Sharpe Ratio (annualized) | 0.5 | 1.0+ | Chan |
| Calmar Ratio | 0.5 | 1.0+ | Industry |
| Monte Carlo ruin probability | <10% | <5% | Chan |

*Van Tharp thresholds — directional only, not peer-reviewed.

**A strategy does not need to pass every metric at target level. It needs to pass all minimum thresholds and show a coherent picture. A strategy that barely passes everything is weaker than one that clearly passes most things and fails one with a known reason.**

---

## 8. Changelog

| Date | Change |
|------|--------|
| June 1, 2026 | Initial document created |

---

*This document is updated every session. No analytical decision is made outside this framework.*
