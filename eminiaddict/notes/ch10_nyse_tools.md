# Ch 10 — Tools for the NYSE

## Summary (3-5 lines)
This chapter defines the leading indicators Halsey uses during the NYSE session to enter precise measured-move (MM) trades and to read the "path of least resistance." It contrasts lagging indicators (moving-average-based, tell you what already happened) with leading indicators (predict future price and target). The toolkit is six items: Bank, Breadth, the Tick, Tick Hook, Time & Sales, and the Trend. Used together they build a "case to a jury" for bullish vs. bearish, layering evidence to confirm or oppose the daily trend.

## Key concepts & definitions
- **Lagging indicator:** tells you what has already happened; "almost all indicators are based one way or another on moving averages," which leads traders into chasing.
- **Leading indicator:** tells you what is going to happen and at what price. Goal: use only leading tools.
- **Bank:** nickname for the **Nasdaq banking index** — an index of **417 securities** (smaller local banks, bank corporations, financial institutions across the US). Not tradable (it's an index), so it gives a clean read on smaller financials being bought/sold intraday. Financials are the second-highest S&P 500 sector weighting (after tech).
- **Breadth:** the ratio of up volume vs down volume, and advancers vs decliners. NYSE and Nasdaq each have separate breadth readings.
  - Up volume = buying/pushing higher; down volume = selling/pushing lower.
  - Advancers = instruments bought/pushed higher; decliners = instruments sold/pushed lower.
  - Positive breadth = upward-trending market; negative breadth = downward-trending.
- **The Tick (NYSE tick):** the NYSE up/down ratio = number of stocks ticking up less the number ticking down. Metaphor: the market's "respirator" (inhale/exhale). Measures brief overbought/oversold moments.
- **Tick Hook:** when a brief overbought moment (high tick) turns into a brief oversold moment (low tick), or vice versa. Used to time entries and free/reduced-risk (RR) trades.
- **Time and Sales ("the tape"):** the receipt tape — real-time transactions; shows participation (contract volume) at key MM levels.
- **The Trend:** the daily trend and target — "the default direction of the market and the path of least resistance." The most powerful tool; other tools confirm or oppose it.

## Rules / setups / mechanics

### Bank — how to use (5 rules, verbatim intent)
1. In uptrends, if **Bank makes new highs by itself and the indices don't, Bank will eventually drag the indices higher — always trust Bank.**
2. If the **indices make new highs and Bank does not follow, do not trust the rally** (potential bull trap). Always trust Bank.
3. In downtrends, if **Bank makes new lows by itself and the indices don't, Bank will drag the indices lower — always trust Bank.**
4. If the **indices make new lows and Bank does not follow, do not trust the sell-off** (potential bear trap). Always trust Bank.
5. **Don't fight Bank.**

### Breadth — how to use
- **The Breadth Rule: you must always know where the breadth ratios started for the day at the opening bell.** Opening breadth confirms the direction for the day.
- Example given: a mid-day reading of **–10:1** looks weak in isolation, but if the **opening reading was –50:1** and it climbed from –50 to –10 over the day, the market is actually strengthening despite still-negative breadth. Without the open you can't read direction.
- Figure 10.2 example values: up vs down **volume ratio –1.2:1** (sellers winning) while advancers vs decliners **1.3:1** (more up-ticking instruments, buyers winning) — the two can conflict; the resolution is knowing the opening reference.

### The Tick — how to use
- **Best time frame to view the NYSE tick: the 1-minute chart** (want the smallest inhale/exhale). It's very fast; without a filter it gives false signals.
- **Best filter for the tick: a one-period simple moving average.**
- **+400 reading = a brief overbought moment; –400 reading = a brief oversold moment.**
- **+400 overbought tick = excellent time to sell** when in a series of MM shorts / downtrending.
- **–400 oversold tick = excellent time to buy** when in a series of MM longs / uptrending.

### Tick Hooks — how to use
- Purpose: enter with the highest probability of success and time free/RR trades.
- **Selling briefly overbought moments (high tick) = highest probability of an RR trade in a short.**
- **Buying briefly oversold moments (low tick) = highest probability of an RR trade in a long.**
- Mechanic (Figure 10.4): every time the tick moves **above +400**, price is sold at the traditional MM short — the high tick is the entry signal into the MM short, and it "quickly moves away from its initial entry." Multiple entry opportunities into one MM. Works in MM longs, MM shorts, and normal support/resistance levels.

### Time and Sales — how to use
- Watch the tape to see participation at MM levels; trade only in the direction of the MMs showing heavy participation.
- **Large blocks of contracts sold at an MM short confirms programs are attached to the setup** → confirms the entry has participation, which also validates its target (the selling programs have a specific profit-target price).
- If in long setups, you want to see heavy participation from buyers only.

### Trade the Trend
- Daily trend + target is the default direction / path of least resistance. Market won't always go straight to the target. Other tools tell you whether the day trades with the daily trend or against it.

### Using all tools together (the "jury" method)
- Analogy: an artist's painting / evidence in a trial — no single piece is decisive; together they make a "glaring bullish or bearish case." Ask: "If I had to make a case to a jury whether this market was bullish or bearish, what would my evidence be?" — forces an emotional step back / logical argument.
- **Hierarchy (stated twice, verbatim):** "The largest trend of daily MMs gives us the road map. Bank and breadth reinforce our bias for the day. The smaller series of MMs gives us our intraday trades and targets, and the tick and tape help us into our entries."
- More validating tools = more reliable / trending market.

## Figures / tables
- **Figure 10.1 — Historical Sector Weightings of the S&P 500: 1990 to Present** (through 2012). Sectors listed: Tech, Financials, Energy, H. Care, Cons Stap, Industrials, Cons Disc, Materials, Utilities, Telecom. Financials = second-highest weighting after Tech.
- **Figure 10.2 — Market Breadth Display:** up/down volume –1.2:1; advancers/decliners 1.3:1.
- **Figure 10.3 — Tick Chart** (top and bottom of range; +400 / –400). Source: thinkorswim®.
- **Figure 10.4 — Tick Hooks** (high ticks +400 entries into a traditional MM short). Source: thinkorswim®.
- **Figure 10.5 — Time and Sales Confirms Resistance** (large blocks sold as price moves down). Source: thinkorswim®.

## Codifiable vs discretionary
- **Codifiable:** Bank vs. indices divergence rules (new-high/new-low comparison → trust/don't-trust); tick at ±400 as OB/OS entry triggers; 1-minute tick chart + 1-period SMA filter; breadth positive/negative sign; the Breadth Rule (capture opening breadth as the reference); "tick hook above +400 → enter MM short" trigger; block-size threshold on the tape as a participation confirm (threshold itself not numerically specified).
- **Discretionary:** Bank's "will eventually drag" (no time horizon); interpreting conflicting breadth (–1.2:1 vs 1.3:1); judging what counts as a "large block" on the tape; weighting the six tools into a net bull/bear "jury" verdict; when a rally/sell-off is a "trap."

## Cross-refs / open questions
- Tick thresholds here are ±400 (intraday OB/OS entries). **Ch 11 adds the tick-extreme / divergence layer** (high/low tick of the day, reversal vs. divergence) — the two chapters are complementary: Ch 10 = entries; Ch 11 = trend-end/continuation.
- Depends on MM (measured move) construction from earlier chapters.
- **Open questions:** exact "Bank" symbol/data source (Nasdaq banking index of 417 names — likely the KBW/BKX-style index but unconfirmed); what contract-size threshold defines a "large block"; over what lookback "new highs/new lows" for Bank vs indices are measured.
- Reference video: "Tools of the Trade," http://eminiaddict.com/?p=5784.
