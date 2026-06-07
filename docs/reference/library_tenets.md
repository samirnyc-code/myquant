# Pardo — Library Tenets
**Source:** *The Evaluation and Optimization of Trading Strategies*, Robert Pardo (2nd ed.)
**Extracted for:** `myquant/docs/library_tenets.md`

---

## Pardo — Chapter 1: On Trading Strategies

### Core Tenet
A trading strategy is a complete, rule-based specification of entries, exits, and risk management. Its value is judged solely by performance on unseen data, not on how well it fits historical data.

### Key Rules / Thresholds
- Distinguish clearly between *optimization* and *overfitting* — they are not synonyms. Optimization done correctly produces robust parameters; overfitting produces parameters that only work on past data.
- A strategy that has never used WFA is not a fully validated strategy.

### Warnings
- Do not conflate optimization with curve-fitting. Those who dismiss all optimization have simply never seen it done correctly.
- Do not evaluate a strategy solely on in-sample performance.

### Applicability to MC Sim
The 5 independent setups (1cc–5cc) must each be treated as distinct strategies and validated independently. Shared signal logic does not mean shared robustness.

---

## Pardo — Chapter 2: The Systematic Trading Edge

### Core Tenet
Systematic trading has a demonstrable edge over discretionary trading because it can be rigorously tested, optimized, and validated on historical data using reproducible methods, including Walk-Forward Analysis.

### Key Rules / Thresholds
- WFA is described as the "only 99 percent" reliable validation method. The only strategy that can forgo WFA is one that requires no optimization at all.

### Direct Quotes
> "the walk-forward method to guide system development" — Foreword (Dunn)

### Warnings
- Real-time efficiency of the markets has never been higher; an edge must be proven rigorously, not assumed.

### Applicability to MC Sim
The MC signal hypothesis (micro-channel breakouts have predictive value on ES futures) must be treated as an empirical claim, not an assumption. WFA is the proof.

---

## Pardo — Chapter 3: The Trading Strategy Development Process

### Core Tenet
Development follows a strict sequential pipeline: formulation → specification → preliminary testing → optimization via WFA → evaluation → real-time trading. Skipping or reordering steps invalidates results.

### Key Rules / Thresholds
The five steps in order:
1. Formulation and specification
2. Preliminary testing
3. Optimization
4. Walk-Forward Analysis
5. Real-time trading

### Warnings
- Do not begin optimization until preliminary testing has confirmed the strategy trades as intended.
- Do not go to real-time trading until WFA has been completed.

### Applicability to MC Sim
The Python simulator is Step 2–3. WFA framework is Step 4. The pipeline order must be honored — do not run WFA on a simulator whose outputs have not been validated against the C# reference.

---

## Pardo — Chapter 4: The Strategy Development Platform

### Core Tenet
The platform (software + data) is not neutral — software limitations and data quality directly affect simulation accuracy and therefore all downstream conclusions.

### Key Rules / Thresholds
- Platform must support: tick-math rounding, accurate slippage modeling, correct bar-to-bar order execution logic.
- WFA must be natively supported or correctly implemented.

### Warnings
- Platforms that do not use proper tick math will overstate performance through cumulative rounding error.
- Never assume the platform is correct; verify outputs against hand calculations on a sample of signals.

### Applicability to MC Sim
The Python simulator must match MCSimulator C# reference outputs exactly before WFA results have any validity. Divergence = invalidated framework.

---

## Pardo — Chapter 5: The Elements of Strategy Design

### Core Tenet
Strategy design must minimize the number of free parameters, maximize logical simplicity, and be grounded in a sound, ideally universal, principle of market behavior — not derived from pattern-matching on historical data.

### Key Rules / Thresholds
- Use only parameters that materially affect performance; fix all others to constants.
- The fewer optimizable parameters, the lower the risk of overfitting.

### Warnings
- Adding rules to "fix" observed historical problems (hindsight-driven design) is one of the most common and dangerous development errors.
- A strategy based on a non-universal principle (e.g., one that only works in bull markets) will fail when conditions change.

### Applicability to MC Sim
MC signal logic (BTC/STC entries, R-levels, EB stops) must be defined and fixed before optimization begins. The optimizer touches only parameter values, never the logic structure.

---

## Pardo — Chapter 6: The Historical Simulation

### Core Tenet
The historical simulation is the foundation of all downstream analysis. An inaccurate simulation produces false conclusions that propagate through optimization and WFA — "if the simulation is inaccurate or flawed by design, the entire [analysis fails]."

### Key Rules / Thresholds
- Use conservative slippage and commission assumptions; optimistic assumptions produce simulations that cannot be replicated in real time.
- Proper tick math is required; rounding errors cause both missed fills and cumulative P&L overstatement.
- Sample must cover all four major market types: (1) bullish, (2) bearish, (3) congested, (4) cyclic.
- Sample should include a range of volatility levels, especially high and low.

### Warnings
- An overly optimistic simulation leads to real-time losses, not from a bad strategy, but from a bad model of the strategy.
- Do not start optimization until the simulation has been verified at the signal-by-signal level.

### Applicability to MC Sim
ES futures tick math ($12.50/tick, 0.25 minimum increment) must be exact. Slippage assumptions must be conservative and consistent. The C# reference simulator is the ground truth; the Python sim must match it before proceeding.

---

## Pardo — Chapter 7: Formulation and Specification

### Core Tenet
Every rule, formula, and parameter of the trading strategy must be precisely and unambiguously specified before testing begins. Vague specifications allow post-hoc rationalization of results.

### Key Rules / Thresholds
- Entry, exit, stop, and position sizing rules must all be fully specified.
- The objective function used during optimization must be chosen before any optimization run.

### Warnings
- Do not modify the strategy specification after seeing optimization results — that is hindsight abuse.

### Applicability to MC Sim
Each of the 5 setups (1cc–5cc) needs a complete specification document (signal definition, entry logic, stop logic, target logic, position sizing) before any optimization. The spec is the contract.

---

## Pardo — Chapter 8: Preliminary Testing

### Core Tenet
Before optimization, verify that the strategy produces the correct signals and trades. A robust trading strategy must be profitable over: (1) a broad range of contiguous parameter sets, (2) diverse markets, (3) multiple market types and conditions, (4) both long and short trades.

### Key Rules / Thresholds
- Robustness definition (4 features):
  1. Profitable over a broad range of contiguous parameter sets
  2. Profitable over a wide-ranging basket of diverse markets
  3. Profitable over a wide range of market types and conditions
  4. Profitable on both long and short trades
