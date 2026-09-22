# Ch 11 — Tick Extremes and Divergences

## Summary (3-5 lines)
The tick divergence is Halsey's flagship strategy, derived from an observation during the 2008 crash. It distinguishes two kinds of daily tick extreme: the traditional reversal (tick and price both make the day's extreme together → profit-taking/reversal signal) and the divergence (price keeps making new extremes without a matching new tick extreme → trend continues). The divergence keeps you in a winning trend trade; its end plus a confirmed trend break signals a safe reversal entry. The "first opposing MM after a trend break + a matching tick extreme" is called one of his very best setups.

## Key concepts & definitions
- **Two types of tick extreme:**
  1. **Traditional / reversal:** the high or low tick of the day that **matches price but breaks trend** (fails to make new highs/lows).
  2. **Divergence:** the high or low tick of the day where price **continues its trend** (keeps making new highs/lows without a new matching tick extreme).
- **Traditional tick extreme (reversal), defined:** a high tick of the day that matches the price high but breaks trend and fails to make new highs; a low tick of the day that matches the price low but breaks trend and fails to make new lows.
- **Tick divergence, defined:** begins when a new high/low tick is made together with a new high/low in price at the same time — and then **the market continues to make new highs/lows in price without a new matching tick extreme.**
  - **What it signals:** the end of the traditional profit-taking signal and the **continuation of the trend.**
  - **Duration:** "It will last until the next time the tick and price make highs or lows together."
- **Bullish divergence:** price makes a high matching the day's highs; market keeps making new price highs **without a new high tick of the day** → bullish divergence begins; continues until a new high price and new high tick match again.
- **Bearish divergence:** the opposite — price makes new lows matching the day's lows without a new low tick of the day; continues until a new low price and new low tick match again.
- **Algo framing:** extreme tick + extreme price matching = a profit-taking signal for computer algorithms; the market making another new high (or new low, for bearish) ends that profit-taking signal. Trading divergences = "grabbing the coattails of the computer algorithms."
- **Origin:** observation made during the 2008 financial crash.

## Rules / setups / mechanics

### How to use a divergence
1. **If you are long and witness a bullish divergence, stay long until the next new high tick of the day.**
2. **If you are short and witness a bearish divergence, stay short until the next new low tick of the day.**
- If a divergence ends, it is a **profit-taking opportunity** — NOT automatically a reversal. **It is only a reversal if the trend breaks and confirms.**
- Divergences let you stay in an intraday swing trade with confidence.

### Trading the reversal safely (what happens if the trend breaks)
- **Dangerous way:** trying to pick the top/bottom on every new high/low tick.
- **Safe way:** wait for the opposing series of MMs to fail.
  - If you see a **high tick matching a high price of the day, wait for a series of longs to fail before selling short.**
  - If you see a **low tick matching a low price of the day, wait for a series of shorts to fail before going long.**
- **The very first entry after a trend break combined with a matching tick extreme of the day is "one of our very best setups"** — highest risk-reward ratio and highest participation. (Stated for both the high-tick/first-MM-short case and the low-tick/first-MM-long case.)
- Sequence (Figs 11.3→11.4, high side): high tick matches high price → trend breaks (series of MM longs broken) → high of day confirmed → next MM long fails, ending the potential divergence → sell the next MM short into the new downtrend.
- Sequence (Figs 11.5→11.6, low side): low tick matches low price → break of the micro MM shorts → lows in / reversal possible → buy the next MM long into the new uptrend.

### Summary rules (verbatim intent)
- The **first opposing MM is the best place for a reversal entry.**
- **Trade the new series of MMs until the next extreme tick or until the trend breaks.**
- Two capabilities delivered:
  1. On an extremely bullish/bearish trend day, the **divergence keeps you in the trade to maximize profit in the continuation.**
  2. It helps **identify a trend reversal** so you can exit as soon as the trend is over.
- Framed as the safe, rule-based way to "pick tops and bottoms" that traders are normally taught never to do.

## Figures / tables
(No numeric tables; all figures are thinkorswim® tick/price charts illustrating the rules.)
- **Figure 11.1 — High Tick of the Day Matches the High in Price** (traditional reversal signal).
- **Figure 11.2 — Market Makes New Highs after a High Tick** (bullish divergence begins; continues to new price highs until next high tick).
- **Figure 11.3 — Break in Trend** (high tick of day causes a break in the series of MM longs → high of day signaled).
- **Figure 11.4 — First Measured Move after a Divergence Ended** (next MM long failed → sell next MM short into new downtrend).
- **Figure 11.5 — Low Tick of the Day Ended Divergence** (low tick breaks micro shorts → lows in, reversal possible).
- **Figure 11.6 — First Entry after the Divergence Ended** (break of micro MM shorts → buy next MM long).

## Codifiable vs discretionary
- **Codifiable:** the two-class tick-extreme test (does the day's new tick extreme coincide with a new price extreme, or does price make a new extreme without a new tick extreme?); divergence-active flag and its termination condition (next simultaneous tick+price extreme); hold rules (stay long/short until next opposing new tick extreme); reversal gating (trend break + confirmation required before entry).
- **Discretionary:** what constitutes a "series of MMs" failing / a confirmed "trend break" (depends on MM construction and micro vs. traditional MM classification); identifying "micro shorts" vs. a full series; judging when a divergence "ends" vs. merely pauses.

## Cross-refs / open questions
- **Builds directly on Ch 10** (the NYSE tick, ±400 OB/OS entries, tick hooks) — Ch 11 adds the day's-extreme / divergence layer on top of the tick tool.
- Depends on the measured-move (MM) series construction and the "series fails / trend breaks" definition from earlier chapters — the reversal rules are only as codifiable as the MM-break definition.
- **Open questions:** no numeric tick threshold is given for a "high/low tick of the day" here (unlike the ±400 in Ch 10) — it is the running daily max/min tick, not a fixed level; confirm whether the intraday tick extreme resets daily and whether it's measured on the 1-min tick + 1-period SMA from Ch 10. Precise, objective definitions of "series of MM longs/shorts fails" and "trend breaks and confirms" are the main blockers to full codification.
- Reference video: "Tick Extremes & Divergences," http://eminiaddict.com/?p=5818.
