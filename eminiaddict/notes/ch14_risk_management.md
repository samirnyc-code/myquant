# Ch 14 — Risk Management (Advanced Trade Management)

## Summary
Chapter 14 is the money-management chapter. It frames the three biggest beginner mistakes (no stops, risking too much, overtrading) via two parables — "Bob the Trader" (the gambler who breaks every rule, gets rewarded early, then blows up) and "Curtis the Contractor" (the businessman with an innate risk/reward instinct). It then lays out concrete position-sizing math: risk a fixed **1 percent** of account per trade, size contracts from account × risk% ÷ (stop × $/tick), always use a stop, always have a target, trade in multiples of two contracts so you can scale out, and use "advanced trade management" (automated bracket profiles) to convert a live trade into a **free trade** or a **reduced-risk trade** after the first target hits. Core thesis: over-leverage is the single biggest reason ~90% of futures traders fail; correct sizing feels boring, and boring is the goal.

## Key concepts & definitions
- **Risk per trade** — calculated as a percentage of trading account size. Recommended starting point: **1 percent risk per trade** (low enough to survive mistakes, large enough to profit). Described as "the single most important ingredient to having a long and lasting trading career."
- **Advanced trade management** — trading-platform feature (on futures) that takes profit at predetermined levels automatically without trader input; predefined and executed automatically. Enables the two bracket profiles below.
- **Free trade** — a two-(or multiple-of-two)-contract trade started with a **−12-pip stop and +6-pip first target**; when +6 hits, the stop is auto-moved from −12 to **−6** (breakeven). Worst case afterward = stopped out at breakeven; only cost = slippage + commissions.
- **Reduced-risk (RR) trade** — a two-(or multiple-of-two)-contract trade started with a **−6-tick stop and +2-tick first target**; when +2 hits, the stop is auto-moved from −6 to **−4**. Worst case afterward = **−2-tick loss** plus slippage + commission.
- **Scaling out** — trading in even (multiple-of-two) contract counts so you can exit half at the first target; lets you find out quickly whether a trade works and removes anxiety.
- **Overleveraging** — risking more than the account dictates; named the single biggest reason traders fail. "Over 90 percent of traders fail" in futures; presumed mostly overleveraged.
- **Trading the news = gambling** — goal is to AVOID news volatility, not trade it. Know the night before WHEN scheduled announcements occur so you can stay out. "It is not the news that is important; it is the reaction to the news."

## Rules / setups / mechanics

### Position-sizing formula
Contracts = (Account size × % of portfolio at risk) ÷ (Stop loss in pips/ticks × $ value per pip/tick)

Worked from the three figures:
- **YM (E-mini Dow):** $40,000 × 1% = $400 risk ÷ (12-tick stop × $5/tick = $60) = **6 contracts**.
- **ES (E-mini S&P):** $40,000 × 1% = $400 risk ÷ (6-tick stop × $12.50/tick = $75) = **5 contracts**.
- **M6E (E-micro Forex):** $3,000 × 1% = $30 risk ÷ (12-pip stop × $1.25/pip = $15) = **2 contracts**.

### Stated rules / principles
1. Use a stop on **every** trade — no exceptions.
2. Risk a **fixed 1 percent** of account per trade (scales with account size: small account → small dollar risk; large account → still 1%).
3. Have a target on every trade (needed to know the risk-reward ratio).
4. Trade in **multiples of two contracts** so half can be scaled out.
5. Prefer futures over stocks — futures move away from S/R with high participation; stocks chop around entries, need wider stops, and trap you for days.
6. Pick one (or a couple of) instrument(s) and become an expert; do not scan hundreds of stocks.
7. Avoid news-event volatility; know the schedule in advance.
8. Never break your risk-management rules.

## Figures / tables
- **Figure 14.1 — YM Position-Sizing Calculator:** Account $40,000.00 / % at risk 1% / Stop 12 pips / $5.00 per pip → **6.00 contracts**.
- **Figure 14.2 — ES Position-Sizing Calculator:** Account $40,000.00 / % at risk 1% / Stop 6 pips / $12.50 per pip → **5.00 contracts**.
- **Figure 14.3 — M6E Position-Sizing Calculator:** Account $3,000.00 / % at risk 1% / Stop 12 pips / $1.25 per pip → **2.00 contracts**.

## Codifiable vs discretionary
**Codifiable (hard/objective):**
- 1% risk-per-trade cap.
- Contract-count formula (account × risk% ÷ stop$ ).
- Free trade bracket: −12 stop / +6 T1 → move stop to −6 (breakeven).
- RR trade bracket: −6 stop / +2 T1 → move stop to −4.
- Scale out half at first target; trade even lot sizes.
- Mandatory stop and mandatory target on every trade.

**Discretionary / judgment:**
- Which instrument(s) to specialize in.
- Whether scaling out suits the individual ("isn't right for everyone").
- Personal comfort with the 1% dollar amount (psychological, not the % itself).
- Deciding which news events to avoid.

## Cross-refs / open questions
- "Pip" and "tick" are used interchangeably throughout the figures (YM/ES stops are in "pips" in the calculator but "ticks" in the prose). The free-trade example is quoted in **pips** (−12/+6) while the RR-trade example is quoted in **ticks** (−6/+2) — verify whether these are two different scales or just inconsistent labeling in the source.
- The free trade (−12/+6) and RR trade (−6/+2) use different stop sizes than the ES sizing example (6-tick stop); which bracket pairs with which instrument is not explicitly mapped.
- "$1.25 per pip" micro contract (M6E) is the cited enabler of small-account trading.
- Links forward to Ch 15 (emotions/casino mentality) and Ch 16 (the codified plan, including the half-size days and no-trade zones).