- Minimum trade sample for verification: enough signals to cover every formula and rule at least a handful of times.

### Direct Quotes
> "We are not looking for the optimum method; we are looking for the hardiest method." — Larry Hite (cited by Pardo, p.158)

### Warnings
- Do not proceed to optimization if the strategy does not produce the intended trades.
- A strategy profitable only in one market type or one direction is not robust.

### Applicability to MC Sim
Preliminary validation = matching MC sim outputs (signal counts, entry prices, stop levels, R-level hits) against the C# reference on a held-out sample before WFA. This is a prerequisite, not optional.

---

## Pardo — Chapter 9: Search and Judgment

### Core Tenet
The objective function determines what "best" means during optimization. The choice of objective function shapes the entire parameter space search and must be made on principled, not arbitrary, grounds. Prefer robust objective functions (e.g., PROM — Pessimistic Return on Margin) over simple net profit.

### Key Rules / Thresholds
- Use performance thresholds (floors and ceilings) to filter parameter candidates, e.g.:
  - Floor: Net return > $X
  - Ceiling: Max drawdown < $Y
  - Floor: Minimum N trades per year (ensure adequate sample size)
- Select parameters from a *region* of robust performance, not the single peak.
- Keep step sizes in scan ranges proportional to each other; equal-percentage-change steps are preferred.
- Candidates in two scan ranges should be roughly equal in number.

### Warnings
- Scanning too finely (step sizes too small) promotes overfitting independent of parameter count.
- Net profit alone as objective function is unreliable; it ignores risk and trade frequency.
- A "big fish in a small pond" — isolated peak surrounded by poor performance — is a hallmark of overfitting.

### Applicability to MC Sim
For 1cc–5cc setups, choose objective function before the first optimization run. PROM or Sharpe preferred over net profit. Define performance floors and ceilings per setup. Favor plateau regions over isolated peaks.

---

## Pardo — Chapter 10: Optimization

### Core Tenet
Optimization is the correct identification of the parameter set most likely to produce real-time profits. It is not curve-fitting unless done incorrectly. The goal is the most *robust* parameter set, not the highest in-sample performer.

### Key Rules / Thresholds
- Minimize optimizable parameters — include only those with material performance impact.
- Historical sample must be sufficient to produce a statistically valid trade sample: traditionally ≥30 trades, in practice the more the better.
- Sample must cover all four market types.
- Degrees of freedom consumed must not exceed a large fraction of the total sample; as a practical guide, keep consumption well below 10%.
- Formula: degrees of freedom used = sum of (indicator lookback + 1 per rule) across all indicators.
- Scan ranges must be intuitively appropriate for the indicator (e.g., 2–14 days for a short-term MA, not 1–1,000).
- Two guidelines for historical sample selection:
  1. Include maximum variation (general rule)
  2. If impractical, include data most similar to current conditions (relevance rule)

### Warnings
- Adding parameters because they improve in-sample performance is the canonical path to overfitting.
- More price data is not always better — relevant data is better than maximal data.
- Do not scan parameters with step sizes too fine relative to the range; this promotes overfitting.
- A strategy that only passes optimization should not be traded; it must pass WFA.

### Applicability to MC Sim
For each 1cc–5cc setup: determine which parameters are truly free (material impact), fix the rest. Define scan ranges based on MC signal theory (e.g., lookback window for R-level calculation, min pullback depth). Do not scan what doesn't matter.

---

## Pardo — Chapter 11: Walk-Forward Analysis

### Core Tenet
WFA is the only method that evaluates a trading strategy exclusively on out-of-sample data across a comprehensive historical range. It simultaneously validates robustness, provides realistic performance estimates, identifies optimal parameter shelf life, and is the primary defense against overfitting.

### Key Rules / Thresholds

**Walk-Forward Efficiency (WFE):**
- WFE = annualized OOS profit / annualized IS profit (expressed as %)
- WFE < 25%: strategy is either unsound or overfit
- WFE ≥ 50–60%: robust strategy (Pardo states "research has clearly demonstrated")
- WFE > 100%: possible; OOS can exceed IS performance (not a red flag)
- WFE is predictive: if WFE = 75% and IS profit = $20,000/yr, expect ~$15,000/yr real-time

**OOS Profitable Windows:**
- The example strategy passed with 63% profitable walk-forward windows (19/30)
- Pardo calls this "a convincing result"
- Implication: ≥60% profitable OOS windows is a reasonable robustness threshold

**Window Sizing:**
- Walk-forward (OOS) window = 25–35% of optimization (IS) window
- Fast strategy: start with IS windows of 1–2 years
- Slow strategy: start with IS windows of 3–6 years
- Parameter shelf life ≈ length of the OOS window (e.g., 2-year IS → ~3–6 months shelf life; 5-year IS → ~1–2 years)
- WFA total length: ≥10–20 years whenever possible; target 10–30+ individual walk-forwards for statistical reliability

**Theory of Relevant Data:**
- IS window size is bounded by: (1) statistical requirements, (2) current market conditions, (3) nature of the strategy
- WFA derives statistical rigor from the *total length* of the analysis, not the IS window size alone
- This allows shorter IS windows (for data relevance) without sacrificing statistical validity

**Robustness Criteria (from WFA results):**
1. Strategy made money on price history it had never seen
2. Profitable across a wide spectrum of trend and volatility conditions
3. WFE ≥ 50–60%
4. Large number of profitable individual walk-forwards (≥60%)

### Direct Quotes
> "Walk-Forward Analysis is the closest approximation or simulation of the way in which an optimizable trading strategy is typically used in real-time trading." — p.251

> "Research has clearly demonstrated that robust trading strategies have WFEs greater than 50 or 60 percent." — p.240

> "A trading strategy that makes a significant overall profit with a large number of profitable individual walk-forwards is unlikely to be a product of chance or accident." — p.241

### Warnings
- A single profitable walk-forward proves nothing; chance explains it.
- A strategy that fails WFA is almost certainly not going to produce real-time profits.
- Sound strategies can fail WFA due to optimization framework errors (too-wide scan ranges, wrong window sizes, insufficient degrees of freedom) — if suspected, fix the framework and re-run before abandoning the strategy.
- The parameter set from WFA comes with an expiration date equal to the OOS window length; reoptimize on schedule regardless of perceived necessity.
- Do not cherry-pick the WFA configuration to get a desired WFE; the setup must be determined empirically, not result-driven.

