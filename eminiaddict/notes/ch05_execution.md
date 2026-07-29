# Ch 5 — The 90 Percent Factor (Executing Your Trade)

## Summary (3-5 lines)
This chapter covers order entry and trade management ("where the rubber meets the road"). The two overriding priorities for the MM trader are (1) achieving reduced-risk trades and (2) riding the coattails of Smart Money. "Job One" is to make every trade a *free trade* (all significant risk removed ASAP), which requires trading multiple contracts (2 minimum) and taking half off at Target 1. Risk is hard-capped at 1% of account per trade; a 2:1 reward-risk ratio is the bare minimum to enter. The chapter details how to preload a DOM with bracket/OCO presets, how to enter with limit orders at HWB, how to endure "taking the heat" without moving stops, stop-out escalation (one = yellow flag, two consecutive = red flag / stop for the day), and single-contract all-in/all-out fallbacks for small accounts. "90 percent" = execution/management is ~90% of the trader's endeavor.

## Key concepts & definitions
- **Two overriding priorities for the MM trader:** (1) Achieving reduced-risk trades, and (2) Riding the coattails of Smart Money.
- **Job One:** achieve *free trades*. "Nothing is more important — nothing."
- **Reduced-risk (RR) trade:** "a trade in which all significant risk is taken off the table at the earliest possible time." Goal: reduce capital risk to nothing but commission cost and slippage as soon as possible after entry.
- **Free trade:** a trade whose maximum potential loss has been moved to ZERO (e.g., +6 booked, stop moved to −6: +6 − 6 = 0).
- **Cardinal rule for trading with free:** "take half the position off after the first target is hit."
- **Scared money:** any risk greater than 1% of total account size on any one trade. Trading scared money prevents following MM rules strictly, consistently, and without emotion.
- **Round trip:** entering and exiting a trade; on a scratch, total loss = commission cost.
- **Taking the heat:** enduring time underwater — both real clock time and (longer-feeling) perceived time — after entry while price moves against the trade. A career in trading cannot be achieved without it.
- **Emotional capital vs financial capital:** preserving financial capital underpins emotional capital; both essential. Free trades preserve both.
- **Overtrading (two kinds):** (1) placing too many trades over a time frame; (2) the "insidious" kind addressed here — succumbing to post-entry temptations: moving stops away from initial settings, or exiting early before Target 2. Both are a "quick click-drag-and-drop with the mouse."
- **Crossing the starting line:** the book's vehicular metaphor for "pulling the trigger" / placing a trade.
- **Running off the road:** a maximum-loss / full stop-out trade (vs a breakeven "scratch" = a minor fender bender / ding).
- **The 90 percent factor:** placing trades at the right price on solid technical data and managing them with strict discipline is ~90% of the trader's endeavor ("where the rubber meets the road"). The exact percentage "might be subject to debate."

## Rules / setups / mechanics

### Priorities & "Job One"
- Must achieve free trades; requires trading **multiple contracts, two contracts being the minimum**.
- Take half the position off after Target 1 is hit → moves the trade to free.

### Example 6E preset levels (long trade, entry 1.3590)
```
Initial stop  = −12 pips
Target 1      = +6 pips
Moved stop    = −6 pips
Target 2      = −23 percent Fibonacci level
```

**Scenario 1 — Maximum Profit**
1. Two contracts bought at 1.3590
2. One contract sold at 1.3596 (Target 1)
3. Stop moved to −6 pips  → **free trade achieved here** (+6 − 6 = 0)
4. One contract sold at −23 percent target

**Scenario 2 — Breakeven (Scratch)**
1. Two contracts bought at 1.3590
2. One contract sold at 1.3596 (Target 1)
3. Stop moved to −6 pips (free trade achieved)
4. One contract sold at 1.3586 (moved stop)
- Total loss = commission (round trip). If slippage takes stop to −7 instead of −6, loss increases by **$12.50** (dollar value per pip for 6E).

**Scenario 3 — Maximum Loss**
1. Two contracts bought at 1.3590
2. Two contracts sold at 1.3582 (initial stop)
- Loss = −24 pips (12-pip stop × 2 contracts) + commission = **$300 (24 × $12.50)** + commission.

### Risk — the 1% rule (Step Zero: calculate risk-reward BEFORE anything)
- "no trade should be entered without both risk and reward expressed specifically in hard, cold numbers."
- Competing views: some risk up to 3%, some ≤2%. **MM methodology: risk for any one trade should never exceed 1% of total account size.** Anything greater = scared money.
- **Maximum Risk = Account size × .01.**
  - $10,000 → $100; $20,000 → $200; $50,000 → $500. (Commissions need not be included.)
- 6E is $12.50/pip; two contracts at −12 pips = $300 max loss (12.50 × 8 × 2 [as printed]; also given as −24 × $12.50 = $300). $300 = 1% of $30,000 → **two 6E contracts require account ≥ $30,000.**
- Under $30,000: either (1) trade one contract all-in/all-out, or (2) trade two contracts of the half-size **E-mini EUR/USD (E7) = $6.25/pip**. Also **E-micro EUR/USD (M6E) = $1.25/pip.**

