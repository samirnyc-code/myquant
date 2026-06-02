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

## Cross-Chapter Summary: Key Thresholds

| Metric | Pardo Threshold | Notes |
|--------|----------------|-------|
| WFE | ≥ 50–60% | Research-demonstrated minimum for robust strategy |
| WFE < 25% | Suspect — likely unsound or overfit | — |
| OOS profitable windows | ≥ 60% | Example: 63% = "convincing result" |
| Min trade sample | ≥ 30 (absolute min) | More is always better; include long + short |
| OOS window size | 25–35% of IS window | Starting point; refine empirically |
| IS window (fast strategy) | 1–2 years | ES futures qualifies as fast |
| IS window (slow strategy) | 3–6 years | — |
| WFA total length | ≥ 10–20 years | More walk-forwards = more statistical reliability |
| Degrees of freedom consumed | < 10% of data points | Practical guide; keep as low as possible |
| Real-time deviation alert | < 50% or > 150% of eval profile stat | Triggers investigation, not automatic halt |
| Reoptimization cadence | = OOS window length | Pre-emptive; do not wait for deterioration |