### Applicability to MC Sim
- Use rolling WFA (not anchored) for MC setups given the adaptive nature of market regimes.
- WFE threshold: ≥50% minimum for any of the 5 setups to be considered valid.
- OOS profitable windows: ≥60% minimum.
- For ES futures (fast strategy): start with IS = 12–18 months, OOS = 3–6 months; validate empirically.
- WFA total length: target 10–15 years of ES data = sufficient for 20–60 walk-forwards depending on OOS window size.
- Reoptimization cadence in real-time use = OOS window length.

---

## Pardo — Chapter 12: The Evaluation of Performance

### Core Tenet
Performance must be evaluated as a complete statistical profile — not any single metric. The evaluation profile (from WFA OOS data) is the reference standard against which real-time trading is continuously compared.

### Key Rules / Thresholds
- Key metrics (minimum required in evaluation profile):
  - Net P&L, annualized P&L
  - Number of trades, % profitable
  - Average win, average loss, win/loss ratio
  - Maximum intraday drawdown, max consecutive losses
  - Profit factor (gross profit / gross loss)
  - Risk-adjusted return (RAR)
  - Reward-to-risk ratio (RRR = annualized net profit / max drawdown)
  - Consistency: % of time periods profitable
- Maximum drawdown from WFA OOS windows is more predictive of real-time drawdown than IS optimization drawdown.
- Compute average, min, max, and standard deviation of drawdown across all OOS windows.
- Real-time performance threshold: if any statistic is < 50% or > 150% of the evaluation profile equivalent, require explanation.

### Warnings
- In-sample maximum drawdown understates real-time risk; most overfit models are filtered out during optimization, creating survivorship bias in the drawdown statistic.
- Do not evaluate performance on a small trade sample; wait for statistical significance.

### Applicability to MC Sim
Build a full evaluation profile for each 1cc–5cc setup from WFA OOS results. The profile is the production monitoring tool. Real-time deviation triggers review, not abandonment.

---

## Pardo — Chapter 13: The Many Faces of Overfitting

### Core Tenet
Overfitting is optimization performed incorrectly — specifically, the identification of parameters that produce good IS performance but poor OOS performance. It is not an inherent feature of optimization; it is a product of procedural violations.

### Key Rules / Thresholds

**5 Causes of Overfitting:**
1. Insufficient degrees of freedom
2. Inadequate data and trade sample size
3. Incorrect optimization methods
4. A big win in a small trade sample ("big fish in a small pond")
5. Absence of Walk-Forward Analysis

**Degrees of Freedom:**
- Each data point = 1 degree of freedom
- Each indicator lookback period consumes that many degrees of freedom + 1 (for the rule)
- Startup overhead (e.g., longest MA period) reduces the effective sample
- Rule of thumb: keep degrees of freedom consumed well below 10% of total data points
- Minimum trade sample: ≥30 trades (absolute minimum); in practice, more is always better; include both long and short trades

**Optimization Error 1 — Overparameterization:**
- Too many free parameters relative to the data sample
- Each added parameter exponentially increases the number of simulations (N params × 10 candidates each = 10^N simulations)
- Fix peripheral parameters; only optimize those with demonstrated material impact

**Optimization Error 2 — Overscanning:**
- Scan ranges too wide or step sizes too fine
- Scanning a long-term MA in steps of 1 day over a range of 20–200 = overscanning
- Appropriate step size is proportional to the parameter magnitude (~5% increments)

**Symptoms of Overfitting:**
- Impressive IS results, devastating real-time losses
- Real-time WFE radically lower than WFA-established WFE (not explained by market condition change)
- Mild overfitting: real-time performance consistently ~50% of IS performance
- Severe overfitting: immediate string of real-time losses exceeding evaluation profile max drawdown

### Direct Quotes
> "With enough variables, a curve can be fit perfectly to any time series." — p.288

> "An overfit trading strategy has an extremely high likelihood of losing money in real-time trading." — p.241

> "Even a poor trading strategy will produce attractive performance in some of its historical simulations." — p.241

### Warnings
- Hindsight abuse (adding rules to fix specific historical losses) is one of the most common causes of strategy failure; it always looks like an improvement in-sample.
- Do not add a parameter because it increases in-sample performance by 150%; that is the canonical overfit scenario.
- An overfit strategy can produce 1–3 profitable real-time trades before collapsing; do not mistake early luck for validation.
- Curve-fitting and data mining are distinct problems; do not conflate them.
- The absence of WFA is itself an overfitting cause — it removes the only reliable detection mechanism.

### Applicability to MC Sim
For each 1cc–5cc setup:
- Count and document degrees of freedom consumed before any optimization run.
- Set scan ranges before seeing any results; do not widen ranges to "find" a profitable region.
- After WFA: compare real-time WFE to WFA WFE; discrepancy > 50% requires investigation.
- Any rule added to improve performance on a specific historical cluster of trades must be validated on a fully independent out-of-sample period.

---

## Pardo — Chapter 14: Trading the Strategy

### Core Tenet
Real-time trading execution requires comparing the live trade profile against the evaluation profile continuously. Deviation — in either direction — requires explanation, not reaction.

### Key Rules / Thresholds
- **System stop-loss**: a predefined equity level at which trading is suspended and the strategy is reviewed. Must be set before trading begins.
- **Performance comparison trigger**: if any statistic in the trade profile is < 50% or > 150% of the corresponding evaluation profile statistic, investigate.
- **Statistical sufficiency**: do not judge a strategy on fewer than a statistically significant number of live trades (same standard as testing: ≥30 trades minimum).
- Reoptimization schedule = OOS window length from WFA; must be followed regardless of perceived performance.

### Warnings
- Early large wins are windfalls, not evidence of skill; do not increase position size based on them.
- Early large losses are not automatic strategy failure; compare against evaluation profile drawdown + standard deviation before acting.
- Flat periods are normal; compare against evaluation profile before abandoning.
- Impatience is the most common cause of real-time strategy failure.
- Do not overscrutinize losses and uncritically accept wins; both must remain in context of the evaluation profile.

### Direct Quotes
> "Trade the strategy as long as it performs in real time according to the expectations produced by its evaluation profile, thereby producing a steadily growing equity, which remains above the strategy stop-loss." — p.318

### Applicability to MC Sim
Build the system stop-loss and the evaluation profile dashboard before any 1cc–5cc setup goes live. Automate the 50%/150% deviation alerts. Automate the reoptimization reminder at the end of each OOS window.

---

---

# Aaronson — Library Tenets
**Source:** *Evidence-Based Technical Analysis*, David R. Aronson (Wiley, 2006)  
**Extracted for:** `myquant` — data-mining bias framework, walk-forward testing, statistical significance