### Reward
- All-in/all-out = simplest (one target). Multicontract = more complex (multiple targets).
- Universal rule: **a profit target will always be set at the −23 percent Fibonacci level**, whether 1 or 21 contracts. Multicontract trades have ≥1 additional target; all-in/all-out has "nothing but a 123 percent target" [text as printed], but in all cases a −23 percent target is present.

### Risk-reward calculation (Figure 5.1 worked example)
- Entered long, 2 contracts at **1.3130** (HWB from Fib low 1.3091 → high 1.3168). −23% line = **1.3186**.
1. Initial stop −12 pips (−12 × 2 = −24 pips max risk)
2. −24 × $12.50 = **$300 max risk**
3. 1.3186 − 1.3130 = 0.0056 = **56-pip** differential (HWB → −23% at Target 2)
4. 56 × $12.50 = **$700** profit for contract sold at Target 2
5. $700 + (6 × $12.50) = **$775** total profit (Target 1 +6 and Target 2 +44 as printed)
6. 775 / 300 = **2.5:1 risk-reward ratio**
- Naming: reward on top, "risk" named first (to force attention to risk).
- **Acceptability thresholds:** 2:1 generally acceptable; some enter 1:1 or smaller; 2:1, 3:1, 4:1 widely worthy. **In MM trading, 2:1 is the bare minimum.**
- Minimum account for $300 risk = $300 / .01 = **$30,000**. Note: a losing trade drops the balance below $30k and prohibits further two-contract trades, so keep balance somewhat above $30,000 for maneuvering room.
- Psychology: a 1% full stop-out on $30k → balance $29,700 ("not too big of a deal") — precisely why it avoids scared money.

### Preparing the DOM
- Don't recompute the 6-step risk-reward every trade; instead build DOM order presets per instrument ("know your instrument," "know your risk-reward ratios").
- DOM requirements: **bracket orders in OCO format** (execution of one part cancels the other), multiple profit-target specs, and ability to move initial stops to a specified level after first targets hit.
- 6E preset entries: initial stop −12 pips; Target 1 = one contract at +6 pips; move 2nd contract's stop to −6 pips after T1; number of contracts = 2.
- Target 2 must be entered in **pips, not a Fib level** → pick a generic default. Example default: **one contract at +25 pips** for Target 2. Adjust the +25 default after each entry if needed; only extreme volatility/speed prevents adjusting before it executes. (Example assumes +25 pips = the −23% level, so no adjustment.)
- Save preset "for the 6E and only the 6E." Each instrument gets its own DOM with unique presets.

### Crossing the Starting Line (entry)
- **MM traders always use limit orders, never market orders** — picky about price, tough negotiators.
- Sequence: wait for a low and a high to be clearly established → draw Fibonacci retracement → wait for retracement to **HWB** → place a limit order **at or near HWB**.
- Figure 5.1: 6E order placed at **1.3130**. DOM auto-places stops/targets and moves stop after T1; trader's job is then done ("sit back and watch").
- **Three simple steps for order entry:**
  1. Calculate risk-reward ratio.
  2. Place limit order with DOM preset.
  3. **SOH (sit on hands)** — wait for fill, let the trade play out.

### DOM execution walkthrough (max profit)
1. Limit executed, 2 contracts bought at 1.3130; stops both at 1.3118 (−12); T1 at 1.3136 (+6); T2 at 1.3155 (+25).
2. One contract sold at 1.3136 (T1); first stop canceled; second contract's stop moved to 1.3124 (−6).
3. One contract sold at 1.3155 (T2); stop canceled.
4. $12.50 × (6 + 25) = **$387.50 profit before commission.**
- All four steps executed automatically (preconfigured DOM); no further intervention after entry.

### Discipline / taking the heat
- Post-entry, price does one of three things: stays at entry (rare, sluggish markets), moves in favor, or moves against (often felt as "the norm").
- **Commit to let the DOM take over after entry. Stops set to a specific level should be allowed to trigger if hit. No trader intervention necessary or desired. "A rule is a rule."**
- When T1 hits: DOM immediately sells one contract (+6) and moves remaining stop to −6 at 1.3124 → max loss goes from −24 pips on two to ZERO → heat removed.
- **Letting profits run:** waiting for +25 (T2) takes much longer than +25... [for +6]; resist exiting early (e.g., taking +15 when goal is +25). "cutting losses short and letting profits run."
- Bailing before −23% violates a fundamental tenet and is only permitted with **solid technical evidence** that the market is reversing before −23% is hit.

