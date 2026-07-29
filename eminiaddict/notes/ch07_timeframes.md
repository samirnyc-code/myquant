# Ch 7 — Using Multiple Time Frames to Trade

## Summary (3-5 lines)
The chapter establishes the multi-timeframe framework for Measured Move (MM) trading and the goal of identifying the "path of least resistance." MM day trading uses three chart types — daily, 15-minute, and tick (called "micro") — which nest like Russian nesting dolls (micro MMs inside 15-minute MMs inside a daily MM). The core philosophy is "trade the trend until it fails" — never pick tops/bottoms. Larger time frames gate smaller ones: the weekly is most powerful and highest-odds; each larger trend is entered by drilling down to the next smaller time frame for an entry. Because MMs are price-based (not indicator-based), setups look the same across all time frames — only visibility differs.

## Key concepts & definitions
- **Path of least resistance**: When multiple time frames all point the same direction, that direction is the path of least resistance. Concept borrowed from Alexander Elder (author of *Come Into My Trading Room*, John Wiley & Sons, 2002), who lined up lagging indicators across weekly, daily, 4-hour, 1-hour, and 15-minute charts. Halsey adapts it but bases it on **price**, not lagging moving-average indicators.
- **Russian nesting dolls (matryoshka/babushka)** metaphor: Fibonacci-based MMs on micro, 15-minute, and daily levels nest — micro MMs inside 15-minute MMs inside a daily MM. Unlike physical dolls, the nesting is fluid/continuous, not fixed.
- **Three MM day-trading chart types**: daily, 15-minute, and tick. First two named for time values; the tick chart is called **micro** (shortest duration). The micro/tick chart is NOT time-based — it can be based on number of trades taken or the range of previous trades. "One is central to the MM methodology" (the tick/micro).
- **Trader categories by time frame**: Position traders use yearly, monthly, weekly. Swing traders use monthly, weekly, daily. Day traders use shortest increments — one-hour and 15-minute charts very common; beyond 15-minute they use even shorter, non-time-based charts.
- **Overbought/oversold rejection**: "There is no such thing as overbought, oversold, expensive, or cheap." These terms come from lagging indicators. Markets making new lows can keep making new lows; new highs can keep making new highs.
- **Why markets keep making new highs**: They are fueled by sellers at highs; they stop only when the last bears turn bullish at the highs ("the market climbs a wall of worry").
- **Why markets keep making new lows**: Fueled by buyers at lows; they stop only when the last bulls turn bearish at the lows.
- **"Trade the trend until it fails"**: You don't need to predict major turns. Programs that trade the markets don't pick tops/bottoms either — their algorithms are cause-and-effect based. Picking tops/bottoms only earns bragging rights and ego. Experienced traders know the market will show a trend change and give an entry into it.

## Rules / setups / mechanics
- **Which time frame to look at**: When trading price, "there is no such thing as the wrong time frame." Setups on the weekly are the same on the daily and 4-hour; setups on the 15-minute are the same on the 1-hour and 30-minute. Price is the same across all time frames; only which setups are *visible* differs.
- **Power ranking (hard rule)**: "The largest time frame is the most powerful, and the smallest time frame is the least powerful."
- **Rules for MMs (explicit list)**:
  - The biggest trend wins.
  - Trade the trend until it breaks.
  - If the trend breaks, a new trend will begin.
  - Respect the weekly trends the most and the micros the least.