---

## Aaronson — Chapter 6: Data-Mining Bias — The Fool's Gold of Objective TA

### Core Tenet
Every optimization run is a multiple comparison procedure (MCP). The rule with the best observed in-sample performance will *systematically overstate* its true future (expected) performance. This gap is the data-mining bias — and it is not optional or occasional; it is mathematical and guaranteed.

### Key Definitions
- **Observed performance** = Expected performance ± Randomness  
  For TA rules, randomness dominates; predictive power is a small component.
- **Data-mining bias** = Long-run average difference between the best rule's observed IS performance and its true expected (future) performance.
- **In-sample data** = Data used for optimization (mining).
- **Out-of-sample data** = Data insulated from mining; provides an unbiased estimate of future performance — but only once.

### The 5 Factors That Drive Data-Mining Bias

| Factor | Direction | Notes |
|--------|-----------|-------|
| 1. Number of rules tested | More rules → larger bias | Main lever the developer controls |
| 2. Number of observations | More observations → smaller bias | *Dominant lever* for controlling bias |
| 3. Correlation among rule returns | Higher correlation → smaller bias | Correlated rules = smaller "effective" universe |
| 4. Presence of positive outliers in returns | More/larger outliers → larger bias | Diluted by more observations |
| 5. Variance in expected returns among rules | Lower variance → larger bias | Homogeneous universes = worse |

### Quantitative Evidence (from Aaronson's simulation experiments)
- **2-month history** (testing best of 256 rules): bias = 200%+ annual return overstatement. Useless.
- **100-month history** (~8.3 years) testing best of 256: bias ≈ 18% annual return overstatement.
- **1,000-month history** (~83 years) testing best of 256: bias < 3% annual return overstatement.
- **Critical insight**: after testing ~30 rules, the marginal increase in bias from testing *more* rules flattens out quickly (at sufficient sample sizes). Testing 256 rules is not much worse than testing 30, if you have enough data. The enemy is few observations, not a large rule universe.
- **Sample size threshold**: at only 2 months of observations, data mining does not work at all — the best of 256 rules has the same expected return as a randomly chosen rule. The rule's observed performance is pure noise.

### Data Mining Is Still the Right Approach
- **The best observed rule has higher expected return than a randomly chosen rule** — proven mathematically (White) as sample size approaches infinity.
- Data mining is compelled by the absence of theory: without theory to derive which rule to test, you must test many and select the best.
- The error is not data mining itself; it is treating the winner's observed performance as an unbiased estimate of future performance. It is not. It is always upward biased.

### Out-of-Sample Testing
- **Single IS/OOS split**: simple but has fundamental weaknesses:  
  (1) OOS data can only be used *once* — after one use, it is "contaminated" and provides no further unbiased estimates; (2) the IS/OOS split ratio is arbitrary with no theoretical basis; (3) reduces data available for mining.