### Running Off the Road (stop-out handling)
- **Breakeven / scratch trade** = fender bender; lose only commission; vehicle still road-worthy.
- **Maximum-loss / full stop-out** = running off the road; more serious damage → take extra caution.
- **One full stop-out** = not enough to remove you from the race, but raises a **yellow flag** (extreme caution reentering).
- **Second consecutive full stop-out** = **red flag** → many experienced MM traders take themselves out; for day traders, **stop for the day.** Prevents a downward spiral.

### When Multiple Contracts Just Aren't Possible (single-contract fallback)
- $10,000 account → max loss $100 = only **8 ES ticks or 6E pips.** Two contracts would mean **4-tick/4-pip stops** = much too tight (volatility hits ±4 "in the blink of an eye"); prohibited by sound money management.
- Fix: trade **one contract all-in/all-out.** 8-pip stop on one 6E = $100; 6-tick stop on one ES = $75. Both within the 1% rule.

**One-contract all-in/all-out 6E settings:**
```
Initial stop = −8 pips
Moved stop   = 0 pips after price hits +8 pips from entry
Target       = +25 (moved to Fibonacci −23 percent level after entry)
```
- R:R = **3.125:1** — max loss $100 (8 × $12.50), max profit $312.50 (25 × $12.50).

**One-contract all-in/all-out ES settings:**
```
Initial Stop = −6 ticks
Moved Stop   = 0 pips after price hits +6 ticks from entry
Target       = +25 (moved to Fibonacci −23 percent level after entry)
```
- R:R = **4.166:1** — max loss $75 (6 × $12.50), max profit $312.50 (25 × $12.50).

**$5,000 account:** full 6E/ES out of the question. Use **E-micro M6E ($1.25/pip)** — 8-pip full stop-out on two M6E contracts = **$20 ($1.25 × 16)**; 1% rule allows this on an account of only $2,000. Caveat: M6E liquidity is extremely limited (Smart Money trades full-size 6E), so **set initial stops much wider**, skewing R:R → paper-trade first in a simulated DOM. Note: $10,000 accounts can also use half-size **E7**.

## Figures / tables
- **Figure 5.1 — "6E Risk Reward"** (Source: thinkorswim®). Long entry 2 contracts at 1.3130 (HWB), Fib from low 1.3091 → high 1.3168, −23% line at 1.3186. Basis for the 2.5:1 worked calculation and the DOM execution walkthrough (stops 1.3118, T1 1.3136, T2 1.3155).

## Codifiable vs discretionary
**Codifiable (hard rules / numbers):**
- Max risk = Account × 0.01 (1% rule); 2:1 R:R bare minimum.
- Two-contract minimum to achieve RR; sell half at Target 1; move stop to make trade free (+6 → −6 = 0).
- 6E preset: stop −12, T1 +6, moved stop −6, T2 −23% Fib (default +25 pips). ES/6E one-contract fallback settings (stops −6 ticks / −8 pips; move to 0 after +6/+8; T +25 → −23%).
- Instrument values: 6E $12.50/pip, E7 $6.25/pip, M6E $1.25/pip; ES $12.50/tick (implied from $75 = 6 ticks).
- Account gates: two 6E contracts require ≥$30,000; keep buffer above; M6E two-contract needs only ~$2,000.
- Entry only via limit order at/near HWB; DOM as OCO bracket with auto stop-move.
- Stop-out escalation: 1 = yellow flag; 2 consecutive = stop for the day.

**Discretionary:**
- Exact "90 percent" figure ("subject to debate").
- Adjusting the +25-pip Target-2 default per trade to the actual −23% level.
- Bailing before −23% — allowed only on "solid technical evidence" of reversal (judgment call).
- Reentry caution after a yellow-flag stop-out; when to remove oneself for the day.
- Wider stops for illiquid M6E (amount not specified) → paper-trade first.
- "Taking the heat" — psychological skill, varies per individual.

## Cross-refs / open questions
- References future chapters: trader psychology, emotional capital, fear/greed dichotomy ("more will be said later").
- The −23 percent Fibonacci target is the core MM tenet (foundation stated here; measurement/drawing mechanics from earlier chapters — Fib low→high, HWB, −23% extension).
- Open/ambiguous printed items:
  - Reward section prints "all-in/all-out trades will have nothing but a **123 percent** target" — appears to be an OCR/typo for the −23 percent target (context says "In all cases, a −23 percent target will be present").
  - Step 5 of the Fig 5.1 calc labels the T2 contract "+44" ($700 = 56 × $12.50 corresponds to +56 pips from HWB; +44 likely refers to pips beyond the +6/entry framing) — reconcile against source PDF if exact pip attribution matters.
  - "$300 max loss (12.50 × 8 × 2)" printed alongside "−24 × $12.50 = $300" — the "× 8" form is inconsistent with the −12-pip stop; both yield $300 but the intermediate arithmetic differs. Not verified against original typesetting.
  - ES tick value stated implicitly as $12.50/tick (25 ticks × $12.50 = $312.50; 6 ticks × $12.50 = $75) — consistent internally.