- **How longer time frames gate the trade (drill-down entry logic)**:
  - **Weekly trend** = the largest trend visible zoomed all the way out with **10 to 20 years of data**. Most powerful; highest odds of completing its target; all other time frames are at its will. Typically long-term swing trades. The weekly chart IS the path of least resistance; all other trends are with or against it. Enter the weekly trend by drilling down to the **daily** trend entry opportunities. Fig 7.1: monthly S&P 500, traditional 50% MM short — draw from top of range trail to lows, wait for retrace to 50%; touching 50% gives a **123% target**. Took **three months to set up** the entry and **three months to complete** to target. When the weekly reacts to resistance and sells off hard from its 50% short, retail chases the sell-off (fear of missing); the squeeze produces a rally into the **next traditional 50% MM short**, drawn from all-time highs to the low — wait for price to return to the 50% retracement to sell. Daily MMs give the entry into the weekly target.
  - **Daily trend** = second most powerful; very high odds of completing target; all other time frames except weekly are at its will. Fig 7.2: daily S&P 500, traditional 50% MM long — took **six weeks to set up** entry, **six weeks to complete** to target. Daily trend takes **10 days to 3 months** to complete its target. Traded with 15-minute MMs; the **first 15-minute MM is the best entry** into the daily trend's target. Sometimes there are no entries into the daily trend (a new event or after-hours test can cause this) — don't chase.
  - **15-minute trend** = medium-term; "can be anywhere from 5 minutes to an hour long." Only requirement: you can see the details inside the daily MM trend. Takes **5 minutes to 10 days** to complete its target. This is where you spend the most time trading. **2 to 12 trade setups per day** depending on time of year. Key: remember the larger weekly/daily path of least resistance and trade the 15-minute MMs in that direction (filters opportunities).
  - **Micro trend** = generally weakest but "incredibly powerful"; a tool to enter the larger trends; at the will of all larger time frames. The micro MM is the **best entry into the 15-minute trend's target**. A micro completes its target within **1 to 30 minutes**; there can be hundreds of micros in a larger structure. The **first micro after a trend break is the best micro to trade**. The farther from the start of the larger trend, the less reliable the micros. Tick and "tick hooks" drill down further to time micro entries (covered in later chapters).
- **Why it matters**: Drilling from large to small fine-tunes entries and lets you hold to target with confidence. Example: at the start of a weekly long, off a daily MM pullback, entering on the 15-minute trend, you can have a **250-point target**. Knowing the target gives risk-reward, which gives positive expectation and makes it easier to pull the trigger.

## Figures / tables
- **Figure 7.1** — Weekly (monthly chart) Traditional Measured Move Short, S&P 500 (thinkorswim). 50% MM short → 123% target; 3 months to set up, 3 months to complete.
- **Figure 7.2** — Daily Traditional Measured Move Long, S&P 500 (thinkorswim). 6 weeks to set up, 6 weeks to complete.
- **Figure 7.3** — 15-Minute Measured Move Long (thinkorswim).
- **Figure 7.4** — Micro Measured Move Long (thinkorswim).
- (No numeric tables in this chapter; all numbers are inline.)

## Codifiable vs discretionary
**Codifiable:**
- Three chart types: daily, 15-minute, tick/micro.
- Power hierarchy weekly > daily > 15-minute > micro (respect weekly most, micro least).
- Traditional 50% MM: draw from range extreme, retrace to 50%, 123% target on completion.
- Time-to-complete envelopes per time frame: weekly (months); daily 10 days–3 months; 15-minute 5 min–10 days; micro 1–30 min.
- "First X after a trigger is best": first 15-minute MM is best entry into daily target; first micro after a trend break is the best micro; micro is best entry into 15-minute target.
- Path of least resistance = alignment of time frames (implementable as a directional filter).
- 2–12 setups per day expectation.

**Discretionary:**
- Judging when a 15-minute "trend" spans 5 min vs an hour (only requirement is "see the details inside the daily MM").
- Deciding when no daily entry exists (news event / after-hours test).
- Which micros are "reliable" as distance from trend origin grows.
- Trusting a support/resistance level as safe.

## Cross-refs / open questions
- Cross-ref Ch 6 (prior chapter): four real-world MMs and how they evolved.
- Tick and "tick hooks" for timing micro entries — deferred to later chapters.
- Ch 8 supplies the actual entry mechanics (front runs, first/second test, trend break) referenced by the "drill down for an entry" logic here.
- Video: "The Three Timeframes to Trade" — http://eminiaddict.com/?p=5580
- Open question: exact rule for "path of least resistance" alignment — which set of time frames must agree (Elder used weekly/daily/4h/1h/15m; Halsey's MM version uses weekly/daily/15-min/micro but doesn't state a strict N-of-M agreement threshold).
- Open question: the "123% target" from a 50% MM and the "250-point target" example are stated but the general target-projection formula is assumed from earlier chapters, not derived here.