- **Alternating/checkerboard patterns**: ensures IS and OOS data come from all market regimes — better than early/late split.
- **Walk-forward testing** (Pardo's WFA): the recommended solution for non-stationary markets. Moving window produces multiple independent OOS estimates (folds), allows confidence intervals, and adapts to changing market dynamics.

### Walk-Forward Testing: Key Details
- Each fold = train (IS) + test (OOS) window, walked forward without OOS overlap.
- Multiple folds → multiple OOS performance estimates → variance computable → confidence interval producible.
- Moving window adapts to non-stationary markets — this is why it is *especially* attractive for financial markets.
- Referenced in Pardo, De La Maza, Katz/McCormick, and Kaufman as the industry consensus approach.

### White's Reality Check (WRC)
- The gold standard for testing statistical significance of a rule discovered by data mining.
- Uses bootstrap method to derive the sampling distribution for the *best of N rules*, under H₀ that all rules have zero expected return.
- Produces a p-value that accounts for the full data-mining exercise, not just a single rule.
- Requires retaining the full interval-by-interval return history for every rule tested during the optimization — this data is almost always discarded but is essential.

### Warnings
- If only 2 months of data are used, testing more rules produces no improvement in the expected return of the best rule. Testing 256 combinations is as good as testing 1. **Sample size is everything.**
- "Out-of-sample performance deterioration" is not primarily a sign that markets have changed. It is primarily a sign of data-mining bias reverting to the rule's true expected return.
- Searching broadly (many parameters, many combinations) without adequate observations guarantees fool's gold — rules that fit the past by luck.

### Applicability to myquant
- Our 3-leg exit parameter space (R multiples per level, tick offsets, stop ratchets, target modes per trade type) is a large combinatorial space. Each staged sweep increases the data-mining bias.
- To control bias: maximize observations (use 2010–2025 data), use rolling WFT (not single IS/OOS split), and always evaluate the *OOS* result — not the IS winner's observed performance.
- Target ≥100 observations per OOS bucket. Monthly P&L = 1 observation. Individual trades = 1 observation each. For a daily simulator, a 3-month OOS bucket on ES futures should produce enough trades.
- Single 2021 IS / 2022 OOS is definitionally not WFA — it produces a single, unrepeatable OOS estimate that cannot be used again. Use rolling walk-forwards instead.

---

---

# Kaufman — Library Tenets (Trading Systems and Methods, 5th ed.)
**Source:** *Trading Systems and Methods*, Perry J. Kaufman (Wiley, 2013, 5th ed.)  
**Extracted for:** `myquant` — step-forward (walk-forward) testing procedure, parameter selection, testing integrity

---

## Kaufman — Chapter 21: System Testing

### Core Tenet
System testing is the validation of a prior idea, not a discovery process. If you test all combinations of parameters hoping to find something that works, you are not validating — you are overfitting. Define expectations first; use testing only to confirm or refute them.

### Step-Forward (Walk-Forward) Testing: The Procedure
Kaufman calls it "step-forward testing" (also: walk-forward testing, blind simulation). Parallels real-world use: choose parameters on past data, apply forward.

Steps:
1. Select total test period (e.g., 20 years: 1988–2007).
2. Select IS window size (e.g., 2 years).
3. Test first IS window (1988–1989); select best parameters.
4. Apply those parameters to the next OOS window (e.g., 6 months of 1990). Record OOS performance.
5. Slide window forward by the OOS step (6 months); repeat from Step 3.
6. Final result = accumulated OOS performance across all folds.

### Short-Term Bias in IS Windows
- If the IS window is too short, the optimizer cannot distinguish between parameter values. Sign: optimal parameter jumps erratically (e.g., best moving average period oscillates 10 → 50 → 15 across successive folds).
- **Fix**: increase IS window (e.g., from 2 years to 5 years).
- Short IS windows bias toward faster systems — slow systems don't accumulate enough trades to be evaluated.

### OOS Data Integrity
- OOS data has **no second chance**. Once used, it is contaminated.
- "You cannot fix anything once you have used the out-of-sample data. That is called feedback. The result is always overfitting." — Kaufman, p.918.
- OOS performance is expected to be approximately **50% of IS performance** for a good system (information ratio drops from 2.0 to 1.0). This aligns with Pardo's WFE ≥ 50%.

### Parameter Selection Rules
- Use **percentage-increment spacing** for parameter ranges, not equal steps. Reason: the difference between 49 and 50 days is only 2%, while the difference between 2 and 3 days is 50%. Equal steps over-represent long-period behavior.  
  Recommended sequence: ×1.5 multiplier per step (1, 1.5, 2.2, 3.3, 5.0, 7.6, 11.4…).
- Test parameters in **order of importance**: primary structural parameter first (e.g., trend period), secondary indicator second, risk control (stops) last.
- Sequential optimization: test one parameter at a time, fixing the others. Reduces n₁ × n₂ × n₃ to n₁ + n₂ + n₃ — massive reduction. Risk: may miss the true peak when parameters interact; use seeding to verify.

### Selection Criterion: Robustness over Peak
- The best result is the **most robust parameter set**, not the one with the maximum profit.
- "The best historic results often come from overfitting the data, and is a poor choice." — Kaufman.
- Prefer a parameter region where performance is good across a range of values over a single-point peak.

### Data Segmentation Options (from most to least common)
1. First 50% IS / last 50% OOS — simple; suffers if market regime changes in second half.
2. Alternating fixed periods — better coverage of regimes; slightly complex.
3. Alternating random periods — most robust; requires commitment before seeing results; each strategy gets its own unique test data.

### Warnings
- Optimization without a prior hypothesis is not validation — it is exploration, and exploration produces overfitting.
- Once you look at OOS data, the feedback loop is open. There is no way to close it again on that data.
- More parameters → exponentially more tests. Compute the number of tests before running. Limit parameter ranges to what is *logically defensible*, not what is computationally feasible.

### Applicability to myquant
- Use 2-year IS / 6-month OOS as the starting structure for ES futures (fast strategy). Verify empirically that the best IS parameter does not jump erratically across folds.
- Apply percentage-increment spacing to all continuous parameters (R multiples for PB levels, tick offsets).
- Test the primary structural parameter first (which trade type is in play), then exit mode parameters, then stop ratchet triggers.
- OOS performance at 50% of IS performance is acceptable. Below 25% (Pardo: WFE < 25%) = suspect.

---

---

# Van Tharp — Library Tenets
**Source:** *Trade Your Way to Financial Freedom*, Van K. Tharp (McGraw-Hill, 2nd ed.)  
**Extracted for:** `myquant` — R multiples, expectancy, position sizing framework

---

## Van Tharp — Chapter 6: Expectancy and R Multiples

### Core Tenet
The fundamental performance metric is not win rate — it is **expectancy**: the average amount made per dollar risked, measured in R multiples. Win rate alone tells you almost nothing about system quality.

### R Multiples — The Universal Unit
- **R** = initial risk on a trade (the amount you would lose if the trade is stopped out immediately after entry).
- All trade outcomes are expressed as R multiples:
  - A $1,000 profit when 1R = $500 → +2R win
  - A $1,000 loss when 1R = $500 → –2R loss (blowup; should be caught)
- Expressing trades in R multiples removes position size effects, making all trades comparable.

### Expectancy Formula
```
Expectancy = (Win_Rate × Avg_Win_R) − (Loss_Rate × Avg_Loss_R)
```
- Expectancy is the average R earned per trade, over many trades.
- A system with 30% win rate can still have positive expectancy if avg win = 5R and avg loss = 1R:  
  0.30 × 5R − 0.70 × 1R = 1.5R − 0.7R = **+0.8R per trade**
- A system with 70% win rate can have negative expectancy if avg win = 0.5R and avg loss = 2R:  
  0.70 × 0.5R − 0.30 × 2R = 0.35R − 0.6R = **−0.25R per trade** (net loser)

### The Six Keys to System Performance

| Key | Variable | Notes |
|-----|----------|-------|
| 1 | Reliability (win rate) | Least important alone; people overemphasize it |
| 2 | Relative size of wins to losses (R multiples) | Critical; interacts with win rate to form expectancy |
| 3 | Cost of trading (commissions + slippage) | Subtracts from every trade; destroys small-edge systems |
| 4 | Opportunity (trade frequency) | Same expectancy × more trades = faster compounding |
| 5 | Capital (account size) | Sets the floor on survivable drawdowns |
| 6 | Position sizing | The dominant lever for long-run account growth |

### Minimum Sample Requirements
- Expectancy calculated from fewer than **100 trades** is unreliable — too much random variation.
- A system with expectancy > 0.50R per trade and ≥100 trade sample is a good long-term system (Van Tharp's general guideline).
- Expectancy can be positive but the account can still lose money if position size is too large. Never conflate a positive expectancy with certainty of profit in any given trade sequence.

### Position Sizing as the Growth Lever
- Two identical systems (same signal, same expectancy) can produce wildly different equity curves based solely on the position sizing model.
- Position sizing determines *how many units* to trade per signal. Trading too large amplifies both wins and losses — and sequence risk makes over-sized drawdowns non-recoverable.
- Key formula: `Position size = (Risk % × Account Equity) / (1R in dollars)` → ensures every trade risks the same % of equity regardless of 1R size.

### Applicability to myquant
- For every simulated trade, compute R multiple: `(P&L of trade) / (1R = E1 entry stop distance in dollars)`.
- Expectancy = mean R across all trades. Any setup with negative expectancy should not be traded regardless of win rate.
- Do not evaluate any setup on fewer than 100 trades; with a 5-day-per-week ES futures session count, 100 trades ≈ 3–6 months of trading (depending on setup frequency).
- Use constant fraction position sizing in all simulations (e.g., risk 1R = 1% of equity) to produce realistic equity curves. The simulator's current R-level framework already provides the 1R reference.
- For blended (multi-leg) trades, recompute 1R from the blended entry price to a consistent stop level for the expectancy calculation.

---

---

---

## Kaufman Guide — Chapters 4, 8, 10, 11, 15

**Source:** *A Guide to Creating a Successful Algorithmic Trading Strategy*, Perry J. Kaufman (2016)
**Extracted for:** `myquant` — robustness definition, parameter selection, testing discipline, volatility filters, market classification

---

## Kaufman Guide — Chapter 4: Why Should I Care about "Robust"?

### Core Tenet
A robust system must produce profitable results across **different markets** and **different time periods** using the **same unmodified rules**. Testing on one instrument for one period proves nothing. The standard benchmark is ≥70% of all parameter combinations profitable (net of costs).

### Key Rules / Thresholds
- **70% profitable tests** across the full parameter space = "great success." Very few strategies reach this; long-term trend following is one that can.
- **Two dimensions of robustness** — both must be satisfied:
  1. *Percentage profitable*: ≥70% of tests make money (50% minimum with clear clustering).
  2. *Smooth surface*: Results transition gradually as parameters change. A chart showing profit vs. parameter should look like a relief map — no isolated spikes surrounded by losses.
- Kurtosis of the optimization result distribution: normal kurtosis ≈ 3 (bell curve). Kurtosis >6 indicates a dangerously narrow peak = overfitting signal.
- **Do not pick the single best parameter** result. It is the most likely to underperform because it benefited from a price shock or unusual market move that will not repeat.
- **Trade ≥3 parameter sets equally** (e.g., 30/60/120-day trends, equal capital allocation). More subsystems → closer to the population average; give up peak returns but eliminate worst outcomes.

### Nonlinear (Percentage-Spaced) Parameter Testing
- Linear spacing (e.g., 10, 20, 30, ... 200 in steps of 10) **overweights slow trends**: the difference between 190 and 200 is 5%, but between 10 and 20 is 100%.
- Correct approach: each step is a **fixed percentage** increase. Multiplying by 1.5 gives: 20 → 30 → 45 → 67 → 101 → 151.
- Kaufman's practical shorthand for moving average strategies: **30, 60, 120 days** (equal ratio spacing, covers slow/medium/fast without bias).

### Warnings
- If the best-performing parameter set is a stark outlier from neighbors (spike in profit surface), **it is an artifact** of timing luck, not edge. Do not trade it.
- A system profitable in only 50/100 parameter tests with profits scattered randomly (not clustered) is not robust — it may just be chance.
- Defining the parameter range *after* seeing the results (cherry-picking the profitable window) is equivalent to feedback/cheating.

### Applicability to myquant
- myquant's current sweep covers a parameter range; ensure sweep plots show a smooth hill, not an isolated spike. If the optimal param jumps erratically across walk-forward folds, the IS window is too short (per Kaufman TSaM: extend IS).
- For stop/target sweeps (e.g., profit_target_r, stop_r), confirm that the optimal result is near the center of the profitable zone, not at an extreme edge.

---

## Kaufman Guide — Chapter 8: Searching for the Perfect System

### Core Tenet
Backtesting is confirmation, not discovery. You must start with a **sound premise** — a concept grounded in a real market mechanism (e.g., interest rate policy causes slow trends; mean reversion exists in noisy equity indexes). If the premise is wrong, more testing cannot fix it.

### Pre-Test Specification Checklist
All of the following must be defined **before** running any test:
1. **Sound premise** — what market phenomenon drives the edge (not "I noticed this pattern in the data").
2. **Parameter range** — define the range that fits the concept. For slow trend: 40–200 days. For short-term mean reversion: 3–15 days. Do not expand range after seeing results.
3. **Expected return profile** — many small wins + few large losses (mean reversion), or few large wins + many small losses (trend)?
4. **Applicable markets** — which markets should this strategy work on, and why? Single-market testing is risky because it may not include enough real-life events.

### How Much Data / How Many Trades Are Enough?
- **Sample error formula**: error = 1/√(number of trades).
- **Minimum acceptable**: 400 trades = 5% error. This is the floor for a short-term trader with 40 trades/year × 10 years.
- **Trend-following problem**: 200-day MA → ~5 trades/year → 50 trades over 10 years = 14% sample error. Not good enough. Mitigate with multi-market testing (same system, 10+ markets = 10× the trades).
- **4 possible test outcomes** — only Case 4 is acceptable: large majority of tests profitable, with results clustering and tapering smoothly at the edges.

### Parameter Selection
- **Single parameter set** = same risk as a single stock: highest potential return but also highest potential loss.
- **Two parameter sets**: smoother return, lower risk; average return, much lower worst case.
- **Three or four sets**: more stable; this is the target. Kaufman uses 30/60/120 as the standard trio.

### Warnings
- If 20% of tests are profitable (even if the best result is extraordinary), the strategy is not robust.
- If profitable results are scattered randomly — not contiguous — the edge is random coincidence.
- Statistically, if you run 100 tests, the top 5 are likely to be successful purely by chance. Cherry-picking them is a trap.

### Applicability to myquant
- The MC breakout premise (micro-channels represent institutional order flow) is a sound market mechanism. The test design (parameter sweep over threshold/length/target/stop) follows the correct approach.
- Trade count concern: with 3–5 setups/week on ES, ~200–250 trades/year. Over a 3-year test that's 600–750 trades = ~3.7% sample error — acceptable. But a 1-year IS window gives ~200 trades = 7% error; needs to be acknowledged in WFA confidence intervals.

---

## Kaufman Guide — Chapter 10: Testing — The Fork in the Road

### Core Tenet
Testing is a discipline, not just a computation. The fork: one path produces a robust, honest validation; the other path produces an overfit system that fails live. The difference is **whether you allow feedback** from test results to change your rules.

### The Non-Negotiable Rules
| Rule | Statement |
|------|-----------|
| More data is better | No such thing as "too much data." The more, the better. |
| Leave data for validation | Set aside OOS data before any development. Once used, it is contaminated. |
| Pre-specify evaluation criteria | Decide *in advance* what metric you will use to judge success (e.g., IR, % profitable). |
| Percentage-spaced test values | Use multiplicative spacing — 40, 60, 90, 135 — not linear. |
| Don't shotgun | Define the parameter range in advance based on the premise. If those values fail, the concept fails. |
| Reject marginal improvements | A new rule must improve the *average* of all tests, not just peak one. |
| **No feedback from validation data** | Once validation data is tested, the result is final. Iterating on it is cheating. |

### Robustness Measurement
- **Primary measure**: % of parameter combinations that are profitable.
- **Target**: 70% profitable. "I can be convinced that 50% is okay if there is a smooth pattern and a clustering of good returns."
- If you are testing 20 trend speeds × 10 stops × 10 profit targets = 2,000 tests: target is 1,400 profitable.
- Do NOT optimize for the single best IR; optimize for the system that maximizes the % of profitable test combinations.

### The Feedback Trap
- Feedback = reviewing losing trades and adding a rule to avoid them. This is cheating.
- Every rule added to fix a specific event will fail in a different way next time (e.g., the next bad day will be 3.1%, not 2.9%).
- "If you fiddle with the data, or create rules to avoid historic losses, then future losses will be entirely your fault."
- Canonical example: Long-Term Capital Management removed the data that showed Russian ruble risk, achieved 50:1 leverage on a "smooth" result, then lost everything on the exact event they had removed.

### Price Shocks — Hidden Danger
- Price shocks are defined as days where the daily range ≥ **2.5× the average daily range**.
- Backtests quietly benefit from fortuitous shock alignment. This cannot persist forward.
- Reasonable assumption: can expect only **50% of price shocks to be favorable** (not the 65%+ typical in IS performance).
- Adjustment: reverse the gains from the excess favorable shocks in your backtest returns. If that degrades results severely, the system is fragile.
- Most traders lose money because they underestimate price shock risk.

### Performance Measurement
- **Information Ratio (IR)** = AROR / annualized volatility (Kaufman's preferred metric).
- Simplified Sharpe (without risk-free rate): `IR = AROR / Annualized_Vol`.
- IR >0 = finished ahead despite drawdowns; IR >1.0 = smooth upward return; IR >3.0 = likely a programming error (look-ahead bias, missing costs).
- **Calmar Ratio** (AROR / max drawdown) understates future risk because drawdowns grow with time.

### Forward Performance Expectations
- **Expect IR to drop ~50% OOS** from the IS result. An IS IR of 2.0 → expect ~1.0 OOS.
- Expect another drop in live trading. Err on the side of caution; never overleverage based on IS results.
- **General rule: expect twice the risk going forward** (not half the return — the return can persist, but the volatility of the return path is higher).

### Data Quality
- **Use "dirty" data** for at least some testing: data with real noise, bad ticks, and execution uncertainty. A system that only profits on perfectly scrubbed data will fail in production.
- Back-adjusted futures/stocks data: cannot compare absolute highs/lows between periods; percentage-based rules can produce incorrect signals; very old data may go negative.

### Applicability to myquant
- The IS window established (≥1 year, targeting ~200 trades) is on the low end of Kaufman's confidence; supplement with multi-symbol robustness tests (ES + NQ + RTY) to multiply trade count.
- Validate the price shock exposure: flag all bars where bar range ≥ 2.5× 20-bar avg range. Report how many of those were entered and what side they went. This is a risk disclosure item for any funded account.
- IR is already the preferred metric in myquant (over raw P&L). Calibrate expectations: IS IR of 1.5 → plan for live IR of ~0.7–1.0 as realistic.
- No feedback from the OOS window of any given WFA fold — this is locked by the rolling WFA structure.

---

## Kaufman Guide — Chapter 11: Beating It into Submission

### Core Tenet
When test results disappoint, there are exactly two responses: (1) make a generalizable improvement that lifts all results, or (2) overfit the system and guarantee it will fail live. The choice defines whether you become a successful system trader.

### What Is an Acceptable Improvement?
A rule change is acceptable **only if** it improves results broadly and uniformly:
- It improves the **average** across the full parameter space, not just the peak.
- It improves **multiple markets**, not just the one where you found the problem.
- It is **generalizable**: based on a principle of market behavior (e.g., high volatility → higher risk), not on a specific historical event.
- Visually: the optimization result curve *shifts up uniformly* (the "good" pattern), rather than *growing a narrow spike* while the wings worsen (the "bad" pattern).

### Detecting Overfitting in Results
- Plot profit vs. parameter value. A **normal kurtosis** result (≈3) shows a smooth hill — acceptable.
- Kurtosis **>6** = dangerously narrow peak = the rule is targeting one specific market condition, not a general property.
- The "bad" change concentrates profits in the center and makes the edges worse. The "good" change improves everything, including the worst results.

### Use the Average, Not the Peak
- The average of all parameter combinations across the defined range is the **best forecast of future performance** — not the single best parameter.
- Why: the best result in any IS test benefited from some unusual event (price shock, favorable timing). That event will not repeat exactly.
- Implementation: trade ≥3 equally-weighted parameter sets spanning the range (e.g., 30-day, 60-day, 120-day trend). This approximates trading the average.
- "The more subsystems, the closer you get to the average."
- Average results are not glamorous but they are realistic. One of the goals of system development is to accurately predict both returns AND risk in real trading.

### Generalizable Rules — The Volatility Toolkit
Rules based on volatility (ATR / annualized vol) are the most generalizable because they scale with market conditions:

| Volatility Level | Observed Behavior | Recommended Action |
|-----------------|------------------|--------------------|
| Annualized vol >45–50% | High risk; returns are high but IR is low | Short-term: skip the trade. Long-term: reduce exposure (equivalent to taking profits and waiting for vol normalization). |
| Annualized vol <15% | Lethargic market; meandering sideways | Poor environment for all strategies; expect lower trade frequency and returns. |
| Vol spike >2.5× average (intrabar) | Price shock / news event | Mean reversion opportunity for equity indexes; potential trend entry for interest rates. |

### Squeezing the Life Out of a System — The Wrong Path
- "Squeezing" = iterating on specific losing periods, adding rules to fix specific scenarios, until the backtest looks perfect.
- Each squeeze removes one historical problem and creates a new hidden sensitivity.
- The correct endpoint: a system where 70%+ of parameter tests are profitable, results are smooth, improvement rules are generalizable, and the validation OOS confirms the IS picture.

### Applicability to myquant
- When evaluating next improvement (e.g., adding a higher-timeframe filter, or a volatility gate): measure its effect on ALL sweep cells, not just the current best. If it helps the best cell but hurts 30% of the rest, reject it.
- Volatility filter is high-priority: ES intraday vol can spike significantly on FOMC/NFP days. A rule that skips entries when 20-bar ATR > X × baseline ATR is generalizable and should improve the average across all parameter combinations.
- For 3-leg implementation: the scale-in concept is generalizable (based on pullback structure), not event-specific, so it qualifies as a legitimate rule addition. Verify by checking that it improves average across all sweep results, not just the current best parameter.

---

## Kaufman Guide — Chapter 15: Matching the Strategy to the Market

### Core Tenet
Markets have measurably different price structures (trending vs. noisy). The **efficiency ratio** quantifies this. Strategy type must match market structure: trend-following belongs in efficient (directional) markets; mean reversion belongs in inefficient (noisy) markets.

### Efficiency Ratio Definition
```
Efficiency Ratio (ER) = |Net price change over n days| / Sum(|daily changes|) over n days
```
- **ER = 1.0**: Price moved in a perfectly straight line (maximum trend efficiency).
- **ER ≈ 0**: Price went up and down in equal amounts — no net progress (maximum noise).
- Practical range: most markets fall between 0.15 and 0.30 (lower = noisier).
- Kaufman uses a 20-day lookback as the standard calculation window.

### Market Classification by Efficiency Ratio

| Market Category | Typical ER | Strategy |
|----------------|-----------|----------|
| Short-term interest rate futures (ED, Euribor, Eurobund) | Highest (~0.25–0.30) | Trend following |
| High-tech growth stocks (TWTR, NFLX, GOOGL, BIDU, AAPL) | High (~0.24–0.27) | Trend following |
| Commodity futures (gold, crude oil, nat gas) | Medium | Context-dependent |
| NASDAQ-100 (NQ) | Medium-high | Trend with caution |
| S&P 500 (ES/SPY) | Medium-low | Mean reversion / fade moves |
| Russell 2000 (RTY) | Medium-low | Mean reversion |
| Mature large-cap stocks (XOM, WMT, AXP) | Low (~0.20) | Mean reversion |

**Key finding**: S&P has *higher* noise than NASDAQ (lower ER), making NASDAQ slightly more trend-amenable. Interest rates have the highest ER of all futures — best trending markets.

### Strategic Implication for Futures
- Short-term interest rates → **follow the breakout** (trend direction).
- Equity index futures → **fade the breakout** (mean reversion; sell an upward breakout, buy a downward one).
- "For most trading strategies, we would want to go in the direction of the breakout for the short-term interest rates, and fade the move for the equity index markets."

### New/Inactive ETFs and Markets
- An inactive ETF dominated by a few commercial interests → unusually sustained moves on low volume → temporarily high ER → good short-term trending opportunity. Monitor new markets for this.

### Applicability to myquant
- ES (S&P E-mini) has a **lower efficiency ratio than NASDAQ** — it is structurally noisier. This supports the micro-channel mean-reversion / pullback entry model: the ES does not trend smoothly intraday; it reverts after breakouts.
- The myquant strategy (fade the breakout / buy the pullback) is correctly matched to ES's market structure per Kaufman's framework.
- When extending to NQ or RTY, recalculate the efficiency ratio per instrument before assuming the same strategy parameters apply. NQ is less noisy and may favor larger profit targets and tighter stops.
- Consider computing a rolling efficiency ratio on each instrument and using it as a filter: only take mean-reversion trades when the rolling ER is below a threshold (e.g., <0.20 = high noise = good for fading).

---

## Cross-Chapter Summary: Key Thresholds

| Metric | Threshold | Source | Notes |
|--------|-----------|--------|-------|
| WFE (OOS/IS profit ratio) | ≥ 50–60% | Pardo | Research-demonstrated minimum |
| WFE | < 25% = suspect | Pardo | Likely unsound or overfit |
| OOS profitable windows | ≥ 60% | Pardo | 63% called "convincing" |
| Min trade sample | ≥ 30 absolute min | Pardo | More always better; include L+S |
| Min trade sample for expectancy | ≥ 100 trades | Van Tharp | Below 100 = unreliable |
| Expectancy threshold | > 0.5R per trade | Van Tharp | General guide for good long-term system |
| OOS window size | 25–35% of IS | Pardo | Starting point; refine empirically |
| OOS/IS performance ratio | ~50% expected | Kaufman TSaM | Info ratio drop from 2.0→1.0 = good result |
| IS window (fast strategy) | 1–2 years | Pardo | ES futures qualifies as fast |
| IS window (slow strategy) | 3–6 years | Pardo | — |
| WFA total length | ≥ 10–20 years | Pardo | Target 20–60 walk-forwards |
| Degrees of freedom consumed | < 10% of data points | Pardo | Practical guide |
| Short-term bias signal | Optimal param jumps erratically across folds | Kaufman TSaM | Fix: increase IS window |
| Data-mining bias (100 obs, 256 rules) | ~18% annual return overstatement | Aaronson | Manageable with proper WFT |
| Data-mining bias (2 obs, 256 rules) | 200%+ overstatement | Aaronson | Useless — sample too small |
| Rule universe threshold | ~30 rules = bias plateau | Aaronson | Testing 256 not much worse than 30 with enough data |
| Real-time deviation alert | < 50% or > 150% of eval profile | Pardo | Triggers investigation, not halt |
| Reoptimization cadence | = OOS window length | Pardo | Pre-emptive; do not wait |
| Robustness threshold | ≥70% of all parameter tests profitable | Kaufman Guide | 50% acceptable if results are clustered smoothly |
| Kurtosis of optimization surface | ≤6 (normal ≈3) | Kaufman Guide | >6 = overfitted; narrow spike = danger signal |
| Parameter spacing | Multiplicative (×1.5 or ×1.25) per step | Kaufman Guide | Linear spacing biases toward slow-trend results |
| Min parameter sets to trade | ≥3, equally weighted | Kaufman Guide | e.g., 30/60/120-day; approximates average performance |
| Sample error (min acceptable) | 5% = 400 trades | Kaufman Guide | Formula: 1/√N; trend systems with 5 trades/yr need 10+ markets |
| Forward risk expectation | 2× the IS risk estimate | Kaufman Guide | IR drops ~50% OOS; drops again in live trading |
| Information Ratio interpretation | IR >1.0 = smooth return; IR >3.0 = likely error | Kaufman Guide | Preferred over Calmar Ratio; use for strategy comparison |
| Price shock definition | Daily range ≥ 2.5× 20-bar avg range | Kaufman Guide | Expect ≤50% favorable shocks forward; adjust IS returns |
| Volatility filter — skip trade | Annualized vol >45–50% | Kaufman Guide | Short-term traders; long-term: reduce exposure instead |
| Efficiency ratio — trend signal | Higher ER → trend; lower ER → mean reversion | Kaufman Guide | ES has lower ER than NQ; interest rates have highest ER |
| ES market structure | Lower ER than NASDAQ; fade-the-breakout favored | Kaufman Guide | Supports myquant pullback / mean-reversion approach |
